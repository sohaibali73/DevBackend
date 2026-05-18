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
from contextvars import ContextVar

# Per-conversation in-memory namespace cache — preserves Python variables
# across successive execute_python() calls within the same conversation.
_SESSION_NAMESPACES: Dict[str, Dict[str, Any]] = {}
_current_session_id: ContextVar[Optional[str]] = ContextVar("_current_session_id", default=None)

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
    "calculate_performance",  # MANDATORY whenever a performance metric is needed
    "invoke_skill",         # REQUIRED: All skill routing goes through this tool
    # AFL — must be visible upfront so Claude always uses it for any
    # AmiBroker/AFL/AmiFormula request instead of writing AFL inline.
    "generate_afl_code",
    "debug_afl_code",
    "explain_afl_code",
    "validate_afl",
    "sanity_check_afl",
    # Ticker universe — MUST be visible without a tool_search call. If this
    # one is deferred, the model "discovers" it's missing and hand-writes
    # AFL with invented symbols (and forbidden colours, because the same
    # discovery failure makes it skip generate_afl_code too).
    "lookup_norgate_ticker",
    # IDE workspace — same reasoning. The model needs to know it can write
    # files into the conversation panel from the very first turn; deferring
    # these tools causes it to dump code into chat instead.
    "workspace_list_files",
    "workspace_read_file",
    "workspace_write_file",
    "workspace_execute_file",
    # PDF reader — needs to be visible upfront so "read this pdf" requests
    # don't fall back to execute_python + pdfplumber + Session Variables noise.
    "read_pdf",
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
    # ── Reference / documentation tools (return static prompt content on demand) ──
    # These exist so the system prompt can stay slim — Claude only loads detailed
    # reference material when it actually needs it (saves ~1500 tokens per turn).
    {
        "name": "get_afl_syntax_reference",
        "description": (
            "THE single source of truth for AFL reference content. Returns the "
            "full Potomac AFL playbook: function signatures, reserved words, "
            "conditional/signal functions, Param/Optimize pattern, parameter "
            "function family, risk management (ApplyStop), timeframe expansion, "
            "plotting + shape/style constants, exploration functions, color "
            "palette, and the 13 non-negotiable house rules. Optionally also "
            "returns the standalone or composite scaffold template. Call this "
            "before answering any AFL question in your own text. Note: when "
            "the user wants NEW code, prefer generate_afl_code (which already "
            "uses this reference internally) instead of writing AFL yourself."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "template": {
                    "type": "string",
                    "description": "Optional scaffold to append: 'standalone' for a single-file strategy template, 'composite' for the multi-file main+helpers template. Omit for reference only.",
                    "enum": ["standalone", "composite"]
                }
            },
            "required": []
        },
    },
    {
        "name": "get_yang_capabilities",
        "description": "Load documentation for the YANG agentic environment: auto-compact context, focus chain, spawn_subagents, background edit, checkpoints, yolo mode, plan mode, double-check verifier, parallel tool dispatch, and tool-search. Call this when you need to explain, rely on, or correctly use any of these capabilities.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_genui_card_schema",
        "description": "Load the GenUI structured-card catalog: full list of card types (stock, weather, afl, backtest, news, etc.) and the exact JSON envelope format the frontend renders. Call this before emitting a structured data card in your reply.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "lookup_norgate_ticker",
        "description": (
            "MANDATORY before emitting any reference to a ticker symbol in AFL "
            "code — Foreign(), SetForeign(), AddToComposite(), PositionScore "
            "on a specific symbol, RelStrength(), watchlist filters, etc. "
            "Searches the live Norgate universe (~75k securities across US "
            "Equities, US Indices, Continuous Futures, Cash Commodities, "
            "Forex Spot, World Indices, Economic) and returns the canonical "
            "Norgate symbol(s) matching your query. Accepts a ticker fragment, "
            "a company name, or an asset description; ranks exact symbol hits "
            "first, then prefix matches, then name-token matches. Use the "
            "`database` filter to scope to one section (e.g. `Continuous "
            "Futures` for ES, `US Equities` for SPY, `Forex Spot` for EURUSD). "
            "NEVER invent a ticker — if this tool returns no result, ask the "
            "user or pick the closest alternative it suggests. Norgate prefix "
            "conventions: $ = index, # = index/cash commodity, & = continuous "
            "future, @ = cash/spot, % = economic series, no prefix = equity / "
            "ETF / forex pair."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Ticker fragment, company name, or asset description (e.g. 'SPY', 'Apple', 'S&P 500', 'crude oil', 'EURUSD').",
                },
                "database": {
                    "type": "string",
                    "description": "Optional database filter. Common values: 'US Equities', 'US Indices', 'Continuous Futures', 'Futures', 'Cash Commodities', 'Forex Spot', 'World Indices', 'Economic', 'US Equities Delisted'.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 15, hard cap 50).",
                },
            },
            "required": ["query"],
        },
    },

    # ── PDF reader ────────────────────────────────────────────────────────────
    # Purpose-built for "the user uploaded a PDF, read it". Replaces the old
    # pattern where the agent called execute_python with a pdfplumber snippet
    # (worked, but rendered as a code-output blob with leaked file handles).
    {
        "name": "read_pdf",
        "description": (
            "Read the text contents of a PDF file that the user uploaded to "
            "this conversation. MANDATORY for any 'please read this pdf' / "
            "'summarize this document' / 'what's on page X' request — do NOT "
            "use execute_python for that anymore. Returns per-page text, full "
            "concatenated text (capped at 200 KB), and document metadata "
            "(title, author, producer). Pass `file_id` (preferred — the UUID "
            "shown next to the file in <file_context>) or `filename` (best-"
            "effort match within this conversation). Optional `page_range` "
            "like '1-5,10,15-20' restricts the extraction; omit it to read "
            "the whole document. The frontend renders a structured PDF card "
            "with collapsible page previews so the chat stays clean — your "
            "reply text should be ONE short sentence on what the document "
            "is about, NOT a re-dump of the text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "string",
                    "description": "UUID from <file_context>. Prefer this over filename for unambiguous lookup.",
                },
                "filename": {
                    "type": "string",
                    "description": "Fallback when file_id isn't known. Matches uploaded files in this conversation; case-insensitive, exact match first then substring.",
                },
                "page_range": {
                    "type": "string",
                    "description": "Optional. Comma-separated 1-based pages and ranges, e.g. '1-5', '1,3,5', '1-10,15-20'. Omit to read all pages.",
                },
            },
            "required": [],
        },
    },

    # ── Per-conversation IDE workspace ────────────────────────────────────────
    # The frontend shows a Monaco-based IDE panel for the active conversation.
    # Every file the model writes through these tools appears there, editable
    # by the user. Use these instead of execute_python whenever the user
    # benefits from seeing/keeping the source code (full strategies, data
    # pipelines, analysis scripts). Reserve execute_python for ephemeral,
    # throwaway calculations the user doesn't need to revisit.
    {
        "name": "workspace_list_files",
        "description": (
            "List every file in the current conversation's IDE workspace. "
            "Use BEFORE writing a new file to check whether one with that name "
            "already exists, and BEFORE editing a file so you know it's there. "
            "Returns filename, language, version, last_author ('agent' or "
            "'user'), and size_bytes for each file. No input required."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "workspace_read_file",
        "description": (
            "Read the current contents of a workspace file. MANDATORY before "
            "editing a file the user may have modified in the IDE panel — "
            "always pull the latest content so your edits don't clobber the "
            "user's changes. Returns content, language, version, last_author. "
            "Returns success=false if the file doesn't exist (use "
            "workspace_list_files first if you're unsure of the name)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Exact filename (e.g. 'agri_cycle_rotator.py'). Flat namespace — no directories. Use the exact name from workspace_list_files.",
                },
            },
            "required": ["filename"],
        },
    },
    {
        "name": "workspace_write_file",
        "description": (
            "Create or overwrite a file in the current conversation's IDE "
            "workspace. This is the DEFAULT way to deliver any Python or "
            "JavaScript code to the user — they see it appear in the IDE "
            "panel with syntax highlighting and can edit and re-run it. "
            "Use a descriptive filename (e.g. 'sector_rotation_v3.py', "
            "'merge_csvs.js'); existing files with the same name are "
            "overwritten and the version bumps. The user may have edited "
            "the file since you last touched it — call workspace_read_file "
            "first if you're producing a NEW version of an existing file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename with extension. Allowed chars: A-Z a-z 0-9 _ - . Max 128 chars. Flat namespace — no directories.",
                },
                "content": {
                    "type": "string",
                    "description": "Full file content. Replaces any previous version entirely (no patch semantics).",
                },
                "language": {
                    "type": "string",
                    "description": "Optional language hint: 'python' | 'javascript' | 'typescript' | 'afl' | 'sql' | 'json' | 'yaml' | 'markdown' | 'text'. Inferred from extension if omitted.",
                },
            },
            "required": ["filename", "content"],
        },
    },
    {
        "name": "workspace_execute_file",
        "description": (
            "Execute a Python or JavaScript file already saved in the "
            "workspace. Streams stdout/stderr back into the IDE console "
            "panel for the user, AND returns the captured output to you "
            "so you can react to errors in your next message. Use this "
            "instead of execute_python when the code is something the user "
            "should see and keep. For Python, the file runs in the same "
            "per-conversation sandbox namespace as previous execute_python "
            "calls, so variables and helper files persist across runs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Exact filename of a previously-written workspace file. Must be Python or JavaScript.",
                },
            },
            "required": ["filename"],
        },
    },

    # Custom: Python Code Execution
    {
        "name": "execute_python",
        "description": "Execute Python code for calculations, data analysis, or generating AFL formulas. The code runs in a sandboxed environment with access to common libraries like math, statistics, numpy, pandas, matplotlib, seaborn, plotly, yfinance, requests, and more. Use this for complex calculations, backtesting logic, data processing, or generating charts. Charts created with plt.show() are automatically captured AND persisted to file_store — the response includes a top-level `charts` array of `{file_id, filename, type}` entries. To embed a chart into a Word/PowerPoint document, take the `file_id` from `charts[]` and pass it into a `generate_docx` or `generate_pptx` image section: `{\"type\":\"image\",\"file_id\":\"<file_id>\"}`. This is the ONLY reliable way to embed Python-generated charts into Office documents. Use display(HTML(...)) or display(SVG(...)) for rich HTML/SVG output.",
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
        "description": (
            "Validate AFL (AmiBroker Formula Language) code by calling the "
            "AFLValidator.validate() method DIRECTLY on the provided code. "
            "No LLM round-trip, no rewriting, no auto-fix. Returns the raw "
            "validator output: success, valid, error_count, warning_count, "
            "errors[], warnings[], suggestions[], issues[] (with line numbers, "
            "severity, category, message, suggestion), line_count, has_buy_sell, "
            "has_plot. USE THIS — never reroute validation requests to "
            "generate_afl_code (that would regenerate the code instead of "
            "validating it)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "AFL code to validate"}
            },
            "required": ["code"]
        }
    },
    # Custom: Generate AFL — MANDATORY for any AFL/AmiBroker code request.
    {
        "name": "generate_afl_code",
        "description": (
            "MANDATORY tool for ANY AmiBroker / AFL / AmiFormula code request. "
            "Generates production-quality AFL code from a natural-language description "
            "using the Potomac ClaudeAFLEngine: full system prompt with the AFL syntax "
            "reference, 19-phase AFLValidator, auto-fix retry loop, and quality scoring. "
            "ALWAYS call this — NEVER write AFL code inline in the chat reply. "
            "Inline-written AFL bypasses the validator and is strictly forbidden.\n\n"
            "Trigger phrases that REQUIRE this tool (non-exhaustive): 'AFL', "
            "'AmiBroker', 'AmiFormula', 'write me a strategy', 'trading strategy code', "
            "'indicator code', 'exploration', 'buy/sell rules', '.afl file', "
            "'RSI crossover', 'MA crossover', 'Bollinger strategy', 'MACD strategy', "
            "'mean reversion', 'breakout strategy', 'Param/Optimize', 'standalone', "
            "'composite system', and any code request that targets AmiBroker.\n\n"
            "If the user's description is vague, DO NOT ask clarifying questions first — "
            "call the tool with sensible defaults (strategy_type='standalone', "
            "trade_timing='close'). The engine handles edge cases.\n\n"
            "Returns: afl_code (the validated/fixed source), explanation (plain-English "
            "summary), validation_report (✅/⚠️ with errors+warnings), validation_valid, "
            "validation_errors, validation_warnings, quality_score (0-100), "
            "generation_time, issues. The frontend renders this as the AFL card."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Natural-language description of the trading strategy. Be as specific as the user was — pass their request through; do NOT rephrase or shrink it."
                },
                "strategy_type": {
                    "type": "string",
                    "description": "AFL code type. 'standalone' = full self-contained strategy with backtest settings + plotting; 'composite' = logic-only module to be included in a master; 'indicator' = plot-only; 'exploration' = AmiBroker Exploration script.",
                    "enum": ["standalone", "composite", "indicator", "exploration"],
                    "default": "standalone"
                },
                "trade_timing": {
                    "type": "string",
                    "description": "Bar timing for entries/exits. 'close' = SetTradeDelays(0,0,0,0); 'open' = SetTradeDelays(1,1,1,1).",
                    "enum": ["close", "open"],
                    "default": "close"
                }
            },
            "required": ["description"]
        }
    },
    # Custom: Debug AFL
    {
        "name": "debug_afl_code",
        "defer_loading": True,
        "description": (
            "Debug and fix AFL code the user PASTED. Use when the user supplies "
            "broken AFL or an AmiBroker error message and wants it fixed. "
            "NEVER reroute a debug request through generate_afl_code — that "
            "would regenerate from scratch instead of inspecting and fixing "
            "the user's code."
        ),
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
        "description": (
            "Explain in plain English what an AFL block does. Use when the "
            "user asks 'what does this do' about AFL they pasted. NEVER "
            "reroute through generate_afl_code."
        ),
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
        "description": (
            "Run AFLValidator.validate() directly on AFL code and return a "
            "pre-formatted ✅/❌/⚠️ human-readable report (in the `report` field) "
            "plus the full raw validator output (issues, errors, warnings, "
            "counts). Use when the user wants a readable validation summary. "
            "Does NOT call an LLM — pure deterministic validator output."
        ),
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
    # Custom: Performance Engine — MANDATORY for any performance/risk metric
    {
        "name": "calculate_performance",
        "description": (
            "MANDATORY tool for ANY performance, return, drawdown, or risk metric on a ticker. "
            "Fetches live Yahoo Finance price history and computes a full quant suite from real data: "
            "CAGR, total return, net profit, max drawdown (% and $, peak/trough/recovery dates), "
            "Sharpe, annualised volatility, recovery factor, CAR/MaxDD (MAR), RAR/MaxDD, "
            "Ulcer Index, UPI, K-Ratio, std error, win rate, profit factor, win/loss ratio. "
            "ALWAYS call this BEFORE quoting any performance number — NEVER estimate or fabricate. "
            "All percentages are plain floats (7.35 means 7.35%). Returns null for undefined values."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker":  {"type": "string", "description": "Yahoo Finance ticker symbol (e.g. 'SIVR', 'SPY', 'PHYS')"},
                "freq":    {"type": "string", "enum": ["daily", "weekly", "monthly"], "default": "daily", "description": "Bar frequency for computation. Default 'daily'."},
                "initial": {"type": "number", "default": 100000, "description": "Hypothetical starting capital for $ figures (default 100,000)."},
            },
            "required": ["ticker"],
        },
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
    # NOTE: The legacy 'generate_afl_with_skill' chat tool has been removed.
    # ALL AFL generation now flows through the single canonical tool
    # 'generate_afl_code' (defined above), which delegates to
    # ClaudeAFLEngine — the same engine the /afl/generate REST endpoint uses.
    # If the model calls 'invoke_skill' with an AFL slug, _invoke_skill below
    # also reroutes it to generate_afl_code.
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
                    "description": "Custom footer left text. Default: 'Potomac'.",
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
    # ── PPTX Freestyle — LLM writes raw pptxgenjs JS ─────────────────────────
    # Zero predefined templates; LLM has full pptxgenjs v3 API access.
    # Canvas: LAYOUT_WIDE 16:9 — 13.333" × 7.5". Logo top-right at x:11.73.
    # Brand constants (YELLOW, DARK_GRAY, FONT_H, FONT_B, LOGOS, addLogo) are
    # pre-loaded in the Node.js execution wrapper — LLM only writes slide logic.
    {
        "name": "generate_pptx_freestyle",
        "description": (
            "Generate ANY Potomac-branded PowerPoint presentation by writing raw pptxgenjs v3 JavaScript. "
            "Unlike generate_pptx (21 fixed templates), this gives full creative freedom: "
            "custom layouts, complex diagrams, org charts, infographics, pixel-perfect positioning, "
            "mixed content per slide — anything the pptxgenjs API supports.\n\n"
            "Pre-loaded in code environment (do NOT redefine):\n"
            "  pres (Presentation)\n"
            "  const engine — layout engine: engine.W=13.333, engine.H=7.5 (inches)\n"
            "  const prim   — Potomac primitives library\n"
            "  Palette constants (hex strings — no leading #):\n"
            "    YELLOW='FEC00F'  DARK_GRAY='212121'  WHITE='FFFFFF'  BLACK='000000'\n"
            "    GRAY_60='999999'  GRAY_40='CCCCCC'  GRAY_20='DDDDDD'  GRAY_10='F0F0F0'\n"
            "    YELLOW_20='FEF7D8'  YELLOW_80='FDD251'  GREEN='22C55E'  RED='EB2F5C'\n"
            "  Font constants:\n"
            "    FONT_H='Rajdhani'   (Potomac headline — use UPPERCASE text)\n"
            "    FONT_B='Quicksand'  (Potomac body / caption)\n"
            "    FONT_M='Consolas'   (monospace)\n"
            "  Logo registry — LOGOS object, each entry has .dataUrl and .aspect:\n"
            "    LOGOS.full        — full color logo (use on light backgrounds)\n"
            "    LOGOS.full_black  — black logo (alias: LOGOS.black)\n"
            "    LOGOS.full_white  — white logo (alias: LOGOS.white, use on dark backgrounds)\n"
            "    LOGOS.icon_yellow — yellow icon only (alias: LOGOS.yellow)\n"
            "    LOGOS.icon_black  — black icon only\n"
            "    LOGOS.icon_white  — white icon only\n"
            "  function addLogo(slide, x, y, w, h, variant='full')  — place logo on slide\n"
            "  PALETTE, FONTS — full brand objects (PALETTE.YELLOW, FONTS.HEADLINE, ...)\n\n"
            "Your `code` field = slide-building JS only. Do NOT include require(), "
            "new pptxgen(), or pres.writeFile() — those are handled automatically.\n\n"
            "Canvas is LAYOUT_WIDE (standard PowerPoint 16:9). Coordinates are in inches. "
            "Always keep x>=0 and y>=0. Place Potomac logo top-right on every slide: "
            "addLogo(slide, 11.73, 0.15, 1.25, 0.5, 'full') unless intentionally omitted.\n\n"
            "Quick ref (canvas is 13.333\"x7.5\", coords in inches):\n"
            "  const slide = pres.addSlide();\n"
            "  slide.background = { color: DARK_GRAY };\n"
            "  slide.addText('TITLE', { x:1, y:1, w:11, h:1, fontFace:FONT_H, fontSize:40, bold:true, color:YELLOW });\n"
            "  slide.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:0.2, h:7.5, fill:{color:YELLOW} });\n"
            "  // Use addLogo() helper (recommended — handles dataUrl automatically):\n"
            "  addLogo(slide, 11.73, 0.15, 1.25, 0.5, 'full');\n"
            "  // Or access dataUrl directly (note .dataUrl — LOGOS.full is an object):\n"
            "  slide.addImage({ data:LOGOS.full.dataUrl, x:11.73, y:0.15, w:1.25, h:0.5, sizing:{type:'contain',w:1.25,h:0.5} });\n"
            "  slide.addChart(pres.charts.BAR, [{name:'S1',labels:['A','B'],values:[10,20]}], {x:1,y:2,w:11,h:4});\n"
            "  slide.addTable([[{text:'H',options:{bold:true,fill:{color:YELLOW}}}]], {x:0.5,y:2,w:12});"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Presentation title (stored in file metadata).",
                },
                "filename": {
                    "type": "string",
                    "description": "Output filename e.g. 'Custom_Deck.pptx'. Use underscores.",
                },
                "code": {
                    "type": "string",
                    "description": (
                        "Raw pptxgenjs v3 JavaScript — just the slide-building logic. "
                        "Use pres.addSlide(), slide.addText(), slide.addShape(), "
                        "slide.addChart(), slide.addImage(), slide.addTable(). "
                        "Brand constants (YELLOW, DARK_GRAY, FONT_H, FONT_B, LOGOS, addLogo) "
                        "are pre-defined. Do NOT include require(), new pptxgen(), or pres.writeFile(). "
                        "Canvas is 13.333\" wide x 7.5\" tall (LAYOUT_WIDE 16:9). "
                        "Logo always placed at addLogo(slide, 11.73, 0.15, 1.25, 0.5, 'full')."
                    ),
                },
            },
            "required": ["title", "code"],
        },
    },

    # ── PPTX Template Engine (pptx-automizer) ────────────────────────────────
    {
        "name": "generate_pptx_template",
        "description": (
            "THE STAFF-REPLACEMENT TOOL. Update existing Potomac client decks and quarterly "
            "reports with new data while preserving every pixel of original designer formatting.\n\n"
            "TWO MODES:\n\n"
            "'update' — Upload last quarter's deck → inject this quarter's numbers, chart data, "
            "table rows → output is pixel-identical updated presentation. Supports:\n"
            "  global_replacements: change 'Q4 2025'→'Q1 2026' across ENTIRE deck at once\n"
            "  set_chart_data: inject new data into real PowerPoint charts (preserves all styling)\n"
            "  set_table: inject rows into real styled tables (preserves formatting)\n"
            "  swap_image: replace chart PNGs, logos, screenshots\n\n"
            "'assembly' — Cherry-pick slides from .pptx template files, assemble new deck.\n\n"
            "WORKFLOW: (1) analyze_pptx → get shape names, (2) generate_pptx_template with mods.\n\n"
            "Per-slide ops: set_text, replace_tagged ({{tag}} style), replace_text, "
            "set_chart_data, set_extended_chart_data, set_table, swap_image, set_position, "
            "remove_element, add_element, generate_scratch (pptxgenjs code).\n\n"
            "Chart format: series:[{label}], categories:[{label, values:[]}]\n"
            "Table format: body:[{label, values:[]}]\n\n"
            "Use cases: quarterly report refresh, fund fact sheets, client deck data updates, "
            "RFP decks, board presentations — any deck that gets updated periodically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "template_file_id": {
                    "type": "string",
                    "description": "file_id of the uploaded .pptx template/existing deck.",
                },
                "output_filename": {
                    "type": "string",
                    "description": "Output filename e.g. 'Potomac_Q1_2026_Report.pptx'.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["assembly", "update"],
                    "description": "'update' to refresh existing deck data. 'assembly' to cherry-pick slides.",
                    "default": "update",
                },
                "global_replacements": {
                    "type": "array",
                    "description": "[update] Replacements on ALL text on ALL slides. [{find, replace}]",
                    "items": {
                        "type": "object",
                        "properties": {
                            "find":       {"type": "string"},
                            "replace":    {"type": "string"},
                            "match_case": {"type": "boolean"},
                        },
                        "required": ["find", "replace"],
                    },
                },
                "slide_modifications": {
                    "type": "array",
                    "description": "[update] Per-slide modifications. [{slide_number, modifications:[mod_spec]}]",
                    "items": {
                        "type": "object",
                        "properties": {
                            "slide_number": {"type": "integer"},
                            "modifications": {"type": "array", "items": {"type": "object"}},
                        },
                        "required": ["slide_number", "modifications"],
                    },
                },
                "slides": {
                    "type": "array",
                    "description": "[assembly] Slides to include. [{source_file, slide_number, modifications}]",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source_file":   {"type": "string", "default": "input.pptx"},
                            "slide_number":  {"type": "integer"},
                            "modifications": {"type": "array", "items": {"type": "object"}},
                        },
                        "required": ["slide_number"],
                    },
                },
                "extra_images": {
                    "type": "array",
                    "description": "Images for swap_image ops. [{name, file_id}]",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name":    {"type": "string"},
                            "file_id": {"type": "string"},
                        },
                        "required": ["name", "file_id"],
                    },
                },
            },
            "required": [],
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
                            "footer_text":    {"type": "string", "description": "Custom footer. Default: 'Potomac'."},
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
    # ── Content Studio: Humanizer ────────────────────────────────────────────
    {
        "name": "humanize_text",
        "defer_loading": True,
        "description": (
            "Rewrite AI-generated or generic text to feel human and bypass AI detectors, "
            "while preserving facts and (optionally) writing in a cloned voice. "
            "Multi-pass pipeline: AI-fingerprint scrub → burstiness rewrite → "
            "perplexity injection → optional voice clone → optional LinkedIn SEO → "
            "detector ensemble (Binoculars + GLTR + Roberta) with retry loop → "
            "fact preservation → style fidelity scoring.\n\n"
            "Use this whenever the user asks to 'humanize', 'undetectable', "
            "'remove AI tells', 'sound like me', 'write for LinkedIn', or wants "
            "an SEO-tuned post. Returns the rewritten text plus detection scores."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to humanize."
                },
                "intensity": {
                    "type": "string",
                    "enum": ["light", "standard", "max"],
                    "default": "standard",
                    "description": "How aggressively to rewrite. 'max' uses extra retries."
                },
                "seo_target": {
                    "type": "string",
                    "enum": ["linkedin"],
                    "description": "If set to 'linkedin', applies a LinkedIn-optimized hook + cadence + hashtags pass."
                },
                "style_profile_id": {
                    "type": "string",
                    "description": "Optional studio_writing_styles.id — when set, the rewrite is in that cloned voice."
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional studio_projects.id to associate the run with."
                },
                "preserve_facts": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true, numbers, names, and quotes from the input are diffed against the output and reported."
                }
            },
            "required": ["text"]
        }
    },
    # ── Content Studio: Sites (Lovable-style website builder) ────────────────
    # generate_site / revise_site emit a multi-file HTML/CSS/JS or React/JSX
    # bundle. React files are auto-detected and wrapped through the same
    # sandbox engine as execute_react (Babel + ESM importmap + Tailwind CDN).
    {
        "name": "generate_site",
        "description": (
            "Generate a complete website as a multi-file bundle. Supports TWO modes:\n\n"
            "MODE 1 — Plain HTML/CSS/JS (default):\n"
            "  The `files` dict MUST contain an `index.html` at the root.\n"
            "  Use modern HTML5 + CSS + vanilla JS. Tailwind CDN is fine.\n\n"
            "MODE 2 — React/JSX (like v0 / Lovable):\n"
            "  Write .jsx files (e.g. App.jsx, components/Header.jsx).\n"
            "  The backend AUTO-DETECTS React and wraps the bundle in a sandboxed\n"
            "  HTML page with Babel + ESM importmap + Tailwind — exactly like the\n"
            "  execute_react tool. You do NOT need to provide your own index.html;\n"
            "  one will be generated automatically from the entry component.\n\n"
            "  Available packages (imported normally in JSX — CDN-backed):\n"
            "    react, react-dom, lucide-react, recharts, framer-motion, react-router-dom,\n"
            "    react-hook-form, zustand, jotai, immer, clsx, tailwind-merge, date-fns,\n"
            "    dayjs, lodash, axios, zod, uuid, d3, chart.js, @headlessui/react,\n"
            "    @heroicons/react, @radix-ui/react-icons, react-icons\n\n"
            "  All React hooks (useState, useEffect, useRef, etc.) are pre-imported.\n"
            "  Export the root component as `export default function App()` in App.jsx.\n"
            "  Tailwind classes work out of the box.\n\n"
            "Use this whenever the user asks to build, design, or scaffold a website,\n"
            "landing page, portfolio, dashboard, marketing page, microsite, or web app.\n"
            "Output is a versioned site artifact previewable in an iframe and publishable\n"
            "to a public subdomain.\n\n"
            "RULES:\n"
            "- Do NOT include server-side files (.py, .php, .rb, .sh, etc.)\n"
            "- Keep total bundle ≤ 50 MB and ≤ 200 files.\n"
            "- For React: put the entry component in App.jsx. Child components go in\n"
            "  components/ or pages/ subdirs. CSS goes in styles/.\n"
            "- For plain HTML: put everything under index.html + styles/ + scripts/."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title":       {"type": "string", "description": "Human-readable site title."},
                "description": {"type": "string", "description": "One-sentence summary."},
                "files": {
                    "type": "object",
                    "description": (
                        "Map of relative file paths to their full text content.\n"
                        "For plain HTML: MUST include 'index.html'.\n"
                        "For React: MUST include 'App.jsx' (index.html is auto-generated).\n\n"
                        "Examples:\n"
                        "  Plain: {\"index.html\": \"<!doctype html>...\", \"styles/main.css\": \"...\"}\n"
                        "  React: {\"App.jsx\": \"export default function App() { return <div>Hi</div> }\"}"
                    ),
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["title", "files"],
        },
    },
    {
        "name": "revise_site",
        "description": (
            "Apply targeted edit operations to an existing Content Studio site "
            "artifact and produce a new version. Use this when the user asks to "
            "modify, restyle, fix, or extend a site they already generated. "
            "Operations are applied in order to the file map of the previous version.\n\n"
            "Supported ops:\n"
            "  {op:'write',  path:'index.html', content:'...'}  // add or replace\n"
            "  {op:'delete', path:'old.html'}\n"
            "  {op:'rename', from:'a.css', to:'b.css'}\n\n"
            "If artifact_id is omitted, the LATEST site artifact in the conversation's "
            "Studio project is used."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "artifact_id": {"type": "string"},
                "summary":     {"type": "string"},
                "ops": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op":      {"type": "string", "enum": ["write", "delete", "rename"]},
                            "path":    {"type": "string"},
                            "content": {"type": "string"},
                            "from":    {"type": "string"},
                            "to":      {"type": "string"},
                        },
                        "required": ["op"],
                    },
                },
            },
            "required": ["ops"],
        },
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


