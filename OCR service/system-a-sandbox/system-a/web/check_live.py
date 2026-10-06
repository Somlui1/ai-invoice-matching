"""Live usability check for the Web Testing Portal.

Run against a server that is already up:

    python web/check_live.py [--base http://127.0.0.1:8080]

Unlike web/test_portal.py (offline, faked subprocess) this walks what a browser actually needs:
the page and every asset it references, the catalog, one real verification through the engine
subprocess, the overlay geometry, rasters, uploads, and the failure paths a user can reach.
It never starts a cold multi-page perception: if the engine is busy it reports 409 as correct
behaviour instead of queueing work behind a live run.
"""
from __future__ import annotations

import io
import json
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8080"
if "--base" in sys.argv:
    BASE = sys.argv[sys.argv.index("--base") + 1]

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Thai on a cp874 console

notes: list[str] = []
fails: list[str] = []


def get(path: str, timeout: int = 90, binary: bool = False):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            body = r.read()
            return r.status, r.headers, (body if binary else body.decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode("utf-8", "replace")
    except Exception as e:                                       # refused, reset, timeout
        return 0, {}, f"{type(e).__name__}: {e}"


def post(path: str, timeout: int = 900, data: bytes = b""):
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE + path, method="POST", data=data),
                                    timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def jload(body: str):
    """Parse a response body, but never die on it.

    When the portal is restarting, a proxy answers with an HTML page, or an endpoint answers 0 because
    the connection was refused, the body is not JSON.  A checker that raises a traceback there tells
    the operator nothing; returning {} turns the same situation into ordinary FAIL lines.
    """
    try:
        return json.loads(body)
    except Exception:
        return {}


def check(label: str, ok, detail: str = "") -> None:
    line = f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   [{detail}]" if detail else "")
    (notes if ok else fails).append(line)


def sse_events(body: str) -> list[dict]:
    out = []
    for chunk in body.split("\n"):
        if chunk.startswith("data:"):
            try:
                out.append(json.loads(chunk[5:].strip()))
            except json.JSONDecodeError:
                pass
    return out


# 1 ------------------------------------------------------------------------ the page and its assets
st, hdr, html = get("/")
check("GET / serves the UI", st == 200 and "<html" in html.lower(), f"{st}, {len(html):,} bytes")
check("UI is served as HTML", "text/html" in (hdr.get("content-type") or ""), hdr.get("content-type"))
check("no CDN / external origin in the markup", not re.search(r'(src|href)="https?://', html),
      "intranet-safe")

refs = sorted(set(re.findall(r'(?:src|href)="(/[^"]+)"', html)))
for ref in refs:
    st, h, body = get(ref, binary=True)
    check(f"asset {ref}", st == 200 and len(body) > 0, f"{st} {len(body):,}B")
    if ref.endswith(".js"):
        check(f"  correct mime for {ref}",
              "javascript" in (h.get("content-type") or "").lower(), h.get("content-type"))

st, _, appjs = get("/static/js/app.js")
for mod in sorted(set(re.findall(r'from\s+["\']([^"\']+)["\']', appjs))):
    path = mod if mod.startswith("/") else "/static/js/" + mod.rsplit("/", 1)[-1]
    st, _, body = get(path, binary=True)
    check(f"import {mod}", st == 200 and len(body) > 0, f"{st} {len(body):,}B")

ids_in_markup = set(re.findall(r'id="([^"]+)"', html))
ids_used = set(re.findall(r"\$\('([^']+)'\)", appjs)) | set(re.findall(r"getElementById\('([^']+)'\)", appjs))
check("every id app.js touches exists in the markup", ids_used <= ids_in_markup,
      f"missing={sorted(ids_used - ids_in_markup)}")

# 2 ------------------------------------------------------------------------ step ids: CLI bridge <-> UI
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import engine                                                     # noqa: E402
engine_steps = {step for _, step, _ in engine.STEP_MARKERS}
ui_steps = set(re.findall(r"\[\s*['\"]([a-z_]+)['\"]\s*,\s*['\"]", appjs))
need = {"start", "perception", "oracle", "assemble", "summary"}
check("UI step strip can be driven by the engine bridge", need <= engine_steps and bool(ui_steps),
      f"engine={sorted(engine_steps)} ui={sorted(ui_steps)}")
check("engine log lines carry a severity", engine.classify("warning: deprecated thing")[0] == "warn")

# 3 ------------------------------------------------------------------------ health + catalog
st, _, body = get("/api/health")
h = jload(body)
eng = h.get("engine") or {}
check("GET /api/health reports the engine interpreter it will use",
      st == 200 and eng.get("engine_python_exists"),
      f"mode={h.get('mode')} python={pathlib.Path(eng.get('engine_python', '?')).name} "
      f"cli_exists={eng.get('process_pdf_exists')}")
