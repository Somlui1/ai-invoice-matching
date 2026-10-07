# Task and Plan

## Task: Fix SYSTEM_A_HOME Configuration and Fallback in src/test-portal

- **Started At**: 2026-10-07T08:22:00+07:00
- **Completed At**: 2026-10-07T08:24:00+07:00
- **Status**: Completed

### Goals & Acceptance Criteria
1. **Fix `src/test-portal/.env`**:
   - Correct `SYSTEM_A_HOME` path from `.../system-a-sandbox/system-a` to `.../system-a-sandbox`.
2. **Resilient Fallback in `src/test-portal/webapp/config.py`**:
   - Enhance `ensure_system_a` to detect parent sandbox directory automatically if path has extra trailing folder or is unset.
3. **Verification**:
   - Run `python -m webapp check` inside `src/test-portal` to verify connection and document listing succeed.

## Task: Clean Unnecessary Files Out of src/test-portal

- **Started At**: 2026-10-07T08:26:00+07:00
- **Completed At**: 2026-10-07T08:32:00+07:00
- **Status**: Completed

### Goals & Acceptance Criteria
1. **Decide necessity of `src/test-portal/tests/` and `src/test-portal/data/`** from the code, not from guesswork:
   - `data/` = runtime output only (`ResultStore` creates it, tests use `tmp_path`, current `.env` has `WEBAPP_PERSIST=false`).
   - `tests/` = the only regression net of the portal (93 tests, `make test` / `make e2e`).
2. **Delete what is regenerable or stale**: old per-document results, `__pycache__`, `.pytest_cache`.
3. **Keep every file the application or the test suite actually imports** (no module of `webapp/` is dead code).
4. **Verification**: `python -m pytest -q` in `src/test-portal` still passes 93/93 and `ResultStore` re-creates `data/results` by itself.

## Task: Make `run.bat` start the portal reliably (ERR-20261007-001)

- **Started At**: 2026-10-07T08:36:00+07:00
- **Completed At**: 2026-10-07T08:42:00+07:00
- **Status**: Completed

### Goals & Acceptance Criteria
1. **Explain the crash** `ModuleNotFoundError: No module named 'websockets.asyncio.compatibility'` and identify which interpreter actually ran.
2. **`run.bat` / `run.sh` must use this project's own interpreter** no matter which venv is active or first in `PATH` (full path, no `activate`).
3. **The portal must not depend on `websockets`** - uvicorn starts with `ws="none"`.
4. **`.venv` must be valid at the folder's real location** (rebuild it; the old one was created elsewhere and its shims pointed at a deleted path).
5. **Verification**:
   - `run.bat` resolves to `.venv\Scripts\python.exe` even with another venv on PATH.
   - `python -m webapp serve` starts with the interpreter that previously crashed (`GET /` 200, `/api/health` `ok:true`).
   - `pytest -q` = 93/93 from the new `.venv`.


## Task: Rework `src/test-portal` to test `src/system_a` only (payload-driven)

- **Started At**: 2026-10-07T09:05:00+07:00
- **Completed At**: 2026-10-07T10:24:00+07:00
- **Status**: Completed

### Goals & Acceptance Criteria
1. **One source of truth**: documents come from real Paperless; every box and every value shown comes only from System A's final `aiva.system_a.result/3.0`. System A เป็นฝ่ายประมวลผลเองทั้งหมด พอร์ทัลไม่มี fallback/ผลบางส่วน - ถ้า System A error ให้โชว์ error จริงพร้อม traceback
2. **ตัดเส้นทางที่ไม่ใช่ System A ออก**: batch/report.html, replay ของ OCR ตัวอื่น, demo batch, หน้า SVG แทนหน้าเอกสาร, โค้ด Paperless/PDF ของพอร์ทัลเอง
3. **คง `SYSTEM_A_ENGINE=http` ไว้** (ทดสอบเส้นทาง API แบบ production) โดยค่าเริ่มต้นยังเป็น `inprocess` และมีวิธีเริ่ม server บอกไว้ใน doc
4. **ผลไม่ครบต้องมองเห็นได้**: payload ที่มี `system_errors` ต้องขึ้น "ผลไม่ครบ" พร้อมรายการ error (ส่วน `halted_by` ของ rule chain ถือเป็นเรื่องปกติ)
5. **Tests ต้องทดสอบ System A ตรงไปตรงมา**: ใช้ `orchestrator.validate()` ของ System A เอง (sandbox, ไม่มี network/VLM/Oracle จริง) สร้าง payload จริง แล้ว assert view/API/service/UI กับ payload นั้น; ข้อมูลสังเคราะห์ห้ามมีชื่อผู้ขาย/Tax ID/เลข invoice จริง
6. **Verification**:
   - `pytest -q` (src/test-portal) = 109/109
   - `node --check webapp/static/app.js` ผ่าน และทุก `$('id')` มีอยู่ใน index.html
   - `python -m webapp check` ผ่านกับ DMS จริง; `SYSTEM_A_ENGINE=http webapp check` ผ่านกับ System A API ที่รันอยู่
   - รันเอกสารจริง 1 ฉบับผ่านพอร์ทัลแล้วเทียบ bbox ของ final refs กับ payload ว่าตรงกัน
