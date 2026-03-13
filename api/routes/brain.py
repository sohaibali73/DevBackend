"""Brain/Knowledge Base routes."""

import hashlib
from typing import Optional, List
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from pydantic import BaseModel

from api.dependencies import get_current_user_id, get_user_api_keys
from core.document_parser import DocumentParser
from core.document_classifier import AIDocumentClassifier
from db.supabase_client import get_supabase

router = APIRouter(prefix="/brain", tags=["Knowledge Base"])

class TextUpload(BaseModel):
    title: str
    content: str
    category: str = "general"

class SearchRequest(BaseModel):
    query: str
    category: Optional[str] = None
    limit: int = 10

@router.post("/upload")
async def upload_document(
        file: UploadFile = File(...),
        title: Optional[str] = Form(None),
        category: Optional[str] = Form("general"),
        user_id: str = Depends(get_current_user_id),
        api_keys: dict = Depends(get_user_api_keys),
):
    """Upload and process a document."""
    try:
        db = get_supabase()

        # Read file content
        content_bytes = await file.read()
        
        # Check file size (limit to 10MB)
        if len(content_bytes) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large. Maximum size is 10MB.")

        # Try to parse based on file type
        try:
            content = content_bytes.decode("utf-8", errors="ignore")
        except:
            content = str(content_bytes)

        # Ensure content is not empty
        if not content or not content.strip():
            raise HTTPException(status_code=400, detail="File is empty or could not be read.")

        # Generate content hash for deduplication
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        # Check for duplicate
        existing = db.table("brain_documents").select("id").eq("content_hash", content_hash).execute()
        if existing.data:
            return {
                "status": "duplicate",
                "document_id": existing.data[0]["id"],
                "message": "Document already exists in knowledge base",
            }

        # Classify document (with graceful fallback if classifier fails)
        final_category = category or "general"
        classification_data = {
            "subcategories": [],
            "tags": [],
            "summary": "",
            "confidence": 0,
        }
        
        try:
            claude_key = api_keys.get("claude", "")
            if claude_key:
                classifier = AIDocumentClassifier(api_key=claude_key)
                classification = classifier.classify_document(content[:5000], file.filename)  # Limit content for classification
                if category == "general" and hasattr(classification, 'primary_category'):
                    final_category = classification.primary_category or "general"
                classification_data = {
                    "subcategories": getattr(classification, 'subcategories', []),
                    "tags": getattr(classification, 'suggested_tags', []),
                    "summary": getattr(classification, 'summary', ""),
                    "confidence": getattr(classification, 'confidence', 0),
                }
        except Exception as cls_err:
            # Classification failed - continue with defaults
            import logging
            logging.getLogger(__name__).warning(f"Document classification failed: {cls_err}")

        # Store document
        doc_result = db.table("brain_documents").insert({
            "uploaded_by": user_id,
            "title": title or file.filename,
            "filename": file.filename,
            "file_type": file.content_type,
            "file_size": len(content_bytes),
            "category": final_category,
            "subcategories": classification_data["subcategories"],
            "tags": classification_data["tags"],
            "raw_content": content,
            "summary": classification_data["summary"],
            "content_hash": content_hash,
            "source_type": "upload",
        }).execute()

        document_id = doc_result.data[0]["id"]

        # Chunk document for RAG (simple chunking for now)
        chunk_size = 500
        chunks = [content[i:i + chunk_size] for i in range(0, len(content), chunk_size)]

        for idx, chunk in enumerate(chunks[:50]):  # Limit chunks
            db.table("brain_chunks").insert({
                "document_id": document_id,
                "chunk_index": idx,
                "content": chunk,
            }).execute()

        # Update document
        db.table("brain_documents").update({
            "is_processed": True,
            "chunk_count": len(chunks),
            "processed_at": "now()",
        }).eq("id", document_id).execute()

        return {
            "status": "success",
            "document_id": document_id,
            "classification": {
                "category": final_category,
                "confidence": classification_data["confidence"],
                "summary": classification_data["summary"],
            },
            "chunks_created": min(len(chunks), 50),
        }
    
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/upload-batch")
async def upload_documents_batch(
        files: List[UploadFile] = File(...),
        category: Optional[str] = Form("general"),
        user_id: str = Depends(get_current_user_id),
        api_keys: dict = Depends(get_user_api_keys),
):
    """Upload and process multiple documents at once."""
    db = get_supabase()
    classifier = AIDocumentClassifier(api_key=api_keys.get("claude", ""))
    
    results = []
    successful = 0
    duplicates = 0
    failed = 0
    
    for file in files:
        try:
            # Read file content
            content_bytes = await file.read()
            
            # Try to parse based on file type
            try:
                content = content_bytes.decode("utf-8", errors="ignore")
            except:
                content = str(content_bytes)
            
            # Generate content hash for deduplication
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            
            # Check for duplicate
            existing = db.table("brain_documents").select("id").eq("content_hash", content_hash).execute()
            if existing.data:
                duplicates += 1
                results.append({
                    "filename": file.filename,
                    "status": "duplicate",
                    "document_id": existing.data[0]["id"],
                    "message": "Document already exists in knowledge base",
                })
                continue
            
            # Classify document
            classification = classifier.classify_document(content, file.filename)
            
            # Use provided category or classified category
            final_category = category if category != "general" else classification.primary_category
            
            # Store document
            doc_result = db.table("brain_documents").insert({
                "uploaded_by": user_id,
                "title": file.filename,
                "filename": file.filename,
                "file_type": file.content_type,
                "file_size": len(content_bytes),
                "category": final_category,
                "subcategories": classification.subcategories,
                "tags": classification.suggested_tags,
                "raw_content": content,
                "summary": classification.summary,
                "content_hash": content_hash,
                "source_type": "upload",
            }).execute()
            
            document_id = doc_result.data[0]["id"]
            
            # Chunk document for RAG (simple chunking for now)
            chunk_size = 500
            chunks = [content[i:i + chunk_size] for i in range(0, len(content), chunk_size)]
            
            for idx, chunk in enumerate(chunks[:50]):  # Limit chunks
                db.table("brain_chunks").insert({
                    "document_id": document_id,
                    "chunk_index": idx,
                    "content": chunk,
                }).execute()
            
            # Update document
            db.table("brain_documents").update({
                "is_processed": True,
                "chunk_count": len(chunks),
                "processed_at": "now()",
            }).eq("id", document_id).execute()
            
            successful += 1
            results.append({
                "filename": file.filename,
                "status": "success",
                "document_id": document_id,
                "classification": {
                    "category": final_category,
                    "confidence": classification.confidence,
                    "summary": classification.summary,
                },
                "chunks_created": min(len(chunks), 50),
            })
            
        except Exception as e:
            failed += 1
            results.append({
                "filename": file.filename,
                "status": "error",
                "error": str(e),
            })
    
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


