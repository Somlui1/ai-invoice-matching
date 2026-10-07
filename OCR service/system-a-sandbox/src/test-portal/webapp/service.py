"""One small state machine per document.

    idle --start--> processing --ok--> done
                        |
                        +--failure--> error          (start again from any state except processing)

* a document is processed by one job at a time (``Busy`` -> HTTP 409); different documents run side by side;
* each ``start`` increases ``run`` and clears the document's previous result first, and a job may only write its
  outcome if its ``run`` is still the current one - so a result can never be mixed with another run's or document's;
* the outcome is persisted per document and restored after a restart (a job interrupted by the restart is
  reported as an error, never as a result);
* when System A raises, the document goes to ``error`` with the exception's own type, message and traceback.  A
  failed run keeps no partial result: the portal would otherwise be showing something System A never produced.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from .store import ResultStore
from .view import build_view

log = logging.getLogger("webapp.service")


class Busy(RuntimeError):
    """The document is being processed right now."""


class NotReady(RuntimeError):
    """The document has no result (not processed yet, still processing, or the last run failed)."""


class DocumentService:
    def __init__(self, catalog, runner, store: ResultStore, *, workers: int = 4, mode: str = "production"):
        self.catalog, self.runner, self.store = catalog, runner, store
        self.mode = mode
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="doc")
        self._lock = threading.RLock()
        self._st: dict = {}
        self._futures: dict = {}
        self._search_cache: dict = {}
        for d in catalog.docs:
            saved = store.load(d.id, "state")
            if saved:
                if saved.get("state") == "processing":
                    saved.update(state="error", step=None, error="interrupted by a restart - process it again")
                    store.save(d.id, "state", saved)
                self._st[d.id] = saved

    # ------------------------------------------------------------------ state helpers
    def _state(self, doc_id: int) -> dict:
        self.catalog.get(doc_id)                                       # KeyError for an unknown id
        return self._st.setdefault(int(doc_id), {"id": int(doc_id), "state": "idle", "run": 0, "step": None,
                                                 "started_at": None, "finished_at": None, "seconds": None,
                                                 "error": None, "traceback": None})

    def _public(self, d) -> dict:
        s = self._state(d.id)
        return {"id": d.id, "title": d.title, "file_name": d.file_name, "mime": d.mime,
                "file_class": d.file_class, "tagged": d.tagged, "pages_total": d.pages_total,
                "pages": d.page_numbers, "created": d.created, "correspondent": d.correspondent,
                "dms_url": d.dms_url, "viewer_url": self.catalog.viewer_url(d.id),
                "state": s["state"], "run": s["run"], "step": s.get("step"), "seconds": s.get("seconds"),
                "error": s.get("error"), "traceback": s.get("traceback"),
                "recommendation": s.get("recommendation"), "cls": s.get("cls"),
                "types": s.get("types") or [], "boxes": s.get("boxes") or 0,
                "started_at": s.get("started_at"),
                "elapsed": (round(time.time() - s["started_at"], 1)
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
            return [self._public(d) for d in self.catalog.docs]

    def status(self, doc_id: int) -> dict:
        with self._lock:
            return self._public(self.catalog.get(doc_id))

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
        """Ids of processed documents whose id / title / payload text contains ``q`` (case-insensitive)."""
        q = (q or "").strip().lower()
        if not q:
            return []
        hits = []
        for d in self.catalog.docs:
            with self._lock:
                s = self._state(d.id)
                if s["state"] != "done":
                    continue
                key = (d.id, s["run"])
                text = self._search_cache.get(key)
                if text is None:
                    v = self.store.load(d.id, "view") or {}
                    s = v.get("search") or {}                   # the words of the payload itself, nothing invented
                    text = self._search_cache[key] = "\n".join(
                        str(x) for x in (s.get("elements_text"), s.get("fields_text"), s.get("lines_text"),
                                         s.get("rules_text"), s.get("exceptions_text")) if x).lower()
            if q == str(d.id) or q in d.title.lower() or q in text:
                hits.append(d.id)
        return hits

    # ------------------------------------------------------------------ commands
    def start(self, doc_id: int) -> dict:
        with self._lock:
            d = self.catalog.get(doc_id)
            s = self._state(doc_id)
            if s["state"] == "processing":
                raise Busy(f"#{doc_id} is already being processed")
            s["run"] += 1
            run = s["run"]
            s.update(state="processing", step="process", started_at=time.time(), finished_at=None, seconds=None,
                     error=None, traceback=None, recommendation=None, cls=None, types=[], boxes=0)
            self.store.clear(doc_id)                                   # the previous result is gone before the new run
            self.store.save(doc_id, "state", s)
            self._futures[doc_id] = self.pool.submit(self._job, d.id, run)
            return self._public(d)

    def delete(self, doc_id: int) -> dict:
        with self._lock:
            d = self.catalog.get(doc_id)
            s = self._state(doc_id)
            if s["state"] == "processing":
                raise Busy(f"#{doc_id} is being processed")
            s.update(state="idle", step=None, error=None, traceback=None, seconds=None, recommendation=None,
                     cls=None, types=[], boxes=0, started_at=None, finished_at=None)
            self.store.clear(doc_id)
            self.store.save(doc_id, "state", s)
            return self._public(d)

    # ------------------------------------------------------------------ the job
    def _job(self, doc_id: int, run: int) -> None:
        """One document, start to finish, in a worker thread.  Never raises to the caller.

        System A is called once and what it hands back is stored as-is; the browser view is derived from that
        payload alone.  A failure leaves the document in ``error`` with the traceback System A produced - the
        portal invents no partial result.
        """
        t0 = time.perf_counter()
        try:
            payload = self.runner.run(doc_id, run=run)                 # System A, all of it
            secs = time.perf_counter() - t0
            view = build_view(payload)                                 # the view is only ever the payload, reshaped
            view["seconds"] = round(secs, 1)
            view["engine"] = self.runner.name
            view["mode"] = self.mode
            self._update(doc_id, run, step="view")
            with self._lock:
                if self._state(doc_id)["run"] != run:
                    return                                             # a newer run owns the document now
                self.store.save(doc_id, "payload", payload)
                self.store.save(doc_id, "view", view)
            self._update(doc_id, run, state="done", step=None, seconds=view["seconds"], finished_at=time.time(),
                         error=None, traceback=None, recommendation=view["recommendation"]["value"],
                         cls=view["cls"], types=view["types"], boxes=view["counts"]["boxes"])
        except Exception as e:                       # the document shows exactly what System A raised
            tb = getattr(e, "traceback", None) or ""
            log.exception("processing #%s (run %s) failed", doc_id, run)
            self._update(doc_id, run, state="error", step=None, seconds=round(time.perf_counter() - t0, 1),
                         finished_at=time.time(), error=f"{type(e).__name__}: {e}"[:900],
                         traceback=(tb or _tb_tail())[-6000:])

    # ------------------------------------------------------------------ test / shutdown helpers
    def wait(self, doc_id: int, timeout: float = 30.0) -> dict:
        f = self._futures.get(doc_id)
        if f is not None:
            f.result(timeout=timeout)
        return self.status(doc_id)

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=False)


def _tb_tail() -> str:
    import traceback
    return traceback.format_exc()
