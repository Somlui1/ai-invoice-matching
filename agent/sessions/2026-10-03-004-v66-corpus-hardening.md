# Session 004 — Standard v6.6 Synthetic Corpus เป็น Benchmark ที่เชื่อได้จริง

- **Session ID:** `2026-10-03-004`
- **Task:** `TASK-20261003-006` (root) / `TASK-014` (service)
- **Change:** `CHG-20261003-004` (root) / `CHG-20261003-006` (service)
- **Error record:** `ERR-20261003-004` (root) / `ERR-20261003-004..006` (service)
- **Time:** 2026-10-03T13:50:00+07:00 → 2026-10-03T14:35:00+07:00
- **Agent:** Pi Agent

## Objective
corpus v6.6 (100 cases + 100 PDFs) ถูกรายงานว่าเสร็จ แต่ถูกใช้เป็น answer key ไม่ได้จนกว่าจะพิสูจน์ว่า: ทุก expectation มาจาก engine จริง, ทุก PDF ตรงกับ payload, ทุกตัวเลข realism วัดจากของจริง และ suite ถูกเรียกจาก runner จริง

## Findings (จาก audit ก่อนแก้)
1. `pytest tests/test_corpus_v66.py` = **14 failed / 199 passed** และ `tests/run_tests.py --all` ไม่เคยเรียก suite นี้ → "green" ที่ถูกอ่านว่าเขียวมาจากการนับ suite ไม่ครบ
2. multi-PO 36 เคสใช้เลขที่ใบรับ `RCV-CONSOLIDATED-*` ที่ **ประกอบขึ้นเอง** (รวม 2 ใบรับเป็นเลขเดียว) → expectation ที่ engine คำนวณต่อ ไม่ได้สะท้อน ERP จริง จึงรื้อทิ้ง
3. ตัวเลข realism (`splits 25`, `fuzzy 40`) ไม่มีที่ไหนวัดจริง — เป็นเป้าที่เขียนลงในรายงาน
4. ช่องว่างจริงของ engine: Gate 2 ไม่ตั้ง `halted_by` (Gate 1 ตั้ง `V-02`) → corpus fail ถูกแล้ว
5. test bug: assertion นับกล่องลายเซ็นค้นหา needle ที่มีช่องว่างใน text ที่ collapse แล้ว → ได้ 0 เสมอ (12 false failures)

## Actions
1. `app/core/rules.py`: `gate_halt_reason()` → `halted_by` = `V-02` / `V-04` / `V-05`; ไม่แตะผลของกฎ
2. `extract_oracle_snapshot.py`: เก็บใบรับที่ **หลาย PO จริง** จาก Oracle (28 ใบ, projection rcv_v01 ของ production + `parse_csv_receipts()`) → snapshot v1.1 = 170 scenarios / 653 rows
3. `build_dataset_v66.py`: weave multi-PO 26 + lot split 16 slots แบบ deterministic + fail-fast guard (`min_rows`, raise เมื่อตำแหน่ง defect เกินจำนวนแถว, ล็อก mutation ที่ calibrate ด้วยมูลค่า, pool multi ต้อง FULLY RECEIVED) + `meta.realism` วัดจากเคสจริง
4. `generate_pdfs_v66.py`: ไม่พิมพ์ `None` ในกล่องยอดรวม; `po_display()` พิมพ์ PO ครบทุกเลขเมื่อเอกสารพาดผ่านหลาย PO
5. `tests/test_corpus_v66.py`: ปิด test bug, เพิ่ม assert (measured realism, multi-PO ต้องพิมพ์ PO ≥2, two-hop ไม่มี Tax ID ผู้ขาย, gate ต้องไม่เข้า matcher, Reject ใช้ breaker = parser)
6. `tests/run_tests.py`: เพิ่ม v6.6 tier ใน `corpus`/`all`; `verify_dataset.py --fix` recalibrate answer key เก่า (9 เคสเฉพาะ `halted_by`)
7. เอกสาร: `n8n_flow_v6_6.md` + `parity_spec_matrix.md` sync `halted_by` contract และเปิด Known delta 4 (canvas ยังส่ง `null` ที่ `N8.1`)

## Verification
| Command | Result |
|---|---|
| `tests/test_invoices/extract_oracle_snapshot.py` | 170 scenarios / 653 rows (multi-po 29) |
| `tests/test_invoices/build_dataset_v66.py` | 35/30/30/5 · re-derived 100/100 · never raised: E11, E13 |
| `tests/test_invoices/generate_pdfs_v66.py` | 100/100 PDFs |
| `pytest tests/test_corpus_v66.py -q` | **215 passed** |
| `tests/run_tests.py --all` | **SUCCESS (ALL PASSED)** · 30.99s · 4 tiers |

Measured realism: suppliers 20 · multi-PO 34 · two-hop 5 · split/lot 17 · intercompany 4 · fuzzy 99 · weight 13 (ทุก quota ผ่านด้วยข้อมูล ไม่ใช่ด้วยคำอ้าง)

## Deliberately Not "Fixed"
- `E11`/`E13` ไม่ถูกยกใน engine → corpus ไม่ครอบและบันทึกเป็น documented gap (ไม่บิด matcher เพื่อเคสเดียว)
- intercompany = 4 (อีก 1 เคสถูก Gate 1 ตัดก่อนถึงขั้น flag ผู้ขายภายใน) — เป็นผลจากลำดับ gate ไม่ใช่บั๊ก
- Known delta 4 ของ canvas ยังเปิดอยู่ (ต้องแก้บน canvas ไม่ใช่ในเอกสาร)

## Remaining
- vision extraction จริง 100 PDF + per-field accuracy เทียบ answer key
- ตั้ง `halted_by="V-04"` ที่ `N8.1` true branch
- commit งานนี้แยกจาก WIP ของ TASK-012 (dataset/_raw/pdf เป็น gitignored build output)
