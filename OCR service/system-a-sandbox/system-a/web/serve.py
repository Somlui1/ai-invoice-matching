"""Launcher for the System A web testing portal.

    python web/serve.py                # http://127.0.0.1:8080
    python web/serve.py --port 8090 --no-browser

Reads ``system-a/.env`` (through ``system_a.envfile``) so the portal uses exactly the same
Paperless / LiteLLM / Oracle configuration as ``process_pdf.py``.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
for p in (WEB_DIR, WEB_DIR.parent, WEB_DIR.parent / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import uvicorn                                                      # noqa: E402
from app import app                                                 # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="AIVA System A web testing portal")
    ap.add_argument("--host", default=os.getenv("WEB_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("WEB_PORT", "8080")))
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    ap.add_argument("--reload", action="store_true", help="dev reload (portal code only)")
    args = ap.parse_args()

    url = f"http://{args.host}:{args.port}/"
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"\n  AIVA System A — Web Testing Portal\n  {url}\n  (Ctrl+C to stop)\n", flush=True)
    try:
        uvicorn.run("app:app" if args.reload else app,
                    host=args.host, port=args.port, log_level="info",
                    reload=args.reload, app_dir=str(WEB_DIR) if args.reload else None,
                    ws="none")          # the portal is HTTP + streamed responses only
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
