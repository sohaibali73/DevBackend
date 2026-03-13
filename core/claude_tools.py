"""
Claude Tools - Optimized Tool System for Claude API
====================================================

This module provides a modern, efficient tool system designed for:
- Claude's native tool format
- Built-in web search (web_search_20250305)
- Response streaming support
- Token usage tracking and cost estimation
- Result caching for performance

Key improvements over legacy tools.py:
1. Cleaner tool definitions with registry pattern
2. Built-in web search instead of Tavily fallback
3. Proper token tracking and cost estimation
4. Result caching with configurable TTL
5. Better error handling
"""

import json
import logging
import os
import time
import asyncio
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from functools import lru_cache

logger = logging.getLogger(__name__)

# ============================================================================
# COST TRACKING (Claude pricing as of 2025)
# ============================================================================

MODEL_COSTS = {
    "claude-sonnet-4-20250514": {
        "input": 3.00,      # $3 per million input tokens
        "output": 15.00,    # $15 per million output tokens
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-opus-4-20250514": {
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50,
    },
    "claude-3-5-sonnet-20241022": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
}


@dataclass
class TokenUsage:
    """Track token usage for a request."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens
    
    def estimated_cost(self, model: str) -> float:
        """Estimate cost in dollars."""
        costs = MODEL_COSTS.get(model, MODEL_COSTS["claude-sonnet-4-20250514"])
        return (
            (self.input_tokens / 1_000_000) * costs["input"] +
            (self.output_tokens / 1_000_000) * costs["output"] +
            (self.cache_write_tokens / 1_000_000) * costs.get("cache_write", 0) +
            (self.cache_read_tokens / 1_000_000) * costs.get("cache_read", 0)
        )


@dataclass
class ToolResult:
    """Result from a tool execution."""
    success: bool
    data: Any
    error: Optional[str] = None
    cache_hit: bool = False
    execution_time_ms: float = 0


# ============================================================================
# TOOL DEFINITION
# ============================================================================

@dataclass
class ToolDefinition:
    """Definition of a Claude tool."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Optional[Callable] = None
    cache_ttl_seconds: int = 300  # 5 min default
    
    def to_claude_format(self) -> Dict[str, Any]:
        """Convert to Claude API format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


# ============================================================================
# TOOL REGISTRY
# ============================================================================

class ToolRegistry:
    """
    Registry for Claude tools with caching support.
    
    Usage:
        registry = ToolRegistry()
        
        @registry.tool(
            name="get_stock_price",
            description="Get current stock price",
            input_schema={...}
        )
        async def get_stock_price(symbol: str) -> dict:
            return {"price": 100.0}
        
        # Get tool definitions for API
        tools = registry.get_tool_definitions()
        
        # Execute a tool
        result = await registry.execute("get_stock_price", {"symbol": "AAPL"})
    """
    
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._cache: Dict[str, tuple] = {}  # (result, timestamp)
    
    def tool(
        self, 
        name: str, 
        description: str,
        input_schema: Dict[str, Any],
        cache_ttl: int = 300,
    ) -> Callable:
        """Decorator to register a tool."""
        def decorator(func: Callable) -> Callable:
            self._tools[name] = ToolDefinition(
                name=name,
                description=description,
                input_schema=input_schema,
                handler=func,
                cache_ttl_seconds=cache_ttl,
            )
            return func
        return decorator
    
    def register(self, tool_def: ToolDefinition) -> None:
        """Register a tool definition directly."""
        self._tools[tool_def.name] = tool_def
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get all tool definitions in Claude API format."""
        return [t.to_claude_format() for t in self._tools.values()]
    
    def get_tool_names(self) -> List[str]:
        """Get all registered tool names."""
        return list(self._tools.keys())
    
    async def execute(
        self, 
        tool_name: str, 
        tool_input: Dict[str, Any],
        use_cache: bool = True,
        **kwargs,
    ) -> ToolResult:
        """
        Execute a tool with caching support.
        
        Args:
            tool_name: Name of the tool
            tool_input: Input parameters
            use_cache: Whether to use cached results
            **kwargs: Additional args passed to handler
            
        Returns:
            ToolResult with success status and data
        """
        tool = self._tools.get(tool_name)
        if not tool or not tool.handler:
            return ToolResult(
                success=False,
                data=None,
                error=f"Unknown tool: {tool_name}",
            )
        
        # Check cache
        cache_key = f"{tool_name}:{json.dumps(tool_input, sort_keys=True, default=str)}"
        if use_cache and tool.cache_ttl_seconds > 0:
            cached = self._cache.get(cache_key)
            if cached:
                result, timestamp = cached
                if time.time() - timestamp < tool.cache_ttl_seconds:
                    logger.debug(f"Cache hit for {tool_name}")
                    return ToolResult(
                        success=True,
                        data=result,
                        cache_hit=True,
                    )
        
        # Execute tool
        start_time = time.time()
        try:
            # Merge kwargs into tool_input for handler
            handler_kwargs = {**tool_input, **kwargs}
            
            if asyncio.iscoroutinefunction(tool.handler):
                result = await tool.handler(**handler_kwargs)
            else:
                result = tool.handler(**handler_kwargs)
            
            execution_time = (time.time() - start_time) * 1000
            
            # Cache result
            if use_cache and tool.cache_ttl_seconds > 0:
                self._cache[cache_key] = (result, time.time())
            
            return ToolResult(
                success=True,
                data=result,
                execution_time_ms=execution_time,
            )
            
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return ToolResult(
                success=False,
                data=None,
                error=str(e),
            )
    
    def clear_cache(self) -> None:
        """Clear all cached results."""
        self._cache.clear()


