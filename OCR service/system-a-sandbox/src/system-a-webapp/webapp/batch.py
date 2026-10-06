"""The document list: a batch folder produced by the OCR engine (``report.html`` + ``docs/doc_<id>/page_<n>.jpg``).

``report.html`` carries the whole batch as one JavaScript literal::

    const DATA=[{id,title,ptype,types,status,pages_total,pages:[{page,image,doc_type,coord,seconds,error,
                 kept:[{type,label,text,bbox_norm,bbox_px}], dropped:[...]}], ...}], COLORS={...};

The literal is located and decoded with ``json.JSONDecoder.raw_decode`` (not a regular expression over
megabytes of text), so a report of any size parses in one pass and a malformed one fails with a position.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_COLORS = {"header": "#d62728", "supplier": "#ff7f0e", "customer": "#9467bd", "table": "#7f7f7f",
                  "line": "#1f77b4", "total": "#2ca02c", "payment": "#bcbd22", "signature": "#e377c2",
                  "stamp": "#8c564b", "other": "#17becf"}
A4_PX = (1240, 1754)                      # A4 at 150 dpi: the size assumed when a page image is missing


class BatchError(ValueError):
    """The batch folder / report could not be read."""


@dataclass
class BatchPage:
    page: int
    image: Optional[str] = None
    doc_type: str = "unknown"
    coord: str = "norm1000"
    seconds: Optional[float] = None
    error: Optional[str] = None
    kept: list = field(default_factory=list)
    dropped: list = field(default_factory=list)


@dataclass
class BatchDoc:
    id: int
    title: str
    ptype: Optional[str] = None
    pages_total: int = 0
    pages: list = field(default_factory=list)
    status: Optional[str] = None            # status the OCR engine reported (kept for reference only)
    # metadata of the source (filled by the Paperless source; a batch document leaves these empty)
    created: str = ""
    correspondent: str = ""
    mime: str = ""
    file_class: str = ""
    dms_url: str = ""

    @property
    def page_numbers(self) -> list:
        return [p.page for p in self.pages]


def _num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _items(raw) -> list:
    out = []
    for it in raw or []:
        if not isinstance(it, dict):
            continue
        b = it.get("bbox_norm")
        b = [float(x) for x in b] if isinstance(b, (list, tuple)) and len(b) == 4 and all(
            isinstance(x, (int, float)) for x in b) else None
        out.append({**it, "bbox_norm": b})
    return out


def parse_report(text: str) -> tuple[list, dict]:
    """``report.html`` text -> (documents, colors)."""
    at = text.find("const DATA=")
    if at < 0:
        raise BatchError("report.html has no 'const DATA=' literal - is this an AIVA bbox batch report?")
    dec = json.JSONDecoder()
    try:
        data, end = dec.raw_decode(text, at + len("const DATA="))
    except json.JSONDecodeError as e:
        raise BatchError(f"DATA literal is not valid JSON (char {e.pos}): {e.msg}") from e
    if not isinstance(data, list):
        raise BatchError("DATA is not a list of documents")
    colors = dict(DEFAULT_COLORS)
    ca = text.find("COLORS=", end)
    if ca >= 0:
        try:
            c, _ = dec.raw_decode(text, ca + len("COLORS="))
            if isinstance(c, dict):
                colors.update({str(k): str(v) for k, v in c.items()})
        except json.JSONDecodeError:
            pass                                    # colours are cosmetic; the defaults stand in
    docs: list[BatchDoc] = []
    seen: set = set()
    for d in data:
        if not isinstance(d, dict) or "id" not in d:
            raise BatchError("a DATA entry has no 'id'")
        did = int(d["id"])
        if did in seen:
            raise BatchError(f"duplicate document id {did}")
        seen.add(did)
        pages = [BatchPage(page=int(p.get("page") or i), image=p.get("image"), doc_type=str(p.get("doc_type") or "unknown"),
                           coord=str(p.get("coord") or "norm1000"), seconds=_num(p.get("seconds")),
                           error=p.get("error"), kept=_items(p.get("kept")), dropped=_items(p.get("dropped")))
                 for i, p in enumerate(d.get("pages") or [], start=1)]
        docs.append(BatchDoc(id=did, title=str(d.get("title") or f"doc {did}"), ptype=d.get("ptype"),
                             pages_total=int(d.get("pages_total") or len(pages)), pages=pages, status=d.get("status")))
    return docs, colors


class BatchSource:
    """Read-only view of one batch folder."""

    kind = "batch"
    owns_pdf = False                                   # LivePerception reads the batch's own files

    def __init__(self, path: Path):
        path = Path(path)
        report = path / "report.html" if path.is_dir() else path
        if not report.is_file():
            raise BatchError(f"report not found: {report}")
        self.report_path = report.resolve()
        self.root = self.report_path.parent
        self.docs, self.colors = parse_report(report.read_text(encoding="utf-8"))
        self.by_id = {d.id: d for d in self.docs}

    # ---------------------------------------------------------------- lookups
    def get(self, doc_id: int) -> BatchDoc:
        try:
            return self.by_id[int(doc_id)]
        except (KeyError, ValueError):
            raise KeyError(f"unknown document {doc_id}") from None

    def _inside(self, rel: str) -> Optional[Path]:
        """``root / rel`` if it stays inside the batch folder (no ``..`` escapes), else None."""
        p = (self.root / rel).resolve()
        try:
            p.relative_to(self.root)
        except ValueError:
            return None
        return p

    def image_path(self, doc_id: int, page: int) -> Optional[Path]:
        pg = next((p for p in self.get(doc_id).pages if p.page == page), None)
        if pg is None or not pg.image:
            return None
        p = self._inside(pg.image)
        return p if p is not None and p.is_file() else None

    def viewer_url(self, doc_id: int) -> Optional[str]:
        rel = f"docs/doc_{int(doc_id)}/viewer.html"
        p = self._inside(rel)
        return f"/batch/{rel}" if p is not None and p.is_file() else None

    # --------------------------------------------------------------- bytes for the UI / perception
    def page_image(self, doc_id: int, page: int) -> Optional[tuple]:
        """``(image bytes, media_type)`` of the page JPG/PNG of the batch, or None when it is not on disk."""
        p = self.image_path(doc_id, page)
        if p is None:
            return None
        return p.read_bytes(), ("image/png" if p.suffix.lower() == ".png" else "image/jpeg")

    def pdf_bytes(self, doc_id: int) -> tuple:
        p = self.pdf_path(doc_id)
        if p is None:
            raise BatchError(f"document #{doc_id} has no PDF in {self.root}")
        return p.read_bytes(), f"pdf:{p.name}"

    def pdf_path(self, doc_id: int, pdf_dir: Optional[Path] = None) -> Optional[Path]:
        """The PDF of a document, if one exists: ``<pdf_dir>/doc_<id>.pdf`` / ``<title>.pdf`` / ``<id>.pdf``,
        or ``docs/doc_<id>/*.pdf`` inside the batch folder."""
        d = self.get(doc_id)
        names = (f"doc_{d.id}.pdf", f"{d.title}.pdf", f"{d.id}.pdf")
        for base in filter(None, (pdf_dir, self.root / "docs" / f"doc_{d.id}")):
            for n in names:
                p = Path(base) / n
                if p.is_file():
                    return p
        folder = self.root / "docs" / f"doc_{d.id}"
        found = sorted(folder.glob("*.pdf")) if folder.is_dir() else []
        return found[0] if found else None

    def page_size_px(self, doc_id: int, page: int) -> tuple:
        p = self.image_path(doc_id, page)
        if p is not None:
            try:
                from PIL import Image
                with Image.open(p) as im:
                    return im.size
            except Exception:
                pass
        return A4_PX

    def stats(self) -> dict:
        kept = sum(len(p.kept) for d in self.docs for p in d.pages)
        return {"documents": len(self.docs), "pages": sum(len(d.pages) for d in self.docs), "items": kept,
                "dropped": sum(len(p.dropped) for d in self.docs for p in d.pages),
                "images_found": sum(1 for d in self.docs for p in d.pages if self.image_path(d.id, p.page)),
                "images_missing": sum(1 for d in self.docs for p in d.pages if not self.image_path(d.id, p.page)),
                "items_without_bbox": sum(1 for d in self.docs for p in d.pages for i in p.kept
                                          if not i.get("bbox_norm")),
                "doc_types": sorted({p.doc_type for d in self.docs for p in d.pages})}


_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(s: str) -> str:
    return _SAFE.sub("_", s)[:80] or "doc"
