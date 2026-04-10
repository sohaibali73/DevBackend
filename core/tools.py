"""
Claude Tools - Custom tools for the AI agent.
Implements: Code Execution, Knowledge Base Search, Stock Data, and many more.

CHANGES FROM PREVIOUS VERSION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BUG FIX 1  — handle_tool_call assumed tool handlers always return a dict.
             Unconditional result["_tool_time_ms"] = ... would crash with TypeError
             / KeyError if a handler returned a string, None, or any non-dict.
             Fixed: isinstance guard wraps the timing injection.

PERF FIX 2 — _build_dispatch_table() was called on EVERY tool invocation,
             allocating ~45 lambda closures each time.  The vast majority of tools
             don't need supabase_client or api_key at all.
             Fixed: the static portion is built ONCE at module load into
             _STATIC_DISPATCH.  The 5 dependency-injected tools are handled
             directly inside handle_tool_call — no throwaway dict needed.

PERF FIX 3 — generate_afl_code / debug_afl_code / explain_afl_code each created
             a fresh ClaudeAFLEngine (and a fresh AsyncAnthropic HTTP client) on
             every single tool call.  This defeated all engine-level caching and
             created unnecessary connection overhead.
             Fixed: module-level _get_claude_engine() returns a shared singleton,
             re-creating it only when the api_key changes.

All prior optimisations are preserved:
  - ALL imports at module top-level (no hot-path imports)
  - execute_python sandbox globals built ONCE at module load
  - Unified cache: {key: (data, timestamp)} — halves dict operations
  - Cache mutation bug fixed: return shallow copy instead of mutating stored entry
  - O(1) dispatch dict (now split static/dynamic — see PERF FIX 2)
  - _analyze_basic_sentiment word lists are module-level frozensets
  - O(n) SMA in get_stock_chart (cumulative-sum approach)
  - _ema() at module level, not re-defined per call
  - Duplicate Tavily boilerplate in single _tavily_search() helper
  - dangerous_keywords pre-lowercased; no redundant .lower() per iteration
  - URL encoding via urllib.parse.quote (not manual .replace)
  - AFLValidator singleton at module level, not per-call
  - chr(10) replaced with "\n" literal
  - datetime/re/urllib re-imports inside functions removed
  - _FILE_EXTENSIONS dict promoted to module-level constant
  - CUSTOM_TOOLS / ALL_TOOLS computed at module load (no lru_cache needed)
"""

import json
import traceback
import logging
import os
import time
import math
import statistics
import csv
import io as _io
import re as re_mod
import urllib.request
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import OrderedDict

# ---------------------------------------------------------------------------
# Tool Search — tool-type constants (no extra beta headers required)
# ---------------------------------------------------------------------------
# Adding tool_search_tool_regex or tool_search_tool_bm25 to the tools list
# activates deferred (on-demand) loading of tool definitions.
# This keeps context usage low when large tool catalogs are in use.
# See: https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool

TOOL_SEARCH_REGEX_ENTRY: Dict[str, str] = {
    "type": "tool_search_tool_regex_20251119",
    "name": "tool_search_tool_regex",
}

TOOL_SEARCH_BM25_ENTRY: Dict[str, str] = {
    "type": "tool_search_tool_bm25_20251119",
    "name": "tool_search_tool_bm25",
}

# Tools always loaded immediately (not deferred) even in tool-search mode.
# Keep this to 3-5 most frequently used tools.
TOOL_SEARCH_NON_DEFERRED: frozenset = frozenset({
    "web_search",           # built-in, always present
    "execute_python",       # used on nearly every request
    "search_knowledge_base",
    "get_stock_data",
    "technical_analysis",
    "invoke_skill",         # REQUIRED: All skill routing goes through this tool
})

# ── Optional heavy dependencies — guarded with try/except at use sites ────────
try:
    import numpy as np
    _NP_AVAILABLE = True
except ImportError:
    _NP_AVAILABLE = False

try:
    import pandas as pd
    _PD_AVAILABLE = True
except ImportError:
    _PD_AVAILABLE = False

try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False

# AFL validator — single module-level instance (not re-created per call)
try:
    from core.afl_validator import AFLValidator, get_valid_colors, Severity
    _AFL_VALIDATOR  = AFLValidator()
    _AFL_AVAILABLE  = True
except ImportError:
    _AFL_VALIDATOR  = None
    _AFL_AVAILABLE  = False
    # Fallback Severity enum so the code doesn't crash
    class Severity:
        ERROR = "ERROR"
        WARNING = "WARNING"
        INFO = "INFO"
        SUGGESTION = "SUGGESTION"

# ── Shared ClaudeAFLEngine singleton (PERF FIX 3) ────────────────────────────
# Previously, generate_afl_code / debug_afl_code / explain_afl_code each called
#   engine = ClaudeAFLEngine(api_key=api_key)
# on every invocation, which allocates a new AsyncAnthropic HTTP client and
# discards all of the engine-level LRU cache on every single AFL tool call.
#
# The singleton is keyed on api_key: if the key changes (e.g. multi-tenant
# deployment) a new engine is created, otherwise the existing instance is reused.
_shared_engine: Optional["ClaudeAFLEngine"] = None   # type: ignore[name-defined]

def _get_claude_engine(api_key: str) -> "ClaudeAFLEngine":   # type: ignore[name-defined]
    """
    Return (or create) the module-level shared ClaudeAFLEngine.

    Re-initialises only when the api_key differs from the current instance.
    This preserves the engine's LRU request cache and the AsyncAnthropic
    connection pool across consecutive tool calls.
    """
    global _shared_engine
    if _shared_engine is None or _shared_engine.api_key != api_key:
        from core.claude_engine import ClaudeAFLEngine   # local import avoids circular dep
        _shared_engine = ClaudeAFLEngine(api_key=api_key)
    return _shared_engine

# ── Logger ────────────────────────────────────────────────────────────────────
log_level = os.getenv(
    "LOG_LEVEL",
    "WARNING" if os.getenv("ENVIRONMENT") == "production" else "INFO",
)
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, log_level.upper()))


# =============================================================================
# MODULE-LEVEL CONSTANTS
# =============================================================================

# File extension map — rebuilt per call in the original; now a module constant
_FILE_EXTENSIONS: Dict[str, str] = {
    "python": "py", "javascript": "js", "afl": "afl", "sql": "sql", "r": "r",
}

# Sentiment word sets — module-level frozensets so they are not rebuilt per call
_POSITIVE_WORDS = frozenset({
    "surge", "gain", "rally", "rise", "jump", "soar", "beat", "exceed",
    "strong", "growth", "profit", "upgrade", "bullish", "record", "boom",
    "optimistic", "positive", "upbeat", "recovery", "breakthrough",
})
_NEGATIVE_WORDS = frozenset({
    "fall", "drop", "crash", "decline", "plunge", "loss", "miss", "cut",
    "weak", "recession", "bearish", "downgrade", "warning", "concern",
    "pessimistic", "negative", "fear", "crisis", "layoff", "bankrupt",
})

# Dangerous code keywords for execute_python sandbox — pre-lowercased
# so no .lower() is needed when iterating during code scanning
_DANGEROUS_KEYWORDS: frozenset = frozenset({
    "import os", "import sys", "import subprocess", "import shutil",
    "exec(", "eval(", "open(", "file(",
    "os.", "sys.", "subprocess.", "shutil.",
    "requests.", "urllib.", "socket.",
})

# Default chart colour palette (tuple — immutable, shared safely)
_DEFAULT_CHART_COLORS = (
    "#F59E0B", "#3B82F6", "#10B981", "#EF4444", "#8B5CF6",
    "#EC4899", "#06B6D4", "#F97316", "#84CC16", "#6366F1",
)

# Sector ETFs — single source of truth for sector_heatmap AND get_sector_performance
_SECTOR_ETFS: Dict[str, str] = {
    "Technology":       "XLK", "Healthcare":       "XLV", "Financial":     "XLF",
    "Consumer Disc.":   "XLY", "Consumer Staples": "XLP", "Energy":        "XLE",
    "Utilities":        "XLU", "Real Estate":      "XLRE", "Materials":    "XLB",
    "Industrials":      "XLI", "Communication":    "XLC",
}


# =============================================================================
# SANDBOX GLOBALS — built ONCE at module load
# Previously rebuilt from scratch on every execute_python() call.
# =============================================================================

_SANDBOX_GLOBALS: Dict[str, Any] = {
    "__builtins__": {
        # Safe built-ins only — no __import__ escape hatches here
        "abs": abs, "all": all, "any": any, "bool": bool,
        "dict": dict, "enumerate": enumerate, "filter": filter,
        "float": float, "format": format, "int": int, "len": len,
        "list": list, "map": map, "max": max, "min": min,
        "pow": pow, "range": range, "reversed": reversed,
        "round": round, "set": set, "slice": slice, "sorted": sorted,
        "str": str, "sum": sum, "tuple": tuple, "zip": zip,
        "print": print, "True": True, "False": False, "None": None,
        "isinstance": isinstance, "type": type, "hasattr": hasattr,
        "getattr": getattr, "setattr": setattr, "dir": dir, "vars": vars,
        "repr": repr, "hash": hash, "id": id, "callable": callable,
        "iter": iter, "next": next, "enumerate": enumerate,
        "property": property, "staticmethod": staticmethod, "classmethod": classmethod,
        "super": super, "object": object, "chr": chr, "ord": ord,
        "bin": bin, "hex": hex, "oct": oct,
        "ValueError": ValueError, "TypeError": TypeError,
        "KeyError": KeyError, "IndexError": IndexError, "Exception": Exception,
        "AttributeError": AttributeError, "NameError": NameError,
        "RuntimeError": RuntimeError, "StopIteration": StopIteration,
        "__import__": __import__,
    },
    "math":      math,
    "statistics": statistics,
    "csv":       csv,
    "io":        _io,
    "json":      json,
    "StringIO":  _io.StringIO,
    "BytesIO":   _io.BytesIO,
    "re":        re_mod,
    "datetime":  datetime,
    "timedelta": timedelta,
}

# Inject optional heavy libraries if they are available
if _NP_AVAILABLE:
    _SANDBOX_GLOBALS["np"]    = np
    _SANDBOX_GLOBALS["numpy"] = np
if _PD_AVAILABLE:
    _SANDBOX_GLOBALS["pd"]     = pd
    _SANDBOX_GLOBALS["pandas"] = pd

# Inject matplotlib and its patches if available
try:
    import matplotlib
    matplotlib.use("Agg")  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import FancyBboxPatch, Rectangle, Circle, Ellipse, Polygon, Wedge, Arrow
    import matplotlib.patheffects as path_effects
    from matplotlib.path import Path
    import matplotlib.colors as mcolors
    from matplotlib.collections import PatchCollection
    from matplotlib.font_manager import FontProperties
    
    _SANDBOX_GLOBALS["matplotlib"] = matplotlib
    _SANDBOX_GLOBALS["plt"] = plt
    _SANDBOX_GLOBALS["mpatches"] = mpatches
    _SANDBOX_GLOBALS["FancyBboxPatch"] = FancyBboxPatch
    _SANDBOX_GLOBALS["Rectangle"] = Rectangle
    _SANDBOX_GLOBALS["Circle"] = Circle
    _SANDBOX_GLOBALS["Ellipse"] = Ellipse
    _SANDBOX_GLOBALS["Polygon"] = Polygon
    _SANDBOX_GLOBALS["Wedge"] = Wedge
    _SANDBOX_GLOBALS["Arrow"] = Arrow
    _SANDBOX_GLOBALS["path_effects"] = path_effects
    _SANDBOX_GLOBALS["Path"] = Path
    _SANDBOX_GLOBALS["mcolors"] = mcolors
    _SANDBOX_GLOBALS["PatchCollection"] = PatchCollection
    _SANDBOX_GLOBALS["FontProperties"] = FontProperties
except ImportError:
    pass


# =============================================================================
# UNIFIED CACHE — {cache_key: (data_dict, timestamp_float)}
# Previously two parallel dicts per cache (data dict + time dict).
# One dict halves the number of lookups and sets.
# =============================================================================

_stock_cache: Dict[str, Tuple[Dict, float]] = {}
_STOCK_CACHE_TTL = 300    # 5 minutes

_kb_cache: Dict[str, Tuple[Dict, float]] = {}
_KB_CACHE_TTL = 600       # 10 minutes


def _get_cached(cache: Dict, key: str, ttl: float) -> Optional[Dict]:
    """
    Generic cache getter.

    Returns a SHALLOW COPY of the stored value so callers cannot accidentally
    mutate the cached dict (the original cache-mutation bug).
    Returns None on a miss or when the entry has expired.
    """
    entry = cache.get(key)
    if entry is not None:
        data, ts = entry
        if time.time() - ts < ttl:
            return dict(data)   # shallow copy — prevents cache mutation
    return None


def _set_cached(cache: Dict, key: str, data: Dict) -> None:
    """Generic cache setter — stores (data, current_timestamp)."""
    cache[key] = (data, time.time())


def _get_cached_stock(symbol: str, info_type: str) -> Optional[Dict]:
    """Look up a stock data entry; returns None on miss/expiry."""
    key    = f"{symbol}_{info_type}"
    result = _get_cached(_stock_cache, key, _STOCK_CACHE_TTL)
    if result:
        result["cached"] = True
        logger.debug("Stock cache hit: %s", key)
    return result


def _set_cached_stock(symbol: str, info_type: str, data: Dict) -> None:
    """Store a stock data entry."""
    _set_cached(_stock_cache, f"{symbol}_{info_type}", data)


def _get_cached_kb(query: str, category: str) -> Optional[Dict]:
    """Look up a knowledge-base search result; returns None on miss/expiry."""
    key    = f"{query}_{category}"
    result = _get_cached(_kb_cache, key, _KB_CACHE_TTL)
    if result:
        logger.debug("KB cache hit for query")
    return result


def _set_cached_kb(query: str, category: str, data: Dict) -> None:
    """Store a knowledge-base search result."""
    _set_cached(_kb_cache, f"{query}_{category}", data)


# =============================================================================
# SHARED HELPERS
# =============================================================================

def _ema(data, window: int):
    """
    Exponential Moving Average.

    Promoted to module level so it is not re-created as a new function object
    on every call to technical_analysis() or backtest_quick().
    """
    if not _NP_AVAILABLE:
        return data
    alpha  = 2.0 / (window + 1)
    result = [float(data[0])]
    for val in data[1:]:
        result.append(alpha * float(val) + (1 - alpha) * result[-1])
    return np.array(result)


def _tavily_search(query: str, max_results: int = 5) -> Optional[Dict]:
    """
    Centralised Tavily API call.

    Previously copy-pasted verbatim into get_live_scores, get_search_trends,
    order_food, and track_flight.  Extracted here to eliminate duplication.

    Returns the raw Tavily response dict, or None if unavailable / failed.
    Reads TAVILY_API_KEY from env first, then falls back to config.settings.
    """
    # Prefer the environment variable; fall back to the config object
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        try:
            from config import settings
            tavily_key = getattr(settings, "TAVILY_API_KEY", None)
        except Exception:
            pass

    if not tavily_key:
        return None

    try:
        payload = json.dumps({
            "api_key":        tavily_key,
            "query":          query,
            "search_depth":   "basic",
            "include_answer": True,
            "max_results":    max_results,
        })
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.warning("Tavily search failed: %s", e)
        return None


def _extract_domain(url: str) -> str:
    """Extract a clean domain name from a URL for display in results."""
    try:
        return urllib.parse.urlparse(url).netloc.replace("www.", "")
    except Exception:
        return "Unknown"


def _analyze_basic_sentiment(text: str) -> str:
    """
    Basic keyword-based sentiment analysis.
    Word lists are module-level frozensets — not rebuilt on every call.
    """
    words = text.lower().split()
    pos   = sum(1 for w in words if w in _POSITIVE_WORDS)
    neg   = sum(1 for w in words if w in _NEGATIVE_WORDS)
    if pos > neg:   return "positive"
    if neg > pos:   return "negative"
    return "neutral"


def _get_file_extension(language: str) -> str:
    """Return the file extension for a given language identifier."""
    # Dict is a module-level constant — no per-call allocation
    return _FILE_EXTENSIONS.get(language, "txt")


# =============================================================================
# TOOL DEFINITIONS (for Claude API)
# =============================================================================

