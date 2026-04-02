"""
Vercel AI SDK Integration Module - v7 Beta
==========================================
Native integration with Vercel AI Gateway and AI SDK v7 Beta UI Message Stream Protocol.

This module provides:
1. Vercel AI Gateway client (proxied Anthropic API)
2. AI SDK v7 Beta UI Message Stream Protocol encoder
3. Generative UI component streaming
4. Tool calling with proper streaming format

v7 Beta Protocol Format:
- Uses JSON objects with "type" field (e.g., {"type":"text-delta","id":"text-1","delta":"Hello"})
- Supports: start, text-start, text-delta, text-end, tool-input-start, tool-input-delta,
  tool-input-available, tool-output-available, tool-output-error, start-step, finish-step,
  finish, error, data-{name}

Compatible with:
- useChat() hook from @ai-sdk/react v7 Beta
- AI SDK v7 Beta UI Message Stream Protocol
"""

import json
import logging
import os
import time
import httpx
from typing import Dict, Any, List, Optional, AsyncGenerator, Union, Callable
from dataclasses import dataclass, field
import anthropic

logger = logging.getLogger(__name__)

# Default model
DEFAULT_MODEL = "claude-sonnet-4-20250514"


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
    Encoder for Vercel AI SDK v7 Beta UI Message Stream Protocol.
    
    Format: {"type":"...", ...}\n
    
    See: https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol
    """
    
    @staticmethod
    def encode_start(message_id: str, message_metadata: Optional[Any] = None) -> str:
        """Signal start of new message."""
        chunk = {"type": "start", "messageId": message_id}
        if message_metadata is not None:
            chunk["messageMetadata"] = message_metadata
        return json.dumps(chunk) + "\n"
    
    @staticmethod
    def encode_text_start(text_id: str, provider_metadata: Optional[Dict] = None) -> str:
        """Signal start of text block."""
        chunk = {"type": "text-start", "id": text_id}
        if provider_metadata:
            chunk["providerMetadata"] = provider_metadata
        return json.dumps(chunk) + "\n"
    
    @staticmethod
    def encode_text(text_id: str, delta: str, provider_metadata: Optional[Dict] = None) -> str:
        """Encode text delta."""
        if not delta:
            return ""
        chunk = {"type": "text-delta", "id": text_id, "delta": delta}
        if provider_metadata:
            chunk["providerMetadata"] = provider_metadata
        return json.dumps(chunk) + "\n"
    
    @staticmethod
    def encode_text_end(text_id: str, provider_metadata: Optional[Dict] = None) -> str:
        """Signal end of text block."""
        chunk = {"type": "text-end", "id": text_id}
        if provider_metadata:
            chunk["providerMetadata"] = provider_metadata
        return json.dumps(chunk) + "\n"
    
    @staticmethod
    def encode_error(message: str) -> str:
        """Encode error message."""
        return json.dumps({"type": "error", "errorText": message}) + "\n"
    
    @staticmethod
    def encode_tool_input_start(tool_call_id: str, tool_name: str, provider_executed: bool = False, dynamic: bool = False, title: Optional[str] = None, provider_metadata: Optional[Dict] = None) -> str:
        """Signal start of streaming tool call."""
        chunk = {"type": "tool-input-start", "toolCallId": tool_call_id, "toolName": tool_name}
        if provider_executed:
            chunk["providerExecuted"] = provider_executed
        if dynamic:
            chunk["dynamic"] = dynamic
        if title:
            chunk["title"] = title
        if provider_metadata:
            chunk["providerMetadata"] = provider_metadata
        return json.dumps(chunk) + "\n"
    
    @staticmethod
    def encode_tool_input_delta(tool_call_id: str, input_text_delta: str) -> str:
        """Stream tool call argument delta."""
        if not input_text_delta:
            return ""
        return json.dumps({"type": "tool-input-delta", "toolCallId": tool_call_id, "inputTextDelta": input_text_delta}) + "\n"
    
    @staticmethod
    def encode_tool_input_available(tool_call_id: str, tool_name: str, input: Any, provider_executed: bool = False, dynamic: bool = False, title: Optional[str] = None, provider_metadata: Optional[Dict] = None) -> str:
        """Encode complete tool call input."""
        chunk = {"type": "tool-input-available", "toolCallId": tool_call_id, "toolName": tool_name, "input": input}
        if provider_executed:
            chunk["providerExecuted"] = provider_executed
        if dynamic:
            chunk["dynamic"] = dynamic
        if title:
            chunk["title"] = title
        if provider_metadata:
            chunk["providerMetadata"] = provider_metadata
        return json.dumps(chunk) + "\n"
    
    @staticmethod
    def encode_tool_output_available(tool_call_id: str, output: Any, provider_executed: bool = False, dynamic: bool = False, preliminary: bool = False, provider_metadata: Optional[Dict] = None) -> str:
        """Encode tool result."""
        chunk = {"type": "tool-output-available", "toolCallId": tool_call_id, "output": output}
        if provider_executed:
            chunk["providerExecuted"] = provider_executed
        if dynamic:
            chunk["dynamic"] = dynamic
        if preliminary:
            chunk["preliminary"] = preliminary
        if provider_metadata:
            chunk["providerMetadata"] = provider_metadata
        return json.dumps(chunk) + "\n"
    
    @staticmethod
    def encode_tool_output_error(tool_call_id: str, error_text: str, provider_executed: bool = False, dynamic: bool = False, provider_metadata: Optional[Dict] = None) -> str:
        """Encode tool execution error."""
        chunk = {"type": "tool-output-error", "toolCallId": tool_call_id, "errorText": error_text}
        if provider_executed:
            chunk["providerExecuted"] = provider_executed
        if dynamic:
            chunk["dynamic"] = dynamic
        if provider_metadata:
            chunk["providerMetadata"] = provider_metadata
        return json.dumps(chunk) + "\n"
    
    @staticmethod
    def encode_data(data_name: str, data: Any, data_id: Optional[str] = None, transient: bool = False) -> str:
        """Encode custom data (type data-{name})."""
        chunk = {"type": f"data-{data_name}", "data": data}
        if data_id:
            chunk["id"] = data_id
        if transient:
            chunk["transient"] = transient
        return json.dumps(chunk) + "\n"
    
    @staticmethod
    def encode_start_step() -> str:
        """Signal start of a new step."""
        return json.dumps({"type": "start-step"}) + "\n"
    
    @staticmethod
    def encode_finish_step() -> str:
        """Signal end of a step."""
        return json.dumps({"type": "finish-step"}) + "\n"
    
    @staticmethod
    def encode_finish_message(
        stop_reason: str = "stop",
        message_metadata: Optional[Any] = None
    ) -> str:
        """Encode finish message with reason."""
        chunk = {"type": "finish", "finishReason": stop_reason}
        if message_metadata is not None:
            chunk["messageMetadata"] = message_metadata
        return json.dumps(chunk) + "\n"
    
    @staticmethod
    def encode_message_metadata(message_metadata: Any) -> str:
        """Encode message metadata update."""
        return json.dumps({"type": "message-metadata", "messageMetadata": message_metadata}) + "\n"
    
    @staticmethod
    def encode_abort(reason: Optional[str] = None) -> str:
        """Encode abort signal."""
        chunk = {"type": "abort"}
        if reason:
            chunk["reason"] = reason
        return json.dumps(chunk) + "\n"


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
        return VercelAIStreamProtocol.encode_data(
            data_name="component",
            data={
                "componentType": component_type,
                "componentId": component_id or f"comp_{hash(json.dumps(props)) % 100000}",
                "props": props
            }
        )
    
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
        return VercelAIStreamProtocol.encode_data(
            data_name="artifact",
            data={
                "artifactType": "code",
                "id": artifact_id or f"code_{hash(code) % 100000}",
                "language": language,
                "title": title or f"{language.upper()} Code",
                "content": code
            }
        )
    
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
        Stream chat completion with AI SDK v7 Beta UI Message Stream Protocol.
        
        Args:
            messages: Conversation messages
            system: System prompt
            tools: Tool definitions
            max_tokens: Maximum tokens
            tool_handler: Async function to handle tool calls
            
        Yields:
            AI SDK v7 Beta UI Message Stream Protocol formatted chunks
        """
        protocol = VercelAIStreamProtocol()
        text_id = f"text_{int(time.time() * 1000)}"
        text_started = False
        
        try:
            # Generate message ID
            message_id = f"msg_{int(time.time() * 1000)}"
            
            # Signal start
            yield protocol.encode_start(message_id)
            
            if self.use_gateway:
                async for chunk in self._stream_via_gateway(
                    messages, system, tools, max_tokens, tool_handler, protocol, text_id
                ):
                    if chunk:
                        yield chunk
            else:
                async for chunk in self._stream_via_anthropic(
                    messages, system, tools, max_tokens, tool_handler, protocol, text_id
                ):
                    if chunk:
                        yield chunk
            
            # Ensure text block is closed
            if text_started:
                yield protocol.encode_text_end(text_id)
                    
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield protocol.encode_error(str(e))
    
    async def _stream_via_anthropic(
        self,
        messages: List[Dict],
        system: str,
        tools: Optional[List[Dict]],
        max_tokens: int,
        tool_handler: Optional[Callable],
        protocol: VercelAIStreamProtocol,
        text_id: str
    ) -> AsyncGenerator[str, None]:
        """Stream using direct Anthropic SDK."""
        
        accumulated_text = ""
        pending_tool_calls = []
        text_started = False
        
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
                                # Close text block if open
                                if text_started:
                                    yield protocol.encode_text_end(text_id)
                                    text_started = False
                                
                                # Start streaming tool call
                                current_tool = {
                                    "id": event.content_block.id,
                                    "name": event.content_block.name,
                                    "input": ""
                                }
                                yield protocol.encode_tool_input_start(
                                    current_tool["id"],
                                    current_tool["name"]
                                )
                                
                    elif event.type == "content_block_delta":
                        if hasattr(event.delta, "type"):
                            if event.delta.type == "text_delta":
                                text = event.delta.text
                                accumulated_text += text
                                if not text_started:
                                    yield protocol.encode_text_start(text_id)
                                    text_started = True
                                yield protocol.encode_text(text_id, text)
                                
                            elif event.delta.type == "input_json_delta":
                                if current_tool:
                                    delta = event.delta.partial_json
                                    current_tool["input"] += delta
                                    yield protocol.encode_tool_input_delta(
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
                            
                            yield protocol.encode_tool_input_available(
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
                            yield protocol.encode_tool_output_available(tool_call["id"], result)
                        except Exception as e:
                            yield protocol.encode_tool_output_error(
                                tool_call["id"],
                                str(e)
                            )
                
                # Emit finish
                finish_reason = "stop"
                if final_message.stop_reason == "tool_use":
                    finish_reason = "tool-calls"
                elif final_message.stop_reason == "max_tokens":
                    finish_reason = "length"
                
                yield protocol.encode_finish_step()
                yield protocol.encode_finish_message(finish_reason)
                
        except Exception as e:
            logger.error(f"Anthropic stream error: {e}")
            yield protocol.encode_error(str(e))
    
    async def _stream_via_gateway(
        self,
        messages: List[Dict],
        system: str,
        tools: Optional[List[Dict]],
        max_tokens: int,
        tool_handler: Optional[Callable],
        protocol: VercelAIStreamProtocol,
        text_id: str
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
                                event, protocol, tool_handler, text_id
                            ):
                                if chunk:
                                    yield chunk
                        except json.JSONDecodeError:
                            continue
                            
        except httpx.HTTPError as e:
            logger.error(f"Gateway HTTP error: {e}")
            yield protocol.encode_error(f"Gateway error: {str(e)}")
    
    async def _process_gateway_event(
        self,
        event: Dict,
        protocol: VercelAIStreamProtocol,
        tool_handler: Optional[Callable],
        text_id: str
    ) -> AsyncGenerator[str, None]:
        """Process a gateway SSE event."""
        event_type = event.get("type")
        
        if event_type == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                yield protocol.encode_text(text_id, delta.get("text", ""))
        
        elif event_type == "message_stop":
            yield protocol.encode_finish_message("stop")
    
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