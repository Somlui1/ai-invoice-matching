# Current State

Last verified: `2026-10-05T23:55:00+07:00`

## Repository
- Branch: `main` — merge `origin/main` (6 commits: archive `invoice-web/` + mockup `invoice-web1`/`invoice-webV2`/`invoice-webv3` + skill) เข้ากับงาน n8n v6.6 ฝั่ง local เรียบร้อยแล้ว
- การย้าย `invoice-web/` → `Web portal/` ที่ทำค้างไว้ใน working tree **ถูกยกเลิกตามคำสั่งผู้ใช้** เพื่อรับ layout ของ `origin/main`; สำเนาก่อนทิ้งอยู่ที่ `git\wip-backup-20261003\` และ snapshot commit `backup/wip-dirty-20261003`
- Existing OCR service (`OCR service/n8n`) และ original HTML mockup (`Web portal/AIVA-Web-Portal-Mockup-v4.4-Release.html`) ยังคงอยู่ตามเดิม — ไม่มีการแก้ไฟล์ใน `OCR service/` ระหว่าง integrate
- Agent records ถูกจัดเก็บบน `agent/` ตาม canonical protocol

## New engine — Vision OCR bbox batch prototype (`OCR service/new engine/`)

สถานะ: **รัน proof-of-use ครบทั้ง 99 ฉบับของ Paperless แล้ว** (2026-10-04, workers=2) + `report.html` แบบโต้ตอบได้

- ผลรันจริงทั้งรอบ: **99/99 ฉบับ · 425 หน้า (ครบทุกหน้า) · 15,111 กรอบเก็บ · 51 กรอบตัดทิ้ง · 99 `ok` / 0 `partial` / 0 doc-level error · 5,951 s (~99 นาที, เฉลี่ย 24.7 s/หน้า)** · output `new engine/tests/out/batch/`
- การกระจาย `doc_type` ระดับหน้า: tax_invoice 237 · purchase_order 90 · delivery_note 48 · other 18 · osp 14 · invoice 12 · tax_invoice_receipt 6 · เหตุผลที่ถูกตัด: zero_area 34, no_text 11, duplicate 6
- **report.html โต้ตอบได้** (`CHG-20261004-002`): ชี้เมาส์ที่กรอบ/แถวตาราง → tooltip แสดง `type · label` + ข้อความเต็ม + พิกัด px/norm และไฮไลต์คู่อีกฝั่ง (sync สองทาง) · คลิก = ตรึง panel + เลื่อนไปแถวที่ตรงกัน · `Esc` ปลด · toggle ซ่อน overlay · ตรวจด้วย jsdom ผ่าน 20/20 ทั้งต่อฉบับ (32 กรอบ) และ batch (overlay 15,111 กรอบ)
- สคริปต์หลัก: `OCR service/new engine/tests/bbox_testv3.py` (663 บรรทัด) — ดึงเอกสารจาก Paperless → เรนเดอร์ทุกหน้าที่ DPI 150 → เรียก VLM ผ่าน LiteLLM (`nvidia/Qwen3.8-Flash-Next-NVFP4`) → ตรวจ/กรอง bbox → วาดกรอบลงภาพ และสร้าง `report.html`, `summary.csv`, `viewer.html` (PDF.js overlay) ต่อฉบับ
- Config อ่านจากไฟล์ `env` ข้างสคริปต์ (fallback เมื่อไม่มี `.env`): `LITELLM_URL`, `LITELLM_KEY`, `VLM_MODEL`, `PAPERLESS_BASE_URL`, `PAPERLESS_API_TOKEN`, `RENDER_DPI`, `VLM_MAX_TOKENS` — ค่าจริงไม่ถูกบันทึกใน agent records
- พฤติกรรมการกรองกรอบ: ตัด text ว่าง/`-`/`unreadable`/ลายเซ็น-ตราประทับที่ไม่มีรอย, bbox พิกัดเสีย, พื้นที่ < 4 px, และซ้ำกับกรอบก่อนหน้า → ของที่ถูกตัดไม่หาย แต่เก็บใน `doc.json` → `dropped` พร้อม `drop_reason`; ตรวจจับ coord mode เอง (`pixel` / `norm1000` / `norm1`)
- Resume native: มี `docs/doc_<id>/doc.json` แล้วจะข้าม (`--force` = ทำซ้ำทุกฉบับ, `--retry-errors` = เฉพาะที่ไม่ ok) และ `--report-only` มีทั้งสองสคริปต์สำหรับสร้างรายงานใหม่จากผลเดิมโดยไม่เรียก AI — ต้องใช้หลังแก้ template รายงาน เพราะ process ที่รันค้างอยู่ยังใช้ template ที่โหลดเข้า memory (`ERR-20261004-003`)
- สิ่งที่ยืนยันจากการรันจริงแล้ว: ขนาดงานจริง 99 ฉบับ, ~20 s/หน้า, เอกสารบางฉบับมี 4–11 หน้า และ model ตอบ `doc_type` ต่างกันได้ในแต่ละหน้าของไฟล์เดียวกัน (เช่น delivery_note + invoice + purchase_order ในฉบับเดียว)
- การป้องกันข้อมูล: `.gitignore` หมวด 13 (เพิ่ม 2026-10-04) ไม่ยอมให้ `new engine/tests/env` (มี API key), `new engine/tests/out/` และ `OCR service/out/` (ภาพเอกสารจริง + ผล OCR) เข้า repo — ตรวจด้วย `git check-ignore` แล้วว่า IGNORED ครบ; `new engine/` ยัง untrack และมี source พร้อม commit 42 ไฟล์
- ข้อจำกัดปัจจุบัน: **ยังไม่มีตัวเลข accuracy** เทียบ ground truth (เป็นแค่ proof-of-use), `viewer.html` (PDF.js) มีแค่ hover ยังไม่มี click-to-pin, `report.html` โตตามจำนวนฉบับ (99 ฉบับ = 3.2 MB และโหลด DATA ทั้งก้อนตอนเปิดหน้า), `new engine/` ทั้งโฟลเดอร์ยัง untrack, ชื่อไฟล์จริง (`bbox_testv3.py`) ไม่ตรงกับชื่อในเอกสาร (`bbox_batch.py`)

## Portal versions under `Web portal/` (layout หลัง merge ตาม `origin/main`)
- `Web portal/invoice-web-9054076/` (87 ไฟล์) — portal React + FastAPI ชุดเดิมที่ remote เป็นฝ่าย archive จาก `invoice-web/`: FastAPI modular monolith แยก `api/auth/core/domain/db/integrations/storage/workers` + React/Vite/TanStack Query, KPI overview strip และ Document detail 5 แท็บ
- `Web portal/invoice-web1/` (106 ไฟล์) — ชุดงาน redesign ให้ตรง Mockup v4.4 (sessions 007–010) ซึ่งเป็นเวอร์ชันล่าสุดของ portal ที่มี backend+frontend ครบ + `agent/` ของตัวเอง
- `Web portal/invoice-webV2/` (58 ไฟล์) — React app ชุดใหม่ที่ align กับ skill `aiva-invoice-core` (ยังไม่มี docs/ ของตัวเอง)
- `Web portal/invoice-webv3/` (9 ไฟล์) — mockup no-build ดูหัวข้อด้านล่าง
- `Web portal/.agents/skills/aiva-invoice-core/` (3 ไฟล์, ถูก force-add ทั้งที่ root `.gitignore` ระบุ `.agents/`) — สรุป field หลัก, กฎ V-01–V-09, decision/routing, workflow/audit requirements และความขัดแย้งระหว่าง code/docs/mockup ใช้เป็น domain reference

## Mockup v3 (no-build) — `Web portal/invoice-webv3`

สถานะ: สร้างใหม่ทั้งโฟลเดอร์ ยังไม่ต่อ backend — commit `94d8cad` และ push ไป `origin/invoice-web` แล้ว (2026-10-03)

- เปิดจาก `file://` ได้ทันที (ดเบิลคลิก `index.html`) ไม่ต้องมี `node_modules` หรือ bundler; ปุ่มคัดลอก JSON ต้องเปิดผ่าน `python -m http.server 5190`
- โหลดสคริปต์คลาสสิก 4 ไฟล์ตามลำดับ `assets/data.js` → `assets/domain.js` → `assets/docs.js` → `assets/app.js`
- `assets/data.js` ถูกรีเจเนอเรตด้วย `tools/build-domain-data.py` จาก `OCR service/n8n/app/core/master_data.py` (นิติบุคคล 48 แถว) และ `rules.py` (exception as-built 15 รหัส + ชุดรหัสฝั่ง user)
- พฤติกรรมที่ฝังใน UI ตรงกับ as-built engine: decision order (manual_review → Manual Review, High → Hold, Medium → Review, ที่เหลือรวม Low → Auto-pass), ownership ตาม `owner_of()`, ladder จับคู่ M1–M4 (M4 = ต้องให้คนตรวจ)
- ข้อมูลเอกสาร 16 ฉบับใน `assets/docs.js` เป็นข้อมูลสังเคราะห์ แต่โครงสร้าง field ตาม receiving contract (schema 1.0) และครอบคลุมเคส fail-safe/duplicate/revision/pipeline-fail
- จำลอง workflow ตาม contract: reason code + required note + `expected_workflow_version` + Idempotency-Key → 409 Conflict เมื่อ version ไม่ตรง (ไม่แก้สถานะ), `rerun` สร้าง action outbox `waiting_revision` และกันการสั่งซ้ำ
- RBAC page แสดงผู้ใช้ 6 คน/5 บทบาท ขอบเขต company ↔ receiver, ผัง Portal ↔ Entra ID ↔ Oracle `RECEIVER` ↔ บริษัท และตาราง Mockup ↔ Production gap
- ความขัดแย้งของแหล่งข้อมูลแสดงต่อหน้าผู้ใช้ ไม่ถูกทำให้หาย: ผัง docs-catalog ↔ as-built, รหัสชนกัน (`E13`, `E34`), Tax ID `0107545000179` / ORG `222` / ORG `196` ที่ไม่มีใน master, ORG `556` ที่ master map แล้ว, ขีดจำกัด PDF portal ↔ Vision, `Decimal` ↔ JSON float
- ตัดสินใจ design สำคัญ: เอกสารที่ map บริษัทไม่ได้ (ORG/Tax ID ว่างหรือไม่อยู่ใน master) ต้องขึ้นในคิวฝ่ายบัญชีพร้อมป้ายเตือน แทนการถูกกรองหายจากทุกคิว
- `tools/smoke-test.js` เป็น DOM ปลอมสำหรับตรวจว่าทุกผู้ใช้/ทุกหน้า/ทุกแท็บ/ทุกเอกสาร/ทุก action เรนเดอร์ได้ และคง invariant ของ `decide()`

