"""Ports.  The domain depends on these Protocols only — adapters implement them."""
from __future__ import annotations

from typing import Optional, Protocol

from .contracts import ReceiptRow


class OracleRepository(Protocol):
    """Read-only, bind-variable queries registered in Standard Table 5."""

    def rcv_v01(self, po_number: str, invoice_num: str) -> list[ReceiptRow]: ...
    def supplier_tax_by_po(self, po_number: str) -> Optional[str]: ...
    def rcv_v02(self, supplier_tax_id: str, invoice_num: str) -> list[ReceiptRow]: ...

    # AIVA-SYSA-ORA-01 — Tax ID + Invoice, across several POs and receipts.  ``invoice_variants`` are
    # the config-generated spellings of one invoice number; the adapter compares them against the
    # configured receipt columns (SHIPMENT_NUM / PACKING_SLIP / WAYBILL_AIRBILL_NUM).
    # A backend that only implements the legacy trio (``OracleDbRepository``) offers neither method,
    # which is why container refuses ``mode: tax_invoice`` on that backend instead of failing later.
    def receipts_by_tax_invoice(self, supplier_tax_id: str, invoice_variants: list[str]) -> list[ReceiptRow]: ...
    def receipts_by_po_list(self, po_numbers: list[str]) -> list[ReceiptRow]: ...


class LineMatcherAI(Protocol):
    """V-07 M3/M4/M5 proposer.  Input/output follow config/prompts/v07_match.md."""

    def propose(self, invoice_lines: list[dict], receipt_lines: list[dict]) -> dict: ...


class QtyJudgeAI(Protocol):
    """V-08 judge.  Input/output follow config/prompts/v08_qty.md."""

    def judge(self, payload: dict) -> dict: ...


class EntityJudgeAI(Protocol):
    """V-05 helper.  Name equivalence + address key extraction (config/prompts/v05_entity.md)."""

    def name_equivalent(self, invoice_name: str, candidates: dict[str, str]) -> dict: ...
    def parse_address(self, address: str) -> dict: ...
