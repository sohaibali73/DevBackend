"""Chat/Agent routes with conversation history and Claude tools."""

import io
import json
import re
import asyncio
import traceback
from typing import Optional, Dict, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Request, UploadFile, File, Form
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
    "claude-opus-4-6": "claude-opus-4-6",
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-opus-4-5": "claude-opus-4-5-20251101",
    "claude-sonnet-4-5": "claude-sonnet-4-5-20250929",
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
    """
    Fetch file context for this conversation:
    1. User-uploaded files (via conversation_files junction table)
    2. Previously generated files (via tool_results table) — enables session
       memory so the LLM can revise/edit documents without regenerating them.

    CRITICAL: The file_id UUID MUST be included so the LLM passes the correct
    UUID to tools (analyze_xlsx, transform_xlsx, revise_pptx, etc.).
    Without the UUID the LLM uses the filename, causing 'File not found' errors.
    """
    snippets = []
    _TOOL_FILE_NAMES = {
        "generate_pptx":  "PowerPoint",
        "generate_docx":  "Word doc",
        "generate_xlsx":  "Excel workbook",
        "analyze_pptx":   "analyzed PPTX",
        "revise_pptx":    "revised PPTX",
        "transform_xlsx": "transformed XLSX",
        "analyze_xlsx":   "analyzed XLSX",
    }

    # ── 1. User-uploaded files ─────────────────────────────────────────────
    try:
        conv_files = db.table("conversation_files").select(
            "file_id, file_uploads(id, original_filename, extracted_text, content_type, file_size)"
        ).eq("conversation_id", conversation_id).execute()

        for cf in (conv_files.data or []):
            fu = cf.get("file_uploads")
            if not fu:
                continue
            fid          = cf.get("file_id") or fu.get("id", "")
            fname        = fu.get("original_filename", "unknown")
            content_type = fu.get("content_type", "")
            size_kb      = round((fu.get("file_size") or 0) / 1024, 1)
            snippet      = (fu.get("extracted_text") or "")[:200]
            line = f'📎 UPLOADED: "{fname}" | file_id: {fid} | type: {content_type} | size: {size_kb} KB'
            if snippet:
                line += f'\n   Preview: {snippet}...'
            snippets.append(line)
    except Exception:
        pass

    # ── 2. Previously generated files (session memory) ────────────────────
    # Query tool_results for any file-generating tools run in this conversation.
    # This gives the LLM the file_id so it can make targeted edits (revise_pptx,
    # transform_xlsx, etc.) without regenerating the entire document.
    try:
        gen_results = db.table("tool_results").select(
            "tool_name, output, created_at"
        ).eq("conversation_id", conversation_id).in_(
            "tool_name", list(_TOOL_FILE_NAMES.keys())
        ).order("created_at", desc=False).limit(20).execute()

        for tr in (gen_results.data or []):
            output   = tr.get("output") or {}
            if isinstance(output, str):
                import json as _json
                try:
                    output = _json.loads(output)
                except Exception:
                    continue
            fid      = output.get("file_id") or output.get("presentation_id") or output.get("document_id")
            fname    = output.get("filename", "")
            tool     = tr.get("tool_name", "")
            label    = _TOOL_FILE_NAMES.get(tool, tool)
            if not fid or not fname:
                continue
            size_kb  = output.get("size_kb", 0)
            snippets.append(
                f'📄 GENERATED ({label}): "{fname}" | file_id: {fid} | size: {size_kb} KB'
                f'\n   To edit: use revise_pptx / transform_xlsx / analyze_pptx with this file_id'
            )
    except Exception:
        pass

    if not snippets:
        return ""

    header = (
        "Files available in this conversation. "
        "ALWAYS pass the exact file_id UUID to tools — NEVER use the filename. "
        "To edit a previously generated file use revise_pptx (PPTX), "
        "transform_xlsx (XLSX), or generate_docx with table_from_xlsx sections (DOCX)."
    )
    return (
        f"\n\n<file_context>\n{header}\n\n"
        f"{chr(10).join(snippets)}\n</file_context>"
    )


async def _fetch_kb_context(db, user_content: str) -> str:
    """Search KB for relevant context based on user message."""
    # Placeholder: implement semantic search if available
    return ""


