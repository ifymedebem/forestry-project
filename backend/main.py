import json
import os
import secrets
import uuid
import io
import zipfile
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from shapely.errors import ShapelyError

from .geo import validate_boundary
from .report import report_html
from .store import Job, Project, Session, get_file, init_db, now, put_file, save_geometry

@asynccontextmanager
async def lifespan(app):
    init_db()
    yield

app = FastAPI(title='Canopy Evidence API', version='0.1.0', lifespan=lifespan)
allowed_origins = [s.strip() for s in os.getenv('CORS_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',')]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_methods=['GET', 'POST', 'PUT'], allow_headers=['Content-Type', 'Authorization'])

def auth(authorization: str | None = Header(default=None)):
    key = os.getenv('CANOPY_API_TOKEN')
    if key and (not authorization or not secrets.compare_digest(authorization, f'Bearer {key}')):
        raise HTTPException(401, 'A valid workspace API token is required.')

def find(session, project_id):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, 'Project not found.')
    return project

def serialize(project):
    return {key: getattr(project, key) for key in ('id', 'name', 'created_at', 'status', 'stage', 'boundary', 'area_ha', 'document', 'settings', 'result', 'reviews')}

async def read_limited(upload, maximum):
    data = await upload.read(maximum + 1)
    if len(data) > maximum:
        raise HTTPException(413, f'{upload.filename} exceeds the {maximum//1048576} MB limit.')
    return data

@app.get('/api/health')
def health():
    return {'status': 'ok', 'version': '0.1.0', 'workspace': 'single-tenant', 'auth_required': bool(os.getenv('CANOPY_API_TOKEN'))}

@app.get('/api/projects', dependencies=[Depends(auth)])
def projects():
    with Session() as session:
        return [serialize(p) for p in session.scalars(select(Project).order_by(Project.created_at.desc()))]

@app.post('/api/projects', dependencies=[Depends(auth)], status_code=201)
async def create_project(name: str = Form(..., min_length=2, max_length=120), document: UploadFile = File(...), boundary: UploadFile = File(...), baseline_start: date = Form(...), baseline_end: date = Form(...), monitoring_start: date = Form(...), monitoring_end: date = Form(...)):
    if not (date(2017, 1, 1) <= baseline_start <= baseline_end < monitoring_start <= monitoring_end <= date.today()):
        raise HTTPException(422, 'Choose non-overlapping baseline and monitoring dates from 2017 through today.')
    doc = await read_limited(document, 25 * 1048576)
    boundary_data = await read_limited(boundary, 5 * 1048576)
    filename = Path(document.filename or 'document').name
    if not filename.lower().endswith(('.pdf', '.txt')) or not doc:
        raise HTTPException(422, 'Upload a non-empty PDF or UTF-8 TXT document.')
    if filename.lower().endswith('.pdf') and not doc.startswith(b'%PDF'):
        raise HTTPException(422, 'The uploaded file is not a PDF.')
    if filename.lower().endswith('.txt'):
        try:
            doc.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise HTTPException(422, 'Text documents must use UTF-8 encoding.')
    try:
        geometry, area = validate_boundary(json.loads(boundary_data))
    except (ValueError, TypeError, KeyError, AttributeError, ShapelyError) as error:
        raise HTTPException(422, 'Invalid GeoJSON boundary: ' + str(error))
    project_id = str(uuid.uuid4())
    source = put_file(f'{project_id}/original.{filename.rsplit(".", 1)[-1].lower()}', doc, 'application/pdf' if filename.lower().endswith('.pdf') else 'text/plain')
    source['name'] = filename
    boundary_source = put_file(f'{project_id}/boundary.geojson', boundary_data, 'application/geo+json')
    settings = {key: value.isoformat() for key, value in {'baseline_start': baseline_start, 'baseline_end': baseline_end, 'monitoring_start': monitoring_start, 'monitoring_end': monitoring_end}.items()}
    settings['boundary_sha256'] = boundary_source['sha256']
    with Session.begin() as session:
        project = Project(id=project_id, name=name.strip(), boundary=geometry, area_ha=area, document=source, settings=settings, result={}, reviews={})
        session.add(project)
        save_geometry(session, project)
    with Session() as session:
        return serialize(find(session, project_id))

@app.get('/api/projects/{project_id}', dependencies=[Depends(auth)])
def project(project_id: str):
    with Session() as session:
        return serialize(find(session, project_id))

@app.post('/api/projects/{project_id}/analyze', dependencies=[Depends(auth)], status_code=202)
def analyze_project(project_id: str):
    with Session.begin() as session:
        project = session.scalar(select(Project).where(Project.id == project_id).with_for_update())
        if not project:
            raise HTTPException(404, 'Project not found.')
        if project.status in ('queued', 'processing'):
            raise HTTPException(409, 'Analysis is already running.')
        job_id = str(uuid.uuid4())
        session.add(Job(id=job_id, project_id=project.id))
        project.status, project.stage = 'queued', 'Queued for processing'
        # Previous decisions remain in the audit trail and are reset for the new run.
        old = dict(project.result or {})
        old['prior_reviews'] = [*old.get('prior_reviews', []), {'at': now(), 'run_id': old.get('run_id'), 'reviews': project.reviews or {}}] if project.reviews else old.get('prior_reviews', [])
        project.result, project.reviews = old, {}
        return {'job_id': job_id, 'status': 'queued'}

class Review(BaseModel):
    decision: str = Field(pattern='^(confirmed|dismissed|investigate)$')
    note: str = Field(default='', max_length=5000)

@app.put('/api/projects/{project_id}/reviews/{finding_id}', dependencies=[Depends(auth)])
def review(project_id: str, finding_id: str, value: Review):
    with Session.begin() as session:
        project = session.scalar(select(Project).where(Project.id == project_id).with_for_update())
        if not project:
            raise HTTPException(404, 'Project not found.')
        if project.status != 'complete':
            raise HTTPException(409, 'Wait for analysis to complete before reviewing.')
        if finding_id not in [f['id'] for f in (project.result or {}).get('findings', [])]:
            raise HTTPException(404, 'Finding not found.')
        reviews = dict(project.reviews or {})
        prior = reviews.get(finding_id, {})
        reviews[finding_id] = {**value.model_dump(), 'updated_at': now(), 'history': [*prior.get('history', []), {k: v for k, v in prior.items() if k != 'history'}] if prior else []}
        project.reviews = reviews
        return reviews[finding_id]

@app.get('/api/projects/{project_id}/document', dependencies=[Depends(auth)])
def document(project_id: str):
    with Session() as session:
        source = find(session, project_id).document
        return Response(get_file(source['key']), media_type='application/pdf' if source['name'].lower().endswith('.pdf') else 'text/plain; charset=utf-8', headers={'Content-Disposition': 'inline'})

@app.get('/api/projects/{project_id}/imagery/{period}', dependencies=[Depends(auth)])
def imagery(project_id: str, period: str):
    if period not in ('baseline', 'monitoring'):
        raise HTTPException(404)
    with Session() as session:
        project = find(session, project_id)
        run_id = (project.result or {}).get('run_id')
    try:
        return Response(get_file(f'{project_id}/runs/{run_id}/{period}.png'), media_type='image/png')
    except Exception:
        raise HTTPException(404, 'Composite image unavailable.')

@app.get('/api/projects/{project_id}/report', response_class=HTMLResponse, dependencies=[Depends(auth)])
def report(project_id: str):
    with Session() as session:
        return report_html(find(session, project_id))

@app.get('/api/projects/{project_id}/report-bundle', dependencies=[Depends(auth)])
def report_bundle(project_id: str):
    with Session() as session:
        project = find(session, project_id)
        if project.status != 'complete':
            raise HTTPException(409, 'Complete the analysis before exporting a report.')
        source_name = 'original.pdf' if project.document['name'].lower().endswith('.pdf') else 'original.txt'
        html = report_html(project).replace(f'/api/projects/{project.id}/document', source_name)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr('report.html', html)
            bundle.writestr(source_name, get_file(project.document['key']))
            bundle.writestr('boundary.geojson', json.dumps(project.boundary, indent=2))
            bundle.writestr('evidence-and-provenance.json', json.dumps({'project': serialize(project)}, indent=2))
            for period in ('baseline', 'monitoring'):
                try:
                    bundle.writestr(f'{period}-ndvi.png', get_file(f'{project.id}/runs/{project.result["run_id"]}/{period}.png'))
                except Exception:
                    pass
        return Response(archive.getvalue(), media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="canopy-review-bundle.zip"'})

# A built export is served by Python for a single-origin local installation.
static_root = Path(__file__).resolve().parent.parent / 'out'
if static_root.exists():
    app.mount('/', StaticFiles(directory=static_root, html=True), name='frontend')
