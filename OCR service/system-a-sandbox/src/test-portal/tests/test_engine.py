"""The seam: ``Runner.run(doc_id) -> aiva.system_a.result/3.0``, for both values of ``SYSTEM_A_ENGINE``.

``http`` is tested against **System A's own API** (``system_a.api.app.create_app``) mounted in-process on an ASGI
transport - same routes, same auth, same async job, no network and no VLM.  The extraction that goes over the
wire is the synthetic ``aiva.extraction/2.0`` of :mod:`tests.synth`.
"""
import httpx
import pytest

from doubles import FakeSystemA
from fastapi.testclient import TestClient
from webapp.engine import EngineError, HttpValidator, LocalRunner, RemoteRunner, build_runner


def asgi(app):
    """A sync httpx client that talks to an ASGI app in this process - no socket, no uvicorn."""
    return TestClient(app, base_url="http://system-a.test")


class Recorder:
    """A transport that answers with what the test says, and keeps every request the validator sent."""

    def __init__(self, replies):
        self.replies, self.requests = replies, []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        reply = self.replies[min(len(self.requests) - 1, len(self.replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        status, body = reply
        return httpx.Response(status, json=body, request=request)


def validator(replies, **kw) -> tuple[HttpValidator, Recorder]:
    rec = Recorder(replies)
    v = HttpValidator("http://system-a.test/", api_key=kw.pop("key", ""),
                      client=httpx.Client(transport=httpx.MockTransport(rec.handler)),
                      poll_s=kw.pop("poll_s", 0.0), timeout_s=kw.pop("timeout_s", 5.0), **kw)
    return v, rec


# ------------------------------------------------------------------ inprocess
def test_local_runner_just_asks_system_a(settings):
    sa = FakeSystemA({"contract": "aiva.system_a.result/3.0"})
    r = LocalRunner(sa)
    assert r.name == "inprocess"
    assert r.run(101, run=1) == {"contract": "aiva.system_a.result/3.0"}
    assert sa.calls == [("process", 101)]
    assert r.health()["standard"] == "6.6"


def test_local_runner_lets_the_failure_through_untouched():
    sa = FakeSystemA(fail_with=RuntimeError("VLM returned no page items"))
    with pytest.raises(RuntimeError, match="VLM returned no page items"):
        LocalRunner(sa).run(101, run=1)


def test_the_engine_setting_picks_the_runner(settings):
    from dataclasses import replace
    sa = FakeSystemA({})
    assert isinstance(build_runner(settings, sa), LocalRunner)
    assert build_runner(settings, sa).name == "inprocess"
    http = build_runner(replace(settings, engine="http"), sa)
    assert isinstance(http, RemoteRunner) and http.name == "http"
    assert http.v.base == settings.system_a_url                  # the server the portal was told to talk to


# ------------------------------------------------------------------ http: the protocol
def test_the_validator_creates_polls_and_fetches_the_result(payload):
    v, rec = validator([(202, {"validation_id": "VAL-1", "status": "queued", "idempotent_replay": False}),
                        (200, {"validation_id": "VAL-1", "status": "running", "error": None}),
                        (200, {"validation_id": "VAL-1", "status": "completed", "error": None}),
                        (200, payload)])
    got = v.validate({"contract": "aiva.extraction/2.0", "dms_doc_id": "DMS-101"}, doc_id=101, run=4)
    assert got == payload
    assert [r.url.path for r in rec.requests] == ["/v1/validations", "/v1/validations/VAL-1",
                                                  "/v1/validations/VAL-1", "/v1/validations/VAL-1/result"]
    import json
    body = json.loads(rec.requests[0].content)
    assert body["extraction"]["dms_doc_id"] == "DMS-101"
    assert body["portal_refs"] == {"document_revision": 1, "validation_round": 4}   # the round is told to System A
    assert rec.requests[0].headers["idempotency-key"].startswith("web-101-4-")
    assert rec.requests[0].headers["x-correlation-id"] == "web-101-4"


def test_the_api_key_is_sent_on_every_call(payload):
    v, rec = validator([(202, {"validation_id": "V", "status": "completed"}),
                        (200, {"status": "completed"}), (200, payload)], key="sekret")
    v.validate({"contract": "aiva.extraction/2.0"}, doc_id=1, run=1)
    assert all(r.headers.get("x-api-key") == "sekret" for r in rec.requests)
    assert len(rec.requests) == 3
    v2, rec2 = validator([(202, {"validation_id": "V", "status": "completed"}),
                          (200, {"status": "completed"}), (200, payload)])
    v2.validate({"contract": "aiva.extraction/2.0"}, doc_id=1, run=1)
    assert not any("x-api-key" in r.headers for r in rec2.requests)   # no key configured -> none sent


@pytest.mark.parametrize("replies,why", [
    ([(500, {"detail": "boom"})], "rejected the request"),
    ([(202, {"validation_id": "V", "status": "queued"}), (200, {"status": "failed", "error": {"code": "E"}})],
     "job failed"),
    ([(202, {"validation_id": "V", "status": "queued"}), (404, {"detail": "gone"})], "status check failed"),
    ([(202, {"validation_id": "V", "status": "queued"}), (200, {"status": "queued"})] * 6, "did not finish"),
    ([(202, {"validation_id": "V", "status": "completed"}), (200, {"status": "completed"}),
      (500, {"detail": "no result"})], "result fetch failed"),
    ([(202, {"validation_id": "V", "status": "completed"}), (200, {"status": "completed"}),
      (409, {"detail": "status=running"})], "result fetch failed"),
])
def test_every_way_the_server_can_fail_becomes_one_engine_error(replies, why):
    v, _ = validator(replies, timeout_s=0.05)
    with pytest.raises(EngineError) as e:
        v.validate({"contract": "aiva.extraction/2.0"}, doc_id=9, run=1)
    assert why in str(e.value), str(e.value)


def test_a_server_that_is_not_there_is_an_engine_error():
    v = HttpValidator("http://127.0.0.1:1/", client=httpx.Client(
        transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("connection refused")))))
    with pytest.raises(EngineError, match="unreachable"):
        v.validate({"contract": "aiva.extraction/2.0"}, doc_id=1, run=1)
    h = v.health()
    assert h["ok"] is False and h["url"] == "http://127.0.0.1:1" and "ConnectError" in h["error"]


def test_remote_runner_reads_here_and_validates_there(payload):
    sent = {}

    class Read(FakeSystemA):
        def perceive(self, doc_id):
            sent["doc"] = doc_id
            return {"contract": "aiva.extraction/2.0", "dms_doc_id": f"DMS-{doc_id}"}

    v, rec = validator([(202, {"validation_id": "V", "status": "completed"}), (200, {"status": "completed"}),
                        (200, payload)])
    r = RemoteRunner(Read(payload), v)
    assert r.run(103, run=2) == payload
    assert sent == {"doc": 103}
    import json
    assert json.loads(rec.requests[0].content)["extraction"]["dms_doc_id"] == "DMS-103"
    assert r.health()["ok"] is True


def test_health_of_the_http_engine_reports_the_server_it_probes():
    v, rec = validator([(200, {"status": "ok", "mode": "production", "ai_mode": "litellm", "standard": "6.6",
                               "ruleset": "v6.6-r4"})])
    h = v.health()
    assert h == {"engine": "http", "ok": True, "url": "http://system-a.test", "status": "ok", "mode": "production",
                 "ai_mode": "litellm", "standard": "6.6", "ruleset": "v6.6-r4"}
    assert rec.requests[0].url.path == "/health/ready"


# ------------------------------------------------------------------ http: the real System A server
@pytest.fixture(scope="session")
def system_a_asgi(harness, buyer):
    """System A's own HTTP API, in-process, sandbox mode: real routes, real job store, in-memory Oracle."""
    import synth
    from system_a import container
    from system_a.api.app import create_app

    ext = synth.extraction(buyer=buyer)
    ds = synth.oracle_dataset()
    a = container.Settings(mode="sandbox", ai_mode="sim", api_key="", oracle_backend="memory")
    app = create_app(a, lambda: container.build_services(a, oracle_dataset=ds))
    return ext, app


def test_the_http_engine_is_the_same_system_a(system_a_asgi):
    import json

    ext, app = system_a_asgi
    v = HttpValidator("http://system-a.test", client=asgi(app), poll_s=0.01)
    got = RemoteRunner(FakeSystemA(None, extraction=ext), v).run(101, run=1)

    assert got["contract"] == "aiva.system_a.result/3.0"
    assert got["recommendation"]["value"] == "AUTO_PASS"
    assert [r["rule_id"] for r in got["rule_results"]] == [f"V-0{i}" for i in range(1, 10)]
    assert got["ocr"]["elements"] and all(e["bbox"] for e in got["ocr"]["elements"])
    assert got["request"]["validation_round"] == 1 and got["request"]["correlation_id"].startswith("web-101-1")
    assert got["request"]["idempotency_key"].startswith("web-101-1-")
    assert json.loads(json.dumps(got)) == got                            # it survives the wire unchanged


def test_the_http_engine_and_the_library_agree_on_the_same_payload(system_a_asgi, buyer):
    """Same extraction in, same bytes out - that is what makes the engine switch a test choice, not a rewrite."""
    import synth
    from system_a import container

    ext, app = system_a_asgi
    over_http = RemoteRunner(FakeSystemA(None, extraction=ext),
                             HttpValidator("http://system-a.test", client=asgi(app), poll_s=0.01)).run(101, run=1)
    in_process = synth.payload(buyer=buyer, ext=ext, dataset=synth.oracle_dataset(), validation_id="VAL-SYN-0001")

    volatile = ("request", "metrics", "oracle_snapshot", "integrity")
    for block in ("pages", "documents", "ocr", "extraction", "normalized_fields", "line_matching", "rule_results",
                  "evidence", "exceptions", "recommendation"):
        assert over_http[block] == in_process[block], block
    assert over_http["contract"] == in_process["contract"]
    assert all(k in over_http for k in volatile)


def test_an_extraction_system_a_rejects_is_an_engine_error(system_a_asgi):
    _ext, app = system_a_asgi
    v = HttpValidator("http://system-a.test", client=asgi(app), poll_s=0.01)
    with pytest.raises(EngineError, match="HTTP 422"):
        v.validate({"contract": "aiva.extraction/1.0"}, doc_id=1, run=1)


def test_a_key_the_server_does_not_know_is_refused(buyer, system_a_asgi):
    import synth
    from system_a import container
    from system_a.api.app import create_app

    ext, _app = system_a_asgi
    a = container.Settings(mode="sandbox", ai_mode="sim", api_key="sekret", oracle_backend="memory")
    app = create_app(a, lambda: container.build_services(a, oracle_dataset=synth.oracle_dataset()))
    with pytest.raises(EngineError, match="HTTP 401") as e:
        HttpValidator("http://system-a.test", api_key="wrong", client=asgi(app)).validate(ext, doc_id=1, run=1)
    assert "401" in str(e.value)
    assert asgi(app).get("/health/live").status_code == 200       # the health routes are open by design
