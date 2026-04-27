"""
api/routes/debug.py — Debug transcript access router.

Provides read access to the debug transcripts written by core.debug_transcript
when DEBUG_TRANSCRIPTS_ENABLED=1 is set.  All endpoints require a static
DEBUG_KEY header (set DEBUG_KEY in Railway environment variables) so they
are never accidentally exposed to end-users.

Endpoints:
    GET  /debug/health              — confirm the router is loaded
    GET  /debug/transcripts         — list available transcript files
    GET  /debug/transcripts/{name}  — fetch a specific transcript by filename
    DELETE /debug/transcripts/{name} — delete a specific transcript file

Router prefix: /debug
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debug", tags=["Debug"])

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_TRANSCRIPT_DIR = Path(os.getenv("DEBUG_TRANSCRIPT_DIR", "/data/debug_transcripts"))

# Protect all endpoints with a static key.  Set DEBUG_KEY in Railway vars.
# If not configured the endpoints return 503 so they fail safely.
_DEBUG_KEY: str = os.getenv("DEBUG_KEY", "")


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _require_key(x_debug_key: Optional[str]) -> None:
    """Raise 401/503 if the debug key is wrong or not configured."""
    if not _DEBUG_KEY:
        raise HTTPException(
            status_code=503,
            detail=(
                "Debug endpoints are disabled. "
                "Set DEBUG_KEY in Railway environment variables to enable."
            ),
        )
    if x_debug_key != _DEBUG_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Debug-Key header.")


def _safe_filename(name: str) -> Path:
    """Resolve a transcript filename and guard against path traversal."""
    # Only allow plain filenames — no slashes, no dots leading to parent dirs
    if "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    path = (_TRANSCRIPT_DIR / name).resolve()
    try:
        path.relative_to(_TRANSCRIPT_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Path traversal detected.")
    return path


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/health")
async def debug_health() -> Dict[str, Any]:
    """
    Confirm the debug router is loaded and report transcript directory status.
    Does NOT require authentication — safe to call from health checks.
    """
    enabled = os.getenv("DEBUG_TRANSCRIPTS_ENABLED", "").strip() == "1"
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "debug_transcripts_enabled": enabled,
        "transcript_dir": str(_TRANSCRIPT_DIR),
        "transcript_dir_exists": _TRANSCRIPT_DIR.exists(),
        "key_configured": bool(_DEBUG_KEY),
    }


@router.get("/transcripts")
async def list_transcripts(
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
    limit: int = 50,
) -> Dict[str, Any]:
    """
    List available debug transcript files, newest first.

    Requires X-Debug-Key header matching the DEBUG_KEY environment variable.
    """
    _require_key(x_debug_key)

    if not _TRANSCRIPT_DIR.exists():
        return {
            "transcript_dir": str(_TRANSCRIPT_DIR),
            "exists": False,
            "files": [],
            "count": 0,
        }

    try:
        files: List[Dict[str, Any]] = []
        for p in sorted(_TRANSCRIPT_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
            try:
                stat = p.stat()
                files.append({
                    "name": p.name,
                    "size_bytes": stat.st_size,
                    "size_kb": round(stat.st_size / 1024, 1),
                    "modified": datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
                })
            except OSError:
                pass
        files = files[:limit]
    except Exception as exc:
        logger.error("list_transcripts error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "transcript_dir": str(_TRANSCRIPT_DIR),
        "exists": True,
        "files": files,
        "count": len(files),
    }


@router.get("/transcripts/{name}")
async def get_transcript(
    name: str,
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
) -> Any:
    """
    Fetch the full content of a specific transcript file by filename.

    Requires X-Debug-Key header matching the DEBUG_KEY environment variable.
    """
    _require_key(x_debug_key)
    path = _safe_filename(name)

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Transcript not found: {name!r}")
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {name!r}")

    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"Transcript is not valid JSON: {exc}")
    except Exception as exc:
        logger.error("get_transcript error for %s: %s", name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    return data


@router.delete("/transcripts/{name}")
async def delete_transcript(
    name: str,
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
) -> Dict[str, Any]:
    """
    Delete a specific transcript file by filename.

    Requires X-Debug-Key header matching the DEBUG_KEY environment variable.
    """
    _require_key(x_debug_key)
    path = _safe_filename(name)

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Transcript not found: {name!r}")

    try:
        path.unlink()
    except Exception as exc:
        logger.error("delete_transcript error for %s: %s", name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    return {"success": True, "deleted": name}
