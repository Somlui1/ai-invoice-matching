"""HTTP API + the single-page UI.

    GET    /                                      the UI
    GET    /api/meta                              what this instance is wired to (engine, mode, source, colours)
    GET    /api/health                            System A reachable? the DMS reachable?
    GET    /api/documents                         every document with its state
    POST   /api/documents/refresh                 re-read the document list from the DMS
    GET    /api/documents/{id}                    one document's state (poll while processing)
    POST   /api/documents/{id}/process            start (202) - 409 if that document is already running
    GET    /api/documents/{id}/result             the screen model: boxes from ``ocr.elements``, Final, Verify
    GET    /api/documents/{id}/payload            the raw aiva.system_a.result/3.0, exactly as System A returned it
    GET    /api/documents/{id}/extraction         the ``extraction`` block of that payload (what System A read)
    DELETE /api/documents/{id}/result             forget the result of that document (server side)
    GET    /api/documents/{id}/pdf                the document's own file, inline
    GET    /api/documents/{id}/pages/{n}/image    that page rendered, to draw the boxes on
    GET    /api/search?q=                         ids of processed documents whose payload text contains q

There is no stand-in page and no second source anywhere in here: if System A did not produce something, the
request says so (409 while it has not run, 502 when the file cannot be read) and the UI shows the failure.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response

from . import __version__
from .config import Settings
from .service import Busy, DocumentService, NotReady
from .view import COLORS, DEFAULT_TYPES, ELEMENT_TYPES

log = logging.getLogger("webapp.api")
STATIC = Path(__file__).resolve().parent / "static"
NO_STORE = {"Cache-Control": "no-store"}
LONG_CACHE = {"Cache-Control": "private, max-age=3600"}


def create_app(settings: Settings, service: DocumentService, catalog) -> FastAPI:
    app = FastAPI(title="AIVA System A test portal", version=__version__)

    def doc_or_404(doc_id: int):
        try:
            return catalog.get(doc_id)
        except KeyError:
            raise HTTPException(404, f"unknown document {doc_id}") from None

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html", headers=NO_STORE, media_type="text/html")

    @app.get("/static/app.js", include_in_schema=False)
    def js():
        return FileResponse(STATIC / "app.js", headers=NO_STORE, media_type="application/javascript")

    @app.get("/api/meta")
    def meta():
        return {"version": __version__, "engine": settings.engine, "mode": settings.mode, "quick": settings.quick,
                "persist": settings.persist_results, "workers": settings.workers, "render_dpi": settings.render_dpi,
                "source": catalog.stats(), "system_a": str(settings.system_a_home or ""),
                "colors": COLORS, "element_types": list(ELEMENT_TYPES), "default_types": list(DEFAULT_TYPES)}

    @app.get("/api/health")
    def health():
        eng = service.runner.health()
        src = {"kind": catalog.kind}
        try:                                                # one cheap call, never fatal
            src.update(catalog.health())
        except Exception as e:
            src.update(error=f"{type(e).__name__}: {e}"[:200])
        return JSONResponse({"ok": bool(eng.get("ok")), "engine": eng, "source": src, "kind": catalog.kind,
                             "mode": settings.mode, "documents": len(catalog.docs)},
                            status_code=200 if eng.get("ok") else 503)

    @app.get("/api/documents")
    def documents():
        return service.list_documents()

    @app.post("/api/documents/refresh")
    def refresh():
        from .catalog import CatalogError
        try:
            catalog.refresh()
        except CatalogError as e:
            raise HTTPException(502, str(e)) from None
        return {"documents": len(catalog.docs), "pages": sum(d.pages_total or 0 for d in catalog.docs),
                "error": catalog.list_error}

    @app.get("/api/documents/{doc_id}")
    def document(doc_id: int):
        d = doc_or_404(doc_id)
        source_error = None
        try:                                                # the page count only exists once the file has been read
            d = catalog.ensure(doc_id) or d
        except Exception as e:
            source_error = f"อ่านไฟล์เอกสารจาก Paperless ไม่สำเร็จ: {type(e).__name__}: {e}"[:300]
        return {**service.status(doc_id), "source_error": source_error}

    @app.post("/api/documents/{doc_id}/process", status_code=202)
    def process(doc_id: int):
        doc_or_404(doc_id)
        try:
            return service.start(doc_id)
        except Busy as e:
            raise HTTPException(409, str(e)) from None

    @app.get("/api/documents/{doc_id}/result")
    def result(doc_id: int):
        doc_or_404(doc_id)
        try:
            return JSONResponse(service.view(doc_id), headers=NO_STORE)
        except NotReady as e:
            raise HTTPException(409, str(e)) from None

    @app.get("/api/documents/{doc_id}/payload")
    def payload(doc_id: int):
        doc_or_404(doc_id)
        try:
            return JSONResponse(service.part(doc_id, "payload"), headers=NO_STORE)
        except NotReady as e:
            raise HTTPException(409, str(e)) from None

    @app.get("/api/documents/{doc_id}/extraction")
    def extraction(doc_id: int):
        """The ``extraction`` block *inside* the result - System A echoes what it read, boxes and all."""
        doc_or_404(doc_id)
        try:
            data = service.part(doc_id, "payload").get("extraction")
        except NotReady as e:
            raise HTTPException(409, str(e)) from None
        if data is None:
            raise HTTPException(409, "this payload carries no extraction block")
        return JSONResponse(data, headers=NO_STORE)

    @app.delete("/api/documents/{doc_id}/result")
    def delete(doc_id: int):
        doc_or_404(doc_id)
        try:
            return service.delete(doc_id)
        except Busy as e:
            raise HTTPException(409, str(e)) from None

    @app.get("/api/documents/{doc_id}/pdf")
    def pdf(doc_id: int):
        doc_or_404(doc_id)
        try:
            raw = catalog.sa.pdf_bytes(doc_id)
        except Exception as e:
            raise HTTPException(502, f"อ่านไฟล์ของเอกสาร #{doc_id} ไม่ได้: {e}") from None
        return Response(raw, media_type="application/pdf",
                        headers={**LONG_CACHE, "Content-Disposition": f'inline; filename="DMS-{doc_id}.pdf"'})

    @app.get("/api/documents/{doc_id}/pages/{page}/image")
    def image(doc_id: int, page: int):
        doc_or_404(doc_id)
        try:
            png, _size = catalog.sa.page_image(doc_id, page, settings.render_dpi)
        except Exception as e:
            raise HTTPException(502, f"อ่านหน้า {page} ของเอกสาร #{doc_id} ไม่ได้: {e}") from None
        return Response(png, media_type="image/png", headers=LONG_CACHE)

    @app.get("/api/search")
    def search(q: str = Query("", max_length=200)):
        return {"q": q, "ids": service.search(q)}

    return app
