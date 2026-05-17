"""
AFL prompt shim.

This file exists so that core/claude_engine.py can import from
'core.prompts.afl' without triggering its multi-path fallback chain.

All actual prompt content lives in core/prompts/base.py.
Edit base.py to improve the AFL system prompt.
"""

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
)

# Alias: some callers use get_afl_system_prompt
get_afl_system_prompt = get_base_prompt

__all__ = [
    "build_afl_reference",
    "get_afl_system_prompt",
    "get_base_prompt",
    "get_chat_prompt",
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
]
