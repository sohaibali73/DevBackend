"""
api.routes.yang_autopilot
=========================

YANG Autopilot HTTP surface — Goals, Memory, Schedules.

Mounted by ``main.py``.  Frontend Edge proxies live under
``/api/yang/{goal,goal/[id],goal/[id]/stream,memory,schedule}`` and just
forward to these endpoints.

Auth: standard JWT (``get_current_user_id``) for every route.

The actual goal runner / SSE fan-out / memory store live in
:mod:`core.yang_autopilot` — this router is a thin HTTP wrapper.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.dependencies import get_current_user_id
from core import yang_autopilot as ya

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["YANG Autopilot"])


# ────────────────────────────────────────────────────────────────────────────
# Request/Response models
# ────────────────────────────────────────────────────────────────────────────

class GoalCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    prompt: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None
    model: Optional[str] = None


class GoalControlRequest(BaseModel):
    action: Literal["pause", "resume", "cancel"]


class MemorySaveRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=200)
    value: Any
    kind: Literal["preference", "fact", "tool_recipe", "schedule"] = "fact"
    tags: list[str] = []


class ScheduleCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    cron: str = Field(..., min_length=1, max_length=120)
    prompt: str = Field(..., min_length=1)


# ────────────────────────────────────────────────────────────────────────────
# Goals
# ────────────────────────────────────────────────────────────────────────────

@router.post("/goals")
async def create_goal(
    data: GoalCreateRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Create a new goal. Worker picks it up within a few seconds."""
    meta: dict[str, Any] = {}
    if data.model:
        meta["model"] = data.model
    goal = await ya.create_goal(
        user_id=user_id,
        title=data.title,
        prompt=data.prompt,
        description=data.description,
        conversation_id=data.conversation_id,
        metadata=meta,
    )
    return goal


@router.get("/goals")
async def list_goals(user_id: str = Depends(get_current_user_id)):
    """List all goals for the current user, newest first."""
    return await ya.list_goals(user_id)


@router.get("/goals/{goal_id}")
async def get_goal(
    goal_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Fetch a goal + all its persisted steps (for hydration)."""
    goal = await ya.get_goal(user_id, goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    steps = await ya.get_goal_steps(goal_id)
    return {"goal": goal, "steps": steps}


@router.post("/goals/{goal_id}/control")
async def control_goal(
    goal_id: str,
    payload: GoalControlRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Pause / resume / cancel a goal."""
    goal = await ya.control_goal(user_id, goal_id, payload.action)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.delete("/goals/{goal_id}")
async def delete_goal(
    goal_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a goal and all its steps."""
    ok = await ya.delete_goal(user_id, goal_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"ok": True}


@router.get("/goals/{goal_id}/stream")
async def stream_goal(
    goal_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    """
    Server-Sent Events stream of goal events. Replays existing steps then
    tails new ones.  Frontend ``EventSource`` consumes:

    ::

        data: {"type": "status", "status": "running"}
        data: {"type": "step",   "step": {...goal_steps row...}}
        data: {"type": "done"}
    """
    # Validate ownership up front so a 404 is a real HTTP error, not an SSE close.
    goal = await ya.get_goal(user_id, goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    headers = {
        "Cache-Control":     "no-cache, no-transform",
        "Connection":        "keep-alive",
        "X-Accel-Buffering": "no",       # disable proxy buffering (nginx/Railway)
        "Content-Type":      "text/event-stream; charset=utf-8",
    }
    return StreamingResponse(
        ya.goal_stream(user_id, goal_id),
        media_type="text/event-stream; charset=utf-8",
        headers=headers,
    )


# ────────────────────────────────────────────────────────────────────────────
# Memory
# ────────────────────────────────────────────────────────────────────────────

@router.post("/memory/save")
async def memory_save(
    data: MemorySaveRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Insert or update a memory; embedding recomputed on every save."""
    try:
        m = await ya.memory_save(
            user_id=user_id,
            key=data.key,
            value=data.value,
            kind=data.kind,
            tags=data.tags,
        )
        return m
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/memory/search")
async def memory_search(
    q: str = "",
    limit: int = 20,
    user_id: str = Depends(get_current_user_id),
):
    """Top-K cosine-similar memories. Empty ``q`` returns most-recent."""
    rows = await ya.memory_search(user_id, q, limit=limit)
    return {"memories": rows, "count": len(rows)}


@router.delete("/memory/{key}")
async def memory_delete(
    key: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a memory by key. 404 if it doesn't exist."""
    ok = await ya.memory_delete(user_id, key)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True}


# ────────────────────────────────────────────────────────────────────────────
# Schedules
# ────────────────────────────────────────────────────────────────────────────

@router.post("/schedule")
async def create_schedule(
    data: ScheduleCreateRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Create a recurring goal. Cron is validated server-side."""
    try:
        s = await ya.create_schedule(
            user_id=user_id, name=data.name, cron=data.cron, prompt=data.prompt,
        )
        return s
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/schedules")
async def list_schedules(user_id: str = Depends(get_current_user_id)):
    """List the user's scheduled jobs."""
    return await ya.list_schedules(user_id)


@router.delete("/schedule/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a scheduled job."""
    ok = await ya.delete_schedule(user_id, schedule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"ok": True}


# ────────────────────────────────────────────────────────────────────────────
# Slash-command bridge — used by the chat UI to translate /goal /remember
# /schedule into the right backend call without round-tripping through the
# agent loop. The frontend can either call this directly OR keep it routed
# through the chat endpoint and let the agent loop dispatch.
# ────────────────────────────────────────────────────────────────────────────

class SlashCommandRequest(BaseModel):
    text: str
    conversation_id: Optional[str] = None


@router.post("/yang/slash")
async def slash_dispatch(
    data: SlashCommandRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Translate a single slash command and execute it. Returns the created
    resource (goal / memory / schedule) or 400 if the command isn't
    recognised.
    """
    parsed = ya.parse_slash_command(data.text)
    if not parsed:
        raise HTTPException(status_code=400, detail="Unrecognised slash command")

    cmd = parsed["cmd"]
    if cmd == "goal":
        goal = await ya.create_goal(
            user_id=user_id,
            title=parsed["title"],
            prompt=parsed["prompt"],
            conversation_id=data.conversation_id,
        )
        return {"cmd": "goal", "goal": goal}
    if cmd == "remember":
        m = await ya.memory_save(
            user_id=user_id,
            key=parsed["key"],
            value=parsed["value"],
            kind=parsed.get("kind", "preference"),
        )
        return {"cmd": "remember", "memory": m}
    if cmd == "schedule":
        try:
            s = await ya.create_schedule(
                user_id=user_id,
                name=parsed["name"],
                cron=parsed["cron"],
                prompt=parsed["prompt"],
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"cmd": "schedule", "schedule": s}

    raise HTTPException(status_code=400, detail=f"Unhandled command: {cmd}")
