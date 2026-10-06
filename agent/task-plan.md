# Task และ Plan

Last updated: 2026-10-05T21:05:00+07:00

## Active Task
- Task ID: TASK-20261005-002
- Title: จัดระเบียบ System A ย้ายไฟล์ทดสอบ/artifacts ไปยัง archive/ และสร้าง process_pdf.py ให้เหลือเฉพาะ Core Engine รับ PDF -> Final Result
- Status: **completed** (2026-10-05T21:12:00+07:00)
- Goal: แยกไฟล์ที่ไม่ใช่ Core ทั้งหมด (tests, sandbox_data, runs, reports, doc tools) ไปไว้ใน rchive/ และจัดเตรียมสคริปต์ process_pdf.py ที่อ่านไฟล์ PDF เดี่ยว แล้วประมวลผลจนได้ผลลัพธ์ iva.system_a.result/3.0 โดยตรง เพื่อลดความซับซ้อนและให้ใช้งานได้ง่าย

## Plan
- [x] สำรวจและจัดเตรียมโฟลเดอร์ rchive/
- [x] ย้าย 	ests/, sandbox_data/, 
uns/, docker/, scripts/ (เครื่องมือทดสอบ/ทำรายงาน) และ FINDINGS.md ไปไว้ใน rchive/
- [x] สร้างสคริปต์ Core process_pdf.py สำหรับรับไฟล์ PDF (เช่น python process_pdf.py invoice.pdf) แล้วคืนผล iva.system_a.result/3.0
- [x] ทดสอบรัน process_pdf.py กับตัวอย่าง PDF จริง ยืนยันว่าแปลงออกมาเป็น Final Result สำเร็จ
- [x] ปรับปรุง README.md ให้เรียบง่าย อธิบายเฉพาะวิธีใช้งาน Core Engine รับ PDF -> Result
- [x] บันทึก Canonical Records ใน gent/ ครบตาม AGENTS.md

## Acceptance criteria
- [x] โฟลเดอร์ system-a/ สะอาด มีเฉพาะ Core code (src/system_a/, config/, schemas/, process_pdf.py, .env)
- [x] ไฟล์ทดสอบและผลรันถูกเก็บรักษาไว้อย่างปลอดภัยใน rchive/ ไม่สูญหาย
- [x] สคริปต์ process_pdf.py สามารถรันรับ PDF แล้วพิมพ์/บันทึกผลลัพธ์ 
esult-3.0 ออกมาได้จริง
- [x] มีเอกสารสรุปการใช้งานที่เข้าใจง่าย ไม่สับสน

## Completed Tasks
### TASK-20261005-001 (Completed)
- Last updated: 2026-10-05T20:47:00+07:00

## Active Task
- Task ID: TASK-20261005-001
- Title: เชื่อม System A เข้ากับข้อมูลจริง (Paperless + Oracle EBS + LiteLLM Qwen), รัน batch 99 เอกสาร, สร้าง HTML Report พร้อม PDF.js/BBox และผ่าน 14/14 Acceptance Criteria
- Status: **completed** (2026-10-05T20:47:00+07:00)
- Goal: ตรวจสอบงานที่ดำเนินการไปแล้ว (Phase 0-6), แก้ไขข้อติดขัด (Windows cp874 stdout encoding), อัปเดต FINDINGS.md ครบถ้วน, รัน verify_run.py ผ่าน 14/14 AC และส่งมอบตาม AGENT_TASK §10

## Plan
- [x] ตรวจสอบสถานะการทำงานเดิม (Iteration 1-4 ใน 
uns/iteration_log.md, 99 เอกสารใน 
uns/2026-10-05-full/, รายงานใน 
eports/2026-10-05-full/)
- [x] แก้ไข Windows console encoding (cp874) ใน scripts/run_stats.py และ scripts/verify_run.py เพื่อป้องกัน UnicodeEncodeError
- [x] รัน 
un_stats.py และนำตัวเลขสถิติจริงเติมลงใน Numbers appendix ของ FINDINGS.md
- [x] นำข้อค้นพบ DIAGNOSE จาก Iteration 4 (การตัดหน้าเกิน 12 หน้า และ 21 เอกสารที่ pages_complete = false) บันทึกลงใน FINDINGS.md (ข้อ 3.7, 3.8 และ Open issues O-09, O-10)
- [x] คัดลอกเอกสารส่งมอบ (FINDINGS.md, iteration_log.md, sql_registry.md) เข้า 
uns/2026-10-05-full/ และอัปเดต 
uns/LATEST
- [x] รัน erify_run.py --run-id 2026-10-05-full ยืนยันผล AC-01 ถึง AC-14 ผ่านครบ 100% (14/14)
- [x] บันทึก Canonical Records ใน gent/ ครบตาม AGENTS.md

