"""
BrandEnforcer
=============
Scores any PPTX slide against the Potomac brand guidelines and optionally
applies automatic corrections to bring it into compliance.

Brand Guidelines (Potomac)
--------------------------
Colors       : YELLOW #FEC00F, DARK_GRAY #212121, WHITE #FFFFFF
               Accent: GRAY_60 #999999, YELLOW_20 #FEF7D8
Title font   : Rajdhani (ALL CAPS)
Body font    : Quicksand
Logo         : Must appear on every content slide (top-right corner)
Accent bar   : Yellow vertical bar (left side) on content slides
Background   : White (#FFFFFF) or Dark (#212121) — no other backgrounds

Scoring (0–100)
---------------
Each violation deducts points:
  Missing logo                -15
  Off-brand background color  -15
  Off-brand dominant color     -10
  Non-brand font detected      -10
  No accent bar                -5
  Title not ALL CAPS           -5
  Excessive colors (>4)        -5

Auto-corrections (applied to SlideAnalysis when possible)
---------------------------------------------------------
  Replace off-brand background → white or dark_gray
  Insert Potomac logo position hint
  Force title to uppercase
  Suggest font replacements

Usage
-----
    from core.vision.brand_enforcer import BrandEnforcer

    enforcer = BrandEnforcer()

    # Score a single slide analysis
    report = enforcer.score(analysis)
    print(report.score, report.violations)

    # Score all slides in a manifest
    reports = await enforcer.score_manifest(manifest, analyses)

    # Auto-correct an analysis dict
    corrected = enforcer.auto_correct(analysis)
"""

from __future__ import annotations

import colorsys
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Potomac brand palette ──────────────────────────────────────────────────────
BRAND_COLORS = {
    "YELLOW":    "FEC00F",
    "DARK_GRAY": "212121",
    "WHITE":     "FFFFFF",
    "GRAY_60":   "999999",
    "GRAY_20":   "DDDDDD",
    "YELLOW_20": "FEF7D8",
}

BRAND_COLOR_SET = set(BRAND_COLORS.values())
BRAND_FONTS = {"Rajdhani", "Quicksand"}

ALLOWED_BACKGROUNDS = {"FFFFFF", "212121", "FEF7D8"}
LIGHT_BACKGROUNDS   = {"FFFFFF", "FEF7D8"}
DARK_BACKGROUNDS    = {"212121"}

# Tolerance for color matching (max Euclidean distance in 0-255 RGB space)
_COLOR_TOLERANCE = 30.0


# =============================================================================
# Data classes
# =============================================================================

@dataclass
class BrandViolation:
    """A single detected brand guideline violation."""
    code:        str    # machine-readable code
    severity:    str    # "critical" | "major" | "minor"
    description: str    # human-readable description
    deduction:   int    # points deducted from score
    suggestion:  str    # how to fix it

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code":        self.code,
            "severity":    self.severity,
            "description": self.description,
            "deduction":   self.deduction,
            "suggestion":  self.suggestion,
        }


@dataclass
class BrandReport:
    """Complete brand compliance report for a single slide."""
    slide_index:  int
    score:        int                           # 0–100
    grade:        str                           # A/B/C/D/F
    violations:   List[BrandViolation] = field(default_factory=list)
    suggestions:  List[str]           = field(default_factory=list)
    is_compliant: bool                = False   # True if score >= 80

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slide_index":  self.slide_index,
            "score":        self.score,
            "grade":        self.grade,
            "is_compliant": self.is_compliant,
            "violations":   [v.to_dict() for v in self.violations],
            "suggestions":  self.suggestions,
        }


@dataclass
class BrandAudit:
    """Aggregate brand audit across all slides in a deck."""
    deck_name:       str
    slide_count:     int
    avg_score:       float
    overall_grade:   str
    compliant_slides: int
    reports:         List[BrandReport] = field(default_factory=list)
    top_violations:  List[str]         = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "deck_name":        self.deck_name,
            "slide_count":      self.slide_count,
            "avg_score":        round(self.avg_score, 1),
            "overall_grade":    self.overall_grade,
            "compliance_rate":  f"{self.compliant_slides}/{self.slide_count}",
            "top_violations":   self.top_violations,
            "slide_reports":    [r.to_dict() for r in self.reports],
        }


# =============================================================================
# BrandEnforcer
# =============================================================================

