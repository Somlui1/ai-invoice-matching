"""Live perception: System A's VisionPipeline on a document's PDF (or on a PDF built from its page images)."""
import pytest

from webapp.batch import BatchSource
from webapp.engine import InProcessEngine
from webapp.perception import LivePerception, PerceptionError, images_to_pdf
from webapp.service import DocumentService
from webapp.store import ResultStore


class FakeVlm:
    """Stands in for LiteLLM: answers the page-items call with a fixed page read (boxes in 0-1000)."""

    def __init__(self):
        self.calls = 0

    def chat_json(self, model, system, user, *, images=None, **kw):
        self.calls += 1
        return {"doc_type": "tax_invoice", "items": [
            {"type": "header", "label": "doc_no", "text": "SYN-LIVE-1", "bbox_2d": [600, 80, 900, 100], "confidence": 0.9},
            {"type": "header", "label": "po_number", "text": "PO NO. 50000001", "bbox_2d": [600, 110, 900, 130], "confidence": 0.9},
            {"type": "total", "label": "grand_total", "text": "Net Total 1,337.50", "bbox_2d": [550, 650, 950, 670], "confidence": 0.9},
            {"type": "line", "label": "line_1", "text": "1 BRACKET ASSY 10 PCS 100.00 1,000.00", "bbox_2d": [50, 300, 950, 320], "confidence": 0.9}]}


def pipeline(client):
    from system_a.perception.vision_pipeline import VisionPipeline
    return VisionPipeline(client, "fake-vlm", dpi=150, do_table=False, do_crops=False, do_classify=False)


def make(settings, batch, perception, oracle_dataset):
    return DocumentService(batch, perception, InProcessEngine(oracle_dataset), ResultStore(settings.data_dir), workers=2)


def test_images_become_a_pdf(batch_dir):
    import fitz
    b = BatchSource(batch_dir)
    pdf = images_to_pdf([b.image_path(102, 1), b.image_path(102, 2), b.image_path(102, 3)])
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        assert len(doc) == 3 and abs(doc[0].rect.width - 1240 * 72 / 150) < 1 and abs(doc[0].rect.height - 1754 * 72 / 150) < 1


def test_live_run_end_to_end(settings, oracle_dataset, tmp_path):
    batch = BatchSource(settings.batch_path)
    vlm = FakeVlm()
    live = LivePerception(batch, None, tmp_path / "pdf", pipeline=pipeline(vlm))
    svc = make(settings, batch, live, oracle_dataset)
    svc.start(102)                                                   # 3 page images -> PDF -> pipeline -> System A
    st = svc.wait(102)
    assert st["state"] == "done", st
    assert vlm.calls == 3                                            # one page-items call per page
    v = svc.view(102)
    assert v["perception"] == "live" and v["engine"] == "inprocess" and v["replay"] is None
    assert [len(p["kept"]) for p in v["pages"]] == [4, 4, 4]
    b0 = v["pages"][0]["kept"][0]["bbox_norm"]
    assert 0.55 < b0[0] < 0.65 and 0 <= b0[1] < 0.1 and v["pages"][0]["kept"][0]["bbox_px"]   # 0-1000 box -> normalised
    ext = svc.part(102, "extraction")
    assert ext["extra"]["live"]["input"] == "images->pdf" and ext["extractor"]["vlm"] == "fake-vlm"
    names = {f["name"]: f for f in v["final"]["fields"]}
    assert names["invoice_num"]["raw"] == "SYN-LIVE-1" and names["invoice_num"]["ref"]["page"] in (1, 2, 3)
    svc.shutdown()


def test_live_prefers_a_real_pdf(settings, oracle_dataset, tmp_path):
    batch = BatchSource(settings.batch_path)
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    (pdf_dir / "doc_101.pdf").write_bytes(images_to_pdf([batch.image_path(101, 1)]))
    live = LivePerception(batch, pdf_dir, tmp_path / "pdf", pipeline=pipeline(FakeVlm()))
    assert live.pdf_bytes(101)[1] == "pdf:doc_101.pdf"
    assert live.pdf_bytes(102)[1] == "images->pdf"


def test_live_without_pdf_or_images_is_an_error_on_that_document(settings, oracle_dataset, tmp_path):
    batch = BatchSource(settings.batch_path)
    live = LivePerception(batch, None, tmp_path / "pdf", pipeline=pipeline(FakeVlm()))
    with pytest.raises(PerceptionError, match="nothing to read"):
        live.extract(105)                                            # #105 has no page JPG on disk
    svc = make(settings, batch, live, oracle_dataset)
    svc.start(105)
    st = svc.wait(105)
    assert st["state"] == "error" and "nothing to read" in st["error"]
    svc.start(101)
    assert svc.wait(101)["state"] == "done"                          # the other documents are fine
    svc.shutdown()


def test_a_failing_vlm_is_reported(settings, oracle_dataset, tmp_path):
    class Down:
        def chat_json(self, *a, **k):
            raise RuntimeError("gateway timeout")
    batch = BatchSource(settings.batch_path)
    svc = make(settings, batch, LivePerception(batch, None, tmp_path / "pdf", pipeline=pipeline(Down())), oracle_dataset)
    svc.start(101)
    st = svc.wait(101)
    # System A records a failed page read as a page error; the document is still validated (V-01 will say what is missing)
    assert st["state"] in ("done", "error")
    if st["state"] == "done":
        assert svc.view(101)["pages"][0]["error"] or svc.view(101)["exception_codes"]
    svc.shutdown()
