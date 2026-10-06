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

## ERR-20261003-005: `git pull` ล้มเพราะ uncommitted directory rename ชนกับ remote ที่ย้ายโฟลเดอร์เดียวกัน — และการฝืน merge จะลบงานของอีกฝั่งทิ้งเงียบ ๆ

- Recorded: 2026-10-03T15:35:00+07:00 · Task: `TASK-20261003-007` · Related: `CHG-20261003-007`

### Context
- `main` diverged (ahead 1 / behind 6) ทำให้ `git pull` เป็น merge จริงซึ่งต้องการ working tree ที่สะอาดใน path ที่จะถูกเขียน
- ฝั่ง local มีการย้าย `invoice-web/` → `Web portal/` แบบ staged (87 ไฟล์) + worktree edits 6 ไฟล์ แต่ยังไม่ได้ commit
- ฝั่ง `origin/main` ย้าย `invoice-web/` ไป `Web portal/invoice-web-9054076/` และเพิ่ม `invoice-web1/`, `invoice-webV2/`, `invoice-webv3/`, `.agents/` (รวม 272 path ที่ทับพื้นที่กัน)

### Symptom
- `error: Your local changes to the following files would be overwritten by merge: Web portal/...` แล้วจบที่ `Merge with strategy ort failed.` (ort เป็น default merge strategy ของ git 2.49+; ล้มที่ขั้นตอน checkout ไม่ใช่ขั้นตอนคำนวณ merge)
- บรรทัด `<stdin>:2568: trailing whitespace.` และ `warning: 11 lines add whitespace errors` เป็นเพียง warning จากเนื้อหา blob (xref table ของ PDF) ไม่เกี่ยวกับความล้มเหลว — อ่าน error ผิดบรรทัดจึงวินิจฉัยผิดทาง
- ผลข้างเคียง: merge ที่ล้มเหลวทิ้งผลคำนวณไว้ที่ `.git/AUTO_MERGE`

### Root Cause
- ทั้งสองฝ่ายย้ายโฟลเดอร์ต้นทางเดียวกันไปยังคนละตำแหน่ง และฝ่ายหนึ่งยังไม่ commit → git ไม่สามารถเลือกปลายทางได้เอง จึงปฏิเสธการเขียนทับ
- directory rename detection ของ ort ตัดสินใจ "ยุบ" ทั้งคู่ลงบน `Web portal/` ฝั่งเรา ผลคือ tree ใน `.git/AUTO_MERGE` มี 159 ไฟล์ ขณะที่ `origin/main` มี 340 ไฟล์ — ถ้าฝืน merge ด้วย `git checkout -f` / `git clean -fd` / `git stash -u && git pull` งาน mockup 176 ไฟล์ + session log 8 ไฟล์ของอีกฝั่งจะหายไปโดยไม่มี conflict ให้แก้

### Solution
- จำลอง merge ที่ระดับ commit ก่อนแตะ worktree: `git merge-tree --write-tree HEAD origin/main` → พบว่า conflict จริงมีไฟล์เดียว (`agent/current-state.md`) และ portal renames เป็น `R100` (เนื้อหาไม่เปลี่ยน) → วางแผนได้ว่า "แก้ conflict 1 ไฟล์" ไม่ใช่ "แก้ 87 ไฟล์"
- ตรวจผลข้างเคียงที่ค้าง: `git ls-tree -r $(cat .git/AUTO_MERGE)` แล้วเทียบด้วย `comm` เพื่อวัดปริมาณว่างานฝั่งไหนจะหาย → ใช้เป็นหลักฐานยืนยันว่าห้ามฝืน merge
- backup สองชั้น: `git stash create -u` + `git branch backup/wip-dirty-20261003 <sha>` (ไม่แตะ worktree เลย) และคัดลอกทุก path จาก `git status --porcelain` ออกนอก repo
- ยกเลิกการย้ายฝั่งเราอย่างมีลำดับ: `git rm -r --cached -f -- "Web portal"` → `git checkout HEAD -- invoice-web "Web portal"` → `git clean -fd -- "Web portal"` (**ไม่ใช้ `-x`** เพื่อไม่ให้ลบไฟล์ ignored เช่น `data/`, sqlite, `node_modules`) + `find ... -name __pycache__ -exec rm -rf` สำหรับโครงโฟลเดอร์ที่เหลือแต่ไดเรกทอรีว่าง
- set `git config merge.directoryRenames conflict` ให้ directory rename ที่กระทบกันกลายเป็น conflict ให้อ่าน ไม่ถูกยุบเงียบ แล้ว `git merge --no-ff origin/main` → แก้ conflict ด้วยมือ (คงเนื้อหาทั้งสองฝ่าย) → merge commit `2ce5b9e`

