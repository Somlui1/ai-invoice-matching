# Current State

Last verified: `2026-10-03T14:25:00+07:00`

## Repository
- Branch: `main` (remote `origin/main`); ย้ายและรวมโค้ด Web Portal ทั้งหมด (frontend, backend, docs, examples, infra, scripts) จาก `invoice-web/` เข้าสู่โฟลเดอร์ `Web portal/` อย่างสมบูรณ์ โฟลเดอร์ `invoice-web/` ถูกลบออกแล้ว
- Existing OCR service (`OCR service/n8n`) และ original HTML mockup (`Web portal/AIVA-Web-Portal-Mockup-v4.4-Release.html`) ยังคงอยู่ตามเดิม
- Agent records ถูกจัดเก็บบน `agent/` ตาม canonical protocol

## Implemented Portal (`Web portal/`)
- `Web portal/frontend`: React + TypeScript + Vite + TanStack Query; UI ถูก normalize และ redesign ใหม่ทั้งหมดเพื่อให้อ่านง่ายและเห็นภาพรวม 3-Way Match ทันที.
- Normalized Queue View: KPI overview strip (ทั้งหมด/ผ่าน/รอตรวจ/ระงับ) แบบ interactive, single-bar unified filters (search, company, source, status, quick-tabs, chips), และ high-contrast table พร้อม context chips (ใบรับ, receiver, PO, amount tabular nums).
- Normalized Document Detail: Executive 3-Way Match Snapshot card (Vendor, PO/Release, Goods Receipt, Grand Total), Provenance bar, Executive Workflow Decision Hub, 3-Step Verification Pipeline Stepper, Discrepancy/Exception callout พร้อม direct PDF evidence link, และ 5 แท็บข้อมูล (สรุป, รายการสินค้า 3-way line match, กฎการตรวจพร้อม code/step, ประวัติตาม timeline, ข้อมูลเพิ่มเติมและ JSON).
- `Web portal/backend`: FastAPI modular monolith แยก `api/auth/core/domain/db/integrations/storage/workers`; app factory 49 บรรทัดประกอบ dependencies และ mount frontend.
- Mockup parity ครอบคลุม company chips, receipt/Receiver/ORG_ID, PO/release, rule STEP 1–3, ownership/access, 5 task-first detail tabs, global audit search/filter/pagination และ keyboard tab navigation.
- หน้า Access แสดง permission/capability จาก `/api/portal/v1/session` และแยก organizational dependencies ที่ยังไม่ได้เปิดใช้อย่างชัดเจน; ไม่มี mock role หรือ workflow action ที่ backend ไม่บังคับใช้.
- Persistent workflow แยกจาก immutable source snapshot: explain/resubmit/rerun/return/reject/hold/confirm มี reason policy, required note, expected revision/workflow version, idempotency และ audit.
- Resubmit/rerun สร้าง action outbox สำหรับ producer; accepted ยังรอ snapshot revision ใหม่ เมื่อ revision ใหม่มาถึง request ปิดเป็น completed และ workflow เปิดรอบตรวจใหม่.
- Source integrations submit JSON snapshots and PDF bytes. Portal does not run OCR/matching, approve invoices or send AP transactions.
- Canonical API contract is `Web portal/docs/04-receiving-api.md`; scope and implemented gaps are in `Web portal/docs/05-implementation-status.md`.
- Mockup UI-01–UI-15 parity และข้อจำกัดอยู่ใน `Web portal/docs/07-mockup-feature-parity.md`.
- Current file map, dependency direction และตำแหน่งเพิ่ม feature อยู่ใน `Web portal/docs/06-project-structure.md`.
- Legacy core Table9 converter preserves original standard/code and leaves unavailable receipts/matches empty.
- Persistent local data is in ignored `Web portal/data/`; dependency/build/test artifacts are ignored.
- Local preview runs at `http://127.0.0.1:8010`; API docs at `/api/docs`. One clearly labeled synthetic example with two JSON/PDF revisions was loaded for manual preview.

