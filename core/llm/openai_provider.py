"""
OpenAI Provider
===============
Implements BaseLLMProvider for OpenAI's GPT models.

Uses the openai Python SDK with async support.
Tool format: OpenAI function-calling format.
Streaming: SSE with delta.tool_calls.
"""

import json
import logging
from typing import Dict, Any, List, Optional, AsyncGenerator

import openai

from core.llm.base import BaseLLMProvider, LLMResponse, StreamChunk

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Supported OpenAI models
# ---------------------------------------------------------------------------

OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-4-turbo-preview",
    "gpt-4",
    "gpt-3.5-turbo",
    "o1-preview",
    "o1-mini",
]

_FINISH_REASON_MAP = {
    "stop": "stop",
    "length": "length",
    "tool_calls": "tool_calls",
    "content_filter": "stop",
}


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT provider."""

    def __init__(self, api_key: str, base_url: str = None):
        self._api_key = api_key
        self._client: openai.AsyncOpenAI = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def supported_models(self) -> List[str]:
        return list(OPENAI_MODELS)

    # -----------------------------------------------------------------------
    # Streaming
    # -----------------------------------------------------------------------

    async def stream_chat(
        self,
        messages: List[Dict],
        model: str,
        system: str = "",
        tools: Optional[List[Dict]] = None,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream a chat completion from OpenAI."""
        try:
            openai_messages = self.normalize_messages(messages, system)
            openai_tools = self.normalize_tools(tools) if tools else None

            request_kwargs: Dict[str, Any] = {
                "model": model,
                "messages": openai_messages,
                "max_tokens": max_tokens,
                "stream": True,
            }
            if openai_tools:
                request_kwargs["tools"] = openai_tools

            # Accumulate tool call deltas by index
            tool_call_accumulators: Dict[int, Dict] = {}

            async with self._client.chat.completions.stream(**request_kwargs) as stream:
                async for chunk in stream:
                    choice = chunk.choices[0] if chunk.choices else None
                    if not choice:
                        continue

                    delta = choice.delta

                    # Text content
                    if delta.content:
                        yield StreamChunk(type="text", content=delta.content)

                    # Tool calls (streaming deltas)
                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            if idx not in tool_call_accumulators:
                                tool_call_accumulators[idx] = {
                                    "id": tc_delta.id or "",
                                    "name": "",
                                    "args": "",
                                }

                            acc = tool_call_accumulators[idx]
                            if tc_delta.id:
                                acc["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    acc["name"] = tc_delta.function.name
                                    yield StreamChunk(
                                        type="tool_call_start",
                                        tool_id=acc["id"],
                                        tool_name=acc["name"],
                                    )
                                if tc_delta.function.arguments:
                                    acc["args"] += tc_delta.function.arguments
                                    yield StreamChunk(
                                        type="tool_call_delta",
                                        tool_id=acc["id"],
                                        tool_name=acc["name"],
                                        tool_args=tc_delta.function.arguments,
                                    )

                    # Finish reason
                    if choice.finish_reason:
                        # Emit complete tool calls
                        if choice.finish_reason == "tool_calls":
                            for idx, acc in tool_call_accumulators.items():
                                try:
                                    args = json.loads(acc["args"]) if acc["args"] else {}
                                except json.JSONDecodeError:
                                    args = {}
                                yield StreamChunk(
                                    type="tool_call",
                                    tool_id=acc["id"],
                                    tool_name=acc["name"],
                                    tool_args=args,
                                )

                        # Get usage from the final chunk
                        usage = {}
                        final_completion = await stream.get_final_completion()
                        if final_completion.usage:
                            usage = {
                                "input_tokens": final_completion.usage.prompt_tokens,
                                "output_tokens": final_completion.usage.completion_tokens,
                            }

                        yield StreamChunk(
                            type="finish",
                            usage=usage,
                            finish_reason=_FINISH_REASON_MAP.get(
                                choice.finish_reason, "stop"
                            ),
                        )

        except Exception as e:
            logger.error("OpenAI stream error: %s", e, exc_info=True)
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
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse:
        """Non-streaming chat completion from OpenAI."""
        try:
            openai_messages = self.normalize_messages(messages, system)
            openai_tools = self.normalize_tools(tools) if tools else None

            request_kwargs: Dict[str, Any] = {
                "model": model,
                "messages": openai_messages,
                "max_tokens": max_tokens,
            }
            if openai_tools:
                request_kwargs["tools"] = openai_tools

            response = await self._client.chat.completions.create(**request_kwargs)

            choice = response.choices[0]
            text = choice.message.content or ""
            tool_calls = []

            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    tool_calls.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "args": args,
                    })

            usage = {}
            if response.usage:
                usage = {
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens,
                }

            return LLMResponse(
                text=text,
                tool_calls=tool_calls,
                usage=usage,
                finish_reason=_FINISH_REASON_MAP.get(
                    choice.finish_reason, "stop"
                ),
                raw_response=response,
            )

        except Exception as e:
            logger.error("OpenAI chat error: %s", e, exc_info=True)
            return LLMResponse(text="", finish_reason="error", usage={})

    # -----------------------------------------------------------------------
    # Validation
    # -----------------------------------------------------------------------

    async def validate_connection(self) -> bool:
        """Verify the API key works."""
        try:
            models = await self._client.models.list(limit=1)
            return len(models.data) > 0
        except Exception as e:
            logger.warning("OpenAI connection validation failed: %s", e)
            return False

    # -----------------------------------------------------------------------
    # Format conversion
    # -----------------------------------------------------------------------

    def normalize_tools(self, tools: List[Dict]) -> List[Dict]:
        """
        Convert canonical tool format to OpenAI function format.

        Canonical:  {"name": ..., "description": ..., "parameters": {...}}
        OpenAI:     {"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}
        """
        converted = []
        for tool in tools:
            # Skip Anthropic built-in tools (web_search, etc.)
            tool_type = tool.get("type", "")
            if tool_type.startswith("web_search") or tool_type == "tool_search_tool_regex":
                continue
            if tool_type == "tool_search_tool_bm25":
                continue

            if tool.get("type") == "function" and "function" in tool:
                # Already in OpenAI format
                converted.append(tool)
            elif "name" in tool and "input_schema" in tool:
                # Anthropic format → OpenAI format
                converted.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool["input_schema"],
                    },
                })
            elif "name" in tool and "parameters" in tool:
                # Canonical format → OpenAI format
                converted.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool["parameters"],
                    },
                })
        return converted

    def normalize_messages(
        self, messages: List[Dict], system: str = ""
    ) -> List[Dict]:
        """
        Convert messages to OpenAI format.

        Key differences from Anthropic:
        - System prompt is a message with role="system" (not a separate param)
        - tool_use blocks → assistant message with tool_calls array
        - tool_result blocks → separate role="tool" messages
        - Content can be string or array of content blocks
        """
        openai_messages = []

        # Add system message first
        if system:
            openai_messages.append({"role": "system", "content": system})

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                # Already handled above, but include if present in messages
                openai_messages.append({"role": "system", "content": content})
                continue

            if isinstance(content, str):
                openai_messages.append({"role": role, "content": content})
                continue

            if isinstance(content, list):
                # Anthropic content blocks format
                text_parts = []
                tool_calls = []
                tool_results = []

                for block in content:
                    if isinstance(block, str):
                        text_parts.append(block)
                        continue

                    block_type = block.get("type", "")

                    if block_type == "text":
                        text_parts.append(block.get("text", ""))

                    elif block_type == "tool_use":
                        tool_calls.append({
                            "id": block.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": json.dumps(block.get("input", {})),
                            },
                        })

                    elif block_type == "tool_result":
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": block.get("tool_use_id", ""),
                            "content": block.get("content", "")
                            if isinstance(block.get("content"), str)
                            else json.dumps(block.get("content", "")),
                        })

                if role == "user" and tool_results:
                    # Tool results come as separate tool messages in OpenAI
                    # Any text content goes in a follow-up user message
                    openai_messages.extend(tool_results)
                    if text_parts:
                        openai_messages.append({
                            "role": "user",
                            "content": "\n".join(text_parts),
                        })
                elif role == "assistant" and tool_calls:
                    openai_messages.append({
                        "role": "assistant",
                        "content": "\n".join(text_parts) if text_parts else None,
                        "tool_calls": tool_calls,
                    })
                else:
                    openai_messages.append({
                        "role": role,
                        "content": "\n".join(text_parts) if text_parts else "",
                    })
            else:
                openai_messages.append({"role": role, "content": str(content)})

        return openai_messages