Implements the AI SDK Data Stream Protocol for real-time responses.

This module provides two streaming encoders:
1. VercelAIStreamEncoder - Legacy SSE format (for existing /chat endpoints)
2. VercelAIStreamProtocol - Native AI SDK Data Stream Protocol (new /api/ai endpoints)

See: https://sdk.vercel.ai/docs/ai-sdk-ui/stream-protocol
"""

import json
import logging
from typing import Dict, Any, AsyncGenerator, Optional, List
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)


# ============================================================================
# AI SDK Data Stream Protocol Encoder (Recommended for new integrations)
# ============================================================================

class VercelAIStreamEncoder:
    """
    Encode responses for Vercel AI SDK Data Stream Protocol.
    
    This is the format expected by useChat() and useCompletion() hooks.
    Format: {type}:{JSON value}\n
    
    Type codes:
    - 0: Text delta
    - 2: Data array (custom data)
    - 3: Error
    - 7: Tool call streaming start
    - 8: Tool call argument delta  
    - 9: Complete tool call
    - a: Tool result
    - d: Finish message
    - e: Finish step
    - f: Start step
    """
    
    @staticmethod
    def encode_text(text: str) -> str:
        """
        Encode text delta using AI SDK Data Stream Protocol.
        
        Args:
            text: Text content to stream
            
        Returns:
            Data stream protocol formatted string
        """
        if not text:
            return ""
        return f"0:{json.dumps(text)}\n"
    
    @staticmethod
    def encode_tool_call(tool_id: str, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """
        Encode complete tool call.
        
        Args:
            tool_id: Unique ID for this tool call
            tool_name: Name of the tool being called
            tool_input: Input parameters for the tool
            
        Returns:
            Data stream protocol formatted string
        """
        return f"9:{json.dumps({'toolCallId': tool_id, 'toolName': tool_name, 'args': tool_input})}\n"
    
    @staticmethod
    def encode_tool_call_start(tool_id: str, tool_name: str) -> str:
        """
        Signal start of streaming tool call.
        
        Args:
            tool_id: Unique ID for this tool call
            tool_name: Name of the tool
            
        Returns:
            Data stream protocol formatted string
        """
        return f"7:{json.dumps({'toolCallId': tool_id, 'toolName': tool_name})}\n"
    
    @staticmethod
    def encode_tool_call_delta(tool_id: str, args_delta: str) -> str:
        """
        Stream tool call argument delta.
        
        Args:
            tool_id: ID of the tool call
            args_delta: JSON string delta for arguments
            
        Returns:
            Data stream protocol formatted string
        """
        return f"8:{json.dumps({'toolCallId': tool_id, 'argsTextDelta': args_delta})}\n"
    
    @staticmethod
    def encode_tool_result(tool_id: str, result: str) -> str:
        """
        Encode tool result.
        
        Args:
            tool_id: ID of the tool call
            result: Result from tool execution (string or JSON string)
            
        Returns:
            Data stream protocol formatted string
        """
        return f"a:{json.dumps({'toolCallId': tool_id, 'result': result})}\n"
    
    @staticmethod
    def encode_data(data: Any) -> str:
        """
        Encode custom data (sent as array).
        
        Args:
            data: Data to send (will be wrapped in array if not already)
            
        Returns:
            Data stream protocol formatted string
        """
        if not isinstance(data, list):
            data = [data]
        return f"2:{json.dumps(data)}\n"
    
    @staticmethod
    def encode_error(error_message: str) -> str:
        """
        Encode error message.
        
        Args:
            error_message: Error description
            
        Returns:
            Data stream protocol formatted string
        """
        return f"3:{json.dumps(error_message)}\n"
    
    @staticmethod
    def encode_finish_message(
        stop_reason: str = "stop",
        usage: Optional[Dict[str, int]] = None,
        is_continued: bool = False
    ) -> str:
        """
        Encode finish message with reason and usage.
        
        Args:
            stop_reason: Why the response stopped (stop, tool-calls, length, error)
            usage: Token usage data with promptTokens and completionTokens
            is_continued: Whether more content will follow
            
        Returns:
            Data stream protocol formatted string
        """
        payload = {
            "finishReason": stop_reason,
            "usage": usage or {"promptTokens": 0, "completionTokens": 0},
            "isContinued": is_continued
        }
        return f"d:{json.dumps(payload)}\n"
    
    @staticmethod
    def encode_finish_step(
        stop_reason: str = "stop",
        usage: Optional[Dict[str, int]] = None,
        is_continued: bool = False
    ) -> str:
        """
        Encode finish step (for multi-step tool use).
        
        Args:
            stop_reason: Why the step stopped
            usage: Token usage data
            is_continued: Whether more steps will follow
            
        Returns:
            Data stream protocol formatted string
        """
        payload = {
            "finishReason": stop_reason,
            "usage": usage or {"promptTokens": 0, "completionTokens": 0},
            "isContinued": is_continued
        }
        return f"e:{json.dumps(payload)}\n"
    
    @staticmethod
    def encode_start_step(message_id: str) -> str:
        """
        Signal start of a new step.
        
        Args:
            message_id: Unique message identifier
            
        Returns:
            Data stream protocol formatted string
        """
        return f"f:{json.dumps({'messageId': message_id})}\n"

    @staticmethod
    def encode_file_download(
        file_id: str,
        filename: str,
        download_url: str,
        file_type: str = "unknown",
        size_kb: float = 0,
        tool_name: str = "",
    ) -> str:
        """
        Emit a downloadable-file event as custom data (type 2).
        
        The frontend should listen for data items with type="file_download"
        and render a download button/card.
        
        Args:
            file_id: Unique file identifier
            filename: Suggested filename for the download
            download_url: Relative URL path to download the file (e.g. /files/{id}/download)
            file_type: File extension (pptx, docx, pdf, etc.)
            size_kb: File size in KB
            tool_name: The tool that created the file
            
        Returns:
            Data stream protocol formatted string
        """
        return f"2:{json.dumps([{'type': 'file_download', 'file_id': file_id, 'filename': filename, 'download_url': download_url, 'file_type': file_type, 'size_kb': size_kb, 'tool_name': tool_name}])}\n"
"""
Streaming utilities for Vercel AI SDK v7 Beta
Implements the AI SDK v7 Beta UI Message Stream Protocol for real-time responses.

