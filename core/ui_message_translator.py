"""
On-the-fly translator from the legacy Vercel AI SDK Data Stream Protocol
(``0:...``, ``2:...``, ``9:...``) to the AI SDK v5 UI Message Stream SSE
protocol used by ``@ai-sdk/react`` v5.

This lets us expose a new ``/chat/agent/ui-stream`` endpoint without forking
the proven 1500-line ``chat_agent`` body. We simply run the existing
generator and parse its line-prefixed output back into typed events, then
re-emit them as SSE.

Format reference: https://sdk.vercel.ai/docs/concepts/ui-messages

The translator is forgiving — anything it can't parse is forwarded as a
``data-raw`` event so the frontend never silently loses data.
"""

from __future__ import annotations

import json
import logging
import time
from typing import AsyncGenerator, AsyncIterable, Optional

from core.ui_message_sse import UIMessageSSE

logger = logging.getLogger(__name__)


async def translate_to_ui_message_stream(
    source: AsyncIterable,
    message_id: Optional[str] = None,
) -> AsyncGenerator[bytes, None]:
    """Consume a legacy stream and re-emit as AI SDK v5 SSE.

    *source* yields ``str``/``bytes`` chunks following the Data Stream
    Protocol — typically ``f"0:\"hello\"\\n"`` for text, ``f"2:[{...}]\\n"``
    for data, etc.

    The translator is stateful within a single call:
      - Tracks a current text block (text-start / text-delta / text-end)
      - Tracks open tool-input ids so synthesized ``tool-input-start`` events
        are emitted exactly once per tool.
      - Buffers partial lines across chunks (chunks may split mid-line).
    """
    enc = UIMessageSSE()
    yield enc.start(message_id)
    yield enc.start_step()

    text_open = False
    tool_started: set[str] = set()
    line_buffer = ""

    def _open_text() -> bytes:
        nonlocal text_open
        if text_open:
            return b""
        text_open = True
        return enc.open_text()

    def _close_text() -> bytes:
        nonlocal text_open
        if not text_open:
            return b""
        text_open = False
        return enc.close_text()

    async for chunk in source:
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8", errors="replace")
        if not isinstance(chunk, str) or not chunk:
            continue

        line_buffer += chunk
        # The legacy protocol emits one event per line, terminated by ``\n``.
        # If chunks split mid-line we'll wait for the next chunk.
        while True:
            nl_idx = line_buffer.find("\n")
            if nl_idx < 0:
                break
            line = line_buffer[:nl_idx]
            line_buffer = line_buffer[nl_idx + 1:]
            if not line:
                continue

            # Each line is ``<code>:<json>``.
            colon = line.find(":")
            if colon < 1:
                # Unknown line — forward as raw data so we don't lose it.
                yield enc.data_custom("raw", line)
                continue

            code = line[:colon]
            payload_str = line[colon + 1:]
            try:
                payload = json.loads(payload_str)
            except (json.JSONDecodeError, ValueError):
                payload = payload_str

            # ── 0: text delta ──────────────────────────────────────────────
            if code == "0":
                if not isinstance(payload, str):
                    continue
                if not text_open:
                    yield _open_text()
                yield enc.text_delta(payload)

            # ── 2: data array ──────────────────────────────────────────────
            elif code == "2":
                # Close any open text block — data events shouldn't interleave.
                if text_open:
                    yield _close_text()
                items = payload if isinstance(payload, list) else [payload]
                for item in items:
                    if not isinstance(item, dict):
                        yield enc.data_custom("raw", item)
                        continue

                    # Routing rules (must match SSEAdapter.encode_data)
                    if "skill_status" in item:
                        yield enc.data_skill_status(
                            label=item.get("skill_status", ""),
                            slug=item.get("skill_slug", ""),
                        )
                        continue
                    if item.get("skill_heartbeat"):
                        yield UIMessageSSE.keepalive()
                        continue
                    if any(k.startswith("yang_") for k in item.keys()):
                        yield enc.data_yang(item)
                        continue
                    if item.get("type") == "file_download" or "download_url" in item:
                        yield enc.data_file_download(item)
                        continue
                    if "conversation_id" in item:
                        yield enc.data_conversation(
                            conversation_id=item["conversation_id"],
                            title=item.get("title"),
                        )
                        continue
                    yield enc.data_custom("meta", item)

            # ── 3: error ───────────────────────────────────────────────────
            elif code == "3":
                msg = payload if isinstance(payload, str) else json.dumps(payload)
                yield enc.error(msg)

            # ── 7: tool call start ─────────────────────────────────────────
            elif code == "7":
                if not isinstance(payload, dict):
                    continue
                if text_open:
                    yield _close_text()
                tid = payload.get("toolCallId") or ""
                tname = payload.get("toolName") or ""
                if tid and tid not in tool_started:
                    tool_started.add(tid)
                    yield enc.tool_input_start(tid, tname)

            # ── 8: tool call arg delta ─────────────────────────────────────
            elif code == "8":
                if not isinstance(payload, dict):
                    continue
                tid = payload.get("toolCallId") or ""
                delta = payload.get("argsTextDelta") or ""
                if tid and delta:
                    yield enc.tool_input_delta(tid, delta)

            # ── 9: full tool call (with parsed args) ───────────────────────
            elif code == "9":
                if not isinstance(payload, dict):
                    continue
                if text_open:
                    yield _close_text()
                tid = payload.get("toolCallId") or ""
                tname = payload.get("toolName") or ""
                args = payload.get("args") or {}
                if tid and tid not in tool_started:
                    tool_started.add(tid)
                    yield enc.tool_input_start(tid, tname)
                if tid:
                    yield enc.tool_input_available(tid, tname, args)

            # ── a: tool result ─────────────────────────────────────────────
            elif code == "a":
                if not isinstance(payload, dict):
                    continue
                tid = payload.get("toolCallId") or ""
                result = payload.get("result")
                if isinstance(result, str):
                    try:
                        result = json.loads(result)
                    except (json.JSONDecodeError, ValueError):
                        pass  # keep as string
                if tid:
                    yield enc.tool_output_available(tid, result)

            # ── d: finish message ──────────────────────────────────────────
            elif code == "d":
                # End of full assistant turn. Don't emit done here yet — the
                # source generator may yield more keepalives. We'll emit
                # finish + done after the loop.
                pass

            # ── e: finish step ─────────────────────────────────────────────
            elif code == "e":
                if text_open:
                    yield _close_text()
                yield enc.finish_step()
                yield enc.start_step()  # next iteration begins

            # ── f: start step ──────────────────────────────────────────────
            elif code == "f":
                if text_open:
                    yield _close_text()
                yield enc.start_step()

            # Unknown code — forward
            else:
                yield enc.data_custom("raw", {"code": code, "payload": payload})

    # Final close
    if text_open:
        yield _close_text()
    yield enc.finish_step()
    yield enc.finish()
    yield enc.done()
