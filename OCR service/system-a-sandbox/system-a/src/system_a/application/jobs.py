"""Async job store + idempotency.  In-memory TTL store (sandbox); swap for Redis in production
(same interface).  This is a cache, NOT a system of record.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from typing import Optional


def idempotency_fingerprint(extraction: dict, ruleset: str, models: dict, round_: int, key: Optional[str]) -> str:
    body = json.dumps({"x": extraction, "r": ruleset, "m": models, "n": round_, "k": key}, sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()


class JobStore:
    def __init__(self, ttl_s: int = 86400):
        self.ttl, self._jobs, self._idem, self._lock = ttl_s, {}, {}, threading.Lock()

    def _gc(self):
        now = time.time()
        for k in [k for k, j in self._jobs.items() if now - j["created"] > self.ttl]:
            self._jobs.pop(k, None)
        for k in [k for k, v in self._idem.items() if v not in self._jobs]:
            self._idem.pop(k, None)

    def create_or_get(self, fingerprint: str) -> tuple[str, bool]:
        with self._lock:
            self._gc()
            if fingerprint in self._idem:
                return self._idem[fingerprint], False
            vid = "VAL-" + uuid.uuid4().hex[:12].upper()
            self._jobs[vid] = {"status": "queued", "created": time.time(), "result": None, "error": None, "input": None}
            self._idem[fingerprint] = vid
            return vid, True

    def put_input(self, vid, data):
        self._jobs[vid]["input"] = data

    def set(self, vid: str, **kw):
        with self._lock:
            if vid in self._jobs:
                self._jobs[vid].update(kw)

    def get(self, vid: str) -> Optional[dict]:
        return self._jobs.get(vid)
