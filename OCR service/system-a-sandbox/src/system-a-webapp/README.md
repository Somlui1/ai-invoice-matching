# AIVA System A test application

A web application for testing **OCR + validation** on a batch of documents: pick a document, press **Process**,
see the bounding boxes on the page and the **Final Result** / **Verify Result** from System A next to it.

It lives in its own folder and uses **System A as a library** (`SYSTEM_A_HOME`); nothing of System A is copied here.
The screen is the layout of the existing `report.html` (same CSS, same toolbar, same hover / pin behaviour) with one
new button (**Process**) and the result blocks placed inside the existing right-hand panel.

```
report.html + docs/doc_<id>/page_<n>.jpg            (the OCR batch)
          │
   BatchSource ─────────── document list, page images, "open on PDF" links
          │
   Perception ──┬─ replay: OCR items of the batch  ─► aiva.extraction/2.0
                └─ live:   VisionPipeline (Qwen-VL) on the PDF ─► aiva.extraction/2.0
          │
   Engine ──────┬─ inprocess: system_a.application.orchestrator.validate()
                └─ http:      POST /v1/validations → poll → GET result
          │
   aiva.system_a.result/3.0 ──► view builder ──► JSON for the screen (boxes, Final, Verify)
          │
   DocumentService: one state machine per document, results stored per document
          │
   FastAPI  +  static/index.html + app.js
```

## Quick start

```
copy .env.example .env          # then edit BATCH_REPORT and SYSTEM_A_HOME
python -m pip install -r requirements.txt
python -m webapp check          # reads report.html: documents, pages, items, missing images
python -m webapp serve          # http://127.0.0.1:8090/
```

`run.bat` (Windows) / `run.sh` does the same.  **Run `check` first on a new batch**: it parses the report with
the same code the application uses and tells you what it found.

No batch yet?  `python -m webapp demo --out sample_batch` writes a small synthetic batch addressed to the buyer of
your System A Standard and prints the two lines to add to `.env`.

## What the screen does

| Step | Behaviour |
|---|---|
| 1 | Every document of the batch is listed in the left panel (dot colour = state: grey idle, orange processing, green / red result). |
| 2 | Selecting a document shows its pages in the middle. No boxes yet. |
| 3 | **Process** → *Processing…* with the current step and a running timer (toolbar, document header, right panel). |
| 4 | When finished the boxes are drawn on the page from the detected coordinates (`bbox_norm`, colour = type). |
| 5 | Right panel: **Final Result** (normalised fields, item lines, signatures, recommendation, Oracle lookup) and **Verify Result** (V-01 … V-09 with evidence). Clicking a row pins the box it came from. |
| 6 | Select another document and Process it; **Process ใหม่** runs the selected one again (run 2, 3 …). |
| 7 | Results are kept per document: processing two documents at once is allowed, each keeps its own result, and results survive a reload and a restart. |

Everything else of the original report still works: *มุมมอง*, ◀ ▶ and the arrow keys, type / status filters, text search
(also inside the OCR text of processed documents), *ตาราง*, *แสดงที่ตัดทิ้ง*, *กรอบโต้ตอบ*, hover tooltip, click to pin, Esc.
If a page JPG is not on disk, a stand-in page is drawn from the OCR text so the boxes can still be checked.

## Configuration (`.env` or environment)

| Variable | Default | Meaning |
|---|---|---|
| `BATCH_REPORT` | – | `report.html`, or the folder that contains it. Page images are read relative to it. |
| `SYSTEM_A_HOME` | – | Folder of the System A project (has `src/system_a` and `config/`). **Always required.** |
| `SYSTEM_A_ENGINE` | `inprocess` | `inprocess` or `http`. |
| `SYSTEM_A_URL`, `SYSTEM_A_API_KEY`, `SYSTEM_A_HTTP_TIMEOUT` | `http://127.0.0.1:8080`, – , `300` | `http` engine only. |
| `PERCEPTION` | `replay` | `replay` or `live` (see below). |
| `REPLAY_ASSUME_AGREEMENT`, `REPLAY_CONFIDENCE` | `true`, `0.97` | replay only. |
| `PDF_DIR` | – | live: folder of PDFs (`doc_<id>.pdf` or `<title>.pdf`). |
| `WEBAPP_ORACLE_DATASET` | `<SYSTEM_A_HOME>/sandbox_data/oracle_dataset.json` | in-process **sandbox** only. |
| `WEBAPP_HOST`, `WEBAPP_PORT`, `WEBAPP_WORKERS`, `WEBAPP_DATA_DIR` | `127.0.0.1`, `8090`, `4`, `./data` | the application. |

