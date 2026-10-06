"""Pipeline: normalize -> STEP 1 -> (gate) -> STEP 2 Oracle -> STEP 3 matching/rules -> recommend -> assemble.

Stateless.  Every rule is evaluated independently; only the Standard's gates skip rules
(E02 / missing lookup key / Oracle technical error / E05-E06-row cap) and skipped rules are
reported as ``not_evaluated`` with ``halted_by``.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from ..domain import rules as R
from ..domain.contracts import (AIServiceError, ExtractionResult, OracleInputRejected, OracleTechnicalError,
                                RuleOutcome)
from ..domain.matching import resolve
from ..domain.normalize import normalize
from ..domain.ports import EntityJudgeAI, LineMatcherAI, OracleRepository, QtyJudgeAI
from ..domain.recommendation import recommend
from ..domain.standard import Standard, load_standard
from .assembler import assemble
from .oracle_lookup import TAX_MODE, OracleSession, lookup_mode

log = logging.getLogger("system_a.pipeline")


@dataclass
class Services:
    oracle: OracleRepository
    line_ai: Optional[LineMatcherAI] = None
    qty_ai: Optional[QtyJudgeAI] = None
    entity_ai: Optional[EntityJudgeAI] = None
    models: dict | None = None


def _run(rule, ctx, errors) -> RuleOutcome:
    try:
        return rule(ctx)
    except AIServiceError as e:
        rid = rule.__name__[1:3]
        rid = f"V-{rid}"
        errors.append({"code": "AI_SERVICE_ERROR", "rule_id": rid, "detail": str(e)})
        return RuleOutcome(rid, "not_evaluated", detail="AI service error", halted_by="AI_SERVICE_ERROR")


def validate(ext: ExtractionResult, svc: Services, *, request: dict, std: Optional[Standard] = None) -> dict:
    std = std or load_standard()
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    errors: list[dict] = []
    doc, meta = normalize(ext, std)
    ctx = R.Ctx(doc=doc, std=std, entity_ai=svc.entity_ai, qty_ai=svc.qty_ai)
    outcomes: dict[str, RuleOutcome] = {}

    # STEP 1 — always every rule
    for rule in R.STEP1:
        o = _run(rule, ctx, errors)
        outcomes[o.rule_id] = o
    timings["step1_ms"] = (time.perf_counter() - t0) * 1000

    halted = None
    ora = std.policy["oracle"]
    mode = lookup_mode(std.policy)
    if outcomes["V-02"].result == "fail":                                  # Standard gate (X-02)
        halted = "V-02"
    elif mode == TAX_MODE:
        # AIVA-SYSA-ORA-01: the invoice number is the key; a Tax ID (OCR) or a PO (to resolve it) is enough
        if not (doc.ok("invoice_num") and (doc.ok("supplier_tax_id") or doc.ok("po_number"))):
            halted = "V-01"
    elif not (doc.ok("po_number") and doc.ok("invoice_num")):              # cannot form bind variables
        halted = "V-01"

    session = OracleSession(svc.oracle, ora["row_cap"], max_queries=ora.get("max_queries_per_round"),
                            lookup_cfg=ora.get("lookup"))
    if not halted:
        t1 = time.perf_counter()
        try:
            if mode == TAX_MODE:
                ctx.snapshot = session.lookup_tax_invoice(
                    doc.v("invoice_num"),
                    ocr_supplier_tax_id=doc.v("supplier_tax_id") if doc.ok("supplier_tax_id") else None,
                    po_number=doc.v("po_number") if doc.ok("po_number") else None)
            else:
                ctx.snapshot = session.lookup(doc.v("po_number"), doc.v("invoice_num"))
        except OracleInputRejected as e:
            # Standard §1.5: the key we would have bound is not whitelist-shaped -> no query at all.
            errors.append({"code": "ORACLE_INPUT_REJECTED", "detail": str(e), "queries": session.rejected})
            halted = "ORACLE_ERROR"
        except OracleTechnicalError as e:
            errors.append({"code": "ORACLE_TECHNICAL_ERROR", "detail": str(e)})
            halted = "ORACLE_ERROR"
        timings["oracle_ms"] = (time.perf_counter() - t1) * 1000
    if not halted:
        outcomes["V-04"] = _run(R.v04_receipt, ctx, errors)
        if ctx.snapshot.active:                       # V-05 needs ORG_ID from an active receipt line
            outcomes["V-05"] = _run(R.v05_customer, ctx, errors)
        else:
            outcomes["V-05"] = RuleOutcome("V-05", "not_evaluated", detail="ไม่มีใบรับ จึงไม่มี ORG_ID",
                                           halted_by="V-04")
        v04 = outcomes["V-04"]
        if v04.result != "pass":
            halted = "V-04"
    if not halted:
        t2 = time.perf_counter()
        try:
            ctx.groups, ctx.match_trace = resolve(doc, ctx.snapshot.active, std, svc.line_ai)
            for rule in R.STEP3:
                o = _run(rule, ctx, errors)
                outcomes[o.rule_id] = o
        except AIServiceError as e:
            errors.append({"code": "AI_SERVICE_ERROR", "rule_id": "V-07", "detail": str(e)})
            halted = "AI_SERVICE_ERROR"
        timings["step3_ms"] = (time.perf_counter() - t2) * 1000

    for rid in R.ALL_RULE_IDS:
        outcomes.setdefault(rid, RuleOutcome(rid, "not_evaluated", detail="ข้ามตาม gate", halted_by=halted))
    ordered = [outcomes[r] for r in R.ALL_RULE_IDS]
    rec = recommend(ordered, errors)
    timings["total_ms"] = (time.perf_counter() - t0) * 1000
    log.info("validated", extra={"correlation_id": request.get("correlation_id"),
                                 "validation_id": request.get("validation_id"), "recommendation": rec["value"]})
    return assemble(ext=ext, doc=doc, meta=meta, std=std, ctx=ctx, outcomes=ordered, recommendation=rec,
                    halted=halted, errors=errors, request=request, models=svc.models or {},
                    metrics={"duration_ms": {k: round(v, 2) for k, v in timings.items()},
                             "oracle_calls": session.calls, "oracle_rejected": session.rejected,
                             "oracle_queries": list(session.trace), "oracle_lookup_mode": mode,
                             "ai": ctx.ai_trace,
                             "ai_line_matcher_called": ctx.match_trace.get("ai_called", False)})
