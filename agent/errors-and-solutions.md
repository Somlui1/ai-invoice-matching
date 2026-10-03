# Error และ Solution

บันทึกเฉพาะปัญหาที่มีโอกาสเกิดซ้ำและมีวิธีป้องกันที่นำกลับมาใช้ได้ รายการใหม่ต้องเพิ่มด้านล่างเท่านั้น

## Entry Format

- Error ID: `ERR-YYYYMMDD-NNN`
- Detected: เวลา ISO 8601 พร้อม timezone
- Context: งานหรือไฟล์ที่เกี่ยวข้อง
- Symptom: อาการที่สังเกตได้
- Root Cause: สาเหตุที่ยืนยันแล้ว
- Solution: วิธีแก้ที่ใช้ได้ผล
- Prevention: กติกาหรือ check ที่ป้องกันการเกิดซ้ำ
- Evidence: path, test หรือ command ที่ใช้ยืนยัน โดยไม่ใส่ secret
- Status: `open`, `mitigated` หรือ `resolved`

## Known Errors

### `ERR-20261001-001` — Thai Markdown mojibake in PowerShell output

- Detected: `2026-10-01T15:18:00+07:00`
- Context: อ่าน `OCR service/n8n/README.md` และ `OCR service/n8n/n8n flow structure.md`
- Symptom: อักษรไทยแสดงเป็นชุดอักขระ `à¸...` ใน terminal output
- Root Cause: PowerShell session ถอดรหัสไฟล์ UTF-8 ด้วย encoding ที่ไม่ตรงกัน
- Solution: ระบุ UTF-8 อย่างชัดเจนเมื่ออ่านไฟล์ เช่น `Get-Content -Raw -Encoding UTF8 <path>`
- Prevention: หากพบ mojibake ให้หยุดสรุปเนื้อหาและอ่านใหม่ด้วย UTF-8 ก่อนแก้ไฟล์
- Evidence: source files แสดงโครงสร้าง Markdown ถูกต้อง แต่อักษรไทยผิดเฉพาะ output ที่อ่านด้วย default encoding
- Status: `mitigated`

### `ERR-20261002-001` — Windows test temporary directory permissions
- Detected: `2026-10-02T08:33:00+07:00`
- Context: invoice-web backend tests on Windows sandbox / Python 3.14
- Symptom: creating child PDF directory in tempfile.TemporaryDirectory returned WinError 5
- Root Cause: OS temporary directory permissions in this execution context denied nested writes/cleanup
- Solution: create unique test directories under ignored invoice-web/data/tests and verify containment before cleanup
- Prevention: keep test runtime artifacts within the writable workspace; do not weaken global filesystem permissions
- Evidence: backend unittest suite subsequently passed 9 tests
- Status: `resolved`

### `ERR-20261002-002` — Hand-written expected results drifted from the real rules engine

- Detected: `2026-10-02T18:10:00+07:00`
- Context: replay of the 55 wave-1 invoices in `tests/test_invoices/test_dataset.json` through `app.core.rules`
- Symptom: 30 invoices disagreed with the engine — `halted_by` was filled per failing rule while the engine only ever sets `V-02`; partial-billing cases (INV-A09–A11) were keyed as Review although V-09 also raises E31 (real decision is Hold); INV-B13/B14 missed E31; INV-A04 gained a benign E16
- Root Cause: expectations were derived from a hand-written rule model instead of the engine, and the engine's V-09 compares invoice subtotal with the full received value, so partial billing always adds E31
- Solution: added `invoice_engine.py` + `verify_dataset.py`; wave-2 expectations are produced by the engine at build time and wave-1 was recalibrated with `verify_dataset.py --fix` (drift now 0/155, marker `recalibrated: engine-v6.2`)
- Prevention: never hand-write Table 9 expectations; build them by calling `evaluate_step1..4` and keep the Oracle rows that produced them (`oracle_rows`) in the dataset so the key stays reproducible
- Evidence: `verify_dataset.py` prints `All replayed expectations already match the engine output.` for 155 invoices
- Status: `resolved`

### `ERR-20261002-003` — Thai text extraction from generated PDFs returns mojibake

