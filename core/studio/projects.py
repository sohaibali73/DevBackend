"""
Content Studio — Project + Artifact CRUD on Railway volume + Supabase.

Projects are thin wrappers over a `conversations` row. Each project has zero
or more *versioned artifacts* (.pptx / .docx) persisted to:

    $STORAGE_ROOT/projects/{project_id}/v{n}.{ext}
    $STORAGE_ROOT/projects/{project_id}/edit_state/v{n}.json

Public surface (used by api.routes.studio_projects + the chat hook):

    create_project(...)                   →  dict
    list_projects(user_id, ...)           →  list[dict]
    get_project(project_id, user_id)      →  dict | None
    update_project(...)                   →  dict
    delete_project(project_id, user_id)   →  bool
    list_artifacts(project_id, user_id)   →  list[dict]
    get_artifact(artifact_id, user_id)    →  dict | None
    artifact_bytes(artifact_id, user_id)  →  (bytes, filename, mime) | (None,None,None)

    register_artifact_from_bytes(
        user_id, project_id, kind, data, filename,
        conversation_id=..., message_id=..., source_file_id=..., meta=...,
    ) → artifact dict   (writes bytes to volume + inserts row)

    register_artifact_from_volume(
        user_id, project_id, kind, src_path, filename, ...
    ) → artifact dict   (copies an existing on-disk file to the project dir)
"""

from __future__ import annotations

import io
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Volume layout
# -----------------------------------------------------------------------------

STORAGE_ROOT = os.getenv("STORAGE_ROOT", "/data")
PROJECTS_ROOT = os.path.join(STORAGE_ROOT, "projects")

