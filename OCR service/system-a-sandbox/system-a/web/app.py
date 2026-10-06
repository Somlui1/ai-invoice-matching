"""FastAPI application for the System A testing portal.

The portal is a *consumer* of the existing CLI entrypoint.  It never imports the verification
pipeline in-process and never changes it: verification runs as a subprocess of ``process_pdf.py``,
and results are read from the JSON the engine itself writes.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
SYSTEM_A_DIR = WEB_DIR.parent
if str(SYSTEM_A_DIR / "src") not in sys.path:
    sys.path.insert(0, str(SYSTEM_A_DIR / "src"))
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile    # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse   # noqa: E402
from fastapi.staticfiles import StaticFiles                                     # noqa: E402

import catalog                                                                   # noqa: E402
import engine                                                                    # noqa: E402

app = FastAPI(title="System A Testing Portal", version="1.0.0",
              description="Interactive testing portal for System A core (viewer + verifier + bbox overlay)")

MAX_UPLOAD_MB = float(os.getenv("WEB_MAX_UPLOAD_MB", "60"))


def _die(status: int, message: str) -> None:
    raise HTTPException(status_code=status, detail=message)


# --------------------------------------------------------------------------- static
@app.get("/")
def index() -> Response:
    page = WEB_DIR / "static" / "index.html"
    if not page.exists():
        _die(404, "static/index.html is missing")
    return FileResponse(str(page), media_type="text/html")


# --------------------------------------------------------------------------- health
@app.get("/api/health")
def health(deep: bool = Query(False)) -> dict:
    """Read-only connectivity checks for the portal's three dependencies (never a verdict)."""
    h = catalog.health(deep=deep)
    h["engine"] = {"engine_python": str(engine.ENGINE_PY), "engine_python_exists": engine.ENGINE_PY.exists(),
                   "process_pdf": str(engine.PROCESS_PDF), "process_pdf_exists": engine.PROCESS_PDF.exists()}
    h["storage"] = {"results_dir": str(engine.RESULTS_DIR), "results": len(engine.stored_results()),
                    "free_gb": round(engine.free_disk_bytes() / 1e9, 2) if engine.free_disk_bytes() > 0 else None}
    h["portal"] = {"max_concurrent": engine.MAX_CONCURRENT, "run_timeout_s": engine.RUN_TIMEOUT_S,
                   "running": engine.REGISTRY.running_count()}
    return h


# --------------------------------------------------------------------------- catalog
@app.get("/api/documents")
def documents(search: str = Query(""), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
              ordering: str = Query("-created")) -> dict:
    """Document gallery data from Paperless-ngx, annotated with the portal's stored verdicts."""
    try:
        data = catalog.search_documents(search=search, page=page, page_size=page_size, ordering=ordering)
    except PermissionError as e:
        _die(401, str(e))
    except Exception as e:                                       # unreachable DMS is a normal state
        return {"count": 0, "page": page, "page_size": page_size, "results": [],
                "error": f"{type(e).__name__}: {str(e)[:200]}"}
    badges: dict[int, dict] = {}
    for row in engine.stored_results():
        if row.get("doc_id") is not None:
            badges[int(row["doc_id"])] = row
    for row in data["results"]:
        row["verdict"] = badges.get(int(row["id"])) if row.get("id") is not None else None
    data["badges_available"] = len(badges)
    return data


@app.get("/api/documents/{doc_id}/meta")
def document_meta(doc_id: int) -> dict:
    try:
        meta = catalog.pdf_meta(catalog.pdf_for(doc_id))
    except Exception as e:
        code, msg = _upstream_error(e, doc_id)
        _die(code, msg)
    try:
        meta["paperless"] = catalog.document(doc_id)
    except Exception:
        pass
    return meta


@app.get("/api/documents/{doc_id}/pdf")
def document_pdf(doc_id: int) -> Response:
    try:
        path = catalog.pdf_for(doc_id)
    except Exception as e:
        code, msg = _upstream_error(e, doc_id)
        _die(code, msg)
    return FileResponse(str(path), media_type="application/pdf", filename=f"DMS-{doc_id}.pdf")


