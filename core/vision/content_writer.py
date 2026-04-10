"""
ContentWriter
=============
AI-powered content generation and enhancement for individual slides.

Capabilities
------------
enhance_slide_content   Improve/rewrite existing slide text (concise, punchy, executive)
generate_speaker_notes  Auto-generate speaker notes for every slide
suggest_alternatives    Give 3 alternative ways to present the same information
generate_slide_content  Create content for a slide given a topic + slide_type
summarize_for_exec      Distill detailed content into executive-level bullets
rewrite_as_headline     Turn any text into a single powerful headline
expand_bullets          Expand brief bullet points into fuller content

Usage
-----
    from core.vision.content_writer import ContentWriter

    writer = ContentWriter()

    # Generate speaker notes for all slides
    notes = await writer.generate_speaker_notes(deck_plan)

    # Improve a single slide's content
    improved = await writer.enhance_slide_content(
        title="Q1 PERFORMANCE",
        bullets=["Revenue up 12%", "Cost down 3%", "New clients: 8"],
        instruction="Make this more executive-level, add context"
    )

    # Generate fresh content for a slide type
    content = await writer.generate_slide_content(
        topic="Potomac's investment philosophy",
        slide_type="card_grid",
        audience="investors",
        tone="confident",
    )
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Data classes
# =============================================================================

@dataclass
class SpeakerNote:
    """Speaker notes for a single slide."""
    slide_index: int
    slide_title: str
    notes:       str           # full speaker notes text (150-300 words)
    key_points:  List[str] = field(default_factory=list)  # 3-5 key talking points
    transitions: str = ""     # how to transition to next slide

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slide_index": self.slide_index,
            "slide_title": self.slide_title,
            "notes":       self.notes,
            "key_points":  self.key_points,
            "transitions": self.transitions,
        }


@dataclass
class ContentSuggestion:
    """An alternative content suggestion for a slide."""
    suggestion_index: int
    slide_type:      str
    title:           str
    bullets:         List[str] = field(default_factory=list)
    body_text:       str = ""
    design_notes:    str = ""
    rationale:       str = ""   # why this approach works

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suggestion_index": self.suggestion_index,
            "slide_type":       self.slide_type,
            "title":            self.title,
            "bullets":          self.bullets,
            "body_text":        self.body_text,
            "design_notes":     self.design_notes,
            "rationale":        self.rationale,
        }


# =============================================================================
# ContentWriter
# =============================================================================

class ContentWriter:
    """
    AI-powered slide content generation and enhancement.
    All methods are async and use Claude (Anthropic).
    """

    def __init__(
        self,
        model:      str = "claude-opus-4-5",
        fast_model: str = "claude-sonnet-4-5",
    ):
        self.model      = model
        self.fast_model = fast_model

    # ──────────────────────────────────────────────────────────────────────────
    # Speaker notes
    # ──────────────────────────────────────────────────────────────────────────

    async def generate_speaker_notes(
        self,
        deck_plan,                    # DeckPlan from DeckPlanner, or List[SlideBlueprint]
        audience:  str = "general",
        context:   str = "",          # extra context about the presentation
        fast:      bool = True,       # use faster model for bulk generation
    ) -> List[SpeakerNote]:
        """
        Generate speaker notes for every slide in a deck plan.

        Parameters
        ----------
        deck_plan : DeckPlan or list of slide dicts
        audience  : who you're presenting to
        context   : extra context (e.g., "Q2 earnings call", "investor day")
        fast      : use faster model (recommended for full deck)

        Returns a list of SpeakerNote objects (one per slide).
        """
        slides = deck_plan.slides if hasattr(deck_plan, "slides") else deck_plan
        model  = self.fast_model if fast else self.model

        sem = asyncio.Semaphore(4)

        async def _notes_for_slide(slide) -> SpeakerNote:
            async with sem:
                return await self._generate_single_speaker_note(
                    slide, audience, context, model
                )

        results = await asyncio.gather(*[_notes_for_slide(s) for s in slides],
                                       return_exceptions=True)

        notes = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                slide = slides[i]
                notes.append(SpeakerNote(
                    slide_index=getattr(slide, "slide_number", i + 1),
                    slide_title=getattr(slide, "title", ""),
                    notes=f"[Speaker notes generation failed: {r}]",
                ))
            else:
                notes.append(r)

        return notes

    async def _generate_single_speaker_note(
        self, slide, audience: str, context: str, model: str
    ) -> SpeakerNote:
        """Generate speaker notes for one slide."""
        slide_num   = getattr(slide, "slide_number", 1)
        slide_title = getattr(slide, "title", "")
        slide_type  = getattr(slide, "slide_type", "content")
        bullets     = getattr(slide, "bullets", [])
        body        = getattr(slide, "body_text", "")

        content_summary = "\n".join(bullets[:6]) if bullets else body[:300]

        prompt = f"""You are an expert financial presenter.
