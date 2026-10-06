"""OCR / bbox improvements (perception) and the normalised item list (result contract).

Each test names the measured case it protects (DMS-xx = results/paperless_invoices).
"""
import io
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from system_a.domain.contracts import RawField, RawLine, Region  # noqa: E402
from system_a.domain.normalize import Invalid, date_iso  # noqa: E402
from system_a.perception.text_layer import layer_unreliable  # noqa: E402
from system_a.perception import vision_pipeline as vp  # noqa: E402


# ----------------------------------------------------------------------------------------------- bbox_testv3 alignment
def test_layer_unreliable():
    assert layer_unreliable("ษั ท อ ไป โก ไฮ เท ค ท ู ล ล ิ ่ ง vida")
    assert not layer_unreliable("TEL: (AUTO) (038) 545 999")
    assert not layer_unreliable(None)


@pytest.mark.parametrize("mx,w,h,mode", [(0.9, 1240, 1754, "norm1"), (998, 1240, 1754, "norm1000"),
                                         (1240, 1240, 1754, "pixel"), (900, 1000, 1000, "pixel")])
def test_coordinate_rule_is_bbox_testv3(mx, w, h, mode):
    from system_a.perception.coords import choose_coord_mode
    words = [{"bbox": (0.1, 0.1, 0.05, 0.01)}] * 5          # the text layer must not influence the decision
    assert choose_coord_mode([[1, 1, mx, mx / 2]], w, h, words) == mode


def test_v3_message_layout():
    """One user message, image first, prompt after it, no system message, no response_format (bbox_testv3)."""
    from system_a.adapters.llm.litellm_client import LiteLLMClient
    c = LiteLLMClient("http://x", "k")
    sent = {}
    c._post = lambda body: (sent.update(body), '{"items": []}')[1]
    c.chat_json("m", "SYSTEM PROMPT", "do it", images=["data:image/png;base64,AA"], json_mode=False, layout="v3")
    msgs = sent["messages"]
    assert len(msgs) == 1 and msgs[0]["role"] == "user" and "response_format" not in sent
    assert msgs[0]["content"][0]["type"] == "image_url" and msgs[0]["content"][1]["text"].startswith("SYSTEM PROMPT")


def test_paperless_downloads_the_original_first():
    import httpx
    from system_a.adapters.paperless.reader import PaperlessReader
    seen = []

    def h(req):
        seen.append(str(req.url))
        return httpx.Response(200, content=b"%PDF-1.4 original")
    r = PaperlessReader("http://dms", "t", transport=httpx.MockTransport(h))
    assert r.download(15) == b"%PDF-1.4 original" and "original=true" in seen[0]


def test_paperless_falls_back_to_archive_when_original_is_an_image():
    import httpx
    from system_a.adapters.paperless.reader import PaperlessReader

    def h(req):
        return httpx.Response(200, content=b"\xff\xd8jpeg" if "original" in str(req.url) else b"%PDF archive")
    assert PaperlessReader("http://dms", "t", transport=httpx.MockTransport(h)).download(1) == b"%PDF archive"


def test_cells_use_the_page_read_row_box():
    read = vp.PageRead(page_no=1, items=[{"label": "line_1", "bbox": (0.05, 0.33, 0.9, 0.02)},
                                         {"label": "line_2", "bbox": (0.05, 0.36, 0.9, 0.02)}])
    assert vp.row_box_from_page(read, (0.04, 0.332, 0.91, 0.018)) == (0.05, 0.33, 0.9, 0.02)
    assert vp.row_box_from_page(read, (0.04, 0.50, 0.91, 0.018)) is None


# ----------------------------------------------------------------------------------------------- values
@pytest.mark.parametrize("raw,iso", [("08/07/2026", "2026-07-08"), ("04/09/26", "2026-09-04"),
                                     ("2026/09/02", "2026-09-02"), ("02/09/2569", "2026-09-02"),
                                     ("01/09/69", "2026-09-01")])
def test_date_formats(raw, iso):
    """DMS-21 (dd/mm/yy) and DMS-24 (yyyy/mm/dd) were DATE_FORMAT errors."""
    assert date_iso(raw) == iso


def test_bad_date_is_still_rejected():
    with pytest.raises(Invalid):
        date_iso("31/13/2026")


def test_date_pattern_takes_the_whole_year():
    """DMS-24: "9290186640/ 2026/09/02" was cut to 26/09/02 (-> 2002-09-26)."""
    assert vp.extract_value("invoice_date", "9290186640/ 2026/09/02")[0] == "2026/09/02"


