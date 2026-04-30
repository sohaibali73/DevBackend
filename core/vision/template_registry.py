"""
TemplateRegistry
================
A catalog of pre-built, Potomac-branded slide templates that can be
instantly inserted into any presentation.

Templates are defined as pptx_sandbox spec dicts stored in a JSON registry.
They cover common slide types with pre-filled example content that users
can customize.

Template categories
-------------------
intro         → Title, agenda, executive summary templates
content       → Bullet, two-column, three-column content slides
data          → Metrics, KPI, scorecard, table, chart templates
visual        → Icon grid, card grid, process flow, timeline
strategy      → Comparison, matrix, hub-spoke diagrams
closing       → CTA, contact, thank you, next steps slides
section       → Section dividers with various styles

Usage
-----
    from core.vision.template_registry import TemplateRegistry

    reg = TemplateRegistry()

    # List all templates
    catalog = reg.get_catalog()

    # Get a specific template spec
    spec = reg.get_template("strategy_4_pillars")

    # Search templates by category or keyword
    results = reg.search("metrics", category="data")

    # Get random template of a type
    spec = reg.get_random(slide_type="card_grid")
"""

from __future__ import annotations

import json
import logging
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "ClaudeSkills" / "potomac-pptx" / "templates"
_USER_TEMPLATES_DIR = Path(os.environ.get("STORAGE_ROOT", "/data")) / "pptx_templates"


# =============================================================================
# Data classes
# =============================================================================

@dataclass
class TemplateEntry:
    """A single slide template."""
    template_id:  str
    name:         str
    category:     str          # "intro" | "content" | "data" | "visual" | "strategy" | "closing"
    slide_type:   str          # pptx_sandbox slide type
    description:  str
    tags:         List[str] = field(default_factory=list)
    spec:         Dict[str, Any] = field(default_factory=dict)  # pptx_sandbox spec
    preview_hint: str = ""     # brief visual description for UI

    def to_dict(self, include_spec: bool = True) -> Dict[str, Any]:
        d = {
            "template_id":  self.template_id,
            "name":         self.name,
            "category":     self.category,
            "slide_type":   self.slide_type,
            "description":  self.description,
            "tags":         self.tags,
            "preview_hint": self.preview_hint,
        }
        if include_spec:
            d["spec"] = self.spec
        return d


# =============================================================================
# Built-in template library
# =============================================================================