## Acceptance criteria (AC-01 .. AC-14)
- [x] AC-01: pytest -q ผ่าน 232/232 tests (2.03s)
- [x] AC-02: เอกสาร inventory 99 ฉบับ ตรงกับ index 99 ฉบับ และ evidence 99 ไฟล์ (ครบ 100%)
- [x] AC-03: ทุกเอกสารจบด้วยสถานะ COMPLETED 99/99
- [x] AC-04: ผล COMPLETED ผ่าน schema 3.0 ทั้ง 99 ไฟล์ ไม่มี forbidden keys
- [x] AC-05: SQL query (RCV-V01, PO-SUPPLIER, RCV-V02) รันผ่าน Oracle EBS จริง 12/12 probes, มี receipt line 63 docs
- [x] AC-06: Oracle calls ต่อฉบับ <= 3, ไม่มี DML query
- [x] AC-07: Error code isolation (Oracle technical error ไม่เป็น E05) ผ่าน
- [x] AC-08: Evidence 520 รายการมี bbox/bbox_missing_reason ครบ, bboxes 232,533 กล่องอยู่ใน [0,1]
- [x] AC-09: Bbox ครบทุกระดับ (page, field, row, cell, signature), word bbox 99/99 (100.0% >= 90%)
- [x] AC-10: รายงานเปิดได้แบบ offline, PDF.js เรนเดอร์ได้, deep link #doc=<id> ทำงาน, zoom 50%/100%/200% ตรง 0 px mismatch
- [x] AC-11: Highlight bbox ตรงตาม element_id ของ evidence (2/2 headless tests pass)
- [x] AC-12: ตรวจไม่พบ secret / credentials ใน code, logs, reports
- [x] AC-13: DMS เป็น read-only (GET only) และไม่ยิง AIVA Portal
- [x] AC-14: FINDINGS.md และ iteration_log.md ครบถ้วนตามมาตรฐาน

## Result
- ตรวจสอบและปิดงาน System A Real-Data Integration ครบ 100% ตามข้อกำหนด §9 และ §10
- เอกสาร 99 ฉบับจบด้วย COMPLETED (MANUAL_REVIEW 71, REVIEW 14, HOLD 13, SYSTEM_ERROR 1)
- Report พร้อมใช้งานที่ 
eports/2026-10-05-full/index.html (พร้อม serve.sh / serve.bat)



- Task ID: TASK-20261003-007
- Title: Integrate `origin/main` (portal restructure) เข้ากับ `main` โดยไม่แตะ `OCR service/`
- Status: completed
- Goal: ทำให้ repo กลับเป็นเส้นเดียวที่ push ได้ โดยยอมรับ layout ของ `origin/main` ทั้งพื้นที่ `Web portal/` (ผู้ใช้สั่งชัดเจนว่าสถานะ portal ในเครื่องไม่สำคัญ ให้ merge ทับ) แต่ต้องมีหลักฐานยืนยันว่างาน `OCR service/n8n` ฝั่ง local (15 แก้ไข + 26 untracked + v6.6 corpus) ไม่หายและไม่ถูกแตะ

## Plan (TASK-20261003-007)
- [x] backup full workflow JSON + แยกโหนดเก็บก่อนแก้ (ไว้ restore)
- [x] diff โค้ดโหนดบน canvas กับ canonical copies → ยืนยันว่า logic ตรงกัน แล้ว resync
- [x] ตั้ง workflow name/description ใหม่ + ปรับ IF gate condition ให้ใช้ boolean field `has_e02` / `has_critical_receipt_issue`
- [x] rename โหนดที่ไม่ถูก `$()` อ้างถึง + rename IF nodes ให้ชื่อตรงหน้าที่ Gate
- [x] เพิ่ม Sticky Notes 8 ใบ และจัด 6 Node Groups ตาม STEP (`Manual Trigger` ต้องอยู่นอกกลุ่ม)
- [x] ตรวจ canvas จาก live export: edges / dangling / `$()` refs / gate wiring
- [x] สร้าง `docs/workflows/n8n_flow_v6_6.md` (logic-first) และเขียน `parity_spec_matrix.md` เป็น v2.0.0
- [x] อัปเดต canonical records ทั้ง `agent/` และ `OCR service/n8n/.agent/`

## Acceptance criteria (TASK-20261003-007)
- Workflow ชื่อ `AIVA PO-INV Matching Verification v6.6 (Explanatory Flow)` และยัง `active: false`
- ไม่มี edge ค้าง, ไม่มี `$()` ที่พัง, Gate ทั้งสองยังชี้ `true → N10`
- เอกสาร 2 ฉบับอยู่ระดับ v6.6 และมีตารางเทียบรหัส exception เก่า (E05–E35) → ใหม่ (E01–E15)
- ผลยืนยันต้องมาจาก live canvas export และ Oracle EBS จริง (ไม่ใช่การคาดเดา)
- บันทึก canonical records ครบตามระเบียบ AGENTS.md

