"""Chat/Agent routes with conversation history and Claude tools."""

import io
import json
import re
import asyncio
import traceback
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import anthropic

from api.dependencies import get_current_user_id, get_user_api_keys
from core.claude_engine import ClaudeAFLEngine
from core.prompts import get_base_prompt, get_chat_prompt
from core.tools import get_all_tools, handle_tool_call
from core.artifact_parser import ArtifactParser
from core.streaming import VercelAIStreamEncoder, GenerativeUIStreamBuilder
from db.supabase_client import get_supabase

router = APIRouter(prefix="/chat", tags=["Chat"])

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

    When a user switches conversations mid-stream the backend may save the
    assistant's tool_use message but never receive the tool_result.  The next
    request would then be rejected by Claude with HTTP 400:
    "tool_use ids found without tool_result blocks".

    Fix: inject a dummy tool_result for any orphaned tool_use blocks.
    """
    sanitized = []
    i = 0
    while i < len(messages):
        msg = messages[i]

        if msg.get("role") == "assistant":
            content = msg.get("content")
            tool_use_ids = []

            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_use_ids.append(block.get("id"))

            if tool_use_ids:
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
                    sanitized.append(msg)

                    dummy_results = [
                        {
                            "type": "tool_result",
                            "tool_use_id": tid,
                            "content": (
                                "Tool execution was interrupted — "
                                "the user navigated away before the tool completed."
                            ),
                        }
                        for tid in orphaned
                    ]

                    if next_msg and next_msg.get("role") == "user" and isinstance(next_content, list):
                        sanitized.append({**next_msg, "content": list(next_content) + dummy_results})
                        i += 2
                    elif next_msg and next_msg.get("role") == "user":
                        sanitized.append({"role": "user", "content": dummy_results})
                        i += 1
                    else:
                        sanitized.append({"role": "user", "content": dummy_results})
                        i += 1
                    continue

        sanitized.append(msg)
        i += 1

    return sanitized


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
            "type": f"tool-{t['tool']}",
            "toolCallId": t.get(
                "toolCallId",
                f"call_{t['tool']}_{hash(str(t.get('input', ''))) % 100_000}",
            ),
            "toolName": t["tool"],
            "state": "output-available",
            "input": t.get("input", {}),
            "output": t.get("result", {}),
        }
        for t in tools_used
    ]


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class MessageCreate(BaseModel):
    content: str
    conversation_id: Optional[str] = None
    thinking_mode: Optional[str] = None
    thinking_budget: Optional[int] = None


class ConversationCreate(BaseModel):
    title: str = "New Conversation"
    conversation_type: str = "agent"


class ConversationUpdate(BaseModel):
    title: Optional[str] = None


class TTSRequest(BaseModel):
    text: str
    voice: str = "en-US-AriaNeural"


# ---------------------------------------------------------------------------
# Conversation CRUD
# ---------------------------------------------------------------------------

@router.get("/conversations")
async def get_conversations(
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    """Get all conversations for the current user."""
    db = get_supabase()
    result = db.table("conversations").select("*").eq(
        "user_id", user_id
    ).order("updated_at", desc=True).execute()
    return result.data


@router.post("/conversations")
async def create_conversation(
    data: ConversationCreate,
    user_id: str = Depends(get_current_user_id),
):
    """Create a new conversation."""
    db = get_supabase()
    result = db.table("conversations").insert({
        "user_id": user_id,
        "title": data.title,
        "conversation_type": data.conversation_type,
    }).execute()
    return result.data[0]


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get messages for a conversation."""
    db = get_supabase()

    conv = db.table("conversations").select("user_id").eq("id", conversation_id).execute()
    if not conv.data or conv.data[0]["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    result = db.table("messages").select("*").eq(
        "conversation_id", conversation_id
    ).order("created_at").execute()

    # Back-compat: reconstruct tool parts from metadata.tools_used for older messages
    messages = []
    for msg in result.data:
        metadata = msg.get("metadata") or {}
        parts = metadata.get("parts", [])
        tools_used = metadata.get("tools_used", [])

        has_tool_parts = any(
            p.get("state") == "output-available"
            and p.get("type", "").startswith("tool-")
            and p.get("output")
            and not p["output"].get("code")
            for p in parts
        )

        if tools_used and not has_tool_parts:
            tool_parts = _build_tool_parts(tools_used)
            parts = tool_parts + parts
            metadata = {**metadata, "parts": parts}
            msg = {**msg, "metadata": metadata}

        messages.append(msg)

    return messages


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    data: ConversationUpdate,
    user_id: str = Depends(get_current_user_id),
):
    """Rename a conversation."""
    db = get_supabase()

    conv = db.table("conversations").select("user_id").eq("id", conversation_id).execute()
    if not conv.data or conv.data[0]["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    updates = {}
    if data.title is not None:
        updates["title"] = data.title

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = db.table("conversations").update(updates).eq("id", conversation_id).execute()
    return result.data[0] if result.data else {"status": "updated"}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a conversation and all its messages."""
    db = get_supabase()

    conv = db.table("conversations").select("user_id").eq("id", conversation_id).execute()
    if not conv.data or conv.data[0]["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    try:
        db.table("conversation_files").delete().eq("conversation_id", conversation_id).execute()
    except Exception:
        pass  # table may not exist

    db.table("messages").delete().eq("conversation_id", conversation_id).execute()
    db.table("conversations").delete().eq("id", conversation_id).execute()

    return {"status": "deleted", "conversation_id": conversation_id}


# ---------------------------------------------------------------------------
# Non-streaming message endpoint
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_TOOLS = """
## Available Tools
You have access to powerful tools to help users:

1. **Web Search** - Search the internet for real-time information, news, and data
2. **Execute Python** - Run Python code for calculations, data analysis, and complex computations
3. **Search Knowledge Base** - Search the user's uploaded documents and trading knowledge
4. **Get Stock Data** - Fetch real-time and historical stock market data
5. **Validate AFL** - Check AFL code for syntax errors before presenting it

Use these tools proactively when they would help provide better answers.
"""


@router.post("/message")
async def send_message(
    data: MessageCreate,
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """Send a message and get a full (non-streaming) AI response with tool support."""
    db = get_supabase()

    if not api_keys.get("claude"):
        raise HTTPException(
            status_code=400,
            detail="Claude API key not configured. Please add your API key in Profile Settings.",
        )

    conversation_id = await _get_or_create_conversation(
        db, user_id, data.content, data.conversation_id
    )

    db.table("messages").insert({
        "conversation_id": conversation_id,
        "role": "user",
        "content": data.content,
    }).execute()

    history_result = db.table("messages").select("role, content").eq(
        "conversation_id", conversation_id
    ).order("created_at").execute()

    history = [{"role": m["role"], "content": m["content"]} for m in history_result.data[:-1]]
    messages = sanitize_message_history(history + [{"role": "user", "content": data.content}])

    try:
        # Create thinking config if provided
        thinking_config = None
        if data.thinking_mode:
            from core.claude_engine import ThinkingMode, ThinkingConfig
            mode = ThinkingMode.ENABLED if data.thinking_mode.lower() == "enabled" else ThinkingMode.DISABLED
            thinking_config = ThinkingConfig(
                mode=mode,
                budget_tokens=data.thinking_budget
            )
        
        engine = _get_engine(api_keys["claude"])
        if thinking_config:
            engine.thinking_config = thinking_config
        system_prompt = f"{get_base_prompt()}\n\n{get_chat_prompt()}{_SYSTEM_PROMPT_TOOLS}"
        tools = get_all_tools()
        tools_used = []

        response = engine.chat(
            message=data.content,
            system=system_prompt,
            tools=tools,
            max_tokens=3000,
            messages=messages[:-1],
        )

        max_iterations = 3
        iteration = 0

        while response.get("stop_reason") == "tool_use" and iteration < max_iterations:
            iteration += 1
            tool_results = []

            for block in response.get("content", []):
                if block.get("type") != "tool_use":
                    continue
                tool_name = block.get("name")
                tool_input = block.get("input")
                tool_use_id = block.get("id")

                if tool_name in ["web_search"]:
                    continue

                result = handle_tool_call(
                    tool_name=tool_name,
                    tool_input=tool_input,
                    supabase_client=db,
                    api_key=api_keys.get("claude"),
                )

                try:
                    result_data = json.loads(result) if isinstance(result, str) else result
                except (json.JSONDecodeError, TypeError):
                    result_data = {"raw": str(result)}

                tools_used.append({"tool": tool_name, "input": tool_input, "result": result_data})
                tool_results.append({"type": "tool_result", "tool_use_id": tool_use_id, "content": result})

            if not tool_results:
                break

            messages.append({"role": "assistant", "content": response.get("content", [])})
            messages.append({"role": "user", "content": tool_results})

            response = engine.chat(
                message="",
                system=system_prompt,
                tools=tools,
                max_tokens=4096,
                messages=messages,
            )

        assistant_content = "".join(
            block.get("text", "")
            for block in response.get("content", [])
            if block.get("type") == "text"
        )

        artifacts = ArtifactParser.extract_artifacts(assistant_content)
        parts = _build_parts(assistant_content, artifacts)
        tool_parts = _build_tool_parts(tools_used)
        all_parts = tool_parts + parts

        db.table("messages").insert({
            "conversation_id": conversation_id,
            "role": "assistant",
            "content": assistant_content,
            "metadata": {
                "parts": all_parts,
                "artifacts": artifacts,
                "has_artifacts": len(artifacts) > 0,
                "tools_used": tools_used,
            },
        }).execute()

        db.table("conversations").update({"updated_at": "now()"}).eq(
            "id", conversation_id
        ).execute()

        downloadable_files = []
        for tu in tools_used:
            res = tu.get("result", {})
            if isinstance(res, dict) and res.get("download_url"):
                fid = res.get("presentation_id") or res.get("document_id") or ""
                downloadable_files.append({
                    "file_id": fid,
                    "filename": res.get("filename", "download"),
                    "download_url": f"/files/{fid}/download" if fid else res["download_url"],
                    "file_type": res.get("filename", "").rsplit(".", 1)[-1] if res.get("filename") else "unknown",
                    "size_kb": res.get("file_size_kb", 0),
                    "tool_name": tu.get("tool", ""),
                })

        return {
            "conversation_id": conversation_id,
            "response": assistant_content,
            "parts": all_parts,
            "tools_used": tools_used or None,
            "downloadable_files": downloadable_files or None,
            "all_artifacts": artifacts,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Streaming endpoint (v6 — canonical production endpoint)
# ---------------------------------------------------------------------------

_AFL_RULES = """
## CRITICAL AFL RULES (ALWAYS FOLLOW WHEN WRITING ANY AFL CODE):
### Function Signatures (MUST be exact):
- SINGLE-ARG (NO array): RSI(14), ATR(14), ADX(14), CCI(20), MFI(14), Stoch(14), Williams(14)
- DOUBLE-ARG (WITH array): MA(Close,20), EMA(Close,12), HHV(High,20), LLV(Low,20), Ref(Close,-1)
- ❌ WRONG: RSI(Close,14) → ✅ RIGHT: RSI(14)
- ❌ WRONG: MA(20) → ✅ RIGHT: MA(Close,20)
- ❌ WRONG: RSI = RSI(14) → ✅ RIGHT: RSI_Val = RSI(14)  (NEVER use function names as variable names)

### Required Patterns:
- ALWAYS use Param()/Optimize() for adjustable parameters
- ALWAYS add ExRem(Buy,Sell); ExRem(Sell,Buy); to remove consecutive signals
- ALWAYS wrap code in _SECTION_BEGIN("Name")/_SECTION_END()
- STANDALONE: Include ALL sections (Buy/Sell, plotting, exploration, backtest settings)
- COMPOSITE: Only strategy logic, no plotting, no backtest settings, prefix all variables

### SetTradeDelays:
- For CLOSE execution: SetTradeDelays(0,0,0,0)
- For OPEN execution: SetTradeDelays(1,1,1,1)
"""

_STREAM_TOOLS_LIST = """
## Tools Available — USE THESE PROACTIVELY:

### File & Document Creation (ALWAYS use these — NEVER say you can't create files):
- **create_word_document**: Create a downloadable Potomac-branded Word (.docx) file.
  USE THIS whenever the user asks for a Word document, report, memo, fact sheet, proposal, or any written document.
- **create_pptx_with_skill**: Create a downloadable Potomac-branded PowerPoint (.pptx) file.
  USE THIS whenever the user asks for a presentation, slide deck, pitch deck, or PowerPoint.
- **invoke_skill**: Invoke any Claude beta skill for advanced file creation and analysis.
  USE THIS with skill_slug='potomac-xlsx' or 'xlsx' whenever the user asks for an Excel spreadsheet, .xlsx, or any tabular data file.
  USE THIS with skill_slug='potomac-docx-skill' for complex branded Word docs.
  USE THIS with skill_slug='potomac-pptx' for complex branded PowerPoints.
  USE THIS with skill_slug='dcf-model' for DCF valuation models in Excel.
  USE THIS with skill_slug='doc-interpreter' to read/extract data from images and PDFs.

### Research & Analysis:
- **run_financial_deep_research**: Institutional-grade financial research on any company/topic
- **run_backtest_analysis**: Expert backtest analysis and strategy evaluation
- **run_quant_analysis**: Factor models, portfolio optimization, systematic strategy design
- **run_bubble_detection**: Bubble risk analysis for US equities

### Market Data:
- **web_search**: Search the internet for current information
- **get_stock_data**: Real-time stock prices (cached 5min)
- **technical_analysis**: RSI, MACD, Bollinger Bands, ADX for any stock
- **get_stock_chart**: Full OHLCV candlestick data
- **get_market_overview**: Indices, VIX, commodities, crypto
- **get_market_sentiment**: Fear/greed, put/call ratio, VIX
- **compare_stocks**: Side-by-side stock comparison

### AFL Code:
- **generate_afl_code**: Create AFL trading systems
- **generate_afl_with_skill**: Premium AFL generation for complex strategies
- **validate_afl/sanity_check_afl**: Verify AFL code — ALWAYS run before presenting AFL code

### Other:
- **search_knowledge_base**: User's uploaded documents
- **execute_python**: Run calculations and data analysis
- **edgar_get_financials / edgar_get_filings**: Official SEC financial data

CRITICAL RULES:
1. NEVER say "I don't have the ability to create files" — you DO have create_word_document, create_pptx_with_skill, and invoke_skill tools
2. ALWAYS use sanity_check_afl before presenting any AFL code
3. For Excel/spreadsheet requests → use invoke_skill with skill_slug='potomac-xlsx'
4. For Word document requests → use create_word_document tool directly
5. For PowerPoint requests → use create_pptx_with_skill tool directly
"""


async def _fetch_file_context(db, conversation_id: str, max_chars: int = 6000) -> str:
    """Return formatted text of files uploaded in this conversation.

    Lookup order:
    1. file_uploads.extracted_text (chat uploads)
    2. brain_documents.raw_content (KB uploads linked to conversation)
    3. Read from Railway volume directly as fallback for PDFs/text files
    """
    try:
        result = db.table("conversation_files").select(
            "purpose, file_uploads(id, original_filename, content_type, file_size, extracted_text, storage_path, status)"
        ).eq("conversation_id", conversation_id).execute()

        if not result.data:
            return ""

        snippets = []
        for row in result.data:
            fu = row.get("file_uploads") or {}
            filename = fu.get("original_filename", "unknown")
            content_type = fu.get("content_type", "")
            extracted = fu.get("extracted_text", "")
            storage_path = fu.get("storage_path", "")
            status = fu.get("status", "uploaded")

            if extracted and extracted.strip():
                preview = extracted.replace("\x00", "")[:max_chars]
                snippets.append(f"### File: {filename}\n```\n{preview}\n```")
                continue

            # Fallback: try to read and extract from Railway volume on-demand
            if storage_path:
                import os
                if os.path.exists(storage_path):
                    try:
                        from api.routes.upload import _extract_text
                        with open(storage_path, "rb") as f:
                            raw = f.read()
                        text = _extract_text(raw, content_type, filename)
                        text = text.replace("\x00", "").strip()
                        if text:
                            # Cache it back to DB for next time
                            try:
                                db.table("file_uploads").update({
                                    "extracted_text": text,
                                    "status": "ready",
                                }).eq("id", fu.get("id")).execute()
                            except Exception:
                                pass
                            preview = text[:max_chars]
                            snippets.append(f"### File: {filename}\n```\n{preview}\n```")
                            continue
                    except Exception as read_err:
                        import logging
                        logging.getLogger(__name__).warning(f"On-demand extraction failed for {filename}: {read_err}")

            if content_type.startswith("image/"):
                snippets.append(f"### File: {filename} (image uploaded)")
            else:
                snippets.append(
                    f"### File: {filename}\n"
                    f"Note: Text extraction is pending for this file. "
                    f"If the user asks about this file's contents, tell them "
                    f"pypdf needs to be installed on the server to read PDFs, "
                    f"or ask them to paste the text content directly."
                )

        if snippets:
            return (
                "\n\n## Files Uploaded in This Conversation:\n"
                "IMPORTANT: Analyse file contents directly from the text below. "
                "Do NOT use Python file I/O or try to open paths.\n\n"
                + "\n\n".join(snippets)
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"_fetch_file_context failed: {e}")
    return ""


async def _fetch_kb_context(db, user_message: str) -> str:
    """Return relevant knowledge-base snippets for AFL-related queries."""
    keywords = {"afl", "trading", "strategy", "indicator", "backtest", "buy", "sell"}
    if not any(kw in user_message.lower() for kw in keywords):
        return ""

    try:
        result = db.table("brain_documents").select(
            "title, summary, raw_content"
        ).limit(3).execute()

        if not result.data:
            return ""

        snippets = []
        for doc in result.data:
            snippet = doc.get("summary") or doc.get("raw_content", "")[:300]
            if snippet:
                snippets.append(f"- {doc['title']}: {snippet[:200]}")

        if snippets:
            return "\n\n## User's Knowledge Base (relevant documents):\n" + "\n".join(snippets)
    except Exception:
        pass
    return ""



async def _fetch_kb_doc_refs(db, user_message: str, max_chars: int = 6000) -> str:
    """
    Parse [kb-doc: filename] markers from the user message and inject
    the full raw_content of those documents into the system prompt.
    """
    import re
    refs = re.findall(r'\[kb-doc:\s*([^\]]+)\]', user_message, re.IGNORECASE)
    if not refs:
        return ""

    snippets = []
    for ref_name in refs:
        ref_name = ref_name.strip()
        try:
            # Match by filename or title (case-insensitive)
            result = db.table("brain_documents").select(
                "id, title, filename, raw_content, category"
            ).or_(
                f"filename.ilike.%{ref_name}%,title.ilike.%{ref_name}%"
            ).limit(1).execute()

            if result.data:
                doc = result.data[0]
                raw = (doc.get("raw_content") or "").strip()
                if raw:
                    preview = raw[:max_chars]
                    snippets.append(
                        f"### Referenced Document: {doc.get('filename') or doc.get('title')}\n"
                        f"Category: {doc.get('category', 'general')}\n"
                        f"```\n{preview}\n```"
                    )
                else:
                    snippets.append(
                        f"### Referenced Document: {ref_name}\n"
                        f"Note: This document is stored but has no extracted text content yet."
                    )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"_fetch_kb_doc_refs failed for {ref_name}: {e}")

    if not snippets:
        return ""

    return (
        "\n\n## Explicitly Referenced Knowledge Base Documents:\n"
        "The user has specifically selected these documents for you to analyse. "
        "Read and reference them directly in your response.\n\n"
        + "\n\n".join(snippets)
    )


@router.post("/v6")
async def chat_v6_stream(
    data: MessageCreate,
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """
    Canonical streaming endpoint using the Vercel AI SDK Data Stream Protocol.
    Supports multi-step tool use, artifact detection, and Generative UI.
    """
    db = get_supabase()

    if not api_keys.get("claude"):
        raise HTTPException(status_code=400, detail="Claude API key not configured")

    conversation_id = await _get_or_create_conversation(
        db, user_id, data.content, data.conversation_id
    )

    db.table("messages").insert({
        "conversation_id": conversation_id,
        "role": "user",
        "content": data.content,
    }).execute()

    history_result = db.table("messages").select("role, content").eq(
        "conversation_id", conversation_id
    ).order("created_at").limit(20).execute()

    history = [
        {"role": m["role"], "content": m["content"]}
        for m in history_result.data[:-1]
    ][-10:]

    file_context = await _fetch_file_context(db, conversation_id)
    kb_context = await _fetch_kb_context(db, data.content)

    # Extract [kb-doc: filename] references from the user message and inject full content
    kb_doc_context = await _fetch_kb_doc_refs(db, data.content)

    async def generate_stream():
        encoder = VercelAIStreamEncoder()
        builder = GenerativeUIStreamBuilder()
        accumulated_content = ""
        tools_used = []
        final_message = None  # guard against unbound reference in usage dict

        try:
            # Create thinking config if provided
            thinking_config = None
            if data.thinking_mode:
                from core.claude_engine import ThinkingMode, ThinkingConfig
                mode = ThinkingMode.ENABLED if data.thinking_mode.lower() == "enabled" else ThinkingMode.DISABLED
                thinking_config = ThinkingConfig(
                    mode=mode,
                    budget_tokens=data.thinking_budget
                )
            
            engine = _get_engine(api_keys["claude"])
            if thinking_config:
                engine.thinking_config = thinking_config
            client = anthropic.AsyncAnthropic(api_key=api_keys["claude"])

            system_prompt = (
                f"{get_base_prompt()}\n\n{get_chat_prompt()}"
                f"{file_context}{kb_context}{kb_doc_context}"
                f"{_AFL_RULES}{_STREAM_TOOLS_LIST}"
            )

            messages = sanitize_message_history(
                history + [{"role": "user", "content": data.content}]
            )
            tools = get_all_tools()

            max_iterations = 3
            iteration = 0

            while iteration < max_iterations:
                iteration += 1
                tool_results_for_next_call = []
                assistant_content_blocks = []
                pending_tool_calls = []

                async with client.messages.stream(
                    model=engine.model,
                    max_tokens=3000,
                    system=system_prompt,
                    messages=messages,
                    tools=tools,
                ) as stream:

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

                                if tool_name not in ["web_search"]:
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

                if final_message.stop_reason == "tool_use" and tool_results_for_next_call:
                    messages.append({"role": "assistant", "content": final_message.content})
                    messages.append({"role": "user", "content": tool_results_for_next_call})
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
                    },
                }).execute()

            db.table("conversations").update({"updated_at": "now()"}).eq(
                "id", conversation_id
            ).execute()

            usage = {
                "promptTokens": final_message.usage.input_tokens if final_message else 0,
                "completionTokens": final_message.usage.output_tokens if final_message else 0,
            }

            yield encoder.encode_data({
                "conversation_id": conversation_id,
                "tools_used": tools_used,
                "has_artifacts": len(artifacts) > 0,
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