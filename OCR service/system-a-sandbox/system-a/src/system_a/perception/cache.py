"""Perception cache — re-running a batch must not re-spend GPU minutes on the same bytes.

Key = sha256(file) + model + prompt_version + the perception options that change the answer
(DPI, coordinate mode, which passes ran).  A stored result is only reused when its recorded
``file_sha256`` still matches, so a stale or mismatched entry can never be served for another file.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from ..domain.contracts import ExtractionResult

CACHE_VERSION = "1"


def cache_key(*, file_sha256: str, model: str, prompt_version: str, options: dict) -> str:
    payload = json.dumps({"v": CACHE_VERSION, "sha": file_sha256, "model": model,
                          "prompts": prompt_version, "opts": options}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PerceptionCache:
    def __init__(self, root: str | Path | None):
        self.root = Path(root) if root else None
        self.hits = 0
        self.misses = 0
        self.rejected = 0            # entries that failed the sha/shape check (never served)

    @property
    def enabled(self) -> bool:
        return self.root is not None

    def path_for(self, key: str) -> Optional[Path]:
        return (self.root / f"{key}.json") if self.enabled else None

    def load(self, key: str, expect_sha: str) -> Optional[ExtractionResult]:
        p = self.path_for(key)
        if p is None or not p.exists():
            self.misses += 1
            return None
        try:
            ext = ExtractionResult.model_validate_json(p.read_text(encoding="utf-8"))
        except Exception:
            self.rejected += 1
            self.misses += 1
            return None
        if ext.file_sha256 != expect_sha:
            self.rejected += 1
            self.misses += 1
            return None
        self.hits += 1
        return ext

    def save(self, key: str, ext: ExtractionResult) -> Optional[Path]:
        p = self.path_for(key)
        if p is None:
            return None
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(ext.model_dump_json(), encoding="utf-8")
        tmp.replace(p)                                # atomic: a killed run cannot leave half a cache
        return p

    def stats(self) -> dict:
        return {"enabled": self.enabled, "root": str(self.root) if self.root else None,
                "hits": self.hits, "misses": self.misses, "rejected": self.rejected}
