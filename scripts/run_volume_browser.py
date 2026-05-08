r"""
run_volume_browser.py
======================
Spin up the Volume Browser (FTP-style file manager) locally — pointed at ANY
folder on your machine. Great for testing the same UI you get on Railway,
or just using it as a local file browser / mini FTP server.

Usage (PowerShell):

    # Browse a specific folder on your laptop
    $env:VOLUME_PATH = "C:\Users\SohaibAli\Documents"
    $env:VOLUME_DEBUG_KEY = "letmein"
    python scripts\run_volume_browser.py

    # Then open:  http://localhost:8765/volume/ui

If you don't set VOLUME_PATH it defaults to ./_volume_local (auto-created).
If you don't set VOLUME_DEBUG_KEY it defaults to "dev".
"""
from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path

# Make the project root importable regardless of CWD
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Volume Browser locally.")
    parser.add_argument("--path", default=None,
                        help="Directory to expose (defaults to env VOLUME_PATH or ./_volume_local).")
    parser.add_argument("--key", default=None,
                        help="Auth key (defaults to env VOLUME_DEBUG_KEY or 'dev').")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    # Resolve volume path
    volume = Path(args.path or os.environ.get("VOLUME_PATH") or (ROOT / "_volume_local")).resolve()
    volume.mkdir(parents=True, exist_ok=True)
    os.environ["VOLUME_PATH"] = str(volume)

    # Resolve key
    key = args.key or os.environ.get("VOLUME_DEBUG_KEY") or "dev"
    os.environ["VOLUME_DEBUG_KEY"] = key

    # Build a tiny FastAPI app that ONLY mounts the volume router.
    # We do NOT import the full main.py app because that pulls in heavy ML deps.
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import RedirectResponse

    # Re-import after env vars are set so the router picks up VOLUME_PATH/key
    from importlib import reload
    from api.routes import volume_debug
    reload(volume_debug)

    app = FastAPI(title="Local Volume Browser")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(volume_debug.router)

    @app.get("/")
    def _root():
        return RedirectResponse("/volume/ui")

    print("=" * 70)
    print(" LOCAL VOLUME BROWSER")
    print("=" * 70)
    print(f"  Folder       : {volume}")
    print(f"  Auth key     : {key}")
    print(f"  URL          : http://{args.host}:{args.port}/volume/ui")
    print("=" * 70)
    print("  Press Ctrl+C to stop.\n")

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
