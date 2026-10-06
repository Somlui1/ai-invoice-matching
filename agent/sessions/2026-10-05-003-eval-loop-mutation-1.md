# Session 2026-10-05-003 — Evaluation Loop, Iteration 1 (measurement harness + 3 mutations)

- **Date:** 2026-10-05T23:15:00+07:00
- **Scope:** `OCR service/system-a-sandbox` — `system-a/config/standards/v6.6/`, `system-a/src/system_a/adapters/llm/`, `system-a/src/system_a/perception/`, `.agent/`
- **Objective:** ดำเนิน Autonomous Self-Improving Evaluation Loop รอบที่ 1 ตาม `task.md` — ตั้ง baseline จริงของ 99 ใบแจ้งหนี้, วินิจฉัย error cluster ด้วยหลักฐาน, และทดลอง mutation ที่เล็กที่สุดพร้อม gate ที่ตรวจซ้ำได้ โดยไม่แตะ Standard v6.6 (`policy.yaml`, `codes.yaml`, `rules.yaml`)

## 1. โครงสร้างการวัดที่เพิ่ม (measurement infrastructure)

การรันเต็มรูปแบบต่อเอกสารใช้เวลา 1–3 นาที (VLM + Oracle + LLM) และมีความไม่แน่นอนของโมเดล จึงสร้าง

| สคริปต์ | ใช้ทำอะไร |
| :--- | :--- |
| `.agent/harness/replay.py` | เอา perception ที่ cache ไว้ของ 99 ฉบับ (pin ที่ `PKG-2026-10-05-full-<id>`) แล้วรัน normalize → Oracle → V-01..V-09 → recommendation ผ่านโค้ด production จริง (`validate()`) ตัดเฉพาะ vision ออก |
| `.agent/harness/step1_scan.py` | สรุปรายการที่ V-01 ตก (ระดับ element) ของทั้ง 99 ฉบับโดยไม่ใช้ LLM/Oracle |
| `.agent/harness/fleet_report.py` | ภาพรวม distribution + หลักฐาน UOM/ORG_ID + `--compare` เทียบ regression |
| `.agent/harness/uom_diff.py` | คำนวณผลของ `uom_groups.yaml` กับ V-07 ใหม่จาก AI groups ที่เก็บไว้ในรายงาน → ได้ตัวเลขที่ **ไม่มี noise ของโมเดลเลย** |
| `.agent/harness/v05_predict.py` | คำนวณผลของตารางลูกค้า (Table 4) กับ V-05 ของทุกเอกสารจากข้อมูลในรายงานเดิม |
| `.agent/harness/oracle_probe.py` | query ERP แบบ read-only เพื่อหาหลักฐาน (รายการ ORG_ID, PO→ORG_ID) |
| `.agent/harness/vlm_probe.py` | ยิง request เดียวกับ perception แล้ว dump raw message object เพื่อดูว่า JSON หายไปไหน |
| `.agent/harness/test_salvage.py` | unit test 12 เคสของการกู้ JSON ที่ถูกตัดจบ (ผ่าน 12/12) |

การตรวจสอบความเที่ยงของ harness: รัน `process_pdf.py --dms-id 20` เต็มรูปแบบ (42.4 วินาที, log ขึ้น
`Reusing cached OCR perception result`) แล้วเทียบระดับ exception code กับผลจาก replay — ตรงกันทุก code

## 2. Baseline ที่วัดได้จริง (`full_r0`, 99/99 documents, config เดิมก่อนแก้)

- AUTO_PASS **0** · MANUAL_REVIEW 71 (71.7%) · REVIEW 14 (14.1%) · HOLD 13 (13.1%) · SYSTEM_ERROR 1
  — ตรงกับการรันรอบสดที่บันทึกไว้ก่อนหน้าทุกตัว จึงยืนยันว่า harness replay เที่ยง
- **V-01 fail 99/99** (E01 ทุกฉบับ) ทำให้ไม่มีเส้นทางไปถึง AUTO_PASS เลย
- V-05: `manual_review` 63 + `not_evaluated` 36 (ไม่มีผ่านสักฉบับ) · V-07 fail 63 · V-08 fail 3 / manual_review 57 / pass 3
- Exception (จำนวนเอกสาร): E01 99, E10 55, E13 33, E03 25, E11 11, E09 8, E05 7, E02 6, E14 2, E15 1
- หน่วยนับของเส้นบิลทั้ง 608 เส้น: ใช้ได้ 202 (33.2%), `NOT_PRESENT` 238 (39.1%), `LOW_CONFIDENCE` 168 (27.6%)
- รายงานต่อฉบับเก็บที่ `.agent/eval/full_r0/` ใช้เป็น regression anchor ถาวร

