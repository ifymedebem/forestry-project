# Canopy — forest carbon evidence review

A working first version of the supplied architecture: Next.js / TypeScript, MapLibre, Python FastAPI, PostGIS, S3-compatible storage, a separate Python database-queue worker, page-linked document extraction, optional schema-validated LLM extraction, Sentinel-2 NDVI screening, reviewer decisions and an HTML report bundle.

The hosted Site is an interactive frontend preview. It starts with an explicitly fictional sample project. Sites does not run a Python server. For real processing, run the Python application below or connect the hosted interface to your separately hosted HTTPS API in Workspace settings.

## Run locally with the requested infrastructure

Requirements: Docker and Docker Compose, at least 4 GB RAM, internet access to image/package registries and the satellite services listed below.

```sh
cp .env.example .env
docker compose up --build -d
```

Open http://localhost:8000. The Python server serves the compiled frontend from the same origin. Open http://localhost:8000/docs for the API documentation. MinIO's local console is at http://localhost:9001. PostGIS and MinIO persist in named volumes.

For local loopback development, an empty workspace token is supported. Set `CANOPY_API_TOKEN` to a strong random value before allowing remote API access. Enter that value in Workspace settings. It is a single-workspace shared token, **not** a multi-user authentication system. Before production multi-user use, add an OIDC identity provider, server-side sessions, membership tables, per-project authorization and storage isolation.

Do not expose the development database or MinIO credentials to the internet. Configure HTTPS, a managed PostGIS database, S3 credentials scoped to one bucket, an allowlist of exact frontend CORS origins, backups and resource quotas for a production deployment. Pin image digests and dependency versions as part of that deployment.

## Run without Docker (development)

Install Python 3.12 and Node.js 22 or newer. Open this repository folder in VS Code.

### Windows / VS Code PowerShell

Run these commands one at a time from the repository root. Directly invoking the virtual environment avoids activation and PATH errors.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm ci
npm run build
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Keep that terminal open. In a second terminal in the same folder:

```powershell
.\.venv\Scripts\python.exe -m backend.worker
```

Open http://localhost:8000. If `py -3.12 --version` fails, install Python 3.12 before creating the environment.

### macOS / Linux

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
npm ci
npm run build
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In a second terminal from the same directory:

```sh
. .venv/bin/activate
python -m backend.worker
```

This mode uses SQLite and local files in `data/` unless `DATABASE_URL` and S3 settings are supplied. Use only one worker with SQLite. The default deployment in `compose.yaml` uses PostgreSQL/PostGIS and S3-compatible MinIO. Optional Tesseract (`tesseract-ocr` and the relevant language pack) enables scanned-document OCR; `OCR_LANGUAGE` defaults to `eng`.

## Review a project

1. Create a project with a PDF or UTF-8 TXT document and a WGS84 GeoJSON Polygon / MultiPolygon boundary. The initial limit is 25 MB / 250 pages for documents, 5 MB for boundaries and 0.1–50,000 ha for compact AOIs.
2. Choose non-overlapping baseline and monitoring windows from 2017 onward. Prefer matching seasons. Click **Run analysis** in Claims & evidence. The API queues a job; a separate worker processes it.
3. Inspect extracted passages and their page references. Without `OPENAI_API_KEY`, the document pipeline uses explicitly labelled pattern-assisted extraction. With a key, it uses `OPENAI_MODEL` and schema validation, then rejects quotations that cannot be located verbatim on the stated page. Large contexts fall back explicitly rather than silently truncating text. Scanned PDFs use Tesseract when available.
4. Inspect the boundary map, NDVI comparison and individual catalogue sources. The Esri basemap is an undated context mosaic, never dated evidence. Actual comparison images are cloud-masked NDVI composites and are labelled as such.
5. Confirm, dismiss or investigate each finding; record reviewer notes. A decision means the reviewer has assessed the signal. It does not automatically verify a carbon claim.
6. Download the report ZIP and extract it. Open `report.html` alongside `original.pdf` / `original.txt` so that page-linked local sources work. The bundle also contains the boundary, available NDVI images and the full evidence/provenance manifest.

## Satellite method: ndvi-screen-v1.0.0

Source: Element 84 Earth Search STAC, `sentinel-2-l2a` collection. No catalogue API key is required. Assets are public cloud-optimized GeoTIFFs.

