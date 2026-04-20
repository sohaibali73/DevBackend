"""
PPTX Sandbox v2 — Mega Showcase
================================
Builds a single huge .pptx that exercises:
  • every named template (core + extras)         ~40 templates
  • every theme (light, dark, yellow, cream, slate, midnight, mono, forest, sunset, minimal)
  • every extra primitive (arrow, ribbon, star, badge, sticky, speech, tab,
    progress bar, KPI card, timeline dot, rating stars, callout, iconBox,
    checkCircle, band)
  • many freestyle compositions

End result is `mega_showcase.pptx` — a single deck with 200+ slides
so you can scroll through and review every pattern in one place.

Usage
-----
    python scripts/mega_showcase_pptx.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.sandbox.pptx_sandbox import PptxSandbox  # noqa: E402


THEMES = [
    "light", "dark", "yellow", "cream", "slate",
    "midnight", "mono", "forest", "sunset", "minimal",
]


# ═══════════════════════════════════════════════════════════════════════════
# Per-theme showcase — a compact "all templates" loop repeated per theme
# ═══════════════════════════════════════════════════════════════════════════

def theme_showcase(theme: str) -> list:
    """Return ~25 template slides all set to the same theme."""
    return [
        {"mode": "template", "template": "title",
         "data": {"title": f"THEME — {theme.upper()}", "subtitle": "Showcase deck",
                  "tagline": "Built to Conquer Risk", "style": "executive",
                  "theme": theme}},
        {"mode": "template", "template": "title_card",
         "data": {"title": "INVESTMENT STRATEGIES", "title_accent": "AND SOLUTIONS",
                  "subtitle": "AT POTOMAC FUND MANAGEMENT",
                  "tagline": "STRATEGY OVERVIEW",
                  "body": "Tactical, risk-managed portfolios for any market environment.",
                  "footer": "Confidential — For Internal Use", "theme": theme}},
        {"mode": "template", "template": "section_divider",
         "data": {"title": "PART ONE", "description": "The road ahead", "theme": theme}},
        {"mode": "template", "template": "content",
         "data": {"title": "CONTENT — BULLETS", "theme": theme,
                  "bullets": ["First bullet — autofit resizes as needed.",
                              "Second bullet — no hardcoded pt sizes.",
                              "Third bullet — ellipsis handled by box clamp.",
                              "Fourth bullet — yellow accent remains legible."]}},
        {"mode": "template", "template": "content",
         "data": {"title": "CONTENT — PROSE", "theme": theme,
                  "text": "Long-form body copy renders inside the standard chrome area. "
                          "Font size is chosen by binary-search autofit."}},
        {"mode": "template", "template": "two_column",
         "data": {"title": "TWO COLUMN", "theme": theme,
                  "left_header": "PROS", "left_content": "Risk-adjusted returns.",
                  "right_header": "CONS", "right_content": "Higher tracking error."}},
        {"mode": "template", "template": "metrics",
         "data": {"title": "METRICS", "theme": theme, "columns": 4,
                  "metrics": [{"value": "24%", "label": "Return"},
                              {"value": "0.92", "label": "Sharpe"},
                              {"value": "-8%", "label": "MDD"},
                              {"value": "$2.4B", "label": "AUM"}]}},
        {"mode": "template", "template": "stat_cards",
         "data": {"title": "STAT CARDS", "theme": theme,
                  "cards": [{"label": "GROWTH", "value": "+38%", "description": "3Y CAGR"},
                            {"label": "DRAWDOWN", "value": "-6%", "description": "Max DD"},
                            {"label": "CONVICTION", "value": "93%", "description": "Signal"}]}},
        {"mode": "template", "template": "hex_row",
         "data": {"title": "HEX ROW", "theme": theme,
                  "tiles": [{"label": "FIRST", "subline": "2002"},
                            {"label": "NEXT",  "subline": "2010"},
                            {"label": "GROW",  "subline": "2015"},
                            {"label": "SCALE", "subline": "2020"}]}},
        {"mode": "template", "template": "team_triad",
         "data": {"title": "TEAM TRIAD", "theme": theme, "glyphs": ["+", "="],
                  "cards": [{"pill": "RESEARCH", "body": "Due diligence & monitoring."},
                            {"pill": "PORTFOLIO", "body": "Allocation & rebalancing."},
                            {"pill": "RISK", "body": "Drawdown & vol control."}]}},
        {"mode": "template", "template": "table",
         "data": {"title": "TABLE", "theme": theme,
                  "headers": ["Strategy", "1Y", "3Y", "5Y"],
                  "rows": [["First Step", "18%", "12%", "11%"],
                           ["Evolution",  "22%", "14%", "13%"],
                           ["Opportunity","28%", "17%", "15%"]]}},
        {"mode": "template", "template": "chart",
         "data": {"title": "CHART — BAR", "theme": theme, "chart_type": "bar",
                  "categories": ["Q1","Q2","Q3","Q4"],
                  "series": [{"name": "2025", "values": [8,10,6,12]},
                             {"name": "2026", "values": [9,11,8,13]}]}},
        {"mode": "template", "template": "chart",
         "data": {"title": "CHART — LINE", "theme": theme, "chart_type": "line",
                  "categories": ["2020","2021","2022","2023","2024"],
                  "series": [{"name": "Strategy", "values": [100,118,102,131,146]},
                             {"name": "Bench",   "values": [100,112,95,121,130]}]}},
        {"mode": "template", "template": "chart",
         "data": {"title": "CHART — DONUT", "theme": theme, "chart_type": "donut",
                  "labels": ["US","Intl","Fixed","Alts","Cash"],
                  "values": [42, 18, 22, 12, 6]}},
        {"mode": "template", "template": "quote",
         "data": {"theme": theme,
                  "quote": "Risk comes from not knowing what you're doing.",
                  "attribution": "Warren Buffett", "context": "1993"}},
        {"mode": "template", "template": "cta_framed",
         "data": {"theme": theme,
                  "title_top": "BUILT TO", "title_bottom": "CONQUER RISK",
                  "cta_label": "NEXT STEPS",
                  "steps": ["Review risk", "Pick sleeve", "Onboard"],
                  "url": "potomacfund.com"}},
        # ── Extras ─────────────────────────────────────────────────────────
        {"mode": "template", "template": "agenda",
         "data": {"title": "AGENDA", "theme": theme,
                  "items": [{"title": "Kick-off", "description": "Goals and context."},
                            {"title": "Strategy",  "description": "Market view."},
                            {"title": "Execution", "description": "Trade plan."},
                            {"title": "Risk",      "description": "Guardrails."}]}},
        {"mode": "template", "template": "timeline",
         "data": {"title": "TIMELINE", "theme": theme,
                  "events": [{"label": "Founded", "date": "2002"},
                             {"label": "Launch",  "date": "2010"},
                             {"label": "Scale",   "date": "2015"},
                             {"label": "Atlas",   "date": "2024"}]}},
        {"mode": "template", "template": "process",
         "data": {"title": "PROCESS", "theme": theme,
                  "steps": [{"label": "RESEARCH", "description": "Analyze"},
                            {"label": "DESIGN",   "description": "Shape portfolio"},
                            {"label": "DEPLOY",   "description": "Execute"},
                            {"label": "MONITOR",  "description": "Measure"}]}},
        {"mode": "template", "template": "swot",
         "data": {"title": "SWOT", "theme": theme,
                  "strengths":     ["Seasoned team", "Proven track record"],
                  "weaknesses":    ["Limited int'l footprint"],
                  "opportunities": ["RIA channel growth", "Alts demand"],
                  "threats":       ["Rate volatility", "Fee compression"]}},
        {"mode": "template", "template": "matrix_2x2",
         "data": {"title": "EISENHOWER MATRIX", "theme": theme,
                  "xAxis": "Importance", "yAxis": "Urgency",
                  "quadrants": [
                      {"label": "DO NOW",    "items": ["Client ask", "Trade error"]},
                      {"label": "SCHEDULE",  "items": ["Research", "Planning"]},
                      {"label": "DELEGATE",  "items": ["Reporting"]},
                      {"label": "DROP",      "items": ["Low-value mtgs"]},
                  ]}},
        {"mode": "template", "template": "funnel",
         "data": {"title": "FUNNEL", "theme": theme,
                  "stages": [{"label": "AWARENESS", "value": "100k"},
                             {"label": "INTEREST",  "value": "25k"},
                             {"label": "CONSIDER",  "value": "8k"},
                             {"label": "CONVERT",   "value": "1.2k"},
                             {"label": "RETAIN",    "value": "900"}]}},
        {"mode": "template", "template": "roadmap",
         "data": {"title": "ROADMAP 2026", "theme": theme,
                  "phases": ["Q1", "Q2", "Q3", "Q4"],
                  "tracks": [
                      {"name": "Platform",
                       "milestones": [{"phase": "Q1", "label": "DB migration"},
                                      {"phase": "Q3", "label": "API v2"}]},
                      {"name": "Research",
                       "milestones": [{"phase": "Q2", "label": "Factor lib"},
                                      {"phase": "Q4", "label": "Alt data"}]},
                      {"name": "Client",
                       "milestones": [{"phase": "Q2", "label": "Portal rev"}]},
                  ]}},
        {"mode": "template", "template": "kpi_dashboard",
         "data": {"title": "KPI DASHBOARD", "theme": theme, "columns": 4,
                  "cards": [
                      {"value": "$2.4B", "label": "AUM",     "delta": "+12%", "delta_sign": "up"},
                      {"value": "412",   "label": "ACCOUNTS","delta": "+4%",  "delta_sign": "up"},
                      {"value": "0.92",  "label": "SHARPE",  "delta": "-0.03","delta_sign": "down"},
                      {"value": "4.8",   "label": "NPS",     "delta": "+0.2", "delta_sign": "up"},
                  ]}},
        {"mode": "template", "template": "pricing_tiers",
         "data": {"title": "PRICING", "theme": theme,
                  "tiers": [
                      {"name": "STARTER", "price": "$0", "period": "forever",
                       "features": ["1 portfolio", "Daily reports", "Email support"],
                       "cta": "Start free"},
                      {"name": "PRO",     "price": "$149", "period": "/mo",
                       "highlighted": True,
                       "features": ["10 portfolios", "Real-time risk", "Priority support"],
                       "cta": "Upgrade"},
                      {"name": "ENTERPRISE","price": "Custom", "period": "contact us",
                       "features": ["Unlimited", "SSO/SAML", "Dedicated CSM", "Custom SLAs"],
                       "cta": "Talk to sales"},
                  ]}},
        {"mode": "template", "template": "testimonial",
         "data": {"theme": theme,
                  "quote": "Potomac has been our trusted partner in risk management for over a decade.",
                  "author": "Jane Thompson",
                  "role": "CIO, Riverstone Wealth"}},
        {"mode": "template", "template": "team_grid",
         "data": {"title": "LEADERSHIP", "theme": theme, "columns": 4,
                  "members": [
                      {"name": "Avery Chen",   "title": "CIO"},
                      {"name": "Marcus Patel", "title": "Head of Research"},
                      {"name": "Sofia Reyes",  "title": "PM"},
                      {"name": "Ethan Kim",    "title": "Risk"},
                  ]}},
        {"mode": "template", "template": "big_number",
         "data": {"theme": theme, "eyebrow": "TOTAL PAYOUTS",
                  "value": "$4.2B", "label": "DISTRIBUTED TO CLIENTS",
                  "context": "Since inception (2002–2026)"}},
        {"mode": "template", "template": "split",
         "data": {"theme": theme, "eyebrow": "FLAGSHIP",
                  "title": "EVOLUTION", "textSide": "right",
                  "body": "Our flagship sleeve combining tactical asset allocation "
                          "with systematic risk overlays for consistent compounding.",
                  "cta": "Learn more"}},
        {"mode": "template", "template": "comparison",
         "data": {"title": "PLAN COMPARISON", "theme": theme,
                  "columns": [{"name": "Starter"}, {"name": "Pro", "highlighted": True}, {"name": "Enterprise"}],
                  "rows": [
                      {"label": "Portfolios",    "values": ["1", "10", "Unlimited"]},
                      {"label": "Real-time risk","values": [False, True, True]},
                      {"label": "SSO",           "values": [False, False, True]},
                      {"label": "Priority SLA",  "values": [False, True, True]},
                      {"label": "Dedicated CSM", "values": [False, False, True]},
                  ]}},
        {"mode": "template", "template": "checklist",
         "data": {"title": "ONBOARDING CHECKLIST", "theme": theme,
                  "items": [{"text": "Risk tolerance survey", "done": True},
                            {"text": "Account opened",         "done": True},
                            {"text": "Funds transferred",      "done": True},
                            {"text": "Model selected",         "done": False},
                            {"text": "First rebalance",        "done": False}]}},
        {"mode": "template", "template": "venn",
         "data": {"title": "CAPABILITIES", "theme": theme,
                  "sets": [{"label": "RESEARCH"},
                           {"label": "RISK"},
                           {"label": "OPS"}]}},
        {"mode": "template", "template": "pillars",
         "data": {"title": "PILLARS", "theme": theme,
                  "pillars": [
                      {"icon": "★", "label": "EXCELLENCE", "description": "Performance focus"},
                      {"icon": "◆", "label": "INTEGRITY",  "description": "Client first"},
                      {"icon": "●", "label": "RESILIENCE", "description": "Risk aware"},
                      {"icon": "▲", "label": "GROWTH",     "description": "Always learning"},
                  ]}},
        {"mode": "template", "template": "card_grid",
         "data": {"title": "OFFERINGS", "theme": theme, "columns": 3,
                  "cards": [
                      {"eyebrow": "CORE", "title": "First Step",
                       "description": "Conservative tactical allocation."},
                      {"eyebrow": "CORE", "title": "Evolution",
                       "description": "Balanced growth and drawdown control."},
                      {"eyebrow": "CORE", "title": "Opportunity",
                       "description": "Concentrated conviction plays."},
                      {"eyebrow": "NEW",  "title": "Atlas",
                       "description": "Alternative return streams."},
                      {"eyebrow": "NEW",  "title": "Insight",
                       "description": "Data-driven factor sleeve."},
                      {"eyebrow": "NEW",  "title": "Horizon",
                       "description": "Long-duration thematic."},
                  ]}},
        {"mode": "template", "template": "steps_vertical",
         "data": {"title": "HOW IT WORKS", "theme": theme,
                  "steps": [{"title": "Discover",   "description": "Start with a discovery call."},
                            {"title": "Design",     "description": "Tailor a sleeve mix."},
                            {"title": "Deploy",     "description": "Execute with zero friction."},
                            {"title": "Monitor",    "description": "Measure outcomes weekly."}]}},
        {"mode": "template", "template": "features",
         "data": {"title": "FEATURES", "theme": theme,
                  "items": [
                      {"icon": "—", "title": "FAST",      "description": "Sub-second execution."},
                      {"icon": "—", "title": "SECURE",    "description": "SOC 2 Type II compliant."},
                      {"icon": "—", "title": "INSIGHTFUL","description": "Rich analytics."},
                      {"icon": "—", "title": "PARTNER",   "description": "Dedicated CSM."},
                      {"icon": "—", "title": "GLOBAL",    "description": "Multi-region ops."},
                      {"icon": "—", "title": "INNOVATIVE","description": "AI-enhanced research."},
                  ]}},
        {"mode": "template", "template": "badge_strip",
         "data": {"title": "TAGS", "theme": theme,
                  "tags": ["Strategy", "Risk", "Research", "Compliance",
                           "Execution", "Reporting"]}},
        {"mode": "template", "template": "before_after",
         "data": {"title": "BEFORE / AFTER", "theme": theme,
                  "before": ["Manual rebalancing", "Siloed data",
                             "Lagging reports", "Reactive risk management"],
                  "after":  ["Automated rebalancing", "Unified data platform",
                             "Real-time reports", "Proactive risk overlays"]}},
        {"mode": "template", "template": "org_chart",
         "data": {"title": "ORG CHART", "theme": theme,
                  "root": {"label": "CEO — A. Chen"},
                  "children": [
                      {"label": "CIO — M. Patel"},
                      {"label": "COO — S. Reyes"},
                      {"label": "CTO — E. Kim"},
                      {"label": "CCO — J. Novak"},
                  ]}},
        {"mode": "template", "template": "code",
         "data": {"title": "CODE", "theme": theme, "language": "python",
                  "code": ("def sharpe(r, rf=0.04):\n"
                           "    import numpy as np\n"
                           "    excess = np.array(r) - rf/12\n"
                           "    return excess.mean() / excess.std() * np.sqrt(12)\n")}},
        {"mode": "template", "template": "thank_you",
         "data": {"theme": theme, "title": "THANK YOU",
                  "subtitle": "Questions welcome anytime.",
                  "contact": "investors@potomacfund.com  •  +1 (800) 555-0199"}},
    ]


# ═══════════════════════════════════════════════════════════════════════════
# Extra-primitive freestyle gallery — arrows, ribbons, stars, badges, etc.
# ═══════════════════════════════════════════════════════════════════════════

def extras_gallery_slides() -> list:
    """A set of freestyle slides demonstrating prim.* extras."""
    return [
        # ── Arrow directions ────────────────────────────────────────────────
        {"mode": "freestyle", "code": (
            "const b = prim.standardChrome(slide, { title: 'ARROWS — DIRECTIONS' });"
            "const dirs = ['right','left','up','down','bent','uturn','pentagon','chevron'];"
            "const g = engine.grid(4, 2, b);"
            "dirs.forEach((d, i) => {"
            "  const c = g.cell(i % 4, Math.floor(i / 4));"
            "  prim.arrow(slide, { x: c.x + c.w*0.1, y: c.y + c.h*0.2, w: c.w*0.8, h: c.h*0.55 }, { dir: d });"
            "  prim.text(slide, d.toUpperCase(),"
            "    { x: c.x, y: c.y + c.h*0.78, w: c.w, h: c.h*0.2 },"
            "    { bold: true, align: 'center', color: PALETTE.DARK_GRAY, maxPt: 13 });"
            "});"
        )},
        # ── Stars in various point counts ──────────────────────────────────
        {"mode": "freestyle", "code": (
            "const b = prim.standardChrome(slide, { title: 'STARS & BURSTS' });"
            "const pts = [4,5,6,7,8,10,12,16,24,32];"
            "const g = engine.grid(5, 2, b);"
            "pts.forEach((p, i) => {"
            "  const c = g.cell(i % 5, Math.floor(i / 5));"
            "  prim.star(slide, { x: c.x, y: c.y, w: c.w, h: c.h*0.7 },"
            "    { points: p, label: String(p),"
            "      labelOpts: { color: PALETTE.DARK_GRAY, maxPt: 20 } });"
            "  prim.text(slide, p + '-POINT',"
            "    { x: c.x, y: c.y + c.h*0.75, w: c.w, h: c.h*0.2 },"
            "    { align: 'center', color: PALETTE.GRAY_60, maxPt: 11 });"
            "});"
        )},
        # ── Ribbons + tabs + chevrons ──────────────────────────────────────
        {"mode": "freestyle", "code": (
            "const b = prim.standardChrome(slide, { title: 'RIBBONS · TABS · CHEVRONS' });"
            "const rows = engine.grid(1, 3, b);"
            "prim.ribbon(slide, rows.cell(0,0), { label: 'FEATURED' });"
            "const tabs = ['OVERVIEW','DETAILS','PRICING','FAQ'];"
            "const row2 = rows.cell(0,1);"
            "const tabG = engine.grid(tabs.length, 1, { x: row2.x, y: row2.y + row2.h*0.25, w: row2.w, h: row2.h*0.5 });"
            "tabs.forEach((t,i) => prim.tab(slide, tabG.cell(i,0), { label: t }));"
            "const row3 = rows.cell(0,2);"
            "const chevrons = ['PLAN','BUILD','SHIP'];"
            "const chevG = engine.grid(chevrons.length, 1, { x: row3.x, y: row3.y + row3.h*0.2, w: row3.w, h: row3.h*0.6 });"
            "chevrons.forEach((c,i) => prim.chevron(slide, chevG.cell(i,0),"
            "  { color: i % 2 === 0 ? PALETTE.YELLOW : PALETTE.YELLOW_20, label: c }));"
        )},
        # ── Badges + rating + check circles ────────────────────────────────
        {"mode": "freestyle", "code": (
            "const b = prim.standardChrome(slide, { title: 'BADGES · RATINGS · CHECKS' });"
            "const gap = engine.H * 0.03;"
            "const s = engine.stack({ x: b.x, y: b.y, w: b.w, gap });"
            "const r1 = s.place(b.h * 0.15);"
            "const bg = engine.grid(6, 1, r1);"
            "for (let i = 0; i < 6; i++) {"
            "  prim.badge(slide, bg.cell(i, 0), { label: String(i + 1) });"
            "}"
            "const r2 = s.place(b.h * 0.15);"
            "const h2 = r2.h;"
            "prim.ratingStars(slide, { x: r2.x, y: r2.y, h: h2, gap: h2*0.2 }, { rating: 4 });"
            "prim.ratingStars(slide, { x: r2.x + r2.w*0.4, y: r2.y, h: h2, gap: h2*0.2 }, { rating: 3 });"
            "prim.ratingStars(slide, { x: r2.x + r2.w*0.7, y: r2.y, h: h2, gap: h2*0.2 }, { rating: 5 });"
            "const r3 = s.place(b.h * 0.25);"
            "const cg = engine.grid(6, 1, r3);"
            "for (let i = 0; i < 6; i++) prim.checkCircle(slide, cg.cell(i, 0));"
        )},
        # ── Progress bars + KPI cards ──────────────────────────────────────
        {"mode": "freestyle", "code": (
            "const b = prim.standardChrome(slide, { title: 'PROGRESS · KPI CARDS' });"
            "const s = engine.stack({ x: b.x, y: b.y, w: b.w, gap: engine.H * 0.03 });"
            "[0.25, 0.5, 0.75, 0.92].forEach(p => {"
            "  prim.progressBar(slide, s.place(engine.H * 0.04), { pct: p, label: Math.round(p*100)+'%' });"
            "});"
            "const row = s.place(b.h * 0.4);"
            "const kg = engine.grid(4, 1, row);"
            "const kpis = ["
            "  { value: '24%', label: 'RETURN', delta: '+4pp', deltaSign: 'up' },"
            "  { value: '0.92', label: 'SHARPE', delta: '-0.03', deltaSign: 'down' },"
            "  { value: '-8%', label: 'DRAWDOWN', delta: 'flat',  deltaSign: 'flat' },"
            "  { value: '$2.4B', label: 'AUM', delta: '+12%', deltaSign: 'up' },"
            "];"
            "kpis.forEach((k, i) => prim.kpiCard(slide, kg.cell(i, 0), k));"
        )},
        # ── Sticky notes + speech bubbles + callouts ───────────────────────
        {"mode": "freestyle", "code": (
            "const b = prim.standardChrome(slide, { title: 'STICKY NOTES · SPEECH · CALLOUTS' });"
            "const g = engine.grid(3, 2, b);"
            "prim.sticky(slide, g.cell(0,0), { color: 'YELLOW',    label: 'Idea 1' });"
            "prim.sticky(slide, g.cell(1,0), { color: 'YELLOW_80', label: 'Idea 2' });"
            "prim.sticky(slide, g.cell(2,0), { color: 'GREEN',     label: 'Done ✓' });"
            "prim.speech(slide, g.cell(0,1), { label: 'Great idea!' });"
            "prim.speech(slide, g.cell(1,1), { color: 'YELLOW_20', label: 'Agreed.' });"
            "prim.callout(slide, g.cell(2,1), { label: 'Important →' });"
        )},
        # ── Icon boxes + key/value + band ──────────────────────────────────
        {"mode": "freestyle", "code": (
            "const b = prim.standardChrome(slide, { title: 'ICON BOXES · KEY/VALUE · BANDS' });"
            "const s = engine.stack({ x: b.x, y: b.y, w: b.w, gap: engine.H * 0.02 });"
            "const row1 = s.place(b.h * 0.45);"
            "const g = engine.grid(4, 1, row1);"
            "['—','—','—','—'].forEach((ic, i) =>"
            "  prim.iconBox(slide, g.cell(i, 0),"
            "    { icon: ic, label: ['FAST','SECURE','GROW','GLOBAL'][i],"
            "      subLabel: 'Sub-line here', bg: 'GRAY_05' }));"
            "const row2 = s.place(b.h * 0.3);"
            "const kvG = engine.grid(1, 4, row2);"
            "[['CEO','Avery Chen'],['CIO','Marcus Patel'],['COO','Sofia Reyes'],['CTO','Ethan Kim']]"
            "  .forEach(([k,v], i) => prim.keyValue(slide, kvG.cell(0, i), { label: k, value: v }));"
            "const row3 = s.place(b.h * 0.12);"
            "prim.band(slide, row3, { colorA: 'YELLOW', colorB: 'DARK_GRAY', split: 0.33 });"
        )},
        # ── Timeline freestyle ─────────────────────────────────────────────
        {"mode": "freestyle", "code": (
            "const b = prim.standardChrome(slide, { title: 'TIMELINE MARKERS' });"
            "const y = b.y + b.h * 0.5;"
            "prim.shape(slide, pres.shapes.RECTANGLE,"
            "  { x: b.x, y: y - engine.H * 0.002, w: b.w, h: engine.H * 0.004 },"
            "  { fill: { color: 'FEC00F' }, line: { color: 'FEC00F', width: 0 } });"
            "const years = [2002, 2010, 2015, 2020, 2024];"
            "years.forEach((yr, i) => {"
            "  const x = b.x + (i / (years.length - 1)) * b.w;"
            "  prim.timelineDot(slide, { x, y }, { label: 'MILESTONE', subLabel: String(yr),"
            "    direction: i % 2 === 0 ? 'up' : 'down' });"
            "});"
        )},
    ]


# ═══════════════════════════════════════════════════════════════════════════
# Build + render
# ═══════════════════════════════════════════════════════════════════════════

def main() -> int:
    all_slides: list = []

    # Cover page
    all_slides.append({
        "mode": "template", "template": "title",
        "data": {"title": "POTOMAC MEGA SHOWCASE",
                 "subtitle": "Every template × every theme, in one deck",
                 "tagline": "Built to Conquer Risk", "style": "executive"},
    })

    # 10 themes × ~40 templates ≈ 400 slides
    for th in THEMES:
        # theme divider
        all_slides.append({
            "mode": "template", "template": "section_divider",
            "data": {"title": f"{th.upper()} THEME",
                     "description": f"Every template rendered in the {th} theme.",
                     "theme": th if th != "midnight" else "dark"},
        })
        all_slides.extend(theme_showcase(th))

    # Extra-primitive freestyle gallery
    all_slides.append({
        "mode": "template", "template": "section_divider",
        "data": {"title": "PRIMITIVE GALLERY",
                 "description": "arrows · ribbons · stars · tabs · badges · KPIs · …",
                 "theme": "dark"},
    })
    all_slides.extend(extras_gallery_slides())

    # Goodbye
    all_slides.append({
        "mode": "template", "template": "thank_you",
        "data": {"title": "END OF SHOWCASE",
                 "subtitle": "Scroll back up to review any template.",
                 "contact": "generated by core/sandbox v2"},
    })

    spec = {
        "title": "Potomac Mega Showcase",
        "filename": "mega_showcase.pptx",
        "canvas": {"preset": "wide"},
        "slides": all_slides,
    }

    print(f"→ Rendering {len(all_slides)} slides across {len(THEMES)} themes …")
    t0 = time.time()
    sandbox = PptxSandbox()
    result = sandbox.generate(spec, timeout=600)
    if not result.success:
        print(f"✗ failed: {result.error}")
        for w in result.warnings or []:
            print(" WARN:", w)
        return 1
    print(f"✓ OK  {len(result.data)/1024:.1f} KB  "
          f"{result.exec_time_ms:.0f}ms  canvas={result.canvas}")
    if result.warnings:
        print(f"  ({len(result.warnings)} WARN lines — first 5 shown)")
        for w in result.warnings[:5]:
            print("   -", w)

    # Write (with permission-error fallback)
    out = ROOT / (result.filename or "mega_showcase.pptx")
    try:
        out.write_bytes(result.data)
    except PermissionError:
        out = ROOT / f"mega_showcase_{int(time.time())}.pptx"
        out.write_bytes(result.data)
    print(f"✓ wrote {out}")
    print(f"total wall-time: {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