### Prevention
- **เห็น `would be overwritten by merge` ให้ `git status` + `git fetch` + `git log --oneline HEAD..origin/main` ก่อนเสมอ** ถ้าอีกฝั่งมีการ restructure ระดับโฟลเดอร์ ต้อง commit หรือยกเลิกงานย้ายโฟลเดอร์ของเราก่อน อย่าฝืน
- แยก commit การย้าย/เปลี่ยนชื่อโฟลเดอร์ออกจาก commit เนื้อหา และ commit เร็ว — directory rename ที่ค้างใน working tree คือแหล่ง conflict ที่ debug ยากที่สุด
- ใช้ `git merge-tree --write-tree` เป็น dry-run มาตรฐานก่อน merge ครั้งใหญ่ (ไม่แตะ worktree, อ่าน conflict ได้จริงทั้งชื่อไฟล์และจำนวน)
- `git stash`/snapshot อย่างเดียวไม่พอสำหรับ untracked files — เก็บ `git stash create -u` (แล้วทำ branch ชี้ผล) ควบคู่กับการคัดลอกไฟล์ออกนอก repo และ **ตรวจ mtime/ขนาดไฟล์หลัง backup** เพราะไฟล์อาจถูก editor อื่นบันทึกซ้ำระหว่างทำ (พบจริงกับ `OCR service/n8n/app/AIVA-Document-Card-Verification-v3.html`)
- warning เรื่อง whitespace / `LF will be replaced by CRLF` (จาก `core.autocrlf=true`) ให้ตัดออกจากการวินิจฉัย; ถ้าต้องการให้เงียบและนิ่งจริงให้เพิ่ม `.gitattributes` แบบ `* text=auto eol=lf`

### `ERR-20261004-001` — Python script body duplicated in one file (double `main()`)

- Detected: `2026-10-04T15:13:00+07:00`
- Context: `OCR service/new engine/tests/bbox_testv3.py` ก่อนเริ่ม batch vision-OCR
- Symptom: ไฟล์มี 1,306 บรรทัด ทั้งที่โมดูลจริงยาว 653 บรรทัด — `grep -c "__main__"` คืน **2**, `import importlib.util` ปรากฏที่บรรทัด 31 และ 684; ถ้ารันจะประมวลผลเอกสารทั้งชุดแล้วยิง AI ซ้ำรอบสองโดยไม่มี error ใด ๆ (silent waste ของ GPU/time)
- Root Cause: การคัดลอก/วางหรือ append ทั้งไฟล์ซ้ำลงท้ายไฟล์เดิม — ส่วนที่ซ้ำเริ่มด้วย docstring (`"""` บรรทัด 654) ซึ่ง Python มองเป็น string literal ทิ้งไป แล้วรันโค้ดสำเนที่สองต่อจากนั้น ทำให้ `main()` ถูกเรียกสองครั้ง
- Solution: แบ่งไฟล์ที่เส้นแบ่งธรรมชาติ (หลัง `main()` บรรทัด 653) เป็น `/tmp/c1.py`, `/tmp/c2.py` แล้ว `diff` → 0 บรรทัด (byte-identical) จึงคงไว้เฉพาะซีกแรก ผล: 663 บรรทัด, `__main__` = 1, `py_compile` ผ่าน
- Prevention: ก่อนรันสคริปต์ batch ที่มีการเรียก AI จริง ให้ `grep -c "if __name__" f` และ `wc -l f` เป็น sanity check แรก (ค่ามากกว่า 1 = มีอะไรผิดปกติ) — ตัวเลขขนาดไฟล์/จำนวนบรรทัดที่โตขึ้นสองเท่าคือสัญญาณของการวางซ้ำ; ถ้าต้องใช้ซ้ำจริงให้แยกเป็นโมดูลแล้ว import ไม่วางซ้ำในตัวไฟล์
- Evidence: `diff <(sed -n '1,653p' bbox_testv3.py) <(sed -n '654,1306p' bbox_testv3.py)` = 0 บรรทัด; หลังแก้ `wc -l` = 663 และ `python -m py_compile` ผ่าน
- Status: `resolved`

### `ERR-20261004-002` — UnicodeEncodeError (cp874) ฆ่า Python script ที่ print ภาษาไทยบน Windows

