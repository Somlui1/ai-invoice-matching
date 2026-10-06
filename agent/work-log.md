# Work Log

บันทึกการดำเนินงานและผลตรวจสอบตามลำดับเวลา รายการใหม่ต้องเพิ่มด้านล่างเท่านั้น

## 2026-10-01

### `WORK-20261001-001` — Establish central architecture documentation in `docs/`

- สร้างชุดเอกสารสถาปัตยกรรมและโครงสร้างระบบในโฟลเดอร์ `docs/`:
  - `docs/README.md`: สารบัญกลางและคำแนะนำการใช้งานสำหรับ Agent
  - `docs/system-architecture.md`: ผังและคำอธิบายสถาปัตยกรรม Dual-Circuit 3-Way Matching Engine
  - `docs/matching-rules-standard-v6.2.md`: กฎเกณฑ์การตรวจสอบ V-01 ถึง V-09, ข้อยกเว้น E05-E35, และ Decision Matrix
  - `docs/api-reference.md`: รายการ REST API และ SSE Streaming Endpoints
  - `docs/integrations.md`: ข้อกำหนดการเชื่อมต่อ Oracle EBS MCP, Vision LLM, Paperless-ngx, Portal
- ตรวจสอบความถูกต้องของลิงก์และเนื้อหา สอดคล้องกับ implementation ใน `OCR service/n8n/app/`

## 2026-10-02

### `WORK-20261002-001` — Build receiving portal
- Timestamp: `2026-10-02T08:48:00+07:00`
- อ่าน canonical records และแผนเดิมก่อนพัฒนา; ปรับ scope เป็น JSON receiver + PDF ตามผู้ใช้
- แยก frontend components และ backend schema/storage/API; ไม่แก้ OCR service หรือ mockup ต้นฉบับ
- ทดสอบ backend ด้วย unittest: 9 ผ่าน ครอบคลุม persistence, event/revision conflicts, validation, PDF, key/origin boundary, filters และ adapter
- ทดสอบ TypeScript/Vite production build: ผ่าน
- ทดสอบ Playwright Edge: 3 ผ่าน รวม desktop/mobile import/PDF/history/search, invalid JSON และ decimal precision
- ตรวจ screenshot จริงและแก้ PDF overflow ให้ fit-width; แก้ repeated evidence-page navigation และใช้ decimal string/BigInt สำหรับ display
- ติดตั้ง npm dependencies และ build/browser subprocess ผ่าน sandbox escalation ที่ได้รับอนุมัติ; ไม่มีการ deploy/push
- แยก browser test DB จาก local preview; local preview มีเฉพาะตัวอย่างสังเคราะห์หนึ่งรายการสำหรับดู UI
- API guide/readme/scope status อัปเดตแล้ว; ยังไม่ยืนยัน Entra/RBAC/PostgreSQL/บริการภายนอก production

### `WORK-20261002-002` — Add revision-aware JSON/PDF history
- Timestamp: `2026-10-02T09:03:26+07:00`
- อ่าน `invoice-web/docs` เทียบ implementation แล้วเลือกปิดช่องว่าง PDF revision archive ซึ่งทำได้ภายในขอบเขต receiving portal
- เพิ่ม `pdf_attachments` และ startup compatibility backfill จาก `documents.pdf_*`; ไม่แก้หรือลบไฟล์ PDF เดิม
- เพิ่ม current/historical document presentation, revision index และ exact-revision PDF read/upload
- เพิ่ม UI สลับ revision, URL deep link, historical banner, JSON export/PDF download ที่ระบุ revision และรายการรุ่นพร้อมสถานะไฟล์
- Backend unittest 11 ผ่าน; TypeScript/Vite production build ผ่าน; Playwright Edge 4 ผ่าน
- ตรวจ screenshot desktop/mobile ของ revision history แล้ว และตรวจ mobile horizontal overflow ผ่าน
- ไม่เรียก OCR/Oracle/DMS/AP จริง ไม่มี commit, push หรือ public deployment

### `WORK-20261002-003` — Refactor into documented modular structure
- Timestamp: `2026-10-02T09:21:29+07:00`
- เทียบ code inventory กับ `invoice-web/docs/01-tech-stack-and-architecture.md` แล้วแยก frontend/backend ตาม boundary ที่ใช้งานจริง
- ย้าย queue, document detail tabs, integration, viewer, shared layout/UI, API client/types, styles และ synthetic fixture ไปยังตำแหน่งตาม feature
- แยก FastAPI routes, access policy, configuration, document service, SQLAlchemy setup/models, Table9 adapter และ PDF file store ออกจาก app factory
- คง `app.schemas`, `app.legacy`, `app.db` compatibility imports และ API URLs เดิม เพื่อไม่ทำลาย script/test/client ที่มีอยู่
- เพิ่ม `docs/06-project-structure.md`, boundary READMEs และ architecture test; ไม่เพิ่ม runtime ที่ยังไม่มี requirement
- Backend unittest 12 ผ่าน; TypeScript/Vite production build ผ่าน; Playwright Edge 4 ผ่าน
- Restart local preview และตรวจ health, existing two-revision document, static HTML ผ่าน; ไม่มีข้อมูลเดิมสูญหาย
- ไม่มี commit, push หรือ public deployment

### `WORK-20261002-004` — Implement mockup feature parity for receiving portal
- Timestamp: `2026-10-02T09:40:01+07:00`
- ตรวจ requirements ใน `invoice-web/docs` และ function/constant ของ mockup v4.4 แล้วจัดทำ parity matrix UI-01–UI-15
- เพิ่ม queue/detail metadata, receipt/Receiver/ORG_ID, rule STEP, warnings, ownership/access และ tab interaction โดยใช้ข้อมูลจาก JSON ที่มีจริง
- เพิ่ม `/api/portal/v1/audit-events`, session capabilities, หน้า Access และหน้า Audit พร้อม search/filter/pagination/document navigation
- รักษาขอบเขต receiver/display: ไม่มี mock role switch, OCR/AP workflow action หรือสิทธิ์รายผู้ใช้ที่ backend ยังไม่มี identity enforcement
- Backend unittest 13 ผ่าน; TypeScript/Vite production build ผ่าน; Playwright Edge 5 ผ่าน
- ตรวจภาพ detail/access/audit บน desktop และ audit/mobile overflow ผ่าน; รีสตาร์ต local preview และตรวจ health/session/audit/document/static HTML สำเร็จ
- ไม่มี commit, push หรือ public deployment

### `WORK-20261002-005` — Add review actions and task-first document UI
- Timestamp: `2026-10-02T10:10:57+07:00`
- ตรวจ `actions`, `CFG`, `REASON`, `openM`, `doAct` ใน mockup และยืนยัน 8 actions รวมเงื่อนไข role/status/reason/high severity
- ไม่ย้ายพฤติกรรมจำลองที่แก้ FAIL เป็น PASS หรือ Posted ใน browser; ออกแบบ workflow/action request tables และ source outbox แทน
- เพิ่ม explain/resubmit/rerun/return/reject/hold/confirm API พร้อม validation, expected revision/workflow version, idempotency, audit และ acknowledgement
- ปรับ queue/detail/action modal/history/access/audit/integration UI ให้เห็น next task, blocking reason และ producer handoff ชัดเจน
- รวม ownership/source/JSON เป็นข้อมูลเพิ่มเติม ลด tab หลักเหลือ 5 และรักษา keyboard navigation/responsive behavior
- Backend unittest 15 ผ่าน; production Vite build ผ่าน; Playwright Edge 6 ผ่าน รวม resubmit → outbox → revision ใหม่
- ตรวจ screenshot desktop/mobile ของ task-first detail, waiting state และ workflow result; mobile horizontal overflow ผ่าน
- รีสตาร์ต local preview และตรวจ health, workflow capability, current document actions, empty pending outbox และ final assets สำเร็จ
- ไม่มี commit, push หรือ public deployment

