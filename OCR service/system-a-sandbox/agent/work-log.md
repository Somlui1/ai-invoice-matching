# Work Log

## 2026-10-06T13:27:00+07:00
- Initialized agent canonical records in `agent/`.
- Ran baseline tests: `pytest web/test_portal.py` passed 32 tests.
- Ran baseline UI test: `node web/test_ui_logic.mjs .cache/fixture_DMS-20.json` passed 27 checks.

## 2026-10-06T13:35:00+07:00
- Restructured layout in `web/static/index.html` and styles in `web/static/styles.css`.
- Implemented `CaseStore` in `web/static/js/app.js` and master toggle in `web/static/js/bbox-overlay.js`.
- Verified test suite: 32 tests passed.

## 2026-10-06T13:50:00+07:00
- Clarified requirements with user: documents must be pulled from Paperless live API (not logs), before process there must be NO BBox, and after process results and BBoxes are displayed and stored in browser only.
- Created Implementation Plan artifact `paperless_process_bbox_plan.md` and received user approval.
- Modified `web/static/js/app.js`:
  - Updated `selectDoc(d)` and `selectUpload(u)` to explicitly clear all BBoxes and set unverified state before Process.
  - Eliminated automatic loading of server disk results upon document selection.
  - Ensured BBoxes and results render exclusively after Process completion or explicit browser case recall.
- Verified test suite:
  - `python -m pytest web/test_portal.py -q`: 32/32 passed.
  - `node web/test_ui_logic.mjs .cache/fixture_DMS-20.json`: 27/27 passed.
  - `python -m webapp check`: confirmed live Paperless connection (99 docs).
- Created walkthrough artifact `walkthrough.md`.
 
## 2026-10-06T14:05:00+07:00
- Developed batch test script `scripts/test_paperless_invoices.py` to test System A against Paperless-ngx documents tagged `invoice`.
- Queried live Paperless API: resolved tag `invoice` to ID `5` with 98 documents.
- Implemented individual case saving to `<out_dir>/DMS-<id>_result.json` adhering to Contract 3.0 schema.
- Implemented consolidated summary saving to `<out_dir>/summary.json` containing overall counts and rule pass/fail breakdown.
- Added CLI features: `--tag`, `--mode production|sandbox`, `--limit`, `--skip-existing`, `--quick`, `--doc-id`, `--out-dir`.
- Created Windows launcher `scripts/run_test_invoices.bat`.
- Verified execution with dry-run (`--limit 1 --mode sandbox --quick`) and verified `--skip-existing` caching behavior.
