# Session 2026-10-05-002 — Streamline System A to Core PDF Engine

- **Date:** 2026-10-05T21:12:00+07:00
- **Scope:** `OCR service/system-a-sandbox/system-a`
- **Objective:** จัดระเบียบ System A ให้เหลือเฉพาะ Core Engine สำหรับรับ PDF แล้วแปลงเป็น final result JSON (`aiva.system_a.result/3.0`) โดยย้ายชุดทดสอบและ artifacts เดิมเข้า `archive/`

## สิ่งที่ดำเนินการ
1. **จัดเก็บไฟล์ที่ไม่ใช่ Core เข้า `archive/`**:
   - ย้าย `tests/`, `sandbox_data/`, `runs/`, `reports/`, `docker/`, `scripts/`, `src/system_a/sandbox/` และ `FINDINGS.md` เข้าสู่ `archive/` ทั้งหมด
   - ป้องกันการสูญหายของผลการทดสอบเดิม ขณะที่โครงสร้างหลักสะอาดตา
2. **สร้าง `process_pdf.py`**:
   - เป็นสคริปต์หลักแบบคำสั่งเดียวจบ: `python process_pdf.py invoice.pdf [--output result.json]`
   - มีการโหลด `.env` อัตโนมัติ, เรียก Perception (Qwen Vision) พร้อมระบบ PerceptionCache
   - เชื่อมต่อ Oracle EBS จริง และประเมิน Rules V-01 ถึง V-09
   - แสดงผลสรุป Dashboard บน Terminal สวยงาม และบันทึก payload JSON contract 3.0
3. **ทดสอบใช้งานจริง**:
   - ทดสอบรันกับ `20.pdf` ผลคือรันผ่านสมบูรณ์ใน 33.6 วินาที เชื่อมต่อ Oracle EBS ได้ 12 receipt lines และออกผล recommendation `MANUAL_REVIEW`
4. **ปรับปรุงเอกสาร `README.md`**:
   - สรุปวิธีใช้งานแบบกระชับ 1 หน้า ไม่ซับซ้อน
