"""
Vercel AI SDK Integration Module
================================
Native integration with Vercel AI Gateway and AI SDK Data Stream Protocol.

This module provides:
1. Vercel AI Gateway client (proxied Anthropic API)
2. AI SDK Data Stream Protocol encoder
3. Generative UI component streaming
4. Tool calling with proper streaming format

Compatible with:
- useChat() hook from @ai-sdk/react
- streamUI() from ai/rsc
- generateText() from ai
"""

import json
import logging
import os
import time
import httpx
from typing import Dict, Any, List, Optional, AsyncGenerator, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
import anthropic

logger = logging.getLogger(__name__)

# Default model
DEFAULT_MODEL = "claude-sonnet-4-20250514"


class StreamPartType(Enum):
    """Vercel AI SDK Data Stream Protocol part types."""
    TEXT = "0"           # Text delta
    DATA = "2"           # JSON data array
    ERROR = "3"          # Error message
    ASSISTANT_MESSAGE = "4"  # Assistant message
    ASSISTANT_CONTROL = "5"  # Assistant control data
    DATA_MESSAGE = "6"   # Data message
    TOOL_CALL_STREAMING_START = "7"  # Tool call start (streaming)
    TOOL_CALL_DELTA = "8"  # Tool call argument delta
    TOOL_CALL = "9"      # Complete tool call
    TOOL_RESULT = "a"    # Tool result
    FINISH_MESSAGE = "d"  # Finish with reason
    FINISH_STEP = "e"    # Finish step
    START_STEP = "f"     # Start step


@dataclass
class StreamMessage:
    """Represents a message in the AI SDK format."""
    role: str
    content: str
    id: Optional[str] = None
    tool_calls: List[Dict] = field(default_factory=list)
    tool_results: List[Dict] = field(default_factory=list)


class VercelAIStreamProtocol:
    """
    Encoder for Vercel AI SDK Data Stream Protocol.
    
    Format: {type}:{JSON value}\n
    
    See: https://sdk.vercel.ai/docs/ai-sdk-ui/stream-protocol
    """
    
    @staticmethod
    def text(content: str) -> str:
        """Encode text delta."""
        return f"{StreamPartType.TEXT.value}:{json.dumps(content)}\n"
    
    @staticmethod
    def data(data: List[Any]) -> str:
        """Encode data array."""
        return f"{StreamPartType.DATA.value}:{json.dumps(data)}\n"
    
    @staticmethod
    def error(message: str) -> str:
        """Encode error message."""
        return f"{StreamPartType.ERROR.value}:{json.dumps(message)}\n"
    
    @staticmethod
    def tool_call_streaming_start(tool_call_id: str, tool_name: str) -> str:
        """Signal start of streaming tool call."""
        return f"{StreamPartType.TOOL_CALL_STREAMING_START.value}:{json.dumps({'toolCallId': tool_call_id, 'toolName': tool_name})}\n"
    
    @staticmethod
    def tool_call_delta(tool_call_id: str, args_text_delta: str) -> str:
        """Stream tool call argument delta."""
        return f"{StreamPartType.TOOL_CALL_DELTA.value}:{json.dumps({'toolCallId': tool_call_id, 'argsTextDelta': args_text_delta})}\n"
    
    @staticmethod
    def tool_call(tool_call_id: str, tool_name: str, args: Dict[str, Any]) -> str:
        """Encode complete tool call."""
        return f"{StreamPartType.TOOL_CALL.value}:{json.dumps({'toolCallId': tool_call_id, 'toolName': tool_name, 'args': args})}\n"
    
    @staticmethod
    def tool_result(tool_call_id: str, result: Any) -> str:
        """Encode tool result."""
        result_str = result if isinstance(result, str) else json.dumps(result)
        return f"{StreamPartType.TOOL_RESULT.value}:{json.dumps({'toolCallId': tool_call_id, 'result': result_str})}\n"
    
    @staticmethod
    def finish_message(
        finish_reason: str = "stop",
        usage: Optional[Dict[str, int]] = None,
        is_continued: bool = False
    ) -> str:
        """Encode finish message with reason and usage."""
        payload = {
            "finishReason": finish_reason,
            "usage": usage or {"promptTokens": 0, "completionTokens": 0},
            "isContinued": is_continued
        }
        return f"{StreamPartType.FINISH_MESSAGE.value}:{json.dumps(payload)}\n"
    
    @staticmethod
    def finish_step(
        finish_reason: str = "stop",
        usage: Optional[Dict[str, int]] = None,
        is_continued: bool = False
    ) -> str:
        """Encode finish step."""
        payload = {
            "finishReason": finish_reason,
            "usage": usage or {"promptTokens": 0, "completionTokens": 0},
            "isContinued": is_continued
        }
        return f"{StreamPartType.FINISH_STEP.value}:{json.dumps(payload)}\n"
    
    @staticmethod
    def start_step(message_id: str) -> str:
        """Signal start of a new step."""
        return f"{StreamPartType.START_STEP.value}:{json.dumps({'messageId': message_id})}\n"
    
    @staticmethod
    def assistant_message(message_id: str) -> str:
        """Encode assistant message metadata."""
        return f"{StreamPartType.ASSISTANT_MESSAGE.value}:{json.dumps({'id': message_id})}\n"


