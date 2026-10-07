"""Raw -> normalized values (Standard v6.6 Table 3).  Pure functions.  Never guesses."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from .contracts import ExtractionResult, InvoiceDoc, NField, NLine, RawField
from .standard import Standard

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
MONEY_FIELDS = {"sub_total", "vat", "grand_total", "qty", "unit_price", "amount"}


class Invalid(ValueError):
    pass


def thai_to_arabic(s: str) -> str:
    return s.translate(THAI_DIGITS)


def tax_id(raw: str) -> str:
    d = re.sub(r"\D", "", thai_to_arabic(raw))
    if len(d) != 13:
        raise Invalid("TAX_ID_NOT_13_DIGITS")
    n = [int(c) for c in d]
    if (11 - sum(n[i] * (13 - i) for i in range(12)) % 11) % 10 != n[12]:
        raise Invalid("TAX_ID_CHECKSUM")
    return d


def tax_id_loose(raw: str) -> Optional[str]:
    d = re.sub(r"\D", "", thai_to_arabic(raw or ""))
    return d if len(d) == 13 else None


_MONEY_HEAD = re.compile(r"^(-?\d[\d,]*(?:\.\d+)?)\s*(.*)$")
_ACCOUNTING_NEG = re.compile(r"^\(\s*(\d[\d,]*(?:\.\d+)?)\s*\)$")
#: what may follow the number in a printed cell without changing its meaning:
#: a unit ("PCS", "/PC", "กก.") or a parenthesised remark ("(2PCS)").  Anything else -> NOT_A_NUMBER.
_UNIT_TAIL = re.compile(r"^(?:/\s*)?([A-Za-z\u0E01-\u0E4E][A-Za-z\u0E01-\u0E4E.]{0,11})$")
_PAREN_TAIL = re.compile(r"^\([^()]*\)$")
_CURRENCY = re.compile(r"(฿|THB|บาท)", re.I)


def split_number(raw: str) -> tuple[Decimal, Optional[str]]:
    """``"23,100.00 /PC"`` -> (23100.00, "PC") · ``"1 (2PCS)"`` -> (1, None) · ``"(1,200.00)"`` -> (-1200, None).

    Takes the leading number only; the rest must be a unit or a bracketed remark, otherwise the
    cell is rejected (``"7.00 %"``, ``"1 2"`` -> NOT_A_NUMBER).  Digits are never concatenated across
    a space or a bracket, unlike a strip-everything parser (``"1 (2PCS)"`` would become 12).
    """
    s = _CURRENCY.sub("", thai_to_arabic(str(raw))).strip()
    m = _ACCOUNTING_NEG.match(s)
    if m:
        return -_dec(m.group(1)), None
    m = _MONEY_HEAD.match(s)
    if not m:
        raise Invalid("NOT_A_NUMBER")
    num, tail = m.group(1), m.group(2).strip()
    unit = None
    if tail:
        u = _UNIT_TAIL.match(tail)
        if u:
            unit = u.group(1).rstrip(".") or None
        elif not _PAREN_TAIL.match(tail):
            raise Invalid("NOT_A_NUMBER")
    return _dec(num), unit


def _dec(num: str) -> Decimal:
    t = num.replace(",", "")
    if num.count(",") and not re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", num):
        raise Invalid("NOT_A_NUMBER")             # "1,23" is not a thousands separator
    try:
        return Decimal(t)
    except InvalidOperation as e:
        raise Invalid("NOT_A_NUMBER") from e


def money(raw: str) -> Decimal:
    return split_number(raw)[0]


def invoice_num(raw: str) -> str:
    s = re.sub(r"\s+", "", thai_to_arabic(raw)).upper()
    if not s:
        raise Invalid("EMPTY")
    return s


def po_and_release(raw: str) -> tuple[str, Optional[str]]:
    """Table 3 #8/#9: 40118928-87 -> (40118928, 87) · 4011892887 -> (40118928, 87) ·
    40118638-170-30485114 -> (40118638, 170).  PO must be 8 digits."""
    s = re.sub(r"^\D+", "", thai_to_arabic(raw).strip())
    parts = [p for p in re.split(r"[-/\s]+", s) if p]
    if not parts or not parts[0].isdigit():
        raise Invalid("PO_NOT_NUMERIC")
    head = parts[0]
    if len(head) > 8:
        return head[:8], head[8:] or None
    if len(head) != 8:
        raise Invalid("PO_NOT_8_DIGITS")
    return head, (parts[1] if len(parts) > 1 and parts[1].isdigit() else None)


def date_iso(raw: str) -> str:
    """dd/mm/yyyy · dd/mm/yy · yyyy/mm/dd (Buddhist or Gregorian year) -> ISO yyyy-mm-dd.

    Measured on the DMS batch: ``04/09/26`` (DMS-21) and ``2026/09/02`` (DMS-24) were rejected as DATE_FORMAT.
    Two-digit years are read the way Thai invoices print them: 50-99 = Buddhist era 25xx, 00-49 = 20xx.
    """
    t = thai_to_arabic(raw)
    m = re.search(r"(?<!\d)(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})(?!\d)", t)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.search(r"(?<!\d)(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4}|\d{2})(?!\d)", t)
        if not m:
            raise Invalid("DATE_FORMAT")
        d, mo, y = map(int, m.groups())
        if y < 100:
            y = 2500 + y if y >= 50 else 2000 + y
    if y > 2400:
        y -= 543
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        raise Invalid("DATE_FORMAT")
    return f"{y:04d}-{mo:02d}-{d:02d}"


def text(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


NORMALIZERS = {
    "customer_tax_id": tax_id, "supplier_tax_id": lambda r: tax_id_loose(r) or text(r),
    "invoice_num": invoice_num, "invoice_date": date_iso, "currency": lambda r: text(r).upper() or "THB",
    **{k: money for k in MONEY_FIELDS},
}


def _nfield(std: Standard, name: str, rf: Optional[RawField], element_id: str) -> NField:
    if rf is None or rf.raw is None or str(rf.raw).strip() == "":
        reason = (rf.null_reason if rf else None) or "NOT_PRESENT"
        return NField(name, element_id, None, None, rf.confidence if rf else None, False, reason)
    min_conf, need_agree = std.threshold(name)
    try:
        value = NORMALIZERS.get(name, text)(rf.raw)
    except Invalid as e:
        return NField(name, element_id, rf.raw, None, rf.confidence, False, f"INVALID_FORMAT:{e}")
    if need_agree and not rf.agreement:
        return NField(name, element_id, rf.raw, value, rf.confidence, False, "CONFLICT_BETWEEN_SOURCES")
    if rf.confidence is not None and rf.confidence < min_conf:
        return NField(name, element_id, rf.raw, value, rf.confidence, False, "LOW_CONFIDENCE")
    return NField(name, element_id, rf.raw, value, rf.confidence, True, None)


def normalize(ext: ExtractionResult, std: Standard) -> tuple[InvoiceDoc, dict]:
    """Returns the invoice view used by rules + extra normalized metadata (release_num ...)."""
    did = ext.invoice_document_id
    fields: dict[str, NField] = {}
    meta: dict = {}
    for name, rf in ext.fields.items():
        eid = f"{did}-f-{name}"
        if name == "po_number":
            nf = _nfield(std, "po_number", rf, eid)
            if rf.raw:
                try:
                    po, rel = po_and_release(rf.raw)
                    nf = NField(nf.name, eid, nf.raw, po, nf.confidence, nf.ok, nf.null_reason)
                    meta["release_num"] = rel
                except Invalid as e:
                    nf = NField("po_number", eid, rf.raw, None, rf.confidence, False, f"INVALID_FORMAT:{e}")
            fields[name] = nf
        else:
            fields[name] = _nfield(std, name, rf, eid)
    for req in std.policy["required_fields"]:           # absent key == not present
        fields.setdefault(req, NField(req, f"{did}-f-{req}", None, None, None, False, "NOT_PRESENT"))
    meta.setdefault("release_num", None)
    po_rf = ext.fields.get("po_number")
    meta["po_numbers"] = po_tokens(po_rf.raw if po_rf is not None else None)
    lines = []
    for ln in ext.lines:
        lid = f"{did}-L{ln.line_no}"
        cells = {k: _nfield(std, k, rf, f"{lid}-{k}") for k, rf in ln.cells.items()}
        u = cells.get("uom")
        if (u is None or not u.ok) and _derive_uom_enabled(std):
            d = _uom_from_number_cells(std, ln.cells, f"{lid}-uom")
            if d is not None:
                cells["uom"] = u = d
        if u is not None and u.ok:                      # Table 3 #13: normalized_value = UOM group
            cells["uom"] = NField(u.name, u.element_id, u.raw, std.uom_group(u.value), u.confidence, True, None)
        for req in std.policy["required_line_cells"]:
            cells.setdefault(req, NField(req, f"{lid}-{req}", None, None, None, False, "NOT_PRESENT"))
        ug = cells["uom"].value if cells["uom"].ok else None
        lines.append(NLine(ln.line_no, lid, cells, ug, line_po_refs(ln.cells)))
    sigs = dict(ext.signatures)
    stamp = _deliverer_from_stamp(ext, std, sigs)
    if stamp is not None:
        sigs["deliverer"] = stamp
        meta["deliverer_from_stamp"] = True
    return InvoiceDoc(did, fields, tuple(lines), sigs, ext.pages_complete), meta


def _deliverer_from_stamp(ext: ExtractionResult, std: Standard, sigs: dict):
    """Deliverer slot undecided, but a company stamp was seen on an invoice page.

    The supplier's company stamp is the usual "deliverer" mark on Thai tax invoices; the page read
    reports it as a ``stamp`` region (text "stamped") rather than inside the deliverer signature box.
    Only used when policy.evidence.deliverer_from_stamp is on and the slot is truly undecided.
    """
    if not (std.policy.get("evidence") or {}).get("deliverer_from_stamp", False):
        return None
    cur = sigs.get("deliverer")
    th = float(std.policy["signature"]["min_confidence"])
    if cur is not None and cur.present is not None and (cur.confidence is None or cur.confidence >= th):
        return None
    inv_pages = set()
    for d in ext.documents:
        if d.document_id == ext.invoice_document_id:
            inv_pages |= set(d.pages)
    for rg in ext.regions:
        if rg.kind == "stamp" and rg.page in inv_pages and "stamped" in str(rg.text or "").lower() \
                and (rg.confidence or 0) >= th:
            from .contracts import Region, SignatureObs
            return SignatureObs(present=True, confidence=rg.confidence, kind="company_stamp_region",
                                region=Region(page=rg.page, bbox=rg.bbox))
    return None


_PO_TOKEN = re.compile(r"(?<![0-9A-Za-z])(\d{8})(?:-(\d{1,4}))?(?![0-9])")


def po_tokens(*texts) -> list[str]:
    """Every standalone 8-digit number in printed order ("PO 42052569 / 42052570", "42050536-12").

    A long part number (7553065060) is not split.  A standalone 8-digit material number can still be
    returned: callers must confirm a token against Oracle before treating it as a PO.
    """
    out: list[str] = []
    for t in texts:
        for m in _PO_TOKEN.finditer(thai_to_arabic(str(t or ""))):
            if m.group(1) not in out:
                out.append(m.group(1))
    return out


def line_po_refs(raw_cells: dict) -> tuple:
    return tuple(po_tokens(*((raw_cells.get(k).raw if raw_cells.get(k) is not None else None)
                             for k in ("item_code", "description"))))


def _derive_uom_enabled(std: Standard) -> bool:
    return bool((std.policy.get("evidence") or {}).get("uom_from_number_cells", False))


def _uom_from_number_cells(std: Standard, raw_cells: dict, eid: str) -> Optional[NField]:
    """A unit printed inside the price/qty cell (``23,100.00 /PC``, ``2 PCS``) when the invoice has no
    unit column.  Only a unit that belongs to a Table 3 group is accepted (never a free word)."""
    for src in ("unit_price", "qty"):
        rf = raw_cells.get(src)
        if rf is None or not rf.raw:
            continue
        try:
            _, unit = split_number(rf.raw)
        except Invalid:
            continue
        if unit and unit.upper().rstrip(".") in {g.upper() for g in std.uom_groups} | {
                m.upper().rstrip(".") for ms in std.uom_groups.values() for m in ms}:
            return NField("uom", eid, unit, unit, rf.confidence, True, None, (f"derived:{src}_suffix",))
    return None


# ----------------------------------------------------------------- V-05 helpers (Standard Table 9 script)
_LEGAL = r"บริษัท|จำกัด|\(มหาชน\)|มหาชน|public|company|limited|co\.?|ltd\.?|pcl|บมจ\.?|บจ\.?|[.,()\-]"


def norm_name(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", re.sub(_LEGAL, " ", (s or "").lower())).strip()


def addr_key(s: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """(house_no, postal).  Uses the number after 'เลขที่' first (not a floor number).
    Deliberately ASCII-only: Thai numerals are left to the AI address parser."""
    s = s or ""
    house = (re.search(r"เลขที่\s*([0-9]+(?:/[0-9]+)?(?:-[0-9]+(?:/[0-9]+)?)?)", s, re.A)
             or re.search(r"\b([0-9]+(?:/[0-9]+)?(?:-[0-9]+(?:/[0-9]+)?)?)\b", s, re.A))
    post = re.findall(r"\b([0-9]{5})\b", s, re.A)
    return (house.group(1) if house else None, post[-1] if post else None)
