# Session: 2026-10-06-003 - Batch Test Paperless Invoices

- **Date**: 2026-10-06T14:05:00+07:00
- **Goal**: Develop a batch test script for `system_a` that queries all documents tagged `invoice` from Paperless-ngx, verifies each document, and saves the final result of each case as a JSON file along with a consolidated summary.

## Work Performed
1. **Created Batch Test Script**:
   - File: `scripts/test_paperless_invoices.py`
   - Dynamically resolves tag `invoice` using Paperless-ngx API (found tag ID 5, containing 98 documents).
   - Downloads each document and executes System A verification pipeline (`process_pdf.py`).
   - Saves each document's full Contract 3.0 result JSON to `<out_dir>/DMS-<id>_result.json`.
   - Generates consolidated summary JSON at `<out_dir>/summary.json` containing total documents, execution duration, recommendation counts (`AUTO_PASS`, `REVIEW`, `HOLD`, `MANUAL_REVIEW`, `SYSTEM_ERROR`), and rule pass/fail breakdowns (`V-01` to `V-09`).
   - Supports CLI flags: `--tag`, `--mode production|sandbox`, `--limit`, `--skip-existing`, `--quick`, `--doc-id`, `--out-dir`.
2. **Created Launcher**:
   - File: `scripts/run_test_invoices.bat` for easy CLI execution on Windows.
3. **Verification**:
   - Ran `python scripts/test_paperless_invoices.py --mode sandbox --limit 1 --quick --out-dir results/test_run`.
   - Verified that `DMS-15_result.json` and `summary.json` were written and contain the complete Contract 3.0 schema.
   - Tested `--skip-existing` flag to verify caching logic.
