import pytest

from webapp.batch import BatchDoc, BatchPage, BatchSource
from webapp.extraction import build_replay_extraction, candidate, parse_row


def extract(batch_dir, doc_id, **kw):
    b = BatchSource(batch_dir)
    d = b.get(doc_id)
    return build_replay_extraction(d, {p.page: (1240, 1754) for p in d.pages}, **kw)


def test_engine_helpers_the_adapter_relies_on_exist(harness):
    from system_a.perception import vision_pipeline as vp
    for n in ("LABEL_TO_FIELD", "extract_value", "page_type_of", "group_documents", "drop_duplicate_copies",
              "page_identity", "PageRead", "SIGNATURE_LABELS", "REQUIRED_FIELD_NAMES", "TAX_ID_RE", "DATE_RE",
              "IDENTIFIER_SHAPE", "TOKEN_RE", "_CURRENCY"):
        assert hasattr(vp, n), f"System A no longer exports {n}: update webapp/extraction.py"


def test_fields_of_a_clean_invoice(batch_dir, buyer):
    e = extract(batch_dir, 101)
    f = e["fields"]
    assert e["contract"] == "aiva.extraction/2.0" and e["invoice_document_id"] == "D1"
    assert f["invoice_num"]["raw"] == "SYN-INV-0001"                  # label words stripped: "เลขที่ INVOICE NO. SYN-INV-0001"
    assert f["po_number"]["raw"] == "50000001" and f["invoice_date"]["raw"] == "05/10/2026"
    assert f["sub_total"]["raw"] == "1,250.00" and f["vat"]["raw"] == "87.50" and f["grand_total"]["raw"] == "1,337.50"
    assert f["customer_tax_id"]["raw"] == buyer["tax_id"] and f["customer_name"]["raw"] == buyer["name_th"]
    assert f["customer_address"]["raw"] == buyer["addr_th"]            # the two address boxes are joined
    assert "currency" not in f                                          # only derived when THB / baht is actually printed
    assert all(v["region"] for v in f.values() if v["raw"])
    assert set(e["signatures"]) == {"receiver", "deliverer"} and e["signatures"]["receiver"]["present"] is True


def test_lines_are_derived_from_the_printed_rows(batch_dir):
    lines = extract(batch_dir, 101)["lines"]
    assert [l["line_no"] for l in lines] == [1, 2]
    c = lines[0]["cells"]
    assert (c["qty"]["raw"], c["uom"]["raw"], c["unit_price"]["raw"], c["amount"]["raw"]) == ("10", "PCS", "100.00", "1,000.00")
    assert c["description"]["raw"].endswith("BRACKET ASSY") and c["qty"]["source"] == "derived"


def test_a_printed_copy_page_is_dropped_and_documents_are_grouped(batch_dir):
    e = extract(batch_dir, 102)
    assert len(e["lines"]) == 2 and len(e["extra"]["replay"]["copy_pages_dropped"]) == 1
    assert [(d["document_id"], d["pages"]) for d in e["documents"]] == [("D1", [1, 2]), ("D2", [3])]
    assert [p["page_type"] for p in e["pages"]] == ["TAX_INVOICE", "TAX_INVOICE", "PO"]


def test_weight_unit_price_amount_columns(batch_dir):
    c = extract(batch_dir, 107)["lines"][0]["cells"]
    assert c["unit_price"]["raw"] == "6,950.00" and c["amount"]["raw"] == "13,900.00"      # 2 x 6,950.00 = 13,900.00


def test_non_item_rows_are_skipped_not_guessed(batch_dir):
    e = extract(batch_dir, 106)
    assert e["lines"] == [] and e["extra"]["replay"]["skipped_rows"][0]["label"] == "line_1"
    assert e["extra"]["replay"]["invoice_page_fallback"] is True and e["fields"]["invoice_num"]["raw"] == "DN-0006"


def test_items_are_kept_for_the_screen(batch_dir):
    e = extract(batch_dir, 101)
    items = e["extra"]["items_by_page"]["1"]
    assert len(items) > 15 and items[0]["bbox"] and len(items[0]["bbox"]) == 4 and items[0]["bbox_px"]


