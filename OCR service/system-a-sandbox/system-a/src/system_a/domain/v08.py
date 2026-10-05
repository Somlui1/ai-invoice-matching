"""V-08 Quantity — AI decides (OQ-03), code supplies facts and a consistency guard.

``build_payload`` computes every number with Decimal (prompt rule A3).
``guard`` never flips an AI verdict to pass/fail; a disagreement becomes ``manual_review``.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal

from .contracts import InvoiceDoc, ReceiptRow
from .standard import Standard


def build_payload(doc: InvoiceDoc, groups, rows: dict[str, ReceiptRow], std: Standard) -> tuple[dict, dict]:
    lines = {l.line_no: l for l in doc.lines}
    inv_lines, mg, facts, expected = [], [], {}, {}
    for l in doc.lines:
        inv_lines.append({"invoice_line_no": l.line_no, "description": l.v("description") or "",
                          "qty_inv": None if l.v("qty") is None else str(l.v("qty")), "uom_group": l.uom_group})
    for g in groups:
        rcv = [rows[i] for i in g.rcv_line_ids]
        mg.append({"group_id": g.group_id, "relation": g.relation, "match_level": g.level,
                   "invoice_line_nos": list(g.invoice_line_nos),
                   "rcv_lines": [{"rcv_line": r.rcv_line_id, "qty_rcv": str(r.qty),
                                  "uom_group": std.uom_group(r.uom)} for r in rcv]})
        if g.relation == "UNMATCHED":
            for n in g.invoice_line_nos:
                expected[n] = ("not_evaluated", None)
            continue
        ug = {std.uom_group(r.uom) for r in rcv} | {lines[n].uom_group for n in g.invoice_line_nos}
        comparable = len(ug) == 1 and None not in ug
        rsum = sum((r.qty for r in rcv), Decimal(0))
        per = []
        for n in g.invoice_line_nos:
            q = lines[n].v("qty")
            cmp_ = rsum if g.relation == "1:N" else rcv[0].qty     # B2 sum lots · B1/B3 per line
            diff = None if q is None else q - cmp_
            per.append({"invoice_line_no": n, "qty_rcv_compared": str(cmp_),
                        "qty_diff": None if diff is None else str(diff)})
            if not comparable or diff is None:
                expected[n] = ("manual_review", None)
            elif diff == 0:
                expected[n] = ("pass", None)
            else:
                expected[n] = ("fail", "E14" if diff > 0 else "E15")
        facts[g.group_id] = {"uom_comparable": comparable, "rcv_qty_sum": str(rsum), "per_line": per}
    return {"INVOICE_LINES": inv_lines, "MATCH_GROUPS": mg, "COMPUTED_FACTS": facts}, expected


def vote(answers: list[dict]) -> tuple[dict, bool]:
    """Self-consistency: per-line majority of (result, code).  Returns (merged, unanimous_or_majority)."""
    if len(answers) == 1:
        return answers[0], True
    by_line: dict[int, list] = {}
    for a in answers:
        for lr in a.get("line_results", []):
            by_line.setdefault(lr["invoice_line_no"], []).append(lr)
    merged, ok = [], True
    for n, lrs in sorted(by_line.items()):
        (key, cnt), = Counter((x["result"], x.get("code")) for x in lrs).most_common(1)
        if cnt * 2 <= len(answers):
            ok = False
            merged.append({**lrs[0], "result": "manual_review", "code": None, "severity": None,
                           "reason": "AI_NO_MAJORITY"})
        else:
            merged.append(next(x for x in lrs if (x["result"], x.get("code")) == key))
    return {"rule_id": "V-08", "line_results": merged}, ok


def guard(ai: dict, expected: dict, enabled: bool = True) -> tuple[list[dict], list[dict]]:
    """Returns (line_results, disagreements)."""
    seen = {lr["invoice_line_no"]: lr for lr in ai.get("line_results", []) if isinstance(lr, dict)}
    out, dis = [], []
    for n, (exp_res, exp_code) in sorted(expected.items()):
        lr = seen.get(n)
        if lr is None:
            out.append({"invoice_line_no": n, "result": "manual_review", "code": None, "severity": None,
                        "message": None, "reason": "AI_LINE_MISSING"})
            dis.append({"invoice_line_no": n, "reason": "missing"})
            continue
        if lr.get("code") not in (None, "E14", "E15"):
            lr = {**lr, "result": "manual_review", "code": None, "reason": "AI_INVALID_CODE"}
        if enabled and (lr["result"], lr.get("code")) != (exp_res, exp_code) and lr["result"] != "manual_review":
            dis.append({"invoice_line_no": n, "ai": [lr["result"], lr.get("code")], "facts": [exp_res, exp_code]})
            lr = {**lr, "result": "manual_review", "code": None, "severity": None, "reason": "AI_FACTS_DISAGREE"}
        out.append(lr)
    return out, dis
