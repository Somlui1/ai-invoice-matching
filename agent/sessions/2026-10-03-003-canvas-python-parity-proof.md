# Session 003 — Proof of n8n Canvas ↔ Python Parity + Oracle Query Fix

- **Session ID:** `2026-10-03-003`
- **Task:** `TASK-20261003-005` (root) / `TASK-013` (service)
- **Change:** `CHG-20261003-003` (root) / `CHG-20261003-005` (service)
- **Error record:** `ERR-20261003-003`
- **Time:** 2026-10-03T13:50:00+07:00 → 2026-10-03T14:25:00+07:00
- **Agent:** Pi Agent (via MCP `aiva-n8n` + `oracle`)

## Objective
ปิด follow-up ของการอัปเดต canvas เป็น v6.6: พิสูจน์ด้วยหลักฐานว่าการเดินงานบน n8n ให้ผลตรงกับ Python engine และทำรายการค้าง (credential, E11, commit) ให้ครบเท่าที่ทำได้ โดยไม่แตะระบบจริง

## Scope
- **ไม่แก้โค้ด Python ใดๆ** — งานนี้แก้เฉพาะบน canvas ผ่าน MCP และเอกสาร
- **ไม่เดิน side effect:** ไม่ tag Paperless, ไม่ยิง LiteLLM, ไม่ยิง Portal

## Findings
1. **Parity ผ่านจริง** — รัน canvas ใน n8n ด้วย `test_workflow` + pinData ที่ `N2`/`N2.3a`/`N2.3b`/`N3`/`N7`/`N12`/`N13.1` (execution `#324`, success, ถึง `N14`) แล้วเทียบ Table 9 กับ baseline Python บน fixture `tests/fixtures/verified_scenario.json`:
   `decision` (`Hold`/`user`), `rules` 9 ข้อ (V-01..V-06 PASS, V-07 FAIL `E09`, V-08 PASS, V-09 FAIL `E03`), `exceptions` (`E09`/`E15`/`E03`), `dms`, `access`, `receiver`, `invoice_summary`, `oracle_data.count` = ตรงกันทั้งหมด
2. **พบข้อบกพร่องจริงของ Oracle query** — branch PO ของ `N7` ไม่มี guard และ canvas ไม่มียิง Hop 1 ทำให้ `ED6909/0837` + PO `40083989` คืน **8,359 แถว** (คำตอบที่ถูก 7 แถว) → ดู `ERR-20261003-003`
3. **Known deltas ที่จงใจคงไว้ 3 ข้อ** — รูปแบบตัวเลขในข้อความ `E15` (`10` vs `10.0`), canvas ส่ง `oracle_data.po_numbers` + `SUPPLIER_IS_INTERNAL`/`MATCHED` เผื่อไว้ (pydantic model ของ Python ตัดทิ้ง), `timestamp`

## Changes
- `N7: Oracle MCP: Hop 2 (RCV-V01)` → `parameters.jsonBody`: inline Hop 1 เป็น scalar subquery บน PO แรก (เฉพาะ Tax ID ว่าง + มีเลขที่บิล + PO ไม่ขึ้นต้น `INV`) และครอบ branch `ph.SEGMENT1 IN (...)` ด้วย `NOT EXISTS (<branch invoice>)`; คง prefix `={{`
- `N11: Code: Schema Validate` → `parameters.jsCode`: normalize `rules[]` ให้ทุกแถวมี key `code`/`severity`/`details` (null เมื่อ PASS) เท่ากับ `model_dump()` ของ `RuleResult`
- ชื่อโหนด / connections / node groups ไม่มีการแก้ไข → 31 nodes, 24 edges, 6 groups, `active: false`
- เอกสาร: `docs/workflows/n8n_flow_v6_6.md` (§3 Two-Hop แบบ inline Hop 1 + guard, §9 credential + วัน token หมดอายุ, §10 ผลตรวจจริง execution `#324`), `docs/workflows/parity_spec_matrix.md` (หลักการ D2, ตารางโหนด 13/19, §5 ผลตรวจจริง + Known deltas)

## Verification
| รายการ | ผล |
|---|---|
| Oracle จริง branch invoice | 7 แถว / GR `510522788` / 3 PO (เดิม 8,359 แถว) |
| Oracle จริง branch fallback | 4 แถว = log Python "Found 4 receipt items by PO(s) ['42052835'] (fallback)" |
| SQL ที่ render จาก payload บน canvas | ตรงกับไฟล์ที่ validate แบบ byte-identical (`cmp`) |
| n8n execution `#324` | `success`, 2.7s, `lastNodeExecuted = N14: Verification & Tagging Summary` |
| Python `tests/run_tests.py --mode offline` | SUCCESS (ALL PASSED) |

## Not Done (และเหตุผล)
1. **ย้าย Bearer token ของ `N7` ไป credential** — MCP ไม่มี tool สร้าง credential (มีแค่ `aiva-n8n_list_credentials` แบบ read-only) และการผูก credential แล้วทดสอบต้องยิง HTTP จริงซึ่งยังไม่ปลอดภัย ต้องทำใน UI; **token หมดอายุ 2026-10-28T01:57:06Z**
2. **รัน execution เต็มจริงบนเอกสารจริง** — `N12: HTTP: POST Portal` ยังชี้ `https://httpbin.org/post` การรันจริงจะ tag เอกสาร Paperless ว่า processed ทั้งที่ผลลัพธ์ไม่เข้า Portal
3. **`E11`** — เป็นการตัดสินของ Accounting ไม่ใช่โค้ด defect (ตอนนี้ทั้งสอง engine ให้เคส "คำอธิบายใกล้กันแต่ item code ต่างกัน" เป็น PASS)
4. **commit ทั้ง repo** — มีงานคู่ขนานของ agent อื่น (`TASK-012` 3-Way Pipeline) ที่ยังแก้ `app/engines/`, `tests/` ค้างอยู่ จึง commit แยกเฉพาะเอกสาร + records ของงานนี้

## Risk Notes สำหรับรอบถัดไป
- ห้ามลบ `NOT EXISTS` guard และ `={{` prefix ออกจาก `N7`
- การเทียบ parity ต้องเทียบ "จำนวนแถวที่ยิงจริง" ด้วย ไม่ใช่ดูแค่ output
- พบการใช้เลข ID ซ้ำใน `.agent/CHANGELOG.md` (`CHG-20261003-002` ถูกใช้ 2 รอบจาก 2 session) — ก่อนเพิ่ม entry ใหม่ให้ grep หา ID ที่ใช้ก่อนเสมอ