### `WORK-20261002-006` — Normalize and redesign UI for executive clarity
- Timestamp: `2026-10-02T10:42:00+07:00`
- วางแผนและวิเคราะห์ UX/UI ให้เป็น Executive Overview ตามโจทย์ของผู้ใช้: เน้นให้เห็นภาพรวม 3-Way Match และเข้าใจสถานะเอกสารได้ทันที
- ปรับโครงสร้างหน้า Queue: ยุบตัวกรองซ้ำซ้อนให้เป็น Consolidated Control Bar ชิ้นเดียว, เพิ่ม 4 Interactive KPI Summary Cards, และใช้ตารางข้อมูลความคมชัดสูงพร้อม context chips
- ปรับโครงสร้างหน้า Document Detail: เพิ่ม Executive 3-Way Match Snapshot card 4 ช่องสำคัญ, Source Provenance Bar, 3-Step Verification Pipeline Stepper, Discrepancies Callout with 1-click jump to PDF evidence, และ Decision Hub
- ปรับแท็บรายละเอียดทั้ง 5: Summary Tab, Line Items Table (M1/M2 badges และตัวเลข tabular ชัดเจน), Rules Tab (STEP 1–3 badges และ error code chips), History Tab, และ Source/Revision Tab
- ปรับ Design System CSS: อัปเกรด Font Stack, Card Elevation, HSL Colors, Status Badges และ Responsive Layout ใน `global.css`, `mockup-parity.css`, `revisions.css`
- ตรวจสอบความถูกต้อง: Backend unittest 15 รายการผ่าน, TypeScript + Vite production build ผ่าน, Playwright E2E 6 รายการผ่าน (Edge browser 17.4s), ตรวจภาพจริงผ่าน Browser Subagent ทั้ง desktop และ mobile viewports
- ไม่มี commit, push หรือ public deployment


### `WORK-20261002-007` — Extend synthetic invoice corpus to 155 PDFs with engine-derived answer key
- Timestamp: `2026-10-02T18:40:00+07:00`
- ศึกษา `app/core/rules.py` และ `app/services/pipeline.py` เพื่อทำ replay path ที่เหมือน production ทุกขั้น รวมถึง branch ที่ skip Oracle (E28) และ skip STEP 3 (E17/E35/safety cap)
- ออกแบบ 100 เคสใหม่จากข้อมูล Oracle จริงใน `_raw/` โดยสร้าง `Picker` ที่เลือก receipt group แบบ deterministic (ใช้ครบทุก group ก่อนใช้ซ้ำ) และ scenario พิเศษ: ไม่มีใบรับ, หลายใบรับภายใต้ PO เดียว, price-swap, 50-row safety cap
- ให้ engine เป็นผู้ผลิต expected_result ทั้งหมด แล้วเพิ่ม invariants ตรวจผลรายหมวด (F ต้อง Auto-pass, I ต้อง intercompany=true, H ต้องมีหลาย code ฯลฯ) และ warn เมื่อ description รายงาน code น้อยกว่าจริง
- รัน `verify_dataset.py --fix` พบ drift 30 รายการของ wave 1 (ส่วนใหญ่คือ `halted_by` ที่เขียนเองและ E31 ที่เกิดพร้อม E34/E06) และ recalibrate จน drift = 0 / 155 เคส
- Render PDF ครบ 155 ไฟล์ (Tahoma, 3 layout, watermark/speckle, ต่อบัญชี 2 หน้า) และรัน `check_pdfs.py` ผ่าน 155 ไฟล์ 157 หน้าไม่มี mismatch
- ตรวจภาพจริง 3 หน้าด้วย pypdfium2 + Pillow: อักษรไทยถูกต้อง, watermark ไม่บังข้อมูล, พื้นที่ลายเซ็นผู้รับว่างตามเคส E26, หน้าต่อ (continuation) แสดงหัวเอกสารและเลขหน้า
- ติดตั้ง `fpdf2` และ `pypdf` ใน `.venv` ของ service เพื่อรันชุดทดสอบ (ไม่ถูกเพิ่มใน `requirements.txt` ของ production)
- ไม่มี commit, push หรือการเรียก Oracle/LiteLLM/Paperless จริง

### `WORK-20261002-008` — Wire the invoice corpus into an offline pytest gate
- Timestamp: `2026-10-02T19:05:00+07:00`
- เปลี่ยน `check_pdfs.py`/`verify_dataset.py` จาก script ล้วนเป็น module ที่ import ได้ (`audit(dataset)`, `verify(dataset, fix)`) โดยคง CLI เดิมไว้ แล้วสร้าง `tests/test_invoice_corpus.py` 7 test ครอบคลุม shape, engine drift, coverage, wave-2 invariants และ PDF ↔ key
- เพิ่ม `pytest.ini` + `tests/conftest.py` และ marker `live` เพื่อให้ `python -m pytest` รันเฉพาะชุด offline (ผลลัพธ์ `9 passed, 2 deselected in ~1.7s`) และรันจาก repo root ได้ผ่าน conftest path setup
- เขียน mutation check 4 แบบ (โกหกว่าฟิลด์หาย, โกหกว่าฟิลด์มี, โกหกจำนวนหน้า, โกหก decision) เพื่อยืนยันว่า gate ไม่ใช่ test เปล่า — พบว่า branch "ฟิลด์ที่ต้องหาย" ไม่ทำงานกับ wave 1 จึงแก้ให้ไปอ่านค่าจริงจาก `_raw` แล้วตรวจซ้ำผ่านทั้งหมด
- อัปเดต `OCR service/n8n/README.md` (หัวข้อ Offline Regression Suite) และ `tests/test_invoices/README.md` (หัวข้อ CI gate)
- ไม่มี commit/push และไม่มีการเรียก endpoint ภายนอก

## 2026-10-02 (รอบเย็น: n8n workflow)

### `WORK-20261002-009` — อัปเดต n8n workflow เป็น v6.5 ให้ตรงกับ Python engine ผ่าน MCP
- Timestamp: `2026-10-02T20:20:00+07:00`
- ตรวจสอบว่า `aiva-n8n` MCP ใช้งานได้ (connected + authenticated, 52 tools) แล้ว export workflow `aLUCmn3l0bZDjbVV` ตัวจริงลงมาอ่านทั้ง 23 nodes ก่อนแก้
- อ่าน `app/core/rules.py`, `app/services/oracle_mcp.py`, `pipeline.py`, `vision_extractor.py`, `portal.py`, `paperless.py`, `master_data_service.py` ทั้งไฟล์ เพื่อเทียบ parity กับ n8n ทีละ node แล้วเก็บ JS ต้นฉบับไว้ที่ `tmp/nodes/*.js`
- ยืนยัน SQL shape ด้วย MCP `oracle` (`oracle_sql_run`): invoice `112603974` ไม่ปรากฏใน `RCV_INV_NUM` (primary query คืน no rows) แต่ branch `PO_NUM='40121195'` คืนแถว → จึงใช้ `(Invoice+Tax) OR (PO_NUM)` ในคำสั่งเดียว และ scalar `SUPPLIER_IS_INTERNAL` จาก `financials_system_params_all` ตรวจ intercompany (tax `0145556001111` คืน 1)
- อัปเดตด้วย `aiva-n8n_update_workflow` หลาย-call (atomic): `N2.4`, `HTTP Request`, `N4`, `N7` (jsonBody), `N7.1`, `N8`, `N9`, `N10`, `N12` (settings + options), `N13` และเปลี่ยนชื่อ workflow เป็น `AIVA PO-INV Matching Verification v6.5`; คง `N5`/`N11` ไว้เพราะตรงกับ Python แล้ว
- พบว่า `setNodeParameter.path` สัมพัทธ์กับ `parameters` ทำให้ call แรกเขียน code ลง `parameters.parameters.jsCode` — แก้โดยเขียน path เป็น `/jsCode`, `/jsonBody`, `/options` และล้างค่าค้างด้วย `value: null` แล้ว export ซ้ำเทียบ byte-for-byte: **7 jsCode + N7 jsonBody ตรงกับไฟล์ต้นฉบับทุกตัวอักษร**
- ตรวจ `jsCode` ทั้ง 12 Code nodes ด้วย `node --check` (ผ่านทั้งหมด) และเขียน harness `tmp/run_flow_sim.js` ที่ **รัน jsCode ที่ export จาก workflow จริง** กับ input จำลอง 7 เคส: Auto-pass, PO fallback, E28 bypass, E17, E06, E35, intercompany+E26 — ผลตรงกับ Python ทุกเคส และผ่าน N11 Schema Validate ครบ
- แก้ `OCR service/n8n/n8n flow structure.md` เป็น v6.5: ตารางสิ่งที่เปลี่ยน, หลักการ D2/D3, ผัง mermaid, ตาราง node 8/9/13/14/15/17/20/21, SQL section ใหม่ (dual branch + โหมด `INVOICE/PO_FALLBACK/PO/NONE` + ข้อจำกัด `ORA-01791`), กฎ V-07, Python↔n8n Parity Map, ผล regression test และบันทึกข้อควรระวังของ MCP tool
- Workflow ยัง `active: false` จึงไม่มีผลกระทบ production ระหว่างแก้; ไม่มีการเรียก LiteLLM/Paperless/Portal จริง และไม่มี commit/push ในรอบนี้
- ก่อน commit: สร้าง `.gitignore` ของ repo (กัน archive, `tmp/`, `.pi/`, `.mcp.json`, ไฟล์ผลรัน batch ที่มีข้อมูล invoice จริง และ corpus ที่สังเคราะห์จาก Oracle extract) และเพิ่ม module-level skip ใน `tests/test_invoice_corpus.py` เพื่อให้ clone ที่ยังไม่มีข้อมูล corpus รัน pytest ผ่าน — ตรวจจริงทั้งตอนมีข้อมูล (`9 passed, 2 deselected`) และตอนถอดข้อมูลออก (`2 passed, 1 skipped`)

