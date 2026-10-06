"""The Paperless document source: the list, the document's own file, page renders - and a live run on it.

No network: a ``FakeReader`` stands in for ``system_a.adapters.paperless.reader.PaperlessReader`` and answers
with PDFs/PNGs built by PyMuPDF - the same library System A uses to read them.
"""
import dataclasses
import threading

import pytest

from webapp.batch import BatchDoc, BatchError
from webapp.engine import InProcessEngine
from webapp.paperless import PaperlessSource
from webapp.perception import LivePerception
from webapp.service import DocumentService
from webapp.store import MemoryStore

from test_live import FakeVlm, pipeline


def make_pdf(pages=1, w=595, h=842) -> bytes:
    import fitz
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=w, height=h)
    out = doc.tobytes()
    doc.close()
    return out


def make_png(w=400, h=300) -> bytes:
    import fitz
    doc = fitz.open()
    doc.new_page(width=w, height=h)
    out = doc[0].get_pixmap(dpi=72).tobytes("png")
    doc.close()
    return out


class Doc:
    def __init__(self, doc_id, *, title, file_class="pdf", page_count=None, mime="application/pdf"):
        self.doc_id, self.title, self.file_class = doc_id, title, file_class
        self.page_count, self.mime_type = page_count, mime
        self.file_name = f"{title}.{file_class}"
        self.document_type, self.created, self.correspondent = "Invoice", "2026-02-01", "SUP CO"


class FakeReader:
    base = "http://dms.test"

    def __init__(self, docs, files):
        self.docs, self.files, self.tags = docs, files, [(7, "INVOICE"), (8, "OTHER")]
        self.downloads, self.last_count = 0, len(docs)

    def tag_ids_for(self, names, *, mode="insensitive"):
        return [t for t in self.tags if t[1].lower() in {n.lower() for n in names}]

    def list_documents(self, *, tag_ids=None, limit=None, **kw):
        return self.docs[:limit] if limit else self.docs

    def document(self, doc_id):
        return next(d for d in self.docs if d.doc_id == int(doc_id))

    def download(self, doc_id):
        self.downloads += 1
        return self.files[int(doc_id)]

    def health(self):
        return {"ok": True, "count": len(self.docs)}


@pytest.fixture
def reader():
    return FakeReader(
        [Doc(11, title="INV 11"), Doc(12, title="INV 12", page_count=1),
         Doc(13, title="scan 13", file_class="image", mime="image/jpeg")],
        {11: make_pdf(3), 12: make_pdf(1), 13: make_png()})


@pytest.fixture
def source(reader):
    return PaperlessSource(reader, limit=50, tags=["INVOICE"], render_dpi=150).refresh()


def test_the_list_becomes_the_shape_the_ui_already_knows(source):
    assert source.kind == "paperless" and source.owns_pdf and source.root is None
    d = source.get(11)
    assert isinstance(d, BatchDoc) and d.title == "INV 11" and d.ptype == "invoice" and d.file_class == "pdf"
    assert d.dms_url == "http://dms.test/documents/11/" and d.created == "2026-02-01" and d.correspondent == "SUP CO"
    assert [p.page for p in source.get(12).pages] == [1]
    assert source.tag_ids == [7] and source.unmatched_tags == []
    assert source.base_url == "http://dms.test" and source.viewer_url(12) == "http://dms.test/documents/12/"


def test_the_page_count_comes_from_the_file_not_from_the_api(source):
    assert source.get(11).pages_total == 0                     # Paperless had not counted this one
    source.ensure(11)
    assert source.get(11).pages_total == 3 and [p.page for p in source.get(11).pages] == [1, 2, 3]
    assert source.page_size_px(11, 2) == (1240, 1754)          # A4 at the DPI the pages are drawn at


def test_a_document_is_downloaded_once_even_when_every_page_is_asked_at_once(source):
    got, err = {}, []

    def grab(n):
        try:
            got[n] = source.page_image(11, n)
        except Exception as e:                                # the browser asks for every page at once
            err.append(e)

    ts = [threading.Thread(target=grab, args=(n,)) for n in (1, 2, 3, 1, 9)]
    [t.start() for t in ts]
    [t.join(timeout=30) for t in ts]
    assert not err, err
    assert source.reader.downloads == 1, "the file of one document must be fetched once, not once per page"
    png, media = got[1]
    assert media == "image/png" and png[:8] == b"\x89PNG\r\n\x1a\n"
    assert got[9] is None                                     # past the end: no image, and no crash


