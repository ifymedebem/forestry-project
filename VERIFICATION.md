# Verification — 9 November 2026

Passed:

- Next.js production static export and TypeScript checking.
- 11 Python tests: boundary area / coordinate rejection, page-preserving extraction, LLM quotation grounding, PDF page references, NDVI validity / observation masks, COG offset harmonization, API token checks, date / PDF validation, queued processing, review history, portable source-linked reports, missing satellite evidence and HTML escaping.
- Python module compilation and Docker Compose configuration validation.
- Live Earth Search STAC and cloud-optimized GeoTIFF processing for the 121.62 ha example AOI in Acre, Brazil. Baseline: July–September 2022; monitoring: July–September 2024. Sixteen readable Sentinel-2 granules, valid NDVI medians 0.814 and 0.836, and 100% comparable pixel coverage on the declared 60 m grid. This check verifies that the data path runs, not that the screening method is scientifically validated. The sample dashboard is separate and remains illustrative.

Not verified:

- Visual browser QA: the supported `cua_repl.js` browser tool was not available. No alternate browser-control path was substituted.
- Full Docker/PostGIS/S3 stack: Compose configuration validates, but MinIO registry pulls were denied and Docker container creation hit this environment's disk quota. The temporary downloaded image was removed. Database / queue / storage behavior was exercised with SQLite and local files, not a running PostGIS / MinIO pair.
- Paid LLM extraction: no provider key was configured. Schema and source-grounding behavior were tested using controlled responses.
- OCR language coverage, multi-user identity, production resource isolation and disturbance-detection accuracy have not been validated.

The application is a functional starting version. Production backend deployment, identity integration and evaluation against independently labelled evidence remain separate work.
