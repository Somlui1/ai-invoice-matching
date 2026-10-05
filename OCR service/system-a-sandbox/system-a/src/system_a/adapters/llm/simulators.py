"""Deterministic AI simulators for the sandbox.

They implement the SAME prompt contracts (config/prompts/*.md) with transparent heuristics, so the
whole pipeline runs without GB300.  They are test doubles, not production logic.
Swap them for ``ai_services.LiteLLM*`` by setting ``SYSTEM_A_AI_MODE=litellm``.
"""
from __future__ import annotations

import re
from decimal import Decimal

from ...domain.normalize import addr_key, norm_name, thai_to_arabic


def _tokens(s: str) -> set[str]:
    return {w for w in re.split(r"[^0-9a-zA-Z\u0E00-\u0E7F]+", (s or "").upper()) if len(w) > 1}


def _sim(a: str, b: str) -> float:
    x, y = _tokens(a), _tokens(b)
    return len(x & y) / max(1, len(x | y))


class SimLineMatcher:
    """M3: same item, quantities/amounts decide (1:N lots or N:1 split) · M4: description only ·
    M5: 1:1 by description with a different price.  Unmatched when similarity < 0.34."""

    def propose(self, invoice_lines, receipt_lines):
        groups, unmatched, used_r, used_i = [], [], set(), set()
        by_item: dict[str, list] = {}
        for r in receipt_lines:
            by_item.setdefault(r["item"].upper(), []).append(r)
        # best receipt item for each invoice line
        best = {}
        for l in invoice_lines:
            text = f"{l.get('item_code') or ''} {l.get('description') or ''}"
            scored = sorted(((_sim(text, it), it) for it in by_item), reverse=True)
            if scored and scored[0][0] >= 0.34:
                best[l["invoice_line_no"]] = (scored[0][1], scored[0][0])
        for item, rlines in by_item.items():
            inv = [l for l in invoice_lines if best.get(l["invoice_line_no"], (None,))[0] == item]
            if not inv:
                continue
            rids = [r["rcv_line_id"] for r in rlines]
            same_price = any(Decimal(l["unit_price"] or "0") == Decimal(r["unit_price"]) for l in inv for r in rlines)
            if len(inv) == 1 and len(rids) >= 1:
                lvl = "M3" if (len(rids) > 1 and same_price) else ("M5" if not same_price else "M4")
                groups.append({"invoice_line_nos": [inv[0]["invoice_line_no"]], "rcv_line_ids": rids, "level": lvl,
                               "confidence": {"M3": 0.9, "M4": 0.85, "M5": 0.8}[lvl],
                               "rationale": f"สินค้าเดียวกัน '{item}' ({len(rids)} ล็อต)"})
            elif len(rids) == 1:
                groups.append({"invoice_line_nos": [l["invoice_line_no"] for l in inv], "rcv_line_ids": rids,
                               "level": "M3", "confidence": 0.9,
                               "rationale": f"ใบแจ้งหนี้แยก {len(inv)} บรรทัด ของสินค้า '{item}' ในใบรับบรรทัดเดียว"})
            else:
                continue
            used_i |= {l["invoice_line_no"] for l in inv}
            used_r |= set(rids)
        for l in invoice_lines:
            if l["invoice_line_no"] not in used_i:
                unmatched.append({"invoice_line_no": l["invoice_line_no"], "reason": "ไม่พบสินค้าที่ตรงในใบรับ"})
        return {"groups": groups, "unmatched": unmatched}