# Global registry
registry = ToolRegistry()


# ============================================================================
# WEB SEARCH TOOL (Claude Native)
# ============================================================================

WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 5,
}


# ============================================================================
# PYTHON EXECUTION TOOL
# ============================================================================

@registry.tool(
    name="execute_python",
    description="Execute Python code for calculations, data analysis, or generating formulas. The code runs in a sandboxed environment with access to common libraries like math, statistics, numpy, pandas. Use this for complex calculations, backtesting logic, or data processing.",
    input_schema={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute. Must be safe and computational (no file I/O, network, or system calls)."
            },
            "description": {
                "type": "string",
                "description": "Brief description of what the code does"
            }
        },
        "required": ["code"]
    },
    cache_ttl=0,  # Don't cache code execution
)
async def execute_python(code: str, description: str = "") -> Dict[str, Any]:
    """
    Execute Python code in a sandboxed environment.
    
    Security: No file I/O, network, subprocess, or system calls.
    Libraries: math, statistics, numpy, pandas, datetime
    """
    # Safe built-ins
    safe_builtins = {
        "abs": abs, "all": all, "any": any, "bool": bool,
        "dict": dict, "enumerate": enumerate, "filter": filter,
        "float": float, "format": format, "int": int, "len": len,
        "list": list, "map": map, "max": max, "min": min,
        "pow": pow, "range": range, "reversed": reversed,
        "round": round, "set": set, "slice": slice, "sorted": sorted,
        "str": str, "sum": sum, "tuple": tuple, "zip": zip,
        "print": print, "True": True, "False": False, "None": None,
        "isinstance": isinstance, "type": type,
        "ValueError": ValueError, "TypeError": TypeError,
        "KeyError": KeyError, "IndexError": IndexError,
    }
    
    # Safe modules
    safe_globals = {"__builtins__": safe_builtins}
    
    try:
        import math
        import statistics
        safe_globals["math"] = math
        safe_globals["statistics"] = statistics
    except ImportError:
        pass
    
    try:
        import numpy as np
        safe_globals["np"] = np
        safe_globals["numpy"] = np
    except ImportError:
        pass
    
    try:
        import pandas as pd
        safe_globals["pd"] = pd
        safe_globals["pandas"] = pd
    except ImportError:
        pass
    
    try:
        from datetime import datetime, timedelta
        safe_globals["datetime"] = datetime
        safe_globals["timedelta"] = timedelta
    except ImportError:
        pass
    
    # Security check - block dangerous operations
    dangerous = [
        "import os", "import sys", "import subprocess", "import shutil",
        "exec(", "eval(", "open(", "__import__",
        "os.", "sys.", "subprocess.", "shutil.",
        "requests.", "urllib.", "socket.",
        "compile(", "globals()", "locals()",
    ]
    
    code_lower = code.lower()
    for keyword in dangerous:
        if keyword.lower() in code_lower:
            return {
                "success": False,
                "error": f"Unsafe operation detected: {keyword}",
            }
    
    # Execute
    local_vars = {}
    try:
        exec(code, safe_globals, local_vars)
        result = local_vars.get("result", local_vars.get("output", "Code executed successfully"))
        
        return {
            "success": True,
            "output": str(result),
            "variables": {k: str(v)[:200] for k, v in local_vars.items() if not k.startswith("_")},
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


# ============================================================================
# STOCK DATA TOOL
# ============================================================================

@registry.tool(
    name="get_stock_data",
    description="Fetch real-time or historical stock market data for a given ticker symbol. Results are cached for 5 minutes for faster responses.",
    input_schema={
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Stock ticker symbol (e.g., 'AAPL', 'GOOGL')"
            },
            "period": {
                "type": "string",
                "enum": ["1d", "5d", "1mo", "3mo", "6mo", "1y"],
                "default": "1mo"
            },
            "info_type": {
                "type": "string",
                "enum": ["price", "history", "info"],
                "default": "price"
            }
        },
        "required": ["symbol"]
    },
    cache_ttl=300,  # 5 minute cache
)
async def get_stock_data(
    symbol: str, 
    period: str = "1mo", 
    info_type: str = "price"
) -> Dict[str, Any]:
    """Fetch stock market data using yfinance."""
    try:
        import yfinance as yf
        
        ticker = yf.Ticker(symbol.upper())
        
        if info_type == "price":
            info = ticker.info
            return {
                "success": True,
                "symbol": symbol.upper(),
                "data": {
                    "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                    "previous_close": info.get("previousClose"),
                    "open": info.get("open") or info.get("regularMarketOpen"),
                    "day_high": info.get("dayHigh"),
                    "day_low": info.get("dayLow"),
                    "volume": info.get("volume") or info.get("regularMarketVolume"),
                    "market_cap": info.get("marketCap"),
                    "name": info.get("longName") or info.get("shortName"),
                }
            }
        
        elif info_type == "history":
            hist = ticker.history(period=period)
            if hist.empty:
                return {"success": False, "error": f"No data for {symbol}"}
            
            return {
                "success": True,
                "symbol": symbol.upper(),
                "period": period,
                "data": [
                    {
                        "date": date.strftime("%Y-%m-%d"),
                        "open": round(float(row["Open"]), 2),
                        "high": round(float(row["High"]), 2),
                        "low": round(float(row["Low"]), 2),
                        "close": round(float(row["Close"]), 2),
                        "volume": int(row["Volume"]),
                    }
                    for date, row in hist.tail(30).iterrows()
                ]
            }
        
        elif info_type == "info":
            info = ticker.info
            return {
                "success": True,
                "symbol": symbol.upper(),
                "data": {
                    "name": info.get("longName"),
                    "sector": info.get("sector"),
                    "industry": info.get("industry"),
                    "description": (info.get("longBusinessSummary") or "")[:500],
                    "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
                    "dividend_yield": info.get("dividendYield"),
                    "beta": info.get("beta"),
                    "52week_high": info.get("fiftyTwoWeekHigh"),
                    "52week_low": info.get("fiftyTwoWeekLow"),
                    "market_cap": info.get("marketCap"),
                }
            }
        
    except ImportError:
        return {"success": False, "error": "yfinance library not installed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# KNOWLEDGE BASE SEARCH TOOL
# ============================================================================

@registry.tool(
    name="search_knowledge_base",
    description="Search the user's uploaded documents and knowledge base for relevant information about AFL, trading strategies, indicators, or any uploaded content.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query to find relevant documents"
            },
            "category": {
                "type": "string",
                "enum": ["afl", "strategy", "indicator", "general"],
                "description": "Optional category filter"
            },
            "limit": {
                "type": "integer",
                "default": 3,
                "description": "Maximum results to return"
            }
        },
        "required": ["query"]
    },
    cache_ttl=600,  # 10 minute cache
)
async def search_knowledge_base(
    query: str,
    category: Optional[str] = None,
    limit: int = 3,
    supabase_client=None,
) -> Dict[str, Any]:
    """Search knowledge base documents using full-text search."""
    if supabase_client is None:
        return {
            "success": False,
            "error": "Database not available",
            "results": [],
        }
    
    try:
        # Build query
        db_query = supabase_client.table("brain_documents").select(
            "id, title, category, summary, tags"
        )
        
        if category:
            db_query = db_query.eq("category", category)
        
        # Use full-text search on search_vector
        db_query = db_query.text_search("search_vector", query)
        
        result = db_query.limit(limit).execute()
        
        return {
            "success": True,
            "query": query,
            "results_count": len(result.data or []),
            "results": result.data or [],
        }
        
    except Exception as e:
        logger.error(f"KB search error: {e}")
        return {
            "success": False,
            "error": str(e),
            "results": [],
        }


