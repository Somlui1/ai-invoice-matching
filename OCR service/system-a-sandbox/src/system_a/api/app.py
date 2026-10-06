"""HTTP API for AIVA Web Portal (async, idempotent, correlation-aware).

POST /v1/validations                -> 202 {validation_id}
GET  /v1/validations/{id}            -> status
GET  /v1/validations/{id}/result     -> aiva.system_a.result/3.0
POST /v1/validations/{id}/revalidate -> new round (Oracle re-queried, extraction reused)
GET  /v1/schemas/result/3.0 · /health/live · /health/ready · /metrics
"""
from __future__ import annotations

import json
import logging
import uuid
from collections import Counter
from pathlib import Path
from typing import Callable, Optional

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ..application.jobs import JobStore, idempotency_fingerprint
from ..application.orchestrator import Services, validate
from ..container import Settings
from ..domain.contracts import ExtractionResult
from ..domain.standard import load_standard

log = logging.getLogger("system_a.api")
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schemas" / "result-3.0.schema.json"


class PortalRefs(BaseModel):
    document_revision: int = 1
    validation_round: int = 1


class Options(BaseModel):
    ruleset: str = "v6.6"
    callback_url: Optional[str] = None


class ValidationRequest(BaseModel):
    extraction: Optional[dict] = Field(None, description="aiva.extraction/2.0 (sandbox / pre-extracted)")
    package: Optional[dict] = Field(None, description='{"source":"paperless","dms_doc_id":"190"} (production)')
    portal_refs: PortalRefs = PortalRefs()
    options: Options = Options()


def create_app(settings: Settings, services_factory: Callable[[], Services]) -> FastAPI:
    app = FastAPI(title="System A — Document Intelligence & Validation Engine", version="1.0.0")
    store, std, counters = JobStore(settings.result_ttl_s), load_standard(), Counter()

    def auth(x_api_key: str = Header(default="")):
        if settings.api_key and x_api_key != settings.api_key:
            raise HTTPException(401, "invalid api key")

    def run(vid: str, ext: ExtractionResult, request: dict, callback: Optional[str]):
        store.set(vid, status="running")
        try:
            res = validate(ext, services_factory(), request=request, std=std)
            store.set(vid, status="completed", result=res)
            counters[f"recommendation_{res['recommendation']['value']}"] += 1
            if callback:
                try:
                    httpx.post(callback, json={"validation_id": vid, "status": "completed",
                                               "recommendation": res["recommendation"]["value"]}, timeout=10)
                except Exception as e:  # callback failure never fails the job; portal can poll
                    log.warning("callback failed: %s", e)
        except Exception as e:
            log.exception("validation failed")
            store.set(vid, status="failed", error={"code": "INTERNAL_ERROR", "detail": type(e).__name__})
            counters["jobs_failed"] += 1

    @app.post("/v1/validations", status_code=202, dependencies=[Depends(auth)])
    def create(body: ValidationRequest, bg: BackgroundTasks, idempotency_key: str = Header(default=""),
               x_correlation_id: str = Header(default="")):
        if body.extraction is None:
            raise HTTPException(501, "package ingestion requires production perception (VlmExtractor); "
                                     "send 'extraction' in sandbox")
        try:
            ext = ExtractionResult.model_validate(body.extraction)
        except Exception as e:
            raise HTTPException(422, f"invalid extraction: {e}") from e
        svc_models = services_factory().models or {}
        fp = idempotency_fingerprint(body.extraction, std.ruleset_version, svc_models,
                                     body.portal_refs.validation_round, idempotency_key or None)
        vid, new = store.create_or_get(fp)
        if new:
            request = {"validation_id": vid, "correlation_id": x_correlation_id or str(uuid.uuid4()),
                       "idempotency_key": idempotency_key or None, **body.portal_refs.model_dump()}
            store.put_input(vid, {"extraction": body.extraction, "request": request,
                                  "callback": body.options.callback_url})
            bg.add_task(run, vid, ext, request, body.options.callback_url)
            counters["jobs_created"] += 1
        return {"validation_id": vid, "status": store.get(vid)["status"], "idempotent_replay": not new}

    @app.get("/v1/validations/{vid}", dependencies=[Depends(auth)])
    def status(vid: str):
        j = store.get(vid)
        if not j:
            raise HTTPException(404, "not found")
        return {"validation_id": vid, "status": j["status"], "error": j["error"]}

    @app.get("/v1/validations/{vid}/result", dependencies=[Depends(auth)])
    def result(vid: str):
        j = store.get(vid)
        if not j:
            raise HTTPException(404, "not found")
        if j["status"] != "completed":
            raise HTTPException(409, f"status={j['status']}")
        return j["result"]

    @app.post("/v1/validations/{vid}/revalidate", status_code=202, dependencies=[Depends(auth)])
    def revalidate(vid: str, bg: BackgroundTasks, portal_refs: PortalRefs):
        j = store.get(vid)
        if not j or not j["input"]:
            raise HTTPException(404, "not found or expired")
        body = ValidationRequest(extraction=j["input"]["extraction"], portal_refs=portal_refs,
                                 options=Options(callback_url=j["input"]["callback"]))
        return create(body, bg, idempotency_key=f"reval:{vid}:{portal_refs.validation_round}",
                      x_correlation_id=j["input"]["request"]["correlation_id"])

    @app.get("/v1/schemas/result/3.0")
    def schema():
        return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        return {"status": "ok", "mode": settings.mode, "ai_mode": settings.ai_mode, "standard": std.version,
                "ruleset": std.ruleset_version}

    @app.get("/metrics")
    def metrics():
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("\n".join(f"system_a_{k} {v}" for k, v in sorted(counters.items())) + "\n")

    return app


def default_app() -> FastAPI:
    """uvicorn entrypoint.  Sandbox: Oracle data from sandbox/oracle_dataset.json."""
    s = Settings()
    ds_path = Path(__file__).resolve().parents[3] / "sandbox_data" / "oracle_dataset.json"
    ds = json.loads(ds_path.read_text(encoding="utf-8")) if ds_path.exists() else {}
    from ..container import build_services
    return create_app(s, lambda: build_services(s, oracle_dataset=ds))
