"""Result -> what the screen needs.

Takes the extraction that went into System A and the ``aiva.system_a.result/3.0`` that came out, and returns one
JSON document per processed file: the OCR items with their boxes (per page), the Final Result (normalised fields,
lines, signatures) and the Verify Result (nine rules with their evidence).  Every row that can be located on the
page carries a ``ref = {page, i}`` pointing at the OCR item whose box it came from - that is how a click on a row
pins its box on the document.
"""
from __future__ import annotations

from typing import Optional

RULE_NAMES = {"V-01": "Required fields", "V-02": "Line math", "V-03": "Document totals", "V-04": "Receipt lookup",
              "V-05": "Customer entity", "V-06": "Signatures", "V-07": "Line matching", "V-08": "Quantity",
              "V-09": "Total vs receipt"}
CLASS_OF = {"AUTO_PASS": "ok", "REVIEW": "partial", "MANUAL_REVIEW": "partial", "HOLD": "error",
            "SYSTEM_ERROR": "error"}
FIELD_ORDER = ("invoice_num", "invoice_date", "po_number", "supplier_name", "supplier_tax_id", "customer_name",
               "customer_tax_id", "customer_address", "sub_total", "vat", "grand_total", "currency", "release_num")
SEARCH_CAP = 40000


def _iou(a, b) -> float:
    ax2, ay2, bx2, by2 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw, ih = min(ax2, bx2) - max(a[0], b[0]), min(ay2, by2) - max(a[1], b[1])
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


class Locator:
    """bbox on a page -> index of the OCR item that has that box (exact match first, then best overlap)."""

    def __init__(self, pages: list):
        self.boxes = {p["page"]: [(i, it["bbox_norm"]) for i, it in enumerate(p["kept"]) if it.get("bbox_norm")]
                      for p in pages}

    def ref(self, page, bbox) -> Optional[dict]:
        if page is None or not bbox:
            return None
        bb = [float(x) for x in bbox]
        cands = self.boxes.get(int(page), [])
        for i, b in cands:
            if all(abs(x - y) < 1e-3 for x, y in zip(b, bb)):
                return {"page": int(page), "i": i}
        best = max(((_iou(b, bb), i) for i, b in cands), default=(0.0, None))
        return {"page": int(page), "i": best[1]} if best[0] >= 0.5 else None


def _page_views(extraction: dict) -> list:
    extra = extraction.get("extra") or {}
    items_by = extra.get("items_by_page") or {}
    drops = extra.get("dropped_items") or []
    doc_types = extra.get("doc_type_by_page") or {}
    coords = extra.get("coord_mode_by_page") or {}
    secs = extra.get("seconds_by_page") or {}
    errs = extra.get("page_errors") or {}
    out = []
    for pi in extraction.get("pages") or []:
        n = pi["page_no"]
        W = pi["width_pt"] * pi.get("render_dpi", 150) / 72
        H = pi["height_pt"] * pi.get("render_dpi", 150) / 72
        kept = []
        for it in items_by.get(str(n)) or []:
            b = it.get("bbox")
            px = it.get("bbox_px") or ([round(b[0] * W), round(b[1] * H), round((b[0] + b[2]) * W),
                                         round((b[1] + b[3]) * H)] if b else None)
            kept.append({"type": it.get("type") or "other", "label": it.get("label") or "", "text": it.get("text") or "",
                         "bbox_norm": [round(float(x), 4) for x in b] if b else None, "bbox_px": px,
                         "confidence": it.get("confidence")})
        out.append({"page": n, "doc_type": doc_types.get(str(n)) or pi.get("page_type", "unknown"),
                    "page_type": pi.get("page_type"), "coord": coords.get(str(n)) or "norm1", "seconds": secs.get(str(n)),
                    "error": errs.get(str(n)), "size_px": [round(W), round(H)], "kept": kept,
                    "dropped": [{"type": d.get("type") or "other", "label": d.get("label") or "", "text": d.get("text") or "",
                                 "drop_reason": d.get("drop_reason") or ""} for d in drops if d.get("page") == n]})
    return out


