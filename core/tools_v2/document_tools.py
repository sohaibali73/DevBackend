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
            "template": {
                "type": "string",
                "enum": [
                    "fund_fact_sheet",
                    "market_commentary",
                    "performance_report",
                    "client_letter",
                    "research_report",
                    "proposal",
                    "trade_rationale",
                    "meeting_minutes",
                    "onboarding_packet",
                    "quarterly_review"
                ],
                "description": "Named document template. When provided, pre-populates document structure.",
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
                "  table_from_xlsx → Import table directly from uploaded xlsx file_id\n"
                "  include_pdf    → Inject pages from uploaded PDF file as high res images\n"
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

        # Apply template if specified
        from core.tools_v2.docx_templates import DOCX_TEMPLATES, deep_merge
        template_key = tool_input.get("template")

        if template_key and template_key in DOCX_TEMPLATES:
            base_spec = DOCX_TEMPLATES[template_key]
            spec = deep_merge(base_spec, tool_input)
            # Ensure title/sections are preserved
            spec["title"] = title
            spec["sections"] = sections if sections else base_spec.get("sections", [])
        else:
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

        # Resolve table_from_xlsx sections (import xlsx file_id → highlight_table)
        resolved_sections = []
        for section in spec["sections"]:
            if section.get("type") == "table_from_xlsx":
                try:
                    from core.tools_v2.xlsx_table_importer import xlsx_to_table_section
                    resolved = xlsx_to_table_section(
                        file_id=section.get("file_id", ""),
                        sheet=section.get("sheet", 0),
                        range_str=section.get("range"),
                        header_row=section.get("header_row", True),
                        auto_color=section.get("auto_color", True),
                        caption=section.get("caption"),
                    )
                    resolved_sections.append(resolved)
                except Exception as e:
                    logger.warning("Failed to resolve table_from_xlsx: %s", e)
                    resolved_sections.append({"type": "paragraph", "text": f"[Table import failed: {str(e)}]"})
            elif section.get("type") == "include_pdf":
                try:
                    from core.tools_v2.pdf_injector import pdf_pages_to_sections
                    pdf_sections = pdf_pages_to_sections(
                        file_id=section.get("file_id", ""),
                        pages=section.get("pages"),
                        zoom=section.get("zoom", 2.0),
                        caption=section.get("caption"),
                        align=section.get("align", "center"),
                    )
                    resolved_sections.extend(pdf_sections)
                except Exception as e:
                    logger.warning("Failed to resolve include_pdf: %s", e)
                    resolved_sections.append({"type": "paragraph", "text": f"[PDF import failed: {str(e)}]"})
            else:
                resolved_sections.append(section)
        spec["sections"] = resolved_sections

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
        "Use for any Potomac slide deck request: pitch books, consulting reports, board presentations, "
        "investor day decks, marketing campaigns, M&A advisory, quarterly updates, or any presentation.\n\n"
        "Slide types — original:\n"
        "  title             — branded title slide (standard white or executive dark)\n"
        "  content           — bullet list or text body with title\n"
        "  two_column        — side-by-side layout with optional column headers\n"
        "  three_column      — triple-column with optional yellow header boxes\n"
        "  metrics           — large KPI numbers in Potomac yellow (up to 6 per slide)\n"
        "  process           — numbered step flow with yellow circles and connector lines\n"
        "  quote             — pull-quote with attribution on yellow-tint background\n"
        "  section_divider   — bold branded section break\n"
        "  cta               — closing slide with yellow button and contact info\n"
        "  image             — embedded image from file_id upload or base64\n\n"
        "Slide types — NEW (professional / consulting grade):\n"
        "  table             — data table with yellow headers, zebra rows, optional totals row. Fields: headers:[str], rows:[[str]], number_cols:[int], totals_row:{label,values:[str]}, caption\n"
        "  chart             — native chart. Fields: chart_type (bar/line/pie/donut/waterfall/clustered_bar/stacked_bar/area/scatter), categories:[str], values:[num], series:[{name,values}], caption\n"
        "  timeline          — milestone timeline. Fields: milestones:[{date,label,status(complete|in_progress|upcoming)}], caption\n"
        "  matrix_2x2        — BCG/strategic quadrant. Fields: x_label, y_label, quadrant_labels:[4 str], items:[{label,x(0-1),y(0-1),size}]\n"
        "  scorecard         — RAG status dashboard. Fields: items:[{metric,status(green|yellow|red),value,comment}]\n"
        "  comparison        — side-by-side vs. table. Fields: left_label, right_label, winner(left|right), rows:[{label,left,right}]\n"
        "  icon_grid         — visual feature grid. Fields: items:[{icon,title,body}], columns(2|3). Icons: shield,chart,clock,star,check,lock,globe,dollar,people,trophy,lightning,target\n"
        "  executive_summary — big headline + supporting points. Fields: headline, supporting_points:[str], call_to_action\n"
        "  image_content     — image + bullets hybrid. Fields: image_side(left|right), file_id OR image_search(keyword), bullets:[str], text\n\n"
        "Potomac brand auto-applied to every slide: Potomac logo top-right, yellow left accent bar, "
        "branded footer, Calibri font, #FEC00F/#212121 palette only.\n\n"
        "IMPORTANT: Build a complete deck — title slide, section dividers, content slides, CTA closing. "
        "Use executive_summary for the 'so what' slide. Use table for comps/data. Use chart for trends. "
        "More slides = better output. Always populate all fields for each slide type."
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
            "script":       result.script,
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
# ── PPTX FREESTYLE ────────────────────────────────────────────────────────────
# =============================================================================

GENERATE_PPTX_FREESTYLE_TOOL_DEF: Dict[str, Any] = {
    "name": "generate_pptx_freestyle",
    "description": (
        "Generate ANY Potomac-branded PowerPoint presentation by writing raw pptxgenjs v3 "
        "JavaScript code. Unlike generate_pptx (limited to 21 predefined slide templates), "
        "this tool lets you build any slide design imaginable — fully custom layouts, shapes, "
        "diagrams, infographics, mixed content, pixel-perfect positioning, and anything else "
        "the pptxgenjs v3 API supports.\n\n"
        "Use this when:\n"
        "- The user wants a unique visual design not covered by the standard templates\n"
        "- You need pixel-perfect control over every element's x/y position\n"
        "- Building complex custom diagrams (flowcharts, org charts, custom infographics)\n"
        "- Combining chart + table + text on one slide in a non-standard arrangement\n"
        "- The user references a specific design or says 'make it look like...'\n"
        "- Any request for a slide type not in generate_pptx's template list\n\n"
        "What's pre-loaded in your code environment (do NOT redefine these):\n"
        "  const pres         — pptxgenjs Presentation object (already created)\n"
        "  const engine       — layout engine: engine.W=13.333, engine.H=7.5 (inches)\n"
        "  const prim         — Potomac primitives library\n"
        "  Palette constants (hex strings — no leading #):\n"
        "    YELLOW='FEC00F'  DARK_GRAY='212121'  WHITE='FFFFFF'  BLACK='000000'\n"
        "    GRAY_60='999999'  GRAY_40='CCCCCC'  GRAY_20='DDDDDD'  GRAY_10='F0F0F0'\n"
        "    YELLOW_20='FEF7D8'  YELLOW_80='FDD251'  GREEN='22C55E'  RED='EB2F5C'\n"
        "  Font constants:\n"
        "    FONT_H='Rajdhani'   (Potomac headline — use UPPERCASE text)\n"
        "    FONT_B='Quicksand'  (Potomac body / caption)\n"
        "    FONT_M='Consolas'   (monospace)\n"
        "  Logo registry — LOGOS object, each entry has .dataUrl and .aspect:\n"
        "    LOGOS.full        — full color logo (use on light backgrounds)\n"
        "    LOGOS.full_black  — black logo (alias: LOGOS.black)\n"
        "    LOGOS.full_white  — white logo (alias: LOGOS.white, use on dark backgrounds)\n"
        "    LOGOS.icon_yellow — yellow icon only (alias: LOGOS.yellow)\n"
        "    LOGOS.icon_black  — black icon only\n"
        "    LOGOS.icon_white  — white icon only\n"
        "  function addLogo(slide, x, y, w, h, variant='full')  — place logo on slide\n"
        "  PALETTE, FONTS     — full brand objects (PALETTE.YELLOW, FONTS.HEADLINE, …)\n\n"
        "Your `code` field is just the slide-building logic. Do NOT include:\n"
        "  - require() statements (pptxgenjs is already loaded)\n"
        "  - new pptxgen() (pres is already created for you)\n"
        "  - pres.writeFile() (called automatically after your code)\n\n"
        "pptxgenjs v3 quick reference:\n"
        "  const slide = pres.addSlide();\n"
        "  slide.background = { color: DARK_GRAY };\n"
        "  slide.addText('HELLO', { x:1, y:1, w:8, h:1, fontFace:FONT_H, fontSize:40, bold:true, color:YELLOW });\n"
        "  slide.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:0.2, h:7.5, fill:{color:YELLOW} });\n"
        "  // ✅ Use addLogo() helper (recommended — handles dataUrl automatically):\n"
        "  addLogo(slide, 11.73, 0.15, 1.25, 0.5, 'full');\n"
        "  // ✅ Or access dataUrl directly (note .dataUrl — LOGOS.full is an object):\n"
        "  slide.addImage({ data:LOGOS.full.dataUrl, x:8.5, y:0.15, w:1.25, h:0.5, sizing:{type:'contain',w:1.25,h:0.5} });\n"
        "  slide.addChart(pres.charts.BAR, [{name:'S1',labels:['A','B'],values:[10,20]}], { x:1,y:2,w:8,h:4 });\n"
        "  slide.addTable([[{text:'H1',options:{bold:true,fill:{color:YELLOW}}}]], { x:0.5, y:2, w:9 });\n\n"
        "Canvas is(LAYOUT_WIDE — standard PowerPoint 16:9). Coordinates are in inches. "
        "Always keep x≥0 and y≥0. Place Potomac logo top-right on every slide: "
        "addLogo(slide, 11.73, 0.15, 1.25, 0.5, 'full') unless intentionally omitted."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Presentation title (stored in file metadata).",
            },
            "filename": {
                "type": "string",
                "description": "Output filename e.g. 'Custom_Deck.pptx'. Use underscores.",
            },
            "code": {
                "type": "string",
                "description": (
                    "Raw pptxgenjs v3 JavaScript — just the slide-building logic. "
                    "Use pres.addSlide(), slide.addText(), slide.addShape(), "
                    "slide.addChart(), slide.addImage(), slide.addTable(). "
                    "Brand constants (YELLOW, DARK_GRAY, FONT_H, FONT_B, LOGOS, addLogo) "
                    "are pre-defined. Do NOT include require(), new pptxgen(), or pres.writeFile()."
                ),
            },
        },
        "required": ["title", "code"],
    },
}