## Implemented Portal (`Web portal/invoice-web1/`)
- `invoice-web1/frontend`: React + TypeScript + Vite + TanStack Query; UI ถูกปรับให้ตรงตามต้นแบบ `AIVA-Web-Portal-Mockup-v4.4-Release.html` อย่างสมบูรณ์ 100%:
  - แถบ Header หลัก (`header.aiva-header`): สี Navy เข้ม `#0D274D` สูง 56px พร้อมโลโก้ AI สีเขียว, ลิงก์ Nav 4 ส่วน (`คิวตรวจสอบ`, `สิทธิ์และการเข้าถึง`, `บันทึกการเข้าถึง`, `เชื่อมต่อ API`), Badge บทบาท "เจ้าหน้าที่บัญชี", และ Pill แสดงสถานะ workspace โดยลบ Sidebar สีดำเดิม 240px และ Topbar เดิมออกทั้งหมด
  - แถบขอบเขตและมุมมอง (`.scope`): วางด้านบนสุด ประกอบด้วย `ขอบเขต: รายบริษัท`, Company Chips (`ทุกบริษัท`, `DEMO`), ปุ่มสลับมุมมอง (`[แยก 2 ฝั่ง] [ตารางสรุป]`), และปุ่ม `+ นำเข้าเอกสาร`
  - แถบ KPI Overview (`.kpis`): ตารางสรุป 6 การ์ด (`.kpi`) พร้อมตัวเลขสรุปสถิติเด่นชัดและสีกรอบสถานะ (ทั้งหมด, Auto-pass, Review, Hold, Manual Review, ซ้ำ)
  - เลย์เอาต์หลัก Master-Detail 2 คอลัมน์ (`.wrap`):
    - ด้านซ้าย (`.panel.queue-sidebar` กว้าง 370px, sticky): คิวตรวจสอบเอกสารพร้อมช่องค้นหา (`ค้นหาเลขที่ใบแจ้งหนี้ / PO / ผู้ขาย`), จำนวนเอกสาร, และรายการเอกสารแต่ละใบ (`.qi`) ที่คลิกเลือกแล้วเปิดดูทางขวาทันที
    - ด้านขวา (`.detail-pane`): แสดงเอกสารที่เลือกทันทีตามสถาปัตยกรรมของ Mockup v4.4:
      1. ส่วนหัวเอกสาร (`.dh`): เลขที่ใบแจ้งหนี้, Badge สถานะ, แท็กบริษัท (`.co`), ปุ่มแนบ PDF, ปุ่ม `📄 เปิด/ซ่อน PDF` และ Metadata แถวเดียว (`.meta.document-meta`: ผู้ขาย, PO, Release, ใบรับ, ORG_ID, Receiver, ยอดรวม `.total-number`, รอบตรวจ)
      2. แถบสเต็ปการตรวจ (`.flow`): 4 สเต็ป (`.st.ok / .st.warn / .st.bad / .st.skip`) ได้แก่ STEP 1 สกัดและตรวจเอกสาร, STEP 2 ค้นใบรับและลูกค้า, STEP 3 เทียบกับใบรับ, และ Portal ตรวจซ้ำ
      3. แถบแท็บ (`.tabs`): แท็บแนวนอน 5 แท็บสะอาดตาพร้อมแถบสี teal แสดงแท็บที่เลือก (`.tab.on`)
      4. แท็บ "สรุปและดำเนินการ": แสดงเฉพาะข้อผิดพลาดและข้อสังเกต (`.ex.High / .ex.Medium`) พร้อมรหัส Exception Code, ผู้รับผิดชอบ (`.who`), กฎที่เกี่ยวข้อง, หลักฐาน (`.ev`) และปุ่มเปิดดูหน้า PDF ทันที ไม่ยัดตารางหรือการ์ดซ้ำซ้อน
      5. แท็บ "รายการสินค้า": ตาราง 3-Way Match และการ์ดเปรียบเทียบยอดรวม V-03 กับ V-09 (`.grid2 .card .kv`)
      6. แท็บ "กฎการตรวจ", "ประวัติ", และ "ข้อมูลเพิ่มเติม" (พร้อม JSON preview)
      7. แถบดำเนินการด้านล่าง (`.bar`): Sticky bar พร้อมข้อความระบุสถานะ/ผู้รับผิดชอบ (`.hint`) และปุ่ม Action (`.bp, .bt, .bg, .br, .bw`) พร้อม Modal ยืนยันการดำเนินการ
      8. ตัวอ่าน PDF Viewer แบบคู่ขนานด้านขวา รองรับการซูมและเปิดหน้าตามหลักฐาน
    - รองรับ Responsive บนหน้าจอขนาดเล็ก (Mobile 390px): ซ่อน sidebar เมื่อเลือกเอกสาร ทำให้ไม่มี overflow แนวนอน
