"""
core.vision — PPTX Intelligence Pipeline
==========================================
Computer-vision powered presentation understanding, reconstruction, and merging.

Phase 1 Modules
---------------
slide_renderer      : Convert PPTX / PDF / HTML / images → per-slide PNG bytes
vision_engine       : Claude Vision → structured SlideAnalysis JSON per slide
element_matcher     : Perceptual-hash element library matching (InDesign assets)
reconstruction_engine: SlideAnalysis JSON → pptx_sandbox spec → editable PPTX

Phase 2 Modules
---------------
streaming_pipeline  : SSE async generator — real-time per-slide preview streaming
revision_engine     : NLP instruction → PptxReviser + AutomizerSandbox operations

Phase 3 Modules
---------------
brand_enforcer      : Potomac brand compliance scoring + auto-correction
slide_library       : Persistent corporate slide library (Supabase + semantic search)
export_pipeline     : PPTX → PDF / images / HTML + batch ZIP processing

Phase 4 Modules
---------------
diff_engine         : Detect which slides changed between two PPTX versions (diff-aware re-render)
session_manager     : Stateful editing sessions with full undo/redo history

Phase 5 Modules
---------------
content_extractor   : Extract text from PPTX (OCR), PDF, DOCX, HTML, images
deck_planner        : Claude-powered presentation planning from documents or briefs
content_writer      : AI slide content enhancement, speaker notes, alternatives
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

__all__ = [
    # Phase 1
    "SlideRenderer",
    "SlideManifest",
    "SlideImageInfo",
    "VisionEngine",
    "SlideAnalysis",
    "DetectedElement",
    "ElementMatcher",
    "ElementMatch",
    "LibraryElement",
    "get_element_matcher",
    "ReconstructionEngine",
    # Phase 2
    "StreamingPipeline",
    "RevisionEngine",
    "RevisionResult",
    # Phase 3
    "BrandEnforcer",
    "BrandReport",
    "BrandAudit",
    "BrandViolation",
    "SlideLibrary",
    "LibrarySlide",
    "SearchResult",
    "ExportPipeline",
    "ExportResult",
    # Phase 4
    "DiffEngine",
    "DiffReport",
    "SlideHash",
    "SessionManager",
    "Session",
    "RevisionEntry",
    # Phase 5
    "ContentExtractor",
    "DocumentContent",
    "PageContent",
    "TableData",
    "DeckPlanner",
    "DeckPlan",
    "SlideBlueprint",
    "ContentWriter",
    "SpeakerNote",
    "ContentSuggestion",
]
