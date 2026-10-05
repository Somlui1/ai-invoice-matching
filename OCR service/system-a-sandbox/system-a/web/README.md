# System A Web Testing Portal

An interactive portal for testing and debugging **System A Core** against real invoices in
Paperless-ngx: browse documents, run a verification while watching the real engine steps, render
each PDF page with its bounding boxes, and jump between an extracted value and the region of the
page it came from.

Implemented from `TASK_WEB_TEST_PORTAL.md` (Phases 1–5).

## Hard guarantees

* **No change to verification logic.** The portal never imports `system_a.*` to make a decision —
  it launches `system-a/process_pdf.py` as a subprocess, exactly like a human at a terminal, and
  renders whatever that CLI writes. `src/system_a/**`, `config/**` (including the protected
  `policy.yaml`, `codes.yaml`, `rules.yaml`) and the output-contract schema are untouched.
* **Data first, coordinates second.** Every box on the page is resolved from a contract
  `element_id` (`extraction.fields[*].element_id`, the OCR element plane, and
  `evidence[*].related_element_ids`). Nothing is located by OCR text search or screen geometry.
* The portal is a *consumer*: if `process_pdf.py` output changes, the portal shows the change.

## Starting it

```bat
cd OCR service/system-a-sandbox/system-a
run_portal.bat                     :: probes interpreters, picks one that can import the deps
```

or directly:

```bat
python web\serve.py --port 8080            :: auto-opens the browser
python web\serve.py --port 8080 --no-browser
```

| env var | meaning |
|---|---|
| `WEB_PORT` / `WEB_HOST` | listen port / host (default `8080` / `127.0.0.1`) |
| `WEB_ENGINE_PYTHON` | interpreter used to run `process_pdf.py` — see below |
| `WEB_MAX_CONCURRENT` | parallel engine runs (default 2) |
| `WEB_RUN_TIMEOUT_S` | per-run timeout (default 1800 s) |
| `PAPERVERIFY_*` | same variables the CLI uses (Paperless, LiteLLM, Oracle MCP) |

**Interpreter selection.** The portal process needs `fastapi`, `uvicorn`, `httpx`; the *engine*
process needs `yaml`, `pydantic`, `pymupdf`. On a machine with several Python installs these are
often different interpreters, so the portal probes candidates (`WEB_ENGINE_PYTHON` → its own
interpreter → nearby venvs) and picks the first that can import the engine's dependencies. The
choice is shown in the health pill and `GET /api/health` → `engine.engine_python`. If it is wrong:
`set WEB_ENGINE_PYTHON=<path>\python.exe`.

## Using it

1. **Left column** — search/filter Paperless documents, paged (default 50/page). A badge shows any
   verdict already on disk, so an already-verified invoice is obvious before you spend a run.
2. Select a document, choose a mode, press **Verify**.
   * `sandbox` — Oracle stubbed (no DB round-trips, fast, no receipt lines).
   * `production` — real Oracle EBS via the MCP gateway.
   * `quick` — passes `--quick`, which turns crop and table perception **off**. That is a *different
     perception run*, not a faster one: different cache key (no reuse), generally no speed win, and
     it can change the verdict. It exists so the UI can reproduce a CLI run made with `--quick`.
   Progress shows the engine's own `[1/3] … [3/3]` steps plus its live stdout. Perception for a
   multi-page invoice is minutes; repeat runs normally hit the perception cache and finish in ~1 s.
3. **Middle** — page image with the bbox overlay; zoom/fit and page navigation; layer chips toggle
   exceptions / header fields / table cells / signatures / OCR words.
4. **Right** — verdict, per-rule table, exceptions with the values the rule compared, fields with
   `ok` / `null_reason` / confidence, invoice lines (per cell), matched receipt lines, raw JSON.
5. **Cross-highlighting** — click a field row, line cell or exception to select its box (switching
   page when needed); click a box to scroll its row into view. Rule rows select every box their
   evidence cites.

Uploads: drop a PDF on the left to test a document that is not in Paperless. Uploads live under
`system-a/.cache/downloads/UP-*` and are verified through `--pdf-file`.

## Endpoints