- Detected: `2026-10-04T15:15:48+07:00`
- Context: `bbox_testv3.py` รันผ่าน git-bash บน Windows (console encoding เป็น cp874/Thai) — สคริปต์ log ภาษาไทยปนสัญลักษณ์ `·`, `✗`, `⚠`
- Symptom: `UnicodeEncodeError: 'charmap' codec can't encode character '\xb7' in position 19` ที่ `encodings/cp874.py` → ตายตั้งแต่ `print` บรรทัดแรกก่อนเริ่มงาน batch (ยังไม่ได้เรียก AI เลย) และ log ออกเป็น mojibake
- Root Cause: Python ใช้ encoding ของ console เป็น stdout encoding เมื่อไม่ได้ redirect แบบ UTF-8; อักขระ `·` (U+00B7) ไม่มีใน cp874 map — ต่างจาก error ฝั่ง decode เพราะนี่คือ **encode** ตอนพิมพ์
- Solution: reconfigure stream ที่ต้นโมดูลก่อน `print` ทุกจุด `for s in (sys.stdout, sys.stderr): s.reconfigure(encoding="utf-8", errors="replace")` (ห่อ try/except `AttributeError/ValueError` กันกรณี stream ถูก redirect เป็นสิ่งที่ไม่ใช่ file) และตั้ง `PYTHONIOENCODING=utf-8` ตอนยิงจริงเพื่อความสบายใจของ log file
- Prevention: สคริปต์ไทยทุกตัวที่พิมพ์ลง console บน Windows ต้อง set stdout encoding ที่ต้นไฟล์ ไม่ใช่แก้ด้วย env var นอกเครื่อง (คนรันคนถัดไปจะไม่ตั้ง) หรือเลี่ยงอักขระนอก cp874 ทั้งหมด; ถ้าเห็น `'charmap' codec` ให้แก้ที่ encoding ทันที อย่าไปตัดภาษาไทย/สัญลักษณ์ออก
- Evidence: รันซ้ำหลังแก้ → log อ่านภาษาไทยถูกต้อง `Paperless: 99 ฉบับ · ต้องทำ 99 · ข้าม (ทำแล้ว) 0 · workers=2` และทำงานต่อถึงเอกสารที่ 8+ โดยไม่ error
- Status: `resolved`

### `ERR-20261004-003` — แก้ template ของ report แล้วแต่ไฟล์ `report.html` ยังเป็นแบบเก่า

- Detected: `2026-10-04T16:45:00+07:00`
- Context: แก้ `REPORT_HTML` ใน `bbox_testv3.py` (เพิ่ม overlay ชี้/คลิก bbox) ขณะที่ batch เดิมยังรันค้างอยู่
- Symptom: แก้โค้ด template ผ่าน test แล้ว แต่เปิด `out/batch/report.html` ขึ้นมายังเป็น layout เดิม (ไม่มี overlay) ทั้งที่ process เพิ่งเขียนไฟล์สด ๆ ร้อน ๆ
- Root Cause: 2 ปัจจัยรวมกัน — (1) Python โหลด module เข้า memory ครั้งเดียวตอนเริ่ม process การแก้ไฟล์ `.py` ระหว่างรัน **ไม่มีผล** กับ process เดิม ดังนั้น `write_report()` ครั้งสุดท้ายของรอบนั้นใช้ template เก่า (2) งานเขียนไฟล์ซ้ำหลายรอบ (เขียนทุก 5 ฉบับ) ทำให้เข้าใจว่า "เขียนล่าสุด = ต้องเป็นโค้ดใหม่"
- Solution: รอให้ process จบแล้ว re-render ใหม่จากผลที่เก็บไว้แล้วด้วยโหมด build รายงานเท่านั้น — `python bbox_testv3.py --report-only` (สร้างจาก `docs/doc_*/doc.json`, ไม่เรียก AI) และต่อฉบับ `python bbox_test.py <id> --report-only` (สร้างจาก `page_*.json`)
- Prevention: (1) แยก "ชั้นเก็บผล" ออกจาก "ชั้น render รายงาน" ให้ build รายงานใหม่จากผลที่เก็บไว้ได้เสมอ (โหมด `--report-only`) แล้วสอนให้เป็นขั้นตอนปิดงานทุกครั้งหลังแก้ template (2) ถ้าจะแก้โค้ดที่ process กำลังรันอยู่ ให้ถือว่าผลของรอบนั้นใช้ template เก่า และตั้งใจ re-render ตอนจบ (3) ตอน verify ผลของการแก้ UI ให้ตรวจเวลาที่เขียนไฟล์ + ตรวจว่า process ไหนเขียน
- Evidence: หลัง `--report-only` ไฟล์ `out/batch/report.html` มี overlay 15,111 กล่อง (ครบทุกกรอบที่เก็บทั้ง 99 ฉบับ) และผ่าน harness jsdom 20/20 (ก่อนหน้าไม่ผ่านเพราะไม่มี `.bx` เลย)
- Status: `resolved`

