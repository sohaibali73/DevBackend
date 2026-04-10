"""
VisionEngine
============
Sends slide images to Claude Vision (Anthropic) and returns structured
``SlideAnalysis`` JSON for each slide.

The analysis extracts everything needed to:
  - Understand content and intent of a slide
  - Replicate its design in native pptxgenjs elements
  - Match elements against the Potomac design library
  - Enable intelligent merging / revision decisions

Usage
-----
    from core.vision.vision_engine import VisionEngine, SlideAnalysis

    engine = VisionEngine()

    # Analyse a single slide
    analysis = await engine.analyze_slide(slide_image_bytes, slide_index=1)
    print(analysis.title, analysis.layout_type, analysis.color_palette)

    # Analyse all slides in a manifest
    analyses = await engine.analyze_manifest(manifest, concurrency=3)
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Model selection ────────────────────────────────────────────────────────────
# claude-opus-4-5 has the strongest vision understanding for complex layouts.
# claude-sonnet-3-5-20241022 is faster + cheaper — use for bulk analysis.
_DEFAULT_MODEL = os.environ.get("VISION_MODEL", "claude-opus-4-5")
_FAST_MODEL    = os.environ.get("VISION_FAST_MODEL", "claude-sonnet-4-5")


# =============================================================================
# Data classes
# =============================================================================

@dataclass
class DetectedElement:
    """A single visual element detected on a slide."""
    type:       str             # "text_box" | "shape" | "icon" | "image" | "chart"
                                # "table" | "logo" | "divider" | "badge" | "hexagon"
    label:      str = ""        # primary text content of the element
    sublabel:   str = ""        # secondary text (e.g., year below strategy name)
    icon:       str = ""        # icon identifier: "globe" | "shield" | "anchor" ...
    shape:      str = ""        # "rectangle" | "hexagon" | "ellipse" | "arrow"
    fill_color: str = ""        # hex without #, e.g. "FEC00F"
    text_color: str = ""        # hex without #
    font_family: str = ""       # detected font name
    font_size_approx: int = 0   # approximate pt size
    bold:       bool = False
    italic:     bool = False
    # Position as fractions of slide width/height (0.0–1.0)
    x_pct:      float = 0.0
    y_pct:      float = 0.0
    w_pct:      float = 0.0
    h_pct:      float = 0.0


@dataclass
class SlideAnalysis:
    """Complete structured understanding of one slide."""
    slide_index:   int
    layout_type:   str = ""        # "title" | "content" | "two_column" | "dark_hero"
                                   # "icon_grid" | "card_grid" | "metrics" | "timeline"
                                   # "table" | "chart" | "quote" | "section_divider"
                                   # "full_bleed_image" | "custom"
    background:    str = ""        # hex color e.g. "212121" (no #)
    background_type: str = "solid" # "solid" | "gradient" | "image"
    section_label: str = ""        # top-left section label e.g. "STRATEGIES"
    title:         str = ""        # main slide title text
    subtitle:      str = ""        # subtitle / body intro text
    body_text:     str = ""        # longer body / paragraph text
    color_palette: List[str] = field(default_factory=list)  # top 5 hex colors
    typography: Dict[str, Any] = field(default_factory=dict)
    # {title_font, body_font, title_size_approx, body_size_approx}
    elements:      List[DetectedElement] = field(default_factory=list)
    has_logo:      bool = False
    logo_variant:  str = ""        # "full" | "icon_yellow" | "icon_dark"
    has_chart:     bool = False
    has_table:     bool = False
    has_image:     bool = False     # non-logo image
    grid_columns:  int = 0         # detected column count (for icon grids, etc.)
    reconstruction_strategy: str = ""  # maps to pptx_sandbox slide type
    reconstruction_confidence: float = 0.0  # 0.0–1.0
    raw_description: str = ""      # Claude's free-text description for fallback
    error:         Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slide_index": self.slide_index,
            "layout_type": self.layout_type,
            "background": self.background,
            "background_type": self.background_type,
            "section_label": self.section_label,
            "title": self.title,
            "subtitle": self.subtitle,
            "body_text": self.body_text,
            "color_palette": self.color_palette,
            "typography": self.typography,
            "elements": [
                {
                    "type": e.type,
                    "label": e.label,
                    "sublabel": e.sublabel,
                    "icon": e.icon,
                    "shape": e.shape,
                    "fill_color": e.fill_color,
                    "text_color": e.text_color,
                    "font_family": e.font_family,
                    "font_size_approx": e.font_size_approx,
                    "bold": e.bold,
                    "italic": e.italic,
                    "position": {
                        "x_pct": e.x_pct, "y_pct": e.y_pct,
                        "w_pct": e.w_pct, "h_pct": e.h_pct,
                    },
                }
                for e in self.elements
            ],
            "has_logo": self.has_logo,
            "logo_variant": self.logo_variant,
            "has_chart": self.has_chart,
            "has_table": self.has_table,
            "has_image": self.has_image,
            "grid_columns": self.grid_columns,
            "reconstruction_strategy": self.reconstruction_strategy,
            "reconstruction_confidence": self.reconstruction_confidence,
            "raw_description": self.raw_description,
            "error": self.error,
        }


# =============================================================================
# System prompt for slide analysis
# =============================================================================

_SLIDE_ANALYSIS_SYSTEM = """
You are a senior presentation designer with deep expertise in PowerPoint, InDesign,
and corporate branding.  Your task is to analyse a slide image and return a precise,
structured JSON description of everything on that slide.

