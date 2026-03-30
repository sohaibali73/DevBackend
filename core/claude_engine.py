"""
Claude AFL Engine - Core AFL code generation using Claude API.

COMPREHENSIVE REWRITE - All critical issues resolved:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL FIX 1  — Logger initialization order: logger was used before being defined,
                  causing NameError in fallback scenario. Fixed: logger defined at
                  module top before any code that uses it.

CRITICAL FIX 2  — stream_claude_response parameter mismatch: _stream_wrapper passed
                  kwargs with key "system" but stream_claude_response expects "system_prompt".
                  Fixed: proper parameter mapping in _stream_wrapper.

CRITICAL FIX 3  — Import fallback error handling: fallback prompt functions were
                  defined inside try/except before logger existed. Fixed: proper ordering
                  with logger first, then imports with fallbacks.

PREVIOUS FIXES (carried forward from original):
- BUG FIX 1: generate_afl stream path now correctly awaits _call_claude
- BUG FIX 2: asyncio.Lock created lazily to avoid event loop binding issues
- BUG FIX 3: model included in cache key to prevent cross-model collisions
- BUG FIX 4: MD5 hash of full kb_context prevents truncation collisions
- BUG FIX 5: unified training cache dict (key → (value, timestamp))
- BUG FIX 6: generic language-tag stripper via compiled regex
- BUG FIX 7: explicit 'Not specified' fallback on all answers.get() calls
- BUG FIX 8: collapsed duplicate exception handlers
"""

import re
import asyncio
import hashlib
import time
import logging
import traceback
from typing import Dict, Any, Optional, List, Tuple, Union
from dataclasses import dataclass
from collections import OrderedDict
from enum import Enum

import anthropic

# Initialize logger FIRST before any code that might use it
logger = logging.getLogger(__name__)

# Single source of truth for skills / streaming configuration
from core.skills import SKILLS_BETAS, CODE_EXECUTION_TOOL
from core.context_manager import truncate_context, MAX_RECENT_MESSAGES
from core.streaming import stream_claude_response

# Import the AFL system prompt builders from core/prompts/afl.py.
# Fallbacks kept so a wrong path never crashes all routers at startup.
try:
    from core.prompts.afl import get_base_prompt, get_chat_prompt
    _AFL_IMPORT_SOURCE = "core.prompts.afl"
except ImportError:
    try:
        from routes.afl import get_base_prompt, get_chat_prompt
        _AFL_IMPORT_SOURCE = "routes.afl"
    except ImportError:
        try:
            from afl import get_base_prompt, get_chat_prompt
            _AFL_IMPORT_SOURCE = "afl"
        except ImportError:
            _AFL_IMPORT_SOURCE = "inline-fallback"
            logger.warning(
                "afl.py not found at 'core.prompts.afl', 'routes.afl', or 'afl' — "
                "using minimal inline prompts. Deploy afl.py to fix this."
            )
            def get_base_prompt() -> str:
                return (
                    "You are an expert AmiBroker Formula Language (AFL) developer.\n"
                    "CRITICAL RULES:\n"
                    "- RSI(14) not RSI(Close,14). MA(Close,20) not MA(20). OBV() no args.\n"
                    "- Never shadow built-ins: use RSI_Val not RSI, MALength not MA.\n"
                    "- Always ExRem(Buy,Sell) and ExRem(Sell,Buy).\n"
                    "- RAG Param pattern: varDefault/Min/Max/Step → Var_Dflt=Param() → Var=Optimize().\n"
                    "- CommissionMode 2 only (0.0005). Never mode 3.\n"
                    "- ParamToggle needs 3 args: ParamToggle('x','No|Yes',0).\n"
                    "- Never GetBacktesterObject(). Never if(Status('mode')==1).\n"
                    "- _SECTION_BEGIN/_SECTION_END for all sections.\n"
                    "- Use colorViolet not colorPurple (colorPurple does not exist).\n"
                )
            def get_chat_prompt() -> str:
                return (
                    "You are an expert AFL/AmiBroker assistant. "
                    "Write correct AFL code following all syntax rules. "
                    "RSI(14) not RSI(Close,14). MA(Close,20) not MA(20). "
                    "Always use ExRem() and Param()/Optimize() patterns."
                )

