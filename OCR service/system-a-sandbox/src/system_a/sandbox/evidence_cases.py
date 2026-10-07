"""S30–S37 — evidence-based acceptance (domain/evidence.py, policy.yaml -> evidence).

Each case reproduces a pattern measured on the 98-document Paperless run (2026-10-07) where a
correct invoice was rejected only because two readers did not agree, and one negative case that
must stay safe.  All identities are synthetic (see scenarios.py privacy rule).
"""
from __future__ import annotations

from .scenarios import (BRACKET, DS, E, F, INV_A, PO_A, SUP_TAX, L, R, Scenario, doc, miss)

RCV = "RCV-0000030001"
C = lambda raw: F(raw, conf=0.70, agree=False)        # a read the second reader did not confirm


def LC(no, item, desc, q, u, price, amt=None, **over):
    """L() with cell overrides (L's own parameters are called qty/uom/amount)."""
    row = L(no, item, desc, q, u, price, amt)
    row["cells"].update(over)
    return row


def _ds(*rows):
    return DS([E(PO_A, INV_A, list(rows))], {PO_A: SUP_TAX})


def s30() -> Scenario:
    lines = (LC(1, "ITM-1001", BRACKET, 10, "EA", "100.00", qty=C("10"), unit_price=C("100.00"),
               amount=C("1,000.00")),)
    # sub/vat/grand given explicitly: doc() would otherwise sum the raw (comma) amounts
    return Scenario("S30", "qty/price/amount อ่านไม่ยืนยัน แต่ qty×price=amount และตรงใบรับ -> AUTO_PASS",
                    doc(lines=lines, sub="1000.00", fields={"sub_total": C("1000.00"), "vat": C("70.00"),
                                             "grand_total": C("1070.00")}),
                    _ds(R(PO_A, RCV, 1, BRACKET, 10, "EA", "100.00")), "AUTO_PASS", (), queries=1)


def s31() -> Scenario:
    lines = (LC(1, "ITM-1001", BRACKET, 10, "EA", "100.00", uom=miss()),)
    return Scenario("S31", "ใบแจ้งหนี้ไม่พิมพ์หน่วย -> ใช้หน่วยของบรรทัดใบรับที่จับคู่ได้ -> AUTO_PASS",
                    doc(lines=lines), _ds(R(PO_A, RCV, 1, BRACKET, 10, "Piece", "100.00")), "AUTO_PASS", (),
                    queries=1)


def s32() -> Scenario:
    lines = (LC(1, "ITM-1001", BRACKET, 1, "EA", "23100.00", uom=miss(), unit_price=F("23,100.00 /PC")),)
    return Scenario("S32", "ราคา '23,100.00 /PC' -> ราคา 23100 + หน่วย PC จากช่องเดียวกัน -> AUTO_PASS",
                    doc(lines=lines, sub="23100.00"), _ds(R(PO_A, RCV, 1, BRACKET, 1, "Piece", "23100.00")), "AUTO_PASS", (),
                    queries=1)


def s33() -> Scenario:
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    return Scenario("S33", "ชื่อ/ที่อยู่ลูกค้า LOW_CONFIDENCE แต่ Tax ID ตรง Oracle -> AUTO_PASS",
                    doc(lines=lines, fields={"customer_name": F("บริษัท อาปิโก ไฮเทค พูลลิ่ง", conf=0.55, agree=False),
                                             "customer_address": F("99 ม.1 13160", conf=0.55, agree=False)}),
                    _ds(R(PO_A, RCV, 1, BRACKET, 10, "EA", "100.00")), "AUTO_PASS", (), queries=1)


def s34() -> Scenario:
    one = L(1, "ITM-1001", BRACKET, 1, "EA", "793.60")
    copy = L(2, "ITM-1001", BRACKET, 1, "EA", "793.60")
    return Scenario("S34", "หน้าต้นฉบับ+สำเนาถูกอ่านเป็น 2 บรรทัด (Σ = 2×sub_total) -> ยุบเหลือชุดเดียว -> AUTO_PASS",
                    doc(lines=(one, copy), sub="793.60"),
                    _ds(R(PO_A, RCV, 1, BRACKET, 1, "EA", "793.60")), "AUTO_PASS", (), queries=1)


def s35() -> Scenario:
    lines = (L(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    return Scenario("S35", "เลข Invoice อ่านไม่ยืนยันและค้นไม่พบใบรับ -> E01 (REVIEW) ไม่ใช่ E05",
                    doc(lines=lines, invoice="SBX-INV-9999", fields={"invoice_num": C("SBX-INV-9999")}),
                    _ds(R(PO_A, RCV, 1, BRACKET, 10, "EA", "100.00")), "REVIEW", ("E01",), queries=3)


def s36() -> Scenario:
    # weight-billed casting: qty column prints 1 piece, amount = 38 kg x 47.00
    lines = (LC(1, "ITM-1001", BRACKET, 1, "KG", "47.00", "1786.00", qty=C("1"), uom=miss(),
               unit_price=F("47.00/KG")),)
    return Scenario("S36", "บิลตามน้ำหนัก: amount/price = 38 = QTY ใบรับ (KG) -> qty 38 -> AUTO_PASS",
                    doc(lines=lines, sub="1786.00"),
                    _ds(R(PO_A, RCV, 1, BRACKET, 38, "Kilogram", "47.00")), "AUTO_PASS", (), queries=1)


def s37() -> Scenario:
    # negative: an unconfirmed price that does NOT close and does NOT equal the PO stays E01
    lines = (LC(1, "ITM-1001", BRACKET, 10, "EA", "100.00", unit_price=C("110.00")),)
    return Scenario("S37", "ราคาอ่านไม่ยืนยัน + คณิตไม่ปิด + ไม่ตรง PO -> ยังเป็น E01 (ไม่ถูกยกให้ผ่าน)",
                    doc(lines=lines), _ds(R(PO_A, RCV, 1, BRACKET, 10, "EA", "100.00")), "REVIEW", ("E01",),
                    queries=1)


EVIDENCE = [s30(), s31(), s32(), s33(), s34(), s35(), s36(), s37()]


def s38() -> Scenario:
    # 1 invoice, 2 POs, both lines priced 100.00: M1 cannot decide by price alone.  The PO printed
    # in each line description (confirmed by Oracle) separates them -> no AI, no E11.
    from .scenarios import GASKET, PO_B, RCV_A_B
    l1 = LC(1, "ITM-1001", f"{BRACKET} REF PO {PO_A}", 10, "EA", "100.00")
    l2 = LC(2, "ITM-1001", f"{BRACKET} REF PO {PO_B}", 5, "EA", "100.00")
    ds = DS([E(PO_A, INV_A, [R(PO_A, RCV_A_B[0], 1, BRACKET, 10, "EA", "100.00")]),
             E(PO_B, INV_A, [R(PO_B, RCV_A_B[1], 1, BRACKET, 5, "EA", "100.00", org=103)])],
            {PO_A: SUP_TAX, PO_B: SUP_TAX})
    return Scenario("S38", "1 Invoice 2 PO ราคาเท่ากัน: ใช้เลข PO ในบรรทัดแยกคู่ -> AUTO_PASS",
                    doc(lines=(l1, l2)), ds, "AUTO_PASS", (), mode="tax_invoice", locked=True,
                    flags={"multi_po_receipts": True}, queries=1, checks={"no_ai": True})


EVIDENCE.append(s38())
