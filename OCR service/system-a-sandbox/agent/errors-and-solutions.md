# Errors and Solutions

Record format: ERR-YYYYMMDD-NNN

## Known Issues and Workarounds

### ERR-20261007-004 - `ensure_system_a()` ส่งค่าเป็นโฟลเดอร์ `src` ทำให้ `import process_pdf` ไม่ได้เลย
- **ID / เวลา**: ERR-20261007-004, 2026-10-07T10:24:00+07:00
- **อาการ**: หลังเปลี่ยน engine ของพอร์ทัลไปเรียก entrypoint ของ System A ตรง ๆ (`process_pdf.process_pdf(dms_id=…)`) โหมด `inprocess` ตายทันทีด้วย `ModuleNotFoundError: No module named 'process_pdf'` ทั้งที่ `import system_a` สำเร็จและ `/api/health` ยังตอบ ok
- **สาเหตุ**: `config.ensure_system_a()` คืนค่าและเพิ่ม `Path(system_a.__file__).parents[1]` ลง `sys.path` ซึ่งกรณี sandbox คือ `<root>/src`  แต่ `process_pdf.py` (และ `config/`, `.env`) อยู่ที `<root>`  entrypoint นี้ไม่ใช่ submodule ของแพ็กเกจ จึงมองไม่เห็นจาก path ที่เพิ่มไว้
- **วิธีแก้ที่ใช้จริง**: ใน `webapp/config.py` ตรวจว่า parent ชื่อ `src` ไหม แล้วขึ้นอีกชั้นหนึ่ง (`pkg.parent if pkg.name == "src" else pkg`) ทั้ง branch ที่ import ได้แล้วและ branch ที่ค้นจาก `SYSTEM_A_HOME` ทำให้ได้ `<root>` จริง ๆ และใส่ทั้งสอง path (`<root>/src`, `<root>`) ลง `sys.path`
- **วิธีป้องกัน**: มีเคสนี้ใน `tests/test_config.py` (Assert ว่า root ที่คืนไม่มีชื่อ `src` ปิดท้ายและ `(root / "process_pdf.py").is_file()`) และ smoke test จริงก่อนปิดงานด้วย `webapp check` ซึ่งเรียก path เดียวกับ `serve`

### ERR-20261007-003 - พอร์ทัลตัวเก่าที่ยังค้างอยู่บนพอร์ต 8090 ตอบ API คนละรูปกับโค้ดใหม่
- **ID / เวลา**: ERR-20261007-003, 2026-10-07T10:24:00+07:00
- **อาการ**: เปิด server ของโค้ดที่ rework เสร็จแล้ว แต่ `GET /api/health` ยังตอบคีย์เก่า (`perception`, `batch`, `pdfs_cached`) และ `/api/meta` ไม่มี `element_types` - เหมือน "โค้ดใหม่ไม่ทำงาน" ทั้งที่ test ผ่าน 109/109
- **สาเหตุ**: มี process ของพอร์ทัลรุ่นก่อน rework ฟังพอร์ต 8090 อยู่จาก session ที่แล้ว  process ใหม่ bind ไม่สำเร็จ (`[WinError 10048] only one usage of each socket address`) แต่ log ส่วนนั้นอยู่ใต้บรรทัดที่พิมพ์ URL จึงมักถูกมองข้าม ทุก request จึงตกกับ process เก่า
- **วิธีแก้ที่ใช้จริง**: `netstat -ano | grep ":8090" | grep LISTEN` แล้ว `taskkill //PID <pid> //F` หยุด server ตัวเก่าให้หมด ก่อน start ใหม่ - แล้วตรวจว่า `/api/meta` ตอบคีย์ใหม่ (`engine, mode, element_types, default_types, colors`) ก่อนเริ่มทดสอบใด ๆ
- **วิธีป้องกัน**: เวลา rework API ให้เริ่มด้วยการตรวจ **shape ของ response** ไม่ใช่แค่ status code; และเวลา start server แบบ background ให้เก็บ log ไว้ไฟล์แล้ว grep หา `10048` / `Address already in use` เสมอ (process ที่ bind ไม่สำเร็จจะจบตัวเอง แต่ log ยังอยู่)

