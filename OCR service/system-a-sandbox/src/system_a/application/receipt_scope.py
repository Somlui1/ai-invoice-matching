"""Scope a PO-LIST snapshot to the receipt(s) of THIS invoice (policy.oracle.lookup.po_list_narrowing).

Why: the PO-LIST fallback returns every receipt ever posted on the PO.  On milestone / repeat POs
that is many receipts (DMS-36: 21, DMS-40/47/64/65: 50 = row cap) and V-04 then raised E06
"more than one receipt" although the invoice itself belongs to one of them.  Measured on the
v2 batch: 8 documents held by an E06 that only says "the PO has history".

The narrowing never invents a pairing.  It keeps a receipt only on positive evidence, tried in
order, the first rule that yields a non-empty set wins:

  1. header key   SHIPMENT_NUM / PACKING_SLIP / WAYBILL equals a spelling of the invoice number
  2. amount       exactly one receipt whose active line total equals the invoice sub_total
  3. open         exactly one receipt that still has un-billed quantity (QTY_BILLED < QTY)

When none applies the snapshot is left whole and marked ``po_list_ambiguous``; V-04 then answers
``manual_review`` ("cannot tell which receipt") instead of E06 — the PO having several receipts is
not evidence that this invoice spans several receipts.  Every decision is written to
``query_keys.po_list_narrowing`` so the audit trail shows which receipts were set aside and why.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Optional

from ..domain import evidence as ev
from ..domain.contracts import InvoiceDoc, OracleSnapshot
from ..domain.standard import Standard


def _key(s) -> str:
    return "".join(ch for ch in str(s or "").upper() if ch.isalnum())


def enabled(std: Standard) -> bool:
    return bool(((std.policy.get("oracle") or {}).get("lookup") or {}).get("po_list_narrowing", False))


def narrow(snap: Optional[OracleSnapshot], doc: InvoiceDoc, std: Standard) -> Optional[OracleSnapshot]:
    if snap is None or not enabled(std) or snap.lookup_path != "PO-LIST" or len(snap.receipt_nums) <= 1:
        return snap
    active = snap.active
    by_rcv: dict = {}
    for r in active:
        by_rcv.setdefault(r.receipt_num, []).append(r)
    keys = {_key(v) for v in (snap.query_keys or {}).get("invoice_variants") or ()}
    keys |= {_key((snap.query_keys or {}).get("invoice_num"))}
    keys.discard("")

    chosen, rule = [], None
    hit = sorted(n for n, rs in by_rcv.items()
                 if any(_key(x) in keys for r in rs for x in (r.shipment_num, r.packing_slip, r.waybill_num,
                                                             (r.extra or {}).get("SHIPMENT_NUM"),
                                                             (r.extra or {}).get("PACKING_SLIP"))))
    if hit:
        chosen, rule = hit, "header_key_equals_invoice_num"
    if not chosen:
        sub = ev._dec(ev._val(doc.fields.get("sub_total")))
        if sub is not None and sub > 0:
            tol = std.tol("total")
            same = sorted(n for n, rs in by_rcv.items()
                          if abs(sum((r.line_amount for r in rs), Decimal(0)) - sub) <= tol)
            if len(same) == 1:
                chosen, rule = same, "receipt_total_equals_sub_total"
    if not chosen:
        open_ = sorted(n for n, rs in by_rcv.items() if any((r.qty_billed or 0) < r.qty for r in rs))
        if len(open_) == 1:
            chosen, rule = open_, "only_receipt_with_unbilled_qty"

    note = {"from_receipts": len(by_rcv), "from_rows": len(snap.rows), "rule": rule}
    if not chosen:
        note["result"] = "ambiguous"
        return replace(snap, query_keys={**(snap.query_keys or {}), "po_list_narrowing": note,
                                         "po_list_ambiguous": True})
    keep = set(chosen)
    rows = tuple(r for r in snap.rows if r.receipt_num in keep)
    # a capped result may have cut the kept receipt short: rows are ordered by RECEIPT_NUM, LINE_NUM,
    # so the kept receipt is complete unless it is the last receipt in the result
    last = max(r.receipt_num for r in snap.rows)
    capped = snap.row_cap_hit and last in keep
    note.update(result="narrowed", kept_receipts=sorted(keep),
                set_aside_receipts=sorted(set(by_rcv) - keep), row_cap_hit_before=snap.row_cap_hit)
    return replace(snap, rows=rows, row_cap_hit=capped,
                   po_numbers=tuple(sorted({r.po_number for r in rows if r.po_number})),
                   query_keys={**(snap.query_keys or {}), "po_list_narrowing": note})
