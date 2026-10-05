"""V-07 line resolution: M1 by logic, M3/M4/M5 proposed by AI (OQ-08), then validated by logic.

The AI is the primary matcher for everything that is not a unique 1:1 price match.
Guardrails do not override its judgement; they only reject references to lines that
do not exist / are reused / form N:M groups — those become ``manual_review``.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .contracts import InvoiceDoc, ReceiptRow
from .ports import LineMatcherAI
from .standard import Standard

LEVEL_CONF = {"M1": 1.0, "M3": 0.90, "M4": 0.85, "M5": 0.80}


@dataclass(frozen=True)
class MatchGroup:
    group_id: str
    relation: str                 # 1:1 | 1:N | N:1 | UNMATCHED
    level: str                    # M1 | M3 | M4 | M5 | NONE
    invoice_line_nos: tuple
    rcv_line_ids: tuple
    confidence: float
    source: str                   # logic | ai | guardrail
    rationale: Optional[str] = None


def _price_eq(a, b, std: Standard) -> bool:
    return a is not None and b is not None and abs(a - b) <= std.tol("price_exact")


def inv_payload(doc: InvoiceDoc) -> list[dict]:
    return [{"invoice_line_no": l.line_no, "item_code": l.v("item_code"), "description": l.v("description"),
             "qty": str(l.v("qty")) if l.v("qty") is not None else None, "uom": l.v("uom"), "uom_group": l.uom_group,
             "unit_price": str(l.v("unit_price")) if l.v("unit_price") is not None else None,
             "amount": str(l.v("amount")) if l.v("amount") is not None else None} for l in doc.lines]


def rcv_payload(rows, std: Standard) -> list[dict]:
    return [{"rcv_line_id": r.rcv_line_id, "item": r.item, "qty": str(r.qty), "uom": r.uom,
             "uom_group": std.uom_group(r.uom), "unit_price": str(r.unit_price), "line_amount": str(r.line_amount)}
            for r in rows]


def resolve(doc: InvoiceDoc, active: tuple[ReceiptRow, ...], std: Standard,
            ai: Optional[LineMatcherAI]) -> tuple[list[MatchGroup], dict]:
    groups: list[MatchGroup] = []
    trace: dict = {"ai_rejected": [], "ai_called": False}
    inv = {l.line_no: l for l in doc.lines}
    rcv = {r.rcv_line_id: r for r in active}
    gid = lambda: f"G{len(groups) + 1}"

    # ---- M1 (logic): price equals exactly one receipt line, mutually unique, same UOM group
    for n, l in list(inv.items()):
        p = l.v("unit_price")
        cands = [r for r in rcv.values() if _price_eq(p, r.unit_price, std) and std.uom_group(r.uom) == l.uom_group]
        if len(cands) != 1:
            continue
        r = cands[0]
        rivals = [x for x in inv.values() if x.line_no != n and _price_eq(x.v("unit_price"), r.unit_price, std)]
        if rivals:
            continue
        groups.append(MatchGroup(gid(), "1:1", "M1", (n,), (r.rcv_line_id,), 1.0, "logic", "ราคาตรงบรรทัดเดียว"))
        inv.pop(n), rcv.pop(r.rcv_line_id)

    # ---- M3/M4/M5 (AI primary)
    if inv and rcv and ai is not None:
        trace["ai_called"] = True
        sub = InvoiceDoc(doc.document_id, doc.fields, tuple(inv.values()), doc.signatures, doc.pages_complete)
        out = ai.propose(inv_payload(sub), rcv_payload(list(rcv.values()), std)) or {}
        for g in out.get("groups", []):
            ins = [int(x) for x in g.get("invoice_line_nos", [])]
            rids = [str(x) for x in g.get("rcv_line_ids", [])]
            lvl = g.get("level", "M5")
            why = None
            if not ins or not rids:
                why = "empty_group"
            elif not set(ins) <= inv.keys() or not set(rids) <= rcv.keys():
                why = "unknown_or_reused_line"
            elif len(ins) > 1 and len(rids) > 1:
                why = "n_to_m_not_allowed"
            elif lvl not in ("M3", "M4", "M5"):
                why = "invalid_level"
            if why:
                trace["ai_rejected"].append({"proposal": g, "reason": why})
                continue
            rel = "1:1" if len(ins) == len(rids) == 1 else ("1:N" if len(ins) == 1 else "N:1")
            conf = float(g.get("confidence", LEVEL_CONF[lvl]))
            groups.append(MatchGroup(gid(), rel, lvl, tuple(ins), tuple(rids), conf, "ai", g.get("rationale")))
            for n in ins:
                inv.pop(n)
            for i in rids:
                rcv.pop(i)

    # ---- leftovers
    for n in sorted(inv):
        groups.append(MatchGroup(gid(), "UNMATCHED", "NONE", (n,), (), 0.0,
                                 "guardrail" if trace["ai_rejected"] else ("ai" if trace["ai_called"] else "logic")))
    trace["unmatched_rcv_line_ids"] = sorted(rcv)
    return groups, trace


def price_check(inv_price: Decimal, rcv_price: Decimal, std: Standard) -> str:
    d = abs(inv_price - rcv_price)
    if d <= std.tol("price_exact"):
        return "pass"
    if rcv_price > 0 and d / rcv_price <= std.tol("price_pct") and d <= std.tol("price_abs"):
        return "within_tolerance"
    return "over_tolerance"
