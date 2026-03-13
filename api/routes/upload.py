"""
Unified File Upload Routes
==========================

Secure file upload endpoints using Supabase Storage.

Features:
- Magic byte validation (not just extension)
- File size limits per bucket
- Content hash deduplication
- Presigned URLs for direct client upload
- Automatic text extraction for indexing
"""

import logging
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel

from api.dependencies import get_current_user_id
from core.storage import (
    get_storage_helper, 
    StorageError, 
    FileTypeValidationError,
)
from db.supabase_client import get_supabase

router = APIRouter(prefix="/upload", tags=["Upload"])
logger = logging.getLogger(__name__)


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class UploadUrlRequest(BaseModel):
    filename: str
    bucket: str = "user-uploads"
    content_type: Optional[str] = None


class UploadUrlResponse(BaseModel):
    upload_id: str
    bucket: str
    storage_path: str
    filename: str
    max_size: int
    instructions: dict


class FileInfo(BaseModel):
    id: str
    user_id: str
    bucket_id: str
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
# UPLOAD URL ENDPOINT (for large files / client-side upload)
# ============================================================================

@router.post("/url", response_model=UploadUrlResponse)
async def get_upload_url(
    request: UploadUrlRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Get upload info for direct client upload.
    
    Use this for large files to avoid server bottleneck.
    Client uploads directly to Supabase Storage.
    
    Flow:
    1. Call this endpoint to get upload instructions
    2. Client uploads file using Supabase JS SDK
    3. Call /confirm to register file in database
    """
    storage = get_storage_helper()
    
    try:
        result = await storage.get_upload_url(
            user_id=user_id,
            bucket=request.bucket,
            filename=request.filename,
            content_type=request.content_type,
        )
        return UploadUrlResponse(**result)
    except StorageError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# DIRECT UPLOAD ENDPOINT (for small files)
# ============================================================================

@router.post("/direct", response_model=FileInfo)
async def upload_file_direct(
    file: UploadFile = File(...),
    bucket: str = Form("user-uploads"),
    user_id: str = Depends(get_current_user_id),
):
    """
    Upload a file directly through the server.
    
    For small files (<10MB). Large files should use /url endpoint.
    
    Security:
    - File type validated by magic bytes (not just extension)
    - File size enforced per bucket
    - Content hash for deduplication
    """
    # Read file content
    content = await file.read()
    
    # Validate file size for direct upload
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="File too large for direct upload (>10MB). Use /upload/url endpoint for larger files."
        )
    
    storage = get_storage_helper()
    
    try:
        result = await storage.upload_file(
            user_id=user_id,
            bucket=bucket,
            filename=file.filename or "unknown",
            content=content,
            content_type=file.content_type,
        )
        
        # Get download URL
        download_url = None
        try:
            file_record = await storage.get_file(result["id"], user_id)
            download_url = file_record.get("download_url") if file_record else None
        except Exception:
            pass
        
        return FileInfo(
            id=result["id"],
            user_id=result["user_id"],
            bucket_id=result["bucket_id"],
            storage_path=result["storage_path"],
            original_filename=result["original_filename"],
            content_type=result.get("content_type"),
            file_size=result.get("file_size"),
            status=result.get("status", "uploaded"),
            content_hash=result.get("content_hash"),
            created_at=result.get("created_at", datetime.utcnow().isoformat()),
            download_url=download_url,
        )
        
    except FileTypeValidationError as e:
        raise HTTPException(status_code=415, detail=str(e))
    except StorageError as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")


# ============================================================================
# CONFIRM UPLOAD (after client-side upload)
# ============================================================================

@router.post("/confirm", response_model=FileInfo)
async def confirm_upload(
    upload_id: str = Form(...),
    file_size: Optional[int] = Form(None),
    user_id: str = Depends(get_current_user_id),
):
    """
    Confirm a client-side upload and register in database.
    
    Call this after uploading via Supabase JS SDK using
    the info from /upload/url endpoint.
    """
    storage = get_storage_helper()
    
    try:
        result = await storage.confirm_upload(
            upload_id=upload_id,
            user_id=user_id,
            file_size=file_size,
        )
        
        return FileInfo(
            id=result["id"],
            user_id=result["user_id"],
            bucket_id=result["bucket_id"],
            storage_path=result["storage_path"],
            original_filename=result["original_filename"],
            content_type=result.get("content_type"),
            file_size=result.get("file_size"),
            status=result.get("status", "uploaded"),
            content_hash=result.get("content_hash"),
            created_at=result.get("created_at", datetime.utcnow().isoformat()),
        )
        
    except StorageError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# LIST FILES
# ============================================================================

@router.get("/files", response_model=FileListResponse)
async def list_files(
    bucket: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id),
):
    """List all uploaded files for the current user."""
    storage = get_storage_helper()
    files = await storage.list_files(user_id, bucket, limit, offset)
    
    file_infos = [
        FileInfo(
            id=f["id"],
            user_id=f["user_id"],
            bucket_id=f["bucket_id"],
            storage_path=f["storage_path"],
            original_filename=f["original_filename"],
            content_type=f.get("content_type"),
            file_size=f.get("file_size"),
            status=f.get("status", "uploaded"),
            content_hash=f.get("content_hash"),
            created_at=f.get("created_at", ""),
        )
        for f in files
    ]
    
    return FileListResponse(files=file_infos, total=len(file_infos))


# ============================================================================
# GET FILE INFO
# ============================================================================

@router.get("/files/{file_id}", response_model=FileInfo)
async def get_file_info(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get file info and download URL."""
    storage = get_storage_helper()
    file_info = await storage.get_file(file_id, user_id)
    
    if not file_info:
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileInfo(
        id=file_info["id"],
        user_id=file_info["user_id"],
        bucket_id=file_info["bucket_id"],
        storage_path=file_info["storage_path"],
        original_filename=file_info["original_filename"],
        content_type=file_info.get("content_type"),
        file_size=file_info.get("file_size"),
        status=file_info.get("status", "uploaded"),
        content_hash=file_info.get("content_hash"),
        created_at=file_info.get("created_at", ""),
        download_url=file_info.get("download_url"),
    )


# ============================================================================
# DOWNLOAD FILE
# ============================================================================

@router.get("/files/{file_id}/download")
async def download_file(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Download file content."""
    storage = get_storage_helper()
    content = await storage.get_file_content(file_id, user_id)
    
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_info = await storage.get_file(file_id, user_id)
    
    from fastapi.responses import Response
    return Response(
        content=content,
        media_type=file_info.get("content_type", "application/octet-stream"),
        headers={
            "Content-Disposition": f'attachment; filename="{file_info["original_filename"]}"'
        }
    )


# ============================================================================
# DELETE FILE
# ============================================================================

@router.delete("/files/{file_id}")
async def delete_file(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a file from storage and database."""
    storage = get_storage_helper()
    deleted = await storage.delete_file(file_id, user_id)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="File not found")
    
    return {"status": "deleted", "file_id": file_id}


# ============================================================================
# EXTRACT TEXT
# ============================================================================

@router.post("/files/{file_id}/extract")
async def extract_text(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Extract text content from a file for indexing/analysis."""
    storage = get_storage_helper()
    text = await storage.extract_text(file_id, user_id)
    
    if text is None:
        raise HTTPException(
            status_code=400, 
            detail="Could not extract text from this file type or file not found"
        )
    
    # Update the file record with extracted text
    db = get_supabase()
    db.table("file_uploads").update({
        "extracted_text": text,
        "status": "ready",
        "processed_at": datetime.utcnow().isoformat(),
    }).eq("id", file_id).execute()
    
    return {
        "file_id": file_id,
        "text_length": len(text),
        "text_preview": text[:500] + "..." if len(text) > 500 else text,
    }


# ============================================================================
# BUCKET INFO
# ============================================================================

@router.get("/buckets")
async def list_buckets():
    """List available storage buckets and their limits."""
    from core.storage import ALLOWED_MIME_TYPES, MAX_FILE_SIZES
    
    buckets = []
    for bucket_id, max_size in MAX_FILE_SIZES.items():
        allowed = ALLOWED_MIME_TYPES.get(bucket_id)
        buckets.append({
            "id": bucket_id,
            "max_size_bytes": max_size,
            "max_size_mb": max_size / (1024 * 1024),
            "allowed_types": allowed if allowed else "All types",
        })
    
    return {"buckets": buckets}


# ============================================================================
# LINK FILE TO CONVERSATION
# ============================================================================

@router.post("/files/{file_id}/link/{conversation_id}")
async def link_file_to_conversation(
    file_id: str,
    conversation_id: str,
    purpose: str = "reference",
    user_id: str = Depends(get_current_user_id),
):
    """Link an uploaded file to a conversation."""
    db = get_supabase()
    
    # Verify file ownership
    storage = get_storage_helper()
    file_info = await storage.get_file(file_id, user_id)
    if not file_info:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Verify conversation ownership
    conv = db.table("conversations").select("id").eq("id", conversation_id).eq(
        "user_id", user_id
    ).execute()
    
    if not conv.data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Create link
    try:
        result = db.table("conversation_files").insert({
            "conversation_id": conversation_id,
            "file_id": file_id,
            "purpose": purpose,
        }).execute()
        
        return {"status": "linked", "file_id": file_id, "conversation_id": conversation_id}
        
    except Exception as e:
        # May already be linked
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            return {"status": "already_linked", "file_id": file_id, "conversation_id": conversation_id}
        raise HTTPException(status_code=500, detail=f"Failed to link file: {str(e)}")


@router.get("/conversations/{conversation_id}/files")
async def get_conversation_files(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get all files linked to a conversation."""
    db = get_supabase()
    
    # Verify conversation ownership
    conv = db.table("conversations").select("id").eq("id", conversation_id).eq(
        "user_id", user_id
    ).execute()
    
    if not conv.data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Get linked files
    result = db.table("conversation_files").select(
        "id, purpose, created_at, file_uploads(*)"
    ).eq("conversation_id", conversation_id).execute()
    
    files = []
    for row in result.data or []:
        file_data = row.get("file_uploads", {})
        if file_data:
            files.append({
                "link_id": row["id"],
                "purpose": row["purpose"],
                "linked_at": row["created_at"],
                "file": {
                    "id": file_data.get("id"),
                    "filename": file_data.get("original_filename"),
                    "content_type": file_data.get("content_type"),
                    "file_size": file_data.get("file_size"),
                    "status": file_data.get("status"),
                }
            })
    
    return {"conversation_id": conversation_id, "files": files}