@app.get("/api/documents/{doc_id}/page/{page_no}.png")
def document_page(doc_id: int, page_no: int, dpi: int = Query(150)) -> Response:
    try:
        png, _meta = catalog.render_page(catalog.pdf_for(doc_id), page_no, dpi)
    except IndexError as e:
        _die(404, str(e))
    except Exception as e:
        code, msg = _upstream_error(e, doc_id)
        _die(code, msg if code != 502 else f"page render failed: {msg[:200]}")
    return _png(png)


def _png(png: bytes) -> Response:
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"})


def _upstream_error(e: Exception, doc_id: int) -> tuple[int, str]:
    """Turn a Paperless-ngx failure into the status the browser should show.

    A document that is not in Paperless is an ordinary user situation (a stale id, or a document
    deleted after the list was fetched), so it must read as 'not found' rather than as a portal
    crash.  PAPERLESS_TRANSPORT is what the reader labels a 404, so the code is matched in text.
    """
    msg = str(e)
    if "404" in msg:
        return 404, f"DMS-{doc_id} is not in Paperless-ngx"
    if "PAPERLESS_AUTH" in msg:
        return 502, f"Paperless-ngx rejected this token - check PAPERLESS_API_TOKEN ({msg[:120]})"
    if "not configured" in msg:
        return 503, "Paperless-ngx is not configured on this machine"
    return 502, f"cannot fetch DMS-{doc_id}: {type(e).__name__}: {msg[:200]}"


