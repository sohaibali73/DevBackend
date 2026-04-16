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

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import JSONResponse
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
    _render_pptx_slides_to_disk,
    MAX_FILE_SIZE,
)

router = APIRouter(prefix="/brain", tags=["Knowledge Base"])
logger = logging.getLogger(__name__)


def _extract_text_from_bytes(content_bytes: bytes, content_type: str, filename: str) -> str:
    """Extract text from raw bytes by writing to a temp file, then calling the disk-based parser.
    
    The upload.py _extract_text() expects a file path. Brain routes receive raw bytes
    before saving to disk, so we bridge the gap with a temp file.
    """
    import tempfile
    suffix = os.path.splitext(filename)[1] if filename else ""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content_bytes)
            tmp_path = tmp.name
        return _extract_text(tmp_path)
    except Exception as e:
        logger.warning(f"Temp-file extraction failed for {filename}: {e}")
        return ""
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


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
# BACKGROUND DOCUMENT PROCESSOR
# ============================================================================

def _process_document_background(
    document_id: str,
    storage_path: str,
    content_bytes: bytes,
    content_type: str,
    filename: str,
    claude_key: str,
    user_id: str,
    category: str,
) -> None:
    """
    Blocking sync function — FastAPI runs this in a thread-pool executor so
    it never blocks the uvicorn event loop.

    Steps: extract text → classify → chunk → mark ready.
    On any failure the document row is updated with an error summary so the
    status endpoint can surface it to the frontend.
    """
    db = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    try:
        # ── Text extraction (PPTX now uses fast python-pptx path, <100 ms) ───
        content = _extract_text_from_bytes(content_bytes, content_type, filename)
        content = content.replace("\x00", "")  # strip null bytes — Postgres rejects them

        if not content.strip():
            db.table("brain_documents").update({
                "summary": "[ERROR: Could not extract text from this file]",
                "processed_at": now,
                "is_processed": False,
            }).eq("id", document_id).execute()
            logger.warning(f"Background extraction yielded no text for {filename} ({document_id})")
            return

        # ── Classification ────────────────────────────────────────────────────
        final_category = category
        classification_data: dict = {
            "subcategories": [], "tags": [], "summary": "", "confidence": 0,
        }
        if claude_key:
            try:
                classifier = AIDocumentClassifier(api_key=claude_key)
                cl = classifier.classify_document(content[:5000], filename)
                if category == "general" and hasattr(cl, "primary_category"):
                    final_category = cl.primary_category or "general"
                classification_data = {
                    "subcategories": getattr(cl, "subcategories", []),
                    "tags": getattr(cl, "suggested_tags", []),
                    "summary": getattr(cl, "summary", ""),
                    "confidence": getattr(cl, "confidence", 0),
                }
            except Exception as cls_err:
                logger.warning(f"Classification failed for {filename}: {cls_err}")

        # ── Update DB with extracted content + classification ─────────────────
        db.table("brain_documents").update({
            "raw_content": content,
            "category": final_category,
            "subcategories": classification_data["subcategories"],
            "tags": classification_data["tags"],
            "summary": classification_data["summary"],
        }).eq("id", document_id).execute()

        # ── Chunk for RAG ─────────────────────────────────────────────────────
        chunk_size = 500
        chunks = [content[i:i + chunk_size] for i in range(0, len(content), chunk_size)][:50]
        for idx, chunk_text in enumerate(chunks):
            db.table("brain_chunks").insert({
                "document_id": document_id,
                "chunk_index": idx,
                "content": chunk_text,
            }).execute()

        # ── Mark as ready ─────────────────────────────────────────────────────
        db.table("brain_documents").update({
            "is_processed": True,
            "chunk_count": len(chunks),
            "processed_at": now,
        }).eq("id", document_id).execute()

        logger.info(
            f"Background processing complete: {filename} → {len(chunks)} chunks "
            f"(doc_id={document_id})"
        )

    except Exception as e:
        logger.error(f"Background processing failed for {document_id}: {e}", exc_info=True)
        try:
            db.table("brain_documents").update({
                "summary": f"[ERROR: {str(e)[:200]}]",
                "processed_at": now,
                "is_processed": False,
            }).eq("id", document_id).execute()
        except Exception:
            pass  # DB unavailable — log already written
        return  # don't attempt slide rendering on error

    # ── Slide rendering for PPTX files (vision pipeline, runs after text is ready) ──
    # Stores PNGs at $STORAGE_ROOT/slide_previews/{document_id}/slide_NNN.png
    # These are used by chat.py to inject vision content blocks so the LLM can
    # literally see the slide design, layout, graphics, and branding.
    ext = os.path.splitext(filename)[1].lower()
    if ext in {".pptx", ".ppt"}:
        try:
            import asyncio
            asyncio.run(_render_pptx_slides_to_disk(document_id, content_bytes, filename))
        except Exception as slide_err:
            # Slide rendering is best-effort — text extraction is already done
            logger.warning(f"PPTX slide rendering step failed for {document_id}: {slide_err}")


