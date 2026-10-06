# Changelog

บันทึกผลเปลี่ยนแปลงถาวรที่มีผลต่อผู้ใช้ ระบบ หรือวิธีดูแล repository รายการใหม่ต้องเพิ่มด้านล่างเท่านั้น
## 2026-10-01

### Added — `CHG-20261001-001`

- เพิ่มโฟลเดอร์ `docs/` สำหรับเป็นศูนย์กลางเอกสารสถาปัตยกรรมและโครงสร้างระบบ
- เพิ่มเอกสาร `docs/README.md`, `docs/system-architecture.md`, `docs/matching-rules-standard-v6.2.md`, `docs/api-reference.md`, และ `docs/integrations.md`

## 2026-10-02

### Added — `CHG-20261002-001`
- Timestamp: `2026-10-02T08:48:00+07:00`
- เพิ่ม AIVA receiving portal ใน invoice-web: React/TypeScript frontend และ FastAPI snapshot API
- JSON import/ingest, validation, idempotency, revision protection/history และ persistent SQLite storage
- PDF attachment/viewer พร้อม fit-to-width, zoom, page navigation, evidence links และ stale warning
- เพิ่ม source filters/KPI/detail tabs, integration docs, core Table9 converter, synthetic examples และ automated tests
- ปรับขอบเขตตามผู้ใช้ให้รับข้อมูลจากระบบอื่น ไม่มีการประมวลผล OCR/AP ภายใน Portal

### Added — `CHG-20261002-002`
- Timestamp: `2026-10-02T09:03:26+07:00`
- เพิ่ม PDF archive แยกตาม document revision พร้อม backfill metadata ของฐานข้อมูล pilot เดิม
- เพิ่ม revision index และ historical detail/PDF APIs โดย endpoint เดิมยังเปิด current document ได้
- เพิ่ม revision selector, historical banner, revision list และ deep link ที่คงรุ่นหลัง reload
- ปรับเอกสาร Receiving API/implementation status และหน้าคู่มือเชื่อมต่อให้ตรงกับพฤติกรรมใหม่

### Changed — `CHG-20261002-003`
- Timestamp: `2026-10-02T09:21:29+07:00`
- จัด frontend ตาม feature boundaries: app, API contract/client, shared components, queue, documents/tabs, viewer, integration, styles และ test fixtures
- จัด backend เป็น modular monolith: API routes, auth policy, core config, document domain, database bootstrap/models, adapters และ PDF storage
- ลด `backend/app/main.py` เหลือ application composition 49 บรรทัด โดยรักษา endpoint และ compatibility imports เดิม
- เพิ่ม workers/migrations/infra boundaries พร้อมข้อจำกัด และเพิ่มเอกสาร project structure/dependency direction
- เพิ่ม architecture regression check เพื่อป้องกัน entrypoint กลับเป็นไฟล์รวมขนาดใหญ่

### Added — `CHG-20261002-004`
- Timestamp: `2026-10-02T09:40:01+07:00`
- เพิ่ม mockup read-only parity ให้ receiving portal: company chips, receipt/Receiver/ORG_ID, PO/release, STEP ของกฎ, ownership/access และ 6 detail tabs
- เพิ่ม persistent global audit API/page ที่ค้นหา กรอง แบ่งหน้า และเปิดเอกสารต้นทางได้
- เพิ่มหน้า Access แสดง permission/capability ที่ระบบรองรับจริง พร้อม dependency ของ Entra/RBAC/Oracle/workflow/DMS ที่ยังไม่เปิดใช้
- เพิ่ม keyboard navigation/ARIA สำหรับ tabs, responsive styles และเอกสารเทียบ UI-01–UI-15 กับ mockup v4.4

### Added — `CHG-20261002-005`
- Timestamp: `2026-10-02T10:10:57+07:00`
- เพิ่ม workflow actions จาก mockup: ชี้แจง แก้ไขแล้วส่งตรวจซ้ำ สั่งตรวจซ้ำ ส่งกลับ ปฏิเสธ พัก และยืนยัน
- แยก workflow state จากผลตรวจต้นทาง พร้อม reason policy, optimistic version, idempotency และ persistent history
- เพิ่ม action outbox/acknowledgement สำหรับ producer และปิดคำขออัตโนมัติเมื่อได้รับ revision ใหม่
- ปรับ UI เป็น task-first: queue แสดงงานที่ต้องทำ, detail แสดง next action ก่อนผลตรวจ/PDF และรวมข้อมูลเทคนิคในแท็บข้อมูลเพิ่มเติม
- เพิ่มคู่มือ Task-first UX และอัปเดต API/parity/status docs ให้ตรง implementation

### Changed — `CHG-20261002-006`
- Timestamp: `2026-10-02T10:42:00+07:00`
- ปรับปรุงและ normalize UI ทั้งหมดใน `invoice-web` (Queue, Detail, 3-Way Match Stepper, Line Items, Actions, Tabs) เพื่อให้อ่านง่าย สบายตา และเห็นภาพรวมข้อมูลชัดเจนที่สุด
- ปรับหน้า Queue: รวมแถบควบคุมตัวกรองเป็น Consolidated Single Control Bar (Search, Company, Source, Status dropdowns, quick status pills, company chips) และเพิ่ม 4 Interactive KPI Cards สำหรับกรองสถานะทันที
- ปรับหน้า Document Detail: เพิ่ม Executive 3-Way Match Snapshot Card (Company, PO/Release, Goods Receipt, Grand Total), Source Provenance Bar, 3-Step Verification Pipeline Stepper, Discrepancies Callout พร้อม direct PDF evidence jump, และ Streamlined Decision Hub
- จัดระเบียบ Detail Tabs 5 หมวดหมู่: สรุป 3-Way Match, ตารางเปรียบเทียบรายการสินค้า M1/M2 พร้อมตัวเลข tabular, 9 กฎการตรวจพร้อม STEP badge และรหัสข้อผิดพลาด, Activity Timeline, และข้อมูลแหล่งที่มาพร้อมสลับ Revision
- อัปเกรด Design System ใน `global.css`, `mockup-parity.css`, `revisions.css` (Typography, HSL color tokens, card elevation, responsive layout ป้องกัน horizontal overflow) โดยรักษา selector และ ARIA attributes ให้ผ่าน Playwright E2E 100%