## 2026-10-02T20:55:00+07:00 — TASK-20261002-009: Comprehensive .gitignore for Company Sensitive Data & Push to Remote

- สำรวจความเสี่ยงข้อมูลความลับขององค์กรที่อาจหลุดขึ้น Git Repository: Environment variables, credentials/API keys, private keys, SSL certificates, Oracle database artifacts (wallet, net configs, sqlnet, tnsnames, dumps), ข้อมูลการเงิน/ใบแจ้งหนี้จริง (PDFs, Excel spreadsheets, CSV extracts), batch run reports/failed payloads, n8n automation local states, Python/Node runtime artifacts, IDE/Agent workspace files, OS metadata และ logs
- ยกระดับ root .gitignore ให้เป็นชุดกฎที่ครอบคลุม 12 หมวดหมู่อย่างสมบูรณ์ พร้อมจัดหมวดหมู่อย่างเป็นระเบียบ และกำหนดข้อยกเว้นสำหรับ template (!.env.example) และ mock test fixture (!invoice-web/examples/invoice.pdf)
- ตรวจสอบยืนยันด้วย git check-ignore -v เทียบกับ pattern จำลอง 25+ รายการ (.env, *.key, *.pem, *.pfx, cwallet.sso, tnsnames.ora, *.db, *.dmp, *.pdf, *.xlsx, *.csv, *.log, *.zip, .DS_Store, Thumbs.db) พบว่าถูก ignore ถูกต้อง 100%
- ตรวจสอบยืนยันว่า invoice-web/examples/invoice.pdf และ .env.example ไม่ถูก ignore (exit code 1)
- รัน regression tests ยืนยันว่าระบบทำงานปกติ:
  - OCR service/n8n/.venv/Scripts/python -m pytest: 9 passed, 2 deselected in 1.28s
  - invoice-web/backend unittest: 15 passed in 2.332s
- ปรับปรุง canonical records: gent/current-state.md, gent/task-plan.md, gent/changelog.md, gent/work-log.md, gent/sessions/2026-10-02-009-comprehensive-gitignore-sensitive-data.md
- เตรียม commit และ push สู่ origin/main

## 2026-10-03T09:33:00+07:00 — TASK-20261003-001: Consolidate Web Portal Files and Workflow into Web portal/ Folder

- สอบถามความต้องการชัดเจนของผู้ใช้ผ่าน ask_question tool และได้รับคำยืนยันให้ย้ายเนื้อหาทั้งหมดจาก invoice-web/ (frontend, backend, docs, examples, infra, tests, scripts) และ Review Action Workflow ของ Web Portal เข้ามาไว้ในโฟลเดอร์ Web portal/
- ย้ายไฟล์และโฟลเดอร์ที่ถูก track ใน git ทั้งหมดจาก invoice-web/ ไปยัง Web portal/ ด้วย git mv (backend, frontend, docs, examples, infra, .env.example, .gitignore, README.md, run-local.ps1) ทำให้รักษาประวัติ git ได้ครบถ้วน
- ย้ายโฟลเดอร์ data/ และลบโฟลเดอร์ invoice-web/ ที่ว่างออก
- ปรับปรุง root .gitignore: เพิ่มการ ignore Web portal/data/ และ Web\ portal/data/ พร้อมคงข้อยกเว้น !Web portal/examples/invoice.pdf และ !Web\ portal/examples/invoice.pdf
- ทดสอบ git check-ignore: Web portal/data/tests/sample.sqlite3 ถูก ignore ถูกต้อง และ Web portal/examples/invoice.pdf ได้ exit code 1 (ไม่ถูก ignore)
- ปรับแก้ path อ้างอิงใน Web portal/run-local.ps1, Web portal/README.md, Web portal/.env.example, และเอกสาร Web portal/docs/
- รันการทดสอบยืนยันผลจริง:
  - Web portal/backend unittest: 15 passed in 6.303s (รวม test_project_structure_keeps_entrypoints_and_boundaries_small)
  - OCR service/n8n pytest: 9 passed, 6 deselected in 5.22s
- บันทึก canonical records (current-state.md, task-plan.md, changelog.md, work-log.md, session file) ครบถ้วนตาม protocol

## 2026-10-03T13:35:00+07:00 — TASK-20261003-002: อัปเดต n8n canvas + docs เป็น Standard v6.6 (Explanatory Flow)

- รับคำสั่งให้ทำ 4 สิ่ง: (1) เอกสาร flow แบบ logic-first (2) อัปเดต parity matrix (3) แก้ canvas ผ่าน MCP `aiva-n8n` (4) ตรวจ connections + memory
- ก่อนแก้ทุก batch ทำ backup full workflow JSON และแยกไฟล์ต่อโหนดเก็บไว้ (restore ได้) แล้ว diff โค้ด 7 jsCode nodes + `N7` jsonBody ระหว่าง live canvas กับ canonical copies → ต่างเฉพาะ comment จึง resync live → local และตรวจ `node --check` ผ่าน
- แก้ canvas แบบ batch: rename workflow/description → v6.6 (Explanatory Flow), ปรับ IF gate condition ให้ใช้ boolean field ใหม่, rename `N7`/`N8`/`N9` และ IF nodes 3 ตัว, เพิ่ม Sticky Notes 8 ใบ, จัด 6 Node Groups
- เจอปัญหา 2 ครั้งติดที่ `setNodeGroups` ถูก skip (group มี `Manual Trigger` ปน / ชื่อ IF โดนตัด `?` ท้าย) → แก้ด้วยการ rename IF ให้ไม่มี `?` แล้วส่ง group ops พร้อมกัน ใน batch เดียว → group ตั้งครบและคำเตือน `TOP_LEVEL_ITEMS_OVER_CEILING` หมดไป
- ตรวจ canvas ด้วยสคริปต์จาก live export (edges/dangling/`$()` refs/ตำแหน่ง sticky ชัดเจนว่าทับโหนดหรือไม่) เพราะ `aiva-n8n_validate_workflow` ตรวจได้แค่ shape ของ SDK code ไม่ใช่ canvas จริง
- ยืนยันกับ Oracle EBS จริงด้วยบิล `ED6909/0837`: 7 แถว ข้าม 3 POs (`40083989`,`40089558`,`40118686`), GR `510522788`, receiver `Oracle, Concurrent` และตรวจว่า view เก่า `APPS.AH_DEV_RCV_PO_AP_MATCHING_V` (29 คอลัมน์) ไม่มีคอลัมน์จำเป็นของ v6.6
- สร้าง `OCR service/n8n/docs/workflows/n8n_flow_v6_6.md` (376 บรรทัด, logic-first, มี mermaid + 4 สถานการณ์ตัวอย่าง + ตารางเทียบรหัสเก่า/ใหม่) และเขียน `parity_spec_matrix.md` ใหม่เป็น v2.0.0 (ตาราง 23 โหนด + data contract ราย edge + ตารางเทียบ E01–E15 ↔ รหัสเดิม + checklist 6 ข้อ)
- คงความต่างระหว่าง Python กับ Canvas ไว้ตรง ๆ ในเอกสาร (Canvas รวม Two-Hop เป็น query เดียว, Python ยิงสูงสุด 2 queries; `E11` ยังไม่ถูกยก) แทนการเขียนว่า "เหมือนกัน 100%"
- Workflow คงสถานะ `active: false` ตามนโยบาย ไม่เปิด schedule
- บันทึก canonical records ครบทั้งชุด root (`current-state.md`, `task-plan.md`, `changelog.md` CHG-20261003-002, `work-log.md`, `errors-and-solutions.md` ERR-20261003-001/002, session file) และชุด service (`.agent/` CHG-20261003-004, TASK-011, work-log, active-plan, session)

