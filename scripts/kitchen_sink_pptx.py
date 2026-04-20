"""
PPTX Sandbox v2 — Kitchen Sink
==============================
Generates a comprehensive test deck exercising every template, every slide
mode (template / hybrid / freestyle), both themes (light / dark), and each
canvas preset (wide / standard / hd16_9 / a4_landscape).

Purpose: gives you one file to scroll through to spot visual regressions,
spacing issues, or template bugs.

Usage
-----
    python scripts/kitchen_sink_pptx.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.sandbox.pptx_sandbox import PptxSandbox  # noqa: E402


# ── Each entry mirrors the keys of the spec.slides[] schema ──────────────────
SLIDES = [
    # ── 1. TITLE (light) ──────────────────────────────────────────────────
    {
        "mode": "template", "template": "title",
        "data": {
            "title":    "POTOMAC KITCHEN SINK",
            "subtitle": "Every template, theme & mode in one deck",
            "tagline":  "Built to Conquer Risk",
            "style":    "executive",
        },
    },
    # ── 2. TITLE (dark) ───────────────────────────────────────────────────
    {
        "mode": "template", "template": "title",
        "data": {
            "title":    "DARK THEME TITLE",
            "subtitle": "Same template, different background",
            "theme":    "dark",
        },
    },
    # ── 3. TITLE_CARD ─────────────────────────────────────────────────────
    {
        "mode": "template", "template": "title_card",
        "data": {
            "title":        "INVESTMENT STRATEGIES",
            "title_accent": "AND SOLUTIONS",
            "subtitle":     "AT POTOMAC FUND MANAGEMENT",
            "tagline":      "STRATEGY OVERVIEW",
            "body":         "Tactical, risk-managed portfolios for any market environment.",
            "footer":       "Confidential — For Internal Use",
        },
    },
    # ── 4. SECTION DIVIDER (dark) ─────────────────────────────────────────
    {
        "mode": "template", "template": "section_divider",
        "data": {
            "title":       "SECTION DIVIDER",
            "description": "Use between major sections of a longer deck.",
            "theme":       "dark",
        },
    },
    # ── 5. CONTENT (bullets, light) ───────────────────────────────────────
    {
        "mode": "template", "template": "content",
        "data": {
            "title":    "CONTENT — BULLETS",
            "subtitle": "Standard list layout",
            "bullets": [
                "Bullet one — concise, action-oriented copy.",
                "Bullet two — supports up to ~10 items comfortably.",
                "Bullet three — auto-fits font to the remaining space.",
                "Bullet four — keeps hierarchy flat for readability.",
            ],
        },
    },
    # ── 6. CONTENT (prose, dark) ──────────────────────────────────────────
    {
        "mode": "template", "template": "content",
        "data": {
            "title": "CONTENT — PROSE (DARK)",
            "text": (
                "A single block of body copy wraps inside the standard "
                "chrome area. Font size is chosen via binary search so the "
                "text fills — but does not overflow — the available box. "
                "Switch to dark theme by setting theme:'dark' on the slide."
            ),
            "theme": "dark",
        },
    },
    # ── 7. TWO COLUMN ─────────────────────────────────────────────────────
    {
        "mode": "template", "template": "two_column",
        "data": {
            "title":         "TWO COLUMN",
            "left_header":   "LEFT",
            "left_content":  "Left column — used for pros, bull case, option A, etc.",
            "right_header":  "RIGHT",
            "right_content": "Right column — used for cons, bear case, option B, etc.",
        },
    },
    # ── 8. METRICS GRID ───────────────────────────────────────────────────
    {
        "mode": "template", "template": "metrics",
        "data": {
            "title":   "KEY METRICS",
            "columns": 4,
            "metrics": [
                {"value": "24%", "label": "YTD Return"},
                {"value": "0.92", "label": "Sharpe"},
                {"value": "-8%",  "label": "Max Drawdown"},
                {"value": "$2.4B", "label": "AUM"},
                {"value": "412",   "label": "Accounts"},
                {"value": "12yrs", "label": "Track Record"},
                {"value": "4.8/5", "label": "Advisor NPS"},
                {"value": "1.02",  "label": "Beta"},
            ],
            "context": "As of Q3 2026 — net of fees, USD.",
        },
    },
    # ── 9. STAT CARDS ─────────────────────────────────────────────────────
    {
        "mode": "template", "template": "stat_cards",
        "data": {
            "title": "STAT CARDS",
            "intro": "Three dark cards with a yellow eyebrow and big stat.",
            "cards": [
                {"label": "GROWTH",      "value": "+38%",  "description": "Trailing 3-year gross CAGR"},
                {"label": "DRAWDOWN",    "value": "-6.1%", "description": "Max peak-to-trough on the flagship sleeve"},
                {"label": "CONVICTION",  "value": "93%",   "description": "% of positions with full model agreement"},
            ],
        },
    },
    # ── 10. HEX ROW ───────────────────────────────────────────────────────
    {
        "mode": "template", "template": "hex_row",
        "data": {
            "title":    "HEX ROW — STRATEGIES",
            "subtitle": "Tactical sleeves spanning two decades",
            "tiles": [
                {"label": "FIRST STEP",  "subline": "2002"},
                {"label": "EVOLUTION",   "subline": "2010"},
                {"label": "OPPORTUNITY", "subline": "2015"},
                {"label": "INSIGHT",     "subline": "2020"},
                {"label": "ATLAS",       "subline": "2024"},
            ],
        },
    },
    # ── 11. TEAM TRIAD ────────────────────────────────────────────────────
    {
        "mode": "template", "template": "team_triad",
        "data": {
            "title":  "TEAM TRIAD",
            "glyphs": ["+", "="],
            "cards": [
                {"pill": "RESEARCH",  "body": "Investment due diligence and fund monitoring."},
                {"pill": "PORTFOLIO", "body": "Allocation, execution and rebalancing."},
                {"pill": "RISK",      "body": "Systematic drawdown control & volatility sizing."},
            ],
        },
    },
    # ── 12. TABLE ─────────────────────────────────────────────────────────
    {
        "mode": "template", "template": "table",
        "data": {
            "title":   "PERFORMANCE TABLE",
            "headers": ["Strategy", "1Y", "3Y (ann.)", "5Y (ann.)", "Since Inception"],
            "rows": [
                ["First Step",     "18.2%",  "12.4%", "11.8%", "9.7%"],
                ["Evolution",      "22.1%",  "14.0%", "13.5%", "11.2%"],
                ["Opportunity",    "28.7%",  "17.2%", "15.1%", "13.4%"],
                ["Insight",        "24.3%",  "15.5%", "—",     "14.0%"],
                ["Atlas",          "11.6%",  "—",     "—",     "11.6%"],
            ],
        },
    },
    # ── 13. CHART — BAR ───────────────────────────────────────────────────
    {
        "mode": "template", "template": "chart",
        "data": {
            "title":      "CHART — BAR",
            "chart_type": "bar",
            "categories": ["Q1", "Q2", "Q3", "Q4"],
            "series": [
                {"name": "2025", "values": [8.2, 10.5, 6.7, 12.1]},
                {"name": "2026", "values": [9.1, 11.3, 8.0, 13.4]},
            ],
        },
    },
    # ── 14. CHART — LINE ──────────────────────────────────────────────────
    {
        "mode": "template", "template": "chart",
        "data": {
            "title":      "CHART — LINE",
            "chart_type": "line",
            "categories": ["2020", "2021", "2022", "2023", "2024", "2025"],
            "series": [
                {"name": "Strategy", "values": [100, 118, 102, 131, 146, 172]},
                {"name": "Benchmark","values": [100, 112, 95,  121, 130, 151]},
            ],
        },
    },
    # ── 15. CHART — DONUT ─────────────────────────────────────────────────
    {
        "mode": "template", "template": "chart",
        "data": {
            "title":      "CHART — DONUT",
            "chart_type": "donut",
            "labels":     ["US Equity", "Intl Equity", "Fixed Income", "Alternatives", "Cash"],
            "values":     [42, 18, 22, 12, 6],
        },
    },
    # ── 16. QUOTE ─────────────────────────────────────────────────────────
    {
        "mode": "template", "template": "quote",
        "data": {
            "quote": "Risk comes from not knowing what you're doing.",
            "attribution": "Warren Buffett",
            "context": "Annual Letter — 1993",
        },
    },
    # ── 17. CTA FRAMED ────────────────────────────────────────────────────
    {
        "mode": "template", "template": "cta_framed",
        "data": {
            "title_top":    "BUILT TO",
            "title_bottom": "CONQUER RISK",
            "cta_label":    "NEXT STEPS",
            "steps": [
                "Review risk tolerance",
                "Select matching strategy sleeve",
                "Onboard via advisor portal",
            ],
            "url": "potomacfund.com",
        },
    },
    # ── 18. CTA FRAMED (DARK) ─────────────────────────────────────────────
    {
        "mode": "template", "template": "cta_framed",
        "data": {
            "title_top":    "DARK",
            "title_bottom": "CTA VARIANT",
            "cta_label":    "LEARN MORE",
            "steps": ["Schedule a demo", "Book a discovery call"],
            "url": "potomacfund.com/contact",
            "theme": "dark",
        },
    },
    # ── 19. HYBRID (template + customize JS) ──────────────────────────────
    {
        "mode": "hybrid", "template": "content",
        "data": {
            "title":   "HYBRID MODE",
            "bullets": [
                "template = 'content' renders normal bullets",
                "customize JS adds the yellow badge below",
                "Use for small tweaks without going full freestyle",
            ],
        },
        "customize": (
            "const c = engine.rects.content();"
            "const b = { x: c.x, y: c.y + c.h - engine.H*0.09, w: engine.W*0.28, h: engine.H*0.06 };"
            "prim.pill(slide, b, { fill: 'YELLOW', label: 'CUSTOMIZED ✓' });"
        ),
    },
    # ── 20. FREESTYLE (hand-drawn 2×2 matrix) ─────────────────────────────
    {
        "mode": "freestyle",
        "code": (
            "const b = prim.standardChrome(slide, { title: 'FREESTYLE 2×2 MATRIX' });"
            "const g = engine.grid(2, 2, b);"
            "const cells = ["
            "  {col:0,row:0, label:'HIGH RETURN / LOW RISK', fill:'YELLOW'},"
            "  {col:1,row:0, label:'HIGH RETURN / HIGH RISK', fill:'YELLOW_80'},"
            "  {col:0,row:1, label:'LOW RETURN / LOW RISK',   fill:'GRAY_20'},"
            "  {col:1,row:1, label:'LOW RETURN / HIGH RISK',  fill:'RED'},"
            "];"
            "cells.forEach(c => {"
            "  const r = g.cell(c.col, c.row);"
            "  prim.rect(slide, r, { fill: c.fill, stroke:'DARK_GRAY', strokeW:1,"
            "    label: c.label,"
            "    labelOpts:{ bold:true, align:'center', valign:'middle', color:'DARK_GRAY' } });"
            "});"
        ),
    },
    # ── 21. FREESTYLE (dynamic hub+spokes) ────────────────────────────────
    {
        "mode": "freestyle",
        "code": (
            "const b = prim.standardChrome(slide, { title: 'FREESTYLE — HUB & SPOKES' });"
            "const cx = b.x + b.w/2, cy = b.y + b.h/2;"
            "const r = Math.min(b.w, b.h) * 0.38;"
            "const hub = { x: cx - 0.7, y: cy - 0.35, w: 1.4, h: 0.7 };"
            "prim.pill(slide, hub, { fill:'YELLOW', label:'CORE' });"
            "const spokes = ['RESEARCH','EXECUTION','RISK','OPS','COMPLIANCE','CLIENT'];"
            "spokes.forEach((s,i) => {"
            "  const a = (i / spokes.length) * Math.PI * 2 - Math.PI/2;"
            "  const px = cx + Math.cos(a) * r, py = cy + Math.sin(a) * r;"
            "  const box = { x: px - 0.85, y: py - 0.3, w: 1.7, h: 0.6 };"
            "  prim.roundRect(slide, box, { fill:'WHITE', stroke:'DARK_GRAY', strokeW:1, radiusFrac:0.2, label:s,"
            "    labelOpts:{ bold:true, align:'center', valign:'middle', color:'DARK_GRAY' } });"
            "  prim.connector(slide, { x: cx, y: cy }, { x: px, y: py }, { color:'GRAY_40' });"
            "});"
        ),
    },
    # ── 22. IMAGE SLIDE (stock brand logo as demo image) ──────────────────
    # The `full` logo will be rendered through the `image` template by
    # referencing an asset_key; the Python side injects the data URL.
    {
        "mode": "template", "template": "image",
        "data": {
            "title":   "IMAGE SLIDE",
            "image_key": "potomac_full",
            "aspect":  4.768,
            "caption": "Asset_key → auto-resolved via asset_registry (Potomac wordmark shown).",
        },
    },
]


def build_full_spec(canvas_preset: str, slides: list) -> dict:
    return {
        "title": f"Potomac Kitchen Sink ({canvas_preset})",
        "filename": f"kitchen_sink_{canvas_preset}.pptx",
        "canvas": {"preset": canvas_preset},
        # Always resolve the Potomac wordmark for the IMAGE SLIDE
        "asset_keys": ["potomac_full"],
        "slides": slides,
    }


def _write(path: Path, data: bytes) -> Path:
    """Write bytes, fall back to a timestamped file if locked by PowerPoint."""
    try:
        path.write_bytes(data)
        return path
    except PermissionError:
        alt = path.with_name(path.stem + f"_{int(time.time())}" + path.suffix)
        alt.write_bytes(data)
        return alt


def main() -> int:
    sandbox = PptxSandbox()

    targets = [
        ("wide",         True),   # full kitchen sink
        ("standard",     False),  # canvas-size regression (subset)
        ("hd16_9",       False),
        ("a4_landscape", False),
    ]

    subset = [
        SLIDES[0],       # title
        SLIDES[2],       # title_card
        SLIDES[9],       # hex_row
        SLIDES[10],      # team_triad
        SLIDES[16],      # cta_framed
    ]

    for preset, full in targets:
        slides = SLIDES if full else subset
        spec = build_full_spec(preset, slides)
        print(f"\n→ Rendering preset={preset} slides={len(slides)} …")
        result = sandbox.generate(spec)
        if not result.success:
            print(f"  ✗ failed: {result.error}")
            for w in result.warnings or []:
                print(f"   WARN: {w}")
            continue
        out = _write(ROOT / f"kitchen_sink_{preset}.pptx", result.data)
        print(
            f"  ✓ {out.name}  "
            f"{len(result.data)/1024:.1f} KB  "
            f"{result.exec_time_ms:.0f}ms  "
            f"canvas={result.canvas}"
        )
        if result.warnings:
            print(f"    ({len(result.warnings)} warnings)")
            for w in result.warnings[:5]:
                print(f"     - {w}")

    print("\nDone. Open the `.pptx` files in PowerPoint to review.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
