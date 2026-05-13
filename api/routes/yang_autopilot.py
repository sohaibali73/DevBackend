"""
api.routes.yang_autopilot
=========================

YANG Autopilot HTTP surface — Goals, Memory, Schedules, Artifacts.

Mounted by ``main.py``.  Frontend Edge proxies live under
``/api/yang/{goal,goal/[id],goal/[id]/stream,memory,schedule}`` and just
forward to these endpoints.

Auth: standard JWT (``get_current_user_id``) for every route.

The actual goal runner / SSE fan-out / memory store live in
:mod:`core.yang_autopilot` — this router is a thin HTTP wrapper.

Artifact bytes live on the Railway volume and are served from
``GET /goals/{id}/artifacts/{aid}`` with proper Content-Disposition,
Content-Length, ETag (``sha256:<hex>``) and Cache-Control headers. HEAD
requests are supported for resume / skip / hash lookups. After the
retention window (24h post terminal status) the bytes are GC'd from disk
and the endpoint returns 410 Gone — the row stays so the SSE artifact
step's url is still meaningful.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field

from api.dependencies import get_current_user_id
from core import artifacts as ya_artifacts
from core import yang_autopilot as ya

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["YANG Autopilot"])


# ────────────────────────────────────────────────────────────────────────────
# Request/Response models
# ────────────────────────────────────────────────────────────────────────────

class EmailOnComplete(BaseModel):
    enabled: bool = False
    to:      Optional[str] = None


class GoalOptions(BaseModel):
    """Optional creation-time hints persisted into ``goals.metadata.options``."""
    emailOnComplete: Optional[EmailOnComplete] = None
    saveArtifactsTo: Optional[str] = None
    notify:          Optional[bool] = None


class GoalCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    prompt: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None
    model: Optional[str] = None
    # ── Additive: frontend may send capabilities so the agent knows which
    #    desktop tool families are available (e.g. ["fs","shell","outlook"]).
    capabilities: Optional[list[str]] = None
    # ── Additive: new in spec — per-goal options bag.
    options: Optional[GoalOptions] = None


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
    if data.capabilities:
        meta["capabilities"] = list(data.capabilities)
    if data.options is not None:
        # Persist as plain dict so the runner can read it without a Pydantic
        # round-trip. ``model_dump(exclude_none=True)`` keeps the JSON tidy.
        meta["options"] = data.options.model_dump(exclude_none=True)
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
    """List all goals for the current user, most-recently-updated first.

    Items include ``updatedAt`` (ms epoch) alongside the original
    ``updated_at`` ISO string so the frontend dock can sort/group by
    recency without re-parsing.
    """
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
        data: {"type": "status", "status": "running", "activity": "...",
               "currentStepIdx": 3, "totalSteps": 6}
        data: {"type": "step",   "step": {...goal_steps row...}}
        data: {"type": "step",   "step": {"kind": "artifact", "content": {...}}}
        data: {"type": "done"}

    Every ≤15 seconds the stream emits a ``: keepalive\\n\\n`` SSE comment so
    edge proxies don't close idle connections during long tool calls.
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
# Artifacts (Part 1 of the spec)
# ────────────────────────────────────────────────────────────────────────────

@router.get("/goals/{goal_id}/artifacts")
async def list_goal_artifacts(
    goal_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    List the artifacts a goal has produced. Cheaper than scanning
    ``steps[]`` for ``kind == "artifact"``. Each entry is the same
    frontend-facing dict shape emitted on the SSE stream:

    ::

        { id, name, mime, bytes, sha256, url, producedBy, createdAt }

    The ``url`` is always ``/goals/{goal_id}/artifacts/{id}`` — append the
    user's Bearer token at the edge.
    """
    goal = await ya.get_goal(user_id, goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return await ya_artifacts.list_artifacts(goal_id, user_id)


def _stream_file(path: str, chunk: int = 1 << 16):
    def _gen():
        with open(path, "rb") as f:
            while True:
                buf = f.read(chunk)
                if not buf:
                    break
                yield buf
    return _gen


@router.api_route(
    "/goals/{goal_id}/artifacts/{artifact_id}",
    methods=["GET", "HEAD"],
)
async def download_goal_artifact(
    goal_id: str,
    artifact_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    """
    Download (or HEAD) an artifact's bytes.

    * 200 OK with binary body + ``Content-Disposition: attachment; filename=…``
    * 401 implicit via ``get_current_user_id``
    * 404 if the artifact doesn't exist or isn't owned by this user
    * 410 Gone if the artifact's bytes have been GC'd from disk
      (row still present so the SSE artifact step's url is meaningful).

    HEAD short-circuits before streaming, returning the same headers (so the
    desktop client can size the destination file before downloading).
    """
    row = await ya_artifacts.get_artifact(goal_id, artifact_id, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Artifact not found")

    if row.get("deleted_at"):
        # Retention GC removed the bytes — frontend should drop its
        # "Download" affordance for this artifact.
        raise HTTPException(status_code=410, detail="Artifact has been deleted")

    path = row.get("storage_path") or ""
    if not path or not os.path.exists(path):
        # Bytes missing on disk but row not marked deleted (unexpected).
        # Treat as 410 so the frontend handles it the same way.
        raise HTTPException(status_code=410, detail="Artifact bytes missing")

    filename = row.get("name") or "artifact"
    mime = row.get("mime") or "application/octet-stream"
    size = int(row.get("bytes") or 0)
    sha = row.get("sha256") or ""

    # Build headers — same for HEAD and GET.
    headers = {
        "Content-Type":        mime,
        "Content-Length":      str(size),
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control":       "private, max-age=3600",
    }
    if sha:
        headers["ETag"] = f'"sha256:{sha}"'

    if request.method == "HEAD":
        return Response(status_code=200, headers=headers)

    return StreamingResponse(
        _stream_file(path)(),
        status_code=200,
        media_type=mime,
        headers=headers,
    )


# ────────────────────────────────────────────────────────────────────────────
# Debug fixture — generate a fake artifact so the frontend can wire its
# download path end-to-end without running a real tool. Gated by env var so
# it's never on in production unless the operator opts in.
# ────────────────────────────────────────────────────────────────────────────

_DEBUG_ENABLED = os.getenv("YANG_DEBUG_FIXTURES", "1") not in ("0", "false", "no")


@router.post("/goals/{goal_id}/_debug/emit_fake_artifact")
async def emit_fake_artifact(
    goal_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Register a tiny text artifact and emit the corresponding SSE step.
    Useful for verifying the end-to-end download path before any real tool
    runs. Disable in production by setting ``YANG_DEBUG_FIXTURES=0``.
    """
    if not _DEBUG_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")
    goal = await ya.get_goal(user_id, goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    import time
    name = f"debug_{int(time.time())}.txt"
    entry = await ya_artifacts.register_artifact_bytes(
        goal_id=goal_id, user_id=user_id,
        data=(
            "YANG debug artifact.\n"
            f"goal_id={goal_id}\nuser_id={user_id}\nts={int(time.time())}\n"
        ).encode("utf-8"),
        name=name, mime="text/plain", produced_by="_debug_emit_fake_artifact",
    )
    if not entry:
        raise HTTPException(status_code=500, detail="Could not register artifact")

    # Persist as a step too so a late GET /goals/{id} sees it in `steps`.
    steps = await ya.get_goal_steps(goal_id)
    next_idx = (max((s["idx"] for s in steps), default=-1)) + 1
    await ya._save_step(goal_id, user_id, next_idx, "artifact", entry)
    return entry


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