Generate speaker notes for slide {slide_num} of a presentation for: {audience}
{f'Context: {context}' if context else ''}

Slide title: {slide_title}
Slide type: {slide_type}
Content: {content_summary}

Return ONLY a JSON object:
{{
  "notes": "<150-250 word speaker notes — natural speech, not bullet points>",
  "key_points": ["<3-5 key talking points>"],
  "transitions": "<1 sentence: how to transition to the next slide>"
}}"""

        raw = await self._call_claude(prompt, model, max_tokens=512)
        try:
            data = json.loads(raw)
            return SpeakerNote(
                slide_index=slide_num,
                slide_title=slide_title,
                notes=data.get("notes", ""),
                key_points=data.get("key_points") or [],
                transitions=data.get("transitions", ""),
            )
        except Exception as exc:
            return SpeakerNote(
                slide_index=slide_num,
                slide_title=slide_title,
                notes=raw[:400],
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Slide content enhancement
    # ──────────────────────────────────────────────────────────────────────────

    async def enhance_slide_content(
        self,
        title:       str,
        bullets:     List[str] = None,
        body_text:   str = "",
        slide_type:  str = "content",
        instruction: str = "Make this more concise and executive-level",
        audience:    str = "general",
    ) -> Dict[str, Any]:
        """
        Improve existing slide content with AI.

        Parameters
        ----------
        title       : current slide title
        bullets     : current bullet points
        body_text   : current body text
        slide_type  : hint for pptxgenjs slide type
        instruction : what to do with the content
        audience    : target audience

        Returns
        -------
        Dict with: title, bullets, body_text, design_notes
        """
        bullets_text = "\n".join(f"• {b}" for b in (bullets or []))

        prompt = f"""You are an expert presentation writer.
Improve this slide content: {instruction}
Audience: {audience}
Slide type: {slide_type}

Current title: {title}
Current bullets:
{bullets_text}
Current body: {body_text}

Return ONLY a JSON object:
{{
  "title": "<improved title, ALL CAPS, max 8 words>",
  "bullets": ["<improved bullet 1>", "<improved bullet 2>", ...],
  "body_text": "<improved body text or empty string>",
  "design_notes": "<1 sentence design suggestion>"
}}"""

        raw = await self._call_claude(prompt, self.fast_model, max_tokens=512)
        try:
            return json.loads(raw)
        except Exception:
            return {
                "title": title,
                "bullets": bullets or [],
                "body_text": body_text,
                "design_notes": "",
            }

    # ──────────────────────────────────────────────────────────────────────────
    # Fresh slide content generation
    # ──────────────────────────────────────────────────────────────────────────

    async def generate_slide_content(
        self,
        topic:      str,
        slide_type: str = "content",
        audience:   str = "general",
        tone:       str = "professional",
        context:    str = "",
    ) -> Dict[str, Any]:
        """
        Generate fresh slide content for a given topic and slide type.

        Returns a pptx_sandbox-compatible partial spec dict.
        """
        type_hints = {
            "card_grid": "4 equal-weight items each with a title and 1-2 sentence description",
            "process":   "4-6 sequential steps with titles and short descriptions",
            "metrics":   "4-6 key metrics each with a number/value and a label",
            "timeline":  "4-8 milestones with labels and approximate dates",
            "comparison": "6-8 comparison points between two options",
            "content":   "6-8 concise bullet points",
            "two_column": "2 equal sections with headers and 4-6 bullets each",
            "executive_summary": "1 powerful headline + 4-6 supporting bullet points",
        }
        hint = type_hints.get(slide_type, "6-8 concise bullet points")

        prompt = f"""You are an expert financial presentation writer for Potomac.
