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
## 2026-10-06T14:05:00+07:00
- Developed batch test script `scripts/test_paperless_invoices.py` to test System A against Paperless-ngx documents tagged `invoice`.
- Queried live Paperless API: resolved tag `invoice` to ID `5` with 98 documents.
- Implemented individual case saving to `<out_dir>/DMS-<id>_result.json` adhering to Contract 3.0 schema.
- Implemented consolidated summary saving to `<out_dir>/summary.json` containing overall counts and rule pass/fail breakdown.
- Added CLI features: `--tag`, `--mode production|sandbox`, `--limit`, `--skip-existing`, `--quick`, `--doc-id`, `--out-dir`.
- Created Windows launcher `scripts/run_test_invoices.bat`.
- Verified execution with dry-run (`--limit 1 --mode sandbox --quick`) and verified `--skip-existing` caching behavior.

## 2026-10-06T16:27:00+07:00
- Enhanced `process_pdf.py` with `quiet: bool = False` flag to suppress console printing cleanly during concurrent execution.
- Updated `scripts/test_paperless_invoices.py` to support multi-threaded concurrency using `ThreadPoolExecutor` (default `--concurrency 5`).
- Implemented single-line progress streaming to terminal without race conditions or text interleaving.
- Ensured cases list in `summary.json` is consistently sorted by `doc_id`.
- Verified parallel execution in sandbox mode (`--limit 2 --concurrency 2`), confirming total time was bound by slowest document (73.8s) rather than sequential accumulation (98.8s).
- Ran regression test suite: 36/36 tests passed.

## 2026-10-07T08:24:00+07:00
- Investigated `run.bat` failure in `src/test-portal`: error "no system_a package under .../system-a-sandbox/system-a".
- Verified that `run.bat` already activates `.venv\Scripts\activate.bat`. The issue was an invalid trailing `/system-a` path in `src/test-portal/.env`.
- Corrected `SYSTEM_A_HOME` in `src/test-portal/.env` to point to `c:/Users/wajeepradit.p/git/Invoice-auto-matching/OCR service/system-a-sandbox`.
- Updated `ensure_system_a` in `src/test-portal/webapp/config.py` and `_find_package` in `src/test-portal/tests/conftest.py` with parent and fallback candidate scanning for higher resilience.
- Verified `python -m webapp check` passed cleanly (99 docs, 424 pages).
- Verified `pytest -q` in `src/test-portal` passed 93/93 tests.
- Verified root `pytest -q` passed 36/36 tests.

## 2026-10-07T08:32:00+07:00
- Audited `src/test-portal` for files that are not needed to run the portal, by import analysis (AST closure over `webapp/` + `tests/`) instead of by name.
- Confirmed the portal loads 23 modules of `system_a` through `SYSTEM_A_HOME`, and that System A itself needs `<SYSTEM_A_HOME>/config/standards/v6.6/*.yaml` (always), `config/prompts/vision_*.md` (live perception) and `config/prompts/v05/v07/v08*.md` (`SYSTEM_A_AI_MODE=litellm`).
- Established that `data/` is runtime output only: `ResultStore.__init__` does `mkdir(parents=True)`, every test passes `data_dir=tmp_path/...`, and `.env` sets `WEBAPP_PERSIST=false`; no file in the repository references `src/test-portal/data`.
- Deleted `data/` (stale `doc_23` / `doc_24` results), `webapp/__pycache__/`, `tests/__pycache__/` and `.pytest_cache/`; the folder went from 106 MB to 105 MB (the remaining 105 MB is `.venv/`, which `run.bat` recreates).
- Kept `tests/` deliberately: `python -m pytest -q` in `src/test-portal` = 93/93 passed both before and after the cleanup (9-10 s), and `make test` / `make e2e` depend on it.
- Verified `ResultStore(Path('data'))` recreates `data/results` on its own, so the deletion cannot break a start, then removed the empty folder again.
- Noted for later: `.venv` of the portal has no `pytest` (only `requirements.txt` is installed there), so the suite runs with the machine Python; `python -m pip install -r requirements-dev.txt` inside `.venv` would make `make test` work from the venv.