## 3. การวินิจฉัยที่เปลี่ยนทิศของ backlog (หลักฐานอยู่ใต้ `.agent/eval/`)

1. **V-01 คือคอขวดจริง** ไม่ใช่ backlog ตั้งต้นที่เขียนไว้:
   - `line.uom` **ไม่มี cell หน่วยนับเลย 238 บรรทัด** (การอ่านตารางไม่คืนคอลัมน์หน่วย)
   - `customer_name` conf ≤ 0.70 อยู่ 86/99 และ `customer_address` 82/99 เพราะอ่านด้วย reader เดียว
     (ทั้งที่ 91/99 ฉบับใช้ crop ครบ 12 ครั้งแล้ว — ปัญหาไม่ใช่ budgets แต่คือไม่มีผู้อ่านคนที่สอง)
   - `pages_complete=false` 21/99
2. **ต้นตอของ `pages_complete=false` เป็นข้อผิดพลาดทางเทคนิค ไม่ใช่ลักษณะเอกสาร**:
   `extra.page_errors` = `page_items: AIResponseError: no JSON object` 18 หน้า, `truncated JSON object` 3 หน้า
   และ probe จริงที่ DMS-20 หน้า 3 แสดงว่าโมเดลตอบแบบ **เปิด reasoning เป็น default**
   (`completion_tokens 5819` เป็น `reasoning_tokens 2577`) ขณะที่ `max_tokens = 8000` — หน้าที่มีข้อความหนาแน่น
   จะโดน thinking กินโควตาจน `content` ไม่มี JSON ครบ object
3. **E10 ที่คิดว่ามาจากหน่วยนับไทย 82% ไม่ใช่**: 42/51 findings มี `actual=None` (อ่านหน่วยไม่ได้) และ
   ของจริง 9 รายการเป็นข้ามกลุ่ม (`PCS` vs `JOB` ×7, `SET` vs `PCS`) ที่มาตรฐาน X-06 ห้าม map
4. **V-05 ไม่เคยผ่านได้เลย**: ตารางที่ 4 ของมาตรฐานลงทะเบียนด้วย organization_id ของ *sub-organization*
   (103, 175, 196 …) แต่ SQL ฝั่งใบรับ (RCV-V01) คืน `ph.ORG_ID` ซึ่งเป็น *operating unit* (101, 176, 195 …)
   — สองชุดนี้ไม่ทับกันเลย (ยืนยันจาก `APPS.HR_OPERATING_UNITS` และ `PO_HEADERS_ALL`)

## 4. Mutation ของรอบนี้ และผลที่วัดได้

### MUT-01 — `config/standards/v6.6/buyer_entity.yaml` (เขียนใหม่ทั้งไฟล์)
- ตารางที่ 4 จำนวน 28 แถวตามมาตรฐานต้นฉบับ + แถว bridge 12 รายการสำหรับ OU ที่ชื่อตรง 1:1 กับนิติบุคคล
  ในตาราง (101→103, 176→175, 195→196, 197→199, 243→244, 289→291, 309→310, 329→330, 349→350, 353→354,
  373→376, 413→433) และ 14 OU ที่กำกวม/ไม่มีข้อมูล ตั้ง `status: unknown` ตามที่มาตรฐานสั่ง
- ทุกแถว bridge เก็บ `table4_org_id` + `erp_ou_name` ไว้ตรวจสอบย้อนหลัง
- **ผล (`v05_predict.py` บน 83 ฉบับ):** `manual_review` จาก V-05 **53 → 0**, กลายเป็น `skip(V-01)` 51 ฉบับ
  (อ่านชื่อ/ที่อยู่ลูกค้าไม่ได้ — ให้ E01 เป็นผู้ตัดสินตามจริง), `pass/conditional` 2 ฉบับ,
  **ไม่มีเอกสารใดกลายเป็น E07 tax mismatch เลย** (DMS-25/DMS-68 คืออ่าน tax id ไม่ได้ ไม่ใช่ไม่ตรง)
