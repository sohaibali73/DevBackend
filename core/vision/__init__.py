"""
core.vision — PPTX Intelligence Pipeline
==========================================
Computer-vision powered presentation understanding, reconstruction, and merging.

Phase 1: slide_renderer, vision_engine, element_matcher, reconstruction_engine
Phase 2: streaming_pipeline, revision_engine
Phase 3: brand_enforcer, slide_library, export_pipeline
Phase 4: diff_engine, session_manager
Phase 5: content_extractor, deck_planner, content_writer
Phase 6: job_manager, render_cache, template_registry
"""

from .slide_renderer import SlideRenderer, SlideManifest, SlideImageInfo
from .vision_engine import VisionEngine, SlideAnalysis, DetectedElement
from .element_matcher import ElementMatcher, ElementMatch, LibraryElement, get_element_matcher
from .reconstruction_engine import ReconstructionEngine
from .streaming_pipeline import StreamingPipeline
from .revision_engine import RevisionEngine, RevisionResult
from .brand_enforcer import BrandEnforcer, BrandReport, BrandAudit, BrandViolation
from .slide_library import SlideLibrary, LibrarySlide, SearchResult
from .export_pipeline import ExportPipeline, ExportResult
from .diff_engine import DiffEngine, DiffReport, SlideHash
from .session_manager import SessionManager, Session, RevisionEntry
from .content_extractor import ContentExtractor, DocumentContent, PageContent, TableData
from .deck_planner import DeckPlanner, DeckPlan, SlideBlueprint
from .content_writer import ContentWriter, SpeakerNote, ContentSuggestion
from .job_manager import JobManager, JobInfo, StorageStats
from .render_cache import RenderCache, CacheStats, get_render_cache
from .template_registry import TemplateRegistry, TemplateEntry, get_template_registry

__all__ = [
    # Phase 1
    "SlideRenderer", "SlideManifest", "SlideImageInfo",
    "VisionEngine", "SlideAnalysis", "DetectedElement",
    "ElementMatcher", "ElementMatch", "LibraryElement", "get_element_matcher",
    "ReconstructionEngine",
    # Phase 2
    "StreamingPipeline",
    "RevisionEngine", "RevisionResult",
    # Phase 3
    "BrandEnforcer", "BrandReport", "BrandAudit", "BrandViolation",
    "SlideLibrary", "LibrarySlide", "SearchResult",
    "ExportPipeline", "ExportResult",
    # Phase 4
    "DiffEngine", "DiffReport", "SlideHash",
    "SessionManager", "Session", "RevisionEntry",
    # Phase 5
    "ContentExtractor", "DocumentContent", "PageContent", "TableData",
    "DeckPlanner", "DeckPlan", "SlideBlueprint",
    "ContentWriter", "SpeakerNote", "ContentSuggestion",
    # Phase 6
    "JobManager", "JobInfo", "StorageStats",
    "RenderCache", "CacheStats", "get_render_cache",
    "TemplateRegistry", "TemplateEntry", "get_template_registry",
]
