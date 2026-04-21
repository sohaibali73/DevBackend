"""
core/yang/checkpoints.py — Programmatic Checkpoint API
=======================================================
Reusable functions for creating and restoring conversation checkpoints.
Called by: api/routes/yang.py (CRUD endpoints), yolo.py (auto-checkpoint).

Design:
- High-water-mark model: checkpoint stores the ID of the last message at
  snapshot time. Restore deletes all messages (and orphaned tool_results)
  created AFTER that message's timestamp.
- Generated files (PPTX, DOCX, XLSX) on disk are never touched — only DB
  rows are rolled back.
- Focus chain is separately snapshotted and restored.

Usage:
    from core.yang.checkpoints import create_checkpoint, restore_checkpoint

    ckpt = create_checkpoint(
        db=db, user_id=user_id, conversation_id=conversation_id,
        label="Before big refactor", trigger="pre_yolo"
    )

    result = restore_checkpoint(db=db, user_id=user_id, checkpoint_id=ckpt["id"])
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ─── Create ───────────────────────────────────────────────────────────────────

def create_checkpoint(
    db,
    user_id: str,
    conversation_id: str,
    label: Optional[str] = None,
    trigger: str = "manual",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Snapshot the current state of a conversation as a checkpoint.

    Captures:
    - last_message_id  (high-water mark for restore)
    - focus_snapshot   (current conversation_focus.focus jsonb)
    - optional metadata dict (e.g. yang_config flags at time of checkpoint)

    Args:
        db:               Supabase client.
        user_id:          Authenticated user UUID.
        conversation_id:  Target conversation UUID.
        label:            Human-readable name (shown in UI).
        trigger:          One of 'manual', 'pre_yolo', 'pre_destructive', 'auto'.
        metadata:         Arbitrary extra data to attach to the snapshot.

    Returns:
        The inserted yang_checkpoints row as a dict.

    Raises:
        ValueError:  If the conversation doesn't exist or isn't owned by user_id.
        RuntimeError: On any DB failure.
    """
    # ── 1. Verify conversation ownership ──────────────────────────────────
    try:
        conv = db.table("conversations").select("id").eq(
            "id", conversation_id
        ).eq("user_id", user_id).single().execute()
    except Exception as e:
        raise RuntimeError(f"Failed to verify conversation ownership: {e}") from e

    if not conv.data:
        raise ValueError(f"Conversation {conversation_id!r} not found or not owned by user.")

    # ── 2. High-water mark: last message ID ───────────────────────────────
    last_message_id: Optional[str] = None
    try:
        msg_result = db.table("messages").select("id").eq(
            "conversation_id", conversation_id
        ).order("created_at", desc=True).limit(1).execute()
        if msg_result.data:
            last_message_id = msg_result.data[0]["id"]
    except Exception as e:
        logger.warning("create_checkpoint: could not fetch last message: %s", e)

    # ── 3. Snapshot current focus chain ───────────────────────────────────
    focus_snapshot: Optional[Dict] = None
    try:
        focus_result = db.table("conversation_focus").select("focus").eq(
            "conversation_id", conversation_id
        ).execute()
        if focus_result.data:
            focus_snapshot = focus_result.data[0]["focus"]
    except Exception as e:
        logger.warning("create_checkpoint: could not fetch focus chain: %s", e)

    # ── 4. Insert checkpoint row ───────────────────────────────────────────
    row = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "label": label or _default_label(trigger),
        "trigger": trigger,
        "last_message_id": last_message_id,
        "focus_snapshot": focus_snapshot,
        "metadata": metadata or {},
    }

    try:
        result = db.table("yang_checkpoints").insert(row).execute()
    except Exception as e:
        raise RuntimeError(f"Failed to insert checkpoint: {e}") from e

    saved = result.data[0] if result.data else row
    logger.info(
        "checkpoint created: id=%s conv=%s trigger=%s hwm=%s",
        saved.get("id"), conversation_id, trigger, last_message_id,
    )
    return saved


# ─── Restore ──────────────────────────────────────────────────────────────────

