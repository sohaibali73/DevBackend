"""
Unified File Upload Routes
==========================

Secure file upload endpoints using Railway persistent volume storage.

Files are stored on disk at:  $STORAGE_ROOT/{user_id}/{file_id}_{filename}
Metadata is stored in Supabase: file_uploads table

Features:
- Magic byte validation (not just extension)
- File size limits
- Content hash deduplication
- Text extraction for indexing
"""

import os
import uuid
import hashlib
import mimetypes
import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel

from api.dependencies import get_current_user_id
from db.supabase_client import get_supabase
from core.document_parser import DocumentParser

router = APIRouter(prefix="/upload", tags=["Upload"])
logger = logging.getLogger(__name__)

# Register AFL as a known MIME type so mimetypes.guess_type(".afl") works
mimetypes.add_type("text/plain", ".afl")

# ============================================================================
# STORAGE CONFIG
# ============================================================================

STORAGE_ROOT = os.getenv("STORAGE_ROOT", "/data")
MAX_FILE_SIZE = 10 * 1024 * 1024 * 1024  # 10 GB (no practical limit)

ALLOWED_MIME_TYPES = {
    # Documents
    "text/plain", "text/markdown", "text/csv",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    # Data
    "application/json", "application/xml", "text/xml",
    # Images
    "image/jpeg", "image/png", "image/gif", "image/webp",
    # AFL (AmiBroker Formula Language) — treated as plain text
    "text/x-afl", "application/afl",
}

# Extensions that must be treated as plain text regardless of what the browser
# reports in Content-Type.  Browsers often send 'application/octet-stream' for
# unknown extensions, which would otherwise trigger a 415 rejection.
_FORCE_TEXT_EXTENSIONS = {".afl"}


# ============================================================================
# HELPERS
# ============================================================================

def _storage_path(user_id: str, file_id: str, filename: str) -> str:
    """Absolute path on the Railway volume for this file."""
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")[:100]
    user_dir = os.path.join(STORAGE_ROOT, "uploads", user_id)
    os.makedirs(user_dir, exist_ok=True)
    return os.path.join(user_dir, f"{file_id}_{safe_name}")


def _write_file(path: str, content: bytes) -> None:
    with open(path, "wb") as f:
        f.write(content)


def _read_file(path: str) -> Optional[bytes]:
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def _delete_file(path: str) -> bool:
    try:
        if os.path.exists(path):
            os.remove(path)
            return True
    except OSError as e:
        logger.warning(f"Could not delete file {path}: {e}")
    return False


def _extract_text(storage_path: str) -> str:
    """Use the production-grade universal DocumentParser (OCR, tables, archives, magic bytes, etc.)."""
    try:
        parsed = DocumentParser.parse(storage_path)
        if parsed.success and parsed.content.strip():
            logger.info(f"Extracted {len(parsed.content)} chars from {os.path.basename(storage_path)}")
            return parsed.content.strip()
        if parsed.error:
            logger.warning(f"Parser warning for {storage_path}: {parsed.error}")
        return ""
    except Exception as e:
        logger.warning(f"DocumentParser failed for {storage_path}: {e}")
        return ""


async def _render_pptx_slides_to_disk(document_id: str, file_bytes: bytes, filename: str) -> list:
    """
    Render a PPTX file's slides to PNG images using the existing SlideRenderer
    (LibreOffice → PDF → PyMuPDF pipeline).

    Images are saved to:  $STORAGE_ROOT/slide_previews/{document_id}/slide_NNN.png

    Returns a list of absolute paths to the saved PNG files.
    Call this with `asyncio.run()` from a sync background task, or directly
    `await` it from an async context.
    """
    try:
        from core.vision.slide_renderer import SlideRenderer

        storage_root = os.getenv("STORAGE_ROOT", "/data")
        output_dir = os.path.join(storage_root, "slide_previews", document_id)
        os.makedirs(output_dir, exist_ok=True)

        renderer = SlideRenderer()
        manifest = await renderer.render(
            file_bytes=file_bytes,
            file_type="pptx",
            filename=filename,
        )

        if manifest.error:
            logger.warning(f"SlideRenderer reported error for {filename}: {manifest.error}")

        slide_paths: list = []
        for slide in manifest.slides:
            png_path = os.path.join(output_dir, f"slide_{slide.index:03d}.png")
            with open(png_path, "wb") as fh:
                fh.write(slide.image_bytes)
            slide_paths.append(png_path)

        logger.info(
            f"Rendered {len(slide_paths)} slide PNG(s) for document {document_id} "
            f"→ {output_dir}"
        )
        return slide_paths

    except ImportError:
        logger.info("SlideRenderer not available — skipping slide image rendering")
        return []
    except Exception as e:
        logger.warning(f"Slide rendering failed for document {document_id}: {e}")
        return []


