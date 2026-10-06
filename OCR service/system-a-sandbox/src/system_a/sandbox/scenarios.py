"""Sandbox scenarios (Standard v6.6) — fixtures + the deterministic runner used by ``system_a.cli`` and pytest.

Every scenario is a *whole document*: a complete ``aiva.extraction/2.0`` payload plus the Oracle
dataset the sandbox repository answers with.  Nothing here talks to Oracle, LiteLLM or a DMS.

Privacy rule (task AIVA-SYSA-ORA-01 §2): no real supplier, Tax ID or internal URL is ever typed in
this file.  Buyer identity is read from ``config/standards/v6.6/buyer_entity.yaml`` at runtime, and
supplier Tax IDs are *generated* by :func:`tax_id_of` (synthetic 13-digit values with a valid
Thai check digit).

Runner:  ``python -m system_a.sandbox.scenarios [--hash|--golden|--force-mode MODE|--schema]``
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path
from typing import Optional

from ..application.orchestrator import validate
from ..container import Settings, build_services
from ..domain.contracts import ExtractionResult
from ..domain.standard import Standard, load_standard

# ORG_ID of a *confirmed* entity in Standard Table 4 — the identity values themselves come from config.
BUYER_ORG = 103
DOC_ID = "DOC-0001"
Q2 = Decimal("0.01")
GOLDEN = Path(__file__).resolve().parents[3] / "tests" / "golden_legacy_integrity.json"


# --------------------------------------------------------------------- synthetic identity helpers
def tax_id_of(base12: str) -> str:
    """Complete a synthetic 13-digit Thai Tax ID with a valid check digit (never real supplier data)."""
    d = re.sub(r"\D", "", base12)
    if len(d) != 12:
        raise ValueError("tax_id_of needs the first 12 digits")
    n = [int(c) for c in d]
    return d + str((11 - sum(n[i] * (13 - i) for i in range(12)) % 11) % 10)


SUP_TAX = tax_id_of("123456789012")          # synthetic supplier A
SUP_TAX_B = tax_id_of("987654321000")        # synthetic supplier B
OTHER_TAX = tax_id_of("111111111111")        # a *wrong* buyer Tax ID -> E07
PO_A, PO_B = "50000001", "50000002"
INV_A, INV_B = "SBX-INV-0001", "SBX-INV-0002"

_BUYER = load_standard().entities[BUYER_ORG]
BUYER_TAX, BUYER_NAME, BUYER_ADDR = _BUYER["tax_id"], _BUYER["name_th"], _BUYER["addr_th"]


# --------------------------------------------------------------------- extraction builders
def F(raw, *, conf: float = 0.99, agree: bool = True, page: int = 1,
      bbox: tuple = (0.10, 0.10, 0.22, 0.03), source: str = "consensus") -> dict:
    """One readable field/cell as the perception layer reports it."""
    return {"raw": str(raw), "confidence": conf, "agreement": agree, "region": {"page": page, "bbox": list(bbox)},
            "word_ids": [], "source": source, "null_reason": None}


def miss(null_reason: str = "NOT_PRESENT") -> dict:
    """One unreadable field/cell (``raw=None`` + the reason the extractor gave)."""
    return {"raw": None, "confidence": None, "agreement": True, "region": None, "word_ids": [],
            "source": "ocr", "null_reason": null_reason}


def L(no: int, item_code: str, desc: str, qty, uom: str, price, amount=None, **cells) -> dict:
    """One invoice line; ``amount`` defaults to qty x price (V-02 clean)."""
    amt = Decimal(str(qty)) * Decimal(str(price)) if amount is None else Decimal(str(amount))
    row = {"item_code": F(item_code), "description": F(desc), "qty": F(qty), "uom": F(uom),
           "unit_price": F(price), "amount": F(f"{amt:.2f}")}
    row.update(cells)
    return {"line_no": no, "region": {"page": 1, "bbox": [0.05, 0.30 + 0.07 * no, 0.90, 0.05]}, "cells": row}


def vat_of(sub: Decimal) -> Decimal:
    return (sub * Decimal("0.07")).quantize(Q2, rounding="ROUND_HALF_UP")


def doc(*, invoice: str = INV_A, po: str = PO_A, lines: tuple = (), fields: Optional[dict] = None,
        customer_tax: str = BUYER_TAX, customer_name: str = BUYER_NAME, customer_address: str = BUYER_ADDR,
        supplier_tax: str = SUP_TAX, sub: Optional[str] = None, vat: Optional[str] = None,
        grand: Optional[str] = None, sigs: Optional[dict] = None, pages_complete: bool = True) -> dict:
    """A full extraction payload.  Totals default to what the lines add up to (V-03 clean)."""
    lines = list(lines)
    if sub is None:
        sub = f"{sum((Decimal(str(l['cells']['amount']['raw'])) for l in lines), Decimal(0)):.2f}"
    if vat is None:
        vat = f"{vat_of(Decimal(sub)):.2f}"
    if grand is None:
        grand = f"{Decimal(sub) + Decimal(vat):.2f}"
    f = {"invoice_num": F(invoice), "po_number": F(po), "invoice_date": F("05/10/2026"), "currency": F("THB"),
         "customer_name": F(customer_name), "customer_address": F(customer_address),
         "customer_tax_id": F(customer_tax), "supplier_name": F("SYNTHETIC SUPPLIER CO LTD"),
         "supplier_tax_id": F(supplier_tax), "sub_total": F(sub), "vat": F(vat), "grand_total": F(grand)}
    f.update(fields or {})
    if sigs is None:
        sigs = {"receiver": {"present": True, "confidence": 0.95, "kind": "signature",
                             "region": {"page": 1, "bbox": [0.60, 0.80, 0.25, 0.10]}},
                "deliverer": {"present": True, "confidence": 0.93, "kind": "stamp",
                              "region": {"page": 1, "bbox": [0.60, 0.68, 0.25, 0.10]}}}
    return {"contract": "aiva.extraction/2.0", "package_id": "PKG-SBX", "dms_doc_id": "DMS-SBX",
            "file_sha256": "sha256:sandbox", "pages": [{"page_no": 1, "width_pt": 595.0, "height_pt": 842.0,
                                                       "rotation": 0, "render_dpi": 300, "page_type": "INVOICE",
                                                       "type_confidence": 0.99, "ocr_quality": 0.95}],
            "documents": [{"document_id": DOC_ID, "document_type": "INVOICE", "pages": [1], "confidence": 0.99}],
            "invoice_document_id": DOC_ID, "pages_complete": pages_complete, "fields": f, "lines": lines,
            "signatures": sigs, "extractor": {"ocr": "sandbox", "vlm": "sandbox"}}


# --------------------------------------------------------------------- Oracle dataset builders
def R(po: str, rcv: str, line: int, item: str, qty, uom: str, price, amount=None, *,
      org: int = BUYER_ORG, receiver: str = "SMITH J.", **extra) -> dict:
    """One receipt line as Oracle returns it (column names follow the registered SQL)."""
    amt = Decimal(str(qty)) * Decimal(str(price)) if amount is None else Decimal(str(amount))
    row = {"ORG_ID": org, "RECEIPT_NUM": rcv, "RECEIVER": receiver, "LINE": line, "ITEM": item,
           "QTY": str(qty), "UOM": uom, "UNIT_PRICE": str(price), "LINE_AMOUNT": f"{amt:.2f}", "PO_NUM": po}
    row.update({k.upper(): v for k, v in extra.items()})
    return row


def E(po: str, invoice: str, rows: list, tax: Optional[str] = SUP_TAX) -> dict:
    return {"po_number": po, "invoice_num": invoice, "supplier_tax_id": tax, "rows": rows}


def DS(entries: list, po_supplier: Optional[dict] = None) -> dict:
    return {"receipts": list(entries), "po_supplier": dict(po_supplier or {})}


# --------------------------------------------------------------------- scenario model
@dataclass(frozen=True)
class Scenario:
    sid: str
    title: str
    extraction: dict
    oracle: dict
    expect: str                                  # recommendation value
    codes: tuple = ()                            # exception codes, order-insensitive
    oracle_down: bool = False
    ai: str = "sim"                              # sim | down | faulty_qty
    mode: str = "legacy_po_invoice"              # lookup mode this scenario documents
    flags: dict = field(default_factory=dict)    # validation flags flipped for this scenario only
    queries: Optional[int] = None                # expected Oracle queries per round (documentation)
    locked: bool = False                         # True: --force-mode / SYSTEM_A_LOOKUP_MODE never applies
    checks: dict = field(default_factory=dict)   # extra assertions (lookup_path, matched_on_column, ...)

    @property
    def extraction_model(self) -> ExtractionResult:
        return ExtractionResult.model_validate(self.extraction)


def forced_mode() -> Optional[str]:
    """``SYSTEM_A_LOOKUP_MODE`` / ``--force-mode``: overrides every scenario's pinned mode."""
    return os.getenv("SYSTEM_A_LOOKUP_MODE") or os.getenv("SYSTEM_A_FORCE_MODE") or None


