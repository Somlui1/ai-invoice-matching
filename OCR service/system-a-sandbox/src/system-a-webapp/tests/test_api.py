import time


def run_and_wait(client, doc_id, timeout=20):
    r = client.post(f"/api/documents/{doc_id}/process")
    assert r.status_code == 202, r.text
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = client.get(f"/api/documents/{doc_id}").json()
        if s["state"] != "processing":
            return s
        time.sleep(0.05)
    raise AssertionError("still processing")


def test_meta_health_and_list(client):
    m = client.get("/api/meta").json()
    assert m["engine"] == "inprocess" and m["perception"] == "replay" and m["batch"]["documents"] == 7
    assert m["replay"]["assume_agreement"] is True and m["colors"]["line"] == "#1f77b4"
    h = client.get("/api/health")
    assert h.status_code == 200 and h.json()["ok"] is True
    docs = client.get("/api/documents").json()
    assert [d["id"] for d in docs] == [101, 102, 103, 104, 105, 106, 107]
    assert docs[0]["pages"] == [1] and docs[1]["pages"] == [1, 2, 3] and docs[0]["viewer_url"] and docs[1]["viewer_url"] is None


def test_unknown_document_is_404(client):
    for method, url in (("get", "/api/documents/999"), ("post", "/api/documents/999/process"),
                        ("get", "/api/documents/999/result"), ("delete", "/api/documents/999/result"),
                        ("get", "/api/documents/999/pages/1/image")):
        assert getattr(client, method)(url).status_code == 404, url
    assert client.get("/api/documents/101/pages/9/image").status_code == 404


def test_the_workflow(client):
    assert client.get("/api/documents/101/result").status_code == 409          # nothing before Process
    assert client.get("/api/documents/101/payload").status_code == 409
    s = run_and_wait(client, 101)
    assert s["state"] == "done" and s["recommendation"] == "AUTO_PASS"
    v = client.get("/api/documents/101/result").json()
    assert v["recommendation"] == "AUTO_PASS" and v["cls"] == "ok" and v["run"] == 1 and v["perception"] == "replay"
    page = v["pages"][0]
    assert page["kept"] and all(0 <= i["bbox_norm"][0] <= 1 and 0 <= i["bbox_norm"][1] <= 1 for i in page["kept"])
    refs = [f["ref"] for f in v["final"]["fields"] if f["ref"]]
    assert refs and all(page["kept"][r["i"]]["bbox_norm"] for r in refs)                # row -> the box it came from
    inv = next(f for f in v["final"]["fields"] if f["name"] == "invoice_num")
    assert page["kept"][inv["ref"]["i"]]["label"] == "doc_no"
    assert client.get("/api/documents/101/payload").json()["contract"] == "aiva.system_a.result/3.0"
    assert client.get("/api/documents/101/extraction").json()["contract"] == "aiva.extraction/2.0"
    d = client.delete("/api/documents/101/result")
    assert d.status_code == 200 and d.json()["state"] == "idle"
    assert client.get("/api/documents/101/result").status_code == 409


def test_a_failed_rule_points_at_its_evidence(client):
    run_and_wait(client, 103)
    v = client.get("/api/documents/103/result").json()
    v02 = next(r for r in v["verify"] if r["rule_id"] == "V-02")
    assert v["recommendation"] == "HOLD" and v02["result"] == "fail" and v02["code"] == "E02"
    assert v02["evidence"][0]["refs"] and v02["ref"] == v02["evidence"][0]["refs"][0]
    assert v["pages"][0]["kept"][v02["ref"]["i"]]["label"].startswith("line_")


def test_process_twice_while_running_is_409(client, parts):
    _, svc, _ = parts
    import threading
    gate = threading.Event()
    real = svc.engine.validate
    svc.engine.validate = lambda *a, **k: (gate.wait(10), real(*a, **k))[1]
    try:
        assert client.post("/api/documents/101/process").status_code == 202
        assert client.post("/api/documents/101/process").status_code == 409
        assert client.delete("/api/documents/101/result").status_code == 409
        assert client.post("/api/documents/102/process").status_code == 202          # another document is fine
    finally:
        gate.set()
    svc.wait(101)
    svc.wait(102)


def test_search_endpoint(client):
    run_and_wait(client, 102)
    assert client.get("/api/search", params={"q": "syn-inv-0002"}).json()["ids"] == [102]
    assert client.get("/api/search", params={"q": "syn-inv-0001"}).json()["ids"] == []


def test_page_images(client):
    r = client.get("/api/documents/101/pages/1/image")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content[:2] == b"\xff\xd8"
    s = client.get("/api/documents/105/pages/1/image")                       # no JPG on disk -> a page drawn from the OCR
    assert s.status_code == 200 and s.headers["content-type"] == "image/svg+xml"
    assert "image not found" in s.text and "SYN-INV-0005" in s.text and "<svg" in s.text


def test_viewer_pages_are_served_and_cannot_escape(client):
    assert client.get("/batch/docs/doc_101/viewer.html").status_code == 200
    assert client.get("/batch/docs/../report.html").status_code in (404, 400)
    assert client.get("/batch/docs/%2e%2e/report.html").status_code in (404, 400)


def test_health_is_503_when_the_engine_is_down(client, parts):
    _, svc, _ = parts
    svc.engine.health = lambda: {"ok": False, "error": "down"}
    r = client.get("/api/health")
    assert r.status_code == 503 and r.json()["ok"] is False