### ERR-20261005-001 — Windows cp874 stdout UnicodeEncodeError in verification scripts

- Detected: 2026-10-05T20:40:20+07:00
- Context: รัน scripts/run_stats.py และ scripts/verify_run.py บนสภาพแวดล้อม Windows
- Symptom: UnicodeEncodeError: 'charmap' codec can't encode character '≥' / '→'
- Root Cause: Default encoding ของ stdout ใน Windows terminal คือ cp874 ซึ่งไม่มี mapping สำหรับ unicode สัญลักษณ์คณิตศาสตร์และลูกศร
- Solution: ใส่ 	ry: sys.stdout.reconfigure(encoding='utf-8') except Exception: pass ที่จุดเริ่มต้นของ script และใช้ตัวอักษร ASCII เช่น >=
- Prevention: ทุก CLI script ใน repository ต้อง reconfigure stdout เป็น UTF-8 เสมอเมื่อรันบน Windows
- Evidence: 
un_stats.py และ erify_run.py รันสำเร็จและ exit code 0
- Status: 
esolved

---

### ERR-20261005-002 — V-05 forced Manual Review because Table 4 and RCV-V01 use different ORG_ID spaces

- Detected: 2026-10-05T22:35:00+07:00
- Context: ตรวจว่าทำไม V-05 ให้ผล `manual_review` กับทุกเอกสารที่ไปถึง ใน 99 ใบแจ้งหนี้จริงของ System A sandbox
- Symptom: `detail = "ORG_ID 195 สถานะ ไม่อยู่ในตารางที่ 4 หรือไม่มี Tax ID"` ทั้งที่ชื่อ/Tax ID บนใบแจ้งหนี้
  เป็นบริษัทเดียวกับใบรับใน Oracle จริง
- Root Cause: RCV-V01 คืน `ph.ORG_ID` จาก `PO.PO_HEADERS_ALL` ซึ่งเป็น **operating unit** id
  (`APPS.HR_OPERATING_UNITS` = 101, 176, 195, 197, 202, 223, 243, ...) แต่ Standard v6.6 §04 ตารางที่ 4
  ลงทะเบียนด้วย id ของ **sub-organization** (103, 175, 196, 199, 222, 224, ...) ซึ่งเป็นอีกแถวหนึ่งใน
  `HR_ALL_ORGANIZATION_UNITS` ของบริษัทเดียวกัน — ค่าสองชุดนี้ไม่ทับกันเลยแม้แต่ค่าเดียว
- Solution: เพิ่มแถว bridge ใน `OCR service/system-a-sandbox/system-a/config/standards/v6.6/buyer_entity.yaml`
  ที่คีย์ = operating unit id ที่ Oracle ส่งจริง โดยคัด identity (Tax ID/ชื่อ/ที่อยู่) จากแถวตารางที่ 4 ของ
  บริษัทเดียวกัน และจับคู่จากชื่อใน `HR_OPERATING_UNITS` แบบ 1:1 เท่านั้น; OU ที่ไม่ชัด (285 Plastics,
  475 Bike, 555 MG, 596 AVEE, 202 ITS, 177, 292, 375, 393 และแถวที่มาตรฐานระบุ ยังไม่ทราบ) คง
  `status: unknown` เพื่อให้ V-05 ส่ง Manual Review ต่อตามมาตรฐาน ทุกแถว bridge เก็บ
  `table4_org_id` และ `erp_ou_name` ไว้ตรวจสอบ
  ผลวัดจริง (`v05_predict.py`, 83 ฉบับ): V-05 `manual_review` 53 -> 0 และไม่มีเอกสารใดกลายเป็น E07
- Prevention: เวลาเขียนทะเบียนอ้างอิงลูกค้าที่ผูกกับผลลัพธ์ SQL ต้องตรวจว่าคีย์ที่ใช้เป็น id ชุดเดียวกับที่
  SQL คืนจริงเสมอ (probe ด้วย `SELECT DISTINCT <key>` เทียบกับ key ในไฟล์ config ก่อน) และเก็บหลักฐาน
  cross-reference ไว้ในตัวไฟล์ config; ห้ามปิดอาการด้วยการลดเงื่อนไขของกฎ
- Evidence: `.agent/harness/v05_predict.py`, `.agent/eval/orgid_probe.md`,
  `SELECT organization_id, name FROM APPS.HR_OPERATING_UNITS`, PO 42052405 -> ORG_ID 195
- Status: Resolved (workaround ใน sandbox) — **ต้องแก้ที่ต้นทาง**: มาตรฐาน §04 ต้องเพิ่มคอลัมน์
  operating-unit id (เจ้าของ: AERP)