def test_shapes():
    assert vp.shape_ok("customer_tax_id", "0-1455-48001-55-7") and not vp.shape_ok("customer_tax_id", "13160")
    assert vp.shape_ok("po_number", "40117545-975") and not vp.shape_ok("po_number", "A002")
    assert vp.shaped_value("sub_total", "ร ว ม 49,215.00 ‘4") == "49,215.00"


def test_strip_label():
    assert vp.strip_label("customer_name", "ชื่อผู้ซื้อ SOLD TO บริษัท อาปิโก จำกัด") == "บริษัท อาปิโก จำกัด"
    both = "POLAR STAR ENGINEERING (THAILAND) CO.,LTD. (Head Office) บริษัท โพลาร์ สตาร์ จำกัด"
    assert vp.strip_label("supplier_name", both) == both          # bilingual name, not a label
    assert vp.strip_label("customer_address", "ที่อยู่ บริษัท x") == "ที่อยู่ บริษัท x"


def test_grand_total_prefers_the_largest_amount_on_the_page():
    opts = [(1, {"text": "TOTAL / BAHT 49,215.00", "confidence": 0.9}),
            (1, {"text": "GRAND TOTAL 52,660.05", "confidence": 0.9})]
    assert vp.pick_candidate("grand_total", opts, 1)[1]["text"].endswith("52,660.05")


def test_shape_valid_candidate_wins():
    opts = [(1, {"text": "13160", "confidence": 0.99}), (1, {"text": "Tax ID 0145548001557", "confidence": 0.8})]
    assert vp.pick_candidate("customer_tax_id", opts, 1)[1]["text"].endswith("0145548001557")


def _rf(raw, agree=True, conf=0.96, page=1, bbox=(0.5, 0.5, 0.1, 0.01)):
    return RawField(raw=raw, confidence=conf, agreement=agree, region=Region(page=page, bbox=bbox))


def test_reconcile_grand_total():
    """DMS-20: grand_total = 49,215.00 (the sub-total) -> E03; 52,660.05 is printed on the invoice."""
    fields = {"sub_total": _rf("49,215.00"), "vat": _rf("3,445.05"), "grand_total": _rf("49,215.00")}
    cands = {"grand_total": [(1, {"text": "TOTAL / BAHT 49,215.00", "bbox": (0.6, 0.69, 0.3, 0.01)}),
                             (2, {"text": "GRAND TOTAL 52,660.05", "bbox": (0.9, 0.74, 0.07, 0.015)})]}
    log = []
    vp.reconcile_grand_total(fields, cands, log)
    assert fields["grand_total"].raw == "52,660.05" and fields["grand_total"].region.page == 2 and log


def test_po_from_lines():
    """DMS-15: po_number = customer code A002; the item rows print 40117545-975."""
    read = vp.PageRead(page_no=1, items=[{"label": "line_1", "text": "40117545-975 NM-A002-ED029-0001 BRACKET 50 PCS 4.42 221.00",
                                          "bbox": (0.01, 0.345, 0.9, 0.02)}])
    fields = {"po_number": _rf("A002")}
    log = []
    layers = {1: {"words": [{"text": "40117545-975", "bbox": (0.03, 0.346, 0.08, 0.01)}]}}
    vp.po_from_lines(fields, {1: read}, [1], log, layers)
    assert fields["po_number"].raw == "40117545-975" and fields["po_number"].agreement and fields["po_number"].source == "derived"


def test_po_from_lines_does_not_guess_between_two_pos():
    read = vp.PageRead(page_no=1, items=[{"label": "line_1", "text": "40117545-1 X", "bbox": (0, 0, 1, 0.01)},
                                         {"label": "line_2", "text": "40117546-2 Y", "bbox": (0, 0.1, 1, 0.01)}])
    fields = {"po_number": _rf("A002")}
    vp.po_from_lines(fields, {1: read}, [1], [])
    assert fields["po_number"].raw == "A002"


def test_corroborate_rows_units_and_totals():
    """DMS-15/19/21/24: cells marked CONFLICT only because the layer read "50 PCS" as "OPCS"."""
    cells = {"qty": _rf("50", agree=False, conf=0.7), "uom": _rf("PCS", agree=False, conf=0.7),
             "unit_price": _rf("4.42"), "amount": _rf("221.00")}
    lines = [RawLine(line_no=1, cells=cells)]
    fields = {"sub_total": _rf("221.00", agree=False, conf=0.7), "vat": _rf("15.47"), "grand_total": _rf("236.47")}
    out = vp.corroborate(fields, lines, {"PCS"})
    assert lines[0].cells["qty"].agreement and lines[0].cells["uom"].agreement and fields["sub_total"].agreement
    assert len(out) == 2


