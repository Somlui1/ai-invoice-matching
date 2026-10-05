"""Catalog + rendering services for the portal.

Everything here is a *client* of existing services:

* Paperless-ngx REST (read-only) through ``system_a.container.build_paperless`` and a thin
  pass-through for server-side search / paging.  No write endpoint is ever called.
* the download cache at ``system-a/.cache/downloads`` — the same directory ``process_pdf.py``
  uses, so a document fetched by the engine and one fetched by the viewer share one copy.
* PyMuPDF for page rastering — the same library System A's perception uses, so a portal page image
  is the same raster the VLM was given (``package.coordinate_system`` is defined against it).

Nothing in this module can change a verification outcome.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

WEB_DIR = Path(__file__).resolve().parent
SYSTEM_A_DIR = WEB_DIR.parent
SRC_DIR = SYSTEM_A_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from system_a.envfile import load_env                                # noqa: E402

load_env()                                                          # before Settings reads os.environ

from system_a.container import Settings, build_paperless           # noqa: E402

DOWNLOADS_DIR = Path(os.getenv("WEB_DOWNLOADS_DIR", str(SYSTEM_A_DIR / ".cache" / "downloads")))
PAGES_CACHE_DIR = SYSTEM_A_DIR / ".cache" / "web-pages"
DEFAULT_RENDER_DPI = int(os.getenv("WEB_RENDER_DPI", "150"))          # matches PERCEPTION_DPI

_settings: Settings | None = None
_reader = None
_lock = threading.Lock()


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reader():
    """Cached read-only Paperless client (None when the DMS is not configured)."""
    global _reader
    with _lock:
        if _reader is None:
            try:
                _reader = build_paperless(settings())
            except Exception:
                _reader = False                              # configured wrong: do not retry per request
    return _reader or None


def _pymupdf():
    """PyMuPDF under its current name, with the old ``fitz`` alias as fallback."""
    try:
        import pymupdf
        return pymupdf
    except ModuleNotFoundError:
        import fitz
        return fitz


# --------------------------------------------------------------------------- document catalog
def search_documents(*, search: str = "", page: int = 1, page_size: int = 50,
                     ordering: str = "-created", tag_ids: list[int] | None = None) -> dict:
    """Paperless list endpoint with server-side paging and keyword search.

    Uses the same base URL / token as System A but issues its own GET; the response shape
    (``count`` + ``results``) is passed through so the UI can page without pulling the whole DMS.
    """
    s = settings()
    if not s.paperless_url:
        raise RuntimeError("PAPERLESS_BASE_URL is not configured")
    params: dict[str, Any] = {"page": max(1, page), "page_size": min(200, max(1, page_size)),
                              "ordering": ordering,
                              # ask for exactly the columns the gallery shows; 'content' (stored OCR text)
                              # is huge and is never needed here
                              "fields": "id,title,created,correspondent,page_count,tags"}
    q = (search or "").strip()
    if q:
        params["search"] = q                                  # paperless full-text + title + ASN search
    if tag_ids:
        params["tags__id__in"] = tag_ids
    headers = {"Accept": "application/json"}
    if s.paperless_token:
        headers["Authorization"] = f"Token {s.paperless_token}"
    with httpx.Client(timeout=s.paperless_timeout_s) as c:
        r = c.get(f"{s.paperless_url.rstrip('/')}/api/documents/", params=params, headers=headers)
    if r.status_code in (401, 403):
        raise PermissionError(f"Paperless rejected the token (HTTP {r.status_code})")
    r.raise_for_status()
    data = r.json()
    rows = [_row(raw) for raw in data.get("results") or []]
    return {"count": data.get("count"), "page": params["page"], "page_size": params["page_size"],
            "results": rows}


def _cached_vocab(attr: str, fetch) -> dict[int, str]:
    """5-minute cache for id -> name vocabularies (tags, correspondents) pulled from the DMS."""
    now = time.time()
    current = VOCAB.get(attr)
    if current and now - current[0] < 300:
        return current[1]
    try:
        data = fetch()
    except Exception:
        return {}
    names = {int(x["id"]): str(x.get("name") or "") for x in data if x.get("id") is not None}
    VOCAB[attr] = (now, names)
    return names


VOCAB: dict[str, tuple[float, dict[int, str]]] = {}




def tag_names() -> dict[int, str]:
    rd = reader()
    if rd is None:
        return {}
    return _cached_vocab("tags", rd.tags)


def correspondent_names() -> dict[int, str]:
    """Correspondent id -> name.  The list endpoint only returns the numeric id; names are resolved here."""
    s = settings()
    if not s.paperless_url:
        return {}

    def fetch():
        headers = {"Accept": "application/json"}
        if s.paperless_token:
            headers["Authorization"] = f"Token {s.paperless_token}"
        with httpx.Client(timeout=s.paperless_timeout_s) as c:
            r = c.get(s.paperless_url.rstrip("/") + "/api/correspondents/",
                      params={"page_size": 500}, headers=headers)
            r.raise_for_status()
            return r.json().get("results") or []

    return _cached_vocab("correspondents", fetch)


def _row(raw: dict) -> dict:
    dt = raw.get("document_type")
    names = tag_names()
    tags = []
    for t in raw.get("tags") or []:
        tid = t.get("id") if isinstance(t, dict) else t
        try:
            tags.append(names.get(int(tid), str(tid)))
        except (TypeError, ValueError):
            tags.append(str(t))
    corr_id = raw.get("correspondent")
    corr = raw.get("correspondent_display_name")
    if not corr and corr_id is not None:
        corr = correspondent_names().get(int(corr_id)) if str(corr_id).isdigit() else str(corr_id)
    return {
        "id": raw.get("id"),
        "title": raw.get("title") or "",
        "created": raw.get("created") or raw.get("created_date") or "",
        "correspondent": corr,
        "correspondent_id": corr_id,
        "file_name": raw.get("original_file_name") or raw.get("title") or "",
        "mime_type": raw.get("mime_type") or "",
        "page_count": raw.get("page_count"),
        "document_type": (dt.get("name") if isinstance(dt, dict) else dt),
        "tags": tags,
        "arch_serial": raw.get("archive_serial_number"),
    }


def document(doc_id: int) -> dict:
    rd = reader()
    if rd is None:
        raise RuntimeError("Paperless-ngx is not configured (PAPERLESS_BASE_URL / PAPERLESS_API_TOKEN)")
    d = rd.document(int(doc_id))
    return {"id": d.doc_id, "title": d.title, "created": d.created, "correspondent": d.correspondent,
            "file_name": d.file_name, "mime_type": d.mime_type, "page_count": d.page_count,
            "file_class": d.file_class, "tags": list(d.tags), "dms_doc_id": d.dms_doc_id,
            "doc_url": d.doc_url}


# --------------------------------------------------------------------------- pdf bytes (cached)
def pdf_for(dms_id: int) -> Path:
    """Original file bytes for a DMS document, cached in the shared downloads directory."""
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    path = DOWNLOADS_DIR / f"DMS-{int(dms_id)}.pdf"
    if path.exists() and path.stat().st_size > 0:
        return path
    rd = reader()
    if rd is None:
        raise RuntimeError("Paperless-ngx is not configured; cannot fetch DMS-%s" % dms_id)
    data = rd.download(int(dms_id))
    path.write_bytes(data)
    return path


def local_pdf(key: str) -> Path | None:
    """A file already inside the downloads cache (an upload made through this portal)."""
    stem = "".join(c for c in str(key) if c.isalnum() or c in "-_.")
    for f in sorted(DOWNLOADS_DIR.glob(f"{stem}.*")):
        if f.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"):
            return f
    return None


def resolve_pdf(*, dms_id: int | None = None, key: str | None = None) -> Path:
    if dms_id is not None:
        return pdf_for(int(dms_id))
    if key:
        found = local_pdf(key)
        if found:
            return found
    raise FileNotFoundError("no cached PDF for this document — run the verification first")


def pdf_meta(path: Path) -> dict:
    pymupdf = _pymupdf()
    with pymupdf.open(str(path)) as doc:
        pages = [{"page_no": i + 1, "width_pt": round(float(p.rect.width), 2),
                  "height_pt": round(float(p.rect.height), 2), "rotation": int(p.rotation or 0)}
                 for i, p in enumerate(doc)]
        return {"file": path.name, "bytes": path.stat().st_size,
                "sha256": _sha(path), "page_count": len(pages), "pages": pages,
                "is_pdf": path.suffix.lower() == ".pdf"}


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


# --------------------------------------------------------------------------- page raster
def render_page(path: Path, page_no: int, dpi: int = DEFAULT_RENDER_DPI) -> tuple[bytes, dict]:
    """Raster one page to PNG.

    Returned meta carries the pixel size and the PDF point size, so the browser can map the
    contract's normalised [0,1] boxes onto the image without assuming a DPI.  Rasterising with the
    same PyMuPDF path used by perception keeps the overlay aligned with what the model saw.
    """
    pymupdf = _pymupdf()
    dpi = int(min(400, max(60, dpi)))
    cache = PAGES_CACHE_DIR / f"{path.stem}-p{int(page_no)}-{dpi}.png"
    stamp = f"{path.stat().st_mtime_ns}-{path.stat().st_size}"
    sidecar = cache.with_suffix(".json")
    if cache.exists() and sidecar.exists():
        try:
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
        except Exception:
            meta = None
        if meta and meta.get("stamp") == stamp:
            meta["cached"] = True
            return cache.read_bytes(), meta

    with pymupdf.open(str(path)) as doc:
        if not (1 <= int(page_no) <= len(doc)):
            raise IndexError(f"page {page_no} out of range (document has {len(doc)} pages)")
        page = doc[int(page_no) - 1]
        # every page attribute must be read inside the context: a Page is invalid once closed
        rect = page.rect
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False, colorspace=pymupdf.csRGB)
        png = pix.tobytes("png")
        meta = {"stamp": stamp, "cached": False, "page_no": int(page_no), "dpi": dpi,
                "width_px": int(pix.width), "height_px": int(pix.height),
                "width_pt": round(float(rect.width), 2), "height_pt": round(float(rect.height), 2),
                "rotation": int(page.rotation or 0)}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(png)
    sidecar.write_text(json.dumps(meta), encoding="utf-8")
    return png, meta


# --------------------------------------------------------------------------- health
def health(deep: bool = False) -> dict:
    """Connectivity of the three external systems the portal depends on (never a verdict)."""
    s = settings()
    out: dict[str, Any] = {"mode": s.mode, "ai_mode": s.ai_mode,
                           "model_vision": s.model_vision, "model_reasoning": s.model_reasoning,
                           "perception_cache": s.perception_cache}

    rd = reader()
    out["paperless"] = {"configured": bool(s.paperless_url)}
    if rd is not None:
        try:
            out["paperless"].update({"ok": True, **rd.health()})
        except Exception as e:
            out["paperless"].update({"ok": False, "error": f"{type(e).__name__}: {str(e)[:160]}"})

    out["litellm"] = {"configured": bool(s.litellm_url), "url": s.litellm_url or None}
    if s.litellm_url:
        try:
            with httpx.Client(timeout=8) as c:
                r = c.get(s.litellm_url.rstrip("/") + "/health/liveliness",
                          headers={"Authorization": f"Bearer {s.litellm_key}"} if s.litellm_key else {})
                ok = r.status_code < 400
                if not ok:                                   # some gateways only expose /v1/models
                    r = c.get(s.litellm_url.rstrip("/") + "/models",
                              headers={"Authorization": f"Bearer {s.litellm_key}"} if s.litellm_key else {})
                    ok = r.status_code < 400
                out["litellm"].update({"ok": bool(ok), "status": r.status_code})
        except Exception as e:
            out["litellm"].update({"ok": False, "error": f"{type(e).__name__}: {str(e)[:160]}"})

    out["oracle"] = {"configured": bool(s.oracle_mcp_url or s.oracle_dsn), "backend": s.oracle_backend}
    if deep and s.oracle_backend == "mcp" and s.oracle_mcp_url:
        try:
            from system_a.adapters.oracle.mcp_repository import McpSqlClient, parse_csv_rows
            client = McpSqlClient(s.oracle_mcp_url, s.oracle_mcp_token, timeout_s=s.oracle_timeout_s)
            # McpSqlClient.run() returns the tool's text payload (CSV-ish); no .query() method exists
            txt = client.run("SELECT 1 AS OK FROM dual")
            rows = parse_csv_rows(txt, expect=("OK",)) or parse_csv_rows(txt)
            out["oracle"].update({"ok": bool(rows) or "OK" in str(txt).upper(),
                                  "probe": "SELECT 1 FROM dual", "rows": rows[:1] or None,
                                  "sample": str(txt)[:120]})
        except Exception as e:
            out["oracle"].update({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"})
    elif deep and s.oracle_backend == "db" and s.oracle_dsn:
        try:
            import oracledb
            with oracledb.connect(user=s.oracle_user, password=s.oracle_password, dsn=s.oracle_dsn) as conn:
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM dual")
                out["oracle"].update({"ok": cur.fetchone() is not None, "probe": "SELECT 1 FROM dual"})
        except Exception as e:
            out["oracle"].update({"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"})
    return out
