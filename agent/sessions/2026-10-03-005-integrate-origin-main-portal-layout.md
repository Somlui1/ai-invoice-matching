# Session 005 — Integrate `origin/main` (portal restructure) โดยไม่แตะ `OCR service/`

- **Session ID:** `2026-10-03-005`
- **Task:** `TASK-20261003-007` (root)
- **Change:** `CHG-20261003-007` (root)
- **Error record:** `ERR-20261003-005` (root)
- **Merge commit:** `2ce5b9e` (merge `origin/main` 6 commits เข้า `main`)
- **Time:** 2026-10-03T15:10:00+07:00 → 2026-10-03T15:35:00+07:00
- **Agent:** Pi Agent
- **User direction:** *"ฉันไม่แคร์ web portal folder ปัจจุบัน ให้ merge ทับได้เลย แต่อย่างยุ่งกับ OCR service dir"*

> หมายเหตุ protocol: `agent/sessions/` ของวันที่ `2026-10-03` มี sequence `001–004` ถูกใช้ซ้ำโดยสองผู้เขียน (ชื่อไฟล์ไม่ชนกันแต่ ID ซ้ำตามนิยามใน `agent/README.md`) รอบนี้จึงใช้ `005` และรอบถัดไปให้เริ่มที่ `006`

## Objective
ปลดล็อก `git pull` ที่ล้มเหลว และรวมงาน portal 6 commits ของ `origin/main` เข้า `main` โดย
1. ยอมรับ layout `Web portal/` ของ remote ทั้งก้อน (สถานะ portal ในเครื่องไม่มีค่าให้รักษา ตามคำสั่งผู้ใช้)
2. ไม่แตะ `OCR service/` แม้แต่ไฟล์เดียว — ทั้ง 15 ไฟล์แก้ไข + 26 untracked (n8n v6.6 engines/prompts/corpus/test) ต้องคงอยู่ครบ

## Symptom ที่ผู้ใช้เจอ
```
error: Your local changes to the following files would be overwritten by merge:
  Web portal/.env.example ... Web portal/run-local.ps1
warning: 11 lines add whitespace errors.
Merge with strategy ort failed.
```
บรรทัด whitespace เป็น warning จาก blob content (xref table ของ PDF) — ไม่ใช่ต้นเหตุ

## Findings (จากหลักฐาน ไม่ใช่จากอาการ)
1. `main` **diverged: ahead 1 / behind 6** → `git pull` เป็น merge จริง และ merge ต้องการใช้ path เดียวกับที่มี worktree สกปรก
2. ต้นเหตุโครงสร้าง: **ทั้งสองฝ่ายย้ายโฟลเดอร์ต้นทางเดียวกันไปคนละตำแหน่ง**
   - local (staged แต่ยัง **ไม่ได้ commit**): `invoice-web/` → `Web portal/` (87 ไฟล์) + worktree edits 6 ไฟล์
   - remote (commit แล้ว): `invoice-web/` → `Web portal/invoice-web-9054076/` (R100, เนื้อหาไม่เปลี่ยน) **+ ไฟล์ใหม่ 176 รายการ** (`invoice-web1/` 106, `invoice-webV2/` 58, `invoice-webv3/` 9, `.agents/skills/aiva-invoice-core/` 3) + session log 8 ไฟล์
3. ผล merge ที่ค้างใน `.git/AUTO_MERGE` (`06527b26`) มี **159 ไฟล์** ขณะที่ `origin/main` มี **340 ไฟล์** → การฝืน merge (`checkout -f` / `clean -fd` / `stash -u && pull`) จะลบงาน mockup + session log ของอีกฝั่งทิ้ง **โดยไม่มี conflict ให้แก้**
4. dry-run ด้วย `git merge-tree --write-tree HEAD origin/main` (ไม่แตะ worktree) ทำนายผลจริง: **conflict เนื้อหาไฟล์เดียว = `agent/current-state.md`**; portal renames เป็น `R100` ทั้งหมด จึงไม่ใช่สมรภูมิ 87 ไฟล์อย่างที่อาการบอก
5. `git config` เดิม: `pull.rebase=false`, `merge.renames` default, `core.autocrlf=true` (ที่มาของ warning `LF will be replaced by CRLF`) และไม่มี `merge.directoryRenames` → directory rename ที่ชนกันถูก "ยุบเงียบ"

