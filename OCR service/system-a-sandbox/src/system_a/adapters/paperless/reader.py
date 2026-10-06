"""Read-only Paperless-ngx REST adapter (source of the real document population).

Only ``GET`` is implemented — there is deliberately no tag/field write path here, because the
task's Phase 1 requires a *non-mutating* inventory (tagging documents would change the population
and break re-runs).  The endpoint shape follows the working client in ``OCR_rule/services/paperless.py``.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

import httpx


class PaperlessError(RuntimeError):
    """Transport / HTTP / shape failure while reading the DMS (never a business verdict)."""


@dataclass(frozen=True)
class PaperlessDoc:
    """One row of ``/api/documents/`` — the fields the inventory (§4.1) needs, nothing else.

    ``content`` (the stored OCR text) is deliberately not carried: it is large, may hold personal
    data, and System A re-reads the original file itself.
    """

    doc_id: int
    title: str = ""
    created: str = ""
    correspondent: Optional[str] = None
    tags: tuple[int, ...] = ()
    file_name: str = ""
    owner: str = ""
    mime_type: str = ""
    page_count: Optional[int] = None
    document_type: Optional[str] = None
    deleted_at: Optional[str] = None
    archive_serial: Optional[int] = None
    custom_fields: tuple = ()
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def dms_doc_id(self) -> str:
        return f"DMS-{self.doc_id}"

    @property
    def doc_url(self) -> str:
        return f"/documents/{self.doc_id}/"

    @property
    def file_class(self) -> str:
        """``pdf`` / ``image`` / ``other`` — images are converted to PDF in memory (task §4.1)."""
        m = (self.mime_type or "").lower()
        if m == "application/pdf" or self.file_name.lower().endswith(".pdf"):
            return "pdf"
        if m.startswith("image/") or self.file_name.lower().endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):
            return "image"
        return "other"


def _doc(raw: dict) -> PaperlessDoc:
    tags = raw.get("tags") or []
    dt = raw.get("document_type")
    pc = raw.get("page_count")
    return PaperlessDoc(
        doc_id=int(raw.get("id") or 0),
        title=str(raw.get("title") or ""),
        created=str(raw.get("created") or raw.get("created_date") or ""),
        correspondent=raw.get("correspondent_display_name") or (
            str(raw["correspondent"]) if raw.get("correspondent") is not None else None),
        tags=tuple(int(t.get("id") if isinstance(t, dict) else t) for t in tags),
        file_name=str(raw.get("original_file_name") or raw.get("file_name") or ""),
        owner=str(raw.get("owner") or ""),
        mime_type=str(raw.get("mime_type") or ""),
        page_count=int(pc) if str(pc or "").strip().isdigit() else None,
        document_type=(str(dt.get("name")) if isinstance(dt, dict) else (str(dt) if dt is not None else None)),
        deleted_at=(str(raw["deleted_at"]) if raw.get("deleted_at") else None),
        archive_serial=(int(raw["archive_serial_number"]) if str(raw.get("archive_serial_number") or "").strip()
                        .isdigit() else None),
        custom_fields=tuple(raw.get("custom_fields") or ()),
        raw={k: v for k, v in raw.items() if k != "content"})


@dataclass
class PaperlessReader:
    """Synchronous, paginated reader.  ``transport`` is a test seam (never used against prod)."""

    base_url: str
    token: str = ""
    timeout_s: float = 60.0
    page_size: int = 50
    retries: int = 2
    transport: Optional[httpx.BaseTransport] = None
    calls: list = field(default_factory=list)
    last_count: Optional[int] = None      # ``count`` reported by the API on the last listing

    def __post_init__(self) -> None:
        if not (self.base_url or "").startswith(("http://", "https://")):
            raise PaperlessError(f"PAPERLESS_BASE_URL invalid: {self.base_url!r}")
        self.base = self.base_url.rstrip("/")

    # -- plumbing -------------------------------------------------------------------
    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Token {self.token}"
        return h

    def _request(self, method: str, url: str, *, params: dict | None = None,
                 stream: bool = False) -> httpx.Response:
        last: Optional[str] = None
        for attempt in range(self.retries + 1):
            try:
                t0 = time.perf_counter()
                with httpx.Client(timeout=self.timeout_s, transport=self.transport) as c:
                    r = c.request(method, url, params=params, headers=self._headers())
                self.calls.append({"method": method, "url": url, "status": r.status_code,
                                   "ms": round((time.perf_counter() - t0) * 1000, 1)})
                if r.status_code in (401, 403):
                    raise PaperlessError(f"PAPERLESS_AUTH: HTTP {r.status_code} — check PAPERLESS_API_TOKEN")
                r.raise_for_status()
                return r
            except PaperlessError:
                raise                                    # auth/HTTP 4xx-5xx: a retry cannot fix it
            except Exception as e:                       # transport only
                last = f"{type(e).__name__}: {str(e) or 'no detail'}"
                if attempt < self.retries:
                    time.sleep(min(8, 2 ** attempt))
        raise PaperlessError(f"PAPERLESS_TRANSPORT: {last}")

    def _get_json(self, url: str, params: dict | None = None) -> dict:
        r = self._request("GET", url, params=params)
        try:
            data = r.json()
        except Exception as e:
            raise PaperlessError(f"PAPERLESS_PROTOCOL: {url} is not JSON ({str(e)[:80]})") from e
        if not isinstance(data, dict):
            raise PaperlessError(f"PAPERLESS_PROTOCOL: {url} returned {type(data).__name__}")
        return data

    # -- reads ----------------------------------------------------------------------
    def tags(self) -> list[dict]:
        """All tags (id + name) — used to resolve the inventory filter by name."""
        out, url, query = [], f"{self.base}/api/tags/", {"page_size": 200}
        while url:
            data = self._get_json(url, query)
            out.extend(data.get("results") or [])
            url, query = data.get("next"), None
        return out

    def tag_ids_for(self, names: Sequence[str], *, mode: str = "insensitive") -> list[tuple[int, str]]:
        """Resolve tag names to ids.  Unmatched names are reported by the caller, not guessed here."""
        want = [str(n).strip().casefold() for n in names if str(n).strip()]
        found: list[tuple[int, str]] = []
        for t in self.tags():
            name = str(t.get("name") or "")
            if name.casefold() in want or (mode == "contains" and any(w in name.casefold() for w in want)):
                found.append((int(t["id"]), name))
        return found

    def list_documents(self, *, tag_ids: Iterable[int] | None = None, require_all: bool = False,
                       exclude_tag_ids: Iterable[int] | None = None, limit: int | None = None,
                       order: str = "id") -> list[PaperlessDoc]:
        """Enumerate documents; ``tag_ids`` with ``require_all=False`` means "has any of these tags"."""
        params: dict = {"page_size": self.page_size, "ordering": order}
        ids = [int(t) for t in (tag_ids or [])]
        if ids:
            params["tags__id__all" if require_all else "tags__id__in"] = ids
        ex = [int(t) for t in (exclude_tag_ids or [])]
        if ex:
            params["tags__id__none"] = ex
        out: list[PaperlessDoc] = []
        url: Optional[str] = f"{self.base}/api/documents/"
        query: Optional[dict] = params
        while url:
            data = self._get_json(url, query)
            if self.last_count is None and data.get("count") is not None:
                self.last_count = int(data["count"])
            for raw in data.get("results") or []:
                out.append(_doc(raw))
                if limit is not None and len(out) >= limit:
                    return out
            url, query = data.get("next"), None        # ``next`` already carries the query string
        return out

    def document(self, doc_id: int) -> PaperlessDoc:
        return _doc(self._get_json(f"{self.base}/api/documents/{doc_id}/"))

    def download(self, doc_id: int, original: bool = True) -> bytes:
        """File bytes, the way bbox_testv3 reads them: ``?original=true`` first (the scan as uploaded, not the
        OCRmyPDF archive); when that is not a PDF, the archived PDF; otherwise the original bytes (an image, which
        perception wraps into a PDF)."""
        url = f"{self.base}/api/documents/{doc_id}/download/"
        r = self._request("GET", url, params={"original": "true"} if original else None)
        if not r.content:
            raise PaperlessError(f"PAPERLESS_EMPTY: document {doc_id} downloaded 0 bytes")
        if original and not r.content[:5].startswith(b"%PDF"):
            try:
                a = self._request("GET", url)
                if a.content[:5].startswith(b"%PDF"):
                    return a.content
            except PaperlessError:
                pass
        return r.content

    def metadata(self, doc_id: int) -> dict:
        """Paperless metadata (is_unlisted, media_filename, checksum, custom fields...)."""
        return self._get_json(f"{self.base}/api/documents/{doc_id}/metadata/")

    def health(self) -> dict:
        """Connectivity + population size, without pulling the whole list."""
        data = self._get_json(f"{self.base}/api/documents/", {"page_size": 1})
        return {"count": data.get("count"), "page_size": data.get("page_size"),
                "sample": [d.doc_id for d in map(_doc, data.get("results") or [])]}
