# AIVA System A test portal

A small web application for testing **System A only**.  Pick a real document of the DMS, press **Process**, and
System A runs end to end on that document's own file; the screen then shows the boxes and the verdict taken from
**System A's own final payload** — `aiva.system_a.result/3.0`.

* the document list and the document files come from **real Paperless**, through System A's own read-only reader;
* every box drawn on the page is one element of `ocr.elements[]` in that payload, placed with its own `bbox`;
* every number and word on the right is `normalized_fields`, `line_matching`, `rule_results`, `exceptions`,
  `evidence`, `recommendation` of the same payload — the portal computes nothing of its own and keeps no second
  coordinate system;
* if System A raises, the document shows that exception and its traceback.  There is **no fallback and no partial
  result by design**: a failed run leaves the document in `error`.

System A is used **as a library** (`SYSTEM_A_HOME`).  Nothing of System A is copied into this folder; the only
thing this portal owns is the list/filter of documents, the screen, and the state machine around one document.

```
Paperless (real DMS, tag=invoice) ──► catalog.py  ── list of documents, page images, the document's own file
                                       (system_a.container.build_paperless)
                                              │
   Process  ──► engine.py ──┬─ inprocess: process_pdf.process_pdf(dms_id=…)   ← System A's own entrypoint
                             └─ http:      read here (container.build_perception) → POST /v1/validations → poll
                                              │
                                     aiva.system_a.result/3.0   (stored byte-for-byte as payload.json)
                                              │
   view.py  ──► the screen model: pages, elements (bbox), final fields, lines, signatures, rules, exceptions
                                              │
   service.py ── one state machine per document (idle / processing / done / error, run number)
              └─ store.py ── data/results/doc_<id>/{state,view,payload}.json
                                              │
   app.py (FastAPI) + static/index.html + static/app.js (HTTP + polling, no WebSocket)
```

## Quick start

```
copy .env.example .env         # then set PAPERLESS_*, SYSTEM_A_HOME (+ keep SYSTEM_A_* as you need them)
python -m pip install -r requirements.txt
python -m webapp check         # what System A will load (mode, Standard, models) and which DMS/documents
python -m webapp serve         # http://127.0.0.1:8090/
```

`run.bat` (Windows) / `run.sh` do the same.  **Run `check` first** — it uses the same code path the application
uses, so what it prints is what the screen will see.

Both scripts call **their own** `.venv` interpreter by full path — never `activate` — so an already active venv or
a moved project folder cannot make them start with another Python (a stale `activate.bat` silently leaves `python`
pointing at whatever is first in `PATH`).  `serve` starts uvicorn with `ws="none"`: the screen talks HTTP +
polling only, so the optional `websockets` package is not needed and cannot break the start.

## What the screen does

| | |
|---|---|
| 1 | The left panel lists the documents of the DMS that carry the tag (`PAPERLESS_TAG`). Dot / label = state: `idle`, `processing`, then the recommendation (`AUTO_PASS` green, `MANUAL_REVIEW` orange, `HOLD`/`REJECT` red) or `error`. |
| 2 | Selecting a document shows its pages — the real page images rendered by System A's ingest at `WEBAPP_RENDER_DPI`. |
| 3 | **Process** runs System A on that document: Paperless download → ingest → VisionPipeline → Oracle → rules V-01…V-09 → payload. The strip shows the elapsed time; you can select and wait on other documents meanwhile. |
| 4 | The boxes appear on top of the page. Each box **is** a payload element: its position is `bbox` unchanged, its colour is its `element_type`, its label is its `field_name`. |
| 5 | The type chips above the page choose which element types are drawn (`field`, `row`, `signature`, `stamp` by default; `cell`, `section`, `table`, `word` are opt-in because there are many of them). The choice is remembered in the browser. |
| 6 | Right panel: **Final Result** (recommendation + reasons, the Oracle lookup, the final fields, signatures, the line table with the group System A matched each line to, the totals summary) and **Verify Result** (V-01…V-09, each with its evidence, exception codes and the `element_id`s the evidence names), then the element table per page. |
| 7 | Hovering a row or an `[element_id]` highlights the box on the page; clicking pins it. Esc / clicking again unpins. Search finds the id / title, and inside a processed document the words of the payload. |
| 8 | **ลบผล** deletes that document's result (server and browser). Process again for run 2, 3 … — a new run clears the old result before it starts. |