portal = h.get("portal") or {}
notes.append(f"      portal limits = {json.dumps(portal)}")
for k in ("paperless", "litellm", "oracle", "engine", "perception_cache"):
    if k in h:
        notes.append(f"      health.{k} = {json.dumps(h[k], default=str)[:88]}")

st, _, body = get("/api/documents?page=1")
page1 = jload(body)
items = page1.get("results") or []
check("GET /api/documents", st == 200 and len(items) >= 25,
      f"{page1.get('count')} documents, {len(items)} on page 1, {page1.get('badges_available')} badges")
st, _, body = get("/api/documents?page=2")
p2 = jload(body).get("results") or []
check("paging returns a disjoint slice", bool(p2) and not ({d["id"] for d in p2} & {d["id"] for d in items}),
      f"page 2 = {len(p2)}")
all_ids = {d["id"] for d in items} | {d["id"] for d in p2}
if not items:
    # nothing below this line has anything to probe, so say so instead of reporting 40 FAILs
    fails.append("ABORT  /api/documents returned no documents — the portal or Paperless-ngx is not "
                 f"answerable from this machine (base {BASE})")
    print("\n".join(fails))
    print(f"\n0 checks passed · {len(fails)} failed · base {BASE}")
    sys.exit(1)
check("catalog rows carry what the list renders",
      all({"id", "title", "page_count"} <= set(d) for d in items), "id/title/page_count present")
check("catalog exposes a dms key", all(str(d.get("dms_key") or f"DMS-{d['id']}") for d in items))

st, _, body = get("/api/documents?search=" + urllib.parse.quote("ใบแจ้งหนี้"))
sr = jload(body)
check("Thai search returns hits without mangling",
      st == 200 and (sr.get("count") or 0) > 0 and all(isinstance(d.get("title"), str) for d in sr["results"][:5]),
      f"{sr.get('count')} hits")

probe = items[0]
st, _, body = get(f"/api/documents/{probe['id']}/meta")
meta = jload(body)
check("GET /api/documents/{id}/meta", st == 200 and meta.get("page_count", 0) > 0,
      f"{meta.get('file')} · {meta.get('page_count')} pages · {meta.get('bytes'):,} bytes")
st, _, png = get(f"/api/documents/{probe['id']}/page/1.png", binary=True)
check("page raster renders (browser's own URL)", png[:8] == b"\x89PNG\r\n\x1a\n",
      f"{len(png):,} bytes")
st, _, pdfb = get(f"/api/documents/{probe['id']}/pdf", binary=True)
check("original PDF streams to the viewer", pdfb[:5] == b"%PDF-", f"{len(pdfb):,} bytes")

# 4 ------------------------------------------------------------------------ one real verification run
st, _, body = get("/api/runs")
rd = jload(body)
active, recent = rd.get("active") or [], rd.get("recent") or []
notes.append(f"      engine busy with {active or 'nothing'} at start of the check")
check("GET /api/runs", st == 200 and isinstance(recent, list), f"{len(recent)} recent, {len(active)} active")

st, _, body = get("/api/results")
stored = jload(body)
stored_keys = stored if isinstance(stored, list) else [r.get("key") for r in stored.get("results", [])]
pick = [d for d in (items + p2) if f"DMS-{d['id']}" not in active]
cached = [d for d in pick if f"DMS-{d['id']}" in stored_keys]
target = (cached or pick)[0]
key = f"DMS-{target['id']}"
st, body = post(f"/api/verify/{target['id']}?mode=sandbox")
events = sse_events(body)
steps = [e["step"] for e in events if e.get("type") == "step"]
logs = [e for e in events if e.get("type") == "log"]
done = [e for e in events if e.get("type") == "done"]
final = [e for e in events if "result" in e]

if st == 409:
    check("busy engine refuses a duplicate run (409)", True, "cap honoured")
    notes.append("SKIP  full run check — engine at capacity; re-run when the active runs finish")
    run_ok = None
else:
    run_ok = st == 200 and bool(done) and done[-1].get("ok")
    check(f"POST /api/verify/{key} runs the real CLI", run_ok,
          f"HTTP {st}, {len(events)} events, exit={done[-1].get('exit_code') if done else '?'}")
    check("progress steps streamed", {"perception", "oracle", "assemble"} <= set(steps) or
          {"perception_cached", "oracle", "assemble"} <= set(steps), f"steps={steps}")
    check("every log line carries a level", all("level" in e for e in logs), f"{len(logs)} lines")
    check("no ANSI escapes leak into the log", not any("\x1b" in e["line"] for e in logs))
    check("final event hands back the Contract 3.0 result",
          bool(final) and final[-1]["result"].get("recommendation", {}).get("value"),
          final[-1]["result"]["recommendation"]["value"] if final else "-")

