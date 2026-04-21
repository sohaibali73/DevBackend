"""
core/yang/parallel_tools.py — Parallel Tool Dispatch
=====================================================
When multiple tool calls arrive in a single Claude assistant turn, this
module dispatches the read-only / idempotent ones concurrently using
asyncio.gather, then runs side-effectful tools sequentially.

Key design points:
- Results are ALWAYS returned in the same order as the input calls list,
  regardless of which tools finish first (critical for Claude's tool_result
  ordering requirement).
- `handle_tool_call` in core/tools.py is synchronous.  We wrap every call
  in asyncio.to_thread so it runs in a thread-pool without blocking the event
  loop.
- A shared heartbeat coroutine fires every 15 s during parallel execution so
  the SSE connection / Railway proxy doesn't drop on long-running tools.
- Falls back gracefully on any error: a failed tool returns an error dict
  rather than propagating the exception and aborting the entire batch.

Usage (from api/routes/chat.py):
    from core.yang.parallel_tools import execute_tool_calls_parallel, PARALLEL_SAFE

    results = await execute_tool_calls_parallel(
        calls=deferred_tool_calls,        # [{id, name, input}, ...]
        handle_tool_call=handle_tool_call,
        supabase_client=db,
        api_key=api_key,
        conversation_file_ids=file_ids,
        heartbeat=heartbeat_fn,           # async () -> None
    )
    # results[i] matches calls[i] (order preserved)
"""

import asyncio
import json
import logging
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── Parallel-safe tool allowlist ────────────────────────────────────────────
#
# Tools in this set are idempotent read-only operations that are safe to run
# concurrently.  Any tool NOT in this set runs sequentially after all parallel
# tools complete (preserving order within the sequential group).

PARALLEL_SAFE: frozenset = frozenset({
    # ── Web & market data ────────────────────────────────────────────────
    "web_search",
    "search_knowledge_base",
    "get_stock_data",
    "get_stock_chart",
    "get_financial_data",
    "get_market_data",
    "get_market_sentiment",
    "get_market_overview",
    "get_earnings_data",
    "get_analyst_ratings",
    "get_insider_trading",
    "get_institutional_holders",
    "get_options_data",
    "get_crypto_data",
    "get_fx_data",
    "get_commodity_data",
    "get_economic_indicators",
    "get_sector_performance",

    # ── Technical analysis (pure computation) ─────────────────────────────
    "technical_analysis",
    "pattern_recognition",

    # ── EDGAR / SEC data ──────────────────────────────────────────────────
    "edgar_search",
    "edgar_get_filings",
    "edgar_get_xbrl",
    "edgar_get_company_facts",

    # ── Knowledge base / AFL explanation (read-only) ─────────────────────
    "search_brain",
    "get_training_examples",
    "explain_afl_code",
    "validate_afl_code",

    # ── Research ──────────────────────────────────────────────────────────
    "analyze_company",
    "get_peer_comparison",
    "get_strategy_analysis",

    # ── Document analysis (read, no write) ───────────────────────────────
    "analyze_pptx",
    "analyze_xlsx",
    "read_pptx",
})

# Maximum concurrent parallel tool executions
_MAX_PARALLEL = 5

# Heartbeat interval in seconds (keeps SSE/Railway connection alive)
_HEARTBEAT_INTERVAL_S = 15.0


# ─── Core dispatch function ───────────────────────────────────────────────────

