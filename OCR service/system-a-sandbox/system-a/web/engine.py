"""Engine bridge — the only place in the portal that talks to System A core.

The portal is an *external consumer* of the CLI entrypoint.  It runs
``system-a/process_pdf.py`` as a subprocess (never imports the domain modules) so that

* the CLI stays the single supported entrypoint and keeps working untouched,
* each verification gets its own process, its own ``sys.stdout`` and its own ``load_standard()``
  snapshot — no cross-request bleed through module-level caches,
* the engine's own progress lines become the portal's progress events, and
* a hung or cancelled run can be killed without taking the portal down.

Progress lines come from the CLI's own prints, e.g.
``[1/3] Running Perception (OCR + Layout + BBoxes)...``.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
SYSTEM_A_DIR = WEB_DIR.parent                       # .../system-a
PROCESS_PDF = SYSTEM_A_DIR / "process_pdf.py"
RESULTS_DIR = Path(os.getenv("WEB_RESULTS_DIR", str(WEB_DIR / "results")))
DOWNLOADS_DIR = Path(os.getenv("WEB_DOWNLOADS_DIR", str(SYSTEM_A_DIR / ".cache" / "downloads")))
RUN_LOG = RESULTS_DIR / "runs.jsonl"

MAX_CONCURRENT = int(os.getenv("WEB_MAX_CONCURRENT", "2"))
RUN_TIMEOUT_S = float(os.getenv("WEB_RUN_TIMEOUT_SECONDS", "1800"))


def _imports_engine_deps(py: Path) -> bool:
    """Can this interpreter run the engine?  Checked by importing three of its real dependencies."""
    try:
        r = subprocess.run([str(py), "-c", "import yaml, pydantic, pymupdf"],
                           capture_output=True, timeout=90)
        return r.returncode == 0
    except Exception:
        return False


def _find_engine_python() -> Path:
    """Interpreter for the engine subprocess.

    Order: explicit WEB_ENGINE_PYTHON, then the portal's own interpreter, then any project venv found
    by walking up from system-a/.  A candidate is only chosen when it can actually import the engine's
    dependencies — the machine has more than one Python here and the wrong one dies on ``import yaml``.
    """
    override = os.getenv("WEB_ENGINE_PYTHON")
    if override and Path(override).exists():
        return Path(override)
    rel = ("Scripts/python.exe", "bin/python") if os.name == "nt" else ("bin/python", "bin/python3")
    cands: list[Path] = [Path(sys.executable)]
    for base in (SYSTEM_A_DIR, *SYSTEM_A_DIR.parents):
        for env_name in (".venv", "venv"):
            for r in rel:
                cands.append(base / env_name / r)
    for c in cands:
        if c.exists() and _imports_engine_deps(c):
            return c
    return Path(sys.executable)


ENGINE_PY = _find_engine_python()


# --------------------------------------------------------------------------- progress mapping
# (substring of a CLI line) -> portal step id.  Ordered; first match wins.
STEP_MARKERS: tuple[tuple[str, str, str], ...] = (
    ("Fetching DMS-", "download", "Downloading the original file from Paperless-ngx"),
    ("Processing '", "start", "Loading document"),
    ("[1/3] Running Perception", "perception", "Perception — Qwen vision read of every page (OCR, layout, bounding boxes)"),
    ("Reusing cached OCR perception", "perception_cached", "Perception cache hit — reusing a stored extraction"),
    ("[2/3] Querying Oracle EBS", "oracle", "Oracle EBS lookup (RCV-V01) and rules V-01..V-09"),
    ("[3/3] Assembling final recommendation", "assemble", "Assembling the Contract 3.0 result"),
    ("AIVA System A — Document Verification Result", "summary", "Building the verdict card"),
)


def parse_step(line: str) -> tuple[str, str] | None:
    """Map one CLI output line onto (step_id, label), or None when it is not a step line."""
    for needle, step, label in STEP_MARKERS:
        if needle in line:
            return step, label
    return None


@dataclass
class EngineRun:
    """One engine execution: its log, its result file and a thread-safe event feed."""

    key: str                                   # DMS-20 / UPLOAD-<hash>
    mode: str
    quick: bool
    label: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    exit_code: int | None = None
    error: str = ""
    log: list[str] = field(default_factory=list)
    result_path: Path | None = None
    _events: "queue.Queue[dict | None]" = field(default_factory=queue.Queue, repr=False)
    _proc: subprocess.Popen | None = field(default=None, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)

    # -- lifecycle ------------------------------------------------------------
    def start(self, *, dms_id: int | None, pdf_path: Path | None) -> None:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        out = RESULTS_DIR / f"{self.key}.json"
        cmd = [str(ENGINE_PY), str(PROCESS_PDF), "--mode", self.mode, "-o", str(out)]
        if dms_id is not None:
            cmd += ["--dms-id", str(dms_id)]
        else:
            cmd += [str(pdf_path)]
        if self.quick:
            cmd.append("--quick")

        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"          # Thai text on a cp874 Windows console
        self._proc = subprocess.Popen(
            cmd, cwd=str(SYSTEM_A_DIR), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        self._thread = threading.Thread(target=self._pump, args=(out,), daemon=True)
        self._thread.start()

    def _pump(self, out: Path) -> None:
        proc = self._proc
        assert proc and proc.stdout is not None
        try:
            for raw in proc.stdout:
                line = raw.rstrip("\n")
                if not line.strip():
                    continue
                self.log.append(line)
                self._emit({"type": "log", "line": line, "t": round(time.time() - self.started_at, 1)})
                step = parse_step(line)
                if step:
                    self._emit({"type": "step", "step": step[0], "label": step[1]})
        except Exception as e:                                     # broken pipe / killed process
            self.error = f"{type(e).__name__}: {e}"
        code = proc.wait()
        self.exit_code = code
        self.finished_at = time.time()
        if out.exists():
            self.result_path = out
        if code != 0:
            tail = " · ".join(self.log[-6:])
            self.error = self.error or f"engine exited with code {code}: {tail}"
        self._emit({"type": "done", "exit_code": code,
                    "elapsed_s": round((self.finished_at - self.started_at), 1),
                    "ok": bool(self.result_path) and code == 0,
                    "error": self.error or None})
        self._emit(None)                                          # close the feed

    def _emit(self, event: dict | None) -> None:
        self._events.put(event)

    # -- consumers ------------------------------------------------------------
    def events(self):
        """Yield events until the run finishes (safe for one consumer at a time)."""
        while True:
            ev = self._events.get()
            if ev is None:
                return
            yield ev

    def wait(self, timeout: float | None = None) -> dict:
        """Blocking variant for the non-streaming endpoint; returns the final JSON."""
        deadline = time.time() + (timeout or RUN_TIMEOUT_S)
        for ev in self.events():
            if ev.get("type") == "done":
                break
            if time.time() > deadline:
                self.cancel()
                raise TimeoutError(f"engine run exceeded {timeout or RUN_TIMEOUT_S}s")
        return self.result_json()

    def result_json(self) -> dict:
        if not self.result_path:
            raise RuntimeError(self.error or "the engine produced no result file")
        return json.loads(self.result_path.read_text(encoding="utf-8"))

    def cancel(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def summary(self) -> dict:
        rec = {}
        if self.result_path:
            try:
                rec = (json.loads(self.result_path.read_text(encoding="utf-8")) or {}).get("recommendation", {})
            except Exception:
                rec = {}
        return {"key": self.key, "mode": self.mode, "quick": self.quick, "label": self.label,
                "running": self.alive, "exit_code": self.exit_code, "error": self.error or None,
                "elapsed_s": round(((self.finished_at or time.time()) - self.started_at), 1),
                "recommendation": rec.get("value"), "max_severity": rec.get("max_severity"),
                "exception_codes": rec.get("exception_codes") or []}


# --------------------------------------------------------------------------- registry
class RunRegistry:
    """Tracks in-flight and finished runs; caps concurrency and refuses duplicate work."""

    def __init__(self, max_concurrent: int = MAX_CONCURRENT) -> None:
        self.max_concurrent = max_concurrent
        self._runs: dict[str, EngineRun] = {}
        self._lock = threading.Lock()

    def running_count(self) -> int:
        return sum(1 for r in self._runs.values() if r.alive)

    def get(self, key: str) -> EngineRun | None:
        return self._runs.get(key)

    def start(self, *, key: str, dms_id: int | None = None, pdf_path: Path | None = None,
              mode: str = "production", quick: bool = False, label: str = "") -> EngineRun:
        with self._lock:
            existing = self._runs.get(key)
            if existing and existing.alive:
                raise BusyError(f"{key} is already being verified")
            if self.running_count() >= self.max_concurrent:
                raise BusyError(f"portal is at its concurrency limit ({self.max_concurrent}); try again shortly")
            run = EngineRun(key=key, mode=mode, quick=quick, label=label or key)
            self._runs[key] = run
        run.start(dms_id=dms_id, pdf_path=pdf_path)
        return run

    def recent(self, limit: int = 50) -> list[dict]:
        rows = [r.summary() for r in self._runs.values()]
        rows.sort(key=lambda r: r["elapsed_s"], reverse=True)
        return rows[:limit]


class BusyError(RuntimeError):
    """Another verification for the same document, or the concurrency cap, blocks this request."""


REGISTRY = RunRegistry()


# --------------------------------------------------------------------------- result store
def stored_results() -> list[dict]:
    """Verdict index of every result the portal has stored (drives the gallery badges)."""
    out: list[dict] = []
    if not RESULTS_DIR.exists():
        return out
    for f in sorted(RESULTS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        req = data.get("request") or {}
        rec = data.get("recommendation") or {}
        pkg = data.get("package") or {}
        fields = data.get("normalized_fields") or {}
        out.append({
            "key": f.stem,
            "dms_doc_id": req.get("dms_doc_id") or f.stem,
            "doc_id": _doc_id_of(req.get("dms_doc_id") or f.stem),
            "validation_id": req.get("validation_id"),
            "recommendation": rec.get("value"),
            "max_severity": rec.get("max_severity"),
            "exception_codes": rec.get("exception_codes") or [],
            "invoice_num": fields.get("invoice_num"),
            "supplier_name": fields.get("supplier_name"),
            "po_number": fields.get("po_number"),
            "page_count": pkg.get("page_count"),
            "standard": (data.get("versions") or {}).get("standard"),
            "completed_at": req.get("completed_at"),
            "size_bytes": f.stat().st_size,
        })
    out.sort(key=lambda r: r.get("completed_at") or "", reverse=True)
    return out


def stored_result(key: str) -> dict | None:
    f = RESULTS_DIR / f"{_safe_key(key)}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def log_run(run: EngineRun) -> None:
    """Append one line to results/runs.jsonl (audit trail of portal-initiated runs)."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    row = run.summary()
    row["at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with RUN_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _safe_key(key: str) -> str:
    keep = [c for c in str(key) if c.isalnum() or c in "-_."]
    return "".join(keep)[:120] or "result"


def _doc_id_of(label: str) -> int | None:
    """Accept both shapes the engine has used for ``request.dms_doc_id`` ('DMS-20' and '20')."""
    s = str(label).strip()
    if s.startswith("DMS-"):
        s = s[4:]
    return int(s) if s.isdigit() else None


def upload_key(original_name: str, digest: str) -> str:
    stem = Path(original_name or "upload").stem
    return _safe_key(f"UP-{stem}-{digest[:8]}")


def save_upload(data: bytes, original_name: str, digest: str) -> Path:
    """Store an uploaded file next to the Paperless downloads so the viewer can find it again."""
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(original_name or "upload.pdf").suffix or ".pdf"
    path = DOWNLOADS_DIR / f"{upload_key(original_name, digest)}{suffix}"
    path.write_bytes(data)
    return path


def find_upload(key: str) -> Path | None:
    for f in DOWNLOADS_DIR.glob(f"{_safe_key(key)}*"):
        return f
    return None


def free_disk_bytes(path: Path = RESULTS_DIR) -> int:
    try:
        return shutil.disk_usage(str(path)).free
    except OSError:
        return -1