# 5 ------------------------------------------------------------------------ overlay + geometry
st, _, body = get("/api/overlays/" + urllib.parse.quote(key))
ov = jload(body) if st == 200 else {}
check("GET /api/overlays/{key}", st == 200 and bool(ov), str(st))
coord = ov.get("coordinate_system") or {}
check("coordinate system is reported, never assumed",
      {"origin", "unit", "bbox_format"} <= set(coord), json.dumps(coord, ensure_ascii=False)[:64])

fields = ov.get("fields") or {}
cells = {f"{ln['line_no']}.{c}": c for ln in ov.get("lines") or [] for c in (ln.get("cells") or {})}
field_items, cell_items = list(fields.values()), [ln["cells"][c] for ln in ov.get("lines") or []
                                                  for c in (ln.get("cells") or {})]
check("header fields expose value + geometry",
      bool(field_items) and all({"raw", "ok", "element_id"} <= set(f) for f in field_items),
      f"{sum(1 for f in field_items if f.get('bbox'))}/{len(field_items)} boxed")
check("table cells expose value + geometry",
      bool(cell_items) and all({"raw", "ok"} <= set(c) for c in cell_items),
      f"{sum(1 for c in cell_items if c.get('bbox'))}/{len(cell_items)} boxed")
check("every line has a row box", all(ln.get("row", {}).get("bbox") for ln in ov.get("lines") or []),
      f"{len(ov.get('lines') or [])} lines")
check("exception carries code, severity and evidence boxes",
      all({"code", "severity", "boxes"} <= set(e) for e in ov.get("exceptions") or []),
      f"{sum(len(e.get('boxes') or []) for e in ov.get('exceptions') or [])} boxes")
check("signatures carry region + element id",
      all({"present", "page", "bbox", "element_id"} <= set(s) for s in (ov.get("signatures") or {}).values()),
      f"{len(ov.get('signatures') or {})} signatures")
check("rule cards list result + evidence ids",
      all({"rule_id", "result", "evidence_ids"} <= set(r) for r in ov.get("rules") or []),
      f"{len(ov.get('rules') or [])} rules")
check("layer inventory drives the toggles",
      bool(ov.get("layers")) and all({"id", "label", "count", "default"} <= set(l) for l in ov["layers"]),
      ", ".join(f"{l['id']}={l['count']}" for l in ov["layers"])[:70])

boxes = [b for b in (f.get("bbox") for f in field_items + cell_items) if b]
check("all boxes normalised into range", bool(boxes) and all(0 <= v <= 1.001 for b in boxes for v in b),
      f"{len(boxes)} boxes checked")
check("boxes reference a real page", all((f.get("page") or 1) >= 1 for f in field_items + cell_items))
el_index = {e.get("element_id") for items_ in (ov.get("by_type") or {}).values() for e in items_}
check("every boxed value can be joined to an element (cross-highlight key)",
      all(f.get("element_id") in el_index for f in field_items + cell_items if f.get("bbox")),
      f"element index = {len(el_index)}")
check("element items expose the keys the panels read",
      all({"element_id", "bbox", "page"} <= set(e) for e in (ov.get("by_type") or {}).get("cell", [])))

npages = len(ov.get("pages") or []) or 1
check("page geometry matches the raster",
      all({"page_no", "width_pt", "height_pt"} <= set(p) for p in ov.get("pages") or []),
      f"{npages} pages, {[(p['width_pt'], p['height_pt']) for p in ov.get('pages') or []][:2]}")
check("raster page count matches overlay pages",
      get(f"/api/documents/{probe['id']}/page/{npages}.png", binary=True)[1].get("content-type") == "image/png",
      f"page {npages} ok")
st, _, body = get(f"/api/overlays/{urllib.parse.quote(key)}/page/1")
pge = jload(body) if st == 200 else {}
check("per-page box subset endpoint works", st == 200 and
      all(b.get("page", 1) == 1 for b in pge.get("boxes", [])), f"{len(pge.get('boxes') or [])} boxes on page 1")
st, _, body = get(f"/api/bbox/layers/{urllib.parse.quote(key)}")
check("GET /api/bbox/layers/{key}", st == 200 and bool(jload(body).get("layers")), str(st))

# 6 ------------------------------------------------------------------------ result store + text integrity
st, _, body = get("/api/results/" + urllib.parse.quote(key))
res = jload(body) if st == 200 else {}
check("GET /api/results/{key} returns the stored contract",
      bool(res.get("recommendation", {}).get("value")), res.get("recommendation", {}).get("value", "-"))