- Query each time window for scenes with scene-level cloud cover ≤30%. This is a prefilter, not local coverage.
- The first catalogue page has at most 100 granules. Sample up to eight time-spaced granules per period. Catalogue pagination truncation is reported. This initial sampling is intentionally bounded and is not an exhaustive mosaic service.
- Reproject red, near-infrared and scene classification to an AOI-centered UTM grid at 60 m. Apply the STAC asset scale and offset, honoring `earthsearch:boa_offset_applied` so harmonized COGs do not receive an additive offset twice; use nearest-neighbor classification resampling. Include only SCL 4 / 5 (vegetation / bare surfaces), with nonnegative red and NIR reflectance.
- Compute NDVI and period medians from valid observations. Comparable pixels need at least two valid observations in **each** period. Flag baseline NDVI ≥0.50 with median decline ≥0.20.
- Report flagged hectares and comparable coverage. Under 60% comparable coverage produces an **insufficient evidence** finding, even if some pixels show change. A pixel count is an approximate screening area at the declared grid resolution.
- NDVI decline is a possible disturbance signal. Seasonality, drought, land management and residual atmospheric effects can produce similar signals. The method does not estimate forest canopy percentage, validate carbon stocks/credits or attribute fire/deforestation.
- Claims are linked to satellite context by category; semantic spatial/temporal claim alignment remains a human review task. Registry ingestion is not implemented and is explicitly reported as unavailable.

Full scene IDs, dates, STAC URLs, band-asset URLs, quality metrics, versioned thresholds, run settings, document SHA-256, extraction method and review history are retained in the result manifest. Original documents and boundaries are preserved. Each new analysis resets active review decisions while retaining prior decisions in provenance.

## Configuration

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy URL; production `postgresql+psycopg://...` |
| `DATA_DIR` | Development SQLite and file directory |
| `S3_BUCKET` | Enable S3 storage; omit for development local files |
| `S3_ENDPOINT_URL` | Optional endpoint for MinIO or another S3-compatible store |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` | Standard S3 settings or use an IAM role |
| `CANOPY_API_TOKEN` | Shared single-workspace bearer token |
| `CORS_ORIGINS` | Comma-separated exact frontend origins |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | Optional LLM extraction; key stays on the backend |
| `OCR_LANGUAGE` | Installed Tesseract language (default `eng`) |
| `NEXT_PUBLIC_API_URL` | Optional frontend API URL at build time; settings can override |

Outbound services: `earth-search.aws.element84.com`, `sentinel-cogs.s3.us-west-2.amazonaws.com` (asset hosts are determined by the STAC collection), `server.arcgisonline.com` for context maps, optional `api.openai.com`, Google Fonts for typography. Network errors become explicit limitations; TLS verification remains enabled.

## Verification

```sh
pip install pytest
python -m pytest tests -q
npm run typecheck
npm run build
docker compose config --quiet
```

Tests cover boundary rejection, page-level grounding, NDVI mask/threshold behavior, API authentication, file limits, queued job execution, decisions and portable report links. External catalogue/COG access is checked separately from deterministic tests. The environment's supported browser-control tool was unavailable, so visual browser QA was not performed.

## Architecture mapping and next steps

Project metadata, claims, findings, reviews and geometries live in PostGIS-backed project records; files and images live in S3. Queue rows are claimed using PostgreSQL `FOR UPDATE SKIP LOCKED`; one worker per task executes document and geospatial pipelines outside web requests. The API validates input and protects all project routes with the configured workspace token. Worker failures preserve explicit states and can be retried. Abandoned jobs are retried after a one-hour lease and stop after three attempts; a production worker should add a heartbeat and durable cancellation/time budgets before increasing workload limits.

For a production service, the remaining work includes multi-user identity and authorization, database migrations, a heartbeat/lease-renewal job system, isolated raster/OCR execution with CPU/memory budgets, automatic full STAC pagination and tile mosaicking, storage retention policies, provider quota handling, validated claim alignment, registry integrations, monitoring and evaluation against labelled disturbance data. Run snapshots are stored in queue records and composite files use per-run paths. The current interface and actual pipeline are a starting implementation, not a validated carbon-credit assurance product.
