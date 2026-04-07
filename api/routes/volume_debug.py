"""
Volume Debug Router
====================
Full CRUD access to the Railway persistent volume mounted at /data.
Secured by a static VOLUME_DEBUG_KEY env var (set this in Railway variables).

Endpoints:
  GET    /volume/info                  — disk usage summary
  GET    /volume/ls                    — list root or any subdir
  GET    /volume/ls/{dirpath}          — list a specific subdirectory
  GET    /volume/download/{filepath}   — download any file as bytes
  POST   /volume/upload/{dirpath}      — upload a file into a directory
  DELETE /volume/delete/{filepath}     — delete a file or empty directory
  POST   /volume/mkdir/{dirpath}       — create a directory
  POST   /volume/move                  — move / rename a file or directory
"""

import os
import shutil
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/volume", tags=["Volume Debug"])

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

VOLUME_PATH = Path(os.getenv("VOLUME_PATH", "/data"))

# Secret key — set VOLUME_DEBUG_KEY in Railway environment variables.
# If the env var is not set the endpoints are DISABLED (returns 503).
_DEBUG_KEY: str = os.getenv("VOLUME_DEBUG_KEY", "")


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _require_key(x_debug_key: Optional[str]) -> None:
    """Raise 401/503 if the debug key is wrong or not configured."""
    if not _DEBUG_KEY:
        raise HTTPException(
            status_code=503,
            detail="Volume debug endpoints are disabled. "
                   "Set VOLUME_DEBUG_KEY in Railway environment variables to enable.",
        )
    if x_debug_key != _DEBUG_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Debug-Key header.")


