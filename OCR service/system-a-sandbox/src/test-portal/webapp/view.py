"""Screen model - every value the browser shows is taken from System A's final payload, nothing else.

The payload is ``aiva.system_a.result/3.0``, the object System A returns from ``process_pdf()`` (and from
``POST /api/v1/validations`` when it runs as HTTP).  Its shape is System A's contract, not the portal's choice:

    contract                                    "aiva.system_a.result/3.0"
    versions        schema, standard, ruleset, models, prompts
    package         package_id, dms_doc_id, page_count, pages_complete, coordinate_system
    request         validation_id, run_id, source, created_at, completed_at, validation_round
    documents       [{document_id, document_type, pages, confidence}]
    pages           [{page_no, width_pt, height_pt, rotation, render_dpi, page_type, type_confidence, ocr_quality}]
    ocr.elements    [{element_id, element_type, page_no, parent_id, field_name, raw_value, normalized_value,
                      confidence, bbox, source_reference}]              every box on the page is one of these
    normalized_fields  invoice_num, invoice_date, po_number, supplier_*, currency, sub_total, vat, grand_total,
                       items[] (line_no, element_id, description, qty, uom, unit_price, amount, cells_ok,
                       line_math), items_summary
    line_matching   groups[] (group_id, relation, level, invoice_line_nos, rcv_line_ids, confidence, source,
                    rationale), ai_rejected[], unmatched_rcv_line_ids[]
    signatures / documents are read from the elements; oracle_snapshot is what Oracle answered
    recommendation  value, max_severity, exception_codes[], reasons[], halted_by
    rule_results    [{rule_id, rule_version, result, detail, halted_by, evidence_ids, data}]
    exceptions      [{exception_id, code, name, severity, rule_id, evidence_ids}]
    evidence        [{evidence_id, rule_id, related_element_ids[], bboxes[], message_th, ...}]
    integrity       payload_sha256, excludes[]          metrics  duration_ms, oracle_calls, ai
    system_errors   []

What the portal decides, and nothing else: grouping elements per page, which element backs each final value
(matched by ``element_type`` + ``field_name``, the way System A labels them), the element types offered as
checkboxes and the colour of each.  A box is never moved, resized or invented: it is ``bbox`` as delivered.

The reading stage is deliberately absent.  The payload carries ``extraction`` - the cleaned fields, lines and
signatures System A worked from, with the raw OCR block stripped - and that is what the portal's
``/api/documents/{id}/extraction`` endpoint hands back when someone wants to look at it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

PAYLOAD_CONTRACT = "aiva.system_a.result/3.0"

# Colours are chosen to be distinguishable for common colour-vision deficiencies.
COLORS = {
    "field": "#1f77b4",        # blue
    "row": "#2ca02c",          # green
    "cell": "#9edae5",         # pale cyan
    "table": "#17becf",        # cyan
    "section": "#bcbd22",      # olive
    "signature": "#d62728",    # red
    "stamp": "#e377c2",        # pink
    "word": "#7f7f7f",         # grey
    "page": "#ff7f0e",         # orange
}
DEFAULT_TYPES = ("field", "row", "signature", "stamp")
ELEMENT_TYPES = tuple(COLORS)

#: what a result/3.0 must carry before the portal can draw anything from it
REQUIRED = ("contract", "versions", "package", "pages", "ocr", "normalized_fields",
            "line_matching", "recommendation", "rule_results")

#: shown as "final fields", in this order: payload key, label on screen
FIELD_ORDER = (
    ("invoice_num", "เลขที่เอกสาร"),
    ("invoice_date", "วันที่เอกสาร"),
    ("po_number", "เลขที่ PO"),
    ("supplier_name", "ผู้ขาย"),
    ("supplier_tax_id", "เลขประจำตัวผู้เสียภาษีผู้ขาย"),
    ("currency", "สกุลเงิน"),
    ("sub_total", " subtotal"),
    ("vat", "ภาษีมูลค่าเพิ่ม"),
    ("grand_total", "ยอดรวม"),
)
TOTAL_FIELDS = ("sub_total", "vat", "grand_total")
SEARCH_TEXT_CAP = 5000
SEARCH_EXCERPT = 240
MAX_EXTRA = 200
MAX_PHRASES = 60


class PayloadError(ValueError):
    """What we got is not a System A result 3.0 - so there is nothing to draw.  Never guessed around."""


def text_of(e: Dict[str, Any]) -> str:
    """What a box says on screen: its value, falling back to the field it carries.

    A boolean (a signature is present or not) is not text - the box is named after its field and the panel
    next to it says ``present: true``.
    """
    v = e.get("raw_value")
    if v in (None, "") and e.get("normalized_value") not in (None, "", True, False):
        v = e["normalized_value"]
    if v in (None, "") or isinstance(v, bool):
        return e.get("field_name") or e["element_id"]
    return str(v)


def element_view(e: Dict[str, Any]) -> Dict[str, Any]:
    """One entry of ``ocr.elements``, renamed only where a shorter name is clearer."""
    bbox = e.get("bbox")
    return {
        "id": e.get("element_id"),
        "type": e.get("element_type"),
        "page": e.get("page_no"),
        "parent": e.get("parent_id"),
        "field": e.get("field_name"),
        "raw": e.get("raw_value"),
        "value": e.get("normalized_value"),
        "text": text_of(e),
        "conf": e.get("confidence"),
        "bbox": bbox,
        "source_ref": e.get("source_reference"),
        "has_bbox": isinstance(bbox, list) and len(bbox) == 4,
    }


def _refs_for(by: Dict[str, dict], fields: Dict[str, Any], name: str) -> List[str]:
    """The element System A read a final value from - found the way System A labels elements."""
    e = by.get(("field", name))
    return [e["id"]] if e and e["has_bbox"] else []


def _seconds(metrics: Dict[str, Any]) -> Optional[float]:
    ms = (metrics.get("duration_ms") or {}).get("total_ms")
    return round(ms / 1000.0, 2) if isinstance(ms, (int, float)) else None


def build_view(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Turn a result/3.0 payload into everything the browser needs.  Raises :class:`PayloadError` otherwise."""
    p = payload if isinstance(payload, dict) else {}
    if p.get("contract") != PAYLOAD_CONTRACT:
        raise PayloadError(f"not a {PAYLOAD_CONTRACT} payload (contract={p.get('contract')!r})")
    missing = [k for k in REQUIRED if k not in p]
    if missing:
        raise PayloadError("incomplete result/3.0 payload, missing " + ", ".join(missing))

    # ---------------------------------------------------------------- the elements, and the pages that hold them
    elements: Dict[str, dict] = {}
    by_field: Dict[tuple, dict] = {}
    for raw in p["ocr"].get("elements") or []:
        e = element_view(raw)
        if not e["id"]:
            continue
        elements[e["id"]] = e
        if e["type"] == "field" and e["field"]:
            by_field.setdefault((e["type"], e["field"]), e)

    pages: List[dict] = []
    for pg in p.get("pages") or []:
        pages.append({
            "page": pg.get("page_no"),
            "width_pt": pg.get("width_pt"), "height_pt": pg.get("height_pt"),
            "rotation": pg.get("rotation", 0), "render_dpi": pg.get("render_dpi"),
            "page_type": pg.get("page_type"), "type_confidence": pg.get("type_confidence"),
            "ocr_quality": pg.get("ocr_quality"),
            "elements": [],
        })
    page_of = {q["page"]: q for q in pages}
    for e in elements.values():
        q = page_of.get(e["page"])
        if q is None:                                    # a page the payload never described: still show it
            q = {"page": e["page"], "width_pt": None, "height_pt": None, "rotation": 0, "render_dpi": None,
                 "page_type": None, "type_confidence": None, "ocr_quality": None, "elements": []}
            pages.append(q)
            page_of[e["page"]] = q
        q["elements"].append(e["id"])

    # ---------------------------------------------------------------- what System A decided
    fields = p.get("normalized_fields") or {}
    final = [{"key": k, "label": label, "value": fields.get(k), "refs": _refs_for(by_field, fields, k)}
             for k, label in FIELD_ORDER]

    match_of: Dict[Any, dict] = {}
    for g in (p.get("line_matching") or {}).get("groups") or []:
        for no in g.get("invoice_line_nos") or []:
            match_of[no] = g
    lines: List[dict] = []
    for it in fields.get("items") or []:
        ref = it.get("element_id")
        g = match_of.get(it.get("line_no"))
        lines.append({
            "no": it.get("line_no"), "desc": it.get("description"), "qty": it.get("qty"),
            "uom": it.get("uom"), "unit_price": it.get("unit_price"), "amount": it.get("amount"),
            "page": it.get("page_no"), "bbox": it.get("bbox"), "ref": ref if ref in elements else None,
            "cells_ok": it.get("cells_ok"), "cells_null_reason": it.get("cells_null_reason"),
            "line_math": it.get("line_math"),
            "match": None if g is None else {
                "group_id": g.get("group_id"), "level": g.get("level"), "relation": g.get("relation"),
                "rcv_line_ids": g.get("rcv_line_ids"), "confidence": g.get("confidence"),
                "source": g.get("source"), "rationale": g.get("rationale")},
        })
    lm = p.get("line_matching") or {}
    extra = [{"kind": "ai_rejected", **x} for x in lm.get("ai_rejected") or []]
    extra += [{"kind": "unmatched_rcv_line", "rcv_line_id": x} for x in lm.get("unmatched_rcv_line_ids") or []]

    sigs: List[dict] = []
    for e in elements.values():
        if e["type"] != "signature":
            continue
        sigs.append({"slot": (e["field"] or "").split(".")[-1] or "signature", "present": e["value"],
                     "raw": e["raw"], "conf": e["conf"], "page": e["page"],
                     "refs": [e["id"]] if e["has_bbox"] else []})

    # ---------------------------------------------------------------- the verdict, and the proof of it
    evidence = {ev.get("evidence_id"): ev for ev in p.get("evidence") or [] if ev.get("evidence_id")}
    rules = [{"id": r.get("rule_id"), "result": r.get("result"), "version": r.get("rule_version"),
              "detail": r.get("detail"), "halted_by": r.get("halted_by"),
              "evidence_ids": r.get("evidence_ids") or [], "data": r.get("data") or {}}
             for r in p.get("rule_results") or []]
    exceptions: List[dict] = []
    for x in p.get("exceptions") or []:
        refs, notes, detail = [], [], ""
        for eid in x.get("evidence_ids") or []:
            ev = evidence.get(eid)
            if not ev:
                continue
            refs += [r for r in ev.get("related_element_ids") or [] if r in elements]
            detail = detail or (ev.get("message_th") or "")
            for b in ev.get("bboxes") or []:
                if b.get("element_id") not in elements:
                    notes.append(f"evidence {eid} points at {b.get('element_id')}, which the payload has no element for")
        exceptions.append({"id": x.get("exception_id"), "code": x.get("code"), "name": x.get("name"),
                           "severity": x.get("severity"), "rule_id": x.get("rule_id"),
                           "detail": detail, "refs": refs, "missing_refs": notes})

    rec = p.get("recommendation") or {}
    value = rec.get("value")
    # halted_by is normal: System A stops the rule chain at the first blocking rule.  Only System A's own
    # errors mean the result itself is not whole.
    incomplete = bool(p.get("system_errors"))
    oracle = p.get("oracle_snapshot") or {}

    # ---------------------------------------------------------------- search, over the payload's own text only
    elements_text = "\n".join(f"{e['text']}\n" for e in elements.values())
    fields_text = " ".join(f"{v or ''}\n" for v in fields.values() if isinstance(v, str))
    lines_text = "\n".join(" ".join(str(l.get(k) or "") for k in
                                    ("description", "qty", "uom", "unit_price", "amount")) + "\n"
                           for l in (fields.get("items") or []))
    rules_text = " ".join(f"{r['id']} {r['result']} {r['detail'] or ''} " for r in rules)
    exc_text = " ".join(f"{e['code']} {e['name']} {e['detail']} " for e in exceptions)
    phrases: Dict[str, List[str]] = {}
    for e in elements.values():
        if e["has_bbox"] and e["text"]:
            phrases.setdefault(e["text"][:SEARCH_EXCERPT], []).append(e["id"])
    for l in lines:
        if l["desc"] and l["ref"]:
            phrases.setdefault(l["desc"][:SEARCH_EXCERPT], []).append(l["ref"])

    types_present = [t for t in ELEMENT_TYPES if any(e["type"] == t for e in elements.values())]
    dropped = list(p.get("system_errors") or [])[:MAX_EXTRA]
    return {
        "contract": p["contract"],
        "versions": p.get("versions") or {},
        "package": p.get("package") or {},
        "request": p.get("request") or {},
        "documents": [{"id": d.get("document_id"), "type": d.get("document_type"),
                       "pages": d.get("pages"), "confidence": d.get("confidence")}
                      for d in p.get("documents") or []],
        "recommendation": {"value": value, "severity": rec.get("max_severity"),
                           "codes": rec.get("exception_codes") or [], "reasons": rec.get("reasons") or [],
                           "halted_by": rec.get("halted_by")},
        "cls": "partial" if incomplete else ("ok" if value == "AUTO_PASS"
                                             else "error" if value in ("HOLD", "REJECT") else "partial"),
        "rec": "ผลไม่ครบ" if incomplete else (value or "?"),
        "incomplete": incomplete,
        "seconds": _seconds(p.get("metrics") or {}),
        "pages": pages,
        "elements": elements,
        "types": types_present,
        "types_default": [t for t in DEFAULT_TYPES if t in types_present],
        "colors": COLORS,
        "final": {"refs": [r for f in final for r in f["refs"]], "items": final,
                  "summary": fields.get("items_summary") or {},
                  "buyer": {"name": fields.get("customer_name"), "tax_id": fields.get("customer_tax_id"),
                            "address": fields.get("customer_address")},
                  "source": "normalized_fields"},
        "lines": {"refs": [l["ref"] for l in lines if l["ref"]], "items": lines,
                  "ai_rejected": (lm.get("ai_rejected") or [])[:MAX_EXTRA],
                  "unmatched_rcv_line_ids": (lm.get("unmatched_rcv_line_ids") or [])[:MAX_EXTRA],
                  "extra": extra[:MAX_EXTRA], "source": "normalized_fields.items + line_matching.groups"},
        "signatures": sigs,
        "receipt": {"queried": oracle.get("queried"), "path": oracle.get("lookup_path"),
                    "matched_on": oracle.get("matched_on_column"), "receipt_nums": oracle.get("receipt_nums") or [],
                    "po_numbers": oracle.get("po_numbers") or [], "receiver": oracle.get("receiver"),
                    "query_keys": oracle.get("query_keys") or {}, "row_cap_hit": oracle.get("row_cap_hit"),
                    "fingerprint": oracle.get("fingerprint"), "unknown": not oracle.get("queried")},
        "rules": rules,
        "exceptions": exceptions,
        "integrity": p.get("integrity") or {},
        "metrics": p.get("metrics") or {},
        "dropped": dropped,
        "counts": {"elements": len(elements), "pages": len(pages),
                   "boxes": sum(1 for e in elements.values() if e["has_bbox"]),
                   "no_bbox": sum(1 for e in elements.values() if not e["has_bbox"])},
        "search": {"elements_text": elements_text[:SEARCH_TEXT_CAP], "fields_text": fields_text[:1500],
                   "lines_text": lines_text[:2000], "rules_text": rules_text[:1500],
                   "exceptions_text": exc_text[:1500],
                   "phrases": dict(list(phrases.items())[:MAX_PHRASES])},
    }
