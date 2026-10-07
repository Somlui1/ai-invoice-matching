"""Synthetic input for the tests, written in System A's own input contract (``aiva.extraction/2.0``).

The tests must not read a real invoice and must not call the VLM, the Oracle or the AI gateway.  So the input
here is synthetic (no real supplier, Tax ID or invoice number) and the **payload the tests assert on is produced
by System A itself**: :func:`payload` feeds the extraction to ``system_a.application.orchestrator.validate()``
with ``build_services()`` in sandbox mode (in-memory Oracle + the sim AI).  That way the screen model is tested
against a genuine ``aiva.system_a.result/3.0``, not against something the test invented.

``tests/system_a_stub/config`` is the Standard the harness loads, so the buyer identity comes from that Standard
(entity ORG_ID 103) and the documents are always addressed to a buyer it knows.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional

W, H = 595.0, 842.0                      # the page size the fake geometry is measured in (pt)
Q2 = Decimal("0.01")


def tax_id_of(base12: str) -> str:
    """A 13-digit Tax ID with a real check digit, so Oracle's key whitelist accepts it."""
    n = [int(c) for c in re.sub(r"\D", "", base12)]
    return "".join(map(str, n)) + str((11 - sum(n[i] * (13 - i) for i in range(12)) % 11) % 10)


SUP_TAX = tax_id_of("123456789012")
BRACKET = ("BRACKET ASSY", 10, "PCS", "100.00", "1000.00")
GASKET = ("GASKET PLATE", 5, "PCS", "50.00", "250.00")


def money(v) -> str:
    return f"{Decimal(str(v)):,.2f}"


def _r(page: int, x: float, y: float, w: float, h: float) -> dict:
    return {"page": page, "bbox": [round(x, 4), round(y, 4), round(w, 4), round(h, 4)]}


def _f(text, *, conf=0.97, page=1, box=(0.05, 0.05, 0.3, 0.02), **kw) -> dict:
    out = {"raw": text, "confidence": conf, "agreement": True, "region": _r(page, *box), "source": "consensus"}
    if kw.get("null_reason") is not None:
        out["null_reason"] = kw["null_reason"]
        out["raw"] = None
        out["confidence"] = None
    return out


def totals(lines) -> tuple[str, str, str]:
    sub = sum(Decimal(str(l[4])) for l in lines)
    vat = (sub * Decimal("0.07")).quantize(Q2)
    return money(sub), money(vat), money(sub + vat)