_MIME = {
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def project_dir(project_id: str) -> str:
    p = os.path.join(PROJECTS_ROOT, project_id)
    os.makedirs(p, exist_ok=True)
    os.makedirs(os.path.join(p, "edit_state"), exist_ok=True)
    return p


def _version_filename(project_id: str, version: int, ext: str) -> str:
    return os.path.join(project_dir(project_id), f"v{version}.{ext}")


def _safe_name(name: str, max_len: int = 120) -> str:
    keep = []
    for c in name:
        if c.isalnum() or c in "._- ":
            keep.append(c)
    return ("".join(keep).strip() or "file")[:max_len]


# -----------------------------------------------------------------------------
# DB helpers
# -----------------------------------------------------------------------------

def _db():
    from db.supabase_client import get_supabase
    return get_supabase()


def _slide_count(pptx_bytes: bytes) -> Optional[int]:
    try:
        from pptx import Presentation
        return len(Presentation(io.BytesIO(pptx_bytes)).slides)
    except Exception:
        return None


def _page_count(docx_bytes: bytes) -> Optional[int]:
    # python-docx doesn't expose final paginated page count cheaply; we
    # approximate by counting page breaks. A null is fine if we can't tell.
    try:
        from docx import Document
        d = Document(io.BytesIO(docx_bytes))
        breaks = 0
        for p in d.paragraphs:
            for run in p.runs:
                if "<w:br" in run._r.xml and 'w:type="page"' in run._r.xml:
                    breaks += 1
        return breaks + 1
    except Exception:
        return None


# =============================================================================
# PROJECTS
# =============================================================================

def create_project(
    *,
    user_id: str,
    kind: str,
    title: Optional[str] = None,
    description: str = "",
    style_profile_id: Optional[str] = None,
    humanize_settings: Optional[Dict[str, Any]] = None,
    conversation_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Create a project + its underlying conversation (or reuse an existing one).
    Returns the full project row including conversation_id.
    """
    if kind not in ("pptx", "docx", "chat"):
        raise ValueError(f"Invalid kind: {kind}")

    db = _db()

    # Resolve / create conversation
    if conversation_id:
        conv = db.table("conversations").select("id, user_id").eq("id", conversation_id).limit(1).execute()
        if not conv.data:
            raise ValueError("conversation_id not found")
        if conv.data[0]["user_id"] != user_id:
            raise PermissionError("conversation belongs to another user")
    else:
        conv = (
            db.table("conversations")
            .insert(
                {
                    "user_id": user_id,
                    "title": title or f"New {kind.upper()} Project",
                    "conversation_type": "agent",
                }
            )
            .execute()
        )
        conversation_id = conv.data[0]["id"]

    # Insert project row
    row = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "kind": kind,
        "title": title or f"New {kind.upper()} Project",
        "description": description or "",
        "tags": tags or [],
    }
    if style_profile_id:
        row["style_profile_id"] = style_profile_id
    if humanize_settings:
        row["humanize_settings"] = humanize_settings

    res = db.table("studio_projects").insert(row).execute()
    if not res.data:
        raise RuntimeError("Failed to create project")
    project = res.data[0]

    # Make sure the volume directory exists immediately so subsequent writes succeed.
    project_dir(project["id"])

    return project


def list_projects(
    user_id: str,
    *,
    kind: Optional[str] = None,
    include_archived: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    db = _db()
    q = (
        db.table("studio_projects")
        .select(
            "id, user_id, conversation_id, kind, title, description, "
            "style_profile_id, humanize_settings, current_artifact_id, "
            "thumbnail_path, tags, is_archived, created_at, updated_at, last_opened_at"
        )
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .limit(limit)
        .offset(offset)
    )
    if kind:
        q = q.eq("kind", kind)
    if not include_archived:
        q = q.eq("is_archived", False)
    res = q.execute()
    return res.data or []


def get_project(project_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    db = _db()
    res = (
        db.table("studio_projects")
        .select("*")
        .eq("id", project_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]


def update_project(
    project_id: str,
    user_id: str,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    style_profile_id: Optional[str] = None,
    humanize_settings: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    is_archived: Optional[bool] = None,
    current_artifact_id: Optional[str] = None,
    thumbnail_path: Optional[str] = None,
    touch_opened: bool = False,
) -> Optional[Dict[str, Any]]:
    db = _db()
    fields: Dict[str, Any] = {}
    if title is not None:                fields["title"] = title
    if description is not None:          fields["description"] = description
    if style_profile_id is not None:     fields["style_profile_id"] = style_profile_id or None
    if humanize_settings is not None:    fields["humanize_settings"] = humanize_settings
    if tags is not None:                 fields["tags"] = tags
    if is_archived is not None:          fields["is_archived"] = is_archived
    if current_artifact_id is not None:  fields["current_artifact_id"] = current_artifact_id
    if thumbnail_path is not None:       fields["thumbnail_path"] = thumbnail_path
    if touch_opened:                     fields["last_opened_at"] = "now()"

    if not fields:
        return get_project(project_id, user_id)

    # Note: supabase-py treats string "now()" as literal; use SQL function via rpc if needed.
    # For touch_opened we just set ISO timestamp client-side.
    if touch_opened:
        from datetime import datetime, timezone
        fields["last_opened_at"] = datetime.now(timezone.utc).isoformat()

    res = (
        db.table("studio_projects")
        .update(fields)
        .eq("id", project_id)
        .eq("user_id", user_id)
        .execute()
    )
    return res.data[0] if res.data else None


def delete_project(project_id: str, user_id: str, *, purge_files: bool = True) -> bool:
    db = _db()
    proj = get_project(project_id, user_id)
    if not proj:
        return False

    db.table("studio_projects").delete().eq("id", project_id).eq("user_id", user_id).execute()

    if purge_files:
        try:
            shutil.rmtree(os.path.join(PROJECTS_ROOT, project_id), ignore_errors=True)
        except Exception as e:
            logger.warning("Could not purge project dir for %s: %s", project_id, e)

    return True


# =============================================================================
# ARTIFACTS
# =============================================================================

def list_artifacts(project_id: str, user_id: str) -> List[Dict[str, Any]]:
    db = _db()
    res = (
        db.table("studio_artifacts")
        .select(
            "id, project_id, conversation_id, message_id, source_file_id, "
            "kind, version, filename, size_bytes, slide_count, page_count, "
            "edit_state, meta, created_at"
        )
        .eq("project_id", project_id)
        .eq("user_id", user_id)
        .order("version", desc=False)
        .execute()
    )
    return res.data or []


def get_artifact(artifact_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    db = _db()
    res = (
        db.table("studio_artifacts")
        .select("*")
        .eq("id", artifact_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def artifact_bytes(
    artifact_id: str, user_id: str
) -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
    a = get_artifact(artifact_id, user_id)
    if not a:
        return None, None, None
    path = a.get("volume_path") or ""
    if not path or not os.path.exists(path):
        logger.warning("Artifact volume_path missing on disk: %s", path)
        return None, a.get("filename"), _MIME.get(a.get("kind", ""))
    try:
        with open(path, "rb") as f:
            return f.read(), a.get("filename"), _MIME.get(a.get("kind", ""))
    except OSError as e:
        logger.error("Failed to read artifact %s: %s", artifact_id, e)
        return None, a.get("filename"), _MIME.get(a.get("kind", ""))


def _next_version(project_id: str, user_id: str) -> int:
    db = _db()
    res = (
        db.table("studio_artifacts")
        .select("version")
        .eq("project_id", project_id)
        .eq("user_id", user_id)
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return 1
    return int(res.data[0]["version"]) + 1


def register_artifact_from_bytes(
    *,
    user_id: str,
    project_id: str,
    kind: str,                          # 'pptx' | 'docx'
    data: bytes,
    filename: str,
    conversation_id: Optional[str] = None,
    message_id: Optional[str] = None,
    source_file_id: Optional[str] = None,
    edit_state: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
    set_current: bool = True,
) -> Dict[str, Any]:
    """Persist bytes to volume and insert a studio_artifacts row."""
    if kind not in ("pptx", "docx"):
        raise ValueError(f"Invalid kind: {kind}")

    db = _db()
    version = _next_version(project_id, user_id)
    safe_fn = _safe_name(filename) or f"v{version}.{kind}"
    abs_path = _version_filename(project_id, version, kind)

    with open(abs_path, "wb") as f:
        f.write(data)

    slides = _slide_count(data) if kind == "pptx" else None
    pages = _page_count(data) if kind == "docx" else None

    row = {
        "user_id": user_id,
        "project_id": project_id,
        "conversation_id": conversation_id,
        "message_id": message_id,
        "source_file_id": source_file_id,
        "kind": kind,
        "version": version,
        "filename": safe_fn,
        "volume_path": abs_path,
        "size_bytes": len(data),
        "slide_count": slides,
        "page_count": pages,
        "edit_state": edit_state,
        "meta": meta or {},
    }
    res = db.table("studio_artifacts").insert(row).execute()
    if not res.data:
        # Best-effort cleanup of orphaned bytes
        try:
            os.remove(abs_path)
        except Exception:
            pass
        raise RuntimeError("Failed to insert studio_artifacts row")

    artifact = res.data[0]

    if set_current:
        try:
            db.table("studio_projects").update(
                {"current_artifact_id": artifact["id"]}
            ).eq("id", project_id).eq("user_id", user_id).execute()
        except Exception as e:
            logger.warning("Failed to update current_artifact_id: %s", e)

    logger.info(
        "✓ studio artifact v%d saved: %s (%s, %.1f KB) project=%s",
        version, safe_fn, kind, len(data) / 1024.0, project_id,
    )
    return artifact


def register_artifact_from_volume(
    *,
    user_id: str,
    project_id: str,
    kind: str,
    src_path: str,
    filename: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Like register_artifact_from_bytes but reads bytes from an existing path."""
    if not os.path.exists(src_path):
        raise FileNotFoundError(src_path)
    with open(src_path, "rb") as f:
        data = f.read()
    return register_artifact_from_bytes(
        user_id=user_id,
        project_id=project_id,
        kind=kind,
        data=data,
        filename=filename or os.path.basename(src_path),
        **kwargs,
    )