- Detected: `2026-10-02T18:25:00+07:00`
- Context: validating rendered synthetic invoices in `tests/test_invoices/pdfs/` with pypdfium2 text pages
- Symptom: Latin/digits extracted fine but Thai strings came back as `�Ţ...Шӣ` sequences, even though rendered pages show correct Thai
- Root Cause: the embedded Tahoma subset carries no usable ToUnicode CMap for the Thai glyphs, so text-layer mapping is unreliable even though glyph rendering is correct
- Solution: `check_pdfs.py` compares only ASCII/digit tokens (tax IDs, invoice serial, PO digits, totals) which are exactly what V-01 completeness cares about, and page images are inspected visually via pypdfium2 + Pillow
- Prevention: for OCR-corpus QA, verify Thai content by rendered image (the production path is a vision LLM on page images) and do not trust the PDF text layer of Tahoma-subset PDFs
- Evidence: `check_pdfs.py` reports 155 PDFs / 157 pages with 0 mismatches; preview renders confirmed correct Thai glyphs
- Status: `mitigated`

### `ERR-20261002-004` — PDF audit silently skipped its missing-field assertion

- Detected: `2026-10-02T19:00:00+07:00`
- Context: writing `tests/test_invoice_corpus.py` and mutating the dataset to prove the audit is not vacuous
- Symptom: `check_pdfs.py` returned `[ OK ]` even after the key was edited to claim a printed field was missing; the "field must be absent" branch never fired for the 55 wave-1 invoices
- Root Cause: the branch compared against `oracle_rows[0]`, which only exists on wave-2 entries, so `absent_source` was `{}` and the digit token was shorter than the 6-char guard — a silently inert assertion
- Solution: resolve the source row from the stored wave-2 rows first, otherwise look up `_raw/oracle_receipts.csv` by `oracle_source.receipt_num` (same lookup the renderer uses); also harden `document_flags` handling with `inv.get(...) or {}`
- Prevention: whenever adding a "should be absent" style check, run a deliberate mutation (lie in the answer key) and require the checker to fail; prefer an explicit unverifiable counter over an implicit skip
- Evidence: mutation `INV-A01.supplier_tax_id = None` now yields `INV-A01: supplier_tax_id should be missing but '0105531097289' is printed`; clean dataset still reports 0 failures and `pytest` 9 passed
- Status: `resolved`

### `ERR-20261002-005` — n8n MCP `setNodeParameter` writes to a nested `parameters.parameters` key

- Detected: `2026-10-02T19:40:00+07:00`
- Context: patching Code nodes of workflow `aLUCmn3l0bZDjbVV` with `aiva-n8n_update_workflow` using `path: "/parameters/jsCode"`; the call returned `appliedOperations: 2` with no warning, but a re-export still showed the old v6.4 code
- Symptom: node gained a stray key `parameters.parameters.jsCode` containing the new code while `parameters.jsCode` (the field n8n actually executes) kept the old code — a silent, successful-looking no-op
- Root Cause: the tool's JSON Pointer `path` is already resolved **relative to the node's `parameters` object**, so `/parameters/jsCode` appends one level instead of replacing `jsCode`
- Solution: use `/jsCode`, `/jsonBody`, `/options`; remove the leftover blob with a second `setNodeParameter` operation whose `value` is `null` (the tool nulls the key). Then re-export and diff stored code against the local source files byte-for-byte
- Prevention: after every `update_workflow` call, re-fetch the workflow and compare the target field to the intended value instead of trusting `appliedOperations`; treat "op applied" as transport success, not semantic success. Node-level flags (`onError`, `alwaysOutputData`) land as top-level node keys in the export, not under `settings`
- Evidence: final export diff reports `IDENTICAL` for all 7 rewritten `jsCode` fields and the N7 `jsonBody`; `tmp/run_flow_sim.js` (which executes the exported code) then produces the expected Table 9 decisions
- Status: `resolved`

### `ERR-20261002-006` — `ORA-01791` when a receipt query drops `ITM_CODE` from the SELECT list

- Detected: `2026-10-02T19:15:00+07:00`
- Context: reshaping the `AH_DEV_RCV_PO_AP_MATCHING_V` query in `N7: Oracle MCP rcv_v01` and testing it through the `oracle` MCP tool
- Symptom: `ORA-01791: not a SELECTed expression` when the query used `SELECT DISTINCT` and `ORDER BY v.RCV_NUM, v.ITM_CODE` but omitted `v.ITM_CODE` from the projection
- Root Cause: with `SELECT DISTINCT`, every `ORDER BY` expression must appear in the select list
- Solution: always keep `v.ITM_CODE` in the projection (the matcher needs it as `ITEM_NUMBER` anyway); validate shape/syntax with a bounded query (`AND v.ITM_CODE = '…'` or `AND ROWNUM <= n`) because `max_rows` is not an accepted argument of `oracle_sql_run`
- Prevention: when editing the N7 SQL, never trim the select list without trimming `ORDER BY`; treat row counts from this dev view as non-deterministic (same query returned 2 rows then 0 rows minutes apart) and assert only shape/syntax
- Evidence: bounded queries through `oracle_sql_run` returned the expected columns including the `SUPPLIER_IS_INTERNAL` scalar (`1` for tax `0145556001111`)
- Status: `resolved`