This module provides the VercelAIStreamEncoder for the new v7 Beta protocol format.

See: https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol
"""

import json
import logging
from typing import Dict, Any, AsyncGenerator, Optional, List
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)


# ============================================================================
# AI SDK v7 Beta UI Message Stream Protocol Encoder
# ============================================================================

class VercelAIStreamEncoder:
    """
    Encode responses for Vercel AI SDK v7 Beta UI Message Stream Protocol.
    
    This is the format expected by useChat() in AI SDK v7 Beta.
    Format: {"type":"...", ...}\n
    
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
    def encode_start(message_id: str, message_metadata: Optional[Any] = None) -> str:
        """
        Signal start of new message.
        
        Args:
            message_id: Unique message identifier
            message_metadata: Optional message metadata
            
        Returns:
            UI Message Stream formatted string
        """
        chunk = {"type": "start", "messageId": message_id}
        if message_metadata is not None:
            chunk["messageMetadata"] = message_metadata
        return json.dumps(chunk) + "\n"
    
    @staticmethod
    def encode_text_start(text_id: str, provider_metadata: Optional[Dict] = None) -> str:
        """
        Signal start of text block.
        
        Args:
            text_id: Unique text block identifier
            provider_metadata: Optional provider metadata
            
        Returns:
            UI Message Stream formatted string
        """
        chunk = {"type": "text-start", "id": text_id}
        if provider_metadata:
            chunk["providerMetadata"] = provider_metadata
        return json.dumps(chunk) + "\n"
    
    @staticmethod
    def encode_text_delta(text_id: str, delta: str, provider_metadata: Optional[Dict] = None) -> str:
        """
        Encode text delta using AI SDK v7 Beta UI Message Stream Protocol.
        
        Args:
            text_id: Unique text block identifier
            delta: Text content to stream
            provider_metadata: Optional provider metadata
            
        Returns:
            UI Message Stream formatted string
        """
        if not delta:
            return ""
        chunk = {"type": "text-delta", "id": text_id, "delta": delta}
        if provider_metadata:
            chunk["providerMetadata"] = provider_metadata
        return json.dumps(chunk) + "\n"
    
    @staticmethod
    def encode_text_end(text_id: str, provider_metadata: Optional[Dict] = None) -> str:
        """
        Signal end of text block.
        
        Args:
            text_id: Unique text block identifier
            provider_metadata: Optional provider metadata
            
        Returns:
            UI Message Stream formatted string
        """
        chunk = {"type": "text-end", "id": text_id}
        if provider_metadata:
            chunk["providerMetadata"] = provider_metadata
        return json.dumps(chunk) + "\n"
    
    @staticmethod
    def encode_tool_input_start(tool_call_id: str, tool_name: str, provider_executed: bool = False, dynamic: bool = False, title: Optional[str] = None, provider_metadata: Optional[Dict] = None) -> str:
        """
        Signal start of streaming tool call.
        
        Args:
            tool_call_id: Unique ID for this tool call
            tool_name: Name of the tool
            provider_executed: Whether the tool was executed by the provider
            dynamic: Whether this is a dynamic tool
            title: Optional tool title
            provider_metadata: Optional provider metadata
            
        Returns:
            UI Message Stream formatted string
        """
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
        """
        Stream tool call argument delta.
        
        Args:
            tool_call_id: ID of the tool call
            input_text_delta: JSON string delta for arguments
            
        Returns:
            UI Message Stream formatted string
        """
        if not input_text_delta:
            return ""
        return json.dumps({"type": "tool-input-delta", "toolCallId": tool_call_id, "inputTextDelta": input_text_delta}) + "\n"
    
    @staticmethod
    def encode_tool_input_available(tool_call_id: str, tool_name: str, input: Any, provider_executed: bool = False, dynamic: bool = False, title: Optional[str] = None, provider_metadata: Optional[Dict] = None) -> str:
        """
        Encode complete tool call input.
        
        Args:
            tool_call_id: Unique ID for this tool call
            tool_name: Name of the tool being called
            input: Input parameters for the tool
            provider_executed: Whether the tool was executed by the provider
            dynamic: Whether this is a dynamic tool
            title: Optional tool title
            provider_metadata: Optional provider metadata
            
        Returns:
            UI Message Stream formatted string
        """
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
        """
        Encode tool result.
        
        Args:
            tool_call_id: ID of the tool call
            output: Result from tool execution
            provider_executed: Whether the tool was executed by the provider
            dynamic: Whether this is a dynamic tool
            preliminary: Whether this is a preliminary result
            provider_metadata: Optional provider metadata
            
        Returns:
            UI Message Stream formatted string
        """
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
        """
        Encode tool execution error.
        
        Args:
            tool_call_id: ID of the tool call
            error_text: Error message
            provider_executed: Whether the tool was executed by the provider
            dynamic: Whether this is a dynamic tool
            provider_metadata: Optional provider metadata
            
        Returns:
            UI Message Stream formatted string
        """
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
        """
        Encode custom data (type data-{name}).
        
        Args:
            data_name: Name of the data type
            data: Data to send
            data_id: Optional data identifier
            transient: Whether this data is transient
            
        Returns:
            UI Message Stream formatted string
        """
        chunk = {"type": f"data-{data_name}", "data": data}
        if data_id:
            chunk["id"] = data_id
        if transient:
            chunk["transient"] = transient
        return json.dumps(chunk) + "\n"
    
    @staticmethod
    def encode_error(error_message: str) -> str:
        """
        Encode error message.
        
        Args:
            error_message: Error description
            
        Returns:
            UI Message Stream formatted string
        """
        return json.dumps({"type": "error", "errorText": error_message}) + "\n"
    
    @staticmethod
    def encode_start_step() -> str:
        """
        Signal start of a new step.
        
        Returns:
            UI Message Stream formatted string
        """
        return json.dumps({"type": "start-step"}) + "\n"
    
    @staticmethod
    def encode_finish_step() -> str:
        """
        Signal end of a step.
        
        Returns:
            UI Message Stream formatted string
        """
        return json.dumps({"type": "finish-step"}) + "\n"
    
    @staticmethod
    def encode_finish_message(
        stop_reason: str = "stop",
        message_metadata: Optional[Any] = None
    ) -> str:
        """
        Encode finish message with reason.
        
        Args:
            stop_reason: Why the response stopped (stop, tool-calls, length, error)
            message_metadata: Optional message metadata
            
        Returns:
            UI Message Stream formatted string
        """
        chunk = {"type": "finish", "finishReason": stop_reason}
        if message_metadata is not None:
            chunk["messageMetadata"] = message_metadata
        return json.dumps(chunk) + "\n"
    
    @staticmethod
    def encode_message_metadata(message_metadata: Any) -> str:
        """
        Encode message metadata update.
        
        Args:
            message_metadata: Message metadata
            
        Returns:
            UI Message Stream formatted string
        """
        return json.dumps({"type": "message-metadata", "messageMetadata": message_metadata}) + "\n"
    
    @staticmethod
    def encode_abort(reason: Optional[str] = None) -> str:
        """
        Encode abort signal.
        
        Args:
            reason: Optional abort reason
            
        Returns:
            UI Message Stream formatted string
        """
        chunk = {"type": "abort"}
        if reason:
            chunk["reason"] = reason
        return json.dumps(chunk) + "\n"

    @staticmethod
    def encode_file_download(
        file_id: str,
        filename: str,
        download_url: str,
        file_type: str = "unknown",
        size_kb: float = 0,
        tool_name: str = "",
    ) -> str:
        """
        Emit a downloadable-file event as custom data (type data-file_download).
        
        The frontend should listen for data items with type="data-file_download"
        and render a download button/card.
        
        Args:
            file_id: Unique file identifier
            filename: Suggested filename for the download
            download_url: Relative URL path to download the file (e.g. /files/{id}/download)
            file_type: File extension (pptx, docx, pdf, etc.)
            size_kb: File size in KB
            tool_name: The tool that created the file
            
        Returns:
            UI Message Stream formatted string
        """
        return json.dumps({
            "type": "data-file_download",
            "data": {
                "file_id": file_id,
                "filename": filename,
                "download_url": download_url,
                "file_type": file_type,
                "size_kb": size_kb,
                "tool_name": tool_name
            }
        }) + "\n"
