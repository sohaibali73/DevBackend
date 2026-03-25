"""
Base LLM Provider Interface
============================
Abstract classes and data structures for the multi-provider LLM system.

Every provider (Anthropic, OpenAI, OpenRouter, etc.) implements BaseLLMProvider.
The chat endpoint uses this interface — it doesn't care which provider is behind it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, AsyncGenerator


@dataclass
class LLMResponse:
    """
    Unified response from any LLM provider (non-streaming).

    Attributes:
        text: The assistant's text response (may be empty if only tool calls).
        tool_calls: List of tool calls in canonical format:
                    [{"id": "...", "name": "...", "args": {...}}, ...]
        usage: Token usage dict, e.g.
               {"input_tokens": 100, "output_tokens": 200}
        finish_reason: Why the response ended:
                       "stop", "tool_calls", "length", "error"
        raw_response: Original provider response object (for debugging/logging).
    """
    text: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    raw_response: Any = None


@dataclass
class StreamChunk:
    """
    Unified streaming chunk from any LLM provider.

    Attributes:
        type: Chunk type:
              - "text": text delta
              - "tool_call_start": a tool call has started
              - "tool_call_delta": tool call argument streaming delta
              - "tool_call": complete tool call (args fully received)
              - "finish": stream is done (has usage + finish_reason)
              - "error": an error occurred
        content: Text content (for "text" and "error" types)
        tool_id: Tool call ID (for tool_call_* types)
        tool_name: Tool name (for tool_call_start and tool_call types)
        tool_args: Complete tool arguments (for "tool_call" type) or
                   partial arguments string (for "tool_call_delta")
        usage: Token usage (for "finish" type)
        finish_reason: Why the stream ended (for "finish" type)
    """
    type: str = ""
    content: str = ""
    tool_id: str = ""
    tool_name: str = ""
    tool_args: Any = None  # dict for "tool_call", str for "tool_call_delta"
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: str = ""


class BaseLLMProvider(ABC):
    """
    Abstract base class for all LLM providers.

    Each provider implements:
      - stream_chat(): async generator yielding StreamChunk objects
      - chat(): non-streaming completion returning LLMResponse
      - validate_connection(): check if the API key works
      - normalize_tools(): convert tools to provider format
      - normalize_messages(): convert messages to provider format
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        Unique identifier for this provider.
        e.g. "anthropic", "openai", "openrouter", "vercel_gateway"
        """
        ...

    @property
    @abstractmethod
    def supported_models(self) -> List[str]:
        """
        List of model IDs this provider supports.
        e.g. ["claude-opus-4-6", "claude-sonnet-4-6", ...]
        """
        ...

    @abstractmethod
    async def stream_chat(
        self,
        messages: List[Dict],
        model: str,
        system: str = "",
        tools: Optional[List[Dict]] = None,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream a chat completion from this provider.

        Args:
            messages: Conversation messages in canonical format:
                      [{"role": "user", "content": "Hello"}, ...]
            model: Model ID to use (must be in supported_models).
            system: System prompt string.
            tools: Tool definitions in canonical format:
                   [{"name": "...", "description": "...",
                     "parameters": {JSON Schema}}, ...]
            max_tokens: Maximum tokens in the response.
            **kwargs: Provider-specific options.

        Yields:
            StreamChunk objects as the response is generated.
        """
        ...

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict],
        model: str,
        system: str = "",
        tools: Optional[List[Dict]] = None,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse:
        """
        Non-streaming chat completion.

        Same parameters as stream_chat, but returns a single LLMResponse.
        """
        ...

    @abstractmethod
    async def validate_connection(self) -> bool:
        """
        Check if the provider's API key is valid.

        Returns:
            True if the connection is valid, False otherwise.
        """
        ...

    def normalize_tools(self, tools: List[Dict]) -> List[Dict]:
        """
        Convert tools from canonical format to this provider's format.

        Canonical format:
            {"name": "execute_code",
             "description": "...",
             "parameters": {"type": "object", "properties": {...}, "required": [...]}}

        Anthropic format:
            {"name": "execute_code",
             "description": "...",
             "input_schema": {"type": "object", "properties": {...}, "required": [...]}}

        OpenAI format:
            {"type": "function",
             "function": {"name": "execute_code",
                          "description": "...",
                          "parameters": {...}}}

        Default: pass through unchanged (providers override this).
        """
        return tools

    def normalize_messages(self, messages: List[Dict]) -> List[Dict]:
        """
        Convert messages from canonical format to this provider's format.

        Default: pass through unchanged (providers override this).
        """
        return messages

    def supports_model(self, model: str) -> bool:
        """Check if this provider supports a given model."""
        return model in self.supported_models

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} provider={self.provider_name}>"