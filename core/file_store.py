"""
Persistent File Store — Supabase Storage + In-Memory Cache
===========================================================
Stores generated files (DOCX, PPTX, PDF, etc.) in Supabase Storage so they
persist across container restarts and Railway redeploys.

Architecture:
    1. WRITE PATH: store_file() → saves to in-memory cache AND Supabase Storage
    2. READ PATH:  get_file()   → checks memory cache → falls back to Supabase Storage
    3. Files persist FOREVER in Supabase Storage (no TTL)
    4. Memory cache acts as hot-read layer (evicted after 4 hours to save RAM)

Supabase Storage bucket: "generated-files"
    Path: {file_id}/{filename}

For Claude Files API files (file_xxx IDs), the download endpoint and preview
endpoint have their own fallback logic. This store handles tool-generated files.
"""

import uuid
import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

# ── Bucket configuration ──────────────────────────────────────────────────────
_BUCKET_NAME = "generated-files"
_bucket_verified = False
_bucket_lock = threading.Lock()


@dataclass
class FileEntry:
    """A stored file with metadata."""
    file_id: str
    filename: str
    file_type: str  # "docx", "pptx", "pdf", etc.
    data: bytes
    size_kb: float
    tool_name: str = ""
    created_at: float = field(default_factory=time.time)


# ── In-memory hot cache ──────────────────────────────────────────────────────
_file_cache: Dict[str, FileEntry] = {}

# Memory cache TTL (4 hours — just to save RAM, files are safe in Supabase)
_CACHE_TTL = 14400


# ── Supabase Storage Helpers ─────────────────────────────────────────────────

def _get_storage_client():
    """Get Supabase storage client."""
    try:
        from db.supabase_client import get_supabase
        db = get_supabase()
        return db.storage
    except Exception as e:
        logger.warning("Could not get Supabase storage client: %s", e)
        return None


def _ensure_bucket():
    """Ensure the generated-files bucket exists (creates if needed). Thread-safe."""
    global _bucket_verified
    if _bucket_verified:
        return True

    with _bucket_lock:
        if _bucket_verified:
            return True

        storage = _get_storage_client()
        if not storage:
            return False

        try:
            # Try to get bucket info — if it exists, we're good
            storage.get_bucket(_BUCKET_NAME)
            _bucket_verified = True
            logger.info("✓ Supabase Storage bucket '%s' verified", _BUCKET_NAME)
            return True
        except Exception:
            # Bucket doesn't exist — create it
            try:
                storage.create_bucket(
                    _BUCKET_NAME,
                    options={
                        "public": False,  # Private bucket — requires auth
                        "file_size_limit": 104857600,  # 100MB limit
                    },
                )
                _bucket_verified = True
                logger.info("✓ Created Supabase Storage bucket '%s'", _BUCKET_NAME)
                return True
            except Exception as create_err:
                # Might fail if bucket exists but list_buckets failed
                # or if we don't have admin permissions
                if "already exists" in str(create_err).lower() or "duplicate" in str(create_err).lower() or "409" in str(create_err):
                    _bucket_verified = True
                    logger.info("✓ Bucket '%s' already exists", _BUCKET_NAME)
                    return True
                logger.error("✗ Failed to create bucket '%s': %s", _BUCKET_NAME, create_err)
                return False


def _upload_to_supabase(entry: FileEntry):
    """Upload file bytes to Supabase Storage. Runs in background thread."""
    try:
        if not _ensure_bucket():
            logger.warning("Skipping Supabase upload — bucket not available")
            return

        storage = _get_storage_client()
        if not storage:
            return

        # Path: file_id/filename (e.g., "abc123/report.docx")
        storage_path = f"{entry.file_id}/{entry.filename}"

        # Determine MIME type
        mime_map = {
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "pdf": "application/pdf",
            "csv": "text/csv",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "json": "application/json",
            "txt": "text/plain",
            "png": "image/png",
            "jpg": "image/jpeg",
        }
        content_type = mime_map.get(entry.file_type, "application/octet-stream")

        # Upload (upsert to handle re-uploads)
        storage.from_(_BUCKET_NAME).upload(
            path=storage_path,
            file=entry.data,
            file_options={
                "content-type": content_type,
                "upsert": "true",
            },
        )
        logger.info(
            "✓ Persisted to Supabase Storage: %s (%s, %.1f KB)",
            storage_path, entry.file_type, entry.size_kb,
        )

    except Exception as e:
        error_str = str(e)
        # If the file already exists (duplicate), that's fine
        if "duplicate" in error_str.lower() or "already exists" in error_str.lower() or "409" in error_str:
            logger.debug("File already exists in Supabase Storage: %s", entry.file_id)
        else:
            logger.error("✗ Supabase Storage upload failed for %s: %s", entry.file_id, e)