### ERR-20261007-002 - view model ของพอร์ทัลเขียนตาม "รูป payload ที่เดาไว้" ไม่ใช่ของจริง
- **ID / เวลา**: ERR-20261007-002, 2026-10-07T10:24:00+07:00
- **อาการ**: หน้าจอขึ้นกล่อง/ตัวเลขไม่ตรง payload บาง panel ว่างเปล่าเสมอ (elements, rules) ทั้งที่ payload ที่ System A คืนมามีข้อมูลครบ
- **สาเหตุ**: `webapp/view.py` ฉบับเดิมอ่านจาก `pages[].elements[]` และคีย์แบบ `verify.rules` / `fields` ระดับบน ซึ่ง**ไม่มีอยู่จริง** ใน `aiva.system_a.result/3.0` - โครงจริงคือ element ทั้งหมดอยู่ที่ `ocr.elements[]` (มี `element_id`, `element_type`, `page_no`, `field_name`, `raw_value`, `normalized_value`, `confidence`, `bbox`), ค่าสุดท้ายอยู่ที่ `normalized_fields`, line↔receipt อยู่ที่ `line_matching.groups[]`, evidence ที่ payload เก็บคือ `rule_results[].evidence_ids` + `exceptions[].evidence_ids` (id ชี้ไป `evidence[].evidence_id`) ไม่ใช่ dict ที่ embed ไว้, geometry ของหน้าอยู่ที่ `pages[].width_pt/height_pt/rotation/render_dpi`
- **วิธีแก้ที่ใช้จริง**: เขียน view ใหม่จาก payload จริง โดย**โพรบก่อนเขียน**: สร้าง `aiva.extraction/2.0` สังเคราะห์แล้วให้ System A เอง (`orchestrator.validate()` โหมด sandbox, `InMemoryOracleRepository` + sim AI)  produce payload ออกมา แล้ว dump โครงสร้างจริงทุก key ออกมาดู  จึง map ทีละ field  ของ `view.py` + `app.js`
- **วิธีป้องกัน**:
  - ห้าม test พอร์ทัลด้วย dict ที่คนเขียนขึ้นเอง - `tests/synth.py` + harness สร้าง payload จากโค้ด System A จริง แล้ว `tests/test_view.py` (25 เคส) assert ว่าทุกกล่อง/ทุกค่า/ทุก ref ของ view ตรงกับ payload นั้น (ตรวจเทียบ bbox ทีละ element)
  - สิ่งที่มักพลาดซ้ำ: `normalized_value` ของ signature เป็น boolean (`true`) จึงต้องนับเป็น missing ใน text; และ `halted_by` ใน `recommendation` เป็นกลไกปกติของ rule chain ไม่ใช่ผลไม่ครบ - `incomplete` ให้ดู `system_errors` เท่านั้น

### ERR-20261007-001 - `run.bat` runs the wrong Python and dies inside uvicorn
- **ID / เวลา**: ERR-20261007-001, 2026-10-07T08:42:00+07:00
- **อาการ**: `python -m webapp check` ผ่าน (99 เอกสาร) แต่ `python -m webapp serve` ล้มทันทีหลังพิมพ์ URL:
  ```
  File "...\hermes\hermes-agent\venv\Lib\site-packages\uvicorn\protocols\websockets\websockets_impl.py"
    from websockets.legacy.server import HTTPResponse
  ModuleNotFoundError: No module named 'websockets.asyncio.compatibility'
  ```
  สิ่งที่สำคัญที่สุดคือ traceback ชี้ไปที่ `AppData\Local\hermes\hermes-agent\venv` และ Python 3.11 - ไม่ใช่ `.venv` ของพอร์ทัล
- **สาเหตุ (2 ชั้น)**:
  1. `.venv/Scripts/activate.bat` ตั้ง `PATH=%VIRTUAL_ENV%\Scripts;%PATH%` โดย `VIRTUAL_ENV` ถูกเขียนแข็งไว้ตอนสร้าง venv ที่ `.../system-a-sandbox/system-a/src/system-a-webapp/.venv` ซึ่งเป็น path เก่าก่อนย้ายโฟลเดอร์มา `src/test-portal` - โฟลเดอร์นั้นไม่มีอยู่แล้ว จึงไม่มีอะไรถูก prepend และ `python` ยิงกลับไปหา venv แรกใน PATH (`hermes-agent`, Python 3.11, uvicorn 0.41.0 + websockets 15.0.1 ซึ่งไม่เข้ากัน)  
     ผลข้างเคียงเดียวกัน: shim ทั้งหมดใน `.venv/Scripts/*.exe` (pip.exe, uvicorn.exe, fastapi.exe) และ `pyvenv.cfg` ชี้ไปที่ path เก่าด้วย
  2. uvicorn ค่าเริ่มต้น `ws="auto"` import แพ็กเกจ `websockets` ตอน startup ทั้งที่พอร์ทัลไม่ใช้ WebSocket เลย (ตรวจ `webapp/static/app.js` + `webapp/*.py`: ไม่มี `WebSocket` / `ws://`) ทำให้สภาพแวดล้อมที่ `websockets` เวอร์ชันไม่ตรง uvicorn พังทั้งตัว
- **วิธีแก้ที่ใช้จริง**:
  1. `run.bat` / `run.sh`: เรียก interpreter ด้วย **full path** (`%~dp0.venv\Scripts\python.exe` / `.venv/bin/python`) แทน `call activate` - ไม่ขึ้นกับ PATH หรือ venv ตัวอื่นอีก
  2. `webapp/__main__.py`: `uvicorn.run(..., ws="none")` (uvicorn ทั้ง 0.41 และ 0.54 รองรับ; `WS_PROTOCOLS["none"] is None` และ `import_from_string` คืนค่า non-str ตามเดิม)
  3. สร้าง `.venv` ใหม่ ณ ตำแหน่งจริง ด้วย Python 3.14.2 แล้วติดตั้ง `requirements.txt` + `pytest` + `jsonschema` (เดิมใน venv ไม่มี pytest ทำให้ `make test` ใน venv ใช้ไม่ได้)
