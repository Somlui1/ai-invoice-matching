# Session: 2026-10-07-004 - Rework `src/test-portal` ให้ทดสอบ System A ตรง ๆ ด้วย payload เป็นแหล่งเดียว

- **Date**: 2026-10-07T10:24:00+07:00
- **Goal**: พอร์ทัลต้องทดสอบ `src/system_a` เท่านั้น — เอกสารจาก Paperless จริง, กล่องและตัวเลขทั้งหมดบนจอมาจาก
  `aiva.system_a.result/3.0` ฉบับสุดท้ายของ System A เอง, ตัดเส้นทาง batch/replay/demo ออก, และยังคง `SYSTEM_A_ENGINE=http` ไว้

## คำสั่งที่กำหนดทิศทาง
> "ปรับใหม่ ฉันต้องการให้รัน process จาก `src/system_a` เท่านั้น หาก System A รับกระบวนการส่งนี้จะ error ก็ error ไป
> ค่อยแก้ ฉันต้องการให้ทดสอบ sys-A อย่างตรงไปตรงมา"

จึงตัด mechanism "ทำให้สำเร็จโดยเร็ว" ทั้งหมดออก (OCR items ปลอม, หน้า SVG แทนหน้าเอกสาร, ขอบกล่องที่ portal คำนวณเอง)
และปล่อย error ของ System A ขึ้นจอตรง ๆ พร้อม traceback

## สิ่งที่ค้นพบก่อนแก้ (โพรบ payload จริง)
เขียน `aiva.extraction/2.0` สังเคราะห์แล้วให้ System A รันเองใน sandbox (`orchestrator.validate()` +
`InMemoryOracleRepository` + sim AI) แล้ว dump โครงสร้างจริงออกมาดู ผลคือ view model เดิม **map ผิดทั้งก้อน**:

| ที่โค้ดเดิมอ่าน | ที่มีจริงใน payload |
|---|---|
| `pages[].elements[]` | `ocr.elements[]` (มี `element_id`, `element_type`, `page_no`, `field_name`, `raw_value`, `normalized_value`, `confidence`, `bbox`) |
| `fields` / `verify.rules` ระดับบน | `normalized_fields`, `rule_results[]` (มี `evidence_ids`) → `evidence[]` |
| geometry ต่อหน้าใน units เอง | `pages[].width_pt/height_pt/rotation/render_dpi` + `package.coordinate_system` (origin top-left, bbox เป็น ratio 0–1) |
| element ของ line | `line_matching.groups[]` (`relation`, `level`, `rcv_line_ids`, `source`, `rationale`) และ `line_matching.ai_rejected` |
| signature เป็น field | เป็น element `element_type=signature` ที่ `normalized_value` เป็น **boolean** (`true`) |

สองจุดที่เกือบพลาด: `normalized_value=true` ของ signature ต้องนับเป็น missing ใน text; และ `recommendation.halted_by`
(กฎก่อน fail แล้ว halt กฎถัดไป) เป็นกลไกปกติของ System A **ไม่ใช่**ผลไม่ครบ — `incomplete` จึงดูแค่ `system_errors`

## สิ่งที่แก้ (โค้ด)
| ไฟล์ | เปลี่ยนอะไร |
|---|---|
| `webapp/view.py` | เขียนใหม่ทั้งไฟล์จาก payload จริง (โพรบแล้ว map ทีละ key) + `extraction_of()` ตัด blocks ที่พอร์ทัลไม่ใช้ |
| `webapp/app.py` `build.py` `__main__.py` `store.py` | API/ wiring ใหม่รอบ payload: `/api/meta,health,documents(+refresh),documents/{id},POST process,result,payload,extraction,DELETE result,pdf,pages/{n}/image,search`; `PARTS = ("state","view","payload")`; คำสั่งเหลือแค่ `check`/`serve` |
| `webapp/static/app.js` `index.html` | renderer ของ view model (JS 576 บรรทัด): list + recommendation colors, type chips, hover/pin ด้วย `element_id`, Final/Verify panel, traceback panel, localStorage (`aiva.sysA.cases.v1`, `aiva.sysA.types.v1`), keyboard (↑↓, PgUp/PgDn, `f`, `o`, Esc) |
| `webapp/config.py` | `ensure_system_a()` คืน **project root** (ถ้า package อยู่ที่ `<root>/src/system_a` ให้ขึ้นอีกชั้น) — ERR-20261007-004 |
| `webapp/catalog.py` `service.py` | `Doc` เพิ่ม `file_name`, `tagged`; `_job(doc_id, run)`; `build_view(payload)` แล้ว service ต่อ `seconds/engine/mode`; state เก็บ `recommendation.value` สั้น; search text lowercase ตอนเขียน cache |
| **ลบ** | `webapp/batch.py`, `extraction.py`, `perception.py`, `placeholder.py`, `demo.py`, `paperless.py`, `pdfkit.py` + routes/controls ที่ใช้ |
| `.env`, `.env.example`, `README.md`, `Makefile`, `requirements-dev.txt`, `.gitignore` | เขียนใหม่ให้เหลือ config จริง (`PAPERLESS_*`, `SYSTEM_A_*`, `WEBAPP_*`) ไม่มี `BATCH_REPORT`/`PERCEPTION`/`REPLAY_*`/`PDF_DIR`/`DOC_SOURCE`/playwright; `.env` เก่าเก็บ token ไว้ครบ (แก้เป็นก้อน ๆ ไม่ทับบรรทัด secret) |

