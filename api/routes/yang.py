"""
api/routes/yang.py — YANG Advanced Agentic Features API
=======================================================
Provides CRUD for per-user YANG settings and conversation checkpoints.

Endpoints:
    GET  /yang/settings                    — fetch current settings
    PATCH /yang/settings                   — partial update settings

    GET  /yang/checkpoints                 — list checkpoints for a conversation
    POST /yang/checkpoints                 — create a manual checkpoint
    POST /yang/checkpoints/{id}/restore    — restore conversation to a checkpoint
    DELETE /yang/checkpoints/{id}          — delete a checkpoint

Router prefix: /yang
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.dependencies import get_current_user_id
from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/yang", tags=["YANG"])


# ─── Pydantic models ─────────────────────────────────────────────────────────

class YangSettingsPatch(BaseModel):
    """Partial update for yang settings — all fields optional."""
    subagents:        Optional[bool] = None
    parallel_tools:   Optional[bool] = None
    plan_mode:        Optional[bool] = None
    tool_search:      Optional[bool] = None
    auto_compact:     Optional[bool] = None
    focus_chain:      Optional[bool] = None
    background_edit:  Optional[bool] = None
    checkpoints:      Optional[bool] = None
    yolo_mode:        Optional[bool] = None
    double_check:     Optional[bool] = None
    advanced:         Optional[Dict[str, Any]] = None


class CreateCheckpointRequest(BaseModel):
    conversation_id: str
    label:           Optional[str] = None


# ─── Settings endpoints ───────────────────────────────────────────────────────

@router.get("/settings")
async def get_yang_settings(user_id: str = Depends(get_current_user_id)):
    """
    Return the current user's YANG feature settings.
    Auto-creates a row with all defaults if this user has none yet.
    """
    from core.yang.settings import load_yang_config
    cfg = load_yang_config(user_id)
    return {
        "user_id": user_id,
        **cfg.to_dict(),
    }


@router.patch("/settings")
async def update_yang_settings(
    patch: YangSettingsPatch,
    user_id: str = Depends(get_current_user_id),
):
    """
    Partially update YANG feature settings for the current user.
    Only supplied (non-null) fields are changed.
    """
    from core.yang.settings import save_yang_settings

    patch_dict = patch.model_dump(exclude_none=True)
    if not patch_dict:
        raise HTTPException(status_code=422, detail="No settings provided to update.")

    try:
        updated = save_yang_settings(user_id, patch_dict)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        logger.error("Failed to save yang settings for %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Failed to save settings.")

    return {
        "status": "updated",
        "user_id": user_id,
        "updated_fields": list(patch_dict.keys()),
        "row": updated,
    }


# ─── Checkpoint endpoints (delegate to core/yang/checkpoints.py) ─────────────

@router.get("/checkpoints")
async def list_checkpoints_endpoint(
    conversation_id: str = Query(..., description="Conversation ID to list checkpoints for"),
    user_id: str = Depends(get_current_user_id),
):
    """
    List all checkpoints for a conversation (newest first).
    Only the requesting user's checkpoints are returned.
    """
    from core.yang.checkpoints import list_checkpoints
    rows = list_checkpoints(get_supabase(), user_id, conversation_id)
    return {
        "conversation_id": conversation_id,
        "checkpoints": rows,
        "count": len(rows),
    }


@router.post("/checkpoints")
async def create_checkpoint_endpoint(
    body: CreateCheckpointRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Manually create a checkpoint for a conversation.
    Snaps the current last message ID and focus chain.
    """
    from core.yang.checkpoints import create_checkpoint
    try:
        ckpt = create_checkpoint(
            db=get_supabase(),
            user_id=user_id,
            conversation_id=body.conversation_id,
            label=body.label,
            trigger="manual",
        )
        return {"status": "created", "checkpoint": ckpt}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        logger.error("create_checkpoint_endpoint failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create checkpoint.")


@router.post("/checkpoints/{checkpoint_id}/restore")
async def restore_checkpoint_endpoint(
    checkpoint_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Restore a conversation to a checkpoint.

    Deletes messages (and orphaned tool_results) newer than the checkpoint's
    high-water mark and restores the focus chain.

    ⚠️  Generated files (PPTX, DOCX, XLSX) are NOT deleted — they remain on
    disk and in file storage. The response includes a warning about this.
    """
    from core.yang.checkpoints import restore_checkpoint
    try:
        result = restore_checkpoint(
            db=get_supabase(),
            user_id=user_id,
            checkpoint_id=checkpoint_id,
        )
        return {"status": "restored", **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        logger.error("restore_checkpoint_endpoint %s failed: %s", checkpoint_id, e)
        raise HTTPException(status_code=500, detail="Failed to restore checkpoint.")


@router.delete("/checkpoints/{checkpoint_id}")
async def delete_checkpoint_endpoint(
    checkpoint_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Delete a checkpoint. Ownership is verified.
    """
    from core.yang.checkpoints import delete_checkpoint
    deleted = delete_checkpoint(get_supabase(), user_id, checkpoint_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Checkpoint not found or you do not own it.",
        )
    return {"status": "deleted", "checkpoint_id": checkpoint_id}


# ─── Background edit task poll endpoint ──────────────────────────────────────

@router.get("/tasks/{task_id}")
async def get_background_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Poll the status of a background edit task.

    Returns the task record:
      {
        "task_id":      "uuid",
        "tool_name":    "generate_pptx",
        "status":       "running" | "complete" | "failed",
        "result":       {...},   # populated when complete
        "error":        "...",   # populated when failed
        "elapsed_s":    12.3,
      }

    ⚠️  Tasks are in-memory only.  Lost on container restart.
    """
    from core.yang.background_edit import get_bg_task_status
    task = get_bg_task_status(task_id, user_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found or you do not own it.",
        )
    return task


# ─── Status endpoint ──────────────────────────────────────────────────────────

@router.get("/status")
async def yang_status(user_id: str = Depends(get_current_user_id)):
    """
    Return the current user's YANG config + a summary of available features.
    Useful for the frontend settings panel.
    """
    from core.yang.settings import load_yang_config
    cfg = load_yang_config(user_id)

    return {
        "user_id": user_id,
        "settings": cfg.to_dict(),
        "features": {
            "subagents": {
                "enabled": cfg.subagents,
                "description": "Parallel focused subagents for research and analysis",
                "max_concurrent": cfg.subagent_max,
            },
            "parallel_tools": {
                "enabled": cfg.parallel_tools,
                "description": "Execute multiple read-only tools simultaneously",
            },
            "plan_mode": {
                "enabled": cfg.plan_mode,
                "description": "Restrict tool execution to read-only tools (safe exploration)",
            },
            "tool_search": {
                "enabled": cfg.tool_search,
                "description": "Lazy-load tool definitions to reduce context usage",
            },
            "auto_compact": {
                "enabled": cfg.auto_compact,
                "description": "Automatically summarize old conversation history",
                "threshold_tokens": cfg.compact_token_threshold,
            },
            "focus_chain": {
                "enabled": cfg.focus_chain,
                "description": "Maintain a rolling goal/task/file summary across turns",
            },
            "background_edit": {
                "enabled": cfg.background_edit,
                "description": "Queue document generation without blocking the response",
            },
            "checkpoints": {
                "enabled": cfg.checkpoints,
                "description": "Save rollback points for easy undo",
            },
            "yolo_mode": {
                "enabled": cfg.yolo_mode,
                "description": "Execute all tools without confirmation prompts",
            },
            "double_check": {
                "enabled": cfg.double_check,
                "description": "Verify final responses against original requirements",
            },
        },
    }