# ============================================================================
# TECHNICAL ANALYSIS TOOL
# ============================================================================

@registry.tool(
    name="technical_analysis",
    description="Perform comprehensive technical analysis on a stock including RSI, MACD, moving averages, support/resistance levels, and overall signal.",
    input_schema={
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Stock ticker symbol"
            },
            "period": {
                "type": "string",
                "enum": ["1mo", "3mo", "6mo", "1y"],
                "default": "3mo"
            }
        },
        "required": ["symbol"]
    },
    cache_ttl=300,
)
async def technical_analysis(symbol: str, period: str = "3mo") -> Dict[str, Any]:
    """Perform technical analysis on a stock."""
    try:
        import yfinance as yf
        import numpy as np
        
        ticker = yf.Ticker(symbol.upper())
        hist = ticker.history(period=period)
        
        if hist.empty or len(hist) < 20:
            return {"success": False, "error": f"Insufficient data for {symbol}"}
        
        closes = hist["Close"].values.astype(float)
        highs = hist["High"].values.astype(float)
        lows = hist["Low"].values.astype(float)
        
        # RSI (14-period)
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-14:])
        avg_loss = np.mean(losses[-14:])
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        rsi = round(100 - (100 / (1 + rs)), 2)
        
        # Simple Moving Averages
        sma20 = round(float(np.mean(closes[-20:])), 2)
        sma50 = round(float(np.mean(closes[-50:]))) if len(closes) >= 50 else None
        current_price = round(float(closes[-1]), 2)
        
        # Bollinger Bands
        std20 = np.std(closes[-20:])
        bb_upper = round(float(sma20 + 2 * std20), 2)
        bb_lower = round(float(sma20 - 2 * std20), 2)
        
        # Support/Resistance
        recent_lows = sorted(lows[-20:])[:3]
        recent_highs = sorted(highs[-20:], reverse=True)[:3]
        
        # Overall signal
        bullish = 0
        bearish = 0
        
        if rsi < 30:
            bullish += 1  # Oversold
        elif rsi > 70:
            bearish += 1  # Overbought
        
        if current_price > sma20:
            bullish += 1
        else:
            bearish += 1
        
        if sma50 and current_price > sma50:
            bullish += 1
        elif sma50:
            bearish += 1
        
        if bullish > bearish + 1:
            signal = "bullish"
        elif bearish > bullish + 1:
            signal = "bearish"
        else:
            signal = "neutral"
        
        return {
            "success": True,
            "symbol": symbol.upper(),
            "current_price": current_price,
            "analysis": {
                "rsi": rsi,
                "sma20": sma20,
                "sma50": sma50,
                "bollinger_bands": {"upper": bb_upper, "middle": sma20, "lower": bb_lower},
                "support_levels": [round(float(l), 2) for l in recent_lows],
                "resistance_levels": [round(float(h), 2) for h in recent_highs],
            },
            "signal": signal,
            "signal_strength": max(bullish, bearish) / 4 * 100,
        }
        
    except ImportError:
        return {"success": False, "error": "Required libraries not installed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# AFL VALIDATION TOOL
# ============================================================================

@registry.tool(
    name="validate_afl",
    description="Validate AFL (AmiBroker Formula Language) code for syntax errors and common issues.",
    input_schema={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "AFL code to validate"
            }
        },
        "required": ["code"]
    },
    cache_ttl=0,
)
async def validate_afl(code: str) -> Dict[str, Any]:
    """Validate AFL code syntax."""
    try:
        from core.afl_validator import AFLValidator
        
        validator = AFLValidator()
        result = validator.validate(code)
        
        return {
            "success": True,
            "is_valid": result.is_valid,
            "errors": result.errors + result.color_issues + result.function_issues,
            "warnings": result.warnings + result.reserved_word_issues,
            "line_count": len(code.split("\n")),
        }
    except ImportError:
        # Fallback basic validation
        errors = []
        warnings = []
        
        # Check for common issues
        if "Buy =" not in code and "Sell =" not in code:
            warnings.append("No Buy/Sell signals defined")
        
        if "Plot(" not in code and "PlotShapes(" not in code:
            warnings.append("No Plot statements - consider adding visualization")
        
        # Check for unmatched brackets
        open_brackets = code.count("{") - code.count("}")
        if open_brackets != 0:
            errors.append(f"Unmatched curly brackets: {open_brackets} extra {'{' if open_brackets > 0 else '}' }")
        
        return {
            "success": True,
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "line_count": len(code.split("\n")),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# CREATE CHART TOOL
# ============================================================================

@registry.tool(
    name="create_chart",
    description="Create a data visualization chart. Returns structured data for rendering interactive charts. Supports bar, line, area, pie, and scatter charts.",
    input_schema={
        "type": "object",
        "properties": {
            "chart_type": {
                "type": "string",
                "enum": ["bar", "horizontal_bar", "line", "area", "pie", "donut", "scatter"],
                "description": "Type of chart to create"
            },
            "title": {
                "type": "string",
                "description": "Chart title"
            },
            "data": {
                "type": "array",
                "description": "Array of data points with 'label' and 'value' keys",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "value": {"type": "number"}
                    }
                }
            }
        },
        "required": ["chart_type", "title", "data"]
    },
    cache_ttl=0,
)
async def create_chart(chart_type: str, title: str, data: List[Dict]) -> Dict[str, Any]:
    """Create chart data for frontend rendering."""
    if not data:
        return {"success": False, "error": "No data provided"}
    
    # Normalize data format
    normalized = []
    for i, item in enumerate(data):
        if isinstance(item, dict):
            normalized.append({
                "label": str(item.get("label", item.get("name", f"Item {i+1}"))),
                "value": float(item.get("value", item.get("y", 0))),
            })
        elif isinstance(item, (int, float)):
            normalized.append({
                "label": f"Item {i+1}",
                "value": float(item),
            })
    
    # Calculate stats
    values = [d["value"] for d in normalized]
    
    return {
        "success": True,
        "tool": "create_chart",
        "chart_type": chart_type,
        "title": title,
        "data": normalized,
        "summary": {
            "total": round(sum(values), 2),
            "average": round(sum(values) / len(values), 2) if values else 0,
            "min": round(min(values), 2) if values else 0,
            "max": round(max(values), 2) if values else 0,
            "count": len(normalized),
        }
    }