def _background_extract_and_update(file_id: str, storage_path: str) -> None:
    """
    Blocking sync background task — FastAPI runs this in a thread pool so the
    conversation upload HTTP response is never blocked by slow parsing.

    Steps:
    1. Extract text and update file_uploads.extracted_text / status
    2. For PPTX files: render slides to PNG (enables vision analysis in chat)
    """
    import asyncio

    try:
        text = _extract_text(storage_path)
        if text:
            db = get_supabase()
            db.table("file_uploads").update({
                "extracted_text": text,
                "status": "ready",
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", file_id).execute()
            logger.info(f"Background extraction done for file {file_id}: {len(text)} chars")
        else:
            logger.warning(f"Background extraction yielded no text for file {file_id}")
    except Exception as e:
        logger.warning(f"Background extraction failed for file {file_id}: {e}")

    # ── Slide rendering for PPTX files (vision pipeline) ──────────────────────
    # Check extension from the storage_path
    ext = os.path.splitext(storage_path)[1].lower()
    if ext in {".pptx", ".ppt"}:
        try:
            with open(storage_path, "rb") as fh:
                file_bytes = fh.read()
            filename = os.path.basename(storage_path)
            # asyncio.run() creates a new event loop — safe from a thread-pool thread
            asyncio.run(_render_pptx_slides_to_disk(file_id, file_bytes, filename))
        except Exception as e:
            logger.warning(f"PPTX slide rendering failed for file {file_id}: {e}")


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class FileInfo(BaseModel):
    id: str
    user_id: str
    storage_path: str
    original_filename: str
    content_type: Optional[str]
    file_size: Optional[int]
    status: str
    content_hash: Optional[str]
    created_at: str
    download_url: Optional[str] = None


class FileListResponse(BaseModel):
    files: List[FileInfo]
    total: int


# ============================================================================
# DIRECT UPLOAD
# ============================================================================

@router.post("/direct", response_model=FileInfo)
async def upload_file_direct(
    file: UploadFile = File(...),
    bucket: str = Form("user-uploads"),          # kept for API compat, ignored
    user_id: str = Depends(get_current_user_id),
):
    """
    Upload a file directly through the server (≤10 MB).

    Saves to Railway volume at $STORAGE_ROOT/uploads/{user_id}/{file_id}_{filename}.
    Writes metadata row to Supabase file_uploads table.
    """
    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10 MB.")

    content_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"

    # Override content_type for extensions we know must be treated as plain text.
    # Browsers routinely report 'application/octet-stream' for unknown extensions
    # (e.g. .afl) which would otherwise hit the 415 guard below.
    _ext = os.path.splitext(file.filename or "")[1].lower()
    if _ext in _FORCE_TEXT_EXTENSIONS:
        content_type = "text/plain"
        logger.debug("AFL upload: overriding content_type to text/plain for %s", file.filename)

    if content_type not in ALLOWED_MIME_TYPES:
        logger.warning(f"Rejected file type: {content_type} ({file.filename})")
        raise HTTPException(status_code=415, detail=f"File type '{content_type}' is not allowed.")

    content_hash = hashlib.sha256(content).hexdigest()
    db = get_supabase()

    # Deduplication check
    existing = db.table("file_uploads").select("id, storage_path, status").eq(
        "content_hash", content_hash
    ).eq("user_id", user_id).limit(1).execute()

    if existing.data:
        row = existing.data[0]
        # Only reuse the existing record if the disk file is actually present.
        # If the volume was wiped or remounted the path in the DB is stale — fall
        # through and re-write the bytes so the download endpoint never gets a 404.
        if os.path.exists(row["storage_path"]):
            return FileInfo(
                id=row["id"],
                user_id=user_id,
                storage_path=row["storage_path"],
                original_filename=file.filename or "unknown",
                content_type=content_type,
                file_size=len(content),
                status=row["status"],
                content_hash=content_hash,
                created_at=row.get("created_at", datetime.now(timezone.utc).isoformat()),
            )
        # Disk file is gone — reuse the same UUID/path and re-write the bytes.
        logger.warning(
            f"Dedup hit for file {row['id']} but disk file is missing "
            f"({row['storage_path']}); re-writing bytes to disk."
        )
        _write_file(row["storage_path"], content)
        db.table("file_uploads").update({
            "status": "uploaded",
            "file_size": len(content),
        }).eq("id", row["id"]).execute()
        return FileInfo(
            id=row["id"],
            user_id=user_id,
            storage_path=row["storage_path"],
            original_filename=file.filename or "unknown",
            content_type=content_type,
            file_size=len(content),
            status="uploaded",
            content_hash=content_hash,
            created_at=row.get("created_at", datetime.now(timezone.utc).isoformat()),
        )

    file_id = str(uuid.uuid4())
    path = _storage_path(user_id, file_id, file.filename or "upload")

    try:
        _write_file(path, content)
    except OSError as e:
        logger.error(f"Failed to write file to disk: {e}")
        raise HTTPException(status_code=500, detail="Storage error — could not save file.")

    now = datetime.now(timezone.utc).isoformat()
    try:
        result = db.table("file_uploads").insert({
            "id": file_id,
            "user_id": user_id,
            "bucket_id": "local",
            "storage_path": path,
            "original_filename": file.filename or "upload",
            "content_type": content_type,
            "file_size": len(content),
            "content_hash": content_hash,
            "status": "uploaded",
            "created_at": now,
        }).execute()
    except Exception as e:
        # Roll back the file write if DB insert fails
        _delete_file(path)
        logger.error(f"DB insert failed after file write: {e}")
        raise HTTPException(status_code=500, detail="Database error — upload rolled back.")

    row = result.data[0]
    return FileInfo(
        id=row["id"],
        user_id=user_id,
        storage_path=path,
        original_filename=row["original_filename"],
        content_type=content_type,
        file_size=len(content),
        status="uploaded",
        content_hash=content_hash,
        created_at=now,
    )


# ============================================================================
# CONVERSATION UPLOAD (single-step: upload + link)
# ============================================================================

@router.post("/conversations/{conversation_id}", response_model=FileInfo)
async def upload_to_conversation(
    conversation_id: str,
    file: UploadFile = File(...),
    purpose: str = Form("reference"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user_id: str = Depends(get_current_user_id),
):
    """
    Upload a file and immediately link it to a conversation.

    This is the endpoint called by the Next.js /api/upload proxy.

    Text extraction runs in a background thread so the response is returned
    immediately — this prevents 504 timeouts on large/complex files (e.g.
    50 MB PPTX with many embedded graphics).
    """
    # ── Save file to disk + insert DB row ─────────────────────────────────────
    file_info = await upload_file_direct(file=file, bucket="user-uploads", user_id=user_id)

    db = get_supabase()

    # ── Queue text extraction in background (non-blocking) ────────────────────
    # _background_extract_and_update is a plain sync function; FastAPI runs it
    # in the default thread-pool executor so we never block the event loop.
    background_tasks.add_task(
        _background_extract_and_update,
        file_info.id,
        file_info.storage_path,
    )

    # ── Verify conversation belongs to this user ──────────────────────────────
    conv = db.table("conversations").select("id").eq("id", conversation_id).eq(
        "user_id", user_id
    ).execute()
    if not conv.data:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    # ── Link file ↔ conversation (ignore duplicate) ───────────────────────────
    try:
        db.table("conversation_files").insert({
            "conversation_id": conversation_id,
            "file_id": file_info.id,
            "purpose": purpose,
        }).execute()
    except Exception as e:
        if "unique" not in str(e).lower() and "duplicate" not in str(e).lower():
            logger.warning(f"Could not link file to conversation: {e}")

    return file_info


# ============================================================================
# LIST FILES
# ============================================================================

@router.get("/files", response_model=FileListResponse)
async def list_files(
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id),
):
    """List all uploaded files for the current user."""
    db = get_supabase()
    result = db.table("file_uploads").select("*").eq("user_id", user_id).order(
        "created_at", desc=True
    ).range(offset, offset + limit - 1).execute()

    files = [
        FileInfo(
            id=r["id"],
            user_id=r["user_id"],
            storage_path=r["storage_path"],
            original_filename=r["original_filename"],
            content_type=r.get("content_type"),
            file_size=r.get("file_size"),
            status=r.get("status", "uploaded"),
            content_hash=r.get("content_hash"),
            created_at=r.get("created_at", ""),
        )
        for r in result.data or []
    ]
    return FileListResponse(files=files, total=len(files))


# ============================================================================
# GET FILE INFO
# ============================================================================

@router.get("/files/{file_id}", response_model=FileInfo)
async def get_file_info(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get file metadata."""
    db = get_supabase()
    result = db.table("file_uploads").select("*").eq("id", file_id).eq(
        "user_id", user_id
    ).limit(1).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="File not found.")

    r = result.data[0]
    return FileInfo(
        id=r["id"],
        user_id=r["user_id"],
        storage_path=r["storage_path"],
        original_filename=r["original_filename"],
        content_type=r.get("content_type"),
        file_size=r.get("file_size"),
        status=r.get("status", "uploaded"),
        content_hash=r.get("content_hash"),
        created_at=r.get("created_at", ""),
    )


# ============================================================================
# DOWNLOAD
# ============================================================================

@router.get("/files/{file_id}/download")
async def download_file(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Stream file content back to the client."""
    db = get_supabase()
    result = db.table("file_uploads").select("*").eq("id", file_id).eq(
        "user_id", user_id
    ).limit(1).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="File not found.")

    r = result.data[0]
    content = _read_file(r["storage_path"])
    if content is None:
        raise HTTPException(status_code=404, detail="File data missing from storage.")

    return Response(
        content=content,
        media_type=r.get("content_type", "application/octet-stream"),
        headers={
            "Content-Disposition": f'attachment; filename="{r["original_filename"]}"'
        },
    )


# ============================================================================
# DELETE
# ============================================================================

@router.delete("/files/{file_id}")
async def delete_file(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete file from disk and database."""
    db = get_supabase()
    result = db.table("file_uploads").select("storage_path").eq("id", file_id).eq(
        "user_id", user_id
    ).limit(1).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="File not found.")

    _delete_file(result.data[0]["storage_path"])
    db.table("file_uploads").delete().eq("id", file_id).execute()

    return {"status": "deleted", "file_id": file_id}


# ============================================================================
# EXTRACT TEXT
# ============================================================================

@router.post("/files/{file_id}/extract")
async def extract_text(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Extract text content from a stored file and update the DB record."""
    db = get_supabase()
    result = db.table("file_uploads").select("*").eq("id", file_id).eq(
        "user_id", user_id
    ).limit(1).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="File not found.")

    r = result.data[0]
    text = _extract_text(r["storage_path"])
    if not text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from this file.")

    db.table("file_uploads").update({
        "extracted_text": text,
        "status": "ready",
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", file_id).execute()

    return {
        "file_id": file_id,
        "text_length": len(text),
        "text_preview": text[:500] + ("..." if len(text) > 500 else ""),
    }


# ============================================================================
# CONVERSATION FILES
# ============================================================================

@router.get("/conversations/{conversation_id}/files")
async def get_conversation_files(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get all files linked to a conversation."""
    db = get_supabase()

    conv = db.table("conversations").select("id").eq("id", conversation_id).eq(
        "user_id", user_id
    ).execute()
    if not conv.data:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    result = db.table("conversation_files").select(
        "id, purpose, created_at, file_uploads(*)"
    ).eq("conversation_id", conversation_id).execute()

    files = []
    for row in result.data or []:
        fd = row.get("file_uploads") or {}
        if fd:
            files.append({
                "link_id": row["id"],
                "purpose": row["purpose"],
                "linked_at": row["created_at"],
                "file": {
                    "id": fd.get("id"),
                    "filename": fd.get("original_filename"),
                    "content_type": fd.get("content_type"),
                    "file_size": fd.get("file_size"),
                    "status": fd.get("status"),
                },
            })

    return {"conversation_id": conversation_id, "files": files}


# ============================================================================
# LINK FILE TO CONVERSATION (standalone, for post-upload linking)
# ============================================================================

@router.post("/files/{file_id}/link/{conversation_id}")
async def link_file_to_conversation(
    file_id: str,
    conversation_id: str,
    purpose: str = "reference",
    user_id: str = Depends(get_current_user_id),
):
    """Link an already-uploaded file to a conversation."""
    db = get_supabase()

    file_row = db.table("file_uploads").select("id").eq("id", file_id).eq(
        "user_id", user_id
    ).limit(1).execute()
    if not file_row.data:
        raise HTTPException(status_code=404, detail="File not found.")

    conv = db.table("conversations").select("id").eq("id", conversation_id).eq(
        "user_id", user_id
    ).execute()
    if not conv.data:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    try:
        db.table("conversation_files").insert({
            "conversation_id": conversation_id,
            "file_id": file_id,
            "purpose": purpose,
        }).execute()
        return {"status": "linked", "file_id": file_id, "conversation_id": conversation_id}
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            return {"status": "already_linked", "file_id": file_id, "conversation_id": conversation_id}
        raise HTTPException(status_code=500, detail=f"Failed to link file: {e}")


# ============================================================================
# STORAGE INFO
# ============================================================================

@router.get("/info")
async def storage_info():
    """Return storage root and disk usage stats."""
    uploads_dir = os.path.join(STORAGE_ROOT, "uploads")
    total_bytes = 0
    file_count = 0

    if os.path.exists(uploads_dir):
        for dirpath, _, filenames in os.walk(uploads_dir):
            for fn in filenames:
                try:
                    total_bytes += os.path.getsize(os.path.join(dirpath, fn))
                    file_count += 1
                except OSError:
                    pass

    return {
        "storage_root": STORAGE_ROOT,
        "uploads_dir": uploads_dir,
        "total_files": file_count,
        "total_size_mb": round(total_bytes / (1024 * 1024), 2),
    }