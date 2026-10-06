"""Production Oracle backend for the ORDS MCP JSON-RPC endpoint (``sql_run``).

System A's port (``OracleRepository``) is implemented here without a DB driver: the ORDS
MCP server accepts a *SQL string*, so bind variables are emulated by ``bind_literal()``
which only accepts whitelist-shaped values and escapes ``'`` -> ``''``.  Anything that is
not whitelist-clean is never sent to Oracle (``OracleInputRejected`` -> INPUT_REJECTED).

Guarantees enforced in code (Standard v6.6 safety rules + Decision Log §7.3):
* only ``SELECT`` / ``WITH`` statements can leave this module (``ensure_read_only``)
* every statement carries a row cap (``FETCH FIRST n ROWS ONLY``)
* any transport / protocol / driver error becomes ``OracleTechnicalError`` — never E05
* every statement + duration + row count is appended to ``self.audit`` (no secrets, no payload)
"""
from __future__ import annotations

import csv
import io
import json
import re
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx

from ...domain.contracts import OracleInputRejected, OracleTechnicalError, ReceiptRow
from .repositories import _row as _repo_row
from .sql_guard import (INVOICE_VARIANT_LIMIT, WHITELIST, bind_literal, check_keys, ensure_read_only,
                        invoice_variants, render_in_list, render_sql, strip_sql_comments)

__all__ = ["McpSqlClient", "OracleMcpRepository", "OracleInputRejected", "RCV_V01", "RCV_V02",
           "PO_SUPPLIER_TAX", "bind_literal", "ensure_read_only", "invoice_variants", "parse_csv_rows",
           "parse_mcp_payload", "parse_mcp_result_data", "render_in_list", "render_sql", "row_from_csv",
           "WHITELIST", "INVOICE_VARIANT_LIMIT", "strip_sql_comments", "PO_LIST", "tax_inv_sql"]


