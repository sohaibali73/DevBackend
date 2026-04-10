"""
core.vision — PPTX Intelligence Pipeline
==========================================
Computer-vision powered presentation understanding, reconstruction, and merging.

Modules
-------
slide_renderer      : Convert PPTX / PDF / HTML / images → per-slide PNG bytes
vision_engine       : Claude Vision → structured SlideAnalysis JSON per slide
element_matcher     : Perceptual-hash element library matching (InDesign assets)
reconstruction_engine: SlideAnalysis JSON → pptx_sandbox spec → editable PPTX
"""

from .slide_renderer import SlideRenderer, SlideManifest, SlideImageInfo
from .vision_engine import VisionEngine, SlideAnalysis
from .element_matcher import ElementMatcher
from .reconstruction_engine import ReconstructionEngine

__all__ = [
    "SlideRenderer",
    "SlideManifest",
    "SlideImageInfo",
    "VisionEngine",
    "SlideAnalysis",
    "ElementMatcher",
    "ReconstructionEngine",
]