def effective_mode(sc: Scenario) -> str:
    return sc.mode if sc.locked else (forced_mode() or sc.mode)


def standard_for(sc: Scenario) -> Standard:
    """The shipped Standard with this scenario's lookup mode + validation flags applied.

    The flags are never written to ``policy.yaml`` (they default to false there); a scenario that
    needs them flips them on a derived copy only, pending approval by the Standard owner.
    """
    std = load_standard()
    policy = copy.deepcopy(std.policy)
    val = policy.setdefault("validation", {})
    val.update(sc.flags)
    lookup = policy.setdefault("oracle", {}).setdefault("lookup", {})
    lookup["mode"] = effective_mode(sc)
    return replace(std, policy=policy)


def run_scenario(sc: Scenario, settings: Optional[Settings] = None) -> tuple[dict, object]:
    svc = build_services(settings or Settings(mode="sandbox"), oracle_dataset=sc.oracle,
                         oracle_down=sc.oracle_down, ai=sc.ai)
    res = validate(sc.extraction_model, svc, std=standard_for(sc),
                   request={"validation_id": f"SBX-{sc.sid}", "correlation_id": f"corr-{sc.sid}",
                            "idempotency_key": None, "document_revision": 1, "validation_round": 1})
    return res, svc


def outcome_ok(sc: Scenario, res: dict) -> bool:
    rec = res["recommendation"]
    return rec["value"] == sc.expect and set(sc.codes) == set(rec["exception_codes"])


