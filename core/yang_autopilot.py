"""
core.yang_autopilot
===================

YANG Autopilot — Phase 3 (Goals) + Phase 4 (Memory & Schedules).

Three pieces:

* **Memory store** — ``memories`` table + cosine-similarity search.
* **Goal runner** — drives a goal forward one Claude turn at a time, persists
  every event as a ``goal_steps`` row, and reuses
  :mod:`core.desktop_pending` for client-executed tools.
* **Scheduler** — polls ``scheduled_jobs`` every 30 s and spawns goals when
  cron expressions fall due.

Everything is keyed by Supabase auth UUIDs (matches the rest of the codebase).
The recipe specifies BIGINT user IDs but we standardize on UUID across the app.

This module purposefully avoids new heavy dependencies: scheduling uses
``asyncio.create_task`` from the FastAPI lifespan, and SSE events are
streamed from an in-process ``asyncio.Queue`` fanout (no LISTEN/NOTIFY).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import anthropic
import httpx

from core import desktop_pending
from core.desktop_tools import DESKTOP_TOOL_NAMES, desktop_tools_for
from core.yang_cu_tools import YANG_CU_TOOL_NAMES, yang_cu_tools_for
from core.yang_workflow_tools import (
    YANG_WORKFLOW_TOOL_NAMES,
    yang_workflow_tools_for,
)
from core.tools import get_tools_for_api, handle_tool_call
from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Shared constants
# ────────────────────────────────────────────────────────────────────────────

# Every tool name whose execution lives on the Electron client. The agent
# loop short-circuits these and waits on a ``desktop_pending`` future for the
# client to POST the result back to ``/chat/agent/tool-result``.
CLIENT_EXECUTED_TOOL_NAMES: frozenset[str] = (
    DESKTOP_TOOL_NAMES
    | YANG_CU_TOOL_NAMES
    | YANG_WORKFLOW_TOOL_NAMES
)


def is_client_executed(tool_name: str) -> bool:
    """True if the named tool must be executed by the Electron client.

    Also matches the ``mcp_*`` prefix so user-installed MCP tools are routed
    through the same pause/resume pipeline (their schemas are advertised by
    the client; the server just relays).
    """
    return tool_name in CLIENT_EXECUTED_TOOL_NAMES or tool_name.startswith("mcp_")

GOAL_STATUSES = {
    "queued", "running", "waiting_for_input", "paused",
    "done", "failed", "cancelled",
}

# Configurable from main.py if needed.
TICKER_INTERVAL_S = 5.0       # how often we look for queued goals to advance
SCHEDULER_INTERVAL_S = 30.0   # how often we look for due scheduled_jobs

# Per-goal cap so a runaway loop can't burn an entire account.
MAX_STEPS_PER_GOAL = 60

# Client-executed tool wait budget (per call).
CLIENT_TOOL_TIMEOUT_S = 300.0


# ────────────────────────────────────────────────────────────────────────────
# SSE fan-out
# ────────────────────────────────────────────────────────────────────────────
# Each running goal has a list of asyncio.Queue subscribers. The runner pushes
# events to every subscriber. The /goals/{id}/stream endpoint creates a new
# queue, hands the goal a reference, and yields from it.

_subscribers: dict[str, list[asyncio.Queue]] = {}
_subscribers_lock = asyncio.Lock()


async def _subscribe(goal_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=512)
    async with _subscribers_lock:
        _subscribers.setdefault(goal_id, []).append(q)
    return q


async def _unsubscribe(goal_id: str, q: asyncio.Queue) -> None:
    async with _subscribers_lock:
        lst = _subscribers.get(goal_id) or []
        if q in lst:
            lst.remove(q)
        if not lst and goal_id in _subscribers:
            _subscribers.pop(goal_id, None)


def _broadcast_nowait(goal_id: str, event: dict[str, Any]) -> None:
    """Push an event to every subscriber. Drops to oldest if full."""
    for q in list(_subscribers.get(goal_id, [])):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            try:
                _ = q.get_nowait()  # drop oldest
                q.put_nowait(event)
            except Exception:
                pass


# ────────────────────────────────────────────────────────────────────────────
# DB helpers (sync Supabase client run via asyncio.to_thread)
# ────────────────────────────────────────────────────────────────────────────

def _db():
    return get_supabase()


async def _to_thread(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


# ────────────────────────────────────────────────────────────────────────────
# Goals: CRUD
# ────────────────────────────────────────────────────────────────────────────

async def create_goal(
    user_id: str,
    title: str,
    prompt: str,
    description: Optional[str] = None,
    conversation_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    def _ins():
        return (
            _db()
            .table("goals")
            .insert({
                "user_id": user_id,
                "title": title[:200] or "Goal",
                "description": description,
                "prompt": prompt,
                "status": "queued",
                "conversation_id": conversation_id,
                "metadata": metadata or {},
            })
            .execute()
        )

    result = await _to_thread(_ins)
    if not result.data:
        raise RuntimeError("Failed to create goal")
    goal = result.data[0]
    # Don't wait — let the ticker pick it up.
    asyncio.create_task(tick_goal(goal["id"]))
    return goal


async def list_goals(user_id: str, limit: int = 100) -> list[dict]:
    def _q():
        return (
            _db()
            .table("goals")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    r = await _to_thread(_q)
    return r.data or []


async def get_goal(user_id: str, goal_id: str) -> Optional[dict]:
    def _q():
        return (
            _db()
            .table("goals")
            .select("*")
            .eq("id", goal_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    r = await _to_thread(_q)
    return (r.data or [None])[0]


async def get_goal_steps(goal_id: str) -> list[dict]:
    def _q():
        return (
            _db()
            .table("goal_steps")
            .select("id, goal_id, idx, kind, content, ts")
            .eq("goal_id", goal_id)
            .order("idx")
            .order("id")
            .execute()
        )
    r = await _to_thread(_q)
    return r.data or []


async def control_goal(user_id: str, goal_id: str, action: str) -> Optional[dict]:
    goal = await get_goal(user_id, goal_id)
    if not goal:
        return None
    cur = goal["status"]
    new_status: Optional[str] = None
    if action == "pause" and cur in ("queued", "running", "waiting_for_input"):
        new_status = "paused"
    elif action == "resume" and cur == "paused":
        new_status = "queued"
    elif action == "cancel" and cur not in ("done", "failed", "cancelled"):
        new_status = "cancelled"
    if not new_status:
        return goal

    await _set_status(goal_id, new_status, user_id=user_id)
    goal = await get_goal(user_id, goal_id)
    if new_status == "queued":
        asyncio.create_task(tick_goal(goal_id))
    return goal


async def delete_goal(user_id: str, goal_id: str) -> bool:
    def _d():
        return (
            _db()
            .table("goals")
            .delete()
            .eq("id", goal_id)
            .eq("user_id", user_id)
            .execute()
        )
    r = await _to_thread(_d)
    return bool(r.data)


async def _set_status(goal_id: str, status: str, user_id: Optional[str] = None) -> None:
    if status not in GOAL_STATUSES:
        raise ValueError(f"invalid goal status: {status}")

    update: dict[str, Any] = {"status": status}
    if status in ("done", "failed", "cancelled"):
        update["finished_at"] = datetime.now(timezone.utc).isoformat()

    def _u():
        return (
            _db()
            .table("goals")
            .update(update)
            .eq("id", goal_id)
            .execute()
        )

    try:
        await _to_thread(_u)
    except Exception as e:
        logger.warning("goals: failed to update status: %s", e)

    _broadcast_nowait(goal_id, {"type": "status", "status": status})
    if status == "done":
        _broadcast_nowait(goal_id, {"type": "done"})


async def _save_step(
    goal_id: str,
    user_id: str,
    idx: int,
    kind: str,
    content: dict | list | str,
) -> dict | None:
    def _ins():
        return (
            _db()
            .table("goal_steps")
            .insert({
                "goal_id": goal_id,
                "user_id": user_id,
                "idx": idx,
                "kind": kind,
                "content": content if isinstance(content, (dict, list)) else {"text": content},
            })
            .execute()
        )
    try:
        r = await _to_thread(_ins)
        row = (r.data or [None])[0]
        if row:
            _broadcast_nowait(goal_id, {"type": "step", "step": row})
        return row
    except Exception as e:
        logger.warning("goals: failed to save step (%s): %s", kind, e)
        return None


# ────────────────────────────────────────────────────────────────────────────
# Memory
# ────────────────────────────────────────────────────────────────────────────

VOYAGE_DIM = 1024  # matches migration 026 / Voyage-2 model


async def _embed(text: str) -> Optional[list[float]]:
    """Compute a 1024-d Voyage embedding for ``text``. Returns None on failure."""
    try:
        from core.embeddings import embed_many
        embeds = await embed_many([text[:8000]], model="voyage-2")
        if embeds and embeds[0] is not None:
            return embeds[0]
    except Exception as e:
        logger.debug("yang_autopilot._embed failed: %s", e)
    return None


async def memory_save(
    user_id: str,
    key: str,
    value: Any,
    kind: str = "fact",
    tags: Optional[list[str]] = None,
    source_goal_id: Optional[str] = None,
) -> dict:
    """Insert or update a memory; recomputes embedding from ``{key, value}``."""
    key = (key or "").strip()
    if not key:
        raise ValueError("memory key is required")
    if kind not in ("preference", "fact", "tool_recipe", "schedule"):
        kind = "fact"

    payload = {
        "user_id": user_id,
        "kind": kind,
        "key": key,
        "value": value if isinstance(value, (dict, list)) else {"text": str(value)},
        "tags": list(tags or []),
        "source_goal_id": source_goal_id,
    }
    emb_input = json.dumps({"key": key, "value": payload["value"]}, ensure_ascii=False)
    emb = await _embed(emb_input)
    if emb is not None:
        payload["embedding"] = emb

    def _upsert():
        return (
            _db()
            .table("memories")
            .upsert(payload, on_conflict="user_id,key")
            .execute()
        )

    r = await _to_thread(_upsert)
    return (r.data or [payload])[0]


async def memory_search(user_id: str, query: str, limit: int = 8) -> list[dict]:
    """Top-K cosine-similar memories. Falls back to most-recent when no embedding."""
    limit = max(1, min(int(limit or 8), 50))
    q = (query or "").strip()

    if q:
        emb = await _embed(q)
        if emb is not None:
            def _rpc():
                return _db().rpc(
                    "match_memories",
                    {
                        "query_embedding": emb,
                        "match_threshold": 0.3,
                        "match_count": limit,
                        "p_user_id": user_id,
                    },
                ).execute()
            try:
                r = await _to_thread(_rpc)
                return r.data or []
            except Exception as e:
                logger.debug("memory_search RPC failed (non-fatal): %s", e)

    # Fallback: most-recently updated rows.
    def _q():
        return (
            _db()
            .table("memories")
            .select("id, key, value, kind, tags, updated_at")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )
    r = await _to_thread(_q)
    return r.data or []


async def memory_delete(user_id: str, key: str) -> bool:
    def _d():
        return (
            _db()
            .table("memories")
            .delete()
            .eq("user_id", user_id)
            .eq("key", key)
            .execute()
        )
    r = await _to_thread(_d)
    return bool(r.data)


async def build_memory_block(user_id: str, query: str, limit: int = 8) -> str:
    """Render a ``<learned_preferences>`` system-prompt block for the agent."""
    rows = await memory_search(user_id, query, limit=limit)
    if not rows:
        return ""
    lines: list[str] = []
    for m in rows:
        v = m.get("value")
        try:
            v_str = (
                v.get("text") if isinstance(v, dict) and "text" in v
                else json.dumps(v, ensure_ascii=False)
            )
        except Exception:
            v_str = str(v)
        lines.append(f"- {m.get('key')}: {v_str}")
    return (
        "<learned_preferences>\n"
        "These are facts the user has previously asked you to remember. "
        "Honour them unless the user explicitly contradicts them.\n"
        + "\n".join(lines)
        + "\n</learned_preferences>"
    )


# ────────────────────────────────────────────────────────────────────────────
# Scheduling helpers (cron-like, hand-rolled)
# ────────────────────────────────────────────────────────────────────────────
#
# Supports the standard 5-field cron format (m h dom mon dow) plus the
# convenience expressions "@hourly", "@daily", "@weekly", "@monthly".
# Hand-rolled to avoid pulling in the ``croniter`` dependency for one feature.

def _parse_field(expr: str, lo: int, hi: int) -> set[int]:
    out: set[int] = set()
    for piece in (expr or "*").split(","):
        piece = piece.strip()
        if not piece:
            continue
        step = 1
        if "/" in piece:
            piece, s = piece.split("/", 1)
            step = max(1, int(s))
        if piece in ("*", ""):
            rng = range(lo, hi + 1)
        elif "-" in piece:
            a, b = piece.split("-", 1)
            rng = range(int(a), int(b) + 1)
        else:
            rng = [int(piece)]
        for v in rng:
            if lo <= v <= hi:
                out.add(v)
    if not out:
        out = set(range(lo, hi + 1))
    return out


def next_cron_time(expr: str, after: Optional[datetime] = None) -> datetime:
    """
    Compute the next datetime ≥ ``after`` (default now()) that matches the
    cron expression, in UTC. ``@`` aliases supported. Days-of-week use
    0=Sunday … 6=Saturday (cron-style).
    """
    expr = (expr or "").strip().lower()
    after = (after or datetime.now(timezone.utc)).replace(microsecond=0)

    aliases = {
        "@hourly":  "0 * * * *",
        "@daily":   "0 0 * * *",
        "@midnight": "0 0 * * *",
        "@weekly":  "0 0 * * 0",
        "@monthly": "0 0 1 * *",
        "@yearly":  "0 0 1 1 *",
        "@annually": "0 0 1 1 *",
    }
    if expr in aliases:
        expr = aliases[expr]

    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"invalid cron expression: {expr!r}")

    mins  = _parse_field(parts[0], 0, 59)
    hours = _parse_field(parts[1], 0, 23)
    doms  = _parse_field(parts[2], 1, 31)
    mons  = _parse_field(parts[3], 1, 12)
    dows  = _parse_field(parts[4], 0, 6)

    # Start search from the next minute.
    candidate = after + timedelta(minutes=1)
    candidate = candidate.replace(second=0, microsecond=0)

    for _ in range(366 * 24 * 60):  # at most 1 year ahead
        # cron uses Sunday=0, Python uses Monday=0 → adjust
        py_dow = candidate.weekday()
        cron_dow = (py_dow + 1) % 7
        if (
            candidate.minute in mins
            and candidate.hour in hours
            and candidate.day in doms
            and candidate.month in mons
            and cron_dow in dows
        ):
            return candidate
        candidate += timedelta(minutes=1)

    raise ValueError(f"cron expression matched no datetime in 1y: {expr!r}")


# ────────────────────────────────────────────────────────────────────────────
# Scheduled jobs CRUD
# ────────────────────────────────────────────────────────────────────────────

async def create_schedule(
    user_id: str,
    name: str,
    cron: str,
    prompt: str,
) -> dict:
    # Validate cron.
    next_dt = next_cron_time(cron)
    def _ins():
        return (
            _db()
            .table("scheduled_jobs")
            .insert({
                "user_id": user_id,
                "name": name or "Schedule",
                "cron": cron,
                "prompt": prompt,
                "enabled": True,
                "next_run_at": next_dt.isoformat(),
            })
            .execute()
        )
    r = await _to_thread(_ins)
    return (r.data or [None])[0]


async def list_schedules(user_id: str) -> list[dict]:
    def _q():
        return (
            _db()
            .table("scheduled_jobs")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
    r = await _to_thread(_q)
    return r.data or []


async def delete_schedule(user_id: str, schedule_id: str) -> bool:
    def _d():
        return (
            _db()
            .table("scheduled_jobs")
            .delete()
            .eq("id", schedule_id)
            .eq("user_id", user_id)
            .execute()
        )
    r = await _to_thread(_d)
    return bool(r.data)


# ────────────────────────────────────────────────────────────────────────────
# Goal runner
# ────────────────────────────────────────────────────────────────────────────

# Goals currently being ticked. Using a set instead of an asyncio.Lock per
# goal is necessary because the lock-based "is in flight?" check has a
# TOCTOU race: multiple ticks can all observe `lock.locked() == False`
# before any of them actually acquires the lock, then they serialize on
# `async with lock:` and all run end-to-end — producing duplicate plans,
# notes, and tool calls. ``set.add`` is atomic in single-threaded asyncio
# (no await point between the membership check and the add), so it gives
# us a true "first one wins" guarantee.
_running_goals: set[str] = set()


def _step_kind_to_role(kind: str) -> Optional[str]:
    """Map goal_step kinds back to Claude message roles when reconstructing context."""
    if kind in ("plan", "thought", "note"):
        return "assistant"
    return None  # tool-call / tool-result handled separately


def _build_history_from_steps(steps: list[dict]) -> list[dict]:
    """
    Rebuild a minimal Claude message history from previously persisted steps.

    We render each prior assistant note / plan as a plain assistant message and
    every tool-call/tool-result pair as Anthropic-shape blocks so the model can
    resume cleanly.  Stops at the most recent ``note`` to avoid replaying tools
    that already finished.
    """
    msgs: list[dict] = []
    pending_tool_uses: dict[str, dict] = {}
    for s in steps:
        kind = s.get("kind")
        content = s.get("content") or {}
        if kind == "plan":
            text = (
                content.get("plan") if isinstance(content, dict) else str(content)
            )
            if text:
                msgs.append({"role": "assistant", "content": f"Plan:\n{text}"})
        elif kind in ("thought", "note"):
            text = content.get("text") if isinstance(content, dict) else str(content)
            if text:
                msgs.append({"role": "assistant", "content": text})
        elif kind == "tool-call":
            tu_id = content.get("id") or content.get("tool_call_id")
            name = content.get("name", "")
            args = content.get("args") or content.get("input") or {}
            if tu_id and name:
                pending_tool_uses[tu_id] = {"name": name, "input": args}
                msgs.append({
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": tu_id, "name": name, "input": args}],
                })
        elif kind == "tool-result":
            tu_id = content.get("id") or content.get("tool_call_id")
            result = content.get("result")
            if tu_id:
                msgs.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tu_id,
                        "content": json.dumps(result) if not isinstance(result, str) else result,
                    }],
                })
    return msgs


async def _wait_for_client_tool(
    conversation_id: str,
    tool_call_id: str,
    tool_name: str,
    timeout_s: float = CLIENT_TOOL_TIMEOUT_S,
) -> Any:
    fut = desktop_pending.register(conversation_id, tool_call_id, tool_name=tool_name)
    try:
        return await asyncio.wait_for(asyncio.shield(fut), timeout=timeout_s)
    except asyncio.TimeoutError:
        desktop_pending.cancel(conversation_id, tool_call_id)
        return {"error": f"client did not return result for {tool_name} within {int(timeout_s)}s"}


async def _claude_key_for(user_id: str) -> Optional[str]:
    """Best-effort fetch of the user's decrypted Claude key (falls back to server)."""
    try:
        from api.dependencies import _fetch_api_keys_for_user  # type: ignore
        keys = await _fetch_api_keys_for_user(user_id)
        return keys.get("claude") or None
    except Exception:
        return None


