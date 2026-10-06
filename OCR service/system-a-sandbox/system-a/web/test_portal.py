"""Portal test suite.  Run from system-a/:  python -m pytest web/test_portal.py -q

Design rules:
  * sandbox only — no Paperless, LiteLLM or Oracle calls, and the engine subprocess is faked;
  * every filesystem location is redirected into a pytest tmp_path;
  * the fake engine asserts the exact argv the portal would hand to process_pdf.py, so a change
    that makes the portal a non-consumer of the CLI (importing the pipeline, inventing flags)
    fails here rather than in front of a user.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

WEB_DIR = Path(__file__).resolve().parent
SYSTEM_A_DIR = WEB_DIR.parent
for p in (str(SYSTEM_A_DIR / "src"), str(WEB_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import engine                                                         # noqa: E402
import catalog                                                        # noqa: E402
import app as portal_app                                              # noqa: E402
from fastapi.testclient import TestClient                             # noqa: E402


# --------------------------------------------------------------------------- fixtures
CONTRACT_RESULT = {
    "contract": {"schema": "3.0"},
    "request": {"dms_doc_id": "DMS-9001", "validation_id": "VAL-TEST", "completed_at": "2026-10-05T10:00:00+00:00"},
    "versions": {"standard": "6.6", "ruleset": "v6.6-r4"},
    "package": {"page_count": 1},
    "pages": [{"page_no": 1, "width_pt": 595.0, "height_pt": 842.0, "rotation": 0, "render_dpi": 150}],
    "documents": [{"doc_index": 1, "file_name": "DMS-9001.pdf", "page_count": 1,
                   "file_sha256": "sha256:abc", "document_role": "original_pdf"}],
    "ocr": {
        "coordinate_system": {"origin": "top-left", "unit": "normalized", "range": [0, 1],
                              "bbox_format": "[x, y, w, h]"},
        "elements": [
            {"element_id": "P1", "element_type": "page", "page_no": 1, "bbox": [0, 0, 1, 1]},
            {"element_id": "D1-f-invoice_num", "element_type": "field", "page_no": 1,
             "field_name": "invoice_num", "bbox": [0.69, 0.15, 0.10, 0.02], "confidence": 0.98,
             "raw_value": "26/2691", "normalized_value": "26/2691"},
            {"element_id": "D1-L1", "element_type": "row", "page_no": 1, "field_name": "lines[1]",
             "bbox": [0.01, 0.36, 0.98, 0.05]},
            {"element_id": "D1-L1-uom", "element_type": "cell", "page_no": 1,
             "field_name": "lines[1].uom", "bbox": [0.558, 0.368, 0.03, 0.014],
             "raw_value": "PCS.", "normalized_value": "PCS", "confidence": 0.96},
            {"element_id": "p1-w0001", "element_type": "word", "page_no": 1,
             "bbox": [0.1, 0.2, 0.05, 0.01], "text": "INVOICE", "confidence": 0.99},
            {"element_id": "D1-sig-receiver", "element_type": "signature", "page_no": 1,
             "field_name": "signatures.receiver", "bbox": [0.44, 0.65, 0.11, 0.04]},
        ],
    },
    "extraction": {
        "fields": {"invoice_num": {"raw_value": "26/2691", "normalized_value": "26/2691", "ok": True,
                                    "confidence": 0.98, "null_reason": None,
                                    "element_id": "D1-f-invoice_num"},
                   "customer_tax_id": {"raw_value": None, "normalized_value": None, "ok": False,
                                        "confidence": None, "null_reason": "NOT_PRESENT",
                                        "element_id": None}},
        "lines": [{"line_no": 1, "element_id": "D1-L1", "uom_group": "PCS",
                   "cells": {"uom": {"raw_value": "PCS.", "normalized_value": "PCS", "ok": True,
                                      "null_reason": None},
                             "qty": {"raw_value": None, "normalized_value": None, "ok": False,
                                      "null_reason": "NOT_PRINTED"}}}],
        "signatures": {"receiver": {"present": True, "confidence": 0.8, "kind": "authorized_signature",
                                     "region": {"page": 1, "bbox": [0.44, 0.65, 0.11, 0.04]}}},
    },
    "normalized_fields": {"invoice_num": "26/2691", "customer_tax_id": None},
    "oracle_snapshot": {"lookup_path": "RCV-V01", "org_id": "101", "receipt_lines": []},
    "line_matching": {"groups": [], "ai_rejected": [], "unmatched_rcv_line_ids": []},
    "rule_results": [{"rule_id": "V-01", "rule_version": "1.1", "result": "fail", "detail": None,
                       "halted_by": None, "evidence_ids": ["X1"], "data": {"missing": "customer_tax_id"}}],
    "exceptions": [{"exception_id": "X1", "code": "E01", "name": "Missing Field", "severity": "Medium",
                     "rule_id": "V-01", "evidence_ids": ["X1"]}],
    "evidence": [{"evidence_id": "X1", "rule_id": "V-01", "exception_code": "E01", "result": "fail",
                   "severity": "Medium", "actual_value": None, "expected_value": "customer_tax_id",
                   "page_no": [1], "related_element_ids": ["D1-f-invoice_num", "D1-L1-uom"]}],
    "recommendation": {"value": "REVIEW", "max_severity": "Medium", "exception_codes": ["E01"]},
    "metrics": {"duration_ms": {"step1_ms": 1.0, "total_ms": 2.0}},
    "integrity": {"payload_sha256": "sha256:test", "excludes": ["request", "metrics"]},
}


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """Redirect every portal path into tmp_path and stop the engine from really being launched."""
    results, downloads, pages = tmp_path / "results", tmp_path / "downloads", tmp_path / "pages"
    for d in (results, downloads, pages):
        d.mkdir(parents=True)
    monkeypatch.setattr(engine, "RESULTS_DIR", results)
    monkeypatch.setattr(engine, "DOWNLOADS_DIR", downloads)
    monkeypatch.setattr(engine, "RUN_LOG", results / "runs.jsonl")
    monkeypatch.setattr(catalog, "DOWNLOADS_DIR", downloads)
    monkeypatch.setattr(catalog, "PAGES_CACHE_DIR", pages)
    engine.REGISTRY._runs.clear()
    return {"results": results, "downloads": downloads, "pages": pages}


@pytest.fixture()
def client(home):
    with TestClient(portal_app.app) as c:
        yield c


@pytest.fixture()
def stored(home):
    (home["results"] / "DMS-9001.json").write_text(json.dumps(CONTRACT_RESULT), encoding="utf-8")
    return home["results"] / "DMS-9001.json"


def make_pdf(path: Path, pages: int = 2) -> Path:
    import pymupdf
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), f"INVOICE TEST PAGE {i + 1}", fontsize=18)
    path.write_bytes(doc.tobytes())
    doc.close()
    return path


# --------------------------------------------------------------------------- basic API
def test_health_reports_the_three_dependencies(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    for key in ("paperless", "litellm", "oracle", "engine", "storage", "portal"):
        assert key in body
    assert body["engine"]["process_pdf_exists"] is True          # the CLI entrypoint is the only hook
    assert str(engine.ENGINE_PY) == body["engine"]["engine_python"]


def test_manifest_phases_present(client):
    body = client.get("/api/manifest").json()
    assert all(p["missing"] == [] for p in body["phases"]), \
        {p["phase"]: p["missing"] for p in body["phases"] if p["missing"]}


def test_missing_result_is_404(client):
    assert client.get("/api/results/NOPE").status_code == 404
    assert client.get("/api/overlays/NOPE").status_code == 404


def test_stored_result_roundtrip(client, stored):
    rows = client.get("/api/results").json()["results"]
    assert [r["key"] for r in rows] == ["DMS-9001"]
    assert rows[0]["recommendation"] == "REVIEW"
    assert client.get("/api/results/DMS-9001").json()["recommendation"]["value"] == "REVIEW"


# --------------------------------------------------------------------------- Phase 2 bbox prep
def test_overlays_keep_the_contracts_coordinate_system(client, stored):
    ov = client.get("/api/overlays/DMS-9001").json()
    assert ov["coordinate_system"]["bbox_format"] == "[x, y, w, h]"
    assert ov["coordinate_system"]["unit"] == "normalized"
    assert ov["coordinate_system"]["range"] == [0, 1]
    # boxes are passed through unchanged: the viewer, not the API, converts them to pixels
    field = ov["fields"]["invoice_num"]
    assert field["bbox"] == [0.69, 0.15, 0.10, 0.02] and field["page"] == 1


def test_field_and_page_geometry_come_from_the_element_plane(client, stored):
    ov = client.get("/api/overlays/DMS-9001").json()
    assert ov["fields"]["invoice_num"]["element_id"] == "D1-f-invoice_num"
    # a field the engine could not read has no box to point at — and the reason survives
    missing = ov["fields"]["customer_tax_id"]
    assert missing["ok"] is False and missing["bbox"] is None and missing["null_reason"] == "NOT_PRESENT"
    assert ov["by_page"]["1"] and all(b["bbox"] for b in ov["by_page"]["1"])


def test_cells_join_to_boxes_by_contract_field_name(client, stored):
    """Contract cells carry no element_id; the join key is the field name lines[<n>].<column>."""
    ov = client.get("/api/overlays/DMS-9001").json()
    cells = ov["lines"][0]["cells"]
    assert cells["uom"]["element_id"] == "D1-L1-uom"
    assert cells["uom"]["bbox"] == [0.558, 0.368, 0.03, 0.014] and cells["uom"]["page"] == 1
    assert cells["qty"]["bbox"] is None and cells["qty"]["null_reason"] == "NOT_PRINTED"
    assert ov["lines"][0]["row"]["bbox"] == [0.01, 0.36, 0.98, 0.05]


def test_exception_boxes_resolve_through_evidence(client, stored):
    ov = client.get("/api/overlays/DMS-9001").json()
    exc = ov["exceptions"][0]
    assert exc["code"] == "E01" and exc["rule_id"] == "V-01"
    assert exc["expected_value"] == "customer_tax_id"          # taken from the cited evidence record
    assert {b["element_id"] for b in exc["boxes"]} == {"D1-f-invoice_num", "D1-L1-uom"}
    assert all(b["page"] == 1 for b in exc["boxes"])
    layer = next(l for l in ov["layers"] if l["id"] == "exceptions")
    assert layer["count"] == 1                                 # only exceptions that have boxes are counted


def test_signature_region_and_element_id(client, stored):
    ov = client.get("/api/overlays/DMS-9001").json()
    sig = ov["signatures"]["receiver"]
    assert sig["present"] is True and sig["page"] == 1
    assert sig["element_id"] == "D1-sig-receiver"


def test_layer_inventory_endpoint(client, stored):
    body = client.get("/api/bbox/layers/DMS-9001").json()
    ids = {l["id"] for l in body["layers"]}
    assert {"ocr_words", "table_rows", "header_fields", "signatures", "exceptions"} <= ids
    assert body["element_count"] == 6


# --------------------------------------------------------------------------- engine bridge
def test_step_parser_matches_the_cli_lines():
    assert engine.parse_step("Processing 'DMS-20.pdf' (869,446 bytes, mode=sandbox)...")[0] == "start"
    assert engine.parse_step(" [1/3] Running Perception (OCR + Layout + BBoxes)...")[0] == "perception"
    assert engine.parse_step("       (Reusing cached OCR perception result)")[0] == "perception_cached"
    assert engine.parse_step(" [2/3] Querying Oracle EBS & Evaluating Rules V-01..V-09...")[0] == "oracle"
    assert engine.parse_step(" [3/3] Assembling final recommendation...")[0] == "assemble"
    assert engine.parse_step("Invoice No:      26/2691") is None


def test_engine_log_levels_label_upstream_noise_without_hiding_it():
    """A library deprecation notice must not read as a crash, and a real [ERROR] must read as one."""
    fitz = "warning: The `fitz` API is deprecated and will be removed in future.  Use pymupdf instead."
    assert engine.classify(fitz)[0] == "warn"
    assert "fingerprint" in engine.classify(fitz)[1]              # the explanation is attached
    assert engine.classify("DeprecationWarning: something old")[0] == "warn"
    # the CLI's own healthy output must stay 'info' even though it spells out scary words
    assert engine.classify("Recommendation:  [ SYSTEM_ERROR ] (Max Severity: -)")[0] == "info"
    assert engine.classify("--- Exceptions / Findings ---")[0] == "info"
    assert engine.classify(" [1/3] Running Perception (OCR + Layout + BBoxes)...")[0] == "info"
    assert engine.classify("[ERROR] RuntimeError: oracle unreachable")[0] == "error"
    assert engine.classify("Traceback (most recent call last):")[0] == "error"
    assert engine.strip_ansi("\x1b[95m[ MANUAL_REVIEW ]\x1b[0m") == "[ MANUAL_REVIEW ]"


def test_pump_strips_ansi_and_tags_every_line(client, home):
    """The log stream the browser sees is colour-free and carries a level per line."""
    class Proc:
        stdout = iter(["warning: The `fitz` API is deprecated and will be removed in future.",
                       "Recommendation:  \x1b[95m[ MANUAL_REVIEW ]\x1b[0m (Max Severity: High)",
                       " [1/3] Running Perception (OCR + Layout + BBoxes)..."])

        def wait(self):
            return 0

    run = engine.EngineRun(key="DMS-9002", mode="sandbox", quick=False)
    run._proc = Proc()
    run._pump(engine.RESULTS_DIR / "DMS-9002.json")               # no result file: run 'fails' cleanly
    events = list(run.events())
    logs = [e for e in events if e.get("type") == "log"]
    assert [e["level"] for e in logs] == ["warn", "info", "info"]
    assert logs[0]["hint"]
    assert "\x1b" not in run.log[1] and run.log[1].startswith("Recommendation:  [ MANUAL_REVIEW ]")
    assert [e for e in events if e["type"] == "step"][-1]["step"] == "perception"


def test_verify_streams_progress_and_result(client, home, monkeypatch):
    """The portal must call the CLI with exactly the documented flags and stream its progress."""
    seen = {}

    def fake_start(self, *, dms_id=None, pdf_path=None):
        seen["argv"] = [str(a) for a in [engine.ENGINE_PY, engine.PROCESS_PDF, "--mode", self.mode,
                                         str(dms_id), str(engine.RESULTS_DIR / f"{self.key}.json")]]
        seen["dms_id"], seen["quick"] = dms_id, self.quick
        out = engine.RESULTS_DIR / f"{self.key}.json"
        out.write_text(json.dumps(CONTRACT_RESULT), encoding="utf-8")
        self.result_path = out
        self.exit_code = 0
        self._emit({"type": "step", "step": "perception", "label": "Perception"})
        self._emit({"type": "log", "line": " [1/3] Running Perception (OCR + Layout + BBoxes)..."})
        self._emit({"type": "done", "exit_code": 0, "elapsed_s": 0.1, "ok": True, "error": None})
        self._emit(None)

    monkeypatch.setattr(engine.EngineRun, "start", fake_start)
    r = client.post("/api/verify/9001?mode=sandbox")
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    frames = [f for f in r.text.split("\n\n") if f.strip()]
    events = [l[6:].strip() for f in frames for l in f.split("\n") if l.startswith("event:")]
    assert "step" in events and "result" in events
    payload = [json.loads(l[5:].strip()) for f in frames for l in f.split("\n") if l.startswith("data:")]
    final = [p for p in payload if "result" in p][-1]
    assert final["ok"] is True and final["result"]["recommendation"]["value"] == "REVIEW"
    assert seen["dms_id"] == 9001 and seen["quick"] is False
    assert str(engine.PROCESS_PDF) in seen["argv"] and "--mode" in seen["argv"] and "sandbox" in seen["argv"]
    # the audit line is written for every portal-initiated run
    assert engine.RUN_LOG.exists() and "DMS-9001" in engine.RUN_LOG.read_text(encoding="utf-8")


def test_verify_rejects_unknown_mode(client):
    assert client.post("/api/verify/20?mode=banana").status_code == 400


class FakeProc:
    """Looks like a live subprocess until kill() is called."""

    def __init__(self) -> None:
        self.dead = False

    def poll(self):
        return 0 if self.dead else None

    def kill(self):
        self.dead = True


def _fake_run_starts():
    def never_ending(self, *, dms_id=None, pdf_path=None):
        self._proc = FakeProc()                                  # looks alive
        self._emit(None)
    return never_ending


def test_verify_refuses_duplicate_and_respects_cap(client, home, monkeypatch):
    monkeypatch.setattr(engine.EngineRun, "start", _fake_run_starts())
    assert client.post("/api/verify/20?mode=sandbox").status_code == 200
    assert client.post("/api/verify/20?mode=sandbox").status_code == 409      # same document twice
    assert client.post("/api/verify/21?mode=sandbox").status_code == 200
    assert client.post("/api/verify/22?mode=sandbox").status_code == 409      # concurrency cap = 2
    # cancel is addressed by the portal run key, and it kills the engine process
    assert client.post("/api/runs/20/cancel").status_code == 404              # no run keyed "20"
    assert client.post("/api/runs/DMS-20/cancel").status_code == 200
    assert client.get("/api/runs/DMS-20").json()["running"] is False


def test_runs_endpoint_lists_activity(client, home, monkeypatch):
    monkeypatch.setattr(engine.EngineRun, "start", _fake_run_starts())
    client.post("/api/verify/33?mode=sandbox")
    body = client.get("/api/runs").json()
    assert body["active"] == ["DMS-33"] and body["running"] == 1


# --------------------------------------------------------------------------- uploads and pages
def test_upload_pages_and_result_lookup(client, home):
    pdf = make_pdf(home["downloads"] / "sample-src.pdf", pages=2)
    data = pdf.read_bytes()
    import hashlib
    digest = hashlib.sha256(data).hexdigest()
    r = client.post("/api/upload", files={"file": ("sample.pdf", data, "application/pdf")})
    assert r.status_code == 200, r.text
    key = r.json()["key"]
    assert key.startswith("UP-sample-") and r.json()["page_count"] == 2
    assert client.get("/api/uploads").json()["uploads"][0]["key"] == key
    png = client.get(f"/api/uploads/{key}/page/1.png?dpi=100")
    assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert client.get(f"/api/uploads/{key}/page/9.png").status_code == 404
    assert client.get(f"/api/overlays/{key}").status_code == 404      # uploaded but not yet verified


def test_upload_rejects_non_pdf(client):
    r = client.post("/api/upload", files={"file": ("note.txt", b"hello", "text/plain")})
    assert r.status_code == 415


def test_uploaded_pdf_can_be_verified(client, home, monkeypatch):
    """Regression: '/api/verify/upload' must not be swallowed by '/api/verify/{doc_id}'.

    Starlette answers the first route whose pattern matches, and '{doc_id}' also matches the literal
    'upload'.  With the parameterised route registered first, the browser gets a 422 int-parsing
    error and the upload feature is dead while every other endpoint looks healthy.
    """
    pdf = make_pdf(home["downloads"] / "sample-src.pdf", pages=1)
    up = client.post("/api/upload", files={"file": ("sample.pdf", pdf.read_bytes(), "application/pdf")})
    key = up.json()["key"]

    def fake_start(self, *, dms_id=None, pdf_path=None):
        assert pdf_path is not None and dms_id is None, "an upload must reach the engine as a path"
        out = engine.RESULTS_DIR / f"{self.key}.json"
        out.write_text(json.dumps(CONTRACT_RESULT), encoding="utf-8")
        self.result_path, self.exit_code = out, 0
        self._emit({"type": "log", "line": "Processing 'sample.pdf'", "level": "info"})
        self._emit({"type": "done", "exit_code": 0, "elapsed_s": 0.1, "ok": True, "error": None})
        self._emit(None)

    monkeypatch.setattr(engine.EngineRun, "start", fake_start)
    r = client.post(f"/api/verify/upload?key={key}&mode=sandbox")
    assert r.status_code == 200, f"{r.status_code}: {r.text[:120]}"      # 422 => route order is wrong
    assert "text/event-stream" in r.headers["content-type"]
    assert '"recommendation"' in r.text
    assert client.get(f"/api/overlays/{key}").status_code == 200


def test_document_that_left_paperless_reads_as_not_found(client, monkeypatch):
    """A stale or deleted document id must not surface as a portal crash."""
    def boom(doc_id):
        raise RuntimeError("PAPERLESS_TRANSPORT: HTTPStatusError: Client error '404 Not Found' for "
                           "url 'http://dms/api/documents/999999/download/'")

    monkeypatch.setattr(catalog, "pdf_for", boom)
    for path in ("/api/documents/999999/page/1.png", "/api/documents/999999/pdf",
                 "/api/documents/999999/meta"):
        r = client.get(path)
        assert r.status_code == 404, (path, r.status_code, r.text[:90])
        assert "not in Paperless" in r.json()["detail"]


def test_paperless_outage_is_not_reported_as_not_found(client, monkeypatch):
    def down(doc_id):
        raise RuntimeError("PAPERLESS_TRANSPORT: ConnectTimeout: no detail")

    monkeypatch.setattr(catalog, "pdf_for", down)
    r = client.get("/api/documents/114/pdf")
    assert r.status_code == 502 and "cannot fetch" in r.json()["detail"]


def test_paperless_auth_and_missing_config_are_told_apart(client, monkeypatch):
    """Both strings are real shapes from src/system_a/adapters/paperless/reader.py."""
    def bad_token(doc_id):
        raise RuntimeError("PAPERLESS_AUTH: HTTP 401 — check PAPERLESS_API_TOKEN")

    monkeypatch.setattr(catalog, "pdf_for", bad_token)
    r = client.get("/api/documents/114/pdf")
    assert r.status_code == 502 and "PAPERLESS_API_TOKEN" in r.json()["detail"], r.json()

    def unconfigured(doc_id):
        raise RuntimeError("Paperless-ngx is not configured (PAPERLESS_BASE_URL / PAPERLESS_API_TOKEN)")

    monkeypatch.setattr(catalog, "pdf_for", unconfigured)
    r = client.get("/api/documents/114/pdf")
    assert r.status_code == 503 and "not configured" in r.json()["detail"], r.json()


def test_document_page_render_is_cached(client, home):
    pdf = make_pdf(engine.DOWNLOADS_DIR / "DMS-9002.pdf", pages=1)
    monkey_cache = home["pages"]
    first = client.get("/api/documents/9002/page/1.png?dpi=100")
    assert first.status_code == 200 and first.content[:4] == b"\x89PNG"
    assert list(monkey_cache.glob("*.png")), "raster must be cached for reuse"
    second = client.get("/api/documents/9002/page/1.png?dpi=100")
    assert second.content == first.content
    meta = json.loads(next(monkey_cache.glob("*.json")).read_text(encoding="utf-8"))
    assert meta["width_pt"] and meta["height_pt"] and meta["page_no"] == 1
    assert client.get("/api/documents/9002/page/3.png").status_code == 404


# --------------------------------------------------------------------------- catalog isolation
def test_documents_merges_stored_verdicts_without_network(client, stored, monkeypatch):
    def fake_search(**_kw):
        return {"count": 1, "page": 1, "page_size": 50,
                "results": [{"id": 9001, "title": "Invoice 26/2691", "page_count": 1, "tags": []},
                            {"id": 9002, "title": "Another", "page_count": 2, "tags": []}]}

    monkeypatch.setattr(catalog, "search_documents", fake_search)
    body = client.get("/api/documents?search=2691&page=1").json()
    rows = {r["id"]: r for r in body["results"]}
    assert rows[9001]["verdict"]["recommendation"] == "REVIEW"
    assert rows[9002]["verdict"] is None
    assert body["badges_available"] == 1


def test_documents_reports_dms_outage_instead_of_raising(client, monkeypatch):
    def boom(**_kw):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(catalog, "search_documents", boom)
    body = client.get("/api/documents").json()
    assert body["results"] == [] and "connection refused" in body["error"]


# --------------------------------------------------------------------------- frontend contract
def test_frontend_only_references_ids_that_exist_in_the_markup():
    """The UI has no build step, so an id typo is caught here instead of in the browser."""
    import re
    html = (WEB_DIR / "static" / "index.html").read_text(encoding="utf-8")
    declared = set(re.findall(r'id="([A-Za-z0-9_-]+)"', html))
    used: dict[str, set[str]] = {}
    patterns = (r"\$\(\s*['\"]#?([A-Za-z0-9_-]+)['\"]",            # app.js helper
                r"(?<![\w.])el\(\s*['\"]#?([A-Za-z0-9_-]+)['\"]",   # panels.js helper
                r"getElementById\(\s*['\"]#?([A-Za-z0-9_-]+)['\"]\s*\)")
    for js in sorted((WEB_DIR / "static" / "js").glob("*.js")):
        src = js.read_text(encoding="utf-8")
        refs = set()
        for pat in patterns:
            refs |= set(re.findall(pat, src))
        used[js.name] = refs
    missing = {f: sorted(r - declared) for f, r in used.items() if r - declared}
    assert not missing, f"JS references ids absent from index.html: {missing}"
    # the ids that carry the cross-highlighting contract must be wired up explicitly
    wired = set().union(*used.values())
    for must in ("overlay", "stage", "page-img", "verdict-card", "tabs", "engine-log", "steps",
                 "doclist", "uploads", "layers", "bbox-tooltip"):
        assert must in wired, f"{must} is not referenced by any JS module"


def test_frontend_ships_all_modules(client):
    for path in ("/static/index.html", "/static/styles.css", "/static/js/api.js", "/static/js/viewer.js",
                 "/static/js/bbox-overlay.js", "/static/js/interaction.js", "/static/js/panels.js",
                 "/static/js/app.js"):
        assert client.get(path).status_code == 200, path
    index = client.get("/").text
    for path in ("js/api.js", "js/viewer.js", "js/bbox-overlay.js", "js/interaction.js",
                 "js/panels.js", "js/app.js"):
        assert path in index, f"index.html does not load {path}"


def test_browser_modules_run_against_the_api_data(home):
    """Phase 4's cross-highlighting lives in JS, so the modules are executed against a stub DOM.

    web/test_ui_logic.mjs loads the real module sources in a vm context and asserts that panels
    fill from the overlay schema, that element_id joins work in both directions, and that box
    conversion honours the declared coordinate system.  Skipped where node is not installed.
    """
    import shutil
    import subprocess
    if not shutil.which("node"):
        pytest.skip("node not installed — browser-module checks skipped")
    fixture = home["results"] / "ui_fixture.json"
    fixture.write_text(json.dumps({"result": CONTRACT_RESULT,
                                   "overlays": portal_app.build_overlays(CONTRACT_RESULT)}), encoding="utf-8")
    proc = subprocess.run(["node", str(WEB_DIR / "test_ui_logic.mjs"), str(fixture)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "all checks passed" in proc.stdout, proc.stdout


def test_live_checker_fails_as_lines_when_the_portal_is_down():
    """web/check_live.py is used by a person, against a live server, usually when something is wrong.

    It cannot be driven from the offline suite (it needs a real server), which once let a plain
    NameError sit in it — invisible until someone tried to run it.  Pointed at a closed port it must
    still execute and answer with readable FAIL lines: that walks most of the module in ~1 s and
    turns "the checker itself is broken" into a normal test failure.
    """
    import subprocess
    proc = subprocess.run([sys.executable, str(WEB_DIR / "check_live.py"), "--base", "http://127.0.0.1:9"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, "a checker that reports success against a dead portal is useless"
    assert "Traceback" not in out and "NameError" not in out, out[-400:]
    assert "not answerable from this machine" in out, out[-400:]


def test_pdfjs_is_vendored_not_loaded_from_a_cdn(client):
    """The portal runs on an offline intranet, so the viewer bundle must be same-origin."""
    index = client.get("/").text
    assert "cdn.jsdelivr.net" not in index and "unpkg.com" not in index
    assert "/pdf/pdf.min.mjs" in index
    assert client.get("/pdf/pdf.min.mjs").status_code == 200
    assert client.get("/pdf/pdf.worker.min.mjs").status_code == 200
    viewer = client.get("/static/js/viewer.js").text
    assert "cdn.jsdelivr" not in viewer
    assert "/pdf/pdf.worker.min.mjs" in viewer
