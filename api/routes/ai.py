"""
Vercel AI SDK Compatible API Routes
====================================
Native API endpoints for Vercel AI SDK integration.

These routes are designed to work with:
- useChat() hook from @ai-sdk/react
- useCompletion() hook
- streamUI() from ai/rsc
- Generative UI components

The streaming format follows the AI SDK Data Stream Protocol exactly.
"""

import json
import logging
import time
import asyncio
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from api.dependencies import get_current_user_id, get_user_api_keys
from core.vercel_ai import (
    VercelAIGatewayClient,
    VercelAIStreamProtocol,
    GenerativeUIStream,
    convert_messages_to_anthropic,
    convert_tools_to_anthropic,
    DEFAULT_MODEL
)
from core.tools import get_all_tools, handle_tool_call
from core.artifact_parser import ArtifactParser
from core.prompts import get_base_prompt, get_chat_prompt
from core.ui_message_stream import (
    UIMessageStreamEncoder,
    GenerativeUITools,
    ToolState,
    UIMessage
)
from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["Vercel AI SDK"])


# ============================================================================
# Request/Response Models (matching AI SDK format)
# ============================================================================

class Message(BaseModel):
    """AI SDK message format."""
    role: str = Field(..., description="Message role: user, assistant, system, or tool")
    content: str = Field(..., description="Message content")
    id: Optional[str] = Field(None, description="Message ID")
    name: Optional[str] = Field(None, description="Tool name (for tool messages)")
    tool_call_id: Optional[str] = Field(None, description="Tool call ID (for tool results)")
    toolInvocations: Optional[List[Dict]] = Field(None, description="Tool invocations")


class ChatRequest(BaseModel):
    """
    AI SDK compatible chat request.
    
    This matches the format sent by useChat() hook.
    """
    messages: List[Message] = Field(..., description="Conversation messages")
    model: Optional[str] = Field(None, description="Model to use")
    system: Optional[str] = Field(None, description="System prompt override")
    max_tokens: Optional[int] = Field(4096, description="Maximum tokens")
    temperature: Optional[float] = Field(None, description="Temperature (not used by Anthropic)")
    tools: Optional[List[Dict]] = Field(None, description="Tool definitions")
    tool_choice: Optional[str] = Field(None, description="Tool choice mode")
    
    # Custom fields for this app
    conversation_id: Optional[str] = Field(None, description="Conversation ID for persistence")
    include_kb: Optional[bool] = Field(True, description="Include knowledge base context")
    stream: Optional[bool] = Field(True, description="Enable streaming")


class CompletionRequest(BaseModel):
    """Request for text completion."""
    prompt: str = Field(..., description="Text prompt")
    model: Optional[str] = Field(None, description="Model to use")
    max_tokens: Optional[int] = Field(2048, description="Maximum tokens")
    system: Optional[str] = Field(None, description="System prompt")


class GenerateUIRequest(BaseModel):
    """Request for generative UI generation."""
    prompt: str = Field(..., description="What UI to generate")
    context: Optional[str] = Field(None, description="Additional context")
    component_type: Optional[str] = Field("react", description="Component type: react, html, svg, chart")


# ============================================================================
# Main Chat Endpoint (AI SDK Compatible)
# ============================================================================

