"""
core/yang/focus_chain.py — Rolling Conversation Focus Tracker
=============================================================
Maintains a lightweight JSON summary of the conversation's current goal,
open tasks, key files, and decisions.  Stored in the `conversation_focus`
table (one row per conversation).

Design:
- DETERMINISTIC UPDATE (hot-path, zero LLM cost):
  After each assistant turn, regex-extract file references, task checkboxes,
  and tool names from the assistant's response and merge them in.
  Fast enough to run inline before returning the response.

- OPTIONAL LLM POLISH (background, off hot-path):
  Every `focus_llm_every_n` turns (default 5), fire a Haiku call that
  rewrites the entire focus JSON in a more coherent form.  Runs inside
  an asyncio.create_task so it never adds latency to the user response.
  On failure, the deterministic version is kept — no degradation.

- SYSTEM PROMPT INJECTION:
  The focus chain is prepended to the system prompt as a compact
  `<focus_chain>…</focus_chain>` block.  It uses a SEPARATE un-cached
  system block so the large base system prompt stays prompt-cached while
  the focus block can change every turn.

Usage (from api/routes/chat.py):
    from core.yang.focus_chain import (
        get_focus, update_focus_deterministic,
        build_focus_system_block, schedule_llm_polish,
    )

    focus = get_focus(db, conversation_id)
    focus_block = build_focus_system_block(focus)
    # Inject focus_block as a second system message (un-cached)

    # After response:
    update_focus_deterministic(db, conversation_id, user_id, assistant_text, tool_names)
    schedule_llm_polish(db, conversation_id, user_id, yang_cfg, api_key)
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── Focus schema ─────────────────────────────────────────────────────────────

_EMPTY_FOCUS: Dict[str, Any] = {
    "goal":              "",
    "open_tasks":        [],
    "completed_tasks":   [],
    "key_files":         [],
    "tools_used":        [],
    "turns_since_polish": 0,
}

# ─── Regex patterns for deterministic extraction ──────────────────────────────

# UUID-format file_id references
_RE_FILE_ID = re.compile(r'\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b', re.I)
# Quoted filenames with common extensions
_RE_FILENAME = re.compile(r'"([^"]{3,80}\.(pptx|docx|xlsx|csv|pdf|png|jpg|json|py|afl))"', re.I)
# Unchecked tasks: - [ ] text  or  ☐ text
_RE_OPEN_TASK = re.compile(r'(?:^|\n)\s*(?:-\s*\[\s*\]|☐)\s*(.+)', re.MULTILINE)
# Checked tasks:  - [x] text  or  ✅ text  or  ✓ text
_RE_DONE_TASK  = re.compile(r'(?:^|\n)\s*(?:-\s*\[[xX]\]|✅|✓)\s*(.+)', re.MULTILINE)

# Maximum items kept per category to bound context size
_MAX_FILES = 10
_MAX_TASKS = 15
_MAX_TOOLS = 10


# ─── DB helpers ───────────────────────────────────────────────────────────────

def get_focus(db, conversation_id: str) -> Dict[str, Any]:
    """
    Load the focus chain for a conversation from the DB.
    Returns an empty focus dict if the row doesn't exist yet.
    Never raises.
    """
    try:
        result = db.table("conversation_focus").select("focus, turns_since_llm_polish").eq(
            "conversation_id", conversation_id
        ).execute()
        if result.data:
            focus = dict(result.data[0].get("focus") or {})
            focus["turns_since_polish"] = result.data[0].get("turns_since_llm_polish", 0)
            return {**_EMPTY_FOCUS, **focus}
    except Exception as e:
        logger.debug("get_focus failed (non-fatal): %s", e)
    return dict(_EMPTY_FOCUS)


def _save_focus(db, conversation_id: str, user_id: str, focus: Dict[str, Any]) -> None:
    """Upsert the focus chain row. Extracts turns_since_polish for the DB column."""
    turns = focus.pop("turns_since_polish", 0)
    try:
        db.table("conversation_focus").upsert(
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "focus": focus,
                "turns_since_llm_polish": turns,
            },
            on_conflict="conversation_id",
        ).execute()
    except Exception as e:
        logger.debug("_save_focus failed (non-fatal): %s", e)
    finally:
        focus["turns_since_polish"] = turns  # restore for caller


# ─── Deterministic update ─────────────────────────────────────────────────────

def update_focus_deterministic(
    db,
    conversation_id: str,
    user_id: str,
    assistant_text: str,
    tool_names: Optional[List[str]] = None,
    user_message: Optional[str] = None,
) -> None:
    """
    Fast deterministic focus update — no LLM calls.
    Extracts files, tasks, and tool usage from the latest exchange.

    Args:
        db:               Supabase client.
        conversation_id:  Conversation UUID.
        user_id:          Authenticated user UUID.
        assistant_text:   The full text of the latest assistant response.
        tool_names:       Names of tools called in this turn.
        user_message:     The user's message (used to infer goal on first turn).
    """
    focus = get_focus(db, conversation_id)
    combined_text = (assistant_text or "") + "\n" + (user_message or "")

    # ── Goal: set on first turn from user message ──────────────────────────
    if not focus.get("goal") and user_message:
        focus["goal"] = user_message[:120].strip().replace("\n", " ")

    # ── Key files: UUID file_ids + quoted filenames ────────────────────────
    new_files = set(focus.get("key_files") or [])
    for m in _RE_FILE_ID.findall(combined_text):
        new_files.add(m.lower())
    for m in _RE_FILENAME.findall(combined_text):
        new_files.add(m[0])  # group 0 = full filename
    focus["key_files"] = list(new_files)[:_MAX_FILES]

    # ── Open tasks: unchecked checkboxes ──────────────────────────────────
    open_tasks = list(focus.get("open_tasks") or [])
    done_tasks = list(focus.get("completed_tasks") or [])
    for m in _RE_OPEN_TASK.findall(combined_text):
        task = m.strip()
        if task and task not in open_tasks and task not in done_tasks:
            open_tasks.append(task)

    # ── Completed tasks: checked checkboxes ───────────────────────────────
    newly_done = [m.strip() for m in _RE_DONE_TASK.findall(combined_text) if m.strip()]
    for task in newly_done:
        # Move from open to done if present
        if task in open_tasks:
            open_tasks.remove(task)
        if task not in done_tasks:
            done_tasks.append(task)

    focus["open_tasks"]      = open_tasks[-_MAX_TASKS:]
    focus["completed_tasks"] = done_tasks[-_MAX_TASKS:]

    # ── Tools used ────────────────────────────────────────────────────────
    if tool_names:
        tools_set = list(dict.fromkeys(
            (focus.get("tools_used") or []) + tool_names
        ))
        focus["tools_used"] = tools_set[-_MAX_TOOLS:]

    # ── Increment turns counter ───────────────────────────────────────────
    focus["turns_since_polish"] = int(focus.get("turns_since_polish", 0)) + 1

    _save_focus(db, conversation_id, user_id, focus)
    logger.debug("focus_chain updated deterministically for conv %s", conversation_id)


# ─── System prompt injection ──────────────────────────────────────────────────

def build_focus_system_block(focus: Dict[str, Any]) -> str:
    """
    Format the focus chain as a compact <focus_chain> block for injection
    into the system prompt.  Returns an empty string if focus is empty.
    """
    if not focus or not any([
        focus.get("goal"),
        focus.get("open_tasks"),
        focus.get("key_files"),
        focus.get("tools_used"),
    ]):
        return ""

    lines = ["<focus_chain>"]

    if focus.get("goal"):
        lines.append(f"Goal: {focus['goal']}")

    if focus.get("key_files"):
        lines.append("Key files: " + ", ".join(focus["key_files"][:5]))

    if focus.get("open_tasks"):
        lines.append("Open tasks:")
        for t in focus["open_tasks"][:5]:
            lines.append(f"  - [ ] {t}")

    if focus.get("completed_tasks"):
        recent_done = focus["completed_tasks"][-3:]
        lines.append("Recently completed: " + "; ".join(recent_done))

    if focus.get("tools_used"):
        lines.append("Tools used: " + ", ".join(focus["tools_used"][-5:]))

    lines.append("</focus_chain>")
    return "\n".join(lines)


# ─── Wire serialization (for frontend data events) ───────────────────────────

def serialize_focus(focus: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Flatten a focus row into a compact, wire-safe dict for streaming to the
    frontend (`data-yang_focus_chain` event).  Truncates long strings and
    caps list lengths so the payload stays small (<~600 chars).
    Returns {} when focus is empty / missing.
    """
    if not focus:
        return {}
    return {
        "goal":             (focus.get("goal") or "")[:200],
        "open_tasks":       [str(t)[:120] for t in (focus.get("open_tasks") or [])[:6]],
        "completed_tasks":  [str(t)[:120] for t in (focus.get("completed_tasks") or [])[-3:]],
        "key_files":        [str(f)[:80]  for f in (focus.get("key_files")  or [])[:6]],
        "tools_used":       [str(t)[:40]  for t in (focus.get("tools_used") or [])[-5:]],
        "turns_since_polish": int(focus.get("turns_since_polish", 0)),
    }


