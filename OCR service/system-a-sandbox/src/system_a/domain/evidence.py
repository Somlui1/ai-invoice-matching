"""Evidence-based field acceptance ("a value is trusted when something independent confirms it").

Background (98-document Paperless run, 2026-10-07): every DMS page had no text layer, so the
reader-agreement gate (VLM page read == zoomed crop) was the only way a field became ``ok``.
Correct invoices were rejected wholesale (E01 on 77/98) although their numbers closed exactly
and matched Oracle.  The legacy AIVA app reached >80 % correct verdicts by trusting values that
*reconcile* instead of values that *two readers agree on*.  This module brings that idea in
without its weaknesses (no forced line pairing, no digit concatenation, no Oracle value copied
into the invoice):

    A  reader agreement           (unchanged, normalize._nfield)
    B  arithmetic closes          qty x price = amount · sum(amount) = sub_total · sub+vat = grand
    C  equals Oracle              invoice_num / PO / Tax IDs / matched receipt line price, qty, amount
    D  covered by a stronger key  customer name/address when the customer Tax ID equals Oracle

Rules:
* only a value the reader actually produced can be promoted; ``null_reason`` must be one of
  PROMOTABLE (a *read* that was merely unconfirmed).  NOT_PRESENT / INVALID_FORMAT never are.
* a promotion never changes ``value`` — except ``derive_qty_from_amount``, which is computed from
  two promoted cells of the same line and must also equal the receipt quantity.
* every promotion is recorded in ``NField.evidence`` and surfaced by the orchestrator in V-01 data.
All switches live in ``policy.yaml -> evidence`` and default to OFF when the key is absent.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Iterable, Optional

from .contracts import InvoiceDoc, NField, NLine, OracleSnapshot
from .standard import Standard

PROMOTABLE = {"CONFLICT_BETWEEN_SOURCES", "LOW_CONFIDENCE"}
Q2 = Decimal("0.01")
COVERED_TAG = "covered_by_customer_tax_id"


def enabled(std: Standard, name: str) -> bool:
    return bool((std.policy.get("evidence") or {}).get(name, False))


def _promote(f: Optional[NField], tag: str) -> Optional[NField]:
    if f is None or f.ok or f.value is None or f.null_reason not in PROMOTABLE:
        return f
    return replace(f, ok=True, null_reason=None, evidence=tuple(f.evidence) + (tag,))


def _val(f: Optional[NField]):
    """Value of a field that was read (ok or promotable), else None."""
    if f is None or f.value is None:
        return None
    return f.value if (f.ok or f.null_reason in PROMOTABLE) else None


def _dec(v) -> Optional[Decimal]:
    try:
        return v if isinstance(v, Decimal) else (Decimal(str(v)) if v is not None else None)
    except Exception:
        return None


def _with_cells(line: NLine, **cells) -> NLine:
    new = dict(line.cells)
    new.update({k: v for k, v in cells.items() if v is not None})
    return replace(line, cells=new)


def _rebuild(doc: InvoiceDoc, fields: dict, lines: Iterable[NLine]) -> InvoiceDoc:
    return replace(doc, fields=fields, lines=tuple(lines))


# ======================================================================== printed copies
def collapse_repeated_copies(doc: InvoiceDoc, std: Standard) -> tuple[InvoiceDoc, Optional[dict]]:
    """Original + copy pages read as one table: the line list is k identical blocks and
    sum(amount) == k x sub_total.  Keep the first block (measured: DMS-39 x3, DMS-88/104 x2).

    Identity of a block = (qty, unit_price, amount) of every line in order; descriptions are not
    compared (OCR spells them differently per copy).  Without a readable sub_total nothing is done.
    """
    if not enabled(std, "collapse_repeated_copies"):
        return doc, None
    lines = list(doc.lines)
    sub = _dec(_val(doc.fields.get("sub_total")))
    n = len(lines)
    if n < 2 or sub is None or sub <= 0:
        return doc, None
    sig = [tuple(_dec(_val(l.cells.get(k))) for k in ("qty", "unit_price", "amount")) for l in lines]
    amounts = [s_[2] for s_ in sig]
    if None in amounts:
        return doc, None
    total = sum(amounts, Decimal(0))
    tol = std.tol("total")
    for k in range(n, 1, -1):
        if n % k:
            continue
        size = n // k
        blocks = [sig[i * size:(i + 1) * size] for i in range(k)]
        if all(b == blocks[0] for b in blocks) and abs(total - k * sub) <= tol * k \
                and abs(sum(amounts[:size], Decimal(0)) - sub) <= tol:
            kept = tuple(lines[:size])
            note = {"copies": k, "kept_line_nos": [l.line_no for l in kept],
                    "dropped_line_nos": [l.line_no for l in lines[size:]],
                    "rule": "k identical (qty, unit_price, amount) blocks and sum(amount) = k x sub_total"}
            return replace(doc, lines=kept), note
    return doc, None


# ======================================================================== B — arithmetic
def corroborate_arithmetic(doc: InvoiceDoc, std: Standard) -> InvoiceDoc:
    if not enabled(std, "arithmetic"):
        return doc
    tol_line, tol_total, tol_vat = std.tol("line_math"), std.tol("total"), std.tol("vat")
    rate = std.tol("vat_rate")

    lines = []
    for l in doc.lines:
        q, p, a = (_dec(_val(l.cells.get(k))) for k in ("qty", "unit_price", "amount"))
        if None not in (q, p, a) and abs((q * p).quantize(Q2) - a) <= tol_line and a != 0:
            tag = "arith:qty*unit_price=amount"
            l = _with_cells(l, qty=_promote(l.cells.get("qty"), tag),
                            unit_price=_promote(l.cells.get("unit_price"), tag),
                            amount=_promote(l.cells.get("amount"), tag))
        lines.append(l)

    f = dict(doc.fields)
    sub, vat, grand = (_dec(_val(f.get(k))) for k in ("sub_total", "vat", "grand_total"))
    if None not in (sub, vat, grand) and sub > 0 \
            and abs(sub + vat - grand) <= tol_total and abs((sub * rate).quantize(Q2) - vat) <= tol_vat:
        tag = "arith:sub_total+vat=grand_total"
        for k in ("sub_total", "vat", "grand_total"):
            f[k] = _promote(f.get(k), tag)

    amounts = [_dec(_val(l.cells.get("amount"))) for l in lines]
    if lines and None not in amounts and sub is not None and sub > 0 \
            and abs(sum(amounts, Decimal(0)) - sub) <= tol_total:
        tag = "arith:sum(amount)=sub_total"
        f["sub_total"] = _promote(f.get("sub_total"), tag)
        lines = [_with_cells(l, amount=_promote(l.cells.get("amount"), tag)) for l in lines]
    return _rebuild(doc, f, lines)


# ======================================================================== C/D — Oracle header
def _norm_key(s) -> str:
    return "".join(ch for ch in str(s or "").upper() if ch.isalnum())


def corroborate_oracle(doc: InvoiceDoc, snap: Optional[OracleSnapshot], std: Standard) -> InvoiceDoc:
    if not enabled(std, "oracle") or snap is None or not snap.active:
        return doc
    rows = snap.active
    f = dict(doc.fields)

    # invoice number: the receipt was found by it (shipment / packing slip / waybill, any spelling)
    inv = _val(f.get("invoice_num"))
    if inv is not None:
        keys = {_norm_key(inv)} | {_norm_key(v) for v in (snap.query_keys or {}).get("invoice_variants") or ()}
        stored = set()
        for r in rows:
            stored |= {_norm_key(r.shipment_num), _norm_key(r.packing_slip), _norm_key(r.waybill_num),
                       _norm_key(r.extra.get("SHIPMENT_NUM")), _norm_key(r.extra.get("PACKING_SLIP"))}
        by_query = snap.lookup_path in ("RCV-V01", "RCV-V02")   # legacy queries bind the invoice itself
        if by_query or (keys & (stored - {""})):
            f["invoice_num"] = _promote(f.get("invoice_num"), "oracle:receipt_found_by_invoice_num")

    po = _val(f.get("po_number"))
    if po is not None:
        pos = set(snap.po_numbers or ()) | {r.po_number for r in rows if r.po_number} \
            | {r.extra.get("PO_NUM") for r in rows if r.extra.get("PO_NUM")}
        if str(po) in {str(x) for x in pos}:
            f["po_number"] = _promote(f.get("po_number"), "oracle:po_on_receipt")

    sup = _val(f.get("supplier_tax_id"))
    if sup is not None:
        sups = {r.supplier_tax_id for r in rows if r.supplier_tax_id}
        if (snap.query_keys or {}).get("supplier_tax_id"):
            sups.add(snap.query_keys["supplier_tax_id"])
        if str(sup) in sups:
            f["supplier_tax_id"] = _promote(f.get("supplier_tax_id"), "oracle:supplier_tax_id")

    cust = _val(f.get("customer_tax_id"))
    ent = std.entities.get(snap.org_id) if snap.org_id is not None else None
    oracle_cust = {r.customer_tax_id for r in rows if r.customer_tax_id}
    if ent and ent.get("tax_id"):
        oracle_cust.add(ent["tax_id"])
    if cust is not None and str(cust) in oracle_cust:
        f["customer_tax_id"] = _promote(f.get("customer_tax_id"), "oracle:customer_tax_id")
        if enabled(std, "customer_identity_by_tax_id") and f["customer_tax_id"].ok:
            for k in ("customer_name", "customer_address"):
                g = f.get(k)
                if g is not None and not g.ok:
                    f[k] = _promote(g, COVERED_TAG)
    return _rebuild(doc, f, doc.lines)


def is_covered(field: Optional[NField]) -> bool:
    return bool(field is not None and COVERED_TAG in (field.evidence or ()))


# ======================================================================== C — matched receipt lines
def corroborate_lines(doc: InvoiceDoc, groups, rows: dict, std: Standard) -> InvoiceDoc:
    """After V-07 pairing: unit (inherit / confirm), price, qty, amount equal to the matched receipt."""
    if not enabled(std, "oracle"):
        return doc
    by_no = {l.line_no: l for l in doc.lines}
    tol_line, p_exact = std.tol("line_math"), std.tol("price_exact")
    for g in groups:
        if g.relation == "UNMATCHED" or not g.rcv_line_ids:
            continue
        rcv = [rows[i] for i in g.rcv_line_ids if i in rows]
        if not rcv:
            continue
        rcv_groups = {std.uom_group(r.uom) for r in rcv}
        ids = ",".join(g.rcv_line_ids)
        for n in g.invoice_line_nos:
            l = by_no[n]
            cells = {}
            # ---- unit of measure
            u = l.cells.get("uom")
            if len(rcv_groups) == 1 and (u is None or not u.ok):
                rg = next(iter(rcv_groups))
                raw_group = std.uom_group(u.raw) if (u is not None and u.raw) else None
                known = raw_group in std.uom_groups
                if raw_group == rg and u.null_reason in PROMOTABLE:
                    cells["uom"] = replace(u, value=rg, ok=True, null_reason=None,
                                           evidence=tuple(u.evidence) + ("oracle:uom_equals_receipt",))
                elif not known and enabled(std, "uom_inherit_from_receipt"):
                    base = u or NField("uom", f"{l.element_id}-uom", None, None, None, False, "NOT_PRESENT")
                    cells["uom"] = replace(base, value=rg, ok=True, null_reason=None,
                                           evidence=tuple(base.evidence) + (f"inherited_from_receipt:{ids}",))
            # ---- price / qty / amount (1:1 and 1:N only: N:1 shares one receipt line)
            if g.relation in ("1:1", "1:N"):
                rq = sum((r.qty for r in rcv), Decimal(0))
                ra = sum((r.line_amount for r in rcv), Decimal(0))
                prices = {r.unit_price for r in rcv}
                p = _dec(_val(l.cells.get("unit_price")))
                if p is not None and len(prices) == 1 and abs(p - next(iter(prices))) <= p_exact:
                    cells["unit_price"] = _promote(l.cells.get("unit_price"), f"oracle:po_price:{ids}")
                q = _dec(_val(l.cells.get("qty")))
                if q is not None and q == rq:
                    cells["qty"] = _promote(l.cells.get("qty"), f"oracle:receipt_qty:{ids}")
                a = _dec(_val(l.cells.get("amount")))
                if a is not None and abs(a - ra) <= tol_line:
                    cells["amount"] = _promote(l.cells.get("amount"), f"oracle:receipt_amount:{ids}")
            l = _with_cells(l, **cells)
            # ---- weight-billed lines: qty column holds pieces, amount = weight x price (DMS-102)
            if enabled(std, "derive_qty_from_amount") and g.relation in ("1:1", "1:N") \
                    and l.ok("unit_price") and l.ok("amount") and not l.ok("qty") and l.v("unit_price"):
                derived = (l.v("amount") / l.v("unit_price"))
                rq = sum((r.qty for r in rcv), Decimal(0))
                if abs(derived - rq) <= Decimal("0.001"):
                    qf = l.cells.get("qty") or NField("qty", f"{l.element_id}-qty", None, None, None, False,
                                                      "NOT_PRESENT")
                    l = _with_cells(l, qty=replace(qf, value=rq, ok=True, null_reason=None,
                                                   evidence=tuple(qf.evidence) + (
                                                       f"derived:amount/unit_price={rq}", f"oracle:receipt_qty:{ids}")))
            uf = l.cells.get("uom")
            by_no[n] = replace(l, uom_group=uf.value if uf is not None and uf.ok else l.uom_group)
    return replace(doc, lines=tuple(by_no[l.line_no] for l in doc.lines))


# ======================================================================== audit
def evidence_report(doc: InvoiceDoc) -> dict:
    out = {k: list(f.evidence) for k, f in doc.fields.items() if f.evidence}
    for l in doc.lines:
        for k, c in l.cells.items():
            if c.evidence:
                out[f"L{l.line_no}.{k}"] = list(c.evidence)
    return out
