"""Oracle repositories.

* ``OracleDbRepository``  — production: python-oracledb, read-only replica, BIND VARIABLES ONLY (Standard Table 5).
* ``InMemoryOracleRepository`` — sandbox/tests: same interface, data from JSON, counts calls, can simulate outage.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from ...domain.contracts import OracleTechnicalError, ReceiptRow
from .sql_guard import WHITELIST, check_keys

# Standard v6.6 Table 5 — RCV-V01 (registered, bind variables only)
RCV_V01 = """
SELECT ph.ORG_ID AS ORG_ID, h.RECEIPT_NUM AS RECEIPT_NUM, v.RECEIVER AS RECEIVER, l.LINE_NUM AS LINE,
       l.ITEM_DESCRIPTION AS ITEM, l.QUANTITY_RECEIVED AS QTY, l.UNIT_OF_MEASURE AS UOM,
       pl.UNIT_PRICE AS UNIT_PRICE, l.QUANTITY_RECEIVED * pl.UNIT_PRICE AS LINE_AMOUNT
FROM PO.RCV_SHIPMENT_LINES l
JOIN PO.RCV_SHIPMENT_HEADERS h ON h.SHIPMENT_HEADER_ID = l.SHIPMENT_HEADER_ID
JOIN PO.PO_LINES_ALL pl ON pl.PO_LINE_ID = l.PO_LINE_ID
JOIN PO.PO_HEADERS_ALL ph ON ph.PO_HEADER_ID = l.PO_HEADER_ID
JOIN APPS.RCV_VRC_HDS_V v ON v.SHIPMENT_HEADER_ID = h.SHIPMENT_HEADER_ID
WHERE v.SHIPMENT_NUM = :p_invoice_num AND ph.SEGMENT1 = :p_po_number
ORDER BY l.LINE_NUM FETCH FIRST 50 ROWS ONLY"""

# CR-01 (pending registration in Table 5) — RCV-V02 fallback
PO_SUPPLIER_TAX = """
SELECT COALESCE(pv.VAT_REGISTRATION_NUM, pv.NUM_1099) AS SUPPLIER_TAX_ID
FROM PO.PO_HEADERS_ALL ph JOIN APPS.PO_VENDORS pv ON pv.VENDOR_ID = ph.VENDOR_ID
WHERE ph.SEGMENT1 = :p_po_number FETCH FIRST 1 ROWS ONLY"""

RCV_V02 = """
SELECT ph.ORG_ID AS ORG_ID, h.RECEIPT_NUM AS RECEIPT_NUM, v.RECEIVER AS RECEIVER, l.LINE_NUM AS LINE,
       l.ITEM_DESCRIPTION AS ITEM, l.QUANTITY_RECEIVED AS QTY, l.UNIT_OF_MEASURE AS UOM,
       pl.UNIT_PRICE AS UNIT_PRICE, l.QUANTITY_RECEIVED * pl.UNIT_PRICE AS LINE_AMOUNT
FROM PO.RCV_SHIPMENT_LINES l
JOIN PO.RCV_SHIPMENT_HEADERS h ON h.SHIPMENT_HEADER_ID = l.SHIPMENT_HEADER_ID
JOIN PO.PO_LINES_ALL pl ON pl.PO_LINE_ID = l.PO_LINE_ID
JOIN PO.PO_HEADERS_ALL ph ON ph.PO_HEADER_ID = l.PO_HEADER_ID
JOIN APPS.RCV_VRC_HDS_V v ON v.SHIPMENT_HEADER_ID = h.SHIPMENT_HEADER_ID
JOIN APPS.PO_VENDORS pv ON pv.VENDOR_ID = ph.VENDOR_ID
WHERE v.SHIPMENT_NUM = :p_invoice_num
  AND COALESCE(pv.VAT_REGISTRATION_NUM, pv.NUM_1099) = :p_supplier_tax_id