def handle_generate_pptx_freestyle(
    tool_input: Dict[str, Any],
    api_key: str = None,
    supabase_client=None,
) -> str:
    """Generate a Potomac .pptx from raw pptxgenjs JavaScript code."""
    start = time.time()
    try:
        from core.sandbox.pptx_sandbox import PptxSandbox
        from core.file_store import store_file

        title = (tool_input.get("title") or "Potomac Presentation").strip() or "Potomac Presentation"
        code  = (tool_input.get("code") or "").strip()
        if not code:
            return json.dumps({"status": "error", "error": "Missing required field: 'code'"})

        filename = _safe_filename(
            tool_input.get("filename") or f"{title}.pptx", ".pptx"
        )

        logger.info("generate_pptx_freestyle: title=%r  code_len=%d", title, len(code))

        result = PptxSandbox().generate_freestyle(
            code=code, title=title, filename=filename, timeout=120
        )
        if not result.success:
            return json.dumps({"status": "error", "error": result.error or "PptxSandbox freestyle error"})

        entry = store_file(
            data=result.data, filename=result.filename,
            file_type="pptx", tool_name="generate_pptx_freestyle",
        )
        elapsed_ms = round((time.time() - start) * 1000, 2)
        logger.info(
            "generate_pptx_freestyle ✓  %s  %.1f KB  → /files/%s/download",
            entry.filename, entry.size_kb, entry.file_id,
        )

        return json.dumps({
            "status":       "success",
            "file_id":      entry.file_id,
            "filename":     entry.filename,
            "size_kb":      entry.size_kb,
            "download_url": f"/files/{entry.file_id}/download",
            "exec_time_ms": elapsed_ms,
            "script":       result.script,
            "message": (
                f"✅ Custom presentation '{entry.filename}' generated successfully "
                f"({entry.size_kb:.1f} KB). "
                f"Download: /files/{entry.file_id}/download"
            ),
        })

    except Exception as exc:
        logger.error("handle_generate_pptx_freestyle error: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "error": str(exc)})


# =============================================================================
# ── XLSX ──────────────────────────────────────────────────────────────────────
# =============================================================================

GENERATE_TRANSFORM_XLSX_TOOL_DEF: Dict[str, Any] = {
     "name": "transform_xlsx",
     "description": (
         "Apply data cleaning and transformation operations to any uploaded Excel or CSV file. "
         "Use this instead of asking the user to clean or modify data manually.\n\n"
         "Supported operations: filter_rows, sort, rename_columns, drop_columns, add_column, "
         "fill_nulls, drop_duplicates, change_dtype, normalize_text, group_aggregate, pivot.\n\n"
         "This tool replaces 100% of manual data cleaning work. "
         "All operations are applied in order, and the result is returned as a branded Potomac xlsx file."
     ),
     "input_schema": {
         "type": "object",
         "properties": {
             "file_id": {
                 "type": "string",
                 "description": "UUID of the uploaded file to transform."
             },
             "operations": {
                 "type": "array",
                 "description": "Ordered list of operations to apply",
                 "items": {
                     "type": "object",
                     "properties": {
                         "type": {"type": "string", "description": "Operation type"}
                     },
                     "additionalProperties": True
                 }
             },
             "output_title": {
                 "type": "string",
                 "description": "Title for the output workbook"
             },
             "output_filename": {
                 "type": "string",
                 "description": "Optional custom filename for output"
             }
         },
         "required": ["file_id", "operations"]
     }
 }


GENERATE_ANALYZE_XLSX_TOOL_DEF: Dict[str, Any] = {
     "name": "analyze_xlsx",
     "description": (
         "Analyze any uploaded Excel (.xlsx) or CSV file. "
         "Returns a full structured profile including columns, data types, null counts, "
         "duplicates, numeric statistics, and sample rows.  "
         "Use this BEFORE requesting the user to send raw data or paste cell values.\n\n"
         "This tool eliminates 100% of manual inspection work. "
         "The LLM will know exactly what is inside the file without opening Excel.\n\n"
         "Always call this first when the user uploads any spreadsheet file."
     ),
     "input_schema": {
         "type": "object",
         "properties": {
             "file_id": {
                 "type": "string",
                 "description": "UUID of the uploaded file to analyze."
             }
         },
         "required": ["file_id"]
     }
 }


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


def handle_transform_xlsx(
    tool_input: Dict[str, Any],
    api_key: str = None,
    supabase_client=None,
) -> str:
    """Transform an uploaded Excel/CSV file with pipeline operations."""
    start = time.time()
    try:
        from core.sandbox.xlsx_transformer import XlsxTransformer
        from core.file_store import get_file, store_file

        file_id = tool_input.get("file_id", "").strip()
        operations = tool_input.get("operations", [])
        
        if not file_id:
            return json.dumps({"status": "error", "error": "Missing required field: 'file_id'"})
        if not isinstance(operations, list) or not operations:
            return json.dumps({"status": "error", "error": "'operations' must be a non-empty array"})

        file_entry = get_file(file_id)
        if not file_entry:
            return json.dumps({"status": "error", "error": f"File not found: {file_id}"})

        transformer = XlsxTransformer()
        result = transformer.transform(
            file_entry.data,
            operations,
            filename=file_entry.filename,
            output_title=tool_input.get("output_title")
        )

        if not result.success:
            return json.dumps({
                "status": "error",
                "error": result.error,
                "exec_time_ms": result.exec_time_ms
            })

        entry = store_file(
            data=result.data,
            filename=tool_input.get("output_filename") or result.filename,
            file_type="xlsx",
            tool_name="transform_xlsx"
        )

        logger.info("transform_xlsx ✓  file_id=%s  ops=%d  rows=%d  %.0f ms",
                    file_id, result.operations_applied, result.row_count, result.exec_time_ms)

        return json.dumps({
            "status":       "success",
            "file_id":      entry.file_id,
            "filename":     entry.filename,
            "size_kb":      entry.size_kb,
            "download_url": f"/files/{entry.file_id}/download",
            "row_count":    result.row_count,
            "operations_applied": result.operations_applied,
            "exec_time_ms": result.exec_time_ms,
            "message": (
                f"✅ File transformed successfully. "
                f"{result.operations_applied} operations applied, {result.row_count} rows output."
            ),
        })

    except Exception as exc:
        logger.error("handle_transform_xlsx error: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "error": str(exc)})


def handle_analyze_xlsx(
    tool_input: Dict[str, Any],
    api_key: str = None,
    supabase_client=None,
) -> str:
    """Analyze an uploaded Excel/CSV file and return profile."""
    start = time.time()
    try:
        from core.sandbox.xlsx_analyzer import XlsxAnalyzer
        from core.file_store import get_file

        file_id = tool_input.get("file_id", "").strip()
        if not file_id:
            return json.dumps({"status": "error", "error": "Missing required field: 'file_id'"})

        file_entry = get_file(file_id)
        if not file_entry:
            return json.dumps({"status": "error", "error": f"File not found: {file_id}"})

        analyzer = XlsxAnalyzer()
        result = analyzer.analyze(file_entry.data, filename=file_entry.filename)

        if not result.success:
            return json.dumps({
                "status": "error",
                "error": result.error,
                "exec_time_ms": result.exec_time_ms
            })

        logger.info("analyze_xlsx ✓  file_id=%s  %.0f ms", file_id, result.exec_time_ms)

        return json.dumps({
            "status":       "success",
            "file_id":      file_id,
            "filename":     file_entry.filename,
            "exec_time_ms": result.exec_time_ms,
            "profile":      result.profile,
            "message": (
                f"✅ File analyzed successfully. "
                f"{result.profile['sheet_count']} sheet(s) found."
            ),
        })

    except Exception as exc:
        logger.error("handle_analyze_xlsx error: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "error": str(exc)})


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
# ── PPTX INTELLIGENCE ─────────────────────────────────────────────────────────
# =============================================================================

ANALYZE_PPTX_TOOL_DEF: Dict[str, Any] = {
    "name": "analyze_pptx",
    "description": (
        "Read and profile any uploaded PowerPoint (.pptx) file. "
        "Returns slide count, titles, all text, table data, image locations, "
        "and a Potomac brand compliance score.\n\n"
        "Use this BEFORE revising or extending an existing deck. "
        "The LLM will know the full structure without opening PowerPoint."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the uploaded .pptx file to analyze."}
        },
        "required": ["file_id"],
    },
}

REVISE_PPTX_TOOL_DEF: Dict[str, Any] = {
    "name": "revise_pptx",
    "description": (
        "Apply targeted revisions to an existing .pptx file in milliseconds. "
        "This is the biggest time-saver: IB analysts spend 80% of their time updating numbers. "
        "This tool does a full data refresh in < 500ms.\n\n"
        "Operations:\n"
        "  find_replace   → {find, replace} — replaces all occurrences across the entire deck\n"
        "  update_slide   → {slide_index, slide:{type,...}} — replaces slide content\n"
        "  append_slides  → {slides:[...]} — append new slides to end of deck\n"
        "  delete_slide   → {slide_index} — remove a slide\n"
        "  reorder_slides → {order:[0,2,1,...]} — change slide order\n"
        "  update_table   → {slide_index, row, col, value} — update single table cell\n\n"
        "Use find_replace for quarterly updates (change Q1→Q2, update all numbers). "
        "All revisions are applied in order. Output is a new Potomac-compliant .pptx."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the existing .pptx to revise."},
            "revisions": {
                "type": "array",
                "description": "Ordered list of revision operations.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type":         {"type": "string", "description": "Operation: find_replace|update_slide|append_slides|delete_slide|reorder_slides|update_table"},
                        "find":         {"type": "string", "description": "Text to find (find_replace)."},
                        "replace":      {"type": "string", "description": "Replacement text (find_replace)."},
                        "slide_index":  {"type": "integer", "description": "0-based slide index."},
                        "slide":        {"type": "object",  "description": "Slide spec for update_slide (same format as generate_pptx slides)."},
                        "slides":       {"type": "array",   "description": "Slide specs for append_slides."},
                        "order":        {"type": "array",   "items": {"type": "integer"}, "description": "New slide order for reorder_slides."},
                        "row":          {"type": "integer", "description": "0-based row index for update_table."},
                        "col":          {"type": "integer", "description": "0-based column index for update_table."},
                        "value":        {"type": "string",  "description": "New cell value for update_table."},
                    },
                    "required": ["type"],
                },
            },
            "output_filename": {"type": "string", "description": "Output filename e.g. 'Potomac_Q2_2026_Update.pptx'."},
        },
        "required": ["file_id", "revisions"],
    },
}


