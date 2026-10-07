# Changelog

All notable permanent changes to System A codebase are documented here.

## [2026-10-07] - `src/test-portal` reworked into a System A-only test screen (payload-driven, no batch/replay/demo)
### Changed
- **Purpose fixed to one thing**: the portal now tests `src/system_a/` and nothing else.  Documents come from real
  Paperless only, and everything the screen shows - every box and every value - is read out of System A's own final
  `aiva.system_a.result/3.0`.  A run that System A raises on is shown as that exception with its traceback; the
  portal has **no fallback and no partial result by design**.
- **`webapp/view.py` rewritten against the real payload** (probed from a genuine sandbox `orchestrator.validate()`
  run, not from the old code's assumptions): elements are read from `ocr.elements[]` (the earlier model looked for
  `pages[].elements`, which does not exist), final values from `normalized_fields`, lines/groups from
  `line_matching`, verdict from `recommendation`, Oracle lookup from `oracle_snapshot`, page geometry from `pages[]`
  (`width_pt`, `height_pt`, `rotation`, `render_dpi`) plus `package.coordinate_system`.  `incomplete` is now derived
  only from `system_errors`; a rule-chain `halted_by` is normal behaviour and no longer flags a partial payload.
- **Boxes are the payload's own**: each drawn box is one `ocr.elements[]` entry placed with its unmodified `bbox`
  under `pages[]` geometry, labelled by `field_name`, coloured by `element_type`; references in the result rows are
  `element_id`s resolved directly (`[D1-f-invoice_num]` style spans), so **there is no Locator/IoU matching step left
  in the portal**.  Element types selectable: `field`, `row`, `cell`, `table`, `section`, `signature`, `stamp`,
  `word`, `page`; defaults `field`, `row`, `signature`, `stamp` (choice kept in `localStorage`).
- **`webapp/app.py`, `build.py`, `__main__.py`, `store.py` rewritten** around that payload: API is
  `/api/meta`, `/api/health`, `/api/documents`(+`/refresh`), `/api/documents/{id}`, `POST …/process`,
  `GET …/result|payload|extraction`, `DELETE …/result`, `GET …/pdf`, `GET …/pages/{n}/image`, `/api/search`.
  Stored parts per document are now `state/view/payload.json` (`PARTS`), `payload.json` being the raw contract bytes.
  `check` prints what System A loads (mode, Standard, ruleset, vision model, Oracle backend) and the DMS/tag stats.
- **`webapp/static/app.js` + `index.html` rewritten** (576 lines JS) as a renderer of the view model: document list
  with recommendation colours, page images with the payload boxes, type chips, hover-to-highlight / click-to-pin
  driven by `element_id`, Final/Verify panels, traceback panel for a failing run, browser case store
  (`aiva.sysA.cases.v1`, `aiva.sysA.types.v1`), keyboard navigation (arrows, PgUp/PgDn, `f`, `o`, Esc).
- **`webapp/config.py` `ensure_system_a()`** resolves the project *root*: when `system_a.__file__` sits at
  `<root>/src/system_a/__init__.py` the parent (`<root>`, which holds `process_pdf.py` and `config/`) is put on
  `sys.path`, not `<root>/src` - the previous behaviour broke `import process_pdf` for the `inprocess` engine.
- **`webapp/catalog.py` `Doc`** carries `file_name` and `tagged` (from `PaperlessDoc`) and `_public()` exposes
  `file_name`, `file_class`, `tagged`, `correspondent`, `dms_url`, so the screen shows what the DMS actually says.
- **`SYSTEM_A_ENGINE=http` kept and documented**: the reading (file → `container.build_perception` →
  `aiva.extraction/2.0`) stays in this process because System A's `POST /v1/validations` requires an extraction in
  the body; only the validation runs remotely (`python -m system_a.cli serve --port 8080`, which does not load
  `<SYSTEM_A_HOME>/.env` by itself).  Default stays `inprocess`.
- **Test suite rewritten** (109 tests, 6.6 s, no network): `tests/synth.py` builds a synthetic
  `aiva.extraction/2.0` and System A's own sandbox `orchestrator.validate()` produces the genuine `result/3.0` the
  tests assert against - the portal is no longer tested against hand-made dictionaries.  Covers view (25), service
  (12), api (19), engine incl. System A's real API app (18), catalog (12), config (16), UI static (7).
