"""
Document Generation Tools  (core/tools_v2/document_tools.py)
=============================================================
Provides the ``generate_docx`` tool: a server-side Potomac DOCX generator
that runs entirely on the Railway server using Node.js + the ``docx`` npm
package.  **No Claude Skills container is used.**

Differences from the Claude-Skill path
---------------------------------------
- ``invoke_skill({skill_slug: "potomac-docx-skill", ...})``
  → Sends the task to Anthropic's Claude code-execution container.
    Costs API tokens.  Requires an active API key.  Takes 20-60 s.

- ``generate_docx({title, sections, ...})``
  → Runs locally on the Railway server using Node.js.
    Zero API cost.  Logos mounted from ClaudeSkills/potomac-docx/assets/.
    Takes 3-10 s (after first npm cache warm-up).
    Output stored via file_store → Railway volume + Supabase.

Tool schema
-----------
See GENERATE_DOCX_TOOL_DEF below for the full JSON-schema description
that is injected into the Claude API.

Handler
-------
``handle_generate_docx(tool_input, api_key=None)``
    Synchronous handler compatible with core/tools.py's dispatch table.
    Internally calls DocxSandbox.generate() (subprocess-based, blocking).
    Returns a JSON string with file_id + download_url on success.

Auto-registration
-----------------
When this module is imported, it calls ``_auto_register()`` which
registers the tool + handler in the ToolRegistry so that any code
path going through ToolRegistry.handle_tool_call() is covered.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)

# =============================================================================
# Tool definition (registered in both TOOL_DEFINITIONS and ToolRegistry)
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
        "- Dividers, spacers, page breaks\n"
        "- Standard Potomac disclosure block (auto-appended unless disabled)\n"
        "- Page-number footer\n\n"
        "IMPORTANT: Populate `sections` with ALL the document content. "
        "Be thorough — the AI writes the content; the tool formats and saves it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": (
                    "Output filename, e.g. 'Potomac_Q1_Commentary.docx'. "
                    "Use underscores, no spaces. Defaults to 'output.docx'."
                ),
            },
            "title": {
                "type": "string",
                "description": "Main document title shown on the title page (ALL CAPS recommended).",
            },
            "subtitle": {
                "type": "string",
                "description": "Optional subtitle shown below the title.",
            },
            "date": {
                "type": "string",
                "description": "Document date, e.g. 'April 2026' or 'Q1 2026'.",
            },
            "author": {
                "type": "string",
                "description": "Author or team name, e.g. 'Potomac Research Team'.",
            },
            "logo_variant": {
                "type": "string",
                "enum": ["standard", "black", "white"],
                "default": "standard",
                "description": (
                    "Which Potomac logo to use in the header: "
                    "'standard' (color, default), 'black', or 'white'."
                ),
            },
            "header_line_color": {
                "type": "string",
                "enum": ["yellow", "dark"],
                "default": "yellow",
                "description": "Color of the underline beneath the header logo.",
            },
            "footer_text": {
                "type": "string",
                "description": (
                    "Custom text for the footer left side. "
                    "Default: 'Potomac  |  Built to Conquer Risk®'."
                ),
            },
            "sections": {
                "type": "array",
                "description": (
                    "Ordered list of content blocks that make up the document body. "
                    "Each item has a 'type' field plus type-specific fields."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": [
                                "heading",
                                "paragraph",
                                "bullets",
                                "numbered",
                                "table",
                                "image",
                                "divider",
                                "spacer",
                                "page_break",
                            ],
                            "description": (
                                "Content block type:\n"
                                "  heading     — section heading (level 1/2/3)\n"
                                "  paragraph   — body text, optionally with mixed bold/italic runs\n"
                                "  bullets     — unordered bullet list\n"
                                "  numbered    — ordered numbered list\n"
                                "  table       — data table with yellow header row\n"
                                "  image       — embedded image from user upload (use file_id) or inline base64\n"
                                "  divider     — horizontal yellow rule\n"
                                "  spacer      — blank vertical space\n"
                                "  page_break  — force a new page"
                            ),
                        },
                        "level": {
                            "type": "integer",
                            "enum": [1, 2, 3],
                            "description": "Heading level (1=H1, 2=H2, 3=H3). Only for type='heading'.",
                        },
                        "text": {
                            "type": "string",
                            "description": "Text content. For type='heading' or type='paragraph' (plain).",
                        },
                        "runs": {
                            "type": "array",
                            "description": (
                                "Mixed-format text runs for type='paragraph'. "
                                "Use instead of 'text' when you need bold/italic within a paragraph."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "text":    {"type": "string"},
                                    "bold":    {"type": "boolean", "default": False},
                                    "italics": {"type": "boolean", "default": False},
                                    "color":   {"type": "string", "description": "Hex color without #, e.g. '212121'"},
                                },
                                "required": ["text"],
                            },
                        },
                        "items": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List items. For type='bullets' or type='numbered'.",
                        },
                        "headers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Column header labels. For type='table'.",
                        },
                        "rows": {
                            "type": "array",
                            "description": (
                                "Table data rows. Each row is an array of cell strings. "
                                "For type='table'."
                            ),
                            "items": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "col_widths": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": (
                                "Optional column widths in DXA (1440 DXA = 1 inch). "
                                "Auto-calculated if omitted. For type='table'."
                            ),
                        },
                        "size": {
                            "type": "integer",
                            "description": "Spacer height in twips (240 = ~1 line). For type='spacer'.",
                        },
                        "color": {
                            "type": "string",
                            "description": "Hex color without # for divider line. Default: 'FEC00F' (yellow). For type='divider'.",
                        },
                    },
                    "required": ["type"],
                },
            },
            "include_disclosure": {
                "type": "boolean",
                "default": True,
                "description": (
                    "Append the standard Potomac disclosure block at the end of the document. "
                    "Set to false for internal memos or non-client-facing documents."
                ),
            },
            "disclosure_text": {
                "type": "string",
                "description": (
                    "Override the default disclosure text. "
                    "Only used when include_disclosure is true."
                ),
            },
        },
        "required": ["title", "sections"],
    },
}


# =============================================================================
# Synchronous handler (compatible with core/tools.py dispatch table)
# =============================================================================

def handle_generate_docx(
    tool_input: Dict[str, Any],
    api_key: str = None,
    supabase_client=None,
) -> str:
    """
    Generate a Potomac-branded .docx and return a JSON result string.

    Compatible with the synchronous ``handle_tool_call()`` dispatch table in
    ``core/tools.py``.  Uses ``subprocess.run`` internally so it does not
    require an asyncio event loop.

    Parameters
    ----------
    tool_input : dict
        The tool call input matching ``GENERATE_DOCX_TOOL_DEF``.
    api_key : str, optional
        Not used — kept for signature compatibility.
    supabase_client : optional
        Not used — kept for signature compatibility.

    Returns
    -------
    str
        JSON string.  On success:
            {
                "status": "success",
                "file_id": "<uuid>",
                "filename": "...",
                "size_kb": 42.3,
                "download_url": "/files/<uuid>/download",
                "exec_time_ms": 4200
            }
        On failure:
            {"status": "error", "error": "<message>"}
    """
    start = time.time()

    try:
        from core.sandbox.docx_sandbox import DocxSandbox
        from core.file_store import store_file

        # ── Validate minimum required fields ──────────────────────────────
        title    = tool_input.get("title", "").strip()
        sections = tool_input.get("sections", [])

        if not title:
            return json.dumps({"status": "error", "error": "Missing required field: 'title'"})
        if not isinstance(sections, list):
            return json.dumps({"status": "error", "error": "'sections' must be an array"})

        # ── Build the spec (pass through all recognised fields) ───────────
        spec: Dict[str, Any] = {
            "title":              title,
            "sections":           sections,
            "filename":           _safe_filename(tool_input.get("filename") or f"{title}.docx"),
            "subtitle":           tool_input.get("subtitle", ""),
            "date":               tool_input.get("date", ""),
            "author":             tool_input.get("author", ""),
            "logo_variant":       tool_input.get("logo_variant", "standard"),
            "header_line_color":  tool_input.get("header_line_color", "yellow"),
            "footer_text":        tool_input.get("footer_text", ""),
            "include_disclosure": tool_input.get("include_disclosure", True),
            "disclosure_text":    tool_input.get("disclosure_text", ""),
        }

        logger.info(
            "generate_docx: title=%r  sections=%d  filename=%r",
            spec["title"], len(spec["sections"]), spec["filename"],
        )

        # ── Run the sandbox ───────────────────────────────────────────────
        sandbox = DocxSandbox()
        result  = sandbox.generate(spec, timeout=120)

        if not result.success:
            logger.error("DocxSandbox failed: %s", result.error)
            return json.dumps({"status": "error", "error": result.error or "Unknown DocxSandbox error"})

        # ── Persist via file_store (Railway volume + Supabase) ────────────
        entry = store_file(
            data      = result.data,
            filename  = result.filename,
            file_type = "docx",
            tool_name = "generate_docx",
        )

        elapsed_ms = round((time.time() - start) * 1000, 2)
        logger.info(
            "generate_docx ✓  %s  %.1f KB  %.0f ms  → /files/%s/download",
            entry.filename, entry.size_kb, elapsed_ms, entry.file_id,
        )

        return json.dumps({
            "status":        "success",
            "file_id":       entry.file_id,
            "filename":      entry.filename,
            "size_kb":       entry.size_kb,
            "download_url":  f"/files/{entry.file_id}/download",
            "exec_time_ms":  elapsed_ms,
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
# Helpers
# =============================================================================

def _safe_filename(name: str) -> str:
    """Sanitise a filename — keep alphanumerics, underscores, hyphens, dots."""
    import re
    safe = re.sub(r"[^\w.\-]", "_", name)
    if not safe.lower().endswith(".docx"):
        safe += ".docx"
    return safe[:120]


# =============================================================================
# Auto-registration in ToolRegistry
# =============================================================================

def _auto_register() -> None:
    """
    Register ``generate_docx`` in the ToolRegistry at import time.

    This covers the code paths that go through
    ``core/tools_v2/registry.py::ToolRegistry.handle_tool_call()``.
    The ``core/tools.py`` dispatch table is handled separately via the
    ``elif tool_name == "generate_docx"`` branch added to ``handle_tool_call``.
    """
    try:
        from core.tools_v2.registry import ToolRegistry
        # Get the singleton (or create one)
        _reg = ToolRegistry()
        _reg.register_tool(GENERATE_DOCX_TOOL_DEF, handler=handle_generate_docx)
        logger.debug("generate_docx registered in ToolRegistry")
    except Exception as exc:
        logger.debug("ToolRegistry auto-register skipped: %s", exc)


# Register on import
_auto_register()