def integrity_hash(res: dict) -> str:
    return res["integrity"]["payload_sha256"]


# ============================================================================= S01–S19 (legacy mode)
# One good document per rule outcome: these pin the behaviour RCV-V01 / RCV-V02 must never lose.
BRACKET, GASKET = "BRACKET ASSY", "GASKET PLATE"


def s01() -> Scenario:
    """clean single-PO document, everything matches -> AUTO_PASS."""
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    return Scenario("S01", "เอกสารถูกต้อง 1 PO 1 ใบรับ", doc(lines=lines),
                    DS([E(PO_A, INV_A, [R(PO_A, "RCV-0000012345", 1, BRACKET, 10, "EA", "100.00")])],
                       {PO_A: SUP_TAX}), "AUTO_PASS", (), queries=1)


def s02() -> Scenario:
    """one invoice line against two receipt lots (1:N) + 0.01 rounding (Low) -> AUTO_PASS with E04."""
    lines = (L(1, "ITM-1001", BRACKET, 20, "EA", "100.00"),)
    rows = [R(PO_A, "RCV-0000012345", 1, BRACKET, 10, "EA", "100.00"),
            R(PO_A, "RCV-0000012345", 2, BRACKET, 10, "EA", "100.00")]
    return Scenario("S02", "1:N สองล็อต + เศษปัดยอดรวม 0.01 (Low)",
                    doc(lines=lines, sub="2000.01", vat="140.00", grand="2140.01"),
                    DS([E(PO_A, INV_A, rows)], {PO_A: SUP_TAX}), "AUTO_PASS", ("E04",), queries=1)


def s03() -> Scenario:
    """qty x price != amount -> E02, gate stops before Oracle (0 queries)."""
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00", amount="1100.00"),)
    return Scenario("S03", "คณิตศาสตร์บรรทัดผิด (gate V-02 ไม่ query)",
                    doc(lines=lines, sub="1100.00", vat="77.00", grand="1177.00"),
                    DS([E(PO_A, INV_A, [R(PO_A, "RCV-0000012345", 1, BRACKET, 10, "EA", "100.00")])],
                       {PO_A: SUP_TAX}), "HOLD", ("E02",), queries=0)


def s04() -> Scenario:
    """customer_tax_id unreadable -> E01 (Medium) and V-05 cannot run."""
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    return Scenario("S04", "Tax ID ลูกค้าอ่านไม่ได้ (V-05 ถูกข้าม)",
                    doc(lines=lines, fields={"customer_tax_id": miss()}),
                    DS([E(PO_A, INV_A, [R(PO_A, "RCV-0000012345", 1, BRACKET, 10, "EA", "100.00")])],
                       {PO_A: SUP_TAX}), "REVIEW", ("E01",), queries=1)


