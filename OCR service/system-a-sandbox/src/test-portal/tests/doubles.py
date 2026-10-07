"""Stand-ins for the two things the portal talks to: System A itself, and the DMS.

The doubles implement the same interfaces the real objects expose (``webapp.sysa.SystemA``,
``system_a.adapters.paperless.reader.PaperlessReader``), so a test can drive the whole portal - catalog, service,
HTTP API - without a network, a GPU or the Oracle.  The ``payload`` a double returns is a genuine
``aiva.system_a.result/3.0`` produced by System A's own code (see :mod:`tests.synth`).
"""
from __future__ import annotations

import io
from types import SimpleNamespace

def png(w: int = 8, h: int = 8) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, "PNG")
    return buf.getvalue()


class FakeReader:
    """``PaperlessReader`` as far as :class:`webapp.catalog.Catalog` is concerned."""

    def __init__(self, docs=None, *, tags=(("invoice", 7),), base_url="http://dms.test", count=None,
                 list_raises=None):
        self._docs = docs                                  # None -> a synthetic set of three invoices
        self._tags, self.base_url, self.fail_list = list(tags), base_url, list_raises
        self.last_count = count if count is not None else (len(docs) if docs is not None else 3)
        self.calls: list = []

    @property
    def docs(self):
        if self._docs is None:
            self._docs = [_paperless_doc(i, f"SYNTHETIC INVOICE {i}") for i in (101, 102, 103)]
        return self._docs

    def tag_ids_for(self, names, *, mode="contains"):
        self.calls.append(("tags", tuple(names)))
        want = {str(n).lower() for n in names}
        return [(tid, name) for name, tid in self._tags if name.lower() in want]

    def list_documents(self, *, tag_ids=None, limit=200, **kw):
        self.calls.append(("list", tuple(tag_ids or ()), limit))
        if self.fail_list:
            raise self.fail_list
        return list(self.docs)[:limit]

    def download(self, doc_id, original=True):
        self.calls.append(("download", doc_id))
        return b"%PDF-1.4 fake document " + str(doc_id).encode()

    def health(self):
        return {"ok": True, "count": self.last_count, "base_url": self.base_url}


def _paperless_doc(doc_id: int, title: str, *, page_count=1, mime="application/pdf",
                   correspondent="SYNTHETIC SUPPLIER"):
    """Built with System A's own parser, so the catalog is tested against the real document shape."""
    from system_a.adapters.paperless.reader import _doc
    return _doc({"id": doc_id, "title": title, "created": "2026-10-01T00:00:00Z", "owner": 1,
                 "correspondent_display_name": correspondent, "tags": [{"id": 7, "name": "invoice"}],
                 "original_file_name": f"DMS-{doc_id}.pdf", "mime_type": mime, "page_count": page_count})


class FakeSystemA:
    """The part of :class:`webapp.sysa.SystemA` the portal actually calls."""

    def __init__(self, payload=None, *, pages=1, root=None, fail_with=None, slow=0.0, extraction=None):
        self.payload, self.pages, self.slow = payload, pages, slow
        self.extraction = extraction or {"contract": "aiva.extraction/2.0", "dms_doc_id": "DMS-0", "extra": {}}
        self.root = root or "."
        self.fail_with = fail_with                       # exception raised by process()
        self.calls: list = []
        self.reader = FakeReader()
        self.container = SimpleNamespace(build_paperless=lambda s: self.reader)

    # -- the pipeline ---------------------------------------------------------------
    def process(self, doc_id):
        self.calls.append(("process", doc_id))
        if self.slow:
            import time
            time.sleep(self.slow)
        if self.fail_with is not None:
            raise self.fail_with
        return self.payload

    def perceive(self, doc_id):
        """The reading half (only ``SYSTEM_A_ENGINE=http`` uses it) - what System A's VisionPipeline produced."""
        self.calls.append(("perceive", doc_id))
        return self.extraction or {"contract": "aiva.extraction/2.0", "dms_doc_id": f"DMS-{doc_id}", "extra": {}}

    # -- the file -------------------------------------------------------------------
    def pdf_bytes(self, doc_id):
        self.calls.append(("pdf", doc_id))
        return self.reader.download(doc_id)

    def page_image(self, doc_id, page, dpi):
        self.calls.append(("image", doc_id, page, dpi))
        return png(), (8, 8)

    def page_count(self, doc_id):
        return self.pages

    def a_settings(self):
        return SimpleNamespace(mode="sandbox", ai_mode="sim")

    def health(self):
        return {"engine": "inprocess", "ok": True, "mode": "sandbox", "ai_mode": "sim", "standard": "6.6",
                "ruleset": "v6.6-r4", "vision_model": "fake-vlm", "oracle_backend": "memory", "home": str(self.root)}


class FakeRunner:
    """A ``Runner`` that answers immediately (or fails) without touching System A."""

    name = "inprocess"

    def __init__(self, payload=None, *, fail_with=None, sa=None):
        self.payload, self.fail_with, self.sa = payload, fail_with, sa or FakeSystemA(payload)
        self.calls: list = []

    def run(self, doc_id, *, run):
        self.calls.append((doc_id, run))
        if self.fail_with is not None:
            raise self.fail_with
        return self.payload

    def health(self):
        return self.sa.health()                                  # what LocalRunner does: System A answers for itself