| | |
|---|---|
| `GET /api/health[?deep=1]` | mode/model, perception cache dir, Paperless, LiteLLM, Oracle probe, engine interpreter, stored results, disk |
| `GET /api/documents?...` | Paperless search with paging + stored-verdict badges |
| `GET /api/documents/{id}/pdf`, `/page/{n}.png?dpi=`, `/meta` | download (cached), server raster, metadata incl. tags |
| `POST /api/upload`, `GET /api/uploads`, `GET /api/uploads/{key}/…` | local PDF testing |
| `POST /api/verify/{id}?mode=&quick=` | SSE stream: `step`, `log`, `heartbeat`, `done`, `result` |
| `POST /api/verify/upload/{key}` | same for an uploaded file |
| `GET /api/runs`, `/api/runs/{key}`, `POST /api/runs/{key}/cancel` | active run status / cancel |
| `GET /api/results`, `/api/results/{key}` | stored engine output |
| `GET /api/overlays/{key}` | the whole bbox plane for one verification |
| `GET /api/bbox/layers/{key}` | layer inventory (counts, defaults, colours) |
| `GET /api/manifest` | phase file inventory |
| `/pdf/*` | vendored PDF.js (same origin, no CDN) |

## How the boxes are derived

`build_overlays()` in `app.py` maps the contract (3.0) onto a page-indexed structure:

| overlay | contract source |
|---|---|
| field box | `extraction.fields[name].element_id` → `ocr.elements[]` → `page_no` + `bbox` |
| line row | `extraction.lines[].element_id` (a `row` element) |
| cell box | cells carry no id, so they join to the OCR plane on `field_name == "lines[<line_no>].<column>"` |
| signature box | `extraction.signatures[k].region`, plus the `signature` element with `field_name == "signatures.<k>"` |
| exception boxes | `exceptions[].evidence_ids` → `evidence[].related_element_ids` → element geometry |
| coordinate system | `ocr.coordinate_system` (`origin`, `unit`, `range`, `bbox_format`) passed through unchanged |

The browser converts normalised boxes with
`left = x·W, top = y·H, width = w·W, height = h·H` for the `[x, y, w, h]` format, and handles
`[x1, y1, x2, y2]`, `unit: point/pixel` and a non-`top-left` origin defensively — the portal reads
the declared system instead of assuming one.

Page images are rasterised **server-side with PyMuPDF** (the same library perception uses, applying
the page's `/Rotate`), so a box aligns with the pixels the model was shown. PDF.js stays available
in the UI as a vector/text-rendering mode.

## Where things are written

| path | contents |
|---|---|
| `system-a/web/results/*.json` | engine output per run (portal store) |
| `system-a/web/results/runs.jsonl` | audit line per portal-initiated run |
| `system-a/.cache/downloads/` | PDFs downloaded from Paperless + uploads |
| `system-a/.cache/web-pages/` | page rasters + geometry sidecars (stale-checked by mtime/size) |

## Tests

```bat
cd system-a
python -m pytest web\test_portal.py -q
```

23 tests, all offline: the engine subprocess is faked and every path is redirected to a temp dir.
They assert the portal is a pure CLI consumer (the argv handed to `process_pdf.py`), the step
markers match the CLI's real stdout lines, contract→overlay joins (field/cell/exception/signature),
the coordinate system is passed through untouched, duplicate-run and concurrency refusal, upload
and raster behaviour, dependency-outage behaviour, and UI/DOM id consistency.

## Troubleshooting

| symptom | cause / fix |
|---|---|
| run dies with `ModuleNotFoundError: yaml` | engine interpreter lacks deps → set `WEB_ENGINE_PYTHON` |
| `409 … already has a verification running` | same document twice; cancel it first |
| first run very slow, next one ~1 s | normal: perception cache hit (`/api/health` → `perception_cache`) |
| verdict differs from an earlier run with the same options | perception cache poisoned by a truncated page — see the integrity flags in the result (`ok=false`, `pages_complete=false`) and delete that cache entry |
| Oracle probe failed in health | MCP gateway unreachable; sandbox mode still works |
| overlay looks shifted | confirm `coordinate_system` in `/api/overlays/{key}` and `pages[].rotation`; the raster applies `/Rotate` |