## Synthetic OCR Test Corpus (`OCR service/n8n/tests/test_invoices`)
- Corpus ถูกเชื่อมกัด pytest เป็น regression gate: `tests/test_invoice_corpus.py` replay ทั้ง 155 เคส มี pytest ที่ติด marker `live` ของ LiteLLM/Paperless เลืกงขัน offline (`python -m pytest` → `9 passed, 2 deselected in ~1.7s`) โดย `tests/conftest.py` กังไม่ให้ pytest เก็ป `test_suite.py` ที่เป็นสคริปที่ต้องยิง service จริง
- `invoice_engine.py` เป็น bridge ที่เรียก `app/core/rules.py` (Step 1–4) จริงแบบ offline โดยรับชุดแถว Oracle ที่เก็บไว้ในแต่ละ invoice (`oracle_rows`) ทำให้ expected_result ไม่มีวันหลุดจาก logic ของ production และรันซ้ำได้โดยไม่ต้องต่อ Oracle MCP.
- `build_test_dataset_wave2.py` สร้าง 100 เคสใหม่โดย expected_result ทุกตัวมาจาก engine; `verify_dataset.py` replay ทั้ง 155 เคสและ `--fix` ใช้ recalibrate key ได้; `check_pdfs.py` ตรวจว่า PDF ที่ render ตรงกับ key (ฟิลด์ที่มีต้องปรากฏ, ฟิลด์ที่หายไปต้องไม่ปรากฏ, จำนวนหน้าตรง `document_flags`).
- `generate_invoices.py` รองรับ 3 layout เดิมและเพิ่ม `pdf_hints`: watermark/ speckle จำลองเอกสาร scan, ต่อบัญชี 2 หน้า, เชิงอรรถหมายเหตุ, และพิมพ์ `—` สำหรับฟิลด์ที่ key ระบุว่าหาย.
- เคสสำคัญที่ควรทราบเมื่ออ่าน key: `halted_by` เป็น `V-02` เท่านั้นใน engine ปัจจุบัน; partial billing (E34) เกิดพร้อม E31 เสมอ; E16 บนเอกสารที่คำนวณถูกเกิดจาก float noise ของ `sub_total + vat`; `INV-J17` และ `INV-J20` เป็น forgery ที่ระบบตรวจไม่พบโดยเจตนา (ต้องได้ Auto-pass).
- ขอจำกัด: Tahoma subset ที่ฝังใน PDF ไม่มี ToUnicode map ที่ใช้ได้ ทำให้ดึงอักษรไทยเป็นข้อความได้เป็น mojibake (การ render ถูกต้อง) — เครื่องมือตรวจจึงเทียบเฉพาะ ASCII/ตัวเลข; corpus ใช้ dependencies `fpdf2` (render) และ `pypdf` (ตรวจ PDF) ซึ่งไม่ใช่ `requirements.txt` ของ service.

