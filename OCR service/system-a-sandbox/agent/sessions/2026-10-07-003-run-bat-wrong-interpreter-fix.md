# Session: 2026-10-07-003 - run.bat Started Another Project's Python and Crashed in uvicorn

- **Date**: 2026-10-07T08:42:00+07:00
- **Goal**: ทำให้ `run.bat` ใน `src/test-portal` เปิดเว็บได้จริง และแก้สาเหตุที่ `serve` ตายตอน startup

## Symptom (from the user's console)
`python -m webapp check` ผ่าน (99 documents, 424 pages) แล้ว `serve` พิมพ์ URL ตามด้วย:
```
ModuleNotFoundError: No module named 'websockets.asyncio.compatibility'
  ... uvicorn\protocols\websockets\websockets_impl.py -> from websockets.legacy.server import HTTPResponse
```
Traceback ทุกบรรทัดอยู่ใน `C:\Users\wajeepradit.p\AppData\Local\hermes\hermes-agent\venv` และ `AppData\Roaming\uv\python\cpython-3.11` - ไม่ใช่ `.venv` ของพอร์ทัล

## Diagnosis
1. **`activate.bat` of the portal's `.venv` does nothing here.** It ends with `set "PATH=%VIRTUAL_ENV%\Scripts;%PATH%"`, and `VIRTUAL_ENV` is hard-coded (at venv creation time) to
   `...\system-a-sandbox\system-a\src\system-a-webapp\.venv` - the folder before it was moved/renamed to `src/test-portal`.  That directory does not exist, so nothing was prepended and `python` resolved to the first entry on `PATH`: `hermes-agent\venv` (Python 3.11, uvicorn 0.41.0, `websockets` 15.0.1).
   - Proof (probe batch, run in the same shell): `where python` **before** and **after** `call .venv\Scripts\activate.bat` returned the identical hermes interpreter.
   - Same staleness in `.venv/pyvenv.cfg` (`command = ... -m venv ...system-a-webapp\.venv`) and in every shim `Scripts/*.exe` (pip.exe, uvicorn.exe, fastapi.exe ...).
2. **`websockets` 15.0.1 does not match uvicorn 0.41** (`websockets.legacy.server` imports `websockets.asyncio.compatibility`, removed in that build) → the import inside uvicorn's *auto* WebSocket protocol fails.
3. **The portal has no WebSocket at all** - `grep -rn "WebSocket|ws://|wss://" webapp/ tests/` over `.js`, `.html`, `.py` = no match; the screen polls `GET /api/documents/{id}`.  So uvicorn's default `ws="auto"` only adds a way to die.

## Fixes
| File | Change |
|---|---|
| `src/test-portal/run.bat` | เรียก interpreter ด้วย full path `%~dp0.venv\Scripts\python.exe` (ลบ `call .venv\Scripts\activate.bat`), check + serve ใช้ `%PY%` ทั้งคู่, เพิ่ม fail-fast เมื่อสร้าง `.venv` ไม่สำเร็จ |
| `src/test-portal/run.sh` | เช่นกันกับ `.venv/bin/python` (fallback `python3`) |
| `src/test-portal/webapp/__main__.py` | `uvicorn.run(app, host=..., port=..., log_level="info", ws="none")` พร้อมคอมเมนต์อ้างอิง ERR-20261007-001 |
| `src/test-portal/.venv` | สร้างใหม่ด้วย Python 3.14.2 ณ path จริง + `pip install -r requirements.txt pytest jsonschema` (PyPI ตอบ 200 ใน 1.5 s) - เป็นการลบ shim/`pyvenv.cfg` ที่ชี้ path เก่าทั้งชุด |

ตรวจสอบแล้วพบว่า `ws="none"` ใช้ได้กับ uvicorn ทั้งสองเวอร์ชันที่เครื่องนี้มี: `WS_PROTOCOLS["none"] is None` และ `import_from_string()` คืนค่า non-str ตามเดิม (uvicorn 0.41.0 ของ hermes และ 0.54.0 ของ `.venv`)

## Verification
1. `run.bat` logic probe: `PY = ...\src\test-portal\.venv\Scripts\python.exe`, interpreter 3.14.2, uvicorn 0.54.0 - ทั้งที่ venv อื่นอยู่ใน PATH ก่อน
2. `python -m webapp check` (`.venv`): exit 0, `{"source":"paperless","documents":99,"pages":424,"list_error":null}`
3. `python -m webapp serve` ด้วย `.venv`: `GET /` 200, `/api/health` `{"ok":true,"engine":{...,"mode":"production","ai_mode":"litellm","standard":"6.6","ruleset":"v6.6-r4"}}`, `/api/documents` 200
4. **การทดสอบ regression ตัวจริง**: รัน `python -m webapp serve` ด้วย interpreter ที่เคย crash (`hermes-agent\venv`, Python 3.11, `websockets` 15.0.1) → `GET /` 200 และ `/api/health` `ok:true` ไม่เกิด `ModuleNotFoundError` อีก
5. `python -m pytest -q` จาก `.venv` ใหม่: **93/93 passed** (8.3 s) - เดิมทำใน `.venv` ไม่ได้เพราะไม่มี pytest
6. ทิ้งท้าย: kill เซิร์ฟเวอร์ที่ทดสอบ (port 8090 กลับมาว่าง, เหลือแต่ TIME_WAIT) และลบ `.pytest_cache`, `__pycache__`, `data/` ที่ test สร้างกับ `_rb_probe.bat` ชั่วคราว

## Notes for next time
- ถ้าย้ายหรือเปลี่ยนชื่อโฟลเดอร์โครงการที่มี `.venv` → venv พังเงียบ ๆ; ตรวจ `pyvenv.cfg` ว่า `command` ชี้มาที่ path ปัจจุบัน หรือไม่ก็สร้างใหม่
- `.venv` ตอนนี้มี 124 MB (รวม pytest/jsonschema) - ยัง gitignore เหมือนเดิม
- `websockets` ไม่ได้ติดตั้งใน `.venv` และพอร์ทัลก็ไม่ต้องการ เพราะตั้ง `ws="none"` แล้ว