async def _plan_step(
    client: anthropic.AsyncAnthropic,
    model: str,
    sys_prompt: str,
    prompt: str,
    available_tool_names: list[str] | None = None,
) -> str:
    """Ask the model to produce a short bullet plan before any tool calls.

    The full real tool catalogue is named explicitly so the planner can't
    hallucinate tools that don't exist (e.g. ``cu_launch_application`` when
    the real entry point is ``cu_open_target``).
    """
    tool_recap = ""
    if available_tool_names:
        # Cap the recap so we don't blow the context if 50+ tools are loaded.
        _shown = ", ".join(sorted(set(available_tool_names))[:80])
        tool_recap = (
            "\n\nThe ONLY tools you can use in this goal are the following "
            f"(use these exact names — do NOT invent new ones):\n{_shown}"
        )
    plan_sys = (
        sys_prompt
        + "\n\nYou are about to start a long-running autonomous goal. "
        "Reply with a short bullet plan (no more than 6 bullets) describing "
        "how you intend to accomplish the goal, referring to the available "
        "tools by their exact names. Do not call any tools yet. "
        "Reply with plain text only."
        + tool_recap
    )
    try:
        resp = await client.messages.create(
            model=model,
            max_tokens=600,
            system=plan_sys,
            messages=[{"role": "user", "content": prompt}],
        )
        out: list[str] = []
        for b in resp.content or []:
            if getattr(b, "type", None) == "text":
                out.append(b.text)
        return "\n".join(out).strip() or "(no plan generated)"
    except Exception as e:
        logger.warning("yang_autopilot: plan_step failed: %s", e)
        return "(plan generation failed — proceeding directly)"


