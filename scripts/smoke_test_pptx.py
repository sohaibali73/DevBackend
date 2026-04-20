"""
PPTX Sandbox v2 — Smoke Test
============================
Quickly verifies that:
  • Node runtime renders a multi-slide Potomac deck.
  • Canvas is 13.333" × 7.5" (NOT the legacy 10×7.5).
  • Warnings from the JS clampBox are captured.

Usage
-----
    python scripts/smoke_test_pptx.py

Will write `smoke_out.pptx` in the current directory and print the detected
canvas dimensions extracted from the raw .pptx package.
"""

from __future__ import annotations

import sys
import zipfile
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.sandbox.pptx_sandbox import PptxSandbox  # noqa: E402


SPEC = {
    "title": "Potomac Sandbox v2 Smoke Test",
    "filename": "smoke_out.pptx",
    "canvas": {"preset": "wide"},
    "slides": [
        {
            "mode": "template",
            "template": "title",
            "data": {
                "title": "POTOMAC SANDBOX V2",
                "subtitle": "Canvas, layout engine, primitives & templates",
                "style": "executive",
            },
        },
        {
            "mode": "template",
            "template": "title_card",
            "data": {
                "title": "INVESTMENT STRATEGIES",
                "title_accent": "AND SOLUTIONS",
                "subtitle": "AT POTOMAC FUND MANAGEMENT",
                "tagline": "STRATEGY OVERVIEW",
                "body": "Tactical risk-managed portfolios for any market environment.",
                "footer": "Confidential — For Internal Use",
            },
        },
        {
            "mode": "template",
            "template": "team_triad",
            "data": {
                "title": "BRINGING THE TEAM TOGETHER",
                "cards": [
                    {
                        "pill": "FUND RESEARCH",
                        "body": "Investment due diligence and fund monitoring.",
                    },
                    {
                        "pill": "PORTFOLIO MGMT",
                        "body": "Allocation, execution and rebalancing.",
                    },
                    {
                        "pill": "RISK OVERLAY",
                        "body": "Systematic drawdown control & volatility sizing.",
                    },
                ],
                "glyphs": ["+", "="],
            },
        },
        {
            "mode": "template",
            "template": "hex_row",
            "data": {
                "title": "OUR STRATEGIES ARE TACTICAL",
                "subtitle": "Each sleeve plays a specific role in the portfolio.",
                "tiles": [
                    {"label": "FIRST STEP",  "subline": "2002"},
                    {"label": "EVOLUTION",   "subline": "2010"},
                    {"label": "OPPORTUNITY", "subline": "2015"},
                    {"label": "INSIGHT",     "subline": "2020"},
                ],
            },
        },
        {
            "mode": "template",
            "template": "cta_framed",
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
    ],
}


def inspect_canvas(pptx_path: Path) -> tuple[float, float]:
    """Read the `<p:sldSz />` element from the .pptx package and return (W, H) in inches."""
    with zipfile.ZipFile(pptx_path) as z:
        xml = z.read("ppt/presentation.xml").decode("utf-8", errors="replace")
    m = re.search(r'<p:sldSz[^/]*cx="(\d+)"[^/]*cy="(\d+)"', xml)
    if not m:
        raise RuntimeError("Could not find sldSz in presentation.xml")
    cx = int(m.group(1))  # EMU — 914400 per inch
    cy = int(m.group(2))
    return round(cx / 914400, 3), round(cy / 914400, 3)


def main() -> int:
    print("→ Generating presentation via PptxSandbox v2 …")
    sandbox = PptxSandbox()
    result = sandbox.generate(SPEC)
    if not result.success:
        print(f"✗ Generation failed: {result.error}")
        for w in result.warnings or []:
            print(f"  WARN: {w}")
        return 1

    print(f"✓ Generated {len(result.data)} bytes in {result.exec_time_ms:.0f}ms")
    if result.warnings:
        print("  Warnings:")
        for w in result.warnings:
            print("   -", w)

    out = ROOT / (result.filename or "smoke_out.pptx")
    try:
        out.write_bytes(result.data)
        print(f"✓ Wrote {out}")
    except PermissionError:
        # File is likely open in PowerPoint — drop a timestamped copy instead.
        import time as _t
        alt = ROOT / f"smoke_out_{int(_t.time())}.pptx"
        alt.write_bytes(result.data)
        out = alt
        print(f"✓ Wrote {alt} (fallback — smoke_out.pptx was locked)")

    # Verify canvas
    w, h = inspect_canvas(out)
    print(f"✓ Detected canvas: {w}\" × {h}\"")
    if round(w, 2) == 13.33 and round(h, 2) == 7.5:
        print("✅ PASS: canvas is 16:9 widescreen (13.333 × 7.5)")
        return 0
    if round(w, 2) == 10.0 and round(h, 2) == 7.5:
        print("❌ FAIL: canvas is legacy 4:3 (10.0 × 7.5). The LAYOUT fix is NOT working.")
        return 2
    print(f"❌ UNEXPECTED canvas size: {w} × {h}")
    return 3


if __name__ == "__main__":
    sys.exit(main())