@router.post("/chat")
async def chat(
    request: ChatRequest,
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """
    AI SDK compatible streaming chat endpoint.
    
    This endpoint is designed to work directly with the useChat() hook:
    
    ```typescript
    const { messages, input, handleSubmit } = useChat({
        api: '/api/ai/chat',
        // ... other options
    });
    ```
    
    The response follows the AI SDK Data Stream Protocol for proper
    streaming support with tool calls and generative UI.
    """
    db = get_supabase()
    
    if not api_keys.get("claude"):
        raise HTTPException(
            status_code=400, 
            detail="Claude API key not configured. Please add your API key in Profile Settings."
        )
    
    # Handle conversation persistence
    conversation_id = request.conversation_id
    if not conversation_id and request.messages:
        # Create new conversation from first user message
        first_user_msg = next(
            (m for m in request.messages if m.role == "user"),
            None
        )
        if first_user_msg:
            title = first_user_msg.content[:50] + "..." if len(first_user_msg.content) > 50 else first_user_msg.content
            conv_result = db.table("conversations").insert({
                "user_id": user_id,
                "title": title,
                "conversation_type": "ai_sdk",
            }).execute()
            conversation_id = conv_result.data[0]["id"]
    
    # Save user message if conversation exists
    if conversation_id and request.messages:
        last_user_msg = next(
            (m for m in reversed(request.messages) if m.role == "user"),
            None
        )
        if last_user_msg:
            db.table("messages").insert({
                "conversation_id": conversation_id,
                "role": "user",
                "content": last_user_msg.content,
            }).execute()
    
    # Build system prompt
    system_prompt = request.system or _build_system_prompt(
        db, user_id, request.include_kb, 
        request.messages[-1].content if request.messages else ""
    )
    
    # Convert messages to Anthropic format
    anthropic_messages = convert_messages_to_anthropic(
        [m.model_dump() for m in request.messages]
    )
    
    # Get tools
    tools = request.tools
    if tools:
        tools = convert_tools_to_anthropic(tools)
    else:
        tools = get_all_tools()
    
    if request.stream:
        # Streaming response
        return StreamingResponse(
            _stream_chat_response(
                api_key=api_keys["claude"],
                model=request.model or DEFAULT_MODEL,
                messages=anthropic_messages,
                system=system_prompt,
                tools=tools,
                max_tokens=request.max_tokens,
                conversation_id=conversation_id,
                db=db,
                user_id=user_id
            ),
            media_type="text/plain; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Vercel-AI-Data-Stream": "v1",
                "X-Conversation-Id": conversation_id or "",
                "Access-Control-Expose-Headers": "X-Conversation-Id, X-Vercel-AI-Data-Stream"
            }
        )
    else:
        # Non-streaming response
        return await _generate_chat_response(
            api_key=api_keys["claude"],
            model=request.model or DEFAULT_MODEL,
            messages=anthropic_messages,
            system=system_prompt,
            tools=tools,
            max_tokens=request.max_tokens,
            conversation_id=conversation_id,
            db=db
        )