class BrandEnforcer:
    """
    Scores slides against Potomac brand guidelines and suggests corrections.
    Works on SlideAnalysis objects from VisionEngine.
    """

    def __init__(self, compliance_threshold: int = 80):
        self.compliance_threshold = compliance_threshold

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def score(self, analysis) -> BrandReport:
        """
        Score a single SlideAnalysis against brand guidelines.

        Parameters
        ----------
        analysis : SlideAnalysis from VisionEngine

        Returns
        -------
        BrandReport with score (0–100), grade, and violation list
        """
        violations: List[BrandViolation] = []
        score = 100

        layout = (analysis.layout_type or "").lower()
        bg     = (analysis.background or "FFFFFF").upper().lstrip("#")
        title  = analysis.title or ""
        fonts  = self._extract_fonts(analysis)
        colors = [c.upper().lstrip("#") for c in (analysis.color_palette or [])]

        # ── 1. Logo check ──────────────────────────────────────────────────────
        # Skip title slides and section dividers
        if layout not in ("title", "section_divider", "full_bleed_image"):
            if not analysis.has_logo:
                v = BrandViolation(
                    code="NO_LOGO",
                    severity="critical",
                    description="Potomac logo missing from slide",
                    deduction=15,
                    suggestion="Add the Potomac logo to the top-right corner",
                )
                violations.append(v)
                score -= v.deduction

        # ── 2. Background color check ─────────────────────────────────────────
        if bg and bg not in ALLOWED_BACKGROUNDS:
            # Check if it's close to an allowed background
            closest, dist = self._closest_brand_color(bg)
            if dist > _COLOR_TOLERANCE:
                v = BrandViolation(
                    code="OFF_BRAND_BACKGROUND",
                    severity="major",
                    description=f"Background #{bg} is not in Potomac palette",
                    deduction=15,
                    suggestion=f"Use WHITE (#FFFFFF), DARK_GRAY (#212121), or YELLOW_20 (#FEF7D8)",
                )
                violations.append(v)
                score -= v.deduction
            else:
                # Close enough — minor warning only
                v = BrandViolation(
                    code="NEAR_BRAND_BACKGROUND",
                    severity="minor",
                    description=f"Background #{bg} is close to #{closest} but not exact",
                    deduction=3,
                    suggestion=f"Use exact brand color #{closest}",
                )
                violations.append(v)
                score -= v.deduction

        # ── 3. Dominant color palette check ───────────────────────────────────
        off_brand_colors = [
            c for c in colors
            if c not in BRAND_COLOR_SET
            and self._closest_brand_color(c)[1] > _COLOR_TOLERANCE
            and c != bg   # already checked background
        ]
        if off_brand_colors:
            v = BrandViolation(
                code="OFF_BRAND_COLORS",
                severity="major",
                description=f"Off-brand colors detected: {', '.join('#'+c for c in off_brand_colors[:3])}",
                deduction=10,
                suggestion="Use only Potomac palette: Yellow #FEC00F, Dark Gray #212121, White #FFFFFF",
            )
            violations.append(v)
            score -= v.deduction

        # ── 4. Excessive colors ───────────────────────────────────────────────
        if len(colors) > 4:
            v = BrandViolation(
                code="TOO_MANY_COLORS",
                severity="minor",
                description=f"Slide uses {len(colors)} colors (max 4 recommended)",
                deduction=5,
                suggestion="Reduce to 2–4 colors: Yellow + Dark Gray + White + one accent",
            )
            violations.append(v)
            score -= v.deduction

        # ── 5. Font check ─────────────────────────────────────────────────────
        off_brand_fonts = [f for f in fonts if f and f not in BRAND_FONTS
                           and f.lower() not in ("arial", "calibri")]  # tolerate common fallbacks
        if off_brand_fonts:
            v = BrandViolation(
                code="OFF_BRAND_FONT",
                severity="major",
                description=f"Non-Potomac font(s) detected: {', '.join(off_brand_fonts[:3])}",
                deduction=10,
                suggestion="Use Rajdhani for headlines (ALL CAPS) and Quicksand for body text",
            )
            violations.append(v)
            score -= v.deduction

        # ── 6. Title case check ───────────────────────────────────────────────
        if (title and
            layout not in ("title", "section_divider") and
            len(title) > 3 and
            title != title.upper() and
            not title.istitle()):
            v = BrandViolation(
                code="TITLE_NOT_CAPS",
                severity="minor",
                description=f"Title '{title[:40]}...' is not ALL CAPS",
                deduction=5,
                suggestion="Potomac headlines use Rajdhani font in ALL CAPS",
            )
            violations.append(v)
            score -= v.deduction

        # ── 7. Accent bar check (content slides) ─────────────────────────────
        if layout in ("content", "two_column", "three_column", "metrics", "process"):
            has_yellow_divider = any(
                e.type in ("divider", "shape") and e.fill_color.upper() in ("FEC00F",)
                for e in (analysis.elements or [])
            )
            if not has_yellow_divider and bg in LIGHT_BACKGROUNDS:
                v = BrandViolation(
                    code="MISSING_ACCENT_BAR",
                    severity="minor",
                    description="Yellow accent bar missing on content slide",
                    deduction=5,
                    suggestion="Add yellow (#FEC00F) left-side vertical bar (0.15 in wide, full height)",
                )
                violations.append(v)
                score -= v.deduction

        score = max(0, score)
        grade = self._grade(score)
        suggestions = self._build_suggestions(violations, analysis)

        return BrandReport(
            slide_index=analysis.slide_index,
            score=score,
            grade=grade,
            violations=violations,
            suggestions=suggestions,
            is_compliant=score >= self.compliance_threshold,
        )

    def score_manifest_sync(
        self,
        analyses: List,
        deck_name: str = "Presentation",
    ) -> BrandAudit:
        """
        Score all slides synchronously. Returns a BrandAudit.
        """
        reports = [self.score(a) for a in analyses]
        scores  = [r.score for r in reports]
        avg     = sum(scores) / len(scores) if scores else 0.0
        compliant = sum(1 for r in reports if r.is_compliant)

        # Top violations (most common codes)
        from collections import Counter
        all_codes = [v.code for r in reports for v in r.violations]
        top = [code for code, _ in Counter(all_codes).most_common(5)]

        return BrandAudit(
            deck_name=deck_name,
            slide_count=len(reports),
            avg_score=avg,
            overall_grade=self._grade(int(avg)),
            compliant_slides=compliant,
            reports=reports,
            top_violations=top,
        )

    def auto_correct(self, analysis_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply safe automatic corrections to a SlideAnalysis dict.

        Returns a copy of the dict with corrections applied.
        Corrections made:
          - Background normalized to nearest brand color
          - Title uppercased
          - Logo hint added if missing
          - Font suggestions added to metadata
        """
        import copy
        corrected = copy.deepcopy(analysis_dict)

        # Normalize background
        bg = corrected.get("background", "FFFFFF").upper().lstrip("#")
        if bg not in ALLOWED_BACKGROUNDS:
            closest, dist = self._closest_brand_color(bg)
            if dist <= _COLOR_TOLERANCE * 2:
                corrected["background"] = closest
                corrected.setdefault("_corrections", []).append(
                    f"Background #{bg} → #{closest}"
                )
            else:
                # Default to white
                corrected["background"] = "FFFFFF"
                corrected.setdefault("_corrections", []).append(
                    f"Background #{bg} → #FFFFFF (defaulted)"
                )

        # Uppercase title
        title = corrected.get("title", "")
        if title and title != title.upper():
            corrected["title"] = title.upper()
            corrected.setdefault("_corrections", []).append("Title uppercased")

        # Add logo hint if missing
        if not corrected.get("has_logo"):
            corrected["_logo_required"] = True
            corrected["logo_variant"] = "full"
            corrected.setdefault("_corrections", []).append("Logo required (not detected)")

        # Suggest font normalization
        typography = corrected.get("typography", {})
        if typography.get("title_font") and typography["title_font"] not in BRAND_FONTS:
            corrected["_corrections"] = corrected.get("_corrections", [])
            corrected["_corrections"].append(
                f"Font '{typography['title_font']}' → suggest Rajdhani"
            )

        return corrected

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
        h = hex_color.upper().lstrip("#").zfill(6)
        try:
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        except ValueError:
            return 255, 255, 255

    @classmethod
    def _color_distance(cls, c1: str, c2: str) -> float:
        r1, g1, b1 = cls._hex_to_rgb(c1)
        r2, g2, b2 = cls._hex_to_rgb(c2)
        return ((r1-r2)**2 + (g1-g2)**2 + (b1-b2)**2) ** 0.5

    @classmethod
    def _closest_brand_color(cls, color: str) -> Tuple[str, float]:
        best_color = "FFFFFF"
        best_dist  = float("inf")
        for bc in BRAND_COLOR_SET:
            d = cls._color_distance(color, bc)
            if d < best_dist:
                best_dist  = d
                best_color = bc
        return best_color, best_dist

    @staticmethod
    def _extract_fonts(analysis) -> List[str]:
        fonts = set()
        typo = analysis.typography or {}
        if typo.get("title_font"):
            fonts.add(typo["title_font"])
        if typo.get("body_font"):
            fonts.add(typo["body_font"])
        for e in (analysis.elements or []):
            if e.font_family:
                fonts.add(e.font_family)
        return list(fonts)

    @staticmethod
    def _grade(score: int) -> str:
        if score >= 90: return "A"
        if score >= 80: return "B"
        if score >= 70: return "C"
        if score >= 60: return "D"
        return "F"

    @staticmethod
    def _build_suggestions(violations: List[BrandViolation], analysis) -> List[str]:
        suggestions = []
        for v in violations:
            if v.suggestion:
                suggestions.append(v.suggestion)
        # Add generic suggestions based on layout
        layout = (analysis.layout_type or "").lower()
        if layout == "full_bleed_image":
            suggestions.append(
                "Consider rebuilding this slide natively — use /pptx/reconstruct "
                "to convert image slides to editable Potomac-branded elements"
            )
        return suggestions
