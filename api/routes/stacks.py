"""
Knowledge Stacks Router — Msty-style RAG collections
=====================================================

Endpoints (all under /stacks):

    POST   /stacks                              Create a new stack
    GET    /stacks                              List all user stacks
    GET    /stacks/{id}                        Get one stack + settings
    PATCH  /stacks/{id}                        Update name / settings
    DELETE /stacks/{id}                        Delete stack (and its docs)
    POST   /stacks/{id}/upload                 Upload a single file into stack
    POST   /stacks/{id}/upload-batch           Upload multiple files at once
    GET    /stacks/{id}/documents              List docs in stack
    DELETE /stacks/{id}/documents/{doc_id}     Remove doc from stack
    POST   /stacks/{id}/documents/{doc_id}/move   Move doc to another stack
    POST   /stacks/{id}/search                 RAG search scoped to stack
    GET    /stacks/{id}/context                Pull context for chat injection

A stack stores its own RAG settings:

    {
        "chunk_size":          1500,    # chars per chunk
        "chunk_count":         20,      # top-K retrieved on search
        "overlap":             150,     # chunk overlap chars
        "load_mode":           "static",# "static" | "dynamic" | "sync"
        "generate_embeddings": true     # produce vectors at ingest time
    }
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.dependencies import get_current_user_id
from core.rag_chunker import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_OVERLAP,
    chunk_and_index,
    generate_embeddings_batch,
)
from db.supabase_client import get_supabase

# Reuse helpers from upload.py — single source of truth for storage layout
from api.routes.upload import (
    MAX_FILE_SIZE,
    _delete_file,
    _extract_text,
    _storage_path,
    _write_file,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stacks", tags=["Knowledge Stacks"])


# ────────────────────────────────────────────────────────────────────────────
# Default stack settings
# ────────────────────────────────────────────────────────────────────────────

DEFAULT_STACK_SETTINGS: Dict[str, Any] = {
    "chunk_size": DEFAULT_CHUNK_SIZE,
    "chunk_count": 20,
    "overlap": DEFAULT_OVERLAP,
    "load_mode": "static",
    "generate_embeddings": True,
}

ALLOWED_LOAD_MODES = {"static", "dynamic", "sync"}


# ────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ────────────────────────────────────────────────────────────────────────────


class StackSettings(BaseModel):
    chunk_size: int = Field(DEFAULT_CHUNK_SIZE, ge=200, le=8000)
    chunk_count: int = Field(20, ge=1, le=100)
    overlap: int = Field(DEFAULT_OVERLAP, ge=0, le=2000)
    load_mode: str = "static"
    generate_embeddings: bool = True


class CreateStackRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    icon: str = "📚"
    color: str = "#6366f1"
    settings: Optional[StackSettings] = None


class UpdateStackRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    settings: Optional[StackSettings] = None


class SearchRequest(BaseModel):
    query: str
    limit: Optional[int] = None  # falls back to stack settings.chunk_count


class MoveDocRequest(BaseModel):
    target_stack_id: str


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────


def _merge_settings(saved: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge saved settings on top of defaults — guarantees all keys present."""
    out = dict(DEFAULT_STACK_SETTINGS)
    if saved:
        for k, v in saved.items():
            if k in out and v is not None:
                out[k] = v
    if out.get("load_mode") not in ALLOWED_LOAD_MODES:
        out["load_mode"] = "static"
    return out


