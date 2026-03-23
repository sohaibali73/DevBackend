"""Brain/Knowledge Base routes.

Files are stored on the Railway volume via upload.py's helpers.
Supabase holds all metadata + chunk text (no binary blobs in Supabase).
"""

import os
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from pydantic import BaseModel

from api.dependencies import get_current_user_id, get_user_api_keys
from core.document_classifier import AIDocumentClassifier
from db.supabase_client import get_supabase

# Reuse the storage helpers from upload.py so files always land in the same place
from api.routes.upload import (
    _storage_path,
    _write_file,
    _delete_file,
    _extract_text,
    MAX_FILE_SIZE,
)

router = APIRouter(prefix="/brain", tags=["Knowledge Base"])
logger = logging.getLogger(__name__)


# ============================================================================
# MODELS
# ============================================================================

class TextUpload(BaseModel):
    title: str
    content: str
    category: str = "general"


class SearchRequest(BaseModel):
    query: str
    category: Optional[str] = None
    limit: int = 10


# ============================================================================
# UPLOAD DOCUMENT
# ============================================================================

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    category: Optional[str] = Form("general"),
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """Upload and index a document into the knowledge base.

    1. File bytes → Railway volume  ($STORAGE_ROOT/uploads/{user_id}/...)
    2. Metadata + extracted text → Supabase brain_documents
    3. Text chunks → Supabase brain_chunks
    """
    try:
        content_bytes = await file.read()

        if len(content_bytes) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large. Maximum size is 10 MB.")

        if not content_bytes.strip():
            raise HTTPException(status_code=400, detail="File is empty.")

        db = get_supabase()

        # ── Extract text ──────────────────────────────────────────────────────
        content = _extract_text(content_bytes, file.content_type or "", file.filename or "")
        content = content.replace("\x00", "")  # strip null bytes — Postgres rejects them
        if not content.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from this file.")

        # ── Deduplication ─────────────────────────────────────────────────────
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        existing = db.table("brain_documents").select("id").eq(
            "content_hash", content_hash
        ).limit(1).execute()

        if existing.data:
            return {
                "status": "duplicate",
                "document_id": existing.data[0]["id"],
                "message": "Document already exists in knowledge base",
            }

        # ── Save file to Railway volume ───────────────────────────────────────
        file_id = str(uuid.uuid4())
        storage_path = _storage_path(user_id, file_id, file.filename or "upload")
        try:
            _write_file(storage_path, content_bytes)
        except OSError as e:
            logger.error(f"Failed to write brain document to disk: {e}")
            raise HTTPException(status_code=500, detail="Storage error — could not save file.")

        # ── Classify ──────────────────────────────────────────────────────────
        final_category = category or "general"
        classification_data = {"subcategories": [], "tags": [], "summary": "", "confidence": 0}

        try:
            claude_key = api_keys.get("claude", "")
            if claude_key:
                classifier = AIDocumentClassifier(api_key=claude_key)
                classification = classifier.classify_document(content[:5000], file.filename)
                if category == "general" and hasattr(classification, "primary_category"):
                    final_category = classification.primary_category or "general"
                classification_data = {
                    "subcategories": getattr(classification, "subcategories", []),
                    "tags": getattr(classification, "suggested_tags", []),
                    "summary": getattr(classification, "summary", ""),
                    "confidence": getattr(classification, "confidence", 0),
                }
        except Exception as cls_err:
            logger.warning(f"Document classification failed (continuing): {cls_err}")

        # ── Insert brain_documents row ─────────────────────────────────────────
        now = datetime.now(timezone.utc).isoformat()
        doc_result = db.table("brain_documents").insert({
            "id": file_id,
            "uploaded_by": user_id,
            "title": title or file.filename,
            "filename": file.filename,
            "file_type": file.content_type,
            "file_size": len(content_bytes),
            "storage_path": storage_path,          # ← points to Railway volume
            "category": final_category,
            "subcategories": classification_data["subcategories"],
            "tags": classification_data["tags"],
            "raw_content": content,                 # extracted text kept in DB for search
            "summary": classification_data["summary"],
            "content_hash": content_hash,
            "source_type": "upload",
            "created_at": now,
        }).execute()

        document_id = doc_result.data[0]["id"]

        # ── Chunk for RAG ─────────────────────────────────────────────────────
        chunk_size = 500
        chunks = [content[i:i + chunk_size] for i in range(0, len(content), chunk_size)]
        chunks = chunks[:50]  # cap at 50 chunks

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
            "status": "success",
            "document_id": document_id,
            "storage_path": storage_path,
            "classification": {
                "category": final_category,
                "confidence": classification_data["confidence"],
                "summary": classification_data["summary"],
            },
            "chunks_created": len(chunks),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Brain upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")


