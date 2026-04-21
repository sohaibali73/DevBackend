"""
core/yang/background_edit.py — Background Document Generation
=============================================================
When background_edit=True (user setting or per-request override), file-
generating tools (generate_pptx, generate_docx, generate_xlsx, revise_pptx,
generate_presentation) are submitted as background asyncio tasks instead of
blocking the response stream.

The tool call returns immediately with {"task_id": "...", "status": "queued"}
so Claude can acknowledge the operation and the stream can finish.  The actual
file generation continues in the background.  The frontend polls
  GET /yang/tasks/{task_id}
to check progress.

Storage: in-memory dict keyed by task_id.  Lost on container restart.
This is the documented limitation — a Redis/Supabase queue is a future upgrade.

Usage (from api/routes/chat.py):
    from core.yang.background_edit import (
        BG_EDIT_TOOLS, submit_background_edit, get_bg_task_status,
    )

    if yang_cfg.background_edit and tool_name in BG_EDIT_TOOLS:
        task_id, result_json = await submit_background_edit(
            tool_name=tool_name, tool_input=tool_input, ...
        )
        # result_json is the immediate tool_result content
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ─── Tools eligible for background execution ─────────────────────────────────

BG_EDIT_TOOLS: frozenset = frozenset({
    "generate_pptx",
    "generate_docx",
    "generate_xlsx",
    "revise_pptx",
    "generate_presentation",
    "transform_xlsx",
})

# ─── In-memory task store ─────────────────────────────────────────────────────

class _BgTask:
    """Lightweight in-memory task record."""
    __slots__ = (
        "task_id", "tool_name", "user_id", "conversation_id",
        "status", "result", "error", "created_at", "completed_at",
        "_asyncio_task",
    )

    def __init__(
        self,
        task_id: str,
        tool_name: str,
        user_id: str,
        conversation_id: str,
    ):
        self.task_id         = task_id
        self.tool_name       = tool_name
        self.user_id         = user_id
        self.conversation_id = conversation_id
        self.status          = "running"
        self.result: Optional[Any] = None
        self.error:  Optional[str] = None
        self.created_at      = time.time()
        self.completed_at: Optional[float] = None
        self._asyncio_task: Optional[asyncio.Task] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id":         self.task_id,
            "tool_name":       self.tool_name,
            "status":          self.status,
            "result":          self.result,
            "error":           self.error,
            "created_at":      self.created_at,
            "completed_at":    self.completed_at,
            "elapsed_s":       round(
                (self.completed_at or time.time()) - self.created_at, 2
            ),
        }


# Keyed by task_id; max 200 entries before oldest are pruned
_TASKS: Dict[str, _BgTask] = {}
_MAX_TASKS = 200


def _prune():
    if len(_TASKS) > _MAX_TASKS:
        # Remove oldest 20 % by created_at
        by_age = sorted(_TASKS.values(), key=lambda t: t.created_at)
        for t in by_age[: _MAX_TASKS // 5]:
            _TASKS.pop(t.task_id, None)


# ─── Public API ───────────────────────────────────────────────────────────────

async def submit_background_edit(
    tool_name: str,
    tool_input: Dict[str, Any],
    api_key: str,
    supabase_client: Any,
    conversation_file_ids: list,
    user_id: str,
    conversation_id: str,
) -> tuple:
    """
    Start the tool call as a background asyncio task.

    Returns:
        (task_id: str, result_json: str) — the immediate tool_result content.
        The caller should yield result_json as the tool result so Claude
        acknowledges the queued operation.
    """
    task_id = str(uuid.uuid4())
    rec = _BgTask(
        task_id=task_id,
        tool_name=tool_name,
        user_id=user_id,
        conversation_id=conversation_id,
    )
    _TASKS[task_id] = rec
    _prune()

    async def _run():
        from core.tools import handle_tool_call
        try:
            raw = await asyncio.to_thread(
                handle_tool_call,
                tool_name=tool_name,
                tool_input=tool_input,
                supabase_client=supabase_client,
                api_key=api_key,
                conversation_file_ids=conversation_file_ids,
            )
            rec.result = json.loads(raw) if isinstance(raw, str) else raw
            rec.status = "complete"
            logger.info(
                "background_edit: %s completed (task %s)", tool_name, task_id
            )
        except Exception as e:
            rec.error = str(e)
            rec.status = "failed"
            logger.warning(
                "background_edit: %s failed (task %s): %s", tool_name, task_id, e
            )
        finally:
            rec.completed_at = time.time()

    rec._asyncio_task = asyncio.create_task(_run())

    result_json = json.dumps({
        "task_id":  task_id,
        "status":   "queued",
        "tool":     tool_name,
        "note": (
            "File generation has been queued and is running in the background. "
            f"Poll GET /yang/tasks/{task_id} for status and the download URL."
        ),
    })
    logger.info(
        "background_edit: %s queued as task %s (conv %s)",
        tool_name, task_id, conversation_id,
    )
    return task_id, result_json


def get_bg_task_status(task_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """
    Return the status dict for a background task, or None if not found.
    Ownership is verified: only the creating user can query.
    """
    rec = _TASKS.get(task_id)
    if rec is None:
        return None
    if rec.user_id != user_id:
        return None  # treat as not-found for security
    return rec.to_dict()
