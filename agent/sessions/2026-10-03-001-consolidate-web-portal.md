# Session: ย้ายและรวมโครงสร้าง Web Portal ทั้งหมดเข้าสู่โฟลเดอร์ Web portal/

- Session ID: SESSION-20261003-001
- Started: 2026-10-03T09:25:00+07:00
- Ended: 2026-10-03T09:34:00+07:00
- Status: closed
- Task IDs: TASK-20261003-001

## Objective

ย้ายและรวมโครงสร้างไฟล์และโฟลเดอร์ทั้งหมดของ Web Portal จาก `invoice-web/` (frontend, backend, docs, examples, infra, tests, scripts, data, configs) และ Review Action Workflow ของ Web Portal เข้ามาอยู่ในโฟลเดอร์ `Web portal/` ตามคำสั่งของผู้ใช้ เพื่อให้โฟลเดอร์ `Web portal/` เป็นศูนย์กลางของ Web Portal ทั้งหมด และลบโฟลเดอร์ `invoice-web/` ที่ซ้ำซ้อนออก

## Baseline

- เดิมระบบมีโฟลเดอร์ `Web portal/` อยู่ที่ root แต่มีเพียงไฟล์ mockup HTML `AIVA-Web-Portal-Mockup-v4.4-Release.html`
- ตัวแอปพลิเคชันจริงของ Web Portal (React frontend, FastAPI backend, documentation, synthetic fixtures, run scripts) ถูกวางไว้ใน `invoice-web/` ที่ root แยกออกมา ทำให้โครงสร้างไม่สอดคล้องกับชื่อโฟลเดอร์ `Web portal`
- ผู้ใช้ต้องการให้รวมไฟล์และ workflow ที่เกี่ยวกับ Web Portal ทั้งหมดไว้ในโฟลเดอร์ `Web portal/`

## Summary

- ย้ายไฟล์และโมดูลทั้งหมดจาก `invoice-web/` ไปยัง `Web portal/` ด้วย `git mv` เพื่อรักษา git history:
  - `invoice-web/backend/` -> `Web portal/backend/` (รวมทั้ง `backend/app/domain/workflow/` Review Action State Machine)
  - `invoice-web/frontend/` -> `Web portal/frontend/`
  - `invoice-web/docs/` -> `Web portal/docs/`
  - `invoice-web/examples/` -> `Web portal/examples/`
  - `invoice-web/infra/` -> `Web portal/infra/`
  - `invoice-web/data/` -> `Web portal/data/`
  - `invoice-web/.env.example` -> `Web portal/.env.example`
  - `invoice-web/.gitignore` -> `Web portal/.gitignore`
  - `invoice-web/README.md` -> `Web portal/README.md`
  - `invoice-web/run-local.ps1` -> `Web portal/run-local.ps1`
- ไฟล์ mockup เดิม `Web portal/AIVA-Web-Portal-Mockup-v4.4-Release.html` ยังคงถูกเก็บไว้ใน `Web portal/` ตามเดิม
- ลบโฟลเดอร์ `invoice-web/` ออกจากระบบเรียบร้อย
- อัปเดต root `.gitignore`:
  - เพิ่ม `Web portal/data/` และ `Web\ portal/data/`
  - เพิ่ม whitelist `!Web portal/examples/invoice.pdf` และ `!Web\ portal/examples/invoice.pdf`
- อัปเดต path references ใน `Web portal/run-local.ps1`, `Web portal/README.md`, `Web portal/.env.example`, และเอกสารใน `Web portal/docs/`

## Validation

- `git check-ignore`:
  - `Web portal/data/tests/sample.sqlite3` -> ignored ถูกต้อง (ตรงกับ `Web portal/.gitignore:7:data/`)
  - `Web portal/examples/invoice.pdf` -> exit code 1 (not ignored) whitelist ทำงานถูกต้อง
- Web Portal Backend Tests:
  - รัน `unittest discover -s tests -v` ใน `Web portal/backend`: **15 passed in 6.303s** ครอบคลุม:
    - `test_cross_origin_mutation_rejected`
    - `test_filters_counts_and_pagination`
    - `test_idempotent_retry_and_conflicting_event`
    - `test_ingest_survives_new_app_instance_and_search`
    - `test_key_separation_and_protected_content`
    - `test_legacy_adapter_preserves_codes_and_missing_evidence`
    - `test_legacy_pdf_metadata_is_backfilled_into_revision_archive`
    - `test_pdf_is_archived_and_served_per_revision`
    - `test_pdf_upload_view_missing_and_revision_warning`
    - `test_project_structure_keeps_entrypoints_and_boundaries_small`
    - `test_resubmit_is_persistent_idempotent_and_completed_by_new_revision`
    - `test_review_actions_validate_reason_note_state_and_version`
    - `test_revision_history_and_stale_protection`
    - `test_schema_validation_and_redacted_errors`
    - `test_workspace_audit_can_be_searched_filtered_and_paginated`
- OCR Service Regression Tests:
  - รัน `pytest -q` ใน `OCR service/n8n`: **9 passed, 6 deselected in 5.22s** (ไม่มีผลกระทบต่อ OCR service)
