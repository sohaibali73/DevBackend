"""
Document Generation Tools  (core/tools_v2/document_tools.py)
=============================================================
Provides three server-side Potomac document generation tools — all run entirely
on the Railway server without any Claude Skills container or API cost.

Tools
-----
generate_docx  — Potomac-branded Word document (.docx)
                 Engine: Node.js + ``docx`` npm package
                 Assets: ClaudeSkills/potomac-docx/assets/

generate_pptx  — Potomac-branded PowerPoint presentation (.pptx)
                 Engine: Node.js + ``pptxgenjs`` npm package
                 Assets: ClaudeSkills/potomac-pptx/brand-assets/logos/

generate_xlsx  — Potomac-branded Excel workbook (.xlsx)
                 Engine: Pure Python, ``openpyxl``
                 Assets: none (brand applied in-process)

Handler signature (all three)
------------------------------
    handle_generate_*(tool_input, api_key=None, supabase_client=None) -> str (JSON)

On success the JSON contains:
    {"status": "success", "file_id": "...", "filename": "...",
     "size_kb": 42.3, "download_url": "/files/<id>/download",
     "exec_time_ms": 4200, "message": "..."}

On failure:
    {"status": "error", "error": "<message>"}

Auto-registration
-----------------
All three tools are registered in ToolRegistry at import time via
``_auto_register()``.  core/tools.py dispatch table is handled separately
via ``elif tool_name == "generate_*"`` branches.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)


# =============================================================================
# ── DOCX ──────────────────────────────────────────────────────────────────────
# =============================================================================

GENERATE_DOCX_TOOL_DEF: Dict[str, Any] = {
    "name": "generate_docx",
    "description": (
        "Generate a professional Potomac-branded Word document (.docx) entirely "
        "on the server — no Claude Skills container, no API cost, instant download. "
        "Use this instead of invoke_skill for any Potomac Word document request: "
        "fund fact sheets, market commentaries, research reports, client memos, "
        "risk reports, performance reports, proposals, SOPs, trade rationale, "
        "onboarding guides, legal agreements, or any other business document.\n\n"
        "Capabilities:\n"
        "- Potomac yellow (#FEC00F) / dark-gray (#212121) brand palette\n"
        "- Potomac logo on every page header (standard, black, or white variant)\n"
        "- H1/H2/H3 headings (Rajdhani ALL CAPS), body text (Quicksand)\n"
        "- Bullet lists, numbered lists, multi-column tables (zebra-striped, yellow headers)\n"
        "- User-uploaded images embedded via file_id\n"
        "- Dividers, spacers, page breaks\n"
        "- Standard Potomac disclosure block (auto-appended unless disabled)\n"
        "- Page-number footer\n\n"
        "IMPORTANT: Populate `sections` with ALL the document content. "
        "Be thorough — the AI writes the content; the tool formats and saves it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "filename":   {"type": "string", "description": "Output filename e.g. 'Potomac_Q1_Commentary.docx'."},
            "title":      {"type": "string", "description": "Main document title (ALL CAPS recommended)."},
            "subtitle":   {"type": "string", "description": "Optional subtitle below the title."},
            "date":       {"type": "string", "description": "Document date e.g. 'April 2026'."},
            "author":     {"type": "string", "description": "Author / team name."},
            "logo_variant": {
                "type": "string", "enum": ["standard", "black", "white"], "default": "standard",
                "description": "Potomac logo variant in header.",
            },
            "header_line_color": {
                "type": "string", "enum": ["yellow", "dark"], "default": "yellow",
                "description": "Color of the underline beneath the header logo.",
            },
            "footer_text": {"type": "string", "description": "Custom footer left text."},
        "sections": {
            "type": "array",
            "description": (
                "Ordered content blocks. Each has a 'type' field:\n"
                "\n"
                "  heading      → level (1/2/3), text\n"
                "  paragraph    → text  OR  runs:[{text,bold,italics,color,hyperlink}]\n"
                "  bullets      → items:[str, ...]\n"
                "  numbered     → items:[str, ...]\n"
                "  table        → headers:[str], rows:[[str]], col_widths:[int], col_alignment, caption, summary_row\n"
                "  highlight_table → Auto-color table (green/red by +/- sign). Same fields as table + auto_color_cols\n"
                "  image        → file_id (upload) or data (base64), width, height, align, caption\n"
                "  callout      → style (yellow/dark/light), icon, title, body\n"
                "  kpi_row      → metrics:[{value,label,delta,positive}]\n"
                "  quote_block  → quote, attribution, background\n"
                "  two_column   → left:{heading,body}, right:{heading,body}, divider\n"
                "  divider      → (yellow horizontal rule)\n"
                "  spacer       → size (twips)\n"
                "  page_break   → (no extra fields)\n"
            ),
                "items": {
                    "type": "object",
                    "properties": {
                        "type":       {"type": "string"},
                        "level":      {"type": "integer", "enum": [1, 2, 3]},
                        "text":       {"type": "string"},
                        "runs":       {"type": "array", "items": {"type": "object"}},
                        "items":      {"type": "array", "items": {"type": "string"}},
                        "headers":    {"type": "array", "items": {"type": "string"}},
                        "rows":       {"type": "array", "items": {"type": "array"}},
                        "col_widths": {"type": "array", "items": {"type": "integer"}},
                        "size":       {"type": "integer"},
                        "color":      {"type": "string"},
                        "file_id":    {"type": "string"},
                        "width":      {"type": "integer"},
                        "height":     {"type": "integer"},
                        "align":      {"type": "string", "enum": ["left", "center", "right"]},
                        "caption":    {"type": "string"},
                    },
                    "required": ["type"],
                },
            },
            "include_disclosure": {
                "type": "boolean", "default": True,
                "description": "Append standard Potomac disclosures. Set false for internal docs.",
            },
            "disclosure_text": {"type": "string", "description": "Custom disclosure text."},
        },
        "required": ["title", "sections"],
    },
}


def handle_generate_docx(
    tool_input: Dict[str, Any],
    api_key: str = None,
    supabase_client=None,
) -> str:
    """Generate a Potomac-branded .docx and return a JSON result string."""
    start = time.time()
    try:
        from core.sandbox.docx_sandbox import DocxSandbox
        from core.file_store import store_file

        title    = tool_input.get("title", "").strip()
        sections = tool_input.get("sections", [])
        if not title:
            return json.dumps({"status": "error", "error": "Missing required field: 'title'"})
        if not isinstance(sections, list):
            return json.dumps({"status": "error", "error": "'sections' must be an array"})

        spec: Dict[str, Any] = {
            "title":              title,
            "sections":           sections,
            "filename":           _safe_filename(tool_input.get("filename") or f"{title}.docx", ".docx"),
            "subtitle":           tool_input.get("subtitle", ""),
            "date":               tool_input.get("date", ""),
            "author":             tool_input.get("author", ""),
            "logo_variant":       tool_input.get("logo_variant", "standard"),
            "header_line_color":  tool_input.get("header_line_color", "yellow"),
            "footer_text":        tool_input.get("footer_text", ""),
            "include_disclosure": tool_input.get("include_disclosure", True),
            "disclosure_text":    tool_input.get("disclosure_text", ""),
        }

        logger.info("generate_docx: title=%r  sections=%d", spec["title"], len(sections))

        result = DocxSandbox().generate(spec, timeout=120)
        if not result.success:
            return json.dumps({"status": "error", "error": result.error or "DocxSandbox error"})

        entry = store_file(data=result.data, filename=result.filename,
                           file_type="docx", tool_name="generate_docx")
        elapsed_ms = round((time.time() - start) * 1000, 2)
        logger.info("generate_docx ✓  %s  %.1f KB  → /files/%s/download",
                    entry.filename, entry.size_kb, entry.file_id)

        return json.dumps({
            "status":       "success",
            "file_id":      entry.file_id,
            "filename":     entry.filename,
            "size_kb":      entry.size_kb,
            "download_url": f"/files/{entry.file_id}/download",
            "exec_time_ms": elapsed_ms,
            "message": (
                f"✅ Document '{entry.filename}' generated successfully "
                f"({entry.size_kb:.1f} KB). "
                f"Download: /files/{entry.file_id}/download"
            ),
        })

    except Exception as exc:
        logger.error("handle_generate_docx error: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "error": str(exc)})


# =============================================================================
# ── PPTX ──────────────────────────────────────────────────────────────────────
# =============================================================================

GENERATE_PPTX_TOOL_DEF: Dict[str, Any] = {
    "name": "generate_pptx",
    "description": (
        "Generate a professional Potomac-branded PowerPoint presentation (.pptx) "
        "entirely on the server — no Claude Skills container, no API cost, instant download. "
        "Use for any Potomac slide deck request: client pitches, market outlooks, "
        "quarterly reviews, fund overviews, educational decks, board presentations, "
        "proposal decks, investment strategy summaries, or any presentation.\n\n"
        "Slide types available:\n"
        "  title           — large branded title slide (standard or executive dark style)\n"
        "  content         — bullet list or text with title\n"
        "  two_column      — side-by-side comparison layout\n"
        "  three_column    — triple-column layout with optional headers\n"
        "  metrics         — large KPI numbers (up to 6 metrics per slide)\n"
        "  process         — horizontal step-by-step flow with numbered circles\n"
        "  quote           — testimonial / pull-quote with attribution\n"
        "  section_divider — branded section break with thick left accent bar\n"
        "  cta             — closing / call-to-action slide with button and contact info\n"
        "  image           — full-slide image from user upload (file_id) or base64\n\n"
        "IMPORTANT: Build a complete deck — include a title slide, section dividers, "
        "content slides, and a CTA closing slide.  More slides = better output."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Output filename e.g. 'Potomac_Q1_Outlook.pptx'. Use underscores.",
            },
            "title": {
                "type": "string",
                "description": "Presentation title (used in metadata and default title slide).",
            },
            "slides": {
                "type": "array",
                "description": "Ordered list of slides. Each slide has a 'type' field plus type-specific fields.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": [
                                "title", "content", "two_column", "three_column",
                                "metrics", "process", "quote", "section_divider", "cta", "image",
                            ],
                            "description": (
                                "Slide layout type:\n"
                                "  title           → title, subtitle, tagline, style ('standard'|'executive')\n"
                                "  content         → title, bullets:[str] OR text:str\n"
                                "  two_column      → title, left_header, right_header, left_content, right_content\n"
                                "                    (or columns:[left_str, right_str])\n"
                                "  three_column    → title, column_headers:[h1,h2,h3], columns:[c1,c2,c3]\n"
                                "  metrics         → title, metrics:[{value,label},...], context\n"
                                "  process         → title, steps:[{title,description},...]\n"
                                "  quote           → quote, attribution, context\n"
                                "  section_divider → title, description\n"
                                "  cta             → title, action_text, button_text, contact_info\n"
                                "  image           → title(opt), file_id OR data(base64), format, width, height, align, caption"
                            ),
                        },
                        # ── title slide ──
                        "style":      {"type": "string", "enum": ["standard", "executive"],
                                       "description": "Title slide style. 'executive' = dark background."},
                        "subtitle":   {"type": "string"},
                        "tagline":    {"type": "string", "description": "Tagline below accent bar on title slides."},
                        # ── content ──
                        "title":      {"type": "string"},
                        "bullets":    {"type": "array", "items": {"type": "string"},
                                       "description": "Bullet list items for type='content'."},
                        "text":       {"type": "string",
                                       "description": "Plain text body for type='content' (use instead of bullets)."},
                        # ── two_column ──
                        "left_header":  {"type": "string", "description": "Optional left column label."},
                        "right_header": {"type": "string", "description": "Optional right column label."},
                        "left_content": {"type": "string"},
                        "right_content": {"type": "string"},
                        "columns":    {"type": "array", "items": {"type": "string"},
                                       "description": "Content strings for two_column [left, right] or three_column [c1, c2, c3]."},
                        # ── three_column ──
                        "column_headers": {"type": "array", "items": {"type": "string"},
                                           "description": "Header labels for three_column slide."},
                        # ── metrics ──
                        "metrics": {
                            "type": "array",
                            "description": "Key metrics for type='metrics'. Up to 6 items (3 per row).",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "value": {"type": "string", "description": "e.g. '47%', '$2.3B', '4.2x'"},
                                    "label": {"type": "string", "description": "e.g. 'Annualized Return'"},
                                },
                                "required": ["value", "label"],
                            },
                        },
                        "context": {"type": "string",
                                    "description": "Small disclaimer / context text at slide bottom (metrics, quote)."},
                        # ── process ──
                        "steps": {
                            "type": "array",
                            "description": "Process steps for type='process'. 3-5 steps recommended.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title":       {"type": "string"},
                                    "description": {"type": "string"},
                                },
                                "required": ["title", "description"],
                            },
                        },
                        # ── quote ──
                        "quote":       {"type": "string"},
                        "attribution": {"type": "string", "description": "Speaker / source attribution."},
                        # ── section_divider ──
                        "description": {"type": "string", "description": "Subtitle text on section_divider slides."},
                        # ── cta ──
                        "action_text":  {"type": "string", "description": "Main call-to-action body text."},
                        "button_text":  {"type": "string", "description": "CTA button label. Default: 'GET STARTED'."},
                        "contact_info": {"type": "string",
                                         "description": "Contact line e.g. 'potomac.com | (305) 824-2702'."},
                        # ── image ──
                        "file_id":  {"type": "string",
                                     "description": "UUID of a user-uploaded file. Python resolves to base64 before Node runs."},
                        "format":   {"type": "string", "enum": ["png", "jpg", "jpeg", "gif"],
                                     "description": "Image format (default 'png')."},
                        "width":    {"type": "number", "description": "Image width in inches (default 6)."},
                        "height":   {"type": "number", "description": "Image height in inches (auto-calculated if omitted)."},
                        "align":    {"type": "string", "enum": ["left", "center", "right"],
                                     "description": "Image horizontal alignment."},
                        "caption":  {"type": "string", "description": "Small italic caption below the image."},
                    },
                    "required": ["type"],
                },
            },
        },
        "required": ["title", "slides"],
    },
}


def handle_generate_pptx(
    tool_input: Dict[str, Any],
    api_key: str = None,
    supabase_client=None,
) -> str:
    """Generate a Potomac-branded .pptx and return a JSON result string."""
    start = time.time()
    try:
        from core.sandbox.pptx_sandbox import PptxSandbox
        from core.file_store import store_file

        title  = tool_input.get("title", "").strip()
        slides = tool_input.get("slides", [])
        if not title:
            return json.dumps({"status": "error", "error": "Missing required field: 'title'"})
        if not isinstance(slides, list) or not slides:
            return json.dumps({"status": "error", "error": "'slides' must be a non-empty array"})

        spec: Dict[str, Any] = {
            "title":    title,
            "slides":   slides,
            "filename": _safe_filename(tool_input.get("filename") or f"{title}.pptx", ".pptx"),
        }

        logger.info("generate_pptx: title=%r  slides=%d", spec["title"], len(slides))

        result = PptxSandbox().generate(spec, timeout=120)
        if not result.success:
            return json.dumps({"status": "error", "error": result.error or "PptxSandbox error"})

        entry = store_file(data=result.data, filename=result.filename,
                           file_type="pptx", tool_name="generate_pptx")
        elapsed_ms = round((time.time() - start) * 1000, 2)
        logger.info("generate_pptx ✓  %s  %.1f KB  → /files/%s/download",
                    entry.filename, entry.size_kb, entry.file_id)

        return json.dumps({
            "status":       "success",
            "file_id":      entry.file_id,
            "filename":     entry.filename,
            "size_kb":      entry.size_kb,
            "download_url": f"/files/{entry.file_id}/download",
            "exec_time_ms": elapsed_ms,
            "message": (
                f"✅ Presentation '{entry.filename}' generated successfully "
                f"({entry.size_kb:.1f} KB, {len(slides)} slides). "
                f"Download: /files/{entry.file_id}/download"
            ),
        })

    except Exception as exc:
        logger.error("handle_generate_pptx error: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "error": str(exc)})


# =============================================================================
# ── XLSX ──────────────────────────────────────────────────────────────────────
# =============================================================================

GENERATE_XLSX_TOOL_DEF: Dict[str, Any] = {
    "name": "generate_xlsx",
    "description": (
        "Generate a professional Potomac-branded Excel workbook (.xlsx) entirely "
        "on the server — no Claude Skills container, no API cost, instant download. "
        "Use for any Potomac spreadsheet request: performance reports, portfolio trackers, "
        "risk dashboards, trade logs, fee schedules, budget models, data exports, "
        "onboarding checklists, financial models, or any tabular data.\n\n"
        "Capabilities:\n"
        "- Potomac yellow (#FEC00F) column headers and title block\n"
        "- Zebra-striped data rows (white / light-gray alternating)\n"
        "- Thin borders, Calibri font, dark-gray (#212121) text\n"
        "- Multiple sheets with colored tabs\n"
        "- Number format strings per column (%, $, commas, dates)\n"
        "- Excel formula support (e.g. '=SUM(B2:B9)')\n"
        "- Frozen panes, print-ready landscape layout\n"
        "- Optional DISCLOSURES sheet auto-appended\n\n"
        "IMPORTANT: Supply actual data values in 'rows'. "
        "Use formulas for any calculated columns. "
        "Column headers are auto-uppercased."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Output filename e.g. 'Potomac_PerformanceReport_Q12026.xlsx'.",
            },
            "title": {
                "type": "string",
                "description": "Workbook title shown in the title block of every sheet (ALL CAPS recommended).",
            },
            "subtitle": {
                "type": "string",
                "description": "Optional subtitle / date shown below the title, e.g. 'As of March 31, 2026'.",
            },
            "sheets": {
                "type": "array",
                "description": "One or more worksheet definitions.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Sheet tab name (auto-uppercased, max 31 chars). e.g. 'PERFORMANCE'.",
                        },
                        "tab_color": {
                            "type": "string",
                            "description": (
                                "Tab color hex (no #). Defaults by position: "
                                "first=FEC00F (yellow), others=212121 (dark gray)."
                            ),
                        },
                        "columns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Column header labels (auto-uppercased). e.g. ['DATE', 'STRATEGY', 'RETURN %'].",
                        },
                        "col_widths": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Column widths in Excel character units. e.g. [12, 20, 10]. Defaults to 16 for unspecified columns.",
                        },
                        "rows": {
                            "type": "array",
                            "description": "Data rows. Each row is an array of cell values (strings or numbers).",
                            "items": {
                                "type": "array",
                                "items": {},
                            },
                        },
                        "number_formats": {
                            "type": "object",
                            "description": (
                                "Column-index (1-based, as string) → Excel number format string. "
                                "e.g. {\"3\": \"0.0%\", \"4\": \"$#,##0.0\", \"5\": \"MMM D, YYYY\"}. "
                                "Common formats: '0.0%' (percent), '$#,##0.0' (currency), '#,##0' (integer), '0.00' (decimal)."
                            ),
                            "additionalProperties": {"type": "string"},
                        },
                        "formulas": {
                            "type": "array",
                            "description": "Optional formula overrides for specific cells.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "cell":    {"type": "string",
                                                "description": "Cell address e.g. 'C10', 'B2'."},
                                    "formula": {"type": "string",
                                                "description": "Excel formula e.g. '=SUM(C5:C9)', '=AVERAGE(B5:B15)'."},
                                },
                                "required": ["cell", "formula"],
                            },
                        },
                        "include_footer": {
                            "type": "boolean",
                            "default": True,
                            "description": "Add Potomac footer row below the data. Default true.",
                        },
                        "footer_text": {
                            "type": "string",
                            "description": "Custom footer text. Default: 'Potomac | Built to Conquer Risk® | For Advisor Use Only'.",
                        },
                        "freeze_panes": {
                            "type": "string",
                            "description": (
                                "Cell address to freeze panes at e.g. 'A5' freezes rows 1-4. "
                                "Defaults to the row below column headers."
                            ),
                        },
                    },
                    "required": ["name", "columns", "rows"],
                },
            },
            "include_disclosures": {
                "type": "boolean",
                "default": True,
                "description": "Auto-append a DISCLOSURES sheet at the end. Default true.",
            },
            "disclosure_text": {
                "type": "string",
                "description": "Custom disclosure text for the DISCLOSURES sheet.",
            },
        },
        "required": ["title", "sheets"],
    },
}


def handle_generate_xlsx(
    tool_input: Dict[str, Any],
    api_key: str = None,
    supabase_client=None,
) -> str:
    """Generate a Potomac-branded .xlsx workbook and return a JSON result string."""
    start = time.time()
    try:
        from core.sandbox.xlsx_sandbox import XlsxSandbox
        from core.file_store import store_file

        title  = tool_input.get("title", "").strip()
        sheets = tool_input.get("sheets", [])
        if not title:
            return json.dumps({"status": "error", "error": "Missing required field: 'title'"})
        if not isinstance(sheets, list) or not sheets:
            return json.dumps({"status": "error", "error": "'sheets' must be a non-empty array"})

        spec: Dict[str, Any] = {
            "title":                title,
            "subtitle":             tool_input.get("subtitle", ""),
            "sheets":               sheets,
            "filename":             _safe_filename(tool_input.get("filename") or f"{title}.xlsx", ".xlsx"),
            "include_disclosures":  tool_input.get("include_disclosures", True),
            "disclosure_text":      tool_input.get("disclosure_text", ""),
        }

        # Count total rows for logging
        total_rows = sum(len(s.get("rows", [])) for s in sheets)
        logger.info("generate_xlsx: title=%r  sheets=%d  rows=%d",
                    spec["title"], len(sheets), total_rows)

        result = XlsxSandbox().generate(spec)
        if not result.success:
            return json.dumps({"status": "error", "error": result.error or "XlsxSandbox error"})

        entry = store_file(data=result.data, filename=result.filename,
                           file_type="xlsx", tool_name="generate_xlsx")
        elapsed_ms = round((time.time() - start) * 1000, 2)
        logger.info("generate_xlsx ✓  %s  %.1f KB  → /files/%s/download",
                    entry.filename, entry.size_kb, entry.file_id)

        return json.dumps({
            "status":       "success",
            "file_id":      entry.file_id,
            "filename":     entry.filename,
            "size_kb":      entry.size_kb,
            "download_url": f"/files/{entry.file_id}/download",
            "exec_time_ms": elapsed_ms,
            "message": (
                f"✅ Workbook '{entry.filename}' generated successfully "
                f"({entry.size_kb:.1f} KB, {len(sheets)} sheet(s)). "
                f"Download: /files/{entry.file_id}/download"
            ),
        })

    except Exception as exc:
        logger.error("handle_generate_xlsx error: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "error": str(exc)})


# =============================================================================
# Shared helpers
# =============================================================================

def _safe_filename(name: str, ext: str) -> str:
    """Sanitise a filename — keep alphanumerics, underscores, hyphens, dots."""
    safe = re.sub(r"[^\w.\-]", "_", name)
    ext_lower = ext.lower()
    if not safe.lower().endswith(ext_lower):
        safe += ext_lower
    return safe[:120]


# =============================================================================
# Auto-registration in ToolRegistry
# =============================================================================

def _auto_register() -> None:
    """
    Register all three document tools in the ToolRegistry at import time.

    Covers code paths going through
    ``core/tools_v2/registry.py::ToolRegistry.handle_tool_call()``.
    The ``core/tools.py`` dispatch table is handled separately.
    """
    try:
        from core.tools_v2.registry import ToolRegistry
        reg = ToolRegistry()
        reg.register_tool(GENERATE_DOCX_TOOL_DEF, handler=handle_generate_docx)
        reg.register_tool(GENERATE_PPTX_TOOL_DEF, handler=handle_generate_pptx)
        reg.register_tool(GENERATE_XLSX_TOOL_DEF, handler=handle_generate_xlsx)
        logger.debug("generate_docx / generate_pptx / generate_xlsx registered in ToolRegistry")
    except Exception as exc:
        logger.debug("ToolRegistry auto-register skipped: %s", exc)


# Register on import
_auto_register()
