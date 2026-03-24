"""Chat/Agent routes with conversation history and Claude tools."""

import io
import json
import re
import asyncio
import traceback
from typing import Optional, Dict, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import anthropic
from anthropic import APIError, RateLimitError

from api.dependencies import get_current_user_id, get_user_api_keys
from core.claude_engine import ClaudeAFLEngine
from core.prompts import get_base_prompt, get_chat_prompt
from core.tools import get_all_tools, handle_tool_call
from core.artifact_parser import ArtifactParser
from core.streaming import VercelAIStreamEncoder, GenerativeUIStreamBuilder
from db.supabase_client import get_supabase

router = APIRouter(prefix="/chat", tags=["Chat"])

# ---------------------------------------------------------------------------
# Model configuration and capabilities
# ---------------------------------------------------------------------------

# Model capability matrix - update as new models are released
MODEL_CAPABILITIES = {
    # Claude 4.6 models
    "claude-opus-4-6": {
        "max_output_tokens": 128000,
        "context_window": 1000000,
        "supports_adaptive_thinking": True,
        "supports_prompt_caching": True,
        "default_top_p": 0.99,
    },
    "claude-sonnet-4-6": {
        "max_output_tokens": 64000,
        "context_window": 1000000,
        "supports_adaptive_thinking": True,
        "supports_prompt_caching": True,
        "default_top_p": 0.99,
    },
    # Claude 4.5 models
    "claude-opus-4-5": {
        "max_output_tokens": 16384,
        "context_window": 200000,
        "supports_adaptive_thinking": False,
        "supports_prompt_caching": True,
        "default_top_p": 0.99,
    },
    "claude-sonnet-4-5": {
        "max_output_tokens": 8192,
        "context_window": 200000,
        "supports_adaptive_thinking": False,
        "supports_prompt_caching": True,
        "default_top_p": 0.99,
    },
}

# Pinned model snapshots for production stability
RECOMMENDED_MODEL_SNAPSHOTS = {
    "claude-opus-4-6": "claude-opus-4-6-20250202",
    "claude-sonnet-4-6": "claude-sonnet-4-6-20250202",
    "claude-opus-4-5": "claude-opus-4-5-20241022",
    "claude-sonnet-4-5": "claude-sonnet-4-5-20241022",
}

def get_model_config(model: str) -> Dict:
    """Get configuration for a specific model with safe defaults."""
    # Strip snapshot suffix if present
    base_model = model.rsplit("-", 1)[0] if model.count("-") > 3 else model

    return MODEL_CAPABILITIES.get(base_model, {
        "max_output_tokens": 16384,  # Safe default
        "context_window": 200000,
        "supports_adaptive_thinking": False,
        "supports_prompt_caching": False,
        "default_top_p": 0.99,
    })

def get_pinned_model(model: str) -> str:
    """Get the recommended pinned snapshot for a model alias."""
    return RECOMMENDED_MODEL_SNAPSHOTS.get(model, model)

# ---------------------------------------------------------------------------
# ClaudeAFLEngine singleton — avoids creating a new HTTP client per request
# ---------------------------------------------------------------------------
_engine_cache: dict[str, ClaudeAFLEngine] = {}


def _get_engine(api_key: str) -> ClaudeAFLEngine:
    if api_key not in _engine_cache:
        _engine_cache[api_key] = ClaudeAFLEngine(api_key=api_key)
    return _engine_cache[api_key]


# ---------------------------------------------------------------------------
# Default titles that should be replaced on the first real message
# ---------------------------------------------------------------------------
_DEFAULT_TITLES = {"New Conversation", "AFL Code Chat", "New Chat", "Untitled", ""}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sanitize_title(title: str) -> str:
    """Strip [FORMATTING:...] and similar system instruction tags from titles."""
    if not title:
        return title
    cleaned = re.sub(r'\[FORMATTING:[^]]*\]', '', title, flags=re.IGNORECASE)
    cleaned = re.sub(r'\[SYSTEM:[^\]]*\]', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\[INSTRUCTIONS:[^\]]*\]', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\[CONTEXT:[^\]]*\]', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()
    return cleaned or title