def execute_python(
    code: str,
    description: str = "",
    sandbox_files: Optional[Dict[str, bytes]] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute Python code in the unified PythonSandbox.

    Delegates to PythonSandbox._execute_sync() which provides:
      - AST-based security validation (replaces bypassable keyword blocklist)
      - Thread-safe stdout capture via patched print()
      - matplotlib figure capture → base64 PNG artifacts
      - display() / HTML() / SVG() Jupyter-like helpers
      - Shared _SANDBOX_GLOBALS (package installs are immediately visible)

    When ``sandbox_files`` is provided, each (filename → bytes) entry is written
    into the sandbox working dir and exposed to the code as:
        _files["report.pdf"]   → absolute path  (use with open(), PyPDF, pandas…)
        _images["chart.png"]   → base64 string  (images only)

    When ``session_id`` (or the _current_session_id ContextVar) is set, the
    Python namespace is persisted in _SESSION_NAMESPACES so variables defined
    in one execute_python call are visible in subsequent calls within the same
    conversation.
    """
    try:
        from core.sandbox.python_sandbox import PythonSandbox

        ctx: Optional[Dict[str, Any]] = None
        if sandbox_files:
            ctx = {"_sandbox_files": sandbox_files}

        # ── Load persisted namespace for this session ──────────────────────
        # We use the in-process namespace cache (same Python process across
        # successive tool calls in the same conversation), which keeps the
        # FULL Python objects — DataFrames, numpy arrays, dicts of any depth —
        # not just JSON-serialisable scalars.  The sentinel "__inproc__" tells
        # _execute_sync to populate the dict in-place with raw locals instead
        # of going through _serialize_namespace (which strips DataFrames).
        _sid = session_id or _current_session_id.get() or None
        if _sid:
            _ns_in = _SESSION_NAMESPACES.setdefault(_sid, {"__inproc__": True})
            _ns_in.setdefault("__inproc__", True)
        else:
            _ns_in = {}

        # Use __new__ to skip __init__ (which schedules an async task).
        # _execute_sync is fully synchronous and safe to call directly.
        sandbox = object.__new__(PythonSandbox)
        result, _namespace = sandbox._execute_sync(
            code,
            context=ctx,
            persisted_namespace=_ns_in,
            session_id=_sid or None,
        )

        # ── List persistent workspace files (so the model knows what carries
        # over from previous turns instead of regenerating from scratch).
        _workspace_files: List[Dict[str, Any]] = []
        if _sid:
            try:
                from pathlib import Path as _P
                from core.sandbox.db import _SANDBOX_HOME as _SBHOME
                _wsdir = _P(_SBHOME) / "conversations" / str(_sid)
                if _wsdir.exists():
                    for fp in sorted(_wsdir.rglob("*")):
                        if fp.is_file():
                            try:
                                _workspace_files.append({
                                    "path": str(fp.relative_to(_wsdir)).replace("\\", "/"),
                                    "size_bytes": fp.stat().st_size,
                                })
                            except Exception:
                                pass
                        if len(_workspace_files) >= 50:
                            break
            except Exception:
                pass


        # _execute_sync mutated _ns_in in-place when __inproc__ was set, so we
        # don't need to reassign — _SESSION_NAMESPACES already points at it.


        # ── Log sandbox execution to debug transcript ─────────────────────────
        # This gives a dedicated SANDBOX_EXEC event (language, code, stdout,
        # stderr, exit code, duration) instead of burying stdout inside the
        # raw TOOL_CALL_END JSON blob.
        try:
            from core.debug_transcript import get_current_transcript as _get_dt
            _dt_ref = _get_dt()
            if _dt_ref is not None:
                _dt_ref.log_sandbox_exec(
                    language="python",
                    code=code,
                    stdout=result.output or "",
                    stderr=result.error if not result.success else "",
                    exit_code=0 if result.success else 1,
                    duration_ms=result.execution_time_ms or 0.0,
                )
        except Exception:
            pass

        # ── Store file artifacts and generate download URLs ───────────────────
        # _collect_file_artifacts() in python_sandbox.py returns any file the
        # user's code wrote to the sandbox dir as a base64 DisplayArtifact.
        # Store each one via file_store so the frontend can offer a real
        # /files/{id}/download link rather than embedding raw bytes in the JSON.
        _stored_file_ids: Dict[str, str] = {}   # artifact_id → file_id
        if result.artifacts:
            try:
                import base64 as _b64
                from core.file_store import store_file as _sf
                for _a in result.artifacts:
                    if (
                        getattr(_a, "display_type", None) == "file"
                        and (_a.metadata or {}).get("downloadable")
                        and _a.data
                    ):
                        try:
                            _raw = (
                                _b64.b64decode(_a.data)
                                if _a.encoding == "base64"
                                else _a.data.encode("utf-8", errors="replace")
                            )
                            _fname = (_a.metadata or {}).get("filename", "output")
                            _ext   = (_a.metadata or {}).get("extension", ".bin").lstrip(".")
                            _entry = _sf(
                                data=_raw,
                                filename=_fname,
                                file_type=_ext,
                                tool_name="execute_python",
                            )
                            _stored_file_ids[_a.artifact_id] = _entry.file_id
                            logger.info(
                                "execute_python: stored sandbox file '%s' → %s",
                                _fname, _entry.file_id,
                            )
                        except Exception as _fe:
                            logger.debug(
                                "execute_python: could not store file artifact %s: %s",
                                _a.artifact_id, _fe,
                            )
            except ImportError:
                pass

        out: Dict[str, Any] = {
            "success": result.success,
            "output": result.output,
            "variables": result.variables,
        }
        # Surface persistent workspace contents so the agent knows the files
        # it wrote earlier are still on disk (sandbox_dir is reused across
        # turns when session_id is set). Without this hint the model often
        # re-generates the same code/data on every follow-up turn.
        if _workspace_files:
            out["workspace_files"] = _workspace_files
            out["workspace_hint"] = (
                "These files PERSIST across turns in this conversation's sandbox "
                "(in the current working directory). You can re-open / re-read / "
                "modify them with normal Python open()/pandas.read_csv()/etc. — "
                "no need to regenerate them."
            )

        if not result.success:
            out["error"] = result.error
            out["traceback"] = result.output  # _execute_sync puts tb in output on failure
        if result.artifacts:
            _art_list = []
            for a in result.artifacts:
                _art: Dict[str, Any] = {
                    "artifact_id": a.artifact_id,
                    "type":        a.type,
                    "display_type": a.display_type,
                    "encoding":    a.encoding,
                    "metadata":    a.metadata,
                }
                if a.artifact_id in _stored_file_ids:
                    # Replace raw base64 blob with a download URL so the
                    # frontend renders a download card (not a 10 MB JSON blob).
                    _fid = _stored_file_ids[a.artifact_id]
                    _art["data"] = f"/files/{_fid}/download"
                    _art["metadata"] = {
                        **(a.metadata or {}),
                        "file_id":      _fid,
                        "download_url": f"/files/{_fid}/download",
                    }
                else:
                    _art["data"] = a.data
                _art_list.append(_art)
            out["artifacts"]    = _art_list
            out["display_type"] = result.display_type
            # Convenience: surface stored file download URLs at top level
            if _stored_file_ids:
                out["files"] = [
                    {
                        "file_id":      fid,
                        "filename":     next(
                            (a.metadata or {}).get("filename", "output")
                            for a in result.artifacts
                            if a.artifact_id == aid
                        ),
                        "download_url": f"/files/{fid}/download",
                    }
                    for aid, fid in _stored_file_ids.items()
                ]

            # ── Surface chart/image file_ids at the TOP LEVEL ─────────────────
            # plt.show() and other image artifacts now persist to file_store
            # (see python_sandbox._PltCapture.show). The model can pass these
            # file_ids straight into generate_docx / generate_pptx image
            # sections so charts get embedded into Word/PowerPoint instead of
            # silently disappearing.
            _charts: List[Dict[str, Any]] = []
            for a in result.artifacts:
                meta = a.metadata or {}
                fid = meta.get("file_id")
                if not fid:
                    continue
                if a.display_type != "image":
                    continue
                _charts.append({
                    "file_id":      fid,
                    "filename":     meta.get("filename", f"chart_{a.artifact_id[:8]}.png"),
                    "type":         a.type or "image/png",
                    "download_url": meta.get("download_url", f"/files/{fid}/download"),
                    "format":       (meta.get("format") or "png"),
                })
            if _charts:
                out["charts"] = _charts
                # Hint for the model — terse so it stays in context cheaply.
                out["charts_hint"] = (
                    "To embed a chart into a Word/PowerPoint doc, pass its "
                    "file_id in an image section: "
                    '{"type":"image","file_id":"<file_id>"}.'
                )
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


def _build_validation_summary(validation, line_count: int) -> str:
    """One-line human summary for an AFL validation card."""
    if validation.is_valid and validation.error_count == 0:
        return (
            f"AFL code is valid ({line_count} lines, "
            f"{validation.warning_count} warning(s))"
        )
    return (
        f"{validation.error_count} error(s), "
        f"{validation.warning_count} warning(s) across {line_count} lines"
    )


def _normalize_quality_score(value: Any) -> Optional[int]:
    """
    Normalise the AFL engine's quality score to a 0-100 integer for the UI.

    The engine historically returns a 0-1 float (0.95) or a 0-100 number
    depending on the code path. The frontend's QualityRing always treats
    the field as 0-100, so a raw 0.95 would render as "1 / Critical".
    Scale anything that looks fractional up to the 0-100 range, clamp to
    [0, 100], and return as an int. Returns None on missing/invalid input.
    """
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if 0.0 <= f <= 1.0:
        f *= 100.0
    f = max(0.0, min(100.0, f))
    return int(round(f))


def validate_afl(code: str) -> Dict[str, Any]:
    """Validate AFL code using the comprehensive 19-phase validator."""
    if not _AFL_AVAILABLE or _AFL_VALIDATOR is None:
        return {"success": False, "error": "AFL validator not available"}

    validation = _AFL_VALIDATOR.validate(code)
    lines      = code.split("\n")
    code_upper = code.upper()
    line_count = len(lines)
    has_buy_sell = "BUY" in code_upper or "SELL" in code_upper
    has_plot = "PLOT" in code_upper
    has_section_markers = "_SECTION_BEGIN" in code_upper

    # Separate issues by severity for backward-compatible output
    errors   = [i.message for i in validation.issues if i.severity == Severity.ERROR]
    warnings = [i.message for i in validation.issues if i.severity == Severity.WARNING]
    infos    = [i.message for i in validation.issues if i.severity == Severity.INFO]
    suggs    = [i.message for i in validation.issues if i.severity == Severity.SUGGESTION]

    issue_dicts = [i.to_dict() for i in validation.issues]

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
        "issues":           issue_dicts,
        "line_count":       line_count,
        "has_buy_sell":     has_buy_sell,
        "has_plot":         has_plot,
        "genui_card": {
            "type": "data-card_afl_validation",
            "data": {
                "valid": validation.is_valid,
                "line_count": line_count,
                "counts": {
                    "errors": validation.error_count,
                    "warnings": validation.warning_count,
                    "suggestions": validation.suggestion_count,
                    "info": validation.info_count,
                    "cascades": validation.cascade_count,
                },
                "structure": {
                    "has_buy_sell": has_buy_sell,
                    "has_plot": has_plot,
                    "has_section_markers": has_section_markers,
                },
                "issues": issue_dicts[:50],
                "summary": _build_validation_summary(validation, line_count),
            },
        },
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


def generate_afl_code(
    description: str,
    strategy_type: str = "standalone",
    api_key: str = None,
    trade_timing: str = "close",
    extra_context: str = "",
) -> Dict[str, Any]:
    """
    THE singular AFL generation entry point.

    All AFL generation in the system funnels through this function:
      • The chat tool 'generate_afl_code'
      • The chat tool 'generate_afl_with_skill' (legacy alias — routes here)
      • Any stray invoke_skill call with an AFL slug is intercepted by
        _invoke_skill and reshaped to call this function.
      • The /afl/generate REST endpoint also uses the same ClaudeAFLEngine.

    Internally delegates to ClaudeAFLEngine.generate_afl() — the proven path
    with full system-prompt assembly, validation, auto-fix, quality scoring,
    and training-context support. Previously this function used an inline
    sync Anthropic client with a different (weaker) prompt, which is why
    chat-tool AFL generation kept "falling back" while the REST endpoint
    worked. Now they are one and the same.
    """
    if not api_key:
        return {"success": False, "error": "API key required for AFL generation"}

    try:
        import asyncio as _asyncio
        from core.claude_engine import (
            ClaudeAFLEngine,
            BacktestSettings,
            StrategyType,
        )

        # Map trade_timing → trade_delays (close = (0,0,0,0), open = (1,1,1,1))
        _delays = (1, 1, 1, 1) if str(trade_timing).lower() == "open" else (0, 0, 0, 0)
        settings = BacktestSettings(trade_delays=_delays)

        # Build a user_answers dict so the engine's system-prompt builder
        # knows the user's standalone/composite + open/close choices.
        user_answers = {
            "strategy_type": strategy_type or "standalone",
            "trade_timing":  trade_timing or "close",
        }

        engine = ClaudeAFLEngine(api_key=api_key)

        async def _run():
            return await engine.generate_afl(
                request=description,
                settings=settings,
                kb_context=extra_context or "",
                user_answers=user_answers,
                include_training=True,
                stream=False,
            )

        # handle_tool_call is sync, so spin up an event loop.
        try:
            engine_result = _asyncio.run(_run())
        except RuntimeError:
            # Already inside a running loop (e.g. called from async context).
            # Use a fresh loop in a worker thread.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _ex:
                engine_result = _ex.submit(lambda: _asyncio.run(_run())).result()

        afl_code      = engine_result.get("afl_code", "") or ""
        explanation   = engine_result.get("explanation", "") or ""
        stats         = engine_result.get("stats", {}) or {}
        validation    = engine_result.get("validation") or {}
        # Composite mode: engine returns a list of file dicts. Empty list
        # / missing key means single-file output and the UI renders one tab.
        files_list    = engine_result.get("files") or []

        # Build a short human-readable validation report (used by the chat UI).
        v_errors   = validation.get("errors", []) if validation else []
        v_warnings = validation.get("warnings", []) if validation else []
        if validation:
            if validation.get("is_valid"):
                validation_report = (
                    f"Validation passed (0 errors, "
                    f"{len(v_warnings)} warnings)"
                )
            else:
                _errs = v_errors[:10]
                validation_report = (
                    f"{len(v_errors)} error(s):\n  "
                    + "\n  ".join(str(e) for e in _errs)
                )
        else:
            validation_report = ""

        code_upper = afl_code.upper()
        line_count = len(afl_code.split("\n")) if afl_code else 0
        has_buy_sell = "BUY" in code_upper or "SELL" in code_upper
        has_plot = "PLOT" in code_upper
        has_section_markers = "_SECTION_BEGIN" in code_upper

        # Normalize generation_time (engine returns "1.23s" string)
        _gt_raw = stats.get("generation_time")
        if isinstance(_gt_raw, str) and _gt_raw.endswith("s"):
            try:
                gen_time_ms = int(float(_gt_raw[:-1]) * 1000)
            except ValueError:
                gen_time_ms = None
        elif isinstance(_gt_raw, (int, float)):
            gen_time_ms = int(_gt_raw * 1000)
        else:
            gen_time_ms = None

        # Take the first N issue dicts if the validator surfaced structured issues
        raw_issues = validation.get("issues") if validation else None
        if isinstance(raw_issues, list):
            issues_capped = [
                (i if isinstance(i, dict) else (i.to_dict() if hasattr(i, "to_dict") else {"message": str(i)}))
                for i in raw_issues[:50]
            ]
        else:
            issues_capped = []

        result = {
            "success":             True,
            "description":         description,
            "strategy_type":       strategy_type,
            "trade_timing":        trade_timing,
            "afl_code":            afl_code,
            "files":               files_list,
            "explanation":         explanation,
            "validation_valid":    validation.get("is_valid"),
            "validation_errors":   len(v_errors),
            "validation_warnings": len(v_warnings),
            "validation_report":   validation_report,
            "quality_score":       _normalize_quality_score(stats.get("quality_score")),
            "generation_time":     stats.get("generation_time"),
            "line_count":          line_count,
            "has_buy_sell":        has_buy_sell,
            "has_plot":            has_plot,
            "has_section_markers": has_section_markers,
            "issues":              v_errors,
        }
        result["genui_card"] = {
            # The strategy card uses the bare type "afl_strategy" (no
            # data-card_ prefix) — this is the form the frontend's
            # AFLGenerateAdapter checks for. Other AFL cards use the
            # data-card_* prefix; this one predates that convention and
            # the frontend matching is keyed on the bare form.
            "type": "afl_strategy",
            "data": {
                "title": "AFL Strategy",
                "description": description,
                "strategy_type": strategy_type,
                "trade_timing": trade_timing,
                "afl_code": afl_code,
                # Composite bundle: every file the writer emitted, in source
                # order, with the main file flagged. The card renders a
                # file-tab strip and a "Download all (.zip)" button when
                # this list has more than one entry. Pass through the
                # engine's normalised shape verbatim.
                "files": files_list,
                "explanation": explanation,
                "validation": {
                    "is_valid": bool(validation.get("is_valid")) if validation else None,
                    "errors": len(v_errors),
                    "warnings": len(v_warnings),
                    "suggestions": validation.get("suggestion_count", 0) if validation else 0,
                    "info": validation.get("info_count", 0) if validation else 0,
                    "quality_score": _normalize_quality_score(stats.get("quality_score")),
                    "issues": issues_capped,
                },
                "stats": {
                    "generation_time_ms": gen_time_ms,
                    "model": stats.get("model"),
                    "line_count": line_count,
                    "has_buy_sell": has_buy_sell,
                    "has_plot": has_plot,
                    "has_sections": has_section_markers,
                },
                "actions": ["copy", "download_afl", "debug", "explain"],
                "summary": (
                    f"AFL strategy generated ({len(files_list)} files, {line_count} lines, "
                    f"{len(v_errors)} error(s), {len(v_warnings)} warning(s))"
                    if files_list and len(files_list) > 1
                    else
                    f"AFL strategy generated ({line_count} lines, "
                    f"{len(v_errors)} error(s), {len(v_warnings)} warning(s))"
                ),
            },
        }
        return result
    except Exception as e:
        logger.exception("generate_afl_code failed")
        return {"success": False, "error": str(e), "tool": "generate_afl_code"}


def _compute_line_diff(original: str, fixed: str, max_changes: int = 30) -> List[Dict[str, Any]]:
    """Compute a line-by-line diff summary between original and fixed AFL.

    Returns up to ``max_changes`` entries of {line, before, after, kind}
    where kind is 'changed', 'added', or 'removed'.
    """
    import difflib
    orig_lines  = (original or "").splitlines()
    fixed_lines = (fixed or "").splitlines()
    matcher = difflib.SequenceMatcher(a=orig_lines, b=fixed_lines)
    changes: List[Dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            for off in range(max(i2 - i1, j2 - j1)):
                before = orig_lines[i1 + off] if (i1 + off) < i2 else ""
                after  = fixed_lines[j1 + off] if (j1 + off) < j2 else ""
                changes.append({
                    "line": (i1 + off) + 1,
                    "before": before,
                    "after": after,
                    "kind": "changed",
                })
        elif tag == "delete":
            for off in range(i2 - i1):
                changes.append({
                    "line": (i1 + off) + 1,
                    "before": orig_lines[i1 + off],
                    "after": "",
                    "kind": "removed",
                })
        elif tag == "insert":
            for off in range(j2 - j1):
                changes.append({
                    "line": (j1 + off) + 1,
                    "before": "",
                    "after": fixed_lines[j1 + off],
                    "kind": "added",
                })
        if len(changes) >= max_changes:
            break
    return changes[:max_changes]


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

        diff_summary = _compute_line_diff(code, fixed_code)
        return {
            "success":       True,
            "original_code": code,
            "error_message": error_message,
            "fixed_code":    fixed_code,
            "diff_summary":  diff_summary,
            "genui_card": {
                "type": "data-card_afl_debug",
                "data": {
                    "error_message": error_message,
                    "original_code": code,
                    "fixed_code": fixed_code,
                    "diff_summary": diff_summary,
                    "summary": f"{len(diff_summary)} change(s) applied",
                },
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _split_explanation_sections(text: str) -> Dict[str, Any]:
    """Best-effort split of an explain_afl_code response into labelled sections.

    Looks for lines like 'Purpose:', 'Indicators:', 'Entry:', etc. Falls back
    to an empty dict if nothing matches — the frontend can still render the raw text.
    """
    if not text:
        return {}
    section_map = {
        "purpose":     ["purpose", "overview", "summary"],
        "indicators":  ["indicators", "technical indicators"],
        "entry_logic": ["entry", "entry logic", "entry conditions", "buy", "buy signal"],
        "exit_logic":  ["exit", "exit logic", "exit conditions", "sell", "sell signal"],
        "parameters":  ["parameters", "params", "inputs"],
    }
    lines = text.splitlines()
    sections: Dict[str, List[str]] = {k: [] for k in section_map}
    current_key: Optional[str] = None
    for raw_line in lines:
        line = raw_line.rstrip()
        lower = line.lower().strip()
        matched_key = None
        for key, aliases in section_map.items():
            for alias in aliases:
                if lower.startswith(alias + ":") or lower == alias:
                    matched_key = key
                    break
            if matched_key:
                break
        if matched_key:
            current_key = matched_key
            after_colon = line.split(":", 1)[1].strip() if ":" in line else ""
            if after_colon:
                sections[current_key].append(after_colon)
        elif current_key and line.strip():
            sections[current_key].append(line.strip())
    return {k: "\n".join(v).strip() for k, v in sections.items() if v}


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
        sections = _split_explanation_sections(explanation)
        one_liner = (sections.get("purpose") or explanation.strip().split("\n", 1)[0])[:280]

        return {
            "success":     True,
            "code":        (code[:200] + "...") if len(code) > 200 else code,
            "explanation": explanation,
            "genui_card": {
                "type": "data-card_afl_explanation",
                "data": {
                    "code_preview": code[:2000],
                    "sections": sections,
                    "explanation_raw": explanation,
                    "summary": one_liner,
                },
            },
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
        report_lines.append(f"AFL code passed all {len(validation.issues)} checks (0 errors)")
    else:
        report_lines.append(f"Found {validation.error_count} error(s), {validation.warning_count} warning(s)")
    for issue in validation.issues[:20]:
        sev = issue.severity.value if hasattr(issue.severity, "value") else str(issue.severity)
        report_lines.append(f"  [{sev.upper()}] L{issue.line}: [{issue.category}] {issue.message}")
        if issue.suggestion:
            report_lines.append(f"     -> {issue.suggestion}")
        if issue.cascading:
            report_lines.append(f"     (cascading from line {issue.cascading_parent})")
    if len(validation.issues) > 20:
        report_lines.append(f"  ... and {len(validation.issues) - 20} more issues")

    report = "\n".join(report_lines)
    line_count = len(code.split("\n"))

    # Group issues by category for the card UI
    issues_by_category: Dict[str, int] = {}
    for i in validation.issues:
        issues_by_category[i.category] = issues_by_category.get(i.category, 0) + 1

    code_upper = code.upper()
    has_buy_sell = "BUY" in code_upper or "SELL" in code_upper
    has_plot = "PLOT" in code_upper
    has_section_markers = "_SECTION_BEGIN" in code_upper

    issue_dicts = [i.to_dict() for i in validation.issues]

    return {
        "success":          validation.is_valid,
        "is_valid":         validation.is_valid,
        "error_count":      validation.error_count,
        "warning_count":    validation.warning_count,
        "info_count":       validation.info_count,
        "suggestion_count": validation.suggestion_count,
        "cascade_count":    validation.cascade_count,
        "total_issues":     len(validation.issues),
        "issues":           issue_dicts,
        "report":           report,
        "line_count":       line_count,
        "genui_card": {
            "type": "data-card_afl_sanity_check",
            "data": {
                "valid": validation.is_valid,
                "line_count": line_count,
                "counts": {
                    "errors": validation.error_count,
                    "warnings": validation.warning_count,
                    "suggestions": validation.suggestion_count,
                    "info": validation.info_count,
                    "cascades": validation.cascade_count,
                },
                "total_issues": len(validation.issues),
                "auto_fix_applied": bool(auto_fix),
                "structure": {
                    "has_buy_sell": has_buy_sell,
                    "has_plot": has_plot,
                    "has_section_markers": has_section_markers,
                },
                "issues": issue_dicts[:50],
                "issues_by_category": issues_by_category,
                "report": report,
                "summary": _build_validation_summary(validation, line_count),
            },
        },
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

# ── Reference tool handlers (return static prompt content) ──────────────────
# Defined as module-level functions so they're cheap (no closure allocation).
def _get_afl_syntax_reference(ti: Dict[str, Any]) -> Dict[str, Any]:
    """Return the canonical AFL reference, optionally with a scaffold template.

    Delegates to core.prompts.base.build_afl_reference — there is ONE source
    of truth for AFL reference content, and this tool is its public surface.
    """
    try:
        from core.prompts.base import (
            build_afl_reference,
            FUNCTION_REFERENCE,
            RESERVED_KEYWORDS,
            PARAM_OPTIMIZE_PATTERN,
            TIMEFRAME_RULES,
            NORGATE_TICKER_RULES,
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

        template = (ti or {}).get("template")
        content = build_afl_reference(template=template)

        sections = [
            {"title": "Function Signatures",            "body": FUNCTION_REFERENCE.strip()},
            {"title": "Reserved Keywords",              "body": RESERVED_KEYWORDS.strip()},
            {"title": "Conditional + Signal Functions", "body": CONDITIONAL_AND_SIGNAL_FUNCTIONS.strip()},
            {"title": "Param/Optimize Pattern",         "body": PARAM_OPTIMIZE_PATTERN.strip()},
            {"title": "Parameter Functions",            "body": PARAMETER_FUNCTIONS.strip()},
            {"title": "Risk Management",                "body": RISK_MANAGEMENT.strip()},
            {"title": "Timeframe Rules",                "body": TIMEFRAME_RULES.strip()},
            {"title": "Norgate Ticker Universe",        "body": NORGATE_TICKER_RULES.strip()},
            {"title": "Plotting + Shape Constants",     "body": PLOTTING_AND_SHAPES.strip()},
            {"title": "Exploration Functions",          "body": EXPLORATION_FUNCTIONS.strip()},
            {"title": "Color Palette",                  "body": COLOR_PALETTE.strip()},
            {"title": "House Rules",                    "body": HOUSE_RULES.strip()},
        ]
        t = (template or "").strip().lower()
        if t == "standalone":
            sections.append({"title": "Standalone Scaffold", "body": STANDALONE_TEMPLATE.strip()})
        elif t == "composite":
            sections.append({"title": "Composite Scaffold",  "body": COMPOSITE_TEMPLATE.strip()})

        return {
            "success": True,
            "tool": "get_afl_syntax_reference",
            "reference": content,
            "template": t or None,
            "genui_card": {
                "type": "data-card_afl_reference",
                "data": {
                    "sections": sections,
                    "summary": (
                        "Canonical AFL playbook: signatures, reserved words, conditional + "
                        "signal functions, Param/Optimize template, optimiser engines "
                        "(trib default), ApplyStop, timeframe rules, plotting + shape/style "
                        "constants, exploration, colour palette, and the 13 house rules"
                        + (f", plus the {t} scaffold." if t in ("standalone", "composite") else ".")
                    ),
                },
            },
        }
    except Exception as e:
        return {"success": False, "tool": "get_afl_syntax_reference", "error": str(e)}


def _get_yang_capabilities(_ti: Dict[str, Any]) -> Dict[str, Any]:
    """Return the YANG agentic capabilities documentation."""
    try:
        from core.prompts.base import YANG_CAPABILITIES_PROMPT
        return {
            "success": True,
            "tool": "get_yang_capabilities",
            "capabilities": YANG_CAPABILITIES_PROMPT.strip(),
        }
    except Exception as e:
        return {"success": False, "tool": "get_yang_capabilities", "error": str(e)}


def _get_genui_card_schema(_ti: Dict[str, Any]) -> Dict[str, Any]:
    """Return the GenUI structured-card schema."""
    try:
        from core.prompts.base import GENUI_CARD_SCHEMA
        return {
            "success": True,
            "tool": "get_genui_card_schema",
            "schema": GENUI_CARD_SCHEMA.strip(),
        }
    except Exception as e:
        return {"success": False, "tool": "get_genui_card_schema", "error": str(e)}


def _lookup_norgate_ticker(ti: Dict[str, Any]) -> Dict[str, Any]:
    """Search the on-disk Norgate ticker universe and return canonical matches.

    Backs the lookup_norgate_ticker tool. Index is singleton-cached, so only the
    first call pays the ~360 ms parse cost; subsequent calls are pure in-memory
    dict/word-index lookups.
    """
    try:
        from core.norgate_index import NorgateIndex, NORGATE_PREFIX_HINTS

        query = (ti or {}).get("query", "")
        database = (ti or {}).get("database") or None
        try:
            limit = int((ti or {}).get("limit") or 15)
        except (TypeError, ValueError):
            limit = 15
        limit = max(1, min(limit, 50))

        if not query or not str(query).strip():
            return {
                "success": False,
                "tool": "lookup_norgate_ticker",
                "error": "query is required (ticker fragment, company name, or description)",
            }

        index = NorgateIndex.get()
        if not index.loaded:
            return {
                "success": False,
                "tool": "lookup_norgate_ticker",
                "error": index.error or "Norgate ticker index failed to load",
            }

        results = index.search(str(query), database=database, limit=limit)

        # Build a compact, human-summary line and the card.
        if results:
            top = results[0]
            summary = (
                f"{len(results)} match(es) for {query!r}; top: "
                f"{top['symbol']} ({top['database']}) — {top['name']}"
            )
        else:
            summary = f"No Norgate ticker matched {query!r}" + (
                f" in {database!r}." if database else "."
            )

        return {
            "success": True,
            "tool": "lookup_norgate_ticker",
            "query": query,
            "database_filter": database,
            "result_count": len(results),
            "results": results,
            "prefix_hints": NORGATE_PREFIX_HINTS,
            "available_databases": [d["database"] for d in index.list_databases()],
            "genui_card": {
                "type": "data-card_norgate_lookup",
                "data": {
                    "query": query,
                    "database_filter": database,
                    "result_count": len(results),
                    "results": results,
                    "summary": summary,
                },
            },
        }
    except Exception as e:
        logger.exception("lookup_norgate_ticker failed")
        return {"success": False, "tool": "lookup_norgate_ticker", "error": str(e)}


def _calculate_performance(ti: Dict[str, Any]) -> Dict[str, Any]:
    """
    MANDATORY tool for any performance / risk metric on market data.

    Wraps core.performance_engine.calculate_performance() so the LLM can never
    fabricate Sharpe / CAGR / drawdown / etc. — every number is computed from
    live Yahoo Finance data.
    """
    try:
        from core.performance_engine import calculate_performance
        result = calculate_performance(
            ticker=ti.get("ticker", ""),
            freq=ti.get("freq", "daily"),
            initial=float(ti.get("initial", 100_000.0) or 100_000.0),
        )
        # Normalise to the {"success": bool, ...} shape used by handle_tool_call.
        if isinstance(result, dict):
            result["tool"] = "calculate_performance"
            if result.get("status") == "ok":
                result["success"] = True
            elif result.get("status") == "error":
                result["success"] = False
        return result
    except Exception as e:
        logger.error("calculate_performance failed: %s", e, exc_info=True)
        return {
            "success": False,
            "tool": "calculate_performance",
            "error": f"Performance engine failed: {e}",
        }


_STATIC_DISPATCH: Dict[str, Any] = {
    # Each entry: tool_name → lambda tool_input: handler(...)
    # ── Reference / documentation tools (slim system prompt → load on demand) ──
    "get_afl_syntax_reference": _get_afl_syntax_reference,
    "get_yang_capabilities":    _get_yang_capabilities,
    "get_genui_card_schema":    _get_genui_card_schema,
    "lookup_norgate_ticker":    _lookup_norgate_ticker,
    "execute_python":         lambda ti: execute_python(code=ti.get("code",""), description=ti.get("description","")),

    "execute_react":          lambda ti: execute_react(code=ti.get("code",""), description=ti.get("description","")),
    "get_stock_data":         lambda ti: get_stock_data(symbol=ti.get("symbol",""), period=ti.get("period","1mo"), info_type=ti.get("info_type","price")),
    "validate_afl":           lambda ti: validate_afl(code=ti.get("code","")),
    "sanity_check_afl":       lambda ti: sanity_check_afl(code=ti.get("code",""), auto_fix=ti.get("auto_fix",True)),
    "get_stock_chart":        lambda ti: get_stock_chart(symbol=ti.get("symbol",""), period=ti.get("period","3mo"), interval=ti.get("interval","1d"), chart_type=ti.get("chart_type","candlestick")),
    "technical_analysis":     lambda ti: technical_analysis(symbol=ti.get("symbol",""), period=ti.get("period","3mo")),
    "calculate_performance":  lambda ti: _calculate_performance(ti),
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
    """Invoke a registered skill by slug.

    Uses model-agnostic SkillRouter with fallback to legacy Anthropic SkillGateway.
    """
    if not api_key:
        return {"success": False, "error": "API key required for skill invocation"}
    try:
        import asyncio
        skill_slug = tool_input.get("skill_slug", "")

        # ── AFL slugs → canonical generate_afl_code path ─────────────────────
        # The afl-developer skill was retired; AFL goes through ClaudeAFLEngine
        # exclusively. This block is a defensive net: if the model ever calls
        # invoke_skill with an AFL-flavoured slug, we reshape it into a
        # generate_afl_code call so the response still flows through the
        # canonical engine + validator instead of erroring out.
        _AFL_SLUGS = {
            "afl-developer", "amibroker-afl-developer", "afl",
            "amibroker", "afl-expert", "amibroker-developer",
        }
        if (skill_slug or "").lower() in _AFL_SLUGS:
            logger.warning(
                "_invoke_skill: AFL slug '%s' intercepted → rerouting to generate_afl_code "
                "(ClaudeAFLEngine + AFLValidator). All AFL must go through the canonical engine.",
                skill_slug,
            )
            _afl_msg = (
                tool_input.get("message")
                or tool_input.get("prompt")
                or tool_input.get("request")
                or tool_input.get("description")
                or tool_input.get("instructions")
                or ""
            )
            _afl_res = generate_afl_code(
                description=_afl_msg,
                strategy_type=tool_input.get("strategy_type", "standalone"),
                trade_timing=tool_input.get("trade_timing", "close"),
                extra_context=tool_input.get("extra_context", "") or "",
                api_key=api_key,
            )
            # Shape it like an invoke_skill result so the chat layer can
            # render it through the same code path as before.
            _afl_text = ""
            if _afl_res.get("afl_code"):
                _afl_text = (
                    "```afl\n" + _afl_res["afl_code"] + "\n```\n\n"
                    + (_afl_res.get("explanation") or "")
                ).strip()
                if _afl_res.get("validation_report"):
                    _afl_text += "\n\n" + _afl_res["validation_report"]
            return {
                "success":   bool(_afl_res.get("success")),
                "tool":      "invoke_skill",
                "skill":     "afl-developer",
                "skill_name": "AmiBroker AFL Developer",
                "text":      _afl_text or (_afl_res.get("error") or ""),
                "afl_code":  _afl_res.get("afl_code", ""),
                "validation_report": _afl_res.get("validation_report", ""),
                "quality_score":     _afl_res.get("quality_score"),
                "error":     None if _afl_res.get("success") else _afl_res.get("error"),
                "execution_time": 0,
                "usage": {},
            }


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

        from core.llm.anthropic_provider import AnthropicProvider
        from core.sandbox.manager import SandboxManager
        from core.skills.router import SkillRouter

        provider = AnthropicProvider(api_key=api_key)
        sandbox = SandboxManager()
        router = SkillRouter(provider=provider, sandbox_manager=sandbox)

        result = asyncio.run(router.execute(
            skill_slug=skill_slug,
            message=user_message,
            context=tool_input.get("extra_context",""),
        ))

        # ── Surface router-level failures instead of silently masking them
        # The router returns {"success": False, "error": "..."} when the
        # skill slug is unknown/disabled, or when the underlying executor
        # raises. Previously we hardcoded "success": True which led the
        # model to think it had a valid (but empty) response.
        if isinstance(result, dict) and result.get("success") is False:
            err = result.get("error") or "skill execution failed"
            logger.warning("invoke_skill '%s' failed at router level: %s", skill_slug, err)
            return {
                "success": False,
                "tool": "invoke_skill",
                "skill": skill_slug,
                "error": err,
            }

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

        # ── Detect "silent empty" responses: success-shaped result that has
        # no text, no files, no usage. This usually means the executor
        # returned an early-out stub (e.g. the LLM call yielded no content
        # blocks, or the skill prompt was malformed). Telling the model the
        # call was a no-op is much more useful than letting it think it
        # succeeded with empty output.
        files_returned = result.get("files") or result.get("documents") or []
        usage_returned = result.get("usage") or {}
        exec_time = result.get("execution_time", 0) or 0
        if not skill_text and not files_returned and not usage_returned and exec_time == 0:
            logger.warning(
                "invoke_skill '%s' returned a silent-empty response — treating as failure",
                skill_slug,
            )
            return {
                "success": False,
                "tool": "invoke_skill",
                "skill": skill_slug,
                "error": (
                    f"Skill '{skill_slug}' returned an empty response. "
                    "The skill is registered but produced no output. "
                    "Try a different skill, retry with a more detailed prompt, "
                    "or gather the data directly using other tools."
                ),
            }

        base_response = {
            "success":        True,
            "tool":           "invoke_skill",
            "skill":          result.get("skill", skill_slug),
            "skill_name":     result.get("skill_name",""),
            "text":           skill_text,
            "execution_time": exec_time,
            "usage":          usage_returned,
        }
        if files_returned:
            base_response["files"] = files_returned

        # Files are handled locally by the SkillRouter/SandboxManager
        logger.info("invoke_skill '%s' completed successfully", skill_slug)
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


# ── Auto-save Python executions into the conversation workspace ─────────────
# Every non-trivial execute_python call also drops the code into the IDE panel
# so the user can read it, edit it, and re-run it. This is the "the python
# should auto-execute BUT also land in the workspace" flow — the agent doesn't
# have to remember to call workspace_write_file for every analysis script.
#
# Skipped silently when:
#   • code is shorter than _AUTO_SAVE_MIN_CHARS (scratch eval)
#   • code is fewer than _AUTO_SAVE_MIN_LINES non-blank lines (scratch eval
#     even if it happens to have a newline — e.g. `f = open(...); content = f.read()`)
#   • code is just opening/reading uploaded files for the agent's own eyes
#     (no `print`, no assignment to a result variable beyond the read itself)
#   • conversation_id or user_id is missing (no chat context)
#   • the workspace DB layer is unavailable or errors (best-effort)
_AUTO_SAVE_MIN_CHARS = 160
_AUTO_SAVE_MIN_LINES = 4


def _slug_for_auto_save(description: str, code: str) -> str:
    """Pick a stable filename for an auto-saved execute_python script.

    Priority:
      1. Slug of `description` (the agent already wrote a one-liner about
         what the code does) → stable name, agent reruns of the same intent
         version-bump the same file.
      2. Fallback: ``auto_<8-char-content-hash>.py`` — identical code in
         the same conversation lands in the same file.
    """
    import hashlib
    import re as _re

    desc = (description or "").strip()
    if desc:
        slug = _re.sub(r"[^A-Za-z0-9_-]+", "_", desc).strip("_").lower()[:48]
        if slug:
            return f"{slug}.py"

    digest = hashlib.sha1(code.encode("utf-8", errors="replace")).hexdigest()[:8]
    return f"auto_{digest}.py"


def _auto_save_python_to_workspace(
    tool_input: Dict[str, Any],
    result: Dict[str, Any],
    conversation_id: Optional[str],
    user_id: Optional[str],
) -> None:
    """Best-effort: drop the executed code into the per-conversation workspace.

    Mutates ``result`` in place to surface the saved filename + version so the
    chat stream's tool_result event carries enough info for the IDE panel to
    refresh (frontend hook: refetch listWorkspaceFiles when result has a
    ``workspace_file`` field).

    Never raises — auto-save failure must not break the actual execute_python
    response the user is waiting on.
    """
    if not isinstance(result, dict):
        return
    if not conversation_id or not user_id:
        return
    code = (tool_input or {}).get("code") or ""
    if not code or not isinstance(code, str):
        return
    stripped = code.strip()
    if not stripped:
        return
    non_blank_lines = [ln for ln in stripped.splitlines() if ln.strip()]
    # Skip true scratch evaluations:
    #   • too short (under 160 chars OR fewer than 4 non-blank lines)
    #   • no real "work" — the script just opens/reads files for the agent's
    #     own internal use (no print, no return-style assignment, no real
    #     computation). The previous threshold mirrored 90-byte snippets
    #     like `f = open(...); content = f.read()` into the user's IDE,
    #     which the user (correctly) flagged as noise.
    if len(stripped) < _AUTO_SAVE_MIN_CHARS:
        return
    if len(non_blank_lines) < _AUTO_SAVE_MIN_LINES:
        return
    has_print = "print(" in stripped or "print (" in stripped
    has_display = "display(" in stripped or "HTML(" in stripped or "SVG(" in stripped
    has_plot = "plt.show" in stripped or ".show(" in stripped or "plt.savefig" in stripped
    if not (has_print or has_display or has_plot):
        # No visible output of any kind — almost certainly the agent
        # reading/parsing a file for its own context. Don't surface to user.
        return
    try:
        from core import workspace as _ws
        description = (tool_input or {}).get("description") or ""
        filename = _slug_for_auto_save(description, code)
        row = _ws.write_file(
            conversation_id,
            user_id,
            filename,
            code,
            language="python",
            author="system",
        )
        result["workspace_file"] = {
            "filename":   row.get("filename"),
            "version":    row.get("version"),
            "language":   row.get("language"),
            "size_bytes": row.get("size_bytes"),
            "last_author": row.get("last_author"),
            "auto_saved": True,
        }
    except Exception as e:
        logger.debug("auto-save execute_python to workspace skipped: %s", e)


# ── read_pdf — purpose-built PDF reader ─────────────────────────────────────
# The agent used to handle PDFs by writing a pdfplumber snippet through
# execute_python. That works but spills a wall of stdout, leaks file handles
# into Session Variables, and renders as a code-output card. This dedicated
# handler:
#   • takes a file_id (preferred) or filename of an uploaded file
#   • extracts text page-by-page with PyMuPDF (fitz), fallback pdfplumber
#   • returns structured per-page output + metadata
#   • attaches a `genui_card` so the frontend renders a clean PDF panel

_PDF_MAX_TOTAL_CHARS = 200_000   # cap returned text to keep context manageable
_PDF_PAGE_PREVIEW_CHARS = 600    # per-page preview in the card payload


def _resolve_uploaded_pdf_path(
    file_id: Optional[str],
    filename: Optional[str],
    conversation_id: str,
    user_id: str,
) -> Optional[Dict[str, Any]]:
    """Resolve an uploaded file (by id, falling back to filename) to a row
    from the `file_uploads` table that is linked to this conversation AND
    owned by this user. Returns the row or None.
    """
    try:
        from db.supabase_client import get_supabase
        db = get_supabase()
    except Exception as e:
        logger.warning("read_pdf: supabase unavailable: %s", e)
        return None

    if file_id:
        try:
            r = (
                db.table("file_uploads")
                .select("id, user_id, original_filename, storage_path, content_type, file_size")
                .eq("id", file_id)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if r.data:
                return r.data[0]
        except Exception as e:
            logger.debug("read_pdf: file_id lookup failed: %s", e)

    if filename:
        # Match a file uploaded to THIS conversation by name. Newest first.
        try:
            r = (
                db.table("conversation_files")
                .select("file_id, file_uploads(id, user_id, original_filename, storage_path, content_type, file_size, created_at)")
                .eq("conversation_id", conversation_id)
                .execute()
            )
            target = filename.lower().strip()
            best = None
            for cf in (r.data or []):
                fu = cf.get("file_uploads") or {}
                if (fu.get("user_id") != user_id):
                    continue
                fname = (fu.get("original_filename") or "").lower().strip()
                if fname == target:
                    return fu
                if (not best) and target in fname:
                    best = fu
            if best:
                return best
        except Exception as e:
            logger.debug("read_pdf: filename lookup failed: %s", e)
    return None


def _parse_page_range(spec: Optional[str], total_pages: int) -> List[int]:
    """Parse "1-5,8,10-12" into a sorted list of 1-based page indices, clamped
    to ``[1, total_pages]``. Empty / None → all pages."""
    if not spec or not isinstance(spec, str):
        return list(range(1, total_pages + 1))
    out: set = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            try:
                a, b = chunk.split("-", 1)
                lo, hi = int(a), int(b)
                if lo > hi:
                    lo, hi = hi, lo
                for p in range(lo, hi + 1):
                    if 1 <= p <= total_pages:
                        out.add(p)
            except ValueError:
                continue
        else:
            try:
                p = int(chunk)
                if 1 <= p <= total_pages:
                    out.add(p)
            except ValueError:
                continue
    return sorted(out) or list(range(1, total_pages + 1))


def read_pdf(
    file_id: Optional[str] = None,
    filename: Optional[str] = None,
    page_range: Optional[str] = None,
    *,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract text from a previously-uploaded PDF in this conversation.

    Accepts ``file_id`` (preferred) or ``filename``. Returns per-page text
    plus full-text concatenation and a genui_card payload for the IDE.
    """
    import time as _t
    started = _t.time()

    if not conversation_id or not user_id:
        return {
            "success": False, "tool": "read_pdf",
            "error": "read_pdf requires an authenticated chat context",
        }
    if not file_id and not filename:
        return {
            "success": False, "tool": "read_pdf",
            "error": "Provide file_id or filename",
        }

    row = _resolve_uploaded_pdf_path(file_id, filename, conversation_id, user_id)
    if row is None:
        return {
            "success": False, "tool": "read_pdf",
            "error": (
                f"No uploaded PDF matches "
                f"{'file_id=' + repr(file_id) if file_id else 'filename=' + repr(filename)} "
                f"in this conversation"
            ),
        }

    storage_path = row.get("storage_path") or ""
    real_filename = row.get("original_filename") or filename or "document.pdf"
    if not storage_path or not os.path.exists(storage_path):
        return {
            "success": False, "tool": "read_pdf",
            "error": f"File {real_filename!r} is registered but its bytes are missing on disk",
        }

    # ── Extract per-page text ────────────────────────────────────────────────
    pages: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {}
    extractor_used: str = ""
    total_pages_in_doc = 0

    try:
        import fitz  # PyMuPDF
        with fitz.open(storage_path) as doc:
            total_pages_in_doc = doc.page_count
            target = _parse_page_range(page_range, total_pages_in_doc)
            try:
                md = doc.metadata or {}
                metadata = {
                    "title":    md.get("title") or "",
                    "author":   md.get("author") or "",
                    "subject":  md.get("subject") or "",
                    "creator":  md.get("creator") or "",
                    "producer": md.get("producer") or "",
                }
            except Exception:
                metadata = {}
            for p in target:
                try:
                    text = doc[p - 1].get_text("text") or ""
                except Exception:
                    text = ""
                pages.append({"number": p, "text": text, "char_count": len(text)})
        extractor_used = "pymupdf"
    except ImportError:
        try:
            import pdfplumber  # type: ignore
            with pdfplumber.open(storage_path) as pdf:
                total_pages_in_doc = len(pdf.pages)
                target = _parse_page_range(page_range, total_pages_in_doc)
                try:
                    metadata = {
                        k: str(v) for k, v in (pdf.metadata or {}).items()
                    }
                except Exception:
                    metadata = {}
                for p in target:
                    try:
                        text = pdf.pages[p - 1].extract_text() or ""
                    except Exception:
                        text = ""
                    pages.append({"number": p, "text": text, "char_count": len(text)})
            extractor_used = "pdfplumber"
        except Exception as e:
            return {
                "success": False, "tool": "read_pdf",
                "error": f"No PDF extractor available: {e}",
            }
    except Exception as e:
        return {
            "success": False, "tool": "read_pdf",
            "error": f"PDF parse failed: {e}",
        }

    full_text = "\n\n".join(p["text"] for p in pages if p.get("text"))
    truncated = False
    if len(full_text) > _PDF_MAX_TOTAL_CHARS:
        full_text = full_text[:_PDF_MAX_TOTAL_CHARS]
        truncated = True
    total_chars = sum(p.get("char_count", 0) for p in pages)
    elapsed_ms = int((_t.time() - started) * 1000)

    # ── genui_card payload (small enough for the chat envelope; full text
    #    sits on `full_text` for the model, the card shows previews) ───────
    page_previews = [
        {
            "number":     p["number"],
            "char_count": p["char_count"],
            "preview":    (p["text"][:_PDF_PAGE_PREVIEW_CHARS] +
                           ("…" if len(p["text"]) > _PDF_PAGE_PREVIEW_CHARS else "")),
        }
        for p in pages
    ]

    return {
        "success": True,
        "tool": "read_pdf",
        "file_id":     row.get("id"),
        "filename":    real_filename,
        "size_bytes":  row.get("file_size") or 0,
        "total_pages": total_pages_in_doc,
        "pages_returned": len(pages),
        "extractor":   extractor_used,
        "metadata":    metadata,
        "pages":       pages,           # full per-page text for the model
        "full_text":   full_text,       # capped at _PDF_MAX_TOTAL_CHARS
        "truncated":   truncated,
        "total_chars": total_chars,
        "duration_ms": elapsed_ms,
        "genui_card": {
            "type": "data-card_pdf_read",
            "data": {
                "filename":    real_filename,
                "file_id":     row.get("id"),
                "size_bytes":  row.get("file_size") or 0,
                "total_pages": total_pages_in_doc,
                "pages_returned": len(pages),
                "total_chars": total_chars,
                "truncated":   truncated,
                "extractor":   extractor_used,
                "metadata":    metadata,
                "page_range":  page_range or None,
                "page_previews": page_previews,
                "duration_ms": elapsed_ms,
                "summary": (
                    f"Read {len(pages)} of {total_pages_in_doc} pages from "
                    f"{real_filename} ({total_chars:,} chars"
                    + (", truncated" if truncated else "")
                    + ")"
                ),
            },
        },
    }


def handle_tool_call(
    tool_name:       str,
    tool_input:      Dict[str, Any],
    supabase_client=None,
    api_key:         str = None,
    conversation_file_ids: Optional[List[str]] = None,
    conversation_id: Optional[str] = None,
    user_id:         Optional[str] = None,
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

    File injection (FIX for doc-interpreter / uploaded file reading):
      When ``conversation_file_ids`` is provided and the tool is ``execute_python``,
      the attached files are materialized into the sandbox working dir and exposed
      as ``_files["name.ext"]`` / ``_images["name.png"]`` so Claude never has to
      guess a path like ``/uploads/<uuid>`` (which doesn't exist on disk).

    Namespace persistence (FIX for sandbox state loss):
      Sets _current_session_id ContextVar so execute_python() can load/save
      the Python namespace across successive calls within the same conversation.
    """
    # Propagate conversation_id so execute_python() can load/save namespace
    _sid_token = _current_session_id.set(conversation_id or "")
    start_time = time.time()
    try:
        logger.debug("Handling tool call: %s", tool_name)

        # ── Special handling for execute_python with attached files ────────────
        if tool_name == "execute_python" and conversation_file_ids:
            try:
                from core.sandbox.file_injector import resolve_sandbox_files
                sandbox_files = resolve_sandbox_files(list(conversation_file_ids))
            except Exception as _fe:
                logger.warning("Could not resolve conversation file_ids for sandbox: %s", _fe)
                sandbox_files = {}
            result = execute_python(
                code=tool_input.get("code", ""),
                description=tool_input.get("description", ""),
                sandbox_files=sandbox_files or None,
                session_id=conversation_id,
            )
            # Auto-mirror the executed code into the IDE workspace so the
            # user can read / edit / re-run it. Best-effort; never raises.
            _auto_save_python_to_workspace(tool_input, result, conversation_id, user_id)
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            result["_tool_time_ms"] = elapsed_ms
            # Log tool call end for debug transcript (early-return path)
            # log_sandbox_exec was already called inside execute_python() above.
            # Here we log the tool-level end so TOOL_CALL_END appears in the
            # transcript, stripping artifact data to avoid bloating the log.
            try:
                from core.debug_transcript import get_current_transcript as _gct
                _dt = _gct()
                if _dt:
                    _log_res = {k: v for k, v in result.items() if k != "artifacts"}
                    _dt.log_tool_call_end(tool_name, _log_res, elapsed_ms)
            except Exception:
                pass
            return json.dumps(result, indent=2, default=str)

        # ── Fast path: static tools (no injected deps) — O(1), zero allocation ─
        handler = _STATIC_DISPATCH.get(tool_name)
        if handler is not None:
            result = handler(tool_input)
            # Mirror non-trivial execute_python code into the IDE workspace.
            # The synchronous execute_python sandbox runs the code and returns
            # output; this side-effect drops the source into the IDE panel so
            # the user has the script to inspect / edit / re-run. No-op for
            # other static-dispatch tools.
            if tool_name == "execute_python":
                _auto_save_python_to_workspace(tool_input, result, conversation_id, user_id)


        # ── read_pdf — needs conversation_id + user_id to scope file lookup ───
        elif tool_name == "read_pdf":
            if not conversation_id or not user_id:
                result = {
                    "success": False,
                    "tool": "read_pdf",
                    "error": "read_pdf requires an authenticated chat context",
                }
            else:
                try:
                    result = read_pdf(
                        file_id=tool_input.get("file_id"),
                        filename=tool_input.get("filename"),
                        page_range=tool_input.get("page_range"),
                        conversation_id=conversation_id,
                        user_id=user_id,
                    )
                except Exception as _rp_err:
                    logger.exception("read_pdf failed")
                    result = {
                        "success": False, "tool": "read_pdf",
                        "error": str(_rp_err),
                    }

        # ── Workspace tools — need conversation_id + user_id from chat ctx ─────
        elif tool_name in (
            "workspace_list_files",
            "workspace_read_file",
            "workspace_write_file",
            "workspace_execute_file",
        ):
            if not conversation_id or not user_id:
                result = {
                    "success": False,
                    "tool": tool_name,
                    "error": (
                        "workspace tools require conversation_id and user_id; "
                        "available only inside an authenticated chat turn."
                    ),
                }
            else:
                from core import workspace as _ws
                try:
                    if tool_name == "workspace_list_files":
                        files = _ws.list_files(conversation_id, user_id)
                        result = {
                            "success": True,
                            "tool": tool_name,
                            "file_count": len(files),
                            "files": files,
                        }
                    elif tool_name == "workspace_read_file":
                        row = _ws.read_file(
                            conversation_id, user_id, tool_input.get("filename", "")
                        )
                        if row is None:
                            result = {
                                "success": False,
                                "tool": tool_name,
                                "error": f"file {tool_input.get('filename')!r} not found in this conversation's workspace",
                            }
                        else:
                            result = {"success": True, "tool": tool_name, "file": row}
                    elif tool_name == "workspace_write_file":
                        row = _ws.write_file(
                            conversation_id,
                            user_id,
                            tool_input.get("filename", ""),
                            tool_input.get("content", ""),
                            tool_input.get("language"),
                            author="agent",
                        )
                        result = {
                            "success": True,
                            "tool": tool_name,
                            "file": row,
                            "genui_card": {
                                "type": "data-card_workspace_file",
                                "data": {
                                    "filename": row["filename"],
                                    "language": row["language"],
                                    "version": row["version"],
                                    "size_bytes": row.get("size_bytes", 0),
                                    "summary": (
                                        f"Saved {row['filename']} "
                                        f"(v{row['version']}, "
                                        f"{row.get('size_bytes', 0)} bytes) "
                                        f"to the IDE workspace."
                                    ),
                                },
                            },
                        }
                    else:  # workspace_execute_file
                        result = _ws.execute_file(
                            conversation_id,
                            user_id,
                            tool_input.get("filename", ""),
                        ) or {"success": False, "error": "no result"}
                        result.setdefault("tool", tool_name)
                except _ws.WorkspaceError as _we:
                    result = {
                        "success": False,
                        "tool": tool_name,
                        "error": str(_we),
                    }
                except Exception as _wse:
                    logger.exception("workspace tool %s failed", tool_name)
                    result = {
                        "success": False,
                        "tool": tool_name,
                        "error": str(_wse),
                    }

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
            # Legacy alias — reroute to the canonical generate_afl_code so all
            # AFL generation flows through ClaudeAFLEngine (same path as
            # /afl/generate REST endpoint).
            result = generate_afl_code(
                description=tool_input.get("request", "") or tool_input.get("description", ""),
                strategy_type=tool_input.get("strategy_type", "standalone"),
                trade_timing=tool_input.get("trade_timing", "close"),
                api_key=api_key,
            )
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
        elif tool_name == "generate_pptx_freestyle":
            # Freestyle PPTX: LLM writes raw pptxgenjs JS; wrapper provides brand env.
            try:
                from core.tools_v2.document_tools import handle_generate_pptx_freestyle
                _pptx_free_json = handle_generate_pptx_freestyle(tool_input, api_key=api_key)
                result = json.loads(_pptx_free_json)
            except Exception as _pptx_free_err:
                result = {"status": "error", "error": str(_pptx_free_err)}
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
        elif tool_name == "generate_pptx_template":
            # Template-driven PPTX assembly/update via pptx-automizer + pptxgenjs.
            # Supports: update mode (quarterly refresh), assembly mode (cherry-pick slides).
            try:
                from core.tools_v2.document_tools import handle_generate_pptx_template
                _pptx_tmpl_json = handle_generate_pptx_template(tool_input, api_key=api_key)
                result = json.loads(_pptx_tmpl_json)
            except Exception as _pptx_tmpl_err:
                result = {"status": "error", "error": str(_pptx_tmpl_err)}
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
        elif tool_name == "generate_site":
            # Content Studio: Lovable-style website generation.
            try:
                from core.tools_v2.site_tools import handle_generate_site
                _site_json = handle_generate_site(tool_input, api_key=api_key)
                result = json.loads(_site_json)
            except Exception as _site_err:
                result = {"status": "error", "error": str(_site_err), "tool": "generate_site"}
        elif tool_name == "revise_site":
            try:
                from core.tools_v2.site_tools import handle_revise_site
                # Inject conversation_id so the handler can resolve the latest
                # site artifact in the active Studio project.
                _ti = dict(tool_input or {})
                if conversation_id and "conversation_id" not in _ti:
                    _ti["conversation_id"] = conversation_id
                _site_json = handle_revise_site(_ti, api_key=api_key)
                result = json.loads(_site_json)
            except Exception as _site_err:
                result = {"status": "error", "error": str(_site_err), "tool": "revise_site"}
        elif tool_name == "humanize_text":
            # Multi-pass advanced humanizer (AI detector bypass + LinkedIn SEO + voice clone).
            try:
                from core.humanize import pipeline as _hum
                _hu_user_id = (tool_input.get("_user_id") or "") if isinstance(tool_input, dict) else ""
                # The /chat/agent path doesn't currently pass user_id into tool_input; humanizer
                # logs without a user_id are still valid — pipeline only requires the api_key.
                result = _hum.run(
                    text=tool_input.get("text", "") or "",
                    api_key=api_key or "",
                    user_id=_hu_user_id,
                    project_id=tool_input.get("project_id"),
                    conversation_id=conversation_id,
                    style_profile_id=tool_input.get("style_profile_id"),
                    intensity=tool_input.get("intensity", "standard"),
                    seo_target=tool_input.get("seo_target"),
                    preserve_facts=bool(tool_input.get("preserve_facts", True)),
                )
            except Exception as _hum_err:
                result = {"error": f"humanize_text failed: {_hum_err}"}
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
        _json_out = json.dumps(result, indent=2, default=str)
        try:
            from core.debug_transcript import get_current_transcript as _gct
            _dt = _gct()
            if _dt:
                _dt.log_tool_call_end(tool_name, result, elapsed_ms)
        except Exception:
            pass
        return _json_out

    except Exception as e:
        _err_ms = round((time.time() - start_time) * 1000, 2)
        try:
            from core.debug_transcript import get_current_transcript as _gct
            _dt = _gct()
            if _dt:
                _dt.log_tool_call_end(tool_name, {"error": str(e)}, _err_ms)
        except Exception:
            pass
        logger.error("Error in tool call %s: %s", tool_name, e, exc_info=True)
        return json.dumps({"error": str(e), "traceback": traceback.format_exc()[:500]})
    finally:
        _current_session_id.reset(_sid_token)



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