# ============================================================================
# BATCH UPLOAD
# ============================================================================

@router.post("/upload-batch")
async def upload_documents_batch(
    files: List[UploadFile] = File(...),
    category: Optional[str] = Form("general"),
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """Upload and index multiple documents at once."""
    db = get_supabase()

    classifier = None
    try:
        claude_key = api_keys.get("claude", "")
        if claude_key:
            classifier = AIDocumentClassifier(api_key=claude_key)
    except Exception:
        pass

    results = []
    successful = duplicates = failed = 0

    for file in files:
        try:
            content_bytes = await file.read()
            content = _extract_text(content_bytes, file.content_type or "", file.filename or "")
            content = content.replace("\x00", "")  # strip null bytes — Postgres rejects them
            content_hash = hashlib.sha256(content_bytes).hexdigest()

            # Dedup
            existing = db.table("brain_documents").select("id").eq(
                "content_hash", content_hash
            ).limit(1).execute()
            if existing.data:
                duplicates += 1
                results.append({
                    "filename": file.filename,
                    "status": "duplicate",
                    "document_id": existing.data[0]["id"],
                })
                continue

            # Save to disk
            file_id = str(uuid.uuid4())
            storage_path = _storage_path(user_id, file_id, file.filename or "upload")
            _write_file(storage_path, content_bytes)

            # Classify
            final_category = category or "general"
            classification_data = {"subcategories": [], "tags": [], "summary": "", "confidence": 0}
            if classifier:
                try:
                    cl = classifier.classify_document(content[:5000], file.filename)
                    if category == "general" and hasattr(cl, "primary_category"):
                        final_category = cl.primary_category or "general"
                    classification_data = {
                        "subcategories": getattr(cl, "subcategories", []),
                        "tags": getattr(cl, "suggested_tags", []),
                        "summary": getattr(cl, "summary", ""),
                        "confidence": getattr(cl, "confidence", 0),
                    }
                except Exception as cls_err:
                    logger.warning(f"Classification failed for {file.filename}: {cls_err}")

            now = datetime.now(timezone.utc).isoformat()
            doc_result = db.table("brain_documents").insert({
                "id": file_id,
                "uploaded_by": user_id,
                "title": file.filename,
                "filename": file.filename,
                "file_type": file.content_type,
                "file_size": len(content_bytes),
                "storage_path": storage_path,
                "category": final_category,
                "subcategories": classification_data["subcategories"],
                "tags": classification_data["tags"],
                "raw_content": content,
                "summary": classification_data["summary"],
                "content_hash": content_hash,
                "source_type": "upload",
                "created_at": now,
            }).execute()

            document_id = doc_result.data[0]["id"]

            chunk_size = 500
            chunks = [content[i:i + chunk_size] for i in range(0, len(content), chunk_size)][:50]
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

            successful += 1
            results.append({
                "filename": file.filename,
                "status": "success",
                "document_id": document_id,
                "classification": {
                    "category": final_category,
                    "confidence": classification_data["confidence"],
                    "summary": classification_data["summary"],
                },
                "chunks_created": len(chunks),
            })

        except Exception as e:
            failed += 1
            results.append({"filename": file.filename, "status": "error", "error": str(e)})

    return {
        "status": "completed",
        "summary": {
            "total": len(files),
            "successful": successful,
            "duplicates": duplicates,
            "failed": failed,
        },
        "results": results,
    }


# ============================================================================
# UPLOAD TEXT
# ============================================================================

@router.post("/upload-text")
async def upload_text(
    data: TextUpload,
    user_id: str = Depends(get_current_user_id),
):
    """Upload raw text directly (no file needed)."""
    db = get_supabase()
    content_hash = hashlib.sha256(data.content.encode()).hexdigest()

    existing = db.table("brain_documents").select("id").eq(
        "content_hash", content_hash
    ).limit(1).execute()
    if existing.data:
        return {"status": "duplicate", "document_id": existing.data[0]["id"]}

    now = datetime.now(timezone.utc).isoformat()
    doc_result = db.table("brain_documents").insert({
        "uploaded_by": user_id,
        "title": data.title,
        "category": data.category,
        "raw_content": data.content,
        "content_hash": content_hash,
        "source_type": "text",
        "file_type": "text/plain",
        "is_processed": True,
        "created_at": now,
    }).execute()

    return {"status": "success", "document_id": doc_result.data[0]["id"]}


# ============================================================================
# SEARCH
# ============================================================================

@router.post("/search")
async def search_knowledge(
    data: SearchRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Search the knowledge base (vector if embeddings exist, otherwise full-text)."""
    db = get_supabase()

    try:
        # ── Try vector search ─────────────────────────────────────────────────
        try:
            embedding_check = db.table("brain_chunks").select("id").not_.is_(
                "embedding", "null"
            ).limit(1).execute()
            has_embeddings = bool(embedding_check.data)
        except Exception:
            has_embeddings = False

        if has_embeddings:
            try:
                query_embedding = _generate_embedding(data.query)
                if query_embedding:
                    vector_result = db.rpc("match_brain_chunks", {
                        "query_embedding": query_embedding,
                        "match_threshold": 0.5,
                        "match_count": data.limit,
                    }).execute()

                    if vector_result.data:
                        doc_ids = list({r["document_id"] for r in vector_result.data})
                        docs = db.table("brain_documents").select(
                            "id, title, category, summary"
                        ).in_("id", doc_ids).execute()
                        doc_map = {d["id"]: d for d in docs.data}

                        results = [
                            {
                                "id": chunk["document_id"],
                                "title": doc_map.get(chunk["document_id"], {}).get("title", "Unknown"),
                                "category": doc_map.get(chunk["document_id"], {}).get("category", "general"),
                                "summary": doc_map.get(chunk["document_id"], {}).get("summary", ""),
                                "content_snippet": chunk["content"][:300],
                                "similarity": round(chunk["similarity"], 3),
                                "search_type": "vector",
                            }
                            for chunk in vector_result.data
                        ]
                        return {"results": results, "count": len(results), "search_type": "vector"}
            except Exception as vec_err:
                logger.debug(f"Vector search failed, falling back to text: {vec_err}")

        # ── Fallback: full-text search ─────────────────────────────────────────
        search_term = data.query.replace("'", "''")
        query = db.table("brain_documents").select("id, title, category, summary, created_at")
        if data.category:
            query = query.eq("category", data.category)
        query = query.or_(
            f"title.ilike.%{search_term}%,"
            f"summary.ilike.%{search_term}%,"
            f"raw_content.ilike.%{search_term}%"
        )
        result = query.limit(data.limit).execute()

        return {"results": result.data, "count": len(result.data), "search_type": "text"}

    except Exception as e:
        logger.error(f"Knowledge base search error: {e}")
        return {"results": [], "count": 0, "error": str(e)}


# ============================================================================
# LIST DOCUMENTS
# ============================================================================

@router.get("/documents")
async def list_documents(
    category: Optional[str] = None,
    limit: int = 50,
    user_id: str = Depends(get_current_user_id),
):
    """List all documents in the knowledge base."""
    db = get_supabase()
    query = db.table("brain_documents").select(
        "id, title, filename, category, tags, summary, file_size, created_at, chunk_count, storage_path"
    )
    if category:
        query = query.eq("category", category)
    result = query.order("created_at", desc=True).limit(limit).execute()
    return result.data


# ============================================================================
# STATS
# ============================================================================

@router.get("/stats")
async def get_brain_stats(user_id: str = Depends(get_current_user_id)):
    """Return knowledge base statistics."""
    db = get_supabase()

    docs = db.table("brain_documents").select("id", count="exact").execute()

    # brain_chunks count — graceful fallback if table missing
    try:
        chunks = db.table("brain_chunks").select("id", count="exact").execute()
        total_chunks = chunks.count or 0
    except Exception:
        total_chunks = 0

    try:
        learnings = db.table("learnings").select("id", count="exact").execute()
        total_learnings = learnings.count or 0
    except Exception:
        total_learnings = 0

    categories_result = db.table("brain_documents").select("category, file_size").execute()
    category_counts: dict = {}
    total_size = 0
    for doc in categories_result.data or []:
        cat = doc.get("category", "general")
        category_counts[cat] = category_counts.get(cat, 0) + 1
        total_size += doc.get("file_size", 0) or 0

    # Also report actual disk usage from Railway volume
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
        "total_documents": docs.count or 0,
        "total_size": total_size,
        "total_size_on_disk_mb": round(disk_bytes / (1024 * 1024), 2),
        "total_chunks": total_chunks,
        "total_learnings": total_learnings,
        "categories": category_counts,
    }


# ============================================================================
# DELETE DOCUMENT
# ============================================================================

@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a document and its file from the Railway volume."""
    db = get_supabase()

    result = db.table("brain_documents").select("storage_path").eq(
        "id", document_id
    ).limit(1).execute()

    if result.data and result.data[0].get("storage_path"):
        _delete_file(result.data[0]["storage_path"])

    # Chunks deleted via CASCADE in Supabase
    db.table("brain_documents").delete().eq("id", document_id).execute()

    return {"status": "deleted", "document_id": document_id}


# ============================================================================
# EMBEDDING HELPER (unchanged from original)
# ============================================================================

def _generate_embedding(text: str) -> Optional[list]:
    """Generate embedding vector using Voyage AI if available."""
    voyage_key = os.getenv("VOYAGE_API_KEY")
    if not voyage_key:
        return None

    try:
        import json
        import urllib.request

        payload = json.dumps({"input": [text[:8000]], "model": "voyage-2"}).encode()
        req = urllib.request.Request(
            "https://api.voyageai.com/v1/embeddings",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {voyage_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
        return result["data"][0]["embedding"]
    except Exception as e:
        logger.debug(f"Voyage embedding failed: {e}")
        return None

# ============================================================================
# GET DOCUMENT CONTENT (raw bytes for client-side parsing)
# ============================================================================

@router.get("/documents/{document_id}/content")
async def get_document_content(
    document_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Return the original uploaded file bytes for client-side parsing.
    
    The frontend uses mammoth, pdfjs-dist, papaparse, and xlsx to parse
    the raw bytes client-side.
    """
    from fastapi.responses import Response as FastAPIResponse
    import mimetypes

    db = get_supabase()
    result = db.table("brain_documents").select(
        "storage_path, filename, file_type, uploaded_by"
    ).eq("id", document_id).limit(1).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")

    row = result.data[0]

    # Security: only owner can access
    if row.get("uploaded_by") and row["uploaded_by"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    storage_path = row.get("storage_path")
    if not storage_path or not os.path.exists(storage_path):
        raise HTTPException(status_code=404, detail="File not found on storage volume")

    content_type = row.get("file_type") or mimetypes.guess_type(row.get("filename", ""))[0] or "application/octet-stream"

    with open(storage_path, "rb") as f:
        data = f.read()

    return FastAPIResponse(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{row.get("filename", "document")}"',
            "Content-Length": str(len(data)),
        },
    )


# ============================================================================
# DOWNLOAD ORIGINAL FILE FROM RAILWAY VOLUME
# ============================================================================

@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Stream the original file binary from the Railway volume."""
    from fastapi.responses import Response as FastAPIResponse
    import mimetypes

    db = get_supabase()
    result = db.table("brain_documents").select(
        "storage_path, filename, file_type, uploaded_by"
    ).eq("id", document_id).limit(1).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found.")

    row = result.data[0]

    # Security: only owner can download
    if row.get("uploaded_by") and row["uploaded_by"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    storage_path = row.get("storage_path")
    if not storage_path or not os.path.exists(storage_path):
        raise HTTPException(status_code=404, detail="File not found on storage volume.")

    content_type = row.get("file_type") or mimetypes.guess_type(row.get("filename", ""))[0] or "application/octet-stream"

    with open(storage_path, "rb") as f:
        data = f.read()

    return FastAPIResponse(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'inline; filename="{row.get("filename", "document")}"',
            "Content-Length": str(len(data)),
            "Cache-Control": "private, max-age=3600",
        },
    )


# ============================================================================
# GET SINGLE DOCUMENT (with raw_content for preview)
# ============================================================================

@router.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get a single document including raw_content for preview."""
    db = get_supabase()
    result = db.table("brain_documents").select("*").eq(
        "id", document_id
    ).limit(1).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found.")

    return result.data[0]