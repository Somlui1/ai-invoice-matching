# Task และ Plan

Last updated: 2026-10-03T14:25:00+07:00

## Active Task
- Task ID: TASK-20261003-002
- Title: อัปเดต n8n canvas `aLUCmn3l0bZDjbVV` และเอกสาร `OCR service/n8n/docs/workflows/` ให้เป็น Standard v6.6 แบบ Explanatory Flow
- Status: completed
- Goal: ทำให้ Canvas บนเซิร์ฟเวอร์ n8n และเอกสารอ้างอิงสอดคล้อง Standard v6.6 (exception E01–E15, Gate 1/2, Two-Hop Multi-PO, Table 9 Schema v1.5) โดยเอกสารต้องอธิบาย "ตรรกะและเหตุผล" รายขั้น อ่านแล้วเข้าใจทันทีโดยไม่ต้องเปิดดูโค้ดทีละโหนด

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
