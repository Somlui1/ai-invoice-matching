"""The browser half, checked as text: every box it draws must come out of the payload the server sent.

There is no headless browser in this environment, so these tests read ``app.js`` / ``index.html`` and check them
against the server they talk to - the endpoints, the field names of the screen model, the ids of the controls.
"""
import pathlib
import re

from webapp.view import DEFAULT_TYPES

HERE = pathlib.Path(__file__).resolve().parents[1]
JS = (HERE / "webapp" / "static" / "app.js").read_text(encoding="utf-8")
HTML = (HERE / "webapp" / "static" / "index.html").read_text(encoding="utf-8")
CODE = JS.split("*/", 1)[1]                                   # everything after the file's header comment


def js_paths():
    """Every ``/api/...`` path the script uses - concatenation, ``${id}`` and all - with variables as ``{}``."""
    out = set()
    for line in JS.splitlines():
        if "/api" not in line:
            continue
        s = line
        while re.search(r"'\s*\+\s*[a-z][\w.]*\s*\+\s*'", s):          # 'a' + id + 'b'  ->  'a{b'
            s = re.sub(r"'\s*\+\s*[a-z][\w.]*\s*\+\s*'", "\x00", s, count=1)
        s = re.sub(r"'\s*\+\s*(?:[a-z][\w.]*|encodeURIComponent\()", "\x00'", s)   # 'a' + id  ->  'a{'
        for m in re.findall(r"/api[^\s'\"`\\]+", s):
            out.add(re.sub(r"\$\{[^}]*\}", "{}", m).replace("\x00", "{}").split("?")[0].rstrip("/"))
    return out


def test_every_control_the_script_reaches_for_exists():
    wanted = set(re.findall(r"\$\('([a-z]+)'\)", JS))
    have = set(re.findall(r"id=([a-z]+)", HTML))
    assert wanted and wanted <= have, f"app.js wants {sorted(wanted - have)}"


def test_the_script_calls_only_endpoints_the_server_has(client):
    routes = {r.path.replace("{doc_id}", "{}").replace("{page}", "{}")
              for r in client.app.routes if r.path.startswith("/api")}
    called = js_paths()
    assert called, "the script calls nothing"
    assert called <= routes, f"app.js calls {sorted(called - routes)}"
    assert {"/api/meta", "/api/documents", "/api/documents/refresh", "/api/search"} <= called
    assert any(p.endswith("/process") for p in called) and any(p.endswith("/result") for p in called)
    assert any(p.endswith("/payload") for p in called) and any(p.endswith("/extraction") for p in called)
    assert any(p.endswith("/pdf") for p in called) and any(p.endswith("/image") for p in called)


def test_boxes_are_drawn_from_the_payload_and_are_not_moved_or_guessed():
    for field in ("elements", "bbox", "has_bbox", "raw", "conf", "data-ref", "element_id"):
        assert field in CODE, field
    # a box is placed with the four numbers of the payload element, on a page sized by the payload's own geometry
    assert "= e.bbox;" in CODE and "left:${(x * 100)" in CODE and "width:${(w * 100)" in CODE
    assert "aspect-ratio:${full.width_pt}/${full.height_pt}" in CODE and "full.rotation" in CODE
    assert "page_type" in CODE
    for invented in ("iou", "bbox_norm", "items_by_page", "kept[", "matchElement"):
        assert invented not in CODE.lower(), invented           # no matching by guess, no second coordinate system


def test_the_paths_that_were_removed_stay_removed():
    for gone in ("/api/batch", "/api/replay", "/api/placeholder", "/api/demo", "items_by_page", "kept",
                 "perception", "<svg", "bbox_norm", "replay"):
        assert gone not in JS, gone
    for gone in ("batch", "replay", "demo"):
        assert gone not in HTML, gone


def test_the_element_types_come_from_the_server_and_are_remembered_locally(client):
    m = client.get("/api/meta").json()
    assert set(DEFAULT_TYPES) <= set(m["element_types"]) and set(m["default_types"]) <= set(m["element_types"])
    assert "META.element_types" in CODE and "default_types" in CODE      # the script hard-codes no type name
    assert "v.types" in CODE                                            # which types this document has = the payload
    assert "localStorage" in JS and "aiva.sysA" in JS                   # the user's toggles survive a reload
    assert "data-t=" in CODE and "SHOW.has(" in CODE and "writeTypes()" in CODE
    assert "#1f77b4" not in JS                                          # no colour is hard-coded in the script either


def test_a_failure_is_shown_as_the_failure_system_a_gave():
    assert "traceback" in CODE and "<details" in CODE and "<pre>" in CODE
    assert "source_error" in CODE                              # a DMS that cannot serve its file is said too
    assert "src_err" in CODE


def test_it_starts_a_run_then_polls_and_can_forget_a_result():
    assert "setTimeout" in CODE and "'POST'" in CODE or "method: 'POST'" in CODE
    assert "DELETE" in CODE                                    # forget(doc_id)
    assert "Esc" in CODE or "keydown" in CODE                  # the pinned box can be closed
