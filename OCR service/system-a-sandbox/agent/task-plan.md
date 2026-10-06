# Task and Plan

## Task: Create Batch Test Script for System A against Paperless Documents with Tag 'invoice'

- **Started At**: 2026-10-06T14:01:00+07:00
- **Completed At**: 2026-10-06T14:05:00+07:00
- **Status**: Completed

### Goals & Acceptance Criteria
1. **Target**: Create batch testing script `scripts/test_paperless_invoices.py` that exercises `src/system_a`. [Completed]
2. **Document Discovery**:
   - Query Paperless-ngx API for all documents tagged `invoice` (tag ID 5, case-insensitive). [Completed - 98 documents found]
3. **Execution & Resiliency**:
   - Process each document through System A (Perception VLM + Oracle EBS + Rules V-01..V-09). [Completed]
   - Support execution modes (`production` and `sandbox`). [Completed]
   - Support `--limit`, `--skip-existing`, `--tag`, `--out-dir`, `--quick`, `--doc-id`. [Completed]
   - Fault-tolerant: errors on individual documents are captured in summary and do not halt the entire batch. [Completed]
4. **Result Storage**:
   - Save full final Contract 3.0 result for each document as a JSON file (`DMS-{id}_result.json`). [Completed]
   - Save batch summary JSON (`summary.json`) and display a clear terminal summary table. [Completed]
5. **Testing & Verification**:
   - Verified dry-run / sample test (`python scripts/test_paperless_invoices.py --mode sandbox --limit 1 --quick --out-dir results/test_run`). [Completed - verified JSON payload and summary]
   - Verified `--skip-existing` execution. [Completed]
   - Created convenience batch launcher `scripts/run_test_invoices.bat`. [Completed]