- `invoice-web1/backend`: FastAPI modular monolith แยก `api/auth/core/domain/db/integrations/storage/workers`; app factory 49 บรรทัดประกอบ dependencies และ mount frontend (สำเนาชุดก่อน redesign อยู่ที่ `Web portal/invoice-web-9054076/backend`).
- Mockup parity ครอบคลุม company chips, receipt/Receiver/ORG_ID, PO/release, rule STEP 1–3, ownership/access, 5 task-first detail tabs, global audit search/filter/pagination และ keyboard tab navigation.
- หน้า Access แสดง permission/capability จาก `/api/portal/v1/session` และแยก organizational dependencies ที่ยังไม่ได้เปิดใช้อย่างชัดเจน; ไม่มี mock role หรือ workflow action ที่ backend ไม่บังคับใช้.
- Persistent workflow แยกจาก immutable source snapshot: explain/resubmit/rerun/return/reject/hold/confirm มี reason policy, required note, expected revision/workflow version, idempotency และ audit.
- Resubmit/rerun สร้าง action outbox สำหรับ producer; accepted ยังรอ snapshot revision ใหม่ เมื่อ revision ใหม่มาถึง request ปิดเป็น completed และ workflow เปิดรอบตรวจใหม่.
- Source integrations submit JSON snapshots and PDF bytes. Portal does not run OCR/matching, approve invoices or send AP transactions.
- Canonical API contract is `Web portal/invoice-web1/docs/04-receiving-api.md`; scope and implemented gaps are in `Web portal/invoice-web1/docs/05-implementation-status.md` (สำเนาเดิมใน `Web portal/invoice-web-9054076/docs/`).
- Mockup UI-01–UI-15 parity และข้อจำกัดอยู่ใน `Web portal/invoice-web1/docs/07-mockup-feature-parity.md`.
- Current file map, dependency direction และตำแหน่งเพิ่ม feature อยู่ใน `Web portal/invoice-web1/docs/06-project-structure.md`.
- Legacy core Table9 converter preserves original standard/code and leaves unavailable receipts/matches empty.
- Persistent local data is in ignored `<portal version>/data/` (root `.gitignore` มี pattern `data/` ครอบคลุมทุกโฟลเดอร์ย่อย); dependency/build/test artifacts are ignored.
- โฟลเดอร์ `Web portal/data/` (sqlite runtime เก่า `data/tests/bootstrap/portal.sqlite3` + pdf cache) ยังค้างอยู่บน disk จาก layout ที่ถูกยกเลิก — ไม่ถูก track (root `.gitignore` มี `data/` + `*.sqlite3`) ลบทิ้งได้เมื่อไม่ต้องการใช้ต่อ
- Local preview runs at `http://127.0.0.1:8010`; API docs at `/api/docs`. One clearly labeled synthetic example with two JSON/PDF revisions was loaded for manual preview.

