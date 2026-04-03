"""
Streaming utilities for Vercel AI SDK v7 Beta
Implements the AI SDK v7 Beta UI Message Stream Protocol for real-time responses.

This module provides the VercelAIStreamEncoder for the new v7 Beta protocol format.

See: https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol
"""

import json
import logging
import time
from typing import Dict, Any, AsyncGenerator, Optional, List
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)


# ============================================================================
# AI SDK v7 Beta UI Message Stream Protocol Encoder
# ============================================================================

class VercelAIStreamEncoder:
    """
    Encode responses for Vercel AI SDK v7 UI Message Stream Protocol.
    
    This is the format expected by useChat() in AI SDK v7.
    Format: Server-Sent Events (SSE) with 'data: ' prefix and '\n\n' suffix.
    
    Chunk types:
    - start: Start of message
    - text-start: Start of text block
    - text-delta: Text content chunk
    - text-end: End of text block
    - tool-input-start: Tool call started (streaming)
    - tool-input-delta: Tool input streaming
    - tool-input-available: Tool input complete
    - tool-output-available: Tool result available
    - tool-output-error: Tool execution error
    - start-step: Start of a step
    - finish-step: End of a step
    - finish: End of message
    - error: Error occurred
    - data-{name}: Custom data parts
    """
    
    @staticmethod
    def _encode(chunk: dict) -> str:
        """Encode a chunk according to SSE protocol v1 requirements."""
        return f"data: {json.dumps(chunk)}\n\n"
    
    @staticmethod
    def encode_start(message_id: str, message_metadata: Optional[Any] = None) -> str:
        """Signal start of new message."""
        chunk = {"type": "start", "messageId": message_id}
        if message_metadata is not None:
            chunk["messageMetadata"] = message_metadata
        return VercelAIStreamEncoder._encode(chunk)
    
    @staticmethod
    def encode_text_start(text_id: str, provider_metadata: Optional[Dict] = None) -> str:
        """Signal start of text block."""
        chunk = {"type": "text-start", "id": text_id}
        if provider_metadata:
            chunk["providerMetadata"] = provider_metadata
        return VercelAIStreamEncoder._encode(chunk)
    
    @staticmethod
    def encode_text_delta(text_id: str, delta: str, provider_metadata: Optional[Dict] = None) -> str:
        """Encode text delta using AI SDK v7 UI Message Stream Protocol."""
        if not delta:
            return ""
        chunk = {"type": "text-delta", "id": text_id, "delta": delta}
        if provider_metadata:
            chunk["providerMetadata"] = provider_metadata
        return VercelAIStreamEncoder._encode(chunk)
    
    @staticmethod
    def encode_text_end(text_id: str, provider_metadata: Optional[Dict] = None) -> str:
        """Signal end of text block."""
        chunk = {"type": "text-end", "id": text_id}
        if provider_metadata:
            chunk["providerMetadata"] = provider_metadata
        return VercelAIStreamEncoder._encode(chunk)
    
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
        return VercelAIStreamEncoder._encode(chunk)
    
    @staticmethod
    def encode_tool_input_delta(tool_call_id: str, input_text_delta: str) -> str:
        """Stream tool call argument delta."""
        if not input_text_delta:
            return ""
        return VercelAIStreamEncoder._encode({'type': 'tool-input-delta', 'toolCallId': tool_call_id, 'inputTextDelta': input_text_delta})
    
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
        return VercelAIStreamEncoder._encode(chunk)
    
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
        return VercelAIStreamEncoder._encode(chunk)
    
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
        return VercelAIStreamEncoder._encode(chunk)
    
    @staticmethod
    def encode_data(data_name: str, data: Any = None, data_id: Optional[str] = None, transient: bool = False) -> str:
        """
        Encode custom data (type data-{name}).
        
        Supports two calling conventions:
        1. encode_data("name", data)        — explicit name + data (original API)
        2. encode_data({"key": "value"})     — single dict (chat.py shorthand, uses "custom" as name)
        """
        # Support chat.py shorthand: encode_data({"key": "value"})
        if isinstance(data_name, dict) and data is None:
            data = data_name
            data_name = "custom"
        chunk = {"type": f"data-{data_name}", "data": data}
        if data_id:
            chunk["id"] = data_id
        if transient:
            chunk["transient"] = transient
        return VercelAIStreamEncoder._encode(chunk)
    
    @staticmethod
    def encode_error(error_message: str) -> str:
        """Encode error message."""
        return VercelAIStreamEncoder._encode({'type': 'error', 'errorText': error_message})
    
    @staticmethod
    def encode_start_step() -> str:
        """Signal start of a new step."""
        return VercelAIStreamEncoder._encode({'type': 'start-step'})
    
    @staticmethod
    def encode_finish_step() -> str:
        """Signal end of a step."""
        return VercelAIStreamEncoder._encode({'type': 'finish-step'})
    
    @staticmethod
    def encode_finish_message(stop_reason: str = "stop", message_metadata: Optional[Any] = None) -> str:
        """Encode finish message with reason."""
        chunk = {"type": "finish", "finishReason": stop_reason}
        if message_metadata is not None:
            chunk["messageMetadata"] = message_metadata
        return VercelAIStreamEncoder._encode(chunk)
    
    @staticmethod
    def encode_message_metadata(message_metadata: Any) -> str:
        """Encode message metadata update."""
        return VercelAIStreamEncoder._encode({'type': 'message-metadata', 'messageMetadata': message_metadata})
    
    @staticmethod
    def encode_abort(reason: Optional[str] = None) -> str:
        """Encode abort signal."""
        chunk = {"type": "abort"}
        if reason:
            chunk["reason"] = reason
        return VercelAIStreamEncoder._encode(chunk)
    
    @staticmethod
    def encode_done() -> str:
        """Signal stream termination (AI SDK v7 protocol)."""
        # The finish event already signals completion. [DONE] is legacy OpenAI format.
        # Return empty string as no separate terminator is required for v7 protocol.
        return ""

    # ── Convenience wrapper methods ──────────────────────────────────────
    # These methods provide a simpler API for chat.py while delegating to
    # the full v7 Beta protocol methods above.

    @staticmethod
    def encode_text(text: str, text_id: Optional[str] = None) -> str:
        """
        Convenience: Encode a complete text block (start + delta + end).
        Used by chat.py for simple text streaming.
        """
        import time as _time
        tid = text_id or f"text_{int(_time.time() * 1000)}"
        return (
            VercelAIStreamEncoder.encode_text_start(tid)
            + VercelAIStreamEncoder.encode_text_delta(tid, text)
            + VercelAIStreamEncoder.encode_text_end(tid)
        )

    @staticmethod
    def encode_tool_call(tool_call_id: str, tool_name: str, input: Any) -> str:
        """
        Convenience: Encode a complete tool call (input-start + input-available).
        Used by chat.py for tool invocation streaming.
        """
        return (
            VercelAIStreamEncoder.encode_tool_input_start(tool_call_id, tool_name)
            + VercelAIStreamEncoder.encode_tool_input_available(tool_call_id, tool_name, input)
        )

    @staticmethod
    def encode_tool_result(tool_call_id: str, output: Any) -> str:
        """
        Convenience: Encode a tool result.
        Used by chat.py for tool result streaming.
        """
        return VercelAIStreamEncoder.encode_tool_output_available(tool_call_id, output)

    @staticmethod
    def encode_file_download(file_id: str, filename: str, download_url: str, file_type: str = "unknown", size_kb: float = 0, tool_name: str = "") -> str:
        """Emit a downloadable-file event as custom data (type data-file_download)."""
        return VercelAIStreamEncoder._encode({'type': 'data-file_download', 'data': {'file_id': file_id, 'filename': filename, 'download_url': download_url, 'file_type': file_type, 'size_kb': size_kb, 'tool_name': tool_name}})