class GenerativeUIStream:
    """
    Stream builder for Generative UI components.
    
    Supports streaming React components that can be rendered
    by the AI SDK RSC (React Server Components) integration.
    """
    
    @staticmethod
    def component(
        component_type: str,
        props: Dict[str, Any],
        component_id: Optional[str] = None
    ) -> str:
        """
        Encode a UI component for streaming.
        
        Args:
            component_type: Type of component (e.g., 'chart', 'code', 'table')
            props: Component properties
            component_id: Unique component identifier
            
        Returns:
            Encoded component data
        """
        component_data = [{
            "type": "component",
            "componentType": component_type,
            "componentId": component_id or f"comp_{hash(json.dumps(props)) % 100000}",
            "props": props
        }]
        return VercelAIStreamProtocol.data(component_data)
    
    @staticmethod
    def code_artifact(
        code: str,
        language: str,
        title: Optional[str] = None,
        artifact_id: Optional[str] = None
    ) -> str:
        """
        Stream a code artifact (React, HTML, SVG, etc.).
        
        This format is compatible with AI SDK's artifact rendering.
        """
        artifact_data = [{
            "type": "artifact",
            "artifactType": "code",
            "id": artifact_id or f"code_{hash(code) % 100000}",
            "language": language,
            "title": title or f"{language.upper()} Code",
            "content": code
        }]
        return VercelAIStreamProtocol.data(artifact_data)
    
    @staticmethod
    def react_component(
        code: str,
        component_name: str = "Component",
        artifact_id: Optional[str] = None
    ) -> str:
        """
        Stream a React component artifact for live rendering.
        """
        return GenerativeUIStream.code_artifact(
            code=code,
            language="jsx",
            title=component_name,
            artifact_id=artifact_id
        )
    
    @staticmethod
    def chart(
        data: List[Dict],
        chart_type: str = "line",
        title: Optional[str] = None,
        config: Optional[Dict] = None
    ) -> str:
        """Stream chart component data."""
        return GenerativeUIStream.component(
            component_type="chart",
            props={
                "data": data,
                "type": chart_type,
                "title": title,
                "config": config or {}
            }
        )
    
    @staticmethod  
    def mermaid_diagram(code: str, title: Optional[str] = None) -> str:
        """Stream a Mermaid diagram."""
        return GenerativeUIStream.code_artifact(
            code=code,
            language="mermaid",
            title=title or "Diagram"
        )


