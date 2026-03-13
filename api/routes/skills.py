"""
Skills API Routes
==================
REST endpoints for listing and executing Claude custom beta skills.

Endpoints:
    GET  /api/skills                        – List all available skills
    GET  /api/skills/categories             – List skill categories with counts
    GET  /api/skills/{slug}                 – Get skill details
    POST /api/skills/{slug}/execute         – Execute a skill (blocking JSON response)
    POST /api/skills/{slug}/stream          – Execute a skill (Vercel AI SDK streaming)
    POST /api/skills/multi                  – Execute multiple skills in one request
"""

import json
import logging
import time
import uuid
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from api.dependencies import get_current_user_id, get_user_api_keys
from core.skills import (
    SkillCategory,
    get_categories,
    get_skill,
    list_skills_dict,
)
from core.skill_gateway import SkillGateway

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skills", tags=["Skills"])


# ============================================================================
# Request / Response Models
# ============================================================================

class SkillMessage(BaseModel):
    """A message in conversation history."""
    role: str = Field(..., description="Message role: user or assistant")
    content: str = Field(..., description="Message content")


class SkillExecuteRequest(BaseModel):
    """Request body for skill execution."""
    message: str = Field(..., description="User message / prompt for the skill")
    system_prompt: Optional[str] = Field(None, description="Override the skill's default system prompt")
    conversation_history: Optional[List[SkillMessage]] = Field(
        None, description="Prior conversation messages for context"
    )
    max_tokens: Optional[int] = Field(None, description="Override max tokens")
    extra_context: Optional[str] = Field("", description="Additional context (e.g. KB content)")
    stream: Optional[bool] = Field(False, description="If true, return AI SDK streaming response")


class MultiSkillRequest(BaseModel):
    """Request body for executing multiple skills."""
    requests: List[Dict[str, Any]] = Field(
        ...,
        description=(
            "List of skill execution requests. Each must have 'skill_slug' and 'message', "
            "plus optional 'system_prompt', 'max_tokens', 'extra_context'."
        ),
    )


class SkillExecuteResponse(BaseModel):
    """Response from a skill execution."""
    text: str
    skill: str
    skill_name: str
    usage: Optional[Dict[str, int]] = None
    model: Optional[str] = None
    execution_time: Optional[float] = None
    stop_reason: Optional[str] = None


# ============================================================================
# List / Discovery Endpoints
# ============================================================================

@router.get("")
@router.get("/")
async def list_all_skills(
    category: Optional[str] = Query(None, description="Filter by category slug"),
    _user_id: str = Depends(get_current_user_id),
):
    """
    List all available skills.

    Optionally filter by category: ``afl``, ``document``, ``presentation``,
    ``ui``, ``backtest``, ``market_analysis``, ``quant``, ``research``.
    """
    try:
        skills = list_skills_dict(category=category)
        return {
            "skills": skills,
            "total": len(skills),
            "category_filter": category,
        }
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid category: {category}")


@router.get("/categories")
async def list_categories(
    _user_id: str = Depends(get_current_user_id),
):
    """List skill categories with counts."""
    return {"categories": get_categories()}


@router.get("/{slug}")
async def get_skill_detail(
    slug: str,
    _user_id: str = Depends(get_current_user_id),
):
    """Get details for a specific skill."""
    skill = get_skill(slug)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found")
    return {"skill": skill.to_dict()}


# ============================================================================
# Execution Endpoints
# ============================================================================