async def _fetch_kb_doc_refs(db, user_content: str) -> str:
    """Extract [kb-doc: filename] refs and inject full content from brain_documents."""
    try:
        matches = re.findall(r'\[kb-doc:\s*([^\]]+)\]', user_content)
        if not matches:
            return ""

        docs = []
        for filename in matches:
            result = db.table("brain_documents").select("raw_content, title").eq(
                "filename", filename.strip()
            ).execute()
            if result.data:
                content = result.data[0].get("raw_content") or ""
                title = result.data[0].get("title") or filename
                docs.append(f"### {title}\n{content[:2000]}")

        if not docs:
            return ""

        return f"\n\n<kb_doc_context>\n{chr(10).join(docs)}\n</kb_doc_context>"
    except Exception:
        # Don't let KB lookup failures break the chat endpoint
        return ""


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
    """Get all messages for a conversation. Verifies ownership.

    Returns messages enriched with:
    - ``parts``  — AI SDK v4 parts array (from the dedicated column, falling
                   back to metadata.parts for older messages)
    - ``persisted_tool_results`` — rows from the tool_results table linked
                                   to this message, enabling Generative UI
                                   card rehydration without re-running tools
    """
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

    # Fetch messages (include the new top-level parts column)
    result = (
        db.table("messages")
        .select("id, conversation_id, role, content, parts, created_at, metadata, tool_calls, tool_results")
        .eq("conversation_id", conversation_id)
        .order("created_at")
        .execute()
    )

    # Fetch all tool_results for this conversation from the dedicated table.
    # These contain the rich structured output needed to rehydrate Generative UI
    # cards (file download cards, stock charts, research panels, etc.)
    try:
        tr_result = (
            db.table("tool_results")
            .select("id, message_id, tool_call_id, tool_name, input, output, state, error_text, created_at")
            .eq("conversation_id", conversation_id)
            .order("created_at")
            .execute()
        )
        # Build lookup: message_id → [tool_result, ...]
        tool_results_by_msg: dict = {}
        for tr in (tr_result.data or []):
            mid = tr.get("message_id")
            if mid:
                tool_results_by_msg.setdefault(mid, []).append(tr)
    except Exception as _tr_fetch_err:
        # tool_results table may not exist yet on older deployments — degrade gracefully
        tool_results_by_msg = {}

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

        # ── parts: use dedicated column first, fall back to metadata.parts ──
        if m.get("parts"):
            msg["parts"] = m["parts"]
        elif m.get("metadata") and m["metadata"].get("parts"):
            msg["parts"] = m["metadata"]["parts"]

        # ── legacy metadata fields ────────────────────────────────────────────
        if m.get("metadata"):
            msg["metadata"] = m["metadata"]
            if m["metadata"].get("artifacts"):
                msg["artifacts"] = m["metadata"]["artifacts"]
            if m["metadata"].get("tools_used"):
                msg["tools_used"] = m["metadata"]["tools_used"]

        # ── persisted tool results for Generative UI rehydration ─────────────
        if m["id"] in tool_results_by_msg:
            msg["persisted_tool_results"] = tool_results_by_msg[m["id"]]

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

    Supports multi-provider routing:
    - Claude models → existing Anthropic path (unchanged)
    - GPT/OpenAI models → new generic path via OpenAI provider
    - OpenRouter models → new generic path via OpenRouter provider
    """
    # ── Provider routing: check if this is a non-Claude model ─────────────
    requested_model = (data.model or "").strip()
    is_claude_model = (
        not requested_model  # no model specified → default to Claude
        or requested_model.startswith("claude-")
        or requested_model.startswith("anthropic/")
    )

    if not is_claude_model:
        # Non-Claude model → use the generic multi-provider path
        return await _chat_generic_endpoint(
            data=data,
            user_id=user_id,
            api_keys=api_keys,
            db=get_supabase(),
        )

    # ── Existing Claude path — completely unchanged ───────────────────────
    if not api_keys or not api_keys.get("claude"):
        raise HTTPException(status_code=401, detail="Claude API key required")

    db = get_supabase()

    conversation_id = await _get_or_create_conversation(
        db=db,
        user_id=user_id,
        content=data.content,
        conversation_id=data.conversation_id,
    )

    # Persist user message — include top-level parts column for AI SDK rehydration
    _user_parts = [{"type": "text", "text": data.content}]
    db.table("messages").insert({
        "conversation_id": conversation_id,
        "role": "user",
        "content": data.content,
        "parts": _user_parts,
        "metadata": {"parts": _user_parts},
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

            # Resolve model: use the exact string from the frontend if provided,
            # only fall back to the engine default (SONNET_4) when omitted.
            requested_model = data.model.strip() if data.model and data.model.strip() else engine.model
            print(f"[chat/agent] data.model={data.model!r} → requested_model={requested_model!r}")

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
                                    # Long-running skills (DOCX/PPTX/etc) can take 60-120 s.
                                    # Run the tool in a background task and emit a small
                                    # keepalive heartbeat every 15 s so the SSE connection
                                    # and Railway's proxy don't drop due to inactivity.
                                    _tool_task = asyncio.create_task(
                                        asyncio.to_thread(
                                            handle_tool_call,
                                            tool_name=tool_name,
                                            tool_input=tool_input,
                                            supabase_client=db,
                                            api_key=api_keys.get("claude"),
                                        )
                                    )
                                    while True:
                                        _done, _ = await asyncio.wait(
                                            {_tool_task}, timeout=15.0
                                        )
                                        if _done:
                                            result = await _tool_task  # result or re-raise
                                            break
                                        # Tool still running — emit heartbeat to keep alive
                                        yield encoder.encode_data({
                                            "skill_heartbeat": True,
                                            "skill_slug": tool_input.get("skill_slug", ""),
                                        })
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

                                # ── Persist tool result to dedicated table ────────────────
                                # Saves the rich structured output immediately so Generative
                                # UI cards can be rehydrated when the user revisits the
                                # conversation. message_id is backfilled below after the
                                # assistant message row is created.
                                try:
                                    _tr_state = "error" if isinstance(result_data, dict) and result_data.get("error") else "completed"
                                    db.table("tool_results").insert({
                                        "user_id": user_id,
                                        "conversation_id": conversation_id,
                                        "tool_call_id": tool_call_id,
                                        "tool_name": tool_name,
                                        "input": tool_input,
                                        "output": result_data,
                                        "state": _tr_state,
                                        "error_text": result_data.get("error") if _tr_state == "error" else None,
                                    }).execute()
                                except Exception as _tr_err:
                                    print(f"[chat/agent] ⚠ tool_results insert failed (non-fatal): {_tr_err}")

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

                                # CRITICAL FIX: Build tool_result with proper structure.
                                # Strip download URLs from what Claude sees to prevent it
                                # from repeating relative /files/... URLs in its response
                                # text (which would show broken "Open external link?"
                                # dialogs in the Streamdown renderer).
                                # The frontend already receives the download URL via the
                                # encode_file_download event emitted above.
                                claude_result = result
                                if isinstance(result_data, dict) and result_data.get("download_url"):
                                    _STRIP_URL_FIELDS = {
                                        "download_url", "document_id",
                                        "presentation_id", "file_id",
                                    }
                                    clean_for_claude = {
                                        k: v for k, v in result_data.items()
                                        if k not in _STRIP_URL_FIELDS
                                    }
                                    # Inform Claude the file is ready without giving it
                                    # the raw URL (the UI renders a download card automatically).
                                    clean_for_claude["file_ready"] = True
                                    clean_for_claude["note"] = (
                                        "The file has been prepared and a download card will "
                                        "appear in the chat UI automatically. Do NOT include "
                                        "any download URL or file path in your response."
                                    )
                                    claude_result = json.dumps(clean_for_claude)

                                tool_results_for_next_call.append({
                                    "type": "tool_result",
                                    "tool_use_id": tool_call_id,
                                    "content": claude_result,
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
                try:
                    _msg_insert = db.table("messages").insert({
                        "conversation_id": conversation_id,
                        "role": "assistant",
                        "content": accumulated_content or "(Tool results returned)",
                        # ── NEW: top-level parts column for fast AI SDK rehydration ──
                        "parts": all_parts,
                        "metadata": {
                            "parts": all_parts,        # kept for backwards-compat
                            "artifacts": artifacts,
                            "has_artifacts": len(artifacts) > 0,
                            "tools_used": tools_used,
                            "usage": total_usage,
                            "model": model_to_use,
                            "iterations": iteration,
                        },
                    }).execute()
                    print(f"[chat/agent] ✓ Saved assistant message to DB for conv {conversation_id}")

                    # ── Backfill message_id into tool_results rows ────────────────
                    # The tool_results rows were inserted during streaming without a
                    # message_id because the message didn't exist yet. Now that the
                    # message is saved we link them so the history endpoint can return
                    # Generative UI data keyed by message.
                    if tools_used and _msg_insert.data:
                        _saved_msg_id = _msg_insert.data[0]["id"]
                        _tool_call_ids = [t["toolCallId"] for t in tools_used]
                        try:
                            db.table("tool_results").update({
                                "message_id": _saved_msg_id
                            }).eq("conversation_id", conversation_id).in_(
                                "tool_call_id", _tool_call_ids
                            ).execute()
                            print(f"[chat/agent] ✓ Linked {len(_tool_call_ids)} tool_results → message {_saved_msg_id}")
                        except Exception as _link_err:
                            print(f"[chat/agent] ⚠ tool_results message_id backfill failed (non-fatal): {_link_err}")

                except Exception as db_err:
                    import traceback as _tb
                    print(f"[chat/agent] ✗ FAILED to save assistant message: {db_err}")
                    print(f"[chat/agent] DB traceback: {_tb.format_exc()[:800]}")

            try:
                db.table("conversations").update({"updated_at": "now()"}).eq(
                    "id", conversation_id
                ).execute()
            except Exception as conv_err:
                print(f"[chat/agent] ✗ FAILED to update conversation timestamp: {conv_err}")

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
# Generic Multi-Provider Chat Endpoint
# ---------------------------------------------------------------------------

async def _chat_generic_endpoint(
    data: ChatAgentRequest,
    user_id: str,
    api_keys: dict,
    db,
):
    """
    Handle chat requests for non-Claude models (GPT, OpenRouter, etc.).
    Uses the provider abstraction layer and unified tool registry.
    """
    from core.llm import get_provider_for_model
    from core.tools_v2 import get_tool_registry

    model = data.model.strip()

    # Get the right provider
    try:
        provider = get_provider_for_model(model, api_keys)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    provider_name = provider.provider_name
    provider_key = api_keys.get(provider_name, "")

    if not provider_key:
        raise HTTPException(
            status_code=401,
            detail=f"No API key configured for provider '{provider_name}'. "
                   f"Add your key in Profile Settings."
        )

    conversation_id = await _get_or_create_conversation(
        db=db,
        user_id=user_id,
        content=data.content,
        conversation_id=data.conversation_id,
    )

    # Persist user message — include top-level parts column for AI SDK rehydration
    _generic_user_parts = [{"type": "text", "text": data.content}]
    db.table("messages").insert({
        "conversation_id": conversation_id,
        "role": "user",
        "content": data.content,
        "parts": _generic_user_parts,
        "metadata": {"parts": _generic_user_parts},
    }).execute()

    # Get history
    history_result = db.table("messages").select("role, content").eq(
        "conversation_id", conversation_id
    ).order("created_at").limit(40).execute()

    history = [
        {"role": m["role"], "content": m["content"]}
        for m in history_result.data[:-1]
    ]

    file_context = await _fetch_file_context(db, conversation_id)
    kb_context = await _fetch_kb_context(db, data.content)

    # Build system prompt
    system_prompt = (
        f"You are an expert AI assistant for financial analysis and trading. "
        f"Provide accurate, helpful responses. Use tools when appropriate."
        f"{file_context}{kb_context}"
    )

    # Get tools for this provider
    tool_registry = get_tool_registry()
    tools = tool_registry.get_tools_for_provider(provider_name)

    messages = list(history)
    messages.append({"role": "user", "content": data.content})

    async def generate_stream():
        encoder = VercelAIStreamEncoder()
        accumulated_content = ""
        tools_used = []
        total_usage = {"input_tokens": 0, "output_tokens": 0}
        max_iterations = data.max_iterations
        iteration = 0

        try:
            while iteration < max_iterations:
                iteration += 1

                # Stream from provider
                tool_call_accumulators = {}
                current_tool_calls = []

                async for chunk in provider.stream_chat(
                    messages=messages,
                    model=model,
                    system=system_prompt,
                    tools=tools if tools else None,
                    max_tokens=4096,
                ):
                    if chunk.type == "text":
                        accumulated_content += chunk.content
                        yield encoder.encode_text(chunk.content)

                    elif chunk.type == "tool_call_start":
                        tool_call_accumulators[chunk.tool_id] = {
                            "id": chunk.tool_id,
                            "name": chunk.tool_name,
                            "args": "",
                        }

                    elif chunk.type == "tool_call_delta":
                        if chunk.tool_id in tool_call_accumulators:
                            tool_call_accumulators[chunk.tool_id]["args"] += (
                                chunk.tool_args or ""
                            )

                    elif chunk.type == "tool_call":
                        current_tool_calls.append({
                            "id": chunk.tool_id,
                            "name": chunk.tool_name,
                            "args": chunk.tool_args or {},
                        })

                    elif chunk.type == "finish":
                        total_usage["input_tokens"] += chunk.usage.get("input_tokens", 0)
                        total_usage["output_tokens"] += chunk.usage.get("output_tokens", 0)

                    elif chunk.type == "error":
                        yield encoder.encode_error(chunk.content)

                # If no tool calls, we're done
                if not current_tool_calls:
                    break

                # Execute tool calls
                messages.append({
                    "role": "assistant",
                    "content": accumulated_content or "",
                })

                for tc in current_tool_calls:
                    tool_name = tc["name"]
                    tool_args = tc["args"]

                    yield encoder.encode_tool_call(tc["id"], tool_name, tool_args)

                    try:
                        result = await tool_registry.handle_tool_call(
                            name=tool_name,
                            args=tool_args,
                            supabase_client=db,
                            api_key=api_keys.get("claude", ""),
                        )
                    except Exception as tool_error:
                        result = json.dumps({"error": str(tool_error)})

                    tools_used.append({
                        "tool": tool_name,
                        "toolCallId": tc["id"],
                        "input": tool_args,
                        "result": json.loads(result) if isinstance(result, str) else result,
                    })

                    yield encoder.encode_tool_result(tc["id"], result)

                    # Feed result back
                    messages.append({
                        "role": "user",
                        "content": json.dumps({
                            "tool_result": tool_name,
                            "tool_call_id": tc["id"],
                            "result": result,
                        }),
                    })

            # Persist assistant message — include top-level parts column
            if accumulated_content or tools_used:
                _generic_asst_parts = _build_tool_parts(tools_used) + (
                    [{"type": "text", "text": accumulated_content}]
                    if accumulated_content else []
                )
                db.table("messages").insert({
                    "conversation_id": conversation_id,
                    "role": "assistant",
                    "content": accumulated_content or "(Tool results returned)",
                    "parts": _generic_asst_parts,
                    "metadata": {
                        "parts": _generic_asst_parts,   # kept for backwards-compat
                        "tools_used": tools_used,
                        "usage": total_usage,
                        "model": model,
                        "provider": provider_name,
                        "iterations": iteration,
                    },
                }).execute()

            db.table("conversations").update({"updated_at": "now()"}).eq(
                "id", conversation_id
            ).execute()

            usage = {
                "promptTokens": total_usage["input_tokens"],
                "completionTokens": total_usage["output_tokens"],
            }

            yield encoder.encode_data({
                "conversation_id": conversation_id,
                "tools_used": tools_used,
                "model_used": model,
                "provider": provider_name,
            })

            yield encoder.encode_finish_message("stop", usage)

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
# Models Endpoint
# ---------------------------------------------------------------------------

@router.get("/models")
async def list_available_models(
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """
    List all available models grouped by provider.

    - Anthropic / OpenAI / Vercel Gateway: static comprehensive lists.
    - OpenRouter: fetches the live full model list (~300+ models) from
      OpenRouter's /v1/models API on first call, then serves from cache.

    Shows which providers the user has API keys for.
    """
    from core.llm import get_registry

    registry = get_registry(api_keys)

    # ── Trigger live model refresh for OpenRouter ─────────────────────────
    # This is a fast, non-blocking call: if the cache is already populated
    # it returns immediately; only the first call hits the network.
    if api_keys.get("openrouter"):
        openrouter_provider = registry.get_provider("openrouter")
        if openrouter_provider and hasattr(openrouter_provider, "refresh_models"):
            try:
                await openrouter_provider.refresh_models()
            except Exception:
                pass  # fallback list already in place

    models = registry.list_models()

    return {
        "models": models,
        "default": "claude-sonnet-4-20250514",
        "user_has_keys": {
            "anthropic": bool(api_keys.get("claude")),
            "openai": bool(api_keys.get("openai")),
            "openrouter": bool(api_keys.get("openrouter")),
            "vercel_gateway": bool(api_keys.get("vercel_gateway")),
        },
        "providers": registry.list_providers(),
    }


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


# ---------------------------------------------------------------------------
# Tool Results — Generative UI persistence
# ---------------------------------------------------------------------------

from pydantic import BaseModel as _PydanticBase
from typing import Any as _Any, Optional as _Opt


class _ToolResultItem(_PydanticBase):
    message_id: str
    tool_call_id: str
    tool_name: str
    input: dict = {}
    output: dict = {}
    state: str = "completed"
    error_text: _Opt[str] = None


class _ToolResultsPayload(_PydanticBase):
    tool_results: list[_ToolResultItem]


class _ToolResultUpdate(_PydanticBase):
    output: _Opt[dict] = None
    state: _Opt[str] = None
    error_text: _Opt[str] = None


@router.post("/conversations/{conversation_id}/tool-results")
async def save_tool_results(
    conversation_id: str,
    payload: _ToolResultsPayload,
    user_id: str = Depends(get_current_user_id),
):
    """
    Persist tool results to the database after streaming completes.

    Called by the frontend's onFinish handler so that Generative UI cards
    (documents, charts, presentations, etc.) survive page reloads and work
    across devices.
    """
    db = get_supabase()

    # Verify conversation ownership
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

    saved = 0
    errors = []

    for tr in payload.tool_results:
        try:
            db.table("tool_results").upsert(
                {
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "message_id": tr.message_id,
                    "tool_call_id": tr.tool_call_id,
                    "tool_name": tr.tool_name,
                    "input": tr.input,
                    "output": tr.output,
                    "state": tr.state,
                    "error_text": tr.error_text,
                },
                on_conflict="tool_call_id",
            ).execute()
            saved += 1
        except Exception as e:
            errors.append({"tool_call_id": tr.tool_call_id, "error": str(e)})

    return {"success": True, "saved_count": saved, "errors": errors}


@router.get("/conversations/{conversation_id}/tool-results")
async def get_tool_results(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Fetch all persisted tool results for a conversation.

    Used on page load to rehydrate Generative UI cards without re-running
    expensive tools.
    """
    db = get_supabase()

    # Verify conversation ownership
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

    try:
        result = (
            db.table("tool_results")
            .select("id, message_id, tool_call_id, tool_name, input, output, state, error_text, created_at")
            .eq("conversation_id", conversation_id)
            .eq("user_id", user_id)
            .order("created_at")
            .execute()
        )
        return result.data or []
    except Exception as e:
        # Graceful degradation if table doesn't exist yet
        return []