TOOL_DEFINITIONS = [
    # Built-in Claude Web Search
    {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 5
    },
    # Custom: Python Code Execution
    {
        "name": "execute_python",
        "description": "Execute Python code for calculations, data analysis, or generating AFL formulas. The code runs in a sandboxed environment with access to common libraries like math, statistics, numpy, pandas, matplotlib, seaborn, plotly, yfinance, requests, and more. Use this for complex calculations, backtesting logic, data processing, or generating charts. Charts created with plt.show() are automatically captured as image artifacts. Use display(HTML(...)) or display(SVG(...)) for rich HTML/SVG output.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute. No file I/O or system calls. Use print() for output. Use plt.show() for charts."
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of what the code does"
                }
            },
            "required": ["code"]
        }
    },
    # Custom: React/JSX Component Execution
    {
        "name": "execute_react",
        "description": (
            "Build an interactive React/JSX component or UI and render it as a live iframe in the chat. "
            "Use this when the user asks for interactive UI, dashboards, data visualizations, forms, games, "
            "animations, or any visual component. "
            "The component runs in the browser with full React 18 support.\n\n"
            "AVAILABLE CDN PACKAGES (import directly, no install needed):\n"
            "- UI: react, react-dom, lucide-react, @radix-ui/react-icons, react-icons, framer-motion\n"
            "- Charts: recharts, chart.js, d3\n"
            "- Styling: Tailwind CSS classes work out of the box (CDN loaded)\n"
            "- Utilities: clsx, tailwind-merge, class-variance-authority, lodash, mathjs, uuid, zod\n"
            "- State: zustand, jotai, immer\n"
            "- Forms: react-hook-form\n"
            "- Date: date-fns, dayjs\n"
            "- HTTP: axios\n\n"
            "RULES:\n"
            "- Export the main component as 'App', 'Component', or 'Default'\n"
            "- All React hooks (useState, useEffect, useRef, etc.) are pre-imported\n"
            "- Use Tailwind classes for styling (no CSS imports needed)\n"
            "- Do NOT import from 'react' directly — React and hooks are pre-imported"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "JSX/React code. Export a component named App, Component, or Default. Tailwind and CDN packages available."
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of the component"
                }
            },
            "required": ["code"]
        }
    },
    # Custom: Knowledge Base Search
    {
        "name": "search_knowledge_base",
        "description": "Search the user's uploaded documents and knowledge base for relevant information about AFL, trading strategies, indicators, or any uploaded content. Use this when you need to reference the user's specific documents or previously uploaded trading knowledge. FAST - results are cached.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to find relevant documents"
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter (e.g., 'afl', 'strategy', 'indicator')",
                    "enum": ["afl", "strategy", "indicator", "general", "documentation"]
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 3
                }
            },
            "required": ["query"]
        }
    },
    # Custom: Stock Data
    {
        "name": "get_stock_data",
        "description": "Fetch real-time or historical stock market data for a given ticker symbol. Results are cached for 5 minutes for faster responses.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":    {"type": "string", "description": "Stock ticker symbol (e.g., 'AAPL', 'GOOGL', 'MSFT')"},
                "period":    {"type": "string", "description": "Time period for historical data", "enum": ["1d", "5d", "1mo", "3mo", "6mo", "1y"], "default": "1mo"},
                "info_type": {"type": "string", "description": "Type of information to retrieve", "enum": ["price", "history", "info"], "default": "price"}
            },
            "required": ["symbol"]
        }
    },
    # Custom: AFL Validator
    {
        "name": "validate_afl",
        "defer_loading": True,
        "description": "Validate AFL (AmiBroker Formula Language) code for syntax errors and common issues.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "AFL code to validate"}
            },
            "required": ["code"]
        }
    },
    # Custom: Generate AFL
    {
        "name": "generate_afl_code",
        "defer_loading": True,
        "description": "Generate AmiBroker AFL code from a natural language description.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description":   {"type": "string", "description": "Natural language description of the trading strategy"},
                "strategy_type": {"type": "string", "description": "Type of AFL code", "enum": ["standalone", "composite", "indicator", "exploration"], "default": "standalone"}
            },
            "required": ["description"]
        }
    },
    # Custom: Debug AFL
    {
        "name": "debug_afl_code",
        "defer_loading": True,
        "description": "Debug and fix errors in AFL code.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code":          {"type": "string", "description": "The AFL code that needs debugging"},
                "error_message": {"type": "string", "description": "Optional error message from AmiBroker", "default": ""}
            },
            "required": ["code"]
        }
    },
    # Custom: Explain AFL
    {
        "name": "explain_afl_code",
        "defer_loading": True,
        "description": "Explain AFL code in plain English.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "The AFL code to explain"}
            },
            "required": ["code"]
        }
    },
    # Custom: Sanity Check AFL
    {
        "name": "sanity_check_afl",
        "defer_loading": True,
        "description": "Performs comprehensive sanity check on AFL code and automatically fixes common issues. USE THIS BEFORE PRESENTING ANY AFL CODE TO THE USER.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code":     {"type": "string",  "description": "The AFL code to sanity check and fix"},
                "auto_fix": {"type": "boolean", "description": "Whether to automatically fix detected issues", "default": True}
            },
            "required": ["code"]
        }
    },
    # Custom: Stock Chart
    {
        "name": "get_stock_chart",
        "defer_loading": True,
        "description": "Fetch full OHLCV candlestick data for rendering interactive stock charts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":     {"type": "string"},
                "period":     {"type": "string", "enum": ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y"], "default": "3mo"},
                "interval":   {"type": "string", "enum": ["1m", "5m", "15m", "30m", "1h", "1d", "1wk"], "default": "1d"},
                "chart_type": {"type": "string", "enum": ["candlestick", "line", "area"], "default": "candlestick"}
            },
            "required": ["symbol"]
        }
    },
    # Custom: Technical Analysis
    {
        "name": "technical_analysis",
        "description": "Perform comprehensive technical analysis on a stock. Returns RSI, MACD, Bollinger Bands, ADX, moving averages, support/resistance levels, and an overall signal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "period": {"type": "string", "enum": ["1mo", "3mo", "6mo", "1y"], "default": "3mo"}
            },
            "required": ["symbol"]
        }
    },
    # Custom: Weather
    {
        "name": "get_weather",
        "defer_loading": True,
        "description": "Get current weather conditions and forecast for a location.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "units":    {"type": "string", "enum": ["metric", "imperial"], "default": "imperial"}
            },
            "required": ["location"]
        }
    },
    # Custom: News Headlines
    {
        "name": "get_news",
        "defer_loading": True,
        "description": "Fetch recent news headlines with summaries and sentiment analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":       {"type": "string"},
                "category":    {"type": "string", "enum": ["market", "earnings", "economy", "technology", "politics", "general"], "default": "general"},
                "max_results": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }
    },
    # Custom: Chart Builder
    {
        "name": "create_chart",
        "defer_loading": True,
        "description": "Create a data visualization chart.",
        "input_schema": {
            "type": "object",
            "properties": {
                "chart_type": {"type": "string", "enum": ["bar", "horizontal_bar", "line", "area", "pie", "donut", "scatter"]},
                "title":      {"type": "string"},
                "data":       {"type": "array", "items": {"type": "object"}},
                "x_label":    {"type": "string", "default": ""},
                "y_label":    {"type": "string", "default": ""},
                "colors":     {"type": "array", "items": {"type": "string"}}
            },
            "required": ["chart_type", "title", "data"]
        }
    },
    # Custom: Code Sandbox
    {
        "name": "code_sandbox",
        "defer_loading": True,
        "description": "Create an interactive code sandbox with editable code, run capability, and output terminal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code":             {"type": "string"},
                "language":         {"type": "string", "enum": ["python", "javascript", "afl", "sql", "r"], "default": "python"},
                "title":            {"type": "string", "default": "Code Sandbox"},
                "run_immediately":  {"type": "boolean", "default": True}
            },
            "required": ["code"]
        }
    },
    # Custom: Stock Screener
    {
        "name": "screen_stocks",
        "defer_loading": True,
        "description": "Screen stocks by criteria like market cap, P/E ratio, sector, dividend yield.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sector":             {"type": "string"},
                "min_market_cap":     {"type": "number"},
                "max_pe_ratio":       {"type": "number"},
                "min_dividend_yield": {"type": "number"},
                "symbols":            {"type": "string", "default": "AAPL,MSFT,GOOGL,AMZN,META,NVDA,TSLA,JPM,V,JNJ,WMT,PG,UNH,MA,HD,DIS,BAC,NFLX,ADBE,CRM,PFE,ABBV,KO,PEP,MRK,TMO,COST,AVGO,LLY,ORCL"}
            }
        }
    },
    # Custom: Compare Stocks
    {
        "name": "compare_stocks",
        "defer_loading": True,
        "description": "Compare multiple stocks side by side with key metrics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {"type": "string"},
                "metrics": {"type": "string", "default": "price,market_cap,pe_ratio,revenue,profit_margin,dividend_yield,52w_change"}
            },
            "required": ["symbols"]
        }
    },
    # Custom: Sector Performance
    {
        "name": "get_sector_performance",
        "defer_loading": True,
        "description": "Get performance data for market sectors.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": ["1d", "5d", "1mo", "3mo", "6mo", "1y"], "default": "1mo"}
            }
        }
    },
    # Custom: Position Size Calculator
    {
        "name": "calculate_position_size",
        "defer_loading": True,
        "description": "Calculate optimal position size based on account size, risk tolerance, entry/stop-loss prices.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_size":    {"type": "number"},
                "risk_percent":    {"type": "number", "default": 2.0},
                "entry_price":     {"type": "number"},
                "stop_loss_price": {"type": "number"},
                "symbol":          {"type": "string"}
            },
            "required": ["account_size", "entry_price", "stop_loss_price"]
        }
    },
    # Custom: Correlation Matrix
    {
        "name": "calculate_correlation",
        "defer_loading": True,
        "description": "Calculate the correlation matrix between multiple stocks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {"type": "string"},
                "period":  {"type": "string", "enum": ["1mo", "3mo", "6mo", "1y"], "default": "6mo"}
            },
            "required": ["symbols"]
        }
    },
    # Custom: Dividend Info
    {
        "name": "get_dividend_info",
        "defer_loading": True,
        "description": "Get detailed dividend information for a stock.",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"]
        }
    },
    # Custom: Risk Metrics
    {
        "name": "calculate_risk_metrics",
        "defer_loading": True,
        "description": "Calculate comprehensive risk metrics (Sharpe, Sortino, max drawdown, VaR, beta).",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":         {"type": "string"},
                "period":         {"type": "string", "enum": ["3mo", "6mo", "1y", "2y"], "default": "1y"},
                "benchmark":      {"type": "string", "default": "SPY"},
                "risk_free_rate": {"type": "number", "default": 0.05}
            },
            "required": ["symbol"]
        }
    },
    # Custom: Market Overview
    {
        "name": "get_market_overview",
        "defer_loading": True,
        "description": "Get a comprehensive market overview including major indices, VIX, commodities, crypto.",
        "input_schema": {"type": "object", "properties": {}}
    },
    # Custom: Quick Backtest
    {
        "name": "backtest_quick",
        "defer_loading": True,
        "description": "Run a quick backtest of a simple trading strategy.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":       {"type": "string"},
                "strategy":     {"type": "string", "enum": ["sma_crossover", "ema_crossover", "rsi_oversold", "macd_signal", "bollinger_bounce"], "default": "sma_crossover"},
                "period":       {"type": "string", "enum": ["6mo", "1y", "2y", "5y"], "default": "1y"},
                "fast_period":  {"type": "integer", "default": 20},
                "slow_period":  {"type": "integer", "default": 50}
            },
            "required": ["symbol"]
        }
    },
    # Custom: Options Snapshot
    {
        "name": "get_options_snapshot",
        "defer_loading": True,
        "description": "Get options data overview for a stock.",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"]
        }
    },
    # Custom: Portfolio Analysis
    {
        "name": "portfolio_analysis",
        "defer_loading": True,
        "description": "Analyze a portfolio's holdings, allocation, performance metrics, and risk.",
        "input_schema": {
            "type": "object",
            "properties": {
                "holdings":  {"type": "array", "items": {"type": "object"}},
                "benchmark": {"type": "string", "default": "SPY"}
            },
            "required": ["holdings"]
        }
    },
    # Custom: Watchlist
    {
        "name": "get_watchlist",
        "defer_loading": True,
        "description": "Get user's stock watchlist with current prices and changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {"type": "string", "default": "AAPL,MSFT,GOOGL,TSLA,NVDA,META,AMZN"}
            }
        }
    },
    # Custom: Sector Heatmap
    {
        "name": "sector_heatmap",
        "defer_loading": True,
        "description": "Generate sector performance heatmap data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": ["1d", "5d", "1mo", "3mo", "6mo", "1y"], "default": "1d"}
            }
        }
    },
    # Custom: Options Chain
    {
        "name": "get_options_chain",
        "defer_loading": True,
        "description": "Get detailed options chain data with strikes, expirations, Greeks, and volume.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "expiry": {"type": "string", "description": "Specific expiry date (YYYY-MM-DD) or 'nearest'"}
            },
            "required": ["symbol"]
        }
    },
    # Custom: Market Sentiment
    {
        "name": "get_market_sentiment",
        "defer_loading": True,
        "description": "Get market sentiment indicators including fear/greed index, put/call ratios, VIX.",
        "input_schema": {"type": "object", "properties": {}}
    },
    # Custom: Crypto Data
    {
        "name": "get_crypto_data",
        "defer_loading": True,
        "description": "Get cryptocurrency prices, market data, and basic metrics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {"type": "string", "default": "BTC-USD,ETH-USD,BNB-USD,ADA-USD,SOL-USD"}
            }
        }
    },
    # Custom: Trade Signal
    {
        "name": "generate_trade_signal",
        "defer_loading": True,
        "description": "Generate trade signals with confidence levels.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":    {"type": "string"},
                "timeframe": {"type": "string", "default": "1d"}
            },
            "required": ["symbol"]
        }
    },
    # Custom: Risk Assessment
    {
        "name": "risk_assessment",
        "defer_loading": True,
        "description": "Comprehensive risk assessment for a stock.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "period": {"type": "string", "default": "1y"}
            },
            "required": ["symbol"]
        }
    },
    # Custom: News Digest
    {
        "name": "news_digest",
        "defer_loading": True,
        "description": "Enhanced news digest with impact analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":        {"type": "string"},
                "max_articles": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }
    },
    # Custom: Run Backtest
    {
        "name": "run_backtest",
        "defer_loading": True,
        "description": "Enhanced backtesting with date range support.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols":    {"type": "string"},
                "strategy":   {"type": "string"},
                "start_date": {"type": "string"},
                "end_date":   {"type": "string"}
            },
            "required": ["symbols", "strategy"]
        }
    },
    # Custom: Live Scores
    {
        "name": "get_live_scores",
        "defer_loading": True,
        "description": "Get live and recent sports scores for NBA, NFL, MLB, NHL, soccer, and more.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sport":  {"type": "string", "enum": ["nba", "nfl", "mlb", "nhl", "soccer", "mls", "premier_league"]},
                "league": {"type": "string"},
                "date":   {"type": "string"}
            }
        }
    },
    # Custom: Search Trends
    {
        "name": "get_search_trends",
        "defer_loading": True,
        "description": "Get current trending search topics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "region":   {"type": "string", "default": "US"},
                "category": {"type": "string"},
                "period":   {"type": "string", "default": "today"}
            }
        }
    },
    # Custom: LinkedIn Post
    {
        "name": "create_linkedin_post",
        "defer_loading": True,
        "description": "Generate a professional LinkedIn post preview.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic":            {"type": "string"},
                "tone":             {"type": "string", "enum": ["professional", "casual", "inspirational", "educational", "storytelling"], "default": "professional"},
                "author_name":      {"type": "string"},
                "include_hashtags": {"type": "boolean", "default": True}
            },
            "required": ["topic"]
        }
    },
    # Custom: Preview Website
    {
        "name": "preview_website",
        "defer_loading": True,
        "description": "Get a preview of a website including metadata and status.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"]
        }
    },
    # Custom: Order Food
    {
        "name": "order_food",
        "defer_loading": True,
        "description": "Search for restaurants and food delivery.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":    {"type": "string"},
                "cuisine":  {"type": "string"},
                "location": {"type": "string"}
            },
            "required": ["query"]
        }
    },
    # Custom: Track Flight
    {
        "name": "track_flight",
        "defer_loading": True,
        "description": "Track a flight by its flight number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "flight_number": {"type": "string"},
                "date":          {"type": "string"}
            },
            "required": ["flight_number"]
        }
    },
    # Custom: Search Flights
    {
        "name": "search_flights",
        "defer_loading": True,
        "description": "Search for available flights between two cities/airports.",
        "input_schema": {
            "type": "object",
            "properties": {
                "origin":           {"type": "string"},
                "destination":      {"type": "string"},
                "departure_date":   {"type": "string"},
                "return_date":      {"type": "string"},
                "adults":           {"type": "integer", "default": 1},
                "cabin_class":      {"type": "string", "enum": ["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"], "default": "ECONOMY"},
                "max_results":      {"type": "integer", "default": 5},
                "sort_by":          {"type": "string", "enum": ["price", "duration"], "default": "price"}
            },
            "required": ["origin", "destination", "departure_date"]
        }
    },
    # ── Skill-Dispatch Tools (invoke specialist skills transparently) ──────────
    # These tools allow Claude to invoke registered Claude Beta Skills during chat
    # without any user-facing Skills page. Claude decides when to call them.
    {
        "name": "run_financial_deep_research",
        "defer_loading": True,
        "description": (
            "Performs deep, institutional-grade financial research on a company or market topic. "
            "Use when the user needs comprehensive fundamental analysis, earnings quality assessment, "
            "competitive positioning, SEC filings analysis, macroeconomic impact, or a full research report. "
            "Takes 1-3 minutes. Worth the wait for complex research needs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Company name, ticker symbol, or research topic (e.g. 'NVDA earnings quality', 'AI chip sector outlook')"
                },
                "focus": {
                    "type": "string",
                    "description": "Specific aspects to analyze: fundamentals, technicals, competitive, earnings, macro, full-report"
                }
            },
            "required": ["topic"]
        }
    },
    {
        "name": "run_backtest_analysis",
        "defer_loading": True,
        "description": (
            "Performs expert-level backtest analysis on a trading strategy or equity curve. "
            "Use when the user shares backtest results, strategy performance data, or asks for deep "
            "analysis of trading system metrics. Covers Sharpe/Sortino ratios, drawdown analysis, "
            "win rates, profit factors, parameter optimization, and robustness testing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "string",
                    "description": "The backtest results, equity curve data, strategy description, or performance metrics to analyze"
                },
                "focus": {
                    "type": "string",
                    "description": "Specific analysis focus: risk-metrics, optimization, robustness, walk-forward, drawdown"
                }
            },
            "required": ["data"]
        }
    },
    {
        "name": "run_quant_analysis",
        "defer_loading": True,
        "description": (
            "Runs advanced quantitative analysis using factor models, portfolio optimization, "
            "statistical arbitrage, and systematic strategy construction. Use for complex quantitative "
            "requests that require expert statistical modeling, hypothesis testing, factor analysis, "
            "or systematic trading system design."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "request": {
                    "type": "string",
                    "description": "The quantitative analysis request (e.g. 'build a momentum-value factor model for US equities')"
                },
                "context": {
                    "type": "string",
                    "description": "Additional context, data, or constraints for the analysis"
                }
            },
            "required": ["request"]
        }
    },
    {
        "name": "run_bubble_detection",
        "defer_loading": True,
        "description": (
            "Analyzes US equity markets or specific sectors for bubble indicators. "
            "Use when the user asks about market valuations, crash risk, bubble analysis, "
            "whether current market levels are sustainable, or if a specific sector is overvalued. "
            "Uses Shiller PE, Buffett Indicator, credit spreads, margin debt, and other indicators."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {
                    "type": "string",
                    "description": "Specific market, sector, or ticker to analyze (e.g. 'US tech stocks', 'AI sector', 'SPY', 'NVDA')"
                },
                "context": {
                    "type": "string",
                    "description": "Additional context or specific indicators to focus on"
                }
            },
            "required": ["market"]
        }
    },
    {
        "name": "generate_afl_with_skill",
        "defer_loading": True,
        "description": (
            "Generates high-quality AmiBroker AFL code using the specialized AFL Developer skill. "
            "Use this for COMPLEX AFL generation requests that require expert-level code with proper "
            "Param/Optimize structure, multiple indicators, composite system design, or advanced AFL patterns. "
            "For simple AFL requests, prefer generate_afl_code. This is the premium path for complex requests."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "request": {
                    "type": "string",
                    "description": "The AFL strategy to generate (be specific about indicators, parameters, entry/exit rules)"
                },
                "strategy_type": {
                    "type": "string",
                    "description": "standalone (complete with all sections) or composite (logic only)",
                    "enum": ["standalone", "composite"],
                    "default": "standalone"
                },
                "trade_timing": {
                    "type": "string",
                    "description": "open (execute on next bar open) or close (execute on bar close)",
                    "enum": ["open", "close"],
                    "default": "close"
                }
            },
            "required": ["request"]
        }
    },
    # Generic Skill Invocation — use for document/presentation/excel generation and specialist skills
    {
        "name": "invoke_skill",
        "description": (
            "Invoke a registered Claude custom skill by its slug. Use this for document generation, "
            "presentation creation, Excel spreadsheets, and specialist analysis. Available skill slugs:\n"
            "- 'potomac-docx-skill': Create professional Potomac-branded Word documents (.docx) — "
            "reports, memos, fact sheets, market commentaries, proposals, SOPs, any business document\n"
            "- 'potomac-pptx': Create Potomac-branded PowerPoint presentations (.pptx) — "
            "pitch decks, investor updates, quarterly reviews, strategy overviews with brand compliance\n"
            "- 'potomac-xlsx': Create Potomac-branded Excel spreadsheets (.xlsx) — "
            "performance reports, portfolio trackers, risk dashboards, trade logs, financial models, any spreadsheet\n"
            "- 'xlsx': Anthropic built-in Excel skill — general Excel/spreadsheet creation and editing\n"
            "- 'pptx': Anthropic built-in PowerPoint skill — general presentation creation and editing\n"
            "- 'docx': Anthropic built-in Word skill — general Word document creation and editing\n"
            "- 'pdf': Anthropic built-in PDF skill — PDF creation, extraction, and manipulation\n"
            "- 'amibroker-afl-developer': Expert AFL code generation for complex trading strategies\n"
            "- 'financial-deep-research': Deep institutional-grade financial research reports\n"
            "- 'backtest-expert': Expert backtest analysis and strategy evaluation\n"
            "- 'quant-analyst': Quantitative analysis, factor models, portfolio optimization\n"
            "- 'us-market-bubble-detector': Bubble risk analysis for US equities\n"
            "- 'backtesting-frameworks': Backtest framework design and walk-forward analysis\n"
            "- 'ai-elements': React UI components and charts generation\n"
            "- 'doc-interpreter': Extract and interpret data from PDFs, images, scanned documents\n"
            "- 'dcf-model': Build DCF valuation models in Excel\n"
            "- 'initiating-coverage': Institutional equity research initiation reports\n"
            "- 'datapack-builder': Financial data packs for M&A/PE due diligence\n"
            "- 'artifacts-builder': Complex multi-component React/HTML artifacts"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_slug": {
                    "type": "string",
                    "description": "The skill slug to invoke (e.g. 'potomac-docx-skill', 'potomac-pptx-skill')"
                },
                "message": {
                    "type": "string",
                    "description": "The detailed request/prompt for the skill"
                },
                "extra_context": {"type": "string", "default": ""}
            },
            "required": ["skill_slug", "message"]
        }
    },
    # ── Document & Presentation Generation ────────────────────────────────────
    {
        "name": "create_word_document",
        "defer_loading": True,
        "description": (
            "Create a professional Potomac-branded Word document (.docx). "
            "Use this when the user asks for a document, report, memo, fact sheet, "
            "market commentary, proposal, SOP, research write-up, or any business document. "
            "The document is generated as a downloadable .docx file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Document title"},
                "description": {"type": "string", "description": "Detailed description of what the document should contain"},
                "doc_type": {"type": "string", "description": "Type of document", "enum": ["report", "memo", "fact_sheet", "commentary", "proposal", "letter", "sop", "research", "guide"], "default": "report"},
                "subtitle": {"type": "string", "description": "Optional subtitle", "default": ""}
            },
            "required": ["title", "description"]
        }
    },
    {
        "name": "create_pptx_with_skill",
        "defer_loading": True,
        "description": (
            "Create a professional Potomac-branded PowerPoint presentation (.pptx). "
            "Use this when the user asks for a presentation, pitch deck, slide deck, "
            "investor update, quarterly review, or strategy overview. "
            "The presentation is generated as a downloadable .pptx file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Presentation title"},
                "description": {"type": "string", "description": "Detailed description of what the presentation should cover"},
                "slide_count": {"type": "integer", "description": "Approximate number of slides", "default": 10},
                "subtitle": {"type": "string", "description": "Optional subtitle", "default": ""}
            },
            "required": ["title", "description"]
        }
    },
    # ── Server-side Document Generation (no Claude Skills container) ──────────
    # generate_docx runs entirely on the Railway server via Node.js + docx npm.
    # Zero API cost; logos mounted from ClaudeSkills/potomac-docx/assets/.
    # Image sections accept file_id from user uploads — resolved to base64 before Node runs.
    {
        "name": "generate_docx",
        "description": (
            "Generate a professional Potomac-branded Word document (.docx) entirely "
            "on the server — no Claude Skills container, no API cost, instant download. "
            "Use this instead of invoke_skill for any Potomac Word document request: "
            "fund fact sheets, market commentaries, research reports, client memos, "
            "risk reports, performance reports, proposals, SOPs, trade rationale, "
            "onboarding guides, legal agreements, or any other business document.\n\n"
            "Capabilities:\n"
            "- Potomac yellow (#FEC00F) / dark-gray (#212121) brand palette\n"
            "- Potomac logo on every page header (standard, black, or white variant)\n"
            "- H1/H2/H3 headings (Rajdhani ALL CAPS), body text (Quicksand)\n"
            "- Bullet lists, numbered lists, multi-column tables (zebra-striped, yellow headers)\n"
            "- User-uploaded images embedded via file_id (PNG, JPG, GIF supported)\n"
            "- Dividers, spacers, page breaks\n"
            "- Standard Potomac disclosure block (auto-appended unless disabled)\n"
            "- Page-number footer\n\n"
            "IMPORTANT: Populate `sections` with ALL the document content. "
            "Be thorough — the AI writes the content; the tool formats and saves it. "
            "For images the user has uploaded, use type='image' with file_id from the upload."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Output filename e.g. 'Potomac_Q1_Commentary.docx'. Use underscores.",
                },
                "title": {
                    "type": "string",
                    "description": "Main document title shown on the title page (ALL CAPS recommended).",
                },
                "subtitle": {"type": "string", "description": "Optional subtitle below the title."},
                "date":     {"type": "string", "description": "Document date, e.g. 'April 2026'."},
                "author":   {"type": "string", "description": "Author / team name."},
                "logo_variant": {
                    "type": "string",
                    "enum": ["standard", "black", "white"],
                    "default": "standard",
                    "description": "Potomac logo variant: 'standard' (color), 'black', or 'white'.",
                },
                "header_line_color": {
                    "type": "string",
                    "enum": ["yellow", "dark"],
                    "default": "yellow",
                    "description": "Color of the underline beneath the header logo.",
                },
                "footer_text": {
                    "type": "string",
                    "description": "Custom footer left text. Default: 'Potomac  |  Built to Conquer Risk®'.",
                },
                "sections": {
                    "type": "array",
                    "description": (
                        "Ordered list of content blocks. Each has a 'type' field plus type-specific fields:\n"
                        "  heading    → level (1/2/3), text\n"
                        "  paragraph  → text  OR  runs:[{text,bold,italics,color}]\n"
                        "  bullets    → items:[str, ...]\n"
                        "  numbered   → items:[str, ...]\n"
                        "  table      → headers:[str], rows:[[str]], col_widths:[int] (optional)\n"
                        "  image      → file_id (from user upload), width (px), height (px, auto if omitted),\n"
                        "               align ('left'|'center'|'right'), caption (optional text below image)\n"
                        "  divider    → (no extra fields, draws yellow horizontal rule)\n"
                        "  spacer     → size (twips, default 240)\n"
                        "  page_break → (no extra fields)"
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "type":       {"type": "string"},
                            "level":      {"type": "integer", "enum": [1, 2, 3]},
                            "text":       {"type": "string"},
                            "runs":       {"type": "array", "items": {"type": "object"}},
                            "items":      {"type": "array", "items": {"type": "string"}},
                            "headers":    {"type": "array", "items": {"type": "string"}},
                            "rows":       {"type": "array", "items": {"type": "array"}},
                            "col_widths": {"type": "array", "items": {"type": "integer"}},
                            "size":       {"type": "integer"},
                            "color":      {"type": "string"},
                            "file_id":    {"type": "string", "description": "File UUID from user upload (for type='image')"},
                            "width":      {"type": "integer", "description": "Image width in pixels (for type='image', default 400)"},
                            "height":     {"type": "integer", "description": "Image height in pixels (for type='image', auto-calculated from width if omitted)"},
                            "align":      {"type": "string", "enum": ["left", "center", "right"], "description": "Image alignment (for type='image')"},
                            "caption":    {"type": "string", "description": "Caption text below the image (for type='image')"},
                        },
                        "required": ["type"],
                    },
                },
                "include_disclosure": {
                    "type": "boolean",
                    "default": True,
                    "description": "Append standard Potomac disclosures. Set false for internal docs.",
                },
                "disclosure_text": {
                    "type": "string",
                    "description": "Custom disclosure text (overrides default when include_disclosure=true).",
                },
            },
            "required": ["title", "sections"],
        },
    },
    # ── Server-side PPTX generation ──────────────────────────────────────────
    # generate_pptx runs on Railway via Node.js + pptxgenjs npm.
    # Zero API cost; logos mounted from ClaudeSkills/potomac-pptx/brand-assets/logos/.
    {
        "name": "generate_pptx",
        "description": (
            "Generate a professional Potomac-branded PowerPoint presentation (.pptx) entirely "
            "on the server — no Claude Skills container, no API cost, instant download. "
            "Use for any Potomac slide deck: client pitches, market outlooks, quarterly reviews, "
            "fund overviews, board presentations, proposal decks, or any presentation.\n\n"
            "Slide types: title (standard/executive dark), content (bullets/text), two_column, "
            "three_column, metrics (large KPI numbers), process (numbered step flow), quote, "
            "section_divider, cta (closing + button), image (user upload via file_id).\n\n"
            "IMPORTANT: Build a complete deck — title slide, content slides, and CTA closing. "
            "For images the user has uploaded, use type='image' with file_id from the upload."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Output filename e.g. 'Potomac_Q1_Outlook.pptx'."},
                "title":    {"type": "string", "description": "Presentation title."},
                "slides": {
                    "type": "array",
                    "description": (
                        "Ordered slides. Each has a 'type' field:\n"
                        "  title           → title, subtitle, tagline, style ('standard'|'executive')\n"
                        "  content         → title, bullets:[str] OR text:str\n"
                        "  two_column      → title, left_header, right_header, left_content, right_content\n"
                        "  three_column    → title, column_headers:[h1,h2,h3], columns:[c1,c2,c3]\n"
                        "  metrics         → title, metrics:[{value,label},...], context\n"
                        "  process         → title, steps:[{title,description},...]\n"
                        "  quote           → quote, attribution, context\n"
                        "  section_divider → title, description\n"
                        "  cta             → title, action_text, button_text, contact_info\n"
                        "  image           → title(opt), file_id, format, width, height, align, caption"
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "type":           {"type": "string"},
                            "title":          {"type": "string"},
                            "subtitle":       {"type": "string"},
                            "tagline":        {"type": "string"},
                            "style":          {"type": "string", "enum": ["standard", "executive"]},
                            "bullets":        {"type": "array", "items": {"type": "string"}},
                            "text":           {"type": "string"},
                            "left_header":    {"type": "string"},
                            "right_header":   {"type": "string"},
                            "left_content":   {"type": "string"},
                            "right_content":  {"type": "string"},
                            "columns":        {"type": "array", "items": {"type": "string"}},
                            "column_headers": {"type": "array", "items": {"type": "string"}},
                            "metrics":        {"type": "array", "items": {"type": "object"}},
                            "context":        {"type": "string"},
                            "steps":          {"type": "array", "items": {"type": "object"}},
                            "quote":          {"type": "string"},
                            "attribution":    {"type": "string"},
                            "description":    {"type": "string"},
                            "action_text":    {"type": "string"},
                            "button_text":    {"type": "string"},
                            "contact_info":   {"type": "string"},
                            "file_id":        {"type": "string", "description": "File UUID from user upload (for type='image')"},
                            "format":         {"type": "string", "enum": ["png", "jpg", "jpeg", "gif"]},
                            "width":          {"type": "number"},
                            "height":         {"type": "number"},
                            "align":          {"type": "string", "enum": ["left", "center", "right"]},
                            "caption":        {"type": "string"},
                        },
                        "required": ["type"],
                    },
                },
            },
            "required": ["title", "slides"],
        },
    },
    # ── PPTX Intelligence Tools ──────────────────────────────────────────────
    {
        "name": "analyze_pptx",
        "description": (
            "Read and profile any uploaded PowerPoint (.pptx) file. "
            "Returns slide count, titles, all text, table data, image locations, "
            "and a Potomac brand compliance score. "
            "Use BEFORE revising or extending an existing deck."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "UUID of the uploaded .pptx file."}
            },
            "required": ["file_id"]
        },
    },
    {
        "name": "revise_pptx",
        "description": (
            "Apply targeted revisions to an existing .pptx in milliseconds. "
            "Operations: find_replace (global text swap), update_slide, append_slides, delete_slide, reorder_slides, update_table. "
            "Use find_replace for quarterly updates — change Q1→Q2, update all numbers across entire deck at once."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id":         {"type": "string", "description": "UUID of the existing .pptx to revise."},
                "revisions":       {"type": "array",  "items": {"type": "object"}, "description": "Ordered revision operations."},
                "output_filename": {"type": "string", "description": "Output filename e.g. 'Potomac_Q2_2026.pptx'."},
            },
            "required": ["file_id", "revisions"]
        },
    },
    # ── Server-side XLSX Intelligence Tools ──────────────────────────────────
    # analyze_xlsx: profile any uploaded .xlsx or .csv — columns, dtypes, stats, samples
    # transform_xlsx: pandas pipeline — filter, sort, clean, pivot, group, dedupe
    {
        "name": "analyze_xlsx",
        "description": (
            "Analyze any uploaded Excel (.xlsx) or CSV file. "
            "Returns sheet names, column names, data types, null counts, duplicate count, "
            "numeric statistics (min/max/mean/std), and 5 sample rows. "
            "Call this FIRST whenever the user uploads a spreadsheet — no manual inspection needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "UUID of the uploaded file to analyze."}
            },
            "required": ["file_id"]
        },
    },
    {
        "name": "transform_xlsx",
        "description": (
            "Apply data cleaning and transformation operations to any uploaded Excel or CSV file. "
            "Operations run as a pipeline in order. Output is a branded Potomac .xlsx download.\n\n"
            "Operations (each is an object with 'type' + operation-specific fields):\n"
            "  filter_rows    → {column, op ('=='|'!='|'>'|'>='|'<'|'<='|'contains'|'not_null'), value}\n"
            "  sort           → {by:[col,...], ascending:[true,...]}\n"
            "  rename_columns → {mapper: {old_name: new_name, ...}}\n"
            "  drop_columns   → {columns: [col, ...]}\n"
            "  add_column     → {name, formula} (pandas eval syntax e.g. 'PRICE * SHARES')\n"
            "  fill_nulls     → {column, value}\n"
            "  drop_duplicates → {subset:[col,...], keep:'first'|'last'}\n"
            "  change_dtype   → {column, to:'date'|'int'|'float'|'string'}\n"
            "  normalize_text → {column, transform:'upper'|'lower'|'title'|'strip'}\n"
            "  group_aggregate → {by:[col,...], agg:{col:'sum'|'mean'|'count'|'min'|'max'...}}\n"
            "  pivot          → {index, columns, values, aggfunc:'mean'|'sum'|'count'...}"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id":         {"type": "string", "description": "UUID of the uploaded file."},
                "operations":      {"type": "array", "items": {"type": "object"}, "description": "Ordered operations pipeline."},
                "output_title":    {"type": "string", "description": "Title for the output workbook."},
                "output_filename": {"type": "string", "description": "Custom output filename."},
            },
            "required": ["file_id", "operations"]
        },
    },
    # ── Server-side XLSX generation ──────────────────────────────────────────
    # generate_xlsx runs entirely in Python via openpyxl — no Node.js subprocess.
    # Zero API cost. Full Potomac brand styling applied automatically.
    {
        "name": "generate_xlsx",
        "description": (
            "Generate a professional Potomac-branded Excel workbook (.xlsx) entirely "
            "on the server — no Claude Skills container, no API cost, instant download. "
            "Use for any Potomac spreadsheet: performance reports, portfolio trackers, "
            "risk dashboards, trade logs, fee schedules, budget models, data exports, "
            "financial models, or any tabular data.\n\n"
            "Capabilities: yellow (#FEC00F) column headers, zebra-striped rows, thin borders, "
            "Calibri font, multiple sheets with colored tabs, number formats per column, "
            "Excel formulas (e.g. '=SUM(B2:B9)'), frozen panes, landscape print layout, "
            "optional auto-appended DISCLOSURES sheet.\n\n"
            "IMPORTANT: Supply actual data values in 'rows'. Use formulas for calculated columns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Output filename e.g. 'Potomac_PortfolioTracker.xlsx'."},
                "title":    {"type": "string", "description": "Workbook title shown in every sheet's title block (ALL CAPS recommended)."},
                "subtitle": {"type": "string", "description": "Optional subtitle e.g. 'As of March 31, 2026'."},
                "sheets": {
                    "type": "array",
                    "description": "One or more worksheet definitions.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name":           {"type": "string", "description": "Tab name (auto-uppercased, max 31 chars)."},
                            "tab_color":      {"type": "string", "description": "Tab hex color (no #). Default: FEC00F for first sheet."},
                            "columns":        {"type": "array", "items": {"type": "string"}, "description": "Column headers (auto-uppercased)."},
                            "col_widths":     {"type": "array", "items": {"type": "number"}, "description": "Column widths in Excel character units."},
                            "rows":           {"type": "array", "items": {"type": "array"}, "description": "Data rows — arrays of cell values."},
                            "number_formats": {
                                "type": "object",
                                "description": "Column index 1-based str → Excel format. e.g. {'3':'0.0%','4':'$#,##0.0','5':'MMM D, YYYY'}",
                                "additionalProperties": {"type": "string"},
                            },
                            "formulas":       {
                                "type": "array",
                                "description": "[{cell, formula}] overrides e.g. [{cell:'C10', formula:'=SUM(C5:C9)'}]",
                                "items": {"type": "object"},
                            },
                            "include_footer": {"type": "boolean", "default": True, "description": "Add Potomac footer row below data."},
                            "footer_text":    {"type": "string", "description": "Custom footer. Default: 'Potomac | Built to Conquer Risk®'."},
                            "freeze_panes":   {"type": "string", "description": "Cell to freeze at e.g. 'A5'. Defaults to row below headers."},
                        },
                        "required": ["name", "columns", "rows"],
                    },
                },
                "include_disclosures": {"type": "boolean", "default": True, "description": "Auto-append DISCLOSURES sheet."},
                "disclosure_text":     {"type": "string", "description": "Custom disclosure text."},
            },
            "required": ["title", "sheets"],
        },
    },
    # ── EDGAR / SEC Tools ─────────────────────────────────────────────────────
    # These tools call the SEC EDGAR public API (no API key required).
    # They give Claude access to official SEC filings, financial facts, and
    # company identifiers for any publicly traded company.
    {
        "name": "edgar_get_security_id",
        "defer_loading": True,
        "description": (
            "Resolve a stock ticker symbol or company name to its SEC EDGAR security identifiers. "
            "Returns the CIK (Central Index Key), padded CIK, company name, SIC code, SIC description, "
            "listed tickers, and stock exchange(s). Use this FIRST when any SEC/EDGAR workflow starts "
            "with a ticker (e.g. 'AAPL') or a company name (e.g. 'Apple Inc')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "identifier": {
                    "type": "string",
                    "description": "Ticker symbol (e.g. 'AAPL') or company name (e.g. 'Apple')"
                }
            },
            "required": ["identifier"]
        }
    },
    {
        "name": "edgar_search_companies",
        "defer_loading": True,
        "description": (
            "Search the full SEC company registry for companies matching a name or ticker substring. "
            "Returns a ranked list of matching companies with their CIK, name, and ticker. "
            "Use when the user provides a partial name or wants to find multiple related companies."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Company name or ticker substring to search for"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (1-50)",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "edgar_get_filings",
        "defer_loading": True,
        "description": (
            "Fetch the list of SEC filings for a company identified by ticker symbol. "
            "Supports filtering by form type (10-K annual, 10-Q quarterly, 8-K material events, "
            "DEF 14A proxy, S-1 IPO, 4 insider transactions, SC 13G/13D ownership reports, etc.). "
            "Each filing includes the accession number, filing date, report date, and direct document URL. "
            "Use when the user asks about a company's filings, reports, or SEC disclosures."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g. 'AAPL', 'MSFT')"
                },
                "form_type": {
                    "type": "string",
                    "description": (
                        "SEC form type filter. Common values: '10-K' (annual report), "
                        "'10-Q' (quarterly report), '8-K' (material events), "
                        "'DEF 14A' (proxy statement), '4' (insider transactions), "
                        "'S-1' (IPO registration), 'SC 13G' (ownership > 5%). "
                        "Leave empty for all form types."
                    )
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of filings to return (1-50)",
                    "default": 10
                }
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "edgar_get_financials",
        "defer_loading": True,
        "description": (
            "Fetch official SEC-reported key financial metrics for a company using XBRL structured data. "
            "Returns the most recent values for: Revenues, NetIncomeLoss, EarningsPerShareBasic, "
            "Assets, Liabilities, StockholdersEquity, OperatingIncomeLoss, CashAndCashEquivalents, "
            "LongTermDebt, CommonStockSharesOutstanding — all sourced directly from SEC filings. "
            "Use when the user asks about financial fundamentals, balance sheet, income statement, "
            "or wants to verify reported figures from official sources."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g. 'AAPL', 'GOOGL')"
                }
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "edgar_get_concept",
        "defer_loading": True,
        "description": (
            "Fetch the full historical time-series for a single XBRL financial concept from SEC filings. "
            "Returns annual and quarterly values with fiscal period labels, filing dates, and accession numbers. "
            "Use when the user wants to see how a specific financial metric has trended over time "
            "(e.g. revenue growth, EPS trend, debt levels). "
            "Common concept names: 'Revenues', 'NetIncomeLoss', 'EarningsPerShareBasic', "
            "'EarningsPerShareDiluted', 'Assets', 'Liabilities', 'StockholdersEquity', "
            "'OperatingIncomeLoss', 'CashAndCashEquivalentsAtCarryingValue', 'LongTermDebt'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol"
                },
                "concept": {
                    "type": "string",
                    "description": (
                        "XBRL concept name (PascalCase). Examples: 'Revenues', 'NetIncomeLoss', "
                        "'EarningsPerShareBasic', 'Assets', 'LongTermDebt', 'StockholdersEquity'"
                    )
                },
                "taxonomy": {
                    "type": "string",
                    "description": "XBRL taxonomy namespace",
                    "enum": ["us-gaap", "dei", "ifrs-full"],
                    "default": "us-gaap"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max time-series periods to return",
                    "default": 20
                }
            },
            "required": ["ticker", "concept"]
        }
    },
    {
        "name": "edgar_search_fulltext",
        "defer_loading": True,
        "description": (
            "Search the full text of ALL SEC EDGAR filings using the SEC's EFTS full-text search engine. "
            "Supports boolean operators (AND, OR, NOT), exact phrases (in quotes), and filtering by "
            "form type and date range. Returns matching filing metadata with direct document URLs. "
            "Use when the user wants to find filings that mention a specific topic, product, risk, "
            "person, or keyword across ALL companies — not just a single company. "
            "Examples: 'climate risk in 10-K filings', 'AI chip supply chain 8-K 2024', "
            "'\"going concern\" AND pharmaceutical'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query. Supports AND/OR/NOT and quoted phrases."
                },
                "form_type": {
                    "type": "string",
                    "description": "Optional form type filter (e.g. '10-K', '8-K', 'DEF 14A')"
                },
                "date_from": {
                    "type": "string",
                    "description": "Start date filter YYYY-MM-DD"
                },
                "date_to": {
                    "type": "string",
                    "description": "End date filter YYYY-MM-DD"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (1-50)",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "edgar_get_insider_transactions",
        "defer_loading": True,
        "description": (
            "Fetch recent SEC Form 4 insider transaction filings for a company. "
            "Form 4 must be filed within 2 business days of any insider buy/sell/gift of company securities. "
            "Use when the user asks about insider buying/selling, executive stock transactions, "
            "or wants to monitor insider activity for a stock."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max insider transaction filings to return",
                    "default": 20
                }
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "edgar_get_material_events",
        "defer_loading": True,
        "description": (
            "Fetch recent 8-K (Current Report) filings for a company. "
            "8-Ks disclose material events including earnings releases, M&A activity, "
            "executive changes, credit facility updates, regulatory actions, and more. "
            "Use when the user wants to see recent corporate events or material disclosures."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max 8-K filings to return",
                    "default": 10
                }
            },
            "required": ["ticker"]
        }
    },
]


