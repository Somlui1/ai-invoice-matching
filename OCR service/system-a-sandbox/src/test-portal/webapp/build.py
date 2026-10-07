"""Wiring: ``Settings`` -> System A + document list + runner + store -> :class:`DocumentService` -> FastAPI.

There is one path only: the documents are the real ones in Paperless, and a document is processed by System A's
own code (:mod:`webapp.sysa`).  The portal contributes a list, a queue and a screen - nothing else.
"""
from __future__ import annotations

import logging

from .config import Settings
from .store import MemoryStore, ResultStore

log = logging.getLogger("webapp")


def build_catalog(settings: Settings, sa):
    """The document list, read through System A's Paperless reader."""
    from .catalog import Catalog, CatalogError

    try:
        catalog = Catalog(sa, tag=settings.paperless_tag, limit=settings.paperless_limit)
        catalog.refresh()
    except CatalogError:
        raise
    except Exception as e:                            # a DMS that cannot even be talked to: say so, do not pretend
        raise CatalogError(f"System A อ่าน Paperless ไม่ได้: {type(e).__name__}: {e}") from e
    if catalog.list_error and not catalog.docs:
        raise CatalogError(catalog.list_error)                 # without a single document the portal has no purpose
    return catalog


def build_all(settings: Settings, *, sa=None, catalog=None, runner=None):
    """Return ``(app, service, catalog)``.  ``sa`` / ``catalog`` / ``runner`` can be injected (tests)."""
    from .app import create_app
    from .engine import build_runner
    from .service import DocumentService
    from . import sysa

    settings.validate()
    sa = sa if sa is not None else sysa.init(settings)
    catalog = catalog if catalog is not None else build_catalog(settings, sa)
    run = runner if runner is not None else build_runner(settings, sa)
    store = ResultStore(settings.data_dir) if settings.persist_results else MemoryStore()
    service = DocumentService(catalog, run, store, workers=settings.workers, mode=settings.mode)
    info = catalog.stats()
    log.info("%s | documents=%s | engine=%s mode=%s | results %s", sa.health().get("home"), info.get("documents"),
             run.name, settings.mode, "on disk in " + str(store.root) if settings.persist_results
             else "in memory (the browser holds the cases)")
    for t in info.get("unmatched_tags") or []:
        log.warning("no tag named %r in the DMS: the list is unfiltered", t)
    return create_app(settings, service, catalog), service, catalog