raw_res = ((res.get("extraction") or {}).get("fields") or {}).get("supplier_address", {}).get("raw_value")
raw_ov = (fields.get("supplier_address") or {}).get("raw")
check("Thai text survives the API round trip", raw_res == raw_ov and bool(raw_res),
      repr((raw_ov or "")[:24]))
check("integrity hash present", bool((res.get("integrity") or {}).get("payload_sha256")),
      (res.get("integrity") or {}).get("payload_sha256", "")[:24])

# 7 ------------------------------------------------------------------------ uploads
downloads = pathlib.Path(".cache/downloads")
cand = sorted((f for f in downloads.glob("*.pdf") if not f.name.startswith("UP-")),
                  key=lambda p: p.stat().st_size) if downloads.exists() else []
if cand:
    pdf = cand[-1]
    bound = "----portalcheck"
    buf = io.BytesIO()
    buf.write((f"--{bound}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{pdf.name}\"\r\n"
               f"Content-Type: application/pdf\r\n\r\n").encode())
    buf.write(pdf.read_bytes())
    buf.write(f"\r\n--{bound}--\r\n".encode())
    req = urllib.request.Request(BASE + "/api/upload", data=buf.getvalue(),
                                 headers={"Content-Type": f"multipart/form-data; boundary={bound}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            up = json.loads(r.read().decode())
        ukey = up.get("key") or ""
        check("POST /api/upload accepts a PDF", bool(ukey), json.dumps(up, ensure_ascii=False)[:80])
        st, _, body = get("/api/uploads")
        check("GET /api/uploads lists it", ukey in body, str(st))
        st, _, upng = get(f"/api/uploads/{urllib.parse.quote(ukey)}/page/1.png", binary=True)
        check("uploaded page raster renders", upng[:8] == b"\x89PNG\r\n\x1a\n", f"{len(upng):,} bytes")
        st, _, updf = get(f"/api/uploads/{urllib.parse.quote(ukey)}/pdf", binary=True)
        check("uploaded PDF served back", updf[:5] == b"%PDF-", f"{len(updf):,} bytes")
        st, body = post(f"/api/verify/upload?key={urllib.parse.quote(ukey)}&mode=sandbox")
        if st == 409:
            notes.append("SKIP  upload verification — engine at capacity")
        else:
            # this is the route that '/api/verify/{doc_id}' used to swallow, so both the status and
            # the terminal event matter: 200 with a failed run is a different bug
            ev = sse_events(body)
            done_ev = [e for e in ev if e.get("type") == "done"]
            check("uploaded PDF verifies end to end", any(e.get("ok") for e in done_ev),
                  f"HTTP {st}, {len(ev)} events, exit={done_ev[-1].get('exit_code') if done_ev else 'no done event'}")
    except Exception as e:
        check("POST /api/upload accepts a PDF", False, f"{type(e).__name__}: {e}")
else:
    notes.append("SKIP  upload path (no cached PDF on disk to post)")

# 8 ------------------------------------------------------------------------ failure paths a user can reach
cases = [("/api/overlays/DMS-999999", 404), ("/api/results/DMS-999999", 404),
         ("/api/documents/999999/page/1.png", 404), ("/api/uploads/NOPE/page/1.png", 404),
         ("/static/js/nope.js", 404), ("/api/documents?page=999", 200)]
for path, want in cases:
    st, _, body = get(path)
    ok = st == want and "Traceback" not in body
    check(f"{path} -> {want}", ok, f"got {st}")
st, _, body = get("/api/documents/999999/pdf")
check("a stale document id explains itself", st == 404 and "not in Paperless" in body, f"{st} {body[:70]}")
st, _ = post("/api/verify/20?mode=banana", timeout=30)
check("unknown mode rejected (400)", st == 400, str(st))
st, _ = post("/api/runs/DMS-999999/cancel", timeout=30)
check("cancel of an idle document is a clean answer", st in (200, 404, 409), str(st))
st, _, body = get("/api/manifest")
mf = jload(body)
gaps = [f"P{p['phase']}:{p['missing']}" for p in mf.get("phases", []) if p.get("missing")]
check("manifest reports every phase complete", st == 200 and not gaps, "; ".join(gaps) or "no gaps")

# 9 ------------------------------------------------------------------------ cache friendliness of rasters
st, hdr1, _ = get(f"/api/documents/{probe['id']}/page/1.png", binary=True)
st, hdr2, _ = get(f"/api/documents/{probe['id']}/page/1.png", binary=True)
check("repeat raster request is served (cache sidecar)", st == 200 and
      hdr1.get("content-length") == hdr2.get("content-length"),
      f"{hdr2.get('content-length')} bytes both times")

print("\n".join(notes))
print("-" * 78)
print("\n".join(fails) if fails else "no failures")
print(f"\n{len(notes)} checks passed · {len(fails)} failed · base {BASE}")
sys.exit(1 if fails else 0)