# ============================================================================
# Generative UI Stream Builder
# ============================================================================

class GenerativeUIStreamBuilder:
    """
    Build streaming Generative UI components.
    
    Supports streaming React components, charts, diagrams, and other
    interactive elements that can be rendered by the frontend.
    """
    
    @staticmethod
    def add_generative_ui_component(
        component_type: str,
        code: str,
        language: str = "jsx",
        component_id: Optional[str] = None,
        props: Optional[Dict[str, Any]] = None
    ) -> str:
        """Add a UI component to the stream."""
        component_data = [{
            "type": "artifact",
            "artifactType": component_type,
            "id": component_id or f"ui_{hash(code) % 100000}",
            "language": language,
            "content": code,
            "props": props or {}
        }]
        return f"{json.dumps({'type': 'data-artifact', 'data': component_data})}\n"
    
    @staticmethod
    def add_react_component(
        code: str,
        component_name: str = "Component",
        component_id: Optional[str] = None
    ) -> str:
        """Add a React component artifact."""
        return GenerativeUIStreamBuilder.add_generative_ui_component(
            component_type="react",
            code=code,
            language="jsx",
            component_id=component_id,
            props={"name": component_name}
        )
    
    @staticmethod
    def add_chart(
        data: List[Dict],
        chart_type: str = "line",
        title: Optional[str] = None,
        config: Optional[Dict] = None
    ) -> str:
        """Add a chart component."""
        chart_data = [{
            "type": "component",
            "componentType": "chart",
            "chartType": chart_type,
            "data": data,
            "title": title,
            "config": config or {}
        }]
        return f"{json.dumps({'type': 'data-component', 'data': chart_data})}\n"
    
    @staticmethod
    def add_mermaid_diagram(code: str, title: Optional[str] = None) -> str:
        """Add a Mermaid diagram."""
        return GenerativeUIStreamBuilder.add_generative_ui_component(
            component_type="mermaid",
            code=code,
            language="mermaid",
            props={"title": title}
        )
    
    @staticmethod
    def add_code_block(
        code: str,
        language: str,
        title: Optional[str] = None,
        artifact_id: Optional[str] = None
    ) -> str:
        """Add a syntax-highlighted code block."""
        return GenerativeUIStreamBuilder.add_generative_ui_component(
            component_type="code",
            code=code,
            language=language,
            component_id=artifact_id,
            props={"title": title, "showLineNumbers": True}
        )


