"""
Claude AFL Engine - Core AFL code generation using Claude API.

CHANGES FROM PREVIOUS VERSION (all bugs / issues resolved):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BUG FIX 1  — generate_afl stream path was returning a coroutine instead of an async
             generator because _call_claude is `async def` but wasn't being awaited.
             Fixed: added `await` on the streaming branch.

             WHY `await` IS CORRECT HERE (verified by runtime test):
             _call_claude is `async def`, so calling it produces a coroutine.
             _stream_wrapper is an `async def` generator, so calling it produces
             an async generator object — not a coroutine.  _call_claude returns
             that generator object as its return value.  Awaiting the coroutine
             therefore gives callers the async generator, which is the right type.
             Omitting `await` would give callers the coroutine itself, which cannot
             be iterated with `async for`.

BUG FIX 2  — asyncio.Lock() was created at class-definition time as a class variable.
             Before Python 3.10 this silently binds to whichever event loop exists at
             import time (often none), causing RuntimeError at runtime.
             Fixed: lock is now created lazily on first use.

BUG FIX 3  — _request_cache is class-level (shared across all instances).  Two engines
             with different models (Sonnet vs Opus) could return each other's cached
             results.  Fixed: self.model is now included in the cache key.

BUG FIX 4  — Cache key truncated kb_context to 200 chars; different contexts with
             identical prefixes would collide.  Fixed: MD5 hash of the full string.

BUG FIX 5  — Two parallel training-cache dicts (_training_cache + _training_cache_time)
             required double lookups / sets for every cache operation.
             Fixed: unified into a single dict: key → (value, timestamp).

BUG FIX 6  — _parse_response silently left unknown language tags (e.g. "python\n") at
             the top of the returned code string.
             Fixed: generic language-tag stripper via compiled regex.

BUG FIX 7  — _format_user_answers used answers.get('strategy_type') (no fallback) in
             the formatted output, rendering "None" into the prompt.
             Fixed: explicit fallback 'Not specified' on every answers.get() call.

BUG FIX 8  — _call_claude had two identical except branches (both log + re-raise).
             Fixed: collapsed into one except Exception block.

STYLE FIX  — _SINGLE_ARG_PATTERNS type hint was misleading (Tuple[re.Pattern, str]
             with no comment on what the str element means).
             Fixed: added inline comment clarifying the (pattern, replacement) tuple.
"""

import re
import asyncio
import hashlib
import time
import logging
import traceback
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from collections import OrderedDict
from enum import Enum

import anthropic

# Single source of truth for skills / streaming configuration
from core.skills import SKILLS_BETAS, CODE_EXECUTION_TOOL
from core.context_manager import truncate_context, MAX_RECENT_MESSAGES
from core.streaming import stream_claude_response

# Training manager is optional — gracefully degraded if the module is absent
try:
    from core.training import get_training_manager
    TRAINING_ENABLED = True
except ImportError:
    TRAINING_ENABLED = False
    get_training_manager = None

logger = logging.getLogger(__name__)

# ── Strategy type enumeration ─────────────────────────────────────────────────
class StrategyType(str, Enum):
    """Strategy type for AFL generation (affects code structure)."""
    STANDALONE = "standalone"  # Complete strategy with all sections
    COMPOSITE = "composite"    # Only strategy logic (no plotting/settings)

# ── Top-level defaults ────────────────────────────────────────────────────────
DEFAULT_MODEL       = "claude-sonnet-4-6"  # FIX-12: was claude-haiku-4-5-20251001
                                           # AFL generation requires complex multi-step
                                           # reasoning; Haiku produces lower quality output
MAX_TOKENS          = 8192  # FIX-03: was 4096 — AFL strategies with full Param/Optimize,
                            # indicators, ExRem, Plot, and AddColumn easily exceed 4096 tokens
AMIBROKER_SKILL_ID  = "skill_01GG6E88EuXr9H9tqLp51sH5"

SKILLS_CONTAINER = {
    "skills": [{"skill_id": AMIBROKER_SKILL_ID, "type": "custom"}]
}

# ── Module-level regex for stripping code-fence language tags ─────────────────
# Matches an optional word (e.g. "afl", "python", "c") followed immediately by a
# newline at the very start of a fenced block.  Used in _parse_response.
_LANG_TAG_RE = re.compile(r'^[a-zA-Z0-9_+-]*\n')


