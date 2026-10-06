# Session 002 — report bbox แบบโต้ตอบ: ชี้/คลิกกรอบแล้วเห็นข้อมูล (doc_99 + batch)

- **Session ID:** `2026-10-04-002`
- **Task:** `TASK-20261004-001` (ต่อจาก session 001)
- **Change:** `CHG-20261004-002`
- **Time:** 2026-10-04T16:29:00+07:00 → 2026-10-04T17:00:00+07:00
- **Agent:** Pi Agent
- **User direction:** *"@out/doc_99/report.html ฉันต้องการให้แสดงข้อมูลเมื่อเอาเมาส์ชี้หรือคลิกไปยัง bbox"* (พร้อมคำสั่งต่อเนื่อง: ทำให้ bbox ทุกอันชี้แล้วเห็นข้อความ, และทำต่อที่เหลือให้เสร็จ)

## Objective
ทำให้รายงานผล OCR เป็นเครื่องมือตรวจงานได้จริง: ตอนชี้เมาส์หรือคลิกที่กรอบ (bbox) ต้องเห็นข้อความของกรอบนั้น
โดยไม่ต้องไล่เทียบกับตารางเอาด้วยตา

## Why เดิมทำไม่ได้
ภาพ `page_N.png` / `page_N.jpg` ถูกวาดกรอบด้วย PIL (Pillow) → กรอบ "เผา" อยู่ในไฟล์ภาพ ส่วนข้อมูล (type/label/text/bbox)
อยู่คนละที่ (ใน `<table>` / ใน `doc.json`) Browser จึงไม่มี hit-area ให้กรอบ และ `report.html` ของ batch ไม่เคยส่ง `bbox` มาให้ JS เลย
(`write_report()` ตัดเหลือแค่ `type/label/text`)

## Design (UI layer ล้วน — ไม่แตะ engine/OCR)
Overlay เป็น `<div class=bx>` ซ้อนบนภาพ ตำแหน่ง/ขนาดมาจาก `bbox_norm` `[x, y, w, h]` (0–1) ที่ `filter_items()` คำนวณไว้แล้ว
→ ไม่ต้องเรียก AI ใหม่, ไม่เปลี่ยนผล OCR, และ re-render รายงานของรอบเก่าได้ฟรี

| ปฏิบัติการ | ผลลัพธ์ |
|---|---|
| ชี้เมาส์ที่กรอบ | tooltip (สีตามประเภท) แสดง `type · label` / ข้อความเต็ม / `px [x1,y1,x2,y2] · norm [x,y,w,h]`, กล่องหนาสีเหลือง, แถวตารางที่ตรงกันไฮไลต์ |
| ชี้เมาส์ที่แถวตาราง | กล่องบนภาพที่ตรงกัน get `hot` (sync กลับกัน) |
| คลิกกรอบ หรือคลิกแถว | ตรึงข้อมูลลง panel ขวาล่าง + เลื่อนไปที่แถวที่ตรงกัน, ทั้งคู่ get `sel` (สีน้ำเงินประ) |
| คลิกซ้ำที่เดิม / `Esc` | ปลดสิ่งที่ตรึงไว้ |
| checkbox **กรอบโต้ตอบ** | ซ่อน overlay ทั้งหมด (`body.no-ov`) → คลิกที่ภาพเพื่อเปิดไฟล์ภาพเต็มได้เหมือนเดิม |
| เลื่อนจอ / ชี้พ้นกรอบ | tooltip ปิดอัตโนมัติ (กัน tooltip ค้างตอน layout เปลี่ยน) |

## Files changed
- `OCR service/new engine/tests/bbox_testv3.py` — template `REPORT_HTML` (CSS overlay + `#tip`/`#pin` + JS `itemOf/tipHtml/mark/moveTip/pinIt/unpin/idxOf` + delegation บน `document`), `docHtml()` สร้าง `boxes` + แถว `<tr data-i>`, `.pg` มี `data-d/data-p`, และ `write_report()` เพิ่ม `bbox_norm`,`bbox_px` เข้า payload
- `OCR service/new engine/tests/bbox_test.py` — เพิ่ม `REPORT_CSS`/`REPORT_JS`, `write_report()` สร้าง overlay + `DATA` ต่อหน้า, เพิ่ม `rebuild_report()` และ flag `--report-only` (สร้าง report จาก `page_*.json` เดิม ไม่เรียก AI/เน็ต, คงชื่อเดิมที่อ่านจาก `<h1>`), เพิ่ม `sys.stdout.reconfigure(utf-8)` ให้เหมือน v3 (เครื่องนี้ console เป็น cp874 — ดู `ERR-20261004-002`)

## Verification (DOM จริง ไม่ใช่แค่ syntax)
ไม่มี browser/headless ในเครื่อง (`playwright`/`selenium` ไม่มี) → ใช้ **jsdom** เขียน harness ที่ fake event จริง
`C:\Users\wajeepradit.p\bbox-verify\test-interact.js` (20 การตรวจ: overlay มี position จาก bbox, tooltip เปิด/ปิด,
ข้อมูลเปลี่ยนตามกรอบที่ชี้, sync box↔แถวสองทาง, คลิกตรึง + `sel`, `Esc` ปลด, toggle ซ่อนกรอบ, ชี้ภาพว่างแล้ว tooltip ปิด)

| เป้า | ผล |
|---|---|
| `OCR service/out/doc_99/report.html` (32 กรอบ) | **20/20 ผ่าน** |
| `new engine/tests/out/batch/report.html` (99 ฉบับ, overlay 15,111 กรอบ) | **20/20 ผ่าน** |
| `node --check` JS ที่ generate แล้ว | ผ่านทั้ง 2 ไฟล์ |
| harness เจาะเจอ | jsdom ไม่มี `Element.scrollIntoView` → ใส่ guard `if(t&&t.scrollIntoView)` (browser ปกติมี) |

## Re-render รายงานเก่า
รายงานที่สร้างก่อนการแก้ (รวมฉบับสุดท้ายของ batch ที่ process เก่าเขียนด้วย template ใน memory) ต้อง rebuild:
`python bbox_testv3.py --report-only` (ไม่เรียก AI) และต่อฉบับ `python bbox_test.py 99 --report-only`

## Batch run ปิดงาน (ผลจริง)
- รอบแรก `--workers 2`: **99/99 ฉบับ · 425 หน้า · 15,111 กรอบเก็บ · 51 ตัดทิ้ง · 99 ok / 0 partial · 0 doc error · 5,951 s (เฉลี่ย 24.7 s/หน้า)**
- fail เดียว: `doc 27 p9/11` → model ไม่ตอบ JSON (`no JSON / no items`) → ซ่อมด้วย `--retry-errors --workers 1` (ข้าม 98 ฉบับที่ ok แล้ว)

## Follow-up
- [ ] ถ้าจะให้ viewer.html (PDF.js) มี click-to-pin เหมือน report ให้ครบทุกจุด (ปัจจุบันมีแค่ hover tooltip)
- [ ] ขนาด `report.html` (3.2 MB ที่ 99 ฉบับ) โตขึ้นเพราะใส่ bbox ใน DATA — ถ้าจะขยายถึงหลักพันฉบับควรวาง plan โหลด per-doc
- [ ] `out/batch/` + `run_v3*.log` + `new engine/` ทั้งโฟลเดอร์ยัง untrack ทั้งหมด → ต้องตัดสินใจก่อน commit ว่าจะเก็บ output ไว้ใน git หรือ ignore