### ERR-20261005-003 — VLM answers lose their JSON because reasoning tokens eat max_tokens

- Detected: 2026-10-05T23:05:00+07:00
- Context: ใบแจ้งหนี้ 21/99 ฉบับมี `pages_complete = false` ทำให้ V-01 ตก (E01) และเอกสารถูกกักทั้งที่อ่านออก
- Symptom: `extra.page_errors` = `page_items: AIResponseError: no JSON object` (18 หน้า) และ
  `truncated JSON object` (3 หน้า)
- Root Cause: โมเดล vision ที่ gateway (`nvidia/Qwen3.8-Flash-Next-NVFP4`) เปิด reasoning เป็น default
  เมื่อ client ไม่ได้ส่ง `chat_template_kwargs.enable_thinking`; probe หน้าจริง (DMS-20 หน้า 3) ได้
  `completion_tokens 5819` โดยเป็น `reasoning_tokens 2577` จากโควตา `max_tokens = 8000`
  หน้าที่ข้อความหนาแน่นกว่านั้นจะถูกตัดกลางคำตอบ ทำให้ `content` ไม่มี JSON object ที่ครบ
  และ `pages_complete=not truncated and not any(r.error ...)` จึงเป็น false
- Solution: ใน `src/system_a/adapters/llm/litellm_client.py` เพิ่มการกู้คำตอบตามลำดับ
  (1) decode ตามปกติ (2) repair prompt เดิม (3) ส่งซ้ำโดยปิด reasoning
  (4) `salvage_json_object()` เก็บเฉพาะสมาชิก JSON ที่ครบถ้วน โดยปิด `in_str` ให้ถูกต้องและปิด
  bracket ตาม stack จริง; เพิ่ม counter `no_thinking_retries`, `decode_salvaged`
  และใน `perception/vision_pipeline.py` หน้าที่ต้องใช้วิธี salvage จะยังถูกติดธง
  `read.error = "page_items: truncated JSON answer, only complete members kept"`
  เพื่อให้ `pages_complete` เป็น false เหมือนเดิม (ไม่เปลี่ยน failure เป็น pass ตอนข้อมูลยังหาย)
- Prevention: ทุก call ที่บังคับตอบเป็น JSON ต้องกำหนดโควตา token ของ reasoning ให้ชัดเจน
  (เปิด/ปิดเชิงเดียว ไม่ใช่ปล่อยให้ default) และต้องทดสอบด้วยหน้าเอกสารที่หนาแน่นที่สุด ไม่ใช่หน้าเดียว
  ที่ว่าง; ห้ามแก้ด้วยการลดเงื่อนไข required field ของ V-01
- Evidence: `.agent/harness/vlm_probe.py 20 3` (raw usage), `.agent/harness/test_salvage.py` 12/12 pass
- Status: Resolved (unit-level); ผลต่อ V-01 ต้องยืนยันด้วยการ re-perception จริง (Tier B)

### ERR-20261005-004 — WRONGLY DIAGNOSED (corrected 2026-10-06): the perception cache key does include a code fingerprint

- Detected: 2026-10-05T23:35:00+07:00 · **Corrected: 2026-10-06T00:40:00+07:00**
- Symptom ที่เจอจริง: รัน `process_pdf.py` ซ้ำหลังแก้โค้ด perception แล้วได้ผลเดิม ไม่เรียก VLM
- **What I wrote first (wrong)**: "cache_key() ไม่ได้รวม code_version" และแนะนำให้เพิ่ม code_version เข้า key
- **หลักฐานที่ตรวจซ้ำแล้ว (ถูกต้อง)**: `process_pdf.py` บรรทัดก่อนเรียก `cache_key()` มี
  `opts["pipeline"] = pipe.code_version` อยู่แล้ว และ `CODE_VERSION = _code_fingerprint()`
  (vision_pipeline.py:40-58) hash source ของ `pdf_ingest`, `coords`, `vision_pipeline` เข้าด้วยกัน
  → **key ครอบคลุมโค้ดอ่านภาพอยู่แล้วโดยออกแบบ** คำแนะนำเดิมจึงเป็นการแก้ที่ไม่มีผลจริง
- สาเหตุจริงของอาการ: ตอนที่รัน Tier B (22:33) การแก้ `vision_pipeline.py` ยังไม่ได้ถูกบันทึก
  fingerprint ตอน import จึงยังเท่าเดิม (57f4096e01a8 เป็นค่าหลังแก้) ผลที่ cache ไว้จึงได้ key เดิมกับ
  รอบ baseline และการรันที่ชี้ cache เดิมจะถูก hit ของเก่า