## Result (TASK-20261003-007)
- Canvas: 31 nodes (23 flow + 8 Sticky Notes), 24 edges, 0 dangling, ทุก flow node มี inbound edge, 0 broken `$()` ref; ตั้ง 6 Node Groups สำเร็จ (คำเตือน `TOP_LEVEL_ITEMS_OVER_CEILING` หมดไป)
- Gate wiring ถูกต้อง: `N6 true→N10 / false→N7` · `N8.1 true→N10 / false→N9` · `N2.2 true→N2.3a / false→Main`
- โค้ดโหนดบน canvas กับ canonical copies ตรงกัน (diff = comment only), `node --check` ผ่านครบ
- Oracle EBS จริง: บิล `ED6909/0837` → 7 แถว / 3 POs (`40083989`,`40089558`,`40118686`), GR `510522788`, receiver `Oracle, Concurrent`; ยืนยันว่า view เก่า `AH_DEV_RCV_PO_AP_MATCHING_V` ไม่มีคอลัมน์ที่ v6.6 ต้องการ
- เอกสาร: `OCR service/n8n/docs/workflows/n8n_flow_v6_6.md` (ใหม่ 376 บรรทัด) + `parity_spec_matrix.md` v2.0.0
- บันทึก canonical records ทั้งสองชุดครบถ้วน (CHG-20261003-002, CHG-20261003-004, ERR-20261003-001, session files)

## Previous Result
- TASK-20261003-001 ย้ายโครงสร้าง Web Portal ทั้งหมดจาก `invoice-web/` → `Web portal/` ด้วย `git mv` (รักษา history), ปรับ root `.gitignore` + paths; backend unittest 15/15 ใน 6.303s, OCR regression 9/9 ใน 5.22s
- TASK-20261002-008 ปรับ n8n workflow `aLUCmn3l0bZDjbVV` ให้ทำงานตรงกับ Python FastAPI engine (v6.5) ผ่าน MCP และอัปเดตเอกสาร flow structure — diff หลัง re-export ตรงกันทุกตัวอักษรสำหรับ 7 jsCode + N7 jsonBody, harness รัน code จาก export จริง 7/7 เคสตรง Python
- TASK-20261002-007 Synthetic invoice corpus: `tests/test_invoices/` มี 155 PDF (157 หน้า) + answer key 155 รายการที่ผลิตจาก `app/core/rules` จริง
- Normalize UI ของ Web Portal ทั้งหมด: KPI cards + consolidated filter bar, high-contrast queue table, Executive 3-Way Match Snapshot, Provenance bar, 3-Step Verification Stepper, Discrepancies callout with PDF jump, Decision Hub และ 5 detail tabs
- Backend unittest 15 ผ่าน, TypeScript + Vite production build ผ่าน, Playwright E2E 6 ผ่าน (desktop/mobile 390px)

## Outside this task
- ไม่แก้ source code ของ OCR/rules engine (Python เป็น v6.6 ครบแล้ว) และ ไม่แก้ Web Portal
- ไม่ activate / เปิด schedule ของ workflow โดยไม่ได้สั่ง
- ไม่ push ข้อมูลความลับ (token, invoice payload, ข้อมูลส่วนบุคคล) ขึ้น git repository

---

## Task ID: TASK-20261003-005
- **Title:** Proof: ผลลัพธ์ n8n canvas ตรงกับ Python engine (Standard v6.6) และปิดช่องว่างที่ตรวจพบ
- **Status:** completed
- **Started / Completed:** 2026-10-03T13:50:00+07:00 → 2026-10-03T14:25:00+07:00
- **Depends on:** TASK-20261003-002
- **Goal:** ทำให้คำว่า "port 1:1" มีหลักฐานจริง — เทียบ output ของ canvas `aLUCmn3l0bZDjbVV` กับ Python pipeline บน input เดียวกัน โดยไม่สร้างความเสียหายให้ Paperless/LiteLLM/Oracle MCP/Portal

### Plan
- [x] จับ baseline ฝั่ง Python จาก fixture จริง (`tests/fixtures/verified_scenario.json`) ด้วย `run_matching_pipeline()`
- [x] ตรวจ SQL ที่ canvas ยิงจริงกับ Oracle MCP → พบ branch PO ดึง 8,359 แถว
- [x] ออกแบบ + validate คำสั่งใหม่ (inline Hop 1 + `NOT EXISTS` guard) กับ Oracle จริงทั้ง 2 branch ก่อน deploy
- [x] deploy ผ่าน `aiva-n8n_update_workflow` (`setNodeParameter /jsonBody`) แล้ว export กลับมา render SQL เทียบกับไฟล์ที่ validate ด้วย `cmp`
- [x] normalize รูป field ของ `rules[]` ที่ `N11` ให้ตรงกับ `model_dump()` ของ Python
- [x] รัน canvas จริงด้วย `test_workflow` + pinData (ไม่แตะระบบภายนอก) แล้วเทียบ Table 9 ทีละหัว field
- [x] อัปเดตเอกสาร + canonical records ทั้งสองชุด

### Acceptance criteria
- decision / rules / exceptions / `dms` / `access` / `receiver` / `invoice_summary` ตรงกัน 100% (ส่วนต่างที่เหลือนอกเหนือจากนี้ต้องเป็น cosmetic และต้องบันทึกไว้)
- ผลการยิง Oracle ของ canvas เท่ากับ Python ทั้ง branch invoice และ branch fallback
- ไม่เกิด side effect ภายนอก (ไม่ tag Paperless, ไม่ยิง LiteLLM, ไม่ยิง Portal จริง)
- workflow ยัง `active: false` และโครงสร้าง node/connection ไม่เปลี่ยน