Processed cases are kept in the browser (`localStorage`, last 12), so restarting the server does not lose what you
were looking at; with `WEBAPP_PERSIST=true` they are also stored on the server per document and are re-fetched.

## The two engines (`SYSTEM_A_ENGINE`)

| | what runs where |
|---|---|
| `inprocess` (default) | this process calls System A's own entrypoint `process_pdf.process_pdf(dms_id=…)` — the same call `scripts/test_paperless_invoices.py` makes. One process, nothing else to start. |
| `http` | the reading (Paperless file → `container.build_perception` → `aiva.extraction/2.0`) happens here, because System A's API does not ingest a package itself (`POST` with only `package` answers 501); the validation — Oracle, AI judges, rules, payload assembly — runs on a System A server: `POST /v1/validations` → poll `GET /v1/validations/{id}` → `GET …/result`. |

Start the server for the `http` engine from `<SYSTEM_A_HOME>`:

```
python -m system_a.cli serve --port 8080
```

Note that its own process reads its own environment: to validate against the real Oracle it must be started with
the production variables of `<SYSTEM_A_HOME>/.env` exported (the CLI does not load `.env` by itself).

Both engines must yield the same payload; `tests/test_engine.py` proves it, including a run against System A's real
API app mounted in-process.

## Configuration (`.env` or environment)

| Variable | Default | Meaning |
|---|---|---|
| `PAPERLESS_BASE_URL`, `PAPERLESS_API_TOKEN` | – | the DMS. Used by System A's reader (read-only `GET` only). |
| `PAPERLESS_TAG` | `invoice` | tag whose documents are listed. |
| `PAPERLESS_LIMIT` | `200` | how many documents the left panel lists. |
| `SYSTEM_A_HOME` | – | the System A project folder (`src/system_a`, `config/`, `process_pdf.py`). **Always required.** |
| `SYSTEM_A_ENGINE` | `inprocess` | `inprocess` or `http`. |
| `SYSTEM_A_URL`, `SYSTEM_A_API_KEY`, `SYSTEM_A_HTTP_TIMEOUT` | `http://127.0.0.1:8080`, – , `300` | `http` only. |
| `SYSTEM_A_MODE`, `SYSTEM_A_AI_MODE` | `production`, – | `production` = real Oracle + real VLM; `sandbox` = simulators (no VLM, no Oracle). |
| `WEBAPP_HOST`, `WEBAPP_PORT` | `127.0.0.1`, `8090` | where the screen listens. |
| `WEBAPP_WORKERS` | `4` | documents processed at the same time. |
| `WEBAPP_RENDER_DPI` | `150` | DPI of the page images shown under the boxes (System A reads the PDF at its own DPI). |
| `WEBAPP_PERSIST`, `WEBAPP_DATA_DIR` | `true`, `./data` | keep results per document on the server. |
| `WEBAPP_QUICK` | `false` | pass `--quick` to System A (no table/crop re-read: faster, weaker). |

The portal stores **no** secrets of System A: `LITELLM_URL`, `LITELLM_API_KEY`, `MODEL_VISION`, `ORACLE_BACKEND`,
`ORACLE_MCP_URL`, `ORACLE_MCP_TOKEN` … are read from `<SYSTEM_A_HOME>/.env` by System A's own loader (`sysa.py`).
Values already in the environment — or set in this folder's `.env` — win; only missing keys are filled in.

## Where each number on the screen comes from

| Screen | payload path |
|---|---|
| the boxes | `ocr.elements[]` → `element_id`, `element_type`, `page_no`, `field_name`, `raw_value`, `normalized_value`, `confidence`, `bbox` |
| page geometry (box placement) | `pages[]` → `width_pt`, `height_pt`, `rotation`, `render_dpi`, `page_type` + `package.coordinate_system` (origin top-left, unit ratio 0–1) |
| Final Result values | `normalized_fields` (incl. `items`, `items_summary`, `customer_*`) — each with the `element_id`s it came from |
| line ↔ receipt | `line_matching.groups[]` (`relation`, `level`, `rcv_line_ids`, `confidence`, `source`, `rationale`), `ai_rejected`, `unmatched_rcv_line_ids` |
| signatures | `ocr.elements[]` with `element_type=signature` |
| Verify Result | `rule_results[]`, `exceptions[]`, `evidence[]` (`related_element_ids`, `bboxes`, `message_th`) |
| verdict | `recommendation` (`value`, `max_severity`, `exception_codes`, `reasons`, `halted_by`) |
| Oracle lookup | `oracle_snapshot` (`queried`, `lookup_path`, `receipt_nums`, `po_numbers`, `receiver`, `fingerprint`, `row_cap_hit`) |
| footer | `contract`, `versions`, `package`, `request`, `integrity.payload_sha256`, `metrics` |
| the raw reading | `extraction` (the `aiva.extraction/2.0` block System A echoes: `fields`, `lines`, `signatures`, `extra`) |