## 2026-10-07T08:42:00+07:00
- Reproduced the user's `run.bat` crash (`ModuleNotFoundError: No module named 'websockets.asyncio.compatibility'`) and found it was **not** a portal bug: the traceback showed `AppData\Local\hermes\hermes-agent\venv` / Python 3.11, i.e. the wrong interpreter.
- Root cause: `.venv/Scripts/activate.bat` sets `PATH=%VIRTUAL_ENV%\Scripts;%PATH%` with a `VIRTUAL_ENV` frozen at `.../system-a-sandbox/system-a/src/system-a-webapp/.venv` - a folder that no longer exists after the move to `src/test-portal`, so activation added nothing and `python` fell back to the first venv on PATH.  Proved it with a probe batch: `where python` returned the same hermes interpreter before and after `call .venv\Scripts\activate.bat`.
- Secondary cause: uvicorn's default `ws="auto"` imports `websockets` at startup although the portal never opens a WebSocket (grep over `app.js` + `webapp/` found none), so an interpreter whose `websockets` build does not match its uvicorn cannot start the server at all.
- Fixed `run.bat` and `run.sh` to call the venv interpreter by full path, and `webapp/__main__.py` to pass `ws="none"` (checked `WS_PROTOCOLS["none"] is None` and that `import_from_string` returns non-strings unchanged, in uvicorn 0.41 and 0.54).
- Rebuilt `.venv` with Python 3.14.2 at the real path and installed `requirements.txt` + `pytest` + `jsonschema` (PyPI reachable: 200 in 1.5 s), which also replaced the stale `Scripts/*.exe` shims and `pyvenv.cfg`.
- Verified: `pytest -q` in `src/test-portal` = 93/93 with the new venv (8.3 s); `webapp check` = 99 documents / 424 pages, exit 0; `webapp serve` answered `GET /` 200 and `/api/health` `ok:true` **with the hermes interpreter that used to crash**; the probe batch now prints `.venv\Scripts\python.exe` + uvicorn 0.54.0.
- Cleanup: killed the test server (8090 free, only TIME_WAIT left) and removed `.pytest_cache`, `__pycache__`, the empty `data/` and the temporary probe batch.

## 2026-10-07T10:24:00+07:00
- Reworked `src/test-portal` into a System A-only test screen: documents from real Paperless, everything shown read out of System A's final `aiva.system_a.result/3.0`; deleted `batch/extraction/perception/placeholder/demo/paperless/pdfkit` modules and their routes/controls.
- Probed the **real** payload first (sandbox `orchestrator.validate()` on synthetic input) instead of trusting the old view model: elements live in `ocr.elements[]` (not `pages[].elements`), final values in `normalized_fields`, lines in `line_matching.groups[]`, verdict in `recommendation`, Oracle in `oracle_snapshot`. Rewrote `webapp/view.py` on that structure and rewrote `webapp/static/app.js` (576 lines) + `index.html` as a renderer of it.
- Fixed `config.ensure_system_a()` to return the project **root** (`<root>` when the package is at `<root>/src/system_a`) - the old return value (`<root>/src`) made `import process_pdf` impossible for the `inprocess` engine.
- Rewrote the suite: `tests/synth.py` (synthetic `aiva.extraction/2.0`) + `tests/doubles.py` + `conftest.make_harness()`; every test asserts the portal against a payload System A itself produced. Result: **109 passed in 6.64 s** (view 25, api 19, engine 18, config 16, catalog 12, service 12, ui_static 7), no VLM/Oracle/Paperless touched.
- Live verification: `webapp check` exit 0 (98 docs / 423 pages, tag invoice id 5, Standard 6.6 / v6.6-r4, mode production, engine inprocess); `SYSTEM_A_ENGINE=http webapp check` exit 0 against `python -m system_a.cli serve --port 8080` (`/health/ready` = sandbox/sim).
- Live single-document run through the running portal: doc 15 (one JPEG page) → `done` in 55.7 s with real LiteLLM Qwen-VL + real Oracle MCP; payload had 1155 elements, 1155 boxes, 0 element without bbox, V-01..V-06/V-08/V-09 pass, V-07 fail (2x E11 Medium) → `MANUAL_REVIEW`; 8 of 9 final items carry refs and **each ref's bbox equals the payload's** (`pages[0]`: 595.69x843.75 pt, rotation 0, render_dpi 150). `/pages/1/image` 200 (3 MB PNG at 150 DPI), `/extraction` 200, `/search` returns `{q, ids}`.
- Caught a stale server during the live check: port 8090 was still held by a portal instance started **before** the rework, so `/api/health` answered with the old shape (`perception`, `batch`, `pdfs_cached`) while the new process failed to bind (WinError 10048). Killed the old PID and re-verified against the new build - documented as ERR-20261007-003.
- Minor UI fix from the live data: Paperless does not report `page_count` for image documents, so `pages_total` is null until the file is read; the list/header now show `?` instead of `null`.
- Docs/records: rewrote `README.md`, `.env.example`, `Makefile`, `requirements-dev.txt`, `.gitignore`, trimmed the dead keys from `.env` (kept its gitignored token), added ERR-20261007-002/003/004, session `2026-10-07-004`.
- Cleanup: killed both test servers (8090/8080 free), removed `data/` and every temp file (`docs.json`, `r15.json`, `p15.json`, `x15.json`, page PNG, probe scripts); no supplier name, Tax ID or invoice number copied into any record.