# ============================================================================
# WEATHER TOOL
# ============================================================================

@registry.tool(
    name="get_weather",
    description="Get current weather conditions and forecast for a location.",
    input_schema={
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "City name or location (e.g., 'New York', 'London, UK')"
            },
            "units": {
                "type": "string",
                "enum": ["metric", "imperial"],
                "default": "imperial"
            }
        },
        "required": ["location"]
    },
    cache_ttl=1800,  # 30 minute cache
)
async def get_weather(location: str, units: str = "imperial") -> Dict[str, Any]:
    """Get weather data using wttr.in (free, no API key).""" 
    try:
        import urllib.request
        import urllib.parse
        
        encoded = urllib.parse.quote(location)
        url = f"https://wttr.in/{encoded}?format=j1"
        
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        
        current = data.get("current_condition", [{}])[0]
        
        if units == "metric":
            temp = int(current.get("temp_C", 0))
            temp_unit = "°C"
        else:
            temp = int(current.get("temp_F", 0))
            temp_unit = "°F"
        
        condition = current.get("weatherDesc", [{}])[0].get("value", "Unknown")
        
        return {
            "success": True,
            "location": location,
            "temperature": temp,
            "temp_unit": temp_unit,
            "condition": condition,
            "humidity": int(current.get("humidity", 0)),
            "wind_speed": int(current.get("windspeedMiles" if units == "imperial" else "windspeedKmph", 0)),
        }
        
    except Exception as e:
        return {"success": False, "error": f"Weather fetch failed: {str(e)}"}