# ============================================================================
# Claude Streaming Helper
# ============================================================================

async def stream_claude_response(
    client: AsyncAnthropic,
    model: str,
    system_prompt: str,
    messages: list,
    tools: Optional[list] = None,
    max_tokens: int = 4096,
    supabase_client=None,
    api_key: str = None,
) -> AsyncGenerator[str, None]:
    """
    Stream a chat response from Anthropic API using AI SDK v7 Beta UI Message Stream Protocol.
    Handles the full tool_use → tool_result → continue loop correctly.
    """
    from core.tools import handle_tool_call

    encoder = VercelAIStreamEncoder()
    messages = list(messages)
    message_id = f"msg_{int(time.time() * 1000)}"
    text_id = f"text_{int(time.time() * 1000)}"
    text_started = False

    try:
        yield encoder.encode_start(message_id)
        
        while True:
            request_kwargs = {
                "model": model,
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": messages,
            }
            if tools:
                request_kwargs["tools"] = tools

            current_tool_calls = []
            current_tool = None
            accumulated_content = []

            async with client.messages.stream(**request_kwargs) as stream:
                async for event in stream:
                    if event.type == "content_block_start":
                        if hasattr(event.content_block, "type"):
                            if event.content_block.type == "tool_use":
                                if text_started:
                                    yield encoder.encode_text_end(text_id)
                                    text_started = False
                                current_tool = {
                                    "id": event.content_block.id,
                                    "name": event.content_block.name,
                                    "input": "",
                                }
                                yield encoder.encode_tool_input_start(
                                    current_tool["id"], current_tool["name"]
                                )
                            elif event.content_block.type == "text":
                                accumulated_content.append({"type": "text", "text": ""})

                    elif event.type == "content_block_delta":
                        if hasattr(event.delta, "type"):
                            if event.delta.type == "text_delta":
                                text = event.delta.text
                                if accumulated_content and accumulated_content[-1]["type"] == "text":
                                    accumulated_content[-1]["text"] += text
                                if not text_started:
                                    yield encoder.encode_text_start(text_id)
                                    text_started = True
                                yield encoder.encode_text_delta(text_id, text)

                            elif event.delta.type == "input_json_delta" and current_tool:
                                delta = event.delta.partial_json
                                current_tool["input"] += delta
                                yield encoder.encode_tool_input_delta(
                                    current_tool["id"], delta
                                )

                    elif event.type == "content_block_stop":
                        if current_tool and current_tool.get("input"):
                            try:
                                args = json.loads(current_tool["input"])
                            except json.JSONDecodeError:
                                args = {}
                            yield encoder.encode_tool_input_available(
                                current_tool["id"], current_tool["name"], args
                            )
                            current_tool_calls.append({
                                "id": current_tool["id"],
                                "name": current_tool["name"],
                                "input": args,
                            })
                            accumulated_content.append({
                                "type": "tool_use",
                                "id": current_tool["id"],
                                "name": current_tool["name"],
                                "input": args,
                            })
                        current_tool = None

                final_message = await stream.get_final_message()
                stop_reason = final_message.stop_reason

            if stop_reason != "tool_use" or not current_tool_calls:
                if text_started:
                    yield encoder.encode_text_end(text_id)
                    text_started = False
                finish_reason = "stop"
                if stop_reason == "max_tokens":
                    finish_reason = "length"
                yield encoder.encode_finish_step()
                yield encoder.encode_finish_message(finish_reason)
                yield encoder.encode_done()
                break

            messages.append({
                "role": "assistant",
                "content": accumulated_content,
            })

            tool_results = []
            for call in current_tool_calls:
                try:
                    result_str = await asyncio.to_thread(
                        handle_tool_call,
                        tool_name=call["name"],
                        tool_input=call["input"],
                        supabase_client=supabase_client,
                        api_key=api_key,
                    )
                except Exception as tool_err:
                    result_str = json.dumps({"error": str(tool_err)})

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": call["id"],
                    "content": result_str,
                })

            messages.append({
                "role": "user",
                "content": tool_results,
            })

            for result in tool_results:
                yield encoder.encode_tool_output_available(
                    result["tool_use_id"],
                    result["content"],
                )

            yield encoder.encode_finish_step()

    except Exception as e:
        logger.error(f"Streaming error: {e}", exc_info=True)
        yield encoder.encode_error(str(e))


