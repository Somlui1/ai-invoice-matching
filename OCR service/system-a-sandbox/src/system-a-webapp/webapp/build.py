"""Wiring: Settings -> document source + Perception + Engine + store -> DocumentService -> FastAPI app.

Two document sources share the same service and UI:

* ``batch``     - a folder the OCR engine already produced (``report.html`` + page JPGs); perception replays it.
* ``paperless`` - the documents of the DMS themselves; perception reads each file here and now with System A.
"""
from __future__ import annotations

import logging

from .batch import BatchError, BatchSource
from .config import Settings, ensure_system_a
from .engine import build_engine
from .perception import build_perception_for
from .service import DocumentService
from .store import MemoryStore, ResultStore

log = logging.getLogger("webapp")


def warm_up() -> None:
    """Import the heavy System A modules and read the Standard now, so the first Process is not slower than the rest."""
    from system_a.domain.standard import load_standard
    from system_a.perception import vision_pipeline  # noqa: F401
    load_standard()


def borrow_system_a_env(settings: Settings, pkg_dir) -> None:
    """Fill the System A settings this process does not have from ``<SYSTEM_A_HOME>/.env``.

    System A's library code reads its secrets (LiteLLM, Oracle, Paperless) from ``os.environ`` only, and it does
    not load that file itself - its CLI scripts do.  Real environment variables (and this app's own ``.env``,
    which ``Settings.from_env`` already exported) keep winning, so nothing here overrides an explicit setting and
    no secret is copied into this project.
    """
    if not settings.system_a_env:
        return
    try:
        from system_a.envfile import load_env
        loaded = load_env(str(pkg_dir.parent / ".env"))
    except Exception as e:                                # a missing .env is normal on a clean checkout
        log.info("no System A .env to borrow (%s)", e)
        return
    if loaded:
        log.info("System A settings borrowed from %s: %d key(s)", pkg_dir.parent / ".env", len(loaded))


def build_source(settings: Settings):
    """The document list the left panel shows: a batch folder, or Paperless itself."""
    if settings.doc_source != "paperless":
        return BatchSource(settings.batch_path)
    from system_a.adapters.paperless.reader import PaperlessReader
    from .paperless import PaperlessSource
    reader = PaperlessReader(base_url=settings.paperless_url, token=settings.paperless_token,
                             timeout_s=max(60.0, settings.http_timeout_s))
    source = PaperlessSource(reader, limit=settings.paperless_limit, tags=settings.paperless_tags.split(","),
                             render_dpi=settings.render_dpi)
    source.refresh()
    if source.list_error and not source.docs:
        raise BatchError(source.list_error)                # without a single document the portal has no purpose
    return source


def build_all(settings: Settings, *, engine=None, perception=None, source=None):
    """Return ``(app, service, source)``.  ``engine`` / ``perception`` / ``source`` can be injected (tests)."""
    from .app import create_app
    settings.validate()
    home = ensure_system_a(settings.system_a_home)
    borrow_system_a_env(settings, home)
    warm_up()
    batch = source if source is not None else build_source(settings)
    eng = engine or build_engine(settings, home)
    per = perception or build_perception_for(settings, batch)
    store = ResultStore(settings.data_dir) if settings.persist_results else MemoryStore()
    service = DocumentService(batch, per, eng, store, workers=settings.workers)
    info = batch.stats()
    log.info("source=%s (%s documents) | engine=%s perception=%s | results %s",
             getattr(batch, "kind", "batch"), info.get("documents"), eng.name, per.name,
             "on disk in " + str(store.root) if settings.persist_results else "in memory (the browser holds the cases)")
    return create_app(settings, service, batch), service, batch