# ------------------------------------------------------------------------------------ protocol
def parse_mcp_payload(raw: str) -> str:
    """Extract the text content of a ``tools/call`` answer.

    The ORDS MCP server answers either as a plain JSON-RPC object or as an SSE stream of
    ``data: {...}`` lines, and reports an empty result set as the literal text
    ``no rows selected`` (mapped to "" == zero rows).
    """
    text = (raw or "").strip()
    if not text:
        return ""

    def content_of(data: dict) -> Optional[str]:
        if "error" in data and data.get("error"):
            err = data["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            code = err.get("code") if isinstance(err, dict) else ""
            raise OracleTechnicalError(f"MCP_ERROR {code}: {str(msg)[:300]}")
        res = data.get("result")
        if not isinstance(res, dict):
            return None
        if res.get("isError"):
            txt = ""
            for c in res.get("content") or []:
                txt += str(c.get("text", ""))
            raise OracleTechnicalError(f"MCP_TOOL_ERROR: {txt[:300]}")
        for c in res.get("content") or []:
            if isinstance(c, dict) and c.get("text") is not None:
                return str(c["text"])
        return None

    def from_json(chunk: str) -> Optional[str]:
        try:
            data = json.loads(chunk)
        except json.JSONDecodeError:
            return None
        return content_of(data) if isinstance(data, dict) else None

    got = from_json(text)
    if got is None and "data:" in text:                     # SSE framing
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            got = from_json(line[5:].strip())
            if got is not None:
                break
    if got is None:
        raise OracleTechnicalError(f"MCP_PROTOCOL: unparsable response {text[:160]!r}")
    if "no rows selected" in got.lower():
        return ""
    return got


def parse_mcp_result_data(raw: str) -> dict:
    """Extract the ``result`` payload of a non-``tools/call`` answer (``tools/list``, ``initialize``).

    ``tools/list`` carries no ``content`` array — the payload is ``result.tools`` — and the endpoint
    answers with the same dual framing (bare JSON-RPC object or SSE ``data:`` lines) as ``sql_run``.
    """
    text = (raw or "").strip()

    def candidate(chunk: str) -> Optional[dict]:
        try:
            data = json.loads(chunk)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        if data.get("error"):
            err = data["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise OracleTechnicalError(f"MCP_ERROR: {str(msg)[:300]}")
        res = data.get("result")
        return res if isinstance(res, dict) else None

    got = candidate(text)
    if got is None and "data:" in text:
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                got = candidate(line[5:].strip())
                if got is not None:
                    break
    if got is None:
        raise OracleTechnicalError(f"MCP_PROTOCOL: unparsable response {text[:160]!r}")
    return got


# SQL*Plus / ORDS footer: "12 rows selected." is appended after the CSV body.  Parsed naively it turns
# into one phantom row (measured on the real endpoint: 12 receipt lines became 13) — see runs/sql_registry.md.
FOOTER_ROW = re.compile(r"^\s*\d+\s+rows?\s+selected\.?\s*$", re.I)


def strip_sqlplus_footer(text: str) -> str:
    return "\n".join(l for l in (text or "").splitlines() if not FOOTER_ROW.match(l))


def csv_header(text: str) -> list[str]:
    line = next((l for l in (text or "").splitlines() if l.strip()), "")
    try:
        return [str(c or "").strip().upper() for c in next(csv.reader([line]))]
    except Exception:
        return []


def parse_csv_rows(text: str, expect: tuple[str, ...] | None = None) -> list[dict]:
    """Parse the MCP CSV result.  Zero rows is ""; a body that is not a result table is an error.

    ``expect`` guards against treating a transport page (HTML error, stack trace) as "no receipts",
    which would silently produce a false E05.
    """
    if not text or not text.strip() or "no rows selected" in text.lower():
        return []
    body = strip_sqlplus_footer(text)
    if expect:
        head = set(csv_header(body))
        if not head & {e.upper() for e in expect}:
            raise OracleTechnicalError(
                f"MCP_PROTOCOL: result has no expected column {sorted(expect)[:3]} — got {sorted(head)[:6]}")
    rows = []
    for raw in csv.DictReader(io.StringIO(body.strip())):
        vals = list(raw.values())
        if not vals or all(v in (None, "") for v in vals):     # footer remnant / blank line, never a receipt
            continue
        rows.append(dict(raw))
    return rows


class McpSqlClient:
    """Minimal JSON-RPC client for ORDS MCP ``sql_run`` (retry on transport only)."""

    def __init__(self, url: str, token: str = "", *, timeout_s: float = 60.0, retries: int = 2,
                 max_inflight: int = 4, transport: Optional[httpx.BaseTransport] = None):
        self.url, self.token, self.timeout = (url or "").rstrip("/"), token, timeout_s
        self.retries = retries
        self._sem = threading.BoundedSemaphore(max(1, max_inflight))
        self._transport = transport                      # test seam

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def list_tools(self) -> list[dict]:
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        with self._sem, httpx.Client(timeout=self.timeout, transport=self._transport) as c:
            r = c.post(self.url, json=body, headers=self._headers())
            r.raise_for_status()
        return parse_mcp_result_data(r.text).get("tools", []) or []

    def run(self, sql: str, *, database: str = "default") -> str:
        """Execute a read-only statement and return the CSV text ("" = zero rows)."""
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "sql_run", "arguments": {"database": database, "sql": ensure_read_only(sql)}}}
        last: Optional[str] = None
        for attempt in range(self.retries + 1):
            try:
                with self._sem, httpx.Client(timeout=self.timeout, transport=self._transport) as c:
                    r = c.post(self.url, json=body, headers=self._headers())
                if r.status_code == 401 or r.status_code == 403:
                    raise OracleTechnicalError(f"MCP_AUTH: HTTP {r.status_code}")
                r.raise_for_status()
                return parse_mcp_payload(r.text)
            except OracleTechnicalError:
                raise                                   # protocol/auth/SQL error: retrying cannot help
            except Exception as e:                      # transport only
                last = f"{type(e).__name__}: {str(e) or 'no detail'}"
                if attempt < self.retries:
                    time.sleep(min(8, 2 ** attempt))
        raise OracleTechnicalError(f"MCP_TRANSPORT: {last}")


