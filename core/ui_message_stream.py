"""
UI Message Stream Protocol for AI SDK v7 Beta
==============================================

This module implements the UIMessageStreamResponse format used by AI SDK v7 Beta
for generative user interfaces with tool parts.

Key concepts:
- Messages have a `parts` array with typed content
- Tool parts use `tool-${toolName}` type naming
- Tool states: 'input-available' -> 'output-available' or 'output-error'
- v7 Beta uses JSON objects with "type" field instead of type codes

v7 Beta Protocol Format:
- Uses JSON objects with "type" field (e.g., {"type":"text-delta","id":"text-1","delta":"Hello"})
- Supports: start, text-start, text-delta, text-end, tool-input-start, tool-input-delta,
  tool-input-available, tool-output-available, tool-output-error, start-step, finish-step,
  finish, error, data-{name}

See: https://ai-sdk.dev/docs/ai-sdk-ui/generative-user-interfaces
"""

import json
import logging
import time
from typing import Dict, Any, List, Optional, AsyncGenerator
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class ToolState(Enum):
    """Tool invocation states for Generative UI."""
    INPUT_AVAILABLE = "input-available"    # Tool called, waiting for result
    OUTPUT_AVAILABLE = "output-available"  # Tool completed successfully
    OUTPUT_ERROR = "output-error"          # Tool failed with error


@dataclass
class TextPart:
    """Text content part."""
    type: str = "text"
    text: str = ""


@dataclass
class ToolPart:
    """Tool invocation part for Generative UI.
    
    The type is formatted as 'tool-{toolName}' to allow typed rendering.
    """
    type: str  # Format: 'tool-{toolName}'
    state: str  # ToolState value
    toolCallId: str
    input: Optional[Dict] = None    # Tool input arguments
    output: Optional[Any] = None    # Tool result (when state is output-available)
    errorText: Optional[str] = None # Error message (when state is output-error)
    
    @classmethod
    def create(cls, tool_name: str, tool_call_id: str, state: ToolState, 
               input_args: Optional[Dict] = None,
               output: Optional[Any] = None,
               error: Optional[str] = None) -> "ToolPart":
        """Create a tool part with proper type naming."""
        return cls(
            type=f"tool-{tool_name}",
            state=state.value,
            toolCallId=tool_call_id,
            input=input_args,
            output=output,
            errorText=error
        )


@dataclass 
class UIMessage:
    """UI Message format for AI SDK v7 Beta."""
    id: str
    role: str  # 'user' | 'assistant' | 'system'
    parts: List[Dict] = field(default_factory=list)
    createdAt: Optional[str] = None
    
    def add_text(self, text: str):
        """Add text part to message."""
        self.parts.append({"type": "text", "text": text})
    
    def add_tool_part(self, tool_name: str, tool_call_id: str, state: ToolState,
                      input_args: Optional[Dict] = None,
                      output: Optional[Any] = None,
                      error: Optional[str] = None):
        """Add tool part to message."""
        part = {
            "type": f"tool-{tool_name}",
            "state": state.value,
            "toolCallId": tool_call_id,
        }
        if input_args is not None:
            part["input"] = input_args
        if output is not None:
            part["output"] = output
        if error is not None:
            part["errorText"] = error
        self.parts.append(part)


class UIMessageStreamEncoder:
    """
    Encoder for UI Message Stream Response format - v7 Beta.
    
    This produces output compatible with `toUIMessageStreamResponse()` from AI SDK v7 Beta.
    
    Stream format uses JSON objects with "type" field:
    - start: Start of a new message
    - text-start: Start of text content
    - text-delta: Text content chunk
    - text-end: End of text content
    - tool-input-start: Tool call begins
    - tool-input-delta: Tool input streaming
    - tool-input-available: Tool input available
    - tool-output-available: Tool result available  
    - tool-output-error: Tool execution failed
    - start-step: Start of a new step
    - finish-step: End of a step
    - finish: Stream complete
    - error: Error occurred
    - data-{name}: Custom data parts
    """
    
    @staticmethod
    def encode_start(message_id: str, role: str = "assistant", message_metadata: Optional[Any] = None) -> str:
        """Signal start of new message."""
        chunk = {"type": "start", "messageId": message_id, "role": role}
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
    def encode_text_delta(text_id: str, delta: str, provider_metadata: Optional[Dict] = None) -> str:
        """Stream text content delta."""
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
    def encode_tool_input_start(tool_name: str, tool_call_id: str, provider_executed: bool = False, dynamic: bool = False, title: Optional[str] = None, provider_metadata: Optional[Dict] = None) -> str:
        """Signal tool call starting (input-streaming state)."""
        chunk = {"type": "tool-input-start", "toolName": tool_name, "toolCallId": tool_call_id}
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
    def encode_tool_input_available(tool_name: str, tool_call_id: str, input: Any, provider_executed: bool = False, dynamic: bool = False, title: Optional[str] = None, provider_metadata: Optional[Dict] = None) -> str:
        """Tool input arguments available (input-available state)."""
        chunk = {"type": "tool-input-available", "toolName": tool_name, "toolCallId": tool_call_id, "input": input}
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
    def encode_tool_output_available(tool_name: str, tool_call_id: str, output: Any, provider_executed: bool = False, dynamic: bool = False, preliminary: bool = False, provider_metadata: Optional[Dict] = None) -> str:
        """Tool execution result (output-available state)."""
        chunk = {"type": "tool-output-available", "toolName": tool_name, "toolCallId": tool_call_id, "output": output}
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
    def encode_tool_output_error(tool_name: str, tool_call_id: str, error_text: str, provider_executed: bool = False, dynamic: bool = False, provider_metadata: Optional[Dict] = None) -> str:
        """Tool execution failed (output-error state)."""
        chunk = {"type": "tool-output-error", "toolName": tool_name, "toolCallId": tool_call_id, "errorText": error_text}
        if provider_executed:
            chunk["providerExecuted"] = provider_executed
        if dynamic:
            chunk["dynamic"] = dynamic
        if provider_metadata:
            chunk["providerMetadata"] = provider_metadata
        return json.dumps(chunk) + "\n"
    
    @staticmethod
    def encode_start_step() -> str:
        """Signal start of a new step."""
        return json.dumps({"type": "start-step"}) + "\n"
    
    @staticmethod
    def encode_finish_step() -> str:
        """Signal step complete."""
        return json.dumps({"type": "finish-step"}) + "\n"
    
    @staticmethod
    def encode_finish(finish_reason: str = "stop", message_metadata: Optional[Any] = None) -> str:
        """Signal stream complete."""
        chunk = {"type": "finish", "finishReason": finish_reason}
        if message_metadata is not None:
            chunk["messageMetadata"] = message_metadata
        return json.dumps(chunk) + "\n"
    
    @staticmethod
    def encode_error(message: str) -> str:
        """Stream error event."""
        return json.dumps({"type": "error", "errorText": message}) + "\n"
    
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