### Result
- n8n execution `#324` status `success` (`lastNodeExecuted = N14: Verification & Tagging Summary`)
- Table 9 ตรงกับ Python ทุกหัว field หลัก; known deltas 3 ข้อบันทึกใน `parity_spec_matrix.md` §5 (รูปแบบตัวเลข `E15`, superset field `po_numbers`/`SUPPLIER_IS_INTERNAL`/`MATCHED`, `timestamp`)
- Oracle rows: 7 (invoice branch) และ 4 (fallback) เท่า Python — ลดจาก 8,359 แถวของเวอร์ชันก่อนแก้
- ไม่แก้โค้ด Python; `tests/run_tests.py --mode offline` = ALL PASSED

---

## TASK-20261003-006: ทำให้ Standard v6.6 Synthetic Corpus เป็น benchmark ที่เชื่อถือได้จริง
- **Status:** completed
- **Started / Completed:** 2026-10-03T13:50:00+07:00 → 2026-10-03T14:35:00+07:00
- **Depends on:** TASK-20261003-003 (engine v6.6), TASK-20261003-005
- **Goal:** dataset 100 cases + PDF 100 ไฟล์ + suite offline replay ต้องเป็น answer key ที่เอาไปวัด OCR/decision ได้จริง ไม่ใช่ชุดที่รายงานว่าครบแต่ตรวจไม่ผ่าน

### Plan
- [x] audit สถานะจริง (pytest + ดูว่า runner เรียก suite หรือไม่) แทนการเชื่อรายงานเดิม
- [x] ปิดช่องว่าง engine: Table 9 ต้องระบุชื่อ breaker ที่ Gate 2 (`halted_by = "V-04"`) โดยไม่เปลี่ยนผลของกฎ
- [x] เก็บ multi-PO ground truth จาก Oracle จริง (ห้ามสังเคราะห์เลขที่ใบรับ) → snapshot v1.1
- [x] deterministic realism weaving + fail-fast guard + วัด `meta.realism` จากของ build จริง
- [x] แก้ renderer/test ที่ผิด และต่อ v6.6 tier เข้า `tests/run_tests.py`
- [x] sync เอกสาร contract (`halted_by`) + recalibrate answer key เก่า 155 ใบ
- [x] บันทึก canonical records ทั้งสองชุด + ย้าย plan ไป completed

### Acceptance criteria
- 100 cases · decision mix 35/30/30/5 · 100% re-derive ผ่าน engine จริงได้ผลเดิม
- PDF 100 ไฟล์ตรงกับ payload (หน้า, เลขบิล, กล่อง PO ครบทุกเลข, ยอด, กล่องลายเซ็นว่าง = ลายเซ็นที่หาย)
- Gate 1/Gate 2 ถูกตัดจริงและ `V-07 = not_evaluated`; `halted_by` ระบุชื่อ breaker
- realism quotas ผ่านแบบวัดได้: multi-PO ≥25, split ≥15, fuzzy ≥25, weight ≥10, two-hop ≥4, ผู้ขาย Oracle ≥15 ราย
- `pytest tests/test_corpus_v66.py` ผ่าน 100% และ `tests/run_tests.py --all` ALL PASSED

### Result
- 100 cases · Auto-pass 35 / Review 30 / Hold 30 / Reject 5 · **re-derived 100/100 expectations identically**
- realism (measured): suppliers 20 · multi-PO 34 · two-hop 5 · split/lot 17 · intercompany 4 · fuzzy 99 · weight 13
- exception coverage E01–E10/E12/E14/E15 ครบ (ไม่ถูกยก: `E11`, `E13` — documented gap ของ engine)
- `pytest tests/test_corpus_v66.py` = **215 passed** (จาก 14 failed) · `tests/run_tests.py --all` = **SUCCESS (ALL PASSED)** 4 tiers / 30.99s
- multi-PO ทุกเคสอ้างใบรับที่มีจริงใน EBS (28 ใบรับที่เก็บเพิ่มรอบนี้) — ไม่มีเลขสังเคราะห์เหลืออยู่

---

## TASK-20261003-007: Integrate `origin/main` (portal restructure) เข้ากับ `main` โดยไม่แตะ `OCR service/`
- **Status:** completed
- **Started / Completed:** 2026-10-03T15:10:00+07:00 → 2026-10-03T15:35:00+07:00
- **Depends on:** TASK-20261003-001 (การย้ายโฟลเดอร์ที่ค้างอยู่), งาน portal ของอีกฝั่งใน `origin/main`
- **Goal:** ปลดล็อก `git pull` ที่ล้มเหลวแบบ `Merge with strategy ort failed` โดยไม่สูญเสียงานของฝ่ายใดฝ่ายหนึ่ง — ยอมรับ layout portal ของ remote ทั้งก้อน แต่ `OCR service/` ต้องไม่ถูกแตะ

