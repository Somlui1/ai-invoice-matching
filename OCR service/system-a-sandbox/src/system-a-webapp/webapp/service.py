"""Document processing service: one small state machine per document.

    idle --start--> processing --ok--> done
                        |
                        +--failure--> error          (start again from any state except processing)

* a document is processed by one job at a time (``Busy`` -> HTTP 409); different documents run side by side;
* each ``start`` increases ``run`` and clears the document's previous result first, and a job may only write its
  outcome if its ``run`` is still the current one - so a result can never be mixed with another run's or document's;
* the outcome is persisted per document and restored after a restart (a job interrupted by the restart is
  reported as an error, never as a result).
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from .batch import BatchSource
from .engine import Engine
from .perception import Perception
from .store import ResultStore
from .view import build_view

log = logging.getLogger("webapp.service")


class Busy(RuntimeError):
    """The document is being processed right now."""


class NotReady(RuntimeError):
    """The document has no result (not processed yet, still processing, or the last run failed)."""


class DocumentService:
    def __init__(self, batch: BatchSource, perception: Perception, engine: Engine, store: ResultStore, workers: int = 4):
        self.batch, self.perception, self.engine, self.store = batch, perception, engine, store
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="doc")
        self._lock = threading.RLock()
        self._st: dict = {}
        self._futures: dict = {}
        self._search_cache: dict = {}
        for d in batch.docs:
            saved = store.load(d.id, "state")
            if saved:
                if saved.get("state") == "processing":
                    saved.update(state="error", step=None, error="interrupted by a restart - process it again")
                    store.save(d.id, "state", saved)
                self._st[d.id] = saved

    # ------------------------------------------------------------------ state helpers
    def _state(self, doc_id: int) -> dict:
        self.batch.get(doc_id)                                         # KeyError for an unknown id
        return self._st.setdefault(int(doc_id), {"id": int(doc_id), "state": "idle", "run": 0, "step": None,
                                                 "started_at": None, "finished_at": None, "seconds": None,
                                                 "error": None})

    def _public(self, d) -> dict:
        s = self._state(d.id)
        return {"id": d.id, "title": d.title, "ptype": d.ptype, "pages_total": d.pages_total,
                "pages": d.page_numbers, "viewer_url": self.batch.viewer_url(d.id), "state": s["state"], "run": s["run"],
                "created": getattr(d, "created", ""), "correspondent": getattr(d, "correspondent", ""),
                "mime": getattr(d, "mime", ""), "file_class": getattr(d, "file_class", ""),
                "dms_url": getattr(d, "dms_url", ""),
                "step": s.get("step"), "seconds": s.get("seconds"), "error": s.get("error"),
                "recommendation": s.get("recommendation"), "cls": s.get("cls"), "types": s.get("types") or [],
                "kept": s.get("kept") or 0, "dropped": s.get("dropped") or 0,
                "started_at": s.get("started_at"), "elapsed": (round(time.time() - s["started_at"], 1)
                                                               if s["state"] == "processing" and s.get("started_at") else None)}

    def _update(self, doc_id: int, run: int, **kw) -> bool:
        with self._lock:
            s = self._state(doc_id)
            if s["run"] != run:
                return False                                           # a newer run owns the document now
            s.update(kw)
            self.store.save(doc_id, "state", s)
            return True

    # ------------------------------------------------------------------ queries
    def list_documents(self) -> list:
        with self._lock:
            return [self._public(d) for d in self.batch.docs]

    def status(self, doc_id: int) -> dict:
        with self._lock:
            return self._public(self.batch.get(doc_id))

    def view(self, doc_id: int) -> dict:
        with self._lock:
            s = self._state(doc_id)
            if s["state"] != "done":
                raise NotReady(f"#{doc_id} is {s['state']}")
        v = self.store.load(doc_id, "view")
        if v is None:
            raise NotReady(f"#{doc_id} has no stored result")
        return v

    def part(self, doc_id: int, part: str) -> dict:
        self.view(doc_id)                                              # same readiness rule
        data = self.store.load(doc_id, part)
        if data is None:
            raise NotReady(f"#{doc_id} has no stored {part}")
        return data

    def search(self, q: str) -> list:
        """Ids of processed documents whose id / title / OCR text contains ``q`` (case-insensitive)."""
        q = (q or "").strip().lower()
        if not q:
            return []
        hits = []
        for d in self.batch.docs:
            with self._lock:
                s = self._state(d.id)
                if s["state"] != "done":
                    continue
                key = (d.id, s["run"])
                text = self._search_cache.get(key)
                if text is None:
                    v = self.store.load(d.id, "view") or {}
                    text = self._search_cache[key] = v.get("search", "")
            if q == str(d.id) or q in d.title.lower() or q in text:
                hits.append(d.id)
        return hits

    # ------------------------------------------------------------------ commands
    def start(self, doc_id: int) -> dict:
        with self._lock:
            d = self.batch.get(doc_id)
            s = self._state(doc_id)
            if s["state"] == "processing":
                raise Busy(f"#{doc_id} is already being processed")
            s["run"] += 1
            run = s["run"]
            s.update(state="processing", step="perception", started_at=time.time(), finished_at=None, seconds=None,
                     error=None, recommendation=None, cls=None, types=[], kept=0, dropped=0)
            self.store.clear(doc_id)                                   # the previous result is gone before the new run starts
            self.store.save(doc_id, "state", s)
            self._futures[doc_id] = self.pool.submit(self._job, d.id, d.title, run)
            return self._public(d)

    def delete(self, doc_id: int) -> dict:
        with self._lock:
            d = self.batch.get(doc_id)
            s = self._state(doc_id)
            if s["state"] == "processing":
                raise Busy(f"#{doc_id} is being processed")
            s.update(state="idle", step=None, error=None, seconds=None, recommendation=None, cls=None, types=[],
                     kept=0, dropped=0, started_at=None, finished_at=None)
            self.store.clear(doc_id)
            self.store.save(doc_id, "state", s)
            return self._public(d)

    def _job(self, doc_id: int, title: str, run: int) -> None:
        t0 = time.perf_counter()
        try:
            extraction = self.perception.extract(doc_id)
            if not self._update(doc_id, run, step="validate"):
                return
            result = self.engine.validate(extraction, doc_id=doc_id, run=run)
            if not self._update(doc_id, run, step="view"):
                return
            secs = time.perf_counter() - t0
            view = build_view(doc_id=doc_id, title=title, run=run, extraction=extraction, result=result, seconds=secs,
                              perception=self.perception.name, engine=self.engine.name)
            with self._lock:
                if self._state(doc_id)["run"] != run:
                    return
                self.store.save(doc_id, "extraction", extraction)
                self.store.save(doc_id, "payload", result)
                self.store.save(doc_id, "view", view)
            self._update(doc_id, run, state="done", step=None, seconds=round(secs, 1), finished_at=time.time(), error=None,
                         recommendation=view["recommendation"], cls=view["cls"], types=view["types"],
                         kept=view["kept"], dropped=view["dropped"])
        except Exception as e:                                         # reported on the document; never raised to the pool
            log.exception("processing #%s (run %s) failed", doc_id, run)
            self._update(doc_id, run, state="error", step=None, seconds=round(time.perf_counter() - t0, 1),
                         finished_at=time.time(), error=f"{type(e).__name__}: {e}"[:600])

    # ------------------------------------------------------------------ test / shutdown helpers
    def wait(self, doc_id: int, timeout: float = 30.0) -> dict:
        f = self._futures.get(doc_id)
        if f is not None:
            f.result(timeout=timeout)
        return self.status(doc_id)

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=False)