### Added — `CHG-20261002-007`
- Timestamp: `2026-10-02T18:40:00+07:00`
- เพิ่ม wave 2 ของชุดทดสอบ PDF สังเคราะห์ใน `OCR service/n8n/tests/test_invoices/`: `INV-F01`–`INV-J20` รวม 100 ไฟล์ (valid/tolerated 20, single-rule fail 25, multi-rule fail 25, intercompany 10, edge cases 20) ทำให้ corpus รวมเป็น 155 PDF + answer key
- เพิ่ม `invoice_engine.py`: เรียก Standard v6.2 rules engine จริง (Step 1–4) แบบ offline ด้วยชุดแถว Oracle ที่เก็บต่อ invoice ทำให้ expected_result ทุกตัวตรงกับ logic ของ production และทำซ้ำได้โดยไม่พึ่ง Oracle MCP
- เพิ่ม `build_test_dataset_wave2.py` (สร้าง 100 เคส + expectation จาก engine + self-check ระดับหมวด), `verify_dataset.py` (replay/recalibrate key ทั้ง 155 เคส), `check_pdfs.py` (ตรวจ PDF ↔ key), และ `tests/test_invoices/README.md` อธิบาย workflow
- ครอบคลุม rule path ที่เคยไม่มีใน corpus: V-04 E17 (ไม่มีใบรับ), V-04 E35 (หลายใบรับ), V-04 MANUAL 50-row safety cap, V-05 E09 ระดับ Medium (ที่อยู่/รหัสไปรษณีย์), V-06 E26 ระดับ Medium (ผู้ส่งของ), V-07 E12 (UOM) และ E29 (price ในกรอบ), boundary 0.50/1.00/1% และ forgery ที่ตรวจไม่พบโดยเจตนา 2 เคส
- `generate_invoices.py` รองรับ `pdf_hints` (scan noise/watermark, ต่อบัญชี 2 หน้า, เชิงอรรถหมายเหตุ, พิมพ์ `—` แทนฟิลด์ที่หาย) และ truncate รายละเอียดตามความกว้างคอลัมน์
- Recalibrate `expected_result` ของ wave 1 จำนวน 30 รายการให้ตรงกับ engine (`halted_by` ที่เขียนเองถูกยกเลิก, partial billing A09–A11 เป็น Hold พร้อม E31+E34, B13/B14 เพิ่ม E31) และบันทึก `recalibrated: engine-v6.2` ไว้ใน record

### Added — `CHG-20261002-008`
- Timestamp: `2026-10-02T19:05:00+07:00`
- เพิ่ม `OCR service/n8n/tests/test_invoice_corpus.py` เป็น offline regression gate ของ synthetic invoice corpus (replay 155 เคสผ่าน `app.core.rules`, ตรวจ key/PDF, ตรวจ wave-2 invariants และ code/decision coverage) — รันด้วย `python -m pytest` ใช้เวลา ~2 วินาที ไม่ต้องพึ่ง Oracle/LiteLLM
- เพิ่ม `pytest.ini` (testpaths=tests, deselect marker `live`) และ `tests/conftest.py` (กัน pytest เก็บ `test_suite.py` ที่เป็นสคริปต์ async + เพิ่ม path ของ corpus tooling)
- ให้ `tests/test_frontend_sse.py` 2 เคสที่ต้องยิง Paperless/LiteLLM จริงติด marker `live` ทำให้ค่าเริ่มต้นของ pytest เป็นชุดที่รันแบบ deterministic
- `check_pdfs.py` และ `verify_dataset.py` ถูกแยกเป็น function ที่ import ได้ (`audit`, `verify`) พร้อม mutation test ยืนยันว่าเครื่องมือจับ error ได้จริง 4 รูปแบบ
- Fixed: การตรวจ "ฟิลด์ที่ต้องหายต้องไม่อยู่ใน PDF" เดิมไม่ทำงานเลยกับ wave 1 (ไม่มี `oracle_rows` จึงเทียบค่ากับ dict ว่าง) — ตอนนี้ resolve ค่าต้นทางจาก `_raw/oracle_receipts.csv` ตาม `oracle_source.receipt_num` แล้ว และแก้ `document_flags` ที่เป็น None ให้ปลอดภัย

### Changed — `CHG-20261002-009`
- Timestamp: `2026-10-02T20:20:00+07:00`
- อัปเดต n8n workflow `aLUCmn3l0bZDjbVV` ผ่าน MCP `aiva-n8n_update_workflow` เป็น **v6.5** และเปลี่ยนชื่อ workflow เป็น `AIVA PO-INV Matching Verification v6.5` (23 nodes เท่าเดิม ไม่แก้ connection, สถานะ `active: false`)
- `N9: Code: STEP 3`: แทน Ladder M1–M4 แบบ "แถวแรกชนะ" ด้วย **8-Pass Greedy Bipartite Matcher** ตาม `app/core/rules.py::evaluate_step3` (P1 price+qty, P2 price tolerance 1%/≤200 + qty, P3 line amount เมื่อ subtotal ตรง, P4 item number + closest price, P5 price only, P6 desc similarity, P7 line number, P8 แถวที่เหลือ/reuse `active_rows[0]`) — ห้ามใช้แถวใบรับซ้ำ, เทียบ UOM ทั้งค่าดิบและ cleansed
- `N7: Oracle MCP rcv_v01` + `N7.1: Parse Oracle Receipts`: Oracle 1 round-trip เดียวด้วย `((RCV_INV_NUM/AP_INV_NUM IN (…) AND supplier tax) OR PO_NUM)` แล้ว N7.1 (port ของ `parse_csv_receipts`) เป็นผู้คัดเลือกแถว Invoice ก่อนเสมอ ถ้าไม่มีจึงใช้แถว PO → รายงาน `oracle_query_mode` = `INVOICE`/`PO_FALLBACK`/`PO`/`NONE`; ไม่ใช้ `NOT EXISTS` เพราะทำให้ view scan ทั้งก้อน (baseline ~60s)
- Intercompany เปลี่ยนจาก list hardcode เป็น scalar subquery `(SELECT COUNT(*) FROM apps.financials_system_params_all fsi WHERE fsi.vat_registration_num = '<supplier tax>') as SUPPLIER_IS_INTERNAL` ที่ N8 อ่านเป็น `rcvRows.some(r => r.SUPPLIER_IS_INTERNAL === true)`
- `N8`/`N10`: เก็บ `oracle_rows_all` (ทุกแถวที่ Oracle คืน) ไว้คู่กับ `oracle_rcv_rows` (แถว active) เพื่อให้ `oracle_data.receipts` ใน Table 9 ตรงกับ `pipeline.py`; ค่า default `po_type` แก้เป็น `Purchase Order`; E28 bypass คืน `{queried:false, reason:'Bypassed due to E28 Line Math Error', count:0, receipts:[]}`
- `N2.4` + `HTTP Request`: ใช้ `SYSTEM_PROMPT`/`EXTRACTION_GUIDE` ชุดเดียวกับ `app/services/vision_extractor.py` (รวมกฎ "ใช้น้ำหนักเป็น qty สำหรับเหล็ก/วัตถุดิบ") สร้างด้วย `join('\n')` เพื่อหนีบั๊ก escape `\n`, OCR fallback prefix, จำกัด 4 หน้า (`max_pages=4`), `temperature: 0`
- `N12: HTTP: POST Portal`: ตั้ง `onError: continueRegularOutput` + `alwaysOutputData: true` + `options.timeout: 15000` ให้เท่าพฤติกรรม `PortalClient` ที่ไม่เคย throw; `N13` รายงาน `portal_dispatch.status` (`SENT`/`FAILED`/`ERROR`) และบล็อก `paperless_update` พร้อม `checked_tag_id: 12`
- ไม่แก้ `N5: Code: STEP 1 Rules` และ `N11: Code: Schema Validate` เพราะตรรกะตรงกับ `evaluate_step1`/`validate_output` อยู่แล้ว
- เอกสาร `OCR service/n8n/n8n flow structure.md` ปรับเป็น v6.5 (สรุปสิ่งที่เปลี่ยน, ผัง, ตาราง node, SQL ใหม่, โหมดค้นหา, กฎ V-07, ตาราง Python↔n8n Parity Map, ผล regression test 7 เคส)

