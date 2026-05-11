"""
Content Studio — Project + Artifact endpoints.

Mounted at /studio/projects/*

Project lifecycle:
    POST   /studio/projects                       — create project (+ conversation)
    GET    /studio/projects                       — list (filter by ?kind=)
    GET    /studio/projects/{id}                  — full project (+ artifacts)
    PATCH  /studio/projects/{id}                  — rename, settings, archive
    DELETE /studio/projects/{id}                  — delete + purge volume

Artifact lifecycle:
    GET    /studio/projects/{id}/artifacts        — list versions
    GET    /studio/projects/{id}/artifacts/{aid}  — metadata
    GET    /studio/projects/{id}/artifacts/{aid}/download  — bytes
    POST   /studio/projects/{id}/artifacts/{aid}/edit      — apply ops → new version
    POST   /studio/projects/{id}/artifacts/upload          — direct upload (rare)

Generation always happens through the existing /chat/agent endpoint — when
the chat is bound to a studio project's conversation, the chat hook
automatically captures generated pptx/docx as artifact versions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api.dependencies import get_current_user_id
from core.studio import projects as studio
from core.studio import edits as studio_edits

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/studio/projects", tags=["studio"])


# -----------------------------------------------------------------------------
# Pydantic models
# -----------------------------------------------------------------------------

class CreateProjectRequest(BaseModel):
    kind: str  # 'pptx' | 'docx' | 'chat' | 'site'
    title: Optional[str] = None
    description: str = ""
    style_profile_id: Optional[str] = None
    humanize_settings: Optional[Dict[str, Any]] = None
    conversation_id: Optional[str] = None
    tags: Optional[List[str]] = None


class UpdateProjectRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    style_profile_id: Optional[str] = None
    humanize_settings: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    is_archived: Optional[bool] = None
    current_artifact_id: Optional[str] = None
    thumbnail_path: Optional[str] = None
    touch_opened: bool = False


class ApplyEditsRequest(BaseModel):
    ops: List[Dict[str, Any]] = Field(default_factory=list)
    save_edit_state: bool = True


# -----------------------------------------------------------------------------
# Project CRUD
# -----------------------------------------------------------------------------

@router.post("")
async def create_project(
    body: CreateProjectRequest,
    user_id: str = Depends(get_current_user_id),
):
    try:
        project = studio.create_project(
            user_id=user_id,
            kind=body.kind,
            title=body.title,
            description=body.description,
            style_profile_id=body.style_profile_id,
            humanize_settings=body.humanize_settings,
            conversation_id=body.conversation_id,
            tags=body.tags,
        )
        return {"project": project}
    except (ValueError, PermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_projects(
    kind: Optional[str] = Query(None, pattern="^(pptx|docx|chat|site)$"),

    include_archived: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user_id),
):
    rows = studio.list_projects(
        user_id,
        kind=kind,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return {"projects": rows, "count": len(rows)}


@router.get("/{project_id}")
async def get_project(
    project_id: str = Path(...),
    user_id: str = Depends(get_current_user_id),
):
    p = studio.get_project(project_id, user_id)
    if not p:
        raise HTTPException(status_code=404, detail="project not found")
    artifacts = studio.list_artifacts(project_id, user_id)
    return {"project": p, "artifacts": artifacts}


@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    body: UpdateProjectRequest,
    user_id: str = Depends(get_current_user_id),
):
    p = studio.update_project(
        project_id, user_id,
        title=body.title,
        description=body.description,
        style_profile_id=body.style_profile_id,
        humanize_settings=body.humanize_settings,
        tags=body.tags,
        is_archived=body.is_archived,
        current_artifact_id=body.current_artifact_id,
        thumbnail_path=body.thumbnail_path,
        touch_opened=body.touch_opened,
    )
    if not p:
        raise HTTPException(status_code=404, detail="project not found")
    return {"project": p}


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    purge_files: bool = Query(True),
    user_id: str = Depends(get_current_user_id),
):
    ok = studio.delete_project(project_id, user_id, purge_files=purge_files)
    if not ok:
        raise HTTPException(status_code=404, detail="project not found")
    return {"deleted": True, "id": project_id}


# -----------------------------------------------------------------------------
# Artifacts
# -----------------------------------------------------------------------------

@router.get("/{project_id}/artifacts")
async def list_artifacts(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
):
    p = studio.get_project(project_id, user_id)
    if not p:
        raise HTTPException(status_code=404, detail="project not found")
    return {"artifacts": studio.list_artifacts(project_id, user_id)}


@router.get("/{project_id}/artifacts/{artifact_id}")
async def get_artifact(
    project_id: str,
    artifact_id: str,
    user_id: str = Depends(get_current_user_id),
):
    a = studio.get_artifact(artifact_id, user_id)
    if not a or a.get("project_id") != project_id:
        raise HTTPException(status_code=404, detail="artifact not found")
    return {"artifact": a}


@router.get("/{project_id}/artifacts/{artifact_id}/download")
async def download_artifact(
    project_id: str,
    artifact_id: str,
    user_id: str = Depends(get_current_user_id),
):
    data, filename, mime = studio.artifact_bytes(artifact_id, user_id)
    if not data:
        raise HTTPException(status_code=404, detail="artifact bytes not found")
    return Response(
        content=data,
        media_type=mime or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename or "file"}"',
            "Content-Length":      str(len(data)),
        },
    )


@router.post("/{project_id}/artifacts/{artifact_id}/edit")
async def apply_edits(
    project_id: str,
    artifact_id: str,
    body: ApplyEditsRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Apply visual-editor JSON ops to an artifact and create v(n+1).
    """
    src = studio.get_artifact(artifact_id, user_id)
    if not src or src.get("project_id") != project_id:
        raise HTTPException(status_code=404, detail="artifact not found")
    try:
        new_artifact = studio_edits.apply_ops_to_artifact(
            user_id=user_id,
            artifact_id=artifact_id,
            ops=body.ops,
            save_edit_state=body.save_edit_state,
        )
        return {"artifact": new_artifact}
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("edit failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"edit failed: {e}")


@router.post("/{project_id}/artifacts/upload")
async def upload_artifact(
    project_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    """
    Direct artifact upload (e.g. user starts from an existing pptx/docx).
    """
    p = studio.get_project(project_id, user_id)
    if not p:
        raise HTTPException(status_code=404, detail="project not found")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")

    name = file.filename or "uploaded.bin"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    # site uploads come in as a zip bundle
    if ext == "zip":
        kind = "site"
    elif ext in ("pptx", "docx"):
        kind = ext
    else:
        raise HTTPException(status_code=400, detail=f"unsupported extension: .{ext}")

    artifact = studio.register_artifact_from_bytes(
        user_id=user_id,
        project_id=project_id,
        kind=kind,
        data=content,
        filename=name,
        meta={"source": "user_upload"},
    )
    return {"artifact": artifact}