async def _get_or_create_conversation(
    db,
    user_id: str,
    content: str,
    conversation_id: Optional[str],
) -> str:
    """
    Return an existing conversation ID or create a new one.
    Also updates the title if it is still a default placeholder.
    """
    raw_title = sanitize_title(content[:50] + "..." if len(content) > 50 else content)

    if not conversation_id:
        result = db.table("conversations").insert({
            "user_id": user_id,
            "title": raw_title,
            "conversation_type": "agent",
        }).execute()
        return result.data[0]["id"]

    # Existing conversation — update title if still a placeholder
    check = db.table("conversations").select("title").eq("id", conversation_id).execute()
    if check.data:
        current = check.data[0].get("title", "")
        if current in _DEFAULT_TITLES or not current:
            db.table("conversations").update({"title": raw_title}).eq(
                "id", conversation_id
            ).execute()

    return conversation_id


def sanitize_message_history(messages: list) -> list:
    """
    Ensure every tool_use block in an assistant message has a matching
    tool_result in the immediately following user message.

    CRITICAL FIX: Tool results must be placed FIRST in the user message content array,
    before any text content. This follows Claude API requirements.

    When orphaned tool_use blocks are detected, we remove the assistant message
    entirely rather than injecting dummy results, as this is more robust.
    """
    sanitized = []
    i = 0

    while i < len(messages):
        msg = messages[i]

        if msg.get("role") == "assistant":
            content = msg.get("content")
            tool_use_ids = []

            # Collect all tool_use IDs from this assistant message
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_use_ids.append(block.get("id"))

            if tool_use_ids:
                # Check if the next message has corresponding tool_results
                next_msg = messages[i + 1] if i + 1 < len(messages) else None
                next_content = next_msg.get("content") if next_msg else None

                existing_result_ids: set = set()
                if (
                    next_msg
                    and next_msg.get("role") == "user"
                    and isinstance(next_content, list)
                ):
                    for block in next_content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            existing_result_ids.add(block.get("tool_use_id"))

                orphaned = [
                    tid for tid in tool_use_ids
                    if tid and tid not in existing_result_ids
                ]

                if orphaned:
                    # CRITICAL FIX: Remove the orphaned assistant message entirely
                    # This is more robust than injecting dummy results
                    i += 1
                    continue

        sanitized.append(msg)
        i += 1

    return sanitized


def ensure_tool_results_first(content: list) -> list:
    """
    CRITICAL FIX: Ensure tool_result blocks come FIRST in user message content,
    before any text blocks. This is a Claude API requirement.
    """
    if not isinstance(content, list):
        return content

    tool_results = []
    other_content = []

    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            tool_results.append(block)
        else:
            other_content.append(block)

    # Tool results MUST come first
    return tool_results + other_content


async def retry_with_exponential_backoff(
    func,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
):
    """
    Retry a function with exponential backoff for rate limit errors.
    """
    delay = initial_delay
    last_error = None

    for attempt in range(max_retries):
        try:
            return await func()
        except RateLimitError as e:
            last_error = e
            if attempt == max_retries - 1:
                raise

            # Wait with exponential backoff
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)
        except APIError as e:
            # Don't retry on other API errors
            raise

    raise last_error


def estimate_token_count(text: str) -> int:
    """
    Rough token estimation: ~4 characters per token for English text.
    This is approximate but good enough for basic context management.
    """
    return len(text) // 4


def manage_context_window(messages: list, context_limit: int, system_prompt: str) -> list:
    """
    Ensure messages fit within context window by removing oldest messages if needed.
    Keep system prompt and most recent messages.
    """
    system_tokens = estimate_token_count(system_prompt)
    available_tokens = context_limit - system_tokens - 10000  # Reserve 10k for response

    if available_tokens < 0:
        raise ValueError("System prompt too large for context window")

    # Calculate current token usage
    current_tokens = sum(
        estimate_token_count(json.dumps(msg.get("content", "")))
        for msg in messages
    )

    if current_tokens <= available_tokens:
        return messages

    # Remove oldest messages until we fit
    while current_tokens > available_tokens and len(messages) > 2:
        # Always keep at least the last user message
        removed = messages.pop(0)
        current_tokens -= estimate_token_count(json.dumps(removed.get("content", "")))

    return messages