## ERR-20261003-001: `setNodeGroups` of `aiva-n8n_update_workflow` silently skipped (returns `skippedOperations`)

- Error ID: `ERR-20261003-001`
- Detected: 2026-10-03T13:05:00+07:00
- Context: การจัด Node Groups ให้ workflow `aLUCmn3l0bZDjbVV` ผ่าน MCP `aiva-n8n` (node names of IF nodes contain a trailing `?`)
- Symptom: คำขอตอบกลับ success แต่กลุ่มไม่ถูกสร้าง และรายการ node ถูกยัดกลับไปใน `skippedOperations` โดยไม่มี error message ที่บอกเหตุผลตรงๆ
- Root Cause: 2 สาเหตุที่เกิดคนละรอบ
  1. n8n ไม่อนุญาตให้ node ประเภท trigger (`n8n-nodes-base.manualTrigger`) อยู่ภายใน node group — ถ้า list ของ group มี trigger ปนอยู่ทั้ง group ถูก skip
  2. Node name ที่ส่งไปไม่ตรงกับชื่อจริงบน canvas แบบตัวต่อตัว โดยเฉพาะชื่อที่ลงท้ายด้วย `?` ซึ่งมีโอกาสสูงที่จะถูกถอด/ใส่ไม่ครบตอนประกอบคำขอ (matching เป็น exact string)
- Solution: เอา trigger ออกจากทุก group (ปล่อยไว้ topLevel) และเปลี่ยนชื่อ IF nodes ทั้งสามให้ไม่มี `?` (`N6: IF: Gate 1 Breaker (E02)`, `N8.1: IF: Gate 2 Breaker (E05 E06)`, `N2.2: IF: Unprocessed Document Found`) จากนั้นส่ง rename + `setNodeGroups` ในคำขอเดียวกัน → group ตั้งครบ และคำเตือน `TOP_LEVEL_ITEMS_OVER_CEILING` หมดไป
- Prevention:
  - ก่อนตั้งกลุ่ม ให้ดึงชื่อโหนดจาก `get_workflow` มาใช้ตรงๆ ห้ามพิมพ์เอง และอย่าให้ trigger ติดไปในกลุ่ม
  - ถ้าเป็นไปได้ตั้งชื่อโหนดที่ไม่มี `?` ท้าย (ชื่อ gate ควรบอกหน้าที่ เช่น `Gate 1 Breaker (E02)`) และโหนดใดที่ถูก `$()` อ้างถึงต้องตรวจรายชื่อก่อน rename เสมอ
  - หลังส่ง ops ต้องอ่าน `skippedOperations` / warnings ใน response แล้ว re-fetch workflow เพื่อยืนยัน ไม่ใช่เชื่อว่า success แล้วเสร็จ
- Evidence: response ของ `aiva-n8n_update_workflow` 2 ครั้งแรก (4 ops applied / 6 groups skipped) และผล re-export หลังแก้ = 31 nodes, 24 edges, 0 dangling, 0 broken `$()` ref
- Status: `resolved`

## ERR-20261003-002: ไม่สามารถใส่ node-level `notes` ให้โหนดเดิมผ่าน `aiva-n8n_update_workflow`

