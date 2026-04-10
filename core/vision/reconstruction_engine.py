"""
ReconstructionEngine
====================
Maps a SlideAnalysis (produced by VisionEngine) to a pptx_sandbox spec dict
that can be fed directly into PptxSandbox.generate() to produce an editable
native PowerPoint slide.

Strategy
--------
1. High-confidence reconstruction (score ≥ 0.70):
   Maps the detected layout + elements to one of the existing pptx_sandbox
   slide type builders (card_grid, icon_grid, content_slide, etc.).

2. Medium-confidence (0.40 ≤ score < 0.70):
   "Smart overlay" — embed the original slide image as the background and
   overlay extracted text boxes as native editable elements.

3. Low-confidence / full_bleed_image (score < 0.40):
   Fall back to buildImageSlide with the original image embedded.

Usage
-----
    from core.vision.reconstruction_engine import ReconstructionEngine

    engine = ReconstructionEngine()
    spec = engine.build_spec(analysis, slide_image_bytes)

    # spec can be passed directly to PptxSandbox:
    # sandbox = PptxSandbox()
    # result = sandbox.generate({"title": "...", "slides": [spec]})
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Confidence thresholds
_HIGH_THRESHOLD   = 0.70
_MEDIUM_THRESHOLD = 0.40

# Mapping from reconstruction_strategy → pptx_sandbox slide type
_STRATEGY_MAP = {
    "title_slide":        "title",
    "content_slide":      "content",
    "two_column":         "two_column",
    "three_column":       "three_column",
    "metrics":            "metrics",
    "process":            "process",
    "card_grid":          "card_grid",
    "icon_grid":          "icon_grid",
    "hub_spoke":          "hub_spoke",
    "timeline":           "timeline",
    "matrix_2x2":         "matrix_2x2",
    "scorecard":          "scorecard",
    "comparison":         "comparison",
    "table":              "table",
    "chart":              "chart",
    "quote":              "quote",
    "section_divider":    "section_divider",
    "executive_summary":  "executive_summary",
    "image_content":      "image_content",
    "full_image_embed":   "image",
}


class ReconstructionEngine:
    """
    Converts SlideAnalysis objects into pptx_sandbox-compatible spec dicts.
    """

    def build_spec(
        self,
        analysis,                          # SlideAnalysis
        slide_image_bytes: Optional[bytes] = None,
        force_image_embed: bool = False,
    ) -> Dict[str, Any]:
        """
        Build a pptx_sandbox slide spec from a SlideAnalysis.

        Parameters
        ----------
        analysis          : SlideAnalysis from VisionEngine
        slide_image_bytes : original PNG bytes (used for image-embed fallback)
        force_image_embed : if True, always embed image regardless of confidence

        Returns
        -------
        dict — slide spec compatible with pptx_sandbox's "slides" array.
        """
        if not analysis or analysis.error:
            return self._image_embed_spec(
                slide_image_bytes,
                title="",
                index=getattr(analysis, "slide_index", 1),
            )

        confidence   = analysis.reconstruction_confidence
        strategy_key = analysis.reconstruction_strategy or "full_image_embed"

        # Always embed if forced or layout is full_bleed_image
        if force_image_embed or strategy_key == "full_image_embed":
            return self._image_embed_spec(
                slide_image_bytes, analysis.title, analysis.slide_index
            )

        if confidence >= _HIGH_THRESHOLD:
            return self._high_confidence_spec(analysis, slide_image_bytes)
        elif confidence >= _MEDIUM_THRESHOLD:
            return self._medium_confidence_spec(analysis, slide_image_bytes)
        else:
            return self._image_embed_spec(
                slide_image_bytes, analysis.title, analysis.slide_index
            )

    def build_spec_batch(
        self,
        analyses: List,                    # List[SlideAnalysis]
        slide_images: Optional[Dict[int, bytes]] = None,  # {slide_index: png_bytes}
    ) -> List[Dict[str, Any]]:
        """Build specs for a list of analyses. Returns specs in slide order."""
        slide_images = slide_images or {}
        specs = []
        for a in sorted(analyses, key=lambda x: x.slide_index):
            img = slide_images.get(a.slide_index)
            specs.append(self.build_spec(a, img))
        return specs

    # ──────────────────────────────────────────────────────────────────────────
    # High-confidence reconstruction (≥ 0.70)
    # Maps directly to a named pptx_sandbox slide type
    # ──────────────────────────────────────────────────────────────────────────

    def _high_confidence_spec(
        self,
        a,                         # SlideAnalysis
        image_bytes: Optional[bytes],
    ) -> Dict[str, Any]:
        s = a.reconstruction_strategy
        pptx_type = _STRATEGY_MAP.get(s, "content")

        # Route to per-layout builder
        builders = {
            "title":            self._build_title,
            "content":          self._build_content,
            "two_column":       self._build_two_column,
            "three_column":     self._build_three_column,
            "metrics":          self._build_metrics,
            "process":          self._build_process,
            "card_grid":        self._build_card_grid,
            "icon_grid":        self._build_icon_grid,
            "hub_spoke":        self._build_hub_spoke,
            "timeline":         self._build_timeline,
            "matrix_2x2":       self._build_matrix2x2,
            "scorecard":        self._build_scorecard,
            "comparison":       self._build_comparison,
            "table":            self._build_table,
            "chart":            self._build_chart,
            "quote":            self._build_quote,
            "section_divider":  self._build_section_divider,
            "executive_summary": self._build_executive_summary,
            "image_content":    self._build_image_content,
            "image":            lambda a, _: self._image_embed_spec(image_bytes, a.title, a.slide_index),
        }

        builder = builders.get(pptx_type)
        if builder:
            try:
                spec = builder(a, image_bytes)
                spec["_reconstruction_confidence"] = a.reconstruction_confidence
                spec["_reconstruction_strategy"]   = a.reconstruction_strategy
                return spec
            except Exception as exc:
                logger.warning(
                    "High-confidence builder '%s' failed for slide %d: %s",
                    pptx_type, a.slide_index, exc,
                )

        # Fallback to image embed
        return self._image_embed_spec(image_bytes, a.title, a.slide_index)

    # ──────────────────────────────────────────────────────────────────────────
    # Medium-confidence (0.40–0.70): image background + native text overlay
    # ──────────────────────────────────────────────────────────────────────────

    def _medium_confidence_spec(
        self,
        a,
        image_bytes: Optional[bytes],
    ) -> Dict[str, Any]:
        """
        Embed original slide image as background, overlay extracted text
        and any reconstructible elements as native pptxgenjs shapes.
        """
        spec = self._image_embed_spec(image_bytes, "", a.slide_index)
        spec["type"] = "image"
        spec["_reconstruction_confidence"] = a.reconstruction_confidence
        spec["_reconstruction_strategy"]   = "medium_overlay"
        spec["_overlay_title"] = a.title
        spec["_overlay_body"]  = a.body_text
        return spec

    # ──────────────────────────────────────────────────────────────────────────
    # Per-layout spec builders
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_title(a, _) -> Dict[str, Any]:
        dark = a.background.upper() not in ("FFFFFF", "F5F5F5", "F0F0F0", "")
        return {
            "type": "title",
            "title": a.title,
            "subtitle": a.subtitle or a.body_text,
            "style": "executive" if dark else "standard",
        }

    @staticmethod
    def _build_content(a, _) -> Dict[str, Any]:
        bullets = [
            line.strip().lstrip("•●-").strip()
            for line in a.body_text.split("\n")
            if line.strip()
        ] if a.body_text else []
        return {
            "type": "content",
            "title": a.title,
            "bullets": bullets if bullets else None,
            "text": a.body_text if not bullets else None,
        }

    @staticmethod
    def _build_two_column(a, _) -> Dict[str, Any]:
        # Try to split elements into left/right groups by x position
        left_elems  = [e for e in a.elements if e.x_pct < 0.5 and e.type in ("text_box", "shape")]
        right_elems = [e for e in a.elements if e.x_pct >= 0.5 and e.type in ("text_box", "shape")]
        left_text  = "\n".join(e.label for e in left_elems)  or a.body_text
        right_text = "\n".join(e.label for e in right_elems) or ""
        return {
            "type": "two_column",
            "title": a.title,
            "left_header": None,
            "right_header": None,
            "left_content": left_text,
            "right_content": right_text,
        }

    @staticmethod
    def _build_three_column(a, _) -> Dict[str, Any]:
        cols = [""] * 3
        hdrs = [""] * 3
        col_elems = sorted(
            [e for e in a.elements if e.type in ("text_box", "badge", "icon")],
            key=lambda e: e.x_pct,
        )
        for i, elem in enumerate(col_elems[:3]):
            cols[i] = elem.label
            if elem.sublabel:
                hdrs[i] = elem.sublabel
        return {
            "type": "three_column",
            "title": a.title,
            "column_headers": hdrs if any(hdrs) else None,
            "columns": cols,
        }

    @staticmethod
    def _build_metrics(a, _) -> Dict[str, Any]:
        metric_elems = [
            e for e in a.elements
            if e.type in ("text_box", "badge") and e.label
        ]
        # Heuristic: short labels with numbers → KPI values
        metrics = []
        for e in metric_elems[:6]:
            label = e.label.strip()
            sub   = e.sublabel.strip()
            # Guess if label is a value or description
            is_value = any(c.isdigit() or c in "$%+" for c in label[:5])
            metrics.append({
                "value": label if is_value else sub,
                "label": sub   if is_value else label,
            })
        return {
            "type": "metrics",
            "title": a.title,
            "metrics": metrics,
            "context": a.body_text or None,
        }

    @staticmethod
    def _build_process(a, _) -> Dict[str, Any]:
        step_elems = sorted(
            [e for e in a.elements if e.type in ("badge", "icon", "shape", "text_box")],
            key=lambda e: e.x_pct,
        )
        steps = [
            {"title": e.label, "description": e.sublabel}
            for e in step_elems[:6]
            if e.label
        ]
        return {
            "type": "process",
            "title": a.title,
            "steps": steps,
        }

    @staticmethod
    def _build_card_grid(a, _) -> Dict[str, Any]:
        """Icon-grid strategy slides (like the yellow hexagon cards)."""
        badge_elems = sorted(
            [e for e in a.elements if e.type in ("badge", "hexagon", "icon", "shape")],
            key=lambda e: e.x_pct,
        )
        cards = []
        for e in badge_elems:
            if not e.label:
                continue
            cards.append({
                "title": e.label,
                "subtitle": e.sublabel or None,
                "color": "yellow" if e.fill_color.upper() in ("FEC00F", "FFD700") else "dark",
                "bold": e.bold,
            })

        dark = a.background.upper() not in ("FFFFFF", "F5F5F5", "", "F0F0F0")
        return {
            "type": "card_grid",
            "title": a.title,
            "subtitle": a.subtitle or None,
            "section_label": a.section_label or None,
            "background": "dark" if dark else "light",
            "columns": a.grid_columns or min(4, len(cards)) or 4,
            "cards": cards,
        }

    @staticmethod
    def _build_icon_grid(a, _) -> Dict[str, Any]:
        icon_elems = sorted(
            [e for e in a.elements if e.type in ("icon", "badge", "hexagon")],
            key=lambda e: e.x_pct,
        )
        items = [
            {
                "icon":  e.icon or "default",
                "title": e.label,
                "body":  e.sublabel or None,
            }
            for e in icon_elems
            if e.label
        ]
        return {
            "type": "icon_grid",
            "title": a.title,
            "columns": a.grid_columns or min(3, len(items)) or 3,
            "items": items,
        }

    @staticmethod
    def _build_hub_spoke(a, _) -> Dict[str, Any]:
        return {
            "type": "hub_spoke",
            "title": a.title,
            "hub": {
                "label": a.subtitle or a.title,
                "items": [],
                "color": "yellow",
            },
            "spokes": [
                {
                    "label": e.label,
                    "items": [e.sublabel] if e.sublabel else [],
                    "side": "left" if e.x_pct < 0.4 else "right",
                    "row": 0,
                }
                for e in a.elements
                if e.type in ("shape", "text_box", "badge") and e.label
            ][:4],
        }

    @staticmethod
    def _build_timeline(a, _) -> Dict[str, Any]:
        milestone_elems = sorted(
            [e for e in a.elements if e.type in ("badge", "text_box", "shape")],
            key=lambda e: e.x_pct,
        )
        milestones = [
            {
                "label": e.label,
                "date": e.sublabel or "",
                "status": "complete",
            }
            for e in milestone_elems
            if e.label
        ]
        return {
            "type": "timeline",
            "title": a.title,
            "milestones": milestones,
        }

    @staticmethod
    def _build_matrix2x2(a, _) -> Dict[str, Any]:
        return {
            "type": "matrix_2x2",
            "title": a.title,
            "x_label": "",
            "y_label": "",
            "quadrant_labels": ["", "", "", ""],
            "items": [],
        }

    @staticmethod
    def _build_scorecard(a, _) -> Dict[str, Any]:
        row_elems = [e for e in a.elements if e.type in ("text_box", "shape") and e.label]
        items = [
            {
                "metric":  e.label,
                "status":  "green",
                "value":   e.sublabel or "",
                "comment": "",
            }
            for e in row_elems[:8]
        ]
        return {
            "type": "scorecard",
            "title": a.title,
            "items": items,
        }

    @staticmethod
    def _build_comparison(a, _) -> Dict[str, Any]:
        left_elems  = sorted(
            [e for e in a.elements if e.x_pct < 0.5 and e.label],
            key=lambda e: e.y_pct,
        )
        right_elems = sorted(
            [e for e in a.elements if e.x_pct >= 0.5 and e.label],
            key=lambda e: e.y_pct,
        )
        n = min(len(left_elems), len(right_elems), 6)
        rows = []
        for i in range(n):
            rows.append({
                "label": f"Point {i+1}",
                "left":  left_elems[i].label  if i < len(left_elems)  else "",
                "right": right_elems[i].label if i < len(right_elems) else "",
            })
        return {
            "type": "comparison",
            "title": a.title,
            "left_label":  "OPTION A",
            "right_label": "OPTION B",
            "winner": "right",
            "rows": rows,
        }

    @staticmethod
    def _build_table(a, _) -> Dict[str, Any]:
        return {
            "type": "table",
            "title": a.title,
            "headers": [],
            "rows": [],
            "caption": a.body_text or None,
        }

    @staticmethod
    def _build_chart(a, _) -> Dict[str, Any]:
        return {
            "type": "chart",
            "title": a.title,
            "chart_type": "bar",
            "categories": [],
            "values": [],
            "caption": a.body_text or None,
        }

    @staticmethod
    def _build_quote(a, _) -> Dict[str, Any]:
        return {
            "type": "quote",
            "quote": a.body_text or a.title,
            "attribution": a.subtitle or None,
        }

    @staticmethod
    def _build_section_divider(a, _) -> Dict[str, Any]:
        return {
            "type": "section_divider",
            "title": a.title,
            "description": a.subtitle or a.body_text or None,
        }

    @staticmethod
    def _build_executive_summary(a, _) -> Dict[str, Any]:
        bullets = [
            line.strip().lstrip("•●-").strip()
            for line in a.body_text.split("\n")
            if line.strip()
        ] if a.body_text else []
        return {
            "type": "executive_summary",
            "headline": a.title,
            "supporting_points": bullets,
            "call_to_action": a.subtitle or None,
        }

    @staticmethod
    def _build_image_content(a, image_bytes) -> Dict[str, Any]:
        data_uri = ""
        if image_bytes:
            data_uri = base64.b64encode(image_bytes).decode()
        bullets = [
            line.strip().lstrip("•●-").strip()
            for line in a.body_text.split("\n")
            if line.strip()
        ] if a.body_text else []
        return {
            "type": "image_content",
            "title": a.title,
            "image_side": "left",
            "data": data_uri,
            "format": "png",
            "bullets": bullets,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Image embed fallback
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _image_embed_spec(
        image_bytes: Optional[bytes],
        title: str,
        slide_index: int,
    ) -> Dict[str, Any]:
        """Embed the original slide image as a native PPTX image element."""
        spec: Dict[str, Any] = {
            "type": "image",
            "title": title or "",
            "width": 9.5,
            "height": 7.0,
            "align": "center",
        }
        if image_bytes:
            spec["data"]   = base64.b64encode(image_bytes).decode()
            spec["format"] = "png"
        return spec
