import html

def report_html(project):
    e = lambda value: html.escape(str(value))
    result = project.result or {}
    claims = result.get('claims', [])
    findings = result.get('findings', [])
    satellite = result.get('satellite') or {}
    reviews = project.reviews or {}
    rows = ''.join(f'<tr><td>{e(c["id"])}</td><td>{e(c["quote"])}<br><a href="/api/projects/{e(project.id)}/document#page={c["page"]}">Document p. {c["page"]}</a></td><td>{e(c["status"])}</td></tr>' for c in claims)
    items = ''.join(f'<article><h3>{e(f["title"])}</h3><p>{e(f["description"])}</p><p>Status: {e(f["status"])} · Rule: {e(f["rule"])}</p><p>Reviewer: {e(reviews.get(f["id"], {}).get("decision", "pending"))}</p><p>{e(reviews.get(f["id"], {}).get("note", ""))}</p></article>' for f in findings)
    sources = ''.join(f'<li><a href="{e(s["url"])}">{e(s["id"])}</a> · {e(s["datetime"])} · {e(s["period"])}</li>' for s in satellite.get('sources', []))
    limitations = ''.join(f'<li>{e(value)}</li>' for value in result.get('limitations', []))
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>{e(project.name)} — Canopy review</title><style>body{{font:16px/1.6 system-ui;max-width:1000px;margin:60px auto;padding:0 24px;color:#203b32}}h1{{font-size:38px}}table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;border-bottom:1px solid #ddd;padding:14px;vertical-align:top}}article{{border:1px solid #ddd;padding:20px;margin:14px 0}}a{{color:#14745c}}small{{color:#65776e}}@media print{{button{{display:none}}body{{margin:0;font-size:11px}}}}</style><body><small>CANOPY / SOURCE-LINKED REVIEW</small><h1>{e(project.name)}</h1><p>Area: {e(project.area_ha)} ha · Run: {e(result.get('run_id', 'not analyzed'))} · Generated: {e(result.get('finished_at', '—'))}</p><p>Screening supports human review. A flag is not proof of deforestation or a finding of carbon-credit validity.</p><h2>Findings and review decisions</h2>{items or '<p>No completed findings.</p>'}<h2>Extracted document claims</h2><p>Method: {e(result.get('extraction_method', 'pending'))}</p><table><tr><th>Claim</th><th>Quoted source</th><th>Assessment</th></tr>{rows}</table><h2>Satellite evidence</h2><p>{e(satellite.get('interpretation', 'Satellite analysis unavailable'))}. Comparable coverage: {satellite.get('valid_coverage', 0)*100:.1f}%. Threshold-exceeding area: {satellite.get('flagged_ha', 0)} ha.</p><ul>{sources}</ul><h2>Methodology and limitations</h2><ul>{limitations}</ul><h2>Provenance</h2><p>Document SHA-256: {e((project.document or {}).get('sha256', '—'))}</p><p>Rule version: {e(satellite.get('rule_version', 'not run'))}. Run settings: {e(project.settings)}</p><p>Registry records were not imported. No registry conclusions were made.</p><button onclick="window.print()">Print / Save as PDF</button></body></html>'''