# ─── Background LLM polish ────────────────────────────────────────────────────


def schedule_llm_polish(
    db,
    conversation_id: str,
    user_id: str,
    yang_cfg: Any,
    api_key: str,
) -> Optional[asyncio.Task]:
    """
    Schedule a background Haiku LLM call to rewrite the focus chain in a
    more coherent form every `focus_llm_every_n` turns.

    Runs as asyncio.create_task — never blocks the response stream.
    Returns the Task object (or None if not triggered).

    Args:
        db:               Supabase client.
        conversation_id:  Conversation UUID.
        user_id:          Authenticated user UUID.
        yang_cfg:         YangConfig (used for focus_llm_every_n and focus_model).
        api_key:          Claude API key for the LLM polish call.
    """
    focus = get_focus(db, conversation_id)
    turns = int(focus.get("turns_since_polish", 0))

    if turns < yang_cfg.focus_llm_every_n:
        return None  # not yet due

    async def _polish_task():
        try:
            import anthropic as _anth
            client = _anth.Anthropic(api_key=api_key)

            current_json = json.dumps({
                k: v for k, v in focus.items() if k != "turns_since_polish"
            }, indent=2)

            response = client.messages.create(
                model=yang_cfg.focus_model,
                max_tokens=512,
                system=(
                    "You are a conversation summarizer. Given the current focus chain JSON, "
                    "rewrite it to be concise and accurate. Preserve all file IDs, task text, "
                    "and the goal. Remove duplicates. Return ONLY valid JSON — no prose."
                ),
                messages=[{
                    "role": "user",
                    "content": (
                        f"Rewrite this focus chain JSON:\n\n{current_json}\n\n"
                        "Return a single JSON object with keys: "
                        "goal, open_tasks, completed_tasks, key_files, tools_used"
                    ),
                }],
            )

            raw = response.content[0].text.strip() if response.content else ""
            # Strip markdown code fences if present
            raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.M)
            raw = re.sub(r'\s*```$', '', raw, flags=re.M)

            polished = json.loads(raw)
            polished["turns_since_polish"] = 0  # reset counter

            _save_focus(db, conversation_id, user_id, polished)
            logger.info("focus_chain LLM-polished for conv %s", conversation_id)

        except Exception as e:
            logger.warning(
                "focus_chain LLM polish failed for conv %s (non-fatal): %s",
                conversation_id, e,
            )

    task = asyncio.create_task(_polish_task())
    logger.debug("focus_chain LLM polish scheduled for conv %s", conversation_id)
    return task