async def execute_tool_calls_parallel(
    calls: List[Dict[str, Any]],
    handle_tool_call: Callable,
    supabase_client: Any,
    api_key: str,
    conversation_file_ids: Optional[List[str]] = None,
    heartbeat: Optional[Callable[[], Coroutine]] = None,
) -> List[Dict[str, Any]]:
    """
    Execute a batch of tool calls (parallel-safe ones concurrently,
    sequential ones one by one) and return results in input order.

    Args:
        calls:                List of {id, name, input} dicts (from the stream).
        handle_tool_call:     The sync tool dispatcher from core/tools.py.
        supabase_client:      Supabase DB client (passed through to tools).
        api_key:              Claude API key (passed through to tools).
        conversation_file_ids: File IDs for sandbox injection.
        heartbeat:            Optional async callable emitted every 15 s.
                              Signature: async () -> None

    Returns:
        List of result dicts, same length and order as `calls`:
        [
            {
                "id":          tool_call_id,
                "name":        tool_name,
                "input":       tool_input,
                "result":      raw result string,
                "result_data": parsed dict,
                "error":       error message or None,
                "elapsed_ms":  wall-clock execution time,
            },
            ...
        ]
    """
    if not calls:
        return []

    # Partition: parallel-safe vs sequential
    parallel_indices = [i for i, c in enumerate(calls) if c["name"] in PARALLEL_SAFE]
    sequential_indices = [i for i, c in enumerate(calls) if c["name"] not in PARALLEL_SAFE]

    results: List[Optional[Dict]] = [None] * len(calls)
    semaphore = asyncio.Semaphore(_MAX_PARALLEL)

    # ── Heartbeat background task ─────────────────────────────────────────
    heartbeat_task: Optional[asyncio.Task] = None
    if heartbeat and (len(calls) > 1 or len(parallel_indices) > 0):
        async def _heartbeat_loop():
            while True:
                await asyncio.sleep(_HEARTBEAT_INTERVAL_S)
                try:
                    await heartbeat()
                except Exception:
                    pass
        heartbeat_task = asyncio.create_task(_heartbeat_loop())

    try:
        # ── Phase 1: parallel batch ───────────────────────────────────────
        if parallel_indices:
            parallel_tasks = [
                asyncio.create_task(
                    _run_tool(
                        call=calls[i],
                        handle_tool_call=handle_tool_call,
                        supabase_client=supabase_client,
                        api_key=api_key,
                        conversation_file_ids=conversation_file_ids,
                        semaphore=semaphore,
                    )
                )
                for i in parallel_indices
            ]
            parallel_results = await asyncio.gather(*parallel_tasks, return_exceptions=False)
            for i, res in zip(parallel_indices, parallel_results):
                results[i] = res

            logger.info(
                "parallel_tools: ran %d tools concurrently (indices %s)",
                len(parallel_indices), parallel_indices,
            )

        # ── Phase 2: sequential batch ─────────────────────────────────────
        for i in sequential_indices:
            res = await _run_tool(
                call=calls[i],
                handle_tool_call=handle_tool_call,
                supabase_client=supabase_client,
                api_key=api_key,
                conversation_file_ids=conversation_file_ids,
                semaphore=None,  # no semaphore needed for sequential
            )
            results[i] = res

        if sequential_indices:
            logger.info(
                "parallel_tools: ran %d tools sequentially (indices %s)",
                len(sequential_indices), sequential_indices,
            )

    finally:
        if heartbeat_task and not heartbeat_task.done():
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    return results  # type: ignore[return-value]


# ─── Single tool runner ───────────────────────────────────────────────────────

async def _run_tool(
    call: Dict[str, Any],
    handle_tool_call: Callable,
    supabase_client: Any,
    api_key: str,
    conversation_file_ids: Optional[List[str]],
    semaphore: Optional[asyncio.Semaphore],
) -> Dict[str, Any]:
    """
    Run a single tool call in a thread-pool worker.
    Returns a result dict (never raises).
    """
    tool_call_id: str = call["id"]
    tool_name: str = call["name"]
    tool_input: Dict = call.get("input") or {}

    start_ms = time.monotonic() * 1000

    async def _execute():
        return await asyncio.to_thread(
            handle_tool_call,
            tool_name=tool_name,
            tool_input=tool_input,
            supabase_client=supabase_client,
            api_key=api_key,
            conversation_file_ids=conversation_file_ids or [],
        )

    try:
        if semaphore:
            async with semaphore:
                raw = await _execute()
        else:
            raw = await _execute()

        elapsed_ms = int(time.monotonic() * 1000 - start_ms)

        try:
            result_data = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            result_data = {"raw": str(raw)}

        logger.debug(
            "parallel_tools: %s done in %d ms (id=%s)",
            tool_name, elapsed_ms, tool_call_id,
        )
        return {
            "id":          tool_call_id,
            "name":        tool_name,
            "input":       tool_input,
            "result":      raw if isinstance(raw, str) else json.dumps(result_data),
            "result_data": result_data,
            "error":       None,
            "elapsed_ms":  elapsed_ms,
        }

    except Exception as e:
        elapsed_ms = int(time.monotonic() * 1000 - start_ms)
        error_str = str(e)
        logger.warning(
            "parallel_tools: %s failed in %d ms: %s (id=%s)",
            tool_name, elapsed_ms, error_str, tool_call_id,
        )
        error_data = {"error": error_str}
        return {
            "id":          tool_call_id,
            "name":        tool_name,
            "input":       tool_input,
            "result":      json.dumps(error_data),
            "result_data": error_data,
            "error":       error_str,
            "elapsed_ms":  elapsed_ms,
        }