@router.post("/{slug}/execute")
async def execute_skill(
    slug: str,
    request: SkillExecuteRequest,
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """
    Execute a skill and return the result.

    If ``stream`` is ``true`` in the request body, the response will be a
    Vercel AI SDK Data Stream (``text/plain; charset=utf-8``) compatible with
    ``useChat()`` / ``useCompletion()`` hooks.  Otherwise, returns JSON.
    """
    # Validate skill exists
    skill = get_skill(slug)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found")
    if not skill.enabled:
        raise HTTPException(status_code=400, detail=f"Skill '{slug}' is currently disabled")

    # Validate API key
    claude_key = api_keys.get("claude")
    if not claude_key:
        raise HTTPException(
            status_code=400,
            detail="Claude API key not configured. Please add your API key in Profile Settings.",
        )

    gateway = SkillGateway(api_key=claude_key)

    # Build conversation history in Anthropic format
    history = None
    if request.conversation_history:
        history = [{"role": m.role, "content": m.content} for m in request.conversation_history]

    if request.stream:
        # Return Vercel AI SDK streaming response
        return StreamingResponse(
            gateway.stream_ai_sdk(
                skill_slug=slug,
                user_message=request.message,
                system_prompt=request.system_prompt,
                conversation_history=history,
                max_tokens=request.max_tokens,
                extra_context=request.extra_context or "",
            ),
            media_type="text/plain; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Vercel-AI-Data-Stream": "v1",
                "X-Skill-Slug": slug,
                "X-Skill-Name": skill.name,
                "Access-Control-Expose-Headers": "X-Skill-Slug, X-Skill-Name, X-Vercel-AI-Data-Stream",
            },
        )

    # Blocking JSON response
    try:
        result = gateway.execute(
            skill_slug=slug,
            user_message=request.message,
            system_prompt=request.system_prompt,
            conversation_history=history,
            max_tokens=request.max_tokens,
            extra_context=request.extra_context or "",
        )

        # If the skill produced file artifacts, download them and add download URLs
        skill_files = result.get("files", [])
        if skill_files:
            try:
                from core.file_store import store_file
                downloaded = gateway.download_files(skill_files)
                download_info = []
                for dl in downloaded:
                    fname = dl.get("filename", "")
                    data = dl.get("content", b"") or dl.get("data", b"")
                    claude_file_id = dl.get("file_id", "")
                    if data and fname:
                        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else "bin"
                        entry = store_file(
                            data=data,
                            filename=fname,
                            file_type=ext,
                            tool_name=f"skill:{slug}",
                            file_id=claude_file_id or None,
                        )
                        download_info.append({
                            "file_id": entry.file_id,
                            "filename": entry.filename,
                            "file_type": entry.file_type,
                            "size_kb": entry.size_kb,
                            "download_url": f"/files/{entry.file_id}/download",
                        })
                        logger.info("Skill %s: stored file %s (%.1f KB)", slug, fname, entry.size_kb)
                if download_info:
                    result["downloadable_files"] = download_info
                    # Also set top-level download_url for simple frontend access
                    result["download_url"] = download_info[0]["download_url"]
                    result["filename"] = download_info[0]["filename"]
            except Exception as dl_err:
                logger.warning("Failed to download skill files for %s: %s", slug, dl_err)

        return JSONResponse(content=result)

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Skill execution failed for %s: %s", slug, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Skill execution failed: {str(exc)}")


@router.post("/{slug}/stream")
async def stream_skill(
    slug: str,
    request: SkillExecuteRequest,
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """
    Stream a skill response using Vercel AI SDK Data Stream Protocol.

    This is a convenience endpoint that always streams, regardless of the
    ``stream`` field in the request body.  Use this with ``useChat()``::

        const { messages, input, handleSubmit } = useChat({
            api: '/api/skills/backtest-expert/stream',
        });
    """
    skill = get_skill(slug)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found")
    if not skill.enabled:
        raise HTTPException(status_code=400, detail=f"Skill '{slug}' is currently disabled")

    claude_key = api_keys.get("claude")
    if not claude_key:
        raise HTTPException(
            status_code=400,
            detail="Claude API key not configured. Please add your API key in Profile Settings.",
        )

    gateway = SkillGateway(api_key=claude_key)

    history = None
    if request.conversation_history:
        history = [{"role": m.role, "content": m.content} for m in request.conversation_history]

    return StreamingResponse(
        gateway.stream_ai_sdk(
            skill_slug=slug,
            user_message=request.message,
            system_prompt=request.system_prompt,
            conversation_history=history,
            max_tokens=request.max_tokens,
            extra_context=request.extra_context or "",
        ),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Vercel-AI-Data-Stream": "v1",
            "X-Skill-Slug": slug,
            "X-Skill-Name": skill.name,
            "Access-Control-Expose-Headers": "X-Skill-Slug, X-Skill-Name, X-Vercel-AI-Data-Stream",
        },
    )


# ============================================================================
# Background Job System for Skills
# ============================================================================

_skill_jobs: dict = {}  # job_id -> job record