- **ความเสี่ยงที่เป็นระบบ:** map ผิดแล้วเกิด E07 (Hold/Review ให้คนตรวจ) ไม่มีทางเกิด AUTO_PASS เท็จ
- **ไม่ใช้ข้อมูลจากใบแจ้งหนี้มาสร้างทะเบียนลูกค้า** เพราะจะกลายเป็นวนเวียน (V-05 ตรวจกับตัวเอง) — ปฏิเสธไว้

### MUT-02 — `config/standards/v6.6/uom_groups.yaml`
- เพิ่มกลุ่มคำพ้องความหมาย SET/BOX/PACK/ROLL/LOT/MTR/FRAME/CAN/DRUM และสมาชิก `ตัว, อัน, EA, EACH`
  อิงคลังคำหน่วยนับจริงทั้ง 32 รูปแบบจาก 99 ฉบับ (`.agent/eval/uom_inventory.md`)
- **ไม่แปลงข้ามกลุ่ม**: ตรวจ pairwise แล้วว่า `SET↔PCS`, `กล่อง↔CAN`, `FOOT↔MTR`, `ชิ้น↔SET` ยังไม่ตรงกัน
  และไม่มีคำใดซ้ำในสองกลุ่ม
- **ผล (`uom_diff.py` บน 51 ฉบับ):** E10 **70 → 68**, E10 ที่เกิดใหม่ **0**, E13 เท่าเดิม (58)
  — clear ที่ DMS-41 (`อัน` vs `Piece`) และ DMS-45 (`กระป๋อง` vs `Can`)

### MUT-03 — `adapters/llm/litellm_client.py` + `perception/vision_pipeline.py` (JSON decode fallback)
- เมื่อตอบไม่เป็น JSON: (1) attempt เดิม (2) ส่งซ้ำพร้อมปิด reasoning (3) กู้เฉพาะสมาชิก JSON ที่ครบถ้วน
- หน้าที่ใช้วิธีกู้ข้อมูลจะถูก **flag ว่าอ่านไม่ครบ** (`read.error = "page_items: truncated JSON answer, only complete members kept"`)
  เพื่อให้ `pages_complete` ยังเป็น false — ไม่เปลี่ยน failure เป็น pass โดยที่ข้อมูลอาจหาย
- เพิ่ม counter `decode_salvaged`, `no_thinking_retries` ใน stats และ unit test 12 เคสผ่านทั้งหมด
- **สถานะ: ผ่าน (ยืนยันด้วย Tier B) — รัน `process_pdf.py --dms-id 20` ใหม่ทั้ง perception ลง cache แยก
  `PERCEPTION_CACHE_DIR=../.agent/cache/perception-cand` (8 นาที) แล้วเทียบกับ baseline

  | จุดที่เทียบ | baseline (cache เดิม) | หลังแก้ (cache ใหม่) |
  | :--- | :--- | :--- |
  | หน้า 3 ของ `page_items` | `ok=false`, 106.5s, `no JSON object` | **`ok=true`, 39.9s** |
  | `page_errors` / `pages_complete` | `{3: ...}` / **false** | `{}` / **true** |
  | เส้นบิลที่ลงทะเบียน | 12 (ตารางซ้ำถูกนับเป็น 2 ชุด) | **6** (กฎกันตารางซ้ำทำงาน เพราะหน้า 3 อ่านออก) |
  | recommendation | MANUAL_REVIEW, max severity **High** | MANUAL_REVIEW, max severity **Medium** |
  | findings | E01 + E10×3 + E11×3 + **E13×6 (High)** = 13 รายการ | E01 + E10×6 = 7 รายการ |
  | V-05 | `manual_review` (ORG_ID ไม่อยู่ในตาราง) | `not_evaluated` (อ่าน Tax ID ลูกค้าไม่ได้) |

  E10 ที่เหลือทั้ง 6 เป็น `actual=None` ทั้งหมด คืออ่านคอลัมน์หน่วยนับไม่ได้ ไม่ใช่เรื่องพจนานุกรม
  และ V-06 เปลี่ยนเป็น `manual_review` (ความมั่นใจต่ำที่ `deliverer`) — เดิมกฎนี้ไม่ถึงเอกสารนี้
  เป็น flag จริงที่ตั้งขึ้นใหม่ ไม่ใช่ regression
- **Commit:** `64152ea`

## 5. Regression gate ของ MUT-01/MUT-02 (`full_r1` รันต่ออัตโนมัติ — 53/99 ฉบับตอนปิดรอบ)