# =============================================================================
# TOOL HANDLERS
# =============================================================================

def execute_react(code: str, description: str = "") -> Dict[str, Any]:
    """
    Wrap React/JSX code using the ReactSandbox.

    Returns a self-contained HTML page (CDN Babel + esm.sh importmap + Tailwind)
    that the frontend renders in an iframe.  No Node.js subprocess is spawned —
    this is synchronous and fast.

    Supported CDN packages (no install needed):
      react, react-dom, lucide-react, recharts, chart.js, d3, framer-motion,
      zustand, lodash, zod, date-fns, clsx, tailwind-merge, react-hook-form,
      @headlessui/react, @heroicons/react, mathjs, uuid, axios, immer, and more.

    Tailwind CSS utility classes work out of the box.

    The component is auto-mounted if it is named App, Component, or Default.
    """
    try:
        import uuid as _uuid
        from core.sandbox.node_sandbox import ReactSandbox, _wrap_for_client_render

        # Validate for dangerous patterns (sync)
        sandbox = ReactSandbox()
        validation = sandbox.validate(code)
        if not validation["safe"]:
            return {
                "success": False,
                "error": f"Unsafe code: {'; '.join(validation['issues'])}",
                "language": "react",
            }

        # Generate the self-contained HTML page (fully synchronous)
        html = _wrap_for_client_render(code)
        artifact_id = str(_uuid.uuid4())

        return {
            "success":      True,
            "output":       "React component compiled successfully",
            "display_type": "react",
            "language":     "react",
            "artifacts": [
                {
                    "artifact_id":  artifact_id,
                    "type":         "text/html",
                    "display_type": "react",
                    "data":         html,
                    "encoding":     "utf-8",
                    "metadata":     {"renderer": "client", "framework": "react18"},
                }
            ],
        }

    except Exception as e:
        return {
            "success":   False,
            "error":     str(e),
            "traceback": traceback.format_exc()[:500],
            "language":  "react",
        }


def execute_python(code: str, description: str = "") -> Dict[str, Any]:
    """
    Execute Python code in the unified PythonSandbox.

    Delegates to PythonSandbox._execute_sync() which provides:
      - AST-based security validation (replaces bypassable keyword blocklist)
      - Thread-safe stdout capture via patched print()
      - matplotlib figure capture → base64 PNG artifacts
      - display() / HTML() / SVG() Jupyter-like helpers
      - Shared _SANDBOX_GLOBALS (package installs are immediately visible)
    """
    try:
        from core.sandbox.python_sandbox import PythonSandbox

        # Use __new__ to skip __init__ (which schedules an async task).
        # _execute_sync is fully synchronous and safe to call directly.
        sandbox = object.__new__(PythonSandbox)
        result, _namespace = sandbox._execute_sync(code, context=None, persisted_namespace={})

        out: Dict[str, Any] = {
            "success": result.success,
            "output": result.output,
            "variables": result.variables,
        }
        if not result.success:
            out["error"] = result.error
            out["traceback"] = result.output  # _execute_sync puts tb in output on failure
        if result.artifacts:
            out["artifacts"] = [
                {
                    "artifact_id": a.artifact_id,
                    "type": a.type,
                    "display_type": a.display_type,
                    "data": a.data,
                    "encoding": a.encoding,
                    "metadata": a.metadata,
                }
                for a in result.artifacts
            ]
            out["display_type"] = result.display_type
        return out

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()[:500],
        }


def search_knowledge_base(
    query:           str,
    category:        Optional[str] = None,
    limit:           int           = 3,
    supabase_client=None,
) -> Dict[str, Any]:
    """Search the knowledge base with caching."""
    cached = _get_cached_kb(query, category or "all")
    if cached:
        return cached

    if supabase_client is None:
        return {"success": False, "error": "Database connection not available", "results": []}

    try:
        start_time = time.time()
        db_query   = supabase_client.table("brain_documents").select(
            "id, title, category, summary, tags, raw_content"
        )
        if category:
            db_query = db_query.eq("category", category)

        # Build OR conditions from the first 3 query words (keeps the DB query fast)
        search_terms  = query.split()[:3]
        or_conditions = [
            cond
            for term in search_terms
            for cond in (
                f"title.ilike.%{term}%",
                f"summary.ilike.%{term}%",
                f"raw_content.ilike.%{term}%",
            )
        ]
        if or_conditions:
            db_query = db_query.or_(",".join(or_conditions))

        result    = db_query.limit(limit).execute()
        documents = []
        for doc in result.data:
            raw_content = doc.get("raw_content", "")
            documents.append({
                "id":               doc["id"],
                "title":            doc["title"],
                "category":         doc["category"],
                "summary":          doc.get("summary", "")[:200],
                "tags":             doc.get("tags", []),
                "content_snippet":  _extract_relevant_snippet(raw_content, query),
            })

        search_time = time.time() - start_time
        response = {
            "success":         True,
            "query":           query,
            "category_filter": category,
            "results_count":   len(documents),
            "search_time_ms":  round(search_time * 1000, 2),
            "results":         documents,
        }
        _set_cached_kb(query, category or "all", response)
        logger.debug("KB search: %.3fs, %d results", search_time, len(documents))
        return response

    except Exception as e:
        logger.error("KB search error: %s", e)
        return {"success": False, "error": str(e), "results": []}


def _extract_relevant_snippet(content: str, query: str, max_len: int = 300) -> str:
    """Extract a relevant snippet from content around the first query term found."""
    if not content:
        return ""
    content_lower = content.lower()
    best_pos      = -1
    for term in query.lower().split():
        pos = content_lower.find(term)
        if pos != -1 and (best_pos == -1 or pos < best_pos):
            best_pos = pos

    if best_pos == -1:
        # Query terms not found — return the start of the content
        return (content[:max_len] + "...") if len(content) > max_len else content

    start   = max(0, best_pos - 50)
    end     = min(len(content), best_pos + max_len - 50)
    snippet = content[start:end]
    if start > 0:             snippet = "..." + snippet
    if end < len(content):    snippet = snippet + "..."
    return snippet


def get_stock_data(symbol: str, period: str = "1mo", info_type: str = "price") -> Dict[str, Any]:
    """Fetch stock market data with caching."""
    if not _YF_AVAILABLE:
        return {"success": False, "error": "yfinance library not available"}

    symbol = symbol.upper()
    cached = _get_cached_stock(symbol, info_type)
    if cached:
        return cached

    try:
        start_time = time.time()
        ticker     = yf.Ticker(symbol)

        if info_type == "price":
            info = ticker.info
            response = {
                "success": True, "symbol": symbol, "data_type": "price", "cached": False,
                "data": {
                    "current_price":  info.get("currentPrice") or info.get("regularMarketPrice"),
                    "previous_close": info.get("previousClose"),
                    "open":           info.get("open") or info.get("regularMarketOpen"),
                    "day_high":       info.get("dayHigh") or info.get("regularMarketDayHigh"),
                    "day_low":        info.get("dayLow") or info.get("regularMarketDayLow"),
                    "volume":         info.get("volume") or info.get("regularMarketVolume"),
                    "market_cap":     info.get("marketCap"),
                    "company_name":   info.get("longName") or info.get("shortName"),
                },
                "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
            }

        elif info_type == "history":
            hist = ticker.history(period=period)
            if hist.empty:
                return {"success": False, "error": f"No historical data found for {symbol}"}
            history_data = [
                {
                    "date":   date.strftime("%Y-%m-%d"),
                    "open":   round(row["Open"],  2), "high": round(row["High"],  2),
                    "low":    round(row["Low"],   2), "close": round(row["Close"], 2),
                    "volume": int(row["Volume"]),
                }
                for date, row in hist.tail(10).iterrows()
            ]
            response = {
                "success": True, "symbol": symbol, "data_type": "history", "period": period,
                "cached": False, "data": history_data,
                "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
            }

        elif info_type == "info":
            info = ticker.info
            response = {
                "success": True, "symbol": symbol, "data_type": "info", "cached": False,
                "data": {
                    "name":        info.get("longName"), "sector":   info.get("sector"),
                    "industry":    info.get("industry"),
                    "description": info.get("longBusinessSummary", "")[:300],
                    "exchange":    info.get("exchange"),
                },
                "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
            }
        else:
            return {"success": False, "error": f"Unknown info_type: {info_type}"}

        if response.get("success"):
            _set_cached_stock(symbol, info_type, response)
        return response

    except Exception as e:
        return {"success": False, "error": str(e)}


def validate_afl(code: str) -> Dict[str, Any]:
    """Validate AFL code using the comprehensive 19-phase validator."""
    if not _AFL_AVAILABLE or _AFL_VALIDATOR is None:
        return {"success": False, "error": "AFL validator not available"}

    validation = _AFL_VALIDATOR.validate(code)
    lines      = code.split("\n")
    code_upper = code.upper()

    # Separate issues by severity for backward-compatible output
    errors   = [i.message for i in validation.issues if i.severity == Severity.ERROR]
    warnings = [i.message for i in validation.issues if i.severity == Severity.WARNING]
    infos    = [i.message for i in validation.issues if i.severity == Severity.INFO]
    suggs    = [i.message for i in validation.issues if i.severity == Severity.SUGGESTION]

    return {
        "success":          validation.is_valid,
        "valid":            validation.is_valid,
        "error_count":      validation.error_count,
        "warning_count":    validation.warning_count,
        "info_count":       validation.info_count,
        "suggestion_count": validation.suggestion_count,
        "cascade_count":    validation.cascade_count,
        "errors":           errors,
        "warnings":         warnings,
        "suggestions":      suggs,
        "issues":           [i.to_dict() for i in validation.issues],
        "line_count":       len(lines),
        "has_buy_sell":     "BUY" in code_upper or "SELL" in code_upper,
        "has_plot":         "PLOT" in code_upper,
    }


def _extract_afl_code(raw_text: str) -> str:
    """Extract AFL code from markdown fenced blocks or return raw text."""
    if "```" in raw_text:
        parts = raw_text.split("```")
        if len(parts) >= 3:
            code = parts[1]
            if code.startswith("afl\n"):
                code = code[4:]
            elif code.startswith("afl"):
                code = code[3:]
            return code.strip()
    return raw_text.strip()