def s05() -> Scenario:
    """PO number is not 8 digits -> lookup key cannot be formed, no query at all."""
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    return Scenario("S05", "เลขที่ PO อ่านไม่ได้รูปแบบ (halt V-01, 0 queries)",
                    doc(lines=lines, fields={"po_number": F("PO-AB/CD", conf=0.60)}),
                    DS([E(PO_A, INV_A, [R(PO_A, "RCV-0000012345", 1, BRACKET, 10, "EA", "100.00")])],
                       {PO_A: SUP_TAX}), "REVIEW", ("E01",), queries=0)


def s06() -> Scenario:
    """no receipt in Oracle for PO + Invoice -> E05 (three queries: V01, PO-SUPPLIER, V02)."""
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    return Scenario("S06", "ไม่พบใบรับ (E05 ผ่าน fallback ครบ 3 queries)", doc(lines=lines),
                    DS([E(PO_B, INV_B, [R(PO_B, "RCV-0000099999", 1, BRACKET, 10, "EA", "100.00")])],
                       {PO_A: SUP_TAX}), "HOLD", ("E05",), queries=3)


def s07() -> Scenario:
    """RCV-V01 misses, RCV-V02 (PO -> supplier tax -> tax + invoice) finds it -> AUTO_PASS."""
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    return Scenario("S07", "fallback RCV-V02 พบใบรับ", doc(lines=lines, invoice=INV_B),
                    DS([E(PO_B, INV_B, [R(PO_B, "RCV-0000012346", 1, BRACKET, 10, "EA", "100.00")])],
                       {PO_A: SUP_TAX}), "AUTO_PASS", (), queries=3)


def s08() -> Scenario:
    """two receipts for one invoice -> E06 while multi_po_receipts is off."""
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    rows = [R(PO_A, "RCV-0000012347", 1, BRACKET, 5, "EA", "100.00"),
            R(PO_A, "RCV-0000012348", 1, BRACKET, 5, "EA", "100.00")]
    return Scenario("S08", "หลายใบรับ + flag ปิด -> E06 (HOLD)", doc(lines=lines),
                    DS([E(PO_A, INV_A, rows)], {PO_A: SUP_TAX}), "HOLD", ("E06",), queries=1)


def s09() -> Scenario:
    """Oracle unreachable -> SYSTEM_ERROR, never E05."""
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    return Scenario("S09", "Oracle ดาวน์ -> SYSTEM_ERROR", doc(lines=lines),
                    DS([E(PO_A, INV_A, [R(PO_A, "RCV-0000012345", 1, BRACKET, 10, "EA", "100.00")])],
                       {PO_A: SUP_TAX}), "SYSTEM_ERROR", (), oracle_down=True, queries=1)


def s10() -> Scenario:
    """buyer Tax ID on the invoice is not the one registered for ORG_ID -> E07 High."""
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    return Scenario("S10", "Tax ID ลูกค้าไม่ตรง ORG_ID (E07 High)",
                    doc(lines=lines, customer_tax=OTHER_TAX),
                    DS([E(PO_A, INV_A, [R(PO_A, "RCV-0000012345", 1, BRACKET, 10, "EA", "100.00")])],
                       {PO_A: SUP_TAX}), "HOLD", ("E07",), queries=1)


def s11() -> Scenario:
    """name is not registered and the AI is not confident -> MANUAL_REVIEW."""
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    return Scenario("S11", "ชื่อลูกค้า AI ไม่มั่นใจ -> MANUAL_REVIEW",
                    doc(lines=lines, customer_name="APICO HITECH PARTS"),
                    DS([E(PO_A, INV_A, [R(PO_A, "RCV-0000012345", 1, BRACKET, 10, "EA", "100.00")])],
                       {PO_A: SUP_TAX}), "MANUAL_REVIEW", (), queries=1)


def s12() -> Scenario:
    """invoice price 10% above the PO price -> E09 + E03 -> HOLD."""
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "110.00"),)
    return Scenario("S12", "ราคาต่างเกินกรอบ (E09) และยอดรวมต่าง (E03)", doc(lines=lines),
                    DS([E(PO_A, INV_A, [R(PO_A, "RCV-0000012345", 1, BRACKET, 10, "EA", "100.00")])],
                       {PO_A: SUP_TAX}), "HOLD", ("E03", "E09"), queries=1)


