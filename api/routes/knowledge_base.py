"""Knowledge Base routes — /knowledge-base/* prefix.

This router mirrors the /brain/* functionality under the frontend-expected
/knowledge-base/* path so both path prefixes work simultaneously.
"""

import os
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import Response as FastAPIResponse
from pydantic import BaseModel

from api.dependencies import get_current_user_id, get_user_api_keys
from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge-base", tags=["Knowledge Base"])


# ──────────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    category: Optional[str] = None
    limit: int = 10


class UpdateFileRequest(BaseModel):
    tags: Optional[List[str]] = None
    description: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# Upload document
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    category: Optional[str] = Form("general"),
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """Upload and index a document into the knowledge base."""
    # Delegate to the brain upload logic to avoid code duplication
    from api.routes.brain import upload_document as brain_upload
    return await brain_upload(
        file=file, title=title, category=category,
        user_id=user_id, api_keys=api_keys,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Search
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/search")
async def search_knowledge_base(
    data: SearchRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Search the knowledge base."""
    from api.routes.brain import search_knowledge
    return await search_knowledge(data=data, user_id=user_id)


# ──────────────────────────────────────────────────────────────────────────────
# List files
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/files")
async def list_files(
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    tags: Optional[str] = None,
    category: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
):
    """List all documents in the knowledge base with pagination and filters."""
    db = get_supabase()

    query = db.table("brain_documents").select(
        "id, title, filename, category, tags, summary, file_size, file_type, created_at, chunk_count"
    )

    # Filter by owner where possible (uploaded_by column)
    try:
        query = query.eq("uploaded_by", user_id)
    except Exception:
        pass

    if category:
        query = query.eq("category", category)

    if search:
        safe = search.replace("'", "''")
        query = query.or_(
            f"title.ilike.%{safe}%,summary.ilike.%{safe}%,filename.ilike.%{safe}%"
        )

    result = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()

    total_res = db.table("brain_documents").select("id", count="exact").execute()
    total = total_res.count or 0

    files = []
    for doc in result.data or []:
        files.append({
            "id": doc["id"],
            "name": doc.get("title") or doc.get("filename", ""),
            "filename": doc.get("filename", ""),
            "size": doc.get("file_size", 0),
            "type": doc.get("file_type", "unknown"),
            "upload_date": doc.get("created_at", ""),
            "tags": doc.get("tags") or [],
            "description": doc.get("summary", ""),
            "category": doc.get("category", "general"),
            "page_count": doc.get("chunk_count"),
        })

    return {
        "files": files,
        "total": total,
        "has_more": (offset + limit) < total,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Get single file
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/files/{file_id}")
async def get_file_details(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get detailed file information."""
    db = get_supabase()

    result = db.table("brain_documents").select("*").eq("id", file_id).limit(1).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="File not found")

    doc = result.data[0]

    # Soft ownership check (don't hard-fail if column missing)
    if doc.get("uploaded_by") and doc["uploaded_by"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Usage stats — graceful
    refs_gen = 0
    refs_chat = 0
    try:
        r = db.table("afl_uploaded_files").select("id", count="exact").eq("user_id", user_id).execute()
        refs_gen = r.count or 0
    except Exception:
        pass

    return {
        "id": doc["id"],
        "name": doc.get("title") or doc.get("filename", ""),
        "filename": doc.get("filename", ""),
        "size": doc.get("file_size", 0),
        "type": doc.get("file_type", "unknown"),
        "upload_date": doc.get("created_at", ""),
        "tags": doc.get("tags") or [],
        "description": doc.get("summary", ""),
        "category": doc.get("category", "general"),
        "page_count": doc.get("chunk_count"),
        "word_count": doc.get("word_count"),
        "metadata": doc.get("metadata") or {},
        "raw_content_preview": (doc.get("raw_content") or "")[:500],
        "usage_stats": {
            "referenced_in_generations": refs_gen,
            "referenced_in_chats": refs_chat,
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# Update file metadata
# ──────────────────────────────────────────────────────────────────────────────

@router.patch("/files/{file_id}")
async def update_file_metadata(
    file_id: str,
    request: UpdateFileRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Update file tags and description/summary."""
    db = get_supabase()

    existing = db.table("brain_documents").select("uploaded_by").eq("id", file_id).limit(1).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="File not found")
    if existing.data[0].get("uploaded_by") and existing.data[0]["uploaded_by"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    update_fields: dict = {}
    if request.tags is not None:
        update_fields["tags"] = request.tags
    if request.description is not None:
        update_fields["summary"] = request.description

    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = db.table("brain_documents").update(update_fields).eq("id", file_id).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Update failed")

    updated = result.data[0]
    return {
        "success": True,
        "file": {
            "id": updated["id"],
            "tags": updated.get("tags") or [],
            "description": updated.get("summary", ""),
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# Delete file
# ──────────────────────────────────────────────────────────────────────────────

@router.delete("/files/{file_id}")
async def delete_file(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a file from the knowledge base."""
    db = get_supabase()

    result = db.table("brain_documents").select("storage_path, uploaded_by").eq(
        "id", file_id
    ).limit(1).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="File not found")

    doc = result.data[0]
    if doc.get("uploaded_by") and doc["uploaded_by"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Delete physical file from Railway volume
    storage_path = doc.get("storage_path")
    if storage_path and os.path.exists(storage_path):
        try:
            os.remove(storage_path)
        except OSError as e:
            logger.warning(f"Could not delete file on disk: {e}")

    # brain_chunks are cascade-deleted by FK
    db.table("brain_documents").delete().eq("id", file_id).execute()

    return {"success": True, "message": "File deleted successfully"}


# ──────────────────────────────────────────────────────────────────────────────
# Download file
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/files/{file_id}/download")
async def download_file(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Download the original file binary."""
    import mimetypes

    db = get_supabase()

    result = db.table("brain_documents").select(
        "storage_path, filename, file_type, uploaded_by"
    ).eq("id", file_id).limit(1).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="File not found")

    doc = result.data[0]
    if doc.get("uploaded_by") and doc["uploaded_by"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    storage_path = doc.get("storage_path")
    if not storage_path or not os.path.exists(storage_path):
        raise HTTPException(status_code=404, detail="File not found on storage volume")

    content_type = (
        doc.get("file_type")
        or mimetypes.guess_type(doc.get("filename", ""))[0]
        or "application/octet-stream"
    )

    with open(storage_path, "rb") as f:
        data = f.read()

    return FastAPIResponse(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{doc.get("filename", "document")}"',
            "Content-Length": str(len(data)),
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Stats (mirrors /brain/stats)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_kb_stats(user_id: str = Depends(get_current_user_id)):
    """Return knowledge base statistics."""
    from api.routes.brain import get_brain_stats
    return await get_brain_stats(user_id=user_id)