- บทเรียนที่ใช้ได้จริง:
  1. **อย่าสรุปกลไกจากบรรทัดเดียว** — ต้องอ่านจนถึงจุดที่ประกอบ options ของ key; ครั้งนี้เห็นแค่ชื่อ
     พารามิเตอร์แล้วสรุปว่าไม่รวม code version
  2. สิ่งที่ยังเป็นช่องว่างจริงคือ **ในไฟล์ cache ไม่มี `code_version` เก็บไว้** (อ่านค่าได้เป็น None ทุกไฟล์)
     จึงดูไม่ออกว่า extraction ไหนเกิดจากโค้ดสถานะไหน → เวลาทดสอบการเปลี่ยน perception layer
     ให้ใช้ `PERCEPTION_CACHE_DIR` แยกเสมอ (ทำแบบนั้นจริงใน MUT-03 และผล Tier B ยังใช้ได้)
  3. ผลข้างเคียงที่ควรทราบ: หลังแก้ `vision_pipeline.py` fingerprint เปลี่ยนเป็น 57f4096e01a8
     extraction ที่ cache ไว้ทั้ง 112 ชุดจะถูกรีเพอร์เซปต์เมื่อรันสดครั้งถัดไป replay harness ยังใช้ได้
     เพราะ `.agent/harness/replay.py` เลือกไฟล์จาก `package_id` ไม่ใช้ key
- Status: Corrected — ไม่มีการแก้โค้ด และไม่มี work-around ที่จำเป็นนอกจาก cache แยกสำหรับทดสอบ

### ERR-20261005-005 — อ่าน result schema ผิดชั้น: `normalized_fields` ไม่ใช่ object ของ field

- อาการ: `GET /api/overlays/{key}` พัง 500 `AttributeError: 'str' object has no attribute 'get'`
  ทั้งที่ endpoint อื่นทำงานปกติ และผล verification ปกติดี
- สิ่งที่เข้าใจผิด: คิดว่า `normalized_fields[name]` เป็น object ที่มี `raw`/`normalized`/`evidence_bbox`
  แล้วใช้เป็นแหล่งเดียวของทั้งค่าและตำแหน่ง
- ความจริงของ Contract 3.0 (ตรวจจาก `cli20_full.json` จริง ไม่ใช่จากเอกสาร):
  - `normalized_fields` = **map name → string** (ไว้แสดงค่าอย่างเดียว)
  - `extraction.fields[name]` = `{raw_value, normalized_value, confidence, ok, null_reason, element_id}`
  - `extraction.lines[].cells[c]` = `{raw_value, normalized_value, ok, null_reason}` — **ไม่มี `element_id`**
  - `extraction.signatures[k]` = `{present, confidence, kind, region:{page, bbox}}`
  - `exceptions[]` มี `evidence_ids` (ไม่ใช่ `element_ids`) และค่าที่กฎเทียบ (`actual_value`,
    `expected_value`, `page_no`, `related_element_ids`) อยู่ในตัว **`evidence[]`**
  - geometry ทั้งหมดอยู่ `ocr.elements[]` (`element_id, element_type, page_no, bbox, field_name, raw_value`)
- วิธีแก้: `build_overlays()` อ่านแยกชั้นให้ถูก — ค่าจาก `extraction.*`, ตำแหน่งจาก `ocr.elements[]`
  โดย join ผ่าน `element_id`; exception → `evidence_ids` → `related_element_ids` → element;
  cell ที่ไม่มี id ใช้ join key `field_name == "lines[<line_no>].<column>"` (key ระดับข้อมูล ไม่ใช่ geometry)
- วิธีป้องกัน: fixture test ที่มีทั้ง field/cell/exception/signature และ assert ว่า "มีกรอบ/ไม่มีกรอบ"
  ถูกต้องตาม `null_reason` — ถ้า schema เลื่อน test จะฟ้องทันที ไม่ใช่พังตอนเปิดหน้า

### ERR-20261005-006 — UI อ่าน key คนละชื่อกับ API: คลิกกรอบแล้วเงียบ ไม่มี error

- อาการ: overlay วาดกรอบครบ แต่กรอบของ header field / cell คลิกไม่ติด และ label ขึ้น `invoice_num=`
  ว่างเปล่า ทั้งที่ pytest ผ่านหมด (ฝั่ง Python ถูกต้องทุกประการ)
- สาเหตุ: `build_overlays()` เก็บ element item เป็น `id` / `text` / `conf` ขณะที่ `panels.js`
  อ่าน `element_id` / `raw` / `confidence` → `dataset.element` ว่าง → `applySelection()` หาไม่เจอ