### Plan
- [x] วินิจฉัยจากหลักฐาน: แยก error จริงออกจาก warning (whitespace) และวัดระดับความรุนแรงของ divergence
- [x] dry-run merge ด้วย `git merge-tree --write-tree` เพื่อ counting conflict จริงก่อนแตะ worktree
- [x] ตรวจผล merge ที่ค้างใน `.git/AUTO_MERGE` ว่าถ้าฝืนแล้วไฟล์ของ remote กี่ไฟล์จะหาย
- [x] backup สองชั้น: snapshot commit จาก `git stash create -u` + คัดลอก dirty paths ทุก path ออกนอก repo
- [x] ยกเลิกการย้ายโฟลเดอร์ฝั่ง local (unstage → restore `invoice-web/` จาก HEAD → `git clean -fd` แบบไม่ใช้ `-x`)
- [x] commit records + ปรับ `.gitignore` ตาม layout ใหม่ แล้ว merge และแก้ conflict `agent/current-state.md` แบบคงเนื้อหาทั้งสองฝ่าย
- [x] รัน test จริงสองฝั่ง + พิสูจน์ว่า `OCR service/` ไม่ถูกแตะ แล้วบันทึก canonical records ครบชุด

### Acceptance criteria
- merge สำเร็จ ไม่มี conflict ค้าง; `invoice-web/` หมดจาก repo; งาน mockup ของ remote ครบ (invoice-web1 106 / invoice-webV2 58 / invoice-webv3 9 / .agents 3 / session log 8)
- `OCR service/` = 0 ไฟล์ที่ถูกแก้โดย merge และ dirty items 41 รายการคงเดิม; test ผ่านจริงบันทึกพร้อมตัวเลข
- ไม่มีข้อมูลลับ (sqlite/invoice payload/token) ถูก commit