def extraction(*, buyer: dict, inv: str = "SYN-INV-0001", po: str = "50000001", date: str = "05/10/2026",
               lines=(), signatures: bool = True, pages: int = 1, sup_tax: str = SUP_TAX,
               drop_field: Optional[str] = None, ocr_text: str = "") -> dict:
    """One synthetic tax invoice as ``aiva.extraction/2.0`` - fields, rows, signatures, words and regions,
    each with its own normalized ``[x, y, w, h]`` box (the same boxes must come back in the result)."""
    lines = list(lines or [BRACKET, GASKET])
    sub, vat, grand = totals(lines)
    # The values here are already label-stripped, exactly as VisionPipeline hands them over: a raw of
    # "INVOICE NO. SYN-INV-0001" would normalise to "INVOICENO.SYN-INV-0001" and would not match the receipt.
    fields = {
        "invoice_num": _f(inv, conf=0.99, box=(0.55, 0.075, 0.38, 0.015)),
        "invoice_date": _f(date, conf=0.96, box=(0.55, 0.095, 0.30, 0.015)),
        "po_number": _f(po, conf=0.99, box=(0.55, 0.115, 0.30, 0.015)),
        "supplier_name": _f("SYNTHETIC SUPPLIER CO., LTD.", box=(0.05, 0.03, 0.40, 0.025)),
        "supplier_tax_id": _f(sup_tax, box=(0.05, 0.06, 0.30, 0.015)),
        "customer_name": _f(buyer["name_th"], box=(0.05, 0.15, 0.45, 0.02)),
        "customer_tax_id": _f(buyer["tax_id"], conf=0.98, box=(0.05, 0.21, 0.30, 0.015)),
        "customer_address": _f(buyer["addr_th"], conf=0.92, box=(0.05, 0.175, 0.45, 0.03)),
        "currency": _f("THB", conf=0.99, box=(0.55, 0.60, 0.05, 0.015)),
        "sub_total": _f(sub, conf=0.98, box=(0.55, 0.60, 0.40, 0.02)),
        "vat": _f(vat, conf=0.98, box=(0.55, 0.625, 0.40, 0.02)),
        "grand_total": _f(grand, conf=0.99, box=(0.55, 0.65, 0.40, 0.02)),
    }
    if drop_field:
        keep_box = (fields.get(drop_field) or {}).get("region", {}).get("bbox") or [0.05, 0.05, 0.3, 0.02]
        fields[drop_field] = {"raw": None, "confidence": None, "agreement": True, "source": "consensus",
                              "region": {"page": 1, "bbox": keep_box}, "null_reason": "NOT_PRESENT"}

    rows = []
    for k, (desc, qty, uom, price, amount) in enumerate(lines, start=1):
        y = 0.295 + 0.025 * (k - 1)
        rows.append({"line_no": k, "region": _r(1, 0.05, y, 0.90, 0.02), "cells": {
            "description": _f(desc, page=1, box=(0.10, y, 0.45, 0.02)),
            "qty": _f(str(qty), page=1, box=(0.58, y, 0.06, 0.02)),
            "uom": _f(uom, conf=0.93, page=1, box=(0.65, y, 0.05, 0.02)),
            "unit_price": _f(money(price), page=1, box=(0.72, y, 0.10, 0.02)),
            "amount": _f(money(amount), conf=0.99, page=1, box=(0.84, y, 0.11, 0.02))}})

    sigs = {}
    if signatures:
        sigs = {"receiver": {"present": True, "confidence": 0.9, "kind": "handwritten", "region": _r(1, 0.08, 0.78, 0.22, 0.06)},
                "deliverer": {"present": True, "confidence": 0.88, "kind": "handwritten", "region": _r(1, 0.40, 0.78, 0.22, 0.06)}}

    words = [{"word_id": f"W{i}", "page": 1, "text": t, "bbox": [0.05 + 0.02 * i, 0.92, 0.018, 0.01],
              "confidence": 0.98} for i, t in enumerate((ocr_text or "E. & O.E. SYNTHETIC ONLY").split()[:6])]
    regions = [
        {"region_id": "SEC-header", "page": 1, "kind": "section", "label": "header", "bbox": [0.04, 0.02, 0.92, 0.22]},
        {"region_id": "TAB-items", "page": 1, "kind": "table", "label": "items", "text": "NO. DESCRIPTION QTY UOM PRICE AMOUNT",
         "bbox": [0.04, 0.26, 0.92, 0.02 + 0.025 * len(lines)], "parent_id": "SEC-header"},
        {"region_id": "STP-stamp", "page": 1, "kind": "stamp", "label": "company_stamp", "text": "RECEIVED STAMP",
         "bbox": [0.35, 0.68, 0.18, 0.06]},
    ]
    page_info = [{"page_no": n, "width_pt": W, "height_pt": H, "rotation": 0, "render_dpi": 150,
                  "page_type": "TAX_INVOICE", "type_confidence": 0.98, "ocr_quality": 0.95} for n in range(1, pages + 1)]
    return {
        "contract": "aiva.extraction/2.0",
        "package_id": f"PKG-SYN-{inv}", "dms_doc_id": f"DMS-SYN-{inv}",
        "file_sha256": "sha256:" + ("ab" * 32),
        "pages": page_info,
        "documents": [{"document_id": "D1", "document_type": "tax_invoice", "pages": tuple(range(1, pages + 1)),
                       "confidence": 0.99}],
        "invoice_document_id": "D1", "pages_complete": True,
        "fields": fields, "lines": rows, "signatures": sigs, "words": words, "regions": regions,
        "extra": {"ocr_text_by_page": {str(n): (ocr_text or f"{inv} {po} {grand}") for n in range(1, pages + 1)},
                  "dropped_items": [{"page": 1, "type": "other", "label": "note", "text": "E. & O.E.",
                                     "drop_reason": "NOT_A_FIELD"}],
                  "coord_mode_by_page": {str(n): "norm1" for n in range(1, pages + 1)},
                  "page_errors": {}, "row_errors": {}, "lines_source": "vlm_table"},
        "extractor": {"vlm": "synthetic-test-vlm", "pipeline": "synth/1.0"},
    }


def oracle_dataset(*, inv: str = "SYN-INV-0001", po: str = "50000001", lines=(), sup_tax: str = SUP_TAX,
                   receipt: str = "RCV-0000010001", with_receipt: bool = True) -> dict:
    """What the in-memory Oracle answers: the receipt rows this synthetic invoice should match."""
    lines = list(lines or [BRACKET, GASKET])
    if not with_receipt:
        return {"receipts": [], "po_supplier": {}}
    return {"receipts": [{"po_number": po, "invoice_num": inv, "supplier_tax_id": sup_tax, "rows": [
        {"ORG_ID": 103, "RECEIPT_NUM": receipt, "RECEIVER": "SMITH J.", "LINE": i, "ITEM": r[0], "QTY": str(r[1]),
         "UOM": r[2], "UNIT_PRICE": str(r[3]), "LINE_AMOUNT": str(r[4]), "PO_NUM": po}
        for i, r in enumerate(lines, start=1)]}], "po_supplier": {po: sup_tax}}


def payload(*, buyer: dict, ext: dict, dataset: dict, validation_id: str = "VAL-SYN-0001") -> dict:
    """Run the extraction through System A's own validation (sandbox: in-memory Oracle + sim AI) -> result 3.0."""
    import time

    from system_a import container
    from system_a.application.orchestrator import validate
    from system_a.domain.contracts import ExtractionResult

    st = container.Settings(mode="sandbox", ai_mode="sim")
    svc = container.build_services(st, oracle_dataset=dataset)
    request = {"validation_id": validation_id, "correlation_id": "webapp-test", "idempotency_key": None,
               "document_revision": 1, "validation_round": 1, "source": "webapp-tests", "run_id": "test",
               "dms_doc_id": ext["dms_doc_id"], "content_kind": "pdf", "declared_mime": "application/pdf",
               "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
    return validate(ExtractionResult(**ext), svc, request=request)
