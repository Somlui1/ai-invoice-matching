"""Replay saved System A results (extraction + Oracle snapshot) through a code tree.
usage: python replay.py <src_root> <results_dir> <out.json>"""
import sys, json, glob, os, re
root, rdir, out = sys.argv[1:4]
sys.path.insert(0, root)
from decimal import Decimal
from system_a.domain.contracts import ExtractionResult, ReceiptRow
from system_a.application.orchestrator import Services, validate
from system_a.adapters.llm.simulators import SimLineMatcher, SimQtyJudge, SimEntityJudge
from system_a.domain.standard import load_standard

class Repo:
    def __init__(s, rows, path): s.rows, s.path = rows, path
    def _r(s, ok): return list(s.rows) if ok else []
    def rcv_v01(s, po, inv): return s._r(s.path == "RCV-V01")
    def supplier_tax_by_po(s, po): return None
    def rcv_v02(s, t, inv): return s._r(s.path == "RCV-V02")
    def receipts_by_tax_invoice(s, t, v): return s._r(s.path == "TAX-INV")
    def receipts_by_po_list(s, pos): return s._r(s.path == "PO-LIST")

ROWF = set(ReceiptRow.__dataclass_fields__)
def row(d):
    k = {a: b for a, b in d.items() if a in ROWF}
    for n in ("qty", "unit_price", "line_amount", "qty_billed"):
        if n in k and k[n] is not None: k[n] = Decimal(str(k[n]))
    k.setdefault("extra", {})
    return ReceiptRow(**k)

def rf(f, el):
    raw = f.get("raw_value")
    reg = {"page": el["page_no"], "bbox": el["bbox"]} if el and el.get("bbox") else None
    nr = f.get("null_reason") if raw is None else None
    return {"raw": raw, "confidence": f.get("confidence", el.get("confidence") if el else None),
            "agreement": (el or {}).get("agreement", True) if (el or {}).get("agreement") is not None else True,
            "region": reg, "source": "consensus", "null_reason": nr}

res = {}
for p in sorted(glob.glob(os.path.join(rdir, "DMS-*_result.json"))):
    d = json.load(open(p, encoding="utf-8"))
    els = {e["element_id"]: e for e in d["ocr"]["elements"]}
    ex = d["extraction"]
    fields = {k: rf(v, els.get(v["element_id"])) for k, v in ex["fields"].items()}
    lines = []
    for l in ex["lines"]:
        cells = {k: rf(c, els.get(f"{l['element_id']}-{k}")) for k, c in l["cells"].items()}
        lines.append({"line_no": l["line_no"], "cells": cells})
    sig = {k: {kk: v.get(kk) for kk in ("present", "confidence", "kind", "region")}
           for k, v in ex["signatures"].items() if k in ("receiver", "deliverer")}
    pk = d["package"]
    e = ExtractionResult.model_validate({"package_id": pk["package_id"], "dms_doc_id": pk["dms_doc_id"],
        "file_sha256": pk["file_sha256"], "pages": d["pages"], "documents": d["documents"],
        "invoice_document_id": ex["invoice_document_id"], "pages_complete": pk["pages_complete"],
        "fields": fields, "lines": lines, "signatures": sig,
        "regions": [{"region_id": x["element_id"], "page": x["page_no"], "kind": x.get("region_kind") or "stamp",
                     "text": x.get("raw_value"), "confidence": x.get("confidence"), "bbox": x["bbox"]}
                    for x in d["ocr"]["elements"] if (x.get("region_kind") == "stamp" or x["element_type"] == "stamp") and x.get("bbox")]})
    snap = d.get("oracle_snapshot") or {}
    rows = [row(x) for x in snap.get("receipt_lines") or []]
    svc = Services(Repo(rows, snap.get("lookup_path")), SimLineMatcher(), SimQtyJudge(), SimEntityJudge())
    r = validate(e, svc, request={"validation_id": "replay", "correlation_id": "replay", "idempotency_key": None, "document_revision": 1, "validation_round": 1})
    res[pk["dms_doc_id"]] = {"rec": r["recommendation"]["value"], "codes": r["recommendation"]["exception_codes"],
        "reasons": r["recommendation"]["reasons"], "had_oracle": bool(snap), "orig": d["recommendation"]["value"],
        "corroborated": next((x["data"].get("corroborated") for x in r["rule_results"] if x["rule_id"] == "V-01"), None),
        "e01": [x["message_th"] for x in r["evidence"] if x["exception_code"] == "E01"]}
json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
from collections import Counter
print(Counter(v["rec"] for v in res.values()))