## Actions
1. **Backup สองชั้นก่อนแตะอะไร**
   - `git stash create -u` → `git branch backup/wip-dirty-20261003 737469a` (ไม่แตะ working tree เลย)
   - คัดลอกทุก path จาก `git status --porcelain` (136 paths / 160 ไฟล์ / 4.7 MB) → `C:\Users\wajeepradit.p\git\wip-backup-20261003\`
   - ตรวจก่อนทิ้ง: 87 relocation files เป็น pure rename (เนื้อหา == HEAD) มี edit จริงแค่ 6 ไฟล์ใน `Web portal/` ตามที่ผู้ใช้ยกให้ทิ้ง
2. **ยกเลิกการย้ายโฟลเดอร์ฝั่ง local** ตามลำดับ: `git rm -r --cached -f -- "Web portal"` → `git checkout HEAD -- invoice-web "Web portal"` → `git clean -fd -- "Web portal"` (ตั้งใจ **ไม่ใช้ `-x`** เพื่อไม่ลบของ ignored: `data/`, `portal.sqlite3`, `node_modules`) → ลบ `__pycache__` และโครงโฟลเดอร์ `Web portal/backend` ที่เหลือแต่ไดเรกทอรีว่าง
3. **เตรียมสถานะให้ merge สะอาด:** commit `agent/` records (`12393f5`) เพราะ `agent/current-state.md` ถูกแก้ทั้งสองฝั่ง (ต้อง clean ถึงจะ merge ได้) และแก้บันทึกที่ให้ข้อมูลผิดไว้ (อ้างว่าย้าย portal สำเร็จแล้ว) ให้ตรงความจริง
4. **Merge:** `git config merge.directoryRenames conflict` + `git config merge.renames true` → `git merge --no-ff origin/main` → conflict ตาม dry-run ทำนายไว้ 1 ไฟล์
5. **แก้ conflict ด้วยมือ** โดยคงเนื้อหาทั้งสองฝ่าย:Mockup v3 + skill + ผลตรวจ Playwright/tsc ของ remote รวมกับ n8n v6.6 corpus + parity + halted_by ของเรา และแก้ path ที่ตายแล้วทั้งหมดเป็น `Web portal/invoice-web1/...` (contract `04-receiving-api.md`, `05/06/07`, ผลตรวจ backend)
6. **`.gitignore`:** เปลี่ยน pattern ที่ผูกกับ path ที่ตายแล้ว → `data/` + `Web portal/*/data/`, `!Web portal/*/examples/invoice.pdf`; ลบ `invoice-web/data/`, `!invoice-web/examples/invoice.pdf`, escaped variants ที่ไม่จำเป็น; ตรวจซ้ำด้วย `git check-ignore -v`
7. บันทึก canonical records: `current-state.md`, `changelog.md` (`CHG-20261003-007`), `work-log.md`, `errors-and-solutions.md` (`ERR-20261003-005`), `task-plan.md` (`TASK-20261003-007` ปิดงาน) และ session ไฟล์นี้

## Verification (ผลจริง ไม่ใช่ที่รายงานต่อ)
| คำสั่ง | ผล |
|---|---|
| `git diff --name-only <merge-base> origin/main -- "OCR service"` | **0 ไฟล์** → remote ไม่แตะ OCR service เลย |
| `git status --porcelain -- "OCR service"` หลัง merge | **41 รายการคงเดิม** (15 แก้ไข + 26 untracked) |
| `python -m pytest -q` (`OCR service/n8n`, `.venv`) | **235 passed, 9 deselected in 35.10s** |
| `pytest "Web portal/invoice-web1/backend/tests"` | **15 passed, 3 warnings in 3.68s** |
| `node tools/smoke-test.js` (`invoice-webv3`) | ผ่าน **46** การตรวจ |
| `python tools/build-domain-data.py --check` (`invoice-webv3`) | **rc 1** — `master_data.py shape changed; update this generator` |
| `git rev-list --left-right --count origin/main...HEAD` | **`0 3`** (behind 0) |
| `git ls-files invoice-web` | **0** (archive ครบใน `Web portal/invoice-web-9054076`) |
| ไฟล์ใหม่ remote หลัง merge | invoice-web1=106, invoice-webV2=58, invoice-webv3=9, .agents=3, remote sessions=8 |

## Incidental finding ระหว่าง backup
`OCR service/n8n/app/AIVA-Document-Card-Verification-v3.html` ถูก process อื่น (editor/dev tool) บันทึกซ้ำระหว่างทำ backup (mtime 15:26:20 → 15:26:29) ทำให้ snapshot รุ่นแรกเก่ากว่า worktree เล็กน้อย — worktree คือรุ่นใหม่สุด (มี null-guard + `setEngineMode`) และ merge ไม่แตะไฟล์นี้

## Known deltas / Next work
1. ยังไม่เลือก "เวอร์ชัน canonical" ของ portal — `invoice-web-9054076` / `invoice-web1` / `invoice-webV2` / `invoice-webv3` ซ้อนกัน 4 ชุด และเอกสาร `docs/01–08` ถูก copy ซ้ำแทบทุกโฟลเดอร์
2. `Web portal/invoice-webv3/tools/build-domain-data.py` ต้องรองรับ shape ใหม่ของ `OCR service/n8n/app/core/master_data.py` แล้ว re-generate `assets/data.js` (ตอนนี้ `--check` fail = mockup v3 แสดง master data/exception code ที่ล้าสมัย) — งานนี้ **อ่าน** OCR service ได้อย่างเดียว ห้ามแก้
3. `Web portal/data/` (sqlite runtime เดิม + pdf cache) ยังค้างบน disk แบบ untracked/ignored — ลบได้เมื่อไม่ใช้ต่อ
4. ยังไม่ push (นำหน้า remote 3 commits) รอคำสั่งผู้ใช้; branch `backup/wip-dirty-20261003` ลบทิ้งได้หลังยืนยันว่าไม่ต้องการงาน portal ที่ทิ้งไปแล้ว
5. แนะนำตั้งค่าถาวร: `merge.directoryRenames=conflict` และเพิ่ม `.gitattributes` (`* text=auto eol=lf`) เพื่อกำจัด noise จาก `core.autocrlf=true`
