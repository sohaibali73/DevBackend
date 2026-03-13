"""Condensed prompts for efficient token usage in reverse engineering workflows."""


def get_condensed_clarification_prompt(query: str) -> str:
    """Get condensed clarification prompt for strategy analysis."""
    return f'''Analyze this trading strategy request and ask focused clarification questions.

Request: {query}

Ask 3-4 targeted questions to clarify:
1. Trading timeframe (daily/weekly/hourly/intraday)
2. Asset class (stocks/forex/crypto/commodities)
3. Risk tolerance (conservative/moderate/aggressive)
4. Entry/exit approach (technical/price-action/statistical)

Keep questions concise and actionable. Focus on specifics needed for code generation.
'''


def get_condensed_reverse_engineer_prompt(phase: str) -> str:
    """Get condensed prompt for reverse engineering based on current phase.
    
    Args:
        phase: Current phase ('clarification', 'findings', 'schematic', 'coding')
    
    Returns:
        Condensed system prompt for the phase
    """
    
    if phase == "clarification":
        return '''You are a trading strategy reverse engineer. 
        
Ask clarification questions to understand the strategy concept. 
Focus on: timeframe, entry/exit logic, indicators, risk management.
Be direct and concise. Ask only essential questions.'''
    
    elif phase == "findings":
        return '''Synthesize research into actionable strategy components.
        
Provide:
1. Key indicators to use
2. Entry conditions (specific triggers)
3. Exit conditions (targets and stops)
4. Risk management rules
5. Parameter ranges

Be specific and code-ready. Avoid vague descriptions.'''
    
    elif phase == "schematic":
        return '''Organize strategy into visual schematic format.

Define:
1. Entry signals (conditions + indicators)
2. Exit signals (conditions + indicators)
3. Filters (trend, volatility, time-based)
4. Risk parameters (position size, stop loss)

Output as structured JSON with clear logic flow.'''
    
    elif phase == "coding":
        return '''Generate production-ready AFL code from schematic.

Requirements:
1. All parameters use Param()/Optimize() pattern
2. Correct function signatures (RSI(14) not RSI(Close,14))
3. ExRem() for signal cleanup
4. _SECTION_BEGIN/_SECTION_END markers
5. SetTradeDelays() and portfolio settings
6. Plot() for visualization

Code must be backtestable immediately.'''
    
    else:
        return '''You are a trading strategy expert. Provide accurate, code-ready strategy analysis.
Focus on specific, implementable logic. Avoid vague concepts.'''


def get_condensed_afl_generation_prompt(strategy_name: str, research: str) -> str:
    """Get condensed prompt for AFL code generation.
    
    Args:
        strategy_name: Name of the strategy
        research: Research synthesis describing the strategy
    
    Returns:
        Condensed prompt for code generation
    """
    return f'''Generate complete AFL code for: {strategy_name}

Strategy Details: {research[:1500] if research else "Custom strategy"}

Requirements:
1. STANDALONE - include all sections (parameters, indicators, logic, plots)
2. Correct syntax: RSI(14), MA(Close, 20), not RSI(Close, 14)
3. All params use Optimize(): Optimize("Description", default, min, max, step)
4. Signal cleanup: Buy = ExRem(Buy, Sell); Sell = ExRem(Sell, Buy);
5. Realistic defaults for good backtest results
6. SetTradeDelays(), SetOption() for proper backtesting
7. Plot() statements for visualization

Output complete, immediately backtestable code.'''


def get_condensed_research_synthesis_prompt(query: str, research_context: str) -> str:
    """Get condensed prompt for synthesizing research findings.
    
    Args:
        query: Original strategy query
        research_context: Raw research data
    
    Returns:
        Condensed synthesis prompt
    """
    return f'''Synthesize research for trading strategy: {query}

Research Data: {research_context[:2000] if research_context else "No research available"}

Extract actionable components:
1. Indicators: Name, period, calculation
2. Entry: Specific conditions (e.g., "RSI < 30 AND MA crossover")
3. Exit: Specific targets (e.g., "RSI > 70 OR 2% stop loss")
4. Filters: Market regime, time-based, volatility
5. Parameters: Realistic ranges for optimization

Output as structured data, not narrative text.'''


def get_condensed_schematic_generation_prompt(strategy_info: str) -> str:
    """Get condensed prompt for strategy schematic generation.
    
    Args:
        strategy_info: Strategy information summary
    
    Returns:
        Condensed schematic prompt
    """
    return f'''Create schematic for: {strategy_info}

Output Mermaid flowchart showing:
1. Entry indicators → Entry conditions → BUY signal
2. Exit indicators → Exit conditions → SELL signal
3. Filters applied to both
4. Parameter connections

Use this exact format:
```mermaid
flowchart TD
    IND1["Indicator 1"] --> ENTRY{{"Entry Cond"}} --> BUY(["BUY"])
    IND2["Indicator 2"] --> ENTRY
    ENTRY --> EXIT{{"Exit Cond"}} --> SELL(["SELL"])
    style BUY fill:#22C55E,color:#fff
    style SELL fill:#EF4444,color:#fff
```

Also provide JSON summary with strategy_type, timeframe, indicators list.'''
