"""
Unified file download router.

Provides GET /files/{file_id}/download for any tool-generated file.
Download flow (all paths require Bearer JWT authentication):
  1. In-memory file_store cache (hot layer — instant)
  2. Supabase Storage "user-uploads" bucket (persistent layer — survives restarts)
  3. Claude's Files API (skill-generated files with file_xxx IDs)
     Uses the authenticated user's Claude API key looked up from Supabase.

For user-uploaded files see /upload/files/{file_id}/download (upload.py).
"""

import logging
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import Response, JSONResponse

from api.dependencies import get_current_user_id
from core.file_store import get_file, list_files

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["files"])

# MIME type mapping
_MIME_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "pdf":  "application/pdf",
    "csv":  "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "json": "application/json",
    "txt":  "text/plain",
    "md":   "text/markdown",
    "png":  "image/png",
    "jpg":  "image/jpeg",
    "jpeg": "image/jpeg",
}


def _get_mime(filename: str, file_type: str = "") -> str:
    """Get MIME type from file_type or filename extension."""
    if file_type and file_type in _MIME_TYPES:
        return _MIME_TYPES[file_type]
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _MIME_TYPES.get(ext, "application/octet-stream")


def _get_user_claude_api_key(user_id: str) -> str | None:
    """Look up the user's decrypted Claude API key from Supabase."""
    try:
        from db.supabase_client import get_supabase
        from core.encryption import decrypt_value
        db = get_supabase()
        result = db.table("user_profiles").select(
            "claude_api_key_encrypted"
        ).eq("id", user_id).limit(1).execute()
        if result.data and result.data[0].get("claude_api_key_encrypted"):
            return decrypt_value(result.data[0]["claude_api_key_encrypted"])
    except Exception as e:
        logger.warning("Could not retrieve user Claude API key: %s", e)
    return None


def _download_from_claude_files_api(file_id: str, claude_api_key: str) -> bytes | None:
    """Download file bytes from Claude's Files API using the user's Claude API key."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=claude_api_key)
        files_beta = ["files-api-2025-04-14"]

        file_content = client.beta.files.download(
            file_id,
            betas=files_beta,
        )
        if isinstance(file_content, bytes):
            return file_content
        elif hasattr(file_content, "iter_bytes"):
            return b"".join(file_content.iter_bytes())
        elif hasattr(file_content, "read"):
            return file_content.read()
        else:
            return bytes(file_content)
    except Exception as e:
        logger.debug("Claude Files API download failed for %s: %s", file_id, e)
        return None


@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    filename: str = None,
    user_id: str = Depends(get_current_user_id),
):
    """
    Download a generated file by its ID. Requires authentication.

    Priority:
      1. In-memory cache (instant — works during container lifetime)
      2. Supabase Storage (persistent — survives container restarts)
      3. Claude Files API (for skill-generated files with file_xxx IDs,
         uses the user's own Claude API key looked up from Supabase)
    """

    # ── 1. In-memory cache / Supabase Storage (handled by get_file) ──────────
    entry = get_file(file_id)
    if entry is not None:
        mime = _get_mime(entry.filename, entry.file_type)
        dl_filename = filename or entry.filename
        return Response(
            content=entry.data,
            media_type=mime,
            headers={
                "Content-Disposition": f'attachment; filename="{dl_filename}"',
                "Content-Length": str(len(entry.data)),
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )

    # ── 2. Claude Files API fallback (file_xxx IDs from skills) ──────────────
    if file_id.startswith("file_"):
        # Get the user's Claude API key from Supabase (NOT from the auth header)
        claude_api_key = _get_user_claude_api_key(user_id)
        if claude_api_key:
            data = _download_from_claude_files_api(file_id, claude_api_key)
            if data:
                # Try to get filename from Claude's metadata
                dl_filename = filename or f"download_{file_id}"
                try:
                    import anthropic
                    client = anthropic.Anthropic(api_key=claude_api_key)
                    meta = client.beta.files.retrieve_metadata(
                        file_id,
                        betas=["files-api-2025-04-14"],
                    )
                    dl_filename = filename or getattr(meta, "filename", None) or dl_filename
                except Exception:
                    pass

                ext = dl_filename.rsplit(".", 1)[-1].lower() if "." in dl_filename else "bin"
                mime = _get_mime(dl_filename)

                logger.info(
                    "Downloaded %s from Claude Files API for user %s (%d bytes)",
                    file_id, user_id, len(data),
                )

                # Cache locally so future downloads are instant
                try:
                    from core.file_store import store_file
                    store_file(
                        data=data,
                        filename=dl_filename,
                        file_type=ext,
                        tool_name="claude_files_api",
                        file_id=file_id,
                    )
                except Exception as cache_err:
                    logger.debug("Could not cache file locally: %s", cache_err)

                return Response(
                    content=data,
                    media_type=mime,
                    headers={
                        "Content-Disposition": f'attachment; filename="{dl_filename}"',
                        "Content-Length": str(len(data)),
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Expose-Headers": "Content-Disposition",
                    },
                )
        else:
            logger.warning(
                "No Claude API key for user %s — cannot fall back to Claude Files API for %s",
                user_id, file_id,
            )

    raise HTTPException(
        status_code=404,
        detail=f"File '{file_id}' not found in local storage, Supabase, or Claude Files API.",
    )


@router.get("/{file_id}/info")
async def file_info(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get file metadata without downloading."""
    entry = get_file(file_id)
    if entry is None:
        return JSONResponse(
            content={"file_id": file_id, "exists": False},
            status_code=404,
        )
    return {
        "file_id":      entry.file_id,
        "filename":     entry.filename,
        "file_type":    entry.file_type,
        "size_kb":      entry.size_kb,
        "exists":       True,
        "download_url": f"/files/{file_id}/download",
    }


@router.get("/generated")
async def list_generated_files(
    user_id: str = Depends(get_current_user_id),
):
    """List all currently available generated files (memory cache)."""
    return {"files": list_files()}