class GenerativeUITools:
    """
    Tools optimized for Generative UI rendering.
    
    These tool definitions include metadata for UI rendering.
    """
    
    # Tool definitions with UI hints
    TOOLS = {
        "displayWeather": {
            "name": "displayWeather",
            "description": "Display weather information for a location",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The location to get weather for"
                    }
                },
                "required": ["location"]
            },
            "ui_component": "Weather"
        },
        "getStockPrice": {
            "name": "getStockPrice",
            "description": "Get current price for a stock symbol",
            "input_schema": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g., AAPL)"
                    }
                },
                "required": ["symbol"]
            },
            "ui_component": "Stock"
        },
        "generateAFL": {
            "name": "generateAFL",
            "description": "Generate AmiBroker AFL trading code",
            "input_schema": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Description of the trading strategy"
                    },
                    "type": {
                        "type": "string",
                        "enum": ["standalone", "composite", "indicator"],
                        "description": "Type of AFL code to generate"
                    }
                },
                "required": ["description"]
            },
            "ui_component": "AFLCode"
        },
        "showChart": {
            "name": "showChart",
            "description": "Display a chart visualization",
            "input_schema": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "description": "Chart data points"
                    },
                    "chartType": {
                        "type": "string",
                        "enum": ["line", "bar", "area", "pie"],
                        "description": "Type of chart"
                    },
                    "title": {
                        "type": "string",
                        "description": "Chart title"
                    }
                },
                "required": ["data"]
            },
            "ui_component": "Chart"
        },
        "showDiagram": {
            "name": "showDiagram",
            "description": "Display a Mermaid diagram",
            "input_schema": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Mermaid diagram code"
                    },
                    "title": {
                        "type": "string",
                        "description": "Diagram title"
                    }
                },
                "required": ["code"]
            },
            "ui_component": "MermaidDiagram"
        },
        "searchKnowledgeBase": {
            "name": "searchKnowledgeBase",
            "description": "Search the user's knowledge base documents",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "category": {
                        "type": "string",
                        "enum": ["afl", "strategy", "indicator", "general"],
                        "description": "Document category filter"
                    }
                },
                "required": ["query"]
            },
            "ui_component": "SearchResults"
        },
        "executeCode": {
            "name": "executeCode",
            "description": "Execute Python code for calculations",
            "input_schema": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute"
                    },
                    "description": {
                        "type": "string",
                        "description": "What the code does"
                    }
                },
                "required": ["code"]
            },
            "ui_component": "CodeExecution"
        }
    }
    
    @classmethod
    def get_anthropic_tools(cls) -> List[Dict]:
        """Get tools in Anthropic format."""
        return [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["input_schema"]
            }
            for tool in cls.TOOLS.values()
        ]
    
    @classmethod
    def get_ui_component(cls, tool_name: str) -> Optional[str]:
        """Get the UI component name for a tool."""
        tool = cls.TOOLS.get(tool_name)
        return tool.get("ui_component") if tool else None


def convert_to_ui_message_format(
    anthropic_response: Dict,
    tool_results: Optional[Dict[str, Any]] = None
) -> UIMessage:
    """
    Convert Anthropic response to UI Message format.
    
    Args:
        anthropic_response: Response from Anthropic API
        tool_results: Map of tool_call_id -> result
        
    Returns:
        UIMessage with parts array
    """
    message = UIMessage(
        id=f"msg_{int(time.time() * 1000)}",
        role="assistant",
        createdAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    )
    
    content = anthropic_response.get("content", [])
    
    for block in content:
        if block.get("type") == "text":
            message.add_text(block.get("text", ""))
        
        elif block.get("type") == "tool_use":
            tool_name = block.get("name", "")
            tool_call_id = block.get("id", "")
            tool_input = block.get("input", {})
            
            # Check if we have a result for this tool
            if tool_results and tool_call_id in tool_results:
                result = tool_results[tool_call_id]
                if isinstance(result, Exception):
                    message.add_tool_part(
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        state=ToolState.OUTPUT_ERROR,
                        input_args=tool_input,
                        error=str(result)
                    )
                else:
                    message.add_tool_part(
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        state=ToolState.OUTPUT_AVAILABLE,
                        input_args=tool_input,
                        output=result
                    )
            else:
                # Tool call without result yet
                message.add_tool_part(
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    state=ToolState.INPUT_AVAILABLE,
                    input_args=tool_input
                )
    
    return message