def _download_from_supabase(file_id: str) -> Optional[FileEntry]:
    """Try to download a file from Supabase Storage by file_id."""
    try:
        if not _ensure_bucket():
            return None

        storage = _get_storage_client()
        if not storage:
            return None

        # List files in the file_id directory to find the filename
        files = storage.from_(_BUCKET_NAME).list(path=file_id)
        if not files or len(files) == 0:
            return None

        # Get the first file in the directory
        file_info = files[0]
        filename = file_info.get("name", f"download_{file_id}")
        storage_path = f"{file_id}/{filename}"

        # Download the file bytes
        data = storage.from_(_BUCKET_NAME).download(storage_path)
        if not data:
            return None

        # Infer file type from filename
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"

        entry = FileEntry(
            file_id=file_id,
            filename=filename,
            file_type=ext,
            data=data,
            size_kb=round(len(data) / 1024, 1),
            tool_name="supabase_storage",
        )

        logger.info(
            "✓ Retrieved from Supabase Storage: %s (%s, %.1f KB)",
            filename, ext, entry.size_kb,
        )

        # Cache in memory for fast subsequent reads
        _file_cache[file_id] = entry

        return entry

    except Exception as e:
        logger.debug("Supabase Storage download failed for %s: %s", file_id, e)
        return None


# ── Public API (same interface as before) ─────────────────────────────────────

def store_file(
    data: bytes,
    filename: str,
    file_type: str = "",
    tool_name: str = "",
    file_id: str = None,
) -> FileEntry:
    """
    Store file bytes persistently.

    1. Saves to in-memory cache (fast reads)
    2. Uploads to Supabase Storage in background thread (persistence)
    """
    if not file_id:
        file_id = str(uuid.uuid4())

    if not file_type:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
        file_type = ext

    entry = FileEntry(
        file_id=file_id,
        filename=filename,
        file_type=file_type,
        data=data,
        size_kb=round(len(data) / 1024, 1),
        tool_name=tool_name,
    )

    # 1. Store in memory cache (immediate)
    _file_cache[file_id] = entry
    logger.info("Stored file: %s (%s, %.1f KB) [memory + Supabase]", filename, file_type, entry.size_kb)

    # 2. Persist to Supabase Storage (background — don't block the response)
    upload_thread = threading.Thread(
        target=_upload_to_supabase,
        args=(entry,),
        daemon=True,
    )
    upload_thread.start()

    # 3. Prune old entries from memory cache (lazy cleanup)
    _prune_memory_cache()

    return entry


def get_file(file_id: str) -> Optional[FileEntry]:
    """
    Retrieve a file by ID.

    Priority:
        1. In-memory cache (instant)
        2. Supabase Storage (persistent, survives restarts)
        3. None (not found anywhere)
    """
    # 1. Check memory cache
    entry = _file_cache.get(file_id)
    if entry is not None:
        return entry

    # 2. Try Supabase Storage (persistent layer)
    entry = _download_from_supabase(file_id)
    if entry is not None:
        return entry

    # 3. Not found
    return None


def get_file_bytes(file_id: str) -> Optional[bytes]:
    """Get just the raw bytes for a file. Returns None if not found."""
    entry = get_file(file_id)
    return entry.data if entry else None


def list_files() -> list:
    """List all currently cached files (memory cache only for speed)."""
    _prune_memory_cache()
    return [
        {
            "file_id": e.file_id,
            "filename": e.filename,
            "file_type": e.file_type,
            "size_kb": e.size_kb,
            "tool_name": e.tool_name,
            "download_url": f"/files/{e.file_id}/download",
        }
        for e in _file_cache.values()
    ]


def _prune_memory_cache():
    """Remove old entries from memory cache (Supabase copy persists)."""
    now = time.time()
    expired = [
        fid for fid, e in _file_cache.items()
        if now - e.created_at > _CACHE_TTL
    ]
    for fid in expired:
        del _file_cache[fid]
    if expired:
        logger.debug(
            "Evicted %d files from memory cache (still in Supabase Storage)", len(expired)
        )
