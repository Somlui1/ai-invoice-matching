# Session: 2026-10-07-002 - Clean Unnecessary Files Out of src/test-portal

- **Date**: 2026-10-07T08:32:00+07:00
- **Goal**: ตอบคำถามว่า `src/test-portal/tests` และ `data` จำเป็นต่อการรัน web หรือไม่ และลบเฉพาะไฟล์ที่จำเป็นน้อยออกจริง

## Investigation (read-only)
1. **Which files the portal really needs** — AST import closure over `webapp/` + `tests/`:
   - the portal imports 23 modules of `system_a` (`container`, `envfile`, `domain.*` (incl. `v08`), `application.*`, `perception.{vision_pipeline,pdf_ingest,coords,text_layer}`, `adapters.{llm,oracle,paperless}`, `api.app` for the HTTP engine only);
   - `system_a/cli.py`, `sandbox/*`, `perception/vlm_extractor.py`, `perception/cache.py` are never imported by the portal;
   - outside the package System A reads `<SYSTEM_A_HOME>/config/standards/v6.6/*.yaml` (always), `config/prompts/vision_*.md` (`PERCEPTION=live`), `config/prompts/v05/v07/v08*.md` (`SYSTEM_A_AI_MODE=litellm`), `schemas/result-3.0.schema.json` (HTTP engine) and optionally `sandbox_data/oracle_dataset.json` (sandbox).
2. **`tests/` is necessary** - 93 tests (`make test`) + `tests/e2e_browser.py` (21 checks in Chromium); `tests/system_a_stub/config/**` is the stub Standard that `tests/conftest.py` copies next to the real `system_a`, so the suite runs without the real Standard/Oracle/documents.  It is the portal's only regression net.
3. **`data/` is not necessary** - written by `ResultStore` only (`mkdir(parents=True, exist_ok=True)` in `__init__`), every test uses `data_dir=tmp_path/...`, `WEBAPP_PERSIST=false` in the live `.env`, no file in the repository references `src/test-portal/data`, and the two folders on disk (`doc_23`, `doc_24`) were leftovers of earlier runs.
4. **No dead module** - each of the 16 modules in `webapp/` is imported at least once by the app or the suite.

## Work Performed
1. Deleted `src/test-portal/data/` (190 KB: `results/doc_23/`, `results/doc_24/` - `state/view/payload/extraction.json`).
2. Deleted `src/test-portal/.pytest_cache/`, `src/test-portal/webapp/__pycache__/`, `src/test-portal/tests/__pycache__/`.
3. Kept `tests/`, `pytest.ini`, `requirements-dev.txt` and every `webapp/` file; `.env` / `.env.example` untouched (the local `.env` holds the Paperless token).
4. `.venv/` (105 MB, gitignored) was left in place - `run.bat` recreates it from `requirements.txt` when missing.

## Verification
- `python -m pytest -q` in `src/test-portal`: **93/93 passed** (before and after the cleanup, 9-10 s, run with the machine Python because `.venv` has no `pytest`).
- `ResultStore(Path('data'))` re-creates `data/results` on its own and returns `ids() == []`, so deleting the folder cannot break a start; the empty folder was removed again afterwards.
- Folder size: 106 MB → 105 MB; remaining content is 16 `webapp/*.py`, 2 static assets, 8 test files + stub config, and the 7 support files (`run.bat`, `run.sh`, `Makefile`, `README.md`, `requirements*.txt`, `pytest.ini`, `.env*`, `.gitignore`).

## Follow-up (not done)
- `python -m pip install -r requirements-dev.txt` inside `src/test-portal/.venv` would let `make test` run from the venv.
- `webapp/pdfkit.py` and `system_a/perception/pdf_ingest.py` still use the deprecated `fitz` alias (`warning: The fitz API is deprecated`), fine for now.
