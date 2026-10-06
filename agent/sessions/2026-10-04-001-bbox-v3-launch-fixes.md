# Session 001 — ทำให้ `bbox_testv3.py` รัน batch ได้จริง + เริ่มรัน 99 ฉบับ (workers=2)

- **Session ID:** `2026-10-04-001`
- **Task:** `TASK-20261004-001` (root)
- **Change:** `CHG-20261004-001` (root)
- **Error records:** `ERR-20261004-001`, `ERR-20261004-002` (root)
- **Time:** 2026-10-04T15:12:00+07:00 → (batch run ยังทำงานค้าง)
- **Agent:** Pi Agent
- **User direction:** *"@new engine/tests/bbox_testv3.py start python bbox_batch.py --workers 2"*

## Objective
ผู้ใช้สั่งให้เริ่มรัน batch vision-OCR ของเอกสาร Paperless ทั้งหมดด้วย `--workers 2`
สคริปต์จริงคือ `OCR service/new engine/tests/bbox_testv3.py` (ชื่อใน docstring เขียนเป็น `bbox_batch.py` ซึ่งไม่มีอยู่จริง)
ก่อนยิง AI ได้ จึงต้องทำให้ไฟล์นี้ "รันได้จริง" ก่อน แล้วจึงเริ่มงาน batch

## Findings (ก่อนรัน มี blocker 3 อย่างที่ซ่อนอยู่)
1. **ไฟล์ถูกเขียนซ้ำเป็นสองสำเนา** — `bbox_testv3.py` มี 1,306 บรรทัด โดยบรรทัด 654–1306 เป็นเนื้อหาซ้ำกับ 1–653
   แบบ byte-identical (`diff` ของสองซีก = 0 บรรทัด) ผลคือ `if __name__ == "__main__": main()` มี **2 จุด**
   → การรันหนึ่งครั้งจะประมวลผลเอกสารทั้งชุดแล้วยิง AI ซ้ำอีกรอบ (เสียเวลา/โหลด GPU ฟรี ๆ และ report ถูกเขียนซ้ำ)
2. **ไฟล์ config ชื่อไม่ตรง** — สคริปต์เรียก `load_dotenv(<script>/.env)` แต่ใน `tests/` มีไฟล์ชื่อ `env` เท่านั้น
   (`bbox_test.py` มี fallback อ่าน `env` อยู่แล้ว, v2/v3 ไม่มี) → จะจบที่ `SystemExit: ยังไม่ได้ตั้งค่า LITELLM_KEY ...`
   ทั้งที่ `LITELLM_KEY` / `PAPERLESS_API_TOKEN` / `VLM_MODEL` ครบ
3. **console เป็น cp874** — รันครั้งแรก crash ทันทีที่ print บรรทัดแรก:
   `UnicodeEncodeError: 'charmap' codec can't encode character '\xb7'` (`encodings/cp874.py`)
   เพราะ log ทุกบรรทัดมี `·`, `✗`, `⚠` และภาษาไทย → batch ตายก่อนเริ่มงานแม้ config ผ่าน

## Actions (แก้ที่ตัวสคริปต์เท่านั้น — ไม่แตะ logic OCR)
1. ตัดสำเนาที่ซ้ำออก คงไว้ 653 บรรทัดแรก (ยืนยันด้วย `diff /tmp/c1.py /tmp/c2.py` = 0 บรรทัดก่อนลบ)
   → หลังแก้: 663 บรรทัด / 36,995 bytes, `grep -c __main__` = **1**
2. เพิ่ม fallback อ่านไฟล์ `env` ข้างสคริปต์ (รูปแบบเดียวกับ `bbox_test.py`) — **จงใจไม่สร้างไฟล์ `.env` ใหม่**
   เพื่อไม่เพิ่มสำเนา secret บน disk (ไม่ log ค่า token ใน record นี้ตามระเบียบ)