async def tick_goal(goal_id: str) -> None:
    """
    Advance one goal by a single Claude turn (with up to a few iterations
    when the model chains tools). Re-schedules itself if the goal is not
    yet finished.
    """
    # Set-membership guard (see _running_goals docstring above).
    if goal_id in _running_goals:
        return  # another tick is already in flight
    _running_goals.add(goal_id)
    try:
        try:
            await _tick_goal_inner(goal_id)
        except Exception as e:
            logger.exception("yang_autopilot: tick_goal crashed: %s", e)
            try:
                goal = await _to_thread(
                    lambda: _db().table("goals").select("user_id").eq("id", goal_id).limit(1).execute()
                )
                user_id = (goal.data or [{}])[0].get("user_id", "")
                if user_id:
                    await _save_step(goal_id, user_id, 9999, "error", {"message": str(e)[:1000]})
                await _set_status(goal_id, "failed")
            except Exception:
                pass
    finally:
        _running_goals.discard(goal_id)


async def _tick_goal_inner(goal_id: str) -> None:
    # Re-fetch the goal — status may have changed (paused/cancelled) between
    # the schedule call and now.
    def _qg():
        return _db().table("goals").select("*").eq("id", goal_id).limit(1).execute()

    r = await _to_thread(_qg)
    goal = (r.data or [None])[0]
    if not goal:
        return
    if goal["status"] in ("done", "failed", "cancelled", "paused"):
        return

    user_id = goal["user_id"]
    api_key = await _claude_key_for(user_id)
    if not api_key:
        await _save_step(goal_id, user_id, 9999, "error", {
            "message": "No Claude API key configured for this user — cannot run goals.",
        })
        await _set_status(goal_id, "failed")
        return

    await _set_status(goal_id, "running")

    # ── Build context ────────────────────────────────────────────────────
    steps = await get_goal_steps(goal_id)
    next_idx = (max((s["idx"] for s in steps), default=-1)) + 1
    history = _build_history_from_steps(steps)

    # Hard cap on steps: prevent runaway goals.
    if len(steps) >= MAX_STEPS_PER_GOAL:
        await _save_step(goal_id, user_id, next_idx, "error", {
            "message": f"goal exceeded {MAX_STEPS_PER_GOAL} steps — stopping.",
        })
        await _set_status(goal_id, "failed")
        return

    # Memory injection.
    memory_block = await build_memory_block(user_id, goal["prompt"], limit=8)
    base_sys = (
        "You are YANG Autopilot, an autonomous agent working on a long-running "
        "goal for the user. Be concise, take small concrete steps, prefer "
        "read-only inspection before mutating tools, and remember to call "
        "memory_save when you discover a user preference or recurring fact. "
        "When the goal is fully complete, do not call any tool — just answer "
        "with a short summary."
    )
    # Describe the desktop/cu/workflow tool families up front so the model
    # doesn't fall back to "I don't have access to those tools" hallucinations.
    _goal_caps = list(((goal.get("metadata") or {}).get("capabilities")) or [
        "fs", "shell", "computer", "yang_cu", "yang_workflow",
    ])
    try:
        from core.desktop_tools     import build_desktop_system_block as _dsb
        from core.yang_cu_tools     import build_yang_cu_system_block as _cusb
        from core.yang_workflow_tools import build_yang_workflow_system_block as _wsb
        for _b in (_dsb(_goal_caps), _cusb(_goal_caps), _wsb(_goal_caps)):
            if _b:
                base_sys += "\n\n" + _b
    except Exception as _sb_err:
        logger.debug("yang_autopilot: system block injection skipped: %s", _sb_err)
    sys_prompt = base_sys + (("\n\n" + memory_block) if memory_block else "")

    # ── Tool list (built BEFORE the plan step so the planner sees the real
    #    catalogue and stops hallucinating tool names like cu_launch_application). ─
    try:
        server_tools = get_tools_for_api(tool_search=False)
    except Exception:
        server_tools = []

    goal_meta = goal.get("metadata") or {}
    caps: list[str] = list(goal_meta.get("capabilities") or [
        "fs", "shell", "computer", "yang_cu", "yang_workflow",
    ])
    try:
        desktop_defs   = desktop_tools_for(caps)
    except Exception:
        desktop_defs = []
    try:
        cu_defs        = yang_cu_tools_for(caps)
    except Exception:
        cu_defs = []
    try:
        workflow_defs  = yang_workflow_tools_for(caps)
    except Exception:
        workflow_defs = []

    tools = (
        list(server_tools)
        + _memory_tool_defs()
        + desktop_defs
        + cu_defs
        + workflow_defs
    )
    _all_tool_names = [t.get("name", "") for t in tools if isinstance(t, dict) and t.get("name")]
    logger.info(
        "goal %s: assembled %d tools (server=%d, memory=2, desktop=%d, cu=%d, workflow=%d) caps=%s",
        goal_id, len(tools), len(server_tools), len(desktop_defs), len(cu_defs),
        len(workflow_defs), caps,
    )

    # ── Plan once at idx=0 if not already planned ────────────────────────
    if not goal.get("plan_jsonb"):
        client = anthropic.AsyncAnthropic(
            api_key=api_key,
            timeout=httpx.Timeout(timeout=600.0, connect=30.0, read=600.0, write=60.0),
        )
        model = goal.get("metadata", {}).get("model") or "claude-sonnet-4-5"
        plan_text = await _plan_step(
            client, model, sys_prompt, goal["prompt"],
            available_tool_names=_all_tool_names,
        )
        await _save_step(goal_id, user_id, next_idx, "plan", {"plan": plan_text})
        next_idx += 1
        def _u():
            return _db().table("goals").update({"plan_jsonb": {"plan": plan_text}}).eq("id", goal_id).execute()
        try:
            await _to_thread(_u)
        except Exception:
            pass
        # Reflect the freshly-written plan locally so the in-memory ``goal``
        # dict matches the DB. Without this a follow-up tick on the same
        # call would replan, although the set-membership guard usually
        # prevents that.
        goal["plan_jsonb"] = {"plan": plan_text}

    # ── Single Claude turn (may stream multiple tool calls) ──────────────
    client = anthropic.AsyncAnthropic(
        api_key=api_key,
        timeout=httpx.Timeout(timeout=600.0, connect=30.0, read=600.0, write=60.0),
    )
    model = goal.get("metadata", {}).get("model") or "claude-sonnet-4-5"

    # Build messages.
    #
    # Claude requires conversations to BEGIN with a `user` message. Our
    # reconstructed history starts with the planner's assistant turn
    # (``Plan:\n...``) — without re-seeding the user prompt the API
    # rejects the call OR the model has no idea what it's being asked
    # to do (causing the infinite "I don't have access to those tools"
    # loop the user reported).
    #
    # Fix: always lead with the goal prompt, then append whatever
    # history we reconstructed.
    messages: list[dict] = [{"role": "user", "content": goal["prompt"]}]
    if history:
        messages.extend(history)
        # After the rebuilt history we need another user message so the
        # model has something to respond to (Anthropic requires the LAST
        # message to be ``user`` for the next turn).
        last = history[-1]
        if last.get("role") != "user":
            messages.append({
                "role": "user",
                "content": (
                    "Continue working on the goal. Call the next tool needed, "
                    "or if the goal is fully complete, summarise what you did "
                    "and stop calling tools."
                ),
            })

    try:
        resp = await client.messages.create(
            model=model,
            max_tokens=8192,
            system=sys_prompt,
            messages=messages,
            tools=tools,
        )
    except Exception as e:
        await _save_step(goal_id, user_id, next_idx, "error", {"message": f"Claude API error: {e}"})
        await _set_status(goal_id, "failed")
        return

    assistant_text_parts: list[str] = []
    tool_uses: list[dict] = []
    for block in resp.content or []:
        b_type = getattr(block, "type", None)
        if b_type == "text":
            assistant_text_parts.append(block.text)
        elif b_type == "tool_use":
            tool_uses.append({
                "id":    block.id,
                "name":  block.name,
                "input": getattr(block, "input", {}) or {},
            })

    # Stop reason — if 'tool_use', we'll come back. If 'end_turn', finish.
    stop_reason = getattr(resp, "stop_reason", None)

    if assistant_text_parts:
        await _save_step(
            goal_id, user_id, next_idx, "note",
            {"text": "\n".join(assistant_text_parts).strip()},
        )
        next_idx += 1

    if not tool_uses:
        # No tools requested. Done.
        await _set_status(goal_id, "done")
        await _save_step(goal_id, user_id, next_idx, "done", {})
        return

    # ── Execute each tool ────────────────────────────────────────────────
    for tu in tool_uses:
        name = tu["name"]; args = tu["input"]; tu_id = tu["id"]
        await _save_step(goal_id, user_id, next_idx, "tool-call", {
            "id": tu_id, "name": name, "args": args,
        })
        next_idx += 1

        # Re-check status between tool calls so pause/cancel takes effect fast.
        cur = await get_goal(user_id, goal_id)
        if not cur or cur["status"] in ("paused", "cancelled", "failed"):
            return

        if name in CLIENT_EXECUTED_TOOL_NAMES:
            # We need a conversation_id for the client to route the result.
            # Use the goal_id itself as the pseudo-conversation key.
            await _set_status(goal_id, "waiting_for_input")
            conv_key = goal.get("conversation_id") or f"goal:{goal_id}"
            result = await _wait_for_client_tool(conv_key, tu_id, name)
            await _set_status(goal_id, "running")
        elif name == "memory_save":
            try:
                m = await memory_save(
                    user_id=user_id,
                    key=str(args.get("key", "")),
                    value=args.get("value"),
                    kind=str(args.get("kind", "fact")),
                    tags=args.get("tags") or [],
                    source_goal_id=goal_id,
                )
                result = {"ok": True, "id": m.get("id"), "key": m.get("key")}
            except Exception as e:
                result = {"error": str(e)}
        elif name == "memory_search":
            try:
                rows = await memory_search(
                    user_id=user_id,
                    query=str(args.get("query", "")),
                    limit=int(args.get("limit", 8) or 8),
                )
                result = {"matches": rows}
            except Exception as e:
                result = {"error": str(e)}
        else:
            # Standard server-side tools.
            try:
                api_keys = {"claude": api_key}
                # Some tools want extra context; pass safe defaults.
                raw = await asyncio.to_thread(
                    handle_tool_call,
                    tool_name=name,
                    tool_input=args,
                    supabase_client=_db(),
                    api_key=api_key,
                    conversation_file_ids=[],
                    conversation_id=goal.get("conversation_id") or "",
                )
                try:
                    result = json.loads(raw) if isinstance(raw, str) else raw
                except Exception:
                    result = {"raw": str(raw)}
            except Exception as e:
                result = {"error": str(e)}

        await _save_step(goal_id, user_id, next_idx, "tool-result", {
            "id": tu_id, "name": name, "result": result,
        })
        next_idx += 1

    # If the stop_reason was tool_use, schedule another tick to feed results
    # back to Claude.
    if stop_reason == "tool_use":
        # Small delay so the SSE consumer can render the partial events first.
        await asyncio.sleep(0.5)
        asyncio.create_task(tick_goal(goal_id))
    else:
        await _set_status(goal_id, "done")
        await _save_step(goal_id, user_id, next_idx, "done", {})