# --------------------------------------------------------------------------- uploads
@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    if not data:
        _die(400, "empty upload")
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        _die(413, f"upload exceeds {MAX_UPLOAD_MB:.0f} MB")
    suffix = Path(file.filename or "upload").suffix.lower()
    if suffix not in (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"):
        _die(415, f"unsupported file type {suffix or '?'}")
    digest = hashlib.sha256(data).hexdigest()
    key = engine.upload_key(file.filename or "upload.pdf", digest)
    path = engine.save_upload(data, file.filename or "upload.pdf", digest)
    try:
        meta = catalog.pdf_meta(path)
    except Exception as e:
        path.unlink(missing_ok=True)
        _die(422, f"not a readable document: {type(e).__name__}: {str(e)[:160]}")
    return {"key": key, "name": file.filename, "sha256": meta["sha256"], "bytes": meta["bytes"],
            "page_count": meta["page_count"], "pages": meta["pages"],
            "has_stored_result": engine.stored_result(key) is not None}


@app.get("/api/uploads")
def uploads() -> dict:
    out = []
    for f in sorted(engine.DOWNLOADS_DIR.glob("UP-*")):
        if f.suffix.lower() not in (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"):
            continue
        key = f.stem
        out.append({"key": key, "name": f.name, "bytes": f.stat().st_size,
                    "has_stored_result": engine.stored_result(key) is not None})
    return {"uploads": out}


@app.get("/api/uploads/{key}/pdf")
def upload_pdf(key: str) -> Response:
    path = engine.find_upload(key)
    if not path:
        _die(404, f"no upload stored under key {key}")
    return FileResponse(str(path), filename=path.name)


@app.get("/api/uploads/{key}/page/{page_no}.png")
def upload_page(key: str, page_no: int, dpi: int = Query(150)) -> Response:
    path = engine.find_upload(key)
    if not path:
        _die(404, f"no upload stored under key {key}")
    try:
        png, _meta = catalog.render_page(path, page_no, dpi)
    except IndexError as e:
        _die(404, str(e))
    except Exception as e:
        _die(502, f"page render failed: {type(e).__name__}: {str(e)[:200]}")
    return _png(png)


# --------------------------------------------------------------------------- verification
def _events_response(run) -> StreamingResponse:
    """Stream engine progress as Server-Sent Events; the final event carries the full result."""

    def gen():
        for ev in run.events():
            etype = ev.get("type", "message")
            payload = dict(ev)
            if etype == "done":
                try:
                    payload["result"] = run.result_json()
                except Exception as e:
                    payload["error"] = payload.get("error") or str(e)
                try:
                    engine.log_run(run)
                except Exception:
                    pass
                etype = "result" if payload.get("ok") else "done"
            if etype == "log" and len(payload.get("line", "")) > 500:
                payload["line"] = payload["line"][:500] + "…"
            yield "event: %s\ndata: %s\n\n" % (etype, json.dumps(payload, ensure_ascii=False, default=str))

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ORDER MATTERS: Starlette answers the first route whose path pattern matches, and
# '/api/verify/{doc_id}' also matches the literal 'upload'.  Registering the upload route first is
# what keeps 'verify an uploaded PDF' working at all - see test_upload_route_is_not_shadowed.
@app.post("/api/verify/upload")
def verify_upload(request: Request, key: str = Query(...), mode: str = Query("production"),
                  quick: bool = Query(False), stream: bool = Query(True)) -> Response:
    path = engine.find_upload(key)
    if not path:
        _die(404, f"no upload stored under key {key}")
    try:
        run = engine.REGISTRY.start(key=key, pdf_path=path, mode=mode, quick=quick, label=key)
    except engine.BusyError as e:
        _die(409, str(e))
    except Exception as e:
        _die(500, f"could not start the engine: {type(e).__name__}: {str(e)[:200]}")
    if not stream:
        try:
            return JSONResponse(run.wait())
        except TimeoutError as e:
            _die(504, str(e))
        except Exception as e:
            _die(500, str(e))
    return _events_response(run)


@app.post("/api/verify/{doc_id}")
def verify(doc_id: int, request: Request, mode: str = Query("production"),
           quick: bool = Query(False), stream: bool = Query(True)) -> Response:
    """Run System A on a Paperless document.  mode=sandbox uses canned fixtures, never real AI/ERP."""
    if mode not in ("production", "sandbox"):
        _die(400, "mode must be production or sandbox")
    if engine.free_disk_bytes() // (1024 * 1024) < 100:
        _die(507, "less than 100 MB free for result files")
    key = f"DMS-{doc_id}"
    try:
        run = engine.REGISTRY.start(key=key, dms_id=doc_id, mode=mode, quick=quick, label=f"DMS-{doc_id}")
    except engine.BusyError as e:
        _die(409, str(e))
    except Exception as e:
        _die(500, f"could not start the engine: {type(e).__name__}: {str(e)[:200]}")
    if not stream:
        try:
            return JSONResponse(run.wait())
        except TimeoutError as e:
            _die(504, str(e))
        except Exception as e:
            _die(500, str(e))
    return _events_response(run)


@app.get("/api/runs")
def runs() -> dict:
    s = catalog.settings()
    active = [r for r in engine.REGISTRY.recent(limit=100) if r.get("running")]
    return {"active": [r["key"] for r in active], "recent": engine.REGISTRY.recent(limit=30),
            "running": len(active), "mode": s.mode, "ai_mode": s.ai_mode, "sandbox": s.mode == "sandbox",
            "max_concurrent": engine.MAX_CONCURRENT}


@app.get("/api/runs/{key}")
def run_detail(key: str) -> dict:
    run = engine.REGISTRY.get(key)
    if not run:
        _die(404, f"no run in this portal session for {key} (results persist under /api/results/{key})")
    return run.summary()


@app.post("/api/runs/{key}/cancel")
def cancel(key: str) -> dict:
    run = engine.REGISTRY.get(key)
    if not run:
        _die(404, f"no active run for {key}")
    run.cancel()
    return {"cancelled": key}


# --------------------------------------------------------------------------- results
@app.get("/api/results")
def results() -> dict:
    return {"results": engine.stored_results()}


@app.get("/api/results/{key}")
def result(key: str) -> Response:
    data = engine.stored_result(key)
    if data is None:
        _die(404, f"no stored result for {key}")
    return JSONResponse(json.loads(json.dumps(data, ensure_ascii=False, default=str)),
                        headers={"Cache-Control": "no-store"})


# --------------------------------------------------------------------------- bbox layers (Phase 2)
# The portal converts the contract's evidence plane into a page-indexed layer set.  The
# coordinate system is taken from the result itself (ocr.coordinate_system) — never assumed.
#
# Contract 3.0 paths used here (verified against a real result, not from the task brief):
#   ocr.elements[]                  element_id, element_type, page_no, bbox, text, confidence, field_name
#   extraction.fields[name]         raw_value, normalized_value, confidence, ok, null_reason, element_id
#   extraction.lines[]              line_no, element_id, uom_group, cells{name: …same shape…}
#   extraction.signatures[name]     present, confidence, kind, region{page, bbox}
#   exceptions[]                    exception_id, code, name, severity, rule_id, evidence_ids[]
#   evidence[]                      evidence_id, rule_id, exception_code, result, actual_value,
#                                   expected_value, page_no[], related_element_ids[]
def build_overlays(result: dict) -> dict:
    pkg = result.get("package") or {}
    ocr = result.get("ocr") or {}
    ex = result.get("extraction") or {}
    docs = {d.get("doc_index"): d for d in result.get("documents") or []}
    pages = {p.get("page_no"): p for p in result.get("pages") or []}

    def bbox_of(node: dict) -> list | None:
        b = node.get("bbox")
        return b if isinstance(b, list) and len(b) >= 4 else None

    # 1. every OCR element, indexed by id, page and type — this is the geometry plane
    elements: dict[str, dict] = {}
    by_page: dict[int, list] = {}
    by_type: dict[str, list] = {}
    for e in ocr.get("elements") or []:
        item = {"element_id": e.get("element_id"), "id": e.get("element_id"),
                "type": e.get("element_type"), "page": e.get("page_no"),
                "bbox": bbox_of(e), "text": e.get("text"), "conf": e.get("confidence"),
                # the viewer labels a box with its raw value, which for an element is raw_value
                # (words carry text instead) — expose both spellings so the UI has one contract
                "raw": e.get("raw_value") or e.get("text"), "confidence": e.get("confidence"),
                "field": e.get("field_name"), "cell": e.get("column")}
        if item["bbox"] is None or item["id"] is None:
            continue
        elements[item["id"]] = item
        by_page.setdefault(int(item["page"] or 0), []).append(item)
        by_type.setdefault(str(item["type"]), []).append(item)

    def locate(element_id: str | None) -> tuple[int | None, list | None]:
        """Where a contract value physically came from: page + box, via its element_id."""
        it = elements.get(element_id or "")
        return (it["page"], it["bbox"]) if it else (None, None)

    # Cell values in extraction.lines[].cells carry no element_id, but the OCR plane has a cell
    # element per column whose field_name is exactly "lines[<line_no>].<column>".  The join is on
    # that contract field name — a data-plane key, not screen geometry or text similarity.
    cell_by_field: dict[str, dict] = {}
    for it in by_type.get("cell", []):
        if it.get("field"):
            cell_by_field.setdefault(str(it["field"]), it)

    # 2. header fields -> element id + page + box, so a click can select it
    fields: dict[str, dict] = {}
    for name, f in (ex.get("fields") or {}).items():
        eid = f.get("element_id")
        page, bbox = locate(eid)
        fields[name] = {"raw": f.get("raw_value"), "normalized": f.get("normalized_value"),
                        "ok": f.get("ok"), "confidence": f.get("confidence"),
                        "null_reason": f.get("null_reason"), "element_id": eid,
                        "page": page, "bbox": bbox}

    # 3. invoice lines: each cell is separately clickable
    lines: list[dict] = []
    for ln in ex.get("lines") or []:
        cells: dict[str, dict] = {}
        for cname, c in (ln.get("cells") or {}).items():
            eid = c.get("element_id") or f"{ln.get('element_id')}-{cname}"
            page, bbox = locate(eid)
            if page is None:
                hit = cell_by_field.get(f"lines[{ln.get('line_no')}].{cname}")
                if hit:
                    eid, page, bbox = hit["element_id"], hit["page"], hit["bbox"]
            cells[cname] = {"raw": c.get("raw_value"), "normalized": c.get("normalized_value"),
                            "ok": c.get("ok"), "confidence": c.get("confidence"),
                            "null_reason": c.get("null_reason"), "element_id": eid,
                            "page": page, "bbox": bbox}
        reid = ln.get("element_id")
        rpage, rbbox = locate(reid)
        lines.append({"line_no": ln.get("line_no"), "uom_group": ln.get("uom_group"),
                      "element_id": reid, "page": rpage, "row": {"bbox": rbbox, "page": rpage},
                      "cells": cells})

    # 4. exceptions: an exception cites evidence_ids; each evidence cites element_ids; boxes come from those
    evid = {e.get("evidence_id"): e for e in result.get("evidence") or []}
    excs: list[dict] = []
    for x in result.get("exceptions") or []:
        eids: list[str] = []
        boxes: list[dict] = []
        for aid in x.get("evidence_ids") or []:
            ev = evid.get(aid) or {}
            for eid in ev.get("related_element_ids") or []:
                if eid in eids:
                    continue
                eids.append(eid)
                it = elements.get(eid)
                if it and it["bbox"]:
                    boxes.append({"element_id": eid, "page": it["page"], "bbox": it["bbox"],
                                  "text": it.get("text") or it.get("raw")})
        first = evid.get((x.get("evidence_ids") or [None])[0]) or {}
        excs.append({"code": x.get("code"), "exception_id": x.get("exception_id"), "name": x.get("name"),
                     "severity": x.get("severity"), "rule_id": (x.get("rule_id") or "").upper(),
                     "detail": first.get("detail"), "actual_value": first.get("actual_value"),
                     "expected_value": first.get("expected_value"), "pages": first.get("page_no") or [],
                     "evidence_ids": x.get("evidence_ids") or [], "element_ids": eids, "boxes": boxes})

    sigs: dict[str, dict] = {}
    for name, s in (ex.get("signatures") or {}).items():
        reg = s.get("region") or {}
        hit = next((it for it in by_type.get("signature", []) if it.get("field") == f"signatures.{name}"), None)
        sigs[name] = {"present": s.get("present"), "confidence": s.get("confidence"), "kind": s.get("kind"),
                      "page": reg.get("page"), "bbox": reg.get("bbox"),
                      "element_id": (hit or {}).get("element_id")}

    rules = [{"rule_id": r.get("rule_id"), "rule_version": r.get("rule_version"), "result": r.get("result"),
              "detail": r.get("detail"), "halted_by": r.get("halted_by"),
              "evidence_ids": r.get("evidence_ids") or [],
              "data_keys": sorted((r.get("data") or {}).keys())}
             for r in result.get("rule_results") or []]

    layers = [
        {"id": "exceptions", "label": "Rule exceptions", "count": sum(1 for e in excs if e["boxes"]),
         "color": "#ff6b6b", "default": True,
         "description": "evidence boxes cited by each raised exception"},
        {"id": "header_fields", "label": "Header fields", "count": len(by_type.get("field", [])),
         "color": "#ffb454", "default": True, "description": "field evidence boxes behind extraction.fields"},
        {"id": "table_rows", "label": "Table rows / cells", "count": len(by_type.get("cell", [])),
         "color": "#35c9e6", "default": True,
         "description": "item table rows and each cell — the geometry V-06/V-07/V-08 rely on"},
        {"id": "signatures", "label": "Signatures / stamps", "count": len(by_type.get("signature", [])) + len(by_type.get("stamp", [])),
         "color": "#b07bff", "default": True, "description": "signature and stamp regions (V-09)"},
        {"id": "ocr_words", "label": "OCR words", "count": len(by_type.get("word", [])),
         "color": "#7f8fa4", "default": False,
         "description": "word boxes with per-word confidence — the raw perception output"},
    ]

    return {
        "key": (result.get("request") or {}).get("dms_doc_id"),
        "coordinate_system": ocr.get("coordinate_system") or pkg.get("coordinate_system"),
        "origin_note": "boxes are relative to the rendered page after rotation correction "
                       "(the same image /api/documents/{id}/page/{n}.png rasterises)",
        "recommendation": result.get("recommendation") or {},
        "rules": rules,
        "versions": result.get("versions") or {},
        "pages": [{"page_no": k, "width_pt": v.get("width_pt"), "height_pt": v.get("height_pt"),
                   "rotation": v.get("rotation"), "page_type": v.get("page_type"),
                   "render_dpi": v.get("render_dpi")} for k, v in sorted(pages.items())],
        "page_meta": [{"page_no": k, "width_pt": v.get("width_pt"), "height_pt": v.get("height_pt")}
                      for k, v in sorted(pages.items())],
        "by_page": {str(k): v for k, v in sorted(by_page.items())},
        "by_type": dict(by_type),
        "layers": layers,
        "fields": fields, "lines": lines, "exceptions": excs, "signatures": sigs,
        "groups": (result.get("line_matching") or {}).get("groups") or [],
        "ai_rejected": (result.get("line_matching") or {}).get("ai_rejected") or [],
        "unmatched_rcv": (result.get("line_matching") or {}).get("unmatched_rcv_line_ids") or [],
        "receipt_lines": (result.get("oracle_snapshot") or {}).get("receipt_lines") or [],
        "oracle": {k: v for k, v in (result.get("oracle_snapshot") or {}).items() if k != "receipt_lines"},
        "normalized_fields": result.get("normalized_fields") or {},
        "element_count": len(ocr.get("elements") or []),
        "document": {k: (docs.get(1) or {}).get(k) for k in ("file_name", "page_count", "file_sha256")},
        "metrics": result.get("metrics") or {},
    }


@app.get("/api/bbox/layers/{key}")
def bbox_layers(key: str) -> dict:
    """Layer inventory for a stored result, so the UI can offer toggles before drawing."""
    data = engine.stored_result(key)
    if data is None:
        _die(404, f"no stored result for {key}")
    ov = build_overlays(data)
    return {"key": key, "layers": ov["layers"], "coordinate_system": ov["coordinate_system"],
            "pages": ov["pages"], "element_count": ov["element_count"]}


@app.get("/api/overlays/{key}")
def overlays(key: str) -> dict:
    """All bbox layers for a stored result in one call."""
    data = engine.stored_result(key)
    if data is None:
        _die(404, f"no stored result for {key} — run the verification first")
    return build_overlays(data)


@app.get("/api/overlays/{key}/page/{page_no}")
def overlays_page(key: str, page_no: int) -> dict:
    data = engine.stored_result(key)
    if data is None:
        _die(404, f"no stored result for {key}")
    ov = build_overlays(data)
    return {"key": key, "page_no": page_no, "coordinate_system": ov["coordinate_system"],
            "layers": ov["layers"], "boxes": ov["by_page"].get(str(page_no), []),
            "exceptions": [e for e in ov["exceptions"] if any(b["page"] == page_no for b in e["boxes"])]}


# --------------------------------------------------------------------------- manifest / static
@app.get("/api/manifest")
def manifest() -> dict:
    """Phase state, derived from files on disk rather than a hand-kept list."""
    phases = [
        (1, "Backend API and engine bridge", ["engine.py", "catalog.py", "app.py", "serve.py"]),
        (2, "BBox data preparation", ["app.py"]),
        (3, "Portal UI", ["static/index.html", "static/styles.css", "static/js/api.js", "static/js/app.js",
                          "static/js/viewer.js", "static/js/bbox-overlay.js", "static/js/interaction.js",
                          "static/js/panels.js"]),
        (4, "Interaction cross-highlighting", ["static/js/interaction.js"]),
        (5, "Launch and test", ["run_portal.bat", "test_portal.py"]),
    ]
    out = []
    for num, name, files in phases:
        present = [f for f in files if (WEB_DIR / f).exists()]
        out.append({"phase": num, "name": name, "files_present": len(present), "files_expected": len(files),
                    "missing": [f for f in files if not (WEB_DIR / f).exists()]})
    return {"phases": out, "results_stored": len(engine.stored_results()),
            "engine_python": str(engine.ENGINE_PY), "system_a_dir": str(SYSTEM_A_DIR)}


app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")
# PDF.js is vendored under static/vendor/pdfjs and mounted at /pdf so the viewer and its worker
# stay on the same origin — the portal has no CDN dependency (intranet / offline use).
PDFJS_DIR = WEB_DIR / "static" / "vendor" / "pdfjs"
PDFJS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/pdf", StaticFiles(directory=str(PDFJS_DIR), check_dir=False), name="pdfjs")
