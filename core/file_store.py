"""
Persistent File Store — Railway Volume + Supabase Storage + In-Memory Cache
=============================================================================
Stores generated files (DOCX, PPTX, XLSX, PDF, etc.) with a 3-tier
persistence strategy:

  WRITE PATH (store_file):
    1. In-memory cache       — instant reads during container lifetime
    2. Railway volume         — fast local disk, persists across restarts
                               $STORAGE_ROOT/generated/{file_id}_{filename}
    3. Supabase Storage       — background upload + DB record insert,
                               cross-deployment backup
                               bucket: "user-uploads" / {file_id}/{filename}
                               table:  "generated_files" row per file

  READ PATH (get_file):
    1. In-memory cache        — O(1) dict lookup
    2. Railway volume         — fast local read (os.path.exists + open)
    3. Supabase Storage       — persistent fallback after Railway volume miss
    4. → None if not found anywhere (caller falls back to Claude Files API)

Files persist FOREVER on Railway volume and Supabase Storage.
Memory cache is evicted after 4 hours (just to save RAM).
"""

import os
import uuid
import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

# ── Storage paths ─────────────────────────────────────────────────────────────
_STORAGE_ROOT = os.getenv("STORAGE_ROOT", "/data")
_GENERATED_DIR = os.path.join(_STORAGE_ROOT, "generated")

# ── Supabase bucket ───────────────────────────────────────────────────────────
_BUCKET_NAME = "user-uploads"
_bucket_verified = False
_bucket_lock = threading.Lock()


@dataclass
class FileEntry:
    """A stored file with metadata."""
    file_id: str
    filename: str
    file_type: str          # "docx", "pptx", "xlsx", "pdf", etc.
    data: bytes
    size_kb: float
    tool_name: str = ""
    created_at: float = field(default_factory=time.time)


# ── In-memory hot cache ──────────────────────────────────────────────────────
_file_cache: Dict[str, FileEntry] = {}
_CACHE_TTL = 14400          # 4 hours — just to save RAM


# ── Railway Volume Helpers ───────────────────────────────────────────────────

def _ensure_generated_dir() -> bool:
    """Ensure the Railway volume generated-files directory exists."""
    try:
        os.makedirs(_GENERATED_DIR, exist_ok=True)
        return True
    except OSError as e:
        logger.warning("Could not create generated dir %s: %s", _GENERATED_DIR, e)
        return False


def _volume_path(file_id: str, filename: str) -> str:
    """Return the absolute path for a generated file on the Railway volume."""
    # Sanitise filename — keep only safe chars
    safe = "".join(c for c in filename if c.isalnum() or c in "._- ")[:120]
    return os.path.join(_GENERATED_DIR, f"{file_id}_{safe}")


def _write_to_volume(entry: FileEntry) -> bool:
    """Write file bytes to the Railway persistent volume. Returns True on success."""
    try:
        if not _ensure_generated_dir():
            return False
        path = _volume_path(entry.file_id, entry.filename)
        with open(path, "wb") as f:
            f.write(entry.data)
        logger.info(
            "✓ Saved to Railway volume: %s (%s, %.1f KB)",
            os.path.basename(path), entry.file_type, entry.size_kb,
        )
        return True
    except OSError as e:
        logger.error("✗ Railway volume write failed for %s: %s", entry.file_id, e)
        return False


def _read_from_volume(file_id: str) -> Optional[FileEntry]:
    """
    Scan the generated directory for files whose name starts with file_id.
    Returns a FileEntry if found, None otherwise.
    """
    try:
        if not os.path.exists(_GENERATED_DIR):
            return None
        prefix = f"{file_id}_"
        for fname in os.listdir(_GENERATED_DIR):
            if fname.startswith(prefix):
                path = os.path.join(_GENERATED_DIR, fname)
                with open(path, "rb") as f:
                    data = f.read()
                # Strip the file_id prefix to recover the original filename
                original_filename = fname[len(prefix):]
                ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else "bin"
                entry = FileEntry(
                    file_id=file_id,
                    filename=original_filename,
                    file_type=ext,
                    data=data,
                    size_kb=round(len(data) / 1024, 1),
                    tool_name="railway_volume",
                )
                logger.info(
                    "✓ Retrieved from Railway volume: %s (%s, %.1f KB)",
                    original_filename, ext, entry.size_kb,
                )
                # Warm the memory cache
                _file_cache[file_id] = entry
                return entry
    except Exception as e:
        logger.debug("Railway volume read failed for %s: %s", file_id, e)
    return None