def _memory_tool_defs() -> list[dict]:
    """Anthropic-shape tool defs for memory_save / memory_search."""
    return [
        {
            "name": "memory_save",
            "description": (
                "Save a long-term memory for the current user. Use this when "
                "the user states a preference (e.g. 'I prefer bullet points'), "
                "a recurring fact (e.g. their company name), or a tool recipe "
                "you want to remember for later. Memories are user-scoped."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Short memorable key."},
                    "value": {
                        "type": ["string", "object", "array"],
                        "description": "The value to remember.",
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["preference", "fact", "tool_recipe", "schedule"],
                        "default": "fact",
                    },
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["key", "value"],
            },
        },
        {
            "name": "memory_search",
            "description": (
                "Search the user's long-term memories by semantic similarity. "
                "Returns the top-K most relevant memories. Use this before "
                "asking the user a question whose answer they may have already "
                "given you."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 8, "minimum": 1, "maximum": 50},
                },
                "required": ["query"],
            },
        },
    ]


# ────────────────────────────────────────────────────────────────────────────
# Background workers (driven by FastAPI lifespan in main.py)
# ────────────────────────────────────────────────────────────────────────────

_ticker_task: Optional[asyncio.Task] = None
_scheduler_task: Optional[asyncio.Task] = None


async def _ticker_loop() -> None:
    """Periodically advance queued / running goals."""
    while True:
        try:
            def _q():
                return (
                    _db()
                    .table("goals")
                    .select("id")
                    .in_("status", ["queued", "running"])
                    .limit(50)
                    .execute()
                )
            r = await _to_thread(_q)
            for row in (r.data or []):
                asyncio.create_task(tick_goal(row["id"]))
        except Exception as e:
            logger.debug("yang_autopilot ticker non-fatal error: %s", e)
        await asyncio.sleep(TICKER_INTERVAL_S)


