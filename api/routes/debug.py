"""
Debug Transcript API Routes
============================
REST endpoints for reading, downloading, and managing debug transcripts.

All endpoints require standard Bearer token auth (same as all other routes).
Transcripts are only written when DEBUG_TRANSCRIPTS_ENABLED=1.

Endpoints:
  GET    /debug/status
  GET    /debug/transcripts
  GET    /debug/transcripts/{request_id}
  GET    /debug/transcripts/{request_id}/text
  GET    /debug/transcripts/{request_id}/download
  DELETE /debug/transcripts/{request_id}
  DELETE /debug/transcripts
  POST   /debug/transcripts/prune
"""

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, FileResponse, JSONResponse
from pydantic import BaseModel

from api.dependencies import get_current_user_id
from core.debug_transcript import (
    is_debug_enabled,
    list_transcripts,
    prune_old_transcripts,
)

router = APIRouter(prefix="/debug", tags=["Debug"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _storage_root() -> str:
    return os.getenv("STORAGE_ROOT", "/data")


def _resolve_transcript_paths(request_id: str):
    """
    Locate .json and .txt files for a request_id by scanning the tree.
    Returns (json_path, txt_path) or raises 404.
    """
    base = Path(_storage_root()) / "debug_transcripts"
    if not base.exists():
        raise HTTPException(status_code=404, detail="No transcripts directory found")

    # Fast path: request_id encodes nothing about user/conv, so do a rglob
    matches = list(base.rglob(f"{request_id}.json"))
    if not matches:
        raise HTTPException(status_code=404, detail=f"Transcript not found: {request_id}")

    json_path = matches[0]
    txt_path = json_path.with_suffix(".txt")
    return json_path, txt_path


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status")
async def debug_status(user_id: str = Depends(get_current_user_id)):
    """Return whether debug transcripts are enabled and where they are stored."""
    enabled = is_debug_enabled()
    storage = _storage_root()
    transcript_dir = str(Path(storage) / "debug_transcripts")
    return {
        "enabled": enabled,
        "storage_root": transcript_dir,
        "message": (
            "Debug transcripts are ENABLED — set DEBUG_TRANSCRIPTS_ENABLED=0 to disable"
            if enabled
            else "Debug transcripts are DISABLED — set DEBUG_TRANSCRIPTS_ENABLED=1 to enable"
        ),
    }


@router.get("/transcripts")
async def list_debug_transcripts(
    user_id: str = Depends(get_current_user_id),
    filter_user_id: Optional[str] = Query(default=None, alias="user_id"),
    conversation_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
):
    """
    List debug transcripts.

    Query params (all optional):
      user_id         — filter to a specific user's transcripts
      conversation_id — filter to a specific conversation
      limit           — max results (default 20, max 200)
    """
    storage = _storage_root()
    transcripts = list_transcripts(
        storage_root=storage,
        user_id=filter_user_id,
        conversation_id=conversation_id,
        limit=limit,
    )
    return {"transcripts": transcripts, "count": len(transcripts)}


@router.get("/transcripts/{request_id}")
async def get_transcript_json(
    request_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Return the full machine-readable JSON transcript for a specific request.
    """
    json_path, _ = _resolve_transcript_paths(request_id)
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read transcript: {e}")
    return JSONResponse(content=data)


@router.get("/transcripts/{request_id}/text", response_class=PlainTextResponse)
async def get_transcript_text(
    request_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Return the human-readable .txt transcript for a specific request.
    This is the most useful endpoint for debugging — shows every event
    in a clean, formatted layout.
    """
    json_path, txt_path = _resolve_transcript_paths(request_id)

    # Prefer the .txt file if it exists
    if txt_path.exists():
        try:
            return PlainTextResponse(
                content=txt_path.read_text(encoding="utf-8"),
                media_type="text/plain; charset=utf-8",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read transcript text: {e}")

    # Fall back: regenerate from JSON using to_text()
    try:
        from core.debug_transcript import DebugTranscript
        raw = json.loads(json_path.read_text(encoding="utf-8"))

        # Build a minimal DebugTranscript and replay events
        dt = DebugTranscript(
            conversation_id=raw.get("conversation_id", ""),
            user_id=raw.get("user_id", ""),
        )
        dt.request_id = raw.get("request_id", dt.request_id)
        dt.model = raw.get("model", "")
        from datetime import datetime, timezone
        try:
            dt.started_at = datetime.fromisoformat(raw["started_at"].replace("Z", "+00:00"))
        except Exception:
            pass
        # Replay events directly into the internal list
        dt._events = raw.get("events", [])
        return PlainTextResponse(
            content=dt.to_text(),
            media_type="text/plain; charset=utf-8",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to render transcript: {e}",
        )


@router.get("/transcripts/{request_id}/download")
async def download_transcript(
    request_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Download the human-readable .txt transcript as a file attachment.
    """
    _, txt_path = _resolve_transcript_paths(request_id)

    if not txt_path.exists():
        # Fall back: generate and return as PlainText
        return await get_transcript_text(request_id=request_id, user_id=user_id)

    return FileResponse(
        path=str(txt_path),
        media_type="text/plain",
        filename=f"{request_id}.txt",
        headers={"Content-Disposition": f'attachment; filename="{request_id}.txt"'},
    )


@router.delete("/transcripts/{request_id}")
async def delete_transcript(
    request_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Delete both the .json and .txt files for a single request transcript.
    """
    json_path, txt_path = _resolve_transcript_paths(request_id)
    deleted = []
    for p in (json_path, txt_path):
        try:
            if p.exists():
                p.unlink()
                deleted.append(p.name)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete {p.name}: {e}")
    return {"deleted": deleted, "request_id": request_id}


@router.delete("/transcripts")
async def delete_all_transcripts(
    user_id: str = Depends(get_current_user_id),
    filter_user_id: Optional[str] = Query(default=None, alias="user_id"),
    conversation_id: Optional[str] = Query(default=None),
):
    """
    Delete all transcripts.
    Optionally scope by user_id and/or conversation_id.
    """
    base = Path(_storage_root()) / "debug_transcripts"
    if not base.exists():
        return {"deleted_files": 0}

    deleted = 0

    def _rm_dir_transcripts(d: Path) -> int:
        count = 0
        for f in list(d.glob("*.json")) + list(d.glob("*.txt")):
            try:
                f.unlink(missing_ok=True)
                count += 1
            except Exception:
                pass
        return count

    if filter_user_id and conversation_id:
        target = base / filter_user_id / conversation_id
        if target.is_dir():
            deleted += _rm_dir_transcripts(target)
    elif filter_user_id:
        user_dir = base / filter_user_id
        if user_dir.is_dir():
            for conv_dir in user_dir.iterdir():
                if conv_dir.is_dir():
                    deleted += _rm_dir_transcripts(conv_dir)
    else:
        # Delete everything
        for user_dir in base.iterdir():
            if user_dir.is_dir():
                for conv_dir in user_dir.iterdir():
                    if conv_dir.is_dir():
                        deleted += _rm_dir_transcripts(conv_dir)

    return {"deleted_files": deleted}


class PruneRequest(BaseModel):
    max_age_days: int = 7


@router.post("/transcripts/prune")
async def prune_transcripts(
    body: PruneRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Delete transcripts older than max_age_days (default: 7).
    Returns a count of files deleted.
    """
    if body.max_age_days < 1:
        raise HTTPException(status_code=400, detail="max_age_days must be >= 1")

    deleted = prune_old_transcripts(
        storage_root=_storage_root(),
        max_age_days=body.max_age_days,
    )
    return {
        "deleted_files": deleted,
        "max_age_days": body.max_age_days,
        "message": f"Pruned {deleted} transcript file(s) older than {body.max_age_days} day(s)",
    }