### Changed — `CHG-20261002-010`
- Timestamp: `2026-10-02T20:35:00+07:00`
- เพิ่ม `.gitignore` ระดับ repository เป็นครั้งแรก: กันไฟล์ archive (`*.7z`), `tmp/`, สถานะของ agent/MCP ในเครื่อง (`.pi/`, `.mcp.json`), ผลรัน batch กับ paperless จริง (`my_report*.md`, `my_failed*.json`) และข้อมูล corpus ที่สังเคราะห์จาก Oracle extract จริง (`tests/test_invoices/_raw/`, `pdfs/`, `test_dataset.json`) ไม่ให้หลุดขึ้น remote
- `tests/test_invoice_corpus.py` เพิ่ม module-level skip เมื่อไม่มี `test_dataset.json` และ skip เฉพาะเคส PDF เมื่อไม่มีโฟลเดอร์ `pdfs/` ทำให้ clone ใหม่รัน `python -m pytest` แล้วไม่แดง (ผลจริง: `2 passed, 1 skipped, 2 deselected` เมื่อไม่มี dataset, `9 passed, 2 deselected` เมื่อมีครบ)

### Security / Changed — CHG-20261002-011
- Timestamp: 2026-10-02T20:54:00+07:00
- ยกระดับ .gitignore ระดับ repository ให้ครอบคลุมข้อมูลความลับขององค์กรทั้งหมด (Company Sensitive Data, Credentials, ERP/Oracle configs, Database files, Financial spreadsheets, Live PDFs, Logs และ Runtimes)
- เพิ่ม rules ครอบคลุม 12 หมวดหมู่:
  1. Environment & Secrets: .env, .env.*, *.env (whitelist !.env.example), *.secret*, secrets/, ault/
  2. Tokens & Credentials: credentials/, *credential*.json, *token*.json, 	oken.json, *service_account*.json, client_secret*.json, *api_key*, *apikey* (whitelist !package.json, !package-lock.json)
  3. Private Keys & SSL/SSH: *.key, *.pem, *.pfx, *.p12, *.pkcs12, *.cer, *.crt, *.der, id_rsa*, id_ed25519*, id_ecdsa*, id_dsa*
  4. Oracle EBS & Databases: Oracle Wallet (cwallet.sso, ewallet.p12, *.wallet), Net config (*.ora, ojdbc.properties), Database files (*.db, *.sqlite*, data/, invoice-web/data/), Dumps/Backups (*.dmp, *.dump, *.bak, *.backup, *dump*.sql, *.sql.gz)
  5. Company Financials & Invoices: Real PDFs (*.pdf ทั่วทั้ง repo ยกเว้น fixture !invoice-web/examples/invoice.pdf), Excel (*.xlsx, *.xls, *.xlsm, *.xlsb), CSV extracts (*export*.csv, *report*.csv, *receipt*.csv, *invoice*.csv, *entity*.csv, *oracle*.csv), Batch reports/payloads (*my_report*, *my_failed*, *batch_result*.json, paperless_downloads/, extracted_invoices/), Synthetic corpus จาก production extract (	ests/test_invoices/_raw/, pdfs/, 	est_dataset.json)
  6. Automation & n8n: .n8n/, 
8n-local/, *n8n_export*.json, *workflow_export*.json
  7. Python Environment: __pycache__/, *.py[cod], .venv/, env/, uild/, dist/, .pytest_cache/, coverage files
  8. Node & Frontend: 
