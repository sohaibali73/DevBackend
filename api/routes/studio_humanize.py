"""
Content Studio — Humanizer endpoints.

Mounted at /studio/humanize/*

    POST /studio/humanize          — full multi-pass rewrite + scoring
    POST /studio/humanize/score    — score-only (no rewriting)
    GET  /studio/humanize/runs     — list past runs (paginated)
    GET  /studio/humanize/runs/{id} — full trace (from volume)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.dependencies import get_current_user_id, get_user_api_keys
from core.humanize import pipeline as humanizer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/studio/humanize", tags=["studio"])


class HumanizeRequest(BaseModel):
    text: str
    project_id: Optional[str] = None
    conversation_id: Optional[str] = None
    style_profile_id: Optional[str] = None
    intensity: str = "standard"           # 'light' | 'standard' | 'max'
    seo_target: Optional[str] = None      # 'linkedin' | None
    preserve_facts: bool = True
    annotate_lost_facts: bool = False
    seed: Optional[int] = None


class ScoreRequest(BaseModel):
    text: str


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@router.post("")
async def humanize(
    body: HumanizeRequest,
    user_id: str = Depends(get_current_user_id),
    api_keys: Dict[str, str] = Depends(get_user_api_keys),
):
    if not (body.text or "").strip():
        raise HTTPException(status_code=400, detail="text is required")

    if body.intensity not in ("light", "standard", "max"):
        raise HTTPException(status_code=400, detail="intensity must be light|standard|max")
    if body.seo_target not in (None, "linkedin"):
        raise HTTPException(status_code=400, detail="seo_target must be 'linkedin' or null")

    api_key = (api_keys or {}).get("claude") or ""

    try:
        result = humanizer.run(
            text=body.text,
            api_key=api_key,
            user_id=user_id,
            project_id=body.project_id,
            conversation_id=body.conversation_id,
            style_profile_id=body.style_profile_id,
            intensity=body.intensity,
            seo_target=body.seo_target,
            preserve_facts=body.preserve_facts,
            annotate_lost_facts=body.annotate_lost_facts,
            seed=body.seed,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("humanize failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"humanize failed: {e}")


@router.post("/score")
async def score(
    body: ScoreRequest,
    user_id: str = Depends(get_current_user_id),
):
    if not (body.text or "").strip():
        raise HTTPException(status_code=400, detail="text is required")
    return humanizer.score(body.text)


@router.get("/runs")
async def list_runs(
    project_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user_id),
):
    from db.supabase_client import get_supabase
    db = get_supabase()
    q = (
        db.table("studio_humanization_runs")
        .select(
            "id, project_id, conversation_id, style_profile_id, intensity, seo_target, "
            "input_word_count, output_word_count, final_scores, detector_retries, "
            "duration_ms, status, created_at"
        )
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit).offset(offset)
    )
    if project_id:
        q = q.eq("project_id", project_id)
    res = q.execute()
    return {"runs": res.data or []}


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
):
    from db.supabase_client import get_supabase
    db = get_supabase()
    res = (
        db.table("studio_humanization_runs")
        .select("*")
        .eq("id", run_id).eq("user_id", user_id)
        .limit(1).execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="run not found")
    row = res.data[0]
    # Try to load full trace from volume
    trace = None
    vp = row.get("volume_path")
    if vp and os.path.exists(vp):
        try:
            with open(vp, "r", encoding="utf-8") as f:
                trace = json.load(f)
        except Exception:
            trace = None
    return {"run": row, "trace": trace}
