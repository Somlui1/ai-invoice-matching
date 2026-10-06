"""The one seam between this application and System A: ``Engine.validate(extraction) -> aiva.system_a.result/3.0``.

* ``InProcessEngine`` imports System A and calls ``application.orchestrator.validate`` directly - the same function
  its HTTP API calls, so the result is byte-for-byte what the API would return.
* ``HttpEngine`` talks to a running System A (``POST /v1/validations`` then poll, then fetch the result).

Both take the extraction as a plain dict (``aiva.extraction/2.0``) and return the result dict.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Optional, Protocol

import httpx


class EngineError(RuntimeError):
    """System A could not produce a result (transport, HTTP error, failed job, timeout)."""


class Engine(Protocol):
    name: str

    def validate(self, extraction: dict, *, doc_id: int, run: int) -> dict: ...

    def health(self) -> dict: ...


def _request(doc_id: int, run: int, correlation: Optional[str] = None) -> dict:
    return {"validation_id": f"WEB-{doc_id}-{run}-{uuid.uuid4().hex[:8]}",
            "correlation_id": correlation or f"web-{doc_id}-{run}", "idempotency_key": None,
            "document_revision": 1, "validation_round": run}


class InProcessEngine:
    name = "inprocess"

    def __init__(self, oracle_dataset: Optional[dict] = None, sa_settings=None):
        from system_a.container import Settings
        self.sa = sa_settings or Settings()
        self.dataset = oracle_dataset or {}

    def validate(self, extraction: dict, *, doc_id: int, run: int) -> dict:
        from system_a.application.orchestrator import validate
        from system_a.container import build_services
        from system_a.domain.contracts import ExtractionResult
        from system_a.domain.standard import load_standard
        try:
            ext = ExtractionResult.model_validate(extraction)
            svc = build_services(self.sa, oracle_dataset=self.dataset)
            return validate(ext, svc, request=_request(doc_id, run), std=load_standard())
        except Exception as e:                                 # one clear message; the log has the traceback
            raise EngineError(f"System A (in-process) failed: {type(e).__name__}: {e}") from e

    def health(self) -> dict:
        from system_a.domain.standard import load_standard
        std = load_standard()
        return {"engine": self.name, "ok": True, "mode": self.sa.mode, "ai_mode": self.sa.ai_mode,
                "standard": std.version, "ruleset": std.ruleset_version}


class HttpEngine:
    name = "http"

    def __init__(self, base_url: str, api_key: str = "", timeout_s: float = 300.0, poll_s: float = 0.4,
                 client: Optional[httpx.Client] = None):
        self.base, self.key, self.timeout, self.poll = base_url.rstrip("/"), api_key, timeout_s, poll_s
        self.http = client or httpx.Client(timeout=30.0)

    def _h(self, extra: Optional[dict] = None) -> dict:
        return {**({"X-API-Key": self.key} if self.key else {}), **(extra or {})}

    def _url(self, path: str) -> str:
        return self.base + path

    def validate(self, extraction: dict, *, doc_id: int, run: int) -> dict:
        body = {"extraction": extraction, "portal_refs": {"document_revision": 1, "validation_round": run}}
        try:
            r = self.http.post(self._url("/v1/validations"), json=body,
                               headers=self._h({"Idempotency-Key": f"web-{doc_id}-{run}-{uuid.uuid4().hex[:8]}",
                                                "X-Correlation-Id": f"web-{doc_id}-{run}"}))
            if r.status_code >= 400:
                raise EngineError(f"System A rejected the request: HTTP {r.status_code} {r.text[:300]}")
            vid = r.json()["validation_id"]
            t0 = time.monotonic()
            while True:
                s = self.http.get(self._url(f"/v1/validations/{vid}"), headers=self._h())
                if s.status_code >= 400:
                    raise EngineError(f"status check failed: HTTP {s.status_code}")
                st = s.json()
                if st["status"] == "completed":
                    break
                if st["status"] == "failed":
                    raise EngineError(f"System A job failed: {st.get('error')}")
                if time.monotonic() - t0 > self.timeout:
                    raise EngineError(f"System A did not finish within {self.timeout:.0f}s")
                time.sleep(self.poll)
            res = self.http.get(self._url(f"/v1/validations/{vid}/result"), headers=self._h())
            if res.status_code >= 400:
                raise EngineError(f"result fetch failed: HTTP {res.status_code}")
            return res.json()
        except httpx.HTTPError as e:
            raise EngineError(f"System A (http) unreachable: {type(e).__name__}: {e}") from e

    def health(self) -> dict:
        try:
            r = self.http.get(self._url("/health/ready"), headers=self._h())
            r.raise_for_status()
            return {"engine": self.name, "ok": True, "url": self.base, **r.json()}
        except Exception as e:
            return {"engine": self.name, "ok": False, "url": self.base, "error": f"{type(e).__name__}: {e}"}


def load_oracle_dataset(path: Optional[Path], home: Optional[Path]) -> dict:
    """Sandbox Oracle data: ``WEBAPP_ORACLE_DATASET`` or ``<System A>/sandbox_data/oracle_dataset.json``."""
    import json
    for p in filter(None, (path, (Path(home) / "sandbox_data" / "oracle_dataset.json") if home else None)):
        if Path(p).is_file():
            return json.loads(Path(p).read_text(encoding="utf-8"))
    return {}


def build_engine(settings, sa_home: Optional[Path]) -> Engine:
    if settings.engine == "http":
        return HttpEngine(settings.system_a_url, settings.system_a_key, settings.http_timeout_s)
    return InProcessEngine(load_oracle_dataset(settings.oracle_dataset, sa_home))