## 2026-10-07T12:07:00+07:00
- รับ log จริงจากผู้ใช้ตอนรันพอร์ทัล แล้วพบ 3 ข้อบกพร่องฝั่ง browser ที่การทดสอบเดิมจับไม่ได้: `GET /api/documents/{id}/pages/undefined/image` (422 ทุกหน้าของทุกเอกสาร), `GET …/result` ยิงซ้ำจนได้ `409` เต็ม log, และ badge/recommendation ไม่แสดงจากแถวของ server
- Root cause: `service._public()` ส่ง `pages` เป็น **เลขหน้า** `[1,2,3]` แต่ `pagesHtml()` in `webapp/static/app.js` ใช้แต่ละตัวเป็นวัตถุ (`p.page`) → ต่อ url จากรูปเป็น `undefined`; `ensureView()` ไม่มี memory ว่าถามไปแล้วจึงถาม `/result` ใหม่ทุกครั้งที่ redraw; `applyServer()` อ่าน `m.rec` ทั้งที่ key จริงคือ `recommendation`
- แก้ `webapp/static/app.js`: เพิ่ม helper `pageNums(m)` (รับเลข / วัตถุ `{page:n}` / ไม่มีข้อมูล แล้วรวมกับ `pages_total`) ใช้ทั้งรายการหน้าและ jump link `หนn`; เพิ่ม flag `probed` ใน per-document state (จำคำตอบ 404/409, clear เมื่อ server แจ้งว่ารันเสร็จ, set เมื่อลบผล); เปลี่ยนเป็นอ่าน `m.recommendation` ทั้งใน `applyServer()` และ `watch()`
- เพิ่ม test 3 ตัวใน `tests/test_ui_static.py` (ยึดตาม row จริงจาก `/api/documents` ที่รันผ่าน TestClient): `pages` ต้องเป็น list ของ int, ห้ามสร้าง url จาก array ดิบ, ต้อง probe ผลครั้งเดียว, ต้องใช้ key name ของ server → `pytest -q` (src/test-portal) **112/112 ใน 6.8 s** และ `node --check webapp/static/app.js` ผ่าน
- พิสูจน์กับ server จริง: url เดิม `…/pages/undefined/image` = 422, url ใหม่ `…/pages/1/image` = **200** ทั้ง doc 15/19/20 (PNG 3.0 MB / 0.8 MB / 2.3 MB), `/api/documents/19` แถวมี `pages [1,2,3,4]` และ `recommendation` อยู่จริง, `/result` ขณะ idle ยังเป็น 409 ตามดีไซน์
- รอบเดียวกันได้ verify update ของ System A (commit `d8000bb` + tree ที่ยังไม่ commit เวลา 11:31: `matching.m1_exact_values_item_code`, `evidence.e11_waive_when_values_match`, `oracle.po_list_narrowing`, โมดูลใหม่ `application/receipt_scope.py`, `summary_version` 1.0→1.1, ไฟล์ schema เนื้อหาเดิม): root **36/36**, `system_a.cli scenarios` **45/45**, พอร์ทัล 112, `webapp check` exit 0, `SYSTEM_A_ENGINE=http webapp check` exit 0 กับ APIโหมด production/litellm
- **Bulk verify payload จริง 226 ไฟล์** (`results/paperless_invoices*/DMS-*_result.json` 3 ชุด) → ผ่าน `schemas/result-3.0.schema.json` และ render ผ่าน `view.build_view` ครบ 226/226 (elements 21,725 → วาด 21,708 กล่อง, bbox ตรงกับ payload ทุกกล่อง, refs resolve ครบ, rule states มี `not_evaluated` ด้วย)
- รันเอกสารจริงผ่านพอร์ทัลบนโค้ดใหม่: doc 15 → `done` 95.3 s, payload มี `summary` v1.1, 1155 elements/1155 boxes และผลเปลี่ยนเป็น **`AUTO_PASS` ไม่มี exception** (เดิม MANUAL_REVIEW + 2x E11) ซึ่งมาจากการเปิดสวิตช์นโยบายใหม่ ไม่ใช่ความล้มเหลวของพอร์ทัล
- Cleanup: ปิด server ที่เปิดทดสอบ (8080/8090 ไม่มี listener ค้าง), ลบ `data/`, `.pytest_cache`, `__pycache__`, ไฟล์ชั่วคราวทั้งหมด; ไม่แตะผลลัพธ์ batch ของผู้ใช้ใน `results/` (อ่านอย่างเดียว); ข้อมูลลับ (token/Paperless) ไม่มีใน record
