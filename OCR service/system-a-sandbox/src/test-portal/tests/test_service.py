"""The per-document state machine: one run at a time, and a System A failure is shown as a failure."""
import time

import pytest

from doubles import FakeRunner
from webapp.catalog import Catalog
from webapp.service import Busy, DocumentService, NotReady
from webapp.store import ResultStore
from webapp.sysa import SystemAError


def svc_for(catalog, runner, settings, **kw):
    return DocumentService(catalog, runner, ResultStore(settings.data_dir), workers=kw.pop("workers", 2),
                           mode="sandbox", **kw)


def test_a_successful_run_leaves_a_view_and_a_payload_on_disk(catalog, sa, payload, settings):
    svc = svc_for(catalog, FakeRunner(payload=payload), settings)
    svc.start(101)
    st = svc.wait(101)
    assert st["state"] == "done" and st["run"] == 1 and st["cls"] == "ok" and st["recommendation"] == "AUTO_PASS"
    assert st["boxes"] == len(payload["ocr"]["elements"])            # every element of the payload is a box
    assert st["types"] == svc.view(101)["types"] and "field" in st["types"]   # the element types it produced
    assert st["seconds"] is not None and st["step"] is None and st["error"] is None
    v = svc.view(101)
    assert v["recommendation"]["value"] == "AUTO_PASS" and v["pages"][0]["elements"]
    assert v["counts"]["elements"] == len(payload["ocr"]["elements"])
    assert svc.part(101, "payload")["contract"] == "aiva.system_a.result/3.0"
    assert (settings.data_dir / "results" / "doc_101" / "payload.json").is_file()
    assert (settings.data_dir / "results" / "doc_101" / "view.json").is_file()
    svc.shutdown()


def test_the_payload_the_service_stored_is_the_payload_system_a_returned(catalog, settings, payload):
    svc = svc_for(catalog, FakeRunner(payload=payload), settings)
    svc.start(102)
    svc.wait(102)
    import json
    on_disk = json.loads((settings.data_dir / "results" / "doc_102" / "payload.json").read_text(encoding="utf-8"))
    assert on_disk == payload                                    # not a copy with the portal's ideas added
    assert on_disk["integrity"]["payload_sha256"] == payload["integrity"]["payload_sha256"]
    svc.shutdown()


def test_a_second_run_replaces_the_previous_result(catalog, settings, payload, hold_payload):
    first = FakeRunner(payload=payload)
    svc = svc_for(catalog, first, settings)
    svc.start(101)
    assert svc.wait(101)["recommendation"] == "AUTO_PASS"
    svc.runner = FakeRunner(payload=hold_payload)               # the same document, a different answer
    svc.start(101)
    st = svc.wait(101)
    assert st["run"] == 2 and st["cls"] == "error" and st["recommendation"] == "HOLD"
    assert svc.view(101)["recommendation"]["value"] == "HOLD"
    svc.shutdown()


def test_a_system_a_failure_is_reported_as_it_is_and_leaves_no_partial_result(catalog, settings):
    tb = "Traceback (most recent call last)\n  File \"process_pdf.py\", line 200, in process_pdf\n" \
         "RuntimeError: VLM returned no page items"
    boom = SystemAError("System A failed on #101: RuntimeError: VLM returned no page items",
                        traceback=tb, exc_type="RuntimeError")
    svc = svc_for(catalog, FakeRunner(fail_with=boom), settings)
    svc.start(101)
    st = svc.wait(101)
    assert st["state"] == "error"
    assert st["error"] == "SystemAError: System A failed on #101: RuntimeError: VLM returned no page items"
    assert "process_pdf.py" in st["traceback"]                  # the traceback System A raised, shown as it is
    with pytest.raises(NotReady):
        svc.view(101)
    with pytest.raises(NotReady):
        svc.part(101, "payload")
    assert not (settings.data_dir / "results" / "doc_101" / "view.json").exists()
    assert svc.status(101)["recommendation"] is None
    svc.shutdown()


def test_one_failing_document_does_not_touch_the_others(catalog, settings, payload):
    class Half:                                                  # #101 works, #102 is where System A fails
        name = "inprocess"

        def __init__(self):
            self.ok = FakeRunner(payload=payload)

        def run(self, doc_id, *, run):
            if doc_id == 102:
                raise RuntimeError("oracle timeout")
            return self.ok.run(doc_id, run=run)

        def health(self):
            return {"engine": "inprocess", "ok": True}

    svc = svc_for(catalog, Half(), settings)
    svc.start(101)
    svc.start(102)
    assert svc.wait(101)["state"] == "done"
    st = svc.wait(102)
    assert st["state"] == "error" and "oracle timeout" in st["error"]
    assert svc.status(101)["boxes"] > 0
    with pytest.raises(NotReady):
        svc.view(102)
    svc.shutdown()


