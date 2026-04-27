"""
core/debug_transcript.py — Debug transcript capture for chat agent requests.

When DEBUG_TRANSCRIPTS_ENABLED=1 is set in the environment, each chat agent
request records a structured transcript (request params, model resolution,
system prompt, messages, tool calls, streaming deltas, and the final response)
and writes it to /data/debug_transcripts/ on the Railway persistent volume.

When the env var is absent or not "1", all operations are zero-cost no-ops
because DebugTranscript is only instantiated when is_debug_enabled() is True.

Public API (consumed by api/routes/chat.py):
    is_debug_enabled()                          → bool
    set_current_transcript(dt)                  → None  (thread-local ctx)
    get_current_transcript()                    → DebugTranscript | None

    DebugTranscript(conversation_id, user_id)
        .log_request(method, path, model, content, *, skill_slug)
        .log_model_resolved(model)
        .log_system_prompt(prompt)
        .log_messages(messages)
        .log_text_delta(text)
        .log_tool_call_start(tool_call_id, tool_name, tool_input)
        .log_iteration(iteration, duration, usage)
        .log_final_response(content, tools_used, total_usage, iteration)
        .log_error(error_type, error_msg)
        .write()                                → path written (str) or None
"""

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_ENV_FLAG = "DEBUG_TRANSCRIPTS_ENABLED"
_TRANSCRIPT_DIR = Path(os.getenv("DEBUG_TRANSCRIPT_DIR", "/data/debug_transcripts"))


def is_debug_enabled() -> bool:
    """Return True only when DEBUG_TRANSCRIPTS_ENABLED=1 is set."""
    return os.getenv(_ENV_FLAG, "").strip() == "1"


# ---------------------------------------------------------------------------
# Thread-local context (allows chat.py to stash the active transcript so
# helper functions deeper in the call stack can retrieve it without threading
# it through every function signature).
# ---------------------------------------------------------------------------

_local = threading.local()


def set_current_transcript(dt: "DebugTranscript") -> None:
    """Store *dt* as the active transcript for the current thread."""
    _local.transcript = dt


def get_current_transcript() -> Optional["DebugTranscript"]:
    """Return the active transcript for the current thread, or None."""
    return getattr(_local, "transcript", None)


# ---------------------------------------------------------------------------
# DebugTranscript
# ---------------------------------------------------------------------------

class DebugTranscript:
    """
    Collects structured debug information for a single chat agent request
    and serialises it to a JSON file on the persistent volume.

    All log_* methods are safe to call unconditionally — they simply append
    to an in-memory list and never raise.
    """

    def __init__(self, conversation_id: str, user_id: str) -> None:
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.transcript_id = str(uuid.uuid4())
        self.started_at = datetime.now(timezone.utc).isoformat()
        self._events: List[Dict[str, Any]] = []
        self._text_buffer: List[str] = []  # accumulate streaming deltas

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _event(self, kind: str, **payload: Any) -> None:
        self._events.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            **payload,
        })

    # ------------------------------------------------------------------
    # Public log_* methods
    # ------------------------------------------------------------------

    def log_request(
        self,
        method: str,
        path: str,
        model: str,
        content: str,
        *,
        skill_slug: str = "",
    ) -> None:
        self._event(
            "request",
            method=method,
            path=path,
            model=model,
            content_preview=content[:500],
            skill_slug=skill_slug,
        )

    def log_model_resolved(self, model: str) -> None:
        self._event("model_resolved", model=model)

    def log_system_prompt(self, prompt: str) -> None:
        self._event("system_prompt", prompt_preview=prompt[:2000], length=len(prompt))

    def log_messages(self, messages: list) -> None:
        self._event("messages_snapshot", count=len(messages))

    def log_text_delta(self, text: str) -> None:
        # Buffer deltas; flush into a single event on write() to keep the
        # transcript file readable.
        self._text_buffer.append(text)

    def log_tool_call_start(
        self,
        tool_call_id: str,
        tool_name: str,
        tool_input: Any,
    ) -> None:
        self._event(
            "tool_call_start",
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_input=tool_input,
        )

    def log_iteration(
        self,
        iteration: int,
        duration: float,
        usage: Any,
    ) -> None:
        self._event(
            "iteration",
            iteration=iteration,
            duration_seconds=round(duration, 3),
            usage=usage,
        )

    def log_final_response(
        self,
        content: str,
        tools_used: list,
        total_usage: Any,
        iteration: int,
    ) -> None:
        # Flush accumulated text deltas first
        if self._text_buffer:
            self._event(
                "streamed_text",
                text="".join(self._text_buffer),
                delta_count=len(self._text_buffer),
            )
            self._text_buffer = []

        self._event(
            "final_response",
            content_preview=content[:1000],
            content_length=len(content),
            tools_used_count=len(tools_used),
            total_usage=total_usage,
            iterations=iteration,
        )

    def log_error(self, error_type: str, error_msg: str) -> None:
        self._event("error", error_type=error_type, error_msg=error_msg[:1000])

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def write(self) -> Optional[str]:
        """
        Write the transcript to a JSON file on the persistent volume.

        Returns the file path on success, or None if writing fails (e.g.
        volume not mounted).  Failures are logged but never re-raised so
        they cannot disrupt the chat response stream.
        """
        # Flush any remaining text deltas
        if self._text_buffer:
            self._event(
                "streamed_text",
                text="".join(self._text_buffer),
                delta_count=len(self._text_buffer),
            )
            self._text_buffer = []

        payload = {
            "transcript_id": self.transcript_id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "events": self._events,
        }

        try:
            _TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
            # Filename: <date>_<conversation_id[:8]>_<transcript_id[:8]>.json
            date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
            filename = (
                f"{date_str}"
                f"_{self.conversation_id[:8] if self.conversation_id else 'noconv'}"
                f"_{self.transcript_id[:8]}.json"
            )
            path = _TRANSCRIPT_DIR / filename
            path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            logger.debug("Debug transcript written: %s", path)
            return str(path)
        except Exception as exc:
            logger.warning("Failed to write debug transcript: %s", exc)
            return None
