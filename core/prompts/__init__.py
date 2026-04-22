"""
Prompts module - exports all prompts for the AFL engine.

This module provides a clean interface to all prompt functions used throughout the application.
"""

# Import from base.py (primary source for base prompts)
from .base import (
    get_base_prompt,
    get_chat_prompt,
    FUNCTION_REFERENCE,
    RESERVED_KEYWORDS,
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



def get_generate_prompt(strategy_type: str = "standalone") -> str:
    """
    Get AFL generation prompt tailored to strategy type.

    Args:
        strategy_type: Either "standalone" or "composite"

    Returns:
        Prompt string for AFL generation
    """
    base = get_base_prompt()

    if strategy_type.lower() == "composite":
        return base + """

## COMPOSITE STRATEGY MODE

This is a COMPOSITE strategy module. Follow these specific rules:

1. **DO NOT** include backtest settings (SetOption, SetTradeDelays, PositionSize)
2. **DO NOT** include Plot() or PlotShapes() for visualization
3. **DO NOT** include AddColumn() or exploration output
4. **DO NOT** assign to Buy/Sell directly

Instead:
- Prefix ALL variables with a unique strategy identifier
- Use Buy[StrategyName], Sell[StrategyName] for signals
- Include only the core strategy logic and indicator calculations
- Document how to integrate with a master template
"""
    else:
        return base + """

## STANDALONE STRATEGY MODE

This is a STANDALONE strategy. Include ALL sections:

1. **Parameters Section** - Complete Param()/Optimize() structure
2. **Backtest Settings** - SetOption(), SetTradeDelays(), PositionSize
3. **Indicators** - All indicator calculations with proper naming
4. **Trading Logic** - Buy/Sell/Short/Cover signals
5. **Signal Cleanup** - ExRem() for all signals
6. **Visualization** - Plot() for indicators, PlotShapes() for signals
7. **Exploration** - AddColumn(), Filter for Analysis window

Generate a complete, production-ready strategy file.
"""


# Convenience aliases for common use cases
def get_afl_base_prompt() -> str:
    """Alias for get_base_prompt for backwards compatibility."""
    return get_base_prompt()


def get_afl_chat_prompt() -> str:
    """Alias for get_chat_prompt for backwards compatibility."""
    return get_chat_prompt()


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
    # Base prompts
    "get_base_prompt",
    "get_chat_prompt",
    "get_generate_prompt",
    "get_afl_system_prompt",
    "FUNCTION_REFERENCE",
    "RESERVED_KEYWORDS",
    "YANG_CAPABILITIES_PROMPT",

    # Aliases for backwards compatibility
    "get_afl_base_prompt",
    "get_afl_chat_prompt",
    
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
