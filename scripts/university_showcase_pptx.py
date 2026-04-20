"""
Potomac University Showcase
===========================
Renders a single .pptx that mirrors all 8 slides of the reference template
in `C:/Users/SohaibAli/Downloads/Potomac_University_Template`.

Outputs: `university_showcase.pptx`

Usage:
    python scripts/university_showcase_pptx.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.sandbox.pptx_sandbox import PptxSandbox  # noqa: E402


SLIDES = [
    # 1) Dark title with crest (matches reference Slide 1)
    {"mode": "template", "template": "university_title",
     "data": {"established": "2026"}},

    # 2) Full yellow cover (reference Slide 2)
    {"mode": "template", "template": "university_yellow_cover",
     "data": {"title": "Title", "byline": "Manish Khatta, CEO"}},

    # 3) Dark hero photo with overlay title (reference Slide 3)
    {"mode": "template", "template": "university_welcome_photo",
     "data": {"title": "Welcome to\nPotomac University"}},

    # 4) History / trend chart (reference Slide 4)
    {"mode": "template", "template": "university_trend_chart",
     "data": {
         "eyebrow": "History",
         "title": "Trend Direction",
         "chart_type": "line",
         "categories": ["2012", "2014", "2016", "2018", "2020", "2022", "2024", "2026"],
         "series": [
             {"name": "ALPS Alerian MLP ETF (AMLP)",
              "values": [32, 36, 30, 28, 14, 28, 38, 46]},
         ],
         "caption": "For illustrative purposes only.",
     }},

    # 5) Pennant + headline (reference Slide 5)
    {"mode": "template", "template": "university_pennant",
     "data": {"title": "Welcome to Potomac University"}},

    # 6) Three numbered circles (reference Slide 6)
    {"mode": "template", "template": "university_number_trio",
     "data": {
         "eyebrow": "History",
         "title": "Trend Direction",
         "items": [
             {"n": 1, "label": "Trend Direction",
              "hint": "(up, down, or sideways)"},
             {"n": 2, "label": "Trend Health",
              "hint": "(Breadth and Volume)"},
             {"n": 3, "label": "Intermarket Confirmation",
              "hint": "(Intermarket Relationships)"},
         ],
     }},

    # 7) Bullets + photo (reference Slide 7)
    {"mode": "template", "template": "university_bullets_photo",
     "data": {
         "eyebrow": "History",
         "title": "Trend Direction",
         "items": [
             "Profitable with healthy margins",
             "Profitable with healthy margins",
             "Profitable with healthy margins",
             "Profitable with healthy margins",
             "Profitable with healthy margins",
         ],
     }},

    # 8) Thank you (reference Slide 8)
    {"mode": "template", "template": "university_thank_you",
     "data": {"title": "Thank you!"}},
]


def main() -> int:
    spec = {
        "title": "Potomac University — Showcase",
        "filename": "university_showcase.pptx",
        "canvas": {"preset": "wide"},
        "slides": SLIDES,
    }
    print(f"→ Rendering {len(SLIDES)} university-style slides …")
    t0 = time.time()
    sandbox = PptxSandbox()
    result = sandbox.generate(spec)
    if not result.success:
        print(f"✗ failed: {result.error}")
        for w in result.warnings or []:
            print("  WARN:", w)
        return 1
    print(f"✓ OK  {len(result.data) / 1024:.1f} KB  "
          f"{result.exec_time_ms:.0f}ms  canvas={result.canvas}")
    if result.warnings:
        print(f"  ({len(result.warnings)} warnings)")
        for w in result.warnings[:10]:
            print("   -", w)

    out = ROOT / (result.filename or "university_showcase.pptx")
    try:
        out.write_bytes(result.data)
    except PermissionError:
        out = ROOT / f"university_showcase_{int(time.time())}.pptx"
        out.write_bytes(result.data)
    print(f"✓ wrote {out}")
    print(f"total wall-time: {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
