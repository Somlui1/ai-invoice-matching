# Task และ Plan

Last updated: 2026-10-03T15:35:00+07:00

## Active Task
- Task ID: TASK-20261003-007
- Title: Integrate `origin/main` (portal restructure) เข้ากับ `main` โดยไม่แตะ `OCR service/`
- Status: completed
- Goal: ทำให้ repo กลับเป็นเส้นเดียวที่ push ได้ โดยยอมรับ layout ของ `origin/main` ทั้งพื้นที่ `Web portal/` (ผู้ใช้สั่งชัดเจนว่าสถานะ portal ในเครื่องไม่สำคัญ ให้ merge ทับ) แต่ต้องมีหลักฐานยืนยันว่างาน `OCR service/n8n` ฝั่ง local (15 แก้ไข + 26 untracked + v6.6 corpus) ไม่หายและไม่ถูกแตะ

## Plan
- [x] backup full workflow JSON + แยกโหนดเก็บก่อนแก้ (ไว้ restore)
- [x] diff โค้ดโหนดบน canvas กับ canonical copies → ยืนยันว่า logic ตรงกัน แล้ว resync
- [x] ตั้ง workflow name/description ใหม่ + ปรับ IF gate condition ให้ใช้ boolean field `has_e02` / `has_critical_receipt_issue`
- [x] rename โหนดที่ไม่ถูก `$()` อ้างถึง + rename IF nodes ให้ชื่อตรงหน้าที่ Gate
- [x] เพิ่ม Sticky Notes 8 ใบ และจัด 6 Node Groups ตาม STEP (`Manual Trigger` ต้องอยู่นอกกลุ่ม)
- [x] ตรวจ canvas จาก live export: edges / dangling / `$()` refs / gate wiring
- [x] สร้าง `docs/workflows/n8n_flow_v6_6.md` (logic-first) และเขียน `parity_spec_matrix.md` เป็น v2.0.0
- [x] อัปเดต canonical records ทั้ง `agent/` และ `OCR service/n8n/.agent/`

## Acceptance criteria
- Workflow ชื่อ `AIVA PO-INV Matching Verification v6.6 (Explanatory Flow)` และยัง `active: false`
- ไม่มี edge ค้าง, ไม่มี `$()` ที่พัง, Gate ทั้งสองยังชี้ `true → N10`
- เอกสาร 2 ฉบับอยู่ระดับ v6.6 และมีตารางเทียบรหัส exception เก่า (E05–E35) → ใหม่ (E01–E15)
- ผลยืนยันต้องมาจาก live canvas export และ Oracle EBS จริง (ไม่ใช่การคาดเดา)
- บันทึก canonical records ครบตามระเบียบ AGENTS.md

## Result
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