async def _stream_chat_response(
    api_key: str,
    model: str,
    messages: List[Dict],
    system: str,
    tools: List[Dict],
    max_tokens: int,
    conversation_id: Optional[str],
    db,
    user_id: str
):
    """
    Stream chat response with proper AI SDK protocol.
    
    Handles:
    - Text streaming
    - Tool calls and results
    - Artifact detection and streaming
    - Multi-step tool use (Claude continues after tool results)
    """
    protocol = VercelAIStreamProtocol()
    ui_stream = GenerativeUIStream()
    
    accumulated_text = ""
    all_tool_calls = []
    message_id = f"msg_{int(time.time() * 1000)}"
    
    try:
        client = VercelAIGatewayClient(api_key=api_key, model=model)
        
        # Tool handler function
        async def handle_tool(tool_id: str, tool_name: str, args: Dict) -> str:
            """Handle tool execution and return result."""
            result = handle_tool_call(
                tool_name=tool_name,
                tool_input=args,
                supabase_client=db,
                api_key=api_key
            )
            all_tool_calls.append({
                "id": tool_id,
                "name": tool_name,
                "args": args,
                "result": result
            })
            return result
        
        # Stream the response
        current_messages = messages.copy()
        max_iterations = 5  # Limit tool use iterations
        
        for iteration in range(max_iterations):
            has_tool_calls = False
            iteration_text = ""
            tool_results = []
            
            async for chunk in client.stream_chat(
                messages=current_messages,
                system=system,
                tools=tools,
                max_tokens=max_tokens,
                tool_handler=handle_tool
            ):
                yield chunk
                
                # Track if we got tool calls in this iteration
                if '"toolCallId"' in chunk and '"toolName"' in chunk:
                    has_tool_calls = True
                
                # Extract text from chunks for artifact detection
                if chunk.startswith("0:"):
                    try:
                        text = json.loads(chunk[2:].strip())
                        iteration_text += text
                        accumulated_text += text
                    except:
                        pass
            
            # If no tool calls, we're done
            if not has_tool_calls:
                break
            
            # Add assistant message with tool calls to conversation
            assistant_content = []
            if iteration_text:
                assistant_content.append({"type": "text", "text": iteration_text})
            
            for tc in all_tool_calls[len(all_tool_calls) - 1:]:  # Only new tool calls
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["args"]
                })
            
            current_messages.append({
                "role": "assistant",
                "content": assistant_content
            })
            
            # Add tool results
            for tc in all_tool_calls[len(all_tool_calls) - 1:]:
                current_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": tc["result"]
                    }]
                })
        
        # Detect and stream artifacts from accumulated text
        artifacts = ArtifactParser.extract_artifacts(accumulated_text)
        
        for artifact in artifacts:
            artifact_type = artifact.get('type', 'code')
            code = artifact.get('code', '')
            language = artifact.get('language', artifact_type)
            
            if artifact_type == 'react' or language in ['jsx', 'tsx', 'react']:
                yield ui_stream.react_component(
                    code=code,
                    component_name=artifact.get('id', 'Component'),
                    artifact_id=artifact.get('id')
                )
            elif artifact_type == 'mermaid' or language == 'mermaid':
                yield ui_stream.mermaid_diagram(code=code)
            elif artifact_type in ['html', 'svg']:
                yield ui_stream.code_artifact(
                    code=code,
                    language=artifact_type,
                    artifact_id=artifact.get('id')
                )
            else:
                # Generic code artifact
                yield ui_stream.code_artifact(
                    code=code,
                    language=language,
                    artifact_id=artifact.get('id')
                )
        
        # Send custom data with conversation info
        yield protocol.data([{
            "type": "metadata",
            "conversationId": conversation_id,
            "messageId": message_id,
            "toolsUsed": [tc["name"] for tc in all_tool_calls],
            "hasArtifacts": len(artifacts) > 0
        }])
        
        # Save assistant message
        if conversation_id and accumulated_text:
            db.table("messages").insert({
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": accumulated_text,
                "metadata": {
                    "message_id": message_id,
                    "tools_used": [tc["name"] for tc in all_tool_calls],
                    "artifacts": [{"id": a["id"], "type": a["type"]} for a in artifacts]
                }
            }).execute()
            
            # Update conversation timestamp
            db.table("conversations").update({
                "updated_at": "now()"
            }).eq("id", conversation_id).execute()
        
        await client.close()
        
    except Exception as e:
        logger.error(f"Stream error: {e}", exc_info=True)
        yield protocol.error(str(e))


