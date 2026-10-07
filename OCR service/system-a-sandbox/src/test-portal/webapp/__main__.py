"""``python -m webapp check`` | ``python -m webapp serve``."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .config import Settings, SystemAUnavailable


def cmd_check(s: Settings) -> int:
    """Show what the portal will drive: System A itself, then the document list.  Run this before ``serve``."""
    from . import sysa
    from .build import build_catalog
    from .catalog import CatalogError

    try:
        sa = sysa.init(s)
    except Exception as e:                                            # an unimportable System A is the whole answer
        print(f"System A cannot be loaded: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    h = sa.health()
    print(json.dumps({"system_a": {"home": h["home"], "standard": h["standard"], "ruleset": h["ruleset"],
                                   "mode": h["mode"], "ai_mode": h["ai_mode"], "vision_model": h["vision_model"],
                                   "oracle_backend": h["oracle_backend"], "engine": s.engine},
                      "process_pdf": bool(sa.process_pdf)}, ensure_ascii=False, indent=2))
    if s.engine == "http":
        print(f"note: engine=http - the reading happens here, the validation runs on {s.system_a_url} "
              f"(start it with: python -m system_a.cli serve --port {s.system_a_url.rsplit(':', 1)[-1]})",
              file=sys.stderr)
    try:
        cat = build_catalog(s, sa)
    except CatalogError as e:
        print(f"cannot list the documents: {e}", file=sys.stderr)
        return 2
    print(json.dumps({"source": {"kind": cat.kind, **cat.stats(), "health": cat.health()}}, ensure_ascii=False, indent=2))
    for t in cat.unmatched_tags:
        print(f"note: no tag named {t!r} in the DMS, so that filter does nothing", file=sys.stderr)
    if cat.list_error:
        print(f"note: {cat.list_error}", file=sys.stderr)
    print("note: Process runs System A's own process_pdf on the real file - one VLM call per page plus the real "
          "Oracle.  An error System A raises is shown as it is, with no fallback.", file=sys.stderr)
    return 0


def cmd_serve(s: Settings) -> int:
    import uvicorn

    from .build import build_all
    from .catalog import CatalogError

    try:
        app, _service, _catalog = build_all(s)
    except (CatalogError, SystemAUnavailable) as e:
        print(f"cannot start: {e}", file=sys.stderr)
        return 2
    print(f"AIVA System A test portal: http://{s.host}:{s.port}/   (engine={s.engine}, mode={s.mode})")
    # ws="none": this application is plain HTTP + polling (the screen never opens a WebSocket), and uvicorn's
    # default "auto" imports the `websockets` package at startup - which stops the whole application when the
    # interpreter it runs under has a `websockets` build that does not match it.  See agent/errors-and-solutions.md.
    uvicorn.run(app, host=s.host, port=s.port, log_level="info", ws="none")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser("webapp", description="Test portal for System A (Paperless -> result 3.0)")
    p.add_argument("cmd", choices=("check", "serve"), nargs="?", default="serve")
    p.add_argument("--env", default=None, help="read this .env instead of the one next to the package")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        s = Settings.from_env(Path(a.env) if a.env else None)
    except ValueError as e:
        print(f"configuration is wrong: {e}", file=sys.stderr)
        return 2
    return cmd_check(s) if a.cmd == "check" else cmd_serve(s)


if __name__ == "__main__":
    raise SystemExit(main())
