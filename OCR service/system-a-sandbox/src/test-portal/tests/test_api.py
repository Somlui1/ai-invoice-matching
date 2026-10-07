"""The HTTP surface.  Everything the browser may ask for, and what it gets when System A has (not) produced it."""
import time

import pytest

from webapp.view import DEFAULT_TYPES, ELEMENT_TYPES


def process_and_wait(client, doc_id=101, timeout=20):
    r = client.post(f"/api/documents/{doc_id}/process")
    assert r.status_code == 202, r.text
    import time
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = client.get(f"/api/documents/{doc_id}").json()
        if st["state"] != "processing":
            return st
        time.sleep(0.05)
    raise AssertionError(f"#{doc_id} still processing")


def test_the_ui_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "id=types" in r.text and "id=main" in r.text and 'src="/static/app.js"' in r.text
    assert r.headers["cache-control"] == "no-store"
    js = client.get("/static/app.js")
    assert js.status_code == 200 and "application/javascript" in js.headers["content-type"]


def test_meta_says_what_this_instance_is_wired_to(client, settings):
    m = client.get("/api/meta").json()
    assert m["engine"] == settings.engine == "inprocess" and m["mode"] == "sandbox"
    assert m["source"]["kind"] == "paperless" and m["source"]["documents"] == 3 and m["source"]["tag"] == "invoice"
    assert m["render_dpi"] == 96 and m["system_a"] == str(settings.system_a_home)
    assert m["colors"]["field"] and m["element_types"][0] == "field"
    assert list(m["element_types"]) == list(ELEMENT_TYPES) and list(m["default_types"]) == list(DEFAULT_TYPES)


def test_health_reports_system_a_and_the_dms(client):
    h = client.get("/api/health")
    assert h.status_code == 200
    b = h.json()
    assert b["ok"] is True and b["kind"] == "paperless" and b["documents"] == 3
    assert b["engine"]["standard"] and b["engine"]["mode"] == "sandbox"
    assert b["source"]["base_url"] == "http://dms.test" and b["source"]["dms_total"] == 3


def test_health_is_503_when_system_a_is_not_usable(settings, sa, catalog):
    from doubles import FakeRunner
    from fastapi.testclient import TestClient
    from webapp.app import create_app
    from webapp.service import DocumentService
    from webapp.store import ResultStore

    class Down(FakeRunner):
        def health(self):
            return {"engine": "inprocess", "ok": False, "error": "system_a not importable"}

    svc = DocumentService(catalog, Down(), ResultStore(settings.data_dir), workers=1, mode="sandbox")
    with TestClient(create_app(settings, svc, catalog)) as c:
        r = c.get("/api/health")
        assert r.status_code == 503 and r.json()["ok"] is False and "not importable" in r.json()["engine"]["error"]
    svc.shutdown()


def test_the_document_list_carries_state_and_dms_links(client):
    docs = client.get("/api/documents").json()
    assert [d["id"] for d in docs] == [101, 102, 103]
    d = docs[0]
    assert d["state"] == "idle" and d["run"] == 0 and d["boxes"] == 0 and d["error"] is None
    assert d["title"] == "SYNTHETIC INVOICE 101" and d["file_class"] == "pdf"
    assert d["viewer_url"] == "http://dms.test/documents/101/"
    assert d["pages"] == [1] and d["pages_total"] == 1 and d["created"] == "2026-10-01"


def test_refresh_re_reads_the_list_from_the_dms(client, catalog):
    catalog.docs.pop()
    r = client.post("/api/documents/refresh")
    assert r.status_code == 200 and r.json()["documents"] == 3
    assert [d["id"] for d in client.get("/api/documents").json()] == [101, 102, 103]


def test_refresh_reports_an_unreachable_dms_as_502(settings, sa):
    from doubles import FakeReader, FakeRunner
    from fastapi.testclient import TestClient
    from webapp.app import create_app
    from webapp.catalog import Catalog, CatalogError
    from webapp.service import DocumentService
    from webapp.store import ResultStore

    sa.reader = FakeReader(list_raises=ConnectionError("dms down"))
    cat = Catalog(sa, tag="invoice")                           # the reader is taken from sa.container
    with pytest.raises(CatalogError):
        cat.refresh()                                          # an empty list is never passed off as "no documents"
    assert cat.list_error == "ConnectionError: dms down"
    svc = DocumentService(cat, FakeRunner(payload=sa.payload), ResultStore(settings.data_dir),
                          workers=1, mode="sandbox")
    with TestClient(create_app(settings, svc, cat)) as c:
        r = c.post("/api/documents/refresh")
        assert r.status_code == 502 and "ConnectionError: dms down" in r.json()["detail"]
    svc.shutdown()