## 2026-10-03T14:25:00+07:00 — TASK-20261003-005: เทียบผล n8n canvas กับ Python engine + แก้ SQL ของ N7

- รับคำสั่ง "ทำ task ทุกอย่างให้สมบูรณ์" → เป้าคือปิด follow-up ที่ค้าง: (1) parity test จริง (2) ย้าย credential (3) E11 (4) commit
- Parity test: ทำได้ครบโดยไม่แตะระบบจริง — ใช้ fixture เดียวกันรัน Python pipeline แล้วรัน canvas ผ่าน `aiva-n8n_test_workflow` พร้อม pinData ที่ `N2`/`N2.3a`/`N2.3b`/`N3`/`N7`/`N12`/`N13.1` (execution `#324` success, `lastNodeExecuted = N14`)
- สิ่งที่เจอจริงและแก้: `N7` ดึงแถวกว้างเกิน (8,359 แถวจาก PO เดี่ยว) เพราะ branch PO ไม่มี guard และไม่มี Hop 1 → inline Hop 1 + `NOT EXISTS` ทำให้เหลือ 7 แถว โดยผลลัพธ์เท่า Python (ตรวจกับ Oracle ทั้ง 2 branch ก่อน deploy)
- `N11`: normalize `rules[]` ให้ตรงกับ `model_dump()` ของ Python (key `code`/`severity`/`details` = null เมื่อ PASS) เพื่อให้ body ที่ POST เข้า Portal เท่ากันจริง
- สรุปผลเทียบ: decision/rules/exceptions + `dms`/`access`/`receiver`/`invoice_summary` ตรงกันทั้งหมด; known deltas 3 ข้อเป็น cosmetic/superset จึงบันทึกไว้ในเอกสารแทนการแก้
- ประเด็นที่ยังทำไม่ได้จริง: (1) ย้าย Bearer token ของ `N7` ไป credential — MCP มีแค่ read-only (`aiva-n8n_list_credentials`) ต้องทำใน UI และ token หมดอายุ 2026-10-28 (2) `E11` รอนโยบาย Accounting (3) `N12` ยังชี้ httpbin จึงไม่รัน execution เต็มจริงกับเอกสารจริง (จะ tag บิลโดยผลลัพธ์ไม่เข้า Portal)
- พบงานคู่ขนาน: อีกรันหนึ่งของ agent (`TASK-012` 3-Way Pipeline) กำลังแก้ไข `app/engines/`, `tests/test_corpus_v66.py` และไฟล์ memory ชุดเดียวกัน → tier `corpus` มี fail จากงานนั้น (ไม่ได้แตะ) และ ID ใน `.agent/CHANGELOG.md` มีเลขซ้ำกัน (002 ถูกใช้ซ้ำ) จึงขยับไปใช้ `CHG-20261003-005` / `TASK-013`
- commit แยกเฉพาะงานนี้: `docs/workflows/n8n_flow_v6_6.md`, `docs/workflows/parity_spec_matrix.md` + ไฟล์ memory (เพื่อไม่ดึงโค้ด WIP ของอีก session ที่ยัง commit ไม่เสร็จ)

## 2026-10-03T14:35:00+07:00 — TASK-20261003-006: ทำให้ corpus v6.6 เป็น benchmark ที่เชื่อได้จริง

- เริ่มจาก audit แทนการเชื่อสถานะที่ส่งต่อมา → พบ 14 failed / 199 passed, runner ไม่รวม v6.6 tier และ multi-PO 36 เคสสร้างจากเลขที่ใบรับที่ไม่มีใน ERP
- หลักที่ยึด: (1) ทุก expectation ต้อง re-derive ผ่าน `app.core.rules` (2) ห้ามสังเคราะห์เลขที่เอกสาร ERP (3) ตัวเลข realism ต้องวัดจาก dataset แล้ว assert ไม่ใช่ hardcode ในรายงาน (4) แตะ engine เท่าที่จำเป็นและเฉพาะ `app/core/rules.py` เพื่อไม่ชน TASK-012
- ทำจริง: เพิ่ม `gate_halt_reason()` (Gate 2 ต้องบอกชื่อ breaker), เก็บ multi-PO จริงจาก Oracle 28 ใบรับเข้า snapshot v1.1, deterministic realism weaving + fail-fast guard, แก้ renderer ที่พิมพ์ `None` ในกล่องยอดรวม, ปิด test bug ที่นับกล่องลายเซ็นได้ 0 เสมอ (needle ไม่ได้ collapse), ต่อ suite เข้า runner, sync เอกสาร contract
- เคสที่ตรวจพบระหว่างทางแล้วแก้ตรง ๆ: 043/046/049 (ราคาต่าง → กลายเป็น Hold), 068 (defect ฝังไม่ลง → Auto-pass เงียบ), 080 (draw ใบที่มีแถว EXPECTED → E05 ปลอม), 069 (PDF พิมพ์คำว่า None), 007/022 (บิลหลาย PO แต่พิมพ์ PO เดียว)
- ผลลัพธ์: 100 cases 35/30/30/5 · re-derived 100/100 · 215 corpus checks passed · `run_tests.py --all` ALL PASSED · answer key เก่า 155 ใบ recalibrate เฉพาะ `halted_by` 9 เคส
- สิ่งที่ไม่แกล้งทำให้ผ่าน: คง E11/E13 เป็น documented gap, คง intercompany = 4 (อีก 1 เคสถูก Gate 1 ตัดก่อนถึงขั้น flag), คง Known delta 4 ของ canvas ไว้ในเอกสาร
- บันทึก canonical records ครบทั้งสองชุด (root `agent/` + service `.agent/`) และย้าย plan ไป `plans/completed/`

## 2026-10-03T15:35:00+07:00 — TASK-20261003-007: Integrate `origin/main` (portal restructure) เข้ากับ main โดยไม่แตะ `OCR service/`

