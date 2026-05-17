"""
Prompts module - exports all prompts for the AFL engine.

This module provides a clean interface to all prompt functions used throughout the application.
"""

# Import from base.py (primary source for base prompts)
from .base import (
    build_afl_reference,
    get_base_prompt,
    get_chat_prompt,
    FUNCTION_REFERENCE,
    RESERVED_KEYWORDS,
    PARAM_OPTIMIZE_PATTERN,
    TIMEFRAME_RULES,
    CONDITIONAL_AND_SIGNAL_FUNCTIONS,
    PLOTTING_AND_SHAPES,
    EXPLORATION_FUNCTIONS,
    PARAMETER_FUNCTIONS,
    RISK_MANAGEMENT,
    COLOR_PALETTE,
    HOUSE_RULES,
    STANDALONE_TEMPLATE,
    COMPOSITE_TEMPLATE,
    YANG_CAPABILITIES_PROMPT,
)

# Import from afl.py (shim that fixes claude_engine.py import chain)
from .afl import get_afl_system_prompt

# Import from condensed_prompts.py (efficient token usage)
from .condensed_prompts import (
    get_condensed_clarification_prompt,
    get_condensed_reverse_engineer_prompt,
    get_condensed_afl_generation_prompt,
    get_condensed_research_synthesis_prompt,
    get_condensed_schematic_generation_prompt,
)


def get_clarification_prompt(query: str = "") -> str:
    """Get clarification prompt for strategy analysis."""
    return get_condensed_clarification_prompt(query)


def get_reverse_engineer_prompt(phase: str = "") -> str:
    """Get reverse engineer prompt for specified phase."""
    return get_condensed_reverse_engineer_prompt(phase)


def get_research_synthesis_prompt(query: str = "", research: str = "") -> str:
    """Get research synthesis prompt."""
    return get_condensed_research_synthesis_prompt(query, research)


def get_schematic_generation_prompt(strategy_info: str = "") -> str:
    """Get schematic generation prompt."""
    return get_condensed_schematic_generation_prompt(strategy_info)


def get_schematic_prompt(strategy_info: str = "") -> str:
    """Alias for get_schematic_generation_prompt for backwards compatibility."""
    return get_schematic_generation_prompt(strategy_info)


def get_findings_summary_prompt(findings: str = "") -> str:
    """Get findings summary prompt."""
    return f"""Summarize these strategy findings:

{findings}

Provide a concise summary with: key indicators, entry signals, exit signals, parameters."""


def get_backtest_analysis_prompt(results: str = "") -> str:
    """Get prompt for backtest analysis."""
    return f"""Analyze these backtest results:

{results}

Provide: performance metrics, key insights, optimization suggestions, risk assessment."""


# Export list - all publicly available functions and constants
__all__ = [
    # Canonical AFL accessor (single source of truth)
    "build_afl_reference",

    # Base prompts
    "get_base_prompt",
    "get_chat_prompt",
    "get_afl_system_prompt",

    # AFL reference constants (returned by get_afl_syntax_reference tool)
    "FUNCTION_REFERENCE",
    "RESERVED_KEYWORDS",
    "PARAM_OPTIMIZE_PATTERN",
    "TIMEFRAME_RULES",
    "CONDITIONAL_AND_SIGNAL_FUNCTIONS",
    "PLOTTING_AND_SHAPES",
    "EXPLORATION_FUNCTIONS",
    "PARAMETER_FUNCTIONS",
    "RISK_MANAGEMENT",
    "COLOR_PALETTE",
    "HOUSE_RULES",
    "STANDALONE_TEMPLATE",
    "COMPOSITE_TEMPLATE",
    "YANG_CAPABILITIES_PROMPT",

    # Condensed prompts
    "get_condensed_clarification_prompt",
    "get_condensed_reverse_engineer_prompt",
    "get_condensed_afl_generation_prompt",
    "get_condensed_research_synthesis_prompt",
    "get_condensed_schematic_generation_prompt",

    # Wrapper functions for compatibility
    "get_clarification_prompt",
    "get_reverse_engineer_prompt",
    "get_research_synthesis_prompt",
    "get_schematic_generation_prompt",
    "get_schematic_prompt",
    "get_findings_summary_prompt",
    "get_backtest_analysis_prompt",
]
