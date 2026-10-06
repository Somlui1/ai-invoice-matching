"""STEP 2 receipt lookup.

Two modes, chosen by ``policy.oracle.lookup.mode``:

* ``legacy_po_invoice`` (X-01, pre AIVA-SYSA-ORA-01 — unchanged byte for byte)
    RCV-V01 (PO + Invoice) -> PO-SUPPLIER -> RCV-V02 (Tax from Oracle + Invoice)

* ``tax_invoice`` (AIVA-SYSA-ORA-01, legacy ``OracleMCPClient`` behaviour made safe)
    1. invoice spellings from config (``oracle.lookup.invoice_variants``)
    2. Supplier Tax ID = OCR value when readable + checksum-valid, else PO-SUPPLIER (Oracle)
    3. TAX-INV : Tax ID + any spelling, matched against SHIPMENT_NUM / PACKING_SLIP / WAYBILL
                 -> every receipt line of this invoice, across every PO and every receipt
    4. PO-LIST : fallback by the header PO when step 3 found nothing (``po_list_fallback``)

Business misses (nothing found, unsafe key) return an empty snapshot -> V-04 E05.  Technical
failures raise ``OracleTechnicalError`` -> SYSTEM_ERROR, never E05.  Results are memoised per
round and the number of queries is capped by ``oracle.max_queries_per_round``.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from ..domain.contracts import OracleInputRejected, OracleSnapshot, OracleTechnicalError
from ..domain.normalize import Invalid, tax_id
from ..domain.ports import OracleRepository
from .invoice_variants import build_variants

LEGACY_MODE, TAX_MODE = "legacy_po_invoice", "tax_invoice"
MODES = (LEGACY_MODE, TAX_MODE)
DEFAULT_MATCH_COLUMNS = ("SHIPMENT_NUM", "PACKING_SLIP", "WAYBILL_AIRBILL_NUM")
_TAX_SHAPE = re.compile(r"^\d{13}$")
_PO_SHAPE = re.compile(r"^\d{8}$")
# ReceiptRow attribute that carries each receipt-header column
_COLUMN_ATTR = {"SHIPMENT_NUM": "shipment_num", "PACKING_SLIP": "packing_slip", "WAYBILL_AIRBILL_NUM": "waybill_num"}


class QueryBudgetExceeded(OracleTechnicalError):
    """More Oracle queries than ``max_queries_per_round`` were requested (a code defect, not data)."""


def lookup_mode(policy: dict) -> str:
    """The configured mode; a Standard without the key behaves as before ORA-01."""
    mode = str(((policy.get("oracle") or {}).get("lookup") or {}).get("mode") or LEGACY_MODE)
    if mode not in MODES:
        raise OracleTechnicalError(f"UNKNOWN_LOOKUP_MODE:{mode}")
    return mode


def valid_supplier_tax(value: object) -> Optional[str]:
    """13 digits with a valid Thai check digit, else None (never queried with a bad Tax ID)."""
    s = str(value or "").strip()
    if not _TAX_SHAPE.match(s):
        return None
    try:
        return tax_id(s)
    except Invalid:
        return None


class OracleSession:
    def __init__(self, repo: OracleRepository, row_cap: int, *, max_queries: Optional[int] = None,
                 lookup_cfg: Optional[dict] = None):
        self.repo, self.row_cap, self.calls, self._memo = repo, row_cap, 0, {}
        self.rejected: list[dict] = []
        self.max_queries = max_queries
        self.cfg = dict(lookup_cfg or {})
        self.trace: list[str] = []                      # query ids in execution order (audit + tests)

    def _call(self, name, fn, *args):
        key = (name, args)
        if key not in self._memo:
            if self.max_queries is not None and self.calls >= self.max_queries:
                raise QueryBudgetExceeded(f"QUERY_BUDGET_EXCEEDED:{self.max_queries}")
            self.calls += 1
            self.trace.append(name)
            try:
                self._memo[key] = fn(*args)
            except OracleInputRejected as e:                     # key shape rejected: never queried Oracle
                self.rejected.append({"query_id": name, "reason": str(e),
                                      "args": [str(a) for a in args]})
                raise
            except OracleTechnicalError:
                raise
            except Exception as e:  # any driver error is technical, never business
                raise OracleTechnicalError(f"{type(e).__name__}: {e}") from e
        return self._memo[key]

    # ------------------------------------------------------------------ legacy (unchanged)
    def lookup(self, po_number: str, invoice_num: str) -> OracleSnapshot:
        keys = {"po_number": po_number, "invoice_num": invoice_num}
        rows, path = self._call("RCV-V01", self.repo.rcv_v01, po_number, invoice_num), "RCV-V01"
        if not rows:
            tax = self._call("PO-SUPPLIER", self.repo.supplier_tax_by_po, po_number)
            if tax:
                keys["supplier_tax_id"] = tax
                rows2 = self._call("RCV-V02", self.repo.rcv_v02, tax, invoice_num)
                if rows2:
                    rows, path = rows2, "RCV-V02"
        return OracleSnapshot(queried_at=datetime.now(timezone.utc).isoformat(), lookup_path=path if rows else None,
                              query_keys=keys, rows=tuple(rows), row_cap_hit=len(rows) >= self.row_cap,
                              calls=self.calls)

    # ------------------------------------------------------------------ AIVA-SYSA-ORA-01
    def lookup_tax_invoice(self, invoice_num: str, *, ocr_supplier_tax_id: Optional[str] = None,
                           po_number: Optional[str] = None) -> OracleSnapshot:
        """Tax ID + Invoice across every PO.  ``ocr_supplier_tax_id`` / ``po_number`` are passed only
        when the domain marked them readable (``ok``); either may be None."""
        variants = build_variants(invoice_num, self.cfg.get("invoice_variants") or ())
        po = po_number if po_number and _PO_SHAPE.match(str(po_number)) else None
        keys: dict = {"invoice_num": invoice_num, "invoice_variants": variants, "po_number": po,
                      "supplier_tax_id": None, "supplier_tax_id_source": None}
        if not variants:
            # An invoice number that cannot become a safe SQL literal is never sent (no PO fallback
            # either: without the invoice key a PO-wide search would return unrelated receipts).
            keys["invoice_rejected"] = True
            return self._snapshot(keys, [], None, variants)

        tax, source = None, None
        if self.cfg.get("use_ocr_supplier_tax_id", True):
            tax = valid_supplier_tax(ocr_supplier_tax_id)
            source = "ocr" if tax else None
        if tax is None and po:
            from_oracle = self._call("PO-SUPPLIER", self.repo.supplier_tax_by_po, po)
            tax = valid_supplier_tax(from_oracle)           # NUM_1099 / foreign IDs are not queried
            source = "oracle_po" if tax else None
            if from_oracle and not tax:
                keys["supplier_tax_id_unusable"] = str(from_oracle)
        keys.update(supplier_tax_id=tax, supplier_tax_id_source=source)

        rows, path = [], None
        if tax:
            rows = list(self._call("TAX-INV", self.repo.receipts_by_tax_invoice, tax, tuple(variants)))
            path = "TAX-INV" if rows else None
        if not rows and po and self.cfg.get("po_list_fallback", True):
            rows = list(self._call("PO-LIST", self.repo.receipts_by_po_list, (po,)))
            path = "PO-LIST" if rows else None
        return self._snapshot(keys, rows, path, variants)

    def _snapshot(self, keys: dict, rows: list, path: Optional[str], variants: list) -> OracleSnapshot:
        return OracleSnapshot(queried_at=datetime.now(timezone.utc).isoformat(), lookup_path=path,
                              query_keys=keys, rows=tuple(rows), row_cap_hit=len(rows) >= self.row_cap,
                              calls=self.calls,
                              po_numbers=tuple(sorted({r.po_number for r in rows if r.po_number})),
                              matched_on_column=matched_column(rows, variants, self.cfg.get("invoice_match_columns")))


def matched_column(rows, variants, columns=None) -> Optional[str]:
    """First configured receipt column whose value equals one of the invoice spellings."""
    want = {str(v).upper() for v in variants or ()}
    for col in columns or DEFAULT_MATCH_COLUMNS:
        attr = _COLUMN_ATTR.get(str(col).upper())
        if attr and any(str(getattr(r, attr, None) or "").upper() in want for r in rows):
            return str(col).upper()
    return None