# Training manager is optional — gracefully degraded if the module is absent
try:
    from core.training import get_training_manager
    TRAINING_ENABLED = True
except ImportError:
    TRAINING_ENABLED = False
    get_training_manager = None

# Comprehensive AFL validator — used for post-generation validation
try:
    from core.afl_validator import AFLValidator, validate_afl_code, fix_afl_code
    AFL_VALIDATOR_AVAILABLE = True
except ImportError:
    AFL_VALIDATOR_AVAILABLE = False
    logger.warning("core.afl_validator not available — using basic inline validation only")

# ── Strategy type enumeration ─────────────────────────────────────────────────
class StrategyType(str, Enum):
    """Strategy type for AFL generation (affects code structure)."""
    STANDALONE = "standalone"  # Complete strategy with all sections
    COMPOSITE = "composite"    # Only strategy logic (no plotting/settings)

class ClaudeModel(str, Enum):
    """Available Claude models for AFL generation."""
    OPUS_4 = "claude-opus-4-6"
    SONNET_4 = "claude-sonnet-4-6"
    HAIKU_4 = "claude-haiku-4-5-20251001"

    @classmethod
    def from_string(cls, model_str: str) -> "ClaudeModel":
        normalized = model_str.lower().strip()
        for model in cls:
            if model.value == model_str:
                return model
        if "opus" in normalized:
            return cls.OPUS_4
        elif "haiku" in normalized:
            return cls.HAIKU_4
        return cls.SONNET_4

    @classmethod
    def supports_extended_thinking(cls, model: "ClaudeModel") -> bool:
        return model in (cls.OPUS_4, cls.SONNET_4)

class ThinkingMode(str, Enum):
    DISABLED = "disabled"
    ENABLED = "enabled"

@dataclass
class ThinkingConfig:
    mode: ThinkingMode = ThinkingMode.DISABLED
    budget_tokens: Optional[int] = None

    def to_api_params(self) -> Optional[Dict[str, Any]]:
        if self.mode == ThinkingMode.DISABLED:
            return None
        params = {"type": "enabled"}
        if self.budget_tokens is not None:
            params["budget_tokens"] = self.budget_tokens
        return params

# ── Top-level defaults ────────────────────────────────────────────────────────
DEFAULT_MODEL       = ClaudeModel.SONNET_4
MAX_TOKENS          = 8192
AMIBROKER_SKILL_ID  = "skill_01GG6E88EuXr9H9tqLp51sH5"

SKILLS_CONTAINER = {
    "skills": [{"skill_id": AMIBROKER_SKILL_ID, "type": "custom"}]
}