- **`.env` / `.env.example` / `README.md` / `Makefile` / `requirements-dev.txt` / `.gitignore`** rewritten to the
  remaining configuration (`PAPERLESS_*`, `SYSTEM_A_*`, `WEBAPP_*`): no `BATCH_REPORT`, `PERCEPTION`,
  `REPLAY_*`, `PDF_DIR`, `WEBAPP_ORACLE_DATASET`, `DOC_SOURCE` and no playwright requirement.

### Removed
- **`webapp/batch.py`, `webapp/extraction.py`, `webapp/perception.py`, `webapp/placeholder.py`, `webapp/demo.py`,
  `webapp/paperless.py`, `webapp/pdfkit.py`** and the routes/controls that used them: batch/report.html sources,
  replay of another OCR engine's items, synthetic demo batch, stand-in SVG pages, portal-side Paperless and PDF code.
  Reading a document is System A's job now (`process_pdf.process_pdf(dms_id=…)`).

### Verified
- `pytest -q` in `src/test-portal` = **109/109**; `node --check webapp/static/app.js` clean (all 14 `$('id')`
  references exist in `index.html`).
- `python -m webapp check` against the real DMS: exit 0, 98 documents / 423 pages, tag `invoice` (id 5), Standard
  6.6 / ruleset v6.6-r4, mode production, ai litellm, engine inprocess.
- `SYSTEM_A_ENGINE=http python -m webapp check`: exit 0 against a running System A API (`/health/ready` =
  sandbox/sim/6.6/v6.6-r4).
- **One real document end to end through the portal** (`inprocess`, production, live VLM + real Oracle MCP):
  `POST /api/documents/15/process` → `done` in 55.7 s (VLM 43.5 s, Oracle 1.85 s), payload
  `aiva.system_a.result/3.0`, 1155 elements / 1155 boxes / 0 without bbox, V-07 `fail` (2× E11 Medium) →
  recommendation `MANUAL_REVIEW`; every `final.items[].refs` bbox compared against `ocr.elements[]` of the stored
  payload - **identical**.

## [2026-10-07] - `src/test-portal` starts on its own interpreter, whatever is on PATH (ERR-20261007-001)
### Fixed
- **`src/test-portal/run.bat` / `run.sh`**: the interpreter is now called by full path (`%~dp0.venv\Scripts\python.exe`, `.venv/bin/python`) instead of `call .venv\Scripts\activate.bat`.  `activate.bat` prepends `%VIRTUAL_ENV%\Scripts`, and that value is frozen when the venv is created - after this folder was moved out of `.../system-a/src/system-a-webapp`, it pointed at a path that no longer exists, so `python` silently resolved to another project's venv (Python 3.11 + uvicorn 0.41 + `websockets` 15.0.1) and `serve` died with `ModuleNotFoundError: No module named 'websockets.asyncio.compatibility'`.  Both scripts also fail with a clear message instead of a traceback when `.venv` cannot be created.
- **`src/test-portal/webapp/__main__.py`**: `uvicorn.run(..., ws="none")`.  The portal is plain HTTP + polling (no `WebSocket` anywhere in `app.js` or `webapp/`), so uvicorn no longer imports the `websockets` package at startup - a mismatched `websockets` build in the interpreter it happens to run under can no longer stop the application.

### Changed
- **`src/test-portal/.venv` rebuilt in place** with Python 3.14.2 at the folder's real location (its `pyvenv.cfg` and every `Scripts/*.exe` shim used to point at the old `system-a-webapp` path).  Installed: `requirements.txt` plus `pytest` and `jsonschema`, so `make test` now works inside the venv (it previously had no `pytest`).

## [2026-10-07] - Repository Hygiene of `src/test-portal` (runtime artifacts removed)
### Removed
- **`src/test-portal/data/`** (190 KB, 8 files): per-document results of old runs (`results/doc_23/`, `results/doc_24/` - `state/view/payload/extraction.json`).  Pure runtime output: it is gitignored, no code or record refers to those two documents, `ResultStore.__init__` re-creates `data/results` on demand, and the live `.env` runs with `WEBAPP_PERSIST=false` (the browser holds the cases) so the folder was not even read.
- **`src/test-portal/.pytest_cache/`**, **`src/test-portal/webapp/__pycache__/`**, **`src/test-portal/tests/__pycache__/`**: regenerable caches.
- Nothing of `webapp/` or `tests/` was deleted: every module of `webapp/` is imported at least once (checked by reference scan) and `tests/system_a_stub/config/**` is what `tests/conftest.py` copies to build its stub Standard.