def test_a_document_is_processed_by_one_job_at_a_time(catalog, settings, payload):
    class Slow(FakeRunner):
        def run(self, doc_id, *, run):
            time.sleep(0.4)
            return self.payload

    slow = Slow(payload=payload)
    svc = svc_for(catalog, slow, settings)
    svc.start(101)
    with pytest.raises(Busy):
        svc.start(101)
    assert svc.status(101)["state"] == "processing"
    assert svc.status(101)["elapsed"] is not None
    assert svc.wait(101)["state"] == "done"
    svc.shutdown()


def test_a_run_cannot_write_over_a_newer_run(catalog, settings, payload, hold_payload):
    """Rounds are numbered, and a job only ever writes while its round is still the current one.

    The public API refuses to overlap two rounds of one document, so the seam is driven directly here: a round
    that comes back after another round has taken the document must throw its result away.
    """
    svc = svc_for(catalog, FakeRunner(payload=payload), settings)
    svc.start(101)
    assert svc.wait(101)["run"] == 1
    st = svc._state(101)
    st["run"] = 7                                             # a newer round owns the document now
    svc.store.save(101, "state", st)
    svc.runner = FakeRunner(payload=hold_payload)
    svc._job(101, 1)                                              # round 1 comes back late
    assert svc.view(101)["recommendation"]["value"] == "AUTO_PASS"   # its result was thrown away, not written
    assert svc.status(101)["run"] == 7
    svc._job(101, 7)                                              # the round that owns it still writes
    assert svc.view(101)["recommendation"]["value"] == "HOLD"
    svc.shutdown()


def test_a_run_interrupted_by_a_restart_is_an_error_not_a_result(harness, sa, settings):
    store = ResultStore(settings.data_dir)
    store.save(101, "state", {"id": 101, "state": "processing", "run": 3, "step": "process", "started_at": 1.0,
                              "finished_at": None, "seconds": None, "error": None, "traceback": None})
    cat = Catalog(sa, tag="invoice")
    cat.refresh()
    svc = DocumentService(cat, FakeRunner(payload=sa.payload), store, workers=1, mode="sandbox")
    st = svc.status(101)
    assert st["state"] == "error" and "restart" in st["error"] and st["run"] == 3
    with pytest.raises(NotReady):
        svc.view(101)
    svc.shutdown()


def test_delete_forgets_the_result_of_that_document_only(catalog, settings, payload):
    svc = svc_for(catalog, FakeRunner(payload=payload), settings)
    svc.start(101)
    svc.wait(101)
    svc.start(102)
    svc.wait(102)
    st = svc.delete(101)
    assert st["state"] == "idle" and st["run"] == 1
    with pytest.raises(NotReady):
        svc.view(101)
    assert svc.status(102)["id"] == 102                          # the other document still has its result
    svc.shutdown()


def test_search_looks_at_processed_documents_only(catalog, settings, payload):
    svc = svc_for(catalog, FakeRunner(payload=payload), settings)
    svc.start(101)
    svc.wait(101)
    assert svc.search("101") == [101]
    assert svc.search("synthetic invoice 101") == [101]          # the title
    assert svc.search("bracket assy") == [101]                   # text inside the payload
    assert svc.search("bracket") == [101]                        # #102 is not processed, so it cannot be a hit
    assert svc.search("") == [] and svc.search("zzz-nothing") == []
    svc.shutdown()


def test_status_reports_the_document_and_its_source(catalog, settings, payload):
    svc = svc_for(catalog, FakeRunner(payload=payload), settings)
    st = svc.status(103)
    assert st["id"] == 103 and st["state"] == "idle" and st["run"] == 0
    assert st["title"] == "SYNTHETIC INVOICE 103" and st["pages_total"] == 1
    assert st["viewer_url"].endswith("/documents/103/")
    assert st["correspondent"] == "SYNTHETIC SUPPLIER" and st["file_class"]
    assert st["traceback"] is None and st["boxes"] == 0
    assert {d["id"] for d in svc.list_documents()} == {101, 102, 103}
    with pytest.raises(KeyError):
        svc.status(999)
    with pytest.raises(KeyError):
        svc.start(999)
    svc.shutdown()


def test_the_real_sya_module_is_what_production_uses(harness, settings):
    """``webapp.sysa`` really imports System A (the harness root) and reports the Standard it loaded."""
    from webapp import sysa
    sa = sysa.init(settings)                                     # settings.system_a_home -> the harness root
    assert sa.process_pdf is not None and callable(sa.process_pdf)
    h = sa.health()
    assert h["ok"] and h["standard"] and h["ruleset"] and h["mode"] == "sandbox"
    assert h["home"] == str(harness)                             # the System A this run is wired to
    assert sa.a_settings().mode == "sandbox"                     # settings.mode -> System A's mode + ai_mode
    assert "process_pdf" in repr(sa.process_pdf)
