# Session: 2026-10-07-001 - Fix Test Portal SYSTEM_A_HOME Path

- **Date**: 2026-10-07T08:24:00+07:00
- **Goal**: Resolve `run.bat` failure in `src/test-portal` complaining of missing `system_a` package.

## Work Performed
1. **Diagnosis**:
   - Error: `no system_a package under C:\Users\wajeepradit.p\git\Invoice-auto-matching\OCR service\system-a-sandbox\system-a`.
   - `run.bat` already calls `.venv\Scripts\activate.bat`. The issue was not lack of virtual environment activation, but an incorrect path in `src/test-portal/.env`.
   - `SYSTEM_A_HOME` had an unnecessary trailing `/system-a`.
2. **Fixes**:
   - `src/test-portal/.env`: Updated `SYSTEM_A_HOME=C:/Users/wajeepradit.p/git/Invoice-auto-matching/OCR service/system-a-sandbox`.
   - `src/test-portal/webapp/config.py`: Added parent and root sandbox fallback candidate scanning to `ensure_system_a()`.
   - `src/test-portal/tests/conftest.py`: Added automatic `.env` loading and sandbox fallback to `_find_package()`.
3. **Verification**:
   - `python -m webapp check` passed with code 0 (connected to Paperless live API: 99 documents, 424 pages).
   - `pytest -q` in `src/test-portal` passed 93/93 tests.
   - Root `pytest -q` passed 36/36 tests.
