"""Rules V-01..V-09 (Standard v6.6 Table 6).  One function per rule: (Ctx) -> RuleOutcome.

Logic rules are pure.  AI-assisted rules (V-05 fallback, V-07 M3-M5, V-08) receive the AI
port through Ctx; they never perform IO themselves beyond calling the port.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from . import v08 as v08mod
from .contracts import Finding, InvoiceDoc, OracleSnapshot, RuleOutcome
from .matching import price_check
from .evidence import is_covered
from .normalize import addr_key, norm_name, thai_to_arabic
from .ports import EntityJudgeAI, QtyJudgeAI
from .standard import Standard

D0 = Decimal(0)
Q2 = Decimal("0.01")


@dataclass
class Ctx:
    doc: InvoiceDoc
    std: Standard
    snapshot: Optional[OracleSnapshot] = None
    groups: list = field(default_factory=list)
    match_trace: dict = field(default_factory=dict)
    entity_ai: Optional[EntityJudgeAI] = None
    qty_ai: Optional[QtyJudgeAI] = None
    ai_trace: dict = field(default_factory=dict)


def _f(c: Ctx, code, rule, msg, sev=None, **kw) -> Finding:
    return Finding(code=code, severity=sev or c.std.severity(code), rule_id=rule, message_th=msg, **kw)


def _ok(rid, detail=None, **data):
    return RuleOutcome(rid, "pass", detail=detail, data=data)


def _fail(rid, findings, detail=None, **data):
    worst = max((f.severity for f in findings), key=["Low", "Medium", "High"].index)
    return RuleOutcome(rid, "fail" if worst != "Low" else "pass", tuple(findings), detail, data=data)


def _skip(rid, by, detail):
    return RuleOutcome(rid, "not_evaluated", detail=detail, halted_by=by)


def _flag(c: Ctx, name: str) -> bool:
    """AIVA-SYSA-ORA-01 Standard-change flags (``policy.validation``) — all default to False."""
    return bool((c.std.policy.get("validation") or {}).get(name, False))


def _evidence_flag(c: Ctx, name: str) -> bool:
    """policy.evidence switches (domain/evidence.py) — default False when absent."""
    return bool((c.std.policy.get("evidence") or {}).get(name, False))


def _tax_lookup(s) -> bool:
    """True when the snapshot came from the Tax ID + Invoice lookup (not RCV-V01/RCV-V02)."""
    return "supplier_tax_id_source" in (s.query_keys or {})


def _line_tag(l) -> str:
    return f"บรรทัดที่ {l.line_no} (Invoice: {l.v('description') or '-'})"


# =============================================================== STEP 1 — document only
def v01_required(c: Ctx) -> RuleOutcome:
    d, miss, eids = c.doc, [], []
    for k in c.std.policy["required_fields"]:
        f = d.fields[k]
        if not f.ok:
            miss.append(f"{k}({f.null_reason})"), eids.append(f.element_id)
    if not d.lines:
        miss.append("lines(NOT_PRESENT)")
    for l in d.lines:
        for k in c.std.policy["required_line_cells"]:
            cf = l.cells[k]
            if not cf.ok:
                miss.append(f"L{l.line_no}.{k}({cf.null_reason})"), eids.append(cf.element_id)
    if not d.pages_complete:
        miss.append("pages_complete(false)")
    if not miss:
        return _ok("V-01")
    return _fail("V-01", [_f(c, "E01", "V-01", "ฟิลด์บังคับอ่านไม่ได้หรือไม่ครบ: " + ", ".join(miss),
                             element_ids=tuple(eids))])


def v02_line_math(c: Ctx) -> RuleOutcome:
    out, checked = [], 0
    for l in c.doc.lines:
        if not all(l.ok(k) for k in ("qty", "unit_price", "amount")):
            continue
        checked += 1
        calc = (l.v("qty") * l.v("unit_price")).quantize(Q2)
        if abs(calc - l.v("amount")) > c.std.tol("line_math"):
            out.append(_f(c, "E02", "V-02",
                          f"{_line_tag(l)}: {l.v('qty')} × {l.v('unit_price')} = {calc} แต่ระบุ {l.v('amount')}",
                          actual=str(l.v("amount")), expected=str(calc),
                          element_ids=(l.element_id, l.cells["qty"].element_id, l.cells["unit_price"].element_id,
                                       l.cells["amount"].element_id)))
    if out:
        return _fail("V-02", out)
    if checked == 0:
        return _skip("V-02", "V-01", "ไม่มีบรรทัดที่อ่านค่าครบ")
    return _ok("V-02", f"ตรวจ {checked} บรรทัด")


def v03_doc_totals(c: Ctx) -> RuleOutcome:
    d = c.doc
    if not all(d.ok(k) for k in ("sub_total", "vat", "grand_total")) or not d.lines \
            or not all(l.ok("amount") for l in d.lines):
        return _skip("V-03", "V-01", "ยอดรวมหรือราคารวมต่อรายการอ่านไม่ได้")
    sub, vat, grand = d.v("sub_total"), d.v("vat"), d.v("grand_total")
    lines_sum = sum((l.v("amount") for l in d.lines), D0)
    diffs = {"lines_vs_sub_total": abs(lines_sum - sub),
             "vat_7pct": abs((sub * c.std.tol("vat_rate")).quantize(Q2) - vat),
             "sub_plus_vat_vs_grand": abs(sub + vat - grand)}
    eids = tuple(d.fields[k].element_id for k in ("sub_total", "vat", "grand_total"))
    over = (diffs["lines_vs_sub_total"] > c.std.tol("total") or diffs["vat_7pct"] > c.std.tol("vat")
            or diffs["sub_plus_vat_vs_grand"] > c.std.tol("total"))
    detail = {k: str(v) for k, v in diffs.items()}
    if over:
        return _fail("V-03", [_f(c, "E03", "V-03", f"ยอดรวมภายในใบแจ้งหนี้ไม่สอดคล้อง {detail}", source="invoice",
                                 actual=str(sub), expected=str(lines_sum), element_ids=eids)], diffs=detail)
    if any(v > 0 for v in diffs.values()):
        return _fail("V-03", [_f(c, "E04", "V-03", f"ผลต่างเศษปัดอยู่ในกรอบ {detail}", element_ids=eids)], diffs=detail)
    return _ok("V-03", diffs=detail)


def v06_signatures(c: Ctx) -> RuleOutcome:
    if not c.doc.pages_complete:
        return _skip("V-06", "V-01", "สแกนไม่ครบหน้า (E01 ไม่ใช่ E08)")
    th = c.std.policy["signature"]["min_confidence"]
    out, unsure = [], []
    for slot, sev, label in (("receiver", "High", "ผู้รับของ"), ("deliverer", "Medium", "ผู้ขาย/ผู้ส่งของ")):
        s = c.doc.signatures.get(slot)
        eid = (f"{c.doc.document_id}-sig-{slot}",)
        if s is None or s.present is None or (s.confidence is not None and s.confidence < th):
            unsure.append(slot)
        elif not s.present:
            out.append(_f(c, "E08", "V-06", f"ไม่พบลายเซ็นหรือตราในช่อง{label}", sev, element_ids=eid))
    if out:
        return _fail("V-06", out, unsure_slots=unsure)
    if unsure:
        return RuleOutcome("V-06", "manual_review", detail=f"ความมั่นใจต่ำ: {unsure}", data={"unsure_slots": unsure})
    return _ok("V-06")


# =============================================================== STEP 2 — Oracle
def v04_receipt(c: Ctx) -> RuleOutcome:
    s = c.snapshot
    keys = tuple(c.doc.fields[k].element_id for k in ("po_number", "invoice_num"))
    data = {"lookup_path": s.lookup_path, "rows": len(s.rows), "active_rows": len(s.active),
            "receipt_nums": s.receipt_nums}
    if _tax_lookup(s):
        data.update(po_numbers=list(s.po_numbers), matched_on_column=s.matched_on_column)
    if not s.active:
        if _tax_lookup(s):
            q = s.query_keys
            why = (" (เลข Invoice มีอักขระที่ไม่อนุญาต จึงไม่ค้นหา)" if q.get("invoice_rejected") else
                   "" if q.get("supplier_tax_id") else " (ไม่ทราบ Tax ID ผู้ขาย)")
            msg = (f"ไม่พบใบรับที่ QTY > 0 สำหรับ Tax ID ผู้ขาย {q.get('supplier_tax_id') or '-'} + Invoice "
                   f"{q.get('invoice_num')}{why}")
            ids = tuple(c.doc.fields[k].element_id for k in ("supplier_tax_id", "invoice_num") if k in c.doc.fields)
            return _fail("V-04", [_f(c, "E05", "V-04", msg, element_ids=ids or keys)], **data)
        return _fail("V-04", [_f(c, "E05", "V-04",
                                 f"ไม่พบใบรับที่ QTY > 0 สำหรับ PO {s.query_keys.get('po_number')} + Invoice "
                                 f"{s.query_keys.get('invoice_num')}", element_ids=keys)], **data)
    if len(s.receipt_nums) > 1 and _flag(c, "multi_po_receipts"):
        # Several receipts / POs are legitimate for ONE supplier and ONE operating unit only.
        sups = sorted({r.supplier_tax_id for r in s.active if r.supplier_tax_id})
        ous = sorted({(r.ou_org_id if r.ou_org_id is not None else r.org_id) for r in s.active} - {None})
        data.update(multi_receipt=True, supplier_tax_ids=sups, ou_org_ids=ous)
        if len(sups) > 1 or len(ous) > 1:
            what = "ผู้ขาย" if len(sups) > 1 else "หน่วยธุรกิจ (OU)"
            vals = sups if len(sups) > 1 else [str(o) for o in ous]
            return _fail("V-04", [_f(c, "E06", "V-04",
                                     f"พบใบรับหลายใบที่มาจาก{what}ต่างกัน: " + ", ".join(vals),
                                     element_ids=keys, oracle_refs=tuple(f"RCV:{n}" for n in s.receipt_nums))],
                         **data)
    elif len(s.receipt_nums) > 1:
        return _fail("V-04", [_f(c, "E06", "V-04", "พบใบรับมากกว่า 1 ใบ: " + ", ".join(s.receipt_nums),
                                 element_ids=keys, oracle_refs=tuple(f"RCV:{n}" for n in s.receipt_nums))], **data)
    if s.row_cap_hit:
        return RuleOutcome("V-04", "manual_review", detail=f"SQL คืน {c.std.policy['oracle']['row_cap']} แถวพอดี",
                           data=data)
    if len(s.receipt_nums) > 1:
        return _ok("V-04", f"ใบรับ {len(s.receipt_nums)} ใบ ({s.lookup_path}): " + ", ".join(s.receipt_nums), **data)
    return _ok("V-04", f"ใบรับ {s.receipt_nums[0]} ({s.lookup_path})", **data)


def v05_customer(c: Ctx) -> RuleOutcome:
    orgs = sorted({r.org_id for r in c.snapshot.active if r.org_id is not None})
    if len(orgs) > 1 and _flag(c, "multi_po_receipts"):
        # V-04 already reports this as E06 (receipts from different OUs); one ORG_ID cannot be chosen.
        return RuleOutcome("V-05", "not_evaluated", detail=f"ใบรับมาจากหลาย ORG_ID: {orgs} (ดู V-04)",
                           halted_by="V-04", data={"org_ids": orgs})
    org = c.snapshot.org_id
    ent = c.std.entities.get(org) if org is not None else None
    base = {"org_id": org, "short_name": ent.get("short") if ent else None}
    sup = c.doc.v("supplier_tax_id")
    base["intercompany"] = bool(sup) and any(e.get("tax_id") == sup for e in c.std.entities.values())
    if ent is None or ent["status"] in ("unknown", "cancelled") or not ent.get("tax_id"):
        return RuleOutcome("V-05", "manual_review",
                           detail=f"ORG_ID {org} สถานะ {ent['status'] if ent else 'ไม่อยู่ในตารางที่ 4'} หรือไม่มี Tax ID",
                           data=base)
    d = c.doc
    if not d.ok("customer_tax_id"):
        return _skip("V-05", "V-01", "Tax ID ลูกค้าอ่านไม่ได้")
    fid = lambda k: (d.fields[k].element_id,)
    if d.v("customer_tax_id") != ent["tax_id"]:
        return _fail("V-05", [_f(c, "E07", "V-05", f"Tax ID ลูกค้า {d.v('customer_tax_id')} ≠ {ent['tax_id']} (ORG_ID {org})",
                                 "High", actual=d.v("customer_tax_id"), expected=ent["tax_id"],
                                 element_ids=fid("customer_tax_id"))], **base, tax_id_match=False)
    findings, data = [], {**base, "tax_id_match": True}
    th = c.std.policy["ai"]["v05_name_min_confidence"]
    # ---- name: logic, then AI semantic (OQ-05).  A name problem is held in name_issue and applied
    # after the address check, so policy.evidence.customer_name_advisory can turn it into audit data
    # when the Tax ID (and the address, where readable) already prove the buyer entity.
    name_issue = None                     # ("manual", detail) | Finding
    if d.ok("customer_name") and is_covered(d.fields.get("customer_name")):
        # the read name was not confirmed by a second reader, but the Tax ID equals Oracle:
        # the legal entity is proven by the Tax ID, the garbled Thai name is not evidence against it
        data.update(name_match=None, name_check="covered_by_customer_tax_id")
    elif d.ok("customer_name"):
        cands = {"name_th": ent.get("name_th"), "name_en": ent.get("name_en"),
                 **{f"former_{i}": n for i, n in enumerate(ent.get("former") or [])}}
        hit = next((k for k, n in cands.items() if n and norm_name(n) == norm_name(d.v("customer_name"))), None)
        if hit:
            data.update(name_match=True, matched_on=hit)
        elif c.entity_ai:
            r = c.entity_ai.name_equivalent(d.v("customer_name"), {k: v for k, v in cands.items() if v})
            c.ai_trace.setdefault("v05", []).append({"task": "name", **r})
            if r.get("equivalent") and float(r.get("confidence", 0)) >= th:
                data.update(name_match=True, matched_on="ai_semantic:" + str(r.get("matched_candidate")))
            elif float(r.get("confidence", 0)) < th:
                data.update(name_match=None)
                name_issue = ("manual", "AI ไม่มั่นใจเรื่องชื่อลูกค้า")
            else:
                data.update(name_match=False)
                name_issue = _f(c, "E07", "V-05", f"ชื่อลูกค้าไม่ตรงกับ ORG_ID {org}", "Medium",
                                actual=d.v("customer_name"), expected=ent.get("name_th"),
                                element_ids=fid("customer_name"))
        else:
            data.update(name_match=False)
            name_issue = _f(c, "E07", "V-05", f"ชื่อลูกค้าไม่ตรงกับ ORG_ID {org}", "Medium",
                            actual=d.v("customer_name"), expected=ent.get("name_th"), element_ids=fid("customer_name"))
    if name_issue is not None and not _evidence_flag(c, "customer_name_advisory"):
        if isinstance(name_issue, tuple):              # unchanged Standard behaviour
            return RuleOutcome("V-05", "manual_review", detail=name_issue[1], data=data)
        findings.append(name_issue)
        name_issue = None
    # ---- address: house no + postal (X-03), AI parse when logic fails
    if d.ok("customer_address") and is_covered(d.fields.get("customer_address")):
        data.update(address_match=None, address_check="covered_by_customer_tax_id")
    elif d.ok("customer_address"):
        addrs = {"head_office_th": ent.get("addr_th"), "head_office_en": ent.get("addr_en"),
                 **{f"branch {k}": v for k, v in (ent.get("branches") or {}).items()}}
        keys = {k: addr_key(v) for k, v in addrs.items() if v}
        inv_key = addr_key(d.v("customer_address"))
        hit = next((k for k, v in keys.items() if None not in inv_key and v == inv_key), None)
        how = "logic"
        if not hit and c.entity_ai and c.std.policy["ai"]["v05_address_ai_enabled"]:
            r = c.entity_ai.parse_address(d.v("customer_address"))
            c.ai_trace.setdefault("v05", []).append({"task": "address", **r})
            if float(r.get("confidence", 0)) < th:
                data.update(address_match=None)
                return RuleOutcome("V-05", "manual_review", tuple(findings), "AI ไม่มั่นใจเรื่องที่อยู่", data=data)
            ai_key = (thai_to_arabic(str(r.get("house_no") or "")) or None,
                      thai_to_arabic(str(r.get("postal_code") or "")) or None)
            hit = next((k for k, v in keys.items() if None not in ai_key and v == ai_key), None)
            how = "ai_normalized"
        data.update(address_match=bool(hit), address_matched=hit, address_method=how if hit else None)
        if not hit:
            findings.append(_f(c, "E07", "V-05", f"ที่อยู่ลูกค้า (เลขที่ {inv_key[0]}, รหัสไปรษณีย์ {inv_key[1]}) "
                                                 f"ไม่ตรงกับที่อยู่ของ ORG_ID {org}", "Medium",
                               actual=d.v("customer_address"), element_ids=fid("customer_address")))
    if name_issue is not None:
        address_ok = data.get("address_match") is True or data.get("address_check") == "covered_by_customer_tax_id"
        if _evidence_flag(c, "customer_name_advisory") and address_ok:
            data.update(name_check="advisory", name_issue=name_issue[1] if isinstance(name_issue, tuple)
                        else name_issue.message_th)
        elif isinstance(name_issue, tuple):
            return RuleOutcome("V-05", "manual_review", tuple(findings), name_issue[1], data=data)
        else:
            findings.insert(0, name_issue)
    if not d.ok("customer_name") or not d.ok("customer_address"):
        if findings:
            return _fail("V-05", findings, **data)
        return _skip("V-05", "V-01", "ชื่อหรือที่อยู่ลูกค้าอ่านไม่ได้")
    return _fail("V-05", findings, **data) if findings else _ok("V-05", **data)


# =============================================================== STEP 3 — vs receipt
def v07_line_match(c: Ctx) -> RuleOutcome:
    rows = {r.rcv_line_id: r for r in c.snapshot.active}
    lines = {l.line_no: l for l in c.doc.lines}
    out, min_conf = [], c.std.policy["ai"]["v07_min_confidence"]
    for g in c.groups:
        refs = tuple(f"RCV:{i}" for i in g.rcv_line_ids)
        if g.relation == "UNMATCHED" or g.confidence < min_conf:
            for n in g.invoice_line_nos:
                l = lines[n]
                out.append(_f(c, "E13", "V-07", f"{_line_tag(l)}: ระบุบรรทัดในใบรับไม่ได้", element_ids=(l.element_id,),
                              oracle_refs=refs))
            continue
        rcv = [rows[i] for i in g.rcv_line_ids]
        rcv_groups = {c.std.uom_group(r.uom) for r in rcv}
        tot_q = sum((r.qty for r in rcv), D0)
        rcv_price = rcv[0].unit_price if len({r.unit_price for r in rcv}) == 1 else \
            (sum((r.line_amount for r in rcv), D0) / tot_q).quantize(Decimal("0.0001")) if tot_q else D0
        for n in g.invoice_line_nos:
            l = lines[n]
            eids = (l.element_id, l.cells["unit_price"].element_id)
            if l.uom_group not in rcv_groups or len(rcv_groups) > 1:
                inv_raw = l.cells["uom"].raw
                rcv_txt = ", ".join(sorted({f"{r.uom}→{c.std.uom_group(r.uom)}" for r in rcv}))
                out.append(_f(c, "E10", "V-07", f"{_line_tag(l)}: หน่วยนับต่างกลุ่มหลังแปลง "
                                                 f"(Inv: {inv_raw}→{l.uom_group}, Rcv: {rcv_txt})",
                              actual=str(l.uom_group), expected=",".join(sorted(rcv_groups)),
                              element_ids=(l.element_id, l.cells["uom"].element_id), oracle_refs=refs))
                continue
            p = l.v("unit_price")
            if p is None:
                # an unreadable price is E01 (V-01), not evidence of a price variance (E09 High)
                if g.level == "M4":
                    out.append(_f(c, "E11", "V-07", f"{_line_tag(l)}: จับคู่ด้วยคำบรรยาย ({g.rationale or ''})"[:200],
                                  element_ids=(l.element_id,), oracle_refs=refs))
                continue
            pc = price_check(p, rcv_price, c.std)
            if pc == "over_tolerance":
                out.append(_f(c, "E09", "V-07", f"{_line_tag(l)}: ราคาต่างเกินกรอบ (Inv: {p}, Rcv: {rcv_price})",
                              actual=str(p), expected=str(rcv_price), element_ids=eids, oracle_refs=refs))
            elif pc == "within_tolerance":
                out.append(_f(c, "E12", "V-07", f"{_line_tag(l)}: ราคาต่างในกรอบ (Inv: {p}, Rcv: {rcv_price})",
                              actual=str(p), expected=str(rcv_price), element_ids=eids, oracle_refs=refs))
            if g.level == "M4":
                out.append(_f(c, "E11", "V-07", f"{_line_tag(l)}: จับคู่ด้วยคำบรรยาย ({g.rationale or ''})"[:200],
                              element_ids=(l.element_id,), oracle_refs=refs))
    data = {"groups": len(c.groups), "ai_rejected": len(c.match_trace.get("ai_rejected", []))}
    if c.match_trace.get("ai_rejected"):
        return RuleOutcome("V-07", "manual_review", tuple(out), "AI เสนอการจับคู่ที่อ้างบรรทัดไม่ถูกต้อง", data=data)
    return _fail("V-07", out, **data) if out else _ok("V-07", **data)


def v08_quantity(c: Ctx) -> RuleOutcome:
    rows = {r.rcv_line_id: r for r in c.snapshot.active}
    payload, expected = v08mod.build_payload(c.doc, c.groups, rows, c.std)
    if c.qty_ai is None:
        return RuleOutcome("V-08", "manual_review", detail="ไม่มี AI สำหรับ V-08")
    n = int(c.std.policy["ai"]["v08_votes"])
    merged, majority = v08mod.vote([c.qty_ai.judge(payload) for _ in range(n)])
    results, dis = v08mod.guard(merged, expected, c.std.policy["ai"]["v08_consistency_guard"])
    c.ai_trace["v08"] = {"votes": n, "majority": majority, "disagreements": dis}
    lines = {l.line_no: l for l in c.doc.lines}
    gid_of = {x: g for g in c.groups for x in g.invoice_line_nos}
    out = []
    for lr in results:
        if lr["result"] == "fail":
            l, g = lines[lr["invoice_line_no"]], gid_of[lr["invoice_line_no"]]
            out.append(_f(c, lr["code"], "V-08", lr.get("message") or f"{_line_tag(l)}: จำนวนไม่เท่าใบรับ",
                          actual=str(l.v("qty")), expected=lr.get("qty_rcv_compared"),
                          element_ids=(l.element_id, l.cells["qty"].element_id),
                          oracle_refs=tuple(f"RCV:{i}" for i in g.rcv_line_ids)))
    res = [lr["result"] for lr in results]
    data = {"line_results": results, "prompt": c.std.rules["V-08"].get("prompt")}
    if out:
        return _fail("V-08", out, **data)
    if "manual_review" in res:
        return RuleOutcome("V-08", "manual_review", detail="AI/facts ไม่สอดคล้อง หรือเทียบจำนวนไม่ได้", data=data)
    if res and all(r == "not_evaluated" for r in res):
        return _skip("V-08", "V-07", "ทุกบรรทัดระบุคู่ในใบรับไม่ได้")
    return _ok("V-08", **data)


def v09_total_vs_receipt(c: Ctx) -> RuleOutcome:
    if not c.doc.ok("sub_total"):
        return _skip("V-09", "V-01", "ยอดก่อนภาษีอ่านไม่ได้")
    sub = c.doc.v("sub_total")
    data: dict = {}
    if _flag(c, "v09_compare_matched_only"):
        # Partial billing of a receipt: compare with the receipt lines V-07 matched, not the whole receipt.
        matched = {i for g in c.groups if g.relation != "UNMATCHED" for i in g.rcv_line_ids}
        rows = [r for r in c.snapshot.active if r.rcv_line_id in matched]
        data = {"compared": "matched_only", "matched_rcv_line_ids": sorted(matched),
                "unmatched_rcv_line_ids": sorted(r.rcv_line_id for r in c.snapshot.active
                                                 if r.rcv_line_id not in matched)}
    else:
        rows = c.snapshot.active
    rcv = sum((r.line_amount for r in rows), D0)
    if abs(sub - rcv) > c.std.tol("total"):
        return _fail("V-09", [_f(c, "E03", "V-09", f"ยอดก่อนภาษี {sub} ≠ ยอดใบรับ {rcv}", source="receipt",
                                 actual=str(sub), expected=str(rcv),
                                 element_ids=(c.doc.fields["sub_total"].element_id,),
                                 oracle_refs=tuple(f"RCV:{n}" for n in c.snapshot.receipt_nums))], **data)
    return _ok("V-09", f"invoice {sub:,} = receipt {rcv:,}", **data)


STEP1 = (v01_required, v02_line_math, v03_doc_totals, v06_signatures)
STEP2 = (v04_receipt, v05_customer)
STEP3 = (v07_line_match, v08_quantity, v09_total_vs_receipt)
ALL_RULE_IDS = ("V-01", "V-02", "V-03", "V-04", "V-05", "V-06", "V-07", "V-08", "V-09")