@router.patch("/conversations/{conversation_id}/tool-results/{tool_call_id}")
async def update_tool_result(
    conversation_id: str,
    tool_call_id: str,
    update: _ToolResultUpdate,
    user_id: str = Depends(get_current_user_id),
):
    """Update a specific tool result (e.g. after user edits a document)."""
    db = get_supabase()

    # Verify conversation ownership
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

    update_fields = {k: v for k, v in update.dict().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        result = (
            db.table("tool_results")
            .update(update_fields)
            .eq("tool_call_id", tool_call_id)
            .eq("conversation_id", conversation_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Tool result not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")


# ---------------------------------------------------------------------------
# Upload file attachment for chat
# ---------------------------------------------------------------------------

@router.post("/upload-attachment")
async def upload_chat_attachment(
    file: UploadFile = File(...),
    conversation_id: str = Form(...),
    user_id: str = Depends(get_current_user_id),
):
    """Upload a file attachment to link with a chat conversation."""
    from fastapi import Form as _Form, UploadFile as _UploadFile
    import uuid as _uuid

    db = get_supabase()

    content = await file.read()
    if len(content) > 10 * 1024 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large — maximum 10 GB")

    file_id = str(_uuid.uuid4())

    try:
        db.table("attachments").insert({
            "id": file_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "filename": file.filename,
            "size": len(content),
            "mime_type": file.content_type,
            "created_at": datetime.now().isoformat(),
        }).execute()
    except Exception as e:
        # attachments table may not exist — non-fatal
        pass

    return {
        "attachment_id": file_id,
        "filename": file.filename,
        "size": len(content),
        "url": f"/files/{file_id}",
    }