def test_one_document_answers_with_its_source_state(client, sa):
    r = client.get("/api/documents/102")
    assert r.status_code == 200
    b = r.json()
    assert (b["id"], b["state"]) == (102, "idle") and b["source_error"] is None
    assert ("image", 102) not in [(c[0], c[1]) for c in sa.calls if c[0] == "image"]
    assert client.get("/api/documents/9999").status_code == 404


def test_processing_a_document_then_reading_the_result(client, payload):
    st = process_and_wait(client)
    assert st["state"] == "done" and st["cls"] == "ok" and st["boxes"] == len(payload["ocr"]["elements"])
    v = client.get("/api/documents/101/result")
    assert v.status_code == 200 and v.headers["cache-control"] == "no-store"
    b = v.json()
    assert b["contract"] == "aiva.system_a.result/3.0" and b["recommendation"]["value"] == "AUTO_PASS"
    assert len(b["pages"][0]["elements"]) == len(payload["ocr"]["elements"])
    assert [i["label"] for i in b["final"]["items"]][:3] == ["เลขที่เอกสาร", "วันที่เอกสาร", "เลขที่ PO"]
    assert b["final"]["items"][0]["value"] == "SYN-INV-0001"          # the final value, with its element behind it
    assert b["elements"][b["final"]["items"][0]["refs"][0]]["field"] == "invoice_num"
    assert [r["id"] for r in b["rules"]] == [f"V-0{i}" for i in range(1, 10)]
    assert b["lines"]["items"][0]["desc"] == "BRACKET ASSY"
    assert b["receipt"]["receipt_nums"] == ["RCV-0000010001"]


def test_the_payload_endpoint_returns_system_as_own_bytes(client, payload):
    process_and_wait(client)
    r = client.get("/api/documents/101/payload")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert r.json() == payload                                  # nothing added, nothing filtered
    assert r.json()["integrity"]["payload_sha256"] == payload["integrity"]["payload_sha256"]


def test_the_extraction_endpoint_is_the_block_inside_the_payload(client, payload):
    """The raw reading System A echoed in its own result - the same bytes, cut out for convenience."""
    process_and_wait(client)
    r = client.get("/api/documents/101/extraction")
    assert r.status_code == 200
    assert r.json() == payload["extraction"]
    assert set(r.json()) == {"invoice_document_id", "fields", "lines", "signatures", "extra"}
    assert r.json()["fields"]["invoice_num"]["normalized_value"] == "SYN-INV-0001"
    assert r.json()["fields"]["invoice_num"]["element_id"] == "D1-f-invoice_num"   # same id as the box drawn
    assert r.json()["lines"][0]["line_no"] == 1 and r.json()["lines"][0]["element_id"] == "D1-L1"
    assert r.json()["signatures"]["receiver"]["present"] is True
    assert "dropped_items" in r.json()["extra"]


def test_result_and_payload_are_409_until_the_document_has_been_processed(client):
    for path in ("result", "payload", "extraction"):
        r = client.get(f"/api/documents/101/{path}")
        assert r.status_code == 409 and "idle" in r.json()["detail"], (path, r.text)
    process_and_wait(client)
    for path in ("result", "payload", "extraction"):
        assert client.get(f"/api/documents/101/{path}").status_code == 200


def test_a_running_document_refuses_a_second_run(settings, sa, catalog):
    from fastapi.testclient import TestClient
    from webapp.app import create_app
    from webapp.service import DocumentService
    from webapp.store import ResultStore

    class Slow:
        name = "inprocess"

        def run(self, doc_id, *, run):
            time.sleep(0.5)
            return sa.payload

        def health(self):
            return {"engine": "inprocess", "ok": True}

    svc = DocumentService(catalog, Slow(), ResultStore(settings.data_dir), workers=2, mode="sandbox")
    with TestClient(create_app(settings, svc, catalog)) as c:
        assert c.post("/api/documents/101/process").status_code == 202
        busy = c.post("/api/documents/101/process")
        assert busy.status_code == 409 and "already being processed" in busy.json()["detail"]
        assert c.delete("/api/documents/101/result").status_code == 409
        while c.get("/api/documents/101").json()["state"] == "processing":
            time.sleep(0.05)
    svc.shutdown()