def _safe_path(rel: str) -> Path:
    """Resolve a relative path under VOLUME_PATH and guard against traversal."""
    # Normalise: strip leading slashes so Path doesn't treat it as absolute
    clean = rel.lstrip("/").lstrip("\\") if rel else ""
    resolved = (VOLUME_PATH / clean).resolve()
    try:
        resolved.relative_to(VOLUME_PATH.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Path traversal detected.")
    return resolved


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class MoveRequest(BaseModel):
    src: str   # relative path of source
    dst: str   # relative path of destination


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/info")
async def volume_info(x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key")):
    """Return volume existence, total size, and file count."""
    _require_key(x_debug_key)
    if not VOLUME_PATH.exists():
        return {
            "volume_path": str(VOLUME_PATH),
            "exists": False,
            "total_files": 0,
            "total_size_bytes": 0,
            "total_size_mb": 0.0,
        }

    total_bytes = 0
    total_files = 0
    try:
        for p in VOLUME_PATH.rglob("*"):
            if p.is_file():
                total_files += 1
                try:
                    total_bytes += p.stat().st_size
                except OSError:
                    pass
    except Exception as e:
        logger.warning("volume_info walk error: %s", e)

    # disk usage
    try:
        usage = shutil.disk_usage(str(VOLUME_PATH))
        disk_info = {
            "disk_total_gb": round(usage.total / 1e9, 2),
            "disk_used_gb":  round(usage.used  / 1e9, 2),
            "disk_free_gb":  round(usage.free  / 1e9, 2),
        }
    except Exception:
        disk_info = {}

    return {
        "volume_path": str(VOLUME_PATH),
        "exists": True,
        "total_files": total_files,
        "total_size_bytes": total_bytes,
        "total_size_mb": round(total_bytes / 1e6, 2),
        **disk_info,
    }


@router.get("/ls")
async def list_root(x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key")):
    """List the root of the volume (non-recursive)."""
    return await _list_dir("", x_debug_key)


@router.get("/ls/{dirpath:path}")
async def list_dir(
    dirpath: str,
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
):
    """List a specific directory inside the volume."""
    return await _list_dir(dirpath, x_debug_key)


async def _list_dir(dirpath: str, x_debug_key: Optional[str]):
    _require_key(x_debug_key)
    target = _safe_path(dirpath)

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {dirpath!r}")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {dirpath!r}")

    items = []
    try:
        for p in sorted(target.iterdir()):
            rel = str(p.relative_to(VOLUME_PATH))
            if p.is_dir():
                items.append({"name": p.name, "path": rel, "type": "directory", "size_bytes": None})
            else:
                try:
                    size = p.stat().st_size
                except OSError:
                    size = 0
                items.append({
                    "name": p.name,
                    "path": rel,
                    "type": "file",
                    "size_bytes": size,
                    "size_kb": round(size / 1024, 1),
                })
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return {
        "directory": dirpath or "/",
        "volume_path": str(VOLUME_PATH),
        "items": items,
        "count": len(items),
        "files": sum(1 for i in items if i["type"] == "file"),
        "directories": sum(1 for i in items if i["type"] == "directory"),
    }


@router.get("/download/{filepath:path}")
async def download_file(
    filepath: str,
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
):
    """Download a file from the volume as a binary response."""
    _require_key(x_debug_key)
    target = _safe_path(filepath)

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filepath!r}")
    if not target.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {filepath!r}")

    return FileResponse(
        path=str(target),
        filename=target.name,
        media_type="application/octet-stream",
    )


@router.post("/upload/{dirpath:path}")
async def upload_file(
    dirpath: str,
    file: UploadFile = File(...),
    overwrite: bool = Query(False, description="Allow overwriting existing file"),
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
):
    """Upload a file into a directory on the volume."""
    _require_key(x_debug_key)
    target_dir = _safe_path(dirpath)

    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
    elif not target_dir.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {dirpath!r}")

    dest = target_dir / (file.filename or "upload")
    if dest.exists() and not overwrite:
        raise HTTPException(
            status_code=409,
            detail=f"File already exists: {file.filename!r}. Use ?overwrite=true to replace.",
        )

    try:
        contents = await file.read()
        dest.write_bytes(contents)
    except Exception as e:
        logger.error("upload_file error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "success": True,
        "path": str(dest.relative_to(VOLUME_PATH)),
        "filename": dest.name,
        "size_bytes": len(contents),
        "size_kb": round(len(contents) / 1024, 1),
    }


@router.post("/upload")
async def upload_file_root(
    file: UploadFile = File(...),
    overwrite: bool = Query(False),
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
):
    """Upload a file into the volume root."""
    return await upload_file("", file, overwrite, x_debug_key)


@router.delete("/delete/{filepath:path}")
async def delete_path(
    filepath: str,
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
):
    """Delete a file or empty directory from the volume."""
    _require_key(x_debug_key)
    target = _safe_path(filepath)

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {filepath!r}")

    try:
        if target.is_dir():
            target.rmdir()  # only removes empty directories
            kind = "directory"
        else:
            target.unlink()
            kind = "file"
    except OSError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not delete: {e}. (Directories must be empty.)",
        )

    return {"success": True, "deleted": filepath, "type": kind}


@router.post("/mkdir/{dirpath:path}")
async def make_directory(
    dirpath: str,
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
):
    """Create a directory (and any missing parents) inside the volume."""
    _require_key(x_debug_key)
    target = _safe_path(dirpath)
    target.mkdir(parents=True, exist_ok=True)
    return {
        "success": True,
        "created": str(target.relative_to(VOLUME_PATH)),
    }


@router.post("/move")
async def move_path(
    body: MoveRequest,
    x_debug_key: Optional[str] = Header(None, alias="X-Debug-Key"),
):
    """Move or rename a file/directory within the volume."""
    _require_key(x_debug_key)
    src = _safe_path(body.src)
    dst = _safe_path(body.dst)

    if not src.exists():
        raise HTTPException(status_code=404, detail=f"Source not found: {body.src!r}")
    if dst.exists():
        raise HTTPException(status_code=409, detail=f"Destination already exists: {body.dst!r}")

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "success": True,
        "src": body.src,
        "dst": str(dst.relative_to(VOLUME_PATH)),
    }
