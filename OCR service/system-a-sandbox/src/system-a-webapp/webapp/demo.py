"""A small, fully synthetic batch in the same shape as the real ``report.html`` batch folder.

    python -m webapp demo --out sample_batch      # writes report.html + docs/doc_<id>/page_<n>.jpg + oracle_dataset.json

Used by the tests and as a demo: it lets you see the whole workflow before pointing the application at a real
batch.  No real supplier, Tax ID or invoice number appears here.  The buyer identity is read from the System A
Standard in use (entity ORG_ID 103), so the documents are always addressed to a buyer that Standard knows.
"""
from __future__ import annotations

import json
import re
import sys
from decimal import Decimal
from pathlib import Path

W, H = 1240, 1754
COLORS = {"header": "#d62728", "supplier": "#ff7f0e", "customer": "#9467bd", "table": "#7f7f7f", "line": "#1f77b4",
          "total": "#2ca02c", "payment": "#bcbd22", "signature": "#e377c2", "stamp": "#8c564b", "other": "#17becf"}
Q2 = Decimal("0.01")


def tax_id_of(base12: str) -> str:
    n = [int(c) for c in re.sub(r"\D", "", base12)]
    return "".join(map(str, n)) + str((11 - sum(n[i] * (13 - i) for i in range(12)) % 11) % 10)


SUP_TAX = tax_id_of("123456789012")
SUP_TAX_2 = tax_id_of("987654321000")


def item(type_, label, text, x, y, w, h):
    return {"type": type_, "label": label, "text": text, "bbox_norm": [round(x, 4), round(y, 4), round(w, 4), round(h, 4)],
            "bbox_px": [round(x * W), round(y * H), round((x + w) * W), round((y + h) * H)]}


def money(v) -> str:
    return f"{Decimal(v):,.2f}"