async def stream_with_artifacts(
    client: AsyncAnthropic,
    model: str,
    system_prompt: str,
    messages: list,
    tools: Optional[list] = None,
    max_tokens: int = 4096,
) -> AsyncGenerator[str, None]:
    """
    Stream response with automatic artifact detection and streaming.

    Detects code artifacts (React, Mermaid, etc.) in the response and
    streams them as Generative UI components.
    """
    from core.artifact_parser import ArtifactParser
    import time

    encoder = VercelAIStreamEncoder()
    ui_builder = GenerativeUIStreamBuilder()
    accumulated_content = ""
    message_id = f"msg_{int(time.time() * 1000)}"
    text_id = f"text_{int(time.time() * 1000)}"
    text_started = False

    try:
        yield encoder.encode_start(message_id)
        
        request_kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": messages,
        }

        if tools:
            request_kwargs["tools"] = tools

        async with client.messages.stream(**request_kwargs) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    if hasattr(event.delta, "type") and event.delta.type == "text_delta":
                        text = event.delta.text
                        accumulated_content += text
                        if not text_started:
                            yield encoder.encode_text_start(text_id)
                            text_started = True
                        yield encoder.encode_text_delta(text_id, text)

            final_message = await stream.get_final_message()

        if text_started:
            yield encoder.encode_text_end(text_id)
            text_started = False

        artifacts = ArtifactParser.extract_artifacts(accumulated_content)

        for artifact in artifacts:
            artifact_type = artifact.get('type', 'code')
            code = artifact.get('code', '')
            language = artifact.get('language', artifact_type)

            if artifact_type == 'react' or language in ['jsx', 'tsx']:
                yield ui_builder.add_react_component(
                    code=code,
                    component_name=artifact.get('id', 'Component'),
                    component_id=artifact.get('id')
                )
            elif artifact_type == 'mermaid':
                yield ui_builder.add_mermaid_diagram(code)
            else:
                yield ui_builder.add_code_block(
                    code=code,
                    language=language,
                    artifact_id=artifact.get('id')
                )

        yield encoder.encode_finish_step()
        yield encoder.encode_finish_message("stop")
        yield encoder.encode_done()

    except Exception as e:
        logger.error(f"Streaming with artifacts error: {e}", exc_info=True)
        yield encoder.encode_error(str(e))