## [2026-10-07] - Test Portal SYSTEM_A_HOME Path Resolution Fix
### Fixed
- **Path Resolution in `src/test-portal/.env`**:
  - Corrected `SYSTEM_A_HOME` from `.../system-a-sandbox/system-a` to `.../system-a-sandbox`.
- **Resilient Fallback in `src/test-portal/webapp/config.py`**:
  - Enhanced `ensure_system_a()` to search parent directories and `ROOT.parents[1]` fallback so test portal finds `system_a` even if paths have extra trailing directories.
- **Test Harness Auto-loading in `src/test-portal/tests/conftest.py`**:
  - Updated `_find_package()` to load `.env` and fallback to sandbox root automatically.

## [2026-10-06] - Parallel Batch Test Execution (Concurrency 5)
### Added
- **Multi-threaded Parallel Execution (`scripts/test_paperless_invoices.py`)**:
  - Added `--concurrency, -c` argument (default: 5) using `ThreadPoolExecutor`.
  - Enables concurrent document verification against Paperless-ngx API and GB300 LiteLLM backend.
  - Thread-safe console status streaming with single-line progress updates per completed document.
  - Automatic sorting of cases in `summary.json` by document ID regardless of completion order.
- **Quiet Mode in Pipeline (`process_pdf.py`)**:
  - Added `quiet: bool = False` flag to suppress console printing when invoked by concurrent batch runner.

## [2026-10-06] - Batch Test Automation for Paperless Invoices
### Added
- **Paperless Invoice Batch Test Script (`scripts/test_paperless_invoices.py`)**:
  - Dynamically resolves tag `invoice` (tag ID 5, 98 documents found) in Paperless-ngx API.
  - Sequentially executes System A verification (`process_pdf`) on every document.
  - Saves full Contract 3.0 result JSON for each case (`<out_dir>/DMS-<id>_result.json`).
  - Generates consolidated summary JSON (`<out_dir>/summary.json`) with pass/fail counts, rule breakdown, and case metrics.
  - Supports CLI flags: `--tag`, `--mode production|sandbox`, `--limit`, `--skip-existing`, `--quick`, `--doc-id`, `--out-dir`.
- **Windows Runner Batch Script (`scripts/run_test_invoices.bat`)**: 1-click launcher for batch verification.

## [2026-10-06] - Workflow & UI Portal Redesign
### Added
- **Browser-Only Case Store (`CaseStore`)**: Client-side storage in `localStorage` for verified cases (`web/static/js/app.js`), including listing, opening, deleting, exporting to JSON, and importing from JSON.
- **Master BBox Toggle**: Button in the viewer toolbar (`#btn-toggle-bbox`) allowing operators to toggle all bounding boxes on/off (`web/static/js/bbox-overlay.js`).
- **Middle Action Bar**: Placed prominent "▶ ประมวลผลเอกสาร" (Verify) button, mode selector (`production` / `sandbox`), and quick switch directly in the center panel header above the PDF stage (`web/static/index.html`).
- **Left Panel Catalog Switcher**: Added tabs to switch between "Paperless-ngx" documents and "เคสในเบราว์เซอร์" (Browser Stored Cases), with browser storage badges (`💾`).
- **Structured Right Panel Tabs**: Added primary group tabs for "📊 สรุปผล (Final Result)", "📝 ผล OCR (OCR Result)", "⚖️ ผล Validate (Validation Result)", and "💻 JSON" while maintaining all sub-tabs and DOM IDs for cross-highlighting and automated testing.

### Changed
- `web/static/js/app.js`: Enforced clean pre-process view without BBoxes or auto-loaded historical results upon document selection. BBoxes and results are now rendered exclusively after clicking "▶ ประมวลผลเอกสาร" or when explicitly opening a saved case from the browser cases tab.
- `web/static/index.html`: Restructured layout into left Paperless/Browser case catalog, center PDF preview + prominent verify button + toggleable BBox, and right structured Final/OCR/Validate panels.
- `web/static/styles.css`: Added styles for center action bar, prominent verify button, catalog switcher, browser cases store management, bbox toggle button, and primary result tabs.
- `web/static/js/bbox-overlay.js`: Added `toggleMaster()` and `isMasterVisible()` functions.
- `web/static/js/panels.js`: Added browser storage indicators to catalog items.