### Result
- merge commit `2ce5b9e`; conflict มีไฟล์เดียวคือ `agent/current-state.md` (แก้ด้วยมือ คงเนื้อหาทั้งสองฝ่าย) — ตรงตามที่ dry-run ทำนายไว้
- layout ใหม่: `Web portal/{invoice-web-9054076, invoice-web1, invoice-webV2, invoice-webv3, .agents}`; `git ls-files invoice-web` = 0
- พิสูจน์ว่าไม่แตะ OCR: `git diff <merge-base> origin/main -- "OCR service"` = 0 ไฟล์; dirty items ในโฟลเดอร์คงเดิม 41 รายการ
- test หลัง merge: OCR service `235 passed, 9 deselected (35.10s)` · portal backend `invoice-web1` `15 passed (3.68s)` · mockup v3 smoke `46 checks passed`
- backup คงอยู่: `git\wip-backup-20261003\` (136 paths) + branch `backup/wip-dirty-20261003`; `Web portal/` ตรงกับ `origin/main` ทุก byte; branch ยังนำหน้า remote (ยังไม่ push รอคำสั่ง)
- งานต่อเนื่องที่เปิดไว้: เลือกเวอร์ชัน canonical ของ portal, แก้ `build-domain-data.py` ให้รองรับ shape ใหม่ของ `master_data.py` (`--check` กำลัง fail), ล้าง `Web portal/data/` ที่ค้าง

## TASK-20261005-001: Autonomous Evaluation Loop รอบที่ 1 — วัด baseline, วินิจฉัย, และผ่าน mutation แรกของ System A Core
- **Status:** completed (รอบที่ 1) — งาน perception รอบที่ 2 ยังเปิดใน `.agent/todo.md`
- **Started / Completed:** 2026-10-05T21:44:00+07:00 → 2026-10-05T23:55:00+07:00
- **Depends on:** ระบบ vision gateway + Oracle read-only, ชุดเอกสารจริง 99 ฉบับใน Paperless-ngx
- **Goal:** ทำให้ "ความแม่นยำของ Core" เป็นสิ่งที่วัดได้และเปรียบเทียบได้ก่อน แล้วจึงแก้ component ที่พิสูจน์
  ว่า penyebab จริง โดย **ไม่แตะ Standard v6.6** (`policy.yaml`, `codes.yaml`, `rules.yaml`) และ ไม่ทำให้
  เอกสารผ่านแบบผิด ๆ

### Plan
- [x] สร้าง rollback anchor (`.agent/baseline/` + commit `291bd76`) เพราะ `config`/`src` ยังไม่ถูก track
- [x] สร้าง harness การวัด: replay จาก perception cache ที่ pin (`replay.py`), สแกน V-01 ไม่ใช้ LLM
  (`step1_scan.py`), fleet report + diff (`fleet_report.py`), ตัวคำนวณ V-05/V-07 ที่ไม่มี noise ของโมเดล
  (`v05_predict.py`, `uom_diff.py`), probe gateway (`vlm_probe.py`)
- [x] พิสูจน์ความเที่ยงของ harness ด้วยรันจริง `process_pdf.py --dms-id 20` แล้วเทียบระดับ exception code
- [x] รัน baseline 99 ฉบับ (`full_r0`) เป็น regression anchor ถาวร
- [x] วินิจฉัย error cluster ด้วยหลักฐานจริง แทนการเชื่อ backlog ตั้งต้น (ซึ่ง sai ว่าปัญหาหน่วยนับคืองานใหญ่)
- [x] MUT-01 ตารางลูกค้า (V-05), MUT-02 หน่วยนับ (V-07), MUT-03 กู้ JSONคำตอบ vision (V-01/pages_complete)
- [x] Gate แต่ละ mutation ด้วยตัวเลขที่ตรวจซ้ำได้ + รัน `full_r1` เทียบทั้ง fleet
- [x] commitแยกต่อ mutation, อัปเดต canonical records ทุกไฟล์

### Acceptance criteria
- baseline ทำซ้ำได้ + มี anchor ที่เปรียบเทียบรอบถัดไปได้
- ทุก mutation ต้องมี: หลักฐานก่อนแก้, ตัวเลขหลังแก้, กลไก rollback, และคำอธิบายว่าทำไมไม่ใช่การ loosening
- ห้ามมีเอกสารใด "ดีขึ้น" เพราะ tolerance/กฎถูกหย่อน — ตรวจว่า `policy.yaml`/`codes.yaml`/`rules.yaml` ไม่ถูกแก้
- ไม่มีการ map หน่วยนับข้ามกลุ่ม (Standard X-06) และไม่นำข้อมูลใบแจ้งหนี้มาสร้างทะเบียนลูกค้า

### Result
- baseline `full_r0` ทำซ้ำ distribution ของรอบสดเดิม **ตรงทุกตัวเลข** (AUTO_PASS 0, MANUAL_REVIEW 71.7%,
  REVIEW 14.1%, HOLD 13.1%, SYSTEM_ERROR 1) และชี้ว่า E01/V-01 คือคอขวดจริง ไม่ใช่ backlog ตั้งต้น
- **MUT-01** `4d80ffc`: V-05 `manual_review` **53 → 0** (83 ฉบับ) + E07 เท็จ 0 — พบว่า Table 4 กับ RCV-V01
  ใช้ ORG_ID คนละชุด (sub-org vs operating unit) ซึ่งไม่ทับกันเลย = V-05 ไม่เคยผ่านมาก่อน
- **MUT-02** `9ab2e9c`: E10 **70 → 68**, E10 ใหม่ 0; ปฏิเสธการ map ข้ามกลุ่ม 8 รายการที่มาตรฐานห้าม
- **MUT-03** `64152ea`: Tier B DMS-20 `pages_complete` false → true, เส้นบิล 12 → 6 (ตัดตารางซ้ำ),
  max severity **High → Medium**, E13/E11 หาย 9 รายการ; หน้าที่กู้ข้อมูลยังถูก flag ว่าอ่านไม่ครบ
- **Gate (`full_r1` 23/99):** comparable 23, improved 1, **REGRESSED 0**
- สิ่งที่ได้เพิ่มนอกเหนือจากตัวเลข: หลักฐานว่า 2/3 ของเส้นบิลทุกฉบับมีหน่วยนับที่ใช้ไม่ได้
  (NOT_PRESENT 238 + LOW_CONFIDENCE 168 จาก 608 เส้น) และ `cache_key()` ไม่รวม code version
- งานรอบถัดไป (เปิดใน `.agent/todo.md` TASK-V01-00): บังคับให้ `vision_table_rows` คืนคอลัมน์หน่วยนับ,
  เพิ่มผู้อ่านคนที่สองของ cell ที่มั่นใจต่ำ, แล้วค่อยกลับไปดู V-07 matching prompt

---

## TASK-20261005-002: Web Testing Portal สำหรับ System A Core (Phases 1–5)

Started: `2026-10-05T20:40:00+07:00` · Finished: `2026-10-05T23:55:00+07:00` · Status: **DONE** (`2d87f6e`)

### Goal
สร้าง portal ทดสอบ/ดีบัก System A แบบโต้ตอบตาม `TASK_WEB_TEST_PORTAL.md` โดยไม่แก้ตรรกะการตรวจสอบ
และคง Standard v6.6 integrity

### Plan
1. Backend: subprocess bridge ไป `process_pdf.py` + SSE progress + result store + health (Phase 1)
2. แปลง Contract 3.0 → overlay ต่อหน้า ผ่าน `element_id`/`evidence` เท่านั้น (Phase 2)
3. UI: viewer + bbox overlay + panels (Phase 3) และ cross-highlighting สองทาง (Phase 4)
4. Launcher, test suite, README (Phase 5)

### Acceptance criteria → ผลจริง
- [x] portal ไม่แตะ `src/system_a/**` และ `config/**` — commit มีแต่ `web/**` + `.gitignore`
- [x] ผลรันผ่าน portal = ผลรัน CLI: `integrity.payload_sha256` ตรงกัน (DMS-20 sandbox)
- [x] ทุกกรอบมาจาก `element_id` ของ contract (ไม่มี text search / no screen geometry) → fields 12/13,
      cells 30/30, rows 6/6, signatures 2/2, exception boxes 5 (DMS-20)
- [x] อ่าน `coordinate_system` จากผลจริง และรองรับ `[x,y,w,h]` / `[x1,y1,x2,y2]`, normalized/point/pixel,
      origin bottom-left (ทดสอบทั้ง 3 แบบใน `test_ui_logic.mjs`)
- [x] test suite offline: pytest 24/24 + browser-module 25 checks
- [ ] คลิกทดสอบบน browser จริงโดยผู้ใช้ (logic ผ่านหมดแล้ว แต่ layout/CSS ยังไม่ได้สายตาคน)

---

## TASK-20261006-001: ปิดงาน portal ที่ค้าง — เส้นทาง upload, การอ่าน error จาก DMS, และตัวตรวจ live

Started: `2026-10-06T07:30:00+07:00` · Finished: `2026-10-06T08:25:00+07:00` · Status: **DONE** (`5a058e0`)

### Goal
งาน portal รอบก่อนถูกทิ้งไว้ใน working tree (ยังไม่ commit) โดยแก้ไปครึ่งทาง: ต้องทำให้จบ ปิด
regression ทั้งสองเคส และพิสูจน์ด้วย portal ที่รันอยู่จริง — โดยไม่แตะ `src/system_a/**` และ `config/**`

### Plan
1. ตรวจโค้ด/test ที่ค้างอยู่ → ผ่าน pytest 29 แล้วทำต่อ
2. ทำให้ error จาก Paperless "อ่านออก" ถึงตาผู้ใช้ (backend สถานะ + ประโยค, frontend แสดง `detail`,
   viewer ไม่ให้ภาพที่โหลดไม่ออกจบแบบเงียบ)
3. เปิด portal จริง + รัน `web/check_live.py` เพื่อยืนยันบนของจริง
4. แก้สิ่งที่ checker เปิดโปงออก แล้วเพิ่ม test กันถอยหลัง + บันทึก canonical records

### Acceptance criteria → ผลจริง
- [x] อัปโหลด PDF แล้วกด Verify ได้จริง (เดิม 422 เพราะ route `{doc_id}` กลืน `upload`) —
      offline test + live check "uploaded PDF verifies end to end" (HTTP 200 + `done` exit 0)
- [x] เอกสารที่ไม่มีใน Paperless แล้ว = `404` พร้อมข้อความ "DMS-<id> is not in Paperless-ngx"
      ทุก endpoint ที่แตะเอกสาร (meta/pdf/page png); token ผิด = `502`, ไม่ได้ตั้งค่า DMS = `503`
- [x] ข้อความ failure ไปถึงตาผู้ใช้: toast แสดง `detail` ไม่ใช่ JSON envelope, ภาพที่โหลดไม่ออก
      จะถาม endpoint กลับเพื่อหาสาเหตุ (และแยกกรณี "endpoint ให้ภาพได้ แต่ browser ไม่วาด")
- [x] `web/check_live.py` ถูก commit (รอบก่อนเขียนไว้แต่ไม่เคย `git add`) และ **เขียวจริง**: 77/77
      บน portal ที่รันอยู่ (รวม sandbox verification ของ DMS-114: perception cache hit, exit 0, REVIEW)
- [x] ตัวตรวจเองต้องพังอย่างอ่านได้: pytest รัน checker ชน port ที่ปิด → FAIL lines + ABORT, ไม่มี traceback
- [x] ไม่แตะ core — `git diff --cached --name-only` มีแต่ไฟล์ใต้ `system-a/web/`
- [ ] การคลิกทดสอบโดยคนจริงบน browser ยังไม่เกิด (logic/DOM ถูก harness ครอบแล้ว)

### Result
- pytest **31/31** (เพิ่ม 5), browser modules **27/27** (เพิ่ม 2 ที่ครอบ failure path),
  live checker **77/77**
- ของที่ได้ฟรีจากการเปิดโปงของ checker: NameError ที่ทำให้งาน "ทดสอบบน live" ของรอบก่อนไม่เคยเกิดขึ้นจริง,
  `json.loads` 12 จุดที่ไม่ทนต่อ body ที่ไม่ใช่ JSON, และ check ที่เขียนกรอง SSE ผิด key จึงไม่มีวันเขียว
- หลักปฏิบัติใหม่ (ERR-20261006-002): script ที่เขียนไว้ "ตรวจระบบที่กำลังพัง" ต้องถูกรันตอนระบบไม่อยู่ด้วย
  และ tool ที่ใช้ตรวจงานต้อง commit พร้อมงาน

### Next (ยังไม่เริ่ม)
- กลับเข้า TASK-V01-00 ใน `.agent/todo.md`: บังคับให้ `vision_table_rows` คืนคอลัมน์หน่วยนับ
  (เป้าหมาย 238 NOT_PRESENT cells) — ตอนนี้ดูผลลัพธ์ line-by-line บน portal ได้แล้ว
- ก่อนแก้ perception ให้ย้าย `import fitz` → `pymupdf` ไปด้วยในครั้งเดียว เพื่อจ่ายค่า perception cache
  หนึ่งครั้ง (DEC-016)

---

## TASK-20261006-002: ตั้งราคาของงาน UOM ก่อนจ่าย perception cache reset

- **Status**: DONE (ไม่มี VLM call, ไม่แตะ engine)
- **Start / End**: 2026-10-06T08:16:00+07:00 → 2026-10-06T08:32:00+07:00
- **ได้รับคำสั่งจาก user**: option 1 = ทำ UOM + `fitz`→`pymupdf` ในรอบเดียวแล้ว re-pin baseline
- **เหตุผลของรอบนี้**: การเปลี่ยน perception 1 บรรทัด = ทิ้ง cache 112 extractions / 425 หน้า (~3 ชม. VLM)
  งานแพงขนาดนี้ต้องพิสูจน์สมมติฐานด้วย cache เดิมก่อน ไม่ใช่จ่ายแล้วค่อยรู้ว่าผิด

### Plan
1. replay `raw` + `word_ids` + `region` จาก cache baseline (`PKG-2026-10-05-full-*`) — ห้าม VLM call
2. แยกให้ได้ว่า cell ที่หายคือ "อ่านไม่ออก" หรือ "ไม่ได้พิมพ์อยู่บนเอกสาร" (เปิด PDF จริงดูด้วยตา)
3. จำลองนโยบาย V-01 จริง (`policy.yaml`) ระดับเอกสาร เพื่อดูเพดานของแต่ละนโยบาย consensus
4. ตั้งราคา "ถ้าแก้ UOM สำบูรณ์ 100%" แล้ว V-01 จะผ่านกี่เอกสาร
5. เสนอ user ใหม่ถ้ายอดที่วัดได้ต่างจากที่เข้าใจ

### Acceptance criteria → ผลจริง
- [x] ตัวเลข UOM จริง: 608 เส้น → มี 2 ผู้อ่านยืนยัน 202, cell เดี่ยว 168, **ไม่อยู่จริง 238**
      และ **236 ใน 238 อยู่ในหน้าที่ไม่พิมพ์คอลัมน์หน่วยนับรายบรรทัด** (DMS-40 ยืนยันด้วยตา —
      หัวตารางมี "หน่วยละ" = ราคาต่อหน่วย ไม่ใช่หน่วยนับ)
- [x] กรณีที่หน่วยอยู่ใน **หัวคอลัมน์** (DMS-65 "จำนวนแผ่น Pcs.", "นน./แผ่น Kgs./Sheet") เมื่อจำกัด geometry
      ที่ code ใช้ได้จริง + vocabulary เข้ม → recover ได้ **12/143 cell ใน 2 เอกสาร** ไม่ใช่ 238
- [x] เพดานของนโยบาย consensus (documents ที่ V-01 ผ่าน / 99): P0 วันนี้ **0**, P1 รันของคำใน box **1**,
      P2 +containment **3**, P3 + substring ของแถว **5**, P4 + substring ทั้งหน้า **16** (P4 ไม่ใช่หลักฐานที่รับได้)
- [x] ราคาของการแก้ UOM ให้สมบูรณ์: P0 **0**, P2 **11**, P3 **13** → **UOM ไม่ใช่กำแพงใหญ่สุด**
      กำแพงที่เหลือ: `customer_name` readers ขัดกัน **43 เอกสาร** (VLM ดูด caption เข้าค่า + text layer
      ไทยเพี้ยน), ตัวเลขอยู่บนหน้าแต่ไม่อยู่ใน box ที่โมเดลเคลม (34–39), cell ที่โมเดลไม่คืนมา (12–16)
- [x] ช่องว่างเพิ่มเติมที่เจอระหว่างทาง: `max_words=2500` ต่อดocument ทำให้หน้าท้ายๆ ไม่เก็บ word เลย
      (DMS-40 p5: 2,054 ตัวอักษร / 0 words) → 42/99 เอกสารโดนตัด และ **84 cell ที่ต้องการตกบนหน้าโดนตัด**
- [x] พบข้อจำกัด control plane: `.agent/` ถูก gitignore (`git ls-files` = 0 ไฟล์) → baseline/todo/decisions
      มีสำเนาเดียวบนดิสก์เครื่องนี้ (ควรจัดการ — TASK-OPS-07)

### Result
- **ไม่รันรอบ "บังคับคอลัมน์ uom"** — สมมติฐานผิด และการบังคับคืนค่า = เติมข้อมูลที่ไม่ได้พิมพ์อยู่บนกระดาษ
  (OQ-09 ห้าม) — ดู ERR-20261006-003
- ชุดที่ควรซื้อด้วย cache reset ครั้งเดียว (รอ user ยืนยัน เพราะเพดานต่างจากที่คุยไว้):
  1. prompt — ค่า field ห้ามกลืน caption ของตัวเอง (เป้า 43 เอกสาร `customer_name`)
  2. prompt — คืนหน่วยนับที่พิมพ์ใน **หัวคอลัมน์ของคอลัมน์ qty** พร้อม provenance (text+bbox) และ
     `NO_UOM_PRINTED` เมื่อเอกสารไม่พิมพ์เลย (เพื่อ report พูดความจริงแทน "อ่านไม่ผ่าน")
  3. code — ยอมรับ "รันของคำติดกันภายใน box" + pad ≈0.02 (145 line cells + 14 fields ที่ pad 0.02)
  4. code — `max_words` ต้องไม่ลบ word ของหน้าใดหน้าออกจาก `consensus_units`
  5. code — `import fitz` → `import pymupdf` (DEC-016 จ่าย cache reset ครั้งเดียว)
  แล้ว re-pin baseline โดยตั้งความคาดหวัง **V-01 ≈ 11–13/99 ไม่ใช่ 99** (AUTO_PASS ยังติด V-05/BLOCKER-01)

### Next
- รอ user เลือก: จ่าย cache reset ซื้อชุด 5 ข้อ / ทำแค่ (3)+(4)+(5) which are deterministic / หรือส่ง
  คำถามมาตรฐาน 2 ข้อให้ owner ก่อน (V-01 รับหน่วยจากหัวคอลัมน์ได้ไหม + ควร block ไหมเมื่อเอกสารไม่พิมพ์หน่วย)