def _build_parts(assistant_content: str, artifacts: list) -> list:
    """Build AI-SDK-style parts array from text + extracted artifacts."""
    parts = []
    last_index = 0

    for artifact in artifacts:
        if artifact["start"] > last_index:
            text = assistant_content[last_index:artifact["start"]].strip()
            if text:
                parts.append({"type": "text", "text": text})

        parts.append({
            "type": f"tool-{artifact['type']}",
            "state": "output-available",
            "output": {
                "code": artifact["code"],
                "language": artifact.get("language", artifact["type"]),
                "id": artifact["id"],
            },
        })
        last_index = artifact["end"]

    if last_index < len(assistant_content):
        remaining = assistant_content[last_index:].strip()
        if remaining:
            parts.append({"type": "text", "text": remaining})

    if not artifacts and assistant_content:
        parts.append({"type": "text", "text": assistant_content})

    return parts


def _build_tool_parts(tools_used: list) -> list:
    """Build tool-invocation parts for Generative UI rehydration."""
    return [
        {
            "type": "tool-invocation",
            "toolCallId": tool["toolCallId"],
            "toolName": tool["tool"],
            "state": "result",
            "result": tool["result"],
        }
        for tool in tools_used
    ]


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class TTSRequest(BaseModel):
    text: str
    voice: str = "en-US-AriaNeural"


class CreateConversationRequest(BaseModel):
    title: Optional[str] = "New Conversation"
    conversation_type: Optional[str] = "agent"


class RenameConversationRequest(BaseModel):
    title: str


class ChatAgentRequest(BaseModel):
    content: str
    conversation_id: Optional[str] = None
    model: Optional[str] = None
    thinking_mode: Optional[str] = None
    thinking_budget: Optional[int] = None
    thinking_effort: Optional[str] = None  # NEW: for Claude 4.6 adaptive thinking
    skill_slug: Optional[str] = None
    use_prompt_caching: bool = True  # NEW: enable prompt caching by default
    max_iterations: int = 5  # NEW: configurable, increased default
    pin_model_version: bool = False  # NEW: option to use pinned snapshots


# ---------------------------------------------------------------------------
# File context helpers (referenced in main endpoint)
# ---------------------------------------------------------------------------

async def _fetch_file_context(db, conversation_id: str) -> str:
    """Fetch file metadata attached to this conversation."""
    files = db.table("files").select("filename, content_snippet").eq(
        "conversation_id", conversation_id
    ).execute()
    if not files.data:
        return ""

    snippets = [
        f"📎 {f['filename']}: {f.get('content_snippet', 'no snippet')[:80]}..."
        for f in files.data
    ]
    return f"\n\n<file_context>\n{chr(10).join(snippets)}\n</file_context>"


async def _fetch_kb_context(db, user_content: str) -> str:
    """Search KB for relevant context based on user message."""
    # Placeholder: implement semantic search if available
    return ""


async def _fetch_kb_doc_refs(db, user_content: str) -> str:
    """Extract [kb-doc: filename] refs and inject full content."""
    matches = re.findall(r'\[kb-doc:\s*([^\]]+)\]', user_content)
    if not matches:
        return ""

    docs = []
    for filename in matches:
        result = db.table("knowledge_base").select("content").eq(
            "filename", filename.strip()
        ).execute()
        if result.data:
            docs.append(f"### {filename}\n{result.data[0]['content'][:2000]}")

    if not docs:
        return ""

    return f"\n\n<kb_doc_context>\n{chr(10).join(docs)}\n</kb_doc_context>"


