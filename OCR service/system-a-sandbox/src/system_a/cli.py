"""CLI.

  python -m system_a.cli scenarios                 # run all sandbox scenarios, print table
  python -m system_a.cli scenarios --show S05      # print full result JSON of one scenario
  python -m system_a.cli export                    # write sandbox_data/*.json (API demo inputs)
  python -m system_a.cli serve                     # start API on :8080 (sandbox)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .application.orchestrator import validate
from .container import Settings, build_services
from .domain.contracts import ExtractionResult
from .sandbox.scenarios import all_scenarios, standard_for

ROOT = Path(__file__).resolve().parents[2]


def run_scenario(sc, settings: Settings | None = None) -> tuple[dict, object]:
    svc = build_services(settings or Settings(mode="sandbox"), oracle_dataset=sc.oracle, oracle_down=sc.oracle_down,
                         ai=sc.ai)
    res = validate(ExtractionResult.model_validate(sc.extraction), svc, std=standard_for(sc),
                   request={"validation_id": f"SBX-{sc.sid}", "correlation_id": f"corr-{sc.sid}",
                            "idempotency_key": None, "document_revision": 1, "validation_round": 1})
    return res, svc


def cmd_scenarios(a):
    rows, bad = [], 0
    for sc in all_scenarios():
        if a.show and sc.sid != a.show:
            continue
        res, svc = run_scenario(sc)
        if a.show:
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return
        rec = res["recommendation"]
        ok = rec["value"] == sc.expect and set(sc.codes) == set(rec["exception_codes"])
        bad += not ok
        rows.append((sc.sid, "OK" if ok else "FAIL", rec["value"], ",".join(rec["exception_codes"]) or "-",
                     rec.get("halted_by") or "-", res["metrics"]["oracle_calls"], sc.title))
    w = [4, 4, 14, 16, 14, 7]
    print(f"{'ID':<4} {'':4} {'Recommendation':<14} {'Codes':<16} {'Halted':<14} {'Oracle':<7} Scenario")
    print("-" * 110)
    for r in rows:
        print(" ".join(f"{str(v):<{w[i]}}" for i, v in enumerate(r[:6])), r[6])
    print(f"\n{len(rows) - bad}/{len(rows)} scenarios match expectation")
    sys.exit(1 if bad else 0)


def cmd_export(_a):
    out = ROOT / "sandbox_data"
    out.mkdir(exist_ok=True)
    merged = {"receipts": [], "po_supplier": {}}
    for sc in all_scenarios():
        (out / f"{sc.sid}_extraction.json").write_text(
            json.dumps({"extraction": sc.extraction, "portal_refs": {"document_revision": 1, "validation_round": 1}},
                       ensure_ascii=False, indent=2), encoding="utf-8")
    sc0 = all_scenarios()[0]
    merged["receipts"] += sc0.oracle["receipts"]
    merged["po_supplier"].update(sc0.oracle["po_supplier"])
    (out / "oracle_dataset.json").write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"exported to {out}")


def cmd_serve(a):
    import uvicorn
    uvicorn.run("system_a.api.app:default_app", factory=True, host=a.host, port=a.port)


def main(argv=None):
    p = argparse.ArgumentParser("system-a")
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("scenarios"); s.add_argument("--show"); s.set_defaults(fn=cmd_scenarios)
    sp.add_parser("export").set_defaults(fn=cmd_export)
    s = sp.add_parser("serve"); s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8080)
    s.set_defaults(fn=cmd_serve)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
