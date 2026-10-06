"""Drive the real UI in a real browser through the 7-step workflow.

    SYSTEM_A_HOME=<system-a project> python tests/e2e_browser.py [--shots DIR]

Needs ``pip install playwright`` + a Chromium (``playwright install chromium``, or CHROMIUM_PATH=<executable>).
Starts its own server on a free port with the synthetic batch; the replay perception is slowed down a little so the
"Processing" state is observable.
"""
import argparse
import glob
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT)]
os.environ.setdefault("SYSTEM_A_MODE", "sandbox")
os.environ.setdefault("SYSTEM_A_AI_MODE", "sim")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def find_package() -> Path:
    home = Path(os.environ["SYSTEM_A_HOME"])
    for c in (home / "src" / "system_a", home / "system_a", home):
        if (c / "__init__.py").is_file() and (c / "domain").is_dir():
            return c
    raise SystemExit("SYSTEM_A_HOME has no system_a package")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", default=str(ROOT / "e2e_shots"))
    a = ap.parse_args()
    shots = Path(a.shots)
    shots.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp())
    shutil.copytree(find_package(), work / "src" / "system_a", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(HERE / "system_a_stub" / "config", work / "config")
    sys.path.insert(0, str(work / "src"))
    from system_a.domain.standard import load_standard
    e = load_standard().entities[103]
    from webapp.demo import write_batch
    batch_dir = work / "batch"
    write_batch(batch_dir, {"tax_id": e["tax_id"], "name_th": e["name_th"], "addr_th": e["addr_th"]})
    dataset = json.loads((batch_dir / "oracle_dataset.json").read_text(encoding="utf-8"))

    import uvicorn
    from webapp.build import build_all
    from webapp.config import Settings
    from webapp.engine import InProcessEngine
    from webapp.perception import ReplayPerception

    class Slow(ReplayPerception):
        def extract(self, doc_id):
            time.sleep(1.2)
            return super().extract(doc_id)

    s = Settings(batch_path=batch_dir, data_dir=work / "data", system_a_home=work, workers=4)
    from webapp.batch import BatchSource
    app, svc, _ = build_all(s, engine=InProcessEngine(dataset), perception=Slow(BatchSource(batch_dir)))
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), 0.1).close()
            break
        except OSError:
            time.sleep(0.1)

    from playwright.sync_api import sync_playwright
    exe = os.environ.get("CHROMIUM_PATH") or next(iter(glob.glob("/opt/pw-browsers/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell")), None)
    errors, checks = [], []

    def check(name, cond, detail=""):
        checks.append((name, bool(cond)))
        print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe, args=["--no-sandbox"]) if exe else p.chromium.launch()
        pg = b.new_page(viewport={"width": 1568, "height": 921})
        pg.on("pageerror", lambda x: errors.append(str(x)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and "favicon" not in m.text else None)
        pg.goto(f"http://127.0.0.1:{port}/")
        pg.wait_for_selector("#side > div")

        # 1. every document is listed on the left
        check("1 list shows all documents", pg.locator("#side > div").count() == 7, pg.locator("#side > div").count())
        pg.screenshot(path=str(shots / "1_list.png"))
        # 2. select -> shown in the middle, no boxes yet
        pg.click('#side > div[data-id="102"]')
        check("2 selected document is shown", "#102" in pg.inner_text(".doc > h2") and pg.locator(".imgbox img").count() == 3)
        check("2 no boxes before Process", pg.locator(".bx").count() == 0)
        # 3. Process -> Processing status
        pg.click("#run")
        pg.wait_for_function("document.getElementById('run').textContent.includes('Processing')")
        check("3 Processing is shown", "Processing" in pg.inner_text("#pst") and "processing" in pg.inner_text(".doc > h2")
              and pg.is_disabled("#run"))
        pg.screenshot(path=str(shots / "3_processing.png"))
        # 4. boxes over the document   5. Final + Verify on the right
        pg.wait_for_function("document.querySelectorAll('.bx').length > 0", timeout=20000)
        n_items = sum(len(p_["kept"]) for p_ in svc.view(102)["pages"])
        check("4 one box per OCR item", pg.locator(".bx").count() == n_items, f"{pg.locator('.bx').count()} vs {n_items}")
        txt = pg.inner_text(".doc")
        check("5 Final Result is shown", "Final Result" in txt and "AUTO_PASS" in txt and "SYN-INV-0002" in txt)
        check("5 Verify Result lists 9 rules", all(f"V-0{i}" in txt for i in range(1, 10)) and "Verify Result" in txt)
        pg.screenshot(path=str(shots / "4_5_done_102.png"))
        # a Verify row pins the box it came from
        pg.click('tr[data-ref] >> nth=2')
        check("5 clicking a result row pins its box", pg.locator(".bx.sel").count() == 1 and pg.is_visible("#pin"))
        pg.keyboard.press("Escape")
        # 6. pick another document and process it (a failing one)
        pg.click('#side > div[data-id="103"]')
        check("7 other document starts clean", pg.locator(".bx").count() == 0 and "รอ Process" in pg.inner_text(".doc > h2"))
        pg.click("#run")
        pg.wait_for_function("document.querySelectorAll('.bx').length > 0", timeout=20000)
        t103 = pg.inner_text(".doc")
        check("6 second document processed", "HOLD" in t103 and "E02" in t103 and "SYN-INV-0003" in t103 and "SYN-INV-0002" not in t103)
        pg.screenshot(path=str(shots / "6_done_103_hold.png"))
        # 7. back to the first: its own result is intact
        pg.click('#side > div[data-id="102"]')
        pg.wait_for_function("document.querySelectorAll('.bx').length > 0")
        t102 = pg.inner_text(".doc")
        check("7 results do not mix", "AUTO_PASS" in t102 and "SYN-INV-0002" in t102 and "SYN-INV-0003" not in t102 and "E02" not in t102)
        # process again
        pg.click("#run")
        pg.wait_for_function("document.getElementById('run').textContent.includes('Processing')")
        check("6 re-process clears the boxes while running", pg.locator(".bx").count() == 0)
        pg.wait_for_function("document.querySelectorAll('.bx').length > 0", timeout=20000)
        check("6 re-process finishes as run 2", "run 2" in pg.inner_text(".doc"))
        # concurrent processing of two documents
        pg.click('#side > div[data-id="101"]'); pg.click("#run")
        pg.click('#side > div[data-id="104"]'); pg.click("#run")
        pg.wait_for_function("document.querySelector('#pst').textContent.includes('#101') && document.querySelector('#pst').textContent.includes('#104')")
        check("7 two documents can run at once", True)
        pg.wait_for_function("document.querySelectorAll('.bx').length > 0", timeout=20000)
        pg.click('#side > div[data-id="101"]')
        pg.wait_for_function("document.querySelectorAll('.bx').length > 0", timeout=20000)
        check("7 each of them has its own result", "SYN-INV-0001" in pg.inner_text(".doc") and "SYN-INV-0004" not in pg.inner_text(".doc"))
        # the stand-in page of the document without a JPG
        pg.click('#side > div[data-id="105"]')
        pg.wait_for_timeout(300)
        natural = pg.evaluate("document.querySelector('.imgbox img').complete && document.querySelector('.imgbox img').naturalWidth")
        check("stand-in page is drawn when the JPG is missing", natural and natural > 100, natural)
        # reload: results are still there
        pg.reload()
        pg.wait_for_selector("#side > div")
        check("results survive a page reload", "Process แล้ว 5" in pg.inner_text("#stat") or "Process แล้ว 4" in pg.inner_text("#stat"),
              pg.inner_text("#stat"))
        pg.click('#side > div[data-id="103"]')
        pg.wait_for_function("document.querySelectorAll('.bx').length > 0", timeout=10000)
        check("a stored result is shown after the reload", "SYN-INV-0003" in pg.inner_text(".doc"))
        pg.screenshot(path=str(shots / "7_reloaded_103.png"))
        # filters + search
        pg.select_option("#fs", "error")
        pg.wait_for_timeout(200)
        check("status filter keeps only HOLD documents", pg.locator("#side > div").count() >= 1 and
              all("●" in t for t in pg.locator("#side > div").all_inner_texts()))
        pg.select_option("#fs", "")
        pg.fill("#q", "gasket")
        pg.wait_for_timeout(700)
        ids = [e_.get_attribute("data-id") for e_ in pg.locator("#side > div").all()]
        check("text search finds processed documents", set(ids) <= {"101", "102", "103", "104"} and len(ids) >= 3, ids)
        b.close()

    server.should_exit = True
    check("no JavaScript errors", not errors, errors[:3])
    bad = [n for n, ok in checks if not ok]
    print(f"\n{len(checks) - len(bad)}/{len(checks)} checks passed; screenshots in {shots}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
