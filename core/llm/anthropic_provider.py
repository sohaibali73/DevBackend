"""
Anthropic Provider
==================
Wraps the existing Claude streaming and chat infrastructure behind the
BaseLLMProvider interface. Zero changes to existing code — this is a
thin adapter layer.

All existing behavior is preserved:
  - ClaudeAFLEngine for AFL generation
  - stream_claude_response for streaming
  - Anthropic beta skills
  - Extended thinking support
"""

import json
import logging
import traceback
from typing import Dict, Any, List, Optional, AsyncGenerator

import anthropic
import httpx

from core.llm.base import BaseLLMProvider, LLMResponse, StreamChunk

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Supported Claude models
# ---------------------------------------------------------------------------

CLAUDE_MODELS = [
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    # Snapshot variants
    "claude-opus-4-5-20251101",
    "claude-sonnet-4-5-20250929",
    "claude-sonnet-4-20250514",
    "claude-haiku-3-5-20241022",
]

# Maps finish_reason from Anthropic → canonical
_FINISH_REASON_MAP = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
}


class AnthropicProvider(BaseLLMProvider):
    """
    Anthropic Claude provider.

    Wraps the existing streaming infrastructure from core/streaming.py
    and the Claude API client. All existing behavior is preserved.

    For AFL-specific generation, use the _afl_engine property to access
    the ClaudeAFLEngine directly.
    """

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client: anthropic.AsyncAnthropic = anthropic.AsyncAnthropic(
            api_key=api_key,
            timeout=httpx.Timeout(
                timeout=900.0,   # 15 min — covers Opus + extended thinking
                connect=30.0,
                read=900.0,
                write=60.0,
            ),
        )
        # Lazy-loaded AFL engine (only created if needed)
        self._afl_engine = None

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def supported_models(self) -> List[str]:
        return list(CLAUDE_MODELS)

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        """Expose the raw Anthropic client for existing code that needs it."""
        return self._client

    @property
    def afl_engine(self):
        """
        Lazy-load the ClaudeAFLEngine for AFL-specific features.
        Reuses the same API key and client.
        """
        if self._afl_engine is None:
            from core.claude_engine import ClaudeAFLEngine
            self._afl_engine = ClaudeAFLEngine(api_key=self._api_key)
        return self._afl_engine

    # -----------------------------------------------------------------------
    # Streaming
    # -----------------------------------------------------------------------

    async def stream_chat(
        self,
        messages: List[Dict],
        model: str,
        system: str = "",
        tools: Optional[List[Dict]] = None,
        max_tokens: int = 1500000,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream a chat completion from Anthropic.

        Uses the raw Anthropic SDK streaming (client.messages.stream())
        and converts events to our unified StreamChunk format.
        """
        try:
            request_kwargs: Dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": self.normalize_messages(messages),
            }

            if system:
                request_kwargs["system"] = system

            if tools:
                request_kwargs["tools"] = self.normalize_tools(tools)

            # Pass through any extra kwargs (thinking, betas, etc.)
            for k, v in kwargs.items():
                if k not in request_kwargs:
                    request_kwargs[k] = v

            current_tool: Optional[Dict] = None

            async with self._client.messages.stream(**request_kwargs) as stream:
                async for event in stream:
                    # --- content block start ---
                    if event.type == "content_block_start":
                        block = event.content_block
                        if hasattr(block, "type"):
                            if block.type == "tool_use":
                                current_tool = {
                                    "id": block.id,
                                    "name": block.name,
                                    "input": "",
                                }
                                yield StreamChunk(
                                    type="tool_call_start",
                                    tool_id=block.id,
                                    tool_name=block.name,
                                )

                    # --- content block delta ---
                    elif event.type == "content_block_delta":
                        delta = event.delta
                        if hasattr(delta, "type"):
                            if delta.type == "text_delta":
                                yield StreamChunk(
                                    type="text", content=delta.text
                                )
                            elif delta.type == "input_json_delta" and current_tool:
                                current_tool["input"] += delta.partial_json
                                yield StreamChunk(
                                    type="tool_call_delta",
                                    tool_id=current_tool["id"],
                                    tool_name=current_tool["name"],
                                    tool_args=delta.partial_json,
                                )

                    # --- content block stop ---
                    elif event.type == "content_block_stop":
                        if current_tool and current_tool.get("input"):
                            try:
                                args = json.loads(current_tool["input"])
                            except json.JSONDecodeError:
                                args = {}
                            yield StreamChunk(
                                type="tool_call",
                                tool_id=current_tool["id"],
                                tool_name=current_tool["name"],
                                tool_args=args,
                            )
                        current_tool = None

                # Final message with usage
                final = await stream.get_final_message()
                usage = {}
                if hasattr(final, "usage") and final.usage:
                    usage = {
                        "input_tokens": final.usage.input_tokens,
                        "output_tokens": final.usage.output_tokens,
                    }
                    thinking_tokens = getattr(
                        final.usage, "thinking_tokens", 0
                    )
                    if thinking_tokens:
                        usage["thinking_tokens"] = thinking_tokens

                finish_reason = _FINISH_REASON_MAP.get(
                    final.stop_reason, "stop"
                )
                yield StreamChunk(
                    type="finish",
                    usage=usage,
                    finish_reason=finish_reason,
                )

        except Exception as e:
            logger.error("Anthropic stream error: %s", e, exc_info=True)
            yield StreamChunk(type="error", content=str(e))

    # -----------------------------------------------------------------------
    # Non-streaming
    # -----------------------------------------------------------------------

    async def chat(
        self,
        messages: List[Dict],
        model: str,
        system: str = "",
        tools: Optional[List[Dict]] = None,
        max_tokens: int = 15000,
        **kwargs,
    ) -> LLMResponse:
        """
        Non-streaming chat completion from Anthropic.
        """
        try:
            request_kwargs: Dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": self.normalize_messages(messages),
            }

            if system:
                request_kwargs["system"] = system

            if tools:
                request_kwargs["tools"] = self.normalize_tools(tools)

            for k, v in kwargs.items():
                if k not in request_kwargs:
                    request_kwargs[k] = v

            response = await self._client.messages.create(**request_kwargs)

            # Extract text and tool calls
            text = ""
            tool_calls = []

            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
                elif hasattr(block, "type") and block.type == "tool_use":
                    tool_calls.append({
                        "id": block.id,
                        "name": block.name,
                        "args": block.input,
                    })

            usage = {}
            if hasattr(response, "usage") and response.usage:
                usage = {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                }

            finish_reason = _FINISH_REASON_MAP.get(
                response.stop_reason, "stop"
            )

            return LLMResponse(
                text=text,
                tool_calls=tool_calls,
                usage=usage,
                finish_reason=finish_reason,
                raw_response=response,
            )

        except Exception as e:
            logger.error("Anthropic chat error: %s", e, exc_info=True)
            return LLMResponse(
                text="",
                finish_reason="error",
                usage={},
            )

    # -----------------------------------------------------------------------
    # Validation
    # -----------------------------------------------------------------------

    async def validate_connection(self) -> bool:
        """Verify the API key works with a minimal request."""
        try:
            response = await self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=15000,
                messages=[{"role": "user", "content": "Hi"}],
            )
            return response is not None
        except Exception as e:
            logger.warning("Anthropic connection validation failed: %s", e)
            return False

    # -----------------------------------------------------------------------
    # Format conversion
    # -----------------------------------------------------------------------

    def normalize_messages(self, messages: List[Dict]) -> List[Dict]:
        """
        Messages are already in Anthropic format in our system.
        Pass through unchanged.
        """
        return messages

    def normalize_tools(self, tools: List[Dict]) -> List[Dict]:
        """
        Convert canonical tool format to Anthropic format.

        Canonical:  {"name": ..., "description": ..., "parameters": {...}}
        Anthropic:  {"name": ..., "description": ..., "input_schema": {...}}
        """
        converted = []
        for tool in tools:
            if "input_schema" in tool:
                # Already in Anthropic format
                converted.append(tool)
            elif "parameters" in tool:
                converted.append({
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": tool["parameters"],
                })
            elif tool.get("type", "").startswith("web_search"):
                # Anthropic built-in tool — pass through
                converted.append(tool)
            else:
                # Unknown format — pass through and hope for the best
                converted.append(tool)
        return converted