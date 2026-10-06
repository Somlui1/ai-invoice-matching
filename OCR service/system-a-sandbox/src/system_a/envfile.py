"""Minimal ``.env`` loader used by the batch/report scripts.

The library code keeps reading secrets from ``os.environ`` only (Decision Log §7.3);
this helper exists so that the CLI scripts can run from a checkout without an external
process manager.  Values already present in the environment win over the file.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV = ROOT / ".env"

REQUIRED_KEYS = ("LITELLM_URL", "LITELLM_API_KEY", "MODEL_VISION", "PAPERLESS_BASE_URL",
                 "PAPERLESS_API_TOKEN", "ORACLE_MCP_URL")


def read_env_file(path: str | Path | None = None) -> dict[str, str]:
    p = Path(path or DEFAULT_ENV)
    out: dict[str, str] = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_env(path: str | Path | None = None, *, apply: bool = True) -> dict[str, str]:
    """.env values, overridden by real environment variables; optionally exported to os.environ."""
    merged = read_env_file(path)
    for k, v in merged.items():
        if os.environ.get(k):
            merged[k] = os.environ[k]
        elif apply:
            os.environ[k] = v
    return merged


def missing_keys(cfg: dict[str, str], keys: tuple[str, ...] = REQUIRED_KEYS) -> list[str]:
    return [k for k in keys if not cfg.get(k)]