- **วิธีพิสูจน์ว่าหาย**: รัน `python -m webapp serve` ด้วย interpreter ตัวที่ crash เดิม (`hermes-agent\venv`, Python 3.11) → `GET /` 200, `GET /api/health` `ok:true` ไม่เกิด ModuleNotFoundError อีก
- **วิธีป้องกัน**:
  - สคริปต์ start ต้องไม่เชื่อ `activate` เมื่อโฟลเดอร์อาจถูกย้าย - เรียกใช้ interpreter ด้วย path ของตัวเองเสมอ
  - service ที่เป็น HTTP ล้วนให้ `ws="none"` ไว้
  - เมื่อย้าย/เปลี่ยนชื่อโฟลเดอร์โครงการที่มี `.venv` ให้สร้าง venv ใหม่ หรือตรวจ `pyvenv.cfg` ว่า `command` ชี้มาที่ path ปัจจุบัน

### ERR-20261007-005 - browser อ่าน field name ที่ API ไม่ได้ส่ง (pages/rec) และถามผลซ้ำไม่หยุด
- **ID / เวลา**: ERR-20261007-005, 2026-10-07T12:07:00+07:00
- **อาการ** (จาก log ของ `python -m webapp serve` ที่ผู้ใช้รันจริง):
  ```
  GET /api/documents/19/pages/undefined/image   -> 422 Unprocessable Content   (ทุกหน้า ของทุกเอกสาร)
  GET /api/documents/19/result                  -> 409 Conflict                (ยิงซ้ำทุกครั้งที่ redraw)
  ```
  กล่อง bbox ไม่เคยแสดงเลย ทั้งที่ payload มี bbox ครบ และ badge recommendation ขึ้นค่าไม่ได้
- **สาเหตุ**:
  1. `service._public()` ส่ง `"pages": d.page_numbers` คือ **list ของเลขหน้า** (`[1,2,3]`) แต่ `pagesHtml()` ใน `webapp/static/app.js` ทำเหมือนเป็น list ของวัตถุ (`p.page`) → `undefined` ถูกเอาไปต่อ url; เอกสารที่ `page_numbers` ยังว่าง (ยังไม่เคยเรียก `catalog.ensure()`) รอดเพราะ fallback ใช้ `pages_total` ทำให้ดูเหมือน bug เกิดสุ่มเฉพาะบางเอกสาร
  2. `ensureView()` เรียก `GET …/result` ทุกครั้งที่ redraw โดยไม่จำว่าถามไปแล้ว — ปกติที่ `/result` ตอบ 409 (ยังไม่ประมวลผล หรือ `WEBAPP_PERSIST=false` แล้ว server restart) จึงกลายเป็น storm ทั้ง client และ server
  3. `applyServer()` อ่าน `m.rec` แต่ key จริงของแถวคือ `recommendation` → `r.rec` เป็น null เสมอ
- **วิธีแก้ที่ใช้จริง** (`webapp/static/app.js` อย่างเดียว backend ไม่เปลี่ยน):
  1. helper `pageNums(m)` แปลง `pages` (เลข หรือวัตถุ `{page:n}` หรือว่าง) รวมกับ `pages_total` เป็นเลขหน้าแล้วใช้ทั้งรายการหน้าและ jump link
  2. flag `probed` ต่อเอกสาร: จำคำตอบ 404/409 ไว้, clear เมื่อ `applyServer()` เห็น `state: "done"` (ต้องไปเอาผลมาแสดง), set เมื่อผู้ใช้ลบผลใน `forget()`
  3. อ่าน `m.recommendation` ทั้งใน `applyServer()` และข้อความสถานะใน `watch()`
- **วิธีพิสูจน์ว่าหาย**: `…/pages/undefined/image` = 422 (ตามเดิมที่ควรเป็น) ส่วน url ที่หน้าสร้างตอนนี้ `…/pages/1/image` = **200** กับ doc 15/19/20 (PNG 3.0 MB / 0.8 MB / 2.3 MB); แถวของ doc 19 มี `pages [1,2,3,4]` และมี key `recommendation`; `pytest -q` (src/test-portal) 112/112, `node --check` ผ่าน
- **วิธีป้องกัน**:
  - test ฝั่ง UI ต้อง assert กับ **row จริงที่ app ส่งออก** (TestClient) ไม่ใช่เชื่อ shape ที่จำมา — เพิ่ม `test_page_numbers_are_used_as_the_numbers_the_server_sends`, `test_a_document_with_no_stored_result_is_asked_for_only_once`, `test_the_state_row_is_read_with_the_keys_the_server_uses`
  - code ที่ต่อ url จากข้อมูลของ server ต้อง normalize ที่จุดเดียว (helper) แล้วห้ามใช้ array ดิบโดยตรง
  - คำตอบ "ยังไม่มีผล" (404/409) ให้ถือเป็นสถานะปลายทาง ห้าม retry อัตโนมัติถ้าไม่มี event ใหม่ (รันเสร็จ/ลบผล)