# ============================================================================
# UPLOAD DOCUMENT  (async — returns 202 immediately, processes in background)
# ============================================================================

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    category: Optional[str] = Form("general"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """
    Upload and index a document into the knowledge base.

    Returns 202 immediately after saving the file to disk.
    Text extraction, classification, and chunking happen in a background
    thread so the HTTP request is never blocked by parsing.

    Poll GET /brain/documents/{id}/status to check processing progress.
    """
    try:
        content_bytes = await file.read()

        if len(content_bytes) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024*1024)} GB.",
            )

        if not content_bytes.strip():
            raise HTTPException(status_code=400, detail="File is empty.")

        db = get_supabase()

        # ── Deduplication (hash check before any heavy work) ──────────────────
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        existing = db.table("brain_documents").select("id, is_processed").eq(
            "content_hash", content_hash
        ).limit(1).execute()

        if existing.data:
            row = existing.data[0]
            return JSONResponse(
                status_code=200,
                content={
                    "status": "duplicate",
                    "document_id": row["id"],
                    "ready": row.get("is_processed", False),
                    "message": "Document already exists in knowledge base",
                },
            )

        # ── Save file to Railway volume immediately ────────────────────────────
        file_id = str(uuid.uuid4())
        storage_path = _storage_path(user_id, file_id, file.filename or "upload")
        try:
            _write_file(storage_path, content_bytes)
        except OSError as e:
            logger.error(f"Failed to write brain document to disk: {e}")
            raise HTTPException(status_code=500, detail="Storage error — could not save file.")

        # ── Insert placeholder DB row (processing not yet started) ────────────
        now = datetime.now(timezone.utc).isoformat()
        db.table("brain_documents").insert({
            "id": file_id,
            "uploaded_by": user_id,
            "title": title or file.filename,
            "filename": file.filename,
            "file_type": file.content_type,
            "file_size": len(content_bytes),
            "storage_path": storage_path,
            "category": category or "general",
            "content_hash": content_hash,
            "source_type": "upload",
            "is_processed": False,
            "created_at": now,
        }).execute()

        # ── Queue background processing (thread-pool, non-blocking) ──────────
        claude_key = api_keys.get("claude", "")
        background_tasks.add_task(
            _process_document_background,
            file_id,
            storage_path,
            content_bytes,
            file.content_type or "",
            file.filename or "upload",
            claude_key,
            user_id,
            category or "general",
        )

        logger.info(
            f"Accepted upload for background processing: {file.filename} "
            f"({len(content_bytes) // 1024} KB, doc_id={file_id})"
        )

        # ── Return 202 immediately ─────────────────────────────────────────────
        return JSONResponse(
            status_code=202,
            content={
                "status": "processing",
                "document_id": file_id,
                "ready": False,
                "message": (
                    "File saved. Text extraction and indexing are running in the background. "
                    "Poll GET /brain/documents/{id}/status for completion."
                ),
            },
        )

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
            content = _extract_text_from_bytes(content_bytes, file.content_type or "", file.filename or "")
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
# DOCUMENT PROCESSING STATUS  (poll after async upload)
# ============================================================================

@router.get("/documents/{document_id}/status")
async def get_document_status(
    document_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Poll the processing status of a document uploaded via POST /brain/upload.

    Response shape:
      { document_id, status: "processing"|"ready"|"error", ready: bool, ... }

    Status logic (no extra DB column needed):
      - is_processed=True                     → "ready"
      - is_processed=False, processed_at=null → "processing" (background task running)
      - is_processed=False, processed_at set  → "error" (task ran, extraction failed)
    """
    db = get_supabase()
    result = db.table("brain_documents").select(
        "id, title, filename, is_processed, processed_at, chunk_count, summary, file_size, file_type"
    ).eq("id", document_id).limit(1).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found.")

    doc = result.data[0]
    is_processed: bool = doc.get("is_processed", False)
    processed_at: Optional[str] = doc.get("processed_at")
    summary: str = doc.get("summary") or ""

    if is_processed:
        return {
            "document_id": document_id,
            "status": "ready",
            "ready": True,
            "title": doc.get("title"),
            "filename": doc.get("filename"),
            "file_size": doc.get("file_size"),
            "file_type": doc.get("file_type"),
            "chunk_count": doc.get("chunk_count", 0),
            "summary_preview": summary[:300] if summary and not summary.startswith("[ERROR") else "",
        }
    elif processed_at and summary.startswith("[ERROR"):
        # Background task ran and reported an error
        return {
            "document_id": document_id,
            "status": "error",
            "ready": False,
            "error": summary,
        }
    else:
        # Background task is still running (or hasn't started yet)
        return {
            "document_id": document_id,
            "status": "processing",
            "ready": False,
            "message": "Document is being indexed. Check back in a few seconds.",
        }


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