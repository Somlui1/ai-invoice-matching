"""Builds the Standard Output Contract ``aiva.system_a.result/3.0``.

* every extracted value becomes an Element (page/field/row/cell/signature/word) with bbox
* every Finding becomes Evidence with ``related_element_ids`` + ``bboxes`` (or ``bbox_missing_reason``)
* NO workflow / assigned_to / approval / AP / duplicate fields (Responsibility Boundary, X-04)
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

from ..domain.contracts import COORDINATE_SYSTEM, ExtractionResult, InvoiceDoc, row_payload

CONTRACT = "aiva.system_a.result/3.0"
SCHEMA_VERSION = "3.0"
FORBIDDEN_KEYS = {"workflow", "allowed_actions", "assigned_to", "approved", "ap_status", "duplicate_status", "history"}


def _s(v):
    return str(v) if isinstance(v, Decimal) else v


def build_elements(ext: ExtractionResult, doc: InvoiceDoc) -> dict[str, dict]:
    did, dtype = ext.invoice_document_id, next(
        (d.document_type for d in ext.documents if d.document_id == ext.invoice_document_id), "INVOICE")
    els: dict[str, dict] = {}
    src = {"package_id": ext.package_id, "dms_doc_id": ext.dms_doc_id, "file_sha256": ext.file_sha256,
           "extractors": ext.extractor}

    def add(eid, etype, page, bbox, field_name=None, raw=None, norm=None, conf=None, parent=None, extra=None):
        els[eid] = {"element_id": eid, "document_id": did, "document_type": dtype, "page_no": page,
                    "element_type": etype, "parent_id": parent, "field_name": field_name, "raw_value": raw,
                    "normalized_value": _s(norm), "confidence": conf, "bbox": list(bbox) if bbox else None,
                    "source_reference": {**src, **(extra or {})}}

    for p in ext.pages:
        doc_of = next((d for d in ext.documents if p.page_no in d.pages), None)
        els[f"P{p.page_no}"] = {"element_id": f"P{p.page_no}", "document_id": doc_of.document_id if doc_of else None,
                                "document_type": doc_of.document_type if doc_of else "UNKNOWN", "page_no": p.page_no,
                                "element_type": "page", "parent_id": None, "field_name": None, "raw_value": None,
                                "normalized_value": None, "confidence": p.type_confidence, "bbox": [0, 0, 1, 1],
                                "source_reference": src}
    for name, rf in ext.fields.items():
        nf = doc.fields[name]
        add(nf.element_id, "field", rf.region.page if rf.region else None, rf.region.bbox if rf.region else None,
            name, rf.raw, nf.value, rf.confidence, extra={"word_ids": list(rf.word_ids), "null_reason": nf.null_reason,
                                                         "agreement": rf.agreement, "source": rf.source})
    for rl, nl in zip(ext.lines, doc.lines):
        add(nl.element_id, "row", rl.region.page if rl.region else None, rl.region.bbox if rl.region else None,
            f"lines[{rl.line_no}]")
        for k, rf in rl.cells.items():
            nf = nl.cells[k]
            add(nf.element_id, "cell", rf.region.page if rf.region else (rl.region.page if rl.region else None),
                rf.region.bbox if rf.region else None, f"lines[{rl.line_no}].{k}", rf.raw, nf.value, rf.confidence,
                parent=nl.element_id, extra={"null_reason": nf.null_reason, "agreement": rf.agreement})
    for slot, s in ext.signatures.items():
        add(f"{did}-sig-{slot}", "signature", s.region.page if s.region else None, s.region.bbox if s.region else None,
            f"signatures.{slot}", None, s.present, s.confidence, extra={"kind": s.kind})
    for w in ext.words:
        add(w.word_id, "word", w.page, w.bbox, None, w.text, w.text, w.confidence)

    # section / table / stamp level boxes (same 9-level decomposition the result contract allows)
    _kind_map = {"section": "section", "table": "table", "stamp": "stamp"}
    for rg in getattr(ext, "regions", ()) or ():
        owner = next((d for d in ext.documents if rg.page in d.pages), None)
        els[rg.region_id] = {"element_id": rg.region_id,
                             "document_id": owner.document_id if owner else did,
                             "document_type": owner.document_type if owner else dtype,
                             "page_no": rg.page, "element_type": _kind_map.get(rg.kind, "section"),
                             "parent_id": rg.parent_id or f"P{rg.page}", "field_name": rg.label,
                             "raw_value": rg.text, "normalized_value": None, "confidence": rg.confidence,
                             "bbox": list(rg.bbox) if rg.bbox else None,
                             "source_reference": {**src, "region_kind": rg.kind}}
    return els


def _multi_po_keys(snap) -> dict:
    """AIVA-SYSA-ORA-01: the multi-PO audit keys, added only when the lookup produced them.

    A legacy-mode snapshot (RCV-V01 / RCV-V02) fills neither of them, so its payload — and therefore
    ``integrity.payload_sha256`` — is byte-identical to the one this assembler produced before the
    Tax ID + Invoice mode existed.  Reason for touching this file at all: the spec requires new keys
    in ``oracle_snapshot`` (see .agent/decisions.md).
    """
    out: dict = {}
    if getattr(snap, "po_numbers", ()):
        out["po_numbers"] = [str(p) for p in snap.po_numbers]
    if getattr(snap, "matched_on_column", None):
        out["matched_on_column"] = snap.matched_on_column
    return out


def assemble(*, ext, doc, meta, std, ctx, outcomes, recommendation, halted, errors, request, models, metrics) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    els = build_elements(ext, doc)
    evidence, exceptions, rule_results = [], [], []
    n = 0
    for o in outcomes:
        ev_ids = []
        for f in o.findings:
            n += 1
            xid = f"X{n}"
            boxes, missing = [], []
            for eid in f.element_ids:
                e = els.get(eid)
                if e and e["bbox"]:
                    boxes.append({"element_id": eid, "page_no": e["page_no"], "bbox": e["bbox"]})
                else:
                    missing.append(eid)
            evidence.append({
                "evidence_id": xid, "rule_id": o.rule_id, "rule_version": std.rule_version(o.rule_id),
                "result": o.result, "exception_code": f.code, "severity": f.severity,
                "actual_value": f.actual, "expected_value": f.expected,
                "source_document": {"document_id": doc.document_id, "source": f.source},
                "page_no": sorted({b["page_no"] for b in boxes}),
                "related_element_ids": list(f.element_ids), "related_oracle_refs": list(f.oracle_refs),
                "bboxes": boxes, "bbox_missing_reason": ({"element_ids": missing, "reason": "NOT_LOCATED"}
                                                         if missing else None),
                "halted_by": o.halted_by, "evaluated_at": now, "message_th": f.message_th})
            exceptions.append({"exception_id": xid, "code": f.code, "name": std.code_name(f.code),
                               "severity": f.severity, "rule_id": o.rule_id, "evidence_ids": [xid]})
            ev_ids.append(xid)
        rule_results.append({"rule_id": o.rule_id, "rule_version": std.rule_version(o.rule_id), "result": o.result,
                             "detail": o.detail, "halted_by": o.halted_by, "evidence_ids": ev_ids,
                             "data": json.loads(json.dumps(o.data, default=str))})
    snap = ctx.snapshot
    items = normalized_items(doc, els, ctx, outcomes, snap)
    payload = {
        "contract": CONTRACT,
        "request": {**request, "completed_at": now},
        "versions": {"schema": SCHEMA_VERSION, "standard": std.version, "ruleset": std.ruleset_version,
                     "models": models, "prompts": {"V-08": std.rules["V-08"].get("prompt"),
                                                   "V-07": "v07-match@1.0.0", "V-05": "v05-entity@1.0.0"}},
        "package": {"package_id": ext.package_id, "dms_doc_id": ext.dms_doc_id, "file_sha256": ext.file_sha256,
                    "page_count": len(ext.pages), "pages_complete": ext.pages_complete,
                    "coordinate_system": COORDINATE_SYSTEM},
        "pages": [p.model_dump() for p in ext.pages],
        "documents": [d.model_dump() for d in ext.documents],
        "ocr": {"elements": list(els.values())},
        "extraction": {"invoice_document_id": ext.invoice_document_id,
                       "fields": {k: {"raw_value": f.raw, "normalized_value": _s(f.value), "confidence": f.confidence,
                                      "ok": f.ok, "null_reason": f.null_reason, "element_id": f.element_id}
                                  for k, f in doc.fields.items()},
                       "lines": [{"line_no": l.line_no, "element_id": l.element_id, "uom_group": l.uom_group,
                                  "cells": {k: {"raw_value": c.raw, "normalized_value": _s(c.value), "ok": c.ok,
                                                "null_reason": c.null_reason} for k, c in l.cells.items()}}
                                 for l in doc.lines],
                       "signatures": {k: v.model_dump() for k, v in ext.signatures.items()},
                       "extra": ext.extra},
        "normalized_fields": {k: _s(f.value) for k, f in doc.fields.items()} | {"release_num": meta.get("release_num"),
                                                                                "items": items, "items_summary": items_summary(items, doc)},
        "oracle_snapshot": None if snap is None else {
            "queried": True, "queried_at": snap.queried_at, "lookup_path": snap.lookup_path,
            "query_keys": snap.query_keys, "row_cap_hit": snap.row_cap_hit, "fingerprint": snap.fingerprint(),
            "org_id": snap.org_id, "receiver": snap.active[0].receiver if snap.active else None,
            "receipt_nums": snap.receipt_nums,
            "receipt_lines": [{**{k: _s(v) for k, v in row_payload(r).items()}, "rcv_line_id": r.rcv_line_id,
                               "uom_group": std.uom_group(r.uom)}
                              for r in snap.rows]} | _multi_po_keys(snap),
        "line_matching": {"groups": [{**g.__dict__} for g in ctx.groups],
                          "ai_rejected": ctx.match_trace.get("ai_rejected", []),
                          "unmatched_rcv_line_ids": ctx.match_trace.get("unmatched_rcv_line_ids", [])},
        "rule_results": rule_results,
        "evidence": evidence,
        "exceptions": exceptions,
        "recommendation": {**recommendation, "halted_by": halted},
        "system_errors": errors,
        "metrics": metrics,
    }
    payload = json.loads(json.dumps(payload, default=_s, ensure_ascii=False))
    stable = {k: v for k, v in payload.items() if k not in ("request", "metrics")}
    body = json.dumps(_strip_times(stable), sort_keys=True, ensure_ascii=False).encode()
    payload["integrity"] = {"payload_sha256": "sha256:" + hashlib.sha256(body).hexdigest(),
                            "excludes": ["request", "metrics", "*evaluated_at", "*queried_at"]}
    return payload


def _strip_times(o):
    if isinstance(o, dict):
        return {k: _strip_times(v) for k, v in o.items() if k not in ("evaluated_at", "queried_at")}
    if isinstance(o, list):
        return [_strip_times(x) for x in o]
    return o


def normalized_items(doc, els: dict, ctx, outcomes, snap) -> list:
    """The invoice's item list, normalised and checked, for analysis next to the header fields.

    One entry per invoice line: the normalised cells (Decimal -> string), whether each cell is usable, the line's own
    arithmetic (qty x unit_price vs amount), where it is on the page (bbox of the row), which receipt lines it was
    matched to (V-07) and the quantity verdict (V-08).  Nothing here is recomputed by a rule - it is the same data the
    rules used, laid out per line.
    """
    groups = {}
    for g in getattr(ctx, "groups", None) or ():
        for n in g.invoice_line_nos:
            groups[n] = g
    v08 = {}
    for o in outcomes:
        if o.rule_id == "V-08":
            for lr in (o.data or {}).get("line_results") or []:
                if isinstance(lr, dict) and lr.get("invoice_line_no") is not None:
                    v08[lr["invoice_line_no"]] = lr
    rcv = {r.rcv_line_id: r for r in (snap.rows if snap is not None else ())}
    out = []
    for ln in doc.lines:
        cell = lambda k: ln.cells.get(k)
        val = lambda k: _s(cell(k).value) if cell(k) is not None and cell(k).ok else None
        q, p, a = (cell(k).value if cell(k) is not None and cell(k).ok else None for k in ("qty", "unit_price", "amount"))
        math = None
        if None not in (q, p, a):
            diff = (q * p - a).quantize(Decimal("0.01"))
            math = {"qty_x_unit_price": _s((q * p).quantize(Decimal("0.01"))), "amount": _s(a), "diff": _s(diff),
                    "ok": abs(diff) <= Decimal("0.50")}
        g = groups.get(ln.line_no)
        row = els.get(ln.element_id) or {}
        out.append({
            "line_no": ln.line_no, "element_id": ln.element_id, "page_no": row.get("page_no"), "bbox": row.get("bbox"),
            "item_code": val("item_code"), "description": val("description"),
            "qty": val("qty"), "uom": val("uom"), "uom_group": ln.uom_group,
            "unit_price": val("unit_price"), "amount": val("amount"),
            "cells_ok": {k: c.ok for k, c in ln.cells.items()},
            "cells_null_reason": {k: c.null_reason for k, c in ln.cells.items() if not c.ok},
            "line_math": math,
            "match": None if g is None else {
                "group_id": g.group_id, "relation": g.relation, "level": g.level, "confidence": g.confidence,
                "rcv_line_ids": list(g.rcv_line_ids),
                "receipt": [{"rcv_line_id": rid, "item": rcv[rid].item, "qty": _s(rcv[rid].qty), "uom": rcv[rid].uom,
                             "unit_price": _s(rcv[rid].unit_price), "po_number": rcv[rid].po_number}
                            for rid in g.rcv_line_ids if rid in rcv]},
            "qty_check": None if ln.line_no not in v08 else {k: v08[ln.line_no].get(k) for k in
                                                            ("result", "code", "qty_inv", "qty_rcv_compared", "qty_diff")},
        })
    return out


def items_summary(items: list, doc) -> dict:
    """One-glance totals of the item list: how many lines, how many fully usable, sum of amounts vs sub_total."""
    usable = [i for i in items if all(i["cells_ok"].get(k) for k in ("qty", "uom", "unit_price", "amount") if k in i["cells_ok"])]
    amounts = [Decimal(i["amount"]) for i in items if i["amount"] is not None]
    total = sum(amounts, Decimal(0))
    sub = doc.v("sub_total")
    return {"line_count": len(items), "lines_usable": len(usable),
            "lines_math_ok": sum(1 for i in items if (i["line_math"] or {}).get("ok")),
            "lines_matched": sum(1 for i in items if i["match"] and i["match"]["relation"] != "UNMATCHED"),
            "sum_amount": _s(total.quantize(Decimal("0.01"))) if amounts else None,
            "sub_total": _s(sub), "sum_vs_sub_total_diff": _s((total - sub).quantize(Decimal("0.01"))) if amounts and sub is not None else None}