def s13() -> Scenario:
    """UOM from another synonym group -> E10 and V-08 cannot compare quantities (manual_review).

    V-07 reports E10 only: the UOM branch `continue`s before the M4/E11 note, so a line whose unit of
    measure cannot be compared never also carries E11 (measured, not assumed).
    """
    lines = (L(1, "ITM-1001", BRACKET, 10, "KG", "100.00"),)
    return Scenario("S13", "หน่วยนับต่างกลุ่ม เทียบจำนวนไม่ได้", doc(lines=lines),
                    DS([E(PO_A, INV_A, [R(PO_A, "RCV-0000012345", 1, BRACKET, 10, "EA", "100.00")])],
                       {PO_A: SUP_TAX}), "MANUAL_REVIEW", ("E10",), queries=1)


def s14() -> Scenario:
    """price is not unique inside the receipt, so M1 cannot decide -> the AI matches by description.

    M4 (description only) always carries E11 (Medium): quantities and totals are fine, a person just
    confirms the pairing.
    """
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"), L(2, "ITM-2002", GASKET, 4, "EA", "100.00"))
    rows = [R(PO_A, "RCV-0000012349", 1, BRACKET, 10, "EA", "100.00"),
            R(PO_A, "RCV-0000012349", 2, GASKET, 4, "EA", "100.00")]
    return Scenario("S14", "ราคาไม่ unique ในใบรับ -> จับคู่ด้วยคำบรรยาย (E11)", doc(lines=lines),
                    DS([E(PO_A, INV_A, rows)], {PO_A: SUP_TAX}), "REVIEW", ("E11",), queries=1)


def s15() -> Scenario:
    """an invoice line with no receipt counterpart -> E13 (and the total differs, E03)."""
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"), L(2, "ITM-2002", GASKET, 5, "EA", "50.00"))
    return Scenario("S15", "มีบรรทัดที่ไม่อยู่ในใบรับ (E13)", doc(lines=lines),
                    DS([E(PO_A, INV_A, [R(PO_A, "RCV-0000012345", 1, BRACKET, 10, "EA", "100.00")])],
                       {PO_A: SUP_TAX}), "HOLD", ("E03", "E13"), queries=1)


def s16() -> Scenario:
    """invoice quantity above the receipted quantity -> E14 + E03 -> HOLD."""
    lines = (L(1, "ITM-1001", BRACKET, 12, "EA", "100.00"),)
    return Scenario("S16", "วางบิลเกินใบรับ (E14)", doc(lines=lines),
                    DS([E(PO_A, INV_A, [R(PO_A, "RCV-0000012345", 1, BRACKET, 10, "EA", "100.00")])],
                       {PO_A: SUP_TAX}), "HOLD", ("E03", "E14"), queries=1)


def s17() -> Scenario:
    """price differs within tolerance (E12) and quantity is below the receipted qty (E15)."""
    lines = (L(1, "ITM-1001", BRACKET, 20, "EA", "100.50"),)
    return Scenario("S17", "ราคาต่างในกรอบ (E12) + จำนวนน้อยกว่าใบรับ (E15)", doc(lines=lines),
                    DS([E(PO_A, INV_A, [R(PO_A, "RCV-0000012345", 1, BRACKET, 20.10, "EA", "100.00")])],
                       {PO_A: SUP_TAX}), "REVIEW", ("E12", "E15"), queries=1)


def s18() -> Scenario:
    """receiver signature absent -> E08 High -> HOLD."""
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    sigs = {"receiver": {"present": False, "confidence": 0.95, "kind": "signature", "region": None},
            "deliverer": {"present": True, "confidence": 0.93, "kind": "stamp", "region": None}}
    return Scenario("S18", "ไม่พบลายเซ็นผู้รับของ (E08)", doc(lines=lines, sigs=sigs),
                    DS([E(PO_A, INV_A, [R(PO_A, "RCV-0000012345", 1, BRACKET, 10, "EA", "100.00")])],
                       {PO_A: SUP_TAX}), "HOLD", ("E08",), queries=1)