- บทเรียนที่นำไปใช้ต่อ: **UI ที่ไม่มี build step ต้องมี test ที่รัน module จริง** เพราะ type checker
  และ pytest มองไม่เห็นคำว่าพิมพ์ผิดใน JS; จึงเพิ่ม `web/test_ui_logic.mjs` (โหลด source จริงลงใน vm context
  + DOM stub เฉพาะคำสั่งที่ใช้จริง) ซึ่งจับได้ 3 ข้อผิดพลาดในการเขียนรอบนั้นเอง
- วิธีแก้: API ส่งทั้ง `element_id` (ชื่อหลัก) และ alias `id`/`raw`/`confidence` ที่ viewer ใช้
  พร้อมคอมเมนต์กำกับว่าทำไมต้องมีสองชื่อ; harness assert ทั้ง label มีค่า, `.sel/.dim`, และ join สองทาง
- วิธีป้องกัน: test เดียวกันนี้รันใน pytest (`test_browser_modules_run_against_the_api_data`,
  skip เมื่อไม่มี node) และมี `test_frontend_only_references_ids_that_exist_in_the_markup`
  ตรวจ id ที่ JS อ้างถึงว่ามีจริงใน `index.html`

### ERR-20261005-007 — ข้อความ warning ของ library ใน log ของ engine ถูกอ่านผิดว่าเป็นความล้มเหลว

- อาการ: ผู้ใช้รัน verification ผ่าน portal สำเร็จ (exit 0, 0.9 s) แต่ในช่อง engine log มีบรรทัด
  `warning: The `fitz` API is deprecated and will be removed in future. Use `import pymupdf` instead.`
  ซึ่งหน้าตาเหมือน error — และป้ายผล `[ MANUAL_REVIEW ]` แสดงเป็นอักษรกากบาท เพราะ ANSI escape
  ถูกพิมพ์ออกมาตอนอ่านผ่าน pipe
- สาเหตุ: `engine.py` ใช้ `stderr=subprocess.STDOUT` (จำเป็นเพื่อให้เห็น traceback ของ engine) จึง
  รับข้อความของทุก library มาใน stream เดียวกับ step line โดยไม่มีการแยกระดับ; และ `process_pdf.py`
  ใส่สีแบบไม่ดู `isatty()`
- วิธีแก้ (ทำเฉพาะฝั่ง portal): `strip_ansi()` ทุกบรรทัด + `classify()` ให้ `info`/`warn`/`error`
  พร้อม `hint` ต่อ message ที่ไม่ใช่ความผิด → UI ทาเหลือง/แดง + tooltip, ไม่ซ่อนข้อความ
  pattern ของ error จงใจแคบ (`[ERROR]`, `Traceback (most recent call last)`, `(?<![A-Za-z_])ERROR(?![A-Za-z_])`,
  `CRITICAL`) เพราะ output ปกติของ CLI มีคำว่า "Exceptions / Findings" และ `[ SYSTEM_ERROR ]` อยู่แล้ว
  ซึ่งถ้า match หยาบเกินไปจะกลายเป็น error บังคับทุกครั้งที่รันสำเร็จ
- สิ่งที่ไม่แก้และทำไม: การเปลี่ยน `import fitz` → `import pymupdf` ใน `src/system_a/perception/pdf_ingest.py`
  ทำได้ในทาง syntax แต่ `_code_fingerprint()` อ่าน source bytes ของ pdf_ingest/coords/vision_pipeline
  มาทำ perception cache key → แก้แล้ว cache 112 ชุดตกรุ่น ต้อง re-perceive ~425 หน้า (≈3 ชม.)
  จึงยกไปรวมกับงานแก้ perception รอบถัดไป (DEC-016) เพื่อจ่ายค่า cache หนึ่งครั้ง
- วิธีป้องกัน: test assert ว่า output ปกติของ CLI ทั้งหมดยังเป็น `info` และ `_pump` ส่ง log ที่ไม่มี
  escape ออกมาจริง

### ERR-20261006-001 — `/api/verify/{doc_id}` กลืน `/api/verify/upload` ทำให้อัปโหลดใช้ได้แต่ Verify ตายเงียบๆ

- อาการ: อัปโหลด PDF ผ่าน portal สำเร็จ (`POST /api/upload` คืน key, ภาพหน้า PDF ก็เปิดได้) แต่กด Verify
  แล้วได้ `422 Input should be a valid integer, unable to parse string as an integer` — endpoint อื่น
  ปกติหมด จึงไม่มีสัญญาณว่าสาเหตุมาจาก "ลำดับการ register route"
