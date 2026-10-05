"""STEP 2 receipt lookup (X-01): RCV-V01 (PO + Invoice) -> fallback RCV-V02 (PO -> Supplier Tax -> Tax + Invoice).

At most 3 queries per validation round; results memoised per round so rules never re-query.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..domain.contracts import OracleInputRejected, OracleSnapshot, OracleTechnicalError
from ..domain.ports import OracleRepository


class OracleSession:
    def __init__(self, repo: OracleRepository, row_cap: int):
        self.repo, self.row_cap, self.calls, self._memo = repo, row_cap, 0, {}
        self.rejected: list[dict] = []

    def _call(self, name, fn, *args):
        key = (name, args)
        if key not in self._memo:
            self.calls += 1
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