@router.post("/upload-text")
async def upload_text(
        data: TextUpload,
        user_id: str = Depends(get_current_user_id),
):
    """Upload text content directly."""
    db = get_supabase()

    content_hash = hashlib.sha256(data.content.encode()).hexdigest()

    # Check duplicate
    existing = db.table("brain_documents").select("id").eq("content_hash", content_hash).execute()
    if existing.data:
        return {"status": "duplicate", "document_id": existing.data[0]["id"]}

    doc_result = db.table("brain_documents").insert({
        "uploaded_by": user_id,
        "title": data.title,
        "category": data.category,
        "raw_content": data.content,
        "content_hash": content_hash,
        "source_type": "upload",
        "is_processed": True,
    }).execute()

    return {"status": "success", "document_id": doc_result.data[0]["id"]}

@router.post("/search")
async def search_knowledge(
        data: SearchRequest,
        user_id: str = Depends(get_current_user_id),
):
    """Search the knowledge base using text search (with vector search when embeddings available)."""
    db = get_supabase()

    try:
        # Try vector search first if embeddings exist
        try:
            # Check if any chunks have embeddings
            embedding_check = db.table("brain_chunks").select("id").not_.is_("embedding", "null").limit(1).execute()
            has_embeddings = bool(embedding_check.data)
        except Exception:
            has_embeddings = False

        if has_embeddings:
            # Try to generate query embedding for vector search
            try:
                query_embedding = _generate_embedding(data.query)
                if query_embedding:
                    # Use Supabase RPC for vector similarity search
                    vector_result = db.rpc("match_brain_chunks", {
                        "query_embedding": query_embedding,
                        "match_threshold": 0.5,
                        "match_count": data.limit,
                    }).execute()
                    
                    if vector_result.data:
                        # Enrich with document metadata
                        doc_ids = list(set(r["document_id"] for r in vector_result.data))
                        docs = db.table("brain_documents").select("id, title, category, summary").in_("id", doc_ids).execute()
                        doc_map = {d["id"]: d for d in docs.data}
                        
                        results = []
                        for chunk in vector_result.data:
                            doc = doc_map.get(chunk["document_id"], {})
                            results.append({
                                "id": chunk["document_id"],
                                "title": doc.get("title", "Unknown"),
                                "category": doc.get("category", "general"),
                                "summary": doc.get("summary", ""),
                                "content_snippet": chunk["content"][:300],
                                "similarity": round(chunk["similarity"], 3),
                                "search_type": "vector",
                            })
                        return {"results": results, "count": len(results), "search_type": "vector"}
            except Exception as vec_err:
                import logging
                logging.getLogger(__name__).debug(f"Vector search failed, falling back to text: {vec_err}")

        # Fallback: text-based search
        query = db.table("brain_documents").select("id, title, category, summary, created_at")

        if data.category:
            query = query.eq("category", data.category)

        # Search in title, summary, and raw_content
        search_term = data.query.replace("'", "''")  # Escape single quotes
        query = query.or_(f"title.ilike.%{search_term}%,summary.ilike.%{search_term}%,raw_content.ilike.%{search_term}%")

        result = query.limit(data.limit).execute()

        return {"results": result.data, "count": len(result.data), "search_type": "text"}
    
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Knowledge base search error: {e}")
        return {"results": [], "count": 0, "error": str(e)}