async def _scheduler_loop() -> None:
    """Periodically spawn goals from due scheduled_jobs."""
    while True:
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            def _q():
                return (
                    _db()
                    .table("scheduled_jobs")
                    .select("*")
                    .eq("enabled", True)
                    .lte("next_run_at", now_iso)
                    .limit(50)
                    .execute()
                )
            r = await _to_thread(_q)
            for sched in (r.data or []):
                try:
                    await create_goal(
                        user_id=sched["user_id"],
                        title=sched["name"],
                        prompt=sched["prompt"],
                        description=f"Spawned by schedule {sched['name']!r} (cron: {sched['cron']})",
                        metadata={"source": "schedule", "schedule_id": sched["id"]},
                    )
                    next_dt = next_cron_time(sched["cron"])
                    def _u(sched=sched, next_dt=next_dt):
                        return (
                            _db()
                            .table("scheduled_jobs")
                            .update({
                                "last_run_at": now_iso,
                                "next_run_at": next_dt.isoformat(),
                            })
                            .eq("id", sched["id"])
                            .execute()
                        )
                    await _to_thread(_u)
                except Exception as e:
                    logger.warning("yang_autopilot scheduler: failed sched %s: %s", sched.get("id"), e)
        except Exception as e:
            logger.debug("yang_autopilot scheduler non-fatal error: %s", e)
        await asyncio.sleep(SCHEDULER_INTERVAL_S)