OUTPUT RULES
────────────
• Return ONLY valid JSON — no markdown fences, no prose, no commentary.
• Every string field must be present (use "" if not applicable).
• Every numeric field must be a number (use 0 if not applicable).
• Boolean fields must be true or false.
• All hex colour codes must be 6 uppercase characters with NO leading "#".
• Position percentages are fractions (0.0 to 1.0) of the slide width/height.

JSON SCHEMA
───────────
{
  "layout_type": "<one of: title | content | two_column | three_column | dark_hero
                   | icon_grid | card_grid | metrics | timeline | process | table
                   | chart | quote | section_divider | full_bleed_image | custom>",

  "background": "<6-char hex of dominant background colour>",
  "background_type": "<solid | gradient | image>",

  "section_label": "<small all-caps label in top-left corner, e.g. STRATEGIES>",
  "title": "<primary title text, verbatim, preserving CAPS>",
  "subtitle": "<subtitle or tagline text, verbatim>",
  "body_text": "<main paragraph / bullet text, verbatim, newlines as \\n>",

  "color_palette": ["<hex1>", "<hex2>", "<hex3>", "<hex4>", "<hex5>"],

  "typography": {
    "title_font": "<detected or guessed font name>",
    "body_font":  "<detected or guessed font name>",
    "title_size_approx": <integer pt>,
    "body_size_approx":  <integer pt>
  },

  "elements": [
    {
      "type": "<text_box | shape | icon | badge | hexagon | image | chart |
                table | logo | divider | button | callout>",
      "label": "<primary text of this element>",
      "sublabel": "<secondary text, e.g. year or description>",
      "icon": "<icon name if detectable: globe | shield | anchor | bear | plus |
                chart | lock | dollar | star | arrow | check | target | default>",
      "shape": "<rectangle | hexagon | ellipse | arrow | rounded_rect | diamond>",
      "fill_color": "<6-char hex of fill>",
      "text_color": "<6-char hex of text>",
      "font_family": "<font name>",
      "font_size_approx": <integer pt>,
      "bold": <true|false>,
      "italic": <true|false>,
      "position": {
        "x_pct": <0.0–1.0>,
        "y_pct": <0.0–1.0>,
        "w_pct": <0.0–1.0>,
        "h_pct": <0.0–1.0>
      }
    }
  ],

  "has_logo": <true|false>,
  "logo_variant": "<full | icon_yellow | icon_dark | none>",
  "has_chart": <true|false>,
  "has_table": <true|false>,
  "has_image": <true|false>,
  "grid_columns": <integer — number of equal columns in icon grids/card grids, 0 if N/A>,

  "reconstruction_strategy": "<best pptxgenjs slide type to recreate this:
    title_slide | content_slide | two_column | three_column | metrics | process
    | card_grid | icon_grid | hub_spoke | timeline | matrix_2x2 | scorecard
    | comparison | table | chart | quote | section_divider | executive_summary
    | image_content | full_image_embed>",

  "reconstruction_confidence": <0.0–1.0 how well the strategy matches the original>,

  "raw_description": "<2–3 sentences describing the slide design for human reference>"
}

IMPORTANT NOTES
───────────────
• If the slide is a single full-bleed image (common in InDesign exports), set
  layout_type="full_bleed_image" and reconstruction_strategy="full_image_embed".
• Potomac brand colours: YELLOW=#FEC00F, DARK_GRAY=#212121, WHITE=#FFFFFF.
• Detect the Potomac hexagonal logo (top-right corner typically).
• For icon grids with yellow hexagons (strategy slides), use layout_type="icon_grid"
  and reconstruction_strategy="card_grid" or "icon_grid".
