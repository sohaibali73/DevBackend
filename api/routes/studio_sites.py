"""
Content Studio — Sites (auth-gated) endpoints.

Mounted at /studio/sites/*

    GET    /studio/sites/{project_id}/preview/{version}/{path:path}  — auth-gated iframe preview
    GET    /studio/sites/{project_id}/files/{artifact_id}            — return file map for client editor
    POST   /studio/sites/{project_id}/publish                        — publish a site artifact to a subdomain
    POST   /studio/sites/{project_id}/unpublish                      — unpublish (deactivate)
    GET    /studio/sites/{project_id}/publications                   — list publications for the project
    GET    /studio/sites/check/{subdomain}                           — availability check
    GET    /studio/sites/publications                                — list ALL publications for the user

Generation flows through POST /chat/agent (tools: generate_site / revise_site).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api.dependencies import get_current_user_id
from core.studio import projects as studio
from core.studio import sites as sites_mod

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/studio/sites", tags=["studio", "sites"])


# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------

class PublishRequest(BaseModel):
    artifact_id: str
    subdomain: str = Field(..., min_length=1, max_length=32)


class UnpublishRequest(BaseModel):
    publication_id: str


# -----------------------------------------------------------------------------
# Authenticated preview (the live editor iframe target)
# -----------------------------------------------------------------------------

@router.get("/{project_id}/preview/{version}/{path:path}")
@router.get("/{project_id}/preview/{version}")
@router.get("/{project_id}/preview/{version}/")
async def preview_site(
    project_id: str = Path(...),
    version: int = Path(..., ge=1),
    path: str = "",
    user_id: str = Depends(get_current_user_id),
):
    """
    Serve a static file from the extracted bundle for a project's site
    artifact at version N. Auth-gated so unpublished previews stay private.
    """
    p = studio.get_project(project_id, user_id)
    if not p:
        raise HTTPException(status_code=404, detail="project not found")

    # Find the artifact for this version
    db = studio._db()
    res = (
        db.table("studio_artifacts")
        .select("*")
        .eq("project_id", project_id)
        .eq("user_id", user_id)
        .eq("kind", "site")
        .eq("version", version)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="site version not found")

    artifact = res.data[0]
    try:
        site_root = sites_mod.site_root_for_artifact(artifact)
    except FileNotFoundError:
        raise HTTPException(status_code=410, detail="site bundle missing on disk")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    body, mime, status = sites_mod.serve_site_file(site_root, path)
    if body is None:
        raise HTTPException(status_code=status, detail="not found")

    headers = {
        # Conservative defaults for preview frames
        "X-Frame-Options":   "SAMEORIGIN",
        "Referrer-Policy":   "no-referrer",
        "Cache-Control":     "no-store",
    }
    return Response(content=body, media_type=mime, status_code=status, headers=headers)


# -----------------------------------------------------------------------------
# File map (used by an in-app code editor view)
# -----------------------------------------------------------------------------

@router.get("/{project_id}/files/{artifact_id}")
async def get_site_files(
    project_id: str,
    artifact_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Return the {path: content} dict for a site artifact (text + b64 binary)."""
    art = studio.get_artifact(artifact_id, user_id)
    if not art or art.get("project_id") != project_id or art.get("kind") != "site":
        raise HTTPException(status_code=404, detail="site artifact not found")
    try:
        files = sites_mod.read_site_files_as_dict(art)
        return {"artifact_id": artifact_id, "files": files, "file_count": len(files)}
    except Exception as e:
        logger.error("read_site_files_as_dict failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"could not read site files: {e}")


# -----------------------------------------------------------------------------
# Publish / unpublish
# -----------------------------------------------------------------------------

@router.get("/check/{subdomain}")
async def check_subdomain(
    subdomain: str,
    user_id: str = Depends(get_current_user_id),
):
    """Subdomain availability + format check."""
    ok, reason = sites_mod.is_valid_subdomain(subdomain)
    if not ok:
        return {"available": False, "reason": reason, "subdomain": subdomain}
    existing = sites_mod.resolve_subdomain(subdomain)
    if existing and existing.get("user_id") != user_id:
        return {"available": False, "reason": "already taken", "subdomain": subdomain}
    return {"available": True, "subdomain": subdomain}


@router.post("/{project_id}/publish")
async def publish(
    project_id: str,
    body: PublishRequest,
    user_id: str = Depends(get_current_user_id),
):
    p = studio.get_project(project_id, user_id)
    if not p:
        raise HTTPException(status_code=404, detail="project not found")
    try:
        pub = sites_mod.publish_site(
            user_id=user_id,
            project_id=project_id,
            artifact_id=body.artifact_id,
            subdomain=body.subdomain,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=410, detail=str(e))
    except Exception as e:
        logger.error("publish failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"publish failed: {e}")

    sub = pub["subdomain"]
    return {
        "publication": pub,
        "urls": {
            # Path-based always works on the API host
            "path_url":      f"/s/{sub}/",
            # Subdomain URL shape — only resolves once wildcard DNS is set up
            "subdomain_url": f"https://{sub}.sites.potomacai.com/",
        },
    }


@router.post("/{project_id}/unpublish")
async def unpublish(
    project_id: str,
    body: UnpublishRequest,
    user_id: str = Depends(get_current_user_id),
):
    ok = sites_mod.unpublish_site(user_id, body.publication_id)
    if not ok:
        raise HTTPException(status_code=404, detail="publication not found")
    return {"unpublished": True, "publication_id": body.publication_id}


@router.get("/{project_id}/publications")
async def list_publications_for_project(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
):
    rows = sites_mod.list_publications(user_id, project_id=project_id)
    return {"publications": rows, "count": len(rows)}


@router.get("/publications")
async def list_all_publications(
    user_id: str = Depends(get_current_user_id),
):
    rows = sites_mod.list_publications(user_id, project_id=None)
    return {"publications": rows, "count": len(rows)}
