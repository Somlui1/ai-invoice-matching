"""Recommendation — pure function (Table 8 order, as in the original ``decide()``).

Only five values are allowed.  Never a final approval / AP / duplicate status.
"""
from __future__ import annotations

RANK = {"Low": 1, "Medium": 2, "High": 3}
ALLOWED = ("AUTO_PASS", "REVIEW", "HOLD", "MANUAL_REVIEW", "SYSTEM_ERROR")


def recommend(outcomes, system_errors: list) -> dict:
    findings = [f for o in outcomes for f in o.findings]
    sev = max((RANK[f.severity] for f in findings), default=0)
    reasons = sorted({f"{f.code}:{f.severity}" for f in findings})
    if system_errors:
        value = "SYSTEM_ERROR"
        reasons = [e["code"] for e in system_errors] + reasons
    elif any(o.result == "manual_review" for o in outcomes):
        value = "MANUAL_REVIEW"
        reasons = [f"{o.rule_id}:manual_review" for o in outcomes if o.result == "manual_review"] + reasons
    elif sev == 3:
        value = "HOLD"
    elif sev == 2:
        value = "REVIEW"
    elif any(o.result == "not_evaluated" and not o.halted_by for o in outcomes):
        value = "MANUAL_REVIEW"          # not evaluated is never a pass
        reasons.append("not_evaluated_without_cause")
    else:
        value = "AUTO_PASS"
    assert value in ALLOWED
    return {"value": value, "max_severity": {0: "None", 1: "Low", 2: "Medium", 3: "High"}[sev],
            "exception_codes": sorted({f.code for f in findings}), "reasons": reasons}
