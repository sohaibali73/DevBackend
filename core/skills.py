"""
Potomac Custom Beta Skills Registry  (core/skills.py)
=======================================================
This is the single source-of-truth registry used by SkillGateway and all
route handlers.  api/routes/skills.py exposes this registry over HTTP.

Each skill is a custom (or Anthropic built-in) skill created in the Claude
Developer Portal.  Skills run inside the code execution container and require
specific beta headers to activate.

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
    FINANCIAL_MODELING = "financial_modeling"
    DATA = "data"


# ---------------------------------------------------------------------------
# Skill definition dataclass
# ---------------------------------------------------------------------------
@dataclass
class SkillDefinition:
    """A registered Claude custom beta skill."""
    skill_id: str                   # Empty string for Anthropic built-in skills
    name: str
    slug: str                       # URL-safe identifier used in API routes
    description: str
    category: SkillCategory
    system_prompt: str = ""         # Optional system prompt override
    max_tokens: int = 4096
    tags: List[str] = field(default_factory=list)
    enabled: bool = True
    supports_streaming: bool = True
    # Anthropic built-in skills have no skill_id — set is_builtin=True
    is_builtin: bool = False

    def to_container(self) -> Dict[str, Any]:
        """Return the ``container`` param for ``client.beta.messages.create()``."""
        if self.is_builtin:
            # Anthropic-hosted skills use name + type:"anthropic"
            return {
                "skills": [
                    {
                        "name": self.slug,
                        "type": "anthropic",
                    }
                ]
            }
        # Custom skills use skill_id + type:"custom"
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
            "is_builtin": self.is_builtin,
        }


# ---------------------------------------------------------------------------
# MASTER SKILL REGISTRY
# ---------------------------------------------------------------------------
SKILL_REGISTRY: Dict[str, SkillDefinition] = {}


def _register(skill: SkillDefinition) -> SkillDefinition:
    """Register a skill in the global registry."""
    SKILL_REGISTRY[skill.slug] = skill
    return skill


# ===========================================================================
# ANTHROPIC BUILT-IN SKILLS
# Hosted by Anthropic — no skill_id required.
# ===========================================================================

# ── B1. Anthropic XLSX ─────────────────────────────────────────────────────
_register(SkillDefinition(
    skill_id="",
    name="Excel (xlsx)",
    slug="xlsx",
    description=(
        "Comprehensive Microsoft Excel (.xlsx) document creation, editing, and "
        "analysis with support for formulas, formatting, data analysis, and "
        "visualization. Triggers for: Excel, spreadsheet, .xlsx, data table, "
        "budget, financial model, chart, graph, tabular data, xls."
    ),
    category=SkillCategory.DATA,
    max_tokens=8192,
    tags=["excel", "xlsx", "spreadsheet", "data", "formulas"],
    is_builtin=True,
))

# ── B2. Anthropic PPTX ─────────────────────────────────────────────────────
_register(SkillDefinition(
    skill_id="",
    name="PowerPoint (pptx)",
    slug="pptx",
    description=(
        "Create, read, edit, and manipulate PowerPoint (.pptx) presentations. "
        "Triggers whenever a .pptx file is involved — creating decks, pitch decks, "
        "editing existing slides, extracting text, combining files, working with "
        "templates, layouts, speaker notes, or comments."
    ),
    category=SkillCategory.PRESENTATION,
    max_tokens=8192,
    tags=["pptx", "powerpoint", "slides", "presentation", "deck"],
    is_builtin=True,
))

# ── B3. Anthropic PDF ──────────────────────────────────────────────────────
_register(SkillDefinition(
    skill_id="",
    name="PDF",
    slug="pdf",
    description=(
        "Comprehensive PDF manipulation toolkit for extracting text and tables, "
        "creating new PDFs, merging/splitting documents, and handling forms. "
        "Triggers for: PDF, .pdf, form, extract, merge, split."
    ),
    category=SkillCategory.DOCUMENT,
    max_tokens=8192,
    tags=["pdf", "extract", "merge", "split", "forms", "documents"],
    is_builtin=True,
))

# ── B4. Anthropic DOCX ─────────────────────────────────────────────────────
_register(SkillDefinition(
    skill_id="",
    name="Word Document (docx)",
    slug="docx",
    description=(
        "Create, read, edit, or manipulate Word documents (.docx files). "
        "Triggers for: Word doc, word document, .docx, reports with formatting, "
        "tables of contents, headings, page numbers, or letterheads."
    ),
    category=SkillCategory.DOCUMENT,
    max_tokens=8192,
    tags=["docx", "word", "document", "report", "memo", "letter"],
    is_builtin=True,
))


# ===========================================================================
# CUSTOM SKILLS
# ===========================================================================

# ── 1. AmiBroker AFL Developer ─────────────────────────────────────────────
_register(SkillDefinition(
    skill_id="skill_01GG6E88EuXr9H9tqLp51sH5",
    name="AmiBroker AFL Developer",
    slug="amibroker-afl-developer",
    description=(
        "Expert AFL code generator for AmiBroker. Generates, debugs, optimizes, "
        "and explains AmiBroker Formula Language code from natural language."
    ),
    category=SkillCategory.AFL,
    system_prompt=(
        "You are an expert AmiBroker AFL developer. Always follow these rules:\n\n"
        "FUNCTION SIGNATURES:\n"
        "- Single-arg: RSI(14), ATR(14), ADX(14), CCI(20), MFI(14) — NEVER RSI(Close, 14)\n"
        "- Double-arg: MA(Close, 20), EMA(Close, 20), HHV(High, 20) — NEVER MA(20)\n"
        "- OBV() takes NO arguments — NEVER OBV(14) or OBV(Close, 14)\n"
        "- ParamToggle needs 3 args: ParamToggle('name', 'No|Yes', 0)\n"
        "- Param needs 5 args: Param('name', default, min, max, step)\n"
        "- Optimize needs 5 args: Optimize('name', param_var, min, max, step)\n\n"
        "VARIABLE NAMING:\n"
        "- NEVER shadow built-in functions as variable names\n"
        "- Use RSI_Val not RSI; MALength not MA; RSIPeriod not RSI for param vars\n\n"
        "SIGNALS:\n"
        "- ALWAYS apply ExRem(Buy, Sell) and ExRem(Sell, Buy) after signal construction\n"
        "- Use _SECTION_BEGIN/_SECTION_END to structure all major code blocks\n\n"
        "BACKTEST SETTINGS:\n"
        "- SetOption('CommissionMode', 2) — ONLY values 0,1,2 are valid\n"
        "- SetOption('CommissionAmount', 0.0005) — 0.05% per trade\n"
        "- PositionSize = 100\n"
    ),
    max_tokens=20000,
    tags=["afl", "amibroker", "trading", "code-generation"],
))

# ── 2. Potomac DOCX Skill ─────────────────────────────────────────────────
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

# ── 3. Potomac DOCX Document Generator ─────────────────────────────────────
_register(SkillDefinition(
    skill_id="skill_01Jhf6196usgAdPmnZQGedXM",
    name="Potomac DOCX Document Generator",
    slug="potomac-document-generator",
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

# ── 4. Potomac PPTX Skill ─────────────────────────────────────────────────
_register(SkillDefinition(
    skill_id="skill_01R8PDacb1KDHZLR68VsEQ3h",
    name="Potomac PPTX Skill",
    slug="potomac-pptx",
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

# ── 5. Potomac PowerPoint Generator ────────────────────────────────────────
_register(SkillDefinition(
    skill_id="skill_01R8PDacb1KDHZLR68VsEQ3h",
    name="Potomac PowerPoint Generator",
    slug="potomac-powerpoint-generator",
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

# ── 6. AI Elements (Vercel AI SDK) ─────────────────────────────────────────
_register(SkillDefinition(
    skill_id="skill_01ACJvCz8aYdVA91GAqaq2Wx",
    name="AI Elements",
    slug="ai-elements",
    description=(
        "Create new AI chat interface components for the ai-elements library "
        "following established composable patterns, shadcn/ui integration, and "
        "Vercel AI SDK conventions. Use when creating new components in "
        "packages/elements/src or when the user asks to add a new component to ai-elements."
    ),
    category=SkillCategory.UI,
    system_prompt=(
        "You are a React/UI expert specializing in Vercel AI SDK components. "
        "Generate clean, TypeScript-compatible React components using Tailwind CSS, "
        "Recharts for data visualization, and modern React patterns. "
        "Components must be self-contained and export as default."
    ),
    max_tokens=4096,
    tags=["ui", "react", "components", "charts", "vercel", "generative-ui", "ai-elements"],
))

# ── 7. Vercel AI Elements ──────────────────────────────────────────────────
_register(SkillDefinition(
    skill_id="skill_01ACJvCz8aYdVA91GAqaq2Wx",
    name="Vercel AI Elements",
    slug="vercel-ai-elements",
    description=(
        "Create new AI chat interface components for the ai-elements library "
        "following established composable patterns, shadcn/ui integration, and "
        "Vercel AI SDK conventions. Use when creating new components in "
        "packages/elements/src or when the user asks to add a new component to ai-elements."
    ),
    category=SkillCategory.UI,
    system_prompt=(
        "You are a React/UI expert specializing in Vercel AI SDK components. "
        "Generate clean, TypeScript-compatible React components using Tailwind CSS, "
        "Recharts for data visualization, and modern React patterns. "
        "Components must be self-contained and export as default."
    ),
    max_tokens=4096,
    tags=["ui", "react", "components", "charts", "vercel", "generative-ui", "ai-elements"],
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

# ── 8. Financial Deep Research ─────────────────────────────────────────────
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

# ── 10. Document Interpreter ───────────────────────────────────────────────
_register(SkillDefinition(
    skill_id="skill_019kkuGzHQxn9uo5wZcZm7tp",
    name="Document Interpreter",
    slug="doc-interpreter",
    description=(
        "Intelligently read, interpret, and extract structured information from "
        "images, PDFs, and scanned documents using the Anthropic API. Use whenever "
        "the user needs to process any visual or document file — including photos, "
        "screenshots, scanned pages, multi-page PDFs, invoices, contracts, financial "
        "reports, forms, charts, tables, handwritten notes, or any file where content "
        "must be seen rather than just read as text."
    ),
    category=SkillCategory.DOCUMENT,
    system_prompt=(
        "You are an expert document analyst and OCR specialist. Read, interpret, "
        "and extract structured information from images, scanned documents, PDFs, "
        "invoices, contracts, forms, charts, tables, and handwritten notes. "
        "Be thorough and preserve all information."
    ),
    max_tokens=8192,
    tags=["ocr", "pdf", "image", "document", "extraction", "scan", "invoice", "vision"],
))

# ── 11. Potomac XLSX ───────────────────────────────────────────────────────
_register(SkillDefinition(
    skill_id="skill_01Av4tiB8MZNEH4goGHnX5Kv",
    name="Potomac Excel (XLSX)",
    slug="potomac-xlsx",
    description=(
        "Create, read, edit, and modify Potomac-branded Excel spreadsheets (.xlsx) "
        "for any business purpose. Potomac is a tactical fund manager — spreadsheets "
        "include performance reports, portfolio trackers, risk dashboards, trade logs, "
        "fee schedules, budget models, data exports, onboarding checklists, and "
        "financial models."
    ),
    category=SkillCategory.DATA,
    system_prompt=(
        "You are an expert Potomac Excel specialist. Create professional, "
        "brand-compliant Excel spreadsheets using Potomac colors (Yellow #FEC00F, "
        "Dark Gray #212121), Calibri fonts, and industry-standard financial "
        "formatting. Always use Excel formulas rather than hardcoded values. "
        "Apply zebra-stripe row formatting, yellow column headers (ALL CAPS), "
        "and include disclosure footers on external documents."
    ),
    max_tokens=8192,
    tags=["excel", "xlsx", "spreadsheet", "potomac", "financial", "brand", "performance", "portfolio"],
))

# ── 12. DCF Model ─────────────────────────────────────────────────────────
_register(SkillDefinition(
    skill_id="skill_017iHXZfu3T1HKQYTPn9t7KE",
    name="DCF Model",
    slug="dcf-model",
    description=(
        "Real DCF (Discounted Cash Flow) model creation for equity valuation. "
        "Retrieves financial data from SEC filings and analyst reports, builds "
        "comprehensive cash flow projections with proper WACC calculations, performs "
        "sensitivity analysis, and outputs professional Excel models with executive "
        "summaries."
    ),
    category=SkillCategory.FINANCIAL_MODELING,
    system_prompt=(
        "You are an expert equity valuation analyst specializing in DCF modeling. "
        "Build rigorous discounted cash flow models with: multi-year FCFF/FCFE "
        "projections, WACC calculations (cost of equity via CAPM, cost of debt, "
        "capital structure weighting), terminal value (Gordon Growth and exit "
        "multiple methods), sensitivity tables (WACC vs growth rate), and "
        "bridge from enterprise value to equity value per share."
    ),
    max_tokens=16384,
    tags=["dcf", "valuation", "financial-model", "excel", "equity", "wacc", "intrinsic-value"],
))

# ── 13. Initiating Coverage ────────────────────────────────────────────────
_register(SkillDefinition(
    skill_id="skill_01VkFAJJ8G8EQDYty8wA2kEb",
    name="Initiating Coverage",
    slug="initiating-coverage",
    description=(
        "Create institutional-quality equity research initiation reports through a "
        "5-task workflow: (1) company research, (2) financial modeling, (3) valuation "
        "analysis, (4) chart generation, (5) final report assembly."
    ),
    category=SkillCategory.RESEARCH,
    system_prompt=(
        "You are a senior equity research analyst producing institutional-grade "
        "initiation of coverage reports. Follow a rigorous 5-task workflow: "
        "1) Deep company research, 2) Financial model construction, "
        "3) Valuation (DCF, comps), 4) Chart generation, "
        "5) Final report assembly (executive summary, investment thesis, risks, "
        "catalysts, price target, rating)."
    ),
    max_tokens=16384,
    tags=["equity-research", "initiation", "coverage", "valuation", "financial-model", "report"],
))

# ── 14. Datapack Builder ──────────────────────────────────────────────────
_register(SkillDefinition(
    skill_id="skill_01JqFHZGt3XKGHjuEukkB5x2",
    name="Datapack Builder",
    slug="datapack-builder",
    description=(
        "Build professional financial services data packs from CIMs, offering "
        "memorandums, SEC filings, web search, or MCP servers. Extract, normalize, "
        "and standardize financial data into investment committee-ready Excel "
        "workbooks. Use for M&A due diligence, private equity analysis, and "
        "investment committee materials."
    ),
    category=SkillCategory.FINANCIAL_MODELING,
    system_prompt=(
        "You are an expert financial data analyst specializing in investment "
        "committee materials and due diligence data packs. Extract and normalize "
        "financial data. Standardize into consistent Excel workbooks with: income "
        "statement, balance sheet, cash flow statement, KPI dashboard, and "
        "documented assumptions."
    ),
    max_tokens=16384,
    tags=["datapack", "due-diligence", "private-equity", "m-and-a", "excel", "financial-data", "cim"],
))

# ── 15. Artifacts Builder ─────────────────────────────────────────────────
_register(SkillDefinition(
    skill_id="skill_01XonCKm9QM3jUbtxt9Gtm9Q",
    name="Artifacts Builder",
    slug="artifacts-builder",
    description=(
        "Suite of tools for creating elaborate, multi-component claude.ai HTML "
        "artifacts using modern frontend web technologies (React, Tailwind CSS, "
        "shadcn/ui). Use for complex artifacts requiring state management, routing, "
        "or shadcn/ui components."
    ),
    category=SkillCategory.UI,
    system_prompt=(
        "You are an expert frontend engineer building complex, multi-component "
        "React artifacts. Use Tailwind CSS for styling, shadcn/ui for components, "
        "and proper state management (useState, useReducer, Context) for "
        "interactivity. All artifacts must be self-contained and functional."
    ),
    max_tokens=8192,
    tags=["artifacts", "react", "tailwind", "shadcn", "ui", "components", "frontend"],
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
    include_builtins: bool = True,
) -> List[SkillDefinition]:
    """List skills, optionally filtered by category."""
    skills = list(SKILL_REGISTRY.values())
    if enabled_only:
        skills = [s for s in skills if s.enabled]
    if not include_builtins:
        skills = [s for s in skills if not s.is_builtin]
    if category:
        skills = [s for s in skills if s.category == category]
    # Deduplicate (aliases share the same object — compare by skill_id+slug)
    seen, unique = set(), []
    for s in skills:
        key = (s.skill_id, s.slug)
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique


def list_skills_dict(
    category: Optional[str] = None,
    enabled_only: bool = True,
    include_builtins: bool = True,
) -> List[Dict[str, Any]]:
    """List skills as serializable dicts."""
    cat = SkillCategory(category) if category else None
    return [s.to_dict() for s in list_skills(
        category=cat, enabled_only=enabled_only, include_builtins=include_builtins
    )]


def get_categories() -> List[Dict[str, Any]]:
    """Return list of categories with counts (deduped, no aliases)."""
    from collections import Counter
    counts = Counter(
        s.category.value
        for s in list_skills(enabled_only=True)
    )
    return [
        {
            "category": cat.value,
            "label": cat.value.replace("_", " ").title(),
            "count": counts.get(cat.value, 0),
        }
        for cat in SkillCategory
    ]
