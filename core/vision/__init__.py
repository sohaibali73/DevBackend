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
"""

from .slide_renderer import SlideRenderer, SlideManifest, SlideImageInfo
from .vision_engine import VisionEngine, SlideAnalysis, DetectedElement
from .element_matcher import ElementMatcher, ElementMatch, LibraryElement, get_element_matcher
from .reconstruction_engine import ReconstructionEngine
from .streaming_pipeline import StreamingPipeline
from .revision_engine import RevisionEngine, RevisionResult

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
]
