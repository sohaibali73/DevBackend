"""
SlideLibrary
============
Persistent corporate slide library backed by Supabase.

Analyzed slides are stored with:
  - Full SlideAnalysis JSON (layout, title, colors, elements, ...)
  - Semantic embedding of slide title + description (sentence-transformers)
  - Perceptual hash for visual similarity search
  - Preview PNG stored on Railway volume

Enables:
  - Semantic search ("find all slides about investment strategy")
  - Visual search (find slides that look like this one)
  - Reuse library (assemble new decks from saved slides)
  - Corporate slide inventory (deduplicate, track versions)

Supabase Table: slide_library
-------------------------------
  id              uuid PRIMARY KEY
  user_id         text
  source_filename text        -- original deck filename
  slide_index     int
  job_id          text        -- pptx_intelligence job_id that generated the preview
  layout_type     text
  title           text
  section_label   text
  background      text        -- hex without #
  color_palette   jsonb       -- ["FEC00F", "212121", ...]
  analysis        jsonb       -- full SlideAnalysis dict
  phash           text        -- perceptual hash for visual similarity
  preview_url     text        -- /pptx/preview/{job_id}/{slide_index}
  tags            text[]
  brand_score     int         -- BrandEnforcer score (0-100)
  created_at      timestamptz
  updated_at      timestamptz

Usage
-----
    from core.vision.slide_library import SlideLibrary

    lib = SlideLibrary()

    # Index a slide from an analyzed manifest
    slide_id = await lib.index_slide(
        user_id="user123",
        analysis=analysis,
        job_id="abc-123",
        source_filename="meet_potomac.pptx",
        preview_url="/pptx/preview/abc-123/1",
        tags=["strategy", "investment"],
    )

    # Search by text
    results = await lib.search("investment strategy hexagon", user_id="user123")

    # Search by visual similarity
    matches = await lib.find_similar(slide_png_bytes, user_id="user123")

    # Build a deck from library slides
    slide_ids = [r.id for r in results[:5]]
    specs = await lib.build_deck_specs(slide_ids)
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Data classes
# =============================================================================

@dataclass
class LibrarySlide:
    """A single slide stored in the library."""
    id:              str
    user_id:         str
    source_filename: str
    slide_index:     int
    job_id:          str
    layout_type:     str
    title:           str
    section_label:   str
    background:      str
    color_palette:   List[str]
    analysis:        Dict[str, Any]
    phash:           str
    preview_url:     str
    tags:            List[str]
    brand_score:     int
    created_at:      str

    @property
    def description(self) -> str:
        """Short description for embedding."""
        parts = []
        if self.section_label:
            parts.append(self.section_label)
        if self.title:
            parts.append(self.title)
        if self.layout_type:
            parts.append(self.layout_type)
        return " | ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id":              self.id,
            "user_id":         self.user_id,
            "source_filename": self.source_filename,
            "slide_index":     self.slide_index,
            "job_id":          self.job_id,
            "layout_type":     self.layout_type,
            "title":           self.title,
            "section_label":   self.section_label,
            "background":      self.background,
            "color_palette":   self.color_palette,
            "preview_url":     self.preview_url,
            "tags":            self.tags,
            "brand_score":     self.brand_score,
            "created_at":      self.created_at,
        }


@dataclass
class SearchResult:
    """A slide library search result with relevance score."""
    slide:     LibrarySlide
    score:     float          # 0.0–1.0 relevance
    match_type: str           # "semantic" | "visual" | "text"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score":      round(self.score, 4),
            "match_type": self.match_type,
            **self.slide.to_dict(),
        }


# =============================================================================
# SlideLibrary
# =============================================================================

class SlideLibrary:
    """
    Persistent slide library with semantic and visual search.
    Falls back gracefully if Supabase or sentence-transformers are unavailable.
    """

    def __init__(self):
        self._model = None          # sentence-transformers model (lazy load)
        self._in_memory: Dict[str, LibrarySlide] = {}  # fallback in-memory store

    # ──────────────────────────────────────────────────────────────────────────
    # Indexing
    # ──────────────────────────────────────────────────────────────────────────

    async def index_slide(
        self,
        user_id:         str,
        analysis,                    # SlideAnalysis
        job_id:          str,
        source_filename: str,
        preview_url:     str = "",
        tags:            Optional[List[str]] = None,
        brand_score:     int = 0,
        image_bytes:     Optional[bytes] = None,
    ) -> str:
        """
        Store a slide in the library. Returns the new library slide ID.

        Parameters
        ----------
        user_id         : authenticated user
        analysis        : SlideAnalysis from VisionEngine
        job_id          : pptx_intelligence job_id (for preview URL)
        source_filename : original PPTX filename
        preview_url     : URL to serve the slide PNG
        tags            : optional tags for filtering
        brand_score     : BrandEnforcer score (0-100)
        image_bytes     : optional PNG bytes for computing phash
        """
        slide_id = str(uuid.uuid4())
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Compute phash for visual similarity
        phash = ""
        if image_bytes:
            try:
                from core.vision.element_matcher import _phash
                phash = _phash(image_bytes) or ""
            except Exception:
                pass

        # Build tags from analysis
        auto_tags = list(tags or [])
        if analysis.section_label:
            auto_tags.append(analysis.section_label.lower().replace(" ", "_"))
        if analysis.layout_type:
            auto_tags.append(analysis.layout_type)
        auto_tags = list(set(auto_tags))

        slide = LibrarySlide(
            id=slide_id,
            user_id=user_id,
            source_filename=source_filename,
            slide_index=analysis.slide_index,
            job_id=job_id,
            layout_type=analysis.layout_type or "",
            title=analysis.title or "",
            section_label=analysis.section_label or "",
            background=analysis.background or "",
            color_palette=analysis.color_palette or [],
            analysis=analysis.to_dict() if hasattr(analysis, "to_dict") else {},
            phash=phash,
            preview_url=preview_url,
            tags=auto_tags,
            brand_score=brand_score,
            created_at=now,
        )

        # Try Supabase first, fall back to in-memory
        success = await asyncio.get_event_loop().run_in_executor(
            None, self._persist_to_supabase, slide
        )
        if not success:
            self._in_memory[slide_id] = slide
            logger.debug("SlideLibrary: stored %s in memory (Supabase unavailable)", slide_id)

        return slide_id

    async def index_manifest(
        self,
        user_id:          str,
        manifest,                    # SlideManifest
        analyses:         List,      # List[SlideAnalysis]
        job_id:           str,
        tags:             Optional[List[str]] = None,
        brand_scores:     Optional[Dict[int, int]] = None,  # {slide_index: score}
    ) -> List[str]:
        """Index all slides from a manifest. Returns list of library slide IDs."""
        brand_scores = brand_scores or {}
        analysis_map = {a.slide_index: a for a in analyses}
        slide_map    = {s.index: s for s in manifest.slides}

        ids = []
        for idx, analysis in sorted(analysis_map.items()):
            slide_info = slide_map.get(idx)
            img_bytes  = slide_info.image_bytes if slide_info else None
            prev_url   = f"/pptx/preview/{job_id}/{idx}"

            sid = await self.index_slide(
                user_id=user_id,
                analysis=analysis,
                job_id=job_id,
                source_filename=manifest.source_filename,
                preview_url=prev_url,
                tags=tags,
                brand_score=brand_scores.get(idx, 0),
                image_bytes=img_bytes,
            )
            ids.append(sid)

        return ids

    # ──────────────────────────────────────────────────────────────────────────
    # Search
    # ──────────────────────────────────────────────────────────────────────────

    async def search(
        self,
        query:    str,
        user_id:  Optional[str] = None,
        top_k:    int = 10,
        layout_filter: Optional[str] = None,
        tag_filter:    Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Semantic + text search for slides.

        Strategy:
        1. Text match on title, section_label, tags (fast)
        2. Semantic embedding similarity if sentence-transformers available
        3. Combined score

        Returns top_k results sorted by relevance.
        """
        loop = asyncio.get_event_loop()
        all_slides = await loop.run_in_executor(
            None, self._load_all_slides, user_id, layout_filter, tag_filter
        )

        if not all_slides:
            return []

        q_lower = query.lower()

        # ── Text scoring ──────────────────────────────────────────────────────
        def text_score(slide: LibrarySlide) -> float:
            score = 0.0
            text = f"{slide.title} {slide.section_label} {' '.join(slide.tags)} {slide.layout_type}".lower()
            for word in q_lower.split():
                if word in text:
                    score += 1.0 / len(q_lower.split())
            return min(score, 1.0)

        # ── Semantic scoring (if model available) ─────────────────────────────
        semantic_scores: Dict[str, float] = {}
        try:
            model = self._load_model()
            if model:
                q_embed = await loop.run_in_executor(None, model.encode, [query])
                descs = [s.description for s in all_slides]
                d_embeds = await loop.run_in_executor(None, model.encode, descs)

                import numpy as np
                q_vec = q_embed[0]
                for i, slide in enumerate(all_slides):
                    d_vec = d_embeds[i]
                    cosine = float(np.dot(q_vec, d_vec) / (
                        np.linalg.norm(q_vec) * np.linalg.norm(d_vec) + 1e-9
                    ))
                    semantic_scores[slide.id] = max(0.0, cosine)
        except Exception as exc:
            logger.debug("Semantic search unavailable: %s", exc)

        # ── Combined scoring ──────────────────────────────────────────────────
        scored = []
        for slide in all_slides:
            t_score = text_score(slide)
            s_score = semantic_scores.get(slide.id, 0.0)
            combined = 0.6 * s_score + 0.4 * t_score if semantic_scores else t_score
            if combined > 0.05:
                match_type = "semantic" if s_score > t_score else "text"
                scored.append(SearchResult(slide=slide, score=combined, match_type=match_type))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    async def find_similar(
        self,
        image_bytes: bytes,
        user_id:     Optional[str] = None,
        top_k:       int = 5,
        threshold:   float = 0.70,
    ) -> List[SearchResult]:
        """
        Find visually similar slides using perceptual hash comparison.

        Parameters
        ----------
        image_bytes : PNG bytes of the slide to match
        threshold   : minimum similarity score (0–1, default 0.70)
        """
        from core.vision.element_matcher import _phash, _hamming

        q_hash = _phash(image_bytes)
        if not q_hash:
            return []

        loop = asyncio.get_event_loop()
        all_slides = await loop.run_in_executor(
            None, self._load_all_slides, user_id, None, None
        )

        results = []
        for slide in all_slides:
            if not slide.phash:
                continue
            dist = _hamming(q_hash, slide.phash)
            score = max(0.0, 1.0 - dist / 64.0)
            if score >= threshold:
                results.append(SearchResult(slide=slide, score=score, match_type="visual"))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    async def get_by_id(self, slide_id: str) -> Optional[LibrarySlide]:
        """Retrieve a library slide by ID."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_by_id, slide_id)

    async def delete(self, slide_id: str, user_id: str) -> bool:
        """Delete a slide from the library."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._delete_from_db, slide_id, user_id)

    async def list_slides(
        self,
        user_id:       Optional[str] = None,
        layout_filter: Optional[str] = None,
        tag_filter:    Optional[str] = None,
        limit:         int = 50,
        offset:        int = 0,
    ) -> List[LibrarySlide]:
        """List library slides with optional filters."""
        loop = asyncio.get_event_loop()
        all_slides = await loop.run_in_executor(
            None, self._load_all_slides, user_id, layout_filter, tag_filter
        )
        return all_slides[offset: offset + limit]

    async def build_deck_specs(self, slide_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch library slides by ID and return pptx_sandbox-compatible specs.
        Used to assemble a new deck from saved library slides.
        """
        from core.vision.reconstruction_engine import ReconstructionEngine
        from core.vision.vision_engine import SlideAnalysis

        reconstructor = ReconstructionEngine()
        specs = []

        for sid in slide_ids:
            slide = await self.get_by_id(sid)
            if not slide:
                continue

            analysis_dict = slide.analysis
            # Reconstruct a SlideAnalysis from stored dict
            from dataclasses import fields as dc_fields
            try:
                from core.vision.vision_engine import SlideAnalysis, DetectedElement
                elems = []
                for e in analysis_dict.get("elements", []):
                    pos = e.get("position", {})
                    elems.append(DetectedElement(
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
                analysis = SlideAnalysis(
                    slide_index=analysis_dict.get("slide_index", 1),
                    layout_type=analysis_dict.get("layout_type", ""),
                    background=analysis_dict.get("background", ""),
                    background_type=analysis_dict.get("background_type", "solid"),
                    section_label=analysis_dict.get("section_label", ""),
                    title=analysis_dict.get("title", ""),
                    subtitle=analysis_dict.get("subtitle", ""),
                    body_text=analysis_dict.get("body_text", ""),
                    color_palette=analysis_dict.get("color_palette", []),
                    typography=analysis_dict.get("typography", {}),
                    elements=elems,
                    has_logo=analysis_dict.get("has_logo", False),
                    logo_variant=analysis_dict.get("logo_variant", ""),
                    has_chart=analysis_dict.get("has_chart", False),
                    has_table=analysis_dict.get("has_table", False),
                    has_image=analysis_dict.get("has_image", False),
                    grid_columns=analysis_dict.get("grid_columns", 0),
                    reconstruction_strategy=analysis_dict.get("reconstruction_strategy", ""),
                    reconstruction_confidence=float(analysis_dict.get("reconstruction_confidence", 0) or 0),
                    raw_description=analysis_dict.get("raw_description", ""),
                )
                spec = reconstructor.build_spec(analysis)
                specs.append(spec)
            except Exception as exc:
                logger.warning("build_deck_specs failed for %s: %s", sid, exc)
                specs.append({"type": "content", "title": slide.title, "text": ""})

        return specs

    # ──────────────────────────────────────────────────────────────────────────
    # Supabase I/O (blocking, run in executor)
    # ──────────────────────────────────────────────────────────────────────────

    def _persist_to_supabase(self, slide: LibrarySlide) -> bool:
        try:
            from db.supabase_client import get_supabase
            db = get_supabase()
            db.table("slide_library").insert({
                "id":              slide.id,
                "user_id":         slide.user_id,
                "source_filename": slide.source_filename,
                "slide_index":     slide.slide_index,
                "job_id":          slide.job_id,
                "layout_type":     slide.layout_type,
                "title":           slide.title,
                "section_label":   slide.section_label,
                "background":      slide.background,
                "color_palette":   slide.color_palette,
                "analysis":        slide.analysis,
                "phash":           slide.phash,
                "preview_url":     slide.preview_url,
                "tags":            slide.tags,
                "brand_score":     slide.brand_score,
                "created_at":      slide.created_at,
                "updated_at":      slide.created_at,
            }).execute()
            return True
        except Exception as exc:
            logger.debug("Supabase insert failed: %s", exc)
            return False

    def _load_all_slides(
        self,
        user_id:       Optional[str],
        layout_filter: Optional[str],
        tag_filter:    Optional[str],
    ) -> List[LibrarySlide]:
        """Load slides from Supabase (or in-memory fallback)."""
        try:
            from db.supabase_client import get_supabase
            db = get_supabase()
            q = db.table("slide_library").select("*")
            if user_id:
                q = q.eq("user_id", user_id)
            if layout_filter:
                q = q.eq("layout_type", layout_filter)
            if tag_filter:
                q = q.contains("tags", [tag_filter])
            result = q.order("created_at", desc=True).limit(500).execute()
            return [self._row_to_slide(r) for r in (result.data or [])]
        except Exception as exc:
            logger.debug("Supabase load failed: %s — using in-memory", exc)
            slides = list(self._in_memory.values())
            if user_id:
                slides = [s for s in slides if s.user_id == user_id]
            if layout_filter:
                slides = [s for s in slides if s.layout_type == layout_filter]
            if tag_filter:
                slides = [s for s in slides if tag_filter in s.tags]
            return slides

    def _fetch_by_id(self, slide_id: str) -> Optional[LibrarySlide]:
        try:
            from db.supabase_client import get_supabase
            db = get_supabase()
            result = db.table("slide_library").select("*").eq("id", slide_id).limit(1).execute()
            if result.data:
                return self._row_to_slide(result.data[0])
        except Exception:
            pass
        return self._in_memory.get(slide_id)

    def _delete_from_db(self, slide_id: str, user_id: str) -> bool:
        try:
            from db.supabase_client import get_supabase
            db = get_supabase()
            db.table("slide_library").delete().eq("id", slide_id).eq("user_id", user_id).execute()
            self._in_memory.pop(slide_id, None)
            return True
        except Exception as exc:
            logger.warning("Delete failed: %s", exc)
            return False

    @staticmethod
    def _row_to_slide(r: Dict[str, Any]) -> LibrarySlide:
        return LibrarySlide(
            id=r.get("id", ""),
            user_id=r.get("user_id", ""),
            source_filename=r.get("source_filename", ""),
            slide_index=int(r.get("slide_index", 1)),
            job_id=r.get("job_id", ""),
            layout_type=r.get("layout_type", ""),
            title=r.get("title", ""),
            section_label=r.get("section_label", ""),
            background=r.get("background", ""),
            color_palette=r.get("color_palette") or [],
            analysis=r.get("analysis") or {},
            phash=r.get("phash", ""),
            preview_url=r.get("preview_url", ""),
            tags=r.get("tags") or [],
            brand_score=int(r.get("brand_score", 0)),
            created_at=r.get("created_at", ""),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Model loader
    # ──────────────────────────────────────────────────────────────────────────

    def _load_model(self):
        """Lazy-load the sentence-transformers model (small/fast model)."""
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("SlideLibrary: sentence-transformers model loaded")
        except Exception as exc:
            logger.debug("sentence-transformers unavailable: %s", exc)
            self._model = None
        return self._model
