"""
core/yang/auto_compact.py — Background Conversation History Compression
========================================================================
When a conversation grows beyond the configured token / message threshold,
this module summarizes the oldest 60 % of messages using a cheap Haiku
call and stores a compact summary message in the DB.  Original messages
are soft-deleted by setting `metadata.compacted_out = true` so they are
excluded from future history loads without losing the audit trail.

Design:
- Runs as asyncio.create_task — NEVER on the hot path, NEVER blocking the
  user's response stream.
- Debounced: skips if the conversation already has a recent compact summary
  (checks for messages with metadata.compacted = true within the last N min).
- Graceful: any exception is caught and logged; the conversation continues
  normally with un-compacted history.

DB changes made during compaction:
  INSERT  messages (role=user, content=summary, metadata.compacted=true)
  UPDATE  messages SET metadata.compacted_out=true WHERE id IN (old_ids)

Filtering compacted messages in history loads:
  The chat route filters: `if not (m.get("metadata") or {}).get("compacted_out")`
  The compact summary itself is kept and included in future history loads.

Usage (from api/routes/chat.py):
    from core.yang.auto_compact import schedule_compaction

    schedule_compaction(
        db=db, conversation_id=conversation_id, user_id=user_id,
        yang_cfg=yang_cfg, api_key=api_keys.get("claude"),
    )
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Public entry-point ───────────────────────────────────────────────────────

def schedule_compaction(
    db,
    conversation_id: str,
    user_id: str,
    yang_cfg: Any,
    api_key: Optional[str],
    actual_input_tokens: int = 0,       # real token count from API usage object
    context_window_size: int = 0,       # model context window (e.g. 200_000)
) -> Optional[asyncio.Task]:
    """
    Schedule a background compaction task.

    Returns the asyncio.Task (or None if compaction is not needed / scheduled).
    The caller can safely ignore the return value.

    When actual_input_tokens > 0 AND context_window_size > 0, the compaction
    trigger uses the real context-window utilisation percentage (like Cline)
    instead of a rough character-count estimate.
    """
    if not api_key:
        return None  # can't call LLM without key

    async def _task():
        try:
            await _run_compaction(
                db, conversation_id, user_id, yang_cfg, api_key,
                actual_input_tokens=actual_input_tokens,
                context_window_size=context_window_size,
            )
        except Exception as e:
            logger.warning(
                "auto_compact: compaction failed for conv %s (non-fatal): %s",
                conversation_id, e,
            )

    task = asyncio.create_task(_task())
    logger.debug("auto_compact: scheduled for conv %s", conversation_id)
    return task


# ─── Core compaction logic ────────────────────────────────────────────────────

async def _run_compaction(
    db,
    conversation_id: str,
    user_id: str,
    yang_cfg: Any,
    api_key: str,
    actual_input_tokens: int = 0,
    context_window_size: int = 0,
) -> None:
    """
    Evaluate whether compaction is needed and, if so, execute it.

    Steps:
    1. Load all non-compacted messages from DB.
    2. Determine token count (real API usage when available, else rough estimate).
    3. Check threshold: utilisation % when context_window_size is known (like
       Cline), absolute token count otherwise.
    4. If over threshold AND over min message count AND not debounced: compact.
    5. Summarise the oldest 60 % using a cheap model.
    6. Insert summary message + soft-delete originals.
    """
    # ── 1. Load all active (non-compacted-out) messages ───────────────────
    # Supabase Python v2 .execute() is synchronous — wrap in asyncio.to_thread
    # so any blocking I/O (typically 50-200ms) doesn't freeze the event loop
    # and delay the streaming chat response.
    try:
        result = await asyncio.to_thread(
            lambda: db.table("messages").select(
                "id, role, content, metadata, created_at"
            ).eq("conversation_id", conversation_id).order("created_at").execute()
        )
        all_msgs: List[Dict] = result.data or []
    except Exception as e:
        logger.debug("auto_compact: could not load messages: %s", e)
        return

    # Filter out already-compacted messages (metadata.compacted_out=true)
    active = [
        m for m in all_msgs
        if not (m.get("metadata") or {}).get("compacted_out")
    ]

    msg_count = len(active)

    # ── 2. Determine token count ───────────────────────────────────────────
    # Prefer the real API-returned input_tokens count (passed in from chat.py)
    # because it includes the system prompt, tool definitions, and file context
    # — things the rough character estimate misses entirely.
    if actual_input_tokens > 0:
        payload_tokens = actual_input_tokens
        logger.debug(
            "auto_compact: conv %s — using real API token count: %d",
            conversation_id, payload_tokens,
        )
    else:
        payload_tokens = sum(
            len(json.dumps(m.get("content") or "")) // 4
            for m in active
        )
        logger.debug(
            "auto_compact: conv %s — using estimated token count: %d",
            conversation_id, payload_tokens,
        )

    min_msgs = int(yang_cfg.compact_message_min)

    # ── 3. Threshold check ─────────────────────────────────────────────────
    # Use utilisation % when we have real token counts + context window size
    # (mirrors how Cline decides when to compact).
    # Fall back to the absolute token threshold otherwise.
    utilization: float = 0.0
    if context_window_size > 0 and actual_input_tokens > 0:
        utilization = payload_tokens / context_window_size
        util_threshold = float(getattr(yang_cfg, "compact_utilization_threshold", 0.70))
        threshold_met = utilization >= util_threshold
        logger.debug(
            "auto_compact: conv %s — %.1f%% context used (threshold %.0f%%), %d msgs",
            conversation_id, utilization * 100, util_threshold * 100, msg_count,
        )
    else:
        threshold = int(yang_cfg.compact_token_threshold)
        threshold_met = payload_tokens >= threshold
        logger.debug(
            "auto_compact: conv %s — %d tokens / %d msgs, absolute threshold %d",
            conversation_id, payload_tokens, msg_count, threshold,
        )

    if not threshold_met or msg_count <= min_msgs:
        logger.debug(
            "auto_compact: conv %s — below threshold or too few msgs (%d), skipping",
            conversation_id, msg_count,
        )
        return

    # ── 3. Debounce check ─────────────────────────────────────────────────
    debounce_min = int(yang_cfg.compact_debounce_min)
    recent_compact = _find_recent_compact(all_msgs, debounce_min)
    if recent_compact:
        logger.debug(
            "auto_compact: conv %s — recent compaction found (%s), skipping",
            conversation_id, recent_compact,
        )
        return

    logger.info(
        "auto_compact: conv %s — %d tokens / %d msgs over threshold, compacting…",
        conversation_id, payload_tokens, msg_count,
    )

    # ── 4. Choose messages to compact (oldest 60 %) ───────────────────────
    cutoff = int(len(active) * 0.6)
    to_compact = active[:cutoff]
    to_keep    = active[cutoff:]

    if not to_compact:
        return

    # ── 5. Summarise with Haiku ───────────────────────────────────────────
    summary = await _summarise(to_compact, yang_cfg, api_key)
    if not summary:
        logger.warning("auto_compact: Haiku returned empty summary, aborting")
        return

    # ── 6. Insert compact summary message ─────────────────────────────────
    # Use the created_at of the LAST compacted message so the summary sits
    # just before the kept messages in chronological order.
    # Role is "user" with an XML context wrapper so Claude understands this
    # is injected context, not a genuine user statement.
    last_compact_ts = to_compact[-1].get("created_at", "")
    compact_ids = [m["id"] for m in to_compact]

    try:
        db.table("messages").insert({
            "conversation_id": conversation_id,
            "role":            "user",
            "content":         (
                f"<context>\n"
                f"[Conversation history compressed — {len(to_compact)} older messages summarized]\n\n"
                f"{summary}\n"
                f"</context>"
            ),
            "metadata": {
                "compacted":          True,
                "compacted_ids":      compact_ids,
                "original_count":     len(to_compact),
                "token_estimate":     payload_tokens,
                "utilization_pct":    round(utilization * 100, 1),
                "context_window":     context_window_size,
            },
        }).execute()
    except Exception as e:
        logger.warning("auto_compact: could not insert summary message: %s", e)
        return

    # ── 7. Soft-delete the original compacted messages ────────────────────
    # Mark in batches of 20 to avoid URL-length limits.
    _batch_mark_compacted(db, compact_ids)

    logger.info(
        "auto_compact: conv %s — compacted %d messages into summary",
        conversation_id, len(to_compact),
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _find_recent_compact(all_msgs: List[Dict], debounce_min: int) -> Optional[str]:
    """
    Return the id of the most recent compact-summary message if it was created
    within the debounce window, else None.
    """
    import datetime as _dt
    cutoff_ts = time.time() - debounce_min * 60

    for m in reversed(all_msgs):
        meta = m.get("metadata") or {}
        if meta.get("compacted"):
            # Parse created_at
            created_str = m.get("created_at", "")
            try:
                if created_str:
                    # Robust ISO8601 parse: normalise Z → +00:00 so negative
                    # offsets (e.g. -05:00) are NOT stripped by a naive split('+').
                    iso = created_str.replace("Z", "+00:00")
                    ts = _dt.datetime.fromisoformat(iso).timestamp()
                    if ts > cutoff_ts:
                        return m["id"]
            except Exception:
                pass
    return None


def _batch_mark_compacted(db, ids: List[str]) -> None:
    """Soft-delete messages by setting metadata.compacted_out = true.

    Each row UPDATE is wrapped in its own try/except so one failure does NOT
    abort the remaining messages in the batch (which would leave the
    conversation in an inconsistent half-compacted state).
    """
    BATCH = 20
    for i in range(0, len(ids), BATCH):
        batch = ids[i : i + BATCH]
        try:
            rows = db.table("messages").select("id, metadata").in_("id", batch).execute()
        except Exception as e:
            logger.warning(
                "auto_compact: could not fetch metadata for batch %d-%d: %s",
                i, i + BATCH, e,
            )
            continue
        for row in (rows.data or []):
            try:
                meta = dict(row.get("metadata") or {})
                meta["compacted_out"] = True
                db.table("messages").update({"metadata": meta}).eq(
                    "id", row["id"]
                ).execute()
            except Exception as e:
                logger.warning(
                    "auto_compact: failed to mark message %s as compacted: %s",
                    row.get("id"), e,
                )


async def _summarise(
    messages: List[Dict],
    yang_cfg: Any,
    api_key: str,
) -> str:
    """
    Call Haiku to summarise a list of conversation messages.
    Returns the summary string or empty string on failure.
    """
    # Build a compact transcript for the LLM
    lines = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content") or ""
        if isinstance(content, list):
            content = " ".join(
                b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
            )
        # Truncate very long messages to keep Haiku input small
        content = content[:500].replace("\n", " ")
        lines.append(f"{role.upper()}: {content}")

    transcript = "\n".join(lines)

    try:
        import anthropic as _anth
        client = _anth.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=yang_cfg.compact_model,
            max_tokens=int(yang_cfg.compact_token_threshold * 0.05),  # ~5% of threshold
            system=(
                "You are a conversation summarizer. "
                "Condense the conversation into concise bullet points. "
                "Preserve: file names, file IDs (UUIDs), decisions made, tasks completed, "
                "code snippets (abbreviated), and any open questions. "
                "Be factual. Do not add commentary. Return plain text, no markdown headers."
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Summarize this conversation history into bullet points:\n\n{transcript}"
                ),
            }],
        )
        text = response.content[0].text.strip() if response.content else ""
        return text
    except Exception as e:
        logger.warning("auto_compact: Haiku summarization failed: %s", e)
        return ""
