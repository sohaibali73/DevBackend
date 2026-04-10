"""
DeckPlanner
===========
Uses Claude to plan a full presentation structure from:
  - A document (PPTX, PDF, DOCX, HTML) — extract content → structure into slides
  - A text brief / prompt — "Create a 10-slide investor deck about X"
  - A topic + audience + goals — structured planning inputs

Output: A ``DeckPlan`` with ordered ``SlideBlueprint`` objects, each containing:
  - Slide type (from pptx_sandbox slide type vocabulary)
  - Title and content
  - Design recommendations
  - A ready-to-use pptx_sandbox spec dict

The DeckPlan can be fed directly into PptxSandbox.generate() to produce
a complete, branded, native-editable PPTX in seconds.

Usage
-----
    from core.vision.deck_planner import DeckPlanner
    from core.vision.content_extractor import ContentExtractor

    extractor = ContentExtractor()
    planner   = DeckPlanner()

    # From a document
    content = await extractor.extract(pdf_bytes, "pdf", "report.pdf")
    plan = await planner.plan_from_document(content, slide_count=10,
                                            audience="investors",
                                            tone="executive")
    specs = plan.to_pptx_specs()

    # From a brief
    plan = await planner.plan_from_brief(
        brief="Create a 12-slide strategy deck for Potomac's Q2 2026 board meeting",
        audience="board of directors",
        tone="formal",
    )
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── pptx_sandbox slide types (for plan validation) ────────────────────────────
VALID_SLIDE_TYPES = {
    "title", "content", "two_column", "three_column", "metrics", "process",
    "card_grid", "icon_grid", "hub_spoke", "timeline", "matrix_2x2",
    "scorecard", "comparison", "table", "chart", "quote", "section_divider",
    "executive_summary", "image_content", "image",
}


# =============================================================================
# Data classes
# =============================================================================

@dataclass
class SlideBlueprint:
    """Blueprint for a single slide in the planned deck."""
    slide_number:       int
    slide_type:         str              # pptx_sandbox slide type
    title:              str
    subtitle:           str = ""
    section_label:      str = ""
    bullets:            List[str] = field(default_factory=list)
    body_text:          str = ""
    background:         str = "light"   # "light" | "dark"
    design_notes:       str = ""        # e.g. "Use icon_grid with 4 hexagon badges"
    content_source:     str = ""        # "document_p3" | "generated" | "brief"
    # Specific content for special slide types
    metrics:            List[Dict] = field(default_factory=list)    # [{value, label}]
    cards:              List[Dict] = field(default_factory=list)    # [{title, text, color}]
    steps:              List[Dict] = field(default_factory=list)    # [{title, description}]
    milestones:         List[Dict] = field(default_factory=list)    # [{label, date, status}]
    table_headers:      List[str] = field(default_factory=list)
    table_rows:         List[List[str]] = field(default_factory=list)
    columns:            List[str] = field(default_factory=list)

    def to_pptx_spec(self) -> Dict[str, Any]:
        """Convert to a pptx_sandbox slide spec dict."""
        spec: Dict[str, Any] = {
            "type":    self.slide_type,
            "title":   self.title,
        }

        if self.subtitle:
            spec["subtitle"] = self.subtitle
        if self.section_label:
            spec["section_label"] = self.section_label
        if self.background == "dark":
            spec["background"] = "dark"

        # Type-specific fields
        if self.slide_type == "title":
            spec["tagline"] = self.subtitle or ""
            spec["style"] = "executive" if self.background == "dark" else "standard"

        elif self.slide_type in ("content", "executive_summary"):
            if self.bullets:
                spec["bullets"] = self.bullets
            elif self.body_text:
                spec["text"] = self.body_text
            if self.slide_type == "executive_summary":
                spec["headline"] = self.title
                spec["supporting_points"] = self.bullets

        elif self.slide_type in ("two_column", "three_column"):
            if self.columns:
                spec["columns"] = self.columns
            elif self.slide_type == "two_column" and self.bullets:
                mid = len(self.bullets) // 2
                spec["left_content"] = "\n".join(self.bullets[:mid])
                spec["right_content"] = "\n".join(self.bullets[mid:])

        elif self.slide_type == "metrics":
            spec["metrics"] = self.metrics or [
                {"value": b.split(":")[0].strip(), "label": b.split(":")[-1].strip()}
                for b in self.bullets[:6] if ":" in b
            ]
            spec["context"] = self.body_text or None

        elif self.slide_type == "process":
            spec["steps"] = self.steps or [
                {"title": b, "description": ""} for b in self.bullets[:6]
            ]

        elif self.slide_type == "card_grid":
            spec["cards"] = self.cards or [
                {"title": b, "color": "yellow"} for b in self.bullets[:4]
            ]
            spec["columns"] = len(spec["cards"])

        elif self.slide_type == "icon_grid":
            spec["items"] = [
                {"icon": "default", "title": b} for b in self.bullets[:6]
            ]

        elif self.slide_type == "timeline":
            spec["milestones"] = self.milestones or [
                {"label": b, "date": "", "status": "complete"} for b in self.bullets
            ]

        elif self.slide_type == "table":
            spec["headers"] = self.table_headers
            spec["rows"] = self.table_rows

        elif self.slide_type == "section_divider":
            spec["description"] = self.body_text or self.subtitle or None

        elif self.slide_type == "quote":
            spec["quote"] = self.body_text or (self.bullets[0] if self.bullets else "")
            spec["attribution"] = self.subtitle or None

        elif self.slide_type == "comparison":
            spec["left_label"] = "OPTION A"
            spec["right_label"] = "OPTION B"
            spec["winner"] = "right"
            mid = len(self.bullets) // 2
            spec["rows"] = [
                {"label": f"Point {i+1}", "left": self.bullets[i] if i < len(self.bullets) else "",
                 "right": self.bullets[i + mid] if (i + mid) < len(self.bullets) else ""}
                for i in range(min(mid, 6))
            ]

        elif self.slide_type == "content":
            if self.bullets:
                spec["bullets"] = self.bullets

        return spec

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slide_number":  self.slide_number,
            "slide_type":    self.slide_type,
            "title":         self.title,
            "subtitle":      self.subtitle,
            "section_label": self.section_label,
            "bullets":       self.bullets,
            "body_text":     self.body_text,
            "background":    self.background,
            "design_notes":  self.design_notes,
            "content_source": self.content_source,
        }


@dataclass
class DeckPlan:
    """A complete presentation plan."""
    title:       str
    audience:    str
    tone:        str
    slide_count: int
    slides:      List[SlideBlueprint] = field(default_factory=list)
    summary:     str = ""
    theme:       str = "potomac"        # branding theme

    def to_pptx_specs(self) -> List[Dict[str, Any]]:
        """Convert all slide blueprints to pptx_sandbox specs."""
        return [s.to_pptx_spec() for s in self.slides]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title":       self.title,
            "audience":    self.audience,
            "tone":        self.tone,
            "slide_count": self.slide_count,
            "summary":     self.summary,
            "slides":      [s.to_dict() for s in self.slides],
        }


# =============================================================================
# DeckPlanner
# =============================================================================

class DeckPlanner:
    """
    Uses Claude to plan a complete presentation structure.
    Outputs DeckPlan → SlideBlueprint → pptx_sandbox spec pipeline.
    """

    def __init__(self, model: str = "claude-opus-4-5"):
        self.model = model

    # ──────────────────────────────────────────────────────────────────────────
    # Plan from document content
    # ──────────────────────────────────────────────────────────────────────────

    async def plan_from_document(
        self,
        content,                         # DocumentContent from ContentExtractor
        slide_count:  int = 10,
        audience:     str = "general",
        tone:         str = "professional",
        focus:        str = "",          # optional: "summary" | "detail" | "executive"
    ) -> DeckPlan:
        """
        Plan a presentation from extracted document content.

        Takes the full transcript + page structure from ContentExtractor
        and uses Claude to design an optimal slide deck.

        Parameters
        ----------
        content      : DocumentContent from ContentExtractor.extract()
        slide_count  : target number of slides (Claude may adjust ±2)
        audience     : "investors" | "board" | "clients" | "general"
        tone         : "executive" | "professional" | "casual" | "formal"
        focus        : optional focus hint for Claude
        """
        transcript = content.full_transcript[:8000]  # truncate for API
        page_structure = "\n".join([
            f"Page {p.page_index}: {p.title or '(no title)'} [{p.page_type}]"
            for p in content.pages
        ])

        prompt = f"""You are an expert presentation designer.