- Error ID: `ERR-20261003-002`
- Detected: 2026-10-03T12:55:00+07:00
- Context: ต้องการเขียนคำอธิบายไว้ในตัวโหนดของ canvas เพื่อให้เปิดแล้วเข้าใจทันที
- Symptom: `addNode` รับ field `notes` ได้ แต่ไม่มี path ใดใน update API ที่ตั้ง/แก้ `notes` ของโหนดที่มีอยู่แล้ว (แก้ได้เฉพาะ parameter ของโหนดนั้น)
- Root Cause: ข้อจำกัดของ MCP update surface —โหนดเดิมรับได้แค่ rename/parameters/positions ไม่ใช่ property ทุกชนิด
- Solution: ใช้ node ประเภท `n8n-nodes-base.stickyNote` (`addNode` + parameters `{content,width,height}`) วางกำกับแต่ละกลุ่มแทน และ **ไม่เอา sticky เข้า node group** เพื่อให้เป็น annotation ล้วนๆ ที่ไม่มีผลต่อ workflow execution
- Prevention: เมื่อต้อง "เขียนคำอธิบายบน canvas" ให้เริ่มที่ Sticky Notes เป็นทางเลือกแรก และเก็บเนื้อหาเดียวกันไว้ในเอกสาร (`docs/workflows/n8n_flow_v6_6.md`) ด้วยเสมอ เพราะ sticky หากระงับ/ลบจะหายไปจากประวัติ
- Evidence: workflow ปัจจุบันมี 31 nodes = 23 flow nodes + 8 Sticky Notes และทุก sticky ไม่มี edge เชื่อมต่อ
- Status: `resolved`

---

## ERR-20261003-003: Oracle query ของ n8n canvas คืนแถวกว้างเกินจริง (8,359 แถวจาก PO เดี่ยว) เพราะ branch PO ไม่มี guard
- **ID:** `ERR-20261003-003`
- **Date:** `2026-10-03T14:25:00+07:00`
- **Severity:** High (ประสิทธิภาพ + ความเสี่ยงรอบ error cap 50 แถว)
- **Context:** ตรวจ parity ระหว่าง canvas `aLUCmn3l0bZDjbVV` กับ Python pipeline บนบิลจริง `ED6909/0837` (PO เดี่ยว `40083989`)

### Symptom
- คำสั่งของ `N7: Oracle MCP: Hop 2 (RCV-V01)` คืน **8,359 แถว** ทั้งที่คำตอบที่ถูกคือ 7 แถว
- `N7.1: Parse Oracle Receipts` ยังเลือกแถวได้ถูกต้อง (filter แถว invoice ก่อน) ผลลัพธ์ Table 9 จึงไม่เพี้ยน — แต่ payload เข้า memory เกินจริงราว 2.5 MB ต่อเอกสาร

### Root Cause
1. Canvas ยุบ Two-Hop ให้เป็น query เดียว โดยเอา branch PO มา `OR` กับ branch invoice **แบบไม่มีเงื่อนไข** → PO ที่มีการรับสินค้าสะสมหลายร้อยใบจะคืนทุกประวัติการรับของ PO นั้น
2. Canvas ไม่มียิง Hop 1 → เมื่อ OCR อ่าน Tax ID ไม่เจอ branch invoice จะไม่ bind ด้วย Tax ID เลย ยิ่งทำให้ branch PO ถูกใช้บ่อย
3. Python ไม่มีปัญหานี้เพราะ `get_receipts()` ยิง branch PO **เฉพาะเมื่อ invoice query คืน 0 แถว**

### Solution
- inline Hop 1 เป็น scalar subquery บน PO แรก: `(SELECT COALESCE(pv1.VAT_REGISTRATION_NUM, pv1.NUM_1099) FROM apps.po_headers_all ph1 JOIN apps.po_vendors pv1 ON pv1.VENDOR_ID = ph1.vendor_id WHERE ph1.SEGMENT1 = '<PO แรก>')` ใช้เฉพาะกรณี Tax ID ว่าง + invoice_num มีอยู่ + PO ไม่ขึ้นต้น `INV` (ตรงกับเงื่อนไข `resolve_supplier_tax_id_by_po()`)
- ครอบ branch PO ด้วย `NOT EXISTS (<branch invoice เดิม>)` ให้ fallback ทำงานเฉพาะเมื่อไม่เจอแถวจากเลขที่บิล
- ผลหลังแก้ (ตรวจด้วย `oracle_sql_run` จริง): `ED6909/0837` + PO `40083989` = **7 แถว**; กรณีบิลไม่มีใน ERP (`TLP-NOT-EXIST-9999` + PO `42052835`) = **4 แถว** เท่า log Python เดิม

### Prevention
- เวลาเทียบ parity ให้เทียบ "จำนวนแถว/ข้อมูลที่ยิงจริง" ด้วย ไม่ใช่เทียบเฉพาะ output JSON — output ที่ถูกอาจเกิดจากการกรองของ node ถัดไปก็ได้
- ห้ามลบ `NOT EXISTS` guard ออกจาก branch PO (บันทึกไว้เป็น checklist ข้อ 3 ใน `docs/workflows/n8n_flow_v6_6.md`)
- ถ้าอนาคตต้องใช้ view รวม (เช่น `APPS.AH_DEV_RCV_PO_AP_MATCHING_V`) ต้องตรวจว่ามี `SHIPMENT_NUM`/`PACKING_SLIP`/`LINE_STATUS`/`RECEIVER` ก่อน เพราะ view เดิมไม่มีคอลัมน์เหล่านี้

