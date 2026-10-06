# Session 2026-10-06-003 — Portal: ตอบคำถาม "ใช้งานได้หรือยัง" ด้วยหลักฐานสามชั้น แล้วเจอว่า panel พูดความจริงไม่หมด

- วันที่: `2026-10-06T08:51:00+07:00`
- งาน: ตอบคำถามของ user ว่า web portal สำหรับทดสอบใช้งานได้หรือยัง — ด้วยของจริง ไม่ใช่ด้วยบันทึกเก่า
- Commit: `d5ad5c3` — 5 ไฟล์ ทั้งหมดอยู่ใต้ `system-a/web/` · **ไม่มี `src/system_a/**` และ `config/**`**
- งาน/บันทึก: `TASK-20261006-003` · `CHG-20261006-003` · `ERR-20261006-004` · DEC-021

## 1. วิธีตอบ

ไม่ตอบจากความจำว่า "รอบก่อน 27/27 ผ่าน" แต่เรียงหลักฐานจากถูกออกสู่แพง และรันบนของจริงทั้งหมด:

1. `python -m pytest web/test_portal.py -q` → **31/31** (offline, engine ถูก fake)
2. เปิด server จริง `python web/serve.py --port 8080 --no-browser` + `python web/check_live.py`
   → **77/77** (asset ทุกไฟล์ที่ page เรียก, catalog, verification จริงผ่าน subprocess, geometry, upload, failure path)
3. `node web/test_ui_logic.mjs` ชี้ไปที่ fixture ที่ build จาก **API จริง** ของ DMS-20 (`/api/results` +
   `/api/overlays`) → **fail 3 รายการ**

ชั้นที่สามคือชั้นที่จ่ายงาน เพราะมันคือชั้นเดียวที่ไม่เคยถูกชนด้วยข้อมูลอื่นนอกจากเอกสารที่มันเกิดมา

## 2. แยก false failure ออกจากของจริง

false 8 รายการ (DMS-20: 3, DMS-25: 5, DMS-36: 1, DMS-99: 5) มาจาก harness ที่โตมากับเอกสารเดียว:
element id, `26/2691`, `PCS`, `E01`, verdict `/REVIEW/` และขนาดหน้า `595×842` ถูกเขียนเป็น literal ใน assert

- DMS-25 / DMS-99 — field ทั้ง 12 ตัวอยู่ **หน้า 2** เพราะหน้า 1 เป็นใบปะหน้า (`by_type` ไม่มี box หน้า 1)
  harness ที่ถามหา "field box บนหน้า 1" จึงพลาด + selection/layer test พังตามกัน
- DMS-36 — หน้า 1 เป็น **landscape 842×595** การคำนวณ pixel ที่ hardcode 595/842 จึงผิดทั้งหมดยกเว้นกรณี A4

ของจริงเหลือ 1 ตัว และมันไม่ใช่เรื่องเล่น: exception panel ของ DMS-20 ขึ้น E03 "Total Mismatch" ด้วย
`actual 49215.00` / `expected 49215.00` — **ตัวเลขเท่ากัน** เพราะค่าสองตัวนี้ถูก copy มาจาก `evidence[]`
ซึ่งเป็น *คู่ที่ตรงกัน* ส่วนผลต่างที่ทำให้กฎ fail อยู่ใน `rule_results[V-03].data.diffs`:
`sub_plus_vat_vs_grand = 3445.05` ไม่เคยถูกแสดงที่ไหนเลย คนตรวจรับเอกสารจึงเห็นตัวเลขที่ไม่อธิบายอะไร
(อาการเดียวกับที่ DEC-017 แก้ให้ error ของ Paperless)

## 3. สิ่งที่แก้ (ฝั่ง portal ล้วน — ไม่แตะ contract ตาม DEC-013)

- `app.py::build_overlays()` เพิ่ม `exceptions[].diffs` = เฉพาะ entry ที่ **ไม่เป็นศูนย์** จาก
  `data.diffs` ของ rule ที่ exception นั้นอ้าง (match rule_id แบบไม่สนตัวพิมพ์)
- `panels.js` เพิ่ม `exceptionValues()` + เปลี่ยนหัวคอลัมน์เป็น "What differs": แสดง sums ที่ต่างเมื่อคู่
  actual/expected เงียบ (null หรือเท่ากัน) และยังคงคู่เดิมไว้บน payload ไม่ได้คิดเลขเองสักตัว
- `test_ui_logic.mjs` derive ความคาดหวังจาก payload ที่ถูกทดสอบ: เลือกหน้าที่มี field box (prefer หน้าที่มี
  exception box ด้วย), ดึง `W/H` จาก `pages[]`, เทียบ label จาก **หัว** ค่า (label ตัดทอนโดยเจตนา) และ
  assert รายกฎ/ราย field แทน regex กลางๆ
- pytest ใหม่ `test_an_exception_carries_the_sum_that_actually_differs`: diffs กรองศูนย์, ค่าเดิมของ rule
  ที่ไม่มี diffs ไม่เปลี่ยน, คู่ actual/expected เดิมยังอยู่ครบ

## 4. ผลตรวจจริง

| ชั้น | ก่อน | หลัง |
|---|---|---|
| pytest | 31/31 | **32/32** |
| live checker (portal รันอยู่) | 77/77 | **77/77** |
| browser modules | "27/27" บนเอกสารเดียว | ผ่านบนเอกสารจริง **5/5** (DMS-20/25/36/99/114) |

หลักฐานว่า panel พูดจริง: `/api/overlays/DMS-20` → `E03 diffs = {"sub_plus_vat_vs_grand": "3445.05"}`
ส่วน `actual_value/expected_value` ยังเป็น `49215.00` ทั้งคู่ตาม contract

## 5. คำตอบที่ให้ user และสิ่งที่ยังไม่เคลม

**ใช้งานได้** — ค้น/เปิด/อัปโหลด/Verify/ดู overlay + cross-highlight ได้จริง และ failure path ทุกเส้นที่
แตะได้ตอบเป็นภาษาคน สิ่งที่ยัง **ไม่** เคลม: layout/CSS บน browser จริง (harness เป็น stub DOM ไม่ใช่
การจัดวาง) และการยืนยัน AUTO_PASS ยังติด V-05/BLOCKER-01 ที่เป็นคนละงานกับ portal
