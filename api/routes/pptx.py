"""
PPTX Program Routes
===================
Endpoints for generating, editing, versioning, and rendering Potomac-branded
PowerPoint presentations via the PPTX sandbox.

Every generated deck is stored as a reusable "program" (title + canvas +
slide list), allowing subsequent edits through JSON patches instead of
regenerating from scratch.

Routes
------
POST   /api/pptx/generate              — create a new program + render
POST   /api/pptx/{program_id}/edit     — apply patches + re-render
POST   /api/pptx/{program_id}/render   — re-render latest (or specified version)
GET    /api/pptx/{program_id}          — load program source
GET    /api/pptx/programs              — list the user's programs
GET    /api/pptx/{program_id}/versions — list version history
POST   /api/pptx/{program_id}/revert/{version} — roll back to a prior version
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pptx", tags=["pptx"])


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    title: str = Field(..., description="Presentation title (also file metadata)")
    filename: Optional[str] = Field(None, description="Output filename (.pptx)")
    canvas: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Canvas size. Pass {preset:'wide'|'standard'|'hd16_9'|'a4_landscape'} "
            "or {width,height} in inches. Defaults to wide (13.333×7.5)."
        ),
    )
    slides: List[Dict[str, Any]] = Field(..., description="Slide specs")
    asset_keys: Optional[List[str]] = Field(
        None, description="Asset keys to preload into asset_registry"
    )


class GenerateResponse(BaseModel):
    success: bool
    program_id: str
    version: int
    file_id: Optional[str] = None
    filename: Optional[str] = None
    size_kb: Optional[float] = None
    download_url: Optional[str] = None
    canvas: Optional[Dict[str, Any]] = None
    warnings: List[str] = []
    exec_time_ms: float = 0.0


class EditRequest(BaseModel):
    patches: List[Dict[str, Any]] = Field(
        ...,
        description=(
            "JSON patch operations. Supported ops: update, insert, delete, "
            "reorder, set_canvas, set_title, set_filename."
        ),
    )


class RenderRequest(BaseModel):
    version: Optional[int] = None


class ProgramSummary(BaseModel):
    id: str
    title: str
    version: int
    canvas: Dict[str, Any]
    file_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProgramDetail(BaseModel):
    id: str
    title: str
    canvas: Dict[str, Any]
    version: int
    file_id: Optional[str] = None
    program: Dict[str, Any]
    asset_snapshot: Dict[str, Any] = {}


class VersionSummary(BaseModel):
    version: int
    title: Optional[str] = None
    canvas: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _store_and_respond(result, program_id: str, version: int) -> GenerateResponse:
    """Store the rendered .pptx in file_store and build the HTTP response."""
    from core.file_store import store_file

    entry = store_file(
        data=result.data,
        filename=result.filename or "presentation.pptx",
        file_type="pptx",
        tool_name="pptx_program",
    )

    # Back-reference the latest file_id on the program row
    try:
        from db.supabase_client import get_supabase
        db = get_supabase()
        db.table("pptx_programs").update({
            "file_id": entry.file_id,
        }).eq("id", program_id).execute()
    except Exception as exc:
        logger.debug("Could not update program.file_id: %s", exc)

    return GenerateResponse(
        success=True,
        program_id=program_id,
        version=version,
        file_id=entry.file_id,
        filename=entry.filename,
        size_kb=entry.size_kb,
        download_url=f"/files/{entry.file_id}/download",
        canvas=result.canvas,
        warnings=result.warnings or [],
        exec_time_ms=result.exec_time_ms,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Generate
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest, user_id: str = Depends(get_current_user_id)):
    """Render a new presentation AND persist its program for future edits."""
    from core.sandbox.pptx_sandbox import PptxSandbox

    spec: Dict[str, Any] = {
        "title": req.title,
        "slides": req.slides or [],
    }
    if req.filename:
        spec["filename"] = req.filename
    if req.canvas:
        spec["canvas"] = req.canvas
    if req.asset_keys:
        spec["asset_keys"] = req.asset_keys

    sandbox = PptxSandbox()
    result = sandbox.generate_and_store_program(
        spec, user_id=user_id, title=req.title,
    )
    if not result.success:
        raise HTTPException(
            status_code=500,
            detail=result.error or "PPTX generation failed",
        )
    return _store_and_respond(result, result.program_id, result.version)


# ─────────────────────────────────────────────────────────────────────────────
# Edit
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{program_id}/edit", response_model=GenerateResponse)
async def edit(
    program_id: str,
    req: EditRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Apply JSON patches to a stored program and re-render it."""
    from core.sandbox.pptx_sandbox import PptxSandbox

    sandbox = PptxSandbox()
    result = sandbox.edit_program(
        program_id, user_id=user_id, patches=req.patches,
    )
    if not result.success:
        raise HTTPException(
            status_code=400,
            detail=result.error or "Edit failed",
        )
    return _store_and_respond(result, result.program_id or program_id, result.version or 0)