def test_corroborate_never_hides_an_arithmetic_error():
    cells = {"qty": _rf("10", agree=False, conf=0.7), "unit_price": _rf("100.00"), "amount": _rf("1,200.00")}
    lines = [RawLine(line_no=1, cells=cells)]
    vp.corroborate({}, lines, set())
    assert lines[0].cells["qty"].agreement is False


@pytest.mark.parametrize("text,exp", [
    ("1 LOCATING KEY : B-LK 20-60 #94A01,94A04 1 PCS 62.00 62.00", ("1", "PCS", "62.00", "62.00")),
    ("1 FL G05 95 x 220 x 250 2 PCS 83.08 6,950.00 13,900.00", ("2", "PCS", "6,950.00", "13,900.00")),
    ("จำนวน 30 PC 596.40 THB 17,892.00", ("30", "PC", "596.40", "17,892.00")),
])
def test_cells_from_row_text(text, exp):
    c = vp.cells_from_row_text(text)
    assert (c["qty"], c["uom"], c["unit_price"], c["amount"]) == exp


def test_wrapped_description_joins_the_item_above():
    """DMS-22: "( Project:AHD_AS ..., Task:07.2 - DFG0011022A )" became an item with 4 NOT_PRESENT cells."""
    read = vp.PageRead(page_no=5, items=[
        {"label": "line_1", "text": "10 SPOOL RETAINER : B-CSRE 16-70-S20 4 PCS 344.00 1,376.00", "bbox": (0.05, 0.53, 0.87, 0.013)},
        {"label": "line_2", "text": "( Project:AHD_AS (P703 BUNDLE 1.6), Task:07.2 - DFG0011022A )", "bbox": (0.1, 0.556, 0.35, 0.031)}])
    rows = vp.rows_from_line_items(read)
    assert len(rows) == 1 and "Project" in rows[0]["cells"]["description"]["text"] and rows[0]["cells"]["amount"]["text"] == "1,376.00"


def _row(q, p, a):
    return ({"qty": _rf(q), "unit_price": _rf(p), "amount": _rf(a)}, None)


def test_printed_copy_is_dropped_even_with_noise():
    """DMS-24 (date in the number region, "596.40 THB") and DMS-22 (number read as 1690s0082, a delivery-order copy)."""
    rows1 = [_row("30", "596.40", "17,892.00"), _row("2", "62.00", "124.00")]
    rows2 = [_row("30", "596.40 THB", "17,892.00"), ({"description": _rf("( Project x )")}, None),
             _row("2", "62.00", "124.00")]
    read1 = vp.PageRead(page_no=1, items=[{"label": "doc_no", "text": "9290186640/ 2026/09/02"}])
    read2 = vp.PageRead(page_no=2, items=[{"label": "doc_no", "text": "9290186640"}])
    kept, notes = vp.drop_duplicate_copies({1: rows1, 2: rows2}, {1: "TAX_INVOICE", 2: "DELIVERY_NOTE"},
                                           {1: vp.page_identity(read1), 2: vp.page_identity(read2)})
    assert len(kept) == 2 and notes[0]["same_as_page"] == 1


def test_different_invoices_are_never_merged():
    rows = [_row("1", "1.00", "1.00"), _row("2", "1.00", "2.00")]
    r1 = vp.PageRead(page_no=1, items=[{"label": "doc_no", "text": "IV-0001"}])
    r2 = vp.PageRead(page_no=2, items=[{"label": "doc_no", "text": "IV-0777"}])
    kept, _ = vp.drop_duplicate_copies({1: rows, 2: list(rows)}, {1: "INVOICE", 2: "INVOICE"},
                                       {1: vp.page_identity(r1), 2: vp.page_identity(r2)})
    assert len(kept) == 4


