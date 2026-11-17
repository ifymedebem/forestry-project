"""A separate, database-backed worker. Start with python -m backend.worker."""
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from .claims import extract_claims, extract_pages
from .geo import analyze, RULE_VERSION
from .store import Job, Project, Session, get_file, init_db, now, put_file

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('canopy.worker')

def stage(project_id, value):
    with Session.begin() as session:
        session.get(Project, project_id).stage = value

def process(job_id, project_id):
    with Session() as session:
        project = session.get(Project, project_id)
        document, boundary, settings = project.document, project.boundary, project.settings
        prior_reviews = (project.result or {}).get('prior_reviews', [])
    stage(project_id, 'Extracting cited document claims')
    pages, limitations = extract_pages(get_file(document['key']), document['name'])
    claims, method, extraction_warnings = extract_claims(pages)
    limitations += extraction_warnings
    put_file(f'{project_id}/runs/{job_id}/pages.json', __import__('json').dumps(pages).encode(), 'application/json')
    stage(project_id, 'Building cloud-masked satellite composites')
    satellite, images = {}, {}
    try:
        satellite, images = analyze(boundary, settings)
        limitations += satellite.get('limitations', [])
        for label, data in images.items():
            put_file(f'{project_id}/runs/{job_id}/{label}.png', data, 'image/png')
    except Exception as error:
        log.warning('Satellite analysis failed for %s: %s', project_id, type(error).__name__)
        limitations.append(f'Satellite evidence unavailable: {str(error)[:300]}. No satellite conclusion can be drawn.')
    stage(project_id, 'Applying evidence rules')
    coverage = satellite.get('valid_coverage', 0)
    flags = satellite.get('flagged_ha', 0)
    findings = []
    if coverage < 0.6:
        findings.append({'id': 'FND-001', 'title': 'Insufficient satellite evidence', 'description': 'Comparable cloud-masked coverage is below the 60% screening requirement, or imagery could not be processed. Expand the date windows and review source availability.', 'status': 'insufficient evidence', 'rule': RULE_VERSION, 'claim_ids': []})
    else:
        findings.append({'id': 'FND-001', 'title': 'Possible vegetation disturbance' if flags else 'No threshold exceedance in observed pixels', 'description': f'{flags:,.2f} ha exceed the NDVI decline threshold across {coverage:.0%} of the boundary with comparable observations. Review dates, seasonality and imagery before interpreting the signal.', 'status': 'needs review' if flags else 'screened', 'rule': RULE_VERSION, 'claim_ids': [c['id'] for c in claims if c['category'] in ('forest cover', 'disturbance')]})
    for claim in claims:
        # The first version does not invent spatial/temporal alignment from a quotation.
        claim['status'] = 'context available' if coverage >= 0.6 and claim['category'] in ('forest cover', 'disturbance') else 'requires review'
    limitations.append('Claims require human assessment of spatial and temporal alignment. Carbon, area and monitoring statements are not automatically verified by NDVI screening.')
    result = {'run_id': job_id, 'finished_at': now(), 'claims': claims, 'extraction_method': method, 'findings': findings, 'satellite': satellite, 'limitations': limitations, 'prior_reviews': prior_reviews, 'provenance': {'document_sha256': document['sha256'], 'rules': RULE_VERSION, 'settings': settings, 'registry': 'not imported'}, 'pages': [{'page': p['page'], 'characters': len(p['text'])} for p in pages]}
    with Session.begin() as session:
        project = session.get(Project, project_id)
        project.result, project.status, project.stage = result, 'complete', 'Ready for human review'
        job = session.get(Job, job_id)
        job.status, job.result = 'complete', result

def run_once():
    # PostgreSQL SKIP LOCKED permits independent workers without double claiming.
    with Session.begin() as session:
        expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        stale = session.scalars(select(Job).where(Job.status == 'running', Job.started_at < expired)).all()
        for job in stale:
            if job.attempts >= 3:
                job.status, job.error = 'failed', 'Worker lease expired after three attempts.'
                project = session.get(Project, job.project_id)
                project.status, project.stage = 'failed', 'Analysis interrupted. Start another run.'
            else:
                job.status = 'queued'
        job = session.scalar(select(Job).where(Job.status == 'queued').order_by(Job.created_at).with_for_update(skip_locked=True).limit(1))
        if not job:
            return False
        job.status, job.started_at, job.attempts = 'running', now(), job.attempts + 1
        session.get(Project, job.project_id).status = 'processing'
        job_id, project_id = job.id, job.project_id
    try:
        process(job_id, project_id)
    except Exception as error:
        log.exception('Analysis failed for %s', project_id)
        with Session.begin() as session:
            job = session.get(Job, job_id)
            job.status, job.error = 'failed', str(error)[:500]
            project = session.get(Project, project_id)
            project.status, project.stage = 'failed', 'Analysis failed: ' + str(error)[:300]
    return True

if __name__ == '__main__':
    init_db()
    while True:
        if not run_once():
            time.sleep(2)

