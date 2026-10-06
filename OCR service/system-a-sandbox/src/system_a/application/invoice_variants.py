"""Invoice-number spellings used to find a receipt (Standard v6.6 Table 12 #3).

Receipts store the supplier's invoice number in several shapes — with/without slashes, upper/lower
case, and a document-series prefix keyed straight into the number (``SQ26/123`` vs ``SQ26123``).
An exact equality test on one spelling therefore loses real receipts.

The transforms come from ``policy.yaml`` (`oracle.lookup.invoice_variants`), **not** from code: the
series prefix lives in the Standard, so a new document series is a configuration change.  Every
candidate is then dropped unless it has the same safe shape ``adapters/oracle/sql_safety.py``
demands before it renders a SQL literal, which keeps this whole module usable for a value that came
from OCR.  Nothing here touches SQL and nothing here touches the network.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

# Same shape sql_safety enforces (spec AIVA-SYSA-ORA-01 §4): upper-case alphanumerics, slash, hyphen.
# Declared here instead of imported from the adapter so the application layer never depends on it;
# tests/test_sql_safety.py asserts the two patterns stay identical.
SAFE_INVOICE_SHAPE = r"^[A-Z0-9/\-]{1,40}$"
_SAFE = re.compile(SAFE_INVOICE_SHAPE)

VARIANT_LIMIT = 6


def _strip_char(value: str, spec: dict) -> Optional[str]:
    ch = str(spec.get("char") or "")
    return value.replace(ch, "") if ch else None


def _insert_after_prefix(value: str, spec: dict) -> Optional[str]:
    prefix, insert = str(spec.get("prefix") or ""), str(spec.get("insert") or "")
    if not prefix or not insert or not value.startswith(prefix) or len(value) <= len(prefix):
        return None
    rest = value[len(prefix):]
    return None if rest.startswith(insert) else prefix + insert + rest


def _remove_after_prefix(value: str, spec: dict) -> Optional[str]:
    """Inverse transform: the invoice prints ``SQ26/123`` while the receipt keyed ``SQ26123``."""
    prefix, remove = str(spec.get("prefix") or ""), str(spec.get("remove") or "")
    head = value[:len(prefix) + len(remove)]
    if not prefix or not remove or not head.startswith(prefix + remove):
        return None
    return prefix + value[len(prefix) + len(remove):]


TRANSFORMS = {"strip_char": _strip_char, "insert_after_prefix": _insert_after_prefix,
              "remove_after_prefix": _remove_after_prefix}


def safe_invoice(value: object) -> bool:
    """True when a value can be turned into a SQL literal by the safety layer."""
    return bool(_SAFE.match(str(value if value is not None else "").strip()))


def build_variants(raw: object, specs: Optional[Iterable[dict]] = None,
                   limit: int = VARIANT_LIMIT) -> list[str]:
    """Ordered, deduplicated, whitelist-clean spellings of one invoice number ("" -> []).

    The value as normalised by the domain is always the first candidate, so an exact hit stays the
    cheapest and most likely match.
    """
    s = str(raw if raw is not None else "").strip()
    if not s:
        return []
    out: list[str] = []

    def add(cand: Optional[str]) -> None:
        c = str(cand or "").strip()
        if c and c not in out and _SAFE.match(c):
            out.append(c)

    add(s)
    for spec in specs or ():
        fn = TRANSFORMS.get(str((spec or {}).get("type") or ""))
        if fn is None:
            continue
        add(fn(s, spec))
        if len(out) >= limit:
            break
    return out[:limit]