def _make_skill_job(job_id: str, user_id: str, skill_slug: str, skill_name: str, message: str) -> dict:
    record = {
        "id": job_id,
        "user_id": user_id,
        "type": "skill_execution",
        "skill_slug": skill_slug,
        "skill_name": skill_name,
        "message": message[:200],
        "status": "pending",
        "progress": 0,
        "status_message": "Queued…",
        "result": None,
        "error": None,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    _skill_jobs[job_id] = record
    return record


def _update_skill_job(job_id: str, **kwargs):
    if job_id in _skill_jobs:
        _skill_jobs[job_id].update(kwargs)
        _skill_jobs[job_id]["updated_at"] = time.time()


def _prune_skill_jobs():
    cutoff = time.time() - 7200  # 2 hours
    stale = [jid for jid, j in _skill_jobs.items() if j.get("created_at", 0) < cutoff]
    for jid in stale:
        del _skill_jobs[jid]


async def _run_skill_job(job_id: str, skill_slug: str, message: str, claude_key: str, extra_context: str = ""):
    """Background task: execute a skill and store result."""
    _update_skill_job(job_id, status="running", progress=20, status_message="Executing skill…")
    try:
        from core.skill_gateway import SkillGateway

        def _execute():
            gw = SkillGateway(api_key=claude_key)
            return gw.execute(skill_slug=skill_slug, user_message=message, extra_context=extra_context)

        _update_skill_job(job_id, progress=40, status_message="Waiting for AI response…")
        result = await asyncio.to_thread(_execute)
        _update_skill_job(
            job_id,
            status="complete",
            progress=100,
            status_message="Done!",
            result={
                "text": result.get("text", ""),
                "skill": result.get("skill", skill_slug),
                "skill_name": result.get("skill_name", ""),
                "execution_time": result.get("execution_time", 0),
                "usage": result.get("usage", {}),
                "model": result.get("model", ""),
            },
        )
    except Exception as e:
        logger.error("Skill job %s failed: %s", job_id, e, exc_info=True)
        _update_skill_job(job_id, status="error", progress=0, status_message="Failed", error=str(e))


class SkillJobRequest(BaseModel):
    """Request to submit a background skill job."""
    message: str = Field(..., description="Prompt for the skill")
    extra_context: Optional[str] = Field("", description="Additional context")


@router.post("/{slug}/job")
async def submit_skill_job(
    slug: str,
    request: SkillJobRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """
    Submit a skill job to run in the background. Returns job_id immediately.
    Poll ``GET /api/skills/jobs/{job_id}`` for status and result.
    User can navigate away — the job runs server-side.
    """
    skill = get_skill(slug)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found")

    claude_key = api_keys.get("claude")
    if not claude_key:
        raise HTTPException(status_code=400, detail="Claude API key not configured.")

    _prune_skill_jobs()
    job_id = str(uuid.uuid4())
    job = _make_skill_job(job_id, user_id, slug, skill.name, request.message)

    background_tasks.add_task(
        _run_skill_job, job_id, slug, request.message, claude_key, request.extra_context or ""
    )

    return {"job_id": job_id, "status": "pending", "skill": slug, "skill_name": skill.name}


@router.get("/jobs")
async def list_skill_jobs(user_id: str = Depends(get_current_user_id)):
    """List all skill jobs for the current user (active and completed within 2h)."""
    _prune_skill_jobs()
    jobs = [
        {
            "job_id": jid,
            "skill_slug": j.get("skill_slug"),
            "skill_name": j.get("skill_name"),
            "message": j.get("message"),
            "status": j.get("status"),
            "progress": j.get("progress", 0),
            "status_message": j.get("status_message", ""),
            "has_result": j.get("result") is not None,
            "error": j.get("error"),
            "created_at": j.get("created_at"),
            "updated_at": j.get("updated_at"),
        }
        for jid, j in _skill_jobs.items()
        if j.get("user_id") == user_id
    ]
    return {"jobs": sorted(jobs, key=lambda x: x.get("created_at", 0), reverse=True)}


@router.get("/jobs/{job_id}")
async def get_skill_job(job_id: str, user_id: str = Depends(get_current_user_id)):
    """Get status and result of a skill job."""
    job = _skill_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    if job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return {
        "job_id": job_id,
        "skill_slug": job.get("skill_slug"),
        "skill_name": job.get("skill_name"),
        "message": job.get("message"),
        "status": job.get("status"),
        "progress": job.get("progress", 0),
        "status_message": job.get("status_message", ""),
        "result": job.get("result"),
        "error": job.get("error"),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
    }


@router.post("/multi")
async def execute_multi_skills(
    request: MultiSkillRequest,
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """
    Execute multiple skills sequentially and return all results.

    Example request body::

        {
            "requests": [
                {"skill_slug": "backtest-expert", "message": "Analyze this equity curve..."},
                {"skill_slug": "quant-analyst", "message": "Build a momentum factor..."}
            ]
        }
    """
    claude_key = api_keys.get("claude")
    if not claude_key:
        raise HTTPException(
            status_code=400,
            detail="Claude API key not configured. Please add your API key in Profile Settings.",
        )

    # Validate all skills first
    for req in request.requests:
        slug = req.get("skill_slug")
        if not slug:
            raise HTTPException(status_code=400, detail="Each request must include 'skill_slug'")
        if not req.get("message"):
            raise HTTPException(status_code=400, detail=f"Request for '{slug}' is missing 'message'")
        skill = get_skill(slug)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found")

    gateway = SkillGateway(api_key=claude_key)

    start = time.time()
    results = gateway.execute_multi(request.requests)
    total_time = round(time.time() - start, 2)

    return {
        "results": results,
        "total_skills": len(results),
        "total_execution_time": total_time,
    }