class SimQtyJudge:
    """Follows v08_qty.md sections B-D literally, using COMPUTED_FACTS only."""

    def __init__(self, *, faulty: bool = False):
        self.faulty = faulty          # test double that 'forgets' N:1 rule (sums invoice lines)

    def judge(self, payload):
        facts, out = payload["COMPUTED_FACTS"], []
        inv = {l["invoice_line_no"]: l for l in payload["INVOICE_LINES"]}
        for g in payload["MATCH_GROUPS"]:
            if g["relation"] == "UNMATCHED":
                for n in g["invoice_line_nos"]:
                    out.append(self._lr(n, g, "not_evaluated", None, None, None, "V-07 ระบุบรรทัดใบรับไม่ได้", inv))
                continue
            f = facts[g["group_id"]]
            for p in f["per_line"]:
                n = p["invoice_line_no"]
                if not f["uom_comparable"]:
                    out.append(self._lr(n, g, "manual_review", None, p, None, "หน่วยนับต่างกลุ่ม เทียบจำนวนไม่ได้", inv))
                    continue
                if p["qty_diff"] is None:
                    out.append(self._lr(n, g, "manual_review", None, p, None, "qty เป็น null", inv))
                    continue
                d = Decimal(p["qty_diff"])
                if self.faulty and g["relation"] == "N:1":
                    d = sum(Decimal(inv[x]["qty_inv"]) for x in g["invoice_line_nos"]) - Decimal(p["qty_rcv_compared"])
                code = None if d == 0 else ("E14" if d > 0 else "E15")
                out.append(self._lr(n, g, "pass" if d == 0 else "fail", code, p, d, "", inv))
        res = [x["result"] for x in out]
        rule = ("not_evaluated" if res and all(r == "not_evaluated" for r in res) else
                "fail" if "fail" in res else "manual_review" if "manual_review" in res else "pass")
        return {"rule_id": "V-08", "rule_result": rule, "line_results": out,
                "self_check": {"all_lines_covered": True, "facts_consistent": not self.faulty, "codes_valid": True}}

    @staticmethod
    def _lr(n, g, result, code, p, d, reason, inv):
        desc = inv[n]["description"]
        msg = None
        if code:
            word = "เกินใบรับ" if code == "E14" else "น้อยกว่าใบรับ"
            msg = f"บรรทัดที่ {n} (Invoice: {desc}): จำนวนวางบิล{word} (Inv: {inv[n]['qty_inv']}, Rcv: {p['qty_rcv_compared']})"
        return {"invoice_line_no": n, "group_id": g["group_id"], "relation": g["relation"],
                "qty_inv": inv[n]["qty_inv"], "qty_rcv_compared": p["qty_rcv_compared"] if p else None,
                "qty_diff": str(d) if d is not None else (p["qty_diff"] if p else None), "result": result,
                "code": code, "severity": {"E14": "High", "E15": "Medium"}.get(code), "message": msg,
                "reason": reason or "ตาม COMPUTED_FACTS"}


class SimEntityJudge:
    GENERIC = {"HEAD", "OFFICE", "สำนักงานใหญ่", "THAILAND", "BRANCH", "THE"}

    @classmethod
    def _score(cls, inv: str, cand: str) -> float:
        x, y = _tokens(norm_name(inv)), _tokens(norm_name(cand))
        if y and y <= x and (x - y) <= cls.GENERIC:       # candidate fully present, extras are generic words
            return 0.9
        return len(x & y) / max(1, len(x | y))

    def name_equivalent(self, invoice_name, candidates):
        best = max(((self._score(invoice_name, v), k) for k, v in candidates.items()), default=(0, None))
        score, key = best
        return {"equivalent": score >= 0.75, "matched_candidate": key, "confidence": round(0.6 + 0.4 * score, 2),
                "reason": f"token similarity {score:.2f}"}

    def parse_address(self, address):
        house, post = addr_key(thai_to_arabic(address))
        return {"house_no": house, "postal_code": post, "confidence": 0.95 if house and post else 0.5}


class FailingAI:
    """Simulates GB300/LiteLLM outage."""

    def __getattr__(self, _):
        from ...domain.contracts import AIServiceError

        def boom(*a, **k):
            raise AIServiceError("AITransportError: ReadTimeout (simulated)")
        return boom