# =============================================================================
# BacktestSettings
# =============================================================================

@dataclass
class BacktestSettings:
    """
    Immutable configuration for a backtest run.

    Call .to_afl() to produce the AFL SetOption / SetTradeDelays block that
    should be prepended to every generated strategy.
    """
    initial_equity:    float              = 100_000
    position_size:     str                = "100"
    position_size_type: str               = "spsPercentOfEquity"
    max_positions:     int                = 10
    commission:        float              = 0.0005   # 0.05% per trade — FIX-02: was 0.001
    trade_delays:      Tuple[int, int, int, int] = (0, 0, 0, 0)
    margin_requirement: float             = 100

    def to_afl(self) -> str:
        """Return AFL code that encodes these settings.

        FIX-02: CommissionMode corrected from 1 (flat dollar) to 2 (percentage).
        Default commission updated from 0.001 to 0.0005 (0.05%) to match the
        system prompt, skill templates, and SKILL.md — all of which use Mode 2.
        Added the three missing SetOption lines that were in the system prompt
        but absent from this output: UsePrevBarEquityForPosSizing, AllowPositionShrinking,
        and AccountMargin.
        PositionSize now uses a plain assignment (AFL standard) instead of the
        non-existent SetPositionSize() call.
        """
        d = self.trade_delays
        return (
            f'// Backtest Settings\n'
            f'SetOption("InitialEquity", {self.initial_equity});\n'
            f'SetOption("MaxOpenPositions", {self.max_positions});\n'
            f'SetOption("CommissionMode", 2);\n'
            f'SetOption("CommissionAmount", {self.commission});\n'
            f'SetOption("UsePrevBarEquityForPosSizing", True);\n'
            f'SetOption("AllowPositionShrinking", True);\n'
            f'SetOption("AccountMargin", {self.margin_requirement});\n'
            f'SetTradeDelays({d[0]}, {d[1]}, {d[2]}, {d[3]});\n'
            f'PositionSize = {self.position_size};\n'
        )


# =============================================================================
# ClaudeAFLEngine
# =============================================================================