# ─────────────────────────────────────────────────────────────────────────────
# Render (no edits)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{program_id}/render", response_model=GenerateResponse)
async def render(
    program_id: str,
    req: RenderRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Re-render a stored program (optionally a specific version)."""
    from core.sandbox.pptx_sandbox import PptxSandbox
    from core.file_store import store_file

    sandbox = PptxSandbox()
    result = sandbox.render_program(
        program_id, user_id=user_id, version=req.version,
    )
    if not result.success:
        raise HTTPException(status_code=404, detail=result.error or "Render failed")

    entry = store_file(
        data=result.data,
        filename=result.filename or "presentation.pptx",
        file_type="pptx",
        tool_name="pptx_program_render",
    )
    return GenerateResponse(
        success=True,
        program_id=program_id,
        version=req.version or 0,
        file_id=entry.file_id,
        filename=entry.filename,
        size_kb=entry.size_kb,
        download_url=f"/files/{entry.file_id}/download",
        canvas=result.canvas,
        warnings=result.warnings or [],
        exec_time_ms=result.exec_time_ms,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Revert
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{program_id}/revert/{version}", response_model=GenerateResponse)
async def revert(
    program_id: str,
    version: int,
    user_id: str = Depends(get_current_user_id),
):
    """Roll a program back to a prior version (creates a new version row)."""
    from core.sandbox import pptx_program_store
    from core.sandbox.pptx_sandbox import PptxSandbox

    rec = pptx_program_store.revert_to(program_id, version=version, user_id=user_id)
    if not rec:
        raise HTTPException(status_code=404, detail="version not found")

    sandbox = PptxSandbox()
    result = sandbox.render_program(program_id, user_id=user_id)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error or "Revert render failed")
    return _store_and_respond(result, program_id, rec.version)


# ─────────────────────────────────────────────────────────────────────────────
# Read
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/programs", response_model=List[ProgramSummary])
async def list_programs(user_id: str = Depends(get_current_user_id)):
    from core.sandbox import pptx_program_store
    rows = pptx_program_store.list_programs(user_id=user_id)
    return [
        ProgramSummary(
            id=r.get("id"),
            title=r.get("title") or "Untitled",
            version=int(r.get("version") or 1),
            canvas=r.get("canvas") or {},
            file_id=r.get("file_id"),
            created_at=str(r.get("created_at")) if r.get("created_at") else None,
            updated_at=str(r.get("updated_at")) if r.get("updated_at") else None,
        )
        for r in rows
    ]


@router.get("/{program_id}", response_model=ProgramDetail)
async def get_program(
    program_id: str,
    user_id: str = Depends(get_current_user_id),
):
    from core.sandbox import pptx_program_store
    rec = pptx_program_store.load_program(program_id, user_id=user_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Program not found")
    return ProgramDetail(
        id=rec.id,
        title=rec.title,
        canvas=rec.canvas,
        version=rec.version,
        file_id=rec.file_id,
        program=rec.program,
        asset_snapshot=rec.asset_snapshot or {},
    )


@router.get("/{program_id}/versions", response_model=List[VersionSummary])
async def list_versions(
    program_id: str,
    user_id: str = Depends(get_current_user_id),
):
    from core.sandbox import pptx_program_store
    # ensure the caller owns the program
    rec = pptx_program_store.load_program(program_id, user_id=user_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Program not found")
    rows = pptx_program_store.list_versions(program_id=program_id)
    return [
        VersionSummary(
            version=int(r.get("version") or 0),
            title=r.get("title"),
            canvas=r.get("canvas") or {},
            created_at=str(r.get("created_at")) if r.get("created_at") else None,
        )
        for r in rows
    ]