# ============================================================================
# MARKET OVERVIEW TOOL
# ============================================================================

@registry.tool(
    name="get_market_overview",
    description="Get a comprehensive market overview including major indices (S&P 500, Nasdaq, Dow), VIX, gold, oil, and market sentiment.",
    input_schema={
        "type": "object",
        "properties": {}
    },
    cache_ttl=300,  # 5 minute cache
)
async def get_market_overview() -> Dict[str, Any]:
    """Get market overview data."""
    try:
        import yfinance as yf
        
        indices = {
            "S&P 500": "^GSPC",
            "Nasdaq": "^IXIC", 
            "Dow Jones": "^DJI",
            "VIX": "^VIX",
        }
        
        results = {}
        for name, symbol in indices.items():
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
                prev = info.get("previousClose", price)
                change = round(price - prev, 2) if price and prev else 0
                change_pct = round((change / prev) * 100, 2) if prev else 0
                
                results[name] = {
                    "price": round(price, 2),
                    "change": change,
                    "change_percent": change_pct,
                }
            except Exception:
                results[name] = {"price": 0, "change": 0, "change_percent": 0}
        
        # Determine sentiment
        sp500_change = results.get("S&P 500", {}).get("change_percent", 0)
        if sp500_change > 0.5:
            sentiment = "bullish"
        elif sp500_change < -0.5:
            sentiment = "bearish"
        else:
            sentiment = "neutral"
        
        return {
            "success": True,
            "indices": results,
            "sentiment": sentiment,
        }
        
    except ImportError:
        return {"success": False, "error": "yfinance not installed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry."""
    return registry


def get_all_tool_definitions() -> List[Dict[str, Any]]:
    """Get all tool definitions for Claude API."""
    return registry.get_tool_definitions()


def get_tool_names() -> List[str]:
    """Get all registered tool names."""
    return registry.get_tool_names()


async def execute_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    **kwargs,
) -> ToolResult:
    """Execute a tool by name."""
    return await registry.execute(tool_name, tool_input, **kwargs)


# ============================================================================
# STREAMING TOOL EXECUTION (NEW)
# ============================================================================

async def stream_tool_execution(
    tool_name: str,
    tool_input: Dict[str, Any],
    supabase_client=None,
    api_key: str = None,
) -> str:
    """
    Execute a tool and return the result as a JSON string for streaming.
    This is the new function that matches the streaming interface.
    """
    try:
        # Import the legacy tools module for compatibility
        from core.tools import handle_tool_call
        
        # Execute the tool using the legacy handler
        result = handle_tool_call(
            tool_name=tool_name,
            tool_input=tool_input,
            supabase_client=supabase_client,
            api_key=api_key,
        )
        
        # Return as JSON string (as expected by streaming interface)
        return result
        
    except Exception as e:
        logger.error(f"Streaming tool execution failed: {e}")
        return json.dumps({
            "success": False,
            "error": str(e),
            "tool": tool_name
        })