def invoice_items(inv, po, buyer, lines, *, sup_tax=SUP_TAX, signatures=True, copy=False, sub=None, vat=None, grand=None,
                  inv_style="INVOICE NO. {}"):
    """OCR items of one invoice page.  ``lines``: [(desc, qty, uom, price, amount)]."""
    amt_total = sum(Decimal(str(l[4])) for l in lines)
    sub = Decimal(str(sub)) if sub is not None else amt_total
    vat = Decimal(str(vat)) if vat is not None else (sub * Decimal("0.07")).quantize(Q2)
    grand = Decimal(str(grand)) if grand is not None else sub + vat
    its = [item("supplier", "supplier_name", "SYNTHETIC SUPPLIER CO., LTD.", 0.05, 0.03, 0.40, 0.025),
           item("supplier", "supplier_tax_id", f"เลขประจำตัวผู้เสียภาษี {sup_tax}", 0.05, 0.06, 0.30, 0.015),
           item("header", "doc_title", "ใบกำกับภาษี TAX INVOICE" + (" (COPY)" if copy else " (ORIGINAL)"), 0.55, 0.03, 0.40, 0.03),
           item("header", "doc_no", f"เลขที่ {inv_style.format(inv)}", 0.55, 0.075, 0.38, 0.015),
           item("header", "doc_date", "วันที่ DATE 05/10/2026", 0.55, 0.095, 0.30, 0.015),
           item("header", "po_number", f"อ้างอิง PO NO. {po}", 0.55, 0.115, 0.30, 0.015),
           item("customer", "customer_name", buyer["name_th"], 0.05, 0.15, 0.45, 0.02)]
    words = buyer["addr_th"].split(" ")
    half = max(1, len(words) // 2)
    its += [item("customer", "customer_address", " ".join(words[:half]), 0.05, 0.175, 0.45, 0.015),
            item("customer", "customer_address", " ".join(words[half:]), 0.05, 0.19, 0.45, 0.015),
            item("customer", "customer_tax_id", f"Tax ID {buyer['tax_id']}", 0.05, 0.21, 0.30, 0.015),
            item("table", "table_header", "NO. DESCRIPTION QTY UNIT UNIT PRICE AMOUNT", 0.05, 0.27, 0.90, 0.02)]
    for k, (desc, qty, uom, price, amount) in enumerate(lines, start=1):
        its.append(item("line", f"line_{k}", f"{k} {desc} {qty} {uom} {money(price)} {money(amount)}",
                        0.05, 0.295 + 0.025 * (k - 1), 0.90, 0.02))
    its += [item("total", "sub_total", f"รวมเงิน Sub Total {money(sub)}", 0.55, 0.60, 0.40, 0.02),
            item("total", "vat", f"ภาษีมูลค่าเพิ่ม VAT 7% {money(vat)}", 0.55, 0.625, 0.40, 0.02),
            item("total", "grand_total", f"รวมสุทธิ Net Total {money(grand)}", 0.55, 0.65, 0.40, 0.02),
            item("stamp", "company_stamp", "RECEIVED STAMP", 0.35, 0.68, 0.18, 0.06)]
    if signatures:
        its += [item("signature", "receiver_signature", "signed", 0.08, 0.78, 0.22, 0.06),
                item("signature", "deliverer_signature", "signed", 0.40, 0.78, 0.22, 0.06)]
    its.append(item("other", "note", "E. & O.E.", 0.05, 0.90, 0.2, 0.012))
    return its


def po_items(po, buyer, lines):
    its = [item("header", "doc_title", "ใบสั่งซื้อ PURCHASE ORDER", 0.55, 0.03, 0.40, 0.03),
           item("header", "po_number", f"PO. {po}", 0.55, 0.08, 0.30, 0.015),
           item("supplier", "supplier_name", buyer["name_th"], 0.05, 0.03, 0.45, 0.02)]
    for k, (desc, qty, uom, price, amount) in enumerate(lines, start=1):
        its.append(item("line", f"line_{k}", f"{k} {desc} {qty} {uom} {money(price)} {money(amount)}", 0.05, 0.2 + 0.025 * k, 0.9, 0.02))
    return its


def page(n, doc_id, doc_type, kept, *, image=True):
    return {"page": n, "image": f"docs/doc_{doc_id}/page_{n}.jpg" if image else f"docs/doc_{doc_id}/page_{n}.jpg",
            "doc_type": doc_type, "coord": "norm1000", "seconds": 1.5, "error": None, "kept": kept, "dropped": []}


BRACKET = ("BRACKET ASSY", 10, "PCS", "100.00", "1000.00")
GASKET = ("GASKET PLATE", 5, "PCS", "50.00", "250.00")


def build_docs(buyer: dict) -> tuple[list, dict]:
    """``(documents, oracle_dataset)`` of the synthetic batch."""
    two = [BRACKET, GASKET]
    docs, receipts = [], []

    def rcv(po, inv, rcv_no, rows, tax=SUP_TAX):
        receipts.append({"po_number": po, "invoice_num": inv, "supplier_tax_id": tax, "rows": [
            {"ORG_ID": 103, "RECEIPT_NUM": rcv_no, "RECEIVER": "SMITH J.", "LINE": i, "ITEM": r[0], "QTY": str(r[1]),
             "UOM": r[2], "UNIT_PRICE": str(r[3]), "LINE_AMOUNT": str(r[4]), "PO_NUM": po}
            for i, r in enumerate(rows, start=1)]})

    # 101: clean single page -> AUTO_PASS
    docs.append({"id": 101, "title": "SYN_CLEAN_SINGLE", "pages": [page(1, 101, "tax_invoice",
                 invoice_items("SYN-INV-0001", "50000001", buyer, two))]})
    rcv("50000001", "SYN-INV-0001", "RCV-0000010001", two)
    # 102: original + printed copy + purchase order -> AUTO_PASS (the copy must be dropped)
    docs.append({"id": 102, "title": "SYN_ORIGINAL_COPY_PO", "pages": [
        page(1, 102, "tax_invoice", invoice_items("SYN-INV-0002", "50000002", buyer, two)),
        page(2, 102, "tax_invoice", invoice_items("SYN-INV-0002", "50000002", buyer, two, copy=True)),
        page(3, 102, "purchase_order", po_items("50000002", buyer, two))]})
    rcv("50000002", "SYN-INV-0002", "RCV-0000010002", two)
    # 103: arithmetic error in line 1 (10 x 100.00 printed as 1,200.00) -> HOLD E02, Oracle never asked
    bad = [("BRACKET ASSY", 10, "PCS", "100.00", "1200.00"), GASKET]
    docs.append({"id": 103, "title": "SYN_LINE_MATH_ERROR", "pages": [page(1, 103, "tax_invoice",
                 invoice_items("SYN-INV-0003", "50000003", buyer, bad))]})
    # 104: no receiver / deliverer signature -> HOLD E08
    docs.append({"id": 104, "title": "SYN_NO_SIGNATURE", "pages": [page(1, 104, "tax_invoice",
                 invoice_items("SYN-INV-0004", "50000004", buyer, two, signatures=False))]})
    rcv("50000004", "SYN-INV-0004", "RCV-0000010004", two)
    # 105: no receipt in Oracle, and its page JPG is not on disk -> HOLD E05 (stand-in page image)
    docs.append({"id": 105, "title": "SYN_NO_RECEIPT_NO_IMAGE", "pages": [page(1, 105, "tax_invoice",
                 invoice_items("SYN-INV-0005", "50000005", buyer, two, inv_style="เลขที่ NUMBER {}"))]})
    # 106: a delivery note only - nothing that can be validated as an invoice
    docs.append({"id": 106, "title": "SYN_DELIVERY_NOTE_ONLY", "pages": [page(1, 106, "delivery_note", [
        item("header", "doc_title", "ใบส่งของ DELIVERY NOTE", 0.55, 0.03, 0.4, 0.03),
        item("header", "doc_no", "DN-0006", 0.55, 0.08, 0.2, 0.015),
        item("line", "line_1", "1 BRACKET ASSY 10 PCS", 0.05, 0.3, 0.9, 0.02)])]})
    # 107: two lines whose printed row has weight + unit price + amount (3 money columns)
    three = [("MACHINED PLATE FL G05", 2, "PCS", "6950.00", "13900.00")]
    it107 = invoice_items("SYN-INV-0007", "50000007", buyer, three)
    for it in it107:
        if it["label"] == "line_1":
            it["text"] = "1 MACHINED PLATE FL G05 95 x 220 x 250 2 PCS 83.08 6,950.00 13,900.00"
    docs.append({"id": 107, "title": "SYN_THREE_MONEY_COLUMNS", "pages": [page(1, 107, "tax_invoice", it107)]})
    rcv("50000007", "SYN-INV-0007", "RCV-0000010007", [("MACHINED PLATE FL G05", 2, "PCS", "6950.00", "13900.00")])
    for d in docs:
        d.update(ptype=None, types=sorted({p["doc_type"] for p in d["pages"]}), status="ok", error=None, seconds=3.0,
                 pages_total=len(d["pages"]), kept=sum(len(p["kept"]) for p in d["pages"]), dropped=0,
                 search=" ".join([str(d["id"]), d["title"]] + [i["text"] for p in d["pages"] for i in p["kept"]]).lower())
    po_supplier = {r["po_number"]: SUP_TAX for r in receipts}
    return docs, {"receipts": receipts, "po_supplier": po_supplier}


def draw_page(path: Path, kept: list) -> None:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(im)
    for it in kept:
        b = it["bbox_px"]
        dr.text((b[0] + 2, b[1] + 2), str(it["text"]).encode("ascii", "replace").decode()[:80], fill=(40, 40, 40))
        if it["type"] in ("signature", "stamp"):
            dr.ellipse(b, outline=(70, 70, 160), width=3)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "JPEG", quality=70)