A payload with entries in `system_errors` is marked **“ผลไม่ครบ”** (incomplete) — the entries are listed, and the
`halted_by` of a rule chain (a failing rule stops the later ones) is *not* treated as incomplete: that is how
System A's rule chain is meant to behave.

## HTTP API

| | |
|---|---|
| `GET /api/meta` | wiring: engine, mode, colours, element types, defaults, source stats |
| `GET /api/health` | engine health (503 when System A cannot answer) |
| `GET /api/documents`, `POST /api/documents/refresh` | the document list with state; re-read it from Paperless |
| `GET /api/documents/{id}` | one document + its state (poll this) |
| `POST /api/documents/{id}/process` | start → `202`; `409` if another document is already running or this one is |
| `GET /api/documents/{id}/result` | the screen model (`409` until processed) |
| `GET /api/documents/{id}/payload` | the raw `aiva.system_a.result/3.0`, byte for byte |
| `GET /api/documents/{id}/extraction` | the `extraction` block inside that payload |
| `DELETE /api/documents/{id}/result` | forget the result of that document |
| `GET /api/documents/{id}/pdf`, `GET /api/documents/{id}/pages/{n}/image` | the document's own file / a page rendered as PNG |
| `GET /api/search?q=` | ids of processed documents whose id / title / payload text contains `q` |

Interactive docs: `/docs`.

### Per-document isolation

* one document is processed by one job at a time (a second `process` on it → 409); different documents run side by side;
* each `process` raises `run` and clears the previous result **before** the new run starts, and a job may write its
  outcome only while its `run` is still current — a result is never a mixture of runs or documents;
* files are `data/results/doc_<id>/{state,view,payload}.json`, written atomically; a run interrupted by a restart is
  reported as an error, never as a result.

## How the tests run

```
set SYSTEM_A_HOME=C:\path\to\system-a
python -m pip install -r requirements-dev.txt
python -m pytest -q                 # 109 tests, no network
```

No VLM, no Oracle, no Paperless, no real invoice is contacted.  The harness copies System A's package from
`SYSTEM_A_HOME` next to a **stub Standard** (`tests/system_a_stub/config`) into a temp folder and imports it from
there, then `tests/synth.py` builds a **synthetic `aiva.extraction/2.0`** and hands it to System A's own
`orchestrator.validate()` in sandbox mode (`build_services()` with the in-memory Oracle + sim AI).  What comes back
is a genuine `aiva.system_a.result/3.0` — the tests assert the portal against that, not against a hand-made
dictionary.  Every payload is also checked against System A's own envelope/serialiser before it may be used.

| File | Covers |
|---|---|
| `test_view.py` (25) | the screen model is the payload: same boxes, same bbox, same values, same refs, same verdict; nothing is invented for an element without a bbox |
| `test_service.py` (12) | state machine: one run at a time, busy, stale run, restart, delete, search, a failure leaves no partial result |
| `test_api.py` (19) | every endpoint, status codes, `409` before processing, page images, the route whitelist |
| `test_engine.py` (18) | both engines produce the same payload (same `integrity.payload_sha256`), including System A's real API app |
| `test_catalog.py` (12) | the list is what the DMS says: tag filter, paging, limit, a failing DMS is reported |
| `test_config.py` (16) | `.env` semantics (real env wins), defaults, validation errors, finding System A |
| `test_ui_static.py` (7) | the browser half as text: controls exist, only real endpoints are called, boxes come from payload elements |

## Known limits

* **Security:** no authentication; it binds to `127.0.0.1`. Do not expose it as is.
* **Process costs money/time**: one VLM call per page plus the real Oracle, per document, per run. Use
  `SYSTEM_A_MODE=sandbox` + `SYSTEM_A_AI_MODE=sim` for a free (weaker) run: the AI-judged rules come back
  `not_evaluated`.
* With `SYSTEM_A_ENGINE=http` the reading still runs in this process — System A's API takes an extraction in the
  request body, it does not ingest a file itself.
* `WEBAPP_PERSIST=false` means the server keeps nothing: everything you see is in *this* browser only.