def build_view(*, doc_id: int, title: str, run: int, extraction: dict, result: dict, seconds: float,
               perception: str, engine: str) -> dict:
    pages = _page_views(extraction)
    loc = Locator(pages)
    elements = {e["element_id"]: e for e in (result.get("ocr") or {}).get("elements", [])}

    def ref_of(element_id) -> Optional[dict]:
        e = elements.get(element_id)
        return loc.ref(e.get("page_no"), e.get("bbox")) if e else None

    ex = result.get("extraction") or {}
    fields = ex.get("fields") or {}
    order = [k for k in FIELD_ORDER if k in fields] + sorted(k for k in fields if k not in FIELD_ORDER)
    final_fields = [{"name": k, "raw": fields[k].get("raw_value"), "value": fields[k].get("normalized_value"),
                     "ok": bool(fields[k].get("ok")), "confidence": fields[k].get("confidence"),
                     "null_reason": fields[k].get("null_reason"), "ref": ref_of(fields[k].get("element_id"))}
                    for k in order]
    final_lines = [{"line_no": l["line_no"], "ref": ref_of(l.get("element_id")), "uom_group": l.get("uom_group"),
                    "cells": {k: {"raw": c.get("raw_value"), "value": c.get("normalized_value"), "ok": bool(c.get("ok")),
                                  "null_reason": c.get("null_reason")} for k, c in (l.get("cells") or {}).items()}}
                   for l in ex.get("lines") or []]
    sigs = {}
    for k, s in (ex.get("signatures") or {}).items():
        r = s.get("region") or {}
        sigs[k] = {"present": s.get("present"), "confidence": s.get("confidence"), "kind": s.get("kind"),
                   "ref": loc.ref(r.get("page"), r.get("bbox"))}

    evidence = {e["evidence_id"]: e for e in result.get("evidence") or []}
    verify = []
    for r in result.get("rule_results") or []:
        evs = []
        for eid in r.get("evidence_ids") or []:
            e = evidence.get(eid)
            if not e:
                continue
            refs = [x for x in (loc.ref(b.get("page_no"), b.get("bbox")) for b in e.get("bboxes") or []) if x]
            evs.append({"id": eid, "code": e.get("exception_code"), "severity": e.get("severity"),
                        "message": e.get("message_th"), "actual": e.get("actual_value"),
                        "expected": e.get("expected_value"), "refs": refs})
        first = next((x for e in evs for x in e["refs"]), None)
        verify.append({"rule_id": r["rule_id"], "name": RULE_NAMES.get(r["rule_id"], r["rule_id"]), "result": r["result"],
                       "code": next((e["code"] for e in evs if e["code"]), None),
                       "severity": next((e["severity"] for e in evs if e["severity"]), None),
                       "detail": r.get("detail") or "", "halted_by": r.get("halted_by"), "evidence": evs, "ref": first})

    rec = result.get("recommendation") or {}
    snap = result.get("oracle_snapshot") or {}
    qk = snap.get("query_keys") or {}
    oracle = None if not snap else {
        "lookup_path": snap.get("lookup_path"), "receipt_nums": snap.get("receipt_nums") or [],
        "org_id": snap.get("org_id"), "po_numbers": snap.get("po_numbers") or [],
        "matched_on_column": snap.get("matched_on_column"), "row_cap_hit": snap.get("row_cap_hit"),
        "supplier_tax_id_source": qk.get("supplier_tax_id_source"), "receipt_lines": len(snap.get("receipt_lines") or [])}
    types: list = []
    for p in pages:
        if p["doc_type"] not in types:
            types.append(p["doc_type"])
    search = " ".join([str(doc_id), title] + [i["text"] for p in pages for i in p["kept"]]).lower()[:SEARCH_CAP]
    replay = (extraction.get("extra") or {}).get("replay")
    return {
        "id": doc_id, "title": title, "run": run, "seconds": round(seconds, 1), "perception": perception, "engine": engine,
        "recommendation": rec.get("value"), "cls": CLASS_OF.get(rec.get("value"), "error"),
        "exception_codes": rec.get("exception_codes") or [], "max_severity": rec.get("max_severity"),
        "halted_by": rec.get("halted_by"), "types": types, "search": search, "pages": pages,
        "kept": sum(len(p["kept"]) for p in pages), "dropped": sum(len(p["dropped"]) for p in pages),
        "final": {"fields": final_fields, "lines": final_lines, "signatures": sigs},
        "verify": verify, "oracle": oracle, "system_errors": result.get("system_errors") or [],
        "versions": {"standard": (result.get("versions") or {}).get("standard"),
                     "ruleset": (result.get("versions") or {}).get("ruleset"),
                     "schema": (result.get("versions") or {}).get("schema")},
        "validation_id": (result.get("request") or {}).get("validation_id"),
        "integrity": (result.get("integrity") or {}).get("payload_sha256"),
        "replay": None if not replay else {"assume_agreement": replay.get("assume_agreement"),
                                           "skipped_rows": len(replay.get("skipped_rows") or []),
                                           "copy_pages_dropped": len(replay.get("copy_pages_dropped") or [])},
    }