def test_a_system_a_failure_reaches_the_browser_as_an_error(settings, catalog):
    from fastapi.testclient import TestClient
    from webapp.app import create_app
    from webapp.service import DocumentService
    from webapp.store import ResultStore
    from webapp.sysa import SystemAError
    class Boom:
        name = "inprocess"

        def run(self, doc_id, *, run):
            raise SystemAError("System A failed on #101: RuntimeError: no page items",
                               traceback='File "process_pdf.py", line 200\nRuntimeError: no page items',
                               exc_type="RuntimeError")

        def health(self):
            return {"engine": "inprocess", "ok": True}

    svc = DocumentService(catalog, Boom(), ResultStore(settings.data_dir), workers=1, mode="sandbox")
    with TestClient(create_app(settings, svc, catalog)) as c:
        assert c.post("/api/documents/101/process").status_code == 202
        while c.get("/api/documents/101").json()["state"] == "processing":
            time.sleep(0.05)
        st = c.get("/api/documents/101").json()
        assert st["state"] == "error" and "no page items" in st["error"]
        assert "process_pdf.py" in st["traceback"]
        assert c.get("/api/documents/101/result").status_code == 409
    svc.shutdown()


def test_the_result_of_a_document_is_deleted_not_replaced(client, sa):
    process_and_wait(client)
    assert client.get("/api/documents/101/result").status_code == 200
    r = client.delete("/api/documents/101/result")
    assert r.status_code == 200 and r.json()["state"] == "idle"
    assert client.get("/api/documents/101/result").status_code == 409
    process_and_wait(client, 102)
    assert client.delete("/api/documents/101/result").status_code == 200   # idempotent on an empty one
    assert client.get("/api/documents/102/result").status_code == 200      # the neighbour keeps its result


def test_the_pdf_and_the_page_image_come_from_the_document_itself(client, sa):
    r = client.get("/api/documents/101/pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF") and b"101" in r.content
    assert 'inline; filename="DMS-101.pdf"' in r.headers["content-disposition"]
    img = client.get("/api/documents/101/pages/1/image")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert img.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert ("image", 101, 1, 96) in sa.calls                    # rendered at the portal's render_dpi


def test_a_file_that_cannot_be_read_is_reported_as_502(client, sa, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("paperless 403")

    monkeypatch.setattr(sa, "pdf_bytes", boom)
    monkeypatch.setattr(sa, "page_image", boom)
    for url in ("/api/documents/101/pdf", "/api/documents/101/pages/1/image"):
        r = client.get(url)
        assert r.status_code == 502, r.text
        assert "paperless 403" in r.json()["detail"]
        assert "<svg" not in r.text                             # no stand-in image is invented


def test_search_returns_ids_of_processed_documents_only(client):
    assert client.get("/api/search?q=bracket").json() == {"q": "bracket", "ids": []}
    process_and_wait(client)
    assert client.get("/api/search?q=bracket").json()["ids"] == [101]
    assert client.get("/api/search?q=101").json()["ids"] == [101]
    assert client.get("/api/search?q=nothing-here").json()["ids"] == []
    assert client.get("/api/search").json() == {"q": "", "ids": []}


def test_the_api_exposes_only_the_paths_of_this_portal(client):
    paths = {r.path for r in client.app.routes if r.path.startswith("/api")}
    assert paths == {"/api/meta", "/api/health", "/api/documents", "/api/documents/refresh", "/api/documents/{doc_id}",
                     "/api/documents/{doc_id}/process", "/api/documents/{doc_id}/result",
                     "/api/documents/{doc_id}/payload", "/api/documents/{doc_id}/extraction",
                     "/api/documents/{doc_id}/pdf", "/api/documents/{doc_id}/pages/{page}/image", "/api/search"}
    for gone in ("/api/batch", "/api/replay", "/api/placeholder", "/api/extraction-file", "/api/demo"):
        assert client.get(gone).status_code == 404
