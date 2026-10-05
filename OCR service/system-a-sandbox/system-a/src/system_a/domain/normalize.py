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


def money(raw: str) -> Decimal:
    s = thai_to_arabic(raw).strip().replace(",", "").replace("฿", "").replace("THB", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        v = Decimal(s)
    except InvalidOperation as e:
        raise Invalid("NOT_A_NUMBER") from e
    return -v if neg else v


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
    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", thai_to_arabic(raw))
    if not m:
        raise Invalid("DATE_FORMAT")
    d, mo, y = map(int, m.groups())
    if y > 2400:
        y -= 543
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
    lines = []
    for ln in ext.lines:
        lid = f"{did}-L{ln.line_no}"
        cells = {k: _nfield(std, k, rf, f"{lid}-{k}") for k, rf in ln.cells.items()}
        u = cells.get("uom")
        if u is not None and u.ok:                      # Table 3 #13: normalized_value = UOM group
            cells["uom"] = NField(u.name, u.element_id, u.raw, std.uom_group(u.value), u.confidence, True, None)
        for req in std.policy["required_line_cells"]:
            cells.setdefault(req, NField(req, f"{lid}-{req}", None, None, None, False, "NOT_PRESENT"))
        ug = cells["uom"].value if cells["uom"].ok else None
        lines.append(NLine(ln.line_no, lid, cells, ug))
    return InvoiceDoc(did, fields, tuple(lines), dict(ext.signatures), ext.pages_complete), meta


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