_BUILTIN_TEMPLATES: List[Dict[str, Any]] = [

    # ── INTRO ─────────────────────────────────────────────────────────────────

    {
        "template_id": "title_executive_dark",
        "name": "Executive Title (Dark)",
        "category": "intro",
        "slide_type": "title",
        "description": "Bold dark-background title slide with yellow accent",
        "tags": ["title", "executive", "dark", "intro"],
        "preview_hint": "Dark background, large title, yellow tagline",
        "spec": {
            "type": "title",
            "title": "PRESENTATION TITLE",
            "subtitle": "Subtitle or Presenter Name",
            "style": "executive",
        },
    },
    {
        "template_id": "title_clean_white",
        "name": "Clean Title (Light)",
        "category": "intro",
        "slide_type": "title",
        "description": "Clean white title slide with centered logo",
        "tags": ["title", "light", "clean", "intro"],
        "preview_hint": "White background, centered logo, dark title",
        "spec": {
            "type": "title",
            "title": "PRESENTATION TITLE",
            "subtitle": "Subtitle or Date",
            "style": "standard",
        },
    },
    {
        "template_id": "exec_summary_hero",
        "name": "Executive Summary",
        "category": "intro",
        "slide_type": "executive_summary",
        "description": "High-impact executive summary with headline + supporting points",
        "tags": ["executive", "summary", "headline", "intro"],
        "preview_hint": "Large headline, yellow divider, 4 supporting bullets",
        "spec": {
            "type": "executive_summary",
            "headline": "OUR KEY MESSAGE GOES HERE IN ONE POWERFUL STATEMENT",
            "supporting_points": [
                "First key supporting point with specific data",
                "Second supporting point with impact statement",
                "Third point reinforcing the main message",
                "Call to action or forward-looking statement",
            ],
            "call_to_action": "→ Schedule a call to discuss next steps",
        },
    },

    # ── CONTENT ───────────────────────────────────────────────────────────────

    {
        "template_id": "content_bullets_5",
        "name": "5-Bullet Content",
        "category": "content",
        "slide_type": "content",
        "description": "Standard content slide with 5 bullet points",
        "tags": ["content", "bullets", "standard"],
        "preview_hint": "Left accent bar, title, 5 bullet points",
        "spec": {
            "type": "content",
            "title": "SLIDE TITLE",
            "bullets": [
                "First key point — lead with the most important idea",
                "Second point with supporting detail or data",
                "Third point — keep each bullet to one clear idea",
                "Fourth point with specific metrics or outcomes",
                "Fifth point — end with forward-looking statement",
            ],
        },
    },
    {
        "template_id": "two_column_compare",
        "name": "Two-Column Layout",
        "category": "content",
        "slide_type": "two_column",
        "description": "Side-by-side content with optional headers",
        "tags": ["two-column", "compare", "layout"],
        "preview_hint": "Two equal columns with gray divider",
        "spec": {
            "type": "two_column",
            "title": "TWO-COLUMN TITLE",
            "left_header": "LEFT TOPIC",
            "right_header": "RIGHT TOPIC",
            "left_content": "Left column content.\n\nAdd your key points here, one per line.",
            "right_content": "Right column content.\n\nAdd your key points here, one per line.",
        },
    },
    {
        "template_id": "three_column_features",
        "name": "Three-Column Features",
        "category": "content",
        "slide_type": "three_column",
        "description": "Three equal columns for feature/benefit comparisons",
        "tags": ["three-column", "features", "benefits"],
        "preview_hint": "Three yellow-header columns",
        "spec": {
            "type": "three_column",
            "title": "THREE PILLARS OF VALUE",
            "column_headers": ["PERFORMANCE", "RISK CONTROL", "SERVICE"],
            "columns": [
                "Consistent outperformance across market cycles with disciplined process.",
                "Rigorous risk management with real-time monitoring and hedging.",
                "Dedicated team with institutional-grade reporting and transparency.",
            ],
        },
    },

    # ── DATA ──────────────────────────────────────────────────────────────────

    {
        "template_id": "metrics_kpi_4",
        "name": "4 KPI Metrics",
        "category": "data",
        "slide_type": "metrics",
        "description": "Four large KPI values with labels",
        "tags": ["metrics", "kpi", "data", "numbers"],
        "preview_hint": "4 large yellow numbers with labels below",
        "spec": {
            "type": "metrics",
            "title": "KEY PERFORMANCE INDICATORS",
            "metrics": [
                {"value": "$2.4B", "label": "Assets Under Management"},
                {"value": "14.2%", "label": "3-Year Annualized Return"},
                {"value": "0.82", "label": "Sharpe Ratio"},
                {"value": "98%", "label": "Client Retention Rate"},
            ],
            "context": "As of December 31, 2025. Past performance does not guarantee future results.",
        },
    },
    {
        "template_id": "scorecard_rag",
        "name": "RAG Scorecard",
        "category": "data",
        "slide_type": "scorecard",
        "description": "Red/Amber/Green status scorecard for tracking metrics",
        "tags": ["scorecard", "rag", "status", "tracking"],
        "preview_hint": "Table with green/yellow/red status indicators",
        "spec": {
            "type": "scorecard",
            "title": "PERFORMANCE SCORECARD",
            "items": [
                {"metric": "PORTFOLIO RETURN", "status": "green", "value": "+14.2%", "comment": "Above benchmark by 2.1%"},
                {"metric": "VOLATILITY", "status": "green", "value": "8.3%", "comment": "Within target range"},
                {"metric": "DRAWDOWN", "status": "amber", "value": "-4.1%", "comment": "Approaching limit, monitoring"},
                {"metric": "LIQUIDITY RATIO", "status": "red", "value": "82%", "comment": "Below 90% threshold — action required"},
                {"metric": "CLIENT NET FLOWS", "status": "green", "value": "+$124M", "comment": "Strong net inflows"},
            ],
        },
    },
    {
        "template_id": "table_performance",
        "name": "Performance Table",
        "category": "data",
        "slide_type": "table",
        "description": "Styled table with alternating row colors",
        "tags": ["table", "data", "performance", "returns"],
        "preview_hint": "Yellow header row, alternating gray/white rows",
        "spec": {
            "type": "table",
            "title": "PERFORMANCE SUMMARY",
            "headers": ["FUND", "1 YEAR", "3 YEAR", "5 YEAR", "SINCE INCEPTION"],
            "rows": [
                ["Navigrowth", "12.4%", "9.8%", "11.2%", "10.7%"],
                ["Guardian", "8.1%", "7.2%", "8.5%", "9.1%"],
                ["Bull Bear", "15.2%", "11.4%", "13.1%", "12.3%"],
                ["Income Plus", "6.8%", "6.1%", "7.2%", "7.8%"],
            ],
            "number_cols": [2, 3, 4, 5],
            "caption": "Returns are net of fees. Past performance is not indicative of future results.",
        },
    },

    # ── VISUAL ────────────────────────────────────────────────────────────────

    {
        "template_id": "strategy_4_hexagons",
        "name": "4-Strategy Icon Grid",
        "category": "visual",
        "slide_type": "card_grid",
        "description": "4 strategy cards — like the Potomac strategies slide",
        "tags": ["strategy", "hexagon", "icon", "card", "visual"],
        "preview_hint": "4 yellow cards with icons and strategy names",
        "spec": {
            "type": "card_grid",
            "title": "OUR STRATEGIES",
            "subtitle": "Tactical, Unconstrained, and Risk-Aware",
            "section_label": "STRATEGIES",
            "background": "dark",
            "columns": 4,
            "cards": [
                {"title": "Navigrowth\n2000", "color": "yellow", "bold": True},
                {"title": "Guardian\n2000", "color": "yellow", "bold": True},
                {"title": "Bull Bear\n2002", "color": "yellow", "bold": True},
                {"title": "Income Plus\n2009", "color": "yellow", "bold": True},
            ],
        },
    },
    {
        "template_id": "process_5_steps",
        "name": "5-Step Process",
        "category": "visual",
        "slide_type": "process",
        "description": "Five-step process flow with numbered circles",
        "tags": ["process", "steps", "flow", "sequential"],
        "preview_hint": "5 numbered circles connected by lines",
        "spec": {
            "type": "process",
            "title": "INVESTMENT PROCESS",
            "steps": [
                {"title": "RESEARCH", "description": "Proprietary analysis of 500+ securities"},
                {"title": "SCREEN", "description": "Quantitative and qualitative filters"},
                {"title": "SELECT", "description": "Portfolio construction and sizing"},
                {"title": "MONITOR", "description": "Real-time risk monitoring"},
                {"title": "REVIEW", "description": "Quarterly performance attribution"},
            ],
        },
    },
    {
        "template_id": "timeline_milestones",
        "name": "Timeline / Milestones",
        "category": "visual",
        "slide_type": "timeline",
        "description": "Horizontal timeline with milestone markers",
        "tags": ["timeline", "milestones", "history", "roadmap"],
        "preview_hint": "Yellow horizontal line with alternating above/below labels",
        "spec": {
            "type": "timeline",
            "title": "FIRM MILESTONES",
            "milestones": [
                {"label": "Founded", "date": "2000", "status": "complete"},
                {"label": "First $1B AUM", "date": "2005", "status": "complete"},
                {"label": "Bull Bear Launch", "date": "2002", "status": "complete"},
                {"label": "Income Plus", "date": "2009", "status": "complete"},
                {"label": "$2.4B AUM", "date": "2025", "status": "in_progress"},
            ],
        },
    },

    # ── STRATEGY ──────────────────────────────────────────────────────────────

    {
        "template_id": "comparison_vs",
        "name": "A vs B Comparison",
        "category": "strategy",
        "slide_type": "comparison",
        "description": "Side-by-side comparison with winner highlight",
        "tags": ["comparison", "versus", "pros-cons", "strategy"],
        "preview_hint": "Two columns with yellow winner highlight",
        "spec": {
            "type": "comparison",
            "title": "ACTIVE VS PASSIVE INVESTING",
            "left_label": "PASSIVE",
            "right_label": "ACTIVE (POTOMAC)",
            "winner": "right",
            "rows": [
                {"label": "RETURNS", "left": "Index returns only", "right": "Potential to outperform"},
                {"label": "RISK MGMT", "left": "No downside protection", "right": "Active risk controls"},
                {"label": "FEES", "left": "Lower", "right": "Justified by alpha"},
                {"label": "FLEXIBILITY", "left": "Rigid index composition", "right": "Tactical reallocation"},
                {"label": "BEAR MARKETS", "left": "Full drawdown exposure", "right": "Downside mitigation"},
            ],
        },
    },
    {
        "template_id": "matrix_2x2_priority",
        "name": "2x2 Priority Matrix",
        "category": "strategy",
        "slide_type": "matrix_2x2",
        "description": "Impact/Effort matrix for prioritization",
        "tags": ["matrix", "2x2", "priority", "quadrant"],
        "preview_hint": "4-quadrant matrix with items plotted",
        "spec": {
            "type": "matrix_2x2",
            "title": "OPPORTUNITY PRIORITIZATION",
            "x_label": "IMPLEMENTATION EFFORT",
            "y_label": "EXPECTED IMPACT",
            "quadrant_labels": [
                "QUICK WINS",      # top-left
                "MAJOR PROJECTS",  # top-right
                "FILL-INS",        # bottom-left
                "RECONSIDER",      # bottom-right
            ],
            "items": [
                {"label": "Strategy A", "x": 0.2, "y": 0.8, "size": 30},
                {"label": "Strategy B", "x": 0.7, "y": 0.75, "size": 40},
                {"label": "Strategy C", "x": 0.15, "y": 0.35, "size": 20},
                {"label": "Strategy D", "x": 0.8, "y": 0.3, "size": 25},
            ],
        },
    },
    {
        "template_id": "hub_spoke_model",
        "name": "Hub-Spoke Model",
        "category": "strategy",
        "slide_type": "hub_spoke",
        "description": "Central concept with 4 surrounding elements",
        "tags": ["hub", "spoke", "ecosystem", "model", "strategy"],
        "preview_hint": "Center hub with 4 spoke boxes connecting to it",
        "spec": {
            "type": "hub_spoke",
            "title": "INTEGRATED INVESTMENT FRAMEWORK",
            "hub": {
                "label": "POTOMAC\nCORE",
                "items": ["$2.4B AUM", "25 Years"],
                "color": "yellow",
            },
            "spokes": [
                {"label": "RESEARCH", "items": ["Macro analysis", "Security selection"], "side": "left", "row": 0},
                {"label": "RISK", "items": ["Real-time monitoring", "Drawdown limits"], "side": "left", "row": 1},
                {"label": "EXECUTION", "items": ["Low-cost trading", "Tax efficiency"], "side": "right", "row": 0},
                {"label": "SERVICE", "items": ["Dedicated team", "Custom reporting"], "side": "right", "row": 1},
            ],
        },
    },

    # ── SECTION DIVIDERS ──────────────────────────────────────────────────────

    {
        "template_id": "section_divider_yellow",
        "name": "Section Divider",
        "category": "section",
        "slide_type": "section_divider",
        "description": "Yellow-accent section break slide",
        "tags": ["section", "divider", "break", "chapter"],
        "preview_hint": "Yellow vertical bar, large section title on light background",
        "spec": {
            "type": "section_divider",
            "title": "SECTION TITLE",
            "description": "Brief description of what this section covers.",
        },
    },

    # ── CLOSING ───────────────────────────────────────────────────────────────

    {
        "template_id": "cta_contact",
        "name": "Contact / CTA Slide",
        "category": "closing",
        "slide_type": "cta",
        "description": "Call-to-action closing slide with contact details",
        "tags": ["cta", "closing", "contact", "next-steps"],
        "preview_hint": "Centered logo, CTA button, contact information",
        "spec": {
            "type": "cta",
            "title": "READY TO GET STARTED?",
            "action_text": "Contact your Potomac relationship manager to learn more about our investment strategies and how we can help you achieve your financial goals.",
            "button_text": "SCHEDULE A CALL",
            "contact_info": "info@potomacfund.com  |  (202) 555-0100  |  www.potomacfund.com",
        },
    },
    {
        "template_id": "quote_inspirational",
        "name": "Quote Slide",
        "category": "closing",
        "slide_type": "quote",
        "description": "Large quote with attribution",
        "tags": ["quote", "inspiration", "closing", "visual"],
        "preview_hint": "Large opening quotation mark, centered quote, attribution",
        "spec": {
            "type": "quote",
            "quote": "The stock market is a device for transferring money from the impatient to the patient.",
            "attribution": "Warren Buffett",
            "context": "A reminder that disciplined, long-term investing is our core philosophy.",
        },
    },
]


