"""
core/yang/plan_guard.py — Strict Plan Mode Tool Filtering
==========================================================
When Plan Mode is active, the tool list passed to Claude is filtered so
only read-only / non-destructive tools remain.  This is a clean tool-list
filter (not an execution-time block), so Claude never sees write/execute
tools and won't attempt to call them.

Design principle: filter the list, don't block at execution time.
  - Cleaner conversation: no confusing error tool_results.
  - Model can still plan how it would use write tools; it just can't call them.
  - Yolo Mode overrides Plan Mode entirely (handled in yolo.py).

Usage:
    from core.yang.plan_guard import filter_tools_for_plan_mode, READ_ONLY_TOOLS

    if yang_config.plan_mode and not yang_config.yolo_mode:
        tools = filter_tools_for_plan_mode(tools)
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


# ─── Read-only tool allowlist ─────────────────────────────────────────────────
#
# These tools are safe in Plan Mode: they read, search, fetch, or analyse
# data but cannot create, modify, or delete files/records.
#
# Tool search entries (type field prefix "tool_search_tool_") are also
# always allowed because they're meta-operations on the tool catalog.

READ_ONLY_TOOLS: frozenset = frozenset({
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

    # ── Technical analysis (read-only computations) ───────────────────────
    "technical_analysis",
    "backtest_strategy",           # read-only simulation, no DB writes
    "pattern_recognition",

    # ── AFL / code explanation (no execution) ─────────────────────────────
    "explain_afl_code",
    "validate_afl_code",

    # ── EDGAR / SEC data ──────────────────────────────────────────────────
    "edgar_search",
    "edgar_get_filings",
    "edgar_get_xbrl",
    "edgar_get_company_facts",

    # ── Knowledge base lookups ────────────────────────────────────────────
    "search_brain",
    "get_training_examples",

    # ── Research & analysis (no side effects) ────────────────────────────
    "analyze_company",
    "get_peer_comparison",
    "get_strategy_analysis",

    # ── PPTX / DOCX analysis (read, no write) ────────────────────────────
    "analyze_pptx",
    "analyze_xlsx",
    "read_pptx",
})

# Tools that are always included even in plan mode because they're
# meta/utility: tool search catalog entries, thinking tools, etc.
_TYPE_PREFIXES_ALWAYS_ALLOWED: tuple = (
    "tool_search_tool_",   # Anthropic tool-search catalog entries
)


# ─── Public API ───────────────────────────────────────────────────────────────

def filter_tools_for_plan_mode(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Return only the read-only subset of tools for Plan Mode.

    Any tool whose name is in READ_ONLY_TOOLS passes through.
    Any tool whose 'type' field starts with a known meta-type prefix also passes.
    Everything else is filtered out.

    Args:
        tools: Full tool list from get_all_tools() or get_tools_for_api().

    Returns:
        Filtered list. Never raises — if tools is empty or None, returns [].
    """
    if not tools:
        return []

    allowed: List[Dict[str, Any]] = []
    removed_names: List[str] = []

    for tool in tools:
        tool_name: str = tool.get("name", "")
        tool_type: str = tool.get("type", "")

        # Always pass meta/tool-search entries through
        if any(tool_type.startswith(pfx) for pfx in _TYPE_PREFIXES_ALWAYS_ALLOWED):
            allowed.append(tool)
            continue

        if tool_name in READ_ONLY_TOOLS:
            allowed.append(tool)
        else:
            removed_names.append(tool_name or f"<unnamed:{tool_type}>")

    if removed_names:
        logger.debug(
            "plan_mode: filtered out %d tools: %s",
            len(removed_names),
            removed_names[:10],  # log first 10 to keep it readable
        )

    logger.info(
        "plan_mode: %d/%d tools allowed",
        len(allowed),
        len(tools),
    )
    return allowed


def is_plan_mode_blocked(tool_name: str) -> bool:
    """
    Return True if this tool is blocked in Plan Mode.
    Useful for generating informative error messages if needed.
    """
    return tool_name not in READ_ONLY_TOOLS


def get_plan_mode_summary() -> Dict[str, Any]:
    """
    Return a summary of what Plan Mode restricts.
    Useful for the /yang/status endpoint.
    """
    return {
        "allowed_tool_count": len(READ_ONLY_TOOLS),
        "description": (
            "Plan Mode restricts Claude to read-only tools only. "
            "Write, execute, and generate tools are hidden from Claude's "
            "tool list so it can explore and plan without making changes."
        ),
        "allowed_categories": [
            "Web search",
            "Market & financial data",
            "Technical analysis",
            "AFL code explanation",
            "SEC EDGAR lookups",
            "Knowledge base search",
            "Document analysis (read only)",
        ],
        "blocked_categories": [
            "AFL code generation & execution",
            "Python sandbox execution",
            "Document generation (PPTX, DOCX, XLSX)",
            "File uploads & storage",
            "Database writes",
        ],
    }