Create slide content about: {topic}
Slide type: {slide_type} ({hint})
Audience: {audience}
Tone: {tone}
{f'Context: {context}' if context else ''}

Return ONLY a JSON object matching the slide type:
{{
  "title": "<ALL CAPS slide title, max 8 words>",
  "subtitle": "<subtitle or tagline, or empty>",
  "section_label": "<small category label, or empty>",
  "bullets": ["<bullet 1>", ...],
  "body_text": "<paragraph text, or empty>",
  "metrics": [{{"value": "<value>", "label": "<label>"}}],
  "cards": [{{"title": "<title>", "text": "<1-2 sentences>", "color": "yellow|dark|white"}}],
  "steps": [{{"title": "<step>", "description": "<1 sentence>"}}],
  "milestones": [{{"label": "<label>", "date": "<date>", "status": "complete|in_progress|pending"}}],
  "design_notes": "<design recommendation>"
}}

Return only the fields relevant to the slide type. Return ONLY valid JSON."""

        raw = await self._call_claude(prompt, self.model, max_tokens=1024)
        try:
            data = json.loads(raw)
            data["slide_type"] = slide_type
            return data
        except Exception as exc:
            return {
                "slide_type": slide_type,
                "title": topic.upper()[:50],
                "bullets": [],
                "design_notes": f"Content generation failed: {exc}",
            }

    # ──────────────────────────────────────────────────────────────────────────
    # Alternative suggestions
    # ──────────────────────────────────────────────────────────────────────────

    async def suggest_alternatives(
        self,
        title:      str,
        bullets:    List[str] = None,
        body_text:  str = "",
        slide_type: str = "content",
        count:      int = 3,
    ) -> List[ContentSuggestion]:
        """
        Generate N alternative ways to present the same slide content.

        Useful for the UI's "suggest alternatives" feature where users can
        pick the version they like best.
        """
        current = "\n".join(f"• {b}" for b in (bullets or [])) or body_text

        prompt = f"""You are an expert presentation designer.
Suggest {count} different ways to present this slide content.

Current title: {title}
Current content: {current}
Current slide type: {slide_type}

Return ONLY a JSON array of {count} suggestion objects:
[
  {{
    "suggestion_index": 1,
    "slide_type": "<best slide type for this approach>",
    "title": "<alternative title, ALL CAPS>",
    "bullets": ["<bullet>", ...],
    "body_text": "<or paragraph text>",
    "design_notes": "<visual design recommendation>",
    "rationale": "<1 sentence: why this approach works>"
  }},
  ...
]

Make each suggestion meaningfully different (different layout, framing, or emphasis).
Return ONLY valid JSON array."""

        raw = await self._call_claude(prompt, self.model, max_tokens=1024)
        try:
            items = json.loads(raw)
            return [
                ContentSuggestion(
                    suggestion_index=s.get("suggestion_index", i + 1),
                    slide_type=s.get("slide_type", "content"),
                    title=s.get("title", title),
                    bullets=s.get("bullets") or [],
                    body_text=s.get("body_text", ""),
                    design_notes=s.get("design_notes", ""),
                    rationale=s.get("rationale", ""),
                )
                for i, s in enumerate(items if isinstance(items, list) else [])
            ]
        except Exception as exc:
            logger.warning("suggest_alternatives parse failed: %s", exc)
            return []

    # ──────────────────────────────────────────────────────────────────────────
    # Summarization utilities
    # ──────────────────────────────────────────────────────────────────────────

    async def summarize_for_exec(
        self,
        text:          str,
        max_bullets:   int = 5,
        audience:      str = "executive",
    ) -> List[str]:
        """Distill any text into executive-level bullet points."""
        prompt = f"""Distill this content into {max_bullets} executive-level bullet points for: {audience}