class VercelAIGatewayClient:
    """
    Client for Vercel AI Gateway with Anthropic provider.
    
    Can use either:
    1. Direct Anthropic API
    2. Vercel AI Gateway (if VERCEL_AI_GATEWAY_URL is set)
    
    The gateway provides:
    - Unified API across providers
    - Built-in caching
    - Analytics and monitoring
    - Rate limiting
    """
    
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        gateway_url: Optional[str] = None,
        timeout: float = 60.0
    ):
        """
        Initialize the client.
        
        Args:
            api_key: Anthropic API key
            model: Model to use
            gateway_url: Optional Vercel AI Gateway URL
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        
        # Check for gateway URL from env or parameter
        self.gateway_url = gateway_url or os.getenv("VERCEL_AI_GATEWAY_URL")
        
        if self.gateway_url:
            # Use gateway with httpx
            self.use_gateway = True
            self.http_client = httpx.AsyncClient(
                base_url=self.gateway_url,
                timeout=timeout,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
            )
            logger.info(f"Using Vercel AI Gateway: {self.gateway_url}")
        else:
            # Use direct Anthropic SDK
            self.use_gateway = False
            self.client = anthropic.Anthropic(api_key=api_key)
            logger.info("Using direct Anthropic API")
    
    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        system: str = "",
        tools: Optional[List[Dict]] = None,
        max_tokens: int = 4096,
        tool_handler: Optional[Callable[[str, str, Dict], Any]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat completion with AI SDK Data Stream Protocol.
        
        Args:
            messages: Conversation messages
            system: System prompt
            tools: Tool definitions
            max_tokens: Maximum tokens
            tool_handler: Async function to handle tool calls
            
        Yields:
            AI SDK Data Stream Protocol formatted chunks
        """
        protocol = VercelAIStreamProtocol()
        
        try:
            # Generate message ID
            message_id = f"msg_{int(time.time() * 1000)}"
            
            # Signal start
            yield protocol.start_step(message_id)
            
            if self.use_gateway:
                async for chunk in self._stream_via_gateway(
                    messages, system, tools, max_tokens, tool_handler, protocol
                ):
                    yield chunk
            else:
                async for chunk in self._stream_via_anthropic(
                    messages, system, tools, max_tokens, tool_handler, protocol
                ):
                    yield chunk
                    
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield protocol.error(str(e))
    
    async def _stream_via_anthropic(
        self,
        messages: List[Dict],
        system: str,
        tools: Optional[List[Dict]],
        max_tokens: int,
        tool_handler: Optional[Callable],
        protocol: VercelAIStreamProtocol
    ) -> AsyncGenerator[str, None]:
        """Stream using direct Anthropic SDK."""
        
        accumulated_text = ""
        pending_tool_calls = []
        
        # Build request
        request_kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages
        }
        
        if system:
            request_kwargs["system"] = system
        
        if tools:
            request_kwargs["tools"] = tools
        
        try:
            with self.client.messages.stream(**request_kwargs) as stream:
                current_tool: Optional[Dict] = None
                
                for event in stream:
                    if event.type == "content_block_start":
                        if hasattr(event.content_block, "type"):
                            if event.content_block.type == "tool_use":
                                # Start streaming tool call
                                current_tool = {
                                    "id": event.content_block.id,
                                    "name": event.content_block.name,
                                    "input": ""
                                }
                                yield protocol.tool_call_streaming_start(
                                    current_tool["id"],
                                    current_tool["name"]
                                )
                                
                    elif event.type == "content_block_delta":
                        if hasattr(event.delta, "type"):
                            if event.delta.type == "text_delta":
                                text = event.delta.text
                                accumulated_text += text
                                yield protocol.text(text)
                                
                            elif event.delta.type == "input_json_delta":
                                if current_tool:
                                    delta = event.delta.partial_json
                                    current_tool["input"] += delta
                                    yield protocol.tool_call_delta(
                                        current_tool["id"],
                                        delta
                                    )
                    
                    elif event.type == "content_block_stop":
                        if current_tool and current_tool.get("input"):
                            # Parse and emit complete tool call
                            try:
                                args = json.loads(current_tool["input"])
                            except json.JSONDecodeError:
                                args = {}
                            
                            yield protocol.tool_call(
                                current_tool["id"],
                                current_tool["name"],
                                args
                            )
                            
                            pending_tool_calls.append({
                                "id": current_tool["id"],
                                "name": current_tool["name"],
                                "args": args
                            })
                            current_tool = None
                
                # Get final message
                final_message = stream.get_final_message()
                
                # Handle tool calls if we have a handler
                if pending_tool_calls and tool_handler:
                    for tool_call in pending_tool_calls:
                        try:
                            result = await tool_handler(
                                tool_call["id"],
                                tool_call["name"],
                                tool_call["args"]
                            )
                            yield protocol.tool_result(tool_call["id"], result)
                        except Exception as e:
                            yield protocol.tool_result(
                                tool_call["id"],
                                json.dumps({"error": str(e)})
                            )
                
                # Emit finish
                usage = {
                    "promptTokens": final_message.usage.input_tokens,
                    "completionTokens": final_message.usage.output_tokens
                }
                
                finish_reason = "stop"
                if final_message.stop_reason == "tool_use":
                    finish_reason = "tool-calls"
                elif final_message.stop_reason == "max_tokens":
                    finish_reason = "length"
                
                yield protocol.finish_step(finish_reason, usage)
                yield protocol.finish_message(finish_reason, usage)
                
        except Exception as e:
            logger.error(f"Anthropic stream error: {e}")
            yield protocol.error(str(e))
    
    async def _stream_via_gateway(
        self,
        messages: List[Dict],
        system: str,
        tools: Optional[List[Dict]],
        max_tokens: int,
        tool_handler: Optional[Callable],
        protocol: VercelAIStreamProtocol
    ) -> AsyncGenerator[str, None]:
        """Stream using Vercel AI Gateway."""
        
        # Build gateway request
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "stream": True
        }
        
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = tools
        
        try:
            async with self.http_client.stream(
                "POST",
                "/v1/messages",
                json=payload
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        
                        try:
                            event = json.loads(data)
                            # Process gateway event and convert to AI SDK format
                            async for chunk in self._process_gateway_event(
                                event, protocol, tool_handler
                            ):
                                yield chunk
                        except json.JSONDecodeError:
                            continue
                            
        except httpx.HTTPError as e:
            logger.error(f"Gateway HTTP error: {e}")
            yield protocol.error(f"Gateway error: {str(e)}")
    
    async def _process_gateway_event(
        self,
        event: Dict,
        protocol: VercelAIStreamProtocol,
        tool_handler: Optional[Callable]
    ) -> AsyncGenerator[str, None]:
        """Process a gateway SSE event."""
        event_type = event.get("type")
        
        if event_type == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                yield protocol.text(delta.get("text", ""))
        
        elif event_type == "message_stop":
            usage = event.get("usage", {})
            yield protocol.finish_message("stop", {
                "promptTokens": usage.get("input_tokens", 0),
                "completionTokens": usage.get("output_tokens", 0)
            })
    
    async def generate(
        self,
        messages: List[Dict[str, Any]],
        system: str = "",
        tools: Optional[List[Dict]] = None,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        Non-streaming generation.
        
        Returns:
            Response dict with text, tool_calls, and usage
        """
        if self.use_gateway:
            return await self._generate_via_gateway(
                messages, system, tools, max_tokens
            )
        else:
            return self._generate_via_anthropic(
                messages, system, tools, max_tokens
            )
    
    def _generate_via_anthropic(
        self,
        messages: List[Dict],
        system: str,
        tools: Optional[List[Dict]],
        max_tokens: int
    ) -> Dict[str, Any]:
        """Non-streaming generation via Anthropic."""
        
        request_kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages
        }
        
        if system:
            request_kwargs["system"] = system
        if tools:
            request_kwargs["tools"] = tools
        
        response = self.client.messages.create(**request_kwargs)
        
        # Extract content
        text = ""
        tool_calls = []
        
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text
            elif hasattr(block, "type") and block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "args": block.input
                })
        
        return {
            "text": text,
            "tool_calls": tool_calls,
            "usage": {
                "promptTokens": response.usage.input_tokens,
                "completionTokens": response.usage.output_tokens
            },
            "finish_reason": response.stop_reason
        }
    
    async def _generate_via_gateway(
        self,
        messages: List[Dict],
        system: str,
        tools: Optional[List[Dict]],
        max_tokens: int
    ) -> Dict[str, Any]:
        """Non-streaming generation via gateway."""
        
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "stream": False
        }
        
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = tools
        
        response = await self.http_client.post("/v1/messages", json=payload)
        response.raise_for_status()
        
        data = response.json()
        
        text = ""
        tool_calls = []
        
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block["id"],
                    "name": block["name"],
                    "args": block["input"]
                })
        
        return {
            "text": text,
            "tool_calls": tool_calls,
            "usage": {
                "promptTokens": data.get("usage", {}).get("input_tokens", 0),
                "completionTokens": data.get("usage", {}).get("output_tokens", 0)
            },
            "finish_reason": data.get("stop_reason", "stop")
        }
    
    async def close(self):
        """Close the client."""
        if self.use_gateway and hasattr(self, "http_client"):
            await self.http_client.aclose()


# Convenience functions

def create_client(
    api_key: str,
    model: str = DEFAULT_MODEL,
    gateway_url: Optional[str] = None
) -> VercelAIGatewayClient:
    """
    Create a Vercel AI Gateway client.
    
    Args:
        api_key: Anthropic API key
        model: Model to use
        gateway_url: Optional gateway URL (falls back to env var)
        
    Returns:
        Configured client
    """
    return VercelAIGatewayClient(
        api_key=api_key,
        model=model,
        gateway_url=gateway_url
    )


def convert_messages_to_anthropic(messages: List[Dict]) -> List[Dict]:
    """
    Convert AI SDK message format to Anthropic format.
    
    AI SDK format:
    - role: 'user' | 'assistant' | 'system' | 'tool'
    - content: string | parts array
    - toolInvocations: array of tool calls/results
    
    Anthropic format:
    - role: 'user' | 'assistant'
    - content: string | content blocks
    """
    converted = []
    
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")
        
        if role == "system":
            # System messages are handled separately in Anthropic
            continue
        
        if role == "tool":
            # Tool results need to be added as user messages with tool_result blocks
            tool_call_id = msg.get("tool_call_id")
            converted.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": content if isinstance(content, str) else json.dumps(content)
                }]
            })
        else:
            # Check for tool invocations in the message
            tool_invocations = msg.get("toolInvocations", [])
            
            if tool_invocations and role == "assistant":
                # Assistant message with tool calls
                content_blocks = []
                
                if content:
                    content_blocks.append({"type": "text", "text": content})
                
                for invocation in tool_invocations:
                    if invocation.get("state") == "call" or "args" in invocation:
                        content_blocks.append({
                            "type": "tool_use",
                            "id": invocation.get("toolCallId"),
                            "name": invocation.get("toolName"),
                            "input": invocation.get("args", {})
                        })
                
                converted.append({
                    "role": "assistant",
                    "content": content_blocks
                })
            else:
                # Regular message
                converted.append({
                    "role": role,
                    "content": content
                })
    
    return converted


def convert_tools_to_anthropic(tools: List[Dict]) -> List[Dict]:
    """
    Convert AI SDK tool format to Anthropic format.
    
    AI SDK format:
    {
        type: "function",
        function: {
            name: string,
            description: string,
            parameters: JSONSchema
        }
    }
    
    Anthropic format:
    {
        name: string,
        description: string,
        input_schema: JSONSchema
    }
    """
    converted = []
    
    for tool in tools:
        if tool.get("type") == "function":
            func = tool.get("function", {})
            converted.append({
                "name": func.get("name"),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}})
            })
        elif "name" in tool and "input_schema" in tool:
            # Already in Anthropic format
            converted.append(tool)
        elif "type" in tool and tool["type"].startswith("web_search"):
            # Anthropic built-in tool
            converted.append(tool)
    
    return converted
