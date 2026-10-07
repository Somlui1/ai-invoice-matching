"""S30–S43 — evidence-based acceptance (domain/evidence.py, policy.yaml -> evidence / matching /
oracle.lookup.po_list_narrowing).

Each case reproduces a pattern measured on the Paperless runs (2026-10-07) where a correct invoice
was rejected only because of how it was read or looked up, plus negative cases that must stay safe.
All identities are synthetic (see scenarios.py privacy rule).
"""
from __future__ import annotations

from .scenarios import (BRACKET, DS, E, F, GASKET, INV_A, PO_A, PO_B, RCV_A_B, SUP_TAX, L, R, Scenario,
                        doc, miss)

RCV = "RCV-0000030001"
C = lambda raw: F(raw, conf=0.70, agree=False)        # a read the second reader did not confirm
TAX = "tax_invoice"


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
                    doc(lines=lines, sub="23100.00"), _ds(R(PO_A, RCV, 1, BRACKET, 1, "Piece", "23100.00")),
                    "AUTO_PASS", (), queries=1)


def s33() -> Scenario:
    lines = (LC(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    return Scenario("S33", "ชื่อ/ที่อยู่ลูกค้า LOW_CONFIDENCE แต่ Tax ID ตรง Oracle -> AUTO_PASS",
                    doc(lines=lines, fields={"customer_name": F("บริษัท อาปิโก ไฮเทค พูลลิ่ง", conf=0.55, agree=False),
                                             "customer_address": F("99 ม.1 13160", conf=0.55, agree=False)}),
                    _ds(R(PO_A, RCV, 1, BRACKET, 10, "EA", "100.00")), "AUTO_PASS", (), queries=1)


def s34() -> Scenario:
    one = LC(1, "ITM-1001", BRACKET, 1, "EA", "793.60")
    copy = LC(2, "ITM-1001", BRACKET, 1, "EA", "793.60")
    return Scenario("S34", "หน้าต้นฉบับ+สำเนาถูกอ่านเป็น 2 บรรทัด (Σ = 2×sub_total) -> ยุบเหลือชุดเดียว -> AUTO_PASS",
                    doc(lines=(one, copy), sub="793.60"),
                    _ds(R(PO_A, RCV, 1, BRACKET, 1, "EA", "793.60")), "AUTO_PASS", (), queries=1)


def s35() -> Scenario:
    lines = (LC(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    return Scenario("S35", "เลข Invoice อ่านไม่ยืนยันและค้นไม่พบใบรับ -> E01 (REVIEW) ไม่ใช่ E05",
                    doc(lines=lines, invoice="SBX-INV-9999", fields={"invoice_num": C("SBX-INV-9999")}),
                    _ds(R(PO_A, RCV, 1, BRACKET, 10, "EA", "100.00")), "REVIEW", ("E01",), queries=3)


def s36() -> Scenario:
    lines = (LC(1, "ITM-1001", BRACKET, 1, "KG", "47.00", "1786.00", qty=C("1"), uom=miss(),
                unit_price=F("47.00/KG")),)
    return Scenario("S36", "บิลตามน้ำหนัก: amount/price = 38 = QTY ใบรับ (KG) -> qty 38 -> AUTO_PASS",
                    doc(lines=lines, sub="1786.00"),
                    _ds(R(PO_A, RCV, 1, BRACKET, 38, "Kilogram", "47.00")), "AUTO_PASS", (), queries=1)


def s37() -> Scenario:
    lines = (LC(1, "ITM-1001", BRACKET, 10, "EA", "100.00", unit_price=C("110.00")),)
    return Scenario("S37", "ราคาอ่านไม่ยืนยัน + คณิตไม่ปิด + ไม่ตรง PO -> ยังเป็น E01 (ไม่ถูกยกให้ผ่าน)",
                    doc(lines=lines), _ds(R(PO_A, RCV, 1, BRACKET, 10, "EA", "100.00")), "REVIEW", ("E01",),
                    queries=1)


def s38() -> Scenario:
    l1 = LC(1, "ITM-1001", f"{BRACKET} REF PO {PO_A}", 10, "EA", "100.00")
    l2 = LC(2, "ITM-1001", f"{BRACKET} REF PO {PO_B}", 5, "EA", "100.00")
    ds = DS([E(PO_A, INV_A, [R(PO_A, RCV_A_B[0], 1, BRACKET, 10, "EA", "100.00")]),
             E(PO_B, INV_A, [R(PO_B, RCV_A_B[1], 1, BRACKET, 5, "EA", "100.00", org=103)])],
            {PO_A: SUP_TAX, PO_B: SUP_TAX})
    return Scenario("S38", "1 Invoice 2 PO ราคาเท่ากัน: ใช้เลข PO ในบรรทัดแยกคู่ -> AUTO_PASS",
                    doc(lines=(l1, l2)), ds, "AUTO_PASS", (), mode=TAX, locked=True,
                    flags={"multi_po_receipts": True}, queries=1)


# ------------------------------------------------------------------ v2 batch #1 (E11 when all values agree)
def _dms114_like():
    """Milestone 30 % billing, two pairs of identical price/qty/amount lines (DMS-114 shape)."""
    lines = (LC(1, "", "dfg0010600a ccn50386 c/f", "0.3", "SET", "33000.00", "9900.00"),
             LC(2, "", "dfg0010601a ccn50385 c/f", "0.3", "SET", "33000.00", "9900.00"),
             LC(3, "", "dfg0010493a ccn42138 c/f", "0.3", "SET", "28000.00", "8400.00"),
             LC(4, "", "dfg0010494a ccn42132 c/f", "0.3", "SET", "28000.00", "8400.00"))
    rows = [R(PO_A, RCV, 1, "CCN50386 C/F", "0.3", "Set", "33000", "9900", ITEM_CODE="DFG0010600A"),
            R(PO_A, RCV, 2, "CCN50385 C/F", "0.3", "Set", "33000", "9900", ITEM_CODE="DFG0010601A"),
            R(PO_A, RCV, 3, "CCN42138 C/F", "0.3", "Set", "28000", "8400", ITEM_CODE="DFG0010493A"),
            R(PO_A, RCV, 4, "CCN42132 C/F", "0.3", "Set", "28000", "8400", ITEM_CODE="DFG0010494A")]
    return lines, rows


def s39() -> Scenario:
    lines, rows = _dms114_like()
    return Scenario("S39", "ราคาซ้ำกันหลายบรรทัด แต่ ราคา/จำนวน/ยอด/หน่วยตรง + ITEM code ในบรรทัด -> M1 (ไม่เรียก AI)",
                    doc(lines=lines, sub="36600.00"), _ds(*rows), "AUTO_PASS", (), mode=TAX, locked=True,
                    queries=1, checks={"no_ai": True})


def s40() -> Scenario:
    lines, rows = _dms114_like()
    return Scenario("S40", "AI จับคู่ด้วยคำบรรยาย (M4) แต่ทุกค่าตรงใบรับ -> E11 waived -> AUTO_PASS",
                    doc(lines=lines, sub="36600.00"), _ds(*rows), "AUTO_PASS", (), mode=TAX, locked=True,
                    queries=1, policy={"matching": {"m1_exact_values_item_code": False}},
                    checks={"e11_waived": 4})


def s41() -> Scenario:
    # negative: M4 pairing where the quantity differs -> E11 stays (and V-08 judges the quantity)
    lines = (LC(1, "ITM-1001", BRACKET, 10, "EA", "100.00"), LC(2, "ITM-2002", GASKET, 4, "EA", "100.00"))
    rows = [R(PO_A, RCV, 1, BRACKET, 10, "EA", "100.00"), R(PO_A, RCV, 2, GASKET, 6, "EA", "100.00")]
    return Scenario("S41", "M4 แต่จำนวนไม่ตรงใบรับ -> E11 ไม่ถูกยกเว้น",
                    doc(lines=lines), _ds(*rows), "HOLD", ("E03", "E11", "E15"), queries=1,
                    policy={"matching": {"m1_exact_values_item_code": False}})


# ------------------------------------------------------------------ v2 batch #2 (PO-LIST narrowing)
def _po_list(extra_rows, *, sub="1000.00"):
    """TAX-INV finds nothing (receipts keyed with other numbers) -> PO-LIST returns the PO history."""
    lines = (LC(1, "ITM-1001", BRACKET, 10, "EA", "100.00"),)
    entries = [E(PO_A, ref, rows) for ref, rows in extra_rows]
    return doc(lines=lines, sub=sub), DS(entries, {PO_A: SUP_TAX})


def s42() -> Scenario:
    d, ds = _po_list([("OTHER-1", [R(PO_A, "RCV-0000042001", 1, BRACKET, 20, "EA", "100.00", SHIPMENT_NUM="OTHER-1",
                                     QTY_BILLED="20")]),
                      ("OTHER-2", [R(PO_A, "RCV-0000042002", 1, BRACKET, 10, "EA", "100.00", SHIPMENT_NUM=INV_A,
                                     PACKING_SLIP=INV_A)]),
                      ("OTHER-3", [R(PO_A, "RCV-0000042003", 1, BRACKET, 5, "EA", "100.00", SHIPMENT_NUM="OTHER-3")])])
    return Scenario("S42", "PO-LIST คืน 3 ใบรับ; ใบที่ SHIPMENT_NUM = เลข Invoice -> เหลือใบเดียว -> AUTO_PASS",
                    d, ds, "AUTO_PASS", (), mode=TAX, locked=True, queries=2,
                    checks={"lookup_path": "PO-LIST", "narrowing": "header_key_equals_invoice_num"})


def s43() -> Scenario:
    d, ds = _po_list([("OTHER-1", [R(PO_A, "RCV-0000043001", 1, BRACKET, 20, "EA", "100.00", QTY_BILLED="20")]),
                      ("OTHER-2", [R(PO_A, "RCV-0000043002", 1, BRACKET, 10, "EA", "100.00", QTY_BILLED="10")])])
    return Scenario("S43", "PO-LIST 2 ใบรับ ไม่มีเลข Invoice; ยอดใบรับเดียว = sub_total -> เลือกใบนั้น -> AUTO_PASS",
                    d, ds, "AUTO_PASS", (), mode=TAX, locked=True, queries=2,
                    checks={"lookup_path": "PO-LIST", "narrowing": "receipt_total_equals_sub_total"})


def s44() -> Scenario:
    d, ds = _po_list([("OTHER-1", [R(PO_A, "RCV-0000044001", 1, BRACKET, 10, "EA", "100.00", QTY_BILLED="10")]),
                      ("OTHER-2", [R(PO_A, "RCV-0000044002", 1, BRACKET, 10, "EA", "100.00", QTY_BILLED="10")])])
    return Scenario("S44", "PO-LIST 2 ใบรับ ยอดเท่ากันทั้งคู่ ปิดวางบิลแล้ว -> ระบุไม่ได้ -> MANUAL_REVIEW (ไม่ใช่ E06)",
                    d, ds, "MANUAL_REVIEW", (), mode=TAX, locked=True, queries=2,
                    checks={"lookup_path": "PO-LIST", "narrowing": None})


def s45() -> Scenario:
    d, ds = _po_list([("OTHER-1", [R(PO_A, "RCV-0000045001", 1, BRACKET, 10, "EA", "100.00", QTY_BILLED="10")]),
                      ("OTHER-2", [R(PO_A, "RCV-0000045002", 1, BRACKET, 10, "EA", "100.00", QTY_BILLED="10")])])
    return Scenario("S45", "เหมือน S44 แต่ปิด po_list_narrowing -> พฤติกรรมเดิม E06 (HOLD)",
                    d, ds, "HOLD", ("E06",), mode=TAX, locked=True, queries=2,
                    policy={"oracle.lookup": {"po_list_narrowing": False}})


EVIDENCE = [s30(), s31(), s32(), s33(), s34(), s35(), s36(), s37(), s38(), s39(), s40(), s41(), s42(), s43(),
            s44(), s45()]