async def _generate_chat_response(
    api_key: str,
    model: str,
    messages: List[Dict],
    system: str,
    tools: List[Dict],
    max_tokens: int,
    conversation_id: Optional[str],
    db
) -> JSONResponse:
    """Non-streaming chat response."""
    
    try:
        client = VercelAIGatewayClient(api_key=api_key, model=model)
        
        response = await client.generate(
            messages=messages,
            system=system,
            tools=tools,
            max_tokens=max_tokens
        )
        
        # Handle tool calls
        if response.get("tool_calls"):
            tool_results = []
            for tc in response["tool_calls"]:
                result = handle_tool_call(
                    tool_name=tc["name"],
                    tool_input=tc["args"],
                    supabase_client=db,
                    api_key=api_key
                )
                tool_results.append({
                    "tool_call_id": tc["id"],
                    "result": result
                })
            
            # Make follow-up call with tool results
            messages.append({
                "role": "assistant",
                "content": [
                    {"type": "text", "text": response["text"]} if response["text"] else None,
                    *[{
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": tc["args"]
                    } for tc in response["tool_calls"]]
                ]
            })
            
            messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tr["tool_call_id"],
                    "content": tr["result"]
                } for tr in tool_results]
            })
            
            response = await client.generate(
                messages=messages,
                system=system,
                max_tokens=max_tokens
            )
        
        # Detect artifacts
        artifacts = ArtifactParser.extract_artifacts(response["text"])
        
        # Save to database
        if conversation_id:
            db.table("messages").insert({
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": response["text"],
                "metadata": {
                    "artifacts": artifacts
                }
            }).execute()
        
        await client.close()
        
        return JSONResponse({
            "id": f"msg_{int(time.time() * 1000)}",
            "role": "assistant",
            "content": response["text"],
            "artifacts": artifacts,
            "usage": response["usage"],
            "conversation_id": conversation_id
        })
        
    except Exception as e:
        logger.error(f"Generate error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Completion Endpoint
# ============================================================================

@router.post("/completion")
async def completion(
    request: CompletionRequest,
    api_keys: dict = Depends(get_user_api_keys),
):
    """
    Text completion endpoint for useCompletion() hook.
    
    ```typescript
    const { completion, input, handleSubmit } = useCompletion({
        api: '/api/ai/completion',
    });
    ```
    """
    if not api_keys.get("claude"):
        raise HTTPException(status_code=400, detail="Claude API key not configured")
    
    protocol = VercelAIStreamProtocol()
    
    async def stream_completion():
        try:
            client = VercelAIGatewayClient(
                api_key=api_keys["claude"],
                model=request.model or DEFAULT_MODEL
            )
            
            messages = [{"role": "user", "content": request.prompt}]
            
            async for chunk in client.stream_chat(
                messages=messages,
                system=request.system or "",
                max_tokens=request.max_tokens
            ):
                yield chunk
            
            await client.close()
            
        except Exception as e:
            yield protocol.error(str(e))
    
    return StreamingResponse(
        stream_completion(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Vercel-AI-Data-Stream": "v1"
        }
    )


# ============================================================================
# Generative UI Endpoint
# ============================================================================

@router.post("/generate-ui")
async def generate_ui(
    request: GenerateUIRequest,
    api_keys: dict = Depends(get_user_api_keys),
):
    """
    Generate UI components on demand.
    
    This endpoint generates React components, charts, diagrams, etc.
    based on natural language prompts.
    
    Useful for:
    - Creating visualizations
    - Building interactive components
    - Generating charts from data
    - Creating diagrams
    """
    if not api_keys.get("claude"):
        raise HTTPException(status_code=400, detail="Claude API key not configured")
    
    protocol = VercelAIStreamProtocol()
    ui_stream = GenerativeUIStream()
    
    # Build prompt based on component type
    component_prompts = {
        "react": """Generate a React component using:
- React hooks (useState, useEffect, etc.)
- Tailwind CSS for styling
- Modern React patterns
- TypeScript-compatible code

The component should be self-contained and ready to render.
Export it as 'default function Component()' or 'export default function ComponentName()'.
""",
        "chart": """Generate a chart visualization using:
- Recharts library components
- Responsive design
- Clear data labels
- Professional styling

Return a complete React component that renders the chart.
""",
        "html": """Generate clean, semantic HTML with:
- Inline or Tailwind CSS styling
- Accessible markup
- Modern HTML5 elements
""",
        "svg": """Generate an SVG graphic with:
- Clean vector paths
- Appropriate viewBox
- Accessible title/desc elements
""",
        "mermaid": """Generate a Mermaid diagram with:
- Clear node labels
- Logical flow
- Appropriate diagram type (flowchart, sequence, etc.)
"""
    }
    
    system_prompt = f"""You are a UI/UX expert that generates clean, professional UI components.

{component_prompts.get(request.component_type, component_prompts['react'])}

Context: {request.context or 'General purpose component'}

IMPORTANT: 
- Output ONLY the code, wrapped in appropriate code blocks
- No explanations before or after
- The code must be complete and runnable
"""
    
    async def stream_ui_generation():
        accumulated_code = ""
        
        try:
            client = VercelAIGatewayClient(
                api_key=api_keys["claude"],
                model=DEFAULT_MODEL
            )
            
            messages = [{"role": "user", "content": request.prompt}]
            
            async for chunk in client.stream_chat(
                messages=messages,
                system=system_prompt,
                max_tokens=4096
            ):
                yield chunk
                
                # Accumulate text for artifact detection
                if chunk.startswith("0:"):
                    try:
                        text = json.loads(chunk[2:].strip())
                        accumulated_code += text
                    except:
                        pass
            
            # Extract and stream the generated component
            artifacts = ArtifactParser.extract_artifacts(accumulated_code)
            
            for artifact in artifacts:
                if request.component_type == "react":
                    yield ui_stream.react_component(
                        code=artifact.get('code', ''),
                        component_name="GeneratedComponent"
                    )
                elif request.component_type == "mermaid":
                    yield ui_stream.mermaid_diagram(artifact.get('code', ''))
                else:
                    yield ui_stream.code_artifact(
                        code=artifact.get('code', ''),
                        language=request.component_type
                    )
            
            await client.close()
            
        except Exception as e:
            yield protocol.error(str(e))
    
    return StreamingResponse(
        stream_ui_generation(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Vercel-AI-Data-Stream": "v1"
        }
    )


# ============================================================================
# Tool Definitions Endpoint
# ============================================================================

@router.get("/tools")
async def list_tools():
    """
    List available tools for the AI.
    
    Returns tools in AI SDK format for client-side tool registration.
    """
    tools = get_all_tools()
    
    # Convert to AI SDK format
    sdk_tools = []
    for tool in tools:
        if "input_schema" in tool:
            sdk_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool["input_schema"]
                }
            })
        else:
            # Built-in tool
            sdk_tools.append({
                "type": tool.get("type", "unknown"),
                "name": tool.get("name", "")
            })
    
    return {"tools": sdk_tools}


