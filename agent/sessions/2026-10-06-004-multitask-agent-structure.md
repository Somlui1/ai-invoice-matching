# Session 2026-10-06-004: Multi-Task Sub-Agent Architecture & Task Isolation

- **Timestamp**: 2026-10-06T09:29:00+07:00
- **Task ID**: TASK-20261006-004
- **Changelog ID**: CHG-20261006-004
- **Scope**: OCR service/system-a-sandbox/.agent, agent.md, task.md, TASK_WEB_TEST_PORTAL.md

## Context & Motivation
เมื่อมีงานหลายประเภททำงานอยู่ใน sandbox เดียวกัน (เช่น Evaluation Loop ใน task.md และ Web Testing Portal ใน TASK_WEB_TEST_PORTAL.md) การใช้พื้นที่เก็บสถานะ .agent/ ร่วมกันแบบ flat ทำให้เกิดปัญหา:
1. State overwriting ใน state.json
2. Backlog ปนกันใน todo.md
3. ความเสี่ยง Git Rollback จาก loop ใน task.md ล้างโค้ดของ web portal ที่กำลังพัฒนา
4. Guardrails และ Allowed search space ของแต่ละงานขัดแย้งกัน

## Changes Made
1. **สร้างระบบ Task Namespace ใน .agent/tasks/**:
   - .agent/tasks/core-optimization/ (state.json, todo.md, progress.md, recovery.md, README.md)
   - .agent/tasks/web-test-portal/ (state.json, todo.md, progress.md, recovery.md, README.md)
   - .agent/tasks/_template/ (แม่แบบสำหรับ task ใหม่ในอนาคต)
2. **แปลง .agent/state.json เป็น Central Multi-Task Registry**:
   - ชี้ตำแหน่งสถานะและ allowed_paths ของแต่ละ task
   - กำหนดกฎ subagent_protocol ชัดเจน
3. **ปรับปรุง Protocol ใน agent.md, task.md, TASK_WEB_TEST_PORTAL.md**:
   - agent.md: กำหนดกติกา Task Isolation ให้ Sub-Agents อ่าน/เขียนสถานะเฉพาะในโฟลเดอร์ของ task ตนเอง
   - task.md: ชี้ state, todo, progress, recovery ไปยัง .agent/tasks/core-optimization/
   - TASK_WEB_TEST_PORTAL.md: ชี้ state, todo, progress ไปยัง .agent/tasks/web-test-portal/

## Verification
- โครงสร้างโฟลเดอร์และไฟล์ทั้งหมดถูกสร้างและทดสอบการเข้าถึง
- .agent/state.json ตอบสนองในฐานะ dispatcher
- เครื่องมือทดสอบเดิมยังคงใช้งาน baseline, harness, cache ร่วมกันได้อย่างถูกต้อง