# ----------------------------------------------------------------------------------------------- full pipeline
class FakeVlm:
    """A model that answers page reads and table reads in a 0-1000 grid."""

    def __init__(self):
        self.last_usage, self.last_salvaged = {}, False

    def chat_json(self, model, system, user, *, images=None, **kw):
        if "Classify" in user:
            return {"page_type": "tax_invoice", "is_copy": False}
        if "Digitise" in user:
            return {"rows": [{"line_no": 1, "bbox_2d": [40, 330, 950, 350], "cells": {
                "description": {"text": "BRACKET ASSY", "bbox_2d": [80, 330, 300, 350]},
                "qty": {"text": "10", "bbox_2d": [520, 330, 560, 350]},
                "uom": {"text": "PCS", "bbox_2d": [570, 330, 620, 350]},
                "unit_price": {"text": "100.00", "bbox_2d": [650, 330, 740, 350]},
                "amount": {"text": "1,000.00", "bbox_2d": [800, 330, 900, 350]}}}]}
        if "crop" in user:
            return {"raw": None}
        return {"doc_type": "tax_invoice", "items": [
            {"type": "header", "label": "doc_no", "text": "IV690900285", "bbox_2d": [600, 100, 760, 115], "confidence": 0.95},
            {"type": "header", "label": "doc_date", "text": "04/09/69", "bbox_2d": [600, 120, 700, 135], "confidence": 0.95},
            {"type": "header", "label": "po_number", "text": "PO 50000001", "bbox_2d": [600, 140, 760, 155], "confidence": 0.95},
            {"type": "total", "label": "sub_total", "text": "1,000.00", "bbox_2d": [800, 700, 900, 715], "confidence": 0.95},
            {"type": "total", "label": "vat", "text": "70.00", "bbox_2d": [800, 720, 900, 735], "confidence": 0.95},
            {"type": "total", "label": "grand_total", "text": "1,070.00", "bbox_2d": [800, 740, 900, 755], "confidence": 0.95},
            {"type": "line", "label": "line_1", "text": "1 BRACKET ASSY 10 PCS 100.00 1,000.00", "bbox_2d": [40, 330, 950, 350]}]}


def _pdf():
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    put = lambda x, y, t: page.insert_text((x * 595, y * 842), t, fontsize=9)
    put(0.640, 0.112, "IV690900285"); put(0.655, 0.134, "04/09/69"); put(0.655, 0.156, "PO 50000001")
    put(0.10, 0.355, "1 BRACKET ASSY"); put(0.55, 0.355, "10 PCS"); put(0.68, 0.355, "100.00"); put(0.83, 0.355, "1,000.00")
    put(0.83, 0.712, "1,000.00"); put(0.84, 0.732, "70.00"); put(0.83, 0.752, "1,070.00")
    out = doc.tobytes()
    doc.close()
    return out


@pytest.fixture(scope="module")
def ext():
    pipe = vp.VisionPipeline(FakeVlm(), "fake", do_crops=False)
    return pipe.extract(_pdf(), package_id="PKG-T", dms_doc_id="T-1")


def test_pipeline_keeps_qwens_boxes(ext):
    """Boxes are Qwen's own (0-1000 -> normalised), never moved onto the text layer."""
    b = ext.fields["invoice_num"].region.bbox
    assert b == (0.6, 0.1, 0.16, 0.015)
    assert "bbox_refinement" not in ext.extra


def test_pipeline_cells_carry_the_row_box(ext):
    row = ext.lines[0].region.bbox
    assert row == (0.04, 0.33, 0.91, 0.02) and ext.lines[0].cells["amount"].region.bbox == row


def test_pipeline_page_type_is_published(ext):
    """All pages of DMS-15..25 were published as UNKNOWN: the classification never reached PageInfo."""
    assert ext.pages[0].page_type == "TAX_INVOICE"


def test_pipeline_cells_line_up_and_validate(ext):
    from system_a.domain.normalize import normalize
    from system_a.domain.standard import load_standard
    doc, _ = normalize(ext, load_standard())
    l1 = doc.lines[0]
    assert l1.v("qty") == Decimal("10") and l1.v("amount") == Decimal("1000.00") and l1.ok("uom")
    assert doc.v("invoice_date") == "2026-09-04" and doc.v("grand_total") == Decimal("1070.00")


def test_result_has_the_normalised_item_list(ext):
    """Requirement: normalized data carries the checked invoice item list."""
    from system_a.application.orchestrator import validate
    from system_a.container import Settings, build_services
    res = validate(ext, build_services(Settings(mode="sandbox", ai_mode="sim"), oracle_dataset={}),
                   request={"validation_id": "T", "correlation_id": "T", "idempotency_key": None,
                            "document_revision": 1, "validation_round": 1})
    items = res["normalized_fields"]["items"]
    assert len(items) == 1
    it = items[0]
    assert (it["qty"], it["uom"], it["unit_price"], it["amount"]) == ("10", "PCS", "100.00", "1000.00")
    assert it["line_math"] == {"qty_x_unit_price": "1000.00", "amount": "1000.00", "diff": "0.00", "ok": True}
    assert it["bbox"] and it["page_no"] == 1 and it["cells_ok"]["amount"] is True
    summ = res["normalized_fields"]["items_summary"]
    assert summ["line_count"] == 1 and summ["sum_amount"] == "1000.00" and summ["sum_vs_sub_total_diff"] == "0.00"
    json.dumps(res)                                                     # serialisable