## Synthetic OCR Test Corpus (`OCR service/n8n/tests/test_invoices`)
- Corpus ถูกเชื่อมกัด pytest เป็น regression gate: `tests/test_invoice_corpus.py` replay ทั้ง 155 เคส มี pytest ที่ติด marker `live` ของ LiteLLM/Paperless เลืกงขัน offline (`python -m pytest` → `9 passed, 2 deselected in ~1.7s`) โดย `tests/conftest.py` กังไม่ให้ pytest เก็ป `test_suite.py` ที่เป็นสคริปที่ต้องยิง service จริง
- `invoice_engine.py` เป็น bridge ที่เรียก `app/core/rules.py` (Step 1–4) จริงแบบ offline โดยรับชุดแถว Oracle ที่เก็บไว้ในแต่ละ invoice (`oracle_rows`) ทำให้ expected_result ไม่มีวันหลุดจาก logic ของ production และรันซ้ำได้โดยไม่ต้องต่อ Oracle MCP.
- `build_test_dataset_wave2.py` สร้าง 100 เคสใหม่โดย expected_result ทุกตัวมาจาก engine; `verify_dataset.py` replay ทั้ง 155 เคสและ `--fix` ใช้ recalibrate key ได้; `check_pdfs.py` ตรวจว่า PDF ที่ render ตรงกับ key (ฟิลด์ที่มีต้องปรากฏ, ฟิลด์ที่หายไปต้องไม่ปรากฏ, จำนวนหน้าตรง `document_flags`).
- `generate_invoices.py` รองรับ 3 layout เดิมและเพิ่ม `pdf_hints`: watermark/ speckle จำลองเอกสาร scan, ต่อบัญชี 2 หน้า, เชิงอรรถหมายเหตุ, และพิมพ์ `—` สำหรับฟิลด์ที่ key ระบุว่าหาย.
- เคสสำคัญที่ควรทราบเมื่ออ่าน key: `halted_by` ระบุชื่อ circuit breaker จริงแล้ว (`V-02` Gate 1 / `V-04` Gate 2 / `V-05` manual review จาก STEP 2 ผ่าน `rules.gate_halt_reason()` — answer key ของ 155 ใบ recalibrate แล้วรอบนี้ เปลี่ยนเฉพาะ 9 เคสที่ `null` → `V-04` partial billing (E34) เกิดพร้อม E31 เสมอ; E16 บนเอกสารที่คำนวณถูกเกิดจาก float noise ของ `sub_total + vat`; `INV-J17` และ `INV-J20` เป็น forgery ที่ระบบตรวจไม่พบโดยเจตนา (ต้องได้ Auto-pass).
## Standard v6.6 Corpus (`OCR service/n8n/tests/test_invoices/test_dataset_v66.json` + `pdfs_v66/`)
- **Verified 2026-10-03T14:35:00+07:00** (`TASK-20261003-006` / `CHG-20261003-004`) — 100 cases + 100 PDFs เป็น answer key ที่ตรวจผ่านจริง: `pytest tests/test_corpus_v66.py` = **215 passed** (จากเดิม 14 failed / 199 passed) และ suite ถูกเชื่อมใน `tests/run_tests.py --all` เป็น tier ที่ 4
- Decision mix 35 Auto-pass / 30 Review / 30 Hold / 5 Reject · **100/100 เคส re-derive ผ่าน `app/core.rules` ได้ผลเดิม** · Gate 1 (`E02`) 5 เคส halt ก่อน query Oracle, Gate 2 (`E05`/`E06`) 9 เคส halt ก่อน Line Matcher และ `V-07 = not_evaluated` ทุกเคส
- Realism ที่ **วัดจาก dataset** (ไม่ใช่ตัวเลขที่ตั้งเป้า): ผู้ขาย Oracle 20 ราย · multi-PO 34 · two-hop (บิลไม่พิมพ์ Tax ID ผู้ขาย) 5 · split/lot lines 17 · intercompany 4 · fuzzy descriptions 99 · weight-based 13
- ทุก scenario อ้าง receipt/PO ที่มีจริงใน EBS; multi-PO 28 ใบรับถูกเก็บเพิ่มจากการ probe Oracle ตรง ๆ (snapshot v1.1 = 170 scenarios / 653 rows) — **ไม่มีการสังเคราะห์เลขที่เอกสาร** (แบบ `RCV-CONSOLIDATED-*` ที่ถูกรื้อทิ้งรอบนี้)
- Exception ที่ครอบ: E01 7 · E02 5 · E03 13 · E04 29 · E05 5 · E06 4 · E07 4 · E08 11 · E09 3 · E10 9 · E12 8 · E14 4 · E15 14 — **ไม่ถูกยก: `E11`, `E13`** (documented gap ของ engine, corpus จึงไม่ครอบ)
- Corpusนี้เป็น offline answer-key layer (payload + PDF ที่ render จาก payload) ยังไม่ใช่วงจรวัด OCR accuracy — รอบ vision ต้องรันแยกแล้วเทียบ `invoice_data` ต่อ field; `test_dataset_v66.json`, `_raw/`, `pdfs_v66/*.pdf` เป็น gitignored build output ที่ regenerate ได้จาก 3 สคริปต์ (extract → build → render)

- ขอจำกัด: Tahoma subset ที่ฝังใน PDF ไม่มี ToUnicode map ที่ใช้ได้ ทำให้ดึงอักษรไทยเป็นข้อความได้เป็น mojibake (การ render ถูกต้อง) — เครื่องมือตรวจจึงเทียบเฉพาะ ASCII/ตัวเลข; corpus ใช้ dependencies `fpdf2` (render) และ `pypdf` (ตรวจ PDF) ซึ่งไม่ใช่ `requirements.txt` ของ service.

## n8n Workflow `aLUCmn3l0bZDjbVV` (Standard v6.6, on server)
- Workflow ชื่อ `AIVA PO-INV Matching Verification v6.6 (Explanatory Flow)` สถานะ `active: false`; 31 nodes = 23 flow nodes + 8 Sticky Notes, 24 edges, ผังการเดินงานเท่าเดิม (ไม่เพิ่ม/ลด node หรือ connection)
- ตรรกะของแต่ละ node ถูก port จาก Python แบบ 1:1: `normalize_extracted_document`→N4, `evaluate_step1`→N5, RCV-V01 base-table SQL + `parse_csv_receipts`→N7/N7.1, `evaluate_step2`→N8, `evaluate_step3`→N9, `evaluate_step4_decision`+`pipeline`→N10, `validate_output`→N11, `PortalClient`→N12, `PaperlessClient.update_verification_status`→N13/N13.1
- Circuit breaker สองชั้นผูกกับ boolean field: `N6: IF: Gate 1 Breaker (E02)` (true→N10 ข้าม Oracle) และ `N8.1: IF: Gate 2 Breaker (E05 E06)` (true→N10 ข้าม Line Matcher); `N2.2: IF: Unprocessed Document Found` กันงานซ้ำ
- Oracle REST ตรงเดียว: `((Invoice No. ทุก variation × SHIPMENT_NUM/PACKING_SLIP/WAYBILL_AIRBILL_NUM + Supplier Tax ID) OR (NOT EXISTS branch invoice) AND ph.SEGMENT1 IN (PO ทุกตัว))` — Tax ID ที่ว่างถูกเติมด้วย scalar subquery จาก PO แรก (inline Hop 1) พร้อม `RECEIVER` และ scalar `SUPPLIER_IS_INTERNAL`; ลำดับความสำคัญ Invoice→PO ตกอยู่ที่ N7.1 · ตรวจกับ Oracle จริง: `ED6909/0837` + PO `40083989` = 7 แถว (ก่อนแก้ได้ 8,359 แถว), fallback case `TLP-NOT-EXIST-9999` + PO `42052835` = 4 แถวตรงกับ log Python
- View เก่า `APPS.AH_DEV_RCV_PO_AP_MATCHING_V` ใช้กับ v6.6 ไม่ได้ (ไม่มี `RECEIVER`, `SHIPMENT_NUM`, `PACKING_SLIP`, `WAYBILL_AIRBILL_NUM`, `LINE_STATUS`, `QTY_BILLED`) — canvas จึงยิง base tables ตาม Python
- อ่านง่ายแบบ logic-first: Sticky Notes 8 ใบ (NOTE 1–6 + REF A exception map + REF B worked examples) และ 6 Node Groups ตาม STEP (`Manual Trigger` ต้องอยู่นอกกลุ่ม เพราะ n8n ห้าม trigger ใน group)
- เอกสาร: `OCR service/n8n/docs/workflows/n8n_flow_v6_6.md` (คำอธิบายตรรกะรายขั้น + ตัวอย่างจริง) และ `parity_spec_matrix.md` v2.0.0 (ตาราง 23 โหนด + data contract + ตารางเทียบรหัสเก่า E05–E35 → E01–E15)
- **Parity กับ Python engine ยืนยันแล้ว:** รัน canvas จริงด้วย `test_workflow` (execution `#324`, pin I/O ที่ `N2`/`N2.3a`/`N2.3b`/`N3`/`N7`/`N12`/`N13.1` ไม่แตะระบบจริง) ด้วย fixture `tests/fixtures/verified_scenario.json` → `decision` (`Hold`/`user`), `rules` 9 ข้อ, `exceptions` (`E09` High + `E15` Medium + `E03` High), `dms`, `access`, `receiver`, `invoice_summary`, `oracle_data.count` ตรงกับ Python ทุกข้อ · known deltas ที่จงใจคงไว้: รูปแบบตัวเลขในข้อความ `E15` (`10` vs `10.0`), canvas ส่ง `po_numbers`/`SUPPLIER_IS_INTERNAL`/`MATCHED` เผื่อไว้, `timestamp`
- `N11` normalize `rules[]` ให้ทุกแถวมี key `code`/`severity`/`details` (null เมื่อ PASS) ตรงกับ `model_dump()` ของ `RuleResult` เพื่อให้ body ที่ POST เข้า Portal เท่ากันจริง
- การทดสอบฝั่ง Python หลังงานนี้: `tests/run_tests.py --mode offline` = ALL PASSED (ไม่มีการแก้โค้ด Python) · tier `corpus` มี fail จาก `tests/test_corpus_v66.py` ซึ่งเป็นงานคู่ขนานของ `TASK-012` (3-Way Pipeline) ไม่ใช่ regression จากงานนี้
- Known delta ใหม่ (ต้องแก้บน canvas): Python ตั้ง `decision.halted_by = "V-04"` เมื่อ Gate 2 ตัดวงจร ส่วน canvas ยังส่ง `null` ที่ `N8.1` → บันทึกเป็น Known delta ข้อ 4 ใน `parity_spec_matrix.md`
- ข้อจำกัดที่ค้าง: N7 ยังใส่ Bearer token ตรงๆ ใน header (`HARDCODED_CREDENTIALS`) — token หมดอายุ **2026-10-28T01:57:06Z** และ MCP ไม่มี tool สร้าง credential จึงต้องย้ายใน UI; `N12` ยังชี้ `https://httpbin.org/post` จึงไม่รัน `execute_workflow` เต็มจริงกับเอกสารจริง; `E11` ยังไม่ถูกยกทั้งสอง engine (รอนโยบาย Accounting)
- Data shape ของ n8n ต่างจาก Python และห้ามสลับกัน: ใช้ `invoice.po_number`, `lines[]`, `oracle_rcv_rows[]` (แถว active สำหรับ STEP 3), `oracle_rows_all` (ทุกแถว สำหรับ Table 9), `rules[]`, `exceptions[]` — **ไม่มี** `mergedFields` / `po_lines` / `oracle_data.rows`

## Repository Security & Git Boundary
- Global .gitignore ครอบคลุมข้อมูลความลับและเอกสารสำคัญของบริษัท 12 หมวดหมู่:
  1. Environment & Config: .env, .env.*, *.env (ยกเว้น !.env.example), *.secret*, secrets/, ault/
  2. Tokens & Credentials: credentials/, *credential*.json, *token*.json, 	oken.json, *service_account*.json, client_secret*.json, *api_key*, *apikey* (ยกเว้น package.json, package-lock.json)
  3. Private Keys & SSL/SSH: *.key, *.pem, *.pfx, *.p12, *.pkcs12, *.cer, *.crt, *.der, id_rsa*, id_ed25519*, id_ecdsa*, id_dsa*
  4. Oracle EBS & Databases: Oracle Wallet (cwallet.sso, ewallet.p12, *.wallet), Net config (*.ora, ojdbc.properties), Database files (*.db, *.sqlite*, data/, invoice-web/data/), Dumps/Backups (*.dmp, *.dump, *.bak, *.backup, *dump*.sql, *.sql.gz)
  5. Company Financials & Invoices: Real PDFs (*.pdf ทั่วทั้ง repo ยกเว้น synthetic fixture !invoice-web/examples/invoice.pdf), Excel (*.xlsx, *.xls, *.xlsm), CSV extracts (*export*.csv, *report*.csv, *receipt*.csv, *invoice*.csv, *entity*.csv, *oracle*.csv), Batch reports/payloads (*my_report*, *my_failed*, *batch_result*.json, paperless_downloads/, extracted_invoices/), Synthetic corpus จาก production extract (	ests/test_invoices/_raw/, pdfs/, 	est_dataset.json)
  6. Automation & n8n: .n8n/, 
8n-local/, *n8n_export*.json, *workflow_export*.json
  7. Python Environment: __pycache__/, *.py[cod], .venv/, env/, uild/, dist/, .pytest_cache/, coverage files
  8. Node & Frontend: 
ode_modules/, rontend/dist/, playwright-report/, 	est-results/, *.tsbuildinfo
  9. IDE, Agent & Scratch: .vscode/* (ยกเว้น !.vscode/extensions.json), .idea/, .agent/, .agents/, .pi/, .mcp.json, .gemini/, scratch/, /tmp/, 	mp/, 	emp/
  10. Archives: *.7z, *.zip, *.tar*, *.rar, *.gz, *.bz2
  11. Operating System: .DS_Store, Thumbs.db, desktop.ini, ehthumbs.db, $RECYCLE.BIN/
  12. Logs: *.log, logs/
- ตรวจสอบยืนยันด้วย git check-ignore -v ครอบคลุม 25+ pattern ตัวอย่างของ sensitive data ทุกหมวดหมู่ และยืนยันว่า Web portal/invoice-web1/examples/invoice.pdf (และสำเนาใน `invoice-web-9054076`) กับ .env.example ไม่ถูก ignore

## Verified
- Integration merge `2ce5b9e` (2026-10-03T15:31:00+07:00): `origin/main` 0 commits behind (นำหน้า 4 commits รวม commit records ของรอบนี้ — ยังไม่ push); conflict มีเพียงไฟล์เดียวคือ `agent/current-state.md` ซึ่ง merge ด้วยมือ (คงเนื้อหาทั้งสองฝ่าย)
- `git diff --stat origin/main HEAD -- "Web portal"` = **ว่าง** → ทั้งโฟลเดอร์ตรงกับ `origin/main` ทุก byte (รับ layout ของ remote เต็มตามคำสั่งผู้ใช้) และ `git status` ไม่มี dirty file นอก `OCR service/` เลย (41/41 dirty items อยู่ใน OCR service ทั้งหมด)
- OCR service หลัง merge: `python -m pytest -q` = **235 passed, 9 deselected in 35.10s** (offline, `.venv` ของ n8n) และยืนยันว่า `origin/main` ไม่มี diff ใน `OCR service/` เลย (0 ไฟล์) — working tree ของ OCR service คงเดิมครบทั้ง 15 แก้ไข + 26 untracked
- Portal backend เวอร์ชันปัจจุบัน: `pytest "Web portal/invoice-web1/backend/tests"` = **15 passed in 3.68s**
- Mockup v3: `node tools/smoke-test.js` = ผ่าน 46 การตรวจ
- **พบปัญหาใหม่ (ยังไม่แก้):** `python tools/build-domain-data.py --check` ใน `Web portal/invoice-webv3` = **rc 1** พร้อมข้อความ `master_data.py shape changed; update this generator` → `assets/data.js` ที่ mockup v3 ใช้ ล้าสมัยเทียบ กับ `app/core/master_data.py` และ `rules.py` ที่แก้ไว้เฉพาะใน working tree ฝั่ง local (ยังไม่ commit)
- OCR Service Regression: 9 passed, 6 deselected in 5.22s (`OCR service/n8n`) ก่อน merge; หลัง merge ยืนยันว่า `origin/main` ไม่มีไฟล์ใดแตะ `OCR service/` (0 ไฟล์) และ working tree ของ OCR service คงเดิมทั้ง 15 แก้ไข + 26 untracked
- Mockup v3: `node --check` ผ่านทั้ง 4 สคริปต์ใน `Web portal/invoice-webv3/assets/` และ `node tools/smoke-test.js` ผ่าน 46 การตรวจ (ครอบคลุม 409 ไม่แก้สถานะ, confirm เพิ่ม `wf_version`, rerun สร้าง outbox, บล็อก action เมื่อขาด note, KPI นับตรงข้อมูล, master 48 แถว / 15 exception code / 9 กฎ, สแกนรูปแบบ credential)
- Mockup v3 เปิดตรวจด้วย Chromium จริง (Playwright ที่ใช้ package จาก `invoice-web-9054076/frontend`): ไล่ 6 ผู้ใช้ × 4 หน้า × ทุกเอกสาร × 6 แท็บ + viewer + modal → console/page error 0, ไม่มี `undefined`/`NaN`/`[object Object]`, viewport 390px ไม่มี horizontal overflow (0px), header 56px `rgb(13,39,77)`, KPI 6 ใบ, active tab underline `rgb(0,181,175)`, คิวของผู้ใช้ตั้งต้น (ACC) 11 ฉบับ
- ยังไม่ได้ทดสอบ Safari/Firefox และการเรนเดอร์ font จริงจาก Google Fonts ต้องใช้ network (offline แล้ว fallback เป็น system-ui/monospace ตามลำดับ)
- Skill package ผ่าน `quick_validate.py` เมื่อรันด้วย UTF-8 mode; reference link และ source paths ที่ระบุมีอยู่จริงครบ.
- Backend: 15 unittest tests passed (persistence, idempotency, conflicts, revisions, schema validation, versioned PDF, global audit, workflow action/version/idempotency/outbox/revision completion, compatibility backfill, origin, keys, filters, adapter, architecture boundaries).
- Frontend: TypeScript strict and Vite production build passed (`tsc -b && vite build` built clean in 5.2s).
- Playwright: 6 tests passed on Edge browser (15.2s), covering import, PDF canvas viewer, tabs, history, filters, mobile viewport (390px) no-overflow, invalid JSON rejection, exact large decimal display, revision deep link/archived PDF, access/audit navigation, and review action persistent outbox.
- Visual inspection: ยืนยันเลย์เอาต์ Master-Detail (ซ้าย: คิว 370px, ขวา: เอกสารและ PDF) สะอาดตา กระชับ ตรงตามโครงสร้าง Mockup v4.4 ปราศจากตารางซ้ำซ้อนในแท็บสรุป.
- Local preview on port 8010 serves latest production bundle successfully.
- Test corpus: `verify_dataset.py` replayed 155/155 invoices and reported 0 drift against `app.core.rules`; `check_pdfs.py` audited 155 PDFs / 157 pages with 0 mismatches; 3 rendered pages visually inspected (Thai glyphs, watermark, blank receiver-signature area, continuation page).
- Offline pytest suite: `9 passed, 2 deselected` ใน ~1.7 วินาที (corpus 7 tests + SSE UI 2 tests ที่ไม่เรียก service ภายนอก); ยืนยันความไวของ gate ด้วยการใส่ข้อมูลผิดตงใจ 4 แบบ แล้วเครื่องมือรายงาน error ครบ
- n8n workflow v6.6 (2026-10-03 บ่าย): re-export จากเซิร์ฟเวอร์แล้วตรวจด้วยสคริปต์ → 31 nodes / 24 edges / 0 dangling / ทุก flow node มี inbound edge / 0 broken `$()` ref; diff โค้ด 7 jsCode + N7 jsonBody เทียบ canonical copies พบต่างเฉพาะ comment (`node --check` ผ่าน);
  Oracle MCP ตรวจจริงด้วยบิล `ED6909/0837` → 7 แถว ข้าม 3 PO (`40083989`,`40089558`,`40118686`), GR `510522788`, receiver `Oracle, Concurrent`
- No live OCR, Oracle, LiteLLM, Paperless or AP tests executed.


## Existing System
- `OCR service/n8n/app` remains the existing Python OCR and matching service.
- `Web portal/AIVA-Web-Portal-Mockup-v4.4-Release.html` remains UI/data reference inside `Web portal/`.
- `Web portal/` เก็บ portal หลายเวอร์ชัน: `invoice-web-9054076/` (archive), `invoice-web1/` (React+FastAPI เวอร์ชันปัจจุบัน), `invoice-webV2/` (React ใหม่ตาม skill), `invoice-webv3/` (mockup no-build) — ยังไม่ได้คัดเลือกเวอร์ชันเดียวเป็น canonical
- `docs/` remains original architecture reference; code/docs have known contract and rules-version differences recorded in Web portal planning documents.

## Constraints / Next Work
- ต้องเลือก "เวอร์ชันเดียวที่เป็น canonical" ของ portal: `invoice-web-9054076` / `invoice-web1` / `invoice-webV2` / `invoice-webv3` ยังอยู่ซ้อนกัน 4 ชุด และเอกสาร contract ถูก copy ซ้ำทุกโฟลเดอร์ — ต้องเลือกก่อนว่างานพัฒนาครั้งถัดไปลงโฟลเดอร์ไหน
- ต้องแก้ `Web portal/invoice-webv3/tools/build-domain-data.py` ให้รองรับ shape ใหม่ของ `OCR service/n8n/app/core/master_data.py` + re-generate `assets/data.js` (ตอนนี้ `--check` fail) — งานนี้แตะ `OCR service/` ได้เฉพาะ "อ่าน" ห้ามแก้
- root `.gitignore` ปรับ pattern ให้ตาม layout ใหม่ (`Web portal/*/data/`, `!Web portal/*/examples/invoice.pdf`) และลบ path ที่ตายแล้ว (`invoice-web/...`); ยืนยันแล้วด้วย `git check-ignore` ว่า `examples/invoice.pdf` ทั้งสองสำเนาไม่ถูก ignore และ `data/` ยังถูก ignore
- การป้องกันข้อมูล: `.gitignore` หมวด 13 (เพิ่ม 2026-10-04) ไม่ยอมให้ `new engine/tests/env` (มี API key), `new engine/tests/out/` และ `OCR service/out/` (ภาพเอกสารจริง + ผล OCR) เข้า repo — ตรวจด้วย `git check-ignore` แล้วว่า IGNORED ครบ; `new engine/` ยัง untrack และมี source พร้อม commit 42 ไฟล์
- n8n workflow v6.6 ยัง `active: false` (ตามนโยบาย: ไม่เปิด schedule โดยไม่ได้สั่ง) และยังไม่เคยรัน end-to-end จริงกับ Paperless/LiteLLM/Portal — การยืนยัน ณ ขณะนี้เป็นแบบ static (topology + code diff) + Oracle query จริงหนึ่งคำสั่งด้วย base tables
- N7 ยัง hardcode Authorization header (ควรย้ายไป credential `httpTemplatedCustomAuth` ตามที่ n8n แนะนำ)
- Current release is local/integration pilot, not company-scoped production: shared API keys are workspace-wide; Entra, user/receiver RBAC and immutable user audit remain unimplemented.
- Workflow actions ใน shared-key pilot ไม่มีตัวตนรายบุคคล; ต้องเชื่อม Entra ก่อนบังคับ EU/ACC/APR และ separation of duties.
- SQLite startup table creation currently used; PostgreSQL/Alembic and production backup/storage/retention/scan/rate limits remain future work.
- `workers`, `migrations` และ `infra` เป็น boundary พร้อม README เท่านั้น ยังไม่มี Celery/Redis, Alembic runtime หรือ production deployment.
- PDF binary upload only; no live DMS URL connector/watermark. JSON/PDF เปิดย้อนหลังตาม revision ได้ แต่ retention/legal hold/cleanup ยังไม่ทำ.
- Need sanitized real producer contract to validate upstream mapping; never relabel legacy codes as a new standard.
- Producer ต้องเชื่อม action outbox และกำหนด SLA/retry/dead-letter ก่อนใช้ resubmit/rerun กับงานจริง; AP post ยังไม่เปิด.
- Keep logs free of secrets and invoice payloads; read Thai files explicitly with UTF-8.

## System A — Real-Data Integration & Offline Verification (OCR service/system-a-sandbox/system-a/)

สถานะ: **รันและตรวจสอบบนข้อมูลจริงครบทั้ง 99 เอกสาร Paperless-ngx เรียบร้อยแล้ว** (2026-10-05) ผ่าน Acceptance Criteria AC-01 ถึง AC-14 ครบ 14/14 (100%)

- **ผลการประมวลผล 99 เอกสาร (runs/2026-10-05-full/)**:
  - เอกสารทั้งหมด: 99 ฉบับ, 424 หน้า (417 หน้าประมวลผล)
  - สถานะ: COMPLETED 99/99 ฉบับ (MANUAL_REVIEW 71, REVIEW 14, HOLD 13, SYSTEM_ERROR 1)
  - กฎและข้อยกเว้น: E01 99, E10 54, E13 30, E03 25, E11 11, E09 9, E05 7, E02 6, E14 2, E15 1
  - Oracle Integration: RCV-V01 63 ฉบับ, PO-SUPPLIER 12/12 probes pass, receipt lines พบใน 63 ฉบับ (รวม 152 rows), calls/doc <= 3
  - Line Matching: 98 ฉบับมี line table, 608 rows, 507 rows มี qty > 0, match กับใบรับ 383 rows (75.5%)
  - BBox coverage: word bbox 100.0% (223,546 words), row/cell 98 ฉบับ, signature 93 ฉบับ, stamp 76 ฉบับ, 0 out-of-range bboxes
- **Interactive HTML Report (reports/2026-10-05-full/)**:
  - Offline-first: PDF.js vendor ในตัว, รองรับ deep link #doc=<id>, zoom 50%/100%/200% ตรง 0 px mismatch
  - Interactive tabs: Summary, Rules, Evidence, OCR Fields, OCR Text, Invoice <-> Receipt, Oracle Snapshot, Raw JSON
  - Privacy mask: ชื่อผู้รับของ (RECEIVER) ถูก mask อักษรแรกของชื่อ/นามสกุลในหน้าจอรายงาน

### Core Clean Layout & Single Runner (process_pdf.py)
- ปรับโครงสร้าง system-a ให้เหลือเฉพาะ Core Engine เพื่อลดความซับซ้อน:
  - ย้ายไฟล์ทดสอบและผลรันเดิม (tests/, sandbox_data/, runs/, reports/, docker/, scripts/, FINDINGS.md) ไปยัง archive/ อย่างปลอดภัย
  - สร้าง process_pdf.py: สคริปต์หลักแบบ Standalone สำหรับรับไฟล์ PDF เดี่ยว -> ทำ Perception (OCR+BBox) -> Query Oracle EBS -> Match Lines & Evaluate Rules V01-V09 -> ออกผลลัพธ์ aiva.system_a.result/3.0
  - ทดสอบรันกับ 20.pdf จริง สำเร็จใน 33.6 วินาที (แมตช์ 12 receipt lines จาก EBS, สรุปผล recommendation เป็น MANUAL_REVIEW)
  - อัปเดต README.md เป็นคู่มือ 1 หน้าที่กระชับและเข้าใจง่าย

## System A — Evaluation Loop รอบที่ 1 (2026-10-05T23:55:00+07:00)

สถานะ: **ตั้ง baseline ที่วัดซ้ำได้ + ผ่าน 3 mutation แรกโดยไม่มี regression**; ความแม่นยำรวมยังไม่ขึ้น
เพราะ E01 ยังค้างทุกเอกสาร — คอขวดจริงอยู่ที่ชั้น Perception ไม่ใช่กฎหรือค่า tolerance

- **Baseline anchor** `.agent/eval/full_r0/` (99/99, replay บน perception cache ที่ pin ไว้) ทำซ้ำ distribution
  ของรอบสดเดิมได้ตรงเป๊ะ: AUTO_PASS 0, MANUAL_REVIEW 71 (71.7%), REVIEW 14 (14.1%), HOLD 13 (13.1%),
  SYSTEM_ERROR 1 และ V-01 fail 99/99
- **Mutation ที่ยอมรับ (commit ทับ `291bd76`):**
  - `4d80ffc` ตารางลูกค้า V-05: key ที่ RCV-V01 ส่งจริงเป็น operating unit ไม่ใช่ sub-organization
    → `manual_review` 53 → 0 และไม่มี E07 เท็จ (วัด offline 83 ฉบับ + ยืนยันสดบน `full_r1` 23 ฉบับแรก)
  - `9ab2e9c` หน่วยนับ: เพิ่มเฉพาะคำพ้องภายในกลุ่ม (X-06) → E10 70 → 68, E10 ใหม่ 0
  - `64152ea` JSONคำตอบ vision ถูกตัดเพราะ reasoning token กิน `max_tokens` → re-ask แบบปิด thinking +
    salvage; Tier B บน DMS-20: `pages_complete` false → true, เส้นบิล 12 → 6 (ตารางซ้ำถูกตัด),
    max severity High → Medium, E13 (High) 6 รายการ + E11 3 รายการหายไป
- **Regression gate ล่าสุด (`full_r1` กำลังรัน 23/99):** comparable 23, improved 1 (DMS-25
  MANUAL_REVIEW → REVIEW), **REGRESSED 0**; V-05หลุดจาก manual_review 9/23 (DMS-21 ผ่าน)
- **ตัวเลขที่ชี้ทางรอบถัดไป**: จาก 608 เส้นบิลของ baseline หน่วยนับใช้ไม่ได้ **66.7%**
  (NOT_PRESENT 238 + LOW_CONFIDENCE 168) → ต้องแก้ prompt ตารางหน่วยนับ + เพิ่มผู้อ่านคนที่สอง
- **ข้อจำกัด/งานค้างเจ้าของ:**
  - ตารางที่ 4 ของมาตรฐาน §04 ต้องลงคีย์ฝั่ง operating unit ให้ครบ (AERP) — OU ที่กำกวม (Plastics, Bike,
    MG, AVEE, ITS, หน่วย test/consolidation) คง `status: unknown` = Manual Review ตามมาตรฐาน
    และ `XLE_*` ของระบบทะเบียนลูกค้าอ่านไม่ได้ด้วยสิทธิ์ read-only ปัจจุบัน จึงสร้างตารางเพิ่มเองไม่ได้
  - perception cache: key ครอบคลุม fingerprint โค้ดอ่านภาพอยู่แล้ว (`opts["pipeline"] = pipe.code_version`
    + `_code_fingerprint()` hash source ของ `pdf_ingest`, `coords`, `vision_pipeline`) แต่ตัวไฟล์ cache
    ไม่ได้บันทึกว่าเกิดจาก code version ไหน → เวลาทดสอบการแก้ perception ต้องใช้
    `PERCEPTION_CACHE_DIR` แยกเสมอ และหลังแก้ `vision_pipeline.py` (fingerprint = 57f4096e01a8)
    extraction ที่ cache ไว้ 112 ชุดจะถูกรีเพอร์เซปต์เมื่อรันสดครั้งถัดไป (ดู ERR-20261005-004 ฉบับแก้ไข)
  - การอ่านเอกสารมีความไม่แน่นอน: `process_pdf.py` รอบสดเรียก matcher ซ้ำทุกครั้งที่ 30–60 วินาที
    การวัดที่เปรียบเทียบได้จึงใช้ replay จาก perception cache + คำนวณ V-05/V-07 ใหม่จากข้อมูลเดิม

## System A — Web Testing Portal (`OCR service/system-a-sandbox/system-a/web/`, อัปเดตล่าสุด 2026-10-06T08:25:00+07:00)

สถานะ: **ครบทั้ง 5 phase ของ `TASK_WEB_TEST_PORTAL.md` · commit `5a058e0` · pytest 31/31 + UI logic 27/27 + live checker 77/77**

- เป็น **consumer ของ CLI เท่านั้น**: การรันทุกครั้งที่ portal คือ subprocess ของ `system-a/process_pdf.py`
  (ไม่ import `system_a` เพื่อตัดสินใจ) → `src/system_a/**`, `config/**` และ output contract ไม่ถูกแตะ
  ตรวจแล้ว `git show --name-only 2d87f6e` ไม่มีไฟล์ core เลย
- ยืนยันความเท่าเทียมกับ CLI ด้วย `integrity.payload_sha256`: DMS-20 sandbox ผ่าน portal = ผ่าน CLI
  ทุกตัวอักษร (1.0s เท่ากัน — perception cache hit)
- bbox ทั้งหมด resolve จาก contract เท่านั้น: ค่าจาก `extraction.*`, ตำแหน่งจาก `ocr.elements[]`
  ผ่าน `element_id`, exception ผ่าน `evidence[].related_element_ids`, cell ที่ไม่มี id join ด้วย
  `field_name = lines[<n>].<column>`; `coordinate_system` อ่านจากผลจริง ไม่เคย assume
- render หลัก = raster ที่ server เรนเดอร์ด้วย PyMuPDF (lib เดียวกับ perception จึงตรงกันกับภาพที่ model เห็น);
  PDF.js 4.10.38 vendor ไว้ same-origin เป็น vector mode และ fallback กลับ raster อัตโนมัติ
- วิธีเปิด: `system-a> run_portal.bat` หรือ `python web\serve.py --port 8080` — interpreter ของ engine
  ถูกเลือกด้วยการ "ลอง import" (yaml/pydantic/pymupdf) ไม่ใช่เดา path; override ด้วย `WEB_ENGINE_PYTHON`
- ข้อจำกัดที่รู้อยู่: `--quick` ของ CLI ไม่ใช่โหมดเร็ว (it disables crops+table ⇒ perception คนละชุด,
  cache key คนละตัว, verdict ต่างกันได้) UI จึงแสดงเป็น "คนละการรัน"; ยังไม่มีการคลิกทดสอบบน browser จริง
- **ลำดับ route มีผล**: `/api/verify/upload` ต้อง register ก่อน `/api/verify/{doc_id}` ไม่งั้น Starlette
  ตอบ literal "upload" เป็น doc_id → อัปโหลดได้แต่ verify ตายด้วย 422 (มี regression test ปิดทางกลับ)
- ความล้มเหลวของ Paperless-ngx ถูกแปลเป็นสถานะที่ browser ควรเห็น + ประโยคอธิบาย 1 ประโยค:
  `404` id เก่า/ถูกลบ, `502` token ถูกปฏิเสธ (`PAPERLESS_AUTH`), `503` ไม่ได้ตั้งค่า DMS, `502` transport;
  ฝั่ง UI แสดง `detail` ของ FastAPI ตรงๆ และภาพที่โหลดไม่ออกจะถาม endpoint กลับไปหาสาเหตุ
- ตัวตรวจแบบเดินจริง `python web\check_live.py` (77 checks: asset ทุกไฟล์ที่ page เรียก, catalog,
  verification จริง 1 ฉบับผ่าน subprocess, geometry, upload, และ failure path) ถูกรวมเข้า repo พร้อม
  pytest ที่บังคับให้มันรันได้ตอน portal ไม่อยู่ (ชน port ที่ปิด → ต้องได้ FAIL lines ไม่มี traceback)
- Record ประกอบ: session `2026-10-05-004` + `2026-10-06-001`, `CHG-20261005-004/005`, `CHG-20261006-001`,
  `ERR-20261005-005/006`, `ERR-20261006-001/002`, DEC-013..015

## System A — ราคาของงาน perception ที่วัดได้จริง (2026-10-06T08:32:00+07:00)

วัดจาก cache baseline (`full_r0`) อย่างเดียว ไม่มี VLM call; harness อยู่ `.agent/harness/`
(`uom_probe.py`, `consensus_probe.py`), ผลดิบ `.agent/eval/{uom,consensus}_probe_r0.json`

- **สถานะ UOM (608 เส้น)**: 2 ผู้อ่านยืนยัน 202 · cell เดี่ยว 168 · ไม่มี cell 238
  โดย **236/238 อยู่ในหน้าที่ไม่พิมพ์คอลัมน์หน่วยนับรายบรรทัด** (ยืนยันด้วยตาบน DMS-40/DMS-65)
  → งาน "บังคับให้โมเดลคืนคอลัมน์ uom" **ถูกล้มล้าง** เพราะเท่ากับการเติมค่าที่ไม่ได้พิมพ์อยู่บนกระดาษ
- **เอกสารที่พิมพ์หน่วยไว้ที่หัวคอลัมน์** (DMS-65: "จำนวนแผ่น Pcs.", "นน./แผ่น Kgs./Sheet") เมื่อใช้ geometry
  ที่ implementation จริงใช้ได้ + vocabulary เข้ม → ได้เพิ่มแค่ **12/143 cell (2 เอกสาร)**
- **เพดานของนโยบาย consensus ต่อ V-01 (documents/99)** — replay นโยบายจริงจาก `policy.yaml`:
  `0` วันนี้ → `1` ยอมรับรันของคำใน box → `3` +containment → `5` + substring ของแถว → `16` + substring ทั้งหน้า
  (ข้อหลังสุดไม่ใช่หลักฐานที่ยอมรับได้ทางบรรษัท)
- **ถ้าแก้ UOM ให้สมบูรณ์ 100%**: ผ่านแค่ **11–13/99** → กำแพงที่ใหญ่กว่าคือ
  (ก) `customer_name` สองผู้อ่านขัดกัน **43 เอกสาร** — VLM กลืน caption เข้าค่า ("ขายให้แก่ SOLD TO บริษัท...")
  ขณะที่ text layer เป็นไทยที่ glyph แตก ("บ ริ ษั ท อ า ป บ โก") ซึ่ง Thai mark folding ที่มีอยู่ช่วยไม่ได้
  (ข) ตัวเลขอยู่บนหน้าแต่ **ไม่อยู่ใน box ที่โมเดลเคลม** 34–39 เอกสาร (grounding ไม่ใช่การอ่าน)
  (ค) cell ที่โมเดลไม่คืนมาเลย: qty 15 / unit_price 16 / amount 12 เอกสาร
- **ข้อจำกัดของ perception ปัจจุบันที่วัดเพิ่ม**: `max_words = 2500` เป็น per-document → หน้าท้ายๆ ของเอกสารยาว
  **ไม่เก็บ word เลย** (DMS-40 p5 text layer 2,054 ตัวอักษร / words=0); 42/99 เอกสารโดนตัดคำ,
  **84 cell ที่ V-01 ต้องการตกบนหน้าที่โดนตัด**
- **ข้อจำกัด control plane (ใหม่)**: `.agent/` ทั้งโฟลเดอร์ถูก gitignore (root `.gitignore:212`) และ
  `git ls-files` คืน 0 ไฟล์ → baseline copy, `todo.md`, `decisions.md`, `recovery.md` มีสำเนาเดียวบนดิสก์เครื่องนี้
  เป็นความเสี่ยงต่อ rollback anchor ที่ DEC-015 พิงอยู่ (ตั้งเป็น TASK-OPS-07)
- **สถานะงาน**: ยังไม่แก้ engine, ยังไม่ re-pin baseline, **V-01 ยัง fail 99/99** ตาม baseline `full_r0`;
  รอ user ตัดสินว่าจะจ่าย cache reset ซื้อชุดไหน (ดู TASK-20261006-002 ใน task-plan)
