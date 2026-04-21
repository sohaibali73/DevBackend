"""
core/yang/subagents.py — Parallel Focused Subagent Runner
==========================================================
Exposes a `spawn_subagents` tool that Claude can call to dispatch multiple
focused research/analysis sub-tasks concurrently.  Each subagent is a
constrained Anthropic API call with a role-specific tool subset:

  researcher  → web_search, edgar lookups, yfinance data
  analyst     → technical analysis, stock data, execute_python
  kb_searcher → search_knowledge_base, explain_afl_code

Architecture:
- Claude calls spawn_subagents({subtasks: [{role, prompt, max_tokens}]})
- The chat route handles this tool call specially (not via handle_tool_call)
- run_subagents() dispatches all subtasks with asyncio.gather under a semaphore
- Individual failures don't abort the batch — they return {error: "..."} entries
- Aggregate output is truncated at 8 K chars before being fed back to Claude

Usage (from api/routes/chat.py):
    from core.yang.subagents import SPAWN_SUBAGENTS_TOOL_DEF, run_subagents

    # Add tool to tools list when yang_cfg.subagents=True
    tools = tools + [SPAWN_SUBAGENTS_TOOL_DEF]

    # Handle special tool call:
    if tool_name == "spawn_subagents":
        result = await run_subagents(tool_input.get("subtasks", []), api_key, yang_cfg)
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── Tool definition ──────────────────────────────────────────────────────────

SPAWN_SUBAGENTS_TOOL_DEF: Dict[str, Any] = {
    "name": "spawn_subagents",
    "description": (
        "Dispatch multiple focused sub-tasks in parallel, each run by a "
        "specialized subagent with a curated tool subset.\n\n"
        "Available roles:\n"
        "- researcher: web search, SEC EDGAR lookups, Yahoo Finance data\n"
        "- analyst:    technical analysis, stock data, Python execution\n"
        "- kb_searcher: knowledge base search, AFL code explanation\n\n"
        "Use this when you need to gather information from multiple sources "
        "simultaneously.  Each subtask runs independently; results are "
        "collected and returned together."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "subtasks": {
                "type": "array",
                "description": "List of subtasks to run in parallel (max 5).",
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "required": ["role", "prompt"],
                    "properties": {
                        "role": {
                            "type": "string",
                            "enum": ["researcher", "analyst", "kb_searcher"],
                            "description": "Subagent specialisation — determines tool access.",
                        },
                        "prompt": {
                            "type": "string",
                            "description": "Focused task description for this subagent.",
                        },
                        "max_tokens": {
                            "type": "integer",
                            "description": "Max output tokens (default 2048, max 4096).",
                            "default": 4096,
                        },
                    },
                },
            }
        },
        "required": ["subtasks"],
    },
}


# ─── Role → allowed tool names ────────────────────────────────────────────────

_ROLE_TOOLS: Dict[str, frozenset] = {
    "researcher": frozenset({
        "web_search",
        "edgar_search",
        "edgar_get_filings",
        "edgar_get_xbrl",
        "edgar_get_company_facts",
        "get_stock_data",
        "get_financial_data",
        "get_earnings_data",
        "get_market_sentiment",
        "get_market_overview",
        "get_analyst_ratings",
        "get_sector_performance",
    }),
    "analyst": frozenset({
        "technical_analysis",
        "get_stock_data",
        "get_stock_chart",
        "get_financial_data",
        "get_earnings_data",
        "pattern_recognition",
        "execute_python",
    }),
    "kb_searcher": frozenset({
        "search_knowledge_base",
        "search_brain",
        "explain_afl_code",
        "validate_afl_code",
        "get_training_examples",
    }),
}

# Hard cap on aggregate output length returned to the main model
_MAX_AGGREGATE_CHARS = 50000

# Haiku-tier subagent model (cheap, fast)
# NOTE: must be a real Anthropic model slug — a stale/invalid slug causes every
# subagent call to fail with `404 not_found_error` and the dispatcher appears offline.
_DEFAULT_SUBAGENT_MODEL = "claude-sonnet-4-6"
_FALLBACK_SUBAGENT_MODEL = "claude-3-5-haiku-latest"


# ─── Public entry-point ───────────────────────────────────────────────────────

async def run_subagents(
    subtasks: List[Dict[str, Any]],
    api_key: Optional[str],
    yang_cfg: Any,
) -> str:
    """
    Dispatch subtasks concurrently and return aggregated results as a JSON string.

    Args:
        subtasks:  List of {role, prompt, max_tokens} dicts from the tool call.
        api_key:   Claude API key.
        yang_cfg:  YangConfig (provides subagent_max, subagent_timeout_s, etc.)

    Returns:
        JSON string with the subagent results, suitable as a tool_result content.
    """
    if not api_key:
        return json.dumps({"error": "No API key available for subagents."})

    if not subtasks:
        return json.dumps({"error": "No subtasks provided."})

    max_concurrent = int(yang_cfg.subagent_max)
    timeout_s = int(yang_cfg.subagent_timeout_s)
    max_tokens_cap = int(yang_cfg.subagent_max_tokens)
    # Prefer explicit subagent_model on yang_cfg; fall back to the default alias.
    # Do NOT reuse double_check_model — that slug may point at a verifier-only model.
    subagent_model = getattr(yang_cfg, "subagent_model", None) or _DEFAULT_SUBAGENT_MODEL

    # Cap number of subtasks
    tasks = subtasks[:max_concurrent]
    semaphore = asyncio.Semaphore(max_concurrent)

    logger.info("subagents: dispatching %d subtask(s)", len(tasks))

    coroutines = [
        _run_one_subagent(
            task=task,
            api_key=api_key,
            model=subagent_model,
            max_tokens_cap=max_tokens_cap,
            timeout_s=timeout_s,
            semaphore=semaphore,
        )
        for task in tasks
    ]

    results: List[Dict] = await asyncio.gather(*coroutines, return_exceptions=False)

    # Truncate each subtask summary BEFORE aggregation so final JSON stays valid
    _PER_RESULT_CHAR_BUDGET = max(512, _MAX_AGGREGATE_CHARS // max(1, len(results)) - 256)
    for r in results:
        summary = r.get("summary")
        if isinstance(summary, str) and len(summary) > _PER_RESULT_CHAR_BUDGET:
            r["summary"] = summary[:_PER_RESULT_CHAR_BUDGET] + "… [truncated]"

    # Build aggregate response
    output = {"subtask_results": results, "count": len(results)}
    raw = json.dumps(output, indent=2)

    # Hard safety net — in the rare case we still overflow, return a minimal
    # but VALID JSON summary rather than a truncated (invalid) blob.
    if len(raw) > _MAX_AGGREGATE_CHARS:
        logger.warning(
            "subagents: aggregate still %d chars after per-result trim — falling back to summaries-only",
            len(raw),
        )
        stripped = [
            {
                "role": r.get("role"),
                "prompt": (r.get("prompt") or "")[:80],
                "summary": (r.get("summary") or "")[: _PER_RESULT_CHAR_BUDGET // 2]
                           + ("… [truncated]" if r.get("summary") else ""),
                "error": r.get("error"),
                "elapsed_s": r.get("elapsed_s"),
            }
            for r in results
        ]
        raw = json.dumps(
            {"subtask_results": stripped, "count": len(stripped), "truncated": True},
            indent=2,
        )


    logger.info(
        "subagents: %d subtasks complete (%d chars)",
        len(results), len(raw),
    )
    return raw


# ─── Single subagent runner ───────────────────────────────────────────────────

async def _run_one_subagent(
    task: Dict[str, Any],
    api_key: str,
    model: str,
    max_tokens_cap: int,
    timeout_s: int,
    semaphore: asyncio.Semaphore,
) -> Dict[str, Any]:
    """
    Run a single subagent call.  Returns a result dict (never raises).
    """
    role   = task.get("role", "researcher")
    prompt = task.get("prompt", "")
    mt     = min(int(task.get("max_tokens", 2048)), max_tokens_cap)

    if not prompt.strip():
        return {"role": role, "error": "Empty prompt.", "summary": ""}

    start = time.monotonic()

    try:
        result_text = await asyncio.wait_for(
            asyncio.to_thread(_call_subagent, api_key, model, role, prompt, mt),
            timeout=timeout_s,
        )
        elapsed = round(time.monotonic() - start, 2)
        logger.debug("subagent[%s]: done in %.2f s", role, elapsed)
        return {
            "role":    role,
            "prompt":  prompt[:120],
            "summary": result_text,
            "elapsed_s": elapsed,
        }
    except asyncio.TimeoutError:
        return {
            "role":  role,
            "error": f"Subagent timed out after {timeout_s} s.",
        }
    except Exception as e:
        logger.warning("subagent[%s] failed: %s", role, e)
        return {
            "role":  role,
            "error": str(e),
        }


def _call_subagent(
    api_key: str,
    model: str,
    role: str,
    prompt: str,
    max_tokens: int,
) -> str:
    """
    Synchronous subagent call (runs in thread-pool via asyncio.to_thread).
    Uses tools filtered to the role's allowed set.
    Returns the assistant's response text.
    """
    import anthropic as _anth
    from core.tools import get_all_tools

    # Filter tools to role's allowed set
    allowed = _ROLE_TOOLS.get(role, frozenset())
    role_tools = [t for t in get_all_tools() if t.get("name", "") in allowed]

    client = _anth.Anthropic(api_key=api_key)

    kwargs: Dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": (
            f"You are a focused {role} subagent. "
            "Answer the task concisely using your available tools. "
            "Be factual and precise. Return only the relevant findings."
        ),
        "messages": [{"role": "user", "content": prompt}],
    }
    if role_tools:
        kwargs["tools"] = role_tools

    # Simple non-streaming call (subagent responses are short).
    # Retry once with the fallback slug if the primary model 404s.
    try:
        response = client.messages.create(**kwargs)
    except _anth.NotFoundError as e:
        logger.warning("subagent model '%s' returned 404; retrying with fallback '%s'",
                       model, _FALLBACK_SUBAGENT_MODEL)
        kwargs["model"] = _FALLBACK_SUBAGENT_MODEL
        response = client.messages.create(**kwargs)

    # Extract text from response
    text_parts = [
        block.text for block in response.content
        if hasattr(block, "text")
    ]
    return " ".join(text_parts).strip() or "(no text response)"