- สาเหตุ: Starlette ตอบ route แรกที่ **pattern** ตรงกัน ไม่ได้เทียบกับความเฉพาะเจาะจงของ path
  `@app.post("/api/verify/{doc_id}")` ซึ่งเขียนไว้ก่อน จึง match literal `upload` ด้วย
  parameter type (`int`) ทำให้ request ของ upload ตกไปที่ handler ผิดตัว
- วิธีแก้: ย้าย `@app.post("/api/verify/upload")` ขึ้นไป **ก่อน** route ที่มี `{doc_id}` และใส่คอมเมนต์
  หน้าบรรทัดว่า "ORDER MATTERS" เพราะคนอ่าน code review ทีหลังไม่มีทางรู้จากตัวโค้ดอย่างเดียว
- วิธีป้องกัน: `test_uploaded_pdf_can_be_verified` ทำของจริงทั้งเส้น (อัปโหลด PDF ปลอม →
  `POST /api/verify/upload?key=...` → assert 200 + SSE มี contract) โดย assert 422 ไว้ทางอ้อม
  — ถ้าสลับลำดับ route อีก test นี้แดงทันที; และ `check_live.py` มี check "uploaded PDF verifies end to end"
  ที่รันบน portal จริง
- บทเรียน: framework แบบ "first match wins" ต้องมี test ที่ชน literal path ที่ซ้ำกับ parameter name
  เสมอ เพราะระบบตรวจ type fail ล่าช้า (ตอน parse) ไม่ใช่ตอนหา route

### ERR-20261006-002 — สคริปต์ "ตรวจ live" ที่ไม่เคยถูกรัน: NameError, json.loads ตาย, และเงื่อนไขที่ไม่มีทางเป็นจริง

- อาการ: เปิด portal จริงแล้วรัน `web/check_live.py` → `NameError: name 'Path' is not defined`
  ที่บรรทัดรายงาน health (ไฟล์ import แค่ `pathlib`) ทั้งที่ไฟล์ถูกเขียนและ "ทดสอบแล้ว" ในรอบก่อน
  เมื่ออ่านต่อจึงพบว่าอีก 2 จุดก็ผิดแบบเดียวกัน: (ก) `json.loads(body)` 12 จุดจะโยน exception ทันทีที่
  body ไม่ใช่ JSON (portal กำลัง restart หรือ proxy ตอบ HTML) ทำให้ checker ตายแทนที่จะรายงาน FAIL
  (ข) `check("uploaded PDF verifies end to end", any(e.get("ok") for e in ev if "done" in e))` — event
  ที่ engine ส่งคือ `{"type": "done", "ok": ...}` ไม่มี key ชื่อ `done` ดังนั้น `any(...)` เป็น False เสมอ
  **check นี้ไม่มีวันเขียว** ไม่ว่าจะรันถูกหรือผิด
- สาเหตุ: `check_live.py` ไม่ได้อยู่ใน offline suite (ต้องอาศัย server ที่รันอยู่) และไม่ใช่ไฟล์ที่ถูก
  `git add` มาก่อน จึงไม่มีใครรันมันหลังเขียนจบ — tool ที่มนุษย์ใช้ตอนระบบมีปัญหา คือไฟล์เดียวที่
  ไม่มีใครทดสอบตอนระบบปกติ
- วิธีแก้: `pathlib.Path`, `jload()` (body ที่ parse ไม่ได้ = คำตอบประเภทหนึ่ง คืน `{}`),
  ABORT พร้อมข้อความเมื่อ `/api/documents` คืนเอกสาร 0 ฉบับ (ไม่งั้นจะมี 40 FAIL ปลอมมาบังสาเหตุจริง),
  และแก้ตัวกรอง event เป็น `e.get("type") == "done"` พร้อมแสดง `exit_code` ในรายละเอียด
- วิธีป้องกัน: pytest 1 ตัว (`test_live_checker_fails_as_lines_when_the_portal_is_down`) รัน checker จริง
  ชน `http://127.0.0.1:9` — connection refused ทำให้ get/post ทุกตัวคืนค่า error แต่โค้ดทั้งก้อนยังถูกรัน
  จึงจับ NameError/AttributeError ได้ใน ~1 วินาที โดย assert ว่า "ไม่มี Traceback" + มีข้อความ ABORT
- หลักปฏิบัติที่ดึงได้: ถ้าจะเขียน script สำหรับ "ตรวจระบบที่กำลังพัง" ต้องมีโหมดที่รันมันตอนระบบ **ไม่อยู่**
  ด้วย มิฉะนั้นจะรู้คำตอบตอนสาย และ tool ที่ใช้ตรวจงานต้องถูก commit พร้อมงาน ไม่ใช่ค้างไว้ใน working tree
