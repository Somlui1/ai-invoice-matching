import httpx
import pytest
from fastapi.testclient import TestClient

from webapp.batch import BatchSource
from webapp.engine import EngineError, HttpEngine, InProcessEngine, load_oracle_dataset
from webapp.perception import ReplayPerception


@pytest.fixture
def extraction(batch_dir):
    return ReplayPerception(BatchSource(batch_dir)).extract(101)


def test_in_process_engine_returns_the_system_a_result(extraction, oracle_dataset):
    eng = InProcessEngine(oracle_dataset)
    res = eng.validate(extraction, doc_id=101, run=1)
    assert res["contract"] == "aiva.system_a.result/3.0" and res["recommendation"]["value"] == "AUTO_PASS"
    assert res["request"]["validation_round"] == 1 and res["package"]["dms_doc_id"] == "101"
    assert [r["rule_id"] for r in res["rule_results"]] == [f"V-0{i}" for i in range(1, 10)]
    assert eng.health()["ok"] is True and eng.health()["standard"]


def test_in_process_engine_wraps_failures(oracle_dataset):
    with pytest.raises(EngineError, match="in-process"):
        InProcessEngine(oracle_dataset).validate({"contract": "aiva.extraction/2.0"}, doc_id=1, run=1)


def test_http_engine_gives_the_same_result_as_in_process(harness, extraction, oracle_dataset):
    """The same extraction through System A's HTTP API and through the direct call: identical payload hash."""
    from system_a.api.app import create_app
    from system_a.container import Settings, build_services
    s = Settings(mode="sandbox", ai_mode="sim")
    api = TestClient(create_app(s, lambda: build_services(s, oracle_dataset=oracle_dataset)))
    http = HttpEngine("http://testserver", client=api, poll_s=0.01)
    a = http.validate(extraction, doc_id=101, run=1)
    b = InProcessEngine(oracle_dataset).validate(extraction, doc_id=101, run=1)
    assert a["integrity"]["payload_sha256"] == b["integrity"]["payload_sha256"]
    assert a["recommendation"]["value"] == b["recommendation"]["value"] == "AUTO_PASS"
    assert http.health()["ok"] is True


def test_http_engine_reports_a_rejected_request(harness, oracle_dataset):
    from system_a.api.app import create_app
    from system_a.container import Settings, build_services
    s = Settings(mode="sandbox", ai_mode="sim")
    api = TestClient(create_app(s, lambda: build_services(s, oracle_dataset=oracle_dataset)))
    with pytest.raises(EngineError, match="HTTP 422"):
        HttpEngine("http://testserver", client=api).validate({"contract": "aiva.extraction/2.0"}, doc_id=1, run=1)


def test_http_engine_unreachable():
    def boom(request):
        raise httpx.ConnectError("refused", request=request)
    eng = HttpEngine("http://nowhere.invalid", client=httpx.Client(transport=httpx.MockTransport(boom)))
    with pytest.raises(EngineError, match="unreachable"):
        eng.validate({}, doc_id=1, run=1)
    h = eng.health()
    assert h["ok"] is False and "ConnectError" in h["error"]


def test_http_engine_sends_the_api_key_and_a_job_that_fails_is_an_error():
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path, request.headers.get("x-api-key")))
        if request.method == "POST":
            return httpx.Response(202, json={"validation_id": "V1", "status": "queued"})
        return httpx.Response(200, json={"validation_id": "V1", "status": "failed", "error": {"code": "INTERNAL_ERROR"}})
    eng = HttpEngine("http://sa", api_key="k", client=httpx.Client(transport=httpx.MockTransport(handler)), poll_s=0.01)
    with pytest.raises(EngineError, match="failed"):
        eng.validate({}, doc_id=1, run=1)
    assert all(k == "k" for _, _, k in seen) and seen[0][:2] == ("POST", "/v1/validations")


def test_oracle_dataset_resolution(tmp_path, batch_dir):
    assert load_oracle_dataset(None, None) == {}
    assert load_oracle_dataset(batch_dir / "oracle_dataset.json", None)["receipts"]
    home = tmp_path / "sa"
    (home / "sandbox_data").mkdir(parents=True)
    (home / "sandbox_data" / "oracle_dataset.json").write_text('{"receipts": [], "po_supplier": {"1": "2"}}')
    assert load_oracle_dataset(None, home)["po_supplier"] == {"1": "2"}