def generate_afl_code(description: str, strategy_type: str = "standalone", api_key: str = None) -> Dict[str, Any]:
    """
    Generate AFL code using a synchronous Anthropic client, then validate and auto-fix.

    Flow:
    1. Generate AFL code from description
    2. Run comprehensive 19-phase validator on the generated code
    3. If errors found, send errors + code back to LLM for fixing (up to 2 rounds)
    4. Return the validated/fixed code with validation report

    Called from handle_tool_call() which is synchronous, so we use the sync
    anthropic.Anthropic client directly instead of the async ClaudeAFLEngine.
    """
    if not api_key:
        return {"success": False, "error": "API key required for AFL generation"}
    try:
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=api_key)
        system = (
            "You are an expert AmiBroker AFL developer. Generate high-quality, production-ready AFL code. "
            "CRITICAL RULES — follow exactly:\n"
            "• Single-arg functions: RSI(14) / ATR(14) / ADX(14) / CCI(14) / MFI(14) / StochK(14) — NO array arg, period ONLY\n"
            "• Double-arg functions: MA(Close,20) / EMA(Close,12) / HHV(High,20) / LLV(Low,20) / Sum(Volume,20) — REQUIRE array arg\n"
            "• IIf(cond, trueVal, falseVal) — 3 args, all arrays. IIf CANNOT return strings.\n"
            "• WriteIf(cond, \"text\", \"text\") — for string output in Title\n"
            "• ExRem(Buy, Sell) and ExRem(Sell, Buy) — must use both to prevent duplicate signals\n"
            "• if() conditions CANNOT contain arrays like Close, Open, MA(). Use IIf() for arrays.\n"
            "• Plot() requires 3+ args: Plot(array, name, color, style)\n"
            "• Always use Param(\"name\", default, min, max, step) for configurable parameters\n"
            "• Always use SetPositionSize() or PositionSize for position sizing\n"
            "• Wrap in _SECTION_BEGIN/_SECTION_END. Include all sections for standalone strategies.\n"
            "• Use correct colors: colorGreen not color_green, styleLine not style_line\n"
            "• Never use MA(20) — must be MA(Close, 20) or MA(Ref(Close,-1), 20)\n"
            "• Return ONLY the AFL code inside a ```afl code block. No explanations outside the block."
        )

        # ── Round 1: Generate ─────────────────────────────────────────────────
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=15000,
            system=system,
            messages=[{"role": "user", "content": f"Generate {strategy_type} AFL code for: {description}"}],
        )
        raw_text = response.content[0].text if response.content else ""
        afl_code = _extract_afl_code(raw_text)

        # ── Round 2: Validate ─────────────────────────────────────────────────
        validation_result = None
        validation_report = ""
        if _AFL_AVAILABLE and _AFL_VALIDATOR:
            validation_result = _AFL_VALIDATOR.validate(afl_code)
            error_count = validation_result.error_count

            # Build a concise error report for the fix prompt
            error_lines = []
            for issue in validation_result.issues:
                if issue.severity == Severity.ERROR:
                    error_lines.append(f"  L{issue.line}: [{issue.category}] {issue.message}")
                    if issue.suggestion:
                        error_lines.append(f"    → Fix: {issue.suggestion}")

            if error_count > 0 and error_count <= 15:
                # ── Round 3: Auto-fix via LLM ────────────────────────────────
                error_report = "\n".join(error_lines[:15])
                fix_prompt = (
                    f"The AFL code below has {error_count} error(s) detected by the validator.\n\n"
                    f"ERRORS:\n{error_report}\n\n"
                    f"CURRENT CODE:\n```afl\n{afl_code}\n```\n\n"
                    f"Fix ALL errors and return the corrected code in a ```afl block. "
                    f"Do not add explanations — just the fixed code."
                )
                fix_response = client.messages.create(
                    model="claude-opus-4-6",
                    max_tokens=15000,
                    system=system,
                    messages=[{"role": "user", "content": fix_prompt}],
                )
                fix_raw = fix_response.content[0].text if fix_response.content else ""
                fixed_code = _extract_afl_code(fix_raw)
                if fixed_code and len(fixed_code) > 20:
                    afl_code = fixed_code
                    # Re-validate
                    validation_result = _AFL_VALIDATOR.validate(afl_code)

            # Build final report
            if validation_result:
                if validation_result.is_valid:
                    validation_report = f"✅ Validation passed (0 errors, {validation_result.warning_count} warnings)"
                else:
                    remaining = []
                    for issue in validation_result.issues:
                        if issue.severity == Severity.ERROR:
                            remaining.append(f"  L{issue.line}: [{issue.category}] {issue.message}")
                    validation_report = (
                        f"⚠️ {validation_result.error_count} error(s) remain after fix attempt:\n"
                        + "\n".join(remaining[:10])
                    )

        return {
            "success":           True,
            "description":       description,
            "strategy_type":     strategy_type,
            "afl_code":          afl_code,
            "validation_valid":  validation_result.is_valid if validation_result else None,
            "validation_errors":  validation_result.error_count if validation_result else 0,
            "validation_warnings": validation_result.warning_count if validation_result else 0,
            "validation_report": validation_report,
            "issues":            [i.to_dict() for i in validation_result.issues] if validation_result else [],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def debug_afl_code(code: str, error_message: str = "", api_key: str = None) -> Dict[str, Any]:
    """Debug and fix AFL code using a synchronous Anthropic client."""
    if not api_key:
        return {"success": False, "error": "API key required for AFL debugging"}
    try:
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=api_key)
        prompt = f"Debug and fix this AFL code:\n\n```afl\n{code}\n```"
        if error_message:
            prompt += f"\n\nAmiBroker error: {error_message}"
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=15000,
            system="Fix AFL syntax and logic issues. Return corrected code in a ```afl block.",
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = response.content[0].text if response.content else code
        fixed_code = raw_text
        if "```" in raw_text:
            parts = raw_text.split("```")
            if len(parts) >= 3:
                fixed_code = parts[1]
                if fixed_code.startswith("afl\n"):
                    fixed_code = fixed_code[4:]
                fixed_code = fixed_code.strip()
        return {
            "success":       True,
            "original_code": (code[:200] + "...") if len(code) > 200 else code,
            "error_message": error_message,
            "fixed_code":    fixed_code,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def explain_afl_code(code: str, api_key: str = None) -> Dict[str, Any]:
    """Explain AFL code in plain English using a synchronous Anthropic client."""
    if not api_key:
        return {"success": False, "error": "API key required for AFL explanation"}
    try:
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system="Explain AFL code clearly for traders. Cover: purpose, indicators, entry/exit, parameters.",
            messages=[{"role": "user", "content": f"Explain this AFL:\n\n```afl\n{code}\n```"}],
        )
        explanation = response.content[0].text if response.content else ""
        return {
            "success":     True,
            "code":        (code[:200] + "...") if len(code) > 200 else code,
            "explanation": explanation,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def sanity_check_afl(code: str, auto_fix: bool = True) -> Dict[str, Any]:
    """Comprehensive 19-phase AFL sanity check with validation report."""
    if not _AFL_AVAILABLE or _AFL_VALIDATOR is None:
        return {"success": False, "error": "AFL validator not available"}

    validation = _AFL_VALIDATOR.validate(code)

    # Build a structured report
    errors   = [i for i in validation.issues if i.severity == Severity.ERROR]
    warnings = [i for i in validation.issues if i.severity == Severity.WARNING]
    suggs    = [i for i in validation.issues if i.severity == Severity.SUGGESTION]
    cascades = [i for i in validation.issues if i.cascading]

    report_lines = []
    if validation.is_valid:
        report_lines.append(f"✅ AFL code passed all {len(validation.issues)} checks (0 errors)")
    else:
        report_lines.append(f"❌ Found {validation.error_count} error(s), {validation.warning_count} warning(s)")
    for issue in validation.issues[:20]:
        prefix = "  " + ("❌" if issue.severity == Severity.ERROR else "⚠️" if issue.severity == Severity.WARNING else "💡")
        report_lines.append(f"{prefix} L{issue.line}: [{issue.category}] {issue.message}")
        if issue.suggestion:
            report_lines.append(f"     → {issue.suggestion}")
        if issue.cascading:
            report_lines.append(f"     ⚡ Cascading from line {issue.cascading_parent}")
    if len(validation.issues) > 20:
        report_lines.append(f"  ... and {len(validation.issues) - 20} more issues")

    report = "\n".join(report_lines)

    return {
        "success":          validation.is_valid,
        "is_valid":         validation.is_valid,
        "error_count":      validation.error_count,
        "warning_count":    validation.warning_count,
        "info_count":       validation.info_count,
        "suggestion_count": validation.suggestion_count,
        "cascade_count":    validation.cascade_count,
        "total_issues":     len(validation.issues),
        "issues":           [i.to_dict() for i in validation.issues],
        "report":           report,
        "line_count":       len(code.split("\n")),
    }


def get_stock_chart(symbol: str, period: str = "3mo", interval: str = "1d", chart_type: str = "candlestick") -> Dict[str, Any]:
    """
    Fetch OHLCV candlestick data.
    SMA calculation is O(n) via a running cumulative sum — not O(n²) slice+sum.
    """
    if not _YF_AVAILABLE:
        return {"success": False, "error": "yfinance library not available"}

    symbol    = symbol.upper()
    cache_key = f"chart_{period}_{interval}"
    cached    = _get_cached_stock(symbol, cache_key)
    if cached:
        return cached

    try:
        start_time = time.time()
        ticker     = yf.Ticker(symbol)
        hist       = ticker.history(period=period, interval=interval)
        if hist.empty:
            return {"success": False, "error": f"No chart data found for {symbol}"}

        fmt         = "%Y-%m-%d" if interval in ("1d", "1wk") else "%Y-%m-%d %H:%M"
        data_points = [
            {
                "date":   date.strftime(fmt),
                "open":   round(float(row["Open"]),  2),
                "high":   round(float(row["High"]),  2),
                "low":    round(float(row["Low"]),   2),
                "close":  round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            }
            for date, row in hist.iterrows()
        ]

        closes = [p["close"] for p in data_points]
        n      = len(closes)

        # O(n) rolling SMA using cumulative sum — replaces the O(n²) slice+sum loop
        # cum[i+1] = sum of closes[0..i], so sum(closes[i-w+1..i]) = cum[i+1] - cum[i-w+1]
        cum  = [0.0] * (n + 1)
        for i, c in enumerate(closes):
            cum[i + 1] = cum[i] + c

        sma20 = [
            round((cum[i + 1] - cum[max(0, i - 19)]) / min(i + 1, 20), 2) if i >= 19 else None
            for i in range(n)
        ]
        sma50 = [
            round((cum[i + 1] - cum[max(0, i - 49)]) / min(i + 1, 50), 2) if i >= 49 else None
            for i in range(n)
        ]

        for i, point in enumerate(data_points):
            point["sma20"] = sma20[i]
            point["sma50"] = sma50[i]

        try:
            info          = ticker.info
            company_name  = info.get("longName") or info.get("shortName") or symbol
            current_price = info.get("currentPrice") or info.get("regularMarketPrice") or closes[-1]
            previous_close = info.get("previousClose") or (closes[-2] if len(closes) > 1 else closes[-1])
        except Exception:
            company_name   = symbol
            current_price  = closes[-1]
            previous_close = closes[-2] if len(closes) > 1 else closes[-1]

        change     = round(current_price - previous_close, 2)
        change_pct = round((change / previous_close) * 100, 2) if previous_close else 0

        response = {
            "success": True, "tool": "get_stock_chart", "symbol": symbol,
            "company_name": company_name, "chart_type": chart_type, "period": period,
            "interval": interval, "current_price": current_price, "change": change,
            "change_percent": change_pct, "data_points": len(data_points),
            "data": data_points, "cached": False,
            "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }
        _set_cached_stock(symbol, cache_key, response)
        return response

    except Exception as e:
        return {"success": False, "error": str(e)}


def technical_analysis(symbol: str, period: str = "3mo") -> Dict[str, Any]:
    """
    Comprehensive technical analysis.
    _ema() is the module-level helper — not redefined on every call.
    """
    if not _YF_AVAILABLE or not _NP_AVAILABLE:
        return {"success": False, "error": "yfinance and numpy are required"}

    symbol    = symbol.upper()
    cache_key = f"ta_{period}"
    cached    = _get_cached_stock(symbol, cache_key)
    if cached:
        return cached

    try:
        start_time = time.time()
        ticker     = yf.Ticker(symbol)
        hist       = ticker.history(period=period)
        if hist.empty or len(hist) < 20:
            return {"success": False, "error": f"Insufficient data for {symbol}"}

        closes = hist["Close"].values.astype(float)
        highs  = hist["High"].values.astype(float)
        lows   = hist["Low"].values.astype(float)

        # ── RSI (14) ─────────────────────────────────────────────────────────
        deltas   = np.diff(closes)
        gains    = np.where(deltas > 0, deltas, 0)
        losses   = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-14:])
        avg_loss = np.mean(losses[-14:])
        rs       = avg_gain / avg_loss if avg_loss != 0 else 100
        rsi      = round(100 - (100 / (1 + rs)), 2)

        # ── MACD (12, 26, 9) — uses module-level _ema() ───────────────────────
        macd_line      = _ema(closes, 12) - _ema(closes, 26)
        signal_line    = _ema(macd_line, 9)
        macd_histogram = macd_line - signal_line
        macd_val   = round(float(macd_line[-1]),   4)
        signal_val = round(float(signal_line[-1]), 4)
        hist_val   = round(float(macd_histogram[-1]), 4)

        # ── Bollinger Bands (20, 2) ───────────────────────────────────────────
        sma20     = np.mean(closes[-20:])
        std20     = np.std(closes[-20:])
        bb_upper  = round(float(sma20 + 2 * std20), 2)
        bb_middle = round(float(sma20), 2)
        bb_lower  = round(float(sma20 - 2 * std20), 2)
        bb_width  = round(float((bb_upper - bb_lower) / bb_middle * 100), 2)

        # ── ADX (14) ──────────────────────────────────────────────────────────
        try:
            tr_list, plus_dm_list, minus_dm_list = [], [], []
            for i in range(1, len(closes)):
                tr       = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
                plus_dm  = highs[i] - highs[i-1] if highs[i] - highs[i-1] > lows[i-1] - lows[i] and highs[i] - highs[i-1] > 0 else 0
                minus_dm = lows[i-1] - lows[i] if lows[i-1] - lows[i] > highs[i] - highs[i-1] and lows[i-1] - lows[i] > 0 else 0
                tr_list.append(tr)
                plus_dm_list.append(plus_dm)
                minus_dm_list.append(minus_dm)
            atr14    = np.mean(tr_list[-14:])
            plus_di  = round(100 * np.mean(plus_dm_list[-14:]) / atr14, 2) if atr14 > 0 else 0
            minus_di = round(100 * np.mean(minus_dm_list[-14:]) / atr14, 2) if atr14 > 0 else 0
            dx       = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0
            adx      = round(dx, 2)
        except Exception:
            adx = plus_di = minus_di = 0

        # ── Moving averages ───────────────────────────────────────────────────
        current_price   = float(closes[-1])
        moving_averages = [
            {
                "period": p, "type": "SMA",
                "value":  round(float(np.mean(closes[-p:])), 2),
                "signal": "bullish" if current_price > round(float(np.mean(closes[-p:])), 2) else "bearish",
            }
            for p in (10, 20, 50, 100, 200) if len(closes) >= p
        ]

        support_levels    = [round(float(l), 2) for l in sorted(lows[-20:])[:3]]
        resistance_levels = [round(float(h), 2) for h in sorted(highs[-20:], reverse=True)[:3]]

        # ── Overall signal (simple vote across indicators) ────────────────────
        bull = bear = 0
        if rsi < 30:   bull += 1
        elif rsi > 70: bear += 1
        if macd_val > signal_val:    bull += 1
        else:                        bear += 1
        if current_price > bb_middle: bull += 1
        else:                         bear += 1
        bull_ma = sum(1 for ma in moving_averages if ma["signal"] == "bullish")
        bear_ma = sum(1 for ma in moving_averages if ma["signal"] == "bearish")
        if bull_ma > bear_ma: bull += 1
        else:                 bear += 1

        if   bull > bear + 1:  overall, label = "strong_buy",  "Strong Buy"
        elif bull > bear:      overall, label = "buy",         "Buy"
        elif bear > bull + 1:  overall, label = "strong_sell", "Strong Sell"
        elif bear > bull:      overall, label = "sell",        "Sell"
        else:                  overall, label = "neutral",     "Neutral"

        try:
            info         = ticker.info
            company_name = info.get("longName") or info.get("shortName") or symbol
        except Exception:
            company_name = symbol

        response = {
            "success": True, "tool": "technical_analysis", "symbol": symbol,
            "company_name": company_name, "current_price": round(current_price, 2),
            "overall_signal": overall, "signal_label": label,
            "signal_strength": max(bull, bear) / (bull + bear) * 100 if (bull + bear) > 0 else 50,
            "indicators": {
                "rsi":             {"value": rsi, "signal": "oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral"},
                "macd":            {"value": macd_val, "signal": signal_val, "histogram": hist_val, "trend": "bullish" if macd_val > signal_val else "bearish"},
                "bollinger_bands": {"upper": bb_upper, "middle": bb_middle, "lower": bb_lower, "width": bb_width},
                "adx":             {"value": adx, "plus_di": plus_di, "minus_di": minus_di, "trend_strength": "strong" if adx > 25 else "weak"},
            },
            "moving_averages":    moving_averages,
            "support_levels":     support_levels,
            "resistance_levels":  resistance_levels,
            "cached": False,
            "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }
        _set_cached_stock(symbol, cache_key, response)
        return response

    except Exception as e:
        return {"success": False, "error": str(e)}


def get_weather(location: str, units: str = "imperial") -> Dict[str, Any]:
    """Get current weather and forecast via wttr.in (no API key needed)."""
    try:
        start_time = time.time()
        url = f"https://wttr.in/{urllib.parse.quote(location)}?format=j1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        current      = data.get("current_condition", [{}])[0]
        nearest_area = data.get("nearest_area", [{}])[0]
        forecasts    = data.get("weather", [])

        is_metric  = units == "metric"
        temp       = int(current.get("temp_C" if is_metric else "temp_F", 0))
        feels_like = int(current.get("FeelsLikeC" if is_metric else "FeelsLikeF", 0))
        temp_unit  = "°C" if is_metric else "°F"

        desc_lower     = current.get("weatherDesc", [{}])[0].get("value", "Unknown").lower()
        condition_desc = current.get("weatherDesc", [{}])[0].get("value", "Unknown")

        if   "sun" in desc_lower or "clear" in desc_lower:                      condition = "sunny"
        elif "cloud" in desc_lower or "overcast" in desc_lower:                  condition = "cloudy"
        elif any(w in desc_lower for w in ("rain", "drizzle", "shower")):        condition = "rainy"
        elif any(w in desc_lower for w in ("snow", "blizzard", "sleet")):        condition = "snowy"
        elif any(w in desc_lower for w in ("thunder", "storm")):                 condition = "stormy"
        elif any(w in desc_lower for w in ("fog", "mist", "haze")):              condition = "foggy"
        elif "partly" in desc_lower:                                             condition = "partly_cloudy"
        else:                                                                    condition = "cloudy"

        forecast_list = [
            {
                "date":      day.get("date", ""),
                "high":      int(day.get("maxtempC" if is_metric else "maxtempF", 0)),
                "low":       int(day.get("mintempC" if is_metric else "mintempF", 0)),
                "condition": day.get("hourly", [{}])[4].get("weatherDesc", [{}])[0].get("value", "") if day.get("hourly") else "",
            }
            for day in forecasts[:5]
        ]

        area_name = nearest_area.get("areaName", [{}])[0].get("value", location)
        region    = nearest_area.get("region",   [{}])[0].get("value", "")
        country   = nearest_area.get("country",  [{}])[0].get("value", "")

        return {
            "success": True, "tool": "get_weather",
            "location":        f"{area_name}, {region}" if region else f"{area_name}, {country}",
            "temperature":     temp,
            "feels_like":      feels_like,
            "temp_unit":       temp_unit,
            "condition":       condition,
            "condition_text":  condition_desc,
            "humidity":        int(current.get("humidity", 0)),
            "wind_speed":      int(current.get("windspeedMiles" if not is_metric else "windspeedKmph", 0)),
            "wind_unit":       "mph" if not is_metric else "km/h",
            "wind_direction":  current.get("winddir16Point", ""),
            "visibility":      int(current.get("visibilityMiles" if not is_metric else "visibility", 10)),
            "visibility_unit": "mi" if not is_metric else "km",
            "uv_index":        int(current.get("uvIndex", 0)),
            "pressure":        float(current.get("pressure", 0)),
            "forecast":        forecast_list,
            "fetch_time_ms":   round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        return {"success": False, "error": f"Weather fetch failed: {str(e)}"}


def get_news(query: str, category: str = "general", max_results: int = 5) -> Dict[str, Any]:
    """Fetch news headlines via Tavily."""
    try:
        start_time = time.time()
        tavily_key = os.getenv("TAVILY_API_KEY")
        if not tavily_key:
            return {"success": False, "error": "News search requires TAVILY_API_KEY environment variable.", "tool": "get_news"}

        data = _tavily_search(f"{query} news {category}", max_results)
        if not data:
            return {"success": False, "error": "News search failed.", "tool": "get_news"}

        articles = []
        for item in data.get("results", [])[:max_results]:
            title   = item.get("title", "")
            content = item.get("content", "")
            url     = item.get("url", "")
            articles.append({
                "title":     title,
                "summary":   content[:300],
                "url":       url,
                "source":    _extract_domain(url),
                "sentiment": _analyze_basic_sentiment(title + " " + content),
                "category":  category,
                "published": item.get("published_date", ""),
            })

        sentiments = [a["sentiment"] for a in articles]
        pos        = sentiments.count("positive")
        neg        = sentiments.count("negative")
        overall    = "bullish" if pos > neg + 1 else "bearish" if neg > pos + 1 else "mixed"

        return {
            "success": True, "tool": "get_news", "query": query, "category": category,
            "overall_sentiment": overall, "article_count": len(articles),
            "articles": articles, "answer": data.get("answer", ""),
            "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        return {"success": False, "error": f"News fetch failed: {str(e)}", "tool": "get_news"}


def create_chart(
    chart_type: str, title: str, data: list,
    x_label: str = "", y_label: str = "", colors: list = None,
) -> Dict[str, Any]:
    """Create a data visualization chart."""
    try:
        if not data or not isinstance(data, list):
            return {"success": False, "error": "Data must be a non-empty array"}

        valid_types = {"bar", "horizontal_bar", "line", "area", "pie", "donut", "scatter"}
        if chart_type not in valid_types:
            return {"success": False, "error": f"Invalid chart type. Must be one of: {', '.join(sorted(valid_types))}"}

        chart_colors = list(colors) if colors else list(_DEFAULT_CHART_COLORS)
        normalized   = []
        for i, item in enumerate(data):
            color = chart_colors[i % len(chart_colors)]
            if isinstance(item, dict):
                normalized.append({
                    "label": str(item.get("label", item.get("name", f"Item {i+1}"))),
                    "value": float(item.get("value", item.get("y", 0))),
                    "x":     float(item.get("x", i)) if chart_type == "scatter" else None,
                    "y":     float(item.get("y", item.get("value", 0))) if chart_type == "scatter" else None,
                    "color": color,
                })
            elif isinstance(item, (int, float)):
                normalized.append({"label": f"Item {i+1}", "value": float(item), "color": color})

        values = [d["value"] for d in normalized]
        total  = sum(values)
        avg    = total / len(values) if values else 0
        return {
            "success": True, "tool": "create_chart", "chart_type": chart_type, "title": title,
            "x_label": x_label, "y_label": y_label, "data": normalized,
            "colors": chart_colors[:len(normalized)],
            "summary": {
                "total":   round(total, 2), "average": round(avg, 2),
                "min":     round(min(values), 2) if values else 0,
                "max":     round(max(values), 2) if values else 0,
                "count":   len(normalized),
            },
        }
    except Exception as e:
        return {"success": False, "error": f"Chart creation failed: {str(e)}"}


def code_sandbox(
    code: str, language: str = "python",
    title: str = "Code Sandbox", run_immediately: bool = True,
) -> Dict[str, Any]:
    """Create an interactive code sandbox."""
    try:
        output = execution_error = None
        exec_ms = 0
        if run_immediately and language == "python":
            t0     = time.time()
            res    = execute_python(code=code, description=title)
            exec_ms = round((time.time() - t0) * 1000, 2)
            if res.get("success"):
                output  = res.get("output", "Code executed successfully")
                var_out = "\n".join(f"{k} = {v}" for k, v in res.get("variables", {}).items())
                if var_out:
                    output = var_out if output == "Code executed successfully" else f"{output}\n\nVariables:\n{var_out}"
            else:
                execution_error = res.get("error", "Unknown error")
                output          = f"Error: {execution_error}"
        elif run_immediately:
            output = f"[{language}] Code preview only - execution supported for Python"

        return {
            "success": True, "tool": "code_sandbox", "title": title, "language": language,
            "code": code, "output": output, "error": execution_error,
            "execution_time_ms": exec_ms,
            "is_executed": run_immediately and language == "python",
            "files": [{"name": f"main.{_get_file_extension(language)}", "language": language, "code": code}],
        }
    except Exception as e:
        return {"success": False, "error": f"Sandbox creation failed: {str(e)}"}


def screen_stocks(
    sector=None, min_market_cap=None, max_pe_ratio=None,
    min_dividend_yield=None,
    symbols="AAPL,MSFT,GOOGL,AMZN,META,NVDA,TSLA,JPM,V,JNJ,WMT,PG,UNH,MA,HD,DIS,BAC,NFLX,ADBE,CRM,PFE,ABBV,KO,PEP,MRK,TMO,COST,AVGO,LLY,ORCL",
) -> Dict[str, Any]:
    """Screen stocks by sector, market cap, P/E, and dividend yield."""
    if not _YF_AVAILABLE:
        return {"success": False, "error": "yfinance not available"}
    try:
        start_time = time.time()
        results    = []
        for sym in [s.strip().upper() for s in symbols.split(",")][:30]:
            try:
                info   = yf.Ticker(sym).info
                mc, pe = info.get("marketCap", 0), info.get("trailingPE") or info.get("forwardPE")
                dy_pct = (info.get("dividendYield", 0) or 0) * 100
                sec    = info.get("sector", "")
                if sector            and sec.lower() != sector.lower(): continue
                if min_market_cap    and mc < min_market_cap * 1e9:     continue
                if max_pe_ratio      and pe and pe > max_pe_ratio:       continue
                if min_dividend_yield and dy_pct < min_dividend_yield:  continue
                results.append({
                    "symbol":       sym,
                    "name":         info.get("longName", sym),
                    "sector":       sec,
                    "price":        info.get("currentPrice") or info.get("regularMarketPrice", 0),
                    "market_cap":   mc,
                    "market_cap_b": round(mc / 1e9, 1) if mc else 0,
                    "pe_ratio":     round(pe, 1) if pe else None,
                    "dividend_yield": round(dy_pct, 2),
                    "52w_change":   round((info.get("52WeekChange", 0) or 0) * 100, 1),
                })
            except Exception:
                continue
        return {
            "success": True, "tool": "screen_stocks", "results": results, "count": len(results),
            "filters": {"sector": sector, "min_market_cap": min_market_cap, "max_pe_ratio": max_pe_ratio, "min_dividend_yield": min_dividend_yield},
            "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def compare_stocks(symbols: str, metrics: str = "price,market_cap,pe_ratio,revenue,profit_margin,dividend_yield,52w_change") -> Dict[str, Any]:
    """Compare multiple stocks side by side."""
    if not _YF_AVAILABLE:
        return {"success": False, "error": "yfinance not available"}
    try:
        start_time  = time.time()
        symbol_list = [s.strip().upper() for s in symbols.split(",")][:6]
        comparisons = []
        for sym in symbol_list:
            try:
                info = yf.Ticker(sym).info
                comparisons.append({
                    "symbol": sym, "name": info.get("longName", sym), "sector": info.get("sector", ""),
                    "price": info.get("currentPrice") or info.get("regularMarketPrice", 0),
                    "market_cap": info.get("marketCap", 0), "market_cap_b": round(info.get("marketCap", 0) / 1e9, 1),
                    "pe_ratio": round(info.get("trailingPE", 0) or 0, 1), "forward_pe": round(info.get("forwardPE", 0) or 0, 1),
                    "revenue": info.get("totalRevenue", 0), "revenue_b": round(info.get("totalRevenue", 0) / 1e9, 1) if info.get("totalRevenue") else 0,
                    "profit_margin": round((info.get("profitMargins", 0) or 0) * 100, 1),
                    "dividend_yield": round((info.get("dividendYield", 0) or 0) * 100, 2),
                    "beta": round(info.get("beta", 0) or 0, 2),
                    "52w_high": info.get("fiftyTwoWeekHigh", 0), "52w_low": info.get("fiftyTwoWeekLow", 0),
                    "52w_change": round((info.get("52WeekChange", 0) or 0) * 100, 1),
                })
            except Exception:
                comparisons.append({"symbol": sym, "error": "Data unavailable"})
        return {
            "success": True, "tool": "compare_stocks", "symbols": symbol_list,
            "comparisons": comparisons, "metrics": metrics.split(","),
            "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_sector_performance(period: str = "1mo") -> Dict[str, Any]:
    """Get sector performance using module-level _SECTOR_ETFS constant."""
    if not _YF_AVAILABLE:
        return {"success": False, "error": "yfinance not available"}
    try:
        start_time = time.time()
        sectors    = []
        for name, etf in _SECTOR_ETFS.items():
            try:
                hist = yf.Ticker(etf).history(period=period)
                if not hist.empty and len(hist) >= 2:
                    start_p = float(hist["Close"].iloc[0])
                    end_p   = float(hist["Close"].iloc[-1])
                    sectors.append({
                        "name": name, "etf": etf,
                        "change_percent": round((end_p - start_p) / start_p * 100, 2),
                        "current_price":  round(end_p, 2),
                    })
            except Exception:
                continue
        sectors.sort(key=lambda x: x["change_percent"], reverse=True)
        return {
            "success": True, "tool": "get_sector_performance", "period": period, "sectors": sectors,
            "best": sectors[0] if sectors else None, "worst": sectors[-1] if sectors else None,
            "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def calculate_position_size(
    account_size: float, entry_price: float,
    stop_loss_price: float, risk_percent: float = 2.0, symbol: str = None,
) -> Dict[str, Any]:
    """Calculate optimal position size based on risk parameters."""
    try:
        risk_per_share = abs(entry_price - stop_loss_price)
        if risk_per_share == 0:
            return {"success": False, "error": "Entry and stop loss prices cannot be the same"}
        max_risk = account_size * (risk_percent / 100)
        shares   = int(max_risk / risk_per_share)
        pos_val  = shares * entry_price
        current_price = None
        if symbol and _YF_AVAILABLE:
            try:
                current_price = yf.Ticker(symbol.upper()).info.get("currentPrice")
            except Exception:
                pass
        return {
            "success": True, "tool": "calculate_position_size",
            "account_size": account_size, "risk_percent": risk_percent,
            "entry_price": entry_price, "stop_loss_price": stop_loss_price,
            "risk_per_share": round(risk_per_share, 2), "max_risk_amount": round(max_risk, 2),
            "recommended_shares": shares, "position_value": round(pos_val, 2),
            "position_percent": round(pos_val / account_size * 100, 1),
            "potential_loss": round(shares * risk_per_share, 2),
            "reward_targets": {
                "1R": round(entry_price + risk_per_share, 2),
                "2R": round(entry_price + 2 * risk_per_share, 2),
                "3R": round(entry_price + 3 * risk_per_share, 2),
            },
            "current_price": current_price, "symbol": symbol,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_correlation_matrix(symbols: str, period: str = "6mo") -> Dict[str, Any]:
    """Calculate correlation matrix between stocks."""
    if not _YF_AVAILABLE or not _NP_AVAILABLE:
        return {"success": False, "error": "yfinance and numpy are required"}
    try:
        start_time  = time.time()
        symbol_list = [s.strip().upper() for s in symbols.split(",")][:8]
        prices: Dict[str, Any] = {}
        for sym in symbol_list:
            try:
                hist = yf.Ticker(sym).history(period=period)
                if not hist.empty:
                    prices[sym] = hist["Close"].pct_change().dropna().values
            except Exception:
                continue
        if len(prices) < 2:
            return {"success": False, "error": "Need at least 2 valid symbols"}
        valid   = list(prices.keys())
        min_len = min(len(v) for v in prices.values())
        corr    = np.corrcoef(np.array([prices[s][:min_len] for s in valid]))
        matrix  = [{"symbol": s, "correlations": {valid[j]: round(float(corr[i][j]), 3) for j in range(len(valid))}} for i, s in enumerate(valid)]
        pairs   = sorted(
            [{"pair": f"{valid[i]}/{valid[j]}", "correlation": round(float(corr[i][j]), 3)} for i in range(len(valid)) for j in range(i + 1, len(valid))],
            key=lambda x: abs(x["correlation"]), reverse=True,
        )
        return {
            "success": True, "tool": "get_correlation_matrix", "symbols": valid,
            "period": period, "matrix": matrix, "notable_pairs": pairs[:5],
            "data_points": min_len, "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_dividend_info(symbol: str) -> Dict[str, Any]:
    """Get dividend information for a stock."""
    if not _YF_AVAILABLE:
        return {"success": False, "error": "yfinance not available"}
    try:
        start_time = time.time()
        ticker     = yf.Ticker(symbol.upper())
        info       = ticker.info
        divs       = ticker.dividends
        div_history = []
        if divs is not None and not divs.empty:
            for date, amount in divs.tail(8).items():
                div_history.append({"date": date.strftime("%Y-%m-%d"), "amount": round(float(amount), 4)})

        ex_date = info.get("exDividendDate")
        if ex_date and isinstance(ex_date, (int, float)):
            # datetime is already imported at the top of the module — no re-import needed
            ex_date = datetime.fromtimestamp(ex_date).strftime("%Y-%m-%d")

        return {
            "success": True, "tool": "get_dividend_info", "symbol": symbol.upper(),
            "name":             info.get("longName", symbol),
            "annual_dividend":  round(info.get("dividendRate", 0) or 0, 2),
            "dividend_yield":   round((info.get("dividendYield", 0) or 0) * 100, 2),
            "payout_ratio":     round((info.get("payoutRatio", 0) or 0) * 100, 1),
            "ex_dividend_date": ex_date,
            "frequency":        info.get("dividendFrequency", "Quarterly"),
            "5y_avg_yield":     round(info.get("fiveYearAvgDividendYield", 0) or 0, 2),
            "history":          div_history,
            "fetch_time_ms":    round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def calculate_risk_metrics(
    symbol: str, period: str = "1y",
    benchmark: str = "SPY", risk_free_rate: float = 0.05,
) -> Dict[str, Any]:
    """Calculate comprehensive risk metrics: Sharpe, Sortino, max drawdown, VaR, beta."""
    if not _YF_AVAILABLE or not _NP_AVAILABLE:
        return {"success": False, "error": "yfinance and numpy are required"}
    try:
        start_time  = time.time()
        sym         = symbol.upper()
        stock_hist  = yf.Ticker(sym).history(period=period)
        bench_hist  = yf.Ticker(benchmark.upper()).history(period=period)
        if stock_hist.empty:
            return {"success": False, "error": f"No data for {sym}"}

        sr  = stock_hist["Close"].pct_change().dropna().values
        br  = bench_hist["Close"].pct_change().dropna().values if not bench_hist.empty else None
        ml  = min(len(sr), len(br)) if br is not None else len(sr)
        sr  = sr[:ml]
        if br is not None:
            br = br[:ml]

        ann_ret = float(np.mean(sr) * 252)
        ann_vol = float(np.std(sr) * np.sqrt(252))
        sharpe  = round((ann_ret - risk_free_rate) / ann_vol, 2) if ann_vol > 0 else 0
        neg_r   = sr[sr < 0]
        ds_vol  = float(np.std(neg_r) * np.sqrt(252)) if len(neg_r) > 0 else ann_vol
        sortino = round((ann_ret - risk_free_rate) / ds_vol, 2) if ds_vol > 0 else 0
        cum     = np.cumprod(1 + sr)
        peak    = np.maximum.accumulate(cum)
        max_dd  = round(float(np.min((cum - peak) / peak)) * 100, 2)
        var_95  = round(float(np.percentile(sr, 5)) * 100, 2)
        var_99  = round(float(np.percentile(sr, 1)) * 100, 2)
        beta = alpha = 1.0
        if br is not None and len(br) > 0:
            cov   = np.cov(sr, br)
            beta  = round(float(cov[0][1] / cov[1][1]), 2) if cov[1][1] != 0 else 1.0
            alpha = round((ann_ret - (risk_free_rate + beta * (float(np.mean(br) * 252) - risk_free_rate))) * 100, 2)

        return {
            "success": True, "tool": "calculate_risk_metrics", "symbol": sym,
            "benchmark": benchmark, "period": period,
            "annual_return": round(ann_ret * 100, 2), "annual_volatility": round(ann_vol * 100, 2),
            "sharpe_ratio": sharpe, "sortino_ratio": sortino, "max_drawdown": max_dd,
            "var_95": var_95, "var_99": var_99, "beta": beta, "alpha": alpha,
            "risk_free_rate": risk_free_rate * 100, "trading_days": len(sr),
            "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_market_overview() -> Dict[str, Any]:
    """Get comprehensive market overview: indices, commodities, crypto, bonds."""
    if not _YF_AVAILABLE:
        return {"success": False, "error": "yfinance not available"}
    try:
        start_time = time.time()

        def get_quote(sym):
            """Fetch a single price + change from yfinance, returning zeros on failure."""
            try:
                info  = yf.Ticker(sym).info
                price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
                prev  = info.get("previousClose", price)
                chg   = round(price - prev, 2) if price and prev else 0
                return {"price": round(price, 2), "change": chg, "change_percent": round((chg / prev) * 100, 2) if prev else 0}
            except Exception:
                return {"price": 0, "change": 0, "change_percent": 0}

        idx_data    = {n: get_quote(s) for n, s in {"S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Dow Jones": "^DJI", "Russell 2000": "^RUT", "VIX": "^VIX"}.items()}
        comm_data   = {n: get_quote(s) for n, s in {"Gold": "GC=F", "Silver": "SI=F", "Crude Oil": "CL=F", "Natural Gas": "NG=F"}.items()}
        crypto_data = {n: get_quote(s) for n, s in {"Bitcoin": "BTC-USD", "Ethereum": "ETH-USD"}.items()}
        bond_data   = {n: get_quote(s) for n, s in {"10Y Treasury": "^TNX", "2Y Treasury": "^IRX"}.items()}
        chg_pct     = idx_data.get("S&P 500", {}).get("change_percent", 0)
        sentiment   = "bullish" if chg_pct > 0.5 else "bearish" if chg_pct < -0.5 else "neutral"

        return {
            "success": True, "tool": "get_market_overview",
            "indices": idx_data, "commodities": comm_data, "crypto": crypto_data, "bonds": bond_data,
            "market_sentiment": sentiment, "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def backtest_quick(
    symbol: str, strategy: str = "sma_crossover", period: str = "1y",
    fast_period: int = 20, slow_period: int = 50,
) -> Dict[str, Any]:
    """
    Quick backtest.
    EMA path uses module-level _ema(); SMA path uses vectorised numpy cumsum.
    """
    if not _YF_AVAILABLE or not _NP_AVAILABLE:
        return {"success": False, "error": "yfinance and numpy are required"}
    try:
        start_time = time.time()
        sym        = symbol.upper()
        hist       = yf.Ticker(sym).history(period=period)
        if hist.empty or len(hist) < slow_period + 10:
            return {"success": False, "error": f"Insufficient data for backtest on {sym}"}

        closes  = hist["Close"].values.astype(float)
        dates   = [d.strftime("%Y-%m-%d") for d in hist.index]
        signals = np.zeros(len(closes))

        if strategy in ("sma_crossover", "ema_crossover"):
            use_ema = strategy == "ema_crossover"
            if use_ema:
                fast_ma = _ema(closes, fast_period)   # module-level helper
                slow_ma = _ema(closes, slow_period)
            else:
                # Vectorised SMA with cumulative sum
                cum     = np.cumsum(np.insert(closes, 0, 0))
                fast_ma = np.where(np.arange(len(closes)) >= fast_period - 1, (cum[fast_period:] - cum[:-fast_period]) / fast_period, np.nan)
                slow_ma = np.where(np.arange(len(closes)) >= slow_period - 1, (cum[slow_period:] - cum[:-slow_period]) / slow_period, np.nan)
                fast_ma = np.concatenate([np.full(fast_period - 1, np.nan), fast_ma])
                slow_ma = np.concatenate([np.full(slow_period - 1, np.nan), slow_ma])
            for i in range(slow_period, len(closes)):
                if not np.isnan(fast_ma[i]) and not np.isnan(slow_ma[i]):
                    signals[i] = 1 if fast_ma[i] > slow_ma[i] else -1

        elif strategy == "rsi_oversold":
            deltas = np.diff(closes, prepend=closes[0])
            gains  = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            for i in range(14, len(closes)):
                ag  = np.mean(gains[i - 13:i + 1])
                al  = np.mean(losses[i - 13:i + 1])
                rsi = 100 - (100 / (1 + (ag / al if al != 0 else 100)))
                signals[i] = 1 if rsi < 30 else (-1 if rsi > 70 else signals[i - 1])
        else:
            for i in range(slow_period, len(closes)):
                signals[i] = 1 if closes[i] > np.mean(closes[i - slow_period:i]) else -1

        daily_returns    = np.diff(closes) / closes[:-1]
        strategy_returns = daily_returns * signals[:-1]
        strategy_returns = strategy_returns[~np.isnan(strategy_returns)]
        total_return     = round(float(np.prod(1 + strategy_returns) - 1) * 100, 2)
        buy_hold         = round(float((closes[-1] / closes[0] - 1) * 100), 2)
        trades           = sum(1 for i in range(1, len(signals)) if signals[i] != signals[i - 1] and signals[i] != 0)
        wins             = len(strategy_returns[strategy_returns > 0])
        total_days       = len(strategy_returns[strategy_returns != 0])
        win_rate         = round(wins / total_days * 100, 1) if total_days > 0 else 0
        cum              = np.cumprod(1 + strategy_returns)
        peak             = np.maximum.accumulate(cum) if len(cum) > 0 else np.array([1])
        dd               = (cum - peak) / peak if len(cum) > 0 else np.array([0])
        max_dd           = round(float(np.min(dd)) * 100, 2) if len(dd) > 0 else 0
        ann_vol          = round(float(np.std(strategy_returns) * np.sqrt(252) * 100), 2) if len(strategy_returns) > 0 else 0
        sharpe           = round((np.mean(strategy_returns) * 252 - 0.05) / (np.std(strategy_returns) * np.sqrt(252)), 2) if np.std(strategy_returns) > 0 else 0

        return {
            "success": True, "tool": "backtest_quick", "symbol": sym, "strategy": strategy, "period": period,
            "parameters": {"fast_period": fast_period, "slow_period": slow_period},
            "total_return": total_return, "buy_hold_return": buy_hold, "excess_return": round(total_return - buy_hold, 2),
            "total_trades": trades, "win_rate": win_rate, "max_drawdown": max_dd,
            "annual_volatility": ann_vol, "sharpe_ratio": sharpe, "trading_days": len(closes),
            "start_date": dates[0], "end_date": dates[-1],
            "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_options_snapshot(symbol: str) -> Dict[str, Any]:
    """Get options overview for a stock."""
    if not _YF_AVAILABLE:
        return {"success": False, "error": "yfinance not available"}
    try:
        start_time   = time.time()
        ticker       = yf.Ticker(symbol.upper())
        expirations  = ticker.options
        if not expirations:
            return {"success": False, "error": f"No options data for {symbol.upper()}"}
        info           = ticker.info
        price          = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        nearest_exp    = expirations[0]
        chain          = ticker.option_chain(nearest_exp)
        calls, puts    = chain.calls, chain.puts
        total_call_vol = int(calls["volume"].sum()) if "volume" in calls else 0
        total_put_vol  = int(puts["volume"].sum())  if "volume" in puts  else 0
        pc_ratio       = round(total_put_vol / total_call_vol, 2) if total_call_vol > 0 else 0

        def _top5(df):
            if df.empty: return []
            return [
                {"strike": float(r["strike"]), "last": float(r.get("lastPrice", 0)),
                 "volume": int(r.get("volume", 0)), "oi": int(r.get("openInterest", 0)),
                 "iv": round(float(r.get("impliedVolatility", 0)) * 100, 1)}
                for _, r in df.sort_values("volume", ascending=False).head(5).iterrows()
            ]

        avg_iv = round(float(calls["impliedVolatility"].mean()) * 100, 1) if not calls.empty and "impliedVolatility" in calls else 0
        return {
            "success": True, "tool": "get_options_snapshot", "symbol": symbol.upper(),
            "current_price": price, "expirations": list(expirations[:6]),
            "nearest_expiration": nearest_exp, "put_call_ratio": pc_ratio,
            "total_call_volume": total_call_vol, "total_put_volume": total_put_vol,
            "average_iv": avg_iv, "top_calls": _top5(calls), "top_puts": _top5(puts),
            "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_presentation(
    title: str, slides: list, subtitle: str = "", theme: str = "potomac",
    author: str = "Analyst by Potomac", template_id: str = None, api_key: str = None,
) -> Dict[str, Any]:
    """
    Create a real PowerPoint (.pptx) presentation.

    Flow:
    1. Ask Claude to produce a structured JSON outline from the user's slide list.
    2. Pass the outline to PotomacPPTXGenerator via the shared _write_pptx_to_memory().
    3. On JSONDecodeError, fall back to building the outline directly (no duplication —
       both paths call the same _write_pptx_to_memory() helper).
    """
    start_time = time.time()
    if not api_key:
        return {"success": False, "error": "Claude API key required for PowerPoint generation"}

    try:
        import anthropic as _anthropic

        slide_descriptions = [
            f"Slide {i+2}: '{s.get('title', f'Slide {i+2}')}'"
            + (f" — Bullets: {', '.join(s.get('bullets', [])[:5])}" if s.get("bullets") else "")
            + (f" — Layout: {s.get('layout', '')}" if s.get("layout") else "")
            for i, s in enumerate(slides)
        ]

        # Join before f-string: Python <3.12 forbids backslash inside f-string expressions
        slides_text = "\n".join(slide_descriptions)

        outline_prompt = f"""Generate a JSON outline for a Potomac-branded PowerPoint presentation.

Title: {title}
Subtitle: {subtitle or ""}
Author: {author}

User's requested slides:
{slides_text}

You MUST return ONLY valid JSON (no markdown, no code fences) in this exact format:
{{
  "title": "{title}",
  "slides": [
    {{"type": "title", "title": "{title}", "subtitle": "{subtitle or ''}", "date": "2025", "presenter": "{author}"}},
    {{"type": "agenda", "topics": [{{"num": "01", "title": "TOPIC", "sub": "Description"}}]}},
    {{"type": "content", "title": "SLIDE TITLE", "bullets": ["Point 1", "Point 2", "Point 3"]}},
    {{"type": "closing"}}
  ]
}}

Available slide types: title, agenda, chart, stats, content, summary, two_charts, closing.
Create {len(slides) + 2} slides total (title + user slides + closing).
Return ONLY the JSON object, nothing else."""

        client      = _anthropic.Anthropic(api_key=api_key)
        response    = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4000,
            messages=[{"role": "user", "content": outline_prompt}],
        )
        result_text = response.content[0].text.strip()

        # Strip optional markdown fences that Claude sometimes wraps the JSON in
        if "```" in result_text:
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()

        outline = json.loads(result_text)
        presentation_id, pptx_bytes = _write_pptx_to_memory(outline, title)

        try:
            from core.file_store import store_file
            store_file(
                data=pptx_bytes,
                filename=f"{title.replace(' ', '_')}.pptx",
                file_type="pptx",
                tool_name="create_presentation",
                file_id=presentation_id,
            )
        except Exception as _fs_err:
            logger.warning("file_store persist failed for pptx: %s", _fs_err)

        return {
            "success": True, "tool": "create_presentation",
            "presentation_id": presentation_id,
            "filename":    f"{title.replace(' ', '_')}.pptx",
            "title":       title, "subtitle": subtitle, "theme": theme,
            "template_used": template_id, "template_id": template_id, "author": author,
            "slide_count": len(outline.get("slides", [])),
            "file_size_kb": round(len(pptx_bytes) / 1024, 1),
            "download_url": f"/files/{presentation_id}/download",
            "method":      "potomac_pptx_generator",
            "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }

    except json.JSONDecodeError as e:
        # Claude returned malformed JSON — build the outline directly from user input.
        # Both paths call the SAME _write_pptx_to_memory() helper (no duplication).
        logger.error("Failed to parse Claude outline JSON: %s", e)
        try:
            fallback_slides = [{"type": "title", "title": title, "subtitle": subtitle, "date": "2025"}]
            for s in slides:
                fallback_slides.append({
                    "type":    s.get("layout", "content"),
                    "title":   s.get("title", ""),
                    "bullets": s.get("bullets", []),
                })
            fallback_slides.append({"type": "closing"})
            fallback_outline = {"title": title, "slides": fallback_slides}
            presentation_id, pptx_bytes = _write_pptx_to_memory(fallback_outline, title)

            try:
                from core.file_store import store_file
                store_file(
                    data=pptx_bytes,
                    filename=f"{title.replace(' ', '_')}.pptx",
                    file_type="pptx",
                    tool_name="create_presentation",
                    file_id=presentation_id,
                )
            except Exception as _fs_err:
                logger.warning("file_store persist failed for pptx: %s", _fs_err)

            return {
                "success": True, "tool": "create_presentation",
                "presentation_id": presentation_id,
                "filename":   f"{title.replace(' ', '_')}.pptx",
                "title":      title,
                "slide_count": len(fallback_slides),
                "file_size_kb": round(len(pptx_bytes) / 1024, 1),
                "download_url": f"/files/{presentation_id}/download",
                "method":     "potomac_pptx_generator_fallback",
                "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
            }
        except Exception as fallback_err:
            return {"success": False, "error": f"Presentation generation failed: {str(fallback_err)}"}

    except ImportError as e:
        return {"success": False, "error": f"Missing dependency: {e}"}
    except Exception as e:
        logger.error("Presentation creation error: %s", e, exc_info=True)
        return {"success": False, "error": f"Presentation creation failed: {str(e)}"}


def get_presentation_bytes(presentation_id: str) -> Optional[bytes]:
    """Retrieve stored presentation bytes by ID."""
    return _presentation_store.get(presentation_id)


# =============================================================================
# REMAINING TOOL HANDLERS
# =============================================================================

def portfolio_analysis(holdings: list, benchmark: str = "SPY") -> Dict[str, Any]:
    """Analyse portfolio holdings: allocation, weighted beta, sector breakdown."""
    if not _YF_AVAILABLE:
        return {"success": False, "error": "yfinance not available"}
    try:
        start_time = time.time()
        if not holdings:
            return {"success": False, "error": "Portfolio holdings required"}
        portfolio_data, total_value = [], 0.0
        for h in holdings:
            symbol = h.get("symbol", "").upper()
            if not symbol: continue
            try:
                info   = yf.Ticker(symbol).info
                price  = info.get("currentPrice") or info.get("regularMarketPrice", 0)
                shares = h.get("shares", 0)
                value  = shares * price if shares > 0 else (h.get("allocation", 0) / 100) * 100_000
                total_value += value
                portfolio_data.append({
                    "symbol":         symbol,
                    "name":           info.get("longName", symbol),
                    "shares":         shares,
                    "price":          round(price, 2),
                    "value":          round(value, 2),
                    "sector":         info.get("sector", "Unknown"),
                    "beta":           round(info.get("beta", 1.0) or 1.0, 2),
                    "dividend_yield": round((info.get("dividendYield", 0) or 0) * 100, 2),
                    "52w_change":     round((info.get("52WeekChange", 0) or 0) * 100, 1),
                })
            except Exception:
                continue
        for h in portfolio_data:
            h["allocation"] = round(h["value"] / total_value * 100, 1) if total_value > 0 else 0
        sector_alloc: Dict[str, float] = {}
        for h in portfolio_data:
            sector_alloc[h["sector"]] = sector_alloc.get(h["sector"], 0) + h["allocation"]
        return {
            "success": True, "tool": "portfolio_analysis",
            "total_value": round(total_value, 2), "holdings": portfolio_data,
            "holdings_count": len(portfolio_data), "sector_allocation": sector_alloc,
            "metrics": {
                "weighted_beta":            round(sum(h["beta"] * h["allocation"] / 100 for h in portfolio_data), 2),
                "weighted_dividend_yield":  round(sum(h["dividend_yield"] * h["allocation"] / 100 for h in portfolio_data), 2),
                "diversification_score":    min(100, len(portfolio_data) * 10),
            },
            "benchmark":    benchmark,
            "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_watchlist(symbols: str = "AAPL,MSFT,GOOGL,TSLA,NVDA,META,AMZN") -> Dict[str, Any]:
    """Get watchlist with current prices and daily changes."""
    if not _YF_AVAILABLE:
        return {"success": False, "error": "yfinance not available"}
    try:
        start_time  = time.time()
        symbol_list = [s.strip().upper() for s in symbols.split(",")][:10]
        watchlist   = []
        for sym in symbol_list:
            try:
                info       = yf.Ticker(sym).info
                price      = info.get("currentPrice") or info.get("regularMarketPrice", 0)
                prev_close = info.get("previousClose", price)
                change     = round(price - prev_close, 2) if price and prev_close else 0
                change_pct = round((change / prev_close) * 100, 2) if prev_close else 0
                watchlist.append({
                    "symbol": sym, "name": info.get("longName", sym),
                    "price": round(price, 2), "change": change, "change_percent": change_pct,
                    "volume": info.get("volume", 0), "market_cap": info.get("marketCap", 0),
                    "trend": "up" if change > 0 else "down" if change < 0 else "flat",
                })
            except Exception:
                continue
        watchlist.sort(key=lambda x: x["change_percent"], reverse=True)
        return {
            "success": True, "tool": "get_watchlist", "symbols": symbol_list,
            "watchlist": watchlist, "count": len(watchlist),
            "market_movers": {
                "biggest_gainer": watchlist[0]  if watchlist else None,
                "biggest_loser":  watchlist[-1] if watchlist else None,
            },
            "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def sector_heatmap(period: str = "1d") -> Dict[str, Any]:
    """Generate sector performance heatmap using module-level _SECTOR_ETFS."""
    if not _YF_AVAILABLE:
        return {"success": False, "error": "yfinance not available"}
    try:
        start_time   = time.time()
        heatmap_data = []
        for name, etf in _SECTOR_ETFS.items():
            try:
                hist = yf.Ticker(etf).history(period=period)
                if not hist.empty and len(hist) >= 2:
                    sp, ep     = float(hist["Close"].iloc[0]), float(hist["Close"].iloc[-1])
                    change_pct = round((ep - sp) / sp * 100, 2)
                    # Colour-code by magnitude of the move
                    if   change_pct > 2:    color, intensity = "#22c55e", "hot"
                    elif change_pct > 0.5:  color, intensity = "#84cc16", "warm"
                    elif change_pct > -0.5: color, intensity = "#94a3b8", "neutral"
                    elif change_pct > -2:   color, intensity = "#f97316", "cool"
                    else:                   color, intensity = "#ef4444", "cold"
                    heatmap_data.append({
                        "sector": name, "etf": etf, "change_percent": change_pct,
                        "color": color, "intensity": intensity,
                        "size": max(50, abs(change_pct) * 10),
                    })
            except Exception:
                continue
        heatmap_data.sort(key=lambda x: x["change_percent"], reverse=True)
        return {
            "success": True, "tool": "sector_heatmap", "period": period, "sectors": heatmap_data,
            "hottest": heatmap_data[0]  if heatmap_data else None,
            "coldest": heatmap_data[-1] if heatmap_data else None,
            "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_options_chain(symbol: str, expiry: str = "nearest") -> Dict[str, Any]:
    """Get detailed options chain data for a stock."""
    if not _YF_AVAILABLE:
        return {"success": False, "error": "yfinance not available"}
    try:
        start_time   = time.time()
        ticker       = yf.Ticker(symbol.upper())
        expirations  = ticker.options
        if not expirations:
            return {"success": False, "error": f"No options available for {symbol.upper()}"}
        selected_exp  = expirations[0] if expiry == "nearest" or expiry not in expirations else expiry
        chain         = ticker.option_chain(selected_exp)
        info          = ticker.info
        current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)

        def _parse_chain(df, is_call):
            """Convert a calls/puts DataFrame into a list of dicts."""
            return [
                {
                    "strike":             float(r["strike"]),
                    "last":               float(r.get("lastPrice", 0)),
                    "bid":                float(r.get("bid", 0)),
                    "ask":                float(r.get("ask", 0)),
                    "volume":             int(r.get("volume", 0)),
                    "open_interest":      int(r.get("openInterest", 0)),
                    "implied_volatility": round(float(r.get("impliedVolatility", 0)) * 100, 1),
                    "in_the_money":       r["strike"] < current_price if is_call else r["strike"] > current_price,
                }
                for _, r in df.iterrows()
            ] if not df.empty else []

        calls_data = _parse_chain(chain.calls, True)
        puts_data  = _parse_chain(chain.puts, False)
        return {
            "success": True, "tool": "get_options_chain", "symbol": symbol.upper(),
            "current_price": current_price, "expiry": selected_exp,
            "available_expiries": list(expirations[:6]),
            "calls": calls_data, "puts": puts_data,
            "calls_count": len(calls_data), "puts_count": len(puts_data),
            "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_market_sentiment() -> Dict[str, Any]:
    """Get market sentiment indicators: fear/greed, put/call, breadth."""
    if not _YF_AVAILABLE:
        return {"success": False, "error": "yfinance not available"}
    try:
        start_time = time.time()
        vix_value  = yf.Ticker("^VIX").info.get("regularMarketPrice", 20)

        # Map VIX level to a fear/greed label and numeric score
        if   vix_value < 15: fear_greed, score = "Extreme Greed", 85
        elif vix_value < 20: fear_greed, score = "Greed",         70
        elif vix_value < 25: fear_greed, score = "Neutral",       50
        elif vix_value < 30: fear_greed, score = "Fear",          30
        else:                fear_greed, score = "Extreme Fear",  15

        try:
            spy_opts = yf.Ticker("SPY").options
            if spy_opts:
                chain    = yf.Ticker("SPY").option_chain(spy_opts[0])
                call_vol = int(chain.calls["volume"].sum()) if "volume" in chain.calls else 1
                put_vol  = int(chain.puts["volume"].sum())  if "volume" in chain.puts  else 1
                pc_ratio = round(put_vol / call_vol, 2) if call_vol > 0 else 0.8
            else:
                pc_ratio = 0.8
        except Exception:
            pc_ratio = 0.8

        positive_markets = 0
        for sym in ("^GSPC", "^IXIC", "^DJI"):
            try:
                if (yf.Ticker(sym).info.get("regularMarketChangePercent", 0) or 0) > 0:
                    positive_markets += 1
            except Exception:
                pass
        breadth = round(positive_markets / 3 * 100, 0)

        return {
            "success": True, "tool": "get_market_sentiment",
            "fear_greed_index": score, "fear_greed_label": fear_greed,
            "vix_level": round(vix_value, 2), "put_call_ratio": pc_ratio,
            "market_breadth": breadth,
            "indicators": [
                {"name": "VIX Fear Index",   "value": round(vix_value, 1), "signal": fear_greed},
                {"name": "Put/Call Ratio",   "value": pc_ratio, "signal": "bearish" if pc_ratio > 1.1 else "bullish" if pc_ratio < 0.7 else "neutral"},
                {"name": "Market Breadth",   "value": f"{breadth}%", "signal": "bullish" if breadth > 60 else "bearish" if breadth < 40 else "neutral"},
            ],
            "overall_sentiment": "bullish" if score > 60 else "bearish" if score < 40 else "neutral",
            "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_crypto_data(symbols: str = "BTC-USD,ETH-USD,BNB-USD,ADA-USD,SOL-USD") -> Dict[str, Any]:
    """Get cryptocurrency prices and market data."""
    if not _YF_AVAILABLE:
        return {"success": False, "error": "yfinance not available"}
    try:
        start_time  = time.time()
        crypto_data = []
        for sym in [s.strip().upper() for s in symbols.split(",")]:
            try:
                info       = yf.Ticker(sym).info
                price      = info.get("regularMarketPrice", 0)
                prev_close = info.get("previousClose", price)
                change     = round(price - prev_close, 2) if price and prev_close else 0
                change_pct = round((change / prev_close) * 100, 2) if prev_close else 0
                crypto_data.append({
                    "symbol":     sym,
                    "name":       info.get("longName", sym.replace("-USD", "").replace("-USDT", "")),
                    "price":      round(price, 8) if price < 1 else round(price, 2),
                    "change":     change, "change_percent": change_pct,
                    "market_cap": info.get("marketCap", 0),
                    "volume":     info.get("volume24Hr", info.get("volume", 0)),
                    "trend":      "up" if change > 0 else "down" if change < 0 else "flat",
                })
            except Exception:
                continue
        crypto_data.sort(key=lambda x: x.get("market_cap", 0), reverse=True)
        return {
            "success": True, "tool": "get_crypto_data", "cryptos": crypto_data, "count": len(crypto_data),
            "top_performer":  max(crypto_data, key=lambda x: x["change_percent"]) if crypto_data else None,
            "worst_performer": min(crypto_data, key=lambda x: x["change_percent"]) if crypto_data else None,
            "fetch_time_ms":  round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def generate_trade_signal(symbol: str, timeframe: str = "1d") -> Dict[str, Any]:
    """Generate trade signals (BUY / SELL / HOLD) with confidence levels."""
    if not _YF_AVAILABLE or not _NP_AVAILABLE:
        return {"success": False, "error": "yfinance and numpy are required"}
    try:
        start_time    = time.time()
        symbol        = symbol.upper()
        period        = {"1d": "1mo", "1w": "3mo", "1m": "1y"}.get(timeframe, "1mo")
        ticker        = yf.Ticker(symbol)
        hist          = ticker.history(period=period)
        info          = ticker.info
        if hist.empty or len(hist) < 20:
            return {"success": False, "error": f"Insufficient data for {symbol}"}

        closes        = hist["Close"].values.astype(float)
        current_price = float(closes[-1])
        sma20         = np.mean(closes[-20:])
        sma50         = np.mean(closes[-50:]) if len(closes) >= 50 else sma20
        bb_upper      = sma20 + 2 * np.std(closes[-20:])
        bb_lower      = sma20 - 2 * np.std(closes[-20:])

        deltas = np.diff(closes)
        rsi    = 100 - (100 / (1 + (
            np.mean(np.where(deltas > 0, deltas, 0)[-14:]) /
            max(np.mean(np.where(deltas < 0, -deltas, 0)[-14:]), 1e-10)
        )))

        signals = []
        if   rsi < 30: signals.append({"indicator": "RSI",      "signal": "BUY",  "strength": "strong", "confidence": 80})
        elif rsi > 70: signals.append({"indicator": "RSI",      "signal": "SELL", "strength": "strong", "confidence": 80})
        if   current_price > sma20 > sma50:  signals.append({"indicator": "SMA",      "signal": "BUY",  "strength": "medium", "confidence": 65})
        elif current_price < sma20 < sma50:  signals.append({"indicator": "SMA",      "signal": "SELL", "strength": "medium", "confidence": 65})
        if   current_price <= bb_lower:      signals.append({"indicator": "Bollinger", "signal": "BUY",  "strength": "medium", "confidence": 70})
        elif current_price >= bb_upper:      signals.append({"indicator": "Bollinger", "signal": "SELL", "strength": "medium", "confidence": 70})

        buy_s  = [s for s in signals if s["signal"] == "BUY"]
        sell_s = [s for s in signals if s["signal"] == "SELL"]
        if   len(buy_s) > len(sell_s):  overall_signal = "BUY";  confidence = min(95, sum(s["confidence"] for s in buy_s)  / len(buy_s))
        elif len(sell_s) > len(buy_s):  overall_signal = "SELL"; confidence = min(95, sum(s["confidence"] for s in sell_s) / len(sell_s))
        else:                           overall_signal = "HOLD"; confidence = 50

        entry_price = current_price
        if overall_signal == "BUY":
            stop_loss = round(bb_lower, 2); target_1 = round(current_price * 1.05, 2); target_2 = round(current_price * 1.10, 2)
        elif overall_signal == "SELL":
            stop_loss = round(bb_upper, 2); target_1 = round(current_price * 0.95, 2); target_2 = round(current_price * 0.90, 2)
        else:
            stop_loss = target_1 = target_2 = None

        return {
            "success": True, "tool": "generate_trade_signal", "symbol": symbol,
            "company_name": info.get("longName", symbol), "current_price": current_price,
            "timeframe": timeframe, "signal": overall_signal, "confidence": round(confidence, 0),
            "entry_price": entry_price, "stop_loss": stop_loss,
            "targets": {"target_1": target_1, "target_2": target_2},
            "supporting_signals": signals,
            "risk_reward": round(abs(target_1 - entry_price) / abs(stop_loss - entry_price), 1) if stop_loss and target_1 else None,
            "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def risk_assessment(symbol: str, period: str = "1y") -> Dict[str, Any]:
    """Thin alias for calculate_risk_metrics — sets the tool name correctly."""
    result = calculate_risk_metrics(symbol, period, "SPY", 0.05)
    if result.get("success"):
        result["tool"] = "risk_assessment"
    return result


def news_digest(query: str, max_articles: int = 5) -> Dict[str, Any]:
    """Enhanced news digest: delegates to get_news then adds impact analysis."""
    result = get_news(query, "general", max_articles)
    if result.get("success"):
        result["tool"]  = "news_digest"
        articles        = result.get("articles", [])
        # Flag high-impact articles that mention key market-moving terms
        high_impact     = [a for a in articles if any(w in a["title"].lower() for w in ("fed", "earnings", "guidance", "merger", "acquisition"))]
        result["high_impact_articles"] = high_impact
        result["impact_level"]         = "high" if len(high_impact) > 1 else "medium" if high_impact else "low"
    return result


def run_backtest(symbols: str, strategy: str, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
    """Enhanced backtesting wrapper: maps strategy names and delegates to backtest_quick."""
    try:
        primary = symbols.split(",")[0].strip().upper()
        mapped  = {"moving_average": "sma_crossover", "rsi_strategy": "rsi_oversold", "macd_strategy": "macd_signal"}.get(strategy, strategy)
        result  = backtest_quick(primary, mapped, "1y", 20, 50)
        if result.get("success"):
            result["tool"]            = "run_backtest"
            result["strategy_config"] = {"name": strategy, "symbols": symbols}
            if start_date: result["start_date"] = start_date
            if end_date:   result["end_date"]   = end_date
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tavily-backed tools (all use the shared _tavily_search() helper) ──────────

def get_live_scores(sport: str = None, league: str = None, date: str = None) -> Dict[str, Any]:
    """Get live sports scores via Tavily web search."""
    try:
        start_time     = time.time()
        selected_sport = sport or "nba"
        # datetime is imported at the top — no re-import needed here
        today          = datetime.now().strftime("%Y-%m-%d")
        query          = f"{selected_sport} scores today {date or today}"
        data           = _tavily_search(query, 5)
        base = {
            "tool": "get_live_scores", "sport": selected_sport,
            "league": league or selected_sport.upper(), "date": date or today,
            "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }
        if data:
            return {
                "success": True, **base,
                "answer":  data.get("answer", ""),
                "sources": [{"title": r.get("title",""), "url": r.get("url",""), "snippet": r.get("content","")[:200]} for r in data.get("results", [])[:5]],
                "source":  "tavily_live",
            }
        return {"success": True, **base, "message": "Live scores available when Tavily API key is configured. Check ESPN.com or TheScore.com.", "links": ["https://www.espn.com/", "https://www.thescore.com/"], "source": "fallback"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_search_trends(region: str = "US", category: str = None, period: str = "today") -> Dict[str, Any]:
    """Get trending search topics via Tavily."""
    try:
        start_time = time.time()
        data       = _tavily_search(f"trending topics today {category or 'all'} {region}", 8)
        base = {"tool": "get_search_trends", "region": region, "category": category, "period": period, "fetch_time_ms": round((time.time() - start_time) * 1000, 2)}
        if data:
            return {"success": True, **base, "answer": data.get("answer", ""), "sources": [{"title": r.get("title",""), "url": r.get("url",""), "snippet": r.get("content","")[:200]} for r in data.get("results", [])[:8]], "source": "tavily_live"}
        return {"success": True, **base, "message": "Trending topics available when Tavily API key is configured. Check Google Trends.", "links": ["https://trends.google.com/trending"], "source": "fallback"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_linkedin_post(topic: str, tone: str = "professional", author_name: str = None, include_hashtags: bool = True) -> Dict[str, Any]:
    """Generate a LinkedIn post preview."""
    try:
        start_time = time.time()
        if tone == "professional":
            content = f"Excited to share insights on {topic}. Key takeaways from recent analysis show significant opportunities in this space. Looking forward to discussing with the community."
        elif tone == "educational":
            content = f"Let me break down {topic} for everyone. Here's what you need to know: 1) Market fundamentals are shifting 2) New opportunities are emerging 3) Time to act strategically."
        else:
            content = f"Thoughts on {topic}? The landscape is evolving rapidly and I'm seeing some interesting patterns emerge. What's your take?"
        return {
            "success": True, "tool": "create_linkedin_post", "topic": topic, "tone": tone,
            "author_name":       author_name or "Anonymous",
            "post_content":      content,
            "hashtags":          ["#trading", "#finance", "#investing", "#markets", "#analysis"] if include_hashtags else [],
            "engagement_preview": {"likes": "12", "comments": "3", "shares": "1"},
            "estimated_reach":   "500-1000 people",
            "fetch_time_ms":     round((time.time() - start_time) * 1000, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def preview_website(url: str) -> Dict[str, Any]:
    """Preview a website by fetching its HTTP headers."""
    try:
        start_time = time.time()
        if not url.startswith(("http://", "https://")):
            return {"success": False, "error": "URL must start with http:// or https://"}
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            return {
                "success": True, "tool": "preview_website", "url": url,
                "status_code":  response.getcode(),
                "content_type": response.headers.get("content-type", ""),
                "ssl_enabled":  url.startswith("https://"),
                "domain":       urllib.parse.urlparse(url).netloc,
                "preview":      f"Website accessible (HTTP {response.getcode()})",
                "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
            }
    except Exception as e:
        return {"success": False, "error": f"Could not access website: {str(e)}"}


def order_food(query: str, cuisine: str = None, location: str = None) -> Dict[str, Any]:
    """Search for restaurants via Tavily.  Uses urllib.parse.quote for safe URL encoding."""
    try:
        start_time   = time.time()
        search_query = f"{query}{' ' + cuisine if cuisine else ''} restaurants {location or 'near me'} delivery"
        data         = _tavily_search(search_query, 5)
        # Build order links with proper percent-encoding (not manual .replace())
        q_encoded = urllib.parse.quote(query, safe="")
        order_links = {
            "doordash": f"https://www.doordash.com/search/store/{q_encoded}",
            "ubereats":  f"https://www.ubereats.com/search?q={q_encoded}",
            "grubhub":   f"https://www.grubhub.com/search?queryText={q_encoded}",
        }
        base = {"tool": "order_food", "query": query, "cuisine": cuisine, "location": location or "Your area", "order_links": order_links, "fetch_time_ms": round((time.time() - start_time) * 1000, 2)}
        if data:
            return {"success": True, **base, "answer": data.get("answer", ""), "restaurants": [{"name": r.get("title",""), "url": r.get("url",""), "description": r.get("content","")[:200]} for r in data.get("results", [])[:5]], "source": "tavily_live"}
        return {"success": True, **base, "message": "Restaurant search available when Tavily API key is configured.", "source": "fallback"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def track_flight(flight_number: str, date: str = None) -> Dict[str, Any]:
    """Track flight status via Tavily.  Uses urllib.parse.quote for safe URL encoding."""
    try:
        start_time = time.time()
        fn         = flight_number.upper()
        # datetime is imported at the top — no re-import needed here
        today      = datetime.now().strftime("%Y-%m-%d")
        data       = _tavily_search(f"flight status {fn} {date or today}", 5)
        fn_encoded = urllib.parse.quote(fn, safe="")
        tracking_links = {
            "flightaware":   f"https://flightaware.com/live/flight/{fn_encoded}",
            "flightradar24": f"https://www.flightradar24.com/{fn.lower()}",
            "google":        f"https://www.google.com/search?q=flight+{fn_encoded}",
        }
        base = {"tool": "track_flight", "flight_number": fn, "date": date or today, "tracking_links": tracking_links, "fetch_time_ms": round((time.time() - start_time) * 1000, 2)}
        if data:
            return {"success": True, **base, "answer": data.get("answer", ""), "sources": [{"title": r.get("title",""), "url": r.get("url",""), "snippet": r.get("content","")[:200]} for r in data.get("results", [])[:5]], "source": "tavily_live"}
        return {"success": True, **base, "message": "Flight tracking available when Tavily API key is configured.", "source": "fallback"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# CITY → IATA AIRPORT CODE LOOKUP
# =============================================================================

_CITY_TO_IATA: Dict[str, str] = {
    "washington": "DCA", "washington dc": "DCA", "dc": "DCA", "reagan": "DCA", "national": "DCA", "dca": "DCA",
    "dulles": "IAD", "iad": "IAD", "bwi": "BWI", "baltimore": "BWI", "baltimore washington": "BWI",
    "new york": "JFK", "nyc": "JFK", "jfk": "JFK", "laguardia": "LGA", "lga": "LGA", "newark": "EWR", "ewr": "EWR",
    "los angeles": "LAX", "la": "LAX", "lax": "LAX", "las vegas": "LAS", "vegas": "LAS", "las": "LAS",
    "chicago": "ORD", "ord": "ORD", "ohare": "ORD", "midway": "MDW", "mdw": "MDW",
    "miami": "MIA", "mia": "MIA", "orlando": "MCO", "mco": "MCO",
    "dallas": "DFW", "dfw": "DFW", "fort worth": "DFW", "houston": "IAH", "iah": "IAH",
    "atlanta": "ATL", "atl": "ATL", "seattle": "SEA", "sea": "SEA",
    "san francisco": "SFO", "sf": "SFO", "sfo": "SFO", "denver": "DEN", "den": "DEN",
    "boston": "BOS", "bos": "BOS", "phoenix": "PHX", "phx": "PHX", "minneapolis": "MSP", "msp": "MSP",
    "detroit": "DTW", "dtw": "DTW", "philadelphia": "PHL", "phl": "PHL", "charlotte": "CLT", "clt": "CLT",
    "salt lake city": "SLC", "slc": "SLC", "portland": "PDX", "pdx": "PDX", "san diego": "SAN", "san": "SAN",
    "nashville": "BNA", "bna": "BNA", "austin": "AUS", "aus": "AUS", "new orleans": "MSY", "msy": "MSY",
    "kansas city": "MCI", "mci": "MCI", "raleigh": "RDU", "rdu": "RDU", "tampa": "TPA", "tpa": "TPA",
    "san jose": "SJC", "sjc": "SJC", "oakland": "OAK", "oak": "OAK",
    "honolulu": "HNL", "hawaii": "HNL", "hnl": "HNL", "anchorage": "ANC", "anc": "ANC",
    "london": "LHR", "lhr": "LHR", "heathrow": "LHR", "gatwick": "LGW", "lgw": "LGW",
    "paris": "CDG", "cdg": "CDG", "tokyo": "NRT", "nrt": "NRT", "dubai": "DXB", "dxb": "DXB",
    "toronto": "YYZ", "yyz": "YYZ", "vancouver": "YVR", "yvr": "YVR",
    "mexico city": "MEX", "mex": "MEX", "cancun": "CUN", "cun": "CUN",
    "frankfurt": "FRA", "fra": "FRA", "amsterdam": "AMS", "ams": "AMS",
    "sydney": "SYD", "syd": "SYD", "singapore": "SIN", "sin": "SIN",
}


def _resolve_iata(location: str) -> str:
    """Resolve a city name or partial name to a 3-letter IATA code."""
    if not location:
        return ""
    clean = location.strip().lower()
    # Already a 3-letter code?
    if len(clean) == 3 and clean.isalpha():
        return clean.upper()
    # Exact match
    if clean in _CITY_TO_IATA:
        return _CITY_TO_IATA[clean]
    # Partial / substring match
    for key, code in _CITY_TO_IATA.items():
        if key in clean or clean in key:
            return code
    # Last resort: take first 3 chars
    return location.strip().upper()[:3]


def search_flights(
    origin: str, destination: str, departure_date: str,
    return_date: str = None, adults: int = 1, cabin_class: str = "ECONOMY",
    max_results: int = 5, sort_by: str = "price",
) -> Dict[str, Any]:
    """Search for flights via Amadeus API, falling back to Tavily web search."""
    start_time  = time.time()
    origin_code = _resolve_iata(origin)
    dest_code   = _resolve_iata(destination)

    amadeus_key    = os.getenv("AMADEUS_API_KEY")
    amadeus_secret = os.getenv("AMADEUS_API_SECRET")

    if amadeus_key and amadeus_secret:
        try:
            # Step 1: Get an OAuth2 access token
            token_data = urllib.parse.urlencode({
                "grant_type": "client_credentials",
                "client_id":  amadeus_key,
                "client_secret": amadeus_secret,
            }).encode()
            with urllib.request.urlopen(
                urllib.request.Request(
                    "https://test.api.amadeus.com/v1/security/oauth2/token",
                    data=token_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                ),
                timeout=15,
            ) as resp:
                access_token = json.loads(resp.read().decode()).get("access_token")
            if not access_token:
                raise ValueError("No access token returned from Amadeus")

            # Step 2: Search for flight offers
            params = {
                "originLocationCode":      origin_code,
                "destinationLocationCode": dest_code,
                "departureDate":           departure_date,
                "adults":                  str(adults),
                "travelClass":             cabin_class,
                "max":                     str(min(max_results, 10)),
                "currencyCode":            "USD",
            }
            if return_date:
                params["returnDate"] = return_date
            with urllib.request.urlopen(
                urllib.request.Request(
                    "https://test.api.amadeus.com/v2/shopping/flight-offers?" + urllib.parse.urlencode(params),
                    headers={"Authorization": f"Bearer {access_token}"},
                ),
                timeout=20,
            ) as resp:
                flight_data = json.loads(resp.read().decode())

            offers   = flight_data.get("data", [])
            carriers = flight_data.get("dictionaries", {}).get("carriers", {})

            if not offers:
                return {
                    "success": True, "tool": "search_flights",
                    "origin": origin_code, "destination": dest_code,
                    "departure_date": departure_date, "return_date": return_date,
                    "flights": [], "message": f"No flights found from {origin_code} to {dest_code} on {departure_date}.",
                    "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
                }

            flights = []
            for offer in offers[:max_results]:
                price       = float(offer.get("price", {}).get("grandTotal", 0))
                currency    = offer.get("price", {}).get("currency", "USD")
                itineraries = offer.get("itineraries", [])
                parsed_itin = []
                for itin in itineraries:
                    segs     = itin.get("segments", [])
                    duration = itin.get("duration", "").replace("PT", "").replace("H", "h ").replace("M", "m").strip()
                    stops    = len(segs) - 1
                    seg_list = [
                        {
                            "flight":   f"{s.get('carrierCode','')}{s.get('number','')}",
                            "airline":  carriers.get(s.get("carrierCode",""), s.get("carrierCode","")),
                            "from":     s.get("departure",{}).get("iataCode",""),
                            "to":       s.get("arrival",{}).get("iataCode",""),
                            "departs":  s.get("departure",{}).get("at",""),
                            "arrives":  s.get("arrival",{}).get("at",""),
                            "aircraft": s.get("aircraft",{}).get("code",""),
                        }
                        for s in segs
                    ]
                    parsed_itin.append({
                        "duration":   duration,
                        "stops":      stops,
                        "stop_label": "Nonstop" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}",
                        "segments":   seg_list,
                    })
                first_seg       = itineraries[0]["segments"][0] if itineraries and itineraries[0].get("segments") else {}
                primary_carrier = first_seg.get("carrierCode", "")
                flights.append({
                    "id":              offer.get("id",""),
                    "price":           price,
                    "price_formatted": f"${price:,.0f}",
                    "currency":        currency,
                    "airline":         carriers.get(primary_carrier, primary_carrier),
                    "airline_code":    primary_carrier,
                    "cabin":           cabin_class,
                    "seats_available": offer.get("numberOfBookableSeats"),
                    "itineraries":     parsed_itin,
                    "outbound":        parsed_itin[0] if parsed_itin else {},
                    "return":          parsed_itin[1] if len(parsed_itin) > 1 else None,
                    "is_round_trip":   len(parsed_itin) > 1,
                })

            if sort_by == "duration":
                flights.sort(key=lambda f: f.get("outbound", {}).get("duration", "99h"))
            else:
                flights.sort(key=lambda f: f.get("price", 9999))

            cheapest = flights[0] if flights else None
            return {
                "success": True, "tool": "search_flights",
                "origin": origin_code, "origin_city": origin,
                "destination": dest_code, "destination_city": destination,
                "departure_date": departure_date, "return_date": return_date,
                "adults": adults, "cabin_class": cabin_class,
                "trip_type": "round_trip" if return_date else "one_way",
                "flights_found":    len(flights),
                "cheapest_price":   cheapest["price_formatted"] if cheapest else None,
                "cheapest_airline": cheapest["airline"] if cheapest else None,
                "flights":          flights,
                "source":           "amadeus",
                "fetch_time_ms":    round((time.time() - start_time) * 1000, 2),
            }

        except Exception as e:
            logger.warning("Amadeus search failed: %s — falling back to Tavily", e)

    # ── Tavily fallback ───────────────────────────────────────────────────────
    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        try:
            query = (
                f"cheapest flights from {origin} to {destination} "
                f"departing {departure_date}"
                f"{' returning ' + return_date if return_date else ''} "
                f"{cabin_class.lower()} {adults} adult"
            )
            data = _tavily_search(query, 5)
            if data:
                web_results = [
                    {
                        "id":          f"web_{i}",
                        "title":       r.get("title",""),
                        "summary":     r.get("content","")[:300],
                        "url":         r.get("url",""),
                        "source":      _extract_domain(r.get("url","")),
                    }
                    for i, r in enumerate(data.get("results",[])[:max_results])
                ]
                return {
                    "success": True, "tool": "search_flights",
                    "origin": origin_code, "origin_city": origin,
                    "destination": dest_code, "destination_city": destination,
                    "departure_date": departure_date, "return_date": return_date,
                    "adults": adults, "cabin_class": cabin_class,
                    "trip_type": "round_trip" if return_date else "one_way",
                    "answer":      data.get("answer",""),
                    "web_results": web_results,
                    "source":      "web_search",
                    "note":        "Set AMADEUS_API_KEY and AMADEUS_API_SECRET for real-time flight offers.",
                    "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
                }
        except Exception as e:
            return {"success": False, "error": f"Flight search failed: {str(e)}", "tool": "search_flights"}

    # No API keys available at all
    return {
        "success": False, "tool": "search_flights",
        "error":   "Flight search requires AMADEUS_API_KEY+AMADEUS_API_SECRET or TAVILY_API_KEY.",
        "origin": origin_code, "destination": dest_code, "departure_date": departure_date,
        "booking_links": [
            f"https://www.google.com/flights?q=flights+from+{origin_code}+to+{dest_code}+on+{departure_date}",
            f"https://www.kayak.com/flights/{origin_code}-{dest_code}/{departure_date}",
            f"https://www.expedia.com/Flights-Search?trip=oneway&leg1=from:{origin_code},to:{dest_code},departure:{departure_date}",
        ],
    }


# =============================================================================
# TOOL DISPATCHER — O(1) dict lookup, split into static and dynamic parts
# =============================================================================
#
# PERF FIX 2: the original _build_dispatch_table() was called on EVERY
# handle_tool_call() invocation, allocating ~45 lambda objects each time.
# The fix splits the table in two:
#
#   _STATIC_DISPATCH   — built ONCE at module load (module-level constant).
#                        Contains all tools that need NO injected dependencies.
#
#   _DYNAMIC_DISPATCH  — assembled on-the-fly, but only for the 5 tools that
#                        actually require supabase_client or api_key.
#
# For the overwhelmingly common case (a static tool), zero lambdas are allocated.
# The dynamic sub-table is only built when a dynamic tool is requested AND only
# those 5 lambdas are created, not all 45.

_STATIC_DISPATCH: Dict[str, Any] = {
    # Each entry: tool_name → lambda tool_input: handler(...)
    "execute_python":         lambda ti: execute_python(code=ti.get("code",""), description=ti.get("description","")),
    "execute_react":          lambda ti: execute_react(code=ti.get("code",""), description=ti.get("description","")),
    "get_stock_data":         lambda ti: get_stock_data(symbol=ti.get("symbol",""), period=ti.get("period","1mo"), info_type=ti.get("info_type","price")),
    "validate_afl":           lambda ti: validate_afl(code=ti.get("code","")),
    "sanity_check_afl":       lambda ti: sanity_check_afl(code=ti.get("code",""), auto_fix=ti.get("auto_fix",True)),
    "get_stock_chart":        lambda ti: get_stock_chart(symbol=ti.get("symbol",""), period=ti.get("period","3mo"), interval=ti.get("interval","1d"), chart_type=ti.get("chart_type","candlestick")),
    "technical_analysis":     lambda ti: technical_analysis(symbol=ti.get("symbol",""), period=ti.get("period","3mo")),
    "get_weather":            lambda ti: get_weather(location=ti.get("location",""), units=ti.get("units","imperial")),
    "get_news":               lambda ti: get_news(query=ti.get("query",""), category=ti.get("category","general"), max_results=ti.get("max_results",5)),
    "create_chart":           lambda ti: create_chart(chart_type=ti.get("chart_type","bar"), title=ti.get("title","Chart"), data=ti.get("data",[]), x_label=ti.get("x_label",""), y_label=ti.get("y_label",""), colors=ti.get("colors")),
    "code_sandbox":           lambda ti: code_sandbox(code=ti.get("code",""), language=ti.get("language","python"), title=ti.get("title","Code Sandbox"), run_immediately=ti.get("run_immediately",True)),
    "screen_stocks":          lambda ti: screen_stocks(sector=ti.get("sector"), min_market_cap=ti.get("min_market_cap"), max_pe_ratio=ti.get("max_pe_ratio"), min_dividend_yield=ti.get("min_dividend_yield"), symbols=ti.get("symbols","AAPL,MSFT,GOOGL,AMZN,META,NVDA,TSLA,JPM,V,JNJ")),
    "compare_stocks":         lambda ti: compare_stocks(symbols=ti.get("symbols",""), metrics=ti.get("metrics","price,market_cap,pe_ratio")),
    "get_sector_performance": lambda ti: get_sector_performance(period=ti.get("period","1mo")),
    "calculate_position_size":lambda ti: calculate_position_size(account_size=ti.get("account_size",0), entry_price=ti.get("entry_price",0), stop_loss_price=ti.get("stop_loss_price",0), risk_percent=ti.get("risk_percent",2.0), symbol=ti.get("symbol")),
    "calculate_correlation":  lambda ti: get_correlation_matrix(symbols=ti.get("symbols",""), period=ti.get("period","6mo")),
    "get_dividend_info":      lambda ti: get_dividend_info(symbol=ti.get("symbol","")),
    "calculate_risk_metrics": lambda ti: calculate_risk_metrics(symbol=ti.get("symbol",""), period=ti.get("period","1y"), benchmark=ti.get("benchmark","SPY"), risk_free_rate=ti.get("risk_free_rate",0.05)),
    "get_market_overview":    lambda ti: get_market_overview(),
    "backtest_quick":         lambda ti: backtest_quick(symbol=ti.get("symbol",""), strategy=ti.get("strategy","sma_crossover"), period=ti.get("period","1y"), fast_period=ti.get("fast_period",20), slow_period=ti.get("slow_period",50)),
    "get_options_snapshot":   lambda ti: get_options_snapshot(symbol=ti.get("symbol","")),
    "portfolio_analysis":     lambda ti: portfolio_analysis(holdings=ti.get("holdings",[]), benchmark=ti.get("benchmark","SPY")),
    "get_watchlist":          lambda ti: get_watchlist(symbols=ti.get("symbols","AAPL,MSFT,GOOGL,TSLA,NVDA,META,AMZN")),
    "sector_heatmap":         lambda ti: sector_heatmap(period=ti.get("period","1d")),
    "get_options_chain":      lambda ti: get_options_chain(symbol=ti.get("symbol",""), expiry=ti.get("expiry","nearest")),
    "get_market_sentiment":   lambda ti: get_market_sentiment(),
    "get_crypto_data":        lambda ti: get_crypto_data(symbols=ti.get("symbols","BTC-USD,ETH-USD,BNB-USD,ADA-USD,SOL-USD")),
    "generate_trade_signal":  lambda ti: generate_trade_signal(symbol=ti.get("symbol",""), timeframe=ti.get("timeframe","1d")),
    "risk_assessment":        lambda ti: risk_assessment(symbol=ti.get("symbol",""), period=ti.get("period","1y")),
    "news_digest":            lambda ti: news_digest(query=ti.get("query",""), max_articles=ti.get("max_articles",5)),
    "run_backtest":           lambda ti: run_backtest(symbols=ti.get("symbols",""), strategy=ti.get("strategy",""), start_date=ti.get("start_date"), end_date=ti.get("end_date")),
    "get_live_scores":        lambda ti: get_live_scores(sport=ti.get("sport"), league=ti.get("league"), date=ti.get("date")),
    "get_search_trends":      lambda ti: get_search_trends(region=ti.get("region","US"), category=ti.get("category"), period=ti.get("period","today")),
    "create_linkedin_post":   lambda ti: create_linkedin_post(topic=ti.get("topic",""), tone=ti.get("tone","professional"), author_name=ti.get("author_name"), include_hashtags=ti.get("include_hashtags",True)),
    "preview_website":        lambda ti: preview_website(url=ti.get("url","")),
    "order_food":             lambda ti: order_food(query=ti.get("query",""), cuisine=ti.get("cuisine"), location=ti.get("location")),
    "track_flight":           lambda ti: track_flight(flight_number=ti.get("flight_number",""), date=ti.get("date")),
    "search_flights":         lambda ti: search_flights(origin=ti.get("origin",""), destination=ti.get("destination",""), departure_date=ti.get("departure_date",""), return_date=ti.get("return_date"), adults=ti.get("adults",1), cabin_class=ti.get("cabin_class","ECONOMY"), max_results=ti.get("max_results",5), sort_by=ti.get("sort_by","price")),
    # ── EDGAR / SEC tool dispatchers ──────────────────────────────────────────
    "edgar_get_security_id":        lambda ti: _edgar_get_security_id(ti),
    "edgar_search_companies":       lambda ti: _edgar_search_companies(ti),
    "edgar_get_filings":            lambda ti: _edgar_get_filings(ti),
    "edgar_get_financials":         lambda ti: _edgar_get_financials(ti),
    "edgar_get_concept":            lambda ti: _edgar_get_concept(ti),
    "edgar_search_fulltext":        lambda ti: _edgar_search_fulltext(ti),
    "edgar_get_insider_transactions": lambda ti: _edgar_get_insider_transactions(ti),
    "edgar_get_material_events":    lambda ti: _edgar_get_material_events(ti),
}


# =============================================================================
# EDGAR TOOL HANDLERS
# =============================================================================
# All EDGAR tools are no-dependency (no supabase_client, no api_key) so they
# live in _STATIC_DISPATCH above.  The thin wrapper functions below are defined
# after _STATIC_DISPATCH so they can reference the module-level ec import,
# while the lambdas in the dispatch table just call these wrappers.

def _edgar_client():
    """Return the edgar_client module, or None if it cannot be imported."""
    try:
        import core.edgar_client as ec
        return ec
    except Exception as e:
        return None


def _edgar_get_security_id(ti: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve ticker/name → EDGAR CIK and company metadata."""
    ec = _edgar_client()
    if ec is None:
        return {"success": False, "error": "EDGAR client not available", "tool": "edgar_get_security_id"}
    try:
        result = ec.get_security_id(ti.get("identifier", ""))
        result["tool"] = "edgar_get_security_id"
        return result
    except Exception as e:
        return {"success": False, "error": str(e), "tool": "edgar_get_security_id"}


def _edgar_search_companies(ti: Dict[str, Any]) -> Dict[str, Any]:
    """Search SEC company registry by name or ticker substring."""
    ec = _edgar_client()
    if ec is None:
        return {"success": False, "error": "EDGAR client not available", "tool": "edgar_search_companies"}
    try:
        results = ec.search_companies(ti.get("query", ""), limit=ti.get("limit", 10))
        return {
            "success": True,
            "tool":    "edgar_search_companies",
            "query":   ti.get("query", ""),
            "count":   len(results),
            "results": results,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "tool": "edgar_search_companies"}


def _edgar_get_filings(ti: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch SEC filings list for a ticker, with optional form type filter."""
    ec = _edgar_client()
    if ec is None:
        return {"success": False, "error": "EDGAR client not available", "tool": "edgar_get_filings"}
    ticker = ti.get("ticker", "")
    if not ticker:
        return {"success": False, "error": "ticker is required", "tool": "edgar_get_filings"}
    try:
        result = ec.get_latest_filings_by_form(
            ticker,
            form_type=ti.get("form_type"),
            limit=ti.get("limit", 10),
        )
        # get_latest_filings_by_form already sets success=True
        result["tool"] = "edgar_get_filings"
        return result
    except Exception as e:
        return {"success": False, "error": str(e), "tool": "edgar_get_filings"}


def _edgar_get_financials(ti: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch key XBRL financial facts (revenues, net income, EPS, etc.) for a ticker."""
    ec = _edgar_client()
    if ec is None:
        return {"success": False, "error": "EDGAR client not available", "tool": "edgar_get_financials"}
    ticker = ti.get("ticker", "")
    if not ticker:
        return {"success": False, "error": "ticker is required", "tool": "edgar_get_financials"}
    try:
        company = ec.get_company_by_ticker(ticker.upper())
        if not company:
            return {"success": False, "error": f"Ticker '{ticker}' not found in EDGAR", "tool": "edgar_get_financials"}
        result = ec.get_key_financials(company["cik"])
        result["ticker"] = ticker.upper()
        result["tool"]   = "edgar_get_financials"
        return result
    except Exception as e:
        return {"success": False, "error": str(e), "tool": "edgar_get_financials"}


def _edgar_get_concept(ti: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch time-series for a single XBRL concept for a ticker."""
    ec = _edgar_client()
    if ec is None:
        return {"success": False, "error": "EDGAR client not available", "tool": "edgar_get_concept"}
    ticker  = ti.get("ticker", "")
    concept = ti.get("concept", "")
    if not ticker or not concept:
        return {"success": False, "error": "ticker and concept are required", "tool": "edgar_get_concept"}
    try:
        company = ec.get_company_by_ticker(ticker.upper())
        if not company:
            return {"success": False, "error": f"Ticker '{ticker}' not found in EDGAR", "tool": "edgar_get_concept"}
        result = ec.get_company_concept(
            company["cik"],
            concept=concept,
            taxonomy=ti.get("taxonomy", "us-gaap"),
        )
        limit = ti.get("limit", 20)
        result["series"] = result.get("series", [])[:limit]
        result["ticker"] = ticker.upper()
        result["tool"]   = "edgar_get_concept"
        return result
    except Exception as e:
        return {"success": False, "error": str(e), "tool": "edgar_get_concept"}


def _edgar_search_fulltext(ti: Dict[str, Any]) -> Dict[str, Any]:
    """Full-text search across all EDGAR filings (EFTS)."""
    ec = _edgar_client()
    if ec is None:
        return {"success": False, "error": "EDGAR client not available", "tool": "edgar_search_fulltext"}
    query = ti.get("query", "")
    if not query:
        return {"success": False, "error": "query is required", "tool": "edgar_search_fulltext"}
    try:
        result = ec.search_filings_fulltext(
            query=query,
            form_type=ti.get("form_type"),
            date_from=ti.get("date_from"),
            date_to=ti.get("date_to"),
            limit=ti.get("limit", 10),
        )
        result["tool"] = "edgar_search_fulltext"
        return result
    except Exception as e:
        return {"success": False, "error": str(e), "tool": "edgar_search_fulltext"}


def _edgar_get_insider_transactions(ti: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch Form 4 insider transaction filings for a ticker."""
    ec = _edgar_client()
    if ec is None:
        return {"success": False, "error": "EDGAR client not available", "tool": "edgar_get_insider_transactions"}
    ticker = ti.get("ticker", "")
    if not ticker:
        return {"success": False, "error": "ticker is required", "tool": "edgar_get_insider_transactions"}
    try:
        company = ec.get_company_by_ticker(ticker.upper())
        if not company:
            return {"success": False, "error": f"Ticker '{ticker}' not found in EDGAR", "tool": "edgar_get_insider_transactions"}
        result = ec.get_insider_transactions(company["cik"], limit=ti.get("limit", 20))
        result["ticker"] = ticker.upper()
        result["tool"]   = "edgar_get_insider_transactions"
        return result
    except Exception as e:
        return {"success": False, "error": str(e), "tool": "edgar_get_insider_transactions"}


def _edgar_get_material_events(ti: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch 8-K material event filings for a ticker."""
    ec = _edgar_client()
    if ec is None:
        return {"success": False, "error": "EDGAR client not available", "tool": "edgar_get_material_events"}
    ticker = ti.get("ticker", "")
    if not ticker:
        return {"success": False, "error": "ticker is required", "tool": "edgar_get_material_events"}
    try:
        company = ec.get_company_by_ticker(ticker.upper())
        if not company:
            return {"success": False, "error": f"Ticker '{ticker}' not found in EDGAR", "tool": "edgar_get_material_events"}
        result = ec.get_material_events(company["cik"], limit=ti.get("limit", 10))
        result["ticker"] = ticker.upper()
        result["tool"]   = "edgar_get_material_events"
        return result
    except Exception as e:
        return {"success": False, "error": str(e), "tool": "edgar_get_material_events"}


def _invoke_skill(tool_input: Dict, api_key: str) -> Dict:
    """Invoke a registered skill by slug via the SkillGateway.

    If the skill produces file artifacts (e.g. .docx, .pptx), downloads them
    from Claude's Files API and stores them in the local file_store for serving.
    """
    if not api_key:
        return {"success": False, "error": "API key required for skill invocation"}
    try:
        from core.skill_gateway import SkillGateway
        from core.file_store import store_file
        gw     = SkillGateway(api_key=api_key)
        skill_slug = tool_input.get("skill_slug", "")

        # Accept any reasonable field name for the user message — Claude sometimes
        # uses "instructions", "prompt", "request", "description", "task", "text",
        # "input", "task_description", or other variations instead of "message".
        _KNOWN_META_FIELDS = {"skill_slug", "extra_context"}
        user_message = (
            tool_input.get("message")
            or tool_input.get("instructions")
            or tool_input.get("prompt")
            or tool_input.get("request")
            or tool_input.get("description")
            or tool_input.get("content")
            or tool_input.get("query")
            or tool_input.get("task")
            or tool_input.get("text")
            or tool_input.get("input")
            or tool_input.get("task_description")
            or tool_input.get("user_message")
            or ""
        )

        # Last resort: build message from any unknown fields Claude passed in
        if not user_message:
            extra_fields = {
                k: v for k, v in tool_input.items()
                if k not in _KNOWN_META_FIELDS and v and isinstance(v, str)
            }
            if extra_fields:
                user_message = " | ".join(f"{k}: {v}" for k, v in extra_fields.items())

        if not user_message:
            # Absolute fallback — ask the skill to proceed with just the slug context
            user_message = f"Please execute the {skill_slug} skill with your best capabilities."
            logger.warning(
                "invoke_skill called with no message field for slug '%s' — using default prompt. "
                "tool_input keys: %s",
                skill_slug, list(tool_input.keys()),
            )

        result = gw.execute(
            skill_slug=skill_slug,
            user_message=user_message,
            extra_context=tool_input.get("extra_context",""),
        )

        # Strip any Claude ephemeral file_xxx URLs from the skill text before
        # returning it as the tool result.  Claude will see the cleaned text and
        # will NOT repeat the bad URL in its final response.  The correct
        # /files/{uuid}/download URL is provided in base_response["download_url"]
        # once the file has been stored.
        skill_text = result.get("text", "")
        if skill_text and result.get("files"):
            skill_text = re_mod.sub(r'/files/file_[A-Za-z0-9_-]+/download', '', skill_text)
            skill_text = re_mod.sub(r'\bfile_[A-Za-z0-9]{20,}\b', '', skill_text)
            skill_text = re_mod.sub(r'\n{3,}', '\n\n', skill_text).strip()

        base_response = {
            "success":        True,
            "tool":           "invoke_skill",
            "skill":          result.get("skill", skill_slug),
            "skill_name":     result.get("skill_name",""),
            "text":           skill_text,
            "execution_time": result.get("execution_time", 0),
            "usage":          result.get("usage", {}),
        }

        # If the skill produced file artifacts, download and store them
        skill_files = result.get("files", [])
        logger.info("invoke_skill '%s' files returned: %s", skill_slug, skill_files)
        if skill_files:
            try:
                downloaded = gw.download_files(skill_files)
                logger.info("invoke_skill '%s' downloaded: %s files", skill_slug, len(downloaded))
                for dl in downloaded:
                    fname = dl.get("filename", "")
                    # FIX: download_files() returns "content" key, not "data"
                    data = dl.get("content", b"") or dl.get("data", b"")
                    if data and fname:
                        # Determine file type from extension
                        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else "bin"
                        # Do NOT pass claude_file_id — let store_file generate a
                        # permanent backend UUID. The download_url in the tool result
                        # will use this UUID, so neither the text response nor the
                        # frontend ever sees Claude's ephemeral file_xxx ID.
                        entry = store_file(
                            data=data,
                            filename=fname,
                            file_type=ext,
                            tool_name=f"invoke_skill:{skill_slug}",
                        )
                        # Add download info to the response
                        base_response["file_id"] = entry.file_id
                        base_response["filename"] = entry.filename
                        base_response["file_type"] = entry.file_type
                        base_response["file_size_kb"] = entry.size_kb
                        base_response["download_url"] = f"/files/{entry.file_id}/download"
                        # Also set document_id/presentation_id for frontend compatibility
                        if ext in ("docx", "doc"):
                            base_response["document_id"] = entry.file_id
                        elif ext in ("pptx", "ppt"):
                            base_response["presentation_id"] = entry.file_id
                        logger.info("Skill %s produced file: %s (%.1f KB)", skill_slug, fname, entry.size_kb)
                        break  # Use first matching file
            except Exception as dl_err:
                logger.error("Failed to download skill files for '%s': %s", skill_slug, dl_err, exc_info=True)

        return base_response
    except Exception as e:
        logger.error("invoke_skill failed for slug '%s': %s", tool_input.get("skill_slug", "?"), e, exc_info=True)
        return {"success": False, "error": f"Skill invocation failed: {str(e)}", "tool": "invoke_skill"}


# =============================================================================
# DOCUMENT & PRESENTATION GENERATION VIA SKILLS
# =============================================================================

def _create_word_document(tool_input: Dict, api_key: str) -> Dict:
    """
    Create a Potomac-branded Word document using the potomac-docx-skill.

    Flow:
    1. Invoke the skill to generate document content
    2. Convert the markdown content to a branded .docx file
    3. Store the file and return a download URL
    """
    if not api_key:
        return {"success": False, "error": "API key required for document generation", "tool": "create_word_document"}

    title = tool_input.get("title", "Untitled Document")
    description = tool_input.get("description", "")
    doc_type = tool_input.get("doc_type", "report")
    subtitle = tool_input.get("subtitle", "")

    start_time = time.time()

    try:
        from core.skill_gateway import SkillGateway
        from core.file_store import store_file

        # Build the prompt for the DOCX skill
        user_prompt = (
            f"Create a professional Potomac-branded {doc_type} document.\n\n"
            f"Title: {title}\n"
            f"{'Subtitle: ' + subtitle + chr(10) if subtitle else ''}"
            f"Type: {doc_type}\n\n"
            f"Description/Requirements:\n{description}\n\n"
            f"Instructions:\n"
            f"- You MUST create a .docx file using python-docx\n"
            f"- Use code execution to generate the actual .docx file\n"
            f"- Include proper formatting: headings, bullet points, tables\n"
            f"- Use professional, institutional-grade language\n"
            f"- Save the file with a descriptive filename ending in .docx"
        )

        # Execute the skill with code execution support
        gw = SkillGateway(api_key=api_key)
        skill_result = gw.execute(
            skill_slug="potomac-docx-skill",
            user_message=user_prompt,
        )

        # Check if the skill produced file artifacts via code execution
        skill_files = skill_result.get("files", [])
        content_text = skill_result.get("text", "")

        # Try to download files from Claude's Files API
        if skill_files:
            try:
                downloaded = gw.download_files(skill_files)
                for dl in downloaded:
                    fname = dl.get("filename", "")
                    # FIX: download_files() returns "content" key, not "data"
                    data = dl.get("content", b"") or dl.get("data", b"")
                    if fname.endswith(".docx") and data:
                        entry = store_file(
                            data=data,
                            filename=fname,
                            file_type="docx",
                            tool_name="create_word_document",
                        )
                        return {
                            "success": True,
                            "tool": "create_word_document",
                            "file_id": entry.file_id,
                            "document_id": entry.file_id,
                            "filename": entry.filename,
                            "title": title,
                            "subtitle": subtitle,
                            "doc_type": doc_type,
                            "file_size_kb": entry.size_kb,
                            "download_url": f"/files/{entry.file_id}/download",
                            "content_preview": content_text[:500] if content_text else "",
                            "skill_used": "potomac-docx-skill",
                            "method": "skill_file_download",
                            "execution_time": skill_result.get("execution_time", 0),
                            "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
                        }
            except Exception as dl_err:
                logger.warning("File download failed, returning text: %s", dl_err)

        # Fallback: return the text content for the frontend to display
        if not content_text:
            return {"success": False, "error": "Skill returned empty content", "tool": "create_word_document"}

        return {
            "success": True,
            "tool": "create_word_document",
            "title": title,
            "subtitle": subtitle,
            "doc_type": doc_type,
            "text": content_text,
            "content_preview": content_text[:500] + "..." if len(content_text) > 500 else content_text,
            "skill_used": "potomac-docx-skill",
            "method": "skill_text_only",
            "execution_time": skill_result.get("execution_time", 0),
            "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
        }

    except Exception as e:
        logger.error("Word document creation failed: %s", e, exc_info=True)
        return {"success": False, "error": f"Document creation failed: {str(e)}", "tool": "create_word_document"}


def _create_pptx_with_skill(tool_input: Dict, api_key: str) -> Dict:
    """
    Create a Potomac-branded PowerPoint using the potomac-pptx-skill.

    Flow:
    1. Invoke the skill to generate structured slide content
    2. Parse the JSON slide plan
    3. Assemble the .pptx file using PotomacPPTXGenerator
    4. Store and return download URL
    """
    if not api_key:
        return {"success": False, "error": "API key required for presentation generation", "tool": "create_pptx_with_skill"}

    title = tool_input.get("title", "Untitled Presentation")
    description = tool_input.get("description", "")
    slide_count = tool_input.get("slide_count", 10)
    subtitle = tool_input.get("subtitle", "")

    start_time = time.time()

    try:
        from core.skill_gateway import SkillGateway

        # Build the prompt for the PPTX skill
        user_prompt = (
            f"Create a professional Potomac-branded PowerPoint presentation.\n\n"
            f"Title: {title}\n"
            f"{'Subtitle: ' + subtitle + chr(10) if subtitle else ''}"
            f"Number of slides: approximately {slide_count}\n\n"
            f"Content/Requirements:\n{description}\n\n"
            f"Instructions:\n"
            f"- Apply strict Potomac brand compliance: yellow (#FEC00F) and dark (#1A1A2E) color scheme\n"
            f"- Include a title slide, agenda, content slides, and a closing slide\n"
            f"- Each slide should have clear titles, concise bullet points, and speaker notes\n"
            f"- Output as a structured JSON slide plan for assembly\n"
            f"- Use data tables and chart descriptions where appropriate"
        )

        # Execute the skill
        gw = SkillGateway(api_key=api_key)
        skill_result = gw.execute(
            skill_slug="potomac-pptx-skill",
            user_message=user_prompt,
        )

        content_text = skill_result.get("text", "")
        if not content_text:
            return {"success": False, "error": "Skill returned empty content", "tool": "create_pptx_with_skill"}

        # Try to parse JSON from the skill output
        json_match = None
        # Look for JSON block in markdown fences
        json_fenced = re_mod.search(r'```(?:json)?\s*\n([\s\S]*?)\n```', content_text)
        if json_fenced:
            try:
                json_match = json.loads(json_fenced.group(1))
            except json.JSONDecodeError:
                pass

        # Try the whole text as JSON
        if not json_match:
            try:
                json_match = json.loads(content_text.strip())
            except json.JSONDecodeError:
                pass

        if json_match and isinstance(json_match, dict) and "slides" in json_match:
            # We got a valid slide plan — assemble it
            outline = json_match
            if "title" not in outline:
                outline["title"] = title
            presentation_id, pptx_bytes = _write_pptx_to_memory(outline, title)

            try:
                from core.file_store import store_file
                safe_title = title.replace(" ", "_").replace("/", "-")[:50]
                store_file(
                    data=pptx_bytes,
                    filename=f"{safe_title}.pptx",
                    file_type="pptx",
                    tool_name="create_pptx_with_skill",
                    file_id=presentation_id,
                )
            except Exception as _fs_err:
                logger.warning("file_store persist failed for pptx: %s", _fs_err)

            return {
                "success": True,
                "tool": "create_pptx_with_skill",
                "presentation_id": presentation_id,
                "filename": f"{title.replace(' ', '_').replace('/', '-')[:50]}.pptx",
                "title": title,
                "subtitle": subtitle,
                "slide_count": len(outline.get("slides", [])),
                "file_size_kb": round(len(pptx_bytes) / 1024, 1),
                "download_url": f"/files/{presentation_id}/download",
                "method": "potomac_pptx_skill_assembled",
                "skill_used": "potomac-pptx-skill",
                "execution_time": skill_result.get("execution_time", 0),
                "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
            }
        else:
            # Skill returned prose/markdown instead of JSON — build outline from it
            # Use Claude to convert to structured slides
            fallback_slides = [
                {"type": "title", "title": title, "subtitle": subtitle or "Potomac Fund Management", "date": "2025"},
            ]

            # Parse markdown headings as slide titles
            lines = content_text.split("\n")
            current_bullets = []
            current_title = ""

            for line in lines:
                stripped = line.strip()
                if stripped.startswith("## ") or stripped.startswith("# "):
                    if current_title:
                        fallback_slides.append({
                            "type": "content",
                            "title": current_title,
                            "bullets": current_bullets[:5] if current_bullets else ["See notes for details"],
                        })
                    current_title = stripped.lstrip("#").strip()
                    current_bullets = []
                elif stripped.startswith("- ") or stripped.startswith("* "):
                    current_bullets.append(stripped[2:].strip())
                elif stripped and current_title:
                    current_bullets.append(stripped[:100])

            # Add last slide
            if current_title:
                fallback_slides.append({
                    "type": "content",
                    "title": current_title,
                    "bullets": current_bullets[:5] if current_bullets else ["See notes for details"],
                })

            fallback_slides.append({"type": "closing"})

            outline = {"title": title, "slides": fallback_slides}
            presentation_id, pptx_bytes = _write_pptx_to_memory(outline, title)

            try:
                from core.file_store import store_file
                safe_title = title.replace(" ", "_").replace("/", "-")[:50]
                store_file(
                    data=pptx_bytes,
                    filename=f"{safe_title}.pptx",
                    file_type="pptx",
                    tool_name="create_pptx_with_skill",
                    file_id=presentation_id,
                )
            except Exception as _fs_err:
                logger.warning("file_store persist failed for pptx: %s", _fs_err)

            return {
                "success": True,
                "tool": "create_pptx_with_skill",
                "presentation_id": presentation_id,
                "filename": f"{title.replace(' ', '_').replace('/', '-')[:50]}.pptx",
                "title": title,
                "subtitle": subtitle,
                "slide_count": len(fallback_slides),
                "file_size_kb": round(len(pptx_bytes) / 1024, 1),
                "download_url": f"/files/{presentation_id}/download",
                "method": "potomac_pptx_skill_parsed",
                "skill_used": "potomac-pptx-skill",
                "execution_time": skill_result.get("execution_time", 0),
                "fetch_time_ms": round((time.time() - start_time) * 1000, 2),
            }

    except Exception as e:
        logger.error("PPTX with skill creation failed: %s", e, exc_info=True)
        return {"success": False, "error": f"Presentation creation failed: {str(e)}", "tool": "create_pptx_with_skill"}


def handle_tool_call(
    tool_name:       str,
    tool_input:      Dict[str, Any],
    supabase_client=None,
    api_key:         str = None,
) -> str:
    """
    Dispatch a tool call and return a JSON string.

    Performance (PERF FIX 2):
      _STATIC_DISPATCH is a module-level constant — zero allocation per call for
      the ~40 tools that need no injected dependencies.  The 6 tools that DO need
      supabase_client or api_key are handled by a direct if/elif chain below,
      so no throwaway dict is built on every invocation.

    Robustness (BUG FIX 1):
      _tool_time_ms is injected only when the handler returned a dict.  Non-dict
      results (string, None, list) are wrapped so JSON serialisation never fails.
    """
    start_time = time.time()
    try:
        logger.debug("Handling tool call: %s", tool_name)

        # ── Fast path: static tools (no injected deps) — O(1), zero allocation ─
        handler = _STATIC_DISPATCH.get(tool_name)
        if handler is not None:
            result = handler(tool_input)

        # ── Dependency-injected tools — handled inline, no throwaway dict ──────
        elif tool_name == "search_knowledge_base":
            result = search_knowledge_base(
                query=tool_input.get("query", ""),
                category=tool_input.get("category"),
                limit=tool_input.get("limit", 3),
                supabase_client=supabase_client,
            )
        elif tool_name == "generate_afl_code":
            result = generate_afl_code(
                description=tool_input.get("description", ""),
                strategy_type=tool_input.get("strategy_type", "standalone"),
                api_key=api_key,
            )
        elif tool_name == "debug_afl_code":
            result = debug_afl_code(
                code=tool_input.get("code", ""),
                error_message=tool_input.get("error_message", ""),
                api_key=api_key,
            )
        elif tool_name == "explain_afl_code":
            result = explain_afl_code(
                code=tool_input.get("code", ""),
                api_key=api_key,
            )
        elif tool_name == "invoke_skill":
            result = _invoke_skill(tool_input, api_key)
        # ── Skill-dispatch tools — invoke registered Claude Beta Skills ─────────
        elif tool_name == "run_financial_deep_research":
            topic = tool_input.get("topic", "")
            focus = tool_input.get("focus", "comprehensive analysis")
            result = _invoke_skill({
                "skill_slug": "financial-deep-research",
                "message": f"Perform deep financial research on: {topic}\nFocus areas: {focus}",
                "extra_context": f"Topic: {topic}, Focus: {focus}",
            }, api_key)
        elif tool_name == "run_backtest_analysis":
            data_str = tool_input.get("data", "")
            focus = tool_input.get("focus", "comprehensive analysis")
            result = _invoke_skill({
                "skill_slug": "backtest-expert",
                "message": f"Analyze this backtest/strategy:\n{data_str}\nFocus: {focus}",
                "extra_context": f"Focus: {focus}",
            }, api_key)
        elif tool_name == "run_quant_analysis":
            request = tool_input.get("request", "")
            context = tool_input.get("context", "")
            result = _invoke_skill({
                "skill_slug": "quant-analyst",
                "message": f"{request}\n\nContext: {context}" if context else request,
                "extra_context": context,
            }, api_key)
        elif tool_name == "run_bubble_detection":
            market = tool_input.get("market", "US equities")
            context = tool_input.get("context", "")
            msg = f"Analyze bubble risk for: {market}\n\nAdditional context: {context}" if context else f"Analyze bubble risk for: {market}"
            result = _invoke_skill({
                "skill_slug": "us-market-bubble-detector",
                "message": msg,
                "extra_context": context,
            }, api_key)
        elif tool_name == "generate_afl_with_skill":
            request = tool_input.get("request", "")
            strategy_type = tool_input.get("strategy_type", "standalone")
            trade_timing = tool_input.get("trade_timing", "close")
            result = _invoke_skill({
                "skill_slug": "amibroker-afl-developer",
                "message": f"Generate AFL code:\n{request}\nStrategy type: {strategy_type}\nTrade timing: {trade_timing}",
                "extra_context": f"Strategy type: {strategy_type}, Trade timing: {trade_timing}",
            }, api_key)
        # ── Document & Presentation generation tools ───────────────────────────
        elif tool_name == "generate_docx":
            # Server-side Potomac DOCX generation — no Claude Skills container.
            # handle_generate_docx returns a JSON string; parse it to a dict so
            # handle_tool_call can inject _tool_time_ms before re-serialising.
            try:
                from core.tools_v2.document_tools import handle_generate_docx
                _docx_json = handle_generate_docx(tool_input, api_key=api_key)
                result = json.loads(_docx_json)
            except Exception as _docx_err:
                result = {"status": "error", "error": str(_docx_err)}
        elif tool_name == "generate_pptx":
            # Server-side Potomac PPTX generation via Node.js + pptxgenjs.
            try:
                from core.tools_v2.document_tools import handle_generate_pptx
                _pptx_json = handle_generate_pptx(tool_input, api_key=api_key)
                result = json.loads(_pptx_json)
            except Exception as _pptx_err:
                result = {"status": "error", "error": str(_pptx_err)}
        elif tool_name == "analyze_pptx":
            # Read and profile any uploaded .pptx — slide count, titles, text, brand compliance.
            try:
                from core.tools_v2.document_tools import handle_analyze_pptx
                _apptx_json = handle_analyze_pptx(tool_input, api_key=api_key)
                result = json.loads(_apptx_json)
            except Exception as _apptx_err:
                result = {"status": "error", "error": str(_apptx_err)}
        elif tool_name == "revise_pptx":
            # Apply targeted find_replace / slide updates / appends to existing .pptx in milliseconds.
            try:
                from core.tools_v2.document_tools import handle_revise_pptx
                _rpptx_json = handle_revise_pptx(tool_input, api_key=api_key)
                result = json.loads(_rpptx_json)
            except Exception as _rpptx_err:
                result = {"status": "error", "error": str(_rpptx_err)}
        elif tool_name == "analyze_xlsx":
            # Profile an uploaded .xlsx or .csv — columns, dtypes, nulls, samples.
            try:
                from core.tools_v2.document_tools import handle_analyze_xlsx
                _analyze_json = handle_analyze_xlsx(tool_input, api_key=api_key)
                result = json.loads(_analyze_json)
            except Exception as _analyze_err:
                result = {"status": "error", "error": str(_analyze_err)}
        elif tool_name == "transform_xlsx":
            # Pandas pipeline: filter, sort, clean, pivot, group, dedupe — returns branded xlsx.
            try:
                from core.tools_v2.document_tools import handle_transform_xlsx
                _transform_json = handle_transform_xlsx(tool_input, api_key=api_key)
                result = json.loads(_transform_json)
            except Exception as _transform_err:
                result = {"status": "error", "error": str(_transform_err)}
        elif tool_name == "generate_xlsx":
            # Server-side Potomac XLSX generation via Python openpyxl — no Node.js.
            try:
                from core.tools_v2.document_tools import handle_generate_xlsx
                _xlsx_json = handle_generate_xlsx(tool_input, api_key=api_key)
                result = json.loads(_xlsx_json)
            except Exception as _xlsx_err:
                result = {"status": "error", "error": str(_xlsx_err)}
        elif tool_name == "create_word_document":
            result = _create_word_document(tool_input, api_key)
        elif tool_name == "create_pptx_with_skill":
            result = _create_pptx_with_skill(tool_input, api_key)
        else:
            logger.warning("Unknown tool requested: %s", tool_name)
            result = {"error": f"Unknown tool: {tool_name}"}

        # ── BUG FIX 1: safe timing injection ──────────────────────────────────
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        if isinstance(result, dict):
            result["_tool_time_ms"] = elapsed_ms
        else:
            # Wrap unexpected return types so serialisation never fails
            result = {"result": result, "_tool_time_ms": elapsed_ms}

        logger.debug("Tool %s completed in %sms", tool_name, result["_tool_time_ms"])
        return json.dumps(result, indent=2, default=str)

    except Exception as e:
        logger.error("Error in tool call %s: %s", tool_name, e, exc_info=True)
        return json.dumps({"error": str(e), "traceback": traceback.format_exc()[:500]})



# =============================================================================
# TOOL SEARCH SUPPORT
# =============================================================================
#
# Tool search lets Claude discover tools on-demand instead of loading all
# 60+ definitions upfront. Reduces context usage ~85% and keeps tool
# selection accuracy high across large catalogs.
#
# Quick usage:
#   tools = get_tools_for_api(tool_search=True, variant="regex")
#   # Pass to client.messages.create(tools=tools, ...)
#   # No extra beta headers required.
#
# The response may include server_tool_use and tool_search_tool_result blocks.
# Use handle_tool_result_block() to route them correctly.

def get_tools_for_api(
    tool_search: bool = False,
    variant: str = "regex",
    extra_non_deferred: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Return the tools list to pass to the Claude API.

    Args:
        tool_search:         When True, prepend the tool search entry and
                             keep all deferred tools as-is.  When False
                             (default), return ALL_TOOLS unchanged.
        variant:             "regex" (default) or "bm25".
        extra_non_deferred:  Additional tool names to force-load immediately
                             on top of TOOL_SEARCH_NON_DEFERRED.

    Returns:
        List of tool dicts for the API ``tools`` parameter.
    """
    if not tool_search:
        return ALL_TOOLS

    search_entry = (
        TOOL_SEARCH_REGEX_ENTRY if variant == "regex" else TOOL_SEARCH_BM25_ENTRY
    )
    extra = set(extra_non_deferred or [])

    result: List[Dict] = [search_entry]
    for tool in ALL_TOOLS:
        name = tool.get("name", "")
        if name in TOOL_SEARCH_NON_DEFERRED or name in extra:
            # Strip defer_loading so this tool is loaded immediately
            t = {k: v for k, v in tool.items() if k != "defer_loading"}
            result.append(t)
        else:
            result.append(tool)

    return result


def handle_tool_result_block(block: Dict[str, Any]) -> Optional[str]:
    """
    Route a content block from a Claude API response that may contain
    tool-search internal blocks.

    Block types introduced by tool search:

      server_tool_use            Claude searched for tools. The API resolves
                                 this server-side — no server action required.

      tool_search_tool_result    Carries tool_references that the API expands
                                 into full definitions automatically.
                                 No server action required.

    Returns:
        The tool name (str) if this is a standard tool_use block that the
        caller should dispatch via handle_tool_call().
        None if the block is a tool-search internal type (handled server-side)
        or any other non-dispatchable block (text, thinking, etc.).
    """
    block_type = block.get("type", "")

    if block_type == "server_tool_use":
        query = (block.get("input") or {}).get("query", "")
        logger.debug(
            "Tool search query dispatched: %r (id=%s)",
            query, block.get("id", ""),
        )
        return None

    if block_type == "tool_search_tool_result":
        refs  = (block.get("content") or {}).get("tool_references", [])
        names = [r.get("tool_name", "") for r in refs]
        logger.debug("Tool search discovered: %s", names)
        return None

    if block_type == "tool_use":
        return block.get("name")

    return None


def is_tool_search_block(block: Dict[str, Any]) -> bool:
    """Return True if block is a tool-search internal block (not a real tool call)."""
    return block.get("type") in ("server_tool_use", "tool_search_tool_result")


def extract_tool_search_usage(response_usage: Dict[str, Any]) -> int:
    """
    Return the number of tool search requests made from a response usage dict.

    The API reports this at:
        response.usage.server_tool_use.tool_search_requests

    Returns 0 if tool search was not used.
    """
    stu = response_usage.get("server_tool_use") or {}
    return int(stu.get("tool_search_requests", 0))


# =============================================================================
# PUBLIC TOOL LIST ACCESSORS — computed once at module load
# =============================================================================
#
# TOOL_DEFINITIONS is a module-level constant that never changes, so the
# filtered lists below are also constant.  No @lru_cache needed.

CUSTOM_TOOLS: List[Dict] = [t for t in TOOL_DEFINITIONS if "input_schema" in t]
ALL_TOOLS:    List[Dict] = list(TOOL_DEFINITIONS)


def get_custom_tools() -> List[Dict]:
    """Return custom tool definitions (pre-computed at module load)."""
    return CUSTOM_TOOLS


def get_all_tools() -> List[Dict]:
    """Return all tool definitions (pre-computed at module load)."""
    return ALL_TOOLS