ORDER BY h.RECEIPT_NUM, l.LINE_NUM FETCH FIRST 50 ROWS ONLY"""


EXTRA_COLUMNS = ("PO_NUM", "ITEM_CODE", "SHIPMENT_NUM", "PACKING_SLIP", "QTY_BILLED", "MATCH_MODE")

# AIVA-SYSA-ORA-01 — the receipt columns an invoice number may live in (Standard Table 12 #3).
INVOICE_COLUMNS = ("SHIPMENT_NUM", "PACKING_SLIP", "WAYBILL_AIRBILL_NUM")


def _get(d: dict, *keys):
    for k in keys:
        v = d.get(k) if k in d else d.get(k.lower())
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return None


def _opt_int(d: dict, *keys):
    v = _get(d, *keys)
    return int(float(v)) if v and v.replace(".", "").isdigit() else None


def _dec(v, default="0") -> Decimal:
    return Decimal(str(v if v is not None and str(v).strip() != "" else default).replace(",", "").strip())


def _row(d: dict, extended: bool = False) -> ReceiptRow:
    """Map a result row (dataset dict or driver row) onto ``ReceiptRow``.

    ``extended`` belongs to the AIVA-SYSA-ORA-01 queries only: the legacy RCV-V01 / RCV-V02 rows keep
    the shape they always had (extra columns stay in ``extra``), so their audit payload — and the
    integrity hash of every document they find — does not move.
    """
    g = lambda k: d.get(k) if k in d else d.get(k.lower())
    extra = {k: g(k) for k in EXTRA_COLUMNS if g(k) not in (None, "")}
    qty, price = _dec(g("QTY")), _dec(g("UNIT_PRICE"))
    opt = dict(
        po_number=_get(d, "PO_NUM", "PO_NUMBER"), item_code=_get(d, "ITEM_CODE"),
        qty_billed=_dec(g("QTY_BILLED")), po_line_status=_get(d, "PO_LINE_STATUS"),
        line_status=_get(d, "LINE_STATUS"), supplier_tax_id=_get(d, "SUPPLIER_TAX_ID"),
        supplier_name=_get(d, "SUPPLIER_NAME"), customer_tax_id=_get(d, "CUSTOMER_TAX_ID"),
        ou_org_id=_opt_int(d, "OU_ORG_ID"), ou_name=_get(d, "OU_NAME"),
        shipment_num=_get(d, "SHIPMENT_NUM"), packing_slip=_get(d, "PACKING_SLIP"),
        waybill_num=_get(d, "WAYBILL_AIRBILL_NUM", "WAYBILL_NUM")) if extended else {}
    return ReceiptRow(org_id=int(g("ORG_ID")) if g("ORG_ID") is not None else None, receipt_num=str(g("RECEIPT_NUM")),
                      receiver=g("RECEIVER"), line=int(g("LINE")), item=str(g("ITEM") or ""),
                      qty=qty, uom=str(g("UOM") or ""), unit_price=price,
                      line_amount=_dec(g("LINE_AMOUNT")) if g("LINE_AMOUNT") not in (None, "") else (qty * price),
                      extra=extra, **opt)


class OracleDbRepository:
    """Requires `pip install oracledb` and a read-only service account (Decision Log §7.3)."""

    def __init__(self, dsn: str, user: str, password: str, timeout_s: int = 15):
        try:
            import oracledb  # noqa: WPS433
        except ImportError as e:  # pragma: no cover
            raise OracleTechnicalError("python-oracledb not installed") from e
        self._pool = oracledb.create_pool(user=user, password=password, dsn=dsn, min=1, max=4)
        self._timeout_ms = timeout_s * 1000

    def _q(self, sql: str, **binds) -> list[dict]:  # pragma: no cover - needs a live DB
        with self._pool.acquire() as con:
            con.call_timeout = self._timeout_ms
            with con.cursor() as cur:
                cur.execute(sql, **binds)
                cols = [c[0] for c in cur.description]
                return [dict(zip(cols, r)) for r in cur.fetchall()]

    def rcv_v01(self, po_number, invoice_num):  # pragma: no cover
        return [_row(r) for r in self._q(RCV_V01, p_invoice_num=invoice_num, p_po_number=po_number)]

    def supplier_tax_by_po(self, po_number) -> Optional[str]:  # pragma: no cover
        r = self._q(PO_SUPPLIER_TAX, p_po_number=po_number)
        return r[0]["SUPPLIER_TAX_ID"] if r else None

    def rcv_v02(self, supplier_tax_id, invoice_num):  # pragma: no cover
        return [_row(r) for r in self._q(RCV_V02, p_invoice_num=invoice_num, p_supplier_tax_id=supplier_tax_id)]


class InMemoryOracleRepository:
    """dataset = {"receipts": [{po_number, invoice_num, supplier_tax_id, rows: [...]}], "po_supplier": {po: tax}}"""

    def __init__(self, dataset: dict, *, down: bool = False):
        self.data, self.down, self.calls = dataset, down, []

    def _chk(self, name, *a):
        self.calls.append((name, a))
        if self.down:
            raise OracleTechnicalError("ORA-12170: TNS:Connect timeout occurred (simulated)")

    def rcv_v01(self, po_number, invoice_num):
        check_keys(po_number=po_number, invoice_num=invoice_num)      # never query with a malformed key
        self._chk("RCV-V01", po_number, invoice_num)
        return [_row(r) for e in self.data.get("receipts", [])
                if e["po_number"] == po_number and e["invoice_num"] == invoice_num for r in e["rows"]]

    def supplier_tax_by_po(self, po_number):
        check_keys(po_number=po_number)
        self._chk("PO-SUPPLIER", po_number)
        return self.data.get("po_supplier", {}).get(po_number)

    def rcv_v02(self, supplier_tax_id, invoice_num):
        check_keys(tax_id=supplier_tax_id, invoice_num=invoice_num)
        self._chk("RCV-V02", supplier_tax_id, invoice_num)
        return [_row(r) for e in self.data.get("receipts", [])
                if e.get("supplier_tax_id") == supplier_tax_id and e["invoice_num"] == invoice_num for r in e["rows"]]

    # ---- AIVA-SYSA-ORA-01: Tax ID + Invoice (several POs, several receipts) --------------------
    def _entry_columns(self, e: dict) -> dict:
        """The receipt-header columns an invoice number can be found in, for one dataset entry.

        A dataset entry may pin them explicitly (``invoice_columns``); otherwise its own
        ``invoice_num`` stands for SHIPMENT_NUM, which is how the pre-existing S01–S19 datasets read.
        """
        cols = {c: None for c in INVOICE_COLUMNS}
        cols.update({str(k).upper(): (str(v).strip() or None) for k, v in (e.get("invoice_columns") or {}).items()
                     if str(k).upper() in cols})
        if not any(cols.values()) and e.get("invoice_num"):
            cols["SHIPMENT_NUM"] = str(e["invoice_num"]).strip()
        return cols

    def receipts_by_tax_invoice(self, supplier_tax_id, invoice_variants):
        check_keys(tax_id=supplier_tax_id)                    # never "query" with a malformed key
        want = {str(v).strip() for v in (invoice_variants or []) if str(v).strip()}
        self._chk("TAX-INV", supplier_tax_id, tuple(sorted(want)))
        out = []
        for e in self.data.get("receipts", []):
            if e.get("supplier_tax_id") != supplier_tax_id:
                continue
            cols = self._entry_columns(e)
            if not ({v for v in cols.values() if v} & want):
                continue
            out += [_row({**r, **{k: v for k, v in cols.items() if _get(r, k) is None}}, extended=True)
                    for r in e["rows"]]
        return out

    def receipts_by_po_list(self, po_numbers):
        pos = {str(p).strip() for p in (po_numbers or []) if str(p).strip()}
        for p in sorted(pos):
            check_keys(po_number=p)
        self._chk("PO-LIST", tuple(sorted(pos)))
        out = []
        for e in self.data.get("receipts", []):
            if str(e.get("po_number")) not in pos:
                continue
            out += [_row({**r, **({"PO_NUM": e["po_number"]} if _get(r, "PO_NUM") is None else {})}, extended=True)
                    for r in e["rows"]]
        return out
