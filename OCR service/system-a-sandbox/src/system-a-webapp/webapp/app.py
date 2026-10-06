"""HTTP API + the single-page UI.

    GET    /                                      the UI
    GET    /api/meta                              what this instance is wired to (engine, perception, source)
    GET    /api/health                            engine reachable? source reachable?
    GET    /api/documents                         every document with its state
    POST   /api/documents/refresh                 re-read the document list from the source
    GET    /api/documents/{id}                    one document's state (poll while processing)
    POST   /api/documents/{id}/process            start (202) - 409 if that document is already running
    GET    /api/documents/{id}/result             OCR items + boxes, Final Result, Verify Result
    GET    /api/documents/{id}/payload            the raw aiva.system_a.result/3.0 from System A
    GET    /api/documents/{id}/extraction         the aiva.extraction/2.0 that was sent to System A
    DELETE /api/documents/{id}/result             forget the result of that document (server side)
    GET    /api/documents/{id}/pdf                the document's own PDF, inline
    GET    /api/documents/{id}/pages/{n}/image    that page rendered (SVG stand-in when there is no image)
    GET    /api/search?q=                         ids of processed documents whose text contains q

With ``WEBAPP_PERSIST=false`` the server holds nothing on disk: the browser keeps the processed cases (see
``static/app.js``), and a restart leaves only the document list behind.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .batch import BatchSource
from .config import Settings
from .placeholder import page_svg
from .service import Busy, DocumentService, NotReady

log = logging.getLogger("webapp.api")
STATIC = Path(__file__).resolve().parent / "static"
NO_STORE = {"Cache-Control": "no-store"}
LONG_CACHE = {"Cache-Control": "private, max-age=3600"}


def create_app(settings: Settings, service: DocumentService, batch: BatchSource) -> FastAPI:
    app = FastAPI(title="AIVA System A test application", version=__version__)

    def doc_or_404(doc_id: int):
        try:
            return batch.get(doc_id)
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
        report = getattr(batch, "report_path", None)
        source = {"kind": getattr(batch, "kind", "batch"), "report": str(report) if report else None,
                  "base_url": getattr(batch, "base_url", ""), **batch.stats()}
        return {"version": __version__, "perception": settings.perception, "engine": settings.engine,
                "source": source, "batch": source,                     # ``batch`` kept for older clients
                "colors": batch.colors, "persist": settings.persist_results,
                "workers": settings.workers, "render_dpi": settings.render_dpi,
                "replay": {"assume_agreement": settings.replay_assume_agreement,
                           "confidence": settings.replay_confidence} if settings.perception == "replay" else None}

    @app.get("/api/health")
    def health():
        eng = service.engine.health()
        src = {"kind": getattr(batch, "kind", "batch")}
        if hasattr(batch, "health"):                                # Paperless: one cheap call, never fatal
            try:
                src.update(batch.health())
            except Exception as e:
                src.update(error=f"{type(e).__name__}: {e}"[:200])
        return JSONResponse({"ok": bool(eng.get("ok")), "engine": eng, "source": src, "kind": src["kind"],
                             "perception": settings.perception, "documents": len(batch.docs)},
                            status_code=200 if eng.get("ok") else 503)

    @app.get("/api/documents")
    def documents():
        return service.list_documents()

    @app.post("/api/documents/refresh")
    def refresh():
        """ดึงรายการเอกสารจากแหล่งของมันใหม่ (ปุ่มรีเฟรช) — batch ไม่ต้องมีขั้นตอนนี้"""
        if not hasattr(batch, "refresh"):
            raise HTTPException(400, "this document source cannot be refreshed")
        batch.refresh()
        err = getattr(batch, "list_error", None)
        if err and not batch.docs:
            raise HTTPException(502, err)
        return {"documents": len(batch.docs), "pages": sum(d.pages_total for d in batch.docs), "error": err}

    @app.get("/api/documents/{doc_id}")
    def document(doc_id: int):
        d = doc_or_404(doc_id)
        source_error = None
        if hasattr(batch, "ensure"):                                # Paperless: the page count is only known from the file
            try:
                d = batch.ensure(doc_id) or d
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
        doc_or_404(doc_id)
        try:
            return JSONResponse(service.part(doc_id, "extraction"), headers=NO_STORE)
        except NotReady as e:
            raise HTTPException(409, str(e)) from None

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
        provider = getattr(batch, "pdf_bytes", None)
        if provider is None:
            raise HTTPException(404, "this document source has no PDF to serve")
        try:
            raw, _origin = provider(doc_id)
        except Exception as e:
            raise HTTPException(502, f"อ่านไฟล์ของเอกสาร #{doc_id} ไม่ได้: {e}") from None
        return Response(raw, media_type="application/pdf",
                        headers={**LONG_CACHE, "Content-Disposition": f'inline; filename="doc_{doc_id}.pdf"'})

    @app.get("/api/documents/{doc_id}/pages/{page}/image")
    def image(doc_id: int, page: int):
        d = doc_or_404(doc_id)
        bp = next((p for p in d.pages if p.page == page), None)
        if bp is None and hasattr(batch, "ensure"):        # ไฟล์เท่านั้นที่นับหน้าได้: อ่านไฟล์ก่อนแล้วดูใหม่
            try:
                d = batch.ensure(doc_id) or d
                bp = next((p for p in d.pages if p.page == page), None)
            except Exception:
                pass
        if bp is None:
            raise HTTPException(404, f"#{doc_id} has no page {page}")
        try:
            got = batch.page_image(doc_id, page)
        except Exception as e:
            raise HTTPException(502, f"อ่านหน้า {page} ของเอกสาร #{doc_id} ไม่ได้: {e}") from None
        if got is not None:
            data, media_type = got
            return Response(data, media_type=media_type, headers=LONG_CACHE)
        note = f"image not found: {bp.image}" if bp.image else "no image for this page"
        return Response(page_svg(bp, note), media_type="image/svg+xml", headers=NO_STORE)

    @app.get("/api/search")
    def search(q: str = Query("", max_length=200)):
        return {"q": q, "ids": service.search(q)}

    docs_dir = Path(batch.root) / "docs" if getattr(batch, "root", None) else None
    if docs_dir is not None and docs_dir.is_dir():           # viewer.html pages of a batch (the DMS has its own UI)
        app.mount("/batch/docs", StaticFiles(directory=docs_dir), name="batch-docs")
    return app