3. เพิ่ม `sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")` ตอนต้นโมดูล (ก่อน `print` ทุกจุด รวมถึง auto-install)
4. แก้ docstring ให้เป็นชื่อไฟล์จริง `bbox_testv3.py` และเพิ่มตัวเลือก `--retry-errors` ที่มีจริงใน argparse
5. ตรวจ: `python -m py_compile bbox_testv3.py` ผ่าน 3 ครั้ง (หลังแก้แต่ละชุด) และยืนยันว่าโหลด env ครบทุกคีย์
   (พิมพ์เฉพาะชื่อคีย์ + สถานะ set/MISSING ไม่พิมพ์ค่า)
6. เริ่ม batch: `PYTHONIOENCODING=utf-8 python -u bbox_testv3.py --workers 2 > run_v3.log 2>&1 &`
   จาก `OCR service/new engine/tests/` → output ที่ `new engine/tests/out/batch/`

## Batch run evidence (ผลจริงเมื่อจบรอบ 2026-10-04T16:55:51+07:00)
- Paperless count จริงจาก API `/api/documents/`: **99 ฉบับ** → `Paperless: 99 ฉบับ · ต้องทำ 99 · ข้าม 0 · workers=2` → `เสร็จ 99 ฉบับใน 5951s`
- **สรุป: 99/99 ฉบับ · 425 หน้า (ครบทุกหน้าของทุกไฟล์) · 15,111 กรอบที่เก็บ · 51 กรอบถูกตัดทิ้ง · 99 `ok` / 0 `partial` / 0 doc-level error · 5,951 s (~99 นาที)** เฉลี่ย 24.7 s/หน้า (max 191.6 s)
- `doc_type` ระดับหน้า: tax_invoice 237 · purchase_order 90 · delivery_note 48 · other 18 · osp 14 · invoice 12 · tax_invoice_receipt 6 (ไฟล์เดียว 11 หน้ามีหลายประเภทปนกัน เป็นเหตุผลที่ต้อง classify ต่อหน้า)
- กรอบที่เก็บได้: header 3,772 · other 2,771 · customer 1,827 · supplier 1,599 · total 1,496 · signature 1,363 · line 1,218 · table 539 · payment 278 · stamp 128
- เหตุผลที่ถูกตัด: `zero_area_or_out_of_page` 34 · `no_text` 11 · `duplicate` 6 → ยืนยันว่ากติกากรองทำงานจริงและเก็บไว้ตรวจย้อนได้
- fail เดียวของทั้งรอบ: `doc 27 p9/11` model ไม่ตอบ JSON (`no JSON / no items`) → ซ่อมด้วย `--retry-errors --workers 1` (ข้าม 98 ฉบับที่ ok แล้ว, 11 หน้า 210 s) → **สถานะสุดท้าย 99 `ok` / 0 `partial` / 0 page error และ 15,111 กรอบที่เก็บ**
- ไฟล์ที่ได้: `out/batch/report.html` (แบบโต้ตอบได้ — ดู session 002), `summary.csv` 99 แถว, `docs/doc_<id>/{original.pdf,page_N.jpg,doc.json,viewer.html}`

## Follow-up
- [x] batch ครบ 99 ฉบับ + เก็บตัวเลขสรุปจริง (หัวข้อ above) → ต่องานเป็น `CHG-20261004-002` / session `2026-10-04-002`
- [x] re-render report ให้เป็น template ใหม่ด้วย `--report-only` (ไม่ต้องเรียก AI ซ้ำ — see `ERR-20261004-003`)
- [ ] สุ่มตรวจ `report.html` เทียบต้นฉบับ PDF เพื่อวัด accuracy จริง — ตอนนี้เป็นหลักฐานว่า "ใช้งานได้ทั้งชุด" ยังไม่ใช่ตัวเลขความแม่น
- [ ] ตัดสินใจชื่อไฟล์ canonical: `bbox_testv3.py` vs `bbox_batch.py` (docstring/ชื่อไฟล์ไม่ตรงกันจนผู้ใช้สับสน) — ถ้าจะ rename ให้ย้ายทั้งโฟลเดอร์ `tests/` ให้อยู่กับ `app/`
- [ ] `new engine/` ทั้งโฟลเดอร์ยัง untrack; `out/batch/` + `run_v3*.log` เป็น build output → ตัดสินใจก่อน commit ว่าจะ ignore หรือเก็บ