## n8n Workflow `aLUCmn3l0bZDjbVV` (Standard v6.6, on server)
- Workflow ชื่อ `AIVA PO-INV Matching Verification v6.6 (Explanatory Flow)` สถานะ `active: false`; 31 nodes = 23 flow nodes + 8 Sticky Notes, 24 edges, ผังการเดินงานเท่าเดิม (ไม่เพิ่ม/ลด node หรือ connection)
- ตรรกะของแต่ละ node ถูก port จาก Python แบบ 1:1: `normalize_extracted_document`→N4, `evaluate_step1`→N5, RCV-V01 base-table SQL + `parse_csv_receipts`→N7/N7.1, `evaluate_step2`→N8, `evaluate_step3`→N9, `evaluate_step4_decision`+`pipeline`→N10, `validate_output`→N11, `PortalClient`→N12, `PaperlessClient.update_verification_status`→N13/N13.1
- Circuit breaker สองชั้นผูกกับ boolean field: `N6: IF: Gate 1 Breaker (E02)` (true→N10 ข้าม Oracle) และ `N8.1: IF: Gate 2 Breaker (E05 E06)` (true→N10 ข้าม Line Matcher); `N2.2: IF: Unprocessed Document Found` กันงานซ้ำ
- Oracle REST ตรงเดียว: `((Invoice No. ทุก variation × SHIPMENT_NUM/PACKING_SLIP/WAYBILL_AIRBILL_NUM + Supplier Tax ID) OR (NOT EXISTS branch invoice) AND ph.SEGMENT1 IN (PO ทุกตัว))` — Tax ID ที่ว่างถูกเติมด้วย scalar subquery จาก PO แรก (inline Hop 1) พร้อม `RECEIVER` และ scalar `SUPPLIER_IS_INTERNAL`; ลำดับความสำคัญ Invoice→PO ตกอยู่ที่ N7.1 · ตรวจกับ Oracle จริง: `ED6909/0837` + PO `40083989` = 7 แถว (ก่อนแก้ได้ 8,359 แถว), fallback case `TLP-NOT-EXIST-9999` + PO `42052835` = 4 แถวตรงกับ log Python
- View เก่า `APPS.AH_DEV_RCV_PO_AP_MATCHING_V` ใช้กับ v6.6 ไม่ได้ (ไม่มี `RECEIVER`, `SHIPMENT_NUM`, `PACKING_SLIP`, `WAYBILL_AIRBILL_NUM`, `LINE_STATUS`, `QTY_BILLED`) — canvas จึงยิง base tables ตาม Python
- อ่านง่ายแบบ logic-first: Sticky Notes 8 ใบ (NOTE 1–6 + REF A exception map + REF B worked examples) และ 6 Node Groups ตาม STEP (`Manual Trigger` ต้องอยู่นอกกลุ่ม เพราะ n8n ห้าม trigger ใน group)
- เอกสาร: `OCR service/n8n/docs/workflows/n8n_flow_v6_6.md` (คำอธิบายตรรกะรายขั้น + ตัวอย่างจริง) และ `parity_spec_matrix.md` v2.0.0 (ตาราง 23 โหนด + data contract + ตารางเทียบรหัสเก่า E05–E35 → E01–E15)
- **Parity กับ Python engine ยืนยันแล้ว:** รัน canvas จริงด้วย `test_workflow` (execution `#324`, pin I/O ที่ `N2`/`N2.3a`/`N2.3b`/`N3`/`N7`/`N12`/`N13.1` ไม่แตะระบบจริง) ด้วย fixture `tests/fixtures/verified_scenario.json` → `decision` (`Hold`/`user`), `rules` 9 ข้อ, `exceptions` (`E09` High + `E15` Medium + `E03` High), `dms`, `access`, `receiver`, `invoice_summary`, `oracle_data.count` ตรงกับ Python ทุกข้อ · known deltas ที่จงใจคงไว้: รูปแบบตัวเลขในข้อความ `E15` (`10` vs `10.0`), canvas ส่ง `po_numbers`/`SUPPLIER_IS_INTERNAL`/`MATCHED` เผื่อไว้, `timestamp`
- `N11` normalize `rules[]` ให้ทุกแถวมี key `code`/`severity`/`details` (null เมื่อ PASS) ตรงกับ `model_dump()` ของ `RuleResult` เพื่อให้ body ที่ POST เข้า Portal เท่ากันจริง
- การทดสอบฝั่ง Python หลังงานนี้: `tests/run_tests.py --mode offline` = ALL PASSED (ไม่มีการแก้โค้ด Python) · tier `corpus` มี fail จาก `tests/test_corpus_v66.py` ซึ่งเป็นงานคู่ขนานของ `TASK-012` (3-Way Pipeline) ไม่ใช่ regression จากงานนี้
- ข้อจำกัดที่ค้าง: N7 ยังใส่ Bearer token ตรงๆ ใน header (`HARDCODED_CREDENTIALS`) — token หมดอายุ **2026-10-28T01:57:06Z** และ MCP ไม่มี tool สร้าง credential จึงต้องย้ายใน UI; `N12` ยังชี้ `https://httpbin.org/post` จึงไม่รัน `execute_workflow` เต็มจริงกับเอกสารจริง; `E11` ยังไม่ถูกยกทั้งสอง engine (รอนโยบาย Accounting)
- Data shape ของ n8n ต่างจาก Python และห้ามสลับกัน: ใช้ `invoice.po_number`, `lines[]`, `oracle_rcv_rows[]` (แถว active สำหรับ STEP 3), `oracle_rows_all` (ทุกแถว สำหรับ Table 9), `rules[]`, `exceptions[]` — **ไม่มี** `mergedFields` / `po_lines` / `oracle_data.rows`

