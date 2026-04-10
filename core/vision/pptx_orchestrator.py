"""
PptxOrchestrator
================
The master intelligence router for the PPTX pipeline.

Takes any natural language user prompt + uploaded files and automatically:
1. Classifies the intent into one of 20+ action types
2. Plans the multi-step execution sequence
3. Executes the pipeline (calling render, vision, merge, generate, etc.)
4. Returns a unified result with previews, download URL, and explanation

This is the "Superintendent" that makes the entire /pptx/* system accessible
through a single prompt — no frontend logic needed to choose the right endpoint.

Intent Classification
---------------------
merge              "Take slides 15-19 from deck A and add to deck B"
analyze            "What's on each slide of this deck?"
reconstruct        "Convert these static image slides to editable"
generate_from_doc  "Turn this PDF into a 10-slide presentation"
generate_from_brief "Create an investor pitch about..."
export             "Convert this to PDF" / "Export all slides as images"
summarize          "What does this report say? Give me 5 bullets"
compare            "Find duplicate slides between these two decks"
brand_audit        "Check this deck for brand compliance"
brand_fix          "Fix brand violations automatically"
extract_text       "Get all the text from these slides"
speaker_notes      "Write speaker notes for this deck"
revise             "Delete slide 5 and change Q1 to Q2"
plan               "Plan a 12-slide deck about X"
enhance            "Make slide 3 more executive"
suggest            "Show me 3 alternatives for this slide"
template           "Use the strategy hexagon template"
library_search     "Find slides about investment strategy"
library_index      "Save these slides to the library"
session_create     "Start editing this deck"

Usage
-----
    from core.vision.pptx_orchestrator import PptxOrchestrator

    orch = PptxOrchestrator()
    result = await orch.execute(
        prompt="Take slides 15-19 from meet_potomac.pptx and add to composite.pptx",
        ingested=[
            {"filename": "meet_potomac.pptx", "file_type": "pptx", "bytes": ...},
            {"filename": "composite.pptx", "file_type": "pptx", "bytes": ...},
        ],
        user_id="user123",
        job_id="abc-123",
    )
    print(result.action, result.download_url, result.explanation)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "/data"))
_JOB_STORE    = _STORAGE_ROOT / "pptx_jobs"

# ── Recognised intent types ────────────────────────────────────────────────────
INTENT_TYPES = [
    "merge",               # Cherry-pick slides from multiple decks
    "analyze",             # Vision analysis of all slides
    "reconstruct",         # Static-image slides → native editable
    "generate_from_doc",   # Document → AI planned PPTX
    "generate_from_brief", # Text description → AI planned PPTX
    "export_pdf",          # PPTX → PDF
    "export_images",       # PPTX → per-slide PNG ZIP
    "export_html",         # PPTX → HTML
    "summarize",           # Document → executive bullets
    "compare",             # Find similar slides between two decks
    "brand_audit",         # Brand compliance scoring
    "brand_fix",           # Brand auto-correction
    "extract_text",        # OCR / text extraction
    "speaker_notes",       # Auto-generate speaker notes
    "revise",              # NLP-driven revision (delete/reorder/replace)
    "plan",                # Deck structure plan without generating
    "enhance_slide",       # AI improve a single slide's content
    "suggest_alternatives",# Alternative layouts for a slide
    "template",            # Use/generate from a template
    "library_search",      # Search corporate slide library
    "library_index",       # Add slides to library
    "session_create",      # Start stateful editing session
    "preview",             # Just render and show previews
    "unknown",             # Fallback → show analysis
]


# =============================================================================
# Result dataclass
# =============================================================================

@dataclass
class OrchestratorResult:
    """Unified result from any PPTX orchestration action."""
    success:      bool
    job_id:       str
    action:       str                    # which intent was executed
    explanation:  str                    # human-readable what was done
    preview_urls: List[str] = field(default_factory=list)
    download_url: Optional[str] = None  # download the output PPTX/PDF/ZIP
    slide_count:  int = 0
    plan:         Optional[Dict] = None  # DeckPlan if generated
    analyses:     Optional[List] = None  # SlideAnalysis results
    transcript:   Optional[str] = None  # extracted text
    audit:        Optional[Dict] = None  # brand audit report
    speaker_notes: Optional[List] = None
    session_id:   Optional[str] = None  # if session was created
    suggestions:  Optional[List] = None # template/alternative suggestions
    extra:        Dict[str, Any] = field(default_factory=dict)
    elapsed_ms:   float = 0.0
    error:        Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success":       self.success,
            "job_id":        self.job_id,
            "action":        self.action,
            "explanation":   self.explanation,
            "preview_urls":  self.preview_urls,
            "download_url":  self.download_url,
            "slide_count":   self.slide_count,
            "plan":          self.plan,
            "analyses":      self.analyses,
            "transcript":    self.transcript,
            "audit":         self.audit,
            "speaker_notes": self.speaker_notes,
            "session_id":    self.session_id,
            "suggestions":   self.suggestions,
            "extra":         self.extra,
            "elapsed_ms":    round(self.elapsed_ms, 1),
            "error":         self.error,
        }


# =============================================================================
# PptxOrchestrator
# =============================================================================

class PptxOrchestrator:
    """
    Master intent router for the PPTX Intelligence Pipeline.

    Classifies user prompts → executes the right sub-pipeline →
    returns a unified OrchestratorResult.
    """

    def __init__(self, model: str = "claude-opus-4-5"):
        self.model = model

    # ──────────────────────────────────────────────────────────────────────────
    # Main entry point
    # ──────────────────────────────────────────────────────────────────────────

    async def execute(
        self,
        prompt:       str,
        ingested:     List[Dict[str, Any]],   # from _ingest_uploads()
        user_id:      str,
        job_id:       Optional[str] = None,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> OrchestratorResult:
        """
        The main orchestration entry point.

        1. Classify intent from prompt + file context
        2. Extract parameters (slide ranges, counts, etc.)
        3. Execute the right pipeline
        4. Return unified OrchestratorResult

        Parameters
        ----------
        prompt       : user's natural language request
        ingested     : list of {filename, file_type, bytes} dicts
        user_id      : authenticated user
        job_id       : optional existing job_id to build on
        extra_params : optional overrides (e.g., {"slide_count": 12})
        """
        start = time.time()
        job_id = job_id or str(uuid.uuid4())
        extra_params = extra_params or {}

        # ── 1. Classify intent ────────────────────────────────────────────────
        intent_result = await self._classify_intent(prompt, ingested)
        action  = intent_result.get("action", "unknown")
        params  = intent_result.get("params", {})
        params.update(extra_params)

        logger.info("PptxOrchestrator: intent=%s params=%s", action, params)

        # ── 2. Execute the right sub-pipeline ─────────────────────────────────
        try:
            result = await self._dispatch(
                action=action,
                params=params,
                prompt=prompt,
                ingested=ingested,
                user_id=user_id,
                job_id=job_id,
            )
        except Exception as exc:
            logger.error("PptxOrchestrator dispatch failed: %s", exc, exc_info=True)
            result = OrchestratorResult(
                success=False,
                job_id=job_id,
                action=action,
                explanation=f"Execution failed: {exc}",
                error=str(exc),
            )

        result.elapsed_ms = round((time.time() - start) * 1000, 1)
        return result

    # ──────────────────────────────────────────────────────────────────────────
    # Intent classification
    # ──────────────────────────────────────────────────────────────────────────

    async def _classify_intent(
        self,
        prompt:   str,
        ingested: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Use Claude to classify the user's intent and extract parameters.

        Returns:
        {
          "action": "merge",
          "params": {
            "source_file": "meet_potomac.pptx",
            "target_file": "composite.pptx",
            "slide_range": [15, 19],
            "slide_count": 10,
            "audience": "investors",
            "tone": "executive",
            "output_filename": "merged.pptx",
            ...
          },
          "explanation": "Merging slides 15-19 from meet_potomac into composite deck",
          "confidence": 0.97
        }
        """
        file_context = "\n".join(
            f"  - {fi['filename']} ({fi['file_type']}, {len(fi['bytes']) // 1024}KB)"
            for fi in ingested
        ) if ingested else "  (no files uploaded)"

        intent_prompt = f"""You are a PPTX Intelligence Router.
Classify this user request and extract parameters.

User request: "{prompt}"

Uploaded files:
{file_context}

Classify the intent as ONE of:
{', '.join(INTENT_TYPES)}

Return ONLY a JSON object:
{{
  "action": "<intent_type>",
  "explanation": "<1-2 sentence explanation of what will be done>",
  "confidence": <0.0-1.0>,
  "params": {{
    "source_file": "<filename if merging>",
    "target_file": "<filename if merging>",
    "slide_range": [<start>, <end>] or null,
    "insert_after_slide": <int or null>,
    "slide_count": <target slide count for generation>,
    "audience": "<audience if generating>",
    "tone": "<tone if generating>",
    "brief": "<topic or brief if generating from scratch>",
    "focus": "<specific focus for document generation>",
    "output_filename": "<suggested output filename>",
    "export_format": "<pdf|images|html|thumbnails>",
    "dpi": <72|150|200|300>,
    "max_bullets": <int for summarize>,
    "instruction": "<revision instruction if revising>",
    "template_id": "<template_id if template action>",
    "search_query": "<query if library search>",
    "slide_index": <int if enhancing a specific slide>,
    "force_embed": <true|false for reconstruction>,
    "quick_mode": <true|false for fast generation>
  }}
}}

Action guidance:
- "merge": user wants slides from one deck moved/copied to another
- "analyze": user wants to understand what's in slides (vision analysis)
- "reconstruct": user wants static image slides made editable
- "generate_from_doc": user uploaded a document and wants a deck from it
- "generate_from_brief": user described a deck topic without uploading a source document
- "export_pdf": user wants a PDF version
- "export_images": user wants slide images
- "summarize": user wants key points extracted as bullets
- "compare": user wants to find similar/duplicate slides
- "brand_audit": user wants brand compliance check
- "brand_fix": user wants brand violations auto-corrected
- "extract_text": user wants text extracted (OCR for image slides)
- "speaker_notes": user wants speaker notes generated
- "revise": user wants changes to existing slides (delete/reorder/replace text)
- "plan": user wants a deck outline without generating the PPTX yet
- "enhance_slide": user wants one slide's content improved
- "suggest_alternatives": user wants 3 layout options for a slide
- "template": user wants to use a specific template
- "library_search": user wants to find slides in the corporate library
- "library_index": user wants to save slides to the library
- "session_create": user wants to start an interactive editing session
- "preview": user just wants to see the slides (default if unclear)
- "unknown": if truly unclear, treat as "preview"

Return ONLY valid JSON."""

        try:
            import anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                return self._heuristic_classify(prompt, ingested)

            client = anthropic.AsyncAnthropic(api_key=api_key)
            msg = await client.messages.create(
                model=self.model,
                max_tokens=512,
                system="You are a precise JSON classifier. Return only valid JSON.",
                messages=[{"role": "user", "content": intent_prompt}],
            )
            raw = msg.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?", "", raw).strip()
            raw = re.sub(r"```$", "", raw).strip()
            result = json.loads(raw)

            # Validate action
            if result.get("action") not in INTENT_TYPES:
                result["action"] = "preview"

            return result

        except Exception as exc:
            logger.warning("Intent classification failed: %s — using heuristic", exc)
            return self._heuristic_classify(prompt, ingested)

    def _heuristic_classify(
        self, prompt: str, ingested: List[Dict]
    ) -> Dict[str, Any]:
        """Fast regex-based intent classification without Claude."""
        p = prompt.lower()
        n_files = len(ingested)

        # Merge patterns
        if any(w in p for w in ["merge", "combine", "add slides", "incorporate", "insert slides", "take slides"]):
            return {
                "action": "merge",
                "explanation": "Merging slides between the uploaded decks",
                "confidence": 0.7,
                "params": {},
            }

        # Generate from brief (no files, or text description)
        if any(w in p for w in ["create", "generate", "build", "make", "write"]) and not ingested:
            return {
                "action": "generate_from_brief",
                "explanation": "Generating a new presentation from the description",
                "confidence": 0.7,
                "params": {"brief": prompt},
            }

        # Generate from document
        if any(w in p for w in ["create", "generate", "build", "convert"]) and ingested:
            return {
                "action": "generate_from_doc",
                "explanation": "Generating a presentation from the uploaded document",
                "confidence": 0.6,
                "params": {},
            }

        # Export
        if "pdf" in p:
            return {"action": "export_pdf", "explanation": "Exporting to PDF", "confidence": 0.9, "params": {}}
        if any(w in p for w in ["image", "png", "jpg", "slides as"]):
            return {"action": "export_images", "explanation": "Exporting slides as images", "confidence": 0.8, "params": {}}

        # Summarize
        if any(w in p for w in ["summarize", "summary", "key points", "bullet", "what does"]):
            return {"action": "summarize", "explanation": "Summarizing document content", "confidence": 0.8, "params": {}}

        # Revise
        if any(w in p for w in ["delete", "remove slide", "change", "replace", "reorder", "move slide"]):
            return {"action": "revise", "explanation": "Revising the presentation", "confidence": 0.75, "params": {"instruction": prompt}}

        # Speaker notes
        if any(w in p for w in ["speaker notes", "notes", "talking points", "script"]):
            return {"action": "speaker_notes", "explanation": "Generating speaker notes", "confidence": 0.85, "params": {}}

        # Brand
        if any(w in p for w in ["brand", "compliance", "branding", "logo", "colors"]):
            return {"action": "brand_audit", "explanation": "Checking brand compliance", "confidence": 0.8, "params": {}}

        # Extract text
        if any(w in p for w in ["extract", "ocr", "text", "transcript", "read"]):
            return {"action": "extract_text", "explanation": "Extracting text from slides", "confidence": 0.75, "params": {}}

        # Default
        return {
            "action": "preview" if ingested else "generate_from_brief",
            "explanation": "Showing slide previews" if ingested else "Please describe what you want to create",
            "confidence": 0.4,
            "params": {},
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Dispatcher
    # ──────────────────────────────────────────────────────────────────────────

    async def _dispatch(
        self,
        action:   str,
        params:   Dict[str, Any],
        prompt:   str,
        ingested: List[Dict[str, Any]],
        user_id:  str,
        job_id:   str,
    ) -> OrchestratorResult:
        """Route the classified action to the right sub-pipeline."""

        from core.vision.slide_renderer import SlideRenderer
        from core.vision.vision_engine import VisionEngine
        from core.sandbox.pptx_sandbox import PptxSandbox
        from core.vision.content_extractor import ContentExtractor
        from core.vision.content_writer import ContentWriter
        from core.vision.deck_planner import DeckPlanner
        from core.vision.brand_enforcer import BrandEnforcer
        from core.vision.export_pipeline import ExportPipeline
        from core.vision.slide_library import SlideLibrary
        from core.vision.session_manager import SessionManager
        from core.vision.reconstruction_engine import ReconstructionEngine

        renderer     = SlideRenderer()
        vision_eng   = VisionEngine()
        extractor    = ContentExtractor()
        writer       = ContentWriter()
        planner      = DeckPlanner()
        recon        = ReconstructionEngine()

        # ── Helper: render all files and save previews ────────────────────────
        async def render_all(slide_range=None):
            manifests = []
            for fi in ingested:
                if fi["file_type"] not in ("pptx","ppt","pdf","png","jpg","jpeg"):
                    continue
                m = await renderer.render(fi["bytes"], fi["file_type"], fi["filename"], slide_range)
                manifests.append((fi["filename"], m))
                for slide in m.slides:
                    _save_preview(job_id, slide.index, slide.image_bytes)
            return manifests

        # ── Helper: save preview PNG ──────────────────────────────────────────
        def _save_preview(jid, idx, png):
            p = _JOB_STORE / jid
            p.mkdir(parents=True, exist_ok=True)
            (p / f"slide_{idx:04d}.png").write_bytes(png)

        # ── Helper: save output PPTX ──────────────────────────────────────────
        def _save_pptx(jid, data, fname):
            p = _JOB_STORE / jid
            p.mkdir(parents=True, exist_ok=True)
            (p / fname).write_bytes(data)

        def _preview_urls(jid, manifests):
            urls = []
            for _, m in manifests:
                for s in m.slides:
                    urls.append(f"/pptx/preview/{jid}/{s.index}")
            return urls

        # ══════════════════════════════════════════════════════════════════════
        # MERGE
        # ══════════════════════════════════════════════════════════════════════
        if action == "merge":
            # Import the merge helper from pptx_intelligence
            from api.routes.pptx_intelligence import _execute_merge, _run_automizer_merge, _save_output_pptx as _pio_save

            task_plan = {
                "source_file":        params.get("source_file"),
                "target_file":        params.get("target_file"),
                "slide_range":        params.get("slide_range"),
                "insert_after_slide": params.get("insert_after_slide"),
                "output_filename":    params.get("output_filename", "merged_output.pptx"),
                "description":        params.get("explanation", ""),
            }

            merge_result = await _execute_merge(job_id, ingested, task_plan)
            if merge_result.get("success"):
                return OrchestratorResult(
                    success=True,
                    job_id=job_id,
                    action="merge",
                    explanation=params.get("explanation", "Slides merged successfully."),
                    preview_urls=merge_result.get("preview_urls", []),
                    download_url=merge_result.get("download_url"),
                    slide_count=merge_result.get("slide_count", 0),
                )
            else:
                return OrchestratorResult(
                    success=False, job_id=job_id, action="merge",
                    explanation="Merge failed", error=merge_result.get("error"),
                )

        # ══════════════════════════════════════════════════════════════════════
        # ANALYZE
        # ══════════════════════════════════════════════════════════════════════
        elif action == "analyze" or action == "preview":
            manifests = await render_all()
            analyses_list = []
            if action == "analyze" and manifests:
                for fname, m in manifests:
                    if m.success:
                        analyses = await vision_eng.analyze_manifest(m, extra_context=prompt, fast_mode=True)
                        analyses_list.extend([a.to_dict() for a in analyses])

            preview_urls = _preview_urls(job_id, manifests)
            return OrchestratorResult(
                success=True, job_id=job_id, action=action,
                explanation=params.get("explanation", f"Analyzed {sum(m.slide_count for _,m in manifests)} slides."),
                preview_urls=preview_urls,
                slide_count=sum(m.slide_count for _, m in manifests),
                analyses=analyses_list if analyses_list else None,
            )

        # ══════════════════════════════════════════════════════════════════════
        # RECONSTRUCT
        # ══════════════════════════════════════════════════════════════════════
        elif action == "reconstruct":
            from api.routes.pptx_intelligence import _execute_reconstruct
            manifests = await render_all()
            result = await _execute_reconstruct(job_id, ingested, params, manifests,
                                                force_embed=params.get("force_embed", False))
            return OrchestratorResult(
                success=result.get("success", False), job_id=job_id, action="reconstruct",
                explanation=params.get("explanation", "Reconstructed as native editable slides."),
                preview_urls=result.get("preview_urls", []),
                download_url=result.get("download_url"),
                slide_count=result.get("slide_count", 0),
                analyses=result.get("analyses"),
                error=result.get("error"),
            )

        # ══════════════════════════════════════════════════════════════════════
        # GENERATE FROM DOCUMENT
        # ══════════════════════════════════════════════════════════════════════
        elif action == "generate_from_doc":
            all_contents = []
            for fi in ingested:
                doc = await extractor.extract(fi["bytes"], fi["file_type"], fi["filename"])
                if doc.success:
                    all_contents.append(doc)

            if not all_contents:
                return OrchestratorResult(
                    success=False, job_id=job_id, action=action,
                    explanation="Could not extract content from uploaded files.",
                    error="No content extracted",
                )

            primary = all_contents[0]
            plan = await planner.plan_from_document(
                content=primary,
                slide_count=params.get("slide_count", 10),
                audience=params.get("audience", "general"),
                tone=params.get("tone", "professional"),
                focus=params.get("focus", ""),
            )

            specs   = plan.to_pptx_specs()
            sandbox = PptxSandbox()
            loop    = asyncio.get_event_loop()
            pptx_r  = await loop.run_in_executor(None, sandbox.generate, {"title": plan.title, "slides": specs})

            if not pptx_r.success:
                return OrchestratorResult(False, job_id, action, "PPTX generation failed", error=pptx_r.error)

            out_fn = params.get("output_filename", "generated_deck.pptx")
            _save_pptx(job_id, pptx_r.data, out_fn)
            m = await renderer.render(pptx_r.data, "pptx", out_fn)
            for s in m.slides:
                _save_preview(job_id, s.index, s.image_bytes)

            return OrchestratorResult(
                success=True, job_id=job_id, action=action,
                explanation=params.get("explanation", f"Generated {len(specs)}-slide deck from {primary.filename}."),
                preview_urls=[f"/pptx/preview/{job_id}/{s.index}" for s in m.slides],
                download_url=f"/pptx/download/{job_id}",
                slide_count=len(specs),
                plan=plan.to_dict(),
            )

        # ══════════════════════════════════════════════════════════════════════
        # GENERATE FROM BRIEF
        # ══════════════════════════════════════════════════════════════════════
        elif action == "generate_from_brief":
            brief = params.get("brief") or prompt
            plan  = await planner.plan_from_brief(
                brief=brief,
                slide_count=params.get("slide_count", 10),
                audience=params.get("audience", "general"),
                tone=params.get("tone", "professional"),
            )

            specs   = plan.to_pptx_specs()
            sandbox = PptxSandbox()
            loop    = asyncio.get_event_loop()
            pptx_r  = await loop.run_in_executor(None, sandbox.generate, {"title": plan.title, "slides": specs})

            if not pptx_r.success:
                return OrchestratorResult(False, job_id, action, "Generation failed", error=pptx_r.error)

            out_fn = params.get("output_filename", "generated_deck.pptx")
            _save_pptx(job_id, pptx_r.data, out_fn)
            m = await renderer.render(pptx_r.data, "pptx", out_fn)
            for s in m.slides:
                _save_preview(job_id, s.index, s.image_bytes)

            return OrchestratorResult(
                success=True, job_id=job_id, action=action,
                explanation=params.get("explanation", f"Generated {len(specs)}-slide deck from your brief."),
                preview_urls=[f"/pptx/preview/{job_id}/{s.index}" for s in m.slides],
                download_url=f"/pptx/download/{job_id}",
                slide_count=len(specs),
                plan=plan.to_dict(),
            )

        # ══════════════════════════════════════════════════════════════════════
        # EXPORT
        # ══════════════════════════════════════════════════════════════════════
        elif action in ("export_pdf", "export_images", "export_html"):
            pptx_fi = next((fi for fi in ingested if fi["file_type"] in ("pptx","ppt")), None)
            if not pptx_fi:
                return OrchestratorResult(False, job_id, action, "No PPTX file found for export", error="No PPTX")

            pipeline = ExportPipeline()
            fmt_map = {"export_pdf": "pdf", "export_images": "images", "export_html": "html"}
            fmt     = fmt_map[action]
            batch   = await pipeline.batch_export(pptx_fi["bytes"], pptx_fi["filename"], [fmt])
            result  = batch.get(fmt)

            if result and result.success:
                fname = result.filename or f"export.{fmt}"
                _save_pptx(job_id, result.data, fname)
                return OrchestratorResult(
                    success=True, job_id=job_id, action=action,
                    explanation=params.get("explanation", f"Exported to {fmt.upper()}."),
                    download_url=f"/pptx/export/download/{job_id}/{fmt}",
                    slide_count=result.page_count,
                )
            else:
                return OrchestratorResult(False, job_id, action, "Export failed",
                                          error=result.error if result else "Unknown")

        # ══════════════════════════════════════════════════════════════════════
        # SUMMARIZE
        # ══════════════════════════════════════════════════════════════════════
        elif action == "summarize":
            results = []
            for fi in ingested:
                doc  = await extractor.extract(fi["bytes"], fi["file_type"], fi["filename"])
                if doc.success:
                    bullets   = await writer.summarize_for_exec(doc.full_transcript[:6000], params.get("max_bullets", 5))
                    one_liner = await writer.rewrite_as_headline(doc.full_transcript[:500])
                    results.append({"filename": fi["filename"], "bullets": bullets, "one_liner": one_liner})

            return OrchestratorResult(
                success=bool(results), job_id=job_id, action=action,
                explanation=params.get("explanation", f"Summarized {len(results)} document(s)."),
                extra={"summaries": results},
            )

        # ══════════════════════════════════════════════════════════════════════
        # EXTRACT TEXT
        # ══════════════════════════════════════════════════════════════════════
        elif action == "extract_text":
            all_pages = []
            transcript = ""
            for fi in ingested:
                doc = await extractor.extract(fi["bytes"], fi["file_type"], fi["filename"])
                if doc.success:
                    all_pages.extend(doc.to_dict()["pages"])
                    transcript += f"\n\n=== {fi['filename']} ===\n{doc.full_transcript}"

            return OrchestratorResult(
                success=bool(all_pages), job_id=job_id, action=action,
                explanation=params.get("explanation", f"Extracted text from {len(ingested)} file(s)."),
                transcript=transcript.strip(),
                extra={"pages": all_pages},
            )

        # ══════════════════════════════════════════════════════════════════════
        # SPEAKER NOTES
        # ══════════════════════════════════════════════════════════════════════
        elif action == "speaker_notes":
            # Extract from uploaded PPTX
            pptx_fi = next((fi for fi in ingested if fi["file_type"] in ("pptx","ppt")), None)
            if pptx_fi:
                doc    = await extractor.extract(pptx_fi["bytes"], "pptx", pptx_fi["filename"])
                slides = doc.pages

                class PageSlide:
                    def __init__(self, p):
                        self.slide_number = p.page_index
                        self.title = p.title or ""
                        self.slide_type = p.page_type or "content"
                        self.bullets = p.bullets or []
                        self.body_text = p.body_text or ""

                notes = await writer.generate_speaker_notes(
                    [PageSlide(p) for p in slides],
                    audience=params.get("audience", "general"),
                )
                return OrchestratorResult(
                    success=True, job_id=job_id, action=action,
                    explanation=params.get("explanation", f"Generated speaker notes for {len(notes)} slides."),
                    speaker_notes=[n.to_dict() for n in notes],
                )
            return OrchestratorResult(False, job_id, action, "No PPTX found", error="Upload a PPTX file")

        # ══════════════════════════════════════════════════════════════════════
        # REVISE
        # ══════════════════════════════════════════════════════════════════════
        elif action == "revise":
            from core.vision.revision_engine import RevisionEngine
            pptx_fi = next((fi for fi in ingested if fi["file_type"] in ("pptx","ppt")), None)
            if not pptx_fi:
                return OrchestratorResult(False, job_id, action, "No PPTX found", error="Upload a PPTX file")

            engine = RevisionEngine()
            result = await engine.smart_revise(
                pptx_bytes=pptx_fi["bytes"],
                instruction=params.get("instruction", prompt),
                output_filename=params.get("output_filename", f"revised_{pptx_fi['filename']}"),
            )
            if result.success:
                out_fn = result.filename or "revised.pptx"
                _save_pptx(job_id, result.pptx_bytes, out_fn)
                m = await renderer.render(result.pptx_bytes, "pptx", out_fn)
                for s in m.slides:
                    _save_preview(job_id, s.index, s.image_bytes)
                return OrchestratorResult(
                    success=True, job_id=job_id, action=action,
                    explanation=result.summary,
                    preview_urls=[f"/pptx/preview/{job_id}/{s.index}" for s in m.slides],
                    download_url=f"/pptx/download/{job_id}",
                    slide_count=m.slide_count,
                    extra={"operations": result.operations},
                )
            return OrchestratorResult(False, job_id, action, "Revision failed", error=result.error)

        # ══════════════════════════════════════════════════════════════════════
        # BRAND AUDIT / FIX
        # ══════════════════════════════════════════════════════════════════════
        elif action in ("brand_audit", "brand_fix"):
            pptx_fi = next((fi for fi in ingested if fi["file_type"] in ("pptx","ppt")), None)
            if not pptx_fi:
                return OrchestratorResult(False, job_id, action, "No PPTX found", error="Upload a PPTX file")

            manifests = await render_all()
            all_analyses = []
            for _, m in manifests:
                if m.success:
                    analyses = await vision_eng.analyze_manifest(m, fast_mode=True)
                    all_analyses.extend(analyses)

            enforcer = BrandEnforcer()
            loop     = asyncio.get_event_loop()
            audit    = await loop.run_in_executor(
                None, enforcer.score_manifest_sync, all_analyses, pptx_fi["filename"]
            )

            return OrchestratorResult(
                success=True, job_id=job_id, action=action,
                explanation=params.get("explanation",
                    f"Brand audit complete: avg score {round(audit.avg_score)}/100 ({audit.overall_grade})"),
                preview_urls=_preview_urls(job_id, manifests),
                audit=audit.to_dict(),
            )

        # ══════════════════════════════════════════════════════════════════════
        # PLAN
        # ══════════════════════════════════════════════════════════════════════
        elif action == "plan":
            brief = params.get("brief") or prompt
            if ingested:
                doc  = await extractor.extract(ingested[0]["bytes"], ingested[0]["file_type"], ingested[0]["filename"])
                plan = await planner.plan_from_document(doc, slide_count=params.get("slide_count", 10))
            else:
                plan = await planner.plan_from_brief(brief=brief, slide_count=params.get("slide_count", 10))

            return OrchestratorResult(
                success=True, job_id=job_id, action=action,
                explanation=params.get("explanation", f"Created {plan.slide_count}-slide deck plan."),
                slide_count=plan.slide_count,
                plan=plan.to_dict(),
            )

        # ══════════════════════════════════════════════════════════════════════
        # SESSION CREATE
        # ══════════════════════════════════════════════════════════════════════
        elif action == "session_create":
            pptx_fi = next((fi for fi in ingested if fi["file_type"] in ("pptx","ppt")), None)
            if not pptx_fi:
                return OrchestratorResult(False, job_id, action, "No PPTX found", error="Upload a PPTX file")

            mgr     = SessionManager()
            session = await mgr.create(pptx_fi["bytes"], user_id, pptx_fi["filename"])
            init_job = mgr._get_job_id_for_revision(session.session_id, 0) or ""

            from core.vision.slide_renderer import SlideRenderer as SR
            slide_count = SR.get_slide_count(pptx_fi["bytes"])

            return OrchestratorResult(
                success=True, job_id=job_id, action=action,
                explanation=params.get("explanation", f"Editing session created. You can now revise slides and undo/redo changes."),
                preview_urls=[f"/pptx/preview/{init_job}/{i}" for i in range(1, slide_count + 1)],
                slide_count=slide_count,
                session_id=session.session_id,
            )

        # ══════════════════════════════════════════════════════════════════════
        # COMPARE
        # ══════════════════════════════════════════════════════════════════════
        elif action == "compare":
            if len(ingested) < 2:
                return OrchestratorResult(False, job_id, action, "Need 2 files to compare", error="Upload 2 PPTX files")

            from core.vision.element_matcher import _phash
            from core.vision.element_matcher import _hamming

            m_a = await renderer.render(ingested[0]["bytes"], ingested[0]["file_type"], ingested[0]["filename"])
            m_b = await renderer.render(ingested[1]["bytes"], ingested[1]["file_type"], ingested[1]["filename"])

            matches = []
            threshold = params.get("threshold", 0.85)
            for s_a in m_a.slides:
                h_a = _phash(s_a.image_bytes)
                for s_b in m_b.slides:
                    h_b = _phash(s_b.image_bytes)
                    if h_a and h_b:
                        dist  = _hamming(h_a, h_b)
                        score = max(0.0, 1.0 - dist / 64.0)
                        if score >= threshold:
                            matches.append({"a": s_a.index, "b": s_b.index,
                                            "score": round(score, 4),
                                            "type": "identical" if score >= 0.98 else "similar"})

            return OrchestratorResult(
                success=True, job_id=job_id, action=action,
                explanation=params.get("explanation", f"Found {len(matches)} matching slide(s)."),
                extra={
                    "deck_a": ingested[0]["filename"], "slide_count_a": m_a.slide_count,
                    "deck_b": ingested[1]["filename"], "slide_count_b": m_b.slide_count,
                    "matches": sorted(matches, key=lambda x: x["score"], reverse=True),
                },
            )

        # ══════════════════════════════════════════════════════════════════════
        # DEFAULT / UNKNOWN → preview
        # ══════════════════════════════════════════════════════════════════════
        else:
            manifests = await render_all()
            return OrchestratorResult(
                success=True, job_id=job_id, action="preview",
                explanation=params.get("explanation", "Here are the slides from your uploaded files."),
                preview_urls=_preview_urls(job_id, manifests),
                slide_count=sum(m.slide_count for _, m in manifests),
            )