# =============================================================================
# TemplateRegistry
# =============================================================================

class TemplateRegistry:
    """
    Manages the slide template catalog.

    Built-in templates are defined in code above.
    User-custom templates are loaded from $STORAGE_ROOT/pptx_templates/{user_id}/*.json
    """

    def __init__(self):
        self._builtin: Dict[str, TemplateEntry] = {}
        self._load_builtins()

    # ──────────────────────────────────────────────────────────────────────────
    # Load
    # ──────────────────────────────────────────────────────────────────────────

    def _load_builtins(self) -> None:
        for t in _BUILTIN_TEMPLATES:
            entry = TemplateEntry(
                template_id=t["template_id"],
                name=t["name"],
                category=t["category"],
                slide_type=t["slide_type"],
                description=t["description"],
                tags=t.get("tags", []),
                spec=t.get("spec", {}),
                preview_hint=t.get("preview_hint", ""),
            )
            self._builtin[entry.template_id] = entry
        logger.debug("TemplateRegistry: loaded %d built-in templates", len(self._builtin))

    # ──────────────────────────────────────────────────────────────────────────
    # Query
    # ──────────────────────────────────────────────────────────────────────────

    def get_template(
        self,
        template_id: str,
        user_id:     Optional[str] = None,
    ) -> Optional[TemplateEntry]:
        """Get a template by ID (built-in first, then user templates)."""
        if template_id in self._builtin:
            return self._builtin[template_id]
        if user_id:
            return self._load_user_template(template_id, user_id)
        return None

    def search(
        self,
        query:         str = "",
        category:      Optional[str] = None,
        slide_type:    Optional[str] = None,
        user_id:       Optional[str] = None,
    ) -> List[TemplateEntry]:
        """Search templates by keyword, category, or slide_type."""
        results = list(self._builtin.values())

        # Add user templates
        if user_id:
            results.extend(self._load_all_user_templates(user_id))

        # Filter
        q = query.lower()
        filtered = []
        for t in results:
            if category and t.category != category:
                continue
            if slide_type and t.slide_type != slide_type:
                continue
            if q:
                searchable = f"{t.name} {t.description} {' '.join(t.tags)}".lower()
                if q not in searchable:
                    continue
            filtered.append(t)

        return filtered

    def get_catalog(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Return a summary catalog grouped by category."""
        all_templates = list(self._builtin.values())
        if user_id:
            all_templates.extend(self._load_all_user_templates(user_id))

        by_cat: Dict[str, List[Dict]] = {}
        for t in all_templates:
            by_cat.setdefault(t.category, []).append(t.to_dict(include_spec=False))

        return {
            "total": len(all_templates),
            "categories": {cat: sorted(ts, key=lambda x: x["name"])
                           for cat, ts in sorted(by_cat.items())},
        }

    def get_random(
        self,
        slide_type: Optional[str] = None,
        category:   Optional[str] = None,
    ) -> Optional[TemplateEntry]:
        """Return a random template matching the filters."""
        candidates = self.search(slide_type=slide_type, category=category)
        if not candidates:
            return None
        return random.choice(candidates)

    def get_by_slide_type(self, slide_type: str) -> List[TemplateEntry]:
        """Return all templates for a given slide type."""
        return self.search(slide_type=slide_type)

    # ──────────────────────────────────────────────────────────────────────────
    # User templates
    # ──────────────────────────────────────────────────────────────────────────

    def save_user_template(
        self,
        user_id:     str,
        name:        str,
        category:    str,
        slide_type:  str,
        spec:        Dict[str, Any],
        description: str = "",
        tags:        Optional[List[str]] = None,
    ) -> TemplateEntry:
        """Save a custom template for a user."""
        import uuid
        template_id = f"user_{user_id[:8]}_{uuid.uuid4().hex[:8]}"

        entry = TemplateEntry(
            template_id=template_id,
            name=name,
            category=category,
            slide_type=slide_type,
            description=description,
            tags=tags or [],
            spec=spec,
        )

        out_dir = _USER_TEMPLATES_DIR / user_id
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{template_id}.json").write_text(
            json.dumps(entry.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return entry

    def delete_user_template(self, template_id: str, user_id: str) -> bool:
        p = _USER_TEMPLATES_DIR / user_id / f"{template_id}.json"
        if p.exists():
            p.unlink(missing_ok=True)
            return True
        return False

    def _load_user_template(self, template_id: str, user_id: str) -> Optional[TemplateEntry]:
        p = _USER_TEMPLATES_DIR / user_id / f"{template_id}.json"
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return TemplateEntry(**data)
        except Exception as exc:
            logger.debug("Failed to load user template %s: %s", template_id, exc)
            return None

    def _load_all_user_templates(self, user_id: str) -> List[TemplateEntry]:
        user_dir = _USER_TEMPLATES_DIR / user_id
        if not user_dir.exists():
            return []
        templates = []
        for p in user_dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                templates.append(TemplateEntry(**data))
            except Exception:
                pass
        return templates


# ── Module-level singleton ────────────────────────────────────────────────────
_singleton: Optional[TemplateRegistry] = None


def get_template_registry() -> TemplateRegistry:
    """Return the shared TemplateRegistry singleton."""
    global _singleton
    if _singleton is None:
        _singleton = TemplateRegistry()
    return _singleton
