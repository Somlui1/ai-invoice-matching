"""The only module in this project that touches System A.

Everything the portal does with a document goes through the functions here, and every one of them is System A's
own code - the portal reimplements no reading, no coordinate handling and no business rule:

``init()``             put System A on ``sys.path``, load ``<SYSTEM_A_HOME>/.env`` with System A's own loader
                       (``system_a.envfile``), then import its entrypoint ``process_pdf.py``
``process(doc_id)``    ``process_pdf(dms_id=...)`` - the repository's own single-document entrypoint:
                       Paperless download -> image/PDF ingest -> VisionPipeline -> Oracle + rules V-01..V-09
                       -> ``aiva.system_a.result/3.0``.  The same call ``scripts/test_paperless_invoices.py`` makes
``perceive(doc_id)``   only the reading half of that entrypoint (used by ``SYSTEM_A_ENGINE=http``, whose API
                       still requires an extraction in the body - see ``api/app.py``)
``pdf_bytes(doc_id)``  the document's own file, through ``system_a.container.build_paperless``
``page_image(...)``    a page rendered as PNG, through ``system_a.perception.pdf_ingest.ingest_pdf``

An error raised inside System A is **not** translated or softened: the caller stores the exception type, its
message and the traceback, and the UI shows it.  A failed run produces no partial view on purpose.
"""
from __future__ import annotations

import hashlib
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _png_size(png: bytes) -> tuple[int, int]:
    """``(width_px, height_px)`` of a rendered page, so the overlay can be laid out at the image's own ratio."""
    import io

    from PIL import Image
    with Image.open(io.BytesIO(png)) as im:
        return im.size


class SystemAError(RuntimeError):
    """System A raised while processing a document (the traceback travels with it)."""

    def __init__(self, message: str, *, traceback: str = "", exc_type: str = ""):
        super().__init__(message)
        self.traceback = traceback
        self.exc_type = exc_type or "Error"


