"""
PDF Injector
============

Converts pages from an uploaded PDF file → PNG images for DOCX embedding.
Used by the `include_pdf` section type in generate_docx.

Uses PyMuPDF (fitz) for high quality page rendering.
"""

import io
import logging
import base64
from typing import Dict, Any, Optional, List, Union

logger = logging.getLogger(__name__)


def pdf_pages_to_sections(
    file_id: str,
    pages: Optional[Union[int, List[int]]] = None,
    zoom: float = 2.0,
    caption: Optional[str] = None,
    align: str = "center",
) -> List[Dict[str, Any]]:
    """
    Render PDF pages as high resolution PNG images for embedding in DOCX.

    Args:
        file_id: UUID of uploaded PDF file in file_store
        pages: Single page number or list of page numbers (1-based), or None for all pages
        zoom: Render scale factor. 2.0 = 144 DPI, 3.0 = 216 DPI (default 2.0)
        caption: Optional caption text shown below each page
        align: Image alignment: left, center, right (default center)

    Returns:
        List of chart/image sections ready to be inserted into DOCX sections array
    """
    try:
        import fitz  # PyMuPDF
        from core.file_store import get_file

        entry = get_file(file_id)
        if not entry or not entry.data:
            logger.warning("pdf_pages_to_sections: file_id %s not found", file_id)
            return [{"type": "paragraph", "text": "[PDF unavailable]"}]

        # Open PDF from bytes
        doc = fitz.open(stream=io.BytesIO(entry.data), filetype="pdf")
        total_pages = doc.page_count
        logger.info("pdf_pages_to_sections: opened %d pages from %s", total_pages, file_id)

        # Resolve page selection
        selected_pages: List[int] = []
        if pages is None:
            selected_pages = list(range(total_pages))
        elif isinstance(pages, int):
            selected_pages = [pages - 1]  # convert 1-based to 0-based
        elif isinstance(pages, list):
            selected_pages = [p - 1 for p in pages if 1 <= p <= total_pages]

        if not selected_pages:
            logger.warning("pdf_pages_to_sections: no valid pages selected")
            return [{"type": "paragraph", "text": "[No PDF pages selected]"}]

        sections: List[Dict[str, Any]] = []

        for page_idx in selected_pages:
            page = doc.load_page(page_idx)

            # Render page to pixmap (RGBA)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            png_data = pix.tobytes("png")

            sections.append({
                "type": "chart",
                "data": base64.b64encode(png_data).decode("ascii"),
                "format": "png",
                "width": 880,  # full page width in docx twips
                "height": int(880 * (pix.height / pix.width)),
                "align": align,
                "caption": f"{caption} (Page {page_idx + 1})" if caption and len(selected_pages) > 1 else caption,
            })

            # Add small spacer between pages
            if page_idx != selected_pages[-1]:
                sections.append({"type": "spacer", "size": 180})

        doc.close()
        logger.info("pdf_pages_to_sections: rendered %d pages from %s", len(sections), file_id)
        return sections

    except Exception as exc:
        logger.error("pdf_pages_to_sections error: %s", exc, exc_info=True)
        return [{"type": "paragraph", "text": f"[Could not load PDF: {str(exc)}]"}]
