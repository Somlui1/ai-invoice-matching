"""The UI contract.

``ORIGINAL_CSS`` is the CSS of the original ``report.html`` kept verbatim: the portal still draws the boxes, the
tooltip and the pinned card with those rules, so a change here is a deliberate redesign and not an accident.
The workbench (``.wb`` / ``.pages`` / ``.panel``) and the toolbar controls the Paperless workflow needs are
asserted separately; the "added" tail of the stylesheet may only introduce *new* selectors.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "webapp" / "static"
ORIGINAL_CSS = [
    "body{margin:0;font-family:Tahoma,sans-serif;font-size:13px}",
    "#top{position:sticky;top:0;z-index:5;background:#eee;border-bottom:1px solid #bbb;padding:6px 10px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}",
    "#wrap{display:flex}",
    "#side{width:260px;flex:none;height:calc(100vh - 42px);overflow:auto;border-right:1px solid #ccc;position:sticky;top:42px}",
    "#side div{padding:3px 8px;cursor:pointer;border-bottom:1px solid #eee;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
    "#side div:hover{background:#f3f3f3} #side div.cur{background:#dbe9ff}",
    "#main{flex:1;padding:10px;min-width:0}",
    ".doc{border:1px solid #bbb;margin-bottom:18px} .doc>h2{margin:0;padding:6px 8px;background:#f4f4f4;font-size:15px}",
    ".pg{display:flex;gap:10px;padding:8px;border-top:1px dashed #ccc;align-items:flex-start}",
    ".imgbox{position:relative;width:50%;flex:none}",
    ".imgbox img{width:100%;display:block;border:1px solid #ccc}",
    ".bx{position:absolute;box-sizing:border-box;border:1px solid transparent;cursor:pointer}",
    ".bx.hot{border-width:3px;background:rgba(255,220,0,.30);z-index:3}",
    ".bx.sel{border-width:3px;border-style:dashed;background:rgba(20,120,255,.20);z-index:4}",
    "tr.hot{background:#fff8d5} tr.sel{background:#dbe9ff}",
    "#tip{position:fixed;z-index:50;display:none;max-width:460px;background:#111;color:#fff;font-size:12px;line-height:1.4;padding:6px 8px;border-radius:4px;pointer-events:none;white-space:pre-wrap}",
    "#pin{position:fixed;right:12px;bottom:12px;z-index:40;display:none;max-width:420px;background:#fff;border:2px solid #333;font-size:12px;line-height:1.4;padding:7px 26px 7px 9px;border-radius:5px;box-shadow:0 2px 10px #0006;white-space:pre-wrap}",
    "#unc{position:absolute;right:6px;top:4px;color:#666;font-weight:bold}",
    ".no-ov .bx{display:none}",
    ".pg .info{flex:1;min-width:0}",
    "table{border-collapse:collapse;width:100%;font-size:12px} td,th{border:1px solid #ddd;padding:2px 5px;vertical-align:top;text-align:left}",
    "th{background:#fafafa} .dr td{color:#999;text-decoration:line-through}",
    ".ok{color:#2a2} .partial{color:#d80} .error{color:#c00} .lg span{color:#fff;padding:1px 6px;margin-right:3px}",
    ".sw{display:inline-block;width:10px;height:10px;margin-right:4px}",
    ".hide-tbl .info table{display:none}",
]
# The toolbar of the workflow build.  It is the original bar plus the controls the new job needs
# (Process, the bbox switch, refresh, clearing the browser cases, the source badge) - one document at a
# time now, so the old "มุมมอง" (all/one) selector is gone.
BAR = [
    "<b>AIVA System A</b>", "<span id=stat></span>",
    "<button id=run class=run>Process</button>", '<span id=pst style="color:#555"></span>',
    '<label>สถานะ <select id=fs><option value="">ทั้งหมด</option><option>ok</option><option>partial</option><option>error</option></select></label>',
    '<label>ประเภท <select id=ft><option value="">ทั้งหมด</option></select></label>',
    '<input id=q placeholder="ค้น id / ชื่อ / ข้อความ" size=18>',
    "<label><input type=checkbox id=ov checked> <b>แสดง bbox</b></label>",
    "<label><input type=checkbox id=tb checked> ตาราง</label>",
    "<label><input type=checkbox id=dp> ที่ตัดทิ้ง</label>",
    "<button id=rf", "<button id=clr", "<span id=src class=src></span>",
    "<button id=prev>◀</button><button id=next>▶</button>",
    '<span style="color:#555">ชี้กรอบ/แถว = ดูข้อความ · คลิก = ตรึงข้อมูล + ไปแถวนั้น · Esc = ปิด</span>',
    "<div id=wrap><div id=side></div><div id=main></div></div>", "<div id=tip></div><div id=pin></div>",
]


@pytest.fixture(scope="module")
def html():
    return (STATIC / "index.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js():
    return (STATIC / "app.js").read_text(encoding="utf-8")


def test_original_css_is_untouched(html):
    css = html[html.index("<style>"):html.index("</style>")]
    for rule in ORIGINAL_CSS:
        assert rule in css, f"original rule changed or removed: {rule}"


def test_toolbar_and_structure(html):
    for part in BAR:
        assert part in html, part
    legend = re.findall(r"<span style='background:(#[0-9a-f]{6})'>(\w+)</span>", html)
    assert [n for _, n in legend] == ["header", "supplier", "customer", "table", "line", "total", "payment",
                                       "signature", "stamp", "other"]


def _selectors(css: str) -> set:
    return {s.strip() for s in re.findall(r"(?:^|\})\s*([^{}]+)\{", css, flags=re.M)}


def test_added_css_only_adds(html):
    css = html[html.index("<style>"):html.index("</style>")]
    tail = re.sub(r"/\*.*?\*/", "", css[css.index("added for the workflow") - 8:], flags=re.S)
    redefined = _selectors(tail) & _selectors("\n".join(ORIGINAL_CSS))
    assert redefined == {".imgbox img"}, redefined                  # the one deliberate addition: height/aspect-ratio
    assert ".imgbox img{height:auto;aspect-ratio:auto 1240/1754}" in tail
    assert ".pages .imgbox img{aspect-ratio:auto}" in tail          # a page of the DMS is not always A4


def test_new_toolbar_controls(html):
    bar = html[html.index("<div id=top>"):html.index("<div id=wrap>")]
    new = set(re.findall(r"id=(\w+)", bar)) - {"stat", "prev", "next", "ft", "fs", "q", "tb", "dp", "ov", "top"}
    assert new == {"run", "pst", "rf", "clr", "src"}


def test_the_workbench_has_three_panes(js):
    assert "<div class=wbm><div class=pages>" in js and "</div><div class=panel>" in js
    assert "<b>Final Result</b>" in js and "<b>Verify Result</b>" in js and "<b>ผล OCR</b>" in js
    assert re.search(r"<button class=\"run pill\" data-id=\$\{m\.id\}", js), "Process button per document"
    assert "api.pdf(m.id)" in js and "pagesHtml(m)" in js


def test_boxes_come_from_the_pipeline_and_toggle_together(js):
    assert 'class=bx data-i=' in js and "i.bbox_norm" in js
    assert "$('ov').onchange" in js and "'no-ov'" in js          # the switch uses the original .no-ov rule
    assert "data-ref=" in js and "tr[data-ref]" in js            # Final/Verify rows point at their box


def test_processed_cases_live_in_the_browser(js):
    assert "'aiva.sysA.cases.v1'" in js and "localStorage.setItem" in js and "localStorage.getItem" in js
    assert "localStorage.removeItem" in js                        # ล้าง case
    assert "CASE_MAX" in js and "slice(CASE_MAX)" in js           # the oldest cases are dropped, not the newest
    assert "from: null" in js and "'browser'" in js               # the UI says where a result came from


def test_served_with_no_cache(client):
    r = client.get("/")
    assert r.status_code == 200 and "no-store" in r.headers["cache-control"] and "<div id=side>" in r.text
    j = client.get("/static/app.js")
    assert j.status_code == 200 and "javascript" in j.headers["content-type"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_app_js_is_valid_javascript():
    r = subprocess.run(["node", "--check", str(STATIC / "app.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
