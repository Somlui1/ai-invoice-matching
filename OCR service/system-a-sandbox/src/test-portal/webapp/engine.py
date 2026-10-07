"""The one seam between the portal and System A's validation: ``Runner.run(doc_id) -> aiva.system_a.result/3.0``.

``SYSTEM_A_ENGINE`` chooses which of the two runs:

* ``inprocess`` (default) - :class:`LocalRunner` calls System A's own entrypoint ``process_pdf.process_pdf()``
  in this process.  Paperless download, VisionPipeline, Oracle and rules V-01..V-09 all happen here, exactly as
  ``scripts/test_paperless_invoices.py`` does it.
* ``http`` - :class:`RemoteRunner` lets System A read the document here (``container.build_perception``, the same
  call ``process_pdf`` makes) and sends the resulting ``aiva.extraction/2.0`` to a running System A server:
  ``POST /v1/validations`` → poll ``GET /v1/validations/{id}`` → ``GET .../result``.
  Its API does not ingest a package by itself (``POST`` with only ``package`` answers 501), so the reading stays
  on this side and the validation - Oracle, AI judges, the rules, the payload assembly - runs over there.

Both engines return the same payload; ``tests/test_engine.py`` proves it by comparing ``integrity.payload_sha256``.
"""
from __future__ import annotations

import time
import uuid
from typing import Optional, Protocol

import httpx


class EngineError(RuntimeError):
    """System A could not produce a result (transport, HTTP error, failed job, timeout)."""


class Runner(Protocol):
    name: str

    def run(self, doc_id: int, *, run: int) -> dict: ...

    def health(self) -> dict: ...


class LocalRunner:
    """Runs System A's single-document entrypoint inside this process."""

    name = "inprocess"

    def __init__(self, sa):
        self.sa = sa

    def run(self, doc_id: int, *, run: int) -> dict:
        return self.sa.process(doc_id)                          # raises SystemAError with the traceback

    def health(self) -> dict:
        return self.sa.health()


class HttpValidator:
    """The REST client for a System A server (async job: create, poll, fetch the result)."""

    name = "http"

    def __init__(self, base_url: str, api_key: str = "", timeout_s: float = 300.0, poll_s: float = 0.4,
                 client: Optional[httpx.Client] = None):
        self.base, self.key, self.timeout, self.poll = base_url.rstrip("/"), api_key, timeout_s, poll_s
        self.http = client or httpx.Client(timeout=30.0)

    def _h(self, extra: Optional[dict] = None) -> dict:
        return {**({"X-API-Key": self.key} if self.key else {}), **(extra or {})}

    def validate(self, extraction: dict, *, doc_id: int, run: int) -> dict:
        body = {"extraction": extraction, "portal_refs": {"document_revision": 1, "validation_round": run}}
        try:
            r = self.http.post(self.base + "/v1/validations", json=body,
                               headers=self._h({"Idempotency-Key": f"web-{doc_id}-{run}-{uuid.uuid4().hex[:8]}",
                                                "X-Correlation-Id": f"web-{doc_id}-{run}"}))
            if r.status_code >= 400:
                raise EngineError(f"System A rejected the request: HTTP {r.status_code} {r.text[:300]}")
            vid = r.json()["validation_id"]
            t0 = time.monotonic()
            while True:
                s = self.http.get(self.base + f"/v1/validations/{vid}", headers=self._h())
                if s.status_code >= 400:
                    raise EngineError(f"status check failed: HTTP {s.status_code} {s.text[:200]}")
                st = s.json()
                if st["status"] == "completed":
                    break
                if st["status"] == "failed":
                    raise EngineError(f"System A job failed: {st.get('error')}")
                if time.monotonic() - t0 > self.timeout:
                    raise EngineError(f"System A did not finish within {self.timeout:.0f}s (job {vid})")
                time.sleep(self.poll)
            res = self.http.get(self.base + f"/v1/validations/{vid}/result", headers=self._h())
            if res.status_code >= 400:
                raise EngineError(f"result fetch failed: HTTP {res.status_code}")
            return res.json()
        except httpx.HTTPError as e:
            raise EngineError(f"System A at {self.base} unreachable: {type(e).__name__}: {e}") from e

    def health(self) -> dict:
        try:
            r = self.http.get(self.base + "/health/ready", headers=self._h())
            r.raise_for_status()
            return {"engine": self.name, "ok": True, "url": self.base, **r.json()}
        except Exception as e:
            return {"engine": self.name, "ok": False, "url": self.base, "error": f"{type(e).__name__}: {e}"}


class RemoteRunner:
    """System A reads the document here; the validation happens on a System A server."""

    name = "http"

    def __init__(self, sa, validator: HttpValidator):
        self.sa, self.v = sa, validator

    def run(self, doc_id: int, *, run: int) -> dict:
        return self.v.validate(self.sa.perceive(doc_id), doc_id=doc_id, run=run)

    def health(self) -> dict:
        return self.v.health()


def build_runner(settings, sa) -> Runner:
    if settings.engine == "http":
        return RemoteRunner(sa, HttpValidator(settings.system_a_url, settings.system_a_key, settings.http_timeout_s))
    return LocalRunner(sa)