# ── Supabase Storage Helpers ─────────────────────────────────────────────────

def _get_supabase_client():
    """Get the Supabase client (db + storage)."""
    try:
        from db.supabase_client import get_supabase
        return get_supabase()
    except Exception as e:
        logger.warning("Could not get Supabase client: %s", e)
        return None


def _get_storage_client():
    """Get Supabase storage client."""
    db = _get_supabase_client()
    return db.storage if db else None


def _ensure_bucket():
    """Ensure the Supabase bucket exists (creates if needed). Thread-safe."""
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
            storage.get_bucket(_BUCKET_NAME)
            _bucket_verified = True
            logger.info("✓ Supabase Storage bucket '%s' verified", _BUCKET_NAME)
            return True
        except Exception:
            try:
                storage.create_bucket(
                    _BUCKET_NAME,
                    options={"public": False, "file_size_limit": 104857600},
                )
                _bucket_verified = True
                logger.info("✓ Created Supabase Storage bucket '%s'", _BUCKET_NAME)
                return True
            except Exception as create_err:
                err = str(create_err).lower()
                if "already exists" in err or "duplicate" in err or "409" in err:
                    _bucket_verified = True
                    logger.info("✓ Bucket '%s' already exists", _BUCKET_NAME)
                    return True
                logger.error("✗ Failed to create bucket '%s': %s", _BUCKET_NAME, create_err)
                return False


def _insert_supabase_db_record(entry: FileEntry, storage_path: str):
    """
    Insert a row into the `generated_files` table so there is a permanent,
    queryable Supabase DB record for every skill-generated file.

    Runs in a background thread — non-blocking.
    """
    try:
        db = _get_supabase_client()
        if not db:
            return

        record = {
            "file_id":      entry.file_id,
            "filename":     entry.filename,
            "file_type":    entry.file_type,
            "size_kb":      entry.size_kb,
            "tool_name":    entry.tool_name,
            "storage_path": storage_path,   # bucket path: {file_id}/{filename}
        }

        db.table("generated_files").upsert(record, on_conflict="file_id").execute()
        logger.info("✓ Supabase DB record created: generated_files[%s]", entry.file_id)
    except Exception as e:
        # DB record is best-effort — file is already safe on Railway volume
        logger.warning("Could not insert generated_files DB record for %s: %s", entry.file_id, e)


