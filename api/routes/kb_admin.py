"""
KB Admin Routes — Bulk upload to Knowledge Base without Supabase JWT.

Auth: X-Admin-Key header matching the ADMIN_UPLOAD_SECRET environment variable.
This lets you call these endpoints from a local script / CI pipeline / SSH session
without going through the browser auth flow.

  curl -X POST https://your-app.railway.app/kb-admin/bulk-upload \
       -H "X-Admin-Key: $ADMIN_UPLOAD_SECRET" \
       -F "files=@report.pdf" \
       -F "files=@strategy.docx" \
       -F "category=research"
"""

import os
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Header, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from api.routes.upload import (
    _storage_path,
    _write_file,
    _delete_file,
    _extract_text,
    MAX_FILE_SIZE,
)

router = APIRouter(prefix="/kb-admin", tags=["KB Admin (Bulk Upload)"])
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# Documents uploaded via this endpoint are owned by this sentinel user-id so
# they appear in the shared KB without being tied to any real user.
SYSTEM_UPLOADER_ID = "00000000-0000-0000-0000-000000000000"

MAX_BATCH_FILES = 200      # safety cap per request
CHUNK_SIZE = 500           # characters per brain_chunk row
MAX_CHUNKS_PER_DOC = 100   # cap chunks to avoid Supabase row bloat


# ─────────────────────────────────────────────────────────────────────────────
# AUTH DEPENDENCY
# ─────────────────────────────────────────────────────────────────────────────

def _check_admin_key(x_admin_key: Optional[str] = Header(default=None)) -> None:
    """
    Validate the X-Admin-Key header against the ADMIN_UPLOAD_SECRET env var.

    Set the env var on Railway:
        railway variables set ADMIN_UPLOAD_SECRET=<your-long-random-secret>

    Then pass it in every request:
        -H "X-Admin-Key: <your-long-random-secret>"
    """
    secret = os.getenv("ADMIN_UPLOAD_SECRET", "").strip()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_UPLOAD_SECRET is not configured on the server. "
                   "Set it as an environment variable and redeploy.",
        )
    if not x_admin_key or x_admin_key.strip() != secret:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing X-Admin-Key header.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _extract_text_from_bytes(content_bytes: bytes, filename: str) -> str:
    """Write bytes to a temp file and call the disk-based extractor."""
    import tempfile

    suffix = os.path.splitext(filename)[1] if filename else ""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content_bytes)
            tmp_path = tmp.name
        return _extract_text(tmp_path)
    except Exception as exc:
        logger.warning(f"Text extraction failed for {filename}: {exc}")
        return ""
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _insert_document(
    db,
    content_bytes: bytes,
    filename: str,
    content_type: str,
    category: str,
    tags: List[str],
    uploader_id: str,
) -> dict:
    """
    Core logic: extract → dedup → save to disk → insert brain_documents + brain_chunks.
    Returns a dict with keys: status, document_id, filename, chunks_created, error.
    """
    content = _extract_text_from_bytes(content_bytes, filename).replace("\x00", "")
    if not content.strip():
        return {
            "filename": filename,
            "status": "error",
            "error": "Could not extract any text from this file.",
        }

    content_hash = hashlib.sha256(content_bytes).hexdigest()

    # ── Dedup ─────────────────────────────────────────────────────────────────
    existing = db.table("brain_documents").select("id").eq(
        "content_hash", content_hash
    ).limit(1).execute()
    if existing.data:
        return {
            "filename": filename,
            "status": "duplicate",
            "document_id": existing.data[0]["id"],
        }

    # ── Save to Railway volume ────────────────────────────────────────────────
    file_id = str(uuid.uuid4())
    storage_path = _storage_path(uploader_id, file_id, filename)
    try:
        _write_file(storage_path, content_bytes)
    except OSError as exc:
        logger.error(f"Disk write failed for {filename}: {exc}")
        return {
            "filename": filename,
            "status": "error",
            "error": f"Storage error: {exc}",
        }

    # ── Insert brain_documents ─────────────────────────────────────────────────
    now = datetime.now(timezone.utc).isoformat()
    doc_result = db.table("brain_documents").insert({
        "id": file_id,
        "uploaded_by": uploader_id,
        "title": filename,
        "filename": filename,
        "file_type": content_type or "application/octet-stream",
        "file_size": len(content_bytes),
        "storage_path": storage_path,
        "category": category,
        "subcategories": [],
        "tags": tags,
        "raw_content": content,
        "summary": "",
        "content_hash": content_hash,
        "source_type": "bulk_admin_upload",
        "created_at": now,
    }).execute()

    document_id = doc_result.data[0]["id"]

    # ── Chunk for RAG ──────────────────────────────────────────────────────────
    chunks = [
        content[i : i + CHUNK_SIZE]
        for i in range(0, len(content), CHUNK_SIZE)
    ][:MAX_CHUNKS_PER_DOC]

    for idx, chunk in enumerate(chunks):
        db.table("brain_chunks").insert({
            "document_id": document_id,
            "chunk_index": idx,
            "content": chunk,
        }).execute()

    db.table("brain_documents").update({
        "is_processed": True,
        "chunk_count": len(chunks),
        "processed_at": now,
    }).eq("id", document_id).execute()

    return {
        "filename": filename,
        "status": "success",
        "document_id": document_id,
        "storage_path": storage_path,
        "chunks_created": len(chunks),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/bulk-upload")
async def bulk_upload_to_kb(
    files: List[UploadFile] = File(..., description="One or more files to upload"),
    category: Optional[str] = Form("general", description="KB category (e.g. research, strategy)"),
    tags: Optional[str] = Form("", description="Comma-separated tags"),
    uploader_id: Optional[str] = Form(None, description="Override uploader UUID (defaults to system)"),
    x_admin_key: Optional[str] = Header(default=None),
):
    """
    Bulk-upload documents to the shared Knowledge Base.

    **Auth**: Pass the ADMIN_UPLOAD_SECRET value in the X-Admin-Key header.

    **Usage (curl)**:
    ```bash
    curl -X POST https://your-app.railway.app/kb-admin/bulk-upload \\
         -H "X-Admin-Key: YOUR_SECRET" \\
         -F "files=@report.pdf" \\
         -F "files=@notes.docx" \\
         -F "category=research" \\
         -F "tags=2024,earnings"
    ```

    **Usage (Python script)**:
    ```bash
    python scripts/bulk_kb_upload.py \\
        --dir ./docs \\
        --url https://your-app.railway.app \\
        --key YOUR_SECRET \\
        --category research
    ```

    Documents are visible to **all users** in the KB.
    Duplicate files (same SHA-256) are skipped automatically.
    """
    _check_admin_key(x_admin_key)

    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. Maximum batch size is {MAX_BATCH_FILES}.",
        )

    db = get_supabase()
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    owner_id = (uploader_id or "").strip() or SYSTEM_UPLOADER_ID
    cat = (category or "general").strip()

    results = []
    successful = duplicates = failed = 0
    total_bytes = 0

    for upload in files:
        fname = upload.filename or "unnamed"
        try:
            content_bytes = await upload.read()
            total_bytes += len(content_bytes)

            if len(content_bytes) > MAX_FILE_SIZE:
                failed += 1
                results.append({
                    "filename": fname,
                    "status": "error",
                    "error": f"File exceeds {MAX_FILE_SIZE // (1024*1024)} MB limit.",
                })
                continue

            if not content_bytes.strip():
                failed += 1
                results.append({"filename": fname, "status": "error", "error": "File is empty."})
                continue

            result = _insert_document(
                db=db,
                content_bytes=content_bytes,
                filename=fname,
                content_type=upload.content_type or "",
                category=cat,
                tags=tag_list,
                uploader_id=owner_id,
            )

            if result["status"] == "success":
                successful += 1
            elif result["status"] == "duplicate":
                duplicates += 1
            else:
                failed += 1

            results.append(result)

        except Exception as exc:
            failed += 1
            logger.error(f"Bulk upload failed for {fname}: {exc}", exc_info=True)
            results.append({"filename": fname, "status": "error", "error": str(exc)})

    return {
        "status": "completed",
        "summary": {
            "total": len(files),
            "successful": successful,
            "duplicates": duplicates,
            "failed": failed,
            "total_bytes_received": total_bytes,
        },
        "results": results,
    }


