"""Settings of the test portal, and the System A loader.

The portal is a *viewer*: it lists real Paperless documents, asks System A to process one, and draws what
System A returns.  It therefore owns almost no configuration:

* which document to open (Paperless tag / limit) and how to draw (DPI, port, persistence);
* where System A lives (``SYSTEM_A_HOME``) and, for ``SYSTEM_A_ENGINE=http``, its URL and API key.

Everything System A needs - the Paperless token, LiteLLM, the Oracle MCP, the models, the mode - is read by
System A itself from ``<SYSTEM_A_HOME>/.env`` through its own ``system_a.envfile.load_env`` (see ``sysa.py``).
A key set in this project's ``.env`` (or in the real environment) still wins, because ``load_env`` lets an
existing environment variable beat the file.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path) -> dict:
    """Minimal ``.env`` reader.  Real environment variables always win (so a deployment can override)."""
    out: dict = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.split(" #", 1)[0].strip().strip('"').strip("'")
        out[k.strip()] = v
        os.environ.setdefault(k.strip(), v)
    return out


def _bool(v: Optional[str], default: bool) -> bool:
    return default if v is None or v == "" else v.strip().lower() in ("1", "true", "yes", "on")


def _path(v: Optional[str]) -> Optional[Path]:
    return Path(v).expanduser() if v else None


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8090
    data_dir: Path = ROOT / "data"              # view + payload of what was processed (restart-proof)
    workers: int = 4                            # documents processed at the same time
    render_dpi: int = 150                       # DPI the page images shown under the boxes are rendered at
    persist_results: bool = True                # false: nothing is written to disk (the browser holds the cases)

    system_a_home: Optional[Path] = None        # System A project root (the folder that has src/ and config/)
    engine: str = "inprocess"                   # inprocess (run process_pdf here) | http (validate on a server)
    system_a_url: str = "http://127.0.0.1:8080"
    system_a_key: str = ""
    http_timeout_s: float = 300.0               # how long to wait for a remote validation job
    mode: str = "production"                    # production (real Oracle + real VLM) | sandbox (simulators)
    quick: bool = False                         # pass --quick to System A (no table/crop reads: faster, weaker)

    paperless_tag: str = "invoice"              # tag name that selects the documents to show
    paperless_limit: int = 200                  # how many documents to pull into the left panel

    @classmethod
    def from_env(cls, env_file: Optional[Path] = None) -> "Settings":
        load_dotenv(env_file or ROOT / ".env")
        e = os.environ.get
        s = cls(
            host=e("WEBAPP_HOST", "127.0.0.1"), port=int(e("WEBAPP_PORT", "8090")),
            data_dir=_path(e("WEBAPP_DATA_DIR")) or ROOT / "data",
            workers=int(e("WEBAPP_WORKERS", "4")),
            render_dpi=int(e("WEBAPP_RENDER_DPI", "150")),
            persist_results=_bool(e("WEBAPP_PERSIST"), True),
            system_a_home=_path(e("SYSTEM_A_HOME")),
            engine=e("SYSTEM_A_ENGINE", "inprocess").strip().lower(),
            system_a_url=e("SYSTEM_A_URL", "http://127.0.0.1:8080").rstrip("/"),
            system_a_key=e("SYSTEM_A_API_KEY", ""),
            http_timeout_s=float(e("SYSTEM_A_HTTP_TIMEOUT", "300")),
            mode=e("SYSTEM_A_MODE", "production").strip().lower(),
            quick=_bool(e("WEBAPP_QUICK"), False),
            paperless_tag=e("PAPERLESS_TAG", "invoice").strip(),
            paperless_limit=int(e("PAPERLESS_LIMIT", "200")),
        )
        s.validate()
        return s

    def validate(self) -> None:
        if self.engine not in ("inprocess", "http"):
            raise ValueError(f"SYSTEM_A_ENGINE must be inprocess|http, got {self.engine!r}")
        if self.mode not in ("production", "sandbox"):
            raise ValueError(f"SYSTEM_A_MODE must be production|sandbox, got {self.mode!r}")
        if self.workers < 1:
            raise ValueError("WEBAPP_WORKERS must be >= 1")
        if not 72 <= self.render_dpi <= 400:
            raise ValueError(f"WEBAPP_RENDER_DPI must be 72-400, got {self.render_dpi}")
        if self.paperless_limit < 1:
            raise ValueError("PAPERLESS_LIMIT must be >= 1")
        if not self.paperless_tag:
            raise ValueError("PAPERLESS_TAG is empty: the document list would have no filter")


class SystemAUnavailable(RuntimeError):
    """System A cannot be imported (SYSTEM_A_HOME missing or wrong)."""


def ensure_system_a(home: Optional[Path]) -> Path:
    """Put System A on ``sys.path`` and return its project root (the folder holding ``src/`` and ``config/``).

    Both the project root and ``<root>/src`` are added: ``src`` holds the ``system_a`` package, and the root
    holds its standalone entrypoint ``process_pdf.py`` - the script this portal drives.
    """
    try:                                              # already importable (installed / path preset)
        import system_a  # noqa: F401
        pkg = Path(system_a.__file__).resolve().parents[1]
        root = pkg.parent if pkg.name == "src" else pkg        # <root>/src/system_a -> <root>
        if str(root) not in sys.path:                            # so its entrypoint process_pdf.py is importable
            sys.path.insert(0, str(root))
        return root
    except ImportError:
        pass
    candidates: list[Path] = []
    if home is not None:
        home = Path(home)
        candidates.extend([home / "src", home, home.parent / "src", home.parent])
    if (ROOT / "system_a").is_dir():                  # System A vendored next to the portal (not the norm)
        candidates.append(ROOT)
    try:                                              # test-portal hosted inside system-a-sandbox/src/
        candidates.extend([ROOT.parents[1] / "src", ROOT.parents[1]])
    except Exception:
        pass

    for cand in candidates:
        if (cand / "system_a" / "__init__.py").is_file():
            root = cand.parent if cand.name == "src" else cand
            for p in {str(cand), str(root)}:
                if p not in sys.path:
                    sys.path.insert(0, p)
            import system_a  # noqa: F401
            return root

    if home is None:
        raise SystemAUnavailable("SYSTEM_A_HOME is not set: point it at the System A project folder "
                                 "(the one that contains src/system_a, config/ and process_pdf.py)")
    raise SystemAUnavailable(f"no system_a package under {home} (looked in {home / 'src'} and {home})")
