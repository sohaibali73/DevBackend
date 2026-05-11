"""
AI SDK v5 UI Message Stream Protocol encoder.

Emits proper SSE events (``data: <json>\\n\\n``) following the format expected
by ``@ai-sdk/react`` v5's UI Message Stream protocol. Intended for the
``/chat/agent/ui-stream`` endpoint so the Next.js frontend can byte-pass-
through to the browser with zero per-chunk translation.

Spec reference: https://sdk.vercel.ai/docs/concepts/ui-messages

Usage (inside an async generator):

    from core.ui_message_sse import UIMessageSSE

    enc = UIMessageSSE()
    yield enc.start("msg-12345")
    yield enc.start_step()
    yield enc.text_start("text-a")
    yield enc.text_delta("text-a", "hello ")
    yield enc.text_delta("text-a", "world")
    yield enc.text_end("text-a")
    yield enc.finish_step()
    yield enc.finish()
    yield enc.done()

All methods return ``bytes`` ready to push down the wire.

The encoder tracks ONE open text block via ``self._text_id`` so callers don't
have to thread the id manually. Use ``open_text()`` / ``close_text()`` for
the common "interleave text + tool calls" pattern.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional


def _sse(event: Dict[str, Any]) -> bytes:
    """Format a dict as one SSE data event."""
    payload = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
    return f"data: {payload}\n\n".encode("utf-8")


class UIMessageSSE:
    """Stateful SSE emitter following AI SDK v5 UI Message Stream protocol.

    Stateful only for the *currently open text block id* — callers must
    still emit start/start_step/finish_step/finish in the correct order.
    """

    def __init__(self) -> None:
        self._text_id: Optional[str] = None
        self._next_text_seq = 0

    # ── Lifecycle ──────────────────────────────────────────────────────────

    @staticmethod
    def start(message_id: Optional[str] = None) -> bytes:
        mid = message_id or f"msg-{int(time.time() * 1000)}"
        return _sse({"type": "start", "messageId": mid})

    @staticmethod
    def start_step() -> bytes:
        return _sse({"type": "start-step"})

    @staticmethod
    def finish_step() -> bytes:
        return _sse({"type": "finish-step"})

    @staticmethod
    def finish() -> bytes:
        return _sse({"type": "finish"})

    @staticmethod
    def done() -> bytes:
        """Final terminator. After this the response can close."""
        return b"data: [DONE]\n\n"

    @staticmethod
    def keepalive() -> bytes:
        """SSE comment used as a heartbeat. Does NOT trigger a UI re-render."""
        return b": keep-alive\n\n"

    # ── Text block management ──────────────────────────────────────────────

    def open_text(self) -> bytes:
        """Start a new text block if none is open. Idempotent — returns b'' if already open."""
        if self._text_id is not None:
            return b""
        self._next_text_seq += 1
        self._text_id = f"text-{int(time.time() * 1_000_000)}-{self._next_text_seq}"
        return _sse({"type": "text-start", "id": self._text_id})

    def text_delta(self, delta: str) -> bytes:
        """Append a text chunk to the currently-open block.

        If no block is open, opens one first (returns BOTH events concatenated).
        """
        if not delta:
            return b""
        out = b""
        if self._text_id is None:
            out += self.open_text()
        out += _sse({"type": "text-delta", "id": self._text_id, "delta": delta})
        return out

    def close_text(self) -> bytes:
        """Close the currently-open text block, if any. Idempotent."""
        if self._text_id is None:
            return b""
        out = _sse({"type": "text-end", "id": self._text_id})
        self._text_id = None
        return out

    # ── Explicit text id variants (when caller wants control) ──────────────

    @staticmethod
    def text_start_explicit(text_id: str) -> bytes:
        return _sse({"type": "text-start", "id": text_id})

    @staticmethod
    def text_delta_explicit(text_id: str, delta: str) -> bytes:
        if not delta:
            return b""
        return _sse({"type": "text-delta", "id": text_id, "delta": delta})

    @staticmethod
    def text_end_explicit(text_id: str) -> bytes:
        return _sse({"type": "text-end", "id": text_id})

    # ── Tool calls ─────────────────────────────────────────────────────────

    @staticmethod
    def tool_input_start(tool_call_id: str, tool_name: str) -> bytes:
        return _sse({
            "type": "tool-input-start",
            "toolCallId": tool_call_id,
            "toolName": tool_name,
        })

    @staticmethod
    def tool_input_delta(tool_call_id: str, delta: str) -> bytes:
        return _sse({
            "type": "tool-input-delta",
            "toolCallId": tool_call_id,
            "inputTextDelta": delta,
        })

    @staticmethod
    def tool_input_available(tool_call_id: str, tool_name: str, input_obj: Any) -> bytes:
        return _sse({
            "type": "tool-input-available",
            "toolCallId": tool_call_id,
            "toolName": tool_name,
            "input": input_obj,
        })

    @staticmethod
    def tool_output_available(tool_call_id: str, output: Any) -> bytes:
        return _sse({
            "type": "tool-output-available",
            "toolCallId": tool_call_id,
            "output": output,
        })

    # ── Data events (artifacts, files, status, yang, conversation) ────────

    @staticmethod
    def data_artifact(artifact: Dict[str, Any]) -> bytes:
        return _sse({
            "type": "data-artifact",
            "id": artifact.get("id") or artifact.get("artifact_id") or "",
            "data": artifact,
        })

    @staticmethod
    def data_file_download(file_download: Dict[str, Any]) -> bytes:
        # Wrapped in an array per the spec.
        return _sse({"type": "data-file_download", "data": [file_download]})

    @staticmethod
    def data_skill_status(label: str, slug: str = "") -> bytes:
        return _sse({
            "type": "data-skill_status",
            "data": [{"skill_status": label, "skill_slug": slug}],
        })

    @staticmethod
    def data_yang(payload: Dict[str, Any]) -> bytes:
        """Forward any yang_* payload as a v5 data-yang event."""
        return _sse({"type": "data-yang", "data": [payload]})

    @staticmethod
    def data_conversation(conversation_id: str, title: Optional[str] = None) -> bytes:
        body: Dict[str, Any] = {"conversation_id": str(conversation_id)}
        if title is not None:
            body["title"] = title
        return _sse({"type": "data-conversation", "data": body})

    @staticmethod
    def data_custom(kind: str, data: Any) -> bytes:
        """Forward an arbitrary ``data-<kind>`` event for forward compat."""
        return _sse({"type": f"data-{kind}", "data": data})

    # ── Errors ─────────────────────────────────────────────────────────────

    @staticmethod
    def error(message: str) -> bytes:
        return _sse({"type": "error", "errorText": message})


SSE_HEADERS = {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
    "x-vercel-ai-ui-message-stream": "v1",
    "Access-Control-Allow-Origin": "*",
}
