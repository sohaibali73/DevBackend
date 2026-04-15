"""
AFL prompt shim.

This file exists so that core/claude_engine.py can import from
'core.prompts.afl' without triggering its multi-path fallback chain.

All actual prompt content lives in core/prompts/base.py.
Edit base.py to improve the AFL system prompt.
"""

from .base import (
    get_base_prompt,
    get_chat_prompt,
    FUNCTION_REFERENCE,
    RESERVED_KEYWORDS,
    PARAM_OPTIMIZE_PATTERN,
    TIMEFRAME_RULES,
)

# Alias: some callers use get_afl_system_prompt
get_afl_system_prompt = get_base_prompt

__all__ = [
    "get_afl_system_prompt",
    "get_base_prompt",
    "get_chat_prompt",
    "FUNCTION_REFERENCE",
    "RESERVED_KEYWORDS",
    "PARAM_OPTIMIZE_PATTERN",
    "TIMEFRAME_RULES",
]
