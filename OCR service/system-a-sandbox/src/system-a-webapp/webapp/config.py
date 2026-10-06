"""Settings (environment / .env) and the System A loader.

The web application lives in its own folder and uses System A as a *library*: the System A project is
located with ``SYSTEM_A_HOME`` and put on ``sys.path``.  Nothing of System A is copied into this project.
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
    batch_path: Optional[Path] = None           # report.html, or the folder that holds it
    data_dir: Path = ROOT / "data"              # per-document results (survive a restart)
    engine: str = "inprocess"                   # inprocess | http
    system_a_home: Optional[Path] = None        # project root of System A (folder that has src/ and config/)
    system_a_url: str = "http://127.0.0.1:8080"
    system_a_key: str = ""
    http_timeout_s: float = 300.0
    perception: str = "replay"                  # replay (use the OCR items of the batch) | live (run VisionPipeline)
    pdf_dir: Optional[Path] = None              # live: where doc PDFs are (doc_<id>.pdf or <title>.pdf)
    replay_confidence: float = 0.97             # replay only: confidence when the batch has none
    replay_assume_agreement: bool = True        # replay only: a single OCR read counts as agreed
    oracle_dataset: Optional[Path] = None       # in-process sandbox only
    workers: int = 4
    doc_source: str = "batch"                   # batch (a report folder) | paperless (the DMS itself)
    paperless_url: str = ""                     # PAPERLESS_BASE_URL, e.g. http://dms.aapico.com
    paperless_token: str = ""                   # PAPERLESS_API_TOKEN (never committed: it lives in .env)
    paperless_limit: int = 200                  # how many documents to pull into the left panel
    paperless_tags: str = ""                    # comma separated tag names to filter the list (optional)
    render_dpi: int = 150                       # DPI the pages are rendered at for the overlay
    persist_results: bool = True                # false: results are never written to disk (browser holds the cases)
    system_a_env: bool = True                   # fill missing System A settings from <SYSTEM_A_HOME>/.env

    @classmethod
    def from_env(cls, env_file: Optional[Path] = None) -> "Settings":
        load_dotenv(env_file or ROOT / ".env")
        e = os.environ.get
        s = cls(
            host=e("WEBAPP_HOST", "127.0.0.1"), port=int(e("WEBAPP_PORT", "8090")),
            batch_path=_path(e("BATCH_REPORT")),
            data_dir=_path(e("WEBAPP_DATA_DIR")) or ROOT / "data",
            engine=e("SYSTEM_A_ENGINE", "inprocess").strip().lower(),
            system_a_home=_path(e("SYSTEM_A_HOME")),
            system_a_url=e("SYSTEM_A_URL", "http://127.0.0.1:8080").rstrip("/"),
            system_a_key=e("SYSTEM_A_API_KEY", ""),
            http_timeout_s=float(e("SYSTEM_A_HTTP_TIMEOUT", "300")),
            perception=e("PERCEPTION", "replay").strip().lower(),
            pdf_dir=_path(e("PDF_DIR")),
            replay_confidence=float(e("REPLAY_CONFIDENCE", "0.97")),
            replay_assume_agreement=_bool(e("REPLAY_ASSUME_AGREEMENT"), True),
            oracle_dataset=_path(e("WEBAPP_ORACLE_DATASET")),
            workers=int(e("WEBAPP_WORKERS", "4")),
            doc_source=e("DOC_SOURCE", "batch").strip().lower(),
            paperless_url=e("PAPERLESS_BASE_URL", "").strip().rstrip("/"),
            paperless_token=e("PAPERLESS_API_TOKEN", "").strip(),
            paperless_limit=int(e("PAPERLESS_LIMIT", "200")),
            paperless_tags=e("PAPERLESS_TAGS", ""),
            render_dpi=int(e("WEBAPP_RENDER_DPI", "150")),
            persist_results=_bool(e("WEBAPP_PERSIST"), True),
            system_a_env=_bool(e("USE_SYSTEM_A_ENV"), True),
        )
        s.validate()
        return s

    def validate(self) -> None:
        if self.engine not in ("inprocess", "http"):
            raise ValueError(f"SYSTEM_A_ENGINE must be inprocess|http, got {self.engine!r}")
        if self.perception not in ("replay", "live"):
            raise ValueError(f"PERCEPTION must be replay|live, got {self.perception!r}")
        if self.workers < 1:
            raise ValueError("WEBAPP_WORKERS must be >= 1")
        if self.doc_source not in ("batch", "paperless"):
            raise ValueError(f"DOC_SOURCE must be batch|paperless, got {self.doc_source!r}")
        if self.doc_source == "batch" and self.batch_path is None:
            raise ValueError("BATCH_REPORT is not set: point it at report.html (or the folder that contains it)")
        if self.doc_source == "paperless":
            if not self.paperless_url.startswith(("http://", "https://")):
                raise ValueError("DOC_SOURCE=paperless needs PAPERLESS_BASE_URL (http://...)")
            if not self.paperless_token:
                raise ValueError("DOC_SOURCE=paperless needs PAPERLESS_API_TOKEN")
            if self.perception != "live":
                raise ValueError("DOC_SOURCE=paperless needs PERCEPTION=live: the documents are read here and now, "
                                 "there is no batch OCR to replay")
        if not 72 <= self.render_dpi <= 400:
            raise ValueError(f"WEBAPP_RENDER_DPI must be 72-400, got {self.render_dpi}")
        if self.paperless_limit < 1:
            raise ValueError("PAPERLESS_LIMIT must be >= 1")


class SystemAUnavailable(RuntimeError):
    """System A cannot be imported (SYSTEM_A_HOME missing or wrong)."""


def ensure_system_a(home: Optional[Path]) -> Path:
    """Put System A on ``sys.path`` and return the directory that contains the ``system_a`` package."""
    try:                                              # already importable (installed / path preset)
        import system_a  # noqa: F401
        return Path(system_a.__file__).resolve().parents[1]
    except ImportError:
        pass
    if home is None:
        raise SystemAUnavailable("SYSTEM_A_HOME is not set: point it at the System A project folder "
                                 "(the one that contains src/system_a and config/)")
    home = Path(home)
    for cand in (home / "src", home):
        if (cand / "system_a" / "__init__.py").is_file():
            if str(cand) not in sys.path:
                sys.path.insert(0, str(cand))
            import system_a  # noqa: F401
            return cand
    raise SystemAUnavailable(f"no system_a package under {home} (looked in {home / 'src'} and {home})")
