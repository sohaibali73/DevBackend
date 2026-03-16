"""
Potomac Custom Beta Skills Registry
=====================================
Central registry of all Claude custom beta skills used by the platform.

Each skill is a custom skill created in the Claude Developer Portal.
Skills run inside the code execution container and require specific
beta headers to activate.

See: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/quickstart
"""

import logging
from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Beta headers required for ALL skill calls
# ---------------------------------------------------------------------------
SKILLS_BETAS: List[str] = [
    "code-execution-2025-08-25",   # Skills run in code execution container
    "skills-2025-10-02",           # Enables Skills functionality
]

# Code execution tool (required for Skills)
CODE_EXECUTION_TOOL: Dict[str, str] = {
    "type": "code_execution_20250825",
    "name": "code_execution",
}


# ---------------------------------------------------------------------------
# Skill category enum
# ---------------------------------------------------------------------------
class SkillCategory(str, Enum):
    """Categories for organizing skills."""
    AFL = "afl"
    DOCUMENT = "document"
    PRESENTATION = "presentation"
    UI = "ui"
    BACKTEST = "backtest"
    MARKET_ANALYSIS = "market_analysis"
    QUANT = "quant"
    RESEARCH = "research"


# ---------------------------------------------------------------------------
# Skill definition dataclass
# ---------------------------------------------------------------------------
@dataclass
class SkillDefinition:
    """A registered Claude custom beta skill."""
    skill_id: str
    name: str
    slug: str                       # URL-safe identifier (used in API routes)
    description: str
    category: SkillCategory
    system_prompt: str = ""          # Optional system prompt override
    max_tokens: int = 4096
    tags: List[str] = field(default_factory=list)
    enabled: bool = True
    # If True, the skill result is streamed back to the caller
    supports_streaming: bool = True

    def to_container(self) -> Dict[str, Any]:
        """Return the ``container`` param for ``client.beta.messages.create()``."""
        return {
            "skills": [
                {
                    "skill_id": self.skill_id,
                    "type": "custom",
                }
            ]
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for the REST API."""
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "category": self.category.value,
            "max_tokens": self.max_tokens,
            "tags": self.tags,
            "enabled": self.enabled,
            "supports_streaming": self.supports_streaming,
        }


# ---------------------------------------------------------------------------
# MASTER SKILL REGISTRY
# ---------------------------------------------------------------------------
# All custom beta skills are defined here.  Add new skills to this dict.

SKILL_REGISTRY: Dict[str, SkillDefinition] = {}


def _register(skill: SkillDefinition) -> SkillDefinition:
    """Register a skill in the global registry."""
    SKILL_REGISTRY[skill.slug] = skill
    return skill


# ── 1. AmiBroker AFL Developer (existing) ──────────────────────────────────
_register(SkillDefinition(
    skill_id="skill_01GG6E88EuXr9H9tqLp51sH5",
    name="AmiBroker AFL Developer",
    slug="amibroker-afl-developer",
    description=(
        "Expert AFL code generator for AmiBroker. Generates, debugs, optimizes, "
        "and explains AmiBroker Formula Language code from natural language."
    ),
    category=SkillCategory.AFL,
    # FIX-10: Replaced the generic "follow best practices" prompt with a precise
    # rule set that mirrors SKILL.md.  The old prompt mentioned nothing about
    # function signatures, variable naming, ExRem, or color constraints — so those
    # rules were only present in the skill's SKILL.md context, not the system
    # prompt that SkillGateway injects when calling the API directly.
    system_prompt=(
        "You are an expert AmiBroker AFL developer. Always follow these rules:\n\n"
        "FUNCTION SIGNATURES:\n"
        "- Single-arg: RSI(14), ATR(14), ADX(14), CCI(20), MFI(14) — NEVER RSI(Close, 14)\n"
        "- Double-arg: MA(Close, 20), EMA(Close, 20), HHV(High, 20) — NEVER MA(20)\n"
        "- OBV() takes NO arguments — NEVER OBV(14) or OBV(Close, 14)\n"
        "- ParamToggle needs 3 args: ParamToggle('name', 'No|Yes', 0) — 2nd arg MUST be a pipe-separated STRING\n"
        "- ParamList needs 3 args: ParamList('name', 'A|B|C', 0) — 2nd arg MUST be a pipe-separated STRING\n"
        "- Param needs 5 args: Param('name', default, min, max, step)\n"
        "- Optimize needs 5 args: Optimize('name', param_var, min, max, step)\n\n"
        "VARIABLE NAMING:\n"
        "- NEVER shadow built-in functions as variable names\n"
        "- Use RSI_Val not RSI; MALength not MA; RSIPeriod not RSI for param vars\n"
        "- Pattern for period params: RSIPeriod, MALength, ATRPeriod, ADXPeriod\n\n"
        "SIGNALS:\n"
        "- ALWAYS apply ExRem(Buy, Sell) and ExRem(Sell, Buy) after signal construction\n"
        "- Use _SECTION_BEGIN/_SECTION_END to structure all major code blocks\n\n"
        "PARAMETERS:\n"
        "- Every configurable value MUST use the RAG Param/Optimize pattern:\n"
        "  varDefault/Min/Max/Step → Variable_Dflt = Param(...) → Variable = Optimize(...)\n"
        "- Use Variable (not Variable_Dflt) in all formula logic\n\n"
        "COLORS:\n"
        "- Use official AmiBroker color constants by default (colorRed, colorGreen, etc.)\n"
        "- colorPurple does NOT exist — use colorViolet, colorPlum, or colorIndigo\n"
        "- Custom ColorRGB() allowed ONLY with a unique non-colliding variable name\n"
        "- NEVER assign ColorRGB() to a variable that matches a predefined color name\n\n"
        "BACKTEST SETTINGS (standalone strategies only):\n"
        "- SetOption('CommissionMode', 2)  ← ONLY values 0,1,2 are valid. Mode 3 does NOT exist.\n"
        "- SetOption('CommissionAmount', 0.0005)  ← 0.05% per trade\n"
        "- SetOption('UsePrevBarEquityForPosSizing', True)\n"
        "- SetOption('AllowPositionShrinking', True)\n"
        "- SetOption('InitialEquity', 100000)\n"
        "- PositionSize = 100\n\n"
        "NEVER DO THESE — they are hallucinations:\n"
        "- NEVER add if(Status('mode')==1) blocks to run Optimize() — Optimize() works unconditionally\n"
        "- NEVER use GetBacktesterObject() or bo.GetStats() — this API does not exist in AFL\n"
        "- NEVER assign plots to panels via a Param variable — panel layout is set in the chart UI\n\n"
        "COMPOSITE MODULES:\n"
        "- Export signals via StaticVarSet('name', Buy) — NOT #include files\n"
        "- Composite modules must NOT contain backtest settings or Plot() calls\n\n"
        "STRUCTURE (standalone strategies must include all sections):\n"
        "Parameters → Backtest Settings → Indicators → Trading Logic → "
        "ExRem cleanup → Chart Visualization → Exploration (Filter + AddColumn)\n"
    ),
    max_tokens=8192,  # FIX-03 alignment: match MAX_TOKENS in claude_engine.py
    tags=["afl", "amibroker", "trading", "code-generation"],
))

# ── 2. Potomac Document Generator (potomac-docx-skill) ─────────────────────
_register(SkillDefinition(
    skill_id="skill_01Jhf6196usgAdPmnZQGedXM",
    name="Potomac DOCX Skill",
    slug="potomac-docx-skill",
    description=(
        "Create professional Potomac-branded Word documents (.docx files) for any "
        "business purpose. Potomac is a tactical fund manager — documents include "
        "fund fact sheets, market commentaries, performance reports, risk reports, "
        "trade rationale, investment policy statements, DDQs, advisor onboarding "
        "guides, research write-ups, legal agreements, technical docs, SOPs, "
        "invoices, marketing materials, internal memos, client proposals, and "
        "general-purpose documents. Use whenever the user requests any Word "
        "document for Potomac, regardless of type."
    ),
    category=SkillCategory.DOCUMENT,
    system_prompt=(
        "You are a professional Potomac-branded document generator. Create "
        "well-structured, institutional-grade Word documents with proper formatting, "
        "data tables, charts descriptions, and clear prose. Potomac is a tactical "
        "fund manager. Follow financial industry standards for document structure. "
        "Output content in well-formatted markdown that can be converted to .docx."
    ),
    max_tokens=16384,
    tags=["document", "docx", "word", "report", "financial", "writing", "potomac", "fact-sheet", "memo"],
))

# Keep backward-compat alias for existing code that uses old slug
SKILL_REGISTRY["potomac-document-generator"] = SKILL_REGISTRY["potomac-docx-skill"]

# ── 3. Potomac PowerPoint Generator (potomac-pptx skill) ──────────────────
_register(SkillDefinition(
    skill_id="skill_01R8PDacb1KDHZLR68VsEQ3h",
    name="Potomac PPTX Skill",
    slug="potomac-pptx-skill",
    description=(
        "Enhanced PPTX skill with strict Potomac brand compliance. Inherits all "
        "capabilities from the base PPTX skill (markitdown extraction, template "
        "editing, pptxgenjs generation, visual QA) and adds zero-tolerance brand "
        "enforcement, AI-powered template selection, and Potomac-specific design "
        "guidelines. Use for all Potomac presentations requiring perfect brand "
        "adherence with professional quality assurance."
    ),
    category=SkillCategory.PRESENTATION,
    system_prompt=(
        "You are an expert Potomac presentation designer. Create compelling, "
        "brand-compliant slide content with Potomac yellow (#FEC00F) and dark "
        "color scheme. Include clear hierarchies, data visualizations, and "
        "concise bullet points. Output structured JSON for slide assembly. "
        "Every slide must adhere to strict Potomac brand guidelines."
    ),
    max_tokens=16384,
    tags=["presentation", "powerpoint", "pptx", "slides", "potomac", "brand"],
))

# Keep backward-compat alias for existing code that uses old slug
SKILL_REGISTRY["potomac-powerpoint-generator"] = SKILL_REGISTRY["potomac-pptx-skill"]

# ── 4. Vercel AI Elements ──────────────────────────────────────────────────
_register(SkillDefinition(
    skill_id="skill_01ACJvCz8aYdVA91GAqaq2Wx",
    name="Vercel AI Elements",
    slug="vercel-ai-elements",
    description=(
        "Generates interactive React UI components, charts, diagrams, and "
        "generative UI elements compatible with the Vercel AI SDK. "
        "Creates Recharts visualizations, Tailwind-styled components, and "
        "Mermaid diagrams."
    ),
    category=SkillCategory.UI,
    system_prompt=(
        "You are a React/UI expert specializing in Vercel AI SDK components. "
        "Generate clean, TypeScript-compatible React components using Tailwind CSS, "
        "Recharts for data visualization, and modern React patterns. "
        "Components must be self-contained and export as default."
    ),
    max_tokens=4096,
    tags=["ui", "react", "components", "charts", "vercel", "generative-ui"],
))

# ── 5. Backtest Expert ─────────────────────────────────────────────────────
_register(SkillDefinition(
    skill_id="skill_01HKFBybai8sm3gKrxuZbZP3",
    name="Backtest Expert",
    slug="backtest-expert",
    description=(
        "Analyzes backtest results, identifies strengths and weaknesses in "
        "trading strategies, suggests parameter optimizations, and provides "
        "actionable insights on strategy performance metrics."
    ),
    category=SkillCategory.BACKTEST,
    system_prompt=(
        "You are an expert in backtesting and quantitative strategy evaluation. "
        "Analyze backtest results thoroughly, focusing on risk-adjusted returns, "
        "drawdown analysis, Sharpe/Sortino ratios, win rates, profit factors, "
        "and statistical significance. Provide specific, actionable recommendations."
    ),
    max_tokens=4096,
    tags=["backtest", "analysis", "performance", "strategy", "metrics"],
))

# ── 6. US Market Bubble Detector ───────────────────────────────────────────
_register(SkillDefinition(
    skill_id="skill_01UWobdcmuwz1VTYQBTpbGfA",
    name="US Market Bubble Detector",
    slug="us-market-bubble-detector",
    description=(
        "Detects potential market bubbles in US equities by analyzing "
        "valuation metrics, sentiment indicators, credit conditions, "
        "momentum divergences, and historical bubble patterns."
    ),
    category=SkillCategory.MARKET_ANALYSIS,
    system_prompt=(
        "You are a market analysis expert specializing in bubble detection. "
        "Evaluate US equity markets using Shiller PE, Buffett Indicator, "
        "credit spreads, margin debt, insider transactions, IPO activity, "
        "and other bubble indicators. Provide a data-driven risk assessment."
    ),
    max_tokens=4096,
    tags=["market", "bubble", "risk", "valuation", "equities", "us-market"],
))

# ── 7. Quant Analyst ───────────────────────────────────────────────────────
_register(SkillDefinition(
    skill_id="skill_01X5yKJyGcJPRgpFW5C8C1iB",
    name="Quant Analyst",
    slug="quant-analyst",
    description=(
        "Quantitative analysis engine for building and evaluating systematic "
        "trading strategies. Performs factor analysis, statistical modeling, "
        "portfolio optimization, and risk decomposition."
    ),
    category=SkillCategory.QUANT,
    system_prompt=(
        "You are a senior quantitative analyst. Build systematic trading "
        "strategies using factor models, statistical arbitrage, mean reversion, "
        "and momentum approaches. Apply rigorous statistical methods including "
        "hypothesis testing, cross-validation, and walk-forward analysis."
    ),
    max_tokens=4096,
    tags=["quant", "quantitative", "factor", "portfolio", "statistics", "systematic"],
))

# ── 8. Financial Deep Research ──────────────────────────────────────────────
_register(SkillDefinition(
    skill_id="skill_01PdnyT3jcLshnCQJmdPqTR6",
    name="Financial Deep Research",
    slug="financial-deep-research",
    description=(
        "Performs in-depth financial research including fundamental analysis, "
        "industry research, competitive analysis, earnings deep dives, and "
        "macroeconomic impact assessment."
    ),
    category=SkillCategory.RESEARCH,
    system_prompt=(
        "You are a senior financial research analyst. Conduct thorough research "
        "covering fundamental analysis, industry dynamics, competitive positioning, "
        "management quality, and macro factors. Provide well-sourced, balanced "
        "analysis with clear investment implications."
    ),
    max_tokens=8192,
    tags=["research", "fundamental", "analysis", "financial", "deep-dive"],
))

# ── 9. Backtesting Frameworks ──────────────────────────────────────────────
_register(SkillDefinition(
    skill_id="skill_01A2s1Q8zBjfMQC87KTWHavp",
    name="Backtesting Frameworks",
    slug="backtesting-frameworks",
    description=(
        "Expert in backtesting frameworks and methodologies. Designs backtest "
        "configurations, walk-forward analysis setups, Monte Carlo simulations, "
        "and out-of-sample validation strategies for trading systems."
    ),
    category=SkillCategory.BACKTEST,
    system_prompt=(
        "You are an expert in backtesting frameworks and methodologies. "
        "Design robust backtest configurations including walk-forward analysis, "
        "Monte Carlo simulations, bootstrapping, and out-of-sample validation. "
        "Warn about common pitfalls: look-ahead bias, survivorship bias, "
        "overfitting, and data snooping."
    ),
    max_tokens=4096,
    tags=["backtest", "framework", "walk-forward", "monte-carlo", "validation"],
))


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_skill(slug: str) -> Optional[SkillDefinition]:
    """Get a skill by its slug.  Returns None if not found."""
    return SKILL_REGISTRY.get(slug)


def get_skill_by_id(skill_id: str) -> Optional[SkillDefinition]:
    """Get a skill by its Claude skill_id."""
    for skill in SKILL_REGISTRY.values():
        if skill.skill_id == skill_id:
            return skill
    return None


def list_skills(
    category: Optional[SkillCategory] = None,
    enabled_only: bool = True,
) -> List[SkillDefinition]:
    """List skills, optionally filtered by category."""
    skills = list(SKILL_REGISTRY.values())
    if enabled_only:
        skills = [s for s in skills if s.enabled]
    if category:
        skills = [s for s in skills if s.category == category]
    return skills


def list_skills_dict(
    category: Optional[str] = None,
    enabled_only: bool = True,
) -> List[Dict[str, Any]]:
    """List skills as serializable dicts."""
    cat = SkillCategory(category) if category else None
    return [s.to_dict() for s in list_skills(category=cat, enabled_only=enabled_only)]


def get_categories() -> List[Dict[str, Any]]:
    """Return list of categories with counts."""
    from collections import Counter
    counts = Counter(s.category.value for s in SKILL_REGISTRY.values() if s.enabled)
    return [
        {"category": cat.value, "label": cat.value.replace("_", " ").title(), "count": counts.get(cat.value, 0)}
        for cat in SkillCategory
    ]