"""
Skill Bundle Archive (Supabase Storage)
========================================
Persists raw uploaded skill zips in the `skills-bundles` bucket so that
ephemeral container filesystems (Railway redeploys) can rehydrate the
on-disk skill folders on boot.

Object path convention:
    skills-bundles/<slug>.zip

All access goes through the service-role key (no user-facing policies).
Failures are logged but do NOT block the upload pipeline — the skill
will still work for the lifetime of the current container even if the
backup write fails.
"""

from __future__ import annotations

import logging
from typing import Optional

from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

BUCKET = "skills-bundles"


def _client():
    return get_supabase()


def _object_path(slug: str) -> str:
    return f"{slug}.zip"


def upload_zip(slug: str, zip_bytes: bytes) -> bool:
    """Upload (or overwrite) the archived zip for a skill. Returns True on success."""
    try:
        sb = _client()
        path = _object_path(slug)
        # supabase-py v2: storage.upload(path, file, file_options)
        # Use upsert via remove+upload to keep semantics consistent across versions
        try:
            sb.storage.from_(BUCKET).remove([path])
        except Exception:
            pass
        sb.storage.from_(BUCKET).upload(
            path=path,
            file=zip_bytes,
            file_options={"content-type": "application/zip", "upsert": "true"},
        )
        return True
    except Exception as e:
        logger.warning("skill storage upload failed for %s: %s", slug, e)
        return False


def download_zip(slug: str) -> Optional[bytes]:
    """Download the archived zip for a skill. Returns None if missing/error."""
    try:
        sb = _client()
        data = sb.storage.from_(BUCKET).download(_object_path(slug))
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        # Some client versions return a Response-like object
        return getattr(data, "content", None)
    except Exception as e:
        logger.info("skill storage download miss for %s: %s", slug, e)
        return None


def delete_zip(slug: str) -> bool:
    """Delete the archived zip for a skill."""
    try:
        sb = _client()
        sb.storage.from_(BUCKET).remove([_object_path(slug)])
        return True
    except Exception as e:
        logger.warning("skill storage delete failed for %s: %s", slug, e)
        return False


def list_archived_slugs() -> list[str]:
    """List slugs that have archived zips in the bucket."""
    try:
        sb = _client()
        items = sb.storage.from_(BUCKET).list()
        slugs: list[str] = []
        for it in items or []:
            name = it.get("name") if isinstance(it, dict) else getattr(it, "name", None)
            if name and name.endswith(".zip"):
                slugs.append(name[:-4])
        return slugs
    except Exception as e:
        logger.warning("skill storage list failed: %s", e)
        return []