In-process, System A reads **its own** settings (`SYSTEM_A_MODE`, `SYSTEM_A_AI_MODE`, `ORACLE_BACKEND`, `ORACLE_MCP_URL`,
`LITELLM_URL` …) from the same environment, so one `.env` configures both.  `SYSTEM_A_MODE=production` + the Oracle
variables makes **Process** validate against the real Oracle through System A's own adapter.

### Perception: replay or live

* **replay** – the OCR engine already read this batch; its items (type, label, text, box) become System A's input,
  using System A's own label table and helpers (`LABEL_TO_FIELD`, `extract_value`, `group_documents`,
  `drop_duplicate_copies` …).  Fast, no GPU, ideal to exercise the validation rules on a whole batch.
  What replay cannot claim, and records in `extra.replay` of the extraction:
  * a batch item has **one reader**; System A would mark every such field *not agreed* and V-01 would report E01 for
    all of them.  `REPLAY_ASSUME_AGREEMENT=true` treats the single read as agreed (with `REPLAY_CONFIDENCE` when the
    batch has no confidence); `false` reproduces System A's strict behaviour.
  * the batch has **row boxes, not column boxes**.  Qty / unit / unit price / amount are parsed from the printed row
    (`webapp/extraction.py: parse_row`, 3 money columns are resolved by `qty × price = amount`).  A row that does not
    parse is **not guessed**: it is skipped and listed in `extra.replay.skipped_rows`.
  * field choice among several candidates uses small, documented heuristics (first value of the right shape on the
    invoice pages; the largest amount for `grand_total`; split address boxes are joined).
* **live** – System A's `VisionPipeline` reads the document (page items, classification votes, table rows, crop re-reads)
  and produces the extraction itself; this is the production path.  The PDF comes from `PDF_DIR` / `docs/doc_<id>/`;
  with none, the page JPGs of the batch are wrapped into a PDF so the pipeline can still run.  Needs `LITELLM_URL`.

## HTTP API

| | |
|---|---|
| `GET /api/meta`, `GET /api/health` | wiring, engine health (503 if the engine is down) |
| `GET /api/documents` | all documents with state (`idle / processing / done / error`), run, recommendation |
| `GET /api/documents/{id}` | one document's state (poll this) |
| `POST /api/documents/{id}/process` | start → `202`; `409` if that document is already running |
| `GET /api/documents/{id}/result` | OCR items + boxes per page, Final Result, Verify Result (`409` until done) |
| `GET /api/documents/{id}/payload` | the raw `aiva.system_a.result/3.0` |
| `GET /api/documents/{id}/extraction` | the `aiva.extraction/2.0` that was sent to System A |
| `DELETE /api/documents/{id}/result` | forget the result of that document |
| `GET /api/documents/{id}/pages/{n}/image` | the page JPG, or the stand-in SVG |
| `GET /api/search?q=` | ids of processed documents whose id / title / OCR text contains `q` |

Interactive docs: `/docs`.

### Per-document isolation

* a document is processed by one job at a time (a second `process` → 409); different documents run side by side;
* each `process` raises `run` and clears the previous result **before** the new run starts, and a job may only write
  its outcome while its `run` is still current, so a result is never a mixture of runs or documents;
* results are files under `data/results/doc_<id>/{state,view,payload,extraction}.json`, written atomically; a run that
  was interrupted by a restart is shown as an error, never as a result.

## Tests

```
set SYSTEM_A_HOME=C:\path\to\system-a
python -m pip install -r requirements-dev.txt
python -m pytest -q                 # 82 tests
python tests/e2e_browser.py         # 21 checks in a real browser (needs: playwright install chromium)
```

The tests copy System A's package from `SYSTEM_A_HOME` next to a **stub Standard** (`tests/system_a_stub/config`,
reconstructed so that all 29 sandbox scenarios of System A pass) and use a **synthetic batch**, so they do not depend
on your real Standard, Oracle or documents.  They cover: report parsing, the replay adapter, in-process vs HTTP
engine giving the same payload hash, the per-document state machine (concurrency, busy, failure, stale run, restart),
every endpoint, the original CSS being untouched, live perception with a fake VLM, and the whole 7-step workflow in Chromium.

## Known limits

* **Security:** no authentication; it binds to `127.0.0.1`. Do not expose it as is.
* **Replay is a test aid** (see above): results show how System A's *rules* behave on the batch's OCR, not how the
  OCR itself performs. Use `PERCEPTION=live` for that.
* The **live** path is tested with a fake VLM only (no GPU / LiteLLM / Paperless in the test environment).
* Process runs in the application's process; a restart interrupts running jobs (they are reported as errors).