def handle_analyze_pptx(
    tool_input: Dict[str, Any],
    api_key: str = None,
    supabase_client=None,
) -> str:
    """Analyze an uploaded .pptx and return structured profile."""
    start = time.time()
    try:
        from core.sandbox.pptx_analyzer import PptxAnalyzer
        from core.file_store import get_file

        file_id = tool_input.get("file_id", "").strip()
        if not file_id:
            return json.dumps({"status": "error", "error": "Missing required field: 'file_id'"})

        file_entry = get_file(file_id)
        if not file_entry:
            return json.dumps({"status": "error", "error": f"File not found: {file_id}"})

        analyzer = PptxAnalyzer()
        result   = analyzer.analyze(file_entry.data, filename=file_entry.filename)

        if not result.success:
            return json.dumps({"status": "error", "error": result.error, "exec_time_ms": result.exec_time_ms})

        logger.info("analyze_pptx ✓  file_id=%s  slides=%d  %.0f ms",
                    file_id, result.profile.get("slide_count", 0), result.exec_time_ms)

        return json.dumps({
            "status":       "success",
            "file_id":      file_id,
            "filename":     file_entry.filename,
            "exec_time_ms": result.exec_time_ms,
            "profile":      result.profile,
            "message":      f"✅ Presentation analyzed. {result.profile.get('slide_count',0)} slides found. Brand compliance: {result.profile.get('brand_compliance',{}).get('score',0)}%.",
        })

    except Exception as exc:
        logger.error("handle_analyze_pptx error: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "error": str(exc)})


def handle_revise_pptx(
    tool_input: Dict[str, Any],
    api_key: str = None,
    supabase_client=None,
) -> str:
    """Apply targeted revisions to an existing .pptx file."""
    start = time.time()
    try:
        from core.sandbox.pptx_reviser import PptxReviser
        from core.file_store import get_file, store_file

        file_id   = tool_input.get("file_id", "").strip()
        revisions = tool_input.get("revisions", [])

        if not file_id:
            return json.dumps({"status": "error", "error": "Missing required field: 'file_id'"})
        if not isinstance(revisions, list) or not revisions:
            return json.dumps({"status": "error", "error": "'revisions' must be a non-empty array"})

        file_entry = get_file(file_id)
        if not file_entry:
            return json.dumps({"status": "error", "error": f"File not found: {file_id}"})

        reviser = PptxReviser()
        result  = reviser.revise(
            file_entry.data,
            revisions,
            output_filename=tool_input.get("output_filename"),
        )

        if not result.success:
            return json.dumps({"status": "error", "error": result.error, "exec_time_ms": result.exec_time_ms})

        entry = store_file(
            data=result.data,
            filename=result.filename,
            file_type="pptx",
            tool_name="revise_pptx",
        )
        elapsed_ms = round((time.time() - start) * 1000, 2)
        logger.info("revise_pptx ✓  %s  ops=%d  replacements=%d  %.0f ms",
                    entry.filename, result.operations_applied, result.replacements_made, elapsed_ms)

        return json.dumps({
            "status":              "success",
            "file_id":             entry.file_id,
            "filename":            entry.filename,
            "size_kb":             entry.size_kb,
            "download_url":        f"/files/{entry.file_id}/download",
            "operations_applied":  result.operations_applied,
            "replacements_made":   result.replacements_made,
            "exec_time_ms":        elapsed_ms,
            "message": (
                f"✅ Presentation revised. {result.operations_applied} operations, "
                f"{result.replacements_made} text replacements. "
                f"Download: /files/{entry.file_id}/download"
            ),
        })

    except Exception as exc:
        logger.error("handle_revise_pptx error: %s", exc, exc_info=True)
        return json.dumps({"status": "error", "error": str(exc)})


# =============================================================================
# ── PPTX Template Engine (pptx-automizer) ────────────────────────────────────
# =============================================================================

GENERATE_PPTX_TEMPLATE_TOOL_DEF: Dict[str, Any] = {
    "name": "generate_pptx_template",
    "description": (
        "THE STAFF-REPLACEMENT TOOL. Update existing client decks and quarterly reports "
        "with new data in seconds — preserving every pixel of original designer formatting.\n\n"
        "Two modes:\n\n"
        "━━ UPDATE MODE (most common) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "User uploads last quarter's deck → AI injects this quarter's numbers, chart data, "
        "table rows → output is a pixel-identical updated presentation.\n"
        "  - global_replacements: change 'Q4 2025' → 'Q1 2026' across ENTIRE deck at once\n"
        "  - set_chart_data: inject new series/category data into real PowerPoint charts\n"
        "    (preserves ALL chart styling: colors, fonts, axes, legend, borders)\n"
        "  - set_table: inject new rows into real styled tables\n"
        "    (preserves: header fills, borders, column widths, fonts)\n"
        "  - swap_image: replace chart export PNGs, client logos, screenshots\n\n"
        "━━ ASSEMBLY MODE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Cherry-pick slides from one or more .pptx template files and assemble a new "
        "presentation. Each slide can have targeted modifications.\n\n"
        "WORKFLOW FOR QUARTERLY UPDATES:\n"
        "1. Call analyze_pptx(file_id) → get slide-by-slide structure + shape names\n"
        "2. Call generate_pptx_template(template_file_id, mode='update', global_replacements=[...], "
        "slide_modifications=[{slide_number, modifications:[chart/table/image ops]}])\n\n"
        "Shape names: visible in PowerPoint via ALT+F10 (Selection Pane). "
        "analyze_pptx returns all shape names per slide.\n\n"
        "Per-slide modification ops:\n"
        "  set_text            → {op, shape, text}\n"
        "  replace_tagged      → {op, shape, tags:[{find, by}], opening_tag, closing_tag}\n"
        "                        Replaces {{find}} with by. Default delimiters: {{ }}\n"
        "  replace_text        → {op, shape, replacements:[{find, replace}]}\n"
        "                        Simple literal find/replace within a specific shape\n"
        "  set_chart_data      → {op, shape, series:[{label}], categories:[{label, values:[]}]}\n"
        "  set_extended_chart_data → same, for waterfall/funnel/map/combo charts\n"
        "  set_table           → {op, shape, body:[{label, values:[]}], adjust_height, adjust_width}\n"
        "  swap_image          → {op, shape, image_file} (image_file from extra_images)\n"
        "  set_position        → {op, shape, x, y, w, h} (centimeters)\n"
        "  remove_element      → {op, shape}\n"
        "  add_element         → {op, source_file, slide_number, element_name}\n"
        "  generate_scratch    → {op, code} (pptxgenjs code using pSlide, pptxGenJs)\n\n"
        "Chart data format:\n"
        "  series:     [{label: 'Fund'}, {label: 'Benchmark'}]\n"
        "  categories: [{label: 'Jan', values: [2.1, 1.8]}, {label: 'Feb', values: [0.9, 1.1]}]\n\n"
        "Table body format:\n"
        "  body: [{label: 'row1', values: ['AAPL', '8.2%', '$1.2M']}, ...]\n\n"
        "Killer use cases:\n"
        "• Quarterly report refresh: upload Q4 deck → Q1 deck in 30 seconds\n"
        "• Fund fact sheets: inject NAV, returns, holdings into designed template\n"
        "• Client decks: update portfolio stats, benchmark data, commentary\n"
        "• RFP decks: fill prospect name, AUM, strategy details into proposal template\n"
        "• Board decks: update all KPI charts and risk table with latest data"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "template_file_id": {
                "type": "string",
                "description": (
                    "file_id of a user-uploaded .pptx file to use as the template. "
                    "For update mode: this is the deck being updated (e.g. last quarter's report). "
                    "For assembly mode: this is the source of slides to cherry-pick from."
                ),
            },
            "output_filename": {
                "type": "string",
                "description": "Output filename e.g. 'Potomac_Q1_2026_Report.pptx'.",
            },
            "mode": {
                "type": "string",
                "enum": ["assembly", "update"],
                "description": (
                    "'update' — preserve all slides, apply global text replacements + "
                    "targeted chart/table/image ops on specific slides. "
                    "Use for quarterly updates, data refreshes on existing decks.\n"
                    "'assembly' — cherry-pick slides from template file(s) and combine them. "
                    "Use when building a new presentation from designed templates."
                ),
                "default": "update",
            },
            "remove_existing_slides": {
                "type": "boolean",
                "description": (
                    "Remove slides from root template before adding new ones. "
                    "Default: true. Always true for update mode (slides are re-added from source)."
                ),
                "default": True,
            },
            "global_replacements": {
                "type": "array",
                "description": (
                    "[UPDATE MODE] Text replacements applied to ALL text shapes on ALL slides. "
                    "Use for date/period updates that appear throughout the entire deck. "
                    "Example: [{\"find\": \"Q4 2025\", \"replace\": \"Q1 2026\"}, "
                    "{\"find\": \"December 31, 2025\", \"replace\": \"March 31, 2026\"}]"
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "find":        {"type": "string", "description": "Text to find."},
                        "replace":     {"type": "string", "description": "Replacement text."},
                        "match_case":  {"type": "boolean", "description": "Case-sensitive. Default false."},
                    },
                    "required": ["find", "replace"],
                },
            },
            "slide_modifications": {
                "type": "array",
                "description": (
                    "[UPDATE MODE] Per-slide operations (chart data, table data, image swap, etc.) "
                    "applied after global_replacements. Identify slide numbers and shape names "
                    "from analyze_pptx output first."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "slide_number": {
                            "type": "integer",
                            "description": "1-based slide number (from analyze_pptx output).",
                        },
                        "modifications": {
                            "type": "array",
                            "description": "List of modification operations for this slide.",
                            "items": {"type": "object"},
                        },
                    },
                    "required": ["slide_number", "modifications"],
                },
            },
            "slides": {
                "type": "array",
                "description": (
                    "[ASSEMBLY MODE] Slides to cherry-pick from the template and include "
                    "in the output presentation. Each can have modifications."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "source_file": {
                            "type": "string",
                            "description": (
                                "Template filename to pull this slide from. "
                                "Use 'input.pptx' to refer to the file from template_file_id."
                            ),
                            "default": "input.pptx",
                        },
                        "slide_number": {
                            "type": "integer",
                            "description": "1-based slide number within source_file.",
                        },
                        "modifications": {
                            "type": "array",
                            "description": "Modifications to apply to this slide.",
                            "items": {"type": "object"},
                        },
                    },
                    "required": ["slide_number"],
                },
            },
            "extra_images": {
                "type": "array",
                "description": (
                    "Image files (uploaded via file_id) to make available for swap_image operations. "
                    "Each image is referenced by its 'name' in swap_image ops."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name":    {"type": "string", "description": "Filename used in swap_image op (e.g. 'chart.png')."},
                        "file_id": {"type": "string", "description": "file_id of the uploaded image."},
                    },
                    "required": ["name", "file_id"],
                },
            },
        },
        "required": [],
    },
}


