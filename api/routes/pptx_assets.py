"""
PPTX Asset Library Routes
=========================
Endpoints for uploading, listing, and deleting user-scoped asset items
(icons, graphics, backgrounds, logos) used by the PPTX sandbox.

All authenticated users may upload their own assets. Global assets
are seeded by the backend and are read-only for clients.

Routes
------
POST   /api/pptx/assets/upload     — multipart upload (auth)
GET    /api/pptx/assets            — list visible assets
GET    /api/pptx/assets/manifest   — compact LLM-consumable asset manifest
DELETE /api/pptx/assets/{key}      — delete a user-scoped asset
"""

from __future__ import annotations

import logging
import mimetypes
from typing import List, Optional

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, UploadFile, Query,
)
from pydantic import BaseModel

from api.dependencies import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pptx/assets", tags=["pptx-assets"])


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class AssetOut(BaseModel):
    id: Optional[str] = None
    scope: str
    owner_id: Optional[str] = None
    key: str
    kind: str
    mime: str
    aspect: Optional[float] = None
    tags: List[str] = []
    use_when: Optional[str] = None
    on_colors: List[str] = []
    bytes_size: Optional[int] = None


class AssetUploadResponse(BaseModel):
    success: bool
    asset: AssetOut
    message: str


class AssetListResponse(BaseModel):
    assets: List[AssetOut]
    total: int


_ALLOWED_MIME = {
    "image/png", "image/jpeg", "image/gif", "image/webp",
    "image/svg+xml",
}
_ALLOWED_KIND = {"icon", "graphic", "background", "logo"}


# ─────────────────────────────────────────────────────────────────────────────
# Upload
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=AssetUploadResponse)
async def upload_asset(
    file: UploadFile = File(...),
    key: str = Form(..., description="Unique asset key (letters/digits/._-)"),
    kind: str = Form("icon", description="icon | graphic | background | logo"),
    tags: Optional[str] = Form("", description="Comma-separated tags"),
    use_when: Optional[str] = Form(None, description="Natural-language hint for agents"),
    on_colors: Optional[str] = Form("", description="Comma-separated palette keys"),
    user_id: str = Depends(get_current_user_id),
):
    """Upload a user-scoped PPTX asset (icon/graphic/background/logo)."""
    if kind not in _ALLOWED_KIND:
        raise HTTPException(status_code=400, detail=f"kind must be one of {sorted(_ALLOWED_KIND)}")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    mime = (
        file.content_type
        or mimetypes.guess_type(file.filename or "")[0]
        or "application/octet-stream"
    )
    if mime not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{mime}'. Allowed: PNG, JPEG, GIF, WEBP, SVG.",
        )

    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    color_list = [c.strip() for c in (on_colors or "").split(",") if c.strip()]

    try:
        from core.sandbox import pptx_assets
        rec = pptx_assets.upload_asset(
            scope="user",
            owner_id=user_id,
            key=key,
            kind=kind,
            filename=file.filename or f"{key}",
            content=content,
            tags=tag_list,
            use_when=use_when,
            on_colors=color_list,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("upload_asset failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Asset upload failed: {exc}")

    asset = AssetOut(
        id=rec.id, scope=rec.scope, owner_id=rec.owner_id,
        key=rec.key, kind=rec.kind, mime=rec.mime, aspect=rec.aspect,
        tags=rec.tags, use_when=rec.use_when, on_colors=rec.on_colors,
        bytes_size=rec.bytes_size,
    )
    return AssetUploadResponse(
        success=True,
        asset=asset,
        message=(
            f"Uploaded asset '{rec.key}'. Reference in PPTX specs via "
            f"`asset_keys: [\"{rec.key}\"]` or `icon_key: \"{rec.key}\"`."
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# List & manifest
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=AssetListResponse)
async def list_assets(
    kind: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
):
    """List all assets visible to the current user (global + own user-scoped)."""
    from core.sandbox import pptx_assets
    rows = pptx_assets.list_assets(user_id=user_id, kind=kind, tag=tag)
    assets = [
        AssetOut(
            id=r.get("id"), scope=r.get("scope") or "user",
            owner_id=r.get("owner_id"), key=r.get("key") or "",
            kind=r.get("kind") or "icon",
            mime=r.get("mime") or "image/png",
            aspect=r.get("aspect"),
            tags=r.get("tags") or [],
            use_when=r.get("use_when"),
            on_colors=r.get("on_colors") or [],
            bytes_size=r.get("bytes_size"),
        )
        for r in rows
    ]
    return AssetListResponse(assets=assets, total=len(assets))


@router.get("/manifest")
async def get_manifest(user_id: str = Depends(get_current_user_id)):
    """Return a compact asset manifest grouped by kind (for LLM agent context)."""
    from core.sandbox import pptx_assets
    return pptx_assets.build_manifest(user_id=user_id)


# ─────────────────────────────────────────────────────────────────────────────
# Delete
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/{key}")
async def delete_asset(
    key: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete one of the user's own assets (cannot delete global)."""
    from core.sandbox import pptx_assets
    ok = pptx_assets.delete_asset(user_id=user_id, key=key)
    if not ok:
        raise HTTPException(status_code=404, detail="Asset not found or not owned")
    return {"status": "deleted", "key": key}