Content:
{text[:3000]}

Rules:
- Each bullet is one concise sentence
- Lead with the impact/outcome
- Use numbers and specifics where possible
- No jargon

Return ONLY a JSON array of strings: ["bullet 1", "bullet 2", ...]"""

        raw = await self._call_claude(prompt, self.fast_model, max_tokens=512)
        try:
            return json.loads(raw)
        except Exception:
            return [line.strip().lstrip("•-* ") for line in raw.split("\n")
                    if line.strip() and not line.strip().startswith("[")][:max_bullets]

    async def rewrite_as_headline(self, text: str, style: str = "bold") -> str:
        """Rewrite any text as a single powerful presentation headline."""
        prompt = f"""Rewrite this as a single powerful presentation headline.
Style: {style} (bold, action-oriented, max 8 words, ALL CAPS)

Text: {text[:500]}

Return ONLY the headline text, nothing else."""

        raw = await self._call_claude(prompt, self.fast_model, max_tokens=64)
        return raw.strip().upper()[:80]

    async def expand_bullets(
        self,
        bullets:    List[str],
        slide_type: str = "content",
        audience:   str = "general",
    ) -> Dict[str, Any]:
        """Expand brief bullets into richer slide content."""
        bullets_text = "\n".join(f"• {b}" for b in bullets[:8])

        prompt = f"""You are a presentation writer. Expand these brief bullets into richer slide content.
Slide type: {slide_type}, Audience: {audience}

Current bullets:
{bullets_text}

Return ONLY a JSON object:
{{
  "bullets": ["<expanded bullet 1>", ...],
  "body_text": "<optional intro paragraph>",
  "design_notes": "<layout recommendation>"
}}"""

        raw = await self._call_claude(prompt, self.fast_model, max_tokens=512)
        try:
            return json.loads(raw)
        except Exception:
            return {"bullets": bullets, "body_text": "", "design_notes": ""}

    async def generate_deck_summary(
        self,
        deck_plan,           # DeckPlan
        format: str = "executive",   # "executive" | "detailed" | "one_liner"
    ) -> str:
        """Generate a summary of the entire deck plan."""
        titles = [s.title for s in deck_plan.slides]
        titles_str = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))

        format_instructions = {
            "executive": "3-4 sentences, executive level, focus on key message and call to action",
            "detailed":  "1-2 paragraphs covering structure, key themes, and flow",
            "one_liner": "One powerful sentence that captures the deck's core message",
        }
        instruction = format_instructions.get(format, format_instructions["executive"])

        prompt = f"""You are summarizing a presentation for {deck_plan.audience}.
Slide titles:
{titles_str}

Write a {format} summary of this presentation:
{instruction}

Return ONLY the summary text, no JSON."""

        return await self._call_claude(prompt, self.fast_model, max_tokens=256)

    # ──────────────────────────────────────────────────────────────────────────
    # Claude caller
    # ──────────────────────────────────────────────────────────────────────────

    async def _call_claude(
        self,
        prompt:     str,
        model:      str,
        max_tokens: int = 512,
    ) -> str:
        """Simple Claude API call with JSON-stripping."""
        try:
            import anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY not set")

            client = anthropic.AsyncAnthropic(api_key=api_key)
            msg = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system="You are a precise JSON generator. Return only valid JSON or plain text as instructed.",
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?", "", raw).strip()
            raw = re.sub(r"```$", "", raw).strip()
            return raw

        except Exception as exc:
            logger.error("ContentWriter._call_claude failed: %s", exc)
            return json.dumps({})
