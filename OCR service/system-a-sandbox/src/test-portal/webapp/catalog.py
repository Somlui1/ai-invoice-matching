"""The document list in the left panel: the real documents of the DMS, read through System A's own reader.

Only listing lives here.  The reader is ``system_a.container.build_paperless`` (``system_a.adapters.paperless.
reader.PaperlessReader``) - a read-only ``GET`` client, so the portal cannot change the document population, and
the portal adds no HTTP code of its own.

The page count of a document is only knowable from its file, so ``ensure()`` asks System A for the file (which is
the file ``process_pdf`` will use, cached in one place) and counts the pages with System A's ingest.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Doc:
    id: int
    title: str
    pages_total: Optional[int] = None
    page_numbers: list = field(default_factory=list)
    created: str = ""
    correspondent: str = ""
    mime: str = ""
    file_class: str = ""
    file_name: str = ""
    tagged: bool = False
    dms_url: str = ""

    def show_page(self, n: int) -> None:
        if n not in self.page_numbers:
            self.page_numbers = list(range(1, max(n, self.pages_total or 0) + 1))
        self.pages_total = max(self.pages_total or 0, n)


class CatalogError(RuntimeError):
    """The DMS list could not be read at all."""


class Catalog:
    kind = "paperless"

    def __init__(self, sa, *, tag: str = "invoice", limit: int = 200):
        self.sa, self.tag, self.limit = sa, tag, int(limit)
        self.reader = sa.container.build_paperless(sa.a_settings())
        self.docs: list[Doc] = []
        self.tag_ids: list[int] = []
        self.unmatched_tags: list[str] = []
        self.list_error: Optional[str] = None
        self.dms_total: Optional[int] = None
        self._lock = threading.Lock()

    # -- plumbing ---------------------------------------------------------------------
    @property
    def base_url(self) -> str:
        return getattr(self.reader, "base_url", "")

    def viewer_url(self, doc_id: int) -> str:
        return f"{self.base_url.rstrip('/')}/documents/{int(doc_id)}/"

    def _title(self, d) -> str:
        return (d.title or "").strip() or (d.file_name or "").strip() or f"DMS-{d.doc_id}"

    def _as_doc(self, d) -> Doc:
        pc = getattr(d, "page_count", None)
        return Doc(id=int(d.doc_id), title=self._title(d), pages_total=pc,
                   page_numbers=list(range(1, pc + 1)) if pc else [],
                   created=str(getattr(d, "created", "") or "")[:10],
                   correspondent=str(getattr(d, "correspondent", "") or ""),
                   mime=str(getattr(d, "mime_type", "") or ""), file_class=d.file_class,
                   file_name=str(getattr(d, "file_name", "") or ""), tagged=bool(getattr(d, "tags", ())),
                   dms_url=self.viewer_url(d.doc_id))

    # -- the list -----------------------------------------------------------------------
    def refresh(self) -> "Catalog":
        """One tag lookup + a paginated document list.  A failing DMS is reported, never raised away silently."""
        try:
            matched = self.reader.tag_ids_for([self.tag], mode="contains")
            if not matched:
                self.unmatched_tags = [self.tag]
                self.list_error = f"ไม่พบ tag ชื่อ '{self.tag}' ใน DMS - รายการทั้งหมดยังแสดงได้ แต่ไม่ถูกกรอง"
                self.tag_ids = []
            else:
                self.tag_ids = [t[0] for t in matched]
            rows = self.reader.list_documents(tag_ids=self.tag_ids, limit=self.limit)
            self.dms_total = getattr(self.reader, "last_count", None)
        except Exception as e:
            self.list_error = f"{type(e).__name__}: {e}"[:400]
            if not self.docs:
                raise CatalogError(self.list_error) from e
            return self
        with self._lock:
            self.docs = [self._as_doc(d) for d in rows]
        return self

    def get(self, doc_id: int) -> Doc:
        with self._lock:
            for d in self.docs:
                if d.id == int(doc_id):
                    return d
        raise KeyError(doc_id)

    def ensure(self, doc_id: int) -> Doc:
        """The real page count, from the file (this is also the moment the file lands in System A's download cache)."""
        d = self.get(doc_id)
        if d.pages_total:
            return d
        n = self.sa.page_count(doc_id)
        if n:
            d.pages_total, d.page_numbers = n, list(range(1, n + 1))
        return d

    # -- what the UI is told -------------------------------------------------------------
    def health(self) -> dict:
        h = self.reader.health()
        return {"base_url": self.base_url, "dms_total": h.get("count"), "tag": self.tag, "tag_ids": self.tag_ids}

    def stats(self) -> dict:
        return {"kind": self.kind, "documents": len(self.docs), "pages": sum(d.pages_total or 0 for d in self.docs),
                "tag": self.tag, "tag_ids": self.tag_ids, "dms_total": self.dms_total,
                "unmatched_tags": self.unmatched_tags, "error": self.list_error}