# ------------------------------------------------------------------------------------ SQL templates
# Standard v6.6 Table 5 (RCV-V01) — as executed against the real EBS schema; see runs/sql_registry.md
#
# Differences from the literal text in Table 5 (all measured, see sql_registry.md):
#   * invoice key column is RCV_SHIPMENT_HEADERS.SHIPMENT_NUM (Table 5 writes v.SHIPMENT_NUM on the
#     RCV_VRC_HDS_V view; the two carry the same value, the header column is the indexed one)
#   * MATCH_MODE reports which predicate matched, so "exact" vs "normalized" is measurable per document
#   * ORG_ID comes from PO_HEADERS_ALL (the operating unit used by Standard Table 4)
#   * extra informational columns (PO_NUM, ITEM_CODE, SHIPMENT_NUM, PACKING_SLIP, QTY_BILLED)
#
# Table 12 #3 (invoice-number format): 34% of the 1,290,756 receipt headers store SHIPMENT_NUM with a
# space, a slash or a lower-case letter, and 19% store it as a composite (e.g. 30492336-40120916-428 =
# INVOICE-PO-RELEASE).  An exact equality test therefore loses real receipts.  The predicates below add
# (2) a case/space/slash-insensitive equality and (3) a "prefix before the first dash" equality that is
# additionally required to contain the PO number, so it cannot invent a match.  No LIKE wildcards are
# used (the invoice whitelist allows "_", which would otherwise match any character).
INV_KEYS = ("h.SHIPMENT_NUM IN (:p_invoice_in)\n")
INV_PREFIX = ("     OR (INSTR(h.SHIPMENT_NUM, '-') > 0 AND INSTR(h.SHIPMENT_NUM, ph.SEGMENT1) > 0\n"
              "          AND UPPER(SUBSTR(h.SHIPMENT_NUM, 1, INSTR(h.SHIPMENT_NUM, '-') - 1)) = "
              "UPPER(:p_invoice_num))\n")
MATCH_MODE = ("CASE WHEN h.SHIPMENT_NUM = :p_invoice_num THEN 'EXACT'\n"
              "       WHEN h.SHIPMENT_NUM IN (:p_invoice_in) THEN 'NORMALIZED'\n"
              "       ELSE 'PREFIX' END AS MATCH_MODE")
_LINE_COLS = ("ph.ORG_ID AS ORG_ID, h.RECEIPT_NUM AS RECEIPT_NUM, v.RECEIVER AS RECEIVER, l.LINE_NUM AS LINE,\n"
              "       l.ITEM_DESCRIPTION AS ITEM, l.QUANTITY_RECEIVED AS QTY, l.UNIT_OF_MEASURE AS UOM,\n"
              "       pl.UNIT_PRICE AS UNIT_PRICE, l.QUANTITY_RECEIVED * pl.UNIT_PRICE AS LINE_AMOUNT,\n"
              "       ph.SEGMENT1 AS PO_NUM, msi.SEGMENT1 AS ITEM_CODE, h.SHIPMENT_NUM AS SHIPMENT_NUM,\n"
              "       h.PACKING_SLIP AS PACKING_SLIP, NVL(pll.QUANTITY_BILLED, 0) AS QTY_BILLED")
_RECEIPT_FROM = ("FROM PO.RCV_SHIPMENT_LINES l\n"
                 "JOIN PO.RCV_SHIPMENT_HEADERS h ON h.SHIPMENT_HEADER_ID = l.SHIPMENT_HEADER_ID\n"
                 "JOIN PO.PO_LINES_ALL pl ON pl.PO_LINE_ID = l.PO_LINE_ID\n"
                 "JOIN PO.PO_HEADERS_ALL ph ON ph.PO_HEADER_ID = l.PO_HEADER_ID\n"
                 "JOIN APPS.RCV_VRC_HDS_V v ON v.SHIPMENT_HEADER_ID = h.SHIPMENT_HEADER_ID\n"
                 "LEFT JOIN PO.PO_LINE_LOCATIONS_ALL pll ON pll.LINE_LOCATION_ID = l.PO_LINE_LOCATION_ID\n"
                 "LEFT JOIN APPS.MTL_SYSTEM_ITEMS_B msi ON msi.INVENTORY_ITEM_ID = l.ITEM_ID "
                 "AND msi.ORGANIZATION_ID = l.TO_ORGANIZATION_ID")

RCV_V01 = f"""
SELECT {_LINE_COLS},
       {MATCH_MODE}
{_RECEIPT_FROM}
WHERE ({INV_KEYS}{INV_PREFIX})
  AND ph.SEGMENT1 = :p_po_number
ORDER BY h.RECEIPT_NUM, l.LINE_NUM
FETCH FIRST 50 ROWS ONLY"""

# PO-SUPPLIER (Supplier Tax ID of a PO) — hop 1 of RCV-V02
PO_SUPPLIER_TAX = """
SELECT COALESCE(pv.VAT_REGISTRATION_NUM, pv.NUM_1099) AS SUPPLIER_TAX_ID
FROM PO.PO_HEADERS_ALL ph
JOIN APPS.PO_VENDORS pv ON pv.VENDOR_ID = ph.VENDOR_ID
WHERE ph.SEGMENT1 = :p_po_number
FETCH FIRST 1 ROWS ONLY"""

