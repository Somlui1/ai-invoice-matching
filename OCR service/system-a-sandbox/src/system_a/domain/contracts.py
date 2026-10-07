"""Contracts that cross module boundaries.

* ``ExtractionResult``  (aiva.extraction/2.0) : perception -> domain   (pydantic, JSON in/out)
* ``OracleSnapshot``    (aiva.oracle/2.0)     : oracle adapter -> domain
* ``RuleOutcome`` / ``Finding``               : rules -> assembler
Money is Decimal, never float.  Domain objects are frozen.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

BBox = tuple[float, float, float, float]  # normalized [x, y, w, h], origin top-left, 0..1

COORDINATE_SYSTEM = {
    "origin": "top-left", "unit": "normalized", "range": [0, 1], "bbox_format": "[x, y, w, h]",
    "reference": "rendered page after rotation correction (see pages[].rotation)",
}


class _M(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------- 1. extraction (input)
class Region(_M):
    page: int
    bbox: BBox


class RawField(_M):
    raw: Optional[str] = None
    confidence: Optional[float] = None
    agreement: bool = True                 # dual-read / crop re-read agreed
    region: Optional[Region] = None
    word_ids: tuple[str, ...] = ()
    source: Literal["ocr", "vlm", "consensus", "derived"] = "consensus"
    null_reason: Optional[str] = None      # NOT_PRESENT | ILLEGIBLE | OUT_OF_PAGE | CONFLICT_BETWEEN_SOURCES | NOT_GROUNDED


class RawLine(_M):
    line_no: int
    region: Optional[Region] = None
    cells: dict[str, RawField]             # item_code, description, qty, uom, unit_price, amount


class SignatureObs(_M):
    present: Optional[bool] = None         # None = could not decide
    confidence: Optional[float] = None
    kind: Optional[str] = None
    region: Optional[Region] = None


class PageInfo(_M):
    page_no: int
    width_pt: float
    height_pt: float
    rotation: int = 0
    render_dpi: int = 300
    page_type: Literal["INVOICE", "TAX_INVOICE", "PO", "OSP", "DELIVERY_NOTE", "SUPPORTING", "UNKNOWN"] = "UNKNOWN"
    type_confidence: Optional[float] = None
    ocr_quality: Optional[float] = None


class DocumentInfo(_M):
    document_id: str
    document_type: str
    pages: tuple[int, ...]
    confidence: Optional[float] = None


class Word(_M):
    word_id: str
    page: int
    text: str
    bbox: BBox
    confidence: Optional[float] = None


class RegionNode(_M):
    """A region that is not a field/row/cell: page section, item table, stamp, blank signature box...

    These carry the bbox levels the result contract allows (``section`` / ``table`` / ``stamp``) so the
    report can show the whole page decomposition, not only the fields that happened to be used.
    """
    region_id: str
    page: int
    kind: Literal["section", "table", "stamp", "signature_box", "other"] = "other"
    label: Optional[str] = None
    text: Optional[str] = None
    confidence: Optional[float] = None
    bbox: BBox
    parent_id: Optional[str] = None


class ExtractionResult(_M):
    contract: Literal["aiva.extraction/2.0"] = "aiva.extraction/2.0"
    package_id: str
    dms_doc_id: str
    file_sha256: str
    pages: tuple[PageInfo, ...]
    documents: tuple[DocumentInfo, ...]
    invoice_document_id: str
    pages_complete: bool = True
    fields: dict[str, RawField]
    lines: tuple[RawLine, ...] = ()
    signatures: dict[Literal["receiver", "deliverer"], SignatureObs] = Field(default_factory=dict)
    words: tuple[Word, ...] = ()
    regions: tuple[RegionNode, ...] = ()     # section / table / stamp level boxes
    extra: dict = Field(default_factory=dict)          # full extraction: tables, remarks, stamps, other docs
    extractor: dict[str, str] = Field(default_factory=dict)


# --------------------------------------------------------------------------- 2. normalized view (domain)
@dataclass(frozen=True)
class NField:
    name: str
    element_id: str
    raw: Optional[str]
    value: object                 # Decimal | str | None
    confidence: Optional[float]
    ok: bool                      # readable AND meets threshold
    null_reason: Optional[str] = None
    # Why a value that failed the reader-agreement/confidence gate is still trusted
    # (domain/evidence.py): "arith:...", "oracle:...", "covered_by_customer_tax_id", "derived:..."
    evidence: tuple = ()


@dataclass(frozen=True)
class NLine:
    line_no: int
    element_id: str
    cells: dict                   # name -> NField
    uom_group: Optional[str]
    # 8-digit PO numbers printed on this line (description / item code), in printed order.
    # Candidates only: matching uses one when it equals a PO that Oracle returned for this invoice.
    po_refs: tuple = ()

    def v(self, k):
        f = self.cells.get(k)
        return f.value if f and f.ok else None

    def ok(self, k) -> bool:
        f = self.cells.get(k)
        return bool(f and f.ok)


@dataclass(frozen=True)
class InvoiceDoc:
    document_id: str
    fields: dict
    lines: tuple
    signatures: dict
    pages_complete: bool

    def v(self, k):
        f = self.fields.get(k)
        return f.value if f and f.ok else None

    def value_any(self, k):
        """The normalized value even when the field is not ``ok`` (lookup keys, corroboration)."""
        f = self.fields.get(k)
        return f.value if f is not None else None

    def ok(self, k) -> bool:
        f = self.fields.get(k)
        return bool(f and f.ok)


# --------------------------------------------------------------------------- 3. oracle
@dataclass(frozen=True)
class ReceiptRow:
    org_id: Optional[int]
    receipt_num: str
    receiver: Optional[str]
    line: int
    item: str
    qty: Decimal
    uom: str
    unit_price: Decimal
    line_amount: Decimal
    extra: dict = field(default_factory=dict)   # informational columns (PO_NUM, SHIPMENT_NUM, ...)
    # --- AIVA-SYSA-ORA-01: columns the Tax ID + Invoice query adds.  Every one of them defaults to
    # "no data", so a snapshot built by the legacy RCV-V01/RCV-V02 queries serialises exactly as
    # before (see row_payload) and integrity.payload_sha256 of existing documents does not move.
    po_number: Optional[str] = None
    item_code: Optional[str] = None
    qty_billed: Decimal = Decimal(0)
    po_line_status: Optional[str] = None
    line_status: Optional[str] = None
    supplier_tax_id: Optional[str] = None
    supplier_name: Optional[str] = None
    customer_tax_id: Optional[str] = None
    ou_org_id: Optional[int] = None
    ou_name: Optional[str] = None
    shipment_num: Optional[str] = None
    packing_slip: Optional[str] = None
    waybill_num: Optional[str] = None

    @property
    def rcv_line_id(self) -> str:
        return f"{self.receipt_num}-{self.line}"


# New optional fields and their "no data" default: omitted from a serialised row while untouched.
_ROW_OPTIONAL_DEFAULTS: dict = {"po_number": None, "item_code": None, "qty_billed": Decimal(0),
                                "po_line_status": None, "line_status": None, "supplier_tax_id": None,
                                "supplier_name": None, "customer_tax_id": None, "ou_org_id": None,
                                "ou_name": None, "shipment_num": None, "packing_slip": None,
                                "waybill_num": None}


def row_payload(r: ReceiptRow) -> dict:
    """The row as an audit record: every column that carries data, nothing that does not.

    Used by ``assembler`` (``oracle_snapshot.receipt_lines``) and by ``OracleSnapshot.fingerprint`` so
    that adding a field to ``ReceiptRow`` cannot change the payload of a document whose query did not
    return that column.
    """
    out = {k: v for k, v in r.__dict__.items() if k not in _ROW_OPTIONAL_DEFAULTS}
    for k, default in _ROW_OPTIONAL_DEFAULTS.items():
        v = getattr(r, k)
        if v != default:
            out[k] = v
    return out


@dataclass(frozen=True)
class OracleSnapshot:
    queried_at: str
    lookup_path: Optional[str]             # RCV-V01 | RCV-V02 | TAX-INV | PO-LIST | None
    query_keys: dict
    rows: tuple = ()
    row_cap_hit: bool = False
    calls: int = 0
    po_numbers: tuple = ()                 # AIVA-SYSA-ORA-01: sorted, unique POs behind these rows
    matched_on_column: Optional[str] = None  # which receipt column the invoice number was found in

    @property
    def active(self) -> tuple:
        return tuple(r for r in self.rows if r.qty > 0)

    @property
    def receipt_nums(self) -> list[str]:
        return sorted({r.receipt_num for r in self.active})

    @property
    def org_id(self) -> Optional[int]:
        a = self.active
        return a[0].org_id if a else None

    def fingerprint(self) -> str:
        body = json.dumps([row_payload(r) for r in self.rows], default=str, sort_keys=True)
        return "sha256:" + hashlib.sha256(body.encode()).hexdigest()


class OracleTechnicalError(RuntimeError):
    """Connectivity/parse failure — never a business exception."""


class OracleInputRejected(OracleTechnicalError):
    """A lookup key was not whitelist-shaped, so the query was **not executed** (INPUT_REJECTED).

    Still a technical outcome (manual_review, never E05), but reported under its own reason so an
    operator sees "the number we tried to look up has an invalid shape" instead of "database error".
    """


class AIServiceError(RuntimeError):
    """LLM transport/decode failure after retries."""


# --------------------------------------------------------------------------- 4. rule results
Result = Literal["pass", "fail", "not_evaluated", "manual_review"]


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    rule_id: str
    message_th: str
    actual: Optional[str] = None
    expected: Optional[str] = None
    element_ids: tuple = ()
    oracle_refs: tuple = ()
    source: Optional[str] = None           # e.g. E03 "invoice" | "receipt"


@dataclass(frozen=True)
class RuleOutcome:
    rule_id: str
    result: Result
    findings: tuple = ()
    detail: Optional[str] = None
    halted_by: Optional[str] = None
    data: dict = field(default_factory=dict)