• Be precise about text — copy it verbatim.
""".strip()


# =============================================================================
# VisionEngine
# =============================================================================

class VisionEngine:
    """
    Sends slide PNG images to Claude Vision and returns SlideAnalysis objects.

    Thread-safe.  All Claude API calls are async.
    """

    def __init__(
        self,
        model:        str = _DEFAULT_MODEL,
        max_tokens:   int = 2048,
        rate_limit_rps: float = 2.0,   # requests per second (conservative)
    ):
        self.model      = model
        self.max_tokens = max_tokens
        self._min_interval = 1.0 / rate_limit_rps
        self._last_call  = 0.0
        self._api_lock   = asyncio.Lock()

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    async def analyze_slide(
        self,
        image_bytes: bytes,
        slide_index: int = 1,
        extra_context: str = "",
        fast_mode: bool = False,
    ) -> SlideAnalysis:
        """
        Analyse a single slide image with Claude Vision.

        Parameters
        ----------
        image_bytes   : PNG bytes of the slide
        slide_index   : 1-based slide number (for labelling)
        extra_context : additional context to include in prompt
                        (e.g., "This is from the Potomac Meet deck")
        fast_mode     : if True, use the faster/cheaper model
        """
        if not image_bytes:
            return SlideAnalysis(
                slide_index=slide_index,
                error="No image bytes provided",
            )

        model = _FAST_MODEL if fast_mode else self.model
        b64   = base64.b64encode(image_bytes).decode()

        user_content: List[Dict[str, Any]] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": b64,
                },
            },
            {
                "type": "text",
                "text": (
                    f"Analyse this presentation slide (slide {slide_index})."
                    + (f"\n\nAdditional context: {extra_context}" if extra_context else "")
                    + "\n\nReturn the JSON analysis as specified."
                ),
            },
        ]

        try:
            raw_json = await self._call_claude(model, user_content)
            return self._parse_analysis(raw_json, slide_index)
        except Exception as exc:
            logger.error("VisionEngine.analyze_slide failed (slide %d): %s", slide_index, exc)
            return SlideAnalysis(
                slide_index=slide_index,
                error=str(exc),
            )

    async def analyze_manifest(
        self,
        manifest,                         # SlideManifest
        extra_context: str = "",
        concurrency: int = 3,
        fast_mode: bool = False,
    ) -> List[SlideAnalysis]:
        """
        Analyse all slides in a SlideManifest concurrently.

        Returns a list of SlideAnalysis in slide-index order.
        """
        sem = asyncio.Semaphore(concurrency)

        async def _analyze_one(slide_info):
            async with sem:
                return await self.analyze_slide(
                    image_bytes=slide_info.image_bytes,
                    slide_index=slide_info.index,
                    extra_context=extra_context,
                    fast_mode=fast_mode,
                )

        tasks = [_analyze_one(s) for s in manifest.slides]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        analyses: List[SlideAnalysis] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                slide_idx = manifest.slides[i].index if i < len(manifest.slides) else i + 1
                analyses.append(SlideAnalysis(
                    slide_index=slide_idx,
                    error=str(r),
                ))
            else:
                analyses.append(r)

        return sorted(analyses, key=lambda a: a.slide_index)

    async def describe_task(
        self,
        context_text: str,
        file_names: List[str],
        slide_manifests: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Use Claude to interpret a natural language task description and return
        a structured action plan for the PPTX intelligence pipeline.

        Returns
        -------
        {
          "action": "merge" | "reconstruct" | "analyze" | "create",
          "source_file": "<filename or null>",
          "target_file": "<filename or null>",
          "slide_range": [start, end] or null,
          "insert_after_slide": <int or null>,
          "description": "<human-readable summary of understood task>",
          "confidence": 0.0–1.0
        }
        """
        files_str = "\n".join(f"  - {fn}" for fn in file_names)
        manifests_str = ""
        if slide_manifests:
            manifests_str = "\nFile slide counts:\n" + "\n".join(
                f"  - {m['filename']}: {m['slide_count']} slides"
                for m in slide_manifests
            )

        prompt = f"""You are a presentation assistant. A user has uploaded these files:
{files_str}
{manifests_str}

The user's task or instruction is:
---
{context_text}
---

Analyse the task and return a JSON object with this exact structure:
{{
  "action": "<merge | reconstruct | analyze | create | update>",
  "source_file": "<filename of the source/donor deck, or null>",
  "target_file": "<filename of the destination/target deck, or null>",
  "slide_range": [<start_int>, <end_int>] or null,
  "insert_after_slide": <integer slide number to insert after, or null for append>,
  "output_filename": "<suggested output filename.pptx>",
  "description": "<1-2 sentence human-readable summary of what you understood>",
  "confidence": <0.0 to 1.0>
}}

Rules:
- "merge" = take slides from one deck and add them to another
- "reconstruct" = convert static image slides to native editable elements  
- "analyze" = just analyse and preview the uploaded files
- "create" = build a new presentation from scratch based on description
- "update" = modify data/text in an existing presentation
- slide_range is the range of slides to extract from source_file (1-based, inclusive)
- If multiple files and the task is a merge, determine which is source and which is target
- Return ONLY valid JSON, no prose"""

        try:
            import anthropic
            client = anthropic.AsyncAnthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY", "")
            )
            msg = await client.messages.create(
                model=self.model,
                max_tokens=512,
                system="You are a precise JSON generator. Return only valid JSON.",
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?", "", raw).strip()
            raw = re.sub(r"```$", "", raw).strip()
            return json.loads(raw)
        except Exception as exc:
            logger.error("describe_task failed: %s", exc)
            return {
                "action": "analyze",
                "source_file": None,
                "target_file": None,
                "slide_range": None,
                "insert_after_slide": None,
                "output_filename": "output.pptx",
                "description": f"Could not parse task: {exc}",
                "confidence": 0.0,
            }

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    async def _call_claude(
        self,
        model: str,
        user_content: List[Dict[str, Any]],
    ) -> str:
        """Rate-limited Claude API call."""
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("anthropic package not installed")

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")

        # Rate limiting
        async with self._api_lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

        client = anthropic.AsyncAnthropic(api_key=api_key)

        msg = await client.messages.create(
            model=model,
            max_tokens=self.max_tokens,
            system=_SLIDE_ANALYSIS_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )

        return msg.content[0].text.strip()

    def _parse_analysis(self, raw: str, slide_index: int) -> SlideAnalysis:
        """Parse Claude's JSON response into a SlideAnalysis object."""
        # Strip markdown fences if present
        clean = re.sub(r"^```(?:json)?", "", raw).strip()
        clean = re.sub(r"```$", "", clean).strip()

        try:
            data = json.loads(clean)
        except json.JSONDecodeError as exc:
            logger.warning("SlideAnalysis JSON parse error (slide %d): %s", slide_index, exc)
            return SlideAnalysis(
                slide_index=slide_index,
                raw_description=raw[:500],
                error=f"JSON parse error: {exc}",
            )

        # Parse elements
        elements: List[DetectedElement] = []
        for e in data.get("elements", []):
            pos = e.get("position", {})
            elements.append(DetectedElement(
                type=e.get("type", ""),
                label=e.get("label", ""),
                sublabel=e.get("sublabel", ""),
                icon=e.get("icon", ""),
                shape=e.get("shape", ""),
                fill_color=e.get("fill_color", ""),
                text_color=e.get("text_color", ""),
                font_family=e.get("font_family", ""),
                font_size_approx=int(e.get("font_size_approx", 0) or 0),
                bold=bool(e.get("bold", False)),
                italic=bool(e.get("italic", False)),
                x_pct=float(pos.get("x_pct", 0) or 0),
                y_pct=float(pos.get("y_pct", 0) or 0),
                w_pct=float(pos.get("w_pct", 0) or 0),
                h_pct=float(pos.get("h_pct", 0) or 0),
            ))

        return SlideAnalysis(
            slide_index=slide_index,
            layout_type=str(data.get("layout_type", "") or ""),
            background=str(data.get("background", "") or "").upper().lstrip("#"),
            background_type=str(data.get("background_type", "solid") or "solid"),
            section_label=str(data.get("section_label", "") or ""),
            title=str(data.get("title", "") or ""),
            subtitle=str(data.get("subtitle", "") or ""),
            body_text=str(data.get("body_text", "") or ""),
            color_palette=[
                c.upper().lstrip("#")
                for c in (data.get("color_palette") or [])[:5]
            ],
            typography=data.get("typography") or {},
            elements=elements,
            has_logo=bool(data.get("has_logo", False)),
            logo_variant=str(data.get("logo_variant", "") or ""),
            has_chart=bool(data.get("has_chart", False)),
            has_table=bool(data.get("has_table", False)),
            has_image=bool(data.get("has_image", False)),
            grid_columns=int(data.get("grid_columns", 0) or 0),
            reconstruction_strategy=str(data.get("reconstruction_strategy", "") or ""),
            reconstruction_confidence=float(data.get("reconstruction_confidence", 0) or 0),
            raw_description=str(data.get("raw_description", "") or ""),
        )