def test_an_image_document_is_wrapped_into_a_pdf(source):
    raw, origin = source.pdf_bytes(13)
    assert raw[:4] == b"%PDF" and origin == "dms:image->pdf"
    assert source.get(13).pages_total == 1
    assert source.page_size_px(13, 1) == (400, 300)            # 1 PDF point = 1 pixel at the render DPI


def test_a_broken_dms_keeps_the_list_it_already_had(reader, source):
    def boom(*a, **kw):
        raise RuntimeError("connection refused")
    reader.list_documents = boom
    source.refresh()
    assert source.list_error and "connection refused" in source.list_error
    assert [d.id for d in source.docs] == [11, 12, 13]         # the portal is still usable
    assert source.stats()["list_error"] == source.list_error
    assert source.stats()["dms_total"] == 3 and source.stats()["render_dpi"] == 150


def test_unknown_document_and_empty_file_are_errors(source):
    with pytest.raises(KeyError):
        source.get(999)
    source.reader.files[12] = b""
    with pytest.raises(BatchError):
        source.pdf_bytes(12)


def test_live_run_on_a_paperless_document(settings, oracle_dataset, tmp_path, reader):
    """The whole point of the mode: the file of the DMS itself, read here and now by System A."""
    src = PaperlessSource(reader, limit=50, render_dpi=150).refresh()
    per = LivePerception(src, None, tmp_path / "pdf", pipeline=pipeline(FakeVlm()))
    svc = DocumentService(src, per, InProcessEngine(oracle_dataset), MemoryStore(), workers=2)
    svc.start(11)
    st = svc.wait(11)
    assert st["state"] == "done", st
    assert st["kept"] == 12 and st["types"]                                    # one page read per PDF page
    v = svc.view(11)
    assert v["perception"] == "live" and len(v["pages"]) == 3
    box = v["pages"][0]["kept"][0]
    assert box["bbox_norm"] and all(0 <= c <= 1 for c in box["bbox_norm"]) and box["bbox_px"]
    assert box["bbox_norm"][0] == pytest.approx(box["bbox_px"][0] / 1240, abs=1e-3)
    assert svc.part(11, "extraction")["extra"]["live"]["input"] == "dms:pdf"
    assert svc.store.root is None and svc.store.ids() == [11]                 # nothing written to disk
    svc.shutdown()


def test_api_with_a_paperless_source_holds_nothing_on_disk(settings, oracle_dataset, tmp_path, reader):
    from fastapi.testclient import TestClient
    from webapp.build import build_all
    src = PaperlessSource(reader, limit=50, render_dpi=150).refresh()
    settings = dataclasses.replace(settings, data_dir=tmp_path / "data", persist_results=False, perception="live")
    app, svc, batch = build_all(settings, source=src, engine=InProcessEngine(oracle_dataset),
                                perception=LivePerception(src, None, tmp_path / "pdf", pipeline=pipeline(FakeVlm())))
    c = TestClient(app)
    m = c.get("/api/meta").json()
    assert m["source"]["kind"] == "paperless" and m["persist"] is False and m["render_dpi"] == 150
    assert m["batch"] == m["source"] and m["source"]["documents"] == 3
    docs = c.get("/api/documents").json()
    assert [d["id"] for d in docs] == [11, 12, 13]
    assert docs[0]["viewer_url"] == "http://dms.test/documents/11/" and docs[0]["file_class"] == "pdf"
    assert c.get("/api/documents/11").json()["pages_total"] == 3              # the file counted the pages
    assert c.get("/api/documents/99").status_code == 404
    p = c.get("/api/documents/11/pdf")
    assert p.status_code == 200 and p.content[:4] == b"%PDF"
    img = c.get("/api/documents/13/pages/1/image")                            # not counted yet, still renders
    assert img.status_code == 200 and img.content[:4] == b"\x89PNG"
    assert c.get("/api/documents/13/pages/9/image").status_code == 404
    assert c.post("/api/documents/12/process").status_code == 202
    assert svc.wait(12)["state"] == "done"
    v = c.get("/api/documents/12/result").json()
    assert v["pages"][0]["kept"] and v["final"]["fields"] and v["verify"] and v["search"]
    assert not (tmp_path / "data").exists()                                   # WEBAPP_PERSIST=false: no folder at all
    assert c.delete("/api/documents/12/result").json()["state"] == "idle"
    assert c.get("/api/documents/12/result").status_code == 409
    assert c.post("/api/documents/refresh").json()["documents"] == 3
