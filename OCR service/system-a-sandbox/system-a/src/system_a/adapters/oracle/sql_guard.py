"""SQL safety layer shared by every Oracle backend (Standard v6.6 safety rules, Decision Log §7.3).

The ORDS MCP backend receives a *SQL string*, not bind variables, so literals are produced here
from whitelist-shaped values only.  The in-memory sandbox backend uses the same whitelist so that
sandbox and production behave identically for bad keys (``OracleInputRejected`` -> INPUT_REJECTED).
"""
from __future__ import annotations

import re

from ...domain.contracts import OracleInputRejected, OracleTechnicalError

# Standard §1.4 bind whitelist (task file §1.4 / Table 5 "bind variables only")
WHITELIST: dict[str, re.Pattern] = {
    "po_number": re.compile(r"^[0-9]{8}$"),
    "invoice_num": re.compile(r"^[A-Za-z0-9/\-_.]{1,40}$"),
    "tax_id": re.compile(r"^[0-9]{13}$"),
}

FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|UPSERT|CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE|COMMIT|ROLLBACK|"
    r"CALL|EXECUTE|BEGIN|DECLARE|LOCK|EXPLAIN|PLAN|RENAME|COMMENT|SAVEPOINT)\b", re.I)
_MULTI_STMT = re.compile(r";\s*\S", re.S)
_NAMED_PARAM = re.compile(r":([a-z_][a-z0-9_]*)", re.I)

# Table 12 #3: the invoice number as printed and the value keyed into RCV_SHIPMENT_NUM differ by case,
# spaces and slashes.  Variants are generated in code so the SQL keeps an *indexable* equality on the
# column (wrapping the column in a function would full-scan 1.3M headers — measured 24 s vs 0.6 s).
INVOICE_VARIANT_LIMIT = 6


def invoice_variants(raw: object) -> list[str]:
    """Candidate spellings of one invoice number, ordered, deduplicated, whitelist-clean."""
    s = str(raw or "").strip()
    out: list[str] = []
    for cand in (s, s.upper(), s.replace(" ", ""), s.replace("/", ""),
                 s.upper().replace(" ", "").replace("/", ""), s.upper().replace("/", "")):
        c = cand.strip()
        if len(out) >= INVOICE_VARIANT_LIMIT:
            break
        if c and c not in out and WHITELIST["invoice_num"].match(c):
            out.append(c)
    return out


def strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"--[^\n]*", " ", sql)


def ensure_read_only(sql: str) -> str:
    """Return the statement with comments removed, or refuse it.  SELECT/WITH only."""
    body = strip_sql_comments(sql).strip().rstrip(";").strip()
    if not body:
        raise OracleTechnicalError("EMPTY_SQL")
    if _MULTI_STMT.search(body):
        raise OracleTechnicalError("SQL_NOT_READ_ONLY: multiple statements")
    head = body.split(None, 1)[0].upper()
    if head not in ("SELECT", "WITH"):
        raise OracleTechnicalError(f"SQL_NOT_READ_ONLY: {head}")
    if FORBIDDEN.search(body):
        raise OracleTechnicalError("SQL_NOT_READ_ONLY: forbidden keyword")
    if re.search(r"\bFOR\s+UPDATE\b", body, re.I):
        raise OracleTechnicalError("SQL_NOT_READ_ONLY: FOR UPDATE")
    return body


def bind_literal(raw: object, kind: str) -> str:
    """Validate ``raw`` against the whitelist for ``kind`` and render a safe SQL literal.

    Values that are not exactly whitelist-shaped are rejected *before* Oracle sees them, which is
    what keeps string-splicing safe here (SQL*Plus-style literal, no driver bind variables).
    """
    if kind not in WHITELIST:
        raise OracleInputRejected(f"UNKNOWN_BIND_KIND:{kind}")
    s = str(raw if raw is not None else "").strip()
    if not WHITELIST[kind].match(s):
        raise OracleInputRejected(f"INPUT_REJECTED:{kind}")
    return "'" + s.replace("'", "''") + "'"


def render_in_list(values, kind: str) -> str:
    """Render a validated IN-list.  An empty (or all-rejected) list becomes NULL = matches nothing."""
    lits = []
    for v in values or []:
        s = str(v or "").strip()
        if s and WHITELIST[kind].match(s):
            lits.append("'" + s.replace("'", "''") + "'")
    return ", ".join(lits) if lits else "NULL"


def render_sql(template: str, **values: tuple[str, object]) -> str:
    """Replace ``:p_name`` placeholders with validated literals.

    ``values`` maps placeholder name -> (kind, value).  ``kind`` is a WHITELIST key, or one of
    ``invoice_in`` / ``tax_in`` for a comma-separated IN-list built from a list of values.
    """
    def sub(m: re.Match) -> str:
        name = str(m.group(1))
        if name not in values:
            raise OracleTechnicalError(f"MISSING_BIND:{name}")
        kind, val = values[name]
        if kind == "invoice_in":
            return render_in_list([str(v) for v in (val or [])], "invoice_num")
        if kind == "tax_in":
            return render_in_list([str(v) for v in (val or [])], "tax_id")
        return bind_literal(val, str(kind))

    out = _NAMED_PARAM.sub(sub, template)
    if _NAMED_PARAM.search(out):  # a placeholder left over from a quoted literal etc.
        raise OracleTechnicalError("UNBOUND_PLACEHOLDER")
    return out


def check_keys(**keys: object) -> None:
    """Raise ``OracleInputRejected`` unless every key is whitelist-shaped (never sends the query)."""
    for kind, value in keys.items():
        bind_literal(value, kind)