class ClaudeAFLEngine:
    """
    Core AFL code generation engine that wraps the Claude API.

    Design notes
    ────────────
    • All Claude API calls are funnelled through the single _call_claude() helper
      so streaming vs. non-streaming behaviour is handled in one place.
    • _request_cache is a class-level LRU (OrderedDict) that is keyed by a hash
      that INCLUDES self.model, preventing cross-model cache collisions.
    • The training cache uses a single unified dict (key → (value, timestamp))
      instead of two parallel dicts.
    • asyncio.Lock is created lazily (see _training_cache_lock property) to avoid
      the pre-Python-3.10 event-loop binding problem.
    """

    # ── Class-level LRU result cache (shared across instances) ───────────────
    # Key format:  "<model>|<request_hash>|..." — includes model so Sonnet/Opus
    # instances never share cache entries (FIX #3).
    _request_cache: OrderedDict = OrderedDict()
    _request_cache_maxsize      = 128

    # ── AFL validation sets (frozensets for O(1) membership tests) ────────────
    # FIX-01: OBV removed — OBV() takes ZERO arguments (not even a period).
    # It was incorrectly listed here, which caused _SINGLE_ARG_PATTERNS to build
    # a regex that would "fix" OBV(Close, n) → OBV(n) instead of OBV().
    SINGLE_ARG_FUNCTIONS = frozenset({
        "RSI", "ATR", "ADX", "CCI", "MFI", "PDI", "MDI",
        "StochK", "StochD",
    })

    # Zero-argument functions — used by _validate_and_fix to catch OBV(n) misuse
    NO_ARG_FUNCTIONS = frozenset({"OBV"})

    DOUBLE_ARG_FUNCTIONS = frozenset({
        "MA", "EMA", "SMA", "WMA", "DEMA", "TEMA", "ROC",
        "HHV", "LLV", "StDev", "Sum", "Ref", "LinearReg",
    })

    RESERVED_WORDS = frozenset({
        "Open", "High", "Low", "Close", "Volume", "OpenInt",
        "O", "H", "L", "C", "V", "OI", "Average", "A",
        "RSI", "MACD", "MA", "EMA", "SMA", "WMA", "ATR", "ADX",
        "Filter", "PositionSize", "PositionScore",
    })

    # ── Pre-compiled regex patterns (built once at class definition) ──────────
    #
    # FIX (STYLE): the type hint now has an inline comment making it clear that
    # each value is a (match_pattern, replacement_template) pair, not two patterns.
    _SINGLE_ARG_PATTERNS: Dict[str, Tuple[re.Pattern, str]] = {
        # (pattern_to_match,  backreference replacement template)
        func: (
            re.compile(rf'{func}\s*\(\s*Close\s*,\s*(\w+)\s*\)'),
            rf'{func}(\1)',
        )
        for func in SINGLE_ARG_FUNCTIONS
    }

    _DOUBLE_ARG_PATTERNS: Dict[str, re.Pattern] = {
        func: re.compile(rf'{func}\s*\(\s*(\d+)\s*\)')
        for func in DOUBLE_ARG_FUNCTIONS
    }

    # FIX-01: Patterns to detect OBV being called with any argument(s)
    _NO_ARG_PATTERNS: Dict[str, re.Pattern] = {
        func: re.compile(rf'{func}\s*\(\s*\S')
        for func in NO_ARG_FUNCTIONS
    }

    _RESERVED_WORD_PATTERNS: Dict[str, re.Pattern] = {
        word: re.compile(rf'\b{word}\s*=\s*[^=]')
        for word in RESERVED_WORDS
    }

    # Tokens whose presence in generated code earns a quality bonus
    _QUALITY_BONUS_TOKENS = ("_SECTION_BEGIN", "ExRem", "SetTradeDelays", "Param(", "Plot(")

    # ── Unified training cache — key → (context_string, timestamp) ───────────
    # FIX #5: previously two separate dicts (_training_cache + _training_cache_time).
    # Unified into one dict so every cache operation is a single lookup / write.
    _training_cache: Dict[str, Tuple[str, float]] = {}
    _TRAINING_CACHE_TTL = 3600  # 1 hour

    # FIX #2: the lock is NOT created here at class definition time.
    # It is created lazily by _get_training_cache_lock() on first use.
    # This avoids binding to the wrong event loop before Python 3.10.
    _training_cache_lock: Optional[asyncio.Lock] = None

    # ── Constructor ───────────────────────────────────────────────────────────

    def __init__(
        self,
        api_key: Optional[str] = None,
        model:   Optional[str] = None,
    ):
        self.api_key = api_key
        self.model   = model or DEFAULT_MODEL
        self.client: Optional[anthropic.AsyncAnthropic] = None

        # Eagerly create the client if we already have a key
        if self.api_key:
            self._init_client()

    def _init_client(self) -> None:
        """Instantiate the Anthropic async client."""
        self.client = anthropic.AsyncAnthropic(api_key=self.api_key)

    def _ensure_client(self) -> None:
        """Raise ValueError if no client exists; create one lazily if possible."""
        if self.client is None:
            if not self.api_key:
                raise ValueError("No API key provided — cannot create Anthropic client")
            self._init_client()

    # ── Lazy lock accessor (FIX #2) ───────────────────────────────────────────

    @classmethod
    def _get_training_cache_lock(cls) -> asyncio.Lock:
        """
        Return the class-level asyncio.Lock, creating it on first call.

        FIX #2: creating asyncio.Lock() at class definition time can bind it to
        the wrong (or non-existent) event loop before Python 3.10.  Creating it
        lazily inside an async context is safe on all supported Python versions.
        """
        if cls._training_cache_lock is None:
            cls._training_cache_lock = asyncio.Lock()
        return cls._training_cache_lock

    # =========================================================================
    # Central Claude API call helper
    # =========================================================================

    async def _call_claude(
        self,
        system:     str,
        messages:   List[Dict],
        max_tokens: int  = MAX_TOKENS,
        stream:     bool = False,
        use_skill:  bool = True,
    ):
        """
        Single entry point for all Claude API calls.

        Returns
        ───────
        • stream=False → plain text string extracted from the response
        • stream=True  → async generator yielding {"type": ..., "content": ...} dicts

        FIX-13: Added ``use_skill`` parameter (default True).  When False, the
        skills beta headers, container, and code execution tool are NOT attached.
        This prevents explain/debug/chat calls from spinning up a skill container
        unnecessarily, saving ~1–3 seconds of latency and reducing API cost.
        Only generate_afl() passes use_skill=True.

        FIX #8: previously had two identical except branches (APIError + Exception)
        both doing log + re-raise.  Collapsed into one except block.
        """
        self._ensure_client()

        kwargs = {
            "model":     self.model,
            "max_tokens": max_tokens,
            "system":    system,
            "messages":  messages,
        }

        # FIX-13: Only attach skills infrastructure when actually generating AFL
        if use_skill:
            kwargs["betas"]     = SKILLS_BETAS
            kwargs["container"] = SKILLS_CONTAINER
            kwargs["tools"]     = [CODE_EXECUTION_TOOL]

        try:
            if stream:
                # FIX #1 (original):  _stream_wrapper is an async generator function,
                # so we CALL it (no await) to get the generator object back.
                return self._stream_wrapper(**kwargs)

            # Non-streaming path: await the coroutine and extract text
            if use_skill:
                response = await self.client.beta.messages.create(**kwargs)
            else:
                # Non-skill calls use the standard (non-beta) API
                standard_kwargs = {k: v for k, v in kwargs.items()
                                   if k not in ("betas", "container", "tools")}
                response = await self.client.messages.create(**standard_kwargs)

            # Log token usage when the API exposes it (useful for cost tracking)
            usage = getattr(response, "usage", None)
            if usage:
                logger.info(
                    "Claude usage: input=%d, output=%d, total=%d",
                    usage.input_tokens,
                    usage.output_tokens,
                    usage.input_tokens + usage.output_tokens,
                )

            return self._extract_text_from_response(response)

        except Exception as e:
            # FIX #8: single handler covers both anthropic.APIError and anything else.
            logger.error("Claude API error: %s\n%s", e, traceback.format_exc())
            raise

    async def _stream_wrapper(self, **kwargs):
        """
        Async generator that wraps stream_claude_response and yields uniform dicts.

        Yields
        ──────
        {"type": "chunk",    "content": <new_text>,   "full_content": <all_text_so_far>}
        {"type": "complete", "full_content": <all_text>}
        {"type": "error",    "error": <message>}   — on exception
        """
        accumulated = ""
        try:
            async for chunk in stream_claude_response(**kwargs):
                accumulated += chunk
                yield {"type": "chunk", "content": chunk, "full_content": accumulated}

            # Sentinel that signals the stream is fully consumed
            yield {"type": "complete", "full_content": accumulated}

        except Exception as e:
            logger.error("Streaming error: %s", e)
            yield {"type": "error", "error": str(e)}

    def _extract_text_from_response(self, response) -> str:
        """Join all text blocks from a non-streaming response into a single string."""
        return "\n".join(
            block.text for block in response.content if hasattr(block, "text")
        )

    # =========================================================================
    # Response parsing
    # =========================================================================

    def _parse_response(self, text: str) -> Tuple[str, str]:
        """
        Extract the first fenced code block and the surrounding explanation.

        FIX #6: the previous version only handled "afl" and "c" language tags.
        Any other tag (e.g. "python", "js") would be left as a literal prefix
        in the returned code string.  Now uses _LANG_TAG_RE to strip *any*
        optional language identifier at the top of the block.

        Returns
        ───────
        (code, explanation) — either part may be an empty string.
        """
        if "```" not in text:
            # No code fence at all — treat the whole response as explanation
            return "", text.strip()

        parts       = text.split("```")
        code        = ""
        explanation = []

        for i, part in enumerate(parts):
            if i % 2 == 1:
                # ── Inside a code fence ──────────────────────────────────────
                if not code:
                    # Only capture the FIRST code block
                    stripped = part.strip()
                    # Strip the optional language tag (e.g. "afl\n", "python\n")
                    # using the module-level compiled regex — no re-compile overhead.
                    code = _LANG_TAG_RE.sub("", stripped, count=1).strip()
            else:
                # ── Outside a code fence (narrative text) ────────────────────
                if clean := part.strip():
                    explanation.append(clean)

        return code, "\n".join(explanation)

    # =========================================================================
    # Prompt building helpers
    # =========================================================================

    def _build_system_prompt(
        self,
        base:         str,
        training:     str                       = "",
        user_answers: Optional[Dict[str, str]] = None,
        kb:           str                       = "",
        settings:     Optional[BacktestSettings] = None,
    ) -> str:
        """
        Assemble the system prompt from its component sections.

        Each section is only included when it has non-empty content, so the
        prompt stays as short as possible when optional context is absent.
        """
        parts = [base.strip()]

        if training:
            parts.append(f"\n\nLEARNED RULES (admin corrections — apply these):\n{training}")

        if user_answers:
            parts.append(f"\n\n{self._format_user_answers(user_answers)}")

        if kb:
            parts.append(f"\n\nKB CONTEXT:\n{kb}")

        if settings:
            parts.append(f"\n\nBACKTEST SETTINGS:\n{settings.to_afl()}")

        return "".join(parts)

    def _format_user_answers(self, answers: Dict[str, str]) -> str:
        """
        Convert the user's strategy-configuration answers into a prompt section.

        FIX #7: previous version used answers.get('strategy_type') with no fallback,
        so a missing key would render the literal string "None" into the prompt.
        Every .get() call now has an explicit fallback of 'Not specified'.
        """
        # Use lowercase copies for logic branching only; display uses originals
        st = answers.get("strategy_type", "Not specified").lower()
        tt = answers.get("trade_timing",  "Not specified").lower()

        # ── Determine trade timing ────────────────────────────────────────────
        if "close" in tt:
            delays     = "SetTradeDelays(0, 0, 0, 0)"
            timing_txt = "Trade on bar CLOSE"
        elif "open" in tt:
            delays     = "SetTradeDelays(1, 1, 1, 1)"
            timing_txt = "Trade on next bar OPEN"
        else:
            delays     = "SetTradeDelays(0, 0, 0, 0)"
            timing_txt = "Default timing"

        # ── Determine strategy structure ──────────────────────────────────────
        if "standalone" in st:
            structure = "STANDALONE - Complete strategy with all sections"
        elif "composite" in st:
            structure = "COMPOSITE - Only strategy logic"
        else:
            structure = "STANDALONE (default)"

        # FIX #7: both display values now have explicit 'Not specified' fallbacks
        return (
            f"## USER'S MANDATORY ANSWERS:\n\n"
            f"**Strategy Type:** {answers.get('strategy_type', 'Not specified')}\n"
            f"→ {structure}\n\n"
            f"**Trade Timing:** {answers.get('trade_timing', 'Not specified')}\n"
            f"→ {timing_txt}\n"
            f"→ CODE: {delays}\n\n"
            f"⚠️ CRITICAL: Implement according to these specifications."
        )

    # =========================================================================
    # Public API
    # =========================================================================

    async def generate_afl(
        self,
        request:              str,
        settings:             Optional[BacktestSettings]  = None,
        kb_context:           str                         = "",
        conversation_history: Optional[List[Dict]]        = None,
        user_answers:         Optional[Dict[str, str]]   = None,
        include_training:     bool                        = True,
        stream:               bool                        = False,
    ) -> Any:  # Dict on stream=False, async generator on stream=True
        """
        Main AFL generation entry point.

        Parameters
        ──────────
        request              : Natural-language description of the strategy
        settings             : Optional BacktestSettings to embed in the prompt
        kb_context           : Knowledge-base snippet to include
        conversation_history : Prior turns for multi-turn context
        user_answers         : Answers from the strategy-configuration wizard
        include_training     : Whether to fetch and inject training examples
        stream               : If True, returns an async generator of chunk dicts

        FIX #1: the streaming branch now correctly returns the generator produced
        by `await self._call_claude(..., stream=True)`.  Previously this was missing
        the `await`, so the branch returned a coroutine object — callers iterating
        over it would get a TypeError.

        FIX #3 / #4: the cache key now includes self.model AND an MD5 hash of the
        full kb_context string (not just the first 200 chars).
        """
        if len(request) > 8_000:
            raise ValueError("Request too long (>8000 chars) — please shorten your description")

        start = time.time()

        # ── Build a collision-resistant cache key ─────────────────────────────
        # FIX #3: include self.model so Sonnet and Opus never share entries.
        # FIX #4: hash the FULL kb_context instead of truncating to 200 chars.
        kb_hash = hashlib.md5(kb_context.encode()).hexdigest() if kb_context else ""
        cache_key = "|".join([
            self.model,           # FIX #3 — model-specific cache
            request,
            str(settings),
            kb_hash,              # FIX #4 — full hash, no truncation collision
            str(user_answers),
            str(include_training),
        ])

        # ── Cache look-up ──────────────────────────────────────────────────────
        if cache_key in self._request_cache:
            cached = self._request_cache[cache_key]
            # Move to end to keep LRU order correct
            self._request_cache.move_to_end(cache_key)
            logger.debug("Request cache hit")

            if stream:
                # Wrap the cached result in a generator so the caller always gets
                # the same async-generator interface regardless of cache hit/miss.
                async def _replay_cached():
                    yield {"type": "complete", **cached}
                return _replay_cached()

            return cached

        # ── Build system prompt ────────────────────────────────────────────────
        training_text = ""
        if include_training:
            raw_training = await self._get_training_context()
            if raw_training:
                training_text = truncate_context(raw_training, max_tokens=800)

        kb_trunc = truncate_context(kb_context, max_tokens=600) if kb_context else ""

        system = self._build_system_prompt(
            base=(
                "Generate high-quality AFL code for AmiBroker. "
                "Follow best practices, use proper syntax, include comments. "
                "If important details are missing, ask clarifying questions."
            ),
            training=training_text,
            user_answers=user_answers,
            kb=kb_trunc,
            settings=settings,
        )

        # ── Assemble messages (cap history to MAX_RECENT_MESSAGES) ────────────
        messages = []
        if conversation_history:
            messages.extend(conversation_history[-MAX_RECENT_MESSAGES:])
        messages.append({"role": "user", "content": f"Generate AFL code for: {request}"})

        # ── Dispatch to Claude ─────────────────────────────────────────────────
        try:
            if stream:
                # FIX #1: _call_claude is async, so we MUST await it to get the
                # generator back.  Without await, we would return a coroutine object.
                return await self._call_claude(system, messages, stream=True)

            # Non-streaming: get text, parse, validate, score
            raw       = await self._call_claude(system, messages)
            code, explanation = self._parse_response(raw)
            code, errors, warnings = self._validate_and_fix(code)
            quality   = self._calculate_quality(code, errors, warnings)
            elapsed   = time.time() - start

            result = {
                "afl_code":    code,
                "explanation": explanation,
                "stats": {
                    "quality_score":     quality,
                    "generation_time":   f"{elapsed:.2f}s",
                    "errors_fixed":      errors,
                    "warnings":          warnings,
                },
            }

            # ── Write to LRU cache ─────────────────────────────────────────────
            self._request_cache[cache_key] = result
            if len(self._request_cache) > self._request_cache_maxsize:
                # Evict the least-recently-used entry
                self._request_cache.popitem(last=False)

            return result

        except Exception as e:
            logger.error("generate_afl failed: %s", e)
            return {
                "afl_code":    "",
                "explanation": "",
                "error":       str(e),
                "stats": {
                    "quality_score":   0,
                    "generation_time": "0s",
                    "errors_fixed":    [],
                    "warnings":        [str(e)],
                },
            }

    async def debug_code(self, code: str, error_message: str = "") -> str:
        """Ask Claude to debug and fix AFL code, optionally with an error message."""
        prompt = f"Debug and fix this AFL code:\n\n```afl\n{code}\n```"
        if error_message:
            prompt += f"\n\nAmiBroker error: {error_message}"

        raw = await self._call_claude(
            system="You are an expert AFL debugger. Fix syntax and logic issues. Return corrected code only in ```afl block.",
            messages=[{"role": "user", "content": prompt}],
            use_skill=False,
        )
        code_out, _ = self._parse_response(raw)
        return code_out

    async def optimize_code(self, code: str) -> str:
        """Ask Claude to improve AFL code for speed, readability, and correctness."""
        prompt = f"Optimize this AFL code for speed, readability and correctness:\n\n```afl\n{code}\n```"

        raw = await self._call_claude(
            system="You are an AFL optimization expert. Improve performance and style. Return improved code only in ```afl block.",
            messages=[{"role": "user", "content": prompt}],
            use_skill=False,
        )
        code_out, _ = self._parse_response(raw)
        return code_out

    async def explain_code(self, code: str) -> str:
        """Return a plain-English explanation of an AFL strategy for traders."""
        prompt = (
            "Explain this AFL strategy in plain English for traders. "
            "Cover: purpose, indicators, entry/exit logic, parameters."
            f"\n\n```afl\n{code}\n```"
        )
        return await self._call_claude(
            system="Explain AFL code clearly and concisely for non-programmers.",
            messages=[{"role": "user", "content": prompt}],
            use_skill=False,
        )

    async def chat(
        self,
        message: str,
        history: Optional[List[Dict]] = None,
        context: str                  = "",
        stream:  bool                 = False,
    ) -> Any:
        """
        General-purpose AFL/AmiBroker chat.

        Returns a string (stream=False) or an async generator (stream=True).
        """
        kb = truncate_context(context, max_tokens=600) if context else ""

        system = self._build_system_prompt(
            base=(
                "You are an expert AFL / AmiBroker / quantitative trading assistant. "
                "Answer clearly, write correct code when asked, explain concepts."
            ),
            kb=kb,
        )

        messages = []
        if history:
            messages.extend(history[-MAX_RECENT_MESSAGES:])
        messages.append({"role": "user", "content": message})

        return await self._call_claude(system, messages, stream=stream, use_skill=False)

    async def stream_chat(
        self,
        message:    str,
        system:     str,
        tools:      Optional[List[Dict]] = None,
        max_tokens: int = 3000,
        messages:   Optional[List[Dict]] = None,
    ):
        """
        Async generator: streams chat response in Vercel AI SDK Data Stream Protocol.

        This is what /chat/stream calls.  Uses the REGULAR (non-beta) Anthropic
        API with custom tools — NOT the beta/skills endpoint.  Skills are not
        needed for general chat; the tool-use loop is handled by stream_claude_response.

        Yields
        ──────
        Strings in Vercel AI SDK Data Stream Protocol format:
          "0:\"text delta\"\\n"  — text chunk
          "9:{...}\\n"           — tool call
          "a:{...}\\n"           — tool result
          "d:{...}\\n"           — finish message
        """
        self._ensure_client()

        # Build the full messages list including current user message
        all_messages = list(messages or [])
        if message:
            all_messages.append({"role": "user", "content": message})

        # Use the REGULAR (non-beta) API — stream_claude_response handles tool loops
        async for chunk in stream_claude_response(
            client=self.client,
            model=self.model,
            system_prompt=system,
            messages=all_messages,
            tools=tools,
            max_tokens=max_tokens,
        ):
            yield chunk

    # =========================================================================
    # Validation & Quality
    # =========================================================================

    def validate_code(self, code: str) -> Dict[str, Any]:
        """Public validation interface — does NOT auto-fix, just reports issues."""
        _, errs, warns = self._validate_and_fix(code, fix=False)
        return {"is_valid": not errs, "errors": errs, "warnings": warns}

    def _validate_and_fix(
        self,
        code: str,
        fix:  bool = True,
    ) -> Tuple[str, List[str], List[str]]:
        """
        Check the generated AFL for common mistakes.

        When fix=True (default), patches are applied in-place and recorded as
        errors so the caller knows what was changed.  When fix=False (validate-only
        mode) issues are reported but the code is returned unchanged.

        Checks performed
        ────────────────
        1. Single-argument functions incorrectly called with (Close, period)
        2. Double-argument functions called with only one numeric argument
        3. Missing ExRem() when both Buy and Sell signals are present
        4. Assignment to AFL reserved words
        5. Missing _SECTION_BEGIN / _SECTION_END structural markers
        """
        errors   = []
        warnings = []

        # ── 1. Fix single-arg misuse: RSI(Close, 14) → RSI(14) ───────────────
        for func, (pat, repl) in self._SINGLE_ARG_PATTERNS.items():
            if pat.search(code):
                if fix:
                    code = pat.sub(repl, code)
                    errors.append(f"Fixed: {func}(Close, x) → {func}(x)")
                else:
                    errors.append(f"{func}() misused with Close as first argument")

        # ── 1b. Warn on no-arg functions called with arguments: OBV(n) ─────────
        for func, pat in self._NO_ARG_PATTERNS.items():
            if pat.search(code):
                warnings.append(
                    f"{func}() takes NO arguments — found {func}(…). "
                    f"Correct usage: {func}()"
                )

        # ── 2. Warn on double-arg functions missing their array argument ───────
        for func, pat in self._DOUBLE_ARG_PATTERNS.items():
            if pat.search(code):
                warnings.append(f"{func}() possibly missing array argument")

        # ── 3. Suggest ExRem() to eliminate duplicate back-to-back signals ─────
        if "Buy" in code and "Sell" in code and "ExRem" not in code:
            warnings.append("Consider adding ExRem() to remove duplicate signals")

        # ── 4. Warn on assignments to AFL reserved words ─────────────────────
        for word, pat in self._RESERVED_WORD_PATTERNS.items():
            if pat.search(code):
                warnings.append(
                    f"Reserved word '{word}' used as variable name — consider renaming"
                )

        # ── 5. Check for structural section markers ───────────────────────────
        if "_SECTION_BEGIN" not in code:
            warnings.append("Missing _SECTION_BEGIN / _SECTION_END structural markers")

        return code, errors, warnings

    def _calculate_quality(
        self,
        code:     str,
        errors:   List[str],
        warnings: List[str],
    ) -> float:
        """
        Return a quality score in [0.0, 1.0].

        Scoring rules
        ─────────────
        • Start at 1.0
        • Deduct 0.10 per error (auto-fixed issues)
        • Deduct 0.05 per warning
        • Add 0.05 for each quality-bonus token present
        • Clamp to [0.0, 1.0]
        """
        score = 1.0 - len(errors) * 0.10 - len(warnings) * 0.05
        for token in self._QUALITY_BONUS_TOKENS:
            if token in code:
                score += 0.05
        return max(0.0, min(1.0, score))

    # =========================================================================
    # Training context with cache stampede protection
    # =========================================================================

    async def _get_training_context(
        self,
        category: str = "afl",
        limit:    int = 5,
    ) -> str:
        """
        Fetch and cache training examples from the training manager.

        Uses double-checked locking to prevent a cache stampede when multiple
        coroutines simultaneously detect a stale / missing cache entry.

        FIX #5: unified _training_cache dict — key → (value, timestamp) — replaces
        the previous two parallel dicts (_training_cache + _training_cache_time).
        Every cache operation is now a single dict lookup instead of two.
        """
        if not TRAINING_ENABLED or get_training_manager is None:
            return ""  # Training subsystem not available

        key = f"{category}_{limit}"
        now = time.time()

        # ── Fast path: check cache WITHOUT acquiring the lock ─────────────────
        entry = self._training_cache.get(key)
        if entry is not None:
            cached_value, cached_ts = entry  # FIX #5: single tuple unpack
            if now - cached_ts < self._TRAINING_CACHE_TTL:
                return cached_value

        # ── Slow path: acquire lock, then re-check (double-checked locking) ───
        # FIX #2: lock is created lazily to avoid pre-Python-3.10 issues
        lock = self._get_training_cache_lock()
        async with lock:
            # Re-check inside the lock in case another coroutine already refreshed
            entry = self._training_cache.get(key)
            if entry is not None:
                cached_value, cached_ts = entry  # FIX #5
                if now - cached_ts < self._TRAINING_CACHE_TTL:
                    return cached_value

            try:
                mgr = get_training_manager()
                ctx = mgr.get_training_context(category=category, limit=limit)
                if ctx:
                    # FIX #5: store (value, timestamp) in a single dict entry
                    self._training_cache[key] = (ctx, time.time())
                    return ctx
                return ""
            except Exception as e:
                logger.warning("Training context load failed: %s", e)
                return ""

    # =========================================================================
    # Cache management (class methods for external tooling / tests)
    # =========================================================================

    @classmethod
    def clear_training_cache(cls) -> None:
        """Wipe the training context cache (useful after admin updates)."""
        cls._training_cache.clear()
        logger.info("Training cache cleared")

    @classmethod
    def clear_request_cache(cls) -> None:
        """Wipe the AFL generation result cache."""
        cls._request_cache.clear()
        logger.info("Request result cache cleared")