def test_strict_mode_does_not_pretend_two_readers(batch_dir):
    f = extract(batch_dir, 101, assume_agreement=False)["fields"]
    assert f["invoice_num"]["agreement"] is False and f["invoice_num"]["confidence"] <= 0.70
    assert extract(batch_dir, 101)["fields"]["invoice_num"]["agreement"] is True


@pytest.mark.parametrize("text,price,amount,qty,uom", [
    ("1 PLATE A 95 x 220 2 PCS 83.08 6,950.00 13,900.00", "6,950.00", "13,900.00", "2", "PCS"),
    ("CODE-1 PART X 260620143741 50 PCS 4.42 0.00 221.00", "4.42", "221.00", "50", "PCS"),
    ("1 7500000001 STRIKER 200.00 PCS. 0.94 188.00", "0.94", "188.00", "200.00", "PCS."),
    ("3 CARBIDE ENDMILL 202-1200 HPES PCS. 3 3,794.00 11,382.00", "3,794.00", "11,382.00", "3", "PCS."),
    ("1 0800105003216 เหล็กท่อกลม 2\" x 3.2 มม. 3.00 เส้น 755.00 2,265.00", "755.00", "2,265.00", "3.00", "เส้น"),
    ("0010 6768459 XNMU WKP35S จำนวน 30 PC 596.40 THB 17,892.00", "596.40", "17,892.00", "30", "PC"),
])
def test_parse_row(text, price, amount, qty, uom):
    r = parse_row(text)
    assert (r["unit_price"], r["amount"], r["qty"], r["uom"]) == (price, amount, qty, uom)


@pytest.mark.parametrize("text", ["MACHINED PLATE", "( Project:X (P703 BUNDLE 1.6), Task:07.2 - DFG0011022A )", "", "TOTAL 1,000.00"])
def test_parse_row_rejects_what_is_not_an_item_row(text):
    assert parse_row(text) is None


@pytest.mark.parametrize("name,text,value,ok", [
    ("customer_tax_id", "เลขประจำตัวผู้เสียภาษี TAX ID : 0-1455-48001-55-7", "0145548001557", True),
    ("customer_tax_id", "Tax ID 01 45548001557", "0145548001557", True),
    ("customer_tax_id", "Tax ID 12345", "Tax ID 12345", False),
    ("invoice_num", "เลขที่ : INVOICE NO. : IV2609043", "IV2609043", True),
    ("invoice_num", "เลขที่เอกสาร/วันที่ 9290186640/ 2026/09/02", "9290186640", True),
    ("invoice_num", "Document Number", "Document Number", False),
    ("invoice_num", "เลขประจำตัวผู้เสียภาษีอากร 0115538001783", "เลขประจำตัวผู้เสียภาษีอากร 0115538001783", False),
    ("invoice_num", "SQ26/071249", "SQ26/071249", True),
    ("po_number", "PO.NO.42052405", "42052405", True),
    ("po_number", "พนักงานขาย Sales man No MK-09", "พนักงานขาย Sales man No MK-09", False),
    ("vat", "ภาษีมูลค่าเพิ่ม VAT 7.00 % 17,892.00 1,252.44", "1,252.44", True),
    ("grand_total", "32,541.", "32,541", False),
    ("customer_name", "CS100208", "CS100208", False),
    ("customer_name", "บริษัท ตัวอย่าง จำกัด", "บริษัท ตัวอย่าง จำกัด", True),
])
def test_candidate(harness, name, text, value, ok):
    assert candidate(name, text) == (value, ok)


def test_the_net_total_beats_a_total_that_is_the_subtotal(harness):
    def it(label, text, y):
        return {"type": "total", "label": label, "text": text, "bbox_norm": [0.5, y, 0.4, 0.02], "bbox_px": [1, 1, 2, 2]}
    page = BatchPage(page=1, doc_type="tax_invoice", kept=[it("grand_total", "TOTAL / BAHT 49,215.00", .60),
                                                           it("vat", "VAT 7% 3,445.05", .62),
                                                           it("grand_total", "GRAND TOTAL 52,660.05", .64)])
    d = BatchDoc(id=1, title="t", pages=[page], pages_total=1)
    assert build_replay_extraction(d, {1: (1240, 1754)})["fields"]["grand_total"]["raw"] == "52,660.05"