def _generate_embedding(text: str) -> list:
    """Generate embedding vector for text using Voyage AI or fallback.
    
    Returns a list of floats (1536 dimensions) or None if unavailable.
    Set VOYAGE_API_KEY environment variable for proper embeddings.
    """
    import os
    
    voyage_key = os.getenv("VOYAGE_API_KEY")
    if voyage_key:
        try:
            import urllib.request
            import json
            
            payload = json.dumps({
                "input": [text[:8000]],  # Voyage has 8k token limit
                "model": "voyage-2",
            })
            req = urllib.request.Request(
                "https://api.voyageai.com/v1/embeddings",
                data=payload.encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {voyage_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
            return result["data"][0]["embedding"]
        except Exception:
            pass
    
    # No embedding API available
    return None

@router.get("/documents")
async def list_documents(
        category: Optional[str] = None,
        limit: int = 50,
        user_id: str = Depends(get_current_user_id),
):
    """List all documents in the brain."""
    db = get_supabase()

    query = db.table("brain_documents").select(
        "id, title, filename, category, tags, summary, file_size, created_at, chunk_count"
    )

    if category:
        query = query.eq("category", category)

    result = query.order("created_at", desc=True).limit(limit).execute()

    return result.data

@router.get("/stats")
async def get_brain_stats(user_id: str = Depends(get_current_user_id)):
    """Get brain statistics."""
    db = get_supabase()

    docs = db.table("brain_documents").select("id", count="exact").execute()
    chunks = db.table("brain_chunks").select("id", count="exact").execute()
    
    try:
        learnings = db.table("learnings").select("id", count="exact").execute()
        total_learnings = learnings.count or 0
    except Exception:
        total_learnings = 0

    # Get category breakdown and total size
    categories = db.table("brain_documents").select("category, file_size").execute()
    category_counts = {}
    total_size = 0
    for doc in categories.data:
        cat = doc.get("category", "general")
        category_counts[cat] = category_counts.get(cat, 0) + 1
        total_size += doc.get("file_size", 0) or 0

    return {
        "total_documents": docs.count or 0,
        "total_size": total_size,
        "total_chunks": chunks.count or 0,
        "total_learnings": total_learnings,
        "categories": category_counts,
    }

@router.delete("/documents/{document_id}")
async def delete_document(
        document_id: str,
        user_id: str = Depends(get_current_user_id),
):
    """Delete a document from the brain."""
    db = get_supabase()

    # Chunks are deleted via CASCADE
    db.table("brain_documents").delete().eq("id", document_id).execute()

    return {"status": "deleted"}