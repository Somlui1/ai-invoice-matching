"""Per-document persistence: ``<data_dir>/results/doc_<id>/{state,view,payload,extraction}.json``.

Every file is written atomically (temp file + replace), and a document only ever touches its own folder, so two
documents can never share or overwrite each other's result.  ``MemoryStore`` is the same contract without disk.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Optional

PARTS = ("state", "view", "payload", "extraction")


class ResultStore:
    def __init__(self, root: Path):
        self.root = Path(root) / "results"
        self.root.mkdir(parents=True, exist_ok=True)

    def folder(self, doc_id: int) -> Path:
        return self.root / f"doc_{int(doc_id)}"

    def _file(self, doc_id: int, part: str) -> Path:
        if part not in PARTS:
            raise ValueError(part)
        return self.folder(doc_id) / f"{part}.json"

    def save(self, doc_id: int, part: str, data) -> None:
        f = self._file(doc_id, part)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=None, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, f)

    def load(self, doc_id: int, part: str) -> Optional[dict]:
        f = self._file(doc_id, part)
        if not f.is_file():
            return None
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None                                   # a damaged file is treated as absent, never half-read

    def clear(self, doc_id: int, keep_state: bool = True) -> None:
        for part in PARTS:
            if keep_state and part == "state":
                continue
            self._file(doc_id, part).unlink(missing_ok=True)

    def remove(self, doc_id: int) -> None:
        shutil.rmtree(self.folder(doc_id), ignore_errors=True)

    def ids(self) -> list:
        return sorted(int(p.name[4:]) for p in self.root.glob("doc_*") if p.name[4:].isdigit())


class MemoryStore:
    """Same interface, nothing on disk: the processed result of a document lives in this process only.

    Used when the browser is the system of record for cases (``WEBAPP_PERSIST=false``): the server keeps what the
    running page needs while it polls, and the browser keeps the case itself (``localStorage``).  A restart
    therefore leaves no result behind on the server.
    """

    def __init__(self, root=None):
        self.root = None
        self._d: dict = {}

    def save(self, doc_id: int, part: str, data) -> None:
        if part not in PARTS:
            raise ValueError(part)
        self._d.setdefault(int(doc_id), {})[part] = data

    def load(self, doc_id: int, part: str):
        return self._d.get(int(doc_id), {}).get(part)

    def clear(self, doc_id: int, keep_state: bool = True) -> None:
        keep = self._d.get(int(doc_id), {}).get("state") if keep_state else None
        self._d[int(doc_id)] = {"state": keep} if keep is not None else {}

    def remove(self, doc_id: int) -> None:
        self._d.pop(int(doc_id), None)

    def ids(self) -> list:
        return sorted(self._d)

    def folder(self, doc_id: int):
        return None