Design a {slide_count}-slide PowerPoint presentation based on this document.

Document: {content.filename} ({content.file_type}, {content.page_count} pages)
Target audience: {audience}
Tone: {tone}
{f'Focus: {focus}' if focus else ''}

Document structure:
{page_structure}

Document content:
{transcript}

Design a presentation with exactly {slide_count} slides. Return ONLY a JSON array of slide objects.
Each slide object must have:
{{
  "slide_number": <int, 1-based>,
  "slide_type": "<one of: title|content|two_column|three_column|metrics|process|card_grid|icon_grid|timeline|section_divider|executive_summary|quote|comparison|table>",
  "title": "<slide title, ALL CAPS for Potomac brand>",
  "subtitle": "<subtitle or tagline, or empty string>",
  "section_label": "<small top-left category label, or empty>",
  "bullets": ["<bullet 1>", "<bullet 2>", ...],
  "body_text": "<paragraph text, or empty>",
  "background": "<light|dark>",
  "design_notes": "<1 sentence design recommendation>",
  "content_source": "<where this content came from>",
  "metrics": [{{"value": "<val>", "label": "<label>"}}],
  "cards": [{{"title": "<title>", "text": "<text>", "color": "yellow|dark|white"}}],
  "steps": [{{"title": "<step>", "description": "<desc>"}}],
  "milestones": [{{"label": "<label>", "date": "<date>", "status": "complete|in_progress|pending"}}],
  "table_headers": ["<col1>", "<col2>"],
  "table_rows": [["<r1c1>", "<r1c2>"]]
}}