def start_background_workers() -> None:
    """Idempotently start the ticker + scheduler on the current event loop."""
    global _ticker_task, _scheduler_task
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return
    if _ticker_task is None or _ticker_task.done():
        _ticker_task = loop.create_task(_ticker_loop())
        logger.info("yang_autopilot: ticker started")
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = loop.create_task(_scheduler_loop())
        logger.info("yang_autopilot: scheduler started")


async def stop_background_workers() -> None:
    """Cancel the workers on shutdown."""
    for t in (_ticker_task, _scheduler_task):
        if t and not t.done():
            t.cancel()
            try:
                await t
            except Exception:
                pass


# ────────────────────────────────────────────────────────────────────────────
# SSE stream entrypoint (consumed by the router)
# ────────────────────────────────────────────────────────────────────────────

async def goal_stream(user_id: str, goal_id: str):
    """Async generator yielding SSE-formatted lines for a single goal."""
    goal = await get_goal(user_id, goal_id)
    if not goal:
        # Match the frontend shape so it can gracefully close.
        yield _sse({"type": "status", "status": "failed"})
        yield _sse({"type": "done"})
        return

    queue = await _subscribe(goal_id)
    try:
        # Emit current state for fast hydration.
        yield _sse({"type": "status", "status": goal["status"]})
        # Replay existing steps.
        for s in await get_goal_steps(goal_id):
            yield _sse({"type": "step", "step": s})
        # If the goal is already terminal, send done and exit.
        if goal["status"] in ("done", "failed", "cancelled"):
            yield _sse({"type": "done"})
            return
        # Live tail.
        while True:
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                # Heartbeat comment — keeps the SSE alive through proxies.
                yield ": heartbeat\n\n"
                continue
            yield _sse(evt)
            if evt.get("type") == "done":
                return
            if evt.get("type") == "status" and evt.get("status") in ("failed", "cancelled"):
                yield _sse({"type": "done"})
                return
    finally:
        await _unsubscribe(goal_id, queue)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


