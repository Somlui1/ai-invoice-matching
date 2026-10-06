# Session 2026-10-05-004 — Web Testing Portal สำหรับ System A (Phases 1–5)

- วันที่: `2026-10-05T23:55:00+07:00`
- งาน: `TASK_WEB_TEST_PORTAL.md` — portal ทดสอบ System A แบบโต้ตอบ (browse Paperless → รัน verification → แสดง bbox overlay + cross-highlighting)
- Commit: `2d87f6e` (20 ไฟล์, +3,673 บรรทัด) ทับ `64152ea` — **ไม่มีไฟล์ใน `src/system_a/**` และ `config/**` เลย**
- สถานะ: ครบทั้ง 5 phase, test ผ่าน 24/24 (pytest) + UI logic 25 checks, ทดสอบเทียบ CLI จริงแล้ว

## 1. สิ่งที่สร้าง (`system-a/web/`)

| ไฟล์ | หน้าที่ |
|---|---|
| `engine.py` | สะพานไปหา CLI: รัน `process_pdf.py` เป็น subprocess, parse stdout จริงเป็น step event, SSE queue, run registry (ลอคต่อเอกสาร + `WEB_MAX_CONCURRENT`, cancel, timeout), result store, audit log, และ **interpreter probe** สำหรับ process engine |
| `catalog.py` | Paperless search/paging, ดาวน์โหลด PDF (cache), เรนเดอร์หน้าด้วย PyMuPDF + sidecar ตรวจความเก่า, deep health (Paperless / LiteLLM / Oracle probe / engine) |
| `app.py` | REST + SSE endpoints และ `build_overlays()` แปลง Contract 3.0 evidence plane เป็น layer ต่อหน้า |
| `serve.py`, `run_portal.bat` | ตัวเปิด server (เลือก interpreter อัตโนมัติ) และ launcher 2 วิธียังเครื่อง Windows |
| `static/` | UI ไม่มี build step: `api.js`, `viewer.js`, `bbox-overlay.js`, `interaction.js`, `panels.js`, `app.js` |
| `test_portal.py`, `test_ui_logic.mjs` | test 24 รายการ (offline ทั้งหมด) + รัน JS module จริงกับ DOM ปลอม |
| `README.md` | วิธีรัน, env, endpoint, วิธีที่ bbox มาจาก contract, troubleshooting |

หลักการออกแบบที่สำคัญ: portal เป็น **consumer ของ CLI เท่านั้น** (subprocess ไม่ใช่ import) —
verification logic, prompt และ Standard v6.6 ไม่ถูกแตะ และผลของ portal ต้องตรงกับผลของ CLI ทุกประการ

## 2. หลักฐานการทดสอบ

- `python -m pytest web/test_portal.py -q` → **24 passed** (faked subprocess, redirect ทุก path ไป tmp; ครอบคลุม argv ที่ส่งให้ `process_pdf.py`, step markers จริง, contract→overlay join, coordinate passthrough, 409/CAP/cancel, upload, raster cache, เวลา dependency ล่ม, JS↔HTML id)
- `node web/test_ui_logic.mjs` → **all checks passed** (25 checks): panels เติมข้อมูลจาก overlay schema ได้จริง, join สองทางผ่าน `element_id`, `.sel/.dim`, และ toCss ถูกตาม `coordinate_system` (normalized / point+corner+bottom-left / pixel)
- **เทียบ CLI จริง (DMS-20, sandbox)**: portal 1.0 s vs CLI 1.0 s — ต่างกันแค่ timestamp + `correlation_id`; `integrity.payload_sha256` ตรงกัน (`sha256:399a3584…3dbf`) = portal ไม่เปลี่ยนผลการตรวจสอบ
- overlay บนข้อมูลจริง DMS-20: elements 2,589 · fields มีกรอบ 12/13 (อีก 1 คือ field ที่ไม่มีค่าจริง) · cells 30/30 · exception boxes 5 (E03, E05) · rows 6/6 · signatures 2/2
- live: `/api/documents` = 99 ฉบับ, SSE stream มี step ครบ `start→perception→perception_cached→oracle→assemble→summary` + log + `result`

