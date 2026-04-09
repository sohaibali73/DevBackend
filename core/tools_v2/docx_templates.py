"""
DOCX Templates
==============

Named document templates for `generate_docx`.  These are base spec structures
that are deep merged with the user's input.  The LLM only needs to provide
content, not layout structure.

Usage:
  In handle_generate_docx():
    from core.tools_v2.docx_templates import DOCX_TEMPLATES
    template_key = tool_input.get("template")
    if template_key and template_key in DOCX_TEMPLATES:
        base = DOCX_TEMPLATES[template_key]
        spec = deep_merge(base, tool_input)
"""

from typing import Dict, Any

# =============================================================================
# Template Helper: Deep Merge
# =============================================================================

def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively merge two dicts.  Values in `override` take precedence.
    Arrays are replaced, not appended.
    """
    result = base.copy()
    for k, v in override.items():
        if isinstance(v, dict) and k in result and isinstance(result[k], dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


# =============================================================================
# Named Templates
# =============================================================================

DOCX_TEMPLATES: Dict[str, Dict[str, Any]] = {

    # ─────────────────────────────────────────────────────────────────────────
    # 2-page fund fact sheet
    # ─────────────────────────────────────────────────────────────────────────
    "fund_fact_sheet": {
        "include_disclosure": True,
        "logo_variant": "standard",
        "header_line_color": "yellow",
        "sections": [
            { "type": "spacer", "size": 480 },
            {
                "type": "kpi_row",
                "metrics": [
                    { "value": "", "label": "YTD RETURN" },
                    { "value": "", "label": "1 YEAR" },
                    { "value": "", "label": "3 YEAR" },
                    { "value": "", "label": "5 YEAR" },
                ],
            },
            { "type": "spacer", "size": 360 },
            { "type": "heading", "level": 3, "text": "FUND OVERVIEW" },
            {
                "type": "two_column",
                "left": { "heading": "KEY CHARACTERISTICS" },
                "right": { "heading": "ALLOCATION" },
                "divider": True,
            },
            { "type": "spacer", "size": 240 },
            { "type": "heading", "level": 3, "text": "PERFORMANCE vs BENCHMARK" },
            {
                "type": "highlight_table",
                "headers": ["PERIOD", "FUND", "BENCHMARK", "DIFFERENCE"],
                "rows": [],
                "col_alignment": ["left", "right", "right", "right"],
                "auto_color_cols": [2, 3],
                "caption": "As of [DATE].  Performance shown net of fees.",
            },
            { "type": "page_break" },
            { "type": "heading", "level": 2, "text": "PORTFOLIO COMMENTARY" },
            { "type": "paragraph", "text": "" },
            { "type": "callout", "style": "yellow", "title": "KEY RISK FACTORS", "body": "" },
            { "type": "table", "headers": ["TICKER", "NAME", "WEIGHT"], "rows": [], "caption": "Top 10 Holdings" },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # Monthly market commentary (3–5 pages)
    # ─────────────────────────────────────────────────────────────────────────
    "market_commentary": {
        "include_disclosure": True,
        "logo_variant": "standard",
        "sections": [
            { "type": "spacer", "size": 480 },
            { "type": "kpi_row", "metrics": [
                { "value": "", "label": "S&P 500" },
                { "value": "", "label": "10Y TREASURY" },
                { "value": "", "label": "VIX" },
                { "value": "", "label": "USD INDEX" },
            ]},
            { "type": "spacer", "size": 360 },
            { "type": "heading", "level": 2, "text": "EXECUTIVE SUMMARY" },
            { "type": "paragraph", "text": "" },
            { "type": "page_break" },
            { "type": "heading", "level": 2, "text": "MARKET OVERVIEW" },
            { "type": "quote_block", "quote": "", "attribution": "" },
            { "type": "paragraph", "text": "" },
            { "type": "highlight_table", "headers": ["ASSET CLASS", "MONTHLY RETURN", "YTD", "1Y"], "rows": [], "auto_color_cols": [1, 2, 3] },
            { "type": "page_break" },
            { "type": "heading", "level": 2, "text": "FED & MONETARY POLICY" },
            { "type": "callout", "style": "light", "title": "RATE EXPECTATIONS", "body": "" },
            { "type": "paragraph", "text": "" },
            { "type": "page_break" },
            { "type": "heading", "level": 2, "text": "OUTLOOK" },
            { "type": "two_column",
              "left": { "heading": "BULL CASE", "body": "" },
              "right": { "heading": "BEAR CASE", "body": "" },
              "divider": True
            },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # Quarterly performance report (4–6 pages)
    # ─────────────────────────────────────────────────────────────────────────
    "performance_report": {
        "include_disclosure": True,
        "logo_variant": "standard",
        "sections": [
            { "type": "spacer", "size": 480 },
            { "type": "kpi_row", "metrics": [
                { "value": "", "label": "ACCOUNT VALUE" },
                { "value": "", "label": "QUARTER RETURN" },
                { "value": "", "label": "YTD RETURN" },
                { "value": "", "label": "SINCE INCEPTION" },
            ]},
            { "type": "page_break" },
            { "type": "heading", "level": 2, "text": "PERFORMANCE ATTRIBUTION" },
            { "type": "highlight_table", "headers": ["SECTOR", "ALLOCATION", "CONTRIBUTION", "BENCHMARK"], "rows": [], "col_alignment": ["left", "right", "right", "right"] },
            { "type": "spacer", "size": 240 },
            { "type": "heading", "level": 3, "text": "KEY DRIVERS" },
            { "type": "bullets", "items": [] },
            { "type": "spacer", "size": 240 },
            { "type": "heading", "level": 3, "text": "DETRACTORS" },
            { "type": "bullets", "items": [] },
            { "type": "page_break" },
            { "type": "heading", "level": 2, "text": "PORTFOLIO CHARACTERISTICS" },
            { "type": "table", "headers": ["", "VALUE"], "rows": [] },
            { "type": "page_break" },
            { "type": "heading", "level": 2, "text": "TRANSACTIONS THIS QUARTER" },
            { "type": "table", "headers": ["ACTION", "TICKER", "NAME", "DATE", "QUANTITY"], "rows": [] },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # Client letter (1–2 pages)
    # ─────────────────────────────────────────────────────────────────────────
    "client_letter": {
        "include_disclosure": True,
        "logo_variant": "standard",
        "sections": [
            { "type": "spacer", "size": 480 },
            { "type": "paragraph", "text": "[DATE]" },
            { "type": "spacer", "size": 240 },
            { "type": "paragraph", "text": "Dear [CLIENT NAME]," },
            { "type": "spacer", "size": 120 },
            { "type": "paragraph", "text": "" },
            { "type": "paragraph", "text": "" },
            { "type": "paragraph", "text": "" },
            { "type": "callout", "style": "light", "title": "QUARTER HIGHLIGHTS", "body": "" },
            { "type": "paragraph", "text": "" },
            { "type": "paragraph", "text": "Sincerely," },
            { "type": "spacer", "size": 360 },
            { "type": "paragraph", "text": "Potomac Investment Management" },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # Research report / white paper (5–10 pages)
    # ─────────────────────────────────────────────────────────────────────────
    "research_report": {
        "include_disclosure": True,
        "logo_variant": "standard",
        "sections": [
            { "type": "spacer", "size": 480 },
            { "type": "heading", "level": 1, "text": "EXECUTIVE SUMMARY" },
            { "type": "paragraph", "text": "" },
            { "type": "page_break" },
            { "type": "toc", "depth": 2, "title": "TABLE OF CONTENTS" },
            { "type": "page_break" },
            { "type": "heading", "level": 1, "text": "INTRODUCTION" },
            { "type": "paragraph", "text": "" },
            { "type": "page_break" },
            { "type": "heading", "level": 1, "text": "ANALYSIS" },
            { "type": "highlight_table", "headers": [], "rows": [], "caption": "" },
            { "type": "paragraph", "text": "" },
            { "type": "quote_block", "quote": "", "attribution": "" },
            { "type": "page_break" },
            { "type": "heading", "level": 1, "text": "CONCLUSION" },
            { "type": "paragraph", "text": "" },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # Investment proposal (5–8 pages)
    # ─────────────────────────────────────────────────────────────────────────
    "proposal": {
        "include_disclosure": False,
        "logo_variant": "black",
        "header_line_color": "dark",
        "sections": [
            { "type": "spacer", "size": 480 },
            { "type": "heading", "level": 2, "text": "EXECUTIVE SUMMARY" },
            { "type": "kpi_row", "metrics": [
                { "value": "", "label": "TARGET RETURN" },
                { "value": "", "label": "MAX DRAWDOWN" },
                { "value": "", "label": "TIME HORIZON" },
                { "value": "", "label": "MINIMUM INVESTMENT" },
            ]},
            { "type": "page_break" },
            { "type": "heading", "level": 2, "text": "INVESTMENT OBJECTIVE" },
            { "type": "paragraph", "text": "" },
            { "type": "callout", "style": "yellow", "title": "STRATEGY OVERVIEW", "body": "" },
            { "type": "page_break" },
            { "type": "heading", "level": 2, "text": "RISK MANAGEMENT FRAMEWORK" },
            { "type": "two_column",
              "left": { "heading": "RISK CONTROLS", "body": "" },
              "right": { "heading": "CONSTRAINTS", "body": "" },
              "divider": True
            },
            { "type": "page_break" },
            { "type": "heading", "level": 2, "text": "FEES & TERMS" },
            { "type": "table", "headers": ["FEE TYPE", "RATE"], "rows": [] },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # Trade rationale memo (1–2 pages)
    # ─────────────────────────────────────────────────────────────────────────
    "trade_rationale": {
        "include_disclosure": True,
        "logo_variant": "standard",
        "sections": [
            { "type": "spacer", "size": 480 },
            { "type": "kpi_row", "metrics": [
                { "value": "", "label": "TICKER" },
                { "value": "", "label": "ACTION" },
                { "value": "", "label": "QUANTITY" },
                { "value": "", "label": "ENTRY PRICE" },
            ]},
            { "type": "spacer", "size": 360 },
            { "type": "heading", "level": 3, "text": "BACKGROUND" },
            { "type": "paragraph", "text": "" },
            { "type": "heading", "level": 3, "text": "INVESTMENT THESIS" },
            { "type": "bullets", "items": [] },
            { "type": "heading", "level": 3, "text": "RISK CONSIDERATIONS" },
            { "type": "callout", "style": "light", "title": "STOP LOSS", "body": "" },
            { "type": "heading", "level": 3, "text": "EXIT CRITERIA" },
            { "type": "bullets", "items": [] },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # Meeting minutes (1–3 pages)
    # ─────────────────────────────────────────────────────────────────────────
    "meeting_minutes": {
        "include_disclosure": False,
        "logo_variant": "standard",
        "sections": [
            { "type": "spacer", "size": 480 },
            { "type": "table", "headers": ["", ""], "rows": [
                ["DATE", ""],
                ["TIME", ""],
                ["ATTENDEES", ""],
                ["LOCATION", ""],
            ]},
            { "type": "spacer", "size": 360 },
            { "type": "heading", "level": 2, "text": "DISCUSSION" },
            { "type": "paragraph", "text": "" },
            { "type": "heading", "level": 2, "text": "ACTION ITEMS" },
            { "type": "numbered", "items": [] },
            { "type": "heading", "level": 2, "text": "NEXT STEPS" },
            { "type": "bullets", "items": [] },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # New client onboarding packet (3–5 pages)
    # ─────────────────────────────────────────────────────────────────────────
    "onboarding_packet": {
        "include_disclosure": True,
        "logo_variant": "standard",
        "sections": [
            { "type": "spacer", "size": 480 },
            { "type": "heading", "level": 2, "text": "WELCOME TO POTOMAC" },
            { "type": "paragraph", "text": "" },
            { "type": "callout", "style": "yellow", "title": "NEXT STEPS", "body": "1. Sign account opening documents\n2. Fund your account\n3. Schedule introductory call" },
            { "type": "page_break" },
            { "type": "heading", "level": 2, "text": "ACCOUNT SETUP" },
            { "type": "table", "headers": ["ITEM", "DEADLINE", "RESPONSIBLE"], "rows": [] },
            { "type": "page_break" },
            { "type": "heading", "level": 2, "text": "OUR SERVICE MODEL" },
            { "type": "two_column",
              "left": { "heading": "COMMUNICATION", "body": "" },
              "right": { "heading": "REPORTING", "body": "" },
              "divider": True
            },
            { "type": "page_break" },
            { "type": "heading", "level": 2, "text": "KEY CONTACTS" },
            { "type": "table", "headers": ["NAME", "TITLE", "EMAIL", "PHONE"], "rows": [] },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # Quarterly review letter (4–8 pages)
    # ─────────────────────────────────────────────────────────────────────────
    "quarterly_review": {
        "include_disclosure": True,
        "logo_variant": "standard",
        "sections": [
            { "type": "spacer", "size": 480 },
            { "type": "paragraph", "text": "[DATE]" },
            { "type": "spacer", "size": 240 },
            { "type": "paragraph", "text": "Dear Valued Client," },
            { "type": "spacer", "size": 120 },
            { "type": "kpi_row", "metrics": [
                { "value": "", "label": "ACCOUNT VALUE" },
                { "value": "", "label": "QUARTER RETURN" },
                { "value": "", "label": "YTD RETURN" },
                { "value": "", "label": "INCEPTION RETURN" },
            ]},
            { "type": "page_break" },
            { "type": "heading", "level": 2, "text": "PERFORMANCE SUMMARY" },
            { "type": "highlight_table", "headers": ["", "FUND", "BENCHMARK"], "rows": [], "auto_color_cols": [1, 2], "caption": "Net of fees." },
            { "type": "page_break" },
            { "type": "heading", "level": 2, "text": "MARKET COMMENTARY" },
            { "type": "paragraph", "text": "" },
            { "type": "page_break" },
            { "type": "heading", "level": 2, "text": "LOOKING FORWARD" },
            { "type": "paragraph", "text": "" },
            { "type": "callout", "style": "light", "title": "SCHEDULE YOUR REVIEW CALL", "body": "To discuss your portfolio in detail, please schedule a call at your convenience." },
        ],
    },

}


# =============================================================================
# Template Metadata
# =============================================================================

TEMPLATE_METADATA = {
    "fund_fact_sheet": {
        "name": "Fund Fact Sheet",
        "pages": "2",
        "use_case": "Monthly fund summary with KPIs + performance table",
        "default_logo": "standard",
    },
    "market_commentary": {
        "name": "Market Commentary",
        "pages": "3–5",
        "use_case": "Monthly market outlook",
        "default_logo": "standard",
    },
    "performance_report": {
        "name": "Performance Report",
        "pages": "4–6",
        "use_case": "Quarterly performance attribution",
        "default_logo": "standard",
    },
    "client_letter": {
        "name": "Client Letter",
        "pages": "1–2",
        "use_case": "Personalized client correspondence",
        "default_logo": "standard",
    },
    "research_report": {
        "name": "Research Report",
        "pages": "5–10",
        "use_case": "White paper / research publication",
        "default_logo": "standard",
    },
    "proposal": {
        "name": "Investment Proposal",
        "pages": "5–8",
        "use_case": "New client investment proposal",
        "default_logo": "black",
    },
    "trade_rationale": {
        "name": "Trade Rationale Memo",
        "pages": "1–2",
        "use_case": "Trade decision documentation",
        "default_logo": "standard",
    },
    "meeting_minutes": {
        "name": "Meeting Minutes",
        "pages": "1–3",
        "use_case": "Meeting record and action items",
        "default_logo": "standard",
    },
    "onboarding_packet": {
        "name": "Client Onboarding Packet",
        "pages": "3–5",
        "use_case": "New client welcome document",
        "default_logo": "standard",
    },
    "quarterly_review": {
        "name": "Quarterly Client Review",
        "pages": "4–8",
        "use_case": "Quarterly portfolio review letter",
        "default_logo": "standard",
    },
}