# ────────────────────────────────────────────────────────────────────────────
# Slash-command parser for /remember /schedule etc.
# ────────────────────────────────────────────────────────────────────────────

_SCHEDULE_RE = re.compile(
    r"^/schedule\s+(?P<spec>.+?)\s+(?P<prompt>.+)$",
    re.IGNORECASE | re.DOTALL,
)


def parse_slash_command(text: str) -> Optional[dict]:
    """
    Return ``{ "cmd": "goal"|"remember"|"schedule", ... }`` for the supported
    slash commands or ``None`` if the message isn't a slash command.

    Supported:
        /goal <text>
        /remember <text>           → kind=fact, key=<sha1[:8]>
        /remember <key>: <value>   → explicit key
        /schedule <cron-or-alias> <prompt>
        /schedule daily 8am <prompt>   (special phrase → @daily / 8 0 * * *)
    """
    if not text or not text.lstrip().startswith("/"):
        return None
    t = text.strip()

    if t.lower().startswith("/goal "):
        body = t[6:].strip()
        if not body:
            return None
        return {"cmd": "goal", "prompt": body, "title": body[:80]}

    if t.lower().startswith("/remember "):
        body = t[10:].strip()
        if not body:
            return None
        if ":" in body:
            key, _, value = body.partition(":")
            key = key.strip()[:120] or _short_key(body)
            value = value.strip()
        else:
            key = _short_key(body)
            value = body
        return {"cmd": "remember", "key": key, "value": value, "kind": "preference"}

    if t.lower().startswith("/schedule "):
        body = t[10:].strip()
        # Try the "daily 8am" / "weekly mon 9am" friendly forms first.
        friendly = _parse_friendly_schedule(body)
        if friendly:
            cron_expr, remainder = friendly
            if remainder:
                return {
                    "cmd": "schedule",
                    "cron": cron_expr,
                    "name": remainder[:80],
                    "prompt": remainder,
                }
        # Fall back to "<cron> <prompt>" with the cron being a 5-field expr
        # or an @alias.
        parts = body.split(None, 1)
        if len(parts) == 2 and (
            parts[0].startswith("@") or parts[0].count(" ") >= 0
        ):
            # Heuristic: if the first 5 tokens look cron-y, treat them as cron.
            tokens = body.split()
            if len(tokens) >= 6 and all(_looks_cron_field(x) for x in tokens[:5]):
                cron_expr = " ".join(tokens[:5])
                remainder = " ".join(tokens[5:])
                return {"cmd": "schedule", "cron": cron_expr, "name": remainder[:80], "prompt": remainder}
            if parts[0].startswith("@"):
                return {"cmd": "schedule", "cron": parts[0], "name": parts[1][:80], "prompt": parts[1]}
        return None

    return None