## สิ่งที่แก้ (test) — ทดสอบ System A จริง ไม่ใช่ dictionary ที่แต่งเอง
- `tests/synth.py` สร้าง extraction สังเคราะห์ (ไม่มีชื่อผู้ขาย/Tax ID/เลข invoice จริง) ค่า `raw_value` ต้อง **ลอก label
  ออกแล้ว** เพราะ VisionPipeline ส่ง value ที่ strip แล้วให้ ExtractionResult ไม่ใช่ของดิบ (บั๊กที่เจอตอนโพรบ)
- `tests/doubles.py` — `FakeSystemA`, `FakeReader` (สร้างเอกสารผ่าน parser `_doc()` ของ System A เอง), `FakeRunner`
- `tests/conftest.py` — `make_harness(dest)` copy package ของ System A ไปข้าง stub Standard (idempotent: ลบ dest ก่อน copy)
- **109 tests / 6.64 s, offline ทั้งหมด**: view 25, api 19, engine 18, config 16, catalog 12, service 12, ui_static 7
  - `test_engine.py` Mount API app จริงของ System A ด้วย `TestClient` และเทียบ `integrity.payload_sha256` ของสอง engine
  - `test_ui_static.py` ตรวจ JS แบบ text: ทุก control มีใน index.html, เรียกแต่ endpoint จริง, กล่องมาจาก payload element เท่านั้น

## การตรวจสอบ
- `node --check webapp/static/app.js` ผ่าน; `$('id')` ทั้ง 14 ตัวมีอยู่ใน index.html จริง
- `python -m webapp check` → exit 0: 98 documents / 423 pages, tag `invoice` (id 5), Standard 6.6 / v6.6-r4, mode production, ai litellm, engine inprocess
- `SYSTEM_A_ENGINE=http timeout 200 python -m webapp check` → exit 0 เมื่อ System A API รันอยู่ที่ 8080 (`/health/ready` = sandbox/sim) และมี hint วิธีเริ่ม server
- **รันเอกสารจริง 1 ฉบับผ่านพอร์ทัล** (inprocess + production, VLM จริง + Oracle MCP จริง): `POST /api/documents/15/process`
  → `done` 55.7 s (`total_ms` 54893 = step3 43480 + oracle 1849), payload 1155 elements / 1155 boxes / **0 ไม่มี bbox**,
  V-01..V-06,V-08,V-09 pass, V-07 fail (E11 Medium ×2) → `MANUAL_REVIEW`; page geometry 595.69×843.75 pt rot 0 @150 DPI;
  8/9 final items มี refs และ **bbox ของทุก ref เท่ากับ payload ที่ store ไว้**
- ระหว่างทดสอบ เจอ server เก่าค้างบนพอร์ต 8090 ตอบ API รูปเดิม → ERR-20261007-003; และ `pages_total` เป็น null กับเอกสารประเภท image (Paperless ไม่ส่ง `page_count`) จึงแก้ UI ให้แสดง `?`

## บันทึกที่เขียน
`changelog.md`, `work-log.md`, `current-state.md`, `task-plan.md`, `errors-and-solutions.md`
(ERR-20261007-002 payload shape ผิดคาด, ERR-20261007-003 พอร์ตถูกตัวเก่าครอง, ERR-20261007-004 `ensure_system_a` คืน `<root>/src`)

## เทคนิคที่ควรจำ
- เขียนไฟล์ยาว ๆ ที่มีภาษาไทยด้วย tool `write` ครั้งเดียวเคยโดนตัดจนหาย — จึงเขียน `app.js` เป็นสองก้อน (`_app_a.js` +
  `_app_b.js`) แล้ว `cat` รวมกัน ลบก้อนทิ้ง  ตรวจซ้ำด้วย `node --check`
- ห้ามลบ token/secret ตอนแก้ `.env` แบบ write ทับทั้งไฟล์ — ใช้ `edit` เป็นก้อน ๆ เว้นบรรทัด secret ไว้ แล้ว dump
  ไฟล์แบบ `sed -E 's/(TOKEN|KEY)=.*/\1=<redacted>/'` เพื่อตรวจ
