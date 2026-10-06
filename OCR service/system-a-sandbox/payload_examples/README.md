# เปรียบเทียบตัวอย่าง Final Payload: OCR_rule vs System A

โฟลเดอร์นี้เก็บตัวอย่างไฟล์ผลลัพธ์ (Final Payload) ของทั้ง 2 ระบบเพื่อใช้ในการอ้างอิง เปรียบเทียบโครงสร้าง และนำไปใช้เชื่อมต่อระบบหน้าบ้าน (AIVA Web Portal):

---

## 📁 รายการไฟล์ตัวอย่าง

1. [`01_legacy_ocr_rule_table9_payload.json`](file:///c:/Users/wajeepradit.p/git/Invoice-auto-matching/OCR%20service/system-a-sandbox/system-a/payload_examples/01_legacy_ocr_rule_table9_payload.json)
   * **ระบบ**: `OCR_rule/main.py` (Standard v6.2 / Schema Table 9 v1.5)
   * **รูปแบบ Envelope**: `VerificationResponse` ครอบ `Table9Output`
   * **ลักษณะสำคัญ**:
     * มีฟิลด์ด้าน Workflow: `decision.assigned_to` (`accounting`)
     * มีฟิลด์แก้ไขสถานะใน DMS: `paperless_update`
     * **ไม่มี Bounding Box (BBox)**: ไม่สามารถชี้ตำแหน่งบน PDF ได้
     * ใช้รหัสข้อยกเว้นรุ่นเก่า (เช่น E28)

2. [`02_modern_system_a_result_3_0_payload.json`](file:///c:/Users/wajeepradit.p/git/Invoice-auto-matching/OCR%20service/system-a-sandbox/system-a/payload_examples/02_modern_system_a_result_3_0_payload.json)
   * **ระบบ**: `system-a` (Standard v6.6 / Contract `aiva.system_a.result/3.0`)
   * **รูปแบบ Contract**: Defined by JSON Schema `schemas/result-3.0.schema.json`
   * **ลักษณะสำคัญ**:
     * **Pure Recommendation (X-04)**: ให้คำแนะนำเท่านั้น (`MANUAL_REVIEW`, `AUTO_PASS`, `REVIEW`, `HOLD`) ไม่มีคีย์ Workflow หรือการ Assign คน
     * **BBox ครบทุกระดับ**: มีพิกัด Normalize `[x, y, w, h]` (0–1) ครบทั้ง Page, Field, Row, Cell, Signature
     * **Evidence Traceability**: ทุกข้อผิดพลาดมี `evidence` ผูกกับ BBox และ `related_element_ids` ชี้เป้าบน PDF ได้ทันที
     * **Line Matching Groups**: มีโครงสร้าง `1:1`, `1:N`, `N:1` พร้อม Level (M1–M5) และ AI Rationale
     * **Oracle Snapshot**: มี `lookup_path` (`RCV-V01`), รายการใบรับ, และ `fingerprint` SHA-256
     * **Data Integrity**: มี `integrity.payload_sha256` ล็อคความถูกต้องของผลลัพธ์ ป้องกันการดัดแปลงข้อมูล

---

## 🔍 ตารางเปรียบเทียบคีย์หลักใน JSON

| หมวดหมู่ข้อมูล | `OCR_rule` (Table 9 v1.5) | `system-a` (Result 3.0) |
|---|---|---|
| Contract Version | `standard_version: "6.6"`, `schema_version: "1.5"` | `contract: "aiva.system_a.result/3.0"` |
| ผลการตัดสินใจ | `decision.status`, `decision.assigned_to` | `recommendation.value`, `recommendation.max_severity` |
| Bounding Boxes | ❌ ไม่มี | ✅ `ocr.elements[].bbox`, `evidence[].bboxes` |
| รหัส Exception | โค้ดรุ่นเก่า (E09, E28, E35 ฯลฯ) | รหัสมาตรฐานใหม่ **E01 ถึง E15** |
| การจับคู่บรรทัดสินค้า | Flat list (ไม่มี Relation type) | `line_matching.groups[]` (1:1, 1:N, N:1, Level M1..M5) |
| ข้อมูล Oracle EBS | `oracle_data.receipts[]` | `oracle_snapshot` (มี fingerprint, lookup_path, receipt_lines) |
| การตรวจสอบความถูกต้อง | ❌ ไม่มี | ✅ `integrity.payload_sha256` |