# CR-01 (RCV-V02 fallback, Standard Table 5 registration pending — Finding F-01)
# RCV-V02 keeps the two safe predicates only (exact + case/space/slash-insensitive).  The composite
# prefix branch is not used here because without the PO equality it could pick an unrelated supplier's
# receipt whose own PO number happens to start with the same digits.
RCV_V02 = f"""
SELECT {_LINE_COLS},
       {MATCH_MODE}
{_RECEIPT_FROM}
JOIN APPS.PO_VENDORS pv ON pv.VENDOR_ID = ph.VENDOR_ID
WHERE ({INV_KEYS})
  AND COALESCE(pv.VAT_REGISTRATION_NUM, pv.NUM_1099) = :p_supplier_tax_id
ORDER BY h.RECEIPT_NUM, l.LINE_NUM
FETCH FIRST 50 ROWS ONLY"""

EXTRA_COLUMNS = ("PO_NUM", "ITEM_CODE", "SHIPMENT_NUM", "PACKING_SLIP", "QTY_BILLED", "MATCH_MODE")

# ------------------------------------------------------------------ AIVA-SYSA-ORA-01 (Tax ID + Invoice)
# Port of the legacy OracleMCPClient._build_sql_query, made safe:
#   * every value goes through render_sql (whitelist + '' escaping) — no f-string with OCR data
#   * real LINE_NUM, FETCH FIRST row cap, read-only guard, technical errors raise
#   * the supplier is the PO's vendor (ph.VENDOR_ID), consistent with PO-SUPPLIER / RCV-V02
#   * ORG_ID stays PO_HEADERS_ALL.ORG_ID (operating unit of Standard Table 4)
# Column names in the SELECT list are the keys repositories._row(extended=True) reads.
_ALLOWED_INVOICE_COLUMNS = {"SHIPMENT_NUM": "h.SHIPMENT_NUM", "PACKING_SLIP": "h.PACKING_SLIP",
                            "WAYBILL_AIRBILL_NUM": "h.WAYBILL_AIRBILL_NUM"}
_MULTI_COLS = ("ph.ORG_ID AS ORG_ID, ph.ORG_ID AS OU_ORG_ID, hou.NAME AS OU_NAME,\n"
               "       fsp.VAT_REGISTRATION_NUM AS CUSTOMER_TAX_ID, ph.SEGMENT1 AS PO_NUM,\n"
               "       h.RECEIPT_NUM AS RECEIPT_NUM, v.RECEIVER AS RECEIVER, l.LINE_NUM AS LINE,\n"
               "       COALESCE(pv.VAT_REGISTRATION_NUM, pv.NUM_1099) AS SUPPLIER_TAX_ID, pv.VENDOR_NAME AS SUPPLIER_NAME,\n"
               "       msi.SEGMENT1 AS ITEM_CODE, l.ITEM_DESCRIPTION AS ITEM, l.QUANTITY_RECEIVED AS QTY,\n"
               "       l.UNIT_OF_MEASURE AS UOM, pl.UNIT_PRICE AS UNIT_PRICE,\n"
               "       l.QUANTITY_RECEIVED * pl.UNIT_PRICE AS LINE_AMOUNT, l.SHIPMENT_LINE_STATUS_CODE AS LINE_STATUS,\n"
               "       pll.CLOSED_CODE AS PO_LINE_STATUS, NVL(pll.QUANTITY_BILLED, 0) AS QTY_BILLED,\n"
               "       h.SHIPMENT_NUM AS SHIPMENT_NUM, h.PACKING_SLIP AS PACKING_SLIP,\n"
               "       h.WAYBILL_AIRBILL_NUM AS WAYBILL_AIRBILL_NUM")
_MULTI_FROM = (_RECEIPT_FROM + "\n"
               "LEFT JOIN APPS.PO_VENDORS pv ON pv.VENDOR_ID = ph.VENDOR_ID\n"
               "LEFT JOIN APPS.HR_OPERATING_UNITS hou ON hou.ORGANIZATION_ID = ph.ORG_ID\n"
               "LEFT JOIN APPS.FINANCIALS_SYSTEM_PARAMS_ALL fsp ON fsp.ORG_ID = ph.ORG_ID")