=====================================
Implements the AI SDK Data Stream Protocol for real-time responses.

This module provides two streaming encoders:
1. VercelAIStreamEncoder - Legacy SSE format (for existing /chat endpoints)
2. VercelAIStreamProtocol - Native AI SDK Data Stream Protocol (new /api/ai endpoints)

See: https://sdk.vercel.ai/docs/ai-sdk-ui/stream-protocol
"""

import json
import logging
from typing import Dict, Any, AsyncGenerator, Optional, List
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)


# ============================================================================
# AI SDK Data Stream Protocol Encoder (Recommended for new integrations)
# ============================================================================

class VercelAIStreamEncoder:
    """
    Encode responses for Vercel AI SDK Data Stream Protocol.
    
    This is the format expected by useChat() and useCompletion() hooks.
    Format: {type}:{JSON value}\n
    
    Type codes:
    - 0: Text delta
    - 2: Data array (custom data)
    - 3: Error
    - 7: Tool call streaming start
    - 8: Tool call argument delta  
    - 9: Complete tool call
    - a: Tool result
    - d: Finish message
    - e: Finish step
    - f: Start step
    """
    
    @staticmethod
    def encode_text(text: str) -> str:
        """
        Encode text delta using AI SDK Data Stream Protocol.
        
        Args:
            text: Text content to stream
            
        Returns:
            Data stream protocol formatted string
        """
        if not text:
            return ""
        return f"0:{json.dumps(text)}\n"
    
    @staticmethod
    def encode_tool_call(tool_id: str, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """
        Encode complete tool call.
        
        Args:
            tool_id: Unique ID for this tool call
            tool_name: Name of the tool being called
            tool_input: Input parameters for the tool
            
        Returns:
            Data stream protocol formatted string
        """
        return f"9:{json.dumps({'toolCallId': tool_id, 'toolName': tool_name, 'args': tool_input})}\n"
    
    @staticmethod
    def encode_tool_call_start(tool_id: str, tool_name: str) -> str:
        """
        Signal start of streaming tool call.
        
        Args:
            tool_id: Unique ID for this tool call
            tool_name: Name of the tool
            
        Returns:
            Data stream protocol formatted string
        """
        return f"7:{json.dumps({'toolCallId': tool_id, 'toolName': tool_name})}\n"
    
    @staticmethod
    def encode_tool_call_delta(tool_id: str, args_delta: str) -> str:
        """
        Stream tool call argument delta.
        
        Args:
            tool_id: ID of the tool call
            args_delta: JSON string delta for arguments
            
        Returns:
            Data stream protocol formatted string
        """
        return f"8:{json.dumps({'toolCallId': tool_id, 'argsTextDelta': args_delta})}\n"
    
    @staticmethod
    def encode_tool_result(tool_id: str, result: str) -> str:
        """
        Encode tool result.
        
        Args:
            tool_id: ID of the tool call
            result: Result from tool execution (string or JSON string)
            
        Returns:
            Data stream protocol formatted string
        """
        return f"a:{json.dumps({'toolCallId': tool_id, 'result': result})}\n"
    
    @staticmethod
    def encode_data(data: Any) -> str:
        """
        Encode custom data (sent as array).
        
        Args:
            data: Data to send (will be wrapped in array if not already)
            
        Returns:
            Data stream protocol formatted string
        """
        if not isinstance(data, list):
            data = [data]
        return f"2:{json.dumps(data)}\n"
    
    @staticmethod
    def encode_error(error_message: str) -> str:
        """
        Encode error message.
        
        Args:
            error_message: Error description
            
        Returns:
            Data stream protocol formatted string
        """
        return f"3:{json.dumps(error_message)}\n"
    
    @staticmethod
    def encode_finish_message(
        stop_reason: str = "stop",
        usage: Optional[Dict[str, int]] = None,
        is_continued: bool = False
    ) -> str:
        """
        Encode finish message with reason and usage.
        
        Args:
            stop_reason: Why the response stopped (stop, tool-calls, length, error)
            usage: Token usage data with promptTokens and completionTokens
            is_continued: Whether more content will follow
            
        Returns:
            Data stream protocol formatted string
        """
        payload = {
            "finishReason": stop_reason,
            "usage": usage or {"promptTokens": 0, "completionTokens": 0},
            "isContinued": is_continued
        }
        return f"d:{json.dumps(payload)}\n"
    
    @staticmethod
    def encode_finish_step(
        stop_reason: str = "stop",
        usage: Optional[Dict[str, int]] = None,
        is_continued: bool = False
    ) -> str:
        """
        Encode finish step (for multi-step tool use).
        
        Args:
            stop_reason: Why the step stopped
            usage: Token usage data
            is_continued: Whether more steps will follow
            
        Returns:
            Data stream protocol formatted string
        """
        payload = {
            "finishReason": stop_reason,
            "usage": usage or {"promptTokens": 0, "completionTokens": 0},
            "isContinued": is_continued
        }
        return f"e:{json.dumps(payload)}\n"
    
    @staticmethod
    def encode_start_step(message_id: str) -> str:
        """
        Signal start of a new step.
        
        Args:
            message_id: Unique message identifier
            
        Returns:
            Data stream protocol formatted string
        """
        return f"f:{json.dumps({'messageId': message_id})}\n"

    @staticmethod
    def encode_file_download(
        file_id: str,
        filename: str,
        download_url: str,
        file_type: str = "unknown",
        size_kb: float = 0,
        tool_name: str = "",
    ) -> str:
        """
        Emit a downloadable-file event as custom data (type 2).
        
        The frontend should listen for data items with type="file_download"
        and render a download button/card.
        
        Args:
            file_id: Unique file identifier
            filename: Suggested filename for the download
            download_url: Relative URL path to download the file (e.g. /files/{id}/download)
            file_type: File extension (pptx, docx, pdf, etc.)
            size_kb: File size in KB
            tool_name: The tool that created the file
            
        Returns:
            Data stream protocol formatted string
        """
        return f"2:{json.dumps([{'type': 'file_download', 'file_id': file_id, 'filename': filename, 'download_url': download_url, 'file_type': file_type, 'size_kb': size_kb, 'tool_name': tool_name}])}\n"


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
        """
        Add a UI component to the stream.
        
        Args:
            component_type: Type of component (react, chart, mermaid, html, svg)
            code: Component code/content
            language: Language for syntax highlighting
            component_id: Unique component identifier
            props: Additional component properties
            
        Returns:
            Data stream protocol formatted string with component data
        """
        component_data = [{
            "type": "artifact",
            "artifactType": component_type,
            "id": component_id or f"ui_{hash(code) % 100000}",
            "language": language,
            "content": code,
            "props": props or {}
        }]
        return f"2:{json.dumps(component_data)}\n"
    
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
        return f"2:{json.dumps(chart_data)}\n"
    
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
    Stream a chat response from Anthropic API using AI SDK Data Stream Protocol.
    Handles the full tool_use → tool_result → continue loop correctly.
    """
    from core.tools import handle_tool_call

    encoder = VercelAIStreamEncoder()
    # Work on a mutable copy so we can append tool results
    messages = list(messages)

    try:
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
                    # --- content block start ---
                    if event.type == "content_block_start":
                        if hasattr(event.content_block, "type"):
                            if event.content_block.type == "tool_use":
                                current_tool = {
                                    "id": event.content_block.id,
                                    "name": event.content_block.name,
                                    "input": "",
                                }
                                yield encoder.encode_tool_call_start(
                                    current_tool["id"], current_tool["name"]
                                )
                            elif event.content_block.type == "text":
                                accumulated_content.append(
                                    {"type": "text", "text": ""}
                                )

                    # --- content block delta ---
                    elif event.type == "content_block_delta":
                        if hasattr(event.delta, "type"):
                            if event.delta.type == "text_delta":
                                text = event.delta.text
                                if accumulated_content and accumulated_content[-1]["type"] == "text":
                                    accumulated_content[-1]["text"] += text
                                yield encoder.encode_text(text)

                            elif event.delta.type == "input_json_delta" and current_tool:
                                delta = event.delta.partial_json
                                current_tool["input"] += delta
                                yield encoder.encode_tool_call_delta(
                                    current_tool["id"], delta
                                )

                    # --- content block stop ---
                    elif event.type == "content_block_stop":
                        if current_tool and current_tool.get("input"):
                            try:
                                args = json.loads(current_tool["input"])
                            except json.JSONDecodeError:
                                args = {}
                            yield encoder.encode_tool_call(
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
                usage = {
                    "promptTokens": final_message.usage.input_tokens,
                    "completionTokens": final_message.usage.output_tokens,
                }
                stop_reason = final_message.stop_reason

            # --- If no tool calls, we're done ---
            if stop_reason != "tool_use" or not current_tool_calls:
                finish_reason = "stop"
                if stop_reason == "max_tokens":
                    finish_reason = "length"
                yield encoder.encode_finish_message(finish_reason, usage)
                break

            # --- Execute tools and build tool_result messages ---
            # Append assistant turn with tool_use blocks
            messages.append({
                "role": "assistant",
                "content": accumulated_content,
            })

            # Execute each tool and collect results
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

            # Append user turn with tool results so Claude can see them
            messages.append({
                "role": "user",
                "content": tool_results,
            })

            # Emit a: tool result frames BEFORE e: finish step so the AI SDK
            # receives all results before being told the step is complete
            for result in tool_results:
                yield encoder.encode_tool_result(
                    result["tool_use_id"],
                    result["content"],
                )

            # Signal step complete after results have been sent
            yield encoder.encode_finish_step("tool-calls", usage, is_continued=True)

            # Loop back to call Claude again with the tool results in context

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

    Args:
        client: Anthropic client
        model: Model to use
        system_prompt: System instructions
        messages: Message history
        tools: Available tools (optional)
        max_tokens: Maximum tokens in response

    Yields:
        AI SDK Data Stream Protocol formatted strings including artifacts
    """
    from core.artifact_parser import ArtifactParser

    encoder = VercelAIStreamEncoder()
    ui_builder = GenerativeUIStreamBuilder()
    accumulated_content = ""

    try:
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
                        yield encoder.encode_text(text)

            # Get final message
            final_message = await stream.get_final_message()
            usage = {
                "promptTokens": final_message.usage.input_tokens,
                "completionTokens": final_message.usage.output_tokens,
            }
        #test
        # Detect and stream artifacts
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

        yield encoder.encode_finish_message("stop", usage)

    except Exception as e:
        logger.error(f"Streaming with artifacts error: {e}", exc_info=True)
        yield encoder.encode_error(str(e))