- อาการที่ผู้ใช้เจอ: `git pull` ค้างที่ `error: Your local changes ... would be overwritten by merge` + `Merge with strategy ort failed` ส่วนบรรทัด `trailing whitespace` / `11 lines add whitespace errors` เป็นแค่ warning ไม่ใช่ต้นเหตุ
- ต้นเหตุจริง: branch diverged (ahead 1 / behind 6) และฝั่ง local มี **การย้ายโฟลเดอร์ที่ยังไม่ commit** (`invoice-web/` → `Web portal/` 87 ไฟล์ staged + 6 ไฟล์แก้ใน worktree) ขณะที่ `origin/main` ย้าย `invoice-web/` ไป `Web portal/invoice-web-9054076/` และเพิ่ม mockup ใหม่ → git ไม่ยอมเขียนทับ path ที่สกปรกอยู่
- หลักฐานว่า "บังคับ merge" อันตราย: ผล merge ที่ค้างใน `.git/AUTO_MERGE` (`06527b26`) มีแค่ 159 ไฟล์ เทียบ `origin/main` 340 ไฟล์ คือจะ **ลบงาน mockup ของอีกฝั่งทิ้ง 176 ไฟล์** (invoice-web1 106, invoice-webV2 58, invoice-webv3 9, `.agents` 3) + session log 8 ไฟล์
- ตรวจก่อนลงมือด้วย `git merge-tree --write-tree` (merge จำลองที่ระดับ commit ไม่แตะ worktree) → ผลจริงมี conflict เนื้อหาไฟล์เดียวคือ `agent/current-state.md`; portal renames ฝั่ง remote เป็น `R100` (เนื้อหาไม่เปลี่ยน) งานแก้ 6 ไฟล์ของเราจึง apply ได้โดยไม่ชน
- backup สองชั้นก่อนแตะอะไร: `git stash create -u` → snapshot branch `backup/wip-dirty-20261003` และ `git status --porcelain` ทุก path → `C:\Users\wajeepradit.p\git\wip-backup-20261003\` (136 paths / 160 ไฟล์ / 4.7 MB) — ไม่ลบ `Web portal/data/tests/bootstrap/portal.sqlite3` (runtime data เดิมคงไว้)
- ผู้ใช้สั่งให้รับ layout ของ remote จึง: unstage + `git checkout HEAD -- invoice-web` คืนไฟล์เดิม → `git rm -r --cached -f -- "Web portal"` → `git clean -fd -- "Web portal"` (ตั้งใจไม่ใช้ `-x` เพื่อไม่ให้กินไฟล์ ignored) → ลบ `__pycache__` และโฟลเดอร์ `Web portal/backend` ที่เหลือแต่โครงเปล่า
- commit records ของ `agent/` + แก้ `.gitignore` ให้ตรง layout ใหม่ก่อน แล้ว `git merge --no-ff origin/main` → conflict ตามที่คาดไว้ 1 ไฟล์ แก้ด้วยมือโดยคงเนื้อหาทั้งสองฝ่าย (Mockup v3 + skill ฝั่ง remote / n8n v6.6 corpus + parity ฝั่งเรา) และแก้ path เป็น `Web portal/invoice-web1/docs/...` → merge commit `2ce5b9e`
- ผลตรวจหลัง merge: `python -m pytest -q` ใน `OCR service/n8n` = **235 passed, 9 deselected (35.10s)** · `pytest "Web portal/invoice-web1/backend/tests"` = **15 passed (3.68s)** · `node tools/smoke-test.js` ของ mockup v3 ผ่าน 46 การตรวจ · `git rev-list --left-right --count origin/main...HEAD` = `0 3`
- พิสูจน์ว่าไม่แตะ `OCR service/`: `git diff --name-only <merge-base> origin/main -- "OCR service"` คืน 0 ไฟล์ และ working tree ของโฟลเดอร์นี้ยัง dirty เท่าเดิม 41 รายการ (15 แก้ไข + 26 untracked) — ใช้ venv ของ n8n รัน test อย่างเดียว ไม่ได้เขียนไฟล์ในโฟลเดอร์
- พบของใหม่ที่ต้องตาม: `python tools/build-domain-data.py --check` = rc 1 (`master_data.py shape changed; update this generator`) แปลว่า `assets/data.js` ของ mockup v3 ล้าสมัยต่อ `master_data.py`/`rules.py` ที่แก้ไว้ใน working tree ฝั่งเรา
- หมายเหตุ protocol: `agent/sessions/` ปี `2026-10-03` มี sequence 001–004 ซ้ำกันระหว่างสองผู้เขียน (ชื่อไฟล์ไม่ชนกันแต่ ID ซ้ำ) งานรอบนี้จึงใช้ `2026-10-03-005` และรอบถัดไปให้เริ่มที่ 006; ยังไม่ push รอคำสั่งผู้ใช้

## 2026-10-04T15:22:00+07:00 — TASK-20261004-001: ปลดล็อก `bbox_testv3.py` แล้วเริ่ม batch vision-OCR 99 ฉบับ (workers=2)

- ผู้ใช้สั่งเริ่มรัน `bbox_batch.py --workers 2` แต่ไฟล์จริงชื่อ `bbox_testv3.py` (docstring เขียนชื่อไฟล์ผิดไว้) → ก่อนยิง AI ตรวจสภาพไฟล์ก่อน พบ blocker 3 ข้อที่ซ่อนอยู่ ซึ่งล้วนทำให้รันไม่จบหรือเสียเวลาฟรี
- Blocker ที่พบจริง: (1) ทั้งไฟล์ถูกเขียนซ้ำเป็นสองสำเนา byte-identical → `main()` ถูกเรียก 2 รอบ (2) สคริปต์อ่าน `.env` แต่โฟลเดอร์มีแค่ `env` → `SystemExit` เรื่อง token (3) console cp874 ทำให้ `print` บรรทัดแรกที่มี `·` crash ด้วย `UnicodeEncodeError` (เจอจาก log จริง ไม่ใช่การคาดเดา)
- หลักที่ยึด: แตะเฉพาะ "ชั้นรัน" ไม่แตะ logic OCR/coord/filter/report เพื่อไม่ให้ผล batch ที่กำลังจะเทียบกับการรันก่อนหน้าเพี้ยน; ไม่สร้างไฟล์ `.env` ใหม่ (ลดสำเนา secret); แก้ที่ต้นเหตุในโค้ดแทนการใช้ `PYTHONIOENCODING` ชั่วคราว เพราะจะกลับมาพังเมื่อผู้ใช้รันเองใน PowerShell/cmd
- วิธีพิสูจน์สำเนาซ้ำก่อนลบ: `sed -n '1,653p'` / `sed -n '654,1306p'` แล้ว `diff` ได้ 0 บรรทัด จึงแน่ใจว่าการตัดออกไม่ทำให้โค้ดส่วนใดหาย
- เริ่ม batch จาก `OCR service/new engine/tests/`: `PYTHONIOENCODING=utf-8 python -u bbox_testv3.py --workers 2 > run_v3.log 2>&1 &` → Paperless มี **99 ฉบับ** (ยืนยันจาก `/api/documents/` count) ต้องทำ 99 (fresh, ยังไม่มีผลเก่า) workers=2
- ผล interim ณ เวลาบันทึก: 8 ฉบับแรก `ok` ทั้งหมด ไม่มี error/partial · ~20 s/หน้า · มีเอกสารยาว 11 หน้า (`doc 27`) ทำให้ ETA 99 ฉบับอยู่ราว 45–70 นาที · output ลง `new engine/tests/out/batch/` (`report.html` + `summary.csv` เขียนทุก 5 ฉบับ, ต่ละฉบับมี `original.pdf`/`page_N.jpg`/`doc.json`/`viewer.html`)
- หมายเหตุการทำงาน: `nohup` + `&` ใน git-bash บน Windows ทำให้ harness รายงาน "background command completed exit code 0" ตอนที่ shell wrapper ออก ขณะที่ process Python ยังรันต่อ — ต้องยืนยันด้วย `ps -W` + mtime ของ log ไม่ใช่เชื่อ exit code

## 2026-10-04T16:56:00+07:00 — TASK-20261004-001 (ต่อ): report bbox แบบโต้ตอบ + ปิด batch 99 ฉบับ

- ผู้ใช้เปิด `out/doc_99/report.html` แล้วบอกว่าจะดูข้อมูลของกรอบได้ต้องชี้/คลิก → ชี้ให้ชัดว่า "ภาพมีกรอบเผาอยู่ในไฟล์ + ตารางคนละที่" คือช่องว่างของ workflow ตรวจงาน OCR
- เลือก overlay ที่คำนวณจาก `bbox_norm` ที่มีอยู่ในผลเดิม (ไม่เรียก AI ใหม่ ไม่แก้ `filter_items`) เพราะงานนี้คือชั้น UI ไม่ใช่ชั้น engine และทำให้สร้าง report ใหม่จากผลเก่าได้ฟรี (`--report-only`)
- ทำให้ทั้งสอง report มีพฤติกรรมเหมือนกัน: `bbox_test.py` (ต่อฉบับ) และ `bbox_testv3.py` (batch รวม) → ชี้ = tooltip + ไฮไลต์คู่ box↔แถว, คลิก = ตรึง panel + scroll ไปแถว, Esc/คลิกซ้ำ = ปลด, toggle ซ่อนกรอบ
- ทดสอบแบบ DOM จริงด้วย jsdom (ไม่มี browser/headless ในเครื่อง): harness ตรวจ 20 ข้อ ทั้ง tooltip เปิด/ปิด, ข้อมูลตรงกรอบ, sync สองทาง, ตรึง/ปลด, toggle → ผ่าน 20/20 ทั้ง `out/doc_99/report.html` (32 กรอบ) และ `out/batch/report.html` (15,111 กรอบ) · harness เจาะเจอ `scrollIntoView` ไม่มีใน jsdom จึงใส่ guard ให้ปลอดภัยกับ renderer ที่ไม่รองรับ
- ผล batch รอบแรก (`--workers 2`, 15:15:54→16:55:51): **99/99 ฉบับ · 425 หน้า · 14,991 กรอบที่เก็บ · ตัดทิ้ง 51 · 98 `ok` / 1 `partial` · 0 doc-level error** ใช้เวลา 5,951 s (~99 นาที, เฉลี่ย 24.7 s/หน้า, max 191.6 s) · doc_type ต่อหน้า: tax_invoice 236, purchase_order 90, delivery_note 48, other 18, osp 14, invoice 12, tax_invoice_receipt 6, unknown 1 · เหตุผลที่ตัด: zero_area 34, no_text 11, duplicate 6 · ประเภทกรอบ: header 3,772, other 2,771, customer 1,827, supplier 1,599, total 1,496, signature 1,363, line 1,218, table 539
- เคส fail เดียว: `doc 27 p9/11` model ตอบไม่มี JSON (`no JSON / no items`) → รัน `--retry-errors --workers 1` ซ่อมฉบับนั้นฉบับเดียว (11 หน้า, 210 s) **ผลหลังซ่อม: 99 `ok` / 0 `partial` · 0 page error · 15,111 กรอบที่เก็บ · ไม่มี unknown เหลือ** — ตัวเลขที่อ้างอิงใน current-state/changelog ใช้ค่าหลังก่อน
- 17:05 — ตรวจ `.gitignore` ก่อนมีใคร commit `new engine/`: เจอความเสี่ยงจริง 2 จุด → `tests/env` (มี API key) และ `out/**` (ภาพเอกสารจริง + ผล OCR) **ไม่ถูก ignore** เพราะ pattern เดิมมีแต่ `.env`/`*.env` จึงเพิ่มหมวด 13 ใน `.gitignore` ครอบคลุม 3 path → ตรวจซ้ำด้วย `git check-ignore` (IGNORED ครบ) และ `git status -uall` เหลือ 42 ไฟล์ source เท่านั้น (`CHG-20261004-003`) · ยังไม่ได้ commit อะไรทั้งสิ้น

## 2026-10-05
- 20:38 — ผู้ใช้ขอให้ตรวจสอบงานที่ดำเนินการไปแล้วใน system-a และดำเนินการต่อ
- 20:40 — ตรวจสอบ 
uns/iteration_log.md, 
uns/2026-10-05-full/, 
eports/2026-10-05-full/, และ erify_report.json พบว่าการรัน batch 99 เอกสารและการสร้างรายงานเสร็จสิ้นแล้ว แต่มีรายการตกค้างใน iteration_log.md คือการนำข้อค้นพบ DIAGNOSE ใส่ใน FINDINGS.md และการรัน 
un_stats.py เพื่อเติม Numbers appendix
- 20:43 — พบ UnicodeEncodeError บน Windows cp874 console เมื่อรัน 
un_stats.py และ erify_run.py ทำการแก้ไขด้วย sys.stdout.reconfigure(encoding='utf-8') และเปลี่ยน ≥ เป็น >=
- 20:44 — รัน 
un_stats.py --run-id 2026-10-05-full สำเร็จ ได้สถิติจริงครบถ้วน อัปเดต FINDINGS.md (เพิ่มข้อ 3.7, 3.8, O-09, O-10, และ Numbers appendix)
- 20:45 — คัดลอกเอกสารส่งมอบ (FINDINGS.md, iteration_log.md, sql_registry.md) เข้า 
uns/2026-10-05-full/ และอัปเดต 
uns/LATEST เป็น 2026-10-05-full
- 20:47 — รัน python scripts/verify_run.py --run-id 2026-10-05-full ผลคือผ่าน **14/14 Acceptance Criteria (100%)**
- 20:48 — บันทึก Canonical Records ใน gent/ ครบถ้วนตาม AGENTS.md

- 21:01 — ผู้ใช้ต้องการให้ลบไฟล์ test และไฟล์ที่ไม่จำเป็นออก ให้เหลือเฉพาะ Core Engine ที่รับ PDF แล้วแปลงเป็น final result เพื่อลดความสับสน
- 21:03 — สอบถามผู้ใช้เรื่องขอบเขตการจัดเก็บไฟล์ runs/ และ reports/ ผู้ใช้เลือกให้ย้ายไฟล์ทั้งหมดที่ไม่ใช่ Core เข้าสู่โฟลเดอร์สำรอง archive/
- 21:05 — สร้างโฟลเดอร์ archive/ และย้าย tests/, sandbox_data/, runs/, reports/, docker/, scripts/, src/system_a/sandbox/ และ FINDINGS.md เข้าไปเก็บรักษาไว้อย่างปลอดภัย
- 21:06 — พัฒนาสคริปต์ process_pdf.py ที่ root ของ system-a/ รองรับการรับไฟล์ PDF เดี่ยว สกัดข้อความด้วย Perception, ค้นหาใบรับจาก Oracle EBS, รัน Rules V-01..V-09, Line Matching และบันทึกผลลัพธ์ result-3.0
- 21:11 — ทดสอบรัน process_pdf.py กับไฟล์ตัวอย่าง 20.pdf จริง สำเร็จใน 33.6 วินาที ได้ผลสรุปและ JSON สัญญา 3.0 ถูกต้องครบถ้วน
- 21:12 — ปรับปรุง README.md ให้เป็นคู่มือกระชับ เข้าใจง่าย และบันทึก Canonical Records ครบถ้วน

- 21:16 — บันทึกไฟล์ตัวอย่าง Final Payload ของทั้ง 2 ระบบ (OCR_rule vs System A) ไว้ที่ system-a/payload_examples/
- 21:44 — เริ่มงานตาม `task.md`: อ่าน `.agent/*`, สำรวจ codebase และ Standard v6.6 ฉบับจริง (§03/§04/§05-§08)
- 21:57 — สร้าง rollback anchor: สำเนา config+src 85 ไฟล์ลง `.agent/baseline/` และ git commit `291bd76`
  (เดิม `system-a/config` และ `system-a/src` ไม่ถูก track ทำให้คำสั่ง rollback ของ task.md ไม่มีผล)
- 22:00 — สร้าง harness การวัด (replay บน perception cache ที่ pin ไว้) และพิสูจน์ความเที่ยงด้วยการรัน
  `process_pdf.py --dms-id 20` จริง (42.4s, ใช้ cache) เทียบระดับ exception code แล้วตรงกันทุก code
- 21:58–23:20 — รัน baseline 99 ฉบับ `full_r0` ใน background เป็น regression anchor
- 22:05 — สแกน V-01 ทั้ง 99 ฉบับแบบไม่ใช้ LLM: ตก 95 ฉบับ; ไม่มี cell หน่วยนับ 238 บรรทัด;
  `customer_name` conf ต่ำ 86/99, `customer_address` 82/99; `pages_complete=false` 21/99
- 22:25 — query ERP หาหลักฐาน ORG_ID: ยืนยันว่า RCV-V01 คืน operating unit id (101/176/195) แต่ตารางที่ 4
  ของมาตรฐานใช้ sub-org id (103/175/196) ซึ่งไม่ทับกันเลย → ต้นเหตุที่ V-05 เป็น Manual Review 100%
- 22:35 — MUT-01 เขียน `buyer_entity.yaml` ใหม่ (28 แถวมาตรฐาน + 12 bridge + 14 unknown ตามที่มาตรฐานสั่ง)
  and ปฏิเสธการใช้ข้อมูลใบแจ้งหนี้มาสร้างทะเบียนลูกค้า (วนเวียน ทำให้ V-05 ไม่มีความหมาย)
- 22:40 — MUT-02 เขียน `uom_groups.yaml` ใหม่จากคลังคำหน่วยนับจริง 32 รูปแบบของ 99 ฉบับ; ตรวจ pairwise
  ว่าไม่มีการ map ข้ามกลุ่ม (X-06) และวัดผลด้วย `uom_diff.py`: E10 70 -> 68, E10 ใหม่ 0
- 22:45 — วัดผล MUT-01 ด้วย `v05_predict.py` (83 ฉบับ): V-05 `manual_review` 53 -> 0, ไม่เกิด E07เท็จเลย
- 23:05 — probe gateway ที่หน้า 3 ของ DMS-20 (หน้าที่ page_items เคยพัง) พบ `reasoning_tokens 2577`
  จาก `completion_tokens 5819` และ `max_tokens 8000` → MUT-03 แก้ JSON decode recovery ใน
  `litellm_client.py` + ติดธงหน้าที่ salvage ใน `vision_pipeline.py`; unit test `test_salvage.py` ผ่าน 12/12
- 23:10 — เปิดรัน Tier B (`process_pdf.py --dms-id 20` re-perception ลง cache แยก) เพื่อวัดผล MUT-03 จริง
- 23:15 — ตั้ง `full_r1` ให้รันต่ออัตโนมัติเมื่อ `full_r0` จบ (regression gate ของ MUT-01/MUT-02)
- 23:33 — Tier B สำเร็จ (รัน perception ใหม่ลง cache แยก): หน้าที่ 3 ของ DMS-20 ที่เคย `no JSON object`
  อ่านได้ใน 40 วินาที `pages_complete` false → true และ rules ตัดตารางซ้ำออก (เส้นบิล 12 → 6)
  ผลรวมเอกสาร: max severity **High → Medium**, E11/E13 หาย 9 รายการ, V-05 หลุด false hold
- 23:40 — นับสถานะ cell หน่วยนับทั้ง 608 เส้นของ baseline: `NOT_PRESENT` 238 (39.1%),
  `LOW_CONFIDENCE` 168 (27.6%), ใช้ได้ 202 (33.2%) → แก้ backlog TASK-V01-00 ให้แยกอสมติสองข้อออกจากกัน
- 23:45 — (บันทึกนี้ถูกแก้วันที่ 2026-10-06) สรุปผิดว่า `cache_key()` ไม่รวม `code_version` — จริง ๆ
  `process_pdf.py` ส่ง `opts["pipeline"] = pipe.code_version` เข้า key และ `_code_fingerprint()` hash
  source ของ pdf_ingest/coords/vision_pipeline อยู่แล้ว สิ่งที่เหลือเป็นช่องว่างจริงคือไฟล์ cache ไม่ได้เก็บ
  code_version ไว้ จึงต้องทดสอบ perception ด้วย `PERCEPTION_CACHE_DIR` แยก (ERR-20261005-004 ฉบับแก้ไข)
  รันซ้ำดูเหมือนไม่มีผล; บันทึกวิธีทดสอบที่ปลอดภัย (cache แยก) ไว้ใน recovery/todo
- 23:50 — แก้ tooling ของตัวเอง 2 จุดที่วัดผิด: fleet report แสดง group หน่วยนับจาก config ปัจจุบัน
  (ทำให้สับสนระหว่างรอบกับ config ที่แก้ไข) → อ่านค่ากลับจากรายงานของแต่ละรอบ, และ diff นับเอกสาร
  ที่ยังไม่ได้รันเป็น "improved/regressed" → นับแยกเป็น not-in-both
- 23:52 — Regression gate ชั่วคราวบน `full_r1` 23 ฉบับแรก: comparable 23, improved 1 (DMS-25
  MANUAL_REVIEW → REVIEW), **REGRESSED 0**; V-05 เปลี่ยน 9/23 จาก manual_review (DMS-21 → pass)
- 23:54 — commit mutation แยกสามครั้ง `4d80ffc`, `9ab2e9c`, `64152ea` ทับ anchor `291bd76`
- 00:15 — บานปลายที่ควรบันทึก: `full_r1` 53 ฉบับ พบ `MANUAL_REVIEW -> HOLD` 2 ฉบับ (DMS-22, DMS-45)
  ตรวจแล้วไม่ใช่ accuracy loss — `recommend()` ให้ manual_review จากกฎมาก่อน severity ตอน V-06/V-05
  ตอบ manual_review ทุกฉบับ จึงบัง High finding (E03/E09/E13) ไว้ พอเอาตัวบังออก เอกสารกลับเป็น HOLD
  ตาม Table 8 ที่ถูกต้อง ปฏิเสธการใส่ manual_review เท็จกลับเพื่อให้ตัวเลขสวย และแก้ fleet_report
  ให้พิมพ์จำนวนกฎที่ตอบ manual_review ประกอบทุก regression

- 23:55 — ปิดงาน Web Testing Portal ครบ 5 phase + commit `2d87f6e`; พิสูจน์ความเป็น consumer ด้วย
  การรัน DMS-20 ผ่าน portal แล้วเทียบ `integrity.payload_sha256` กับ CLI → ตรงกัน (`sha256:399a3584…3dbf`)
- 23:56 — เจอและแก้บั๊ก schema 2 ชั้นที่ทำให้ overlay พัง/คลิกไม่ติด: (ก) `normalized_fields` เป็น
  name→string ไม่ใช่ object (ของจริงอยู่ `extraction.fields` + geometry ต้องข้ามไปอ่าน `ocr.elements`
  ผ่าน `element_id` / `evidence[].related_element_ids`) (ข) cell ไม่มี `element_id` จึง join ผ่าน
  `field_name = lines[<n>].<column>` และ (ค) API ใช้ key `id`/`raw_value` ขณะที่ viewer อ่าน
  `element_id`/`raw` → field/cell box คลิกไม่ติดเงียบๆ ใน browser
- 23:57 — สร้าง `web/test_ui_logic.mjs` รัน JS module จริงกับ DOM ปลอม เพราะ UI ไม่มี build step;
  จับได้ 3 ข้อพลาดจริง (label "undefined", กล่องไม่ถูก `.sel`, การคำนวณ pixel/point ผิดสูตรทดสอบเอง)
- 23:58 — ย้าย PDF.js จาก CDN มา vendor ใน repo (pdfjs-dist 4.10.38) + เพิ่ม test ห้ามมี CDN link
  ใน index/viewer; แก้ viewer ให้ worker ชี้ไฟล์ `.mjs` ตรงๆ (v4 ใช้ workerSrc เป็น path ไฟล์)
- 23:59 — ยืนยันผลบนข้อมูลจริง: DMS-20 fields มีกรอบ 12/13, cells 30/30, exception boxes 5;
  DMS-36 cells 8/10 ซึ่ง 2 cell ที่ไม่มีกรอบคือ `NOT_PRESENT` (ไม่มีที่ให้ชี้ — เป็นผลถูกต้อง)

- 23:59 — ผู้ใช้รัน verification ผ่าน portal แล้วเห็น `warning: The fitz API is deprecated` ชวนให้เข้าใจว่าพัง
  → แก้ที่ portal ไม่ใช่ core: `strip_ansi()` + `classify()` (info/warn/error + tooltip) commit `fec7451`
  ทดสอบ 26/26 และยืนยันบน SSE จริง (warn + hint, error 0)
- 23:59 — บันทึกไว้ว่าทำไมไม่แก้ `import fitz` ใน `pdf_ingest.py`: `_code_fingerprint()` อ่าน source bytes
  ของ pdf_ingest/coords/vision_pipeline มาทำ key — แก้ 1 บรรทัด = cache extraction 112 ชุดใช้ไม่ได้
  และต้อง re-perceive ~425 หน้า (~3 ชม. ของ VLM) จึงยกไปทำพร้อมงาน perception รอบถัดไป (DEC-016)

## 2026-10-06

- 07:30 — ต่อจากงาน portal ที่ค้างใน working tree (ยังไม่ commit): route `/api/verify/upload` ถูก
  `/api/verify/{doc_id}` กลืน และ error ของ Paperless ตอบ 502 หมดทุกกรณี → ตรวจว่าโค้ด+test ที่เขียนไว้
  ผ่าน (pytest 29) แล้วทำต่อให้จบรอบ
- 07:55 — เพิ่ม test ยืนยันว่า upload ที่อัปโหลดแล้ว verify ได้จริง (422 = route ผิดลำดับ) และ 404 ของ
  เอกสารที่หลุดจาก Paperless ต้องไม่อ่านเป็น portal พัง; รวมเคส token ถูกปฏิเสธ (502) กับไม่ได้ตั้งค่า DMS (503)
- 08:00 — เปลี่ยนฝั่ง UI ให้ error อ่านได้จริง: `api.js` ดึง `detail` ของ FastAPI มาแสดง (จากเดิม `404 {"detail":...}`),
  `viewer.js` ไม่ยอมให้ภาพที่โหลดไม่ออกจบแบบเงียบๆ — จะถาม endpoint กลับไปหาสาเหตุ และถ้า endpoint ยังให้ภาพได้
  จะบอกตรงๆ ว่า "browser ไม่วาด" ไม่ใช่บอกสาเหตุปลอม
- 08:05 — เปิด portal จริง (port 8080) เพื่อตรวจด้วย `web/check_live.py` → **checker ตายด้วย NameError (`Path`)**
  ที่บรรทัด health สรุปได้ว่าไฟล์นี้ไม่เคยถูกรันหลังเขียนจบ (และเป็นไฟล์ที่ยังไม่ถูก `git add` ด้วย)
- 08:08 — แก้ checker: `pathlib.Path`, `jload()` (body ที่ไม่ใช่ JSON = คำตอบ ไม่ใช่ crash), ABORT เมื่อ
  catalog ว่าง, และแก้เงื่อนไข check ของ upload ที่กรอง SSE ผิด key → ไม่เคยมีทางเขียว
- 08:10 — เพิ่ม pytest 1 ตัวรัน checker กับ port ที่ปิด (9) เพื่อบังคับให้ส่วนที่เหลือของไฟล์ถูกรันจริง
  ใน offline suite: ต้องได้ FAIL lines + ข้อความ ABORT ไม่มี traceback
- 08:12 — ผลสุดท้าย: pytest **31/31**, browser modules **27/27**, **live checker 77/77** บน portal จริง
  (upload → verify ผ่าน end-to-end, 404 อ่านได้, sandbox run ของ DMS-114 exit 0) → commit `5a058e0`
- 08:15 — ปิด server ที่เปิดทดสอบ และบันทึก ERR-20261006-001/002 (route shadowing + "tool ที่ไม่มีใครรัน = ยังไม่ถูกทดสอบ")
- 08:16 — เริ่มงาน perception ตามที่ user เลือก (UOM + `fitz`→`pymupdf` ในรอบเดียว) แต่**วัดก่อนจ่ายเงิน**
  cache reset: อ่าน `pdf_ingest.py`, `vlm_extractor.py`, `coords.py`, prompt `vision_table_rows.md` 1.2.0
  และ cache baseline 99 เอกสาร (`PKG-2026-10-05-full-*`) ทั้งหมดมี `raw` + `word_ids` + `region` ต่อ cell
- 08:20 — สร้าง `.agent/harness/uom_probe.py` (replay จาก cache ไม่มี VLM call) → 608บรรทัด:
  UOM มี 2 ผู้อ่านยืนยัน **202**, มี cell เดี่ยว **168**, **NOT_PRESENT 238**
- 08:22 — เปิด PDF จริงของ DMS-40/DMS-65: DMS-40 **ไม่มีคอลัมน์หน่วยนับบนเอกสาร** (หัวตาราง = NO./รหัสสินค้า/
  รายการ/จำนวน/หน่วยละ/ส่วนลด/จำนวนเงิน — "หน่วยละ" คือราคาต่อหน่วยไม่ใช่หน่วยนับ) ส่วน DMS-65 พิมพ์หน่วย
  ไว้ที่ **หัวคอลัมน์** ("จำนวนแผ่น Pcs.", "นน./แผ่น Kgs./Sheet") ไม่ใช่ในรายบรรทัด
  → สมมติฐานตั้งต้น "บังคับให้โมเดลคืนคอลัมน์ uom" ผิด และถ้าทำจริงคือการ**เติมข้อมูลที่ไม่ได้พิมพ์อยู่บนกระดาษ**
- 08:25 — สร้าง `.agent/harness/consensus_probe.py` จำลองการ compare ใหม่บน cache เดิม 1,621 items ที่
  baseline บอกว่ามีผู้อ่านเดียว: cell แถว = 433 "ใน box มีคำแต่ไม่ตรง", 397 "ค่าอยู่บนหน้าแต่ไม่อยู่ใน box",
  196 "ค่าอยู่ในแถว", **97 "รันของคำติดกันใน box ตรงเป๊ะ" (โค้ดปัจจุบันเทียบทั้ง box เลยไม่ผ่าน)**, 48 "ใน box ไม่มีคำ",
  17 "โตก box นิดเดียวก็ตรง"; ที่น่าตกใจ: **box โตขึ้น 0.008→0.05 ช่วยได้ 103→188 cell แต่จำนวนเอกสารที่ผ่านยังเท่าเดิม**
- 08:27 — เอานโยบาย V-01 จริง (`policy.yaml`: min confidence + require_agreement) มา replay ระดับเอกสาร:
  P0 วันนี้ **0/99**, P1 (+รันใน box/box โต) **1/99**, P2 (+containment) **3/99**, P3 (+ substring ของแถว) **5/99**,
  P4 (+ substring ทั้งหน้า ซึ่งไม่ใช่หลักฐานที่ยอมรับได้) **16/99**
- 08:29 — ราคาของการแก้ UOM ให้ "สมบูรณ์" (ใส่ flag `--assume-uom-solved`): P0 ยัง **0/99**, P2 **11/99**, P3 **13/99**
  → **UOM ไม่ใช่กำแพงที่ใหญ่สุด** และกำแพงที่เหลือคือ `customer_name` readers ขัดกัน **43 เอกสาร**
  (VLM ดึง caption ติดมาในค่า เช่น "ขายให้แก่ SOLD TO บริษัท..." ขณะที่ text layer ไทยเพี้ยน "บ ริ ษั ท อ า ป บ โก")
  กับตัวเลขที่ **ไม่อยู่ใน box ที่โมเดลเคลม** (page_substring 34–39 เอกสาร) และ cell ที่โมเดลไม่คืนมาเลย 12–16 เอกสาร
- 08:30 — ตรวจข้อจำกัดอื่นของ cache เดิม: `max_words = 2500` ต่อเอกสาร ทำให้หน้าท้ายๆ ของเอกสารหลายหน้า
  **ไม่มี word เก็บไว้เลย** (บางหน้า text layer 2,000+ ตัวอักษร แต่ words = 0) → มี cell ที่ต้องการ 84 cell
  ตกบนหน้าที่โดนตัด และ 42/99 เอกสารโดนตัดคำ
- 08:31 — พบข้อจำกัดของ control plane: `.agent/` อยู่ใน `.gitignore` (บรรทัด 212 ของ root) และ
  `git ls-files` คืน **0 ไฟล์** → baseline copy, todo, decisions, recovery ทั้งหมดมีอยู่เฉพาะบนดิสก์เครื่องนี้
  ไม่ได้ถูก version ไว้ (อธิบายว่าทำไม recovery.md พูดถึง "copy กลับ" ไม่ใช่ "git restore")
- 08:32 — สรุปเสนอ user: perception round ที่ควรซื้อคือ **ชุด 4 การแก้ใน cache reset ครั้งเดียว**
  (prompt: ห้ามเอา caption มาปนในค่า field / prompt: อ่านหน่วยนับจากหัวคอลัมน์พร้อม provenance +
  `NO_UOM_PRINTED` เมื่อไม่มีพิมพ์จริง / code: เทียบ "รันของคำใน box" + pad / code: cap words ต่อหน้า)
  ไม่ใช่ "บังคับ UOM" อย่างเดียว เพดานที่วัดได้คือ **V-01 ผ่าน ~11–13/99 ไม่ใช่ 99**
- 08:38 — user ถามว่า web portal ใช้งานได้หรือยัง → รันหลักฐานจริงครบ 3 ชั้น: pytest 31/31, server จริง +
  `check_live.py` **77/77**, แล้วชี้ UI logic harness ไปที่ fixture ที่ build จาก API จริงของ DMS-20 → **fail 3 รายการ**
- 08:44 — แยกสาเหตุได้ 2 กลุ่ม: (1) harness hardcode ค่าของเอกสารเดียว (`E01`,`26/2691`,`PCS`,`595×842`)
  ซึ่ง DMS-25/99 ย้าย field ไปหน้า 2 และ DMS-36 เป็น landscape → false failures 8 รายการ (2) ของจริง 1 ตัว:
  exception panel ของ E03 แสดง `49215.00` เทียบ `49215.00` ทั้งที่กฎ fail
- 08:47 — ของที่ต้องแก้ตัวจริง: ค่า `actual/expected` ของ overlay มาจาก `evidence[]` = *คู่ที่ตรงกัน* ส่วนผลต่าง
  อยู่ใน `rule_results[].data.diffs` (`sub_plus_vat_vs_grand = 3445.05`) → เพิ่ม `exceptions[].diffs`
  (non-zero เท่านั้น) ฝั่ง portal + panel "What differs" โดยไม่แตะ contract
- 08:50 — rewrite harness ให้ derive ความคาดหวังจาก payload (เลือกหน้าที่มี field+exception, dims จาก
  `pages[]`, label เทียบจากหัวค่าเพราะ label ตัดทอน by design) → ผ่านครบ **5/5 เอกสาร** (DMS-20/25/36/99/114)
- 08:51 — สรุป: pytest **32/32**, live **77/77**, UI **5/5** — portal ใช้งานได้ และ commit `d5ad5c3`
- 09:25 — ผู้ใช้ถามเรื่องการสั่ง sub-agent แยกกันตาม task และขอให้ปรับโครงสร้าง agent folder
- 09:28 — วิเคราะห์ปัญหา state overwrite, backlog pollution, guardrail conflict และความเสี่ยง git rollback จากการแชร์ flat .agent/
- 09:30 — สร้างระบบ Task Isolation ใน .agent/tasks/: แยก core-optimization และ web-test-portal พร้อม template
- 09:32 — แปลง .agent/state.json เป็น Multi-Task Registry และอัปเดต gent.md, 	ask.md, TASK_WEB_TEST_PORTAL.md
- 09:33 — บันทึก canonical records (CHG-20261006-004, TASK-20261006-004, session 2026-10-06-004)