ode_modules/, rontend/dist/, playwright-report/, 	est-results/, *.tsbuildinfo
  9. IDE, Agent & Scratch: .vscode/* (whitelist !.vscode/extensions.json), .idea/, .agent/, .agents/, .pi/, .mcp.json, .gemini/, scratch/, /tmp/, 	mp/, 	emp/
  10. Archives: *.7z, *.zip, *.tar*, *.rar, *.gz, *.bz2, *.xz
  11. Operating System: .DS_Store, Thumbs.db, desktop.ini, ehthumbs.db, $RECYCLE.BIN/
  12. Logs: *.log, logs/
- ตรวจยืนยันด้วย git check-ignore -v ครอบคลุม 25+ pattern ตัวอย่างของ sensitive data ทุกหมวดหมู่
- รัน regression tests: pytest 9/11 passed (2 deselected), unittest 15/15 passed

### Structure / Changed — CHG-20261003-001
- Timestamp: 2026-10-03T09:33:00+07:00
- ย้ายและรวมโค้ดและไฟล์ทั้งหมดของ Web Portal จาก invoice-web/ เข้าสู่โฟลเดอร์ Web portal/ ตามคำสั่งผู้ใช้:
  - invoice-web/frontend/ -> Web portal/frontend/
  - invoice-web/backend/ -> Web portal/backend/ (รวมทั้ง backend/app/domain/workflow/ Review Action State Machine)
  - invoice-web/docs/ -> Web portal/docs/
  - invoice-web/examples/ -> Web portal/examples/
  - invoice-web/infra/ -> Web portal/infra/
  - invoice-web/data/ -> Web portal/data/
  - invoice-web/.env.example -> Web portal/.env.example
  - invoice-web/.gitignore -> Web portal/.gitignore
  - invoice-web/README.md -> Web portal/README.md
  - invoice-web/run-local.ps1 -> Web portal/run-local.ps1
- ลบโฟลเดอร์ invoice-web/ ที่ว่างออกอย่างสมบูรณ์
- ปรับปรุง .gitignore ที่ระดับ root ให้ครอบคลุม Web portal/data/ และคง whitelist !Web portal/examples/invoice.pdf
- ปรับปรุงพาธใน Web portal/run-local.ps1, Web portal/README.md, Web portal/.env.example, และเอกสารใน Web portal/docs/
- ตรวจสอบความถูกต้อง: Backend unittest 15 รายการใน Web portal/backend ผ่าน 100% (6.303s), Regression pytest ใน OCR service/n8n ผ่าน 9 รายการ (5.22s)

### Documentation / Structure — CHG-20261003-002
- Timestamp: 2026-10-03T13:35:00+07:00
- Task: `TASK-20261003-002` (detail ใน `OCR service/n8n/.agent/CHANGELOG.md` → `CHG-20261003-004`)
- อัปเดต n8n workflow `aLUCmn3l0bZDjbVV` บนเซิร์ฟเวอร์ (ผ่าน MCP `aiva-n8n`) ให้เป็น Standard v6.6 แบบ Explanatory Flow:
  - rename workflow → `AIVA PO-INV Matching Verification v6.6 (Explanatory Flow)` (ยัง `active: false`)
  - rename `N7` → `N7: Oracle MCP: Hop 2 (RCV-V01)`, `N8` → `N8: Code: STEP 2 (Receipt & Customer)`, `N9` → `N9: Code: STEP 3 (8-Pass Line Matcher)`
  - rename IF nodes → `N6: IF: Gate 1 Breaker (E02)`, `N8.1: IF: Gate 2 Breaker (E05 E06)`, `N2.2: IF: Unprocessed Document Found` และปรับ condition ให้ผูกกับ boolean `has_e02` / `has_critical_receipt_issue`
  - เพิ่ม Sticky Notes 8 ใบ (NOTE 1–6 + REF A exception map + REF B worked examples) และจัด 6 Node Groups ตาม STEP โดย `Manual Trigger` อยู่ภายนอก (n8n ห้าม trigger ใน group)
- เพิ่มเอกสารใหม่ `OCR service/n8n/docs/workflows/n8n_flow_v6_6.md` (376 บรรทัด): ภาพรวม 6 ขั้น + mermaid, เหตุผลของ Gate 1/2, Two-Hop Multi-PO (พร้อมตารางเทียบ Python vs Canvas แบบตรงไปตรงมา), 8-Pass matcher + เหตุผลที่ใช้ `QUANTITY_RECEIVED`, Table 8 + Table 9 v1.5 (`dms`, `access`, `receiver`, `release_num`), ตารางเทียบรหัสเก่า E05–E35 → ใหม่ E01–E15, ผังโหนด/กลุ่ม/รายชื่อที่ห้าม rename, 4 สถานการณ์ตัวอย่าง, checklist 5 ข้อ
- เขียน `OCR service/n8n/docs/workflows/parity_spec_matrix.md` ใหม่จาก v1.0.0 (Standard v6.2 + snippet ที่ค้างยุค `has_e28`) → v2.0.0: หลักการ D1–D6, ตาราง 23 โหนด, Data Contract ราย edge, ตารางเทียบ E01–E15 ↔ รหัสเดิม + User Task Codes, checklist 6 ข้อ
- ผลตรวจยืนยันจริง: live export = 31 nodes (23 flow + 8 sticky) / 24 edges / 0 dangling / 0 broken `$()` ref; gate wiring ถูกต้อง; diff โค้ดโหนด = comment-only; `node --check` ผ่าน; Oracle EBS จริง `ED6909/0837` → 7 แถว / 3 POs (GR `510522788`, receiver `Oracle, Concurrent`)
- ข้อจำกัดคงค้าง: `N7` ยัง hardcode Authorization header (`HARDCODED_CREDENTIALS`), `E11` ยังไม่ถูกยกทั้งสอง engine, ยังไม่รัน end-to-end จริงที่ v6.6, workflow ยัง inactive

### Code / Canvas — CHG-20261003-003 (OCR service/n8n — n8n canvas)
- Timestamp: 2026-10-03T14:25:00+07:00
- Task: `TASK-20261003-005` (detail ใน `OCR service/n8n/.agent/CHANGELOG.md` → `CHG-20261003-005`)
- ปิดงาน "ทดสอบเทียบ canvas กับ Python engine จริง" โดยใช้ fixture `tests/fixtures/verified_scenario.json` เป็น input เดียวกันทั้งสองฝั่ง
- พบและแก้ข้อแตกต่างจริง 1 จุด: `N7` ประกอบ WHERE แบบ `(invoice branch) OR (ph.SEGMENT1 IN (...))` โดยไม่มี guard และไม่มี Hop 1 → PO `40083989` คืน **8,359 แถว** ทั้งที่แถวที่ถูกคือ 7 แถว; แก้เป็น inline Hop 1 (scalar subquery บน PO แรก เมื่อ Tax ID ว่าง) + `NOT EXISTS` guard รอบ branch PO = ตรรกะ "fallback เฉพาะเมื่อไม่เจอแถวจากเลขที่บิล" ของ Python
- เพิ่ม normalization ที่ `N11` ให้ `rules[]` ทุกแถวมี key `code`/`severity`/`details` (null เมื่อ PASS) ตรงกับ `model_dump()` ของ `RuleResult`
- ยืนยันด้วย `oracle_sql_run` (invoice branch 7 แถว / fallback 4 แถว), `cmp` ว่า SQL ที่ render บน canvas ตรงกับไฟล์ที่ validate, และรัน canvas จริงผ่าน `test_workflow` แบบ pin I/O → execution `#324` success ถึง `N14`
- ผลเทียบ Table 9: `decision`/`rules`/`exceptions`/`dms`/`access`/`receiver`/`invoice_summary`/`oracle_data.count` ตรงกันหมด เหลือ known deltas 3 ข้อ (รูปแบบตัวเลขในข้อความ `E15`, superset field ของ canvas, `timestamp`) — จงใจคงไว้
- ไม่แก้โค้ด Python; `tests/run_tests.py --mode offline` = ALL PASSED; workflow ยัง `active: false`

### Code / Tests — CHG-20261003-004 (OCR service/n8n — Standard v6.6 synthetic corpus)
- Timestamp: 2026-10-03T14:35:00+07:00
- Task: `TASK-20261003-006` (detail ใน `OCR service/n8n/.agent/CHANGELOG.md` → `CHG-20261003-006`)
- Audit แล้วพบว่า corpus v6.6 ที่รายงานว่า "เสร็จแล้ว" ยังไม่ผ่านจริง: `pytest tests/test_corpus_v66.py` = 14 failed / 199 passed, `run_tests.py --all` ไม่เคยเรียก suite นี้ และตัวเลข realism ที่รายงาน (multi-PO 36, splits, fuzzy) มาจากการ **สร้างเลขที่ใบรับปลอม** (`RCV-CONSOLIDATED-*`) ที่ไม่มีใน Oracle จึงรื้อทิ้งทั้งส่วน
- แก้ engine 1 จุด (real gap): `app/core/rules.py` เพิ่ม `gate_halt_reason()` → `decision.halted_by` ระบุตัว breaker ที่ Gate 2 (`V-04`) และ manual review (`V-05`) แทน `null` โดยไม่แก้ผลของกฎ; recalibrate answer key เก่า 155 ใบด้วย `verify_dataset.py --fix` (9 เคส เปลี่ยนเฉพาะ `halted_by`)
- เก็บ ground truth จริง: เพิ่ม multi-PO harvest ใน `extract_oracle_snapshot.py` (discovery SQL + fetch ด้วย projection rcv_v01 ของ production + parse ผ่าน `parse_csv_receipts()`) ได้ใบรับที่หลาย PO จริง 28 ใบ → snapshot v1.1 = 170 scenarios / 653 rows
- Builder: `_weave_realism_quotas()` กระจาย multi-PO 26 + lot split 16 slots แบบ deterministic พร้อม guard แบบ fail-fast (index เกินจำนวนแถวจริง → raise, ล็อก mutation ที่ calibrate กับมูลค่า, pool multi รับเฉพาะ FULLY RECEIVED) และวัด `meta.realism` จากเคสที่ build เสร็จแล้ว
- Renderer: `baht()` ไม่พิมพ์คำว่า `None` ในกล่องยอดรวมของบิลที่จงใจไม่มียอดรวม; บิลหลาย PO พิมพ์ PO ครบทุกเลข
- ผลตรวจจริง: dataset 100 cases Auto-pass 35 / Review 30 / Hold 30 / Reject 5 · **re-derived 100/100 expectations ผ่าน engine จริง** · realism วัดได้ (suppliers 20, multi-PO 34, two-hop 5, split 17, intercompany 4, fuzzy 99, weight 13) · `pytest tests/test_corpus_v66.py` = **215 passed** · `tests/run_tests.py --all` = **SUCCESS (ALL PASSED)** 4 tiers 30.99s
- เอกสาร: sync contract `halted_by` (`V-02|V-04|V-05|null`) ใน `docs/workflows/n8n_flow_v6_6.md` + `parity_spec_matrix.md` และบันทึก Known delta 4 — canvas ยังส่ง `null` ที่ `N8.1` ต้องใส่ `"V-04"`
- ข้อจำกัดคงค้าง: `E11`/`E13` ไม่ถูกยกใน engine จึงไม่อยู่ใน corpus; corpus เป็น offline answer-key layer ยังไม่ใช่วงจรวัด OCR accuracy; ยังไม่ commit เพราะ workspace มี WIP ของ TASK-012 ปนอยู่ (dataset/_raw/pdf เป็น gitignored build output)

### Structure / VCS — CHG-20261003-007 (repository layout — integrate `origin/main`)
- Timestamp: 2026-10-03T15:35:00+07:00
- Task: `TASK-20261003-007` · Merge commit: `2ce5b9e` (merge `origin/main` 6 commits เข้า `main`)
- โครงสร้าง `Web portal/` เปลี่ยนเป็น layout ของ `origin/main` ตามคำสั่งผู้ใช้ ("ไม่สนใจสถานะ portal ในเครื่อง ให้ merge ทับ"):
  - `Web portal/invoice-web-9054076/` (87 ไฟล์) — archive ของ portal React+FastAPI เดิม (เดิมอยู่ `invoice-web/`)
  - `Web portal/invoice-web1/` (106 ไฟล์) — portal ชุดงาน redesign ตาม Mockup v4.4 พร้อม `agent/` records ของตัวเอง = เวอร์ชันที่มี backend+frontend ครบและ test ผ่านล่าสุด
  - `Web portal/invoice-webV2/` (58 ไฟล์) — React app ชุดใหม่ที่ align กับ skill `aiva-invoice-core`
  - `Web portal/invoice-webv3/` (9 ไฟล์) — mockup no-build ที่ generate ข้อมูลจาก `OCR service/n8n/app/core/{master_data,rules}.py`
  - `Web portal/.agents/skills/aiva-invoice-core/` (3 ไฟล์) — domain reference ที่ถูก force-add ทั้งที่ root `.gitignore` ระบุ `.agents/`
- **ยกเลิก** การย้าย `invoice-web/` → `Web portal/` ที่ค้างอยู่ใน working tree (87 staged renames + 6 ไฟล์แก้ไข) เพื่อไม่ให้บดบังงาน mockup ของอีกฝั่ง; สำเนาก่อนทิ้งอยู่ที่ `C:\Users\wajeepradit.p\git\wip-backup-20261003\` และ snapshot commit `backup/wip-dirty-20261003`
- ผลถาวรต่อ contract/เอกสาร: path อ้างอิง canonical ย้ายเป็น `Web portal/invoice-web1/docs/04-receiving-api.md` (และ `05/06/07`) โดยสำเนาเก่าคงอยู่ใน `Web portal/invoice-web-9054076/docs/`; root `agent/` ยังเป็นบันทึกกลาง ส่วน `Web portal/invoice-web1/agent/` และ `Web portal/invoice-webV2/agent/` เป็นบันทึกแยกของอีกฝั่ง
- `.gitignore`: เปลี่ยน pattern ที่ผูกกับ path ที่ตายแล้วเป็นรูปแบบตาม version (`data/` + `Web portal/*/data/`, `!Web portal/*/examples/invoice.pdf`) และลบ `invoice-web/data/`, `!invoice-web/examples/invoice.pdf`, `Web\ portal/...` ที่ไม่จำเป็น; ยืนยันด้วย `git check-ignore -v` ว่า `examples/invoice.pdf` ทั้งสองสำเนาไม่ถูก ignore และทุกโฟลเดอร์ `data/` ยังถูก ignore
- ขอบเขตของรอบนี้: `OCR service/` ไม่ถูกแตะเลย — ยืนยันว่า `origin/main` ไม่มี diff ในโฟลเดอร์นี้ (0 ไฟล์) และ working tree ฝั่ง local คงเดิมทั้ง 15 แก้ไข + 26 untracked
- ผลตรวจ: OCR service `python -m pytest -q` = 235 passed / 9 deselected · portal backend (`invoice-web1`) 15 passed · mockup v3 smoke test ผ่าน 46 การตรวจ · conflict มีไฟล์เดียวคือ `agent/current-state.md` ซึ่ง merge ด้วยมือ
- ข้อจำกัดคงค้าง: ยังไม่คัดเลือกเวอร์ชัน canonical ของ portal (4 ชุดซ้อนกัน + เอกสารซ้ำทุกชุด); `Web portal/invoice-webv3/tools/build-domain-data.py --check` fail (`master_data.py shape changed`) ต้องแก้ generator แล้ว re-generate `assets/data.js`; `Web portal/data/` (sqlite runtime เก่า) ยังค้างบน disk แบบ untracked; branch ยังนำหน้า remote 3 commits (ยังไม่ push)

## 2026-10-04

### Fixed — `CHG-20261004-001` (OCR service/new engine — ทำให้ `bbox_testv3.py` รัน batch ได้จริง)
- Timestamp: 2026-10-04T15:22:00+07:00
- Task: `TASK-20261004-001` · Session: `2026-10-04-001` · Errors: `ERR-20261004-001`, `ERR-20261004-002`
- ไฟล์: `OCR service/new engine/tests/bbox_testv3.py` (72,786 → 36,995 bytes, 1,306 → 663 บรรทัด) — **ไม่แตะ logic OCR/coord/report แต่อย่างใด**
- ตัดเนื้อหาที่ถูกเขียนซ้ำเป็นสองสำเนาออก: บรรทัด 654–1306 ซ้ำกับ 1–653 แบบ byte-identical (`diff` สองซีก = 0 บรรทัด) ทำให้มี `if __name__ == "__main__": main()` **2 จุด** → หนึ่งการรันเคยยิง AI ซ้ำทั้งชุด ผลหลังแก้ `grep -c __main__` = 1
- `load_dotenv()` เพิ่ม fallback อ่านไฟล์ `env` ข้างสคริปต์ เมื่อไม่มี `.env` (ทำแบบเดียวกับ `bbox_test.py` ที่มี fallback นี้อยู่แล้ว) — โฟลเดอร์ `tests/` มีไฟล์ชื่อ `env` เท่านั้น เดิมจึง `SystemExit: ยังไม่ได้ตั้งค่า LITELLM_KEY` ทั้งที่ config ครบ; **จงใจไม่สร้าง `.env` ใหม่** เพื่อไม่เพิ่มสำเนา secret บน disk
- เพิ่ม `sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")` ที่ต้นโมดูล: console Windows เครื่องนี้เป็น cp874 ทำให้ `print()` บรรทัดแรกที่มี `·`/`✗`/`⚠` และภาษาไทย crash ด้วย `UnicodeEncodeError` ก่อนเริ่มงาน batch
- docstring: เปลี่ยนตัวอย่างคำสั่งจาก `bbox_batch.py` (ชื่อที่ไม่มีไฟล์จริง) เป็น `bbox_testv3.py` และเพิ่มตัวเลือก `--retry-errors` ที่มีอยู่ใน argparse จริง
- ผลตรวจ: `python -m py_compile` ผ่าน · โหลด env ครบทุกคีย์ (ตรวจเฉพาะชื่อคีย์ ไม่พิมพ์ค่า) · `python bbox_testv3.py --workers 2` เริ่ม batch จริง เห็นผลต่อหน้า (`doc 15/19/22/25/26/27` status `ok`, kept 18–50 กรอบ/หน้า, drop=0)

### Added — `CHG-20261004-002` (OCR service/new engine — report bbox แบบโต้ตอบ: ชี้/คลิกกรอบแล้วเห็นข้อมูล)
- Timestamp: 2026-10-04T16:56:00+07:00
- Task: `TASK-20261004-001` · Session: `2026-10-04-002` · ผู้ใช้Request: ให้ `out/doc_99/report.html` แสดงข้อมูลเมื่อชี้/คลิก bbox
- ปัญหาเดิม: ภาพใน report วาดกรอบด้วย PIL (เผาในไฟล์ภาพ) แต่ HTML เป็น ภาพ + ตารางแยกกัน → ตรวจว่ากรอบไหนคือแถวไหนต้องกะตาเอง
- เพิ่ม overlay layer บนภาพทุกภาพ (position: absolute คำนวณจาก `bbox_norm` เดิมที่มีอยู่ในผล OCR — ไม่เรียก AI ซ้ำ):
  - **ชี้เมาส์** ที่กรอบ (หรือแถวตาราง) → tooltip สีตามประเภท แสดง `type · label`, ข้อความเต็มของกรอบ, และพิกัด `px [...] · norm [...]` + ไฮไลต์คู่ของมันอีกฝั่ง (box ↔ แถวตาราง, สองทาง)
  - **คลิก** → ตรึงข้อมูลลง panel มุมขวาล่าง (คลิกซ้ำที่เดิมหรือกด `Esc` เพื่อปลด) และเลื่อนไปยังแถวตารางที่ตรงกัน
  - checkbox **กรอบโต้ตอบ** สำหรับซ่อน overlay ทั้งหมด (กลับมาคลิกที่ภาพเพื่อเปิดไฟล์ภาพเต็มเหมือนเดิม)
- ไฟล์ที่แก้: `OCR service/new engine/tests/bbox_test.py` (report ต่อฉบับ + เพิ่ม `--report-only` ให้สร้าง report จาก `page_*.json` เดิมโดยไม่ต้องเรียก AI/เน็ต และคงชื่อเดิมจาก `<h1>`) และ `OCR service/new engine/tests/bbox_testv3.py` (report รวมของ batch — `write_report` ส่ง `bbox_norm`/`bbox_px` เข้า DATA ด้วย)
- ผลข้างเคียงต่อ contract เล็กน้อย: `report.html` ของ batch มี field เพิ่มใน `DATA.pages[].kept` (`bbox_norm`, `bbox_px`) → ขนาดไฟล์โตขึ้น (~3.2 MB ที่ 87 ฉบับ → 99 ฉบับ) และต้องใช้ `--report-only` เพื่อ re-render report ของรอบเก่าที่ใช้ template เดิม
- ผลตรวจจริง (DOM-level ด้วย jsdom, harness: `C:\Users\wajeepradit.p\bbox-verify\test-interact.js`): `out/doc_99/report.html` ผ่าน **20/20** (32 กรอบ) และ `out/batch/report.html` ผ่าน **20/20** (overlay 15,111 กรอบ) — ครอบคลุม tooltip เปิด/ปิด, ข้อมูลเปลี่ยนตามกรอบ, sync สองทาง box↔แถว, ตรึง/ปลดด้วย Esc, และ toggle ซ่อนกรอบ

### Security/Housekeeping — `CHG-20261004-003` (gitignore: กัน secret `env` + ภาพ/ผล OCR เข้า repo)
- Timestamp: 2026-10-04T17:05:00+07:00
- Task: `TASK-20261004-001` · Session: `2026-10-04-002` · Trigger: ตรวจ `.gitignore` ก่อนมีใคร commit `new engine/`
- สิ่งที่พบ (ก่อนแก้): `git check-ignore` ตอบ **NOT ignored** กับ
  `OCR service/new engine/tests/env` (มี `LITELLM_KEY`, `PAPERLESS_API_TOKEN`) และกับทุกไฟล์ใต้ `out/`
  — pattern เดิมมีแต่ `.env`, `*.env`, `*.token` ซึ่งไม่ครอบไฟล์ชื่อ `env` (ไม่มีจุดนำหน้า) ส่วน `out/batch/` เก็บภาพที่เรนเดอร์จากเอกสารจริง + ผล OCR (ข้อมูลส่วนบุคคล/การเงิน) และ `report.html` 3.8 MB
  (`run_v3.log` ถูก ignore อยู่แล้วด้วย `*.log` บรรทัด 251)
- แก้: เพิ่มหมวด **13. Vision OCR Engine Test Artifacts & Local Config** ใน `.gitignore` (ท้ายไฟล์) 3 รายการ:
  `OCR service/new engine/tests/env`, `OCR service/new engine/tests/out/`, `OCR service/out/`
- ผลตรวจจริง: ทั้ง 3 path ขึ้น `IGNORED` และ `git status --untracked-files=all -- "OCR service/new engine"` เหลือ 42 ไฟล์ (เฉพาะ source/docs — ไม่มี env/out หลุดมา) · `git ls-files "OCR service/out"` = 0 และไม่มีไฟล์ `env`/`*.log` ถูก track มาก่อน จึงไม่ต้อง `git rm --cached`
- หมายเหตุ: ไม่มีการ commit/เพิ่มไฟล์ใด ๆ ในรอบนี้ (ผู้ใช้ยังไม่ได้สั่ง) และไม่ได้แตะการแก้ไขค้างเดิมใน `OCR service/n8n/`

### CHG-20261005-001 — System A Real-Data Integration, Batch Verification & Windows Compatibility
- วันที่: 2026-10-05T20:47:00+07:00
- ประเภท: feature, fix, verification
- ไฟล์ที่เปลี่ยน:
  - OCR service/system-a-sandbox/system-a/scripts/run_stats.py (fix stdout utf-8 encoding, replace ≥ with >=)
  - OCR service/system-a-sandbox/system-a/scripts/verify_run.py (fix stdout utf-8 encoding for Windows cp874)
  - OCR service/system-a-sandbox/system-a/FINDINGS.md (add extraction findings 3.7-3.8, open issues O-09-O-10, Numbers appendix)
  - OCR service/system-a-sandbox/system-a/runs/2026-10-05-full/ (sync delivery files: FINDINGS.md, iteration_log.md, sql_registry.md)
  - OCR service/system-a-sandbox/system-a/runs/LATEST (update to 2026-10-05-full)
- สรุป: ตรวจสอบและดำเนินงานต่อเนื่องจนสมบูรณ์ครบถ้วนตามข้อกำหนด AGENT_TASK §9 และ §10 โดยแก้ปัญหา encoding บน Windows console ทำให้ 
un_stats.py และ erify_run.py รันผ่านครบ 14/14 Acceptance Criteria

### `CHG-20261005-002` — Streamline System A to Core Engine and add process_pdf.py
- วันที่: `2026-10-05T21:12:00+07:00`
- ประเภท: refactor, feature, documentation
- ไฟล์ที่เปลี่ยน:
  - สร้าง `OCR service/system-a-sandbox/system-a/process_pdf.py` (Standalone PDF -> Result 3.0 runner)
  - ปรับปรุง `OCR service/system-a-sandbox/system-a/README.md` (Quick start, architecture & usage)
  - ย้ายไปยัง `OCR service/system-a-sandbox/system-a/archive/`: `tests/`, `sandbox_data/`, `runs/`, `reports/`, `docker/`, `scripts/`, `src/system_a/sandbox/`, `FINDINGS.md`
- สรุป: จัดระเบียบโปรเจกต์แยกส่วนประกอบทดสอบและ artifacts เดิมเข้า `archive/` ทำให้โครงสร้างหลักเหลือเฉพาะ Core Engine และมีสคริปต์ `process_pdf.py` ที่ใช้งานง่ายเพียงคำสั่งเดียว

### `CHG-20261005-003` — Evaluation Loop Iteration 1: measurement harness + buyer registry, UOM groups, JSON decode recovery
- วันที่: `2026-10-05T23:20:00+07:00`
- ประเภท: fix, config, tooling, verification
- ไฟล์ที่เปลี่ยน:
  - สร้าง `OCR service/system-a-sandbox/.agent/harness/`: `replay.py`, `step1_scan.py`, `fleet_report.py`, `uom_diff.py`, `v05_predict.py`, `oracle_probe.py`, `vlm_probe.py`, `test_salvage.py`, `wait_and_run.sh`
  - เขียนใหม่ `OCR service/system-a-sandbox/system-a/config/standards/v6.6/buyer_entity.yaml` (ตารางที่ 4 ครบ 28 แถวตามมาตรฐาน + แถว bridge ฝั่ง operating-unit id พร้อม audit field)
  - เขียนใหม่ `OCR service/system-a-sandbox/system-a/config/standards/v6.6/uom_groups.yaml` (กลุ่มคำพ้อง SET/BOX/PACK/ROLL/LOT/MTR/FRAME/CAN/DRUM + ตัว, อัน, EA, EACH)
  - แก้ `OCR service/system-a-sandbox/system-a/src/system_a/adapters/llm/litellm_client.py` (ปิด reasoning เมื่อ decode ไม่สำเร็จ + salvage JSON ที่ถูกตัด + counter ใหม่)
  - แก้ `OCR service/system-a-sandbox/system-a/src/system_a/perception/vision_pipeline.py` (ติดธงหน้าที่กู้ข้อมูลแบบ salvage ว่ายังไม่ครบ)
  - ปรับ `OCR service/system-a-sandbox/.agent/{state.json,progress.md,todo.md,decisions.md,recovery.md}`
- สรุป: ตั้ง baseline จริงของ 99 ใบแจ้งหนี้ (`full_r0`, AUTO_PASS 0) และพิสูจน์ว่าคอขวดคือ V-01/E01 ไม่ใช่
  backlog ตั้งต้น; วินิจฉัยพบสาเหตุจริง 3 เรื่อง (ไม่มี cell หน่วยนับ 238 บรรทัด, reader เดียวบน header,
  JSONคำตอบ vision โดน reasoning กินโควตา) และแก้ตารางอ้างอิงลูกค้าที่ V-05 ไม่เคยผ่านเลยเพราะ ORG_ID
  คนละชุดกับ SQL — ผลวัด: V-05 `manual_review` 53 -> 0, E10 70 -> 68 โดยไม่มี E10 ใหม่, ไม่มี regression
- โน้มเทียบ: ห้ามตีความว่าความแม่นยำรวมขึ้น — AUTO_PASS ยัง 0 จนกว่าจะแก้ perception layer (E01)

### `CHG-20261005-004` — Web Testing Portal (System A) — Phase 1–5 ครบ, core ไม่ถูกแตะ

- วันที่: `2026-10-05T23:55:00+07:00`
- ประเภท: tooling (เพิ่ม portal สำหรับทดสอบ/ดีบัก System A), test
- ไฟล์ที่เปลี่ยน (commit `2d87f6e`, 20 ไฟล์ +3,673 บรรทัด — **ไม่มี `src/system_a/**` และ `config/**` เลย**):
  - เพิ่ม `system-a/web/{engine.py,catalog.py,app.py,serve.py,run_portal.bat,README.md}`
  - เพิ่ม `system-a/web/static/{index.html,styles.css,js/{api,viewer,bbox-overlay,interaction,panels,app}.js}`
  - เพิ่ม `system-a/web/static/vendor/pdfjs/` (pdfjs-dist 4.10.38, Apache-2.0, same-origin)
  - เพิ่ม `system-a/web/test_portal.py` (24 test) และ `system-a/web/test_ui_logic.mjs` (25 checks)
  - เพิ่ม `.gitignore` หมวด 7 กันผลรันของ portal (`system-a/web/results/`, `system-a/.cache/`)
- พฤติกรรมที่เพิ่ม:
  - เลือก/ค้นหาเอกสารจาก Paperless (99 ฉบับ, แบ่งหน้า, badge แสดง verdict ที่มีอยู่บน disk)
  - รัน verification ผ่าน portal แล้วเห็น step จริงของ CLI + stdout แบบ streaming (SSE), cancel ได้,
    กันรันซ้ำเอกสารเดิม (409) และจำกัดจำนวนรันพร้อมกัน (`WEB_MAX_CONCURRENT` default 2)
  - แสดงภาพหน้า PDF พร้อมกรอบ bbox จาก `element_id` ของ contract, toggle ได้ 5 layer,
    และ cross-highlight สองทาง (คลิกค่า → ไปกรอบ / คลิกกรอบ → ไปแถว) ผูกกันด้วย `element_id` เท่านั้น
  - upload PDF ที่ไม่มีใน Paperless เพื่อทดสอบได้ (`--pdf-file`)
- ผลทดสอบ: pytest 24/24 (offline ทั้งหมด, faked subprocess) · UI logic 25/25 ·
  **เทียบ CLI จริงบน DMS-20 sandbox: `integrity.payload_sha256` ตรงกันทุกตัวอักษร** (portal 1.0s = CLI 1.0s)
- โน้มเทียบ: portal เป็น *consumer* ของ `process_pdf.py` เท่านั้น ไม่ได้เพิ่ม/เปลี่ยนตรรกะการตัดสินใจใด ๆ

### `CHG-20261005-005` — Portal:ติดป้ายระดับให้บรรทัดใน engine log และลบสี ANSI ของ CLI

- วันที่: `2026-10-05T23:59:00+07:00`
- ประเภท: tooling (portal), test
- ไฟล์ที่เปลี่ยน (commit `fec7451`): `system-a/web/engine.py`, `static/js/app.js`, `static/styles.css`,
  `test_portal.py`, `README.md` — ไม่แตะ `src/system_a/**` และ `config/**`
- พฤติกรรมที่เปลี่ยน: stderr ของ engine รวมเข้ากับ stdout ทำให้ข้อความของ library ไหลมาในช่อง log
  เดียวกับ step — ข้อความ `warning: The fitz API is deprecated ...` ของ PyMuPDF จึงดูเหมือนความล้มเหลว
  ทั้งที่รันจบใน 0.9 s; และ `process_pdf.py` พิมพ์ ANSI colour แบบไม่ condition อ่านผ่าน pipe จึงเป็น
  อักขระแปลก ๆ
  - `strip_ansi()` ตัดสีออกทุกบรรทัดที่ดักได้
  - `classify()` ติดป้าย `info`/`warn`/`error` + แนบคำอธิบายของข้อความที่ไม่ใช่ความผิด
    (จงใจให้ pattern แคบ: "--- Exceptions / Findings ---" และป้าย `[ SYSTEM_ERROR ]` ซึ่งเป็น output
    ปกติต้องเป็น info; ของจริงคือ `[ERROR]` หรือ traceback)
  - UI แสดง warn สีเหลือง / error สีแดง และมี tooltip อธิบาย — ไม่มีการซ่อนข้อความใด ๆ
- ผลทดสอบ: pytest 26/26 (เพิ่ม 2) · รันจริง `/api/verify/20` sandbox: 39 events, บรรทัด fitz เป็น
  `level=warn` + hint, error 0 บรรทัด, ไม่มี escape คงเหลือ, exit 0

## 2026-10-06

### Fixed — `CHG-20261006-001` — Portal: เส้นทางการ upload ไม่ถูก route อื่นกลืน, error จาก Paperless อ่านออก, และตัวตรวจ live ที่ไม่เคยผ่าน

- Timestamp: `2026-10-06T08:25:00+07:00`
- Task: `TASK-20261006-001` · Session: `2026-10-06-001` · Commit: `5a058e0`
- ประเภท: bug fix (portal), tooling, test — **ไม่แตะ `src/system_a/**` และ `config/**`** (ตรวจด้วย `git diff --cached --name-only`)
- ไฟล์ที่เปลี่ยน (ทั้งหมดอยู่ใต้ `system-a/web/`): `app.py`, `static/js/api.js`, `static/js/viewer.js`,
  `test_portal.py`, `test_ui_logic.mjs`, `README.md` และ `check_live.py` (ถูก **commit ครั้งแรก** — ไฟล์นี้
  ถูกเขียนไว้รอบก่อนแต่ไม่เคยถูก `git add` จึงหายไปถ้า clone ใหม่)
- สิ่งที่แก้:
  1. **route shadowing**: `POST /api/verify/{doc_id}` ถูก register ก่อน `POST /api/verify/upload` และ
     Starlette ตอบ route แรกที่ pattern ตรงกัน คำว่า `upload` จึงถูกแปลงเป็น `doc_id` → อัปโหลด PDF สำเร็จ
     แต่กด Verify แล้วได้ 422 int-parse โดย endpoint อื่นปกติทั้งหมด ย้าย literal route ขึ้นก่อน +
     regression test (`test_uploaded_pdf_can_be_verified`)
  2. **error จาก Paperless-ngx**: เดิมทุกความผิดพลาดของ DMS กลายเป็น 502 "cannot fetch" เหมือนกันหมด
     ทำให้เอกสารที่ถูกลบไปแล้วยังหน้าจอเหมือน portal พัง → `_upstream_error()` ตอบ `404` (id เก่า/ถูกลบ),
     `502` (token ถูกปฏิเสธ — pattern `PAPERLESS_AUTH` จาก reader จริง), `503` (ไม่ได้ตั้งค่า DMS),
     `502` (transport) พร้อมประโยคอธิบาย 1 ประโยคต่อกรณี; `api.js` แสดง `detail` ของ FastAPI แทน JSON
     envelope; viewer ที่ภาพไม่ออกจะถาม endpoint อีกครั้งเพื่อดูสาเหตุ (และแยกกรณี "endpoint ให้ภาพได้
     แต่ browser ไม่วาด") — ไม่มีข้อความใดถูกซ่อน
  3. **`web/check_live.py` ไม่มีทางผ่านมาก่อน**: NameError (`Path` ไม่ถูก import) ทำให้จบตั้งแต่ตรวจ health,
     `json.loads(body)` 12 จุดตายทันทีที่ body ไม่ใช่ JSON (portal กำลัง restart / proxy ตอบ HTML),
     และเงื่อนไขของ "uploaded PDF verifies end to end" กรอง SSE ด้วย key ที่ไม่มีอยู่ (`"done" in e`)
     → แก้เป็น `e.get("type") == "done"`, เพิ่ม `jload()` + ABORT ที่อ่านได้เมื่อ catalog ว่าง
- ผลตรวจจริง: pytest **31/31** · browser modules (stub DOM) **27/27** · **live checker 77/77** บน portal ที่รันอยู่
  รวม `uploaded PDF verifies end to end` (HTTP 200 + `done` event, perception cache hit) และ
  `a stale document id explains itself` → `404 {"detail":"DMS-999999 is not in Paperless-ngx"}`
  · pytest ใหม่ 1 ตัวรัน checker ชน port ที่ปิด → ได้ FAIL lines ไม่มี traceback
- ข้อจำกัดคงเดิม: ยังไม่มีการคลิกทดสอบโดยคนจริงบน browser (harness ครอบคลุม logic/DOM ไม่ใช่การจัดวาง CSS)
