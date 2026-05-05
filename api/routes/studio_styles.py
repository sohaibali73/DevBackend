"""
Content Studio — Voice cloning ("writing-style training") endpoints.

Mounted at /studio/styles/*

Wizard flow (frontend):
    1. POST /studio/styles                       — create draft {name}
    2. POST /studio/styles/{id}/samples          — add sample (text or upload)
    3. POST /studio/styles/{id}/analyze          — clone voice → status='ready'
    4. POST /studio/styles/{id}/preview          — vibe-check generation
    5. (project create) attach style_profile_id  — auto-injected into chat
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Path, Query, UploadFile
from pydantic import BaseModel

from api.dependencies import get_current_user_id, get_user_api_keys
from core.styles import cloner
from core.styles.injector import build_system_prompt
from core.humanize.llm import claude_rewrite

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/studio/styles", tags=["studio"])


# -----------------------------------------------------------------------------
# Pydantic
# -----------------------------------------------------------------------------

class CreateStyleRequest(BaseModel):
    name: str
    description: str = ""
    icon: str = "✍️"
    color: str = "#FEC00F"


class UpdateStyleRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None


class AddSampleTextRequest(BaseModel):
    text: str
    title: str = ""
    source_url: Optional[str] = None
    source_file_id: Optional[str] = None


class PreviewRequest(BaseModel):
    prompt: str
    max_tokens: int = 400


# -----------------------------------------------------------------------------
# DB helper
# -----------------------------------------------------------------------------

def _db():
    from db.supabase_client import get_supabase
    return get_supabase()


# -----------------------------------------------------------------------------
# Style CRUD
# -----------------------------------------------------------------------------

@router.post("")
async def create_style(
    body: CreateStyleRequest,
    user_id: str = Depends(get_current_user_id),
):
    db = _db()
    try:
        res = db.table("studio_writing_styles").insert({
            "user_id":     user_id,
            "name":        body.name.strip(),
            "description": body.description,
            "icon":        body.icon,
            "color":       body.color,
            "status":      "draft",
        }).execute()
    except Exception as e:
        msg = str(e)
        if "duplicate" in msg.lower() or "unique" in msg.lower():
            raise HTTPException(status_code=409, detail="style name already exists")
        raise HTTPException(status_code=500, detail=msg)
    if not res.data:
        raise HTTPException(status_code=500, detail="failed to create style")
    return {"style": res.data[0]}


@router.get("")
async def list_styles(
    user_id: str = Depends(get_current_user_id),
):
    db = _db()
    res = (
        db.table("studio_writing_styles")
        .select("id, name, description, icon, color, status, sample_count, total_words, "
                "fidelity_score, created_at, updated_at")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )
    return {"styles": res.data or []}


@router.get("/{style_id}")
async def get_style(
    style_id: str,
    user_id: str = Depends(get_current_user_id),
):
    s = cloner.get_style(style_id, user_id)
    if not s:
        raise HTTPException(status_code=404, detail="style not found")
    samples = cloner.list_samples(style_id, user_id)
    return {"style": s, "samples": samples}


@router.patch("/{style_id}")
async def update_style(
    style_id: str,
    body: UpdateStyleRequest,
    user_id: str = Depends(get_current_user_id),
):
    db = _db()
    fields = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not fields:
        return {"style": cloner.get_style(style_id, user_id)}
    res = (
        db.table("studio_writing_styles")
        .update(fields)
        .eq("id", style_id).eq("user_id", user_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="style not found")
    return {"style": res.data[0]}


@router.delete("/{style_id}")
async def delete_style(
    style_id: str,
    user_id: str = Depends(get_current_user_id),
):
    db = _db()
    db.table("studio_writing_styles").delete().eq("id", style_id).eq("user_id", user_id).execute()
    return {"deleted": True, "id": style_id}


# -----------------------------------------------------------------------------
# Samples
# -----------------------------------------------------------------------------

@router.post("/{style_id}/samples")
async def add_sample_text(
    style_id: str,
    body: AddSampleTextRequest,
    user_id: str = Depends(get_current_user_id),
):
    if not cloner.get_style(style_id, user_id):
        raise HTTPException(status_code=404, detail="style not found")
    try:
        sample = cloner.ingest_sample(
            user_id=user_id,
            style_id=style_id,
            text=body.text,
            title=body.title,
            source="paste" if not body.source_url else "url",
            source_url=body.source_url,
            source_file_id=body.source_file_id,
        )
        return {"sample": sample}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{style_id}/samples/upload")
async def upload_sample(
    style_id: str,
    file: UploadFile = File(...),
    title: str = Form(""),
    user_id: str = Depends(get_current_user_id),
):
    """Upload .txt/.md/.docx/.pdf — text is extracted with core.document_parser."""
    if not cloner.get_style(style_id, user_id):
        raise HTTPException(status_code=404, detail="style not found")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")

    text = ""
    fname = file.filename or "sample"
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""

    try:
        if ext in ("txt", "md"):
            text = content.decode("utf-8", errors="ignore")
        else:
            # Try the universal parser
            try:
                from core.document_parser import DocumentParser
                parser = DocumentParser()
                parsed = parser.parse_bytes(content, fname) if hasattr(parser, "parse_bytes") else None
                if parsed and getattr(parsed, "content", None):
                    text = parsed.content
                else:
                    text = content.decode("utf-8", errors="ignore")
            except Exception:
                text = content.decode("utf-8", errors="ignore")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"could not extract text: {e}")

    if not text.strip():
        raise HTTPException(status_code=400, detail="extracted text is empty")

    sample = cloner.ingest_sample(
        user_id=user_id,
        style_id=style_id,
        text=text,
        title=title or fname,
        source="file",
    )
    return {"sample": sample}


@router.get("/{style_id}/samples")
async def list_samples(
    style_id: str,
    user_id: str = Depends(get_current_user_id),
):
    if not cloner.get_style(style_id, user_id):
        raise HTTPException(status_code=404, detail="style not found")
    return {"samples": cloner.list_samples(style_id, user_id)}


@router.delete("/{style_id}/samples/{sample_id}")
async def delete_sample(
    style_id: str,
    sample_id: str,
    user_id: str = Depends(get_current_user_id),
):
    cloner.delete_sample(sample_id, user_id)
    return {"deleted": True, "id": sample_id}


# -----------------------------------------------------------------------------
# Analyze (voice clone)
# -----------------------------------------------------------------------------

@router.post("/{style_id}/analyze")
async def analyze(
    style_id: str,
    self_test: bool = Query(True),
    user_id: str = Depends(get_current_user_id),
    api_keys: Dict[str, str] = Depends(get_user_api_keys),
):
    api_key = (api_keys or {}).get("claude") or ""
    try:
        style = cloner.analyze_style(
            user_id=user_id,
            style_id=style_id,
            api_key=api_key,
            self_test=self_test,
        )
        return {"style": style}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("analyze failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"analyze failed: {e}")


@router.post("/{style_id}/preview")
async def preview(
    style_id: str,
    body: PreviewRequest,
    user_id: str = Depends(get_current_user_id),
    api_keys: Dict[str, str] = Depends(get_user_api_keys),
):
    """Generate a short sample in the cloned voice for vibe-check."""
    s = cloner.get_style(style_id, user_id)
    if not s:
        raise HTTPException(status_code=404, detail="style not found")
    if s.get("status") != "ready":
        raise HTTPException(status_code=400, detail="style not analyzed yet — POST /analyze first")

    api_key = (api_keys or {}).get("claude") or ""
    if not api_key:
        raise HTTPException(status_code=400, detail="claude api key required for preview")

    out = claude_rewrite(
        api_key=api_key,
        user_prompt=body.prompt,
        system_prompt=s.get("system_prompt") or "",
        max_tokens=min(800, max(100, body.max_tokens)),
        temperature=0.8,
    )
    return {"output": out}


# -----------------------------------------------------------------------------
# System prompt fetch (frontend uses this to display "system prompt" tab)
# -----------------------------------------------------------------------------

@router.get("/{style_id}/system_prompt")
async def get_system_prompt(
    style_id: str,
    user_id: str = Depends(get_current_user_id),
):
    s = cloner.get_style(style_id, user_id)
    if not s:
        raise HTTPException(status_code=404, detail="style not found")
    return {
        "status":         s.get("status"),
        "system_prompt":  s.get("system_prompt"),
        "fidelity_score": s.get("fidelity_score"),
        "voice_card":     s.get("voice_card"),
        "exemplars":      s.get("exemplars") or [],
    }