- เอกสารที่มีทั้งสองรอบ 53 ฉบับ: unchanged 50 · improved **1** (DMS-25 `MANUAL_REVIEW → REVIEW`) ·
  **REGRESSED 2** (DMS-22, DMS-45 `MANUAL_REVIEW → HOLD`)
- V-05 เปลี่ยนจาก `manual_review` 9/23 ฉบับแรก (DMS-21 → `pass`, อีก 8 ฉบับ → `not_evaluated`
  เพราะอ่าน tax id/ชื่อลูกค้าไม่ได้จริง = ให้ E01 ตัดสินตามสภาพจริง)
- สอง regression ที่พบถูกตรวจก่อนปิดรอบ: `recommend()` ให้กรณี "กฎตอบ manual_review" มาก่อน severity
  ตอน V-05 ตอบ manual_review ทุกฉบับ จึงบัง High finding (E03/E09/E13) ไว้ใน bucket `MANUAL_REVIEW`
  พอเอาตัวบังออก เอกสารสองฉบับกลับเป็น `HOLD` ตาม Table 8 ที่ถูกต้อง → **ไม่ใช่ accuracy loss**
  และปฏิเสธการใส่ manual_review เท็จกลับเพื่อให้ตัวเลขดีขึ้น (DEC-012)
- findings บน subset เดียวกัน: E10 ลดลงตามที `uom_diff.py` ทำนายไว้ ส่วนต่าง E09/E11/E13 เล็กน้อย
  เป็นความไม่แน่นอนของ LLM จับคู่บรรทัด (perception ชุดเดิมทุกฉบับ) ไม่ใช่ผลของ config
- บทเรียนสำหรับ gate รอบถัดไป: `MANUAL_REVIEW → HOLD` ไม่ใช่ regression อัตโนมัติ และกลับกันก็ไม่ใช่
  improvement — `fleet_report.py` จะพิมพ์จำนวนกฎที่ตอบ `manual_review` ประกอบทุกครั้ง

## 6. สิ่งที่ไม่ได้ทำ (และบันทึกไว้กันคนลองซ้ำ)
- ไม่แตะค่า tolerance / เงื่อนไข rule / schema / archive
- ไม่ map ข้ามกลุ่มหน่วยนับ (X-06) แม้จะทำให้ E10 หายถึง 8 รายการ
- ไม่สร้าง Table 4 จากราคา/ข้อมูลบนใบแจ้งหนี้ (วนเวียน) และ ERP ก็ไม่มีสิทธิ์อ่าน `XLE_*`
- ไม่เพิ่ม `critical_crops` เพราะเอกสาร 91/99 ใช้ครบไปแล้ว — การเพิ่ม crop ไม่สร้างผู้อ่านคนที่สอง

## 7. สถานะค้างเมื่อจบรอบ
- `full_r1` ยังรันต่อถึง 99 ฉบับใน background (config หลัง MUT-01/02) — ปิดรอบด้วยตัวเลข 23 ฉบับแรก
  รัน `python .agent/harness/fleet_report.py full_r1 --compare full_r0` ซ้ำเมื่อจบเพื่อได้ gate ตัวเต็ม
- งานใหญ่ที่สุดของรอบถัดไปคือ TASK-V01-00 (perception) ตามหลักฐานว่า 66.7% ของเส้นบิลหน่วยนับใช้ไม่ได้:
  1. บังคับให้ `vision_table_rows.md` คืนคอลัมน์หน่วยนับทุกบรรทัด (เป้า 238 NOT_PRESENT)
  2. เพิ่มผู้อ่านคนที่สองของ cell ที่ความมั่นใจต่ำ (เป้า 168 LOW_CONFIDENCE + header name/address)
  ต้องใช้ Tier B เท่านั้น เพราะ replay ใช้ perception ชุดเดิม
- งานเจ้าของ: re-key ตารางที่ 4 ในมาตรฐาน §04 ให้มี operating-unit id (AERP)
- **คำแก้ไขรอบถัดไป (2026-10-06)**: ข้อสรุปที่ว่า perception cache key ไม่รวม `code_version` เป็นข้อสรุปที่ผิด
  key รวม fingerprint ของโค้ดอ่านภาพอยู่แล้ว (`opts["pipeline"] = pipe.code_version`) ที่เหลือคือไฟล์ cache
  ไม่ได้บันทึก code version ไว้ ดู ERR-20261005-004 ฉบับแก้ไข และ DEC-010 ถูกถอน (withdrawn)