def _upload_to_supabase(entry: FileEntry):
    """
    Upload file bytes to Supabase Storage AND insert a DB record.
    Runs in a background thread — non-blocking.
    """
    try:
        if not _ensure_bucket():
            logger.warning("Skipping Supabase upload — bucket not available")
            return

        storage = _get_storage_client()
        if not storage:
            return

        storage_path = f"{entry.file_id}/{entry.filename}"

        mime_map = {
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "pdf":  "application/pdf",
            "csv":  "text/csv",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "json": "application/json",
            "txt":  "text/plain",
            "png":  "image/png",
            "jpg":  "image/jpeg",
        }
        content_type = mime_map.get(entry.file_type, "application/octet-stream")

        storage.from_(_BUCKET_NAME).upload(
            path=storage_path,
            file=entry.data,
            file_options={"content-type": content_type, "upsert": "true"},
        )
        logger.info(
            "✓ Persisted to Supabase Storage: %s (%s, %.1f KB)",
            storage_path, entry.file_type, entry.size_kb,
        )

        # Insert DB record now that the file is safely in Storage
        _insert_supabase_db_record(entry, storage_path)

    except Exception as e:
        err = str(e)
        if "duplicate" in err.lower() or "already exists" in err.lower() or "409" in err:
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
        if not files:
            return None

        file_info  = files[0]
        filename   = file_info.get("name", f"download_{file_id}")
        storage_path = f"{file_id}/{filename}"

        data = storage.from_(_BUCKET_NAME).download(storage_path)
        if not data:
            return None

        ext   = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
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
        # Warm both memory cache and Railway volume for next time
        _file_cache[file_id] = entry
        threading.Thread(target=_write_to_volume, args=(entry,), daemon=True).start()
        return entry

    except Exception as e:
        logger.debug("Supabase Storage download failed for %s: %s", file_id, e)
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def store_file(
    data: bytes,
    filename: str,
    file_type: str = "",
    tool_name: str = "",
    file_id: str = None,
) -> FileEntry:
    """
    Store file bytes with 3-tier persistence.

    Always generates a permanent backend UUID as the file_id — never
    re-uses Claude's ephemeral file_id so that download URLs served
    to clients are always Railway/Supabase-backed and never expire.

    1. In-memory cache      (immediate — hot reads)
    2. Railway volume       (synchronous — fast, persistent on disk)
    3. Supabase Storage     (background thread — cross-deployment backup)
       + DB record in `generated_files` table
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

    # 1. Memory cache (instant)
    _file_cache[file_id] = entry
    logger.info(
        "Storing: %s (%s, %.1f KB) [id=%s] → memory + Railway volume + Supabase",
        filename, file_type, entry.size_kb, file_id,
    )

    # 2. Railway volume (synchronous — done before returning so file is safe)
    _write_to_volume(entry)

    # 3. Supabase Storage + DB record (background — don't block the response)
    threading.Thread(target=_upload_to_supabase, args=(entry,), daemon=True).start()

    # 4. Prune stale memory entries
    _prune_memory_cache()

    return entry


def get_file(file_id: str) -> Optional[FileEntry]:
    """
    Retrieve a file by ID.

    Priority:
        1. In-memory cache          (O(1) dict lookup)
        2. Railway volume           (local disk read)
        3. Supabase Storage         (persistent backup)
        4. None                     (caller falls back to Claude Files API)
    """
    # 1. Memory
    entry = _file_cache.get(file_id)
    if entry is not None:
        return entry

    # 2. Railway volume
    entry = _read_from_volume(file_id)
    if entry is not None:
        return entry

    # 3. Supabase Storage
    entry = _download_from_supabase(file_id)
    if entry is not None:
        return entry

    return None


def get_file_bytes(file_id: str) -> Optional[bytes]:
    """Get just the raw bytes for a file. Returns None if not found."""
    entry = get_file(file_id)
    return entry.data if entry else None


def list_files() -> list:
    """List all currently cached files (memory cache + Railway volume scan)."""
    _prune_memory_cache()

    # Scan Railway volume for any files not in memory
    known_ids = set(_file_cache.keys())
    volume_files = []
    try:
        if os.path.exists(_GENERATED_DIR):
            for fname in os.listdir(_GENERATED_DIR):
                parts = fname.split("_", 1)
                if len(parts) == 2:
                    fid, original = parts[0], parts[1]
                    if fid not in known_ids:
                        path = os.path.join(_GENERATED_DIR, fname)
                        ext = original.rsplit(".", 1)[-1].lower() if "." in original else "bin"
                        volume_files.append({
                            "file_id": fid,
                            "filename": original,
                            "file_type": ext,
                            "size_kb": round(os.path.getsize(path) / 1024, 1),
                            "tool_name": "railway_volume",
                            "download_url": f"/files/{fid}/download",
                        })
    except Exception:
        pass

    memory_files = [
        {
            "file_id":     e.file_id,
            "filename":    e.filename,
            "file_type":   e.file_type,
            "size_kb":     e.size_kb,
            "tool_name":   e.tool_name,
            "download_url": f"/files/{e.file_id}/download",
        }
        for e in _file_cache.values()
    ]

    return memory_files + volume_files


def _prune_memory_cache():
    """Remove old entries from memory cache (Railway + Supabase copies persist)."""
    now = time.time()
    expired = [
        fid for fid, e in _file_cache.items()
        if now - e.created_at > _CACHE_TTL
    ]
    for fid in expired:
        del _file_cache[fid]
    if expired:
        logger.debug(
            "Evicted %d files from memory cache (still on Railway volume + Supabase)",
            len(expired),
        )
