# Session 2026-10-06-001 — Portal: ปิดงานที่ค้าง, ทำให้ failure อ่านได้จริง และซ่อมตัวตรวจที่ไม่มีใครรัน

- วันที่: `2026-10-06T08:25:00+07:00`
- งาน: ต่องาน Web Testing Portal ที่ค้างอยู่ใน working tree (รอบก่อนเขียนไว้ครึ่งทางยังไม่ commit)
- Commit: `5a058e0` — 7 ไฟล์ ทั้งหมดอยู่ใต้ `system-a/web/` · **ไม่มี `src/system_a/**` และ `config/**`**
- งาน/บันทึก: `TASK-20261006-001` · `CHG-20261006-001` · `ERR-20261006-001/002`

## 1. จุดเริ่มต้น

รอบก่อน (`2d87f6e` + `fec7451`) ทิ้ง diff ที่ยังไม่ commit ไว้สองเรื่อง: `/api/verify/upload` ถูก route
`/api/verify/{doc_id}` กลืน และ error ทั้งหมดของ Paperless-ngx ถูกตอบเป็น `502 cannot fetch` เหมือนกันหมด
รอบนี้จึงไม่ใช่การเขียนใหม่ แต่คือ **ทำให้จบ + พิสูจน์บนของจริง**

## 2. สิ่งที่แก้

**(ก) Route order —บั๊กที่ทำให้งานหนึ่งตายทั้งงานโดยไม่มีอาการ**
Starlette ตอบ route แรกที่ pattern ตรงกัน `"/api/verify/{doc_id}"` จึงกิน literal `upload` ด้วย
ผลคืออัปโหลดสำเร็จ (`/api/upload` คนละ path) ภาพหน้า PDF ก็เปิดได้ แต่ Verify ได้ `422` และไม่มี
สัญญาณอะไรชี้ไปที่ "ลำดับการเขียน decorator" → ย้าย literal route ขึ้นก่อน + คอมเมนต์ `ORDER MATTERS`
+ regression test ที่เดินทั้งเส้น (อัปโหลด PDF ปลอม → verify → assert 200 + SSE มี contract)

**(ข) Failure จาก DMS ต้องอ่านได้ที่ตา**
`_upstream_error()` แปลง exception ของ reader เป็นสถานะที่ browser ควรใช้ พร้อมประโยคเดียวต่อกรณี
(ตรวจสอบแล้วว่า pattern ที่ match เป็นข้อความจริงจาก `src/system_a/adapters/paperless/reader.py`:
`PAPERLESS_AUTH` สำหรับ 401/403, `PAPERLESS_TRANSPORT` คือสิ่งที่ 404 ถูกห่อมา)

| กรณี | เดิม | ตอนนี้ |
|---|---|---|
| id เก่า / เอกสารถูกลบหลังโหลด list | `502 cannot fetch` | `404 DMS-<id> is not in Paperless-ngx` |
| token ถูกปฏิเสธ | `502 cannot fetch` | `502 Paperless-ngx rejected this token - check PAPERLESS_API_TOKEN` |
| ไม่ได้ตั้งค่า DMS | `502 cannot fetch` | `503 Paperless-ngx is not configured on this machine` |
| timeout / 5xx | `502 cannot fetch` | `502 cannot fetch DMS-<id>: …` (คงเดิม) |

ฝั่ง browser: `api.js` ดึง `detail` จาก body มาแสดง (จากเดิม toast เต็มไปด้วย `{"detail":"…"}`),
และ `viewer.js` ไม่ยอมให้ `<img>` ที่โหลดไม่ออกจบแบบเงียบอีกต่อไป — มันถาม endpoint กลับไปดูสาเหตุ
ถ้า endpoint ยังให้ภาพได้ ก็บอกตรงๆ ว่า "browser ไม่วาด ลอง reload" แทนที่จะอ้างสาเหตุที่ไม่มีอยู่

**(ค) `web/check_live.py` — ตัวตรวจที่ไม่เคยผ่านเพราะไม่มีใครเคยรันมัน**
เปิด portal จริง (port 8080) เพื่อรัน checker ตามแผน แล้วพบว่าไฟล์นี้ไม่เคยใช้ได้จริง:

1. `NameError: name 'Path' is not defined` ที่บรรทัดรายงาน health → จบตั้งแต่ยังไม่เริ่มตรวจ
2. `json.loads(body)` 12 จุดตายทันทีที่ body ไม่ใช่ JSON (portal กำลัง restart / proxy ตอบ HTML)
   ทำให้ checker กลายเป็น traceback แทนที่จะรายงาน FAIL ที่อ่านได้
3. `any(e.get("ok") for e in ev if "done" in e)` — event จริงคือ `{"type":"done","ok":...}` ไม่มี key
   ชื่อ `done` → check "uploaded PDF verifies end to end" **ไม่มีวันเขียว** ไม่ว่าจะดีแค่ไหน

แก้ทั้งสาม (`pathlib.Path`, `jload()` คืน `{}` เมื่อ parse ไม่สำเร็จ, ABORT เมื่อ catalog ว่าง,
กรอง event ด้วย `e.get("type") == "done"` + แสดง `exit_code`) และกันถอยหลังด้วย pytest ที่รัน checker
ชน `http://127.0.0.1:9` — connection refused ทำให้ทุก request คืน error แต่โค้ดทั้งก้อนยังถูกรัน
จึงจับ NameError แบบนี้ได้ใน ~1 วินาทีใน offline suite

## 3. ผลทดสอบจริง

| ชุดทดสอบ | ผล |
|---|---|
| `python -m pytest web/test_portal.py -q` | **31 passed** (เดิม 26 → เพิ่ม 5) |
| `node web/test_ui_logic.mjs <fresh fixture>` | **all checks passed (27)** — เพิ่ม 2 ตัวที่ครอบ failure path |
| `python web/check_live.py` (portal จริง, DMS-114 sandbox) | **77 checks passed · 0 failed** |
| `python web/check_live.py --base http://127.0.0.1:9` | ไม่มี traceback · รายงาน `ABORT ... not answerable from this machine` |

หลักฐานจาก live run: `POST /api/verify/upload?key=UP-DMS-114-…&mode=sandbox` → HTTP 200 + `done`
exit 0 · `/api/documents/999999/pdf` → `404 {"detail":"DMS-999999 is not in Paperless-ngx"}` ·
sandbox verification ของ DMS-114 ผ่าน perception cache (steps ครบ `start→perception_cached→oracle→
assemble→summary`), verdict `REVIEW`, log 28 บรรทัดมี level ทุกบรรทัด ไม่มี ANSI escape

## 4. บทเรียนที่บันทึกไว้

- **ERR-20261006-001**: framework แบบ first-match-wins ต้องมี test ที่ชน literal path ที่ชนกับ parameter
  name เพราะ type check fail ล่าช้า (ตอน parse) ไม่ใช่ตอนหา route
- **ERR-20261006-002**: tool ที่เขียนไว้ใช้ "ตอนระบบพัง" คือไฟล์ที่ไม่มีใครทดสอบตอนระบบปกติ — ต้องมี
  offline test ที่รันมันตอนระบบ **ไม่อยู่** และ tool ตรวจสอบงานต้องถูก commit พร้อมงาน ไม่ใช่ค้างใน working tree
- ของที่ยังไม่ได้ทำ: การคลิกทดสอบโดยคนจริงบน browser (harness ครอบ logic/DOM ไม่ได้ครอบการจัดวาง CSS)

## 5. สิ่งนี้ปลดล็อกงานถัดไปอย่างไร

TASK-V01-00 (หน่วยนับ 238 cell ที่อ่านไม่เจอ + reader เดียวบน cell ที่มั่นใจต่ำ) ต้องดูว่า "ค่าที่ engine
ได้" ต่างจาก "สิ่งที่อยู่บนกระดาษ" ตรงไหน — ตอนนี้เปิดเอกสารจริง รัน engine ผ่าน portal แล้วชี้ดูทีละ
cell บนภาพที่ model ถูกให้เห็นได้ทันที และถ้า portal พังระหว่างทางก็จะได้ประโยคที่อ่านเป็นสาเหตุ ไม่ใช่ภาพเสีย