# ---------------------------------------------------------------------------
# AFL-specific rules and tool list
# ---------------------------------------------------------------------------

_AFL_RULES = """

## AFL Code Rules
- Always use ANSI C++ syntax for AmiBroker
- Use proper AFL functions: MA(), EMA(), RSI(), etc.
- Include proper Buy/Sell/Short/Cover signals
- Add position sizing: SetPositionSize(100, spsPercentOfEquity);
"""

_STREAM_TOOLS_LIST = """

## Available Tools
You have access to: invoke_skill, analyze_backtest, generate_afl_code, and other domain-specific tools.
"""


# ---------------------------------------------------------------------------
# Conversation CRUD Endpoints
# ---------------------------------------------------------------------------

@router.get("/conversations")
async def list_conversations(
    user_id: str = Depends(get_current_user_id),
):
    """List all conversations for the authenticated user, newest first."""
    db = get_supabase()
    result = (
        db.table("conversations")
        .select("id, user_id, title, conversation_type, created_at, updated_at, is_archived, is_pinned, model, metadata")
        .eq("user_id", user_id)
        .eq("is_archived", False)
        .order("updated_at", desc=True)
        .limit(100)
        .execute()
    )
    return result.data or []


@router.post("/conversations")
async def create_conversation(
    data: CreateConversationRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Create a new conversation."""
    db = get_supabase()
    insert_data = {
        "user_id": user_id,
        "title": sanitize_title(data.title or "New Conversation"),
    }
    # Only include conversation_type if the column exists — store in metadata as fallback
    if data.conversation_type:
        insert_data["conversation_type"] = data.conversation_type

    result = db.table("conversations").insert(insert_data).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create conversation")

    return result.data[0]


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get all messages for a conversation. Verifies ownership."""
    db = get_supabase()

    # Verify the conversation belongs to this user
    conv = (
        db.table("conversations")
        .select("id, user_id")
        .eq("id", conversation_id)
        .execute()
    )
    if not conv.data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.data[0]["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    result = (
        db.table("messages")
        .select("id, conversation_id, role, content, created_at, metadata, tool_calls, tool_results")
        .eq("conversation_id", conversation_id)
        .order("created_at")
        .execute()
    )

    # Transform messages to match frontend Message type
    messages = []
    for m in (result.data or []):
        msg = {
            "id": m["id"],
            "conversation_id": m["conversation_id"],
            "role": m["role"],
            "content": m["content"],
            "created_at": m["created_at"],
        }
        if m.get("metadata"):
            msg["metadata"] = m["metadata"]
            # Extract artifacts from metadata for convenience
            if m["metadata"].get("artifacts"):
                msg["artifacts"] = m["metadata"]["artifacts"]
            if m["metadata"].get("tools_used"):
                msg["tools_used"] = m["metadata"]["tools_used"]
        messages.append(msg)

    return messages


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    data: RenameConversationRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Rename a conversation. Verifies ownership."""
    db = get_supabase()

    # Verify ownership
    conv = (
        db.table("conversations")
        .select("id, user_id")
        .eq("id", conversation_id)
        .execute()
    )
    if not conv.data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.data[0]["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    result = (
        db.table("conversations")
        .update({"title": sanitize_title(data.title), "updated_at": "now()"})
        .eq("id", conversation_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to rename conversation")

    return result.data[0]


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a conversation and all its messages (cascade). Verifies ownership."""
    db = get_supabase()

    # Verify ownership
    conv = (
        db.table("conversations")
        .select("id, user_id")
        .eq("id", conversation_id)
        .execute()
    )
    if not conv.data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.data[0]["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Delete conversation — messages are cascade-deleted by FK constraint
    db.table("conversations").delete().eq("id", conversation_id).execute()

    return {"success": True}


# ---------------------------------------------------------------------------
# Main Chat Endpoint
# ---------------------------------------------------------------------------

@router.post("/agent")
async def chat_agent(
    data: ChatAgentRequest,
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
    request: Request = None,
):
    """
    Chat endpoint with full agent capabilities: tool use, streaming, artifacts.

    UPDATED: Now includes all Claude API best practices from 2025:
    - Adaptive thinking for Claude 4.6
    - Prompt caching for cost reduction
    - Context window management for 1M token models
    - Rate limit handling with exponential backoff
    - Per-iteration usage tracking
    - Proper tool result ordering
    - Model version pinning support
    """
    if not api_keys or not api_keys.get("claude"):
        raise HTTPException(status_code=401, detail="Claude API key required")

    db = get_supabase()

    conversation_id = await _get_or_create_conversation(
        db=db,
        user_id=user_id,
        content=data.content,
        conversation_id=data.conversation_id,
    )

    # Persist user message
    db.table("messages").insert({
        "conversation_id": conversation_id,
        "role": "user",
        "content": data.content,
        "metadata": {"parts": [{"type": "text", "text": data.content}]},
    }).execute()

    history_result = db.table("messages").select("role, content").eq(
        "conversation_id", conversation_id
    ).order("created_at").limit(40).execute()  # Increased limit for better context

    history = [
        {"role": m["role"], "content": m["content"]}
        for m in history_result.data[:-1]
    ]

    file_context = await _fetch_file_context(db, conversation_id)
    kb_context = await _fetch_kb_context(db, data.content)
    kb_doc_context = await _fetch_kb_doc_refs(db, data.content)

    async def generate_stream():
        encoder = VercelAIStreamEncoder()
        builder = GenerativeUIStreamBuilder()
        accumulated_content = ""
        tools_used = []
        final_message = None
        total_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }

        try:
            engine = _get_engine(api_keys["claude"])
            client = anthropic.AsyncAnthropic(api_key=api_keys["claude"])

            # Resolve model and get configuration
            from core.claude_engine import ClaudeModel as _CM
            requested_model = _CM.from_string(data.model).value if data.model else engine.model

            # Use pinned version if requested for production stability
            model_to_use = (
                get_pinned_model(requested_model)
                if data.pin_model_version
                else requested_model
            )

            model_config = get_model_config(model_to_use)

            # Build system prompt with optional caching markers
            system_prompt_base = (
                f"{get_base_prompt()}\n\n{get_chat_prompt()}"
                f"{file_context}{kb_context}{kb_doc_context}"
                f"{_AFL_RULES}{_STREAM_TOOLS_LIST}"
            )

            # Force-invoke a specific skill if the user pinned one from the UI
            if data.skill_slug:
                system_prompt_base += (
                    f"\n\n## FORCED SKILL INVOCATION\n"
                    f"The user has explicitly selected the '{data.skill_slug}' skill for this message. "
                    f"You MUST immediately call the `invoke_skill` tool with "
                    f"skill_slug='{data.skill_slug}' as your very first action. "
                    f"Do not write any introductory text before invoking the skill. "
                    f"Pass the user's full message as the `prompt` argument to the skill."
                )

            # NEW: Use system blocks with prompt caching for Claude 4.6+
            if data.use_prompt_caching and model_config["supports_prompt_caching"]:
                system_prompt = [
                    {
                        "type": "text",
                        "text": system_prompt_base,
                        "cache_control": {"type": "ephemeral"}  # Cache this stable content
                    }
                ]
            else:
                system_prompt = system_prompt_base

            # Sanitize and manage context window
            messages = sanitize_message_history(
                history + [{"role": "user", "content": data.content}]
            )
            messages = manage_context_window(
                messages,
                model_config["context_window"],
                system_prompt_base
            )

            tools = get_all_tools()

            # NEW: Configurable iteration limit with increased default
            max_iterations = data.max_iterations
            iteration = 0

            # NEW: Build thinking configuration based on model capabilities
            thinking_params = {}
            if data.thinking_mode:
                if model_config["supports_adaptive_thinking"] and data.thinking_effort:
                    # Claude 4.6: Use adaptive thinking with effort parameter
                    thinking_params = {
                        "thinking": {
                            "type": "adaptive",
                            "effort": data.thinking_effort  # "low", "medium", or "high"
                        }
                    }
                elif data.thinking_mode.lower() == "enabled":
                    # Older models: Use budget-based thinking if still supported
                    if data.thinking_budget:
                        thinking_params = {
                            "thinking": {
                                "type": "enabled",
                                "budget_tokens": data.thinking_budget
                            }
                        }

            while iteration < max_iterations:
                iteration += 1
                tool_results_for_next_call = []
                assistant_content_blocks = []
                pending_tool_calls = []
                iteration_start_time = datetime.now()

                # Build API request parameters
                api_params = {
                    "model": model_to_use,
                    "max_tokens": min(
                        model_config["max_output_tokens"],
                        16384  # Reasonable default that works across models
                    ),
                    "system": system_prompt,
                    "messages": messages,
                    "tools": tools,
                    "top_p": model_config["default_top_p"],  # NEW: Explicit top_p
                    **thinking_params,  # Include thinking config if set
                }

                # Wrap API call with retry logic for rate limits
                async def make_api_call():
                    return client.messages.stream(**api_params)

                stream_context = await retry_with_exponential_backoff(make_api_call)

                async with stream_context as stream:
                    async for event in stream:
                        if event.type == "content_block_start":
                            if (
                                hasattr(event.content_block, "type")
                                and event.content_block.type == "tool_use"
                            ):
                                pending_tool_calls.append({
                                    "id": event.content_block.id,
                                    "name": event.content_block.name,
                                    "input": "",
                                })

                        elif event.type == "content_block_delta":
                            if hasattr(event.delta, "type"):
                                if event.delta.type == "text_delta":
                                    text = event.delta.text
                                    accumulated_content += text
                                    yield encoder.encode_text(text)

                                elif event.delta.type == "input_json_delta":
                                    if pending_tool_calls:
                                        pending_tool_calls[-1]["input"] += event.delta.partial_json

                        elif event.type == "content_block_stop":
                            if pending_tool_calls and pending_tool_calls[-1].get("input"):
                                tool_call = pending_tool_calls[-1]

                                try:
                                    tool_input = json.loads(tool_call["input"]) if tool_call["input"] else {}
                                except json.JSONDecodeError:
                                    tool_input = {}

                                tool_call_id = tool_call["id"]
                                tool_name = tool_call["name"]

                                yield encoder.encode_tool_call(tool_call_id, tool_name, tool_input)

                                if tool_name == "invoke_skill":
                                    _SKILL_LABELS = {
                                        "potomac-pptx":            "Creating PowerPoint presentation…",
                                        "potomac-pptx-skill":      "Creating PowerPoint presentation…",
                                        "potomac-docx-skill":      "Creating Word document…",
                                        "potomac-xlsx":            "Creating Excel spreadsheet…",
                                        "dcf-model":               "Building DCF model…",
                                        "doc-interpreter":         "Reading document…",
                                        "amibroker-afl-developer": "Generating AFL code…",
                                        "backtest-expert":         "Running backtest analysis…",
                                        "quant-analyst":           "Running quant analysis…",
                                        "us-market-bubble-detector": "Analysing bubble risk…",
                                    }
                                    _slug = tool_input.get("skill_slug", "")
                                    _label = _SKILL_LABELS.get(_slug, f"Running {_slug} skill…")
                                    yield encoder.encode_data({"skill_status": _label, "skill_slug": _slug})

                                # CRITICAL FIX: Don't skip web_search - handle it properly
                                # If you don't have the tool handler, return an error result
                                try:
                                    result = await asyncio.to_thread(
                                        handle_tool_call,
                                        tool_name=tool_name,
                                        tool_input=tool_input,
                                        supabase_client=db,
                                        api_key=api_keys.get("claude"),
                                    )
                                except Exception as tool_error:
                                    result = json.dumps({"error": str(tool_error)})

                                try:
                                    result_data = json.loads(result) if isinstance(result, str) else result
                                except (json.JSONDecodeError, TypeError):
                                    result_data = {"raw": str(result)}

                                tools_used.append({
                                    "tool": tool_name,
                                    "toolCallId": tool_call_id,
                                    "input": tool_input,
                                    "result": result_data,
                                    "skill_slug": result_data.get("skill", tool_input.get("skill_slug", "")) if tool_name == "invoke_skill" else "",
                                    "skill_name": result_data.get("skill_name", "") if tool_name == "invoke_skill" else "",
                                })

                                yield encoder.encode_tool_result(tool_call_id, result)

                                # Emit a file_download event so the frontend can render
                                # a download button immediately without waiting for the
                                # full response to complete.
                                if isinstance(result_data, dict) and result_data.get("download_url"):
                                    dl_url = result_data["download_url"]
                                    file_id = (
                                        result_data.get("presentation_id")
                                        or result_data.get("document_id")
                                        or ""
                                    )
                                    if file_id:
                                        dl_url = f"/files/{file_id}/download"
                                    yield encoder.encode_file_download(
                                        file_id=file_id,
                                        filename=result_data.get("filename", "download"),
                                        download_url=dl_url,
                                        file_type=(
                                            result_data.get("filename", "").rsplit(".", 1)[-1]
                                            if result_data.get("filename") else "unknown"
                                        ),
                                        size_kb=result_data.get("file_size_kb", 0),
                                        tool_name=tool_name,
                                    )

                                # CRITICAL FIX: Build tool_result with proper structure
                                tool_results_for_next_call.append({
                                    "type": "tool_result",
                                    "tool_use_id": tool_call_id,
                                    "content": result,
                                })

                                assistant_content_blocks.append({
                                    "type": "tool_use",
                                    "id": tool_call_id,
                                    "name": tool_name,
                                    "input": tool_input,
                                })

                                pending_tool_calls.pop()

                    final_message = await stream.get_final_message()

                # NEW: Track per-iteration usage
                if final_message and hasattr(final_message, 'usage'):
                    iteration_usage = {
                        "input_tokens": final_message.usage.input_tokens,
                        "output_tokens": final_message.usage.output_tokens,
                        "cache_creation_input_tokens": getattr(final_message.usage, 'cache_creation_input_tokens', 0),
                        "cache_read_input_tokens": getattr(final_message.usage, 'cache_read_input_tokens', 0),
                    }

                    # Accumulate total usage
                    for key in total_usage:
                        total_usage[key] += iteration_usage.get(key, 0)

                    # Log per-iteration metrics for debugging
                    iteration_duration = (datetime.now() - iteration_start_time).total_seconds()
                    print(f"Iteration {iteration}: {iteration_duration:.2f}s, tokens: {iteration_usage}")

                # Continue if there are tool calls to process
                if final_message.stop_reason == "tool_use" and tool_results_for_next_call:
                    messages.append({"role": "assistant", "content": final_message.content})

                    # CRITICAL FIX: Ensure tool results are ordered correctly
                    # Tool results MUST come first in the content array
                    user_message_content = ensure_tool_results_first(tool_results_for_next_call)
                    messages.append({"role": "user", "content": user_message_content})
                else:
                    break

            # ── Artifact detection & Generative UI streaming ──────────────
            artifacts = ArtifactParser.extract_artifacts(accumulated_content)

            for artifact in artifacts:
                artifact_type = artifact.get("type", "code")
                code = artifact.get("code", "")
                language = artifact.get("language", artifact_type)
                artifact_id = artifact.get("id", f"artifact_{hash(code) % 10_000}")

                yield builder.add_generative_ui_component(
                    component_type=artifact_type,
                    code=code,
                    language=language,
                    component_id=artifact_id,
                )

            # ── Persist assistant message ─────────────────────────────────
            parts = _build_parts(accumulated_content, artifacts)
            tool_parts = _build_tool_parts(tools_used)
            all_parts = tool_parts + parts

            if accumulated_content or tools_used:
                db.table("messages").insert({
                    "conversation_id": conversation_id,
                    "role": "assistant",
                    "content": accumulated_content or "(Tool results returned)",
                    "metadata": {
                        "parts": all_parts,
                        "artifacts": artifacts,
                        "has_artifacts": len(artifacts) > 0,
                        "tools_used": tools_used,
                        "usage": total_usage,  # NEW: Include full usage tracking
                        "model": model_to_use,  # NEW: Track which model was used
                        "iterations": iteration,  # NEW: Track iteration count
                    },
                }).execute()

            db.table("conversations").update({"updated_at": "now()"}).eq(
                "id", conversation_id
            ).execute()

            # NEW: Enhanced usage reporting with caching metrics
            usage = {
                "promptTokens": total_usage["input_tokens"],
                "completionTokens": total_usage["output_tokens"],
                "cacheCreationTokens": total_usage["cache_creation_input_tokens"],
                "cacheReadTokens": total_usage["cache_read_input_tokens"],
            }

            yield encoder.encode_data({
                "conversation_id": conversation_id,
                "tools_used": tools_used,
                "has_artifacts": len(artifacts) > 0,
                "model_used": model_to_use,
                "iterations": iteration,
            })

            yield encoder.encode_finish_message("stop", usage)

        except RateLimitError as e:
            error_msg = f"Rate limit exceeded: {str(e)}\n\nPlease wait a moment and try again."
            yield encoder.encode_text(f"\n\n{error_msg}")
            yield encoder.encode_error(error_msg)
            yield encoder.encode_finish_message("error")
        except Exception as e:
            error_msg = f"{str(e)}\n{traceback.format_exc()[:500]}"
            yield encoder.encode_text(f"\n\nError: {str(e)}")
            yield encoder.encode_error(error_msg)
            yield encoder.encode_finish_message("error")

    return StreamingResponse(
        generate_stream(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/plain; charset=utf-8",
            "X-Conversation-Id": conversation_id,
            "Access-Control-Expose-Headers": "X-Conversation-Id",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ---------------------------------------------------------------------------
# TTS endpoints
# ---------------------------------------------------------------------------

@router.post("/tts")
async def text_to_speech(
    data: TTSRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Convert text to speech using edge-tts (Microsoft Edge TTS).
    Returns an MP3 audio stream. No API key required.
    """
    if not data.text or not data.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")

    text = data.text[:5000]
    text = re.sub(r'```[\s\S]*?```', ' code block omitted ', text)
    text = re.sub(r'`[^`]+`', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'[#*_~>|]', '', text)
    text = re.sub(r'\n{2,}', '. ', text)
    text = re.sub(r'\n', ' ', text)
    text = text.strip()

    if not text:
        raise HTTPException(status_code=400, detail="No speakable text after processing")

    try:
        import edge_tts

        communicate = edge_tts.Communicate(text, data.voice)
        audio_buffer = io.BytesIO()

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buffer.write(chunk["data"])

        audio_buffer.seek(0)

        return StreamingResponse(
            audio_buffer,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=tts.mp3",
                "Access-Control-Allow-Origin": "*",
            },
        )

    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="edge-tts not installed. Run: pip install edge-tts",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS failed: {str(e)}")


@router.get("/tts/voices")
async def list_tts_voices():
    """List available TTS voices (English only)."""
    try:
        import edge_tts
        voices = await edge_tts.list_voices()
        english = [
            {"name": v["ShortName"], "gender": v["Gender"], "locale": v["Locale"]}
            for v in voices if v["Locale"].startswith("en-")
        ]
        return {"voices": english, "count": len(english)}
    except ImportError:
        return {
            "voices": [
                {"name": "en-US-AriaNeural", "gender": "Female", "locale": "en-US"},
                {"name": "en-US-GuyNeural", "gender": "Male", "locale": "en-US"},
                {"name": "en-US-JennyNeural", "gender": "Female", "locale": "en-US"},
                {"name": "en-GB-SoniaNeural", "gender": "Female", "locale": "en-GB"},
            ],
            "count": 4,
            "note": "edge-tts not installed, showing defaults",
        }