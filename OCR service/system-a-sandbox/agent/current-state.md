# System A Current State

## System Architecture Snapshot
- **Core Engine**: `system-a/process_pdf.py` executing Contract 3.0 verification pipeline (`system_a.perception`, `system_a.application.orchestrator`, `system_a.domain`).
- **Batch Test Tooling**: `scripts/test_paperless_invoices.py` and `scripts/run_test_invoices.bat` for automated testing across all Paperless-ngx documents with tag `invoice`, generating individual Contract 3.0 JSON results and batch summary JSON.
- **Web Testing Portal**: FastAPI backend (`web/app.py`, `web/catalog.py`, `web/engine.py`) and Vanilla JS/CSS frontend (`web/static/index.html`, `web/static/styles.css`, `web/static/js/*`).
- **Integration Points**: Paperless-ngx (DMS document catalog & download), LiteLLM / Qwen vision (perception/OCR/layout/bboxes), Oracle EBS MCP gateway (RCV receipts).

## Verified Status (Updated: 2026-10-06T13:50:00+07:00)
- `web/test_portal.py`: 32/32 tests passed (100%).
- `web/test_ui_logic.mjs`: All checks passed.
- `python -m webapp check`: Connected live to Paperless-ngx DMS (`http://dms.aapico.com/api/documents/`).
- **Document Stream**: Left panel queries documents directly from Paperless-ngx live API.
- **Pre-Process (ก่อน process)**:
  - Selecting any document clears all BBoxes (`Overlay.setLayers([])`, `Overlay.render([])`).
  - Middle panel displays clean PDF/page image with **zero BBoxes**.
  - Right panel displays unverified state ("ยังไม่ได้ประมวลผล — กดปุ่ม 'ประมวลผลเอกสาร'").
  - Server results from past runs are NOT auto-loaded upon document selection.
- **Process & Post-Process (หลัง process)**:
  - Middle panel features prominent "▶ ประมวลผลเอกสาร" button.
  - When pressed, runs live System A processing pipeline.
  - Once complete, renders freshly extracted BBoxes onto the document and displays Final Result + OCR Result + Validate Result in right panel.
  - BBox display has a master toggle button (`👁️ แสดง/ซ่อน BBox`) and layer chips.
- **Browser-Only Storage (เก็บ case ไว้ที่ browser เท่านั้น)**:
  - All verified cases stored in client `localStorage` (`CaseStore`).
  - Left panel provides "เคสในเบราว์เซอร์" tab with list, export JSON, import JSON, and clear cases.
