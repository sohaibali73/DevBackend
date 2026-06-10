"""
Skill Bundle Archive (Azure Blob Storage)
=========================================
Persists raw uploaded skill zips in the `skills-bundles` container so that
ephemeral container filesystems (Container Apps redeploys) can rehydrate the
on-disk skill folders on boot.

Object path convention:
    skills-bundles/<slug>.zip

Failures are logged but do NOT block the upload pipeline — the skill will still
work for the lifetime of the current container even if the backup write fails.
"""

from __future__ import annotations

import logging
from typing import Optional

from core import azure_blob

logger = logging.getLogger(__name__)

BUCKET = "skills-bundles"


def _object_path(slug: str) -> str:
    return f"{slug}.zip"


def upload_zip(slug: str, zip_bytes: bytes) -> bool:
    """Upload (or overwrite) the archived zip for a skill. Returns True on success."""
    try:
        azure_blob.upload(BUCKET, _object_path(slug), zip_bytes, "application/zip")
        return True
    except Exception as e:
        logger.warning("skill storage upload failed for %s: %s", slug, e)
        return False


def download_zip(slug: str) -> Optional[bytes]:
    """Download the archived zip for a skill. Returns None if missing/error."""
    try:
        data = azure_blob.download(BUCKET, _object_path(slug))
        return bytes(data) if data else None
    except Exception as e:
        logger.info("skill storage download miss for %s: %s", slug, e)
        return None


def delete_zip(slug: str) -> bool:
    """Delete the archived zip for a skill."""
    try:
        azure_blob.delete(BUCKET, _object_path(slug))
        return True
    except Exception as e:
        logger.warning("skill storage delete failed for %s: %s", slug, e)
        return False


def list_archived_slugs() -> list[str]:
    """List slugs that have archived zips in the container."""
    try:
        items = azure_blob.list_prefix(BUCKET)
        slugs: list[str] = []
        for it in items or []:
            name = it.get("name")
            if name and name.endswith(".zip"):
                slugs.append(name[:-4])
        return slugs
    except Exception as e:
        logger.warning("skill storage list failed: %s", e)
        return []
