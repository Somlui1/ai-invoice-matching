import threading
import time

import pytest

from webapp.build import build_all
from webapp.engine import EngineError, InProcessEngine
from webapp.service import Busy, DocumentService, NotReady
from webapp.store import ResultStore


class GatedEngine:
    """Wraps a real engine; validate() waits for ``release`` so a test can look at a document mid-run."""
    name = "gated"

    def __init__(self, inner):
        self.inner, self.release, self.entered = inner, threading.Event(), threading.Event()

    def validate(self, extraction, *, doc_id, run):
        self.entered.set()
        assert self.release.wait(10), "test forgot to release the engine"
        return self.inner.validate(extraction, doc_id=doc_id, run=run)

    def health(self):
        return {"ok": True}


class BrokenEngine:
    name = "broken"

    def validate(self, extraction, *, doc_id, run):
        raise EngineError("System A is down (test)")

    def health(self):
        return {"ok": False}


def make(settings, engine):
    _, svc, batch = build_all(settings, engine=engine)
    return svc


def test_everything_starts_idle(parts):
    _, svc, _ = parts
    rows = svc.list_documents()
    assert [r["id"] for r in rows] == [101, 102, 103, 104, 105, 106, 107]
    assert {r["state"] for r in rows} == {"idle"} and {r["run"] for r in rows} == {0}


def test_process_one_document(parts):
    _, svc, _ = parts
    assert svc.start(101)["state"] == "processing"
    st = svc.wait(101)
    assert st["state"] == "done" and st["recommendation"] == "AUTO_PASS" and st["run"] == 1 and st["seconds"] is not None
    v = svc.view(101)
    assert v["id"] == 101 and v["recommendation"] == "AUTO_PASS" and v["kept"] > 15
    assert [r["rule_id"] for r in v["verify"]] == [f"V-0{i}" for i in range(1, 10)]
    assert svc.part(101, "payload")["contract"] == "aiva.system_a.result/3.0"
    assert svc.part(101, "extraction")["contract"] == "aiva.extraction/2.0"


def test_documents_never_mix(parts):
    """Run six documents at the same time: each result belongs to its own document and says so everywhere."""
    _, svc, _ = parts
    ids = [101, 102, 103, 104, 105, 107]
    for i in ids:
        svc.start(i)
    for i in ids:
        svc.wait(i)
    got = {i: svc.view(i) for i in ids}
    assert {i: v["recommendation"] for i, v in got.items()} == {
        101: "AUTO_PASS", 102: "AUTO_PASS", 103: "HOLD", 104: "MANUAL_REVIEW", 105: "HOLD", 107: "AUTO_PASS"}
    inv = {i: {f["name"]: f["value"] for f in v["final"]["fields"]}["invoice_num"] for i, v in got.items()}
    assert inv == {101: "SYN-INV-0001", 102: "SYN-INV-0002", 103: "SYN-INV-0003", 104: "SYN-INV-0004",
                   105: "SYN-INV-0005", 107: "SYN-INV-0007"}
    for i, v in got.items():
        assert v["id"] == i and svc.part(i, "payload")["package"]["dms_doc_id"] == str(i)
        assert svc.part(i, "extraction")["dms_doc_id"] == str(i)
        assert all(it["label"] for p in v["pages"] for it in p["kept"])
    assert got[103]["exception_codes"] == ["E02"] and got[105]["exception_codes"] == ["E05"]
    assert {r["rule_id"]: r["result"] for r in got[103]["verify"]}["V-04"] == "not_evaluated"      # gated by V-02


def test_busy_and_rerun(settings, oracle_dataset):
    eng = GatedEngine(InProcessEngine(oracle_dataset))
    svc = make(settings, eng)
    svc.start(101)
    assert eng.entered.wait(5)
    with pytest.raises(Busy):
        svc.start(101)                                                  # one job per document
    with pytest.raises(Busy):
        svc.delete(101)
    with pytest.raises(NotReady):
        svc.view(101)                                                   # no half result while running
    assert svc.status(101)["state"] == "processing" and svc.status(101)["step"] == "validate"
    assert svc.status(102)["state"] == "idle"                           # other documents are unaffected
    eng.release.set()
    assert svc.wait(101)["state"] == "done"
    eng.release.clear(); eng.entered.clear()
    svc.start(101)                                                      # re-process: run 2, old result gone first
    assert svc.status(101)["run"] == 2
    with pytest.raises(NotReady):
        svc.view(101)
    assert eng.entered.wait(5)
    eng.release.set()
    svc.wait(101)
    assert svc.view(101)["run"] == 2
    svc.shutdown()


def test_a_failing_engine_is_an_error_on_that_document_only(settings, oracle_dataset):
    svc = make(settings, BrokenEngine())
    svc.start(101)
    st = svc.wait(101)
    assert st["state"] == "error" and "System A is down" in st["error"] and st["recommendation"] is None
    with pytest.raises(NotReady):
        svc.view(101)
    assert svc.status(102)["state"] == "idle"
    svc.engine = InProcessEngine(oracle_dataset)                       # System A comes back: process again
    svc.start(101)
    assert svc.wait(101)["state"] == "done" and svc.status(101)["run"] == 2
    svc.shutdown()


def test_a_stale_run_cannot_write(parts):
    _, svc, _ = parts
    svc.start(101)
    svc.wait(101)
    assert svc._update(101, 0, state="error", error="late result of run 0") is False
    assert svc.status(101)["state"] == "done"


def test_results_survive_a_restart(settings, oracle_dataset):
    a = make(settings, InProcessEngine(oracle_dataset))
    a.start(101)
    a.wait(101)
    a.start(103)
    a.wait(103)
    a.shutdown()
    b = make(settings, InProcessEngine(oracle_dataset))
    assert b.status(101)["state"] == "done" and b.status(101)["recommendation"] == "AUTO_PASS"
    assert b.view(103)["exception_codes"] == ["E02"] and b.status(102)["state"] == "idle"
    b.shutdown()


def test_a_run_interrupted_by_a_restart_is_reported_not_served(settings, oracle_dataset):
    store = ResultStore(settings.data_dir)
    store.save(101, "state", {"id": 101, "state": "processing", "run": 3, "step": "validate"})
    svc = make(settings, InProcessEngine(oracle_dataset))
    st = svc.status(101)
    assert st["state"] == "error" and "restart" in st["error"] and st["run"] == 3
    with pytest.raises(NotReady):
        svc.view(101)
    svc.shutdown()


def test_delete_and_search(parts):
    _, svc, _ = parts
    svc.start(101)
    svc.start(102)
    svc.wait(101)
    svc.wait(102)
    assert svc.search("gasket") == [101, 102] and svc.search("SYN-INV-0002") == [102] and svc.search("101") == [101]
    assert svc.search("") == []
    assert svc.delete(101)["state"] == "idle"
    assert svc.search("gasket") == [102]
    with pytest.raises(NotReady):
        svc.view(101)


def test_unknown_document(parts):
    _, svc, _ = parts
    with pytest.raises(KeyError):
        svc.start(999)