def _get_stack_or_404(db, stack_id: str, user_id: str) -> Dict[str, Any]:
    """Fetch stack, verifying ownership. Raises 404 / 403 on miss."""
    res = (
        db.table("knowledge_stacks")
        .select("*")
        .eq("id", stack_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Stack not found")

    stack = res.data[0]
    if stack.get("user_id") and stack["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    stack["settings"] = _merge_settings(stack.get("settings"))
    return stack


def _process_stack_upload_background(
    document_id: str,
    storage_path: str,
    content_bytes: bytes,
    filename: str,
    stack_settings: Dict[str, Any],
) -> None:
    """
    Background task: extract text → chunk → embed → batch insert → mark ready.

    Runs in FastAPI's thread-pool executor so the HTTP response is returned
    immediately. Errors are surfaced via brain_documents.summary so the
    status endpoint can report them.
    """
    db = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    try:
        # ── 1. Extract text from the file we just wrote to disk ──────────────
        text = _extract_text(storage_path)
        text = (text or "").replace("\x00", "").strip()

        if not text:
            db.table("brain_documents").update({
                "summary": "[ERROR: Could not extract any text from this file]",
                "processed_at": now,
                "is_processed": False,
            }).eq("id", document_id).execute()
            logger.warning(f"Stack upload extraction yielded no text: {filename}")
            return

        # ── 2. Update document with raw_content first ────────────────────────
        db.table("brain_documents").update({
            "raw_content": text,
        }).eq("id", document_id).execute()

        # ── 3. Smart chunk + (optional) embed + batch insert ─────────────────
        result = chunk_and_index(
            db=db,
            document_id=document_id,
            text=text,
            chunk_size=stack_settings.get("chunk_size", DEFAULT_CHUNK_SIZE),
            overlap=stack_settings.get("overlap", DEFAULT_OVERLAP),
            max_chunks=0,
            generate_embeddings=stack_settings.get("generate_embeddings", True),
        )

        # ── 4. Mark ready ────────────────────────────────────────────────────
        db.table("brain_documents").update({
            "is_processed": True,
            "chunk_count": result["chunks_created"],
            "processed_at": now,
        }).eq("id", document_id).execute()

        logger.info(
            f"Stack upload indexed: {filename} → "
            f"{result['chunks_created']} chunks, "
            f"{result['embeddings_generated']} embeddings"
        )

    except Exception as e:
        logger.error(f"Stack upload background failed for {document_id}: {e}", exc_info=True)
        try:
            db.table("brain_documents").update({
                "summary": f"[ERROR: {str(e)[:300]}]",
                "processed_at": now,
                "is_processed": False,
            }).eq("id", document_id).execute()
        except Exception:
            pass


# ────────────────────────────────────────────────────────────────────────────
# CRUD: Stacks
# ────────────────────────────────────────────────────────────────────────────


@router.post("")
async def create_stack(
    body: CreateStackRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Create a new Knowledge Stack."""
    db = get_supabase()

    settings = (body.settings.dict() if body.settings else dict(DEFAULT_STACK_SETTINGS))
    settings = _merge_settings(settings)

    try:
        result = db.table("knowledge_stacks").insert({
            "user_id": user_id,
            "name": body.name.strip(),
            "description": body.description.strip(),
            "icon": body.icon or "📚",
            "color": body.color or "#6366f1",
            "settings": settings,
        }).execute()
    except Exception as e:
        # Most likely: unique-name violation
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(
                status_code=409,
                detail=f"A stack named '{body.name}' already exists.",
            )
        logger.error(f"Stack create failed: {e}")
        raise HTTPException(status_code=500, detail=f"Could not create stack: {e}")

    stack = result.data[0]
    stack["settings"] = _merge_settings(stack.get("settings"))
    return stack


@router.get("")
async def list_stacks(
    user_id: str = Depends(get_current_user_id),
):
    """List all Knowledge Stacks for the current user."""
    db = get_supabase()
    result = (
        db.table("knowledge_stacks")
        .select("*")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )

    stacks = []
    for s in result.data or []:
        s["settings"] = _merge_settings(s.get("settings"))
        stacks.append(s)

    return {"stacks": stacks, "count": len(stacks)}


@router.get("/{stack_id}")
async def get_stack(
    stack_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get a single stack with its current settings."""
    db = get_supabase()
    return _get_stack_or_404(db, stack_id, user_id)


@router.patch("/{stack_id}")
async def update_stack(
    stack_id: str,
    body: UpdateStackRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Update stack name, description, icon, color, or settings."""
    db = get_supabase()
    stack = _get_stack_or_404(db, stack_id, user_id)

    update_fields: Dict[str, Any] = {}
    if body.name is not None:
        update_fields["name"] = body.name.strip()
    if body.description is not None:
        update_fields["description"] = body.description.strip()
    if body.icon is not None:
        update_fields["icon"] = body.icon
    if body.color is not None:
        update_fields["color"] = body.color
    if body.settings is not None:
        merged = _merge_settings({**stack["settings"], **body.settings.dict()})
        update_fields["settings"] = merged

    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        result = db.table("knowledge_stacks").update(update_fields).eq(
            "id", stack_id
        ).execute()
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail="That stack name is already in use.")
        raise HTTPException(status_code=500, detail=f"Update failed: {e}")

    updated = result.data[0] if result.data else stack
    updated["settings"] = _merge_settings(updated.get("settings"))
    return updated


@router.delete("/{stack_id}")
async def delete_stack(
    stack_id: str,
    cascade: bool = True,
    user_id: str = Depends(get_current_user_id),
):
    """
    Delete a stack.
    
    If cascade=True (default), also deletes all documents in the stack.
    If cascade=False, documents are unlinked but kept (stack_id set to NULL).
    """
    db = get_supabase()
    _get_stack_or_404(db, stack_id, user_id)

    if cascade:
        # Pull all docs to delete their files from disk
        docs = (
            db.table("brain_documents")
            .select("id, storage_path")
            .eq("stack_id", stack_id)
            .execute()
        )
        for d in docs.data or []:
            if d.get("storage_path"):
                _delete_file(d["storage_path"])
        # brain_chunks cascade via FK
        db.table("brain_documents").delete().eq("stack_id", stack_id).execute()

    db.table("knowledge_stacks").delete().eq("id", stack_id).execute()
    return {"status": "deleted", "stack_id": stack_id, "cascaded": cascade}


# ────────────────────────────────────────────────────────────────────────────
# File ingestion into a stack
# ────────────────────────────────────────────────────────────────────────────


@router.post("/{stack_id}/upload")
async def upload_to_stack(
    stack_id: str,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user_id: str = Depends(get_current_user_id),
):
    """
    Upload a single file into a Knowledge Stack.

    Returns 202 immediately. Text extraction, chunking, and embedding all
    happen in a background thread using the stack's own settings.
    """
    db = get_supabase()
    stack = _get_stack_or_404(db, stack_id, user_id)
    settings = stack["settings"]

    content_bytes = await file.read()

    if not content_bytes.strip():
        raise HTTPException(status_code=400, detail="File is empty.")
    if len(content_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum is {MAX_FILE_SIZE // (1024*1024*1024)} GB.",
        )

    # ── Dedup within stack (SHA-256 of bytes) ───────────────────────────────
    content_hash = hashlib.sha256(content_bytes).hexdigest()
    existing = (
        db.table("brain_documents")
        .select("id, is_processed")
        .eq("content_hash", content_hash)
        .eq("stack_id", stack_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        row = existing.data[0]
        return JSONResponse(
            status_code=200,
            content={
                "status": "duplicate",
                "document_id": row["id"],
                "stack_id": stack_id,
                "ready": row.get("is_processed", False),
                "message": "This file is already in the stack.",
            },
        )

    # ── Save to Railway volume ───────────────────────────────────────────────
    file_id = str(uuid.uuid4())
    storage_path = _storage_path(user_id, file_id, file.filename or "upload")
    try:
        _write_file(storage_path, content_bytes)
    except OSError as e:
        logger.error(f"Stack upload disk write failed: {e}")
        raise HTTPException(status_code=500, detail="Storage error — could not save file.")

    # ── Insert placeholder document row ──────────────────────────────────────
    now = datetime.now(timezone.utc).isoformat()
    db.table("brain_documents").insert({
        "id": file_id,
        "uploaded_by": user_id,
        "stack_id": stack_id,
        "title": title or file.filename,
        "filename": file.filename,
        "file_type": file.content_type,
        "file_size": len(content_bytes),
        "storage_path": storage_path,
        "category": "stack",
        "content_hash": content_hash,
        "source_type": "stack_upload",
        "is_processed": False,
        "created_at": now,
    }).execute()

    # ── Queue background processing (uses stack's settings) ──────────────────
    background_tasks.add_task(
        _process_stack_upload_background,
        file_id,
        storage_path,
        content_bytes,
        file.filename or "upload",
        settings,
    )

    return JSONResponse(
        status_code=202,
        content={
            "status": "processing",
            "document_id": file_id,
            "stack_id": stack_id,
            "ready": False,
            "message": "File uploaded; indexing in background.",
        },
    )


@router.post("/{stack_id}/upload-batch")
async def upload_batch_to_stack(
    stack_id: str,
    files: List[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user_id: str = Depends(get_current_user_id),
):
    """Upload multiple files into a stack at once. Returns 202 immediately."""
    db = get_supabase()
    stack = _get_stack_or_404(db, stack_id, user_id)
    settings = stack["settings"]

    results = []
    for file in files:
        try:
            content_bytes = await file.read()

            if not content_bytes.strip():
                results.append({"filename": file.filename, "status": "error", "error": "Empty file."})
                continue
            if len(content_bytes) > MAX_FILE_SIZE:
                results.append({"filename": file.filename, "status": "error", "error": "File too large."})
                continue

            content_hash = hashlib.sha256(content_bytes).hexdigest()
            existing = (
                db.table("brain_documents")
                .select("id")
                .eq("content_hash", content_hash)
                .eq("stack_id", stack_id)
                .limit(1)
                .execute()
            )
            if existing.data:
                results.append({
                    "filename": file.filename,
                    "status": "duplicate",
                    "document_id": existing.data[0]["id"],
                })
                continue

            file_id = str(uuid.uuid4())
            storage_path = _storage_path(user_id, file_id, file.filename or "upload")
            _write_file(storage_path, content_bytes)

            now = datetime.now(timezone.utc).isoformat()
            db.table("brain_documents").insert({
                "id": file_id,
                "uploaded_by": user_id,
                "stack_id": stack_id,
                "title": file.filename,
                "filename": file.filename,
                "file_type": file.content_type,
                "file_size": len(content_bytes),
                "storage_path": storage_path,
                "category": "stack",
                "content_hash": content_hash,
                "source_type": "stack_upload",
                "is_processed": False,
                "created_at": now,
            }).execute()

            background_tasks.add_task(
                _process_stack_upload_background,
                file_id,
                storage_path,
                content_bytes,
                file.filename or "upload",
                settings,
            )

            results.append({
                "filename": file.filename,
                "status": "processing",
                "document_id": file_id,
            })
        except Exception as e:
            logger.error(f"Batch stack upload failed for {file.filename}: {e}")
            results.append({"filename": file.filename, "status": "error", "error": str(e)})

    return JSONResponse(
        status_code=202,
        content={
            "stack_id": stack_id,
            "total": len(files),
            "queued": sum(1 for r in results if r["status"] == "processing"),
            "duplicates": sum(1 for r in results if r["status"] == "duplicate"),
            "errors": sum(1 for r in results if r["status"] == "error"),
            "results": results,
        },
    )


# ────────────────────────────────────────────────────────────────────────────
# Document management within a stack
# ────────────────────────────────────────────────────────────────────────────


@router.get("/{stack_id}/documents")
async def list_stack_documents(
    stack_id: str,
    limit: int = 100,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id),
):
    """List all documents in a stack with pagination."""
    db = get_supabase()
    _get_stack_or_404(db, stack_id, user_id)

    res = (
        db.table("brain_documents")
        .select(
            "id, title, filename, file_type, file_size, summary, "
            "tags, chunk_count, is_processed, processed_at, created_at"
        )
        .eq("stack_id", stack_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    total = (
        db.table("brain_documents")
        .select("id", count="exact")
        .eq("stack_id", stack_id)
        .execute()
    )

    return {
        "stack_id": stack_id,
        "documents": res.data or [],
        "total": total.count or 0,
        "has_more": (offset + limit) < (total.count or 0),
    }


@router.delete("/{stack_id}/documents/{document_id}")
async def remove_document_from_stack(
    stack_id: str,
    document_id: str,
    delete_file_too: bool = True,
    user_id: str = Depends(get_current_user_id),
):
    """Remove a document from a stack. Optionally also delete the file."""
    db = get_supabase()
    _get_stack_or_404(db, stack_id, user_id)

    res = (
        db.table("brain_documents")
        .select("storage_path, stack_id")
        .eq("id", document_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Document not found.")
    if res.data[0].get("stack_id") != stack_id:
        raise HTTPException(status_code=400, detail="Document is not in this stack.")

    if delete_file_too:
        if res.data[0].get("storage_path"):
            _delete_file(res.data[0]["storage_path"])
        db.table("brain_documents").delete().eq("id", document_id).execute()
        return {"status": "deleted", "document_id": document_id}

    # Otherwise just unlink from stack
    db.table("brain_documents").update({"stack_id": None}).eq("id", document_id).execute()
    return {"status": "unlinked", "document_id": document_id}


@router.post("/{stack_id}/documents/{document_id}/move")
async def move_document(
    stack_id: str,
    document_id: str,
    body: MoveDocRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Move a document from this stack to another stack."""
    db = get_supabase()
    _get_stack_or_404(db, stack_id, user_id)
    _get_stack_or_404(db, body.target_stack_id, user_id)

    res = (
        db.table("brain_documents")
        .select("stack_id")
        .eq("id", document_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Document not found.")
    if res.data[0].get("stack_id") != stack_id:
        raise HTTPException(status_code=400, detail="Document is not in source stack.")

    db.table("brain_documents").update({"stack_id": body.target_stack_id}).eq(
        "id", document_id
    ).execute()
    return {
        "status": "moved",
        "document_id": document_id,
        "from_stack": stack_id,
        "to_stack": body.target_stack_id,
    }


# ────────────────────────────────────────────────────────────────────────────
# RAG: search & context retrieval
# ────────────────────────────────────────────────────────────────────────────


def _stack_text_search(
    db, stack_id: str, query: str, limit: int
) -> List[Dict[str, Any]]:
    """Fallback text search within a stack — uses ILIKE on content."""
    safe = query.replace("'", "''")

    # Get all doc_ids for the stack
    docs = (
        db.table("brain_documents")
        .select("id, title, filename")
        .eq("stack_id", stack_id)
        .execute()
    )
    if not docs.data:
        return []

    doc_ids = [d["id"] for d in docs.data]
    doc_map = {d["id"]: d for d in docs.data}

    # Search chunks across those docs
    res = (
        db.table("brain_chunks")
        .select("id, document_id, chunk_index, content")
        .in_("document_id", doc_ids)
        .ilike("content", f"%{safe}%")
        .limit(limit)
        .execute()
    )

    return [
        {
            "chunk_id": r["id"],
            "document_id": r["document_id"],
            "document_title": doc_map.get(r["document_id"], {}).get("title", ""),
            "document_filename": doc_map.get(r["document_id"], {}).get("filename", ""),
            "chunk_index": r["chunk_index"],
            "content": r["content"],
            "similarity": None,
            "search_type": "text",
        }
        for r in res.data or []
    ]


@router.post("/{stack_id}/search")
async def search_stack(
    stack_id: str,
    body: SearchRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    RAG search scoped to a single stack.
    
    Tries vector search first (if embeddings exist for any chunk in the
    stack); otherwise falls back to ILIKE full-text search.
    """
    db = get_supabase()
    stack = _get_stack_or_404(db, stack_id, user_id)
    settings = stack["settings"]

    limit = body.limit or settings.get("chunk_count", 20)

    # ── Try vector search ────────────────────────────────────────────────────
    embeddings_exist = False
    try:
        check = (
            db.table("brain_chunks")
            .select("id")
            .not_.is_("embedding", "null")
            .limit(1)
            .execute()
        )
        embeddings_exist = bool(check.data)
    except Exception:
        embeddings_exist = False

    if embeddings_exist:
        try:
            qvecs = generate_embeddings_batch([body.query])
            qvec = qvecs[0] if qvecs else None
            if qvec:
                vec_res = db.rpc("match_stack_chunks", {
                    "p_stack_id": stack_id,
                    "query_embedding": qvec,
                    "match_threshold": 0.3,
                    "match_count": limit,
                }).execute()

                if vec_res.data:
                    doc_ids = list({r["document_id"] for r in vec_res.data})
                    docs = (
                        db.table("brain_documents")
                        .select("id, title, filename")
                        .in_("id", doc_ids)
                        .execute()
                    )
                    doc_map = {d["id"]: d for d in docs.data}

                    return {
                        "stack_id": stack_id,
                        "query": body.query,
                        "search_type": "vector",
                        "count": len(vec_res.data),
                        "results": [
                            {
                                "chunk_id": r["chunk_id"],
                                "document_id": r["document_id"],
                                "document_title": doc_map.get(r["document_id"], {}).get("title", ""),
                                "document_filename": doc_map.get(r["document_id"], {}).get("filename", ""),
                                "chunk_index": r["chunk_index"],
                                "content": r["content"],
                                "similarity": round(float(r["similarity"]), 4),
                                "search_type": "vector",
                            }
                            for r in vec_res.data
                        ],
                    }
        except Exception as e:
            logger.debug(f"Stack vector search failed, falling back to text: {e}")

    # ── Text search fallback ─────────────────────────────────────────────────
    results = _stack_text_search(db, stack_id, body.query, limit)
    return {
        "stack_id": stack_id,
        "query": body.query,
        "search_type": "text",
        "count": len(results),
        "results": results,
    }


@router.get("/{stack_id}/context")
async def get_stack_context(
    stack_id: str,
    query: Optional[str] = None,
    limit: Optional[int] = None,
    full_content: bool = False,
    user_id: str = Depends(get_current_user_id),
):
    """
    Pull stack context ready for chat injection.

    Modes:
    - query=...               → RAG mode: returns top-K relevant chunks
    - full_content=true       → Full Content Context: returns complete docs
    - neither                 → returns first N chunks across all docs
    """
    db = get_supabase()
    stack = _get_stack_or_404(db, stack_id, user_id)
    settings = stack["settings"]
    k = limit or settings.get("chunk_count", 20)

    # ── Full content mode (Msty's "Full Content Context") ────────────────────
    if full_content:
        docs = (
            db.table("brain_documents")
            .select("id, title, filename, raw_content, file_size, chunk_count")
            .eq("stack_id", stack_id)
            .execute()
        )
        documents = []
        total_chars = 0
        for d in docs.data or []:
            content = d.get("raw_content") or ""
            documents.append({
                "document_id": d["id"],
                "title": d.get("title"),
                "filename": d.get("filename"),
                "content": content,
                "char_count": len(content),
            })
            total_chars += len(content)

        return {
            "stack_id": stack_id,
            "stack_name": stack["name"],
            "mode": "full_content",
            "document_count": len(documents),
            "total_chars": total_chars,
            "documents": documents,
        }

    # ── RAG mode (query supplied) ────────────────────────────────────────────
    if query:
        search_result = await search_stack(
            stack_id, SearchRequest(query=query, limit=k), user_id
        )
        return {
            "stack_id": stack_id,
            "stack_name": stack["name"],
            "mode": "rag",
            "query": query,
            "search_type": search_result["search_type"],
            "chunk_count": search_result["count"],
            "chunks": search_result["results"],
        }

    # ── No query, no full content → return first K chunks of stack ──────────
    docs = (
        db.table("brain_documents")
        .select("id, title, filename")
        .eq("stack_id", stack_id)
        .execute()
    )
    if not docs.data:
        return {
            "stack_id": stack_id,
            "stack_name": stack["name"],
            "mode": "head",
            "chunk_count": 0,
            "chunks": [],
        }

    doc_ids = [d["id"] for d in docs.data]
    doc_map = {d["id"]: d for d in docs.data}

    chunks = (
        db.table("brain_chunks")
        .select("id, document_id, chunk_index, content")
        .in_("document_id", doc_ids)
        .order("chunk_index")
        .limit(k)
        .execute()
    )

    return {
        "stack_id": stack_id,
        "stack_name": stack["name"],
        "mode": "head",
        "chunk_count": len(chunks.data or []),
        "chunks": [
            {
                "chunk_id": r["id"],
                "document_id": r["document_id"],
                "document_title": doc_map.get(r["document_id"], {}).get("title", ""),
                "document_filename": doc_map.get(r["document_id"], {}).get("filename", ""),
                "chunk_index": r["chunk_index"],
                "content": r["content"],
            }
            for r in chunks.data or []
        ],
    }


# ────────────────────────────────────────────────────────────────────────────
# Reindex endpoint — re-chunk an existing doc with new settings
# ────────────────────────────────────────────────────────────────────────────


@router.post("/{stack_id}/reindex")
async def reindex_stack(
    stack_id: str,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user_id: str = Depends(get_current_user_id),
):
    """
    Re-chunk and re-embed all documents in a stack using the current settings.
    Useful after changing chunk_size / overlap / generate_embeddings.
    """
    db = get_supabase()
    stack = _get_stack_or_404(db, stack_id, user_id)
    settings = stack["settings"]

    docs = (
        db.table("brain_documents")
        .select("id, raw_content, filename, storage_path")
        .eq("stack_id", stack_id)
        .execute()
    )
    if not docs.data:
        return {"stack_id": stack_id, "queued": 0, "message": "Stack has no documents."}

    queued = 0
    for d in docs.data:
        # Wipe existing chunks
        try:
            db.table("brain_chunks").delete().eq("document_id", d["id"]).execute()
        except Exception as e:
            logger.warning(f"Could not delete chunks for {d['id']}: {e}")

        text = d.get("raw_content") or ""
        if not text.strip() and d.get("storage_path"):
            # Re-extract from disk if raw_content was wiped
            text = _extract_text(d["storage_path"]) or ""

        if not text.strip():
            continue

        background_tasks.add_task(
            _process_stack_upload_background,
            d["id"],
            d.get("storage_path") or "",
            b"",
            d.get("filename") or "",
            settings,
        )
        queued += 1

    return {"stack_id": stack_id, "queued": queued, "settings": settings}