def _short_key(text: str) -> str:
    import hashlib
    return "mem_" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def _looks_cron_field(s: str) -> bool:
    return bool(re.fullmatch(r"[\d\*\-/,]+", s))


_TIME_RE = re.compile(r"^\s*(\d{1,2})\s*(am|pm)?\s*$", re.IGNORECASE)
_DAYS = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}


def _parse_friendly_schedule(body: str) -> Optional[tuple[str, str]]:
    """
    Try to parse phrases like ``daily 8am Give me ...`` or ``weekly mon 9 ...``
    into ``(cron_expr, remaining_prompt)``.
    """
    tokens = body.split()
    if not tokens:
        return None
    head = tokens[0].lower()
    if head == "daily":
        # next token = time
        if len(tokens) < 3:
            return None
        time_tok = tokens[1]
        m = _TIME_RE.match(time_tok)
        if not m:
            return None
        hour = _normalise_hour(int(m.group(1)), m.group(2))
        cron = f"0 {hour} * * *"
        return cron, " ".join(tokens[2:]).strip()
    if head == "hourly":
        return "0 * * * *", " ".join(tokens[1:]).strip()
    if head == "weekly":
        if len(tokens) < 4:
            return None
        dow = _DAYS.get(tokens[1].lower())
        if dow is None:
            return None
        m = _TIME_RE.match(tokens[2])
        if not m:
            return None
        hour = _normalise_hour(int(m.group(1)), m.group(2))
        cron = f"0 {hour} * * {dow}"
        return cron, " ".join(tokens[3:]).strip()
    return None


def _normalise_hour(h: int, ampm: Optional[str]) -> int:
    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and h < 12:
            h += 12
        elif ampm == "am" and h == 12:
            h = 0
    return max(0, min(23, h))