MULTI_EXPECT = ("RECEIPT_NUM", "LINE", "PO_NUM")


def tax_inv_sql(match_columns=None) -> str:
    """TAX-INV template.  Column names come from a fixed allow-list, never from data."""
    cols = [str(c).upper() for c in (match_columns or _ALLOWED_INVOICE_COLUMNS)]
    bad = [c for c in cols if c not in _ALLOWED_INVOICE_COLUMNS]
    if bad or not cols:
        raise OracleTechnicalError(f"INVOICE_MATCH_COLUMN_NOT_ALLOWED:{bad or 'empty'}")
    pred = "\n    OR ".join(f"{_ALLOWED_INVOICE_COLUMNS[c]} IN (:p_invoice_in)" for c in cols)
    return (f"SELECT {_MULTI_COLS}\n{_MULTI_FROM}\n"
            f"WHERE COALESCE(pv.VAT_REGISTRATION_NUM, pv.NUM_1099) = :p_supplier_tax_id\n"
            f"  AND ({pred})\n"
            "ORDER BY h.RECEIPT_NUM, l.LINE_NUM\nFETCH FIRST 50 ROWS ONLY")


PO_LIST = (f"SELECT {_MULTI_COLS}\n{_MULTI_FROM}\n"
           "WHERE ph.SEGMENT1 IN (:p_po_in)\n"
           "ORDER BY h.RECEIPT_NUM, l.LINE_NUM\nFETCH FIRST 50 ROWS ONLY")


def _num(v, default="0"):
    s = str(v if v is not None and str(v).strip() != "" else default).replace(",", "").strip()
    return Decimal(s)


def row_from_csv(d: dict) -> ReceiptRow:
    """Map a CSV row (UPPER or lower keys) onto ``ReceiptRow``; extra columns are kept as data."""
    g = lambda k: d.get(k) if d.get(k) is not None else d.get(k.lower())
    org = str(g("ORG_ID") or "").strip()
    qty = _num(g("QTY"))
    price = _num(g("UNIT_PRICE"))
    amt = g("LINE_AMOUNT")
    return ReceiptRow(
        org_id=int(float(org)) if org.replace(".", "").isdigit() else None,
        receipt_num=str(g("RECEIPT_NUM") or "").strip(),
        receiver=(str(g("RECEIVER") or "").strip() or None),
        line=int(float(str(g("LINE") or "0").strip() or 0)),
        item=str(g("ITEM") or "").strip(),
        qty=qty, uom=str(g("UOM") or "").strip(), unit_price=price,
        line_amount=_num(amt) if amt not in (None, "") else (qty * price),
        extra=_extras(d))


def _row_ext(d: dict) -> ReceiptRow:
    """CSV row of TAX-INV / PO-LIST -> ReceiptRow with every ORA-01 column (Decimal, real LINE_NUM)."""
    try:
        return _repo_row({str(k).upper(): (v.strip() if isinstance(v, str) else v) for k, v in d.items()},
                         extended=True)
    except Exception as e:                       # a row we cannot read is a protocol fault, not "no receipt"
        raise OracleTechnicalError(f"MCP_ROW_UNREADABLE: {type(e).__name__}: {str(e)[:120]}") from e


def _extras(d: dict) -> dict:
    g = lambda k: d.get(k) if d.get(k) is not None else d.get(k.lower())
    return {k: (str(g(k)).strip() if g(k) is not None else None) for k in EXTRA_COLUMNS
            if str(g(k) or "").strip() != ""}


