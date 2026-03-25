"""
Vercel AI Gateway Provider
==========================
Wraps the existing VercelAIGatewayClient from core/vercel_ai.py behind
the BaseLLMProvider interface.

The Vercel AI Gateway acts as a proxy to multiple providers (Anthropic,
OpenAI, etc.) through a single endpoint. This provider routes requests
through that gateway.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, AsyncGenerator

from core.llm.base import BaseLLMProvider, LLMResponse, StreamChunk

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models available through Vercel AI Gateway
# These depend on what the gateway is configured to proxy.
# ---------------------------------------------------------------------------

VERCEL_GATEWAY_MODELS = [
    # Anthropic via gateway
    "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3-opus",
    "anthropic/claude-3-haiku",
    # OpenAI via gateway
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "openai/gpt-4-turbo",
    # Generic gateway model (routes to default)
    "gpt-4o",
    "claude-3.5-sonnet",
]

_FINISH_REASON_MAP = {
    "stop": "stop",
    "end_turn": "stop",
    "length": "length",
    "tool_calls": "tool_calls",
    "max_tokens": "length",
}


class VercelGatewayProvider(BaseLLMProvider):
    """
    Vercel AI Gateway provider.

    Routes requests through the Vercel AI Gateway, which proxies to
    underlying providers. Reuses existing VercelAIGatewayClient.
    """

    def __init__(self, api_key: str, gateway_url: str = None):
        self._api_key = api_key
        self._gateway_url = gateway_url or os.getenv("VERCEL_AI_GATEWAY_URL", "")
        # Lazy-load the existing client
        self._gateway_client = None

    @property
    def provider_name(self) -> str:
        return "vercel_gateway"

    @property
    def supported_models(self) -> List[str]:
        return list(VERCEL_GATEWAY_MODELS)

    def _ensure_client(self):
        """Lazy-load the Vercel gateway client."""
        if self._gateway_client is None:
            from core.vercel_ai import VercelAIGatewayClient
            self._gateway_client = VercelAIGatewayClient(
                api_key=self._api_key,
                gateway_url=self._gateway_url,
            )
        return self._gateway_client

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
        """Stream via Vercel AI Gateway."""
        try:
            client = self._ensure_client()
            gateway_tools = self.normalize_tools(tools) if tools else None

            async for raw_chunk in client.stream_chat(
                messages=messages,
                system=system,
                tools=gateway_tools,
                max_tokens=max_tokens,
            ):
                # Vercel gateway returns AI SDK Data Stream Protocol strings
                # Parse them into StreamChunk objects
                if not raw_chunk or not raw_chunk.strip():
                    continue

                chunk_type = raw_chunk[0] if raw_chunk else ""
                payload = raw_chunk[2:].strip() if len(raw_chunk) > 2 else ""

                if chunk_type == "0":  # text delta
                    try:
                        text = json.loads(payload)
                        yield StreamChunk(type="text", content=text)
                    except (json.JSONDecodeError, TypeError):
                        pass

                elif chunk_type == "9":  # complete tool call
                    try:
                        data = json.loads(payload)
                        args = data.get("args", {})
                        if isinstance(args, str):
                            args = json.loads(args)
                        yield StreamChunk(
                            type="tool_call",
                            tool_id=data.get("toolCallId", ""),
                            tool_name=data.get("toolName", ""),
                            tool_args=args,
                        )
                    except (json.JSONDecodeError, TypeError):
                        pass

                elif chunk_type == "a":  # tool result
                    try:
                        data = json.loads(payload)
                        yield StreamChunk(
                            type="tool_result",
                            tool_id=data.get("toolCallId", ""),
                            content=data.get("result", ""),
                        )
                    except (json.JSONDecodeError, TypeError):
                        pass

                elif chunk_type == "d":  # finish message
                    try:
                        data = json.loads(payload)
                        usage = data.get("usage", {})
                        # Convert OpenAI-style keys to canonical
                        canonical_usage = {
                            "input_tokens": usage.get("promptTokens", 0),
                            "output_tokens": usage.get("completionTokens", 0),
                        }
                        yield StreamChunk(
                            type="finish",
                            usage=canonical_usage,
                            finish_reason=data.get("finishReason", "stop"),
                        )
                    except (json.JSONDecodeError, TypeError):
                        yield StreamChunk(
                            type="finish",
                            usage={},
                            finish_reason="stop",
                        )

                elif chunk_type == "3":  # error
                    try:
                        error_msg = json.loads(payload)
                        yield StreamChunk(type="error", content=error_msg)
                    except (json.JSONDecodeError, TypeError):
                        yield StreamChunk(type="error", content=payload)

        except Exception as e:
            logger.error("Vercel gateway stream error: %s", e, exc_info=True)
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
        """Non-streaming via Vercel AI Gateway."""
        try:
            client = self._ensure_client()
            gateway_tools = self.normalize_tools(tools) if tools else None

            result = await client.generate(
                messages=messages,
                system=system,
                tools=gateway_tools,
                max_tokens=max_tokens,
            )

            # Convert gateway result to canonical LLMResponse
            tool_calls = []
            for tc in result.get("tool_calls", []):
                tool_calls.append({
                    "id": tc.get("id", ""),
                    "name": tc.get("name", ""),
                    "args": tc.get("args", {}),
                })

            usage = result.get("usage", {})
            canonical_usage = {
                "input_tokens": usage.get("promptTokens", 0),
                "output_tokens": usage.get("completionTokens", 0),
            }

            return LLMResponse(
                text=result.get("text", ""),
                tool_calls=tool_calls,
                usage=canonical_usage,
                finish_reason=result.get("finish_reason", "stop"),
                raw_response=result,
            )

        except Exception as e:
            logger.error("Vercel gateway chat error: %s", e, exc_info=True)
            return LLMResponse(text="", finish_reason="error", usage={})

    # -----------------------------------------------------------------------
    # Validation
    # -----------------------------------------------------------------------

    async def validate_connection(self) -> bool:
        """Verify the gateway URL and key work."""
        try:
            client = self._ensure_client()
            result = await client.generate(
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5,
            )
            return result is not None
        except Exception as e:
            logger.warning("Vercel gateway validation failed: %s", e)
            return False

    # -----------------------------------------------------------------------
    # Format conversion
    # -----------------------------------------------------------------------

    def normalize_tools(self, tools: List[Dict]) -> List[Dict]:
        """
        Convert tools to Anthropic format (since the gateway proxies
        to Anthropic by default).
        """
        converted = []
        for tool in tools:
            tool_type = tool.get("type", "")
            # Skip Anthropic built-in tools
            if tool_type.startswith("web_search"):
                continue
            if tool_type in ("tool_search_tool_regex", "tool_search_tool_bm25"):
                continue

            if "input_schema" in tool:
                converted.append(tool)
            elif "parameters" in tool:
                converted.append({
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": tool["parameters"],
                })
        return converted

    def normalize_messages(self, messages: List[Dict]) -> List[Dict]:
        """Pass through — gateway handles format conversion."""
        return messages