# ── Module-level regex for stripping code-fence language tags ─────────────────
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
    commission:        float              = 0.0005   # 0.05% per trade
    trade_delays:      Tuple[int, int, int, int] = (0, 0, 0, 0)
    margin_requirement: float             = 100

    def to_afl(self) -> str:
        """Return AFL code that encodes these settings."""
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
    • asyncio.Lock is created lazily to avoid event loop binding issues.
    """

    # ── Class-level LRU result cache (shared across instances) ───────────────
    _request_cache: OrderedDict = OrderedDict()
    _request_cache_maxsize      = 128

    # ── AFL validation sets (frozensets for O(1) membership tests) ────────────
    SINGLE_ARG_FUNCTIONS = frozenset({
        "RSI", "ATR", "ADX", "CCI", "MFI", "PDI", "MDI",
        "StochK", "StochD",
    })

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

    # ── Pre-compiled regex patterns ───────────────────────────────────────────
    _SINGLE_ARG_PATTERNS: Dict[str, Tuple[re.Pattern, str]] = {
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

    _NO_ARG_PATTERNS: Dict[str, re.Pattern] = {
        func: re.compile(rf'{func}\s*\(\s*\S')
        for func in NO_ARG_FUNCTIONS
    }

    _RESERVED_WORD_PATTERNS: Dict[str, re.Pattern] = {
        word: re.compile(rf'\b{word}\s*=\s*[^=]')
        for word in RESERVED_WORDS
    }

    _QUALITY_BONUS_TOKENS = ("_SECTION_BEGIN", "ExRem", "SetTradeDelays", "Param(", "Plot(")

    # ── Unified training cache ────────────────────────────────────────────────
    _training_cache: Dict[str, Tuple[str, float]] = {}
    _TRAINING_CACHE_TTL = 3600  # 1 hour
    _training_cache_lock: Optional[asyncio.Lock] = None

    # ── Constructor ───────────────────────────────────────────────────────────

    def __init__(
        self,
        api_key: Optional[str] = None,
        model:   Optional[Union[str, ClaudeModel]] = None,
        thinking_config: Optional[ThinkingConfig] = None,
    ):
        self.api_key = api_key

        # Normalize model to string value
        if model is None:
            self.model = DEFAULT_MODEL.value
        elif isinstance(model, ClaudeModel):
            self.model = model.value
        elif isinstance(model, str):
            self.model = ClaudeModel.from_string(model).value
        else:
            logger.warning(f"Invalid model type {type(model)}, using default")
            self.model = DEFAULT_MODEL.value

        # Store and validate thinking config
        self.thinking_config = thinking_config or ThinkingConfig(mode=ThinkingMode.DISABLED)
        model_enum = ClaudeModel.from_string(self.model)
        if (self.thinking_config.mode != ThinkingMode.DISABLED and
            not ClaudeModel.supports_extended_thinking(model_enum)):
            logger.warning(f"{self.model} does not support extended thinking. Disabling.")
            self.thinking_config = ThinkingConfig(mode=ThinkingMode.DISABLED)

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

    # ── Lazy lock accessor ────────────────────────────────────────────────────

    @classmethod
    def _get_training_cache_lock(cls) -> asyncio.Lock:
        """
        Return the class-level asyncio.Lock, creating it on first call.
        Creating asyncio.Lock() at class definition time can bind it to
        the wrong event loop before Python 3.10.
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
        enable_thinking: Optional[bool] = None,
    ):
        """
        Single entry point for all Claude API calls.

        Returns
        ───────
        • stream=False → plain text string extracted from the response
        • stream=True  → async generator yielding {"type": ..., "content": ...} dicts
        """
        self._ensure_client()

        kwargs = {
            "model":     self.model,
            "max_tokens": max_tokens,
            "system":    system,
            "messages":  messages,
        }

        # Add extended thinking if enabled
        # Per Anthropic docs: "Extended thinking can be used alongside tool use"
        # Works with both beta.messages.create() and messages.create()
        thinking_enabled = (
            enable_thinking if enable_thinking is not None
            else self.thinking_config.mode != ThinkingMode.DISABLED
        )

        if thinking_enabled:
            thinking_params = self.thinking_config.to_api_params()
            if thinking_params:
                kwargs["thinking"] = thinking_params

        # Only attach skills infrastructure when actually generating AFL
        if use_skill:
            kwargs["betas"]     = SKILLS_BETAS
            kwargs["container"] = SKILLS_CONTAINER
            kwargs["tools"]     = [CODE_EXECUTION_TOOL]

        try:
            if stream:
                # Return the generator directly (don't await)
                return self._stream_wrapper(**kwargs)

            # Non-streaming path: await the coroutine and extract text
            if use_skill:
                response = await self.client.beta.messages.create(**kwargs)
            else:
                # Non-skill calls use the standard (non-beta) API
                standard_kwargs = {k: v for k, v in kwargs.items()
                                   if k not in ("betas", "container", "tools")}
                response = await self.client.messages.create(**standard_kwargs)

            # Log token usage
            usage = getattr(response, "usage", None)
            if usage:
                thinking_tokens = getattr(usage, "thinking_tokens", 0)
                log_msg = (
                    f"Claude usage (model={self.model}): "
                    f"input={usage.input_tokens}, output={usage.output_tokens}"
                )
                if thinking_tokens > 0:
                    log_msg += f", thinking={thinking_tokens}"
                logger.info(log_msg)

            return self._extract_text_from_response(response)

        except Exception as e:
            logger.error("Claude API error: %s\n%s", e, traceback.format_exc())
            raise

    async def _stream_wrapper(self, **kwargs):
        """
        Async generator that wraps stream_claude_response and yields uniform dicts.

        CRITICAL FIX 2: Properly map parameters for stream_claude_response.

        Yields
        ──────
        {"type": "chunk",    "content": <new_text>,   "full_content": <all_text_so_far>}
        {"type": "complete", "full_content": <all_text>}
        {"type": "error",    "error": <message>}
        """
        accumulated = ""
        try:
            # CRITICAL FIX 2: Extract client from self, map system to system_prompt
            # stream_claude_response expects: client, model, system_prompt, messages, tools, max_tokens
            stream_kwargs = {
                "client": self.client,
                "model": kwargs.get("model"),
                "system_prompt": kwargs.get("system"),  # Map "system" to "system_prompt"
                "messages": kwargs.get("messages"),
                "tools": kwargs.get("tools"),
                "max_tokens": kwargs.get("max_tokens"),
            }

            # Remove None values
            stream_kwargs = {k: v for k, v in stream_kwargs.items() if v is not None}

            async for chunk in stream_claude_response(**stream_kwargs):
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
                # Inside a code fence
                if not code:
                    # Only capture the FIRST code block
                    stripped = part.strip()
                    # Strip the optional language tag
                    code = _LANG_TAG_RE.sub("", stripped, count=1).strip()
            else:
                # Outside a code fence (narrative text)
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
        """Assemble the system prompt from its component sections."""
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
        """Convert the user's strategy-configuration answers into a prompt section."""
        # Use lowercase copies for logic branching only; display uses originals
        st = answers.get("strategy_type", "Not specified").lower()
        tt = answers.get("trade_timing",  "Not specified").lower()

        # Determine trade timing
        if "close" in tt:
            delays     = "SetTradeDelays(0, 0, 0, 0)"
            timing_txt = "Trade on bar CLOSE"
        elif "open" in tt:
            delays     = "SetTradeDelays(1, 1, 1, 1)"
            timing_txt = "Trade on next bar OPEN"
        else:
            delays     = "SetTradeDelays(0, 0, 0, 0)"
            timing_txt = "Default timing"

        # Determine strategy structure
        if "standalone" in st:
            structure = "STANDALONE - Complete strategy with all sections"
        elif "composite" in st:
            structure = "COMPOSITE - Only strategy logic"
        else:
            structure = "STANDALONE (default)"

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
    ) -> Any:
        """
        Main AFL generation entry point.

        Returns Dict on stream=False, async generator on stream=True.
        """
        if len(request) > 8_000:
            raise ValueError("Request too long (>8000 chars) — please shorten your description")

        start = time.time()

        # Build cache key
        kb_hash = hashlib.md5(kb_context.encode()).hexdigest() if kb_context else ""
        cache_key = "|".join([
            self.model,
            request,
            str(settings),
            kb_hash,
            str(user_answers),
            str(include_training),
        ])

        # Cache look-up
        if cache_key in self._request_cache:
            cached = self._request_cache[cache_key]
            self._request_cache.move_to_end(cache_key)
            logger.debug("Request cache hit")

            if stream:
                async def _replay_cached():
                    yield {"type": "complete", **cached}
                return _replay_cached()

            return cached

        # Build system prompt
        training_text = ""
        if include_training:
            raw_training = await self._get_training_context()
            if raw_training:
                training_text = truncate_context(raw_training, max_tokens=800)

        kb_trunc = truncate_context(kb_context, max_tokens=600) if kb_context else ""

        system = self._build_system_prompt(
            base=get_base_prompt(),
            training=training_text,
            user_answers=user_answers,
            kb=kb_trunc,
            settings=settings,
        )

        # Assemble messages
        messages = []
        if conversation_history:
            messages.extend(conversation_history[-MAX_RECENT_MESSAGES:])
        messages.append({"role": "user", "content": f"Generate AFL code for: {request}"})

        # Dispatch to Claude
        try:
            if stream:
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

            # Add comprehensive validation details when available
            if AFL_VALIDATOR_AVAILABLE and code:
                try:
                    validation = validate_afl_code(code)
                    result["validation"] = {
                        "is_valid": validation.get("is_valid", True),
                        "errors": validation.get("errors", []),
                        "warnings": validation.get("warnings", []),
                        "color_issues": validation.get("color_issues", []),
                        "function_issues": validation.get("function_issues", []),
                        "reserved_word_issues": validation.get("reserved_word_issues", []),
                        "style_issues": validation.get("style_issues", []),
                        "suggestions": validation.get("suggestions", []),
                        "total_issues": validation.get("total_issues", 0),
                    }
                except Exception as e:
                    logger.warning(f"Failed to add validation details to result: {e}")

            # Write to LRU cache
            self._request_cache[cache_key] = result
            if len(self._request_cache) > self._request_cache_maxsize:
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
        """Ask Claude to debug and fix AFL code."""
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
        """Ask Claude to improve AFL code."""
        prompt = f"Optimize this AFL code for speed, readability and correctness:\n\n```afl\n{code}\n```"

        raw = await self._call_claude(
            system="You are an AFL optimization expert. Improve performance and style. Return improved code only in ```afl block.",
            messages=[{"role": "user", "content": prompt}],
            use_skill=False,
        )
        code_out, _ = self._parse_response(raw)
        return code_out

    async def explain_code(self, code: str) -> str:
        """Return a plain-English explanation of an AFL strategy."""
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
        """General-purpose AFL/AmiBroker chat — always uses the AFL generator skill."""
        kb = truncate_context(context, max_tokens=600) if context else ""

        system = self._build_system_prompt(
            base=get_chat_prompt(),
            kb=kb,
        )

        messages = []
        if history:
            messages.extend(history[-MAX_RECENT_MESSAGES:])
        messages.append({"role": "user", "content": message})

        # Always use the AFL skill so every chat benefits from the AmiBroker AFL Developer skill
        return await self._call_claude(system, messages, stream=stream, use_skill=True)

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

        Yields strings in format:
          "0:\"text delta\"\\n"  — text chunk
          "9:{...}\\n"           — tool call
          "a:{...}\\n"           — tool result
          "d:{...}\\n"           — finish message
        """
        self._ensure_client()

        # Build the full messages list
        all_messages = list(messages or [])
        if message:
            all_messages.append({"role": "user", "content": message})

        # Use stream_claude_response with proper parameter mapping
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
        """Public validation interface — uses comprehensive AFLValidator when available."""
        if AFL_VALIDATOR_AVAILABLE and code:
            try:
                return validate_afl_code(code)
            except Exception as e:
                logger.warning(f"Comprehensive validation failed in validate_code: {e}")

        # Fallback to basic validation
        _, errs, warns = self._validate_and_fix(code, fix=False)
        return {"is_valid": not errs, "errors": errs, "warnings": warns}

    def _validate_and_fix(
        self,
        code: str,
        fix:  bool = True,
    ) -> Tuple[str, List[str], List[str]]:
        """Check the generated AFL for common mistakes using comprehensive validator when available."""
        errors   = []
        warnings = []

        # Use comprehensive AFLValidator if available
        if AFL_VALIDATOR_AVAILABLE and code:
            try:
                if fix:
                    # Run auto-fix first, then validate the fixed code
                    fix_result = fix_afl_code(code)
                    code = fix_result.get("fixed_code", code)
                    fix_applied = fix_result.get("fixes_applied", [])
                    validation = fix_result.get("validation", {})
                else:
                    # Just validate without fixing
                    validation = validate_afl_code(code)
                    fix_applied = []

                # Collect errors and warnings from comprehensive validation
                if fix_applied:
                    errors.extend(fix_applied)
                errors.extend(validation.get("errors", []))
                errors.extend(validation.get("color_issues", []))
                errors.extend(validation.get("function_issues", []))
                errors.extend(validation.get("reserved_word_issues", []))
                warnings.extend(validation.get("warnings", []))
                warnings.extend(validation.get("style_issues", []))
                warnings.extend(validation.get("suggestions", []))

                return code, errors, warnings
            except Exception as e:
                logger.warning(f"Comprehensive validation failed, falling back to basic: {e}")
                # Fall through to basic validation

        # Basic inline validation fallback
        # Fix single-arg misuse
        for func, (pat, repl) in self._SINGLE_ARG_PATTERNS.items():
            if pat.search(code):
                if fix:
                    code = pat.sub(repl, code)
                    errors.append(f"Fixed: {func}(Close, x) → {func}(x)")
                else:
                    errors.append(f"{func}() misused with Close as first argument")

        # Warn on no-arg functions called with arguments
        for func, pat in self._NO_ARG_PATTERNS.items():
            if pat.search(code):
                warnings.append(
                    f"{func}() takes NO arguments — found {func}(…). "
                    f"Correct usage: {func}()"
                )

        # Warn on double-arg functions missing their array argument
        for func, pat in self._DOUBLE_ARG_PATTERNS.items():
            if pat.search(code):
                warnings.append(f"{func}() possibly missing array argument")

        # Suggest ExRem()
        if "Buy" in code and "Sell" in code and "ExRem" not in code:
            warnings.append("Consider adding ExRem() to remove duplicate signals")

        # Warn on assignments to AFL reserved words
        for word, pat in self._RESERVED_WORD_PATTERNS.items():
            if pat.search(code):
                warnings.append(
                    f"Reserved word '{word}' used as variable name — consider renaming"
                )

        # Check for structural section markers
        if "_SECTION_BEGIN" not in code:
            warnings.append("Missing _SECTION_BEGIN / _SECTION_END structural markers")

        return code, errors, warnings

    def _calculate_quality(
        self,
        code:     str,
        errors:   List[str],
        warnings: List[str],
    ) -> float:
        """Return a quality score in [0.0, 1.0]."""
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
        """Fetch and cache training examples from the training manager."""
        if not TRAINING_ENABLED or get_training_manager is None:
            return ""

        key = f"{category}_{limit}"
        now = time.time()

        # Fast path: check cache WITHOUT acquiring the lock
        entry = self._training_cache.get(key)
        if entry is not None:
            cached_value, cached_ts = entry
            if now - cached_ts < self._TRAINING_CACHE_TTL:
                return cached_value

        # Slow path: acquire lock, then re-check (double-checked locking)
        lock = self._get_training_cache_lock()
        async with lock:
            # Re-check inside the lock
            entry = self._training_cache.get(key)
            if entry is not None:
                cached_value, cached_ts = entry
                if now - cached_ts < self._TRAINING_CACHE_TTL:
                    return cached_value

            try:
                mgr = get_training_manager()
                ctx = mgr.get_training_context(category=category, limit=limit)
                if ctx:
                    self._training_cache[key] = (ctx, time.time())
                    return ctx
                return ""
            except Exception as e:
                logger.warning("Training context load failed: %s", e)
                return ""

    # =========================================================================
    # Cache management
    # =========================================================================

    @classmethod
    def clear_training_cache(cls) -> None:
        """Wipe the training context cache."""
        cls._training_cache.clear()
        logger.info("Training cache cleared")

    @classmethod
    def clear_request_cache(cls) -> None:
        """Wipe the AFL generation result cache."""
        cls._request_cache.clear()
        logger.info("Request result cache cleared")