Rules:
- First slide: type="title", dark background for Potomac brand
- Include section dividers every 3-4 slides for long decks
- Use metrics slide for key numbers
- Use card_grid for 4 equal-weight items (strategies, products, etc.)
- Use process for sequential steps
- Last slide: type="title" or "executive_summary" as a closing slide
- Keep all titles SHORT and ALL CAPS
- Return ONLY valid JSON array, no prose"""

        return await self._call_claude_for_plan(
            prompt=prompt,
            deck_title=content.filename.replace(".pptx", "").replace(".pdf", ""),
            slide_count=slide_count,
            audience=audience,
            tone=tone,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Plan from text brief
    # ──────────────────────────────────────────────────────────────────────────

    async def plan_from_brief(
        self,
        brief:        str,
        slide_count:  int = 10,
        audience:     str = "general",
        tone:         str = "professional",
        deck_title:   str = "",
    ) -> DeckPlan:
        """
        Plan a presentation from a free-text brief.

        Parameters
        ----------
        brief       : "Create a 10-slide investor deck about Potomac's Q2 strategy"
        slide_count : target number of slides
        audience    : target audience description
        tone        : presentation tone
        deck_title  : optional explicit deck title
        """
        prompt = f"""You are an expert presentation designer for Potomac, a financial firm.
Design a {slide_count}-slide PowerPoint presentation based on this brief.

Brief: {brief}
Target audience: {audience}
Tone: {tone}

Design {slide_count} slides that best communicate the brief. Return ONLY a JSON array of slide objects.
Each slide object must have all these fields:
{{
  "slide_number": <int, 1-based>,
  "slide_type": "<title|content|two_column|three_column|metrics|process|card_grid|icon_grid|timeline|section_divider|executive_summary|quote|comparison|table>",
  "title": "<ALL CAPS slide title>",
  "subtitle": "<subtitle or empty string>",
  "section_label": "<small top label or empty>",
  "bullets": ["<bullet points>"],
  "body_text": "<paragraph text or empty>",
  "background": "<light|dark>",
  "design_notes": "<design recommendation>",
  "content_source": "generated",
  "metrics": [],
  "cards": [],
  "steps": [],
  "milestones": [],
  "table_headers": [],
  "table_rows": []
}}

