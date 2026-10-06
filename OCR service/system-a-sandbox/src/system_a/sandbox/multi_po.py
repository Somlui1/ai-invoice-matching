"""S20–S29 — AIVA-SYSA-ORA-01: Tax ID + Invoice lookup (several POs / several receipts).

These scenarios are ``locked`` to ``mode: tax_invoice`` so a forced legacy run of S01–S19 never
re-interprets them.  Flags (``multi_po_receipts`` / ``v09_compare_matched_only``) are switched on
per scenario only; ``policy.yaml`` keeps them OFF pending approval of the Standard owner.
All Tax IDs, POs, invoice numbers and receipt numbers are synthetic.
"""
from __future__ import annotations

from .scenarios import (BRACKET, DS, E, GASKET, INV_A, PO_A, PO_B, SUP_TAX, L, R, Scenario, doc, miss)

TAX = "tax_invoice"
MULTI = {"multi_po_receipts": True}
PARTIAL = {"v09_compare_matched_only": True}
RCV_A, RCV_B = "RCV-0000020001", "RCV-0000020002"


def _two_po_lines():
    return (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"), L(2, "ITM-2002", GASKET, 5, "EA", "50.00"))


def _two_po_dataset(org_b: int = 103):
    return DS([E(PO_A, INV_A, [R(PO_A, RCV_A, 1, BRACKET, 10, "EA", "100.00")]),
               E(PO_B, INV_A, [R(PO_B, RCV_B, 1, GASKET, 5, "EA", "50.00", org=org_b)])],
              {PO_A: SUP_TAX, PO_B: SUP_TAX})


def s20() -> Scenario:
    return Scenario("S20", "Invoice 1 ใบ 2 PO 2 ใบรับ + multi_po_receipts เปิด -> AUTO_PASS",
                    doc(lines=_two_po_lines()), _two_po_dataset(), "AUTO_PASS", (), mode=TAX, locked=True,
                    flags=MULTI, queries=1,
                    checks={"lookup_path": "TAX-INV", "po_numbers": [PO_A, PO_B], "tax_source": "ocr"})


def s21() -> Scenario:
    return Scenario("S21", "เหมือน S20 แต่ flag ปิด -> E06 (HOLD)",
                    doc(lines=_two_po_lines()), _two_po_dataset(), "HOLD", ("E06",), mode=TAX, locked=True,
                    queries=1, checks={"lookup_path": "TAX-INV"})


def s22() -> Scenario:
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    return Scenario("S22", "OCR ไม่มี Tax ID ผู้ขาย -> หาจาก PO (Oracle) -> พบใบรับ",
                    doc(lines=lines, fields={"supplier_tax_id": miss()}),
                    DS([E(PO_A, INV_A, [R(PO_A, RCV_A, 1, BRACKET, 10, "EA", "100.00")])], {PO_A: SUP_TAX}),
                    "AUTO_PASS", (), mode=TAX, locked=True, queries=2,
                    checks={"lookup_path": "TAX-INV", "tax_source": "oracle_po",
                            "queries": ["PO-SUPPLIER", "TAX-INV"]})


def s23() -> Scenario:
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    entry = {**E(PO_A, "ASN-777", [R(PO_A, RCV_A, 1, BRACKET, 10, "EA", "100.00")]),
             "invoice_columns": {"SHIPMENT_NUM": "ASN-777", "PACKING_SLIP": INV_A}}
    return Scenario("S23", "เลข Invoice อยู่ใน PACKING_SLIP -> พบใบรับ",
                    doc(lines=lines), DS([entry], {PO_A: SUP_TAX}), "AUTO_PASS", (), mode=TAX, locked=True,
                    queries=1, checks={"lookup_path": "TAX-INV", "matched_on_column": "PACKING_SLIP"})


def s24() -> Scenario:
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    return Scenario("S24", "Invoice SQ26123 แต่ใบรับเก็บ SQ26/123 -> พบด้วย variant จาก config",
                    doc(lines=lines, invoice="SQ26123"),
                    DS([E(PO_A, "SQ26/123", [R(PO_A, RCV_A, 1, BRACKET, 10, "EA", "100.00")])], {PO_A: SUP_TAX}),
                    "AUTO_PASS", (), mode=TAX, locked=True, queries=1,
                    checks={"lookup_path": "TAX-INV", "matched_on_column": "SHIPMENT_NUM"})


def _partial_dataset():
    return DS([E(PO_A, INV_A, [R(PO_A, RCV_A, 1, BRACKET, 10, "EA", "100.00"),
                               R(PO_A, RCV_A, 2, GASKET, 5, "EA", "50.00")])], {PO_A: SUP_TAX})


def s25() -> Scenario:
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    return Scenario("S25", "วางบิลบางรายการของใบรับ + v09_compare_matched_only เปิด -> ไม่มี E03",
                    doc(lines=lines), _partial_dataset(), "AUTO_PASS", (), mode=TAX, locked=True,
                    flags=PARTIAL, queries=1, checks={"v09_unmatched": [f"{RCV_A}-2"]})


def s26() -> Scenario:
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    return Scenario("S26", "Oracle (ORDS) timeout -> SYSTEM_ERROR ไม่ใช่ E05",
                    doc(lines=lines), _partial_dataset(), "SYSTEM_ERROR", (), oracle_down=True,
                    mode=TAX, locked=True, queries=1)


def s27() -> Scenario:
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    return Scenario("S27", "เลข Invoice มีอักขระอันตราย -> ไม่ query เลย -> E05 (HOLD)",
                    doc(lines=lines, invoice="IV1'; DROP"), _partial_dataset(), "HOLD", ("E05",),
                    mode=TAX, locked=True, queries=0, checks={"queries": []})


def s28() -> Scenario:
    return Scenario("S28", "หลายใบรับแต่คนละ OU (ORG_ID) + flag เปิด -> E06 (HOLD)",
                    doc(lines=_two_po_lines()), _two_po_dataset(org_b=196), "HOLD", ("E06",),
                    mode=TAX, locked=True, flags=MULTI, queries=1)


def s29() -> Scenario:
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    return Scenario("S29", "Tax+Invoice ไม่พบ (ใบรับคีย์เลขอื่น) -> fallback PO-LIST พบ",
                    doc(lines=lines),
                    DS([E(PO_A, "OTHER-REF-9", [R(PO_A, RCV_A, 1, BRACKET, 10, "EA", "100.00")])], {PO_A: SUP_TAX}),
                    "AUTO_PASS", (), mode=TAX, locked=True, queries=2,
                    checks={"lookup_path": "PO-LIST", "queries": ["TAX-INV", "PO-LIST"]})


MULTI_PO = [s20(), s21(), s22(), s23(), s24(), s25(), s26(), s27(), s28(), s29()]
