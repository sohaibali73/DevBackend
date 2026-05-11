"""
Adapter that wraps :class:`UIMessageSSE` behind the legacy
``VercelAIStreamEncoder`` API.

This is a translation shim so the existing ``chat_agent`` generator can be
reused without modification — we just swap ``encoder = VercelAIStreamEncoder()``
for ``encoder = SSEAdapter()`` inside the new ``/chat/agent/ui-stream``
endpoint, and every ``encoder.encode_*`` call now returns SSE-formatted
bytes instead of the legacy ``0:...\\n`` / ``2:...\\n`` Data Stream Protocol.

The adapter handles the lifecycle bookkeeping (text-start / text-end /
start-step / finish-step / finish / done) that the legacy protocol did
implicitly, so callers don't have to think about it.

NOTE: ``encode_finish_message`` from the legacy API does double duty as
the end-of-stream marker. In the SSE flow we map it to:
  1) emit ``finish-step``
  2) emit ``finish``
  3) emit ``[DONE]``
That preserves the existing call site semantics.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from core.ui_message_sse import UIMessageSSE

logger = logging.getLogger(__name__)


class SSEAdapter:
    """Drop-in replacement for ``VercelAIStreamEncoder`` that emits AI SDK
    v5 UI Message Stream SSE bytes.

    All ``encode_*`` methods return ``bytes`` (not ``str``). ``StreamingResponse``
    accepts both, so the FastAPI side doesn't care.
    """

    def __init__(self) -> None:
        self._sse = UIMessageSSE()
        self._step_open = False
        self._finished = False
        # Map of pending tool_call_id → True once tool-input-start emitted.
        self._tool_inputs_started: Dict[str, bool] = {}

    # ── Lifecycle helpers (called by the endpoint wrapper) ─────────────────

    def emit_start(self, message_id: Optional[str] = None) -> bytes:
        return self._sse.start(message_id)

    def open_step(self) -> bytes:
        if self._step_open:
            return b""
        self._step_open = True
        return self._sse.start_step()

    def close_step(self) -> bytes:
        if not self._step_open:
            return b""
        out = b""
        out += self._sse.close_text()
        out += self._sse.finish_step()
        self._step_open = False
        return out

    def emit_done(self) -> bytes:
        """Emit ``finish`` + ``[DONE]`` and mark the stream over.

        Idempotent — calling twice returns ``b""`` the second time.
        """
        if self._finished:
            return b""
        self._finished = True
        out = self.close_step()
        out += self._sse.finish()
        out += self._sse.done()
        return out

    # ── Mirror of VercelAIStreamEncoder.encode_text ────────────────────────

    def encode_text(self, text: str) -> bytes:
        if not text:
            return b""
        # Ensure a step is open so text-delta has a parent step.
        prefix = self.open_step() if not self._step_open else b""
        return prefix + self._sse.text_delta(text)

    # ── Tool call streaming ────────────────────────────────────────────────

    def encode_tool_call_start(self, tool_id: str, tool_name: str) -> bytes:
        prefix = self.open_step() if not self._step_open else b""
        prefix += self._sse.close_text()  # close any open text block first
        self._tool_inputs_started[tool_id] = True
        return prefix + self._sse.tool_input_start(tool_id, tool_name)

    def encode_tool_call_delta(self, tool_id: str, args_delta: str) -> bytes:
        return self._sse.tool_input_delta(tool_id, args_delta)

    def encode_tool_call(self, tool_id: str, tool_name: str, tool_input: Dict[str, Any]) -> bytes:
        """Full tool call (the streaming start may or may not have happened).

        The current ``chat_agent`` body calls ``encode_tool_call`` directly
        when the tool input JSON is fully parsed, without ever calling the
        ``_start`` variant. We synthesize a tool-input-start in that case so
        the AI SDK v5 protocol stays well-formed.
        """
        prefix = self.open_step() if not self._step_open else b""
        prefix += self._sse.close_text()
        if not self._tool_inputs_started.get(tool_id):
            prefix += self._sse.tool_input_start(tool_id, tool_name)
            self._tool_inputs_started[tool_id] = True
        return prefix + self._sse.tool_input_available(tool_id, tool_name, tool_input)

    def encode_tool_result(self, tool_id: str, result: Any) -> bytes:
        # Result may be a JSON string or a dict. Spec says output is an
        # arbitrary JSON value, so try to parse strings.
        if isinstance(result, str):
            try:
                result_obj = json.loads(result)
            except (json.JSONDecodeError, ValueError):
                result_obj = result  # leave as plain string
        else:
            result_obj = result
        return self._sse.tool_output_available(tool_id, result_obj)

    # ── Custom data forwarding ─────────────────────────────────────────────

    def encode_data(self, data: Any) -> bytes:
        """Translate the legacy "type-2 array" payload into specific
        ``data-<kind>`` SSE events based on the payload's content.

        The legacy protocol shoved everything (skill_status, yang_*, conversation
        metadata, etc.) into one untyped array. We sniff the keys and emit
        the right ``data-*`` event so the frontend can route them cleanly.
        """
        # Normalize input — legacy accepts list or dict.
        if isinstance(data, list):
            items = data
        else:
            items = [data]

        out = b""
        prefix = self.open_step() if not self._step_open else b""
        if prefix:
            out += prefix

        for item in items:
            if not isinstance(item, dict):
                # Unstructured — forward as a generic data event.
                out += self._sse.data_custom("raw", item)
                continue

            # Skill status / heartbeat
            if "skill_status" in item:
                out += self._sse.data_skill_status(
                    label=item.get("skill_status", ""),
                    slug=item.get("skill_slug", ""),
                )
                continue

            if item.get("skill_heartbeat"):
                # SSE comment — does not trigger UI re-render. Useful for proxy keepalive.
                out += UIMessageSSE.keepalive()
                continue

            # YANG payloads (any key starting with yang_)
            yang_keys = [k for k in item.keys() if k.startswith("yang_")]
            if yang_keys:
                out += self._sse.data_yang(item)
                continue

            # Conversation metadata
            if "conversation_id" in item and not yang_keys:
                out += self._sse.data_conversation(
                    conversation_id=item["conversation_id"],
                    title=item.get("title"),
                )
                continue

            # Auto-continuation, model_used, tools_used summary etc — let the
            # frontend keep its existing handling by forwarding under data-meta.
            out += self._sse.data_custom("meta", item)

        return out

    def encode_error(self, message: str) -> bytes:
        return self._sse.error(str(message))

    # ── File download (separate from encode_data in the legacy path) ──────

    def encode_file_download(
        self,
        file_id: str,
        filename: str,
        download_url: str,
        file_type: str = "",
        size_kb: float = 0,
        tool_name: str = "",
    ) -> bytes:
        prefix = self.open_step() if not self._step_open else b""
        return prefix + self._sse.data_file_download({
            "type": "file_download",
            "file_id": file_id,
            "filename": filename,
            "download_url": download_url,
            "file_type": file_type,
            "size_kb": size_kb,
            "tool_name": tool_name,
        })

    # ── Finish (the legacy "this is the end of the response" signal) ──────

    def encode_finish_message(
        self,
        stop_reason: str = "stop",
        usage: Optional[Dict[str, int]] = None,
        is_continued: bool = False,
    ) -> bytes:
        # Forward usage as a meta event so the frontend can still record it.
        out = b""
        if usage:
            out += self._sse.data_custom("usage", {
                "finishReason": stop_reason,
                "usage": usage,
                "isContinued": is_continued,
            })
        out += self.emit_done()
        return out

    def encode_finish_step(self, *args, **kwargs) -> bytes:
        return self.close_step()

    def encode_start_step(self, message_id: str = "") -> bytes:
        return self.open_step()