def handle_generate_pptx_template(
    tool_input: Dict[str, Any],
    api_key: str = None,
    supabase_client=None,
) -> str:
    """
    Execute a generate_pptx_template operation via pptx-automizer Node.js subprocess.

    Resolves file_ids for the template PPTX and any extra images, builds the spec,
    runs AutomizerSandbox, stores the result, and returns a JSON response.
    """
    start = time.time()
    try:
        from core.sandbox.automizer_sandbox import AutomizerSandbox
        from core.file_store import get_file, store_file

        # ── Validate mode ──────────────────────────────────────────────────
        mode = tool_input.get("mode", "update").lower()
        if mode not in ("assembly", "update"):
            return json.dumps({"status": "error", "error": f"Invalid mode '{mode}'. Use 'assembly' or 'update'."})

        # ── Resolve template file ──────────────────────────────────────────
        template_bytes: bytes | None = None
        template_file_id = tool_input.get("template_file_id", "").strip()

        if template_file_id:
            file_entry = get_file(template_file_id)
            if not file_entry:
                return json.dumps({
                    "status": "error",
                    "error": f"Template file not found: {template_file_id}",
                })
            if not file_entry.filename.lower().endswith(".pptx"):
                return json.dumps({
                    "status": "error",
                    "error": f"Template must be a .pptx file, got: {file_entry.filename}",
                })
            template_bytes = file_entry.data
            logger.info(
                "generate_pptx_template: template=%s (%d bytes)",
                file_entry.filename, len(template_bytes),
            )

        # ── Validate: template required unless using only builtin templates ─
        if not template_file_id and mode == "update":
            return json.dumps({
                "status": "error",
                "error": "template_file_id is required for update mode.",
            })

        # ── Resolve extra images ───────────────────────────────────────────
        extra_images: dict[str, bytes] = {}
        for img_spec in tool_input.get("extra_images", []):
            img_name    = img_spec.get("name", "").strip()
            img_file_id = img_spec.get("file_id", "").strip()
            if not img_name or not img_file_id:
                continue
            img_entry = get_file(img_file_id)
            if img_entry and img_entry.data:
                extra_images[img_name] = img_entry.data
                logger.debug("Resolved extra image: %s (%d bytes)", img_name, len(img_entry.data))
            else:
                logger.warning("Extra image file_id %s not found — skipped", img_file_id)

        # ── Build output filename ──────────────────────────────────────────
        raw_filename = tool_input.get("output_filename", "").strip()
        if not raw_filename:
            raw_filename = "Potomac_Updated.pptx"
        if not raw_filename.lower().endswith(".pptx"):
            raw_filename += ".pptx"
        output_filename = re.sub(r"[^\w.\-]", "_", raw_filename)[:120]

        # ── Build spec ────────────────────────────────────────────────────
        spec: Dict[str, Any] = {
            "mode":     mode,
            "filename": output_filename,
        }

        # root_template is always "input.pptx" when template_bytes is provided
        if template_bytes is not None:
            spec["root_template"] = "input.pptx"

        if "remove_existing_slides" in tool_input:
            spec["remove_existing_slides"] = bool(tool_input["remove_existing_slides"])

        # Update-mode specific fields
        if mode == "update":
            spec["global_replacements"] = tool_input.get("global_replacements", [])
            spec["slide_modifications"] = tool_input.get("slide_modifications", [])

        # Assembly-mode specific fields
        if mode == "assembly":
            raw_slides = tool_input.get("slides", [])
            # Normalize source_file: if omitted, default to "input.pptx"
            norm_slides = []
            for s in raw_slides:
                ns = dict(s)
                if "source_file" not in ns or not ns["source_file"]:
                    ns["source_file"] = "input.pptx"
                norm_slides.append(ns)
            spec["slides"] = norm_slides

        # Media files list (names only — bytes already resolved above)
        if extra_images:
            spec["media_files"] = list(extra_images.keys())

        # ── Execute AutomizerSandbox ───────────────────────────────────────
        sandbox = AutomizerSandbox()
        result  = sandbox.run(
            spec=spec,
            template_bytes=template_bytes,
            extra_images=extra_images if extra_images else None,
            timeout=180,
        )

        if not result.success:
            return json.dumps({
                "status":   "error",
                "error":    result.error,
                "warnings": result.warnings,
                "exec_time_ms": result.exec_time_ms,
            })

        # ── Store result ───────────────────────────────────────────────────
        entry = store_file(
            data=result.data,
            filename=result.filename,
            file_type="pptx",
            tool_name="generate_pptx_template",
        )
        elapsed_ms = round((time.time() - start) * 1000, 2)

        slide_count_info = ""
        if mode == "update":
            n_global = len(spec.get("global_replacements", []))
            n_slides  = len(spec.get("slide_modifications", []))
            slide_count_info = (
                f" {n_global} global replacement(s), {n_slides} slide(s) modified."
            )
        elif mode == "assembly":
            slide_count_info = f" {len(spec.get('slides', []))} slide(s) assembled."

        warn_note = ""
        if result.warnings:
            warn_note = f" ({len(result.warnings)} non-fatal warning(s))"

        logger.info(
            "generate_pptx_template ✓  mode=%s  %s  %.1f KB  %.0f ms",
            mode, entry.filename, entry.size_kb, elapsed_ms,
        )

        return json.dumps({
            "status":        "success",
            "mode":          mode,
            "file_id":       entry.file_id,
            "filename":      entry.filename,
            "size_kb":       entry.size_kb,
            "download_url":  f"/files/{entry.file_id}/download",
            "warnings":      result.warnings,
            "exec_time_ms":  elapsed_ms,
            "message": (
                f"✅ Presentation updated via pptx-automizer.{slide_count_info}{warn_note} "
                f"Download: /files/{entry.file_id}/download"
            ),
        })

    except Exception as exc:
        logger.error("handle_generate_pptx_template error: %s", exc, exc_info=True)
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
        reg.register_tool(GENERATE_DOCX_TOOL_DEF,               handler=handle_generate_docx)
        reg.register_tool(GENERATE_PPTX_TOOL_DEF,               handler=handle_generate_pptx)
        reg.register_tool(GENERATE_PPTX_FREESTYLE_TOOL_DEF,     handler=handle_generate_pptx_freestyle)
        reg.register_tool(GENERATE_PPTX_TEMPLATE_TOOL_DEF,      handler=handle_generate_pptx_template)
        reg.register_tool(ANALYZE_PPTX_TOOL_DEF,                handler=handle_analyze_pptx)
        reg.register_tool(REVISE_PPTX_TOOL_DEF,                 handler=handle_revise_pptx)
        reg.register_tool(GENERATE_TRANSFORM_XLSX_TOOL_DEF,     handler=handle_transform_xlsx)
        reg.register_tool(GENERATE_ANALYZE_XLSX_TOOL_DEF,       handler=handle_analyze_xlsx)
        reg.register_tool(GENERATE_XLSX_TOOL_DEF,               handler=handle_generate_xlsx)
        logger.debug(
            "docx / pptx / pptx_freestyle / pptx_template / analyze_pptx / revise_pptx / "
            "transform_xlsx / analyze_xlsx / generate_xlsx registered"
        )
    except Exception as exc:
        logger.debug("ToolRegistry auto-register skipped: %s", exc)


# Register on import
_auto_register()