Rules:
- First slide must be type="title" with dark background (Potomac style)
- Use Potomac financial firm branding (YELLOW #FEC00F, DARK_GRAY #212121)
- ALL slide titles must be ALL CAPS
- Make it compelling, data-driven, executive-ready
- Return ONLY valid JSON array, no prose, no markdown"""

        title = deck_title or brief[:60].rstrip(".,!?")
        return await self._call_claude_for_plan(
            prompt=prompt,
            deck_title=title,
            slide_count=slide_count,
            audience=audience,
            tone=tone,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Quick outline (fast, no Claude — heuristic only)
    # ──────────────────────────────────────────────────────────────────────────

    def quick_outline_from_content(
        self,
        content,                    # DocumentContent
        slide_count: int = 10,
    ) -> DeckPlan:
        """
        Fast heuristic deck outline without calling Claude.
        Maps document pages → slide blueprints based on page_type + content.
        """
        slides = []
        slide_num = 1

        # Title slide
        title_page = next((p for p in content.pages if p.page_type == "title"), None)
        doc_title = title_page.title if title_page else content.filename.replace(".pdf", "")

        slides.append(SlideBlueprint(
            slide_number=slide_num,
            slide_type="title",
            title=doc_title.upper(),
            subtitle="",
            background="dark",
            content_source="document_title",
        ))
        slide_num += 1

        # Map remaining pages
        content_pages = [p for p in content.pages if p.page_type != "title"]

        # Sample evenly if too many pages
        if len(content_pages) > slide_count - 2:
            step = len(content_pages) / (slide_count - 2)
            content_pages = [content_pages[int(i * step)] for i in range(slide_count - 2)]

        for page in content_pages:
            st = self._infer_slide_type(page)
            slides.append(SlideBlueprint(
                slide_number=slide_num,
                slide_type=st,
                title=page.title.upper() if page.title else f"SLIDE {slide_num}",
                bullets=page.bullets[:6],
                body_text=page.body_text,
                table_headers=page.tables[0].headers if page.tables else [],
                table_rows=page.tables[0].rows[:10] if page.tables else [],
                content_source=f"document_p{page.page_index}",
            ))
            slide_num += 1

        return DeckPlan(
            title=doc_title,
            audience="general",
            tone="professional",
            slide_count=len(slides),
            slides=slides,
            summary=f"Auto-outline from {content.filename} ({content.page_count} pages)",
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    async def _call_claude_for_plan(
        self,
        prompt:      str,
        deck_title:  str,
        slide_count: int,
        audience:    str,
        tone:        str,
    ) -> DeckPlan:
        """Call Claude with a planning prompt and parse the result."""
        try:
            import anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY not set")

            client = anthropic.AsyncAnthropic(api_key=api_key)
            msg = await client.messages.create(
                model=self.model,
                max_tokens=4096,
                system="You are a precise JSON generator. Return only valid JSON arrays.",
                messages=[{"role": "user", "content": prompt}],
            )

            raw = msg.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?", "", raw).strip()
            raw = re.sub(r"```$", "", raw).strip()

            slides_data = json.loads(raw)
            slides = []
            for s in (slides_data if isinstance(slides_data, list) else []):
                stype = s.get("slide_type", "content")
                if stype not in VALID_SLIDE_TYPES:
                    stype = "content"
                slides.append(SlideBlueprint(
                    slide_number=int(s.get("slide_number", len(slides) + 1)),
                    slide_type=stype,
                    title=str(s.get("title", "")).upper() or f"SLIDE {len(slides) + 1}",
                    subtitle=str(s.get("subtitle", "") or ""),
                    section_label=str(s.get("section_label", "") or ""),
                    bullets=s.get("bullets") or [],
                    body_text=str(s.get("body_text", "") or ""),
                    background=str(s.get("background", "light") or "light"),
                    design_notes=str(s.get("design_notes", "") or ""),
                    content_source=str(s.get("content_source", "generated") or "generated"),
                    metrics=s.get("metrics") or [],
                    cards=s.get("cards") or [],
                    steps=s.get("steps") or [],
                    milestones=s.get("milestones") or [],
                    table_headers=s.get("table_headers") or [],
                    table_rows=s.get("table_rows") or [],
                    columns=s.get("columns") or [],
                ))

            return DeckPlan(
                title=deck_title,
                audience=audience,
                tone=tone,
                slide_count=len(slides),
                slides=slides,
                summary=f"AI-planned {len(slides)}-slide deck for {audience}",
            )

        except Exception as exc:
            logger.error("DeckPlanner._call_claude_for_plan failed: %s", exc)
            # Return minimal fallback plan
            return DeckPlan(
                title=deck_title,
                audience=audience,
                tone=tone,
                slide_count=1,
                slides=[SlideBlueprint(
                    slide_number=1,
                    slide_type="title",
                    title=deck_title.upper(),
                    design_notes="Fallback — Claude plan failed",
                )],
                summary=f"Fallback plan (Claude error: {exc})",
            )

    @staticmethod
    def _infer_slide_type(page) -> str:
        """Heuristic: infer the best slide type from a PageContent."""
        if page.page_type == "section_break":
            return "section_divider"
        if page.tables:
            return "table"
        n_bullets = len(page.bullets)
        if 3 <= n_bullets <= 6 and not page.body_text:
            return "content"
        if n_bullets > 6:
            return "two_column"
        if page.body_text and not page.bullets:
            return "content"
        return "content"