def write_batch(out: Path, buyer: dict) -> tuple[list, dict]:
    out = Path(out)
    docs, dataset = build_docs(buyer)
    for d in docs:
        if d["id"] == 105:
            continue                                           # this one has no page images on purpose
        for p in d["pages"]:
            draw_page(out / p["image"], p["kept"])
    (out / "docs" / "doc_101").mkdir(parents=True, exist_ok=True)
    (out / "docs" / "doc_101" / "viewer.html").write_text("<!doctype html><title>viewer 101</title>viewer", encoding="utf-8")
    html = ("<!doctype html><meta charset=utf-8><title>AIVA bbox batch report</title>\n<script>const DATA="
            + json.dumps(docs, ensure_ascii=False) + ", COLORS=" + json.dumps(COLORS) + ";\n$('x');\n</script>\n")
    (out / "report.html").write_text(html, encoding="utf-8")
    (out / "oracle_dataset.json").write_text(json.dumps(dataset, ensure_ascii=False, indent=1), encoding="utf-8")
    return docs, dataset


def demo(out: Path) -> dict:
    """Write the sample batch for the System A that ``SYSTEM_A_HOME`` points at; returns the settings to use."""
    from system_a.domain.standard import load_standard
    e = load_standard().entities[103]
    write_batch(out, {"tax_id": e["tax_id"], "name_th": e["name_th"], "addr_th": e["addr_th"]})
    return {"BATCH_REPORT": str(Path(out) / "report.html"), "WEBAPP_ORACLE_DATASET": str(Path(out) / "oracle_dataset.json")}
