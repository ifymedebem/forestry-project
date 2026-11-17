import io
import json
import os
import tempfile
import zipfile

os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='canopy-tests-')
os.environ.pop('DATABASE_URL', None)
os.environ.pop('S3_BUCKET', None)
os.environ.pop('OPENAI_API_KEY', None)
os.environ.pop('CANOPY_API_TOKEN', None)

import numpy as np
import pytest
from fastapi.testclient import TestClient
from backend.claims import extract_claims, extract_pages
from backend.geo import compare_arrays, reflectance, validate_boundary
from backend.main import app
from backend.store import Job, Project, Session, init_db
from backend.worker import run_once

BOUNDARY = {'type': 'Polygon', 'coordinates': [[[-70.421, -8.991], [-70.411, -8.991], [-70.411, -8.981], [-70.421, -8.981], [-70.421, -8.991]]]}
TEXT = 'The project encompasses 120 hectares of tropical forest. No significant forest disturbance occurred during the monitoring period.\fCarbon stocks were measured through permanent field plots.'

@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv('CANOPY_API_TOKEN', raising=False)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    init_db()
    with Session.begin() as session:
        session.query(Job).delete()
        session.query(Project).delete()
    with TestClient(app) as client:
        yield client

def upload(client, **overrides):
    data = {'name': 'Test Forest Project', 'baseline_start': '2022-06-01', 'baseline_end': '2022-09-30', 'monitoring_start': '2024-06-01', 'monitoring_end': '2024-09-30', **overrides}
    return client.post('/api/projects', data=data, files={'document': ('project.txt', TEXT.encode(), 'text/plain'), 'boundary': ('boundary.geojson', json.dumps(BOUNDARY).encode(), 'application/json')})

def fake_analysis(boundary, settings):
    return {'valid_coverage': 0.85, 'flagged_ha': 2.16, 'interpretation': 'possible disturbance', 'rule_version': 'ndvi-screen-v1.0.0', 'sources': [{'id': 'test-scene', 'url': 'https://example.com/scene', 'datetime': '2024-07-01T00:00:00Z', 'period': 'monitoring'}], 'limitations': ['Synthetic raster fixture, not live satellite evidence.']}, {}

def test_boundary_area_and_crs():
    geometry, area = validate_boundary(BOUNDARY)
    assert geometry['type'] == 'Polygon'
    assert 120 < area < 123
    with pytest.raises(ValueError):
        validate_boundary({'type': 'Point', 'coordinates': [-70, -9]})
    with pytest.raises(ValueError):
        validate_boundary({'type': 'Polygon', 'coordinates': [[[700, 90], [701, 90], [701, 91], [700, 90]]]})

def test_page_preservation_and_claim_grounding():
    pages, warnings = extract_pages(TEXT.encode(), 'project.txt')
    claims, method, limitations = extract_claims(pages)
    assert len(pages) == 2
    assert any(c['page'] == 2 and 'Carbon' in c['quote'] for c in claims)
    assert all(c['quote'] in pages[c['page']-1]['text'] for c in claims)
    assert method == 'pattern-assisted extraction'

