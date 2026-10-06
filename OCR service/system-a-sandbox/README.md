# System A — Core Invoice Matching Engine

เครื่องยนต์ประมวลผลและตรวจสอบใบแจ้งหนี้/ใบกำกับภาษีอัตโนมัติ (AIVA System A) ตามมาตรฐาน **AH-IT-DOC-PO-INV-Matching-Standard v6.6**
ทำหน้าที่รับไฟล์ PDF เข้ามา สกัดข้อมูลด้วย AI Vision ตรวจเทียบกับใบรับสินค้าใน Oracle EBS และประเมินผลการตรวจสอบออกมาเป็น JSON (`aiva.system_a.result/3.0`) พร้อมคำแนะนำ (Recommendation)

---

## 🚀 วิธีใช้งานด่วน (Quick Start)

### 1. ประมวลผลไฟล์ PDF เดี่ยว (Command-Line)
สคริปต์ `process_pdf.py` เป็นจุดเริ่มต้นหลักสำหรับการรันเอกสาร:

```bash
# ประมวลผลและแสดงผลสรุปบนหน้าจอ
python process_pdf.py path/to/invoice.pdf

# ประมวลผลและบันทึกผลลัพธ์เป็นไฟล์ JSON
python process_pdf.py path/to/invoice.pdf --output result.json

# แสดงเฉพาะผลลัพธ์ JSON ออกทาง stdout (สำหรับต่อท่อคำสั่งหรือ API)
python process_pdf.py path/to/invoice.pdf --json-only
```

### 2. รันเป็น REST API Service (FastAPI)
หากต้องการเปิดเป็น Web Service สำหรับรับไฟล์ผ่าน HTTP:

```bash
uvicorn system_a.api.app:app --host 0.0.0.0 --port 8080
```
* **Swagger UI / API Docs**: เปิดเบราว์เซอร์ไปที่ `http://localhost:8080/docs`
* **Endpoint หลัก**: `POST /v1/validations`

---

## 📁 โครงสร้างโปรเจกต์ (Core Structure)

โปรเจกต์ถูกจัดระเบียบให้มีเฉพาะส่วนประกอบหลักที่จำเป็นในการทำงาน:

```
system-a/
├── process_pdf.py          # ⭐️ สคริปต์หลัก: รับไฟล์ PDF แล้วแปลงเป็น final result 3.0 ทันที
├── .env                    # คอนฟิกการเชื่อมต่อระบบจริง (Oracle MCP, LiteLLM GB300, Paperless)
├── pyproject.toml          # กำหนด Dependencies และ Package Metadata
├── config/                 # ค่าคอนฟิกมาตรฐานทางธุรกิจ
│   ├── standards/v6.6/     # กฎการแมตช์, Tolerance, UOM Groups, Buyer Entity (Table 4)
│   └── prompts/            # Prompt templates สำหรับ AI (V-05, V-07, V-08)
├── schemas/                # Contract schemas (result-3.0.schema.json)
├── src/system_a/           # 📦 โค้ด Core ทั้งหมดของระบบ
│   ├── domain/             # Business Logic บริสุทธิ์: กฎ V-01..V-09, Line Matching, Normalization
│   ├── perception/         # OCR & Bounding Box: แปลง PDF และเรียก Qwen Vision
│   ├── application/        # Orchestrator: จัดการ Pipeline (Step 1 -> Gate -> Step 2 -> Step 3)
│   ├── adapters/           # ตัวเชื่อมต่อภายนอก (Oracle EBS MCP, LiteLLM, Paperless)
│   └── api/                # FastAPI Application & Endpoints
└── archive/                # 🗄️ แฟ้มสำรอง: เก็บชุดทดสอบเดิม (tests/, sandbox_data/, runs/, reports/)
```

---

## ⚙️ ขั้นตอนการทำงานภายใน (Pipeline)

เมื่อส่งไฟล์ PDF เข้าสู่ระบบ `process_pdf.py`:
1. **Perception (OCR + Layout + BBox)**:
   - แปลงหน้า PDF และส่งให้ Vision Model (Qwen บน GB300) สกัดข้อความและพิกัด Bounding Box
   - จัดเก็บแคชผลลัพธ์ไว้ที่ `.cache/` เพื่อความรวดเร็วเมื่อรันไฟล์เดิมซ้ำ
2. **Oracle EBS Verification (Step 2)**:
   - นำเลข PO / เลข Invoice / Tax ID ที่ได้ ค้นหาใบรับสินค้าจาก Oracle EBS ผ่าน Oracle MCP (`RCV-V01` หรือ `RCV-V02`)
3. **Rules Evaluation & Matching (Step 1 & 3)**:
   - ตรวจความครบถ้วนของฟิลด์ (V-01), ตรวจสอบตารางรายการสินค้า (V-02), ตรวจเลขคณิต (V-03)
   - ตรวจสอบความถูกต้องของใบรับสินค้า (V-04), ตรวจ Entity ผู้ซื้อ (V-05), ตรวจสถานะใบรับ (V-06)
   - ทำ Line Matching จับคู่แถวสินค้า Invoice ↔ Receipt (V-07)
   - ตรวจสอบปริมาณและ Tolerance สินค้า (V-08) และยอดเงินรวม (V-09)
4. **Final Recommendation**:
   - ประเมินผลลัพธ์เป็น: `AUTO_PASS` | `REVIEW` | `HOLD` | `MANUAL_REVIEW` | `SYSTEM_ERROR`
   - บันทึกผลลัพธ์และรหัส Exception (E01–E15) ตามมาตรฐาน v6.6