# ============================================================================
# Helper Functions
# ============================================================================

def _build_system_prompt(
    db,
    user_id: str,
    include_kb: bool,
    user_message: str
) -> str:
    """Build the system prompt with optional KB context."""
    
    base_prompt = f"""{get_base_prompt()}

{get_chat_prompt()}

## Capabilities
You have access to powerful tools:
- **Web Search**: Search the internet for current information
- **Stock Data**: Real-time and historical market data
- **Knowledge Base**: User's uploaded documents and trading knowledge
- **AFL Tools**: Generate, debug, validate, and explain AFL code
- **Python Execution**: Run calculations and data analysis

## Generative UI
When helpful, you can generate:
- **React Components**: Interactive UI elements
- **Charts**: Data visualizations using Recharts
- **Mermaid Diagrams**: Flowcharts, sequence diagrams, etc.
- **Code Artifacts**: Syntax-highlighted code blocks

Always wrap generated code in appropriate markdown code blocks with language tags.
"""
    
    # Add KB context if enabled
    if include_kb:
        kb_context = _get_kb_context(db, user_message)
        if kb_context:
            base_prompt += f"\n\n## User's Knowledge Base\n{kb_context}"
    
    return base_prompt


def _get_kb_context(db, query: str, limit: int = 3) -> str:
    """Get relevant KB context for the query."""
    try:
        # Search for relevant documents
        keywords = query.lower().split()[:5]
        
        result = db.table("brain_documents").select(
            "title, summary, raw_content"
        ).limit(limit).execute()
        
        if not result.data:
            return ""
        
        snippets = []
        for doc in result.data:
            title = doc.get("title", "Untitled")
            summary = doc.get("summary") or doc.get("raw_content", "")[:200]
            snippets.append(f"- **{title}**: {summary[:150]}...")
        
        return "\n".join(snippets)
        
    except Exception as e:
        logger.warning(f"KB context error: {e}")
        return ""