## 3. ข้อค้นพบระหว่างทาง (บันทึกเป็น ERR ไว้)

1. **`normalized_fields` เป็น map แบบ name→string เท่านั้น** ไม่ใช่วัตถุ field — endpoint overlay พัง 500 เพราะอ่าน `.get()` บน string ที่อยู่จริงคือ `extraction.fields[name]` (`raw_value`/`normalized_value`/`ok`/`null_reason`/`element_id`) และการจะหา "ค่านี้มาจากตรงไหน" ต้องทำบน **evidence plane** (`ocr.elements[]` หาจาก `element_id`, exceptions หาจาก `evidence[].related_element_ids`) — **ERR-20261005-005**
2. **cell ใน `extraction.lines[].cells` ไม่มี `element_id`** — join ได้จาก `field_name` ของ contract เอง (`lines[<n>].<column>`) ซึ่งเป็น key ระดับข้อมูล ไม่ใช่ geometry บนจอ ผล: DMS-20 cell มีกรอบครบ 30/30, DMS-36 8/10 (อีก 2 คือ `NOT_PRESENT` ซึ่งไม่มีกรอบให้ชี้ — ถูกต้องแล้ว)
3. **API กับ viewer อ่าน key คนละชื่อ** (`id` vs `element_id`, `raw_value` vs `raw`) — field/cell box จะคลิกไม่ติดโดยไม่มี error ใดๆ ใน browser จับได้ด้วย stub-DOM harness เท่านั้น **ERR-20261005-006**
4. **`--quick` ไม่ใช่โหมดเร็ว** — `process_pdf.py:132` ตั้ง `do_crops=False, do_table=False` ทำให้ perception คนละชุด (cache key คนละตัว ใช้ซ้ำไม่ได้ ช้ากว่านิดหน่อย และได้ verdict คนละแบบ: DMS-20 `--quick` → SYSTEM_ERROR) UI จึงระบุตรงๆ ว่าเป็นคนละการรัน ไม่ใช่ทางลัด
5. **หลาย Python บนเครื่องเดียวกัน** — interpreter ที่ portal รัน (ต้องมี fastapi/uvicorn/httpx) กับที่ engine รัน (ต้องมี yaml/pydantic/pymupdf) มักคนละตัว; `.venv` 3.14 ไม่มี yaml → subprocess ตายทันที จึงเปลี่ยนเป็น "probe ด้วยการ import จริง" แทนการเดา path และโชว์ผลลัพธ์ใน health
6. **PDF.js เป็น ES module** — `<script type="module" src>` ไม่สร้าง global จึงต้อง import แล้วแนบ `globalThis.pdfjsLib` เอง และ vendor ไว้ same-origin (`static/vendor/pdfjs`, pdfjs-dist 4.10.38, Apache-2.0) เพราะ intranet เข้า CDN ไม่ได้

## 4. ข้อจำกัดที่ยังเหลือ

- ยังไม่ได้ลองคลิกจริงบน browser (harness ครอบคลุมเฉพาะ logic/DOM-level ไม่ใช่การจัดวาง CSS)
- overlay ใช้ raster เป็นโหมดหลัก; vector (PDF.js) ยังไม่ถูกใช้จริงในการทดสอบ
- ผล sandbox ของเอกสารที่ไม่มี Oracle stub จะต่างจาก production ตามที่โหมดกำหนด (portal ไม่ได้ทำให้เหมือนกัน)

## 5. ตัดสินใจ (see `.agent/decisions.md`)

- **DEC-013** portal เป็น subprocess consumer ของ `process_pdf.py` เท่านั้น ห้าม import `system_a` เพื่อตัดสินใจ
- **DEC-014** ห้าม assume พิกัด — อ่าน `coordinate_system` จากผลจริงทุกครั้งที่ render และ map cell ผ่าน `field_name` ของ contract
- **DEC-015** vendor PDF.js ลง repo (same-origin) เพราะงานต้องรันได้บน intranet; ถ้าไฟล์หาย UI ยังทำงานใน raster mode