# ─────────────────────────────────────────────────────────────────────────────

@router.get("/list")
async def list_kb_documents(
    category: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    x_admin_key: Optional[str] = Header(default=None),
):
    """List all documents in the KB (admin view — no user filter)."""
    _check_admin_key(x_admin_key)

    db = get_supabase()
    query = db.table("brain_documents").select(
        "id, title, filename, category, tags, file_size, chunk_count, "
        "uploaded_by, source_type, created_at, is_processed"
    )
    if category:
        query = query.eq("category", category)

    result = (
        query.order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )

    total = db.table("brain_documents").select("id", count="exact").execute()

    return {
        "total": total.count or 0,
        "count": len(result.data),
        "offset": offset,
        "documents": result.data,
    }


# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/documents/{document_id}")
async def delete_kb_document(
    document_id: str,
    x_admin_key: Optional[str] = Header(default=None),
):
    """Delete a KB document (and its file from the Railway volume)."""
    _check_admin_key(x_admin_key)

    db = get_supabase()
    result = db.table("brain_documents").select("storage_path, filename").eq(
        "id", document_id
    ).limit(1).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found.")

    sp = result.data[0].get("storage_path")
    if sp:
        _delete_file(sp)

    db.table("brain_documents").delete().eq("id", document_id).execute()

    return {
        "status": "deleted",
        "document_id": document_id,
        "filename": result.data[0].get("filename"),
    }


# ─────────────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def kb_stats(x_admin_key: Optional[str] = Header(default=None)):
    """Return KB stats (document count, categories, disk usage)."""
    _check_admin_key(x_admin_key)

    db = get_supabase()
    docs = db.table("brain_documents").select("category, file_size").execute()

    category_counts: dict = {}
    total_size = 0
    for doc in docs.data or []:
        cat = doc.get("category", "general")
        category_counts[cat] = category_counts.get(cat, 0) + 1
        total_size += doc.get("file_size", 0) or 0

    try:
        chunks = db.table("brain_chunks").select("id", count="exact").execute()
        total_chunks = chunks.count or 0
    except Exception:
        total_chunks = 0

    storage_root = os.getenv("STORAGE_ROOT", "/data")
    uploads_dir = os.path.join(storage_root, "uploads")
    disk_bytes = 0
    if os.path.exists(uploads_dir):
        for dirpath, _, filenames in os.walk(uploads_dir):
            for fn in filenames:
                try:
                    disk_bytes += os.path.getsize(os.path.join(dirpath, fn))
                except OSError:
                    pass

    return {
        "total_documents": len(docs.data or []),
        "total_chunks": total_chunks,
        "total_size_db_bytes": total_size,
        "total_size_disk_mb": round(disk_bytes / (1024 * 1024), 2),
        "categories": category_counts,
    }
