"""
Sandbox File Injector
=====================
Resolves uploaded file IDs so they can be injected into a sandbox execution
directory. Supports files from two sources:

  1. file_store  — generated files (DOCX, PPTX, XLSX) + dedicated sandbox uploads
                   stored via POST /sandbox/upload → file_store.store_file()
  2. file_uploads — files uploaded via POST /upload/direct or
                    POST /upload/conversations/{id} (stored on Railway volume,
                    metadata in Supabase file_uploads table)

Usage (called by api/routes/sandbox.py before executing code):

    from core.sandbox.file_injector import resolve_sandbox_files
    sandbox_files = resolve_sandbox_files(file_ids)
    # → {"report.xlsx": b"...", "chart.png": b"..."}
    context["_sandbox_files"] = sandbox_files

The Python sandbox then:
  • writes each file to sandbox_dir
  • injects _files   = {"report.xlsx": "/tmp/sbx_xxx/report.xlsx"}  (all types)
  • injects _images  = {"chart.png": "<base64>"}                    (images only)

So in user code:
    import openpyxl
    wb = openpyxl.load_workbook(_files["report.xlsx"])
    ...
    wb.save("modified.xlsx")          # picked up as downloadable artifact
    
    display(HTML(f'<img src="data:image/png;base64,{_images["chart.png"]}"/>'))
"""

import logging
import os
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Max file size allowed into the sandbox (50 MB)
_MAX_SANDBOX_FILE_BYTES = 10 * 1024 * 1024 * 1024  # 10 GB (no practical limit)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_sandbox_files(file_ids: List[str]) -> Dict[str, bytes]:
    """
    Resolve a list of file IDs to {original_filename: raw_bytes}.

    Resolution order per ID:
      1. file_store  (memory cache → Railway volume → Supabase Storage)
      2. file_uploads table in Supabase (user-uploaded chat files)

    Oversized or missing files are skipped with a warning.
    Returns an empty dict if nothing could be resolved.
    """
    result: Dict[str, bytes] = {}
    for fid in (file_ids or []):
        try:
            data, filename = _resolve_single(fid)
            if data is None:
                logger.warning("Sandbox file '%s' not found in any store — skipping", fid)
                continue
            if len(data) > _MAX_SANDBOX_FILE_BYTES:
                logger.warning(
                    "Sandbox file '%s' (%s) too large (%d bytes > 50 MB) — skipping",
                    fid, filename, len(data),
                )
                continue
            # Deduplicate filenames (append _2, _3 … if needed)
            safe_name = _unique_name(filename, result)
            result[safe_name] = data
            logger.info(
                "Resolved sandbox file: %s → %s (%.1f KB)",
                fid, safe_name, len(data) / 1024,
            )
        except Exception as e:
            logger.warning("Could not resolve sandbox file '%s': %s", fid, e)

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_single(file_id: str) -> Tuple[Optional[bytes], Optional[str]]:
    """Try file_store first, then file_uploads DB."""
    # 1. file_store (generated files + sandbox uploads)
    data, name = _from_file_store(file_id)
    if data is not None:
        return data, name

    # 2. file_uploads DB (chat-uploaded files)
    data, name = _from_file_uploads_db(file_id)
    if data is not None:
        return data, name

    return None, None


def _from_file_store(file_id: str) -> Tuple[Optional[bytes], Optional[str]]:
    """Read from the 3-tier file_store (memory → Railway volume → Supabase)."""
    try:
        from core.file_store import get_file
        entry = get_file(file_id)
        if entry is not None:
            return entry.data, entry.filename
    except Exception as e:
        logger.debug("file_store lookup failed for %s: %s", file_id, e)
    return None, None


def _from_file_uploads_db(file_id: str) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Read from the file_uploads Supabase table + Railway volume path.
    This handles files uploaded via POST /upload/direct or /upload/conversations/*.
    """
    try:
        from db.supabase_client import get_supabase
        db = get_supabase()
        result = db.table("file_uploads") \
            .select("storage_path, original_filename") \
            .eq("id", file_id) \
            .limit(1) \
            .execute()

        if not result.data:
            return None, None

        row = result.data[0]
        storage_path: str = row.get("storage_path", "")
        original_filename: str = row.get("original_filename", f"upload_{file_id}")

        if not storage_path or not os.path.exists(storage_path):
            logger.debug("file_uploads path missing on disk for %s: %s", file_id, storage_path)
            return None, None

        with open(storage_path, "rb") as f:
            data = f.read()
        return data, original_filename

    except Exception as e:
        logger.debug("file_uploads DB lookup failed for %s: %s", file_id, e)
    return None, None


def _unique_name(filename: str, existing: Dict[str, bytes]) -> str:
    """Return a filename that doesn't collide with keys already in existing."""
    if filename not in existing:
        return filename
    base, _, ext = filename.rpartition(".")
    if not base:
        base, ext = filename, ""
    idx = 2
    while True:
        candidate = f"{base}_{idx}.{ext}" if ext else f"{base}_{idx}"
        if candidate not in existing:
            return candidate
        idx += 1