@dataclass
class SystemA:
    """The imported System A, with the pieces the portal drives."""

    root: Path
    settings: object                            # webapp.config.Settings (the portal's own)
    process_pdf: object = None                  # the repository's entrypoint function
    container: object = None                    # system_a.container (Settings/builders)
    orchestrator: object = None
    standard: object = None                     # the loaded Standard (for /api/health)
    _a_settings: object = None
    _lock: threading.Lock = None                # type: ignore[assignment]
    _pages: dict = None                         # type: ignore[assignment]  sha -> {page_no: (png, (w, h))}

    # -- the pipeline -----------------------------------------------------------------
    def process(self, doc_id: int) -> dict:
        """Run System A's own single-document entrypoint on a Paperless document and return its result 3.0."""
        import traceback as _tb
        try:
            return self.process_pdf(dms_id=int(doc_id), output_path=None, mode=self.settings.mode,
                                    quick=self.settings.quick, json_only=False, quiet=True)
        except Exception as e:                                  # never softened: type + message + traceback
            raise SystemAError(f"System A failed on #{doc_id}: {type(e).__name__}: {e}",
                               traceback=_tb.format_exc(), exc_type=type(e).__name__) from e

    def a_settings(self):
        """A fresh ``system_a.container.Settings`` (``quick``/``mode`` applied the way ``process_pdf`` does)."""
        from dataclasses import replace
        s = self.container.Settings()
        if self.settings.mode == "production":
            s = replace(s, mode="production", ai_mode="litellm")
        else:
            s = replace(s, mode="sandbox", ai_mode="sim")
        if self.settings.quick:
            s = replace(s, do_crops=False, do_table=False)
        return s

    def perceive(self, doc_id: int) -> dict:
        """System A's reading half only - the extraction that ``process()`` would hand to the rules."""
        import traceback as _tb
        try:
            s = self.a_settings()
            data = self.pdf_bytes(int(doc_id))
            pdf = data if self.ingest.is_pdf(data) else self.ingest.pdf_from_image(data)
            pipe = self.container.build_perception(s)
            ext = pipe.extract(pdf, package_id=f"PKG-DMS-{doc_id}", dms_doc_id=f"DMS-{doc_id}")
            return ext.model_dump(mode="json")
        except Exception as e:
            raise SystemAError(f"System A perception failed on #{doc_id}: {type(e).__name__}: {e}",
                               traceback=_tb.format_exc(), exc_type=type(e).__name__) from e

    # -- the file itself --------------------------------------------------------------
    def download_dir(self) -> Path:
        """Where ``process_pdf`` keeps the files it fetched from Paperless - the same folder, so nobody
        downloads a document twice."""
        d = self.root / ".cache" / "downloads"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def pdf_bytes(self, doc_id: int) -> bytes:
        import traceback as _tb
        try:
            f = self.download_dir() / f"DMS-{int(doc_id)}.pdf"
            if f.is_file() and f.stat().st_size:
                return f.read_bytes()
            reader = self.container.build_paperless(self.a_settings())
            raw = reader.download(int(doc_id))
            if not raw:
                raise SystemAError(f"Paperless returned 0 bytes for #{doc_id}")
            f.write_bytes(raw)
            return raw
        except SystemAError:
            raise
        except Exception as e:
            raise SystemAError(f"cannot read #{doc_id} from Paperless: {type(e).__name__}: {e}",
                               traceback=_tb.format_exc(), exc_type=type(e).__name__) from e

    # -- page images (drawing surface for the boxes; the geometry itself comes from the payload)
    def page_image(self, doc_id: int, page: int, dpi: int) -> tuple[bytes, tuple[int, int]]:
        import traceback as _tb
        try:
            data = self.pdf_bytes(int(doc_id))
            sha = hashlib.sha256(data).hexdigest()[:16]
            with self._lock:
                cached = self._pages.get((sha, int(dpi)))
            if cached is None:
                rendered = self.ingest.ingest_pdf(data, dpi=int(dpi), render=True)[1]
                cached = {rp.info.page_no: (rp.png, _png_size(rp.png)) for rp in rendered}
                with self._lock:
                    self._pages[(sha, int(dpi))] = cached
            got = cached.get(int(page))
            if got is None:
                raise SystemAError(f"#{doc_id} has no page {page}")
            return got
        except SystemAError:
            raise
        except Exception as e:
            raise SystemAError(f"cannot render page {page} of #{doc_id}: {type(e).__name__}: {e}",
                               traceback=_tb.format_exc(), exc_type=type(e).__name__) from e

    def page_count(self, doc_id: int) -> Optional[int]:
        """How many pages the file really has - measured by System A's own ingest, without rendering."""
        try:
            return len(self.ingest.ingest_pdf(self.pdf_bytes(int(doc_id)), dpi=72, render=False)[1])
        except Exception:
            return None

    # -- health -----------------------------------------------------------------------
    def health(self) -> dict:
        std = self.standard
        s = self.a_settings()
        return {"engine": self.settings.engine, "ok": True, "mode": s.mode, "ai_mode": s.ai_mode,
                "standard": std.version, "ruleset": std.ruleset_version,
                "vision_model": s.model_vision, "oracle_backend": s.oracle_backend, "home": str(self.root)}


def init(settings) -> SystemA:
    """Import System A and load *its* configuration.  Called once at startup (and by ``webapp check``)."""
    from .config import ensure_system_a

    root = ensure_system_a(settings.system_a_home)

    # System A's library code reads its configuration from os.environ only, and its scripts load <root>/.env
    # themselves (process_pdf does).  Doing it here, before anything under system_a is imported, is what makes
    # the values real: system_a.container reads them once, at import.  See agent/errors-and-solutions.md.
    from system_a.envfile import load_env
    load_env(str(root / ".env"))

    # The perception cache is keyed by file + model + prompt + options; sharing the folder System A's own
    # scripts use means a document already read by scripts/test_paperless_invoices.py is not read again.
    os.environ.setdefault("PERCEPTION_CACHE_DIR", str(root / ".cache" / "perception"))

    import process_pdf                                   # the repository's single-document entrypoint
    from system_a import container
    from system_a.application import orchestrator
    from system_a.domain.standard import load_standard
    from system_a.perception import pdf_ingest

    sa = SystemA(root=root, settings=settings, process_pdf=process_pdf.process_pdf, container=container,
                 orchestrator=orchestrator)
    sa.ingest = pdf_ingest
    sa.standard = load_standard()
    sa._lock, sa._pages = threading.Lock(), {}
    return sa