---

## ERR-20261003-004: ตัวเลข "realism" ของ synthetic corpus มาจากการสังเคราะห์ข้อมูล ERP และการนับที่ needle เอียง ทำให้ benchmark รายงานเกินจริง

- **ID:** `ERR-20261003-004`
- **Timestamp:** 2026-10-03T14:35:00+07:00
- **Component:** `OCR service/n8n/tests/test_invoices/*` (corpus builder + `tests/test_corpus_v66.py`)
- **Task:** `TASK-20261003-006` / `CHG-20261003-006`

### Context
corpus v6.6 100 เคส + PDF 100 ไฟล์ถูกรายงานว่าเสร็จและครบ quota (multi-PO 36, splits 25, fuzzy 40) เพื่อใช้เป็น answer key ฝึก/วัด multimodal OCR

### Symptom
- `pytest tests/test_corpus_v66.py` = 14 failed / 199 passed แต่ถูกรายงานว่า green เพราะ `tests/run_tests.py --all` ไม่เคยเรียก suite นี้
- 12 เคส fail แบบ "PDF ไม่มีกล่องลายเซ็น" ทั้งที่ PDF พิมพ์กล่องว่างครบ
- multi-PO 36 เคสใช้เลขที่ใบรับ `RCV-CONSOLIDATED-*` ที่ประกอบขึ้นจากการรวม 2 ใบรับ

### Root Cause
1. Assertion ฝั่ง search ผ่าน `collapse()` (ตัด whitespace) แต่ needle ไม่ผ่าน → `count()` ได้ 0 เสมอ (false failure ทุกไฟล์)
2. Builder ยอมให้ defect ที่ระบุตำแหน่งบรรทัด "ถูกข้ามเงียบ" เมื่อ pool ที่ draw มา มีแถวน้อยกว่า index → เคสหลุดเป้าโดยไม่มี warning
3. เพื่อชน quota มีการสร้าง primary key ของ ERP ขึ้นมาเอง → expectation ที่ engine คำนวณต่อ ไม่ได้สะท้อนพฤติกรรมของระบบจริงอีกต่อไป (เลขที่ไม่มีใน Oracle = ไม่มีวันถูก query เจอ)

### Solution
- collapse needle ก่อนค้นหาเสมอ (constant `BLANK_SIGNATURE_MARKER`) + assert จำนวนกล่องว่าง = จำนวนลายเซ็นที่หายจริง
- builder fail-fast: `take(..., min_rows=)` และ raise เมื่อ index เกินจำนวนแถวจริง, ล็อก mutation ที่ calibrate กับมูลค่าเอกสาร, ตรวจ `archetype → decision_status` หลัง build ทุกครั้ง
- ทิ้งเลขสังเคราะห์ทั้งหมด แล้วเก็บใบรับที่หลาย PO จริงจาก Oracle (28 ใบ) ผ่าน projection + parser ตัวเดียวกับ production → snapshot v1.1 (170 scenarios)
- ทุกตัวเลข realism คำนวณจากเคสที่ build เสร็จแล้ว และล็อกไว้ด้วย test assertions (multi_po ≥25, split ≥15, fuzzy ≥25, weight ≥10, two-hop ≥4, suppliers ≥15)

### Prevention
- **ห้ามสร้างเลขที่เอกสาร ERP (RECEIPT_NUM / PO_NUM / TAX_ID) ขึ้นเองในชุดทดสอบ** — ถ้าสถานการณ์ที่ต้องการยังไม่มีใน ERP ให้ไปเก็บของจริงมา หรือบันทึกว่าไม่ครอบคลุม ไม่ใช่ประกอบเลขปลอม
- ทุก quota ต้องมี 3 ส่วนครบ: วัดจริง → พิมพ์ออกใน meta → assert ใน test; ตัวเลขที่ไม่มี test จับถือว่ายังไม่จริง
- เวลา "งานเก่าบอกว่า done" ให้รันคำสั่งตรวจจริงก่อนเสมอ และตรวจว่าคำสั่งนั้นถูกเรียกจาก entry point จริง (runner/report ที่ไม่เรียก suite = false green)