class OracleMcpRepository:
    """Implements ``OracleRepository`` over ORDS MCP.  ``self.audit`` is the SQL evidence log."""

    def __init__(self, client: McpSqlClient, *, row_cap: int = 50, database: str = "default",
                 sql_overrides: Optional[dict] = None, match_columns=None):
        self.c = client
        self.row_cap, self.database = row_cap, database
        self.sql = dict(RCV_V01=RCV_V01, PO_SUPPLIER_TAX=PO_SUPPLIER_TAX, RCV_V02=RCV_V02,
                        TAX_INV=tax_inv_sql(match_columns), PO_LIST=PO_LIST)
        self.sql.update(sql_overrides or {})
        self.audit: list[dict] = []
        self.rejected: list[dict] = []

    # -- helpers ------------------------------------------------------------------
    def _cap(self, sql: str) -> str:
        if re.search(r"FETCH\s+FIRST", sql, re.I):
            return re.sub(r"FETCH\s+FIRST\s+\d+\s+ROWS\s+ONLY", f"FETCH FIRST {self.row_cap} ROWS ONLY",
                          sql, flags=re.I)
        return sql.rstrip().rstrip(";") + f"\nFETCH FIRST {self.row_cap} ROWS ONLY"

    def _query(self, query_id: str, template: str, binds: dict,
               expect: tuple[str, ...] = ("RECEIPT_NUM",)) -> list[dict]:
        entry = {"query_id": query_id, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "sql": None, "binds": {k: v[1] for k, v in binds.items()}, "rows": None, "ms": None, "error": None}
        t0 = time.perf_counter()
        try:
            sql = self._cap(render_sql(template, **binds))
            entry["sql"] = sql
            rows = parse_csv_rows(self.c.run(sql, database=self.database), expect=expect)
        except OracleInputRejected as e:
            entry.update(error=str(e), ms=round((time.perf_counter() - t0) * 1000, 1))
            self.audit.append(entry)
            self.rejected.append(dict(entry))
            raise
        except OracleTechnicalError as e:
            entry.update(error=f"{type(e).__name__}: {str(e)[:200]}", ms=round((time.perf_counter() - t0) * 1000, 1))
            self.audit.append(entry)
            raise
        entry.update(rows=len(rows), ms=round((time.perf_counter() - t0) * 1000, 1))
        self.audit.append(entry)
        return rows

    # -- port ---------------------------------------------------------------------
    def rcv_v01(self, po_number: str, invoice_num: str) -> list[ReceiptRow]:
        rows = self._query("RCV-V01", self.sql["RCV_V01"],
                           {"p_po_number": ("po_number", po_number),
                            "p_invoice_num": ("invoice_num", invoice_num),
                            "p_invoice_in": ("invoice_in", invoice_variants(invoice_num))})
        return [row_from_csv(r) for r in rows]

    def supplier_tax_by_po(self, po_number: str) -> Optional[str]:
        rows = self._query("PO-SUPPLIER", self.sql["PO_SUPPLIER_TAX"], {"p_po_number": ("po_number", po_number)},
                           expect=("SUPPLIER_TAX_ID",))
        if not rows:
            return None
        first = rows[0]
        val = first.get("SUPPLIER_TAX_ID") or first.get("supplier_tax_id")
        return str(val).strip() if val and str(val).strip() else None

    def rcv_v02(self, supplier_tax_id: str, invoice_num: str) -> list[ReceiptRow]:
        rows = self._query("RCV-V02", self.sql["RCV_V02"],
                           {"p_supplier_tax_id": ("tax_id", supplier_tax_id),
                            "p_invoice_num": ("invoice_num", invoice_num),
                            "p_invoice_in": ("invoice_in", invoice_variants(invoice_num))})
        return [row_from_csv(r) for r in rows]

    # -- AIVA-SYSA-ORA-01 ----------------------------------------------------------
    def receipts_by_tax_invoice(self, supplier_tax_id: str, invoice_variants) -> list[ReceiptRow]:
        """Every receipt line of one supplier whose header carries any spelling of the invoice."""
        variants = [str(v).strip() for v in (invoice_variants or [])
                    if v is not None and WHITELIST["invoice_num"].match(str(v).strip())]
        if not variants:                                   # nothing safe to look for: business miss
            return []
        rows = self._query("TAX-INV", self.sql["TAX_INV"],
                           {"p_supplier_tax_id": ("tax_id", supplier_tax_id),
                            "p_invoice_in": ("invoice_in", variants)}, expect=MULTI_EXPECT)
        return [_row_ext(r) for r in rows]

    def receipts_by_po_list(self, po_numbers) -> list[ReceiptRow]:
        pos = sorted({str(p).strip() for p in (po_numbers or [])
                      if p is not None and WHITELIST["po_number"].match(str(p).strip())})
        if not pos:
            return []
        rows = self._query("PO-LIST", self.sql["PO_LIST"], {"p_po_in": ("po_in", pos)}, expect=MULTI_EXPECT)
        return [_row_ext(r) for r in rows]

    # -- reporting helpers ---------------------------------------------------------
    def sql_audit(self) -> list[dict]:
        """Copy of the per-document SQL evidence log (query_id, sql, binds, rows, ms, error)."""
        return list(self.audit)
