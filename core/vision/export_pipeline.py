"""
ExportPipeline
==============
Converts PPTX files to multiple output formats and bundles them for download.

Supported export formats
------------------------
pdf     → LibreOffice headless PPTX→PDF (preserves all fonts + layout)
images  → Per-slide PNG ZIP (via SlideRenderer at configurable DPI)
html    → LibreOffice headless PPTX→HTML (basic fidelity)
thumbnails → Small thumbnail PNGs (120px wide) for gallery views

Usage
-----
    from core.vision.export_pipeline import ExportPipeline

    pipeline = ExportPipeline()

    # Export to PDF
    result = await pipeline.export_pdf(pptx_bytes, "report.pptx")
    # result.data = PDF bytes, result.filename = "report.pdf"

    # Export all slides as PNG ZIP
    result = await pipeline.export_images(pptx_bytes, "report.pptx", dpi=200)
    # result.data = ZIP bytes containing slide_001.png, slide_002.png, ...

    # Batch export: multiple formats at once
    results = await pipeline.batch_export(
        pptx_bytes, "report.pptx",
        formats=["pdf", "images"]
    )
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── LibreOffice lock (shared with slide_renderer.py) ──────────────────────────
import threading
_LO_LOCK = threading.Lock()


# =============================================================================
# Data classes
# =============================================================================

@dataclass
class ExportResult:
    """Result of a single export operation."""
    success:      bool
    data:         Optional[bytes]  = None
    filename:     Optional[str]    = None
    format:       str              = ""
    page_count:   int              = 0
    file_size:    int              = 0
    exec_time_ms: float            = 0.0
    error:        Optional[str]    = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success":      self.success,
            "filename":     self.filename,
            "format":       self.format,
            "page_count":   self.page_count,
            "file_size":    self.file_size,
            "exec_time_ms": round(self.exec_time_ms, 1),
            "error":        self.error,
        }


# =============================================================================
# ExportPipeline
# =============================================================================

class ExportPipeline:
    """
    Converts PPTX bytes to various output formats.
    All heavy work runs in a thread executor to avoid blocking the event loop.
    """

    def __init__(self, default_dpi: int = 150):
        self.default_dpi = default_dpi

    # ──────────────────────────────────────────────────────────────────────────
    # PDF export
    # ──────────────────────────────────────────────────────────────────────────

    async def export_pdf(
        self,
        pptx_bytes: bytes,
        source_filename: str = "presentation.pptx",
    ) -> ExportResult:
        """
        Convert PPTX to PDF using LibreOffice headless.
        Preserves fonts, colors, and layout at presentation quality.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._export_pdf_sync, pptx_bytes, source_filename
        )

    def _export_pdf_sync(self, pptx_bytes: bytes, source_filename: str) -> ExportResult:
        import time
        start = time.time()
        temp_dir = None
        try:
            with _LO_LOCK:
                temp_dir = Path(tempfile.mkdtemp(prefix="export_pdf_"))
                in_path  = temp_dir / Path(source_filename).name
                in_path.write_bytes(pptx_bytes)

                lo_profile = temp_dir / "lo_profile"
                lo_profile.mkdir()

                result = subprocess.run(
                    [
                        "soffice",
                        f"-env:UserInstallation=file://{lo_profile}",
                        "--headless",
                        "--convert-to", "pdf",
                        "--outdir", str(temp_dir),
                        str(in_path),
                    ],
                    capture_output=True,
                    timeout=120,
                )

            if result.returncode != 0:
                err = result.stderr.decode(errors="replace")[:500]
                return ExportResult(False, error=f"LibreOffice PDF export failed: {err}")

            pdf_stem = in_path.stem
            pdf_path = temp_dir / f"{pdf_stem}.pdf"
            if not pdf_path.exists():
                pdfs = list(temp_dir.glob("*.pdf"))
                if pdfs:
                    pdf_path = pdfs[0]
                else:
                    return ExportResult(False, error="No PDF output found")

            pdf_bytes = pdf_path.read_bytes()
            page_count = self._pdf_page_count(pdf_bytes)

            return ExportResult(
                success=True,
                data=pdf_bytes,
                filename=pdf_path.name,
                format="pdf",
                page_count=page_count,
                file_size=len(pdf_bytes),
                exec_time_ms=round((time.time() - start) * 1000, 2),
            )

        except FileNotFoundError:
            return ExportResult(False, error="LibreOffice not found on PATH")
        except subprocess.TimeoutExpired:
            return ExportResult(False, error="LibreOffice timed out (120s)")
        except Exception as exc:
            return ExportResult(False, error=str(exc))
        finally:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    # ──────────────────────────────────────────────────────────────────────────
    # Image ZIP export
    # ──────────────────────────────────────────────────────────────────────────

    async def export_images(
        self,
        pptx_bytes:      bytes,
        source_filename: str = "presentation.pptx",
        dpi:             int = 150,
        slide_range:     Optional[tuple] = None,    # (start, end) 1-based
        format:          str = "png",               # "png" | "jpg"
        thumbnail_size:  Optional[int] = None,      # None = full size, int = max width px
    ) -> ExportResult:
        """
        Export all slides as individual image files bundled in a ZIP.

        Parameters
        ----------
        dpi            : render resolution (72=fast, 150=balanced, 300=print quality)
        slide_range    : optional (start, end) 1-based to export only a range
        format         : "png" or "jpg"
        thumbnail_size : if set, resize each slide to this max width (preserving aspect ratio)
        """
        import time
        start = time.time()

        from core.vision.slide_renderer import SlideRenderer
        renderer = SlideRenderer(render_dpi=dpi)

        manifest = await renderer.render(
            file_bytes=pptx_bytes,
            file_type="pptx",
            filename=source_filename,
            slide_range=slide_range,
        )

        if not manifest.success:
            return ExportResult(False, error=f"Render failed: {manifest.error}")

        # Build ZIP in memory
        loop = asyncio.get_event_loop()
        zip_bytes = await loop.run_in_executor(
            None,
            self._build_zip,
            manifest.slides, format, thumbnail_size,
            Path(source_filename).stem,
        )

        stem = Path(source_filename).stem
        return ExportResult(
            success=True,
            data=zip_bytes,
            filename=f"{stem}_slides.zip",
            format="images_zip",
            page_count=len(manifest.slides),
            file_size=len(zip_bytes),
            exec_time_ms=round((time.time() - start) * 1000, 2),
        )

    def _build_zip(
        self,
        slides,
        fmt: str,
        thumb_size: Optional[int],
        stem: str,
    ) -> bytes:
        """Build in-memory ZIP of slide images."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for slide in slides:
                img_bytes = slide.image_bytes
                if thumb_size:
                    img_bytes = self._resize_image(img_bytes, thumb_size)
                if fmt == "jpg":
                    img_bytes = self._png_to_jpg(img_bytes)

                filename = f"{stem}_slide_{slide.index:04d}.{fmt}"
                zf.writestr(filename, img_bytes)
        return buf.getvalue()

    @staticmethod
    def _resize_image(png_bytes: bytes, max_width: int) -> bytes:
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(png_bytes))
            if img.width > max_width:
                ratio = max_width / img.width
                new_h = int(img.height * ratio)
                img = img.resize((max_width, new_h), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            return png_bytes

    @staticmethod
    def _png_to_jpg(png_bytes: bytes, quality: int = 90) -> bytes:
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            return buf.getvalue()
        except Exception:
            return png_bytes

    # ──────────────────────────────────────────────────────────────────────────
    # HTML export
    # ──────────────────────────────────────────────────────────────────────────

    async def export_html(
        self,
        pptx_bytes:      bytes,
        source_filename: str = "presentation.pptx",
    ) -> ExportResult:
        """
        Convert PPTX to HTML using LibreOffice headless.
        Produces a basic HTML representation (limited fidelity for complex slides).
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._export_html_sync, pptx_bytes, source_filename
        )

    def _export_html_sync(self, pptx_bytes: bytes, source_filename: str) -> ExportResult:
        import time
        start = time.time()
        temp_dir = None
        try:
            with _LO_LOCK:
                temp_dir = Path(tempfile.mkdtemp(prefix="export_html_"))
                in_path  = temp_dir / Path(source_filename).name
                in_path.write_bytes(pptx_bytes)

                lo_profile = temp_dir / "lo_profile"
                lo_profile.mkdir()

                result = subprocess.run(
                    [
                        "soffice",
                        f"-env:UserInstallation=file://{lo_profile}",
                        "--headless",
                        "--convert-to", "html",
                        "--outdir", str(temp_dir),
                        str(in_path),
                    ],
                    capture_output=True,
                    timeout=120,
                )

            if result.returncode != 0:
                err = result.stderr.decode(errors="replace")[:500]
                return ExportResult(False, error=f"LibreOffice HTML export failed: {err}")

            html_files = list(temp_dir.glob("*.html")) + list(temp_dir.glob("*.htm"))
            if not html_files:
                return ExportResult(False, error="No HTML output found")

            # Bundle HTML + any linked assets into a ZIP
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in temp_dir.iterdir():
                    if p.suffix.lower() in (".html", ".htm", ".css", ".png", ".jpg", ".gif"):
                        zf.writestr(p.name, p.read_bytes())

            zip_bytes = buf.getvalue()
            stem = Path(source_filename).stem

            return ExportResult(
                success=True,
                data=zip_bytes,
                filename=f"{stem}_html.zip",
                format="html_zip",
                file_size=len(zip_bytes),
                exec_time_ms=round((time.time() - start) * 1000, 2),
            )

        except FileNotFoundError:
            return ExportResult(False, error="LibreOffice not found on PATH")
        except subprocess.TimeoutExpired:
            return ExportResult(False, error="LibreOffice timed out (120s)")
        except Exception as exc:
            return ExportResult(False, error=str(exc))
        finally:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    # ──────────────────────────────────────────────────────────────────────────
    # Thumbnail generation
    # ──────────────────────────────────────────────────────────────────────────

    async def generate_thumbnails(
        self,
        pptx_bytes:      bytes,
        source_filename: str = "presentation.pptx",
        width:           int = 240,
        slide_range:     Optional[tuple] = None,
    ) -> ExportResult:
        """
        Generate small thumbnail PNGs for gallery/picker UI.
        Returns a ZIP of thumbnail images.
        """
        return await self.export_images(
            pptx_bytes=pptx_bytes,
            source_filename=source_filename,
            dpi=72,
            slide_range=slide_range,
            thumbnail_size=width,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Batch export (multiple formats at once)
    # ──────────────────────────────────────────────────────────────────────────

    async def batch_export(
        self,
        pptx_bytes:      bytes,
        source_filename: str,
        formats:         List[str],     # e.g. ["pdf", "images", "html"]
        dpi:             int = 150,
    ) -> Dict[str, ExportResult]:
        """
        Export to multiple formats concurrently.

        Returns a dict keyed by format name.
        """
        tasks = {}

        if "pdf" in formats:
            tasks["pdf"] = self.export_pdf(pptx_bytes, source_filename)
        if "images" in formats:
            tasks["images"] = self.export_images(pptx_bytes, source_filename, dpi=dpi)
        if "html" in formats:
            tasks["html"] = self.export_html(pptx_bytes, source_filename)
        if "thumbnails" in formats:
            tasks["thumbnails"] = self.generate_thumbnails(pptx_bytes, source_filename)

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        output: Dict[str, ExportResult] = {}

        for fmt, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                output[fmt] = ExportResult(False, format=fmt, error=str(result))
            else:
                output[fmt] = result

        return output

    # ──────────────────────────────────────────────────────────────────────────
    # Batch PPTX processing (ZIP of multiple PPTX files)
    # ──────────────────────────────────────────────────────────────────────────

    async def process_zip_upload(
        self,
        zip_bytes: bytes,
        action:    str = "analyze",     # "analyze" | "export_pdf" | "export_images"
        user_id:   str = "",
    ) -> Dict[str, Any]:
        """
        Extract a ZIP file of PPTX/PDF files and process each one.

        Returns a summary with per-file results and job_ids.
        """
        from core.vision.slide_renderer import SlideRenderer
        from core.vision.vision_engine import VisionEngine

        results = []
        renderer = SlideRenderer()
        vision   = VisionEngine()

        try:
            buf = io.BytesIO(zip_bytes)
            with zipfile.ZipFile(buf, "r") as zf:
                names = [
                    n for n in zf.namelist()
                    if Path(n).suffix.lower() in (".pptx", ".ppt", ".pdf")
                    and not n.startswith("__MACOSX")
                ]

                for name in names:
                    try:
                        file_bytes = zf.read(name)
                        fname = Path(name).name
                        ftype = Path(name).suffix.lstrip(".").lower()

                        file_result: Dict[str, Any] = {
                            "filename": fname,
                            "file_type": ftype,
                            "size_bytes": len(file_bytes),
                        }

                        if action == "analyze":
                            manifest = await renderer.render(
                                file_bytes=file_bytes, file_type=ftype, filename=fname
                            )
                            file_result["slide_count"] = manifest.slide_count
                            file_result["render_success"] = manifest.success
                            file_result["render_error"] = manifest.error

                        elif action == "export_pdf":
                            if ftype in ("pptx", "ppt"):
                                export = await self.export_pdf(file_bytes, fname)
                                file_result["pdf_size"] = export.file_size
                                file_result["export_success"] = export.success
                                file_result["export_error"] = export.error
                                # Store PDF on volume
                                if export.success:
                                    import uuid, os
                                    from pathlib import Path as P
                                    storage = P(os.environ.get("STORAGE_ROOT", "/data"))
                                    out_dir = storage / "batch_exports" / user_id
                                    out_dir.mkdir(parents=True, exist_ok=True)
                                    out_path = out_dir / (export.filename or "export.pdf")
                                    out_path.write_bytes(export.data)
                                    file_result["download_path"] = str(out_path)

                        results.append(file_result)

                    except Exception as exc:
                        results.append({
                            "filename": name,
                            "error": str(exc),
                        })

        except zipfile.BadZipFile:
            return {"success": False, "error": "Invalid ZIP file"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        return {
            "success": True,
            "action": action,
            "file_count": len(results),
            "files": results,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # PDF page count helper
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _pdf_page_count(pdf_bytes: bytes) -> int:
        try:
            import fitz
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            count = len(doc)
            doc.close()
            return count
        except Exception:
            return 0