def s19() -> Scenario:
    """AI outage on a match that logic cannot decide -> SYSTEM_ERROR (not E05/E13)."""
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    rows = [R(PO_A, "RCV-0000012349", 1, BRACKET, 5, "EA", "100.00"),
            R(PO_A, "RCV-0000012349", 2, BRACKET, 5, "EA", "100.00")]
    return Scenario("S19", "AI ดาวน์ระหว่างจับคู่บรรทัด -> SYSTEM_ERROR", doc(lines=lines),
                    DS([E(PO_A, INV_A, rows)], {PO_A: SUP_TAX}), "SYSTEM_ERROR", (), ai="down", queries=1)


LEGACY = [s01(), s02(), s03(), s04(), s05(), s06(), s07(), s08(), s09(), s10(), s11(), s12(), s13(),
          s14(), s15(), s16(), s17(), s18(), s19()]


def all_scenarios() -> list[Scenario]:
    """S01-S19 (legacy contract) + S20-S27 (Tax ID + Invoice), when implemented."""
    try:
        from .multi_po import MULTI_PO           # noqa: WPS433 - optional until Phase 4
    except ImportError:
        return list(LEGACY)
    return list(LEGACY) + list(MULTI_PO)


# ============================================================================= runner
def main(argv=None) -> int:
    ap = argparse.ArgumentParser("system_a.sandbox.scenarios")
    ap.add_argument("--show", help="print the full result JSON of one scenario")
    ap.add_argument("--hash", action="store_true", help="print sid -> integrity.payload_sha256")
    ap.add_argument("--write-golden", action="store_true", help=f"pin hashes into {GOLDEN}")
    ap.add_argument("--golden", action="store_true", help=f"compare hashes against {GOLDEN}")
    ap.add_argument("--force-mode", help="run every scenario in this lookup mode")
    ap.add_argument("--schema", action="store_true", help="validate every result against result-3.0.schema.json")
    a = ap.parse_args(argv)
    if a.force_mode:
        os.environ["SYSTEM_A_FORCE_MODE"] = a.force_mode
    rows, bad, drift, schema_bad = [], 0, [], []
    golden = json.loads(GOLDEN.read_text(encoding="utf-8")) if (a.golden and GOLDEN.exists()) else {}
    validator = None
    if a.schema:
        import jsonschema
        schema = json.loads((Path(__file__).resolve().parents[3] / "schemas" /
                             "result-3.0.schema.json").read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
    got: dict[str, str] = {}
    for sc in all_scenarios():
        res, _ = run_scenario(sc)
        got[sc.sid] = integrity_hash(res)
        if a.show == sc.sid:
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return 0
        if validator is not None:
            err = next(iter(validator.iter_errors(res)), None)
            if err is not None:
                schema_bad.append(f"{sc.sid}: {err.message[:120]}")
        ok = outcome_ok(sc, res)
        bad += not ok
        rows.append((sc.sid, "OK " if ok else "FAIL", effective_mode(sc), res["recommendation"]["value"],
                     ",".join(res["recommendation"]["exception_codes"]) or "-",
                     res["recommendation"].get("halted_by") or "-", res["metrics"]["oracle_calls"]))
    for w, head in zip((4, 4, 18, 14, 14, 16, 7), ("ID", "ST", "Mode", "Recommendation", "Codes", "Halted", "Oracle")):
        print(f"{head:<{w}}", end=" ")
    print("Scenario")
    for r in rows:
        print(" ".join(f"{str(v):<{w}}" for v, w in zip(r, (4, 4, 18, 14, 14, 16, 7))),
              next(s.title for s in all_scenarios() if s.sid == r[0]))
    if a.golden:
        for sid, h in got.items():
            if sid in golden and golden[sid] != h:
                drift.append(sid)
        print(f"\ngolden gate: {len([k for k in golden if k in got]) - len(drift)}/{len(golden)} unchanged"
              + (f", DRIFT {drift}" if drift else ""))
    if a.write_golden or a.hash:
        print(json.dumps(dict(sorted(got.items())), indent=2))
    if a.write_golden:
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(dict(sorted(got.items())), indent=2) + "\n", encoding="utf-8")
        print(f"pinned {len(got)} hashes -> {GOLDEN}")
    if a.schema:
        print("schema: " + ("all results valid" if not schema_bad else "INVALID " + str(schema_bad)))
    print(f"\n{len(rows) - bad}/{len(rows)} scenarios match expectation")
    return 1 if (bad or drift or schema_bad) else 0


if __name__ == "__main__":
    sys.exit(main())