## Repository Security & Git Boundary
- Global .gitignore ครอบคลุมข้อมูลความลับและเอกสารสำคัญของบริษัท 12 หมวดหมู่:
  1. Environment & Config: .env, .env.*, *.env (ยกเว้น !.env.example), *.secret*, secrets/, ault/
  2. Tokens & Credentials: credentials/, *credential*.json, *token*.json, 	oken.json, *service_account*.json, client_secret*.json, *api_key*, *apikey* (ยกเว้น package.json, package-lock.json)
  3. Private Keys & SSL/SSH: *.key, *.pem, *.pfx, *.p12, *.pkcs12, *.cer, *.crt, *.der, id_rsa*, id_ed25519*, id_ecdsa*, id_dsa*
  4. Oracle EBS & Databases: Oracle Wallet (cwallet.sso, ewallet.p12, *.wallet), Net config (*.ora, ojdbc.properties), Database files (*.db, *.sqlite*, data/, invoice-web/data/), Dumps/Backups (*.dmp, *.dump, *.bak, *.backup, *dump*.sql, *.sql.gz)
  5. Company Financials & Invoices: Real PDFs (*.pdf ทั่วทั้ง repo ยกเว้น synthetic fixture !invoice-web/examples/invoice.pdf), Excel (*.xlsx, *.xls, *.xlsm), CSV extracts (*export*.csv, *report*.csv, *receipt*.csv, *invoice*.csv, *entity*.csv, *oracle*.csv), Batch reports/payloads (*my_report*, *my_failed*, *batch_result*.json, paperless_downloads/, extracted_invoices/), Synthetic corpus จาก production extract (	ests/test_invoices/_raw/, pdfs/, 	est_dataset.json)
  6. Automation & n8n: .n8n/, 
8n-local/, *n8n_export*.json, *workflow_export*.json
  7. Python Environment: __pycache__/, *.py[cod], .venv/, env/, uild/, dist/, .pytest_cache/, coverage files
  8. Node & Frontend: 