def restore_checkpoint(
    db,
    user_id: str,
    checkpoint_id: str,
) -> Dict[str, Any]:
    """
    Roll a conversation back to a checkpoint.

    Steps:
    1. Verify the checkpoint exists and is owned by user_id.
    2. Look up the HWM timestamp from last_message_id.
    3. DELETE messages WHERE conversation_id = ? AND created_at > hwm_ts.
    4. DELETE tool_results WHERE conversation_id = ? AND created_at > hwm_ts.
       (tool_results.message_id is NOT a FK — no cascade — must be explicit.)
    5. UPSERT conversation_focus back to focus_snapshot.

    Generated files (PPTX/DOCX/XLSX) are intentionally NOT deleted.

    Args:
        db:             Supabase client.
        user_id:        Authenticated user UUID.
        checkpoint_id:  yang_checkpoints.id to restore.

    Returns:
        Dict with restore stats: {
            checkpoint_id, conversation_id,
            deleted_messages, deleted_tool_results,
            focus_restored
        }

    Raises:
        ValueError:  If checkpoint not found or not owned by user_id.
        RuntimeError: On DB failure.
    """
    # ── 1. Fetch and verify checkpoint ownership ───────────────────────────
    try:
        ckpt_result = db.table("yang_checkpoints").select("*").eq(
            "id", checkpoint_id
        ).eq("user_id", user_id).single().execute()
    except Exception as e:
        raise RuntimeError(f"Failed to fetch checkpoint: {e}") from e

    if not ckpt_result.data:
        raise ValueError(
            f"Checkpoint {checkpoint_id!r} not found or not owned by user."
        )

    ckpt = ckpt_result.data
    conversation_id: str = ckpt["conversation_id"]
    deleted_messages = 0
    deleted_tool_results = 0

    # ── 2. Determine high-water mark timestamp ─────────────────────────────
    hwm_ts: Optional[str] = None
    if ckpt.get("last_message_id"):
        try:
            hwm_result = db.table("messages").select("created_at").eq(
                "id", ckpt["last_message_id"]
            ).execute()
            if hwm_result.data:
                hwm_ts = hwm_result.data[0]["created_at"]
        except Exception as e:
            logger.warning("restore_checkpoint: could not fetch HWM message: %s", e)

    if hwm_ts:
        # ── 3. Delete messages newer than HWM ─────────────────────────────
        try:
            del_msg = db.table("messages").delete().eq(
                "conversation_id", conversation_id
            ).gt("created_at", hwm_ts).execute()
            deleted_messages = len(del_msg.data or [])
        except Exception as e:
            raise RuntimeError(f"Failed to delete messages during restore: {e}") from e

        # ── 4. Delete orphaned tool_results (not covered by FK cascade) ───
        try:
            del_tr = db.table("tool_results").delete().eq(
                "conversation_id", conversation_id
            ).gt("created_at", hwm_ts).execute()
            deleted_tool_results = len(del_tr.data or [])
        except Exception as e:
            # Non-fatal: tool_results may not exist on older deployments
            logger.warning("restore_checkpoint: could not delete tool_results: %s", e)

    # ── 5. Restore focus chain ─────────────────────────────────────────────
    focus_restored = False
    if ckpt.get("focus_snapshot") is not None:
        try:
            db.table("conversation_focus").upsert(
                {
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "focus": ckpt["focus_snapshot"],
                    "turns_since_llm_polish": 0,
                },
                on_conflict="conversation_id",
            ).execute()
            focus_restored = True
        except Exception as e:
            logger.warning("restore_checkpoint: could not restore focus chain: %s", e)

    summary = {
        "checkpoint_id": checkpoint_id,
        "conversation_id": conversation_id,
        "deleted_messages": deleted_messages,
        "deleted_tool_results": deleted_tool_results,
        "focus_restored": focus_restored,
        "hwm_ts": hwm_ts,
        "warning": (
            "Generated files (PPTX, DOCX, XLSX, etc.) created after this "
            "checkpoint are still on disk and accessible. They were not removed."
        ),
    }

    logger.info(
        "checkpoint restored: id=%s conv=%s deleted_msgs=%d deleted_tr=%d focus=%s",
        checkpoint_id, conversation_id, deleted_messages, deleted_tool_results,
        focus_restored,
    )
    return summary


# ─── List ─────────────────────────────────────────────────────────────────────

def list_checkpoints(
    db,
    user_id: str,
    conversation_id: str,
    limit: int = 50,
) -> list:
    """
    Return checkpoints for a conversation, newest first.
    Filters by both conversation_id AND user_id (belt-and-suspenders on top of RLS).
    """
    try:
        result = db.table("yang_checkpoints").select(
            "id, conversation_id, label, trigger, last_message_id, created_at, metadata"
        ).eq("conversation_id", conversation_id).eq(
            "user_id", user_id
        ).order("created_at", desc=True).limit(limit).execute()
        return result.data or []
    except Exception as e:
        logger.error("list_checkpoints failed: %s", e)
        return []


# ─── Delete ───────────────────────────────────────────────────────────────────

def delete_checkpoint(db, user_id: str, checkpoint_id: str) -> bool:
    """
    Delete a single checkpoint.  Returns True if deleted, False if not found.
    Ownership is verified via explicit user_id filter.
    """
    try:
        # First verify ownership
        ckpt = db.table("yang_checkpoints").select("id").eq(
            "id", checkpoint_id
        ).eq("user_id", user_id).execute()
        if not ckpt.data:
            return False
        db.table("yang_checkpoints").delete().eq("id", checkpoint_id).execute()
        return True
    except Exception as e:
        logger.error("delete_checkpoint failed: %s", e)
        return False


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _default_label(trigger: str) -> str:
    labels = {
        "pre_yolo":        "Auto — before Yolo mode",
        "pre_destructive": "Auto — before destructive operation",
        "auto":            "Auto checkpoint",
        "manual":          "Manual checkpoint",
    }
    return labels.get(trigger, "Checkpoint")
