"""``python -m webapp serve`` | ``python -m webapp check``."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .batch import BatchError, BatchSource
from .config import Settings, SystemAUnavailable


def cmd_check(s: Settings) -> int:
    """Read the report and show what the application will see - run this first on a new batch."""
    if s.doc_source == "paperless":
        from .build import build_source
        from .config import ensure_system_a
        try:
            ensure_system_a(s.system_a_home)            # build_source imports the Paperless reader of System A
            src = build_source(s)                       # one real list call + one health call
        except (BatchError, SystemAUnavailable) as e:
            print(f"cannot list the documents: {e}", file=sys.stderr)
            return 2
        print(json.dumps({"source": "paperless", **src.stats(), "health": src.health()}, ensure_ascii=False, indent=2))
        for t in src.unmatched_tags:
            print(f"note: no tag named {t!r} in the DMS, so that filter does nothing", file=sys.stderr)
        if src.list_error:
            print(f"note: {src.list_error}", file=sys.stderr)
        print("note: opening a document downloads its file once; Process runs System A on it (a VLM call per page)."
              " Results are kept in the browser only when WEBAPP_PERSIST=false", file=sys.stderr)
        return 0
    if s.batch_path is None:
        print("BATCH_REPORT is not set", file=sys.stderr)
        return 2
    try:
        b = BatchSource(s.batch_path)
    except BatchError as e:
        print(f"report not usable: {e}", file=sys.stderr)
        return 2
    print(json.dumps({"report": str(b.report_path), **b.stats()}, ensure_ascii=False, indent=2))
    bad = b.stats()["items_without_bbox"]
    if bad:
        print(f"note: {bad} item(s) have no bbox_norm; they are listed but get no box", file=sys.stderr)
    if b.stats()["images_missing"]:
        print("note: some page images are missing; a stand-in page is drawn from the OCR text", file=sys.stderr)
    return 0


def cmd_serve(s: Settings) -> int:
    import uvicorn

    from .build import build_all
    try:
        app, _service, _batch = build_all(s)
    except (BatchError, SystemAUnavailable) as e:
        print(f"cannot start: {e}", file=sys.stderr)
        return 2
    print(f"AIVA System A test application: http://{s.host}:{s.port}/   (engine={s.engine}, perception={s.perception})")
    uvicorn.run(app, host=s.host, port=s.port, log_level="info")
    return 0


def cmd_demo(s: Settings, out: str) -> int:
    """Write a synthetic sample batch (addressed to the buyer of the System A Standard in use)."""
    from .config import ensure_system_a
    from .demo import demo
    try:
        ensure_system_a(s.system_a_home)
    except SystemAUnavailable as e:
        print(f"cannot create the demo: {e}", file=sys.stderr)
        return 2
    cfg = demo(Path(out))
    print(f"sample batch written to {out}\nput this in .env to open it:")
    for k, v in cfg.items():
        print(f"{k}={v}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser("webapp")
    ap.add_argument("cmd", choices=("serve", "check", "demo"))
    ap.add_argument("--env", help="path of a .env file (default: ./.env)")
    ap.add_argument("--out", default="sample_batch", help="demo: folder to write the sample batch to")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    s = Settings.from_env(Path(a.env) if a.env else None)
    if a.cmd == "demo":
        return cmd_demo(s, a.out)
    return {"serve": cmd_serve, "check": cmd_check}[a.cmd](s)


if __name__ == "__main__":
    sys.exit(main())