ode_modules/, rontend/dist/, playwright-report/, 	est-results/, *.tsbuildinfo
  9. IDE, Agent & Scratch: .vscode/* (ยกเว้น !.vscode/extensions.json), .idea/, .agent/, .agents/, .pi/, .mcp.json, .gemini/, scratch/, /tmp/, 	mp/, 	emp/
  10. Archives: *.7z, *.zip, *.tar*, *.rar, *.gz, *.bz2
  11. Operating System: .DS_Store, Thumbs.db, desktop.ini, ehthumbs.db, $RECYCLE.BIN/
  12. Logs: *.log, logs/
- ตรวจสอบยืนยันด้วย git check-ignore -v ครอบคลุม 25+ pattern ตัวอย่างของ sensitive data ทุกหมวดหมู่ และยืนยันว่า Web portal/examples/invoice.pdf และ .env.example ไม่ถูก ignore

## Verified
- Web Portal Backend: 15 unittest tests passed in 6.303s ในตำแหน่งใหม่ `Web portal/backend` (persistence, idempotency, conflicts, revisions, schema validation, versioned PDF, global audit, workflow action/version/idempotency/outbox/revision completion, compatibility backfill, origin, keys, filters, adapter, architecture boundaries).
- OCR Service Regression: 9 passed, 6 deselected in 5.22s (`OCR service/n8n`).
- Frontend: TypeScript strict and Vite production build passed.
- Playwright: 6 tests passed on Edge browser (17.4s), covering import, PDF canvas viewer, tabs, history, filters, mobile viewport (390px) no-overflow, invalid JSON rejection, exact large decimal display, revision deep link/archived PDF, access/audit navigation, and review action persistent outbox.
- Browser subagent visual inspection: ตรวจ Queue page, Document detail overview, Line items table, Rules list, Revision history, Audit page, Action waiting state บน desktop และ mobile เรียบร้อย.
- Local preview on port 8010 serves latest production bundle successfully.
- Test corpus: `verify_dataset.py` replayed 155/155 invoices and reported 0 drift against `app.core.rules`; `check_pdfs.py` audited 155 PDFs / 157 pages with 0 mismatches; 3 rendered pages visually inspected (Thai glyphs, watermark, blank receiver-signature area, continuation page).
- Offline pytest suite: `9 passed, 2 deselected` ใน ~1.7 วินาที (corpus 7 tests + SSE UI 2 tests ที่ไม่เรียก service ภายนอก); ยืนยันความไวของ gate ด้วยการใส่ข้อมูลผิดตงใจ 4 แบบ แล้วเครื่องมือรายงาน error ครบ
- n8n workflow v6.6 (2026-10-03 บ่าย): re-export จากเซิร์ฟเวอร์แล้วตรวจด้วยสคริปต์ → 31 nodes / 24 edges / 0 dangling / ทุก flow node มี inbound edge / 0 broken `$()` ref; diff โค้ด 7 jsCode + N7 jsonBody เทียบ canonical copies พบต่างเฉพาะ comment (`node --check` ผ่าน);
  Oracle MCP ตรวจจริงด้วยบิล `ED6909/0837` → 7 แถว ข้าม 3 PO (`40083989`,`40089558`,`40118686`), GR `510522788`, receiver `Oracle, Concurrent`
- No live OCR, Oracle, LiteLLM, Paperless or AP tests executed.

## Existing System
- `OCR service/n8n/app` remains the existing Python OCR and matching service.
- `Web portal/AIVA-Web-Portal-Mockup-v4.4-Release.html` remains UI/data reference inside `Web portal/`.
- `Web portal/` contains the consolidated receiving and review portal (FastAPI backend + React frontend + workflow).
- `docs/` remains original architecture reference; code/docs have known contract and rules-version differences recorded in Web portal planning documents.

## Constraints / Next Work
- n8n workflow v6.6 ยัง `active: false` (ตามนโยบาย: ไม่เปิด schedule โดยไม่ได้สั่ง) และยังไม่เคยรัน end-to-end จริงกับ Paperless/LiteLLM/Portal — การยืนยัน ณ ขณะนี้เป็นแบบ static (topology + code diff) + Oracle query จริงหนึ่งคำสั่งด้วย base tables
- N7 ยัง hardcode Authorization header (ควรย้ายไป credential `httpTemplatedCustomAuth` ตามที่ n8n แนะนำ)
- Current release is local/integration pilot, not company-scoped production: shared API keys are workspace-wide; Entra, user/receiver RBAC and immutable user audit remain unimplemented.
- Workflow actions ใน shared-key pilot ไม่มีตัวตนรายบุคคล; ต้องเชื่อม Entra ก่อนบังคับ EU/ACC/APR และ separation of duties.
- SQLite startup table creation currently used; PostgreSQL/Alembic and production backup/storage/retention/scan/rate limits remain future work.
- `workers`, `migrations` และ `infra` เป็น boundary พร้อม README เท่านั้น ยังไม่มี Celery/Redis, Alembic runtime หรือ production deployment.
- PDF binary upload only; no live DMS URL connector/watermark. JSON/PDF เปิดย้อนหลังตาม revision ได้ แต่ retention/legal hold/cleanup ยังไม่ทำ.
- Need sanitized real producer contract to validate upstream mapping; never relabel legacy codes as a new standard.
- Producer ต้องเชื่อม action outbox และกำหนด SLA/retry/dead-letter ก่อนใช้ resubmit/rerun กับงานจริง; AP post ยังไม่เปิด.
- Keep logs free of secrets and invoice payloads; read Thai files explicitly with UTF-8.