def test_llm_rejects_unquoted_passages(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-only-placeholder')
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {'choices': [{'message': {'content': json.dumps({'claims': [{'page': 1, 'quote': 'This quotation does not occur in the source.', 'summary': 'Invented forest cover', 'category': 'forest cover'}, {'page': 1, 'quote': 'The forest contains 120 hectares.', 'summary': 'Project area', 'category': 'project area'}]})}}]}
    monkeypatch.setattr('backend.claims.httpx.post', lambda *args, **kwargs: Response())
    claims, method, warnings = extract_claims([{'page': 1, 'text': 'The forest contains 120 hectares.'}])
    assert len(claims) == 1
    assert claims[0]['title'] == 'Project area'
    assert any('Rejected' in warning for warning in warnings)

def test_pdf_page_references():
    import fitz
    pdf = fitz.open()
    pdf.new_page().insert_text((40, 60), 'Forest cover remained intact throughout the monitoring year.')
    pdf.new_page().insert_text((40, 60), 'Carbon stock measurements were made in permanent sample plots.')
    pages, warnings = extract_pages(pdf.tobytes(), 'project.pdf')
    claims, _, _ = extract_claims(pages)
    assert len(pages) == 2
    assert any(c['page'] == 2 for c in claims)

def test_ndvi_masks_and_observation_counts():
    baseline = np.array([[.8, .8], [.8, np.nan]])
    monitoring = np.array([[.4, .4], [.7, .2]])
    inside = np.array([[True, True], [True, True]])
    counts = np.array([[2, 1], [3, 2]])
    result = compare_arrays(baseline, monitoring, inside, .36, counts, counts)
    assert result['flagged_ha'] == .36
    assert result['valid_coverage'] == .5
    assert not result['flag_mask'][0, 1]  # one observation cannot support a flag
    assert not result['flag_mask'][1, 1]  # no data is never interpreted as disturbance

def test_harmonized_cogs_do_not_receive_double_boa_offset():
    asset = {'raster:bands': [{'scale': .0001, 'offset': -.1}]}
    assert np.isclose(reflectance(np.array([500.]), asset, {'earthsearch:boa_offset_applied': True})[0], .05)
    assert np.isclose(reflectance(np.array([1500.]), asset, {'earthsearch:boa_offset_applied': False})[0], .05)

def test_api_authentication(client, monkeypatch):
    monkeypatch.setenv('CANOPY_API_TOKEN', 'unit-test-workspace-token')
    assert client.get('/api/health').status_code == 200
    assert client.get('/api/projects').status_code == 401
    assert client.get('/api/projects', headers={'Authorization': 'Bearer unit-test-workspace-token'}).status_code == 200

def test_input_dates_and_content(client):
    assert upload(client, baseline_end='2024-07-01').status_code == 422
    r = client.post('/api/projects', data={'name': 'Test', 'baseline_start': '2022-01-01', 'baseline_end': '2022-02-01', 'monitoring_start': '2024-01-01', 'monitoring_end': '2024-02-01'}, files={'document': ('fake.pdf', b'not a PDF'), 'boundary': ('boundary.json', json.dumps(BOUNDARY))})
    assert r.status_code == 422

def test_queued_pipeline_review_and_portable_report(client, monkeypatch):
    monkeypatch.setattr('backend.worker.analyze', fake_analysis)
    response = upload(client)
    assert response.status_code == 201, response.text
    project_id = response.json()['id']
    assert len(response.json()['document']['sha256']) == 64
    assert client.post(f'/api/projects/{project_id}/analyze').status_code == 202
    assert client.post(f'/api/projects/{project_id}/analyze').status_code == 409
    assert run_once()
    project = client.get(f'/api/projects/{project_id}').json()
    assert project['status'] == 'complete'
    assert len(project['result']['claims']) >= 3
    assert project['result']['findings'][0]['status'] == 'needs review'
    review = client.put(f'/api/projects/{project_id}/reviews/FND-001', json={'decision': 'investigate', 'note': 'Inspect dry-season context.'})
    assert review.status_code == 200
    review = client.put(f'/api/projects/{project_id}/reviews/FND-001', json={'decision': 'confirmed', 'note': 'Source reviewed.'})
    assert len(review.json()['history']) == 1
    bundle = client.get(f'/api/projects/{project_id}/report-bundle')
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        html = archive.read('report.html').decode()
        assert 'original.txt#page=' in html
        assert f'/api/projects/{project_id}/document' not in html
        assert archive.read('original.txt') == TEXT.encode()
        assert 'Source reviewed.' in html
    assert client.post(f'/api/projects/{project_id}/analyze').status_code == 202
    assert run_once()
    project = client.get(f'/api/projects/{project_id}').json()
    assert project['reviews'] == {}
    assert project['result']['prior_reviews'][0]['reviews']['FND-001']['decision'] == 'confirmed'
    with Session() as session:
        assert session.query(Job).filter(Job.result.is_not(None)).count() == 2

def test_missing_satellite_data_stays_insufficient(client, monkeypatch):
    def unavailable(*args):
        raise ValueError('No readable observations')
    monkeypatch.setattr('backend.worker.analyze', unavailable)
    project_id = upload(client).json()['id']
    client.post(f'/api/projects/{project_id}/analyze')
    assert run_once()
    project = client.get(f'/api/projects/{project_id}').json()
    assert project['status'] == 'complete'
    assert project['result']['findings'][0]['status'] == 'insufficient evidence'
    assert any('No satellite conclusion' in line for line in project['result']['limitations'])

def test_report_escapes_reviewer_markup(client, monkeypatch):
    monkeypatch.setattr('backend.worker.analyze', fake_analysis)
    project_id = upload(client).json()['id']
    client.post(f'/api/projects/{project_id}/analyze')
    run_once()
    client.put(f'/api/projects/{project_id}/reviews/FND-001', json={'decision': 'investigate', 'note': '<script>alert(1)</script>'})
    html = client.get(f'/api/projects/{project_id}/report').text
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;' in html
