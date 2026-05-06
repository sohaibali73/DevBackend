"""
Site Generation Tools  (core/tools_v2/site_tools.py)
=====================================================

Provides two server-side Content Studio tools:

generate_site  — Build a brand-new multi-file static website (HTML/CSS/JS)
                 from a description. Output is a zip bundle stored as a
                 versioned `site` artifact under the active Studio project.

revise_site    — Apply targeted edit ops to an existing site artifact and
                 emit a new version (Lovable-style iterative editing).

Both tools:
  - Accept fully materialised file dicts from the LLM (`files: {path: content}`).
  - Are pure-Python (no Node, no API cost beyond the Claude reasoning that
    produced the dict).
  - Persist via core.file_store so the chat hook auto-captures them as
    versioned site artifacts when the chat is bound to a Studio project.

Handler signature (both)
------------------------
    handle_generate_site(tool_input, api_key=None) -> str (JSON)
    handle_revise_site(tool_input,   api_key=None) -> str (JSON)

Result on success:
    {"status": "success", "file_id": "...", "filename": "site.zip",
     "size_kb": ..., "file_count": N,
     "download_url": "/files/<id>/download",
     "preview_hint": "Preview via studio sites preview endpoint",
     "message": "..."}

Result on failure:
    {"status": "error", "error": "<message>"}
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

from core.studio.sites import (
    build_zip_from_files,
    revise_site_files,
    read_site_files_as_dict,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Tool definitions (registered by core/tools.py)
# =============================================================================

GENERATE_SITE_TOOL_DEF: Dict[str, Any] = {
    "name": "generate_site",
    "description": (
        "Generate a complete static website (HTML / CSS / JS) as a multi-file "
        "bundle. Use this whenever the user asks to build, design, or scaffold "
        "a website, landing page, portfolio, marketing page, microsite, or web app "
        "front-end. Output is a versioned site artifact in the active Content "
        "Studio project, previewable in an iframe and publishable to a public "
        "subdomain.\n\n"
        "REQUIREMENTS:\n"
        "- The `files` dict MUST contain an `index.html` at the root.\n"
        "- All assets are relative paths (e.g. ./styles/main.css, ./scripts/app.js).\n"
        "- Use modern, accessible, mobile-first HTML5 + CSS. No external build "
        "tools. You may inline Tailwind via CDN if helpful.\n"
        "- Do NOT include server-side files (.py, .php, .rb, .sh, etc.) — they "
        "will be rejected. Static-only.\n"
        "- Keep total bundle ≤ 50 MB and ≤ 200 files."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Human-readable site title (used as the artifact name).",
            },
            "description": {
                "type": "string",
                "description": "One-sentence summary of what the site is.",
            },
            "files": {
                "type": "object",
                "description": (
                    "Map of relative file paths to their full text content. "
                    "MUST include 'index.html'. Example: "
                    '{"index.html": "<!doctype html>...", '
                    '"styles/main.css": "body{...}", '
                    '"scripts/app.js": "console.log(...)"}'
                ),
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["title", "files"],
    },
}


REVISE_SITE_TOOL_DEF: Dict[str, Any] = {
    "name": "revise_site",
    "description": (
        "Apply targeted edit operations to an existing Content Studio site "
        "artifact and produce a new version. Use this when the user asks to "
        "modify, tweak, restyle, fix, or extend an existing site they've "
        "already generated. Operations are applied in order to the file map "
        "of the previous version.\n\n"
        "Supported ops:\n"
        "  {op:'write',  path:'index.html',         content:'<!doctype html>...'}  // add or replace\n"
        "  {op:'delete', path:'old.html'}\n"
        "  {op:'rename', from:'a.css', to:'b.css'}\n\n"
        "If artifact_id is omitted, the LATEST site artifact in the conversation's "
        "Studio project is used."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "artifact_id": {
                "type": "string",
                "description": "Optional. UUID of the site artifact to revise. "
                               "If omitted, the latest site artifact in the project is used.",
            },
            "summary": {
                "type": "string",
                "description": "One-sentence description of the changes.",
            },
            "ops": {
                "type": "array",
                "description": "Ordered list of edit operations.",
                "items": {
                    "type": "object",
                    "properties": {
                        "op":      {"type": "string", "enum": ["write", "delete", "rename"]},
                        "path":    {"type": "string"},
                        "content": {"type": "string"},
                        "from":    {"type": "string"},
                        "to":      {"type": "string"},
                    },
                    "required": ["op"],
                },
            },
        },
        "required": ["ops"],
    },
}


# =============================================================================
# Handlers
# =============================================================================

def _err(msg: str) -> str:
    return json.dumps({"status": "error", "error": msg, "tool": "generate_site"})


def _safe_filename(title: str) -> str:
    base = "".join(c if (c.isalnum() or c in "._- ") else "_" for c in (title or "site")).strip()
    base = base.replace(" ", "_")[:80] or "site"
    return f"{base}.zip"


def handle_generate_site(tool_input: Dict[str, Any], api_key: Optional[str] = None) -> str:
    """
    Build a fresh site bundle from a {path: content} dict and persist it via
    core.file_store. The Studio chat hook later registers this as a versioned
    `site` artifact under the active project.
    """
    started = time.time()
    try:
        title = (tool_input.get("title") or "Untitled Site").strip()
        files = tool_input.get("files") or {}
        if not isinstance(files, dict) or not files:
            return _err("`files` must be a non-empty object of {path: content}")

        zip_bytes = build_zip_from_files(files)
        filename = _safe_filename(title)
        entry = _store_zip(zip_bytes=zip_bytes, filename=filename, tool_name="generate_site")

        elapsed_ms = int((time.time() - started) * 1000)
        return json.dumps({
            "status":        "success",
            "tool":          "generate_site",
            "file_id":       entry.file_id,
            "filename":      entry.filename,
            "title":         title,
            "description":   tool_input.get("description") or "",
            "size_kb":       entry.size_kb,
            "file_count":    sum(1 for _ in files),
            "download_url":  f"/files/{entry.file_id}/download",
            "preview_hint":  (
                "Visible in Content Studio under the active project's Sites tab."
            ),
            "exec_time_ms":  elapsed_ms,
            "message":       f"Site '{title}' built ({len(zip_bytes)/1024:.1f} KB, {len(files)} files).",
        })
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        logger.exception("generate_site failed")
        return _err(f"site generation failed: {e}")


def handle_revise_site(tool_input: Dict[str, Any], api_key: Optional[str] = None) -> str:
    """
    Apply edit ops to the latest (or specified) site artifact in the active
    Studio project. Persists the new bundle via core.file_store; the studio
    chat hook captures it as a new artifact version.

    Resolution of the source artifact:
      1) tool_input["artifact_id"] if provided
      2) latest site artifact for the conversation's project
    """
    started = time.time()
    try:
        ops = tool_input.get("ops") or []
        if not isinstance(ops, list) or not ops:
            return _err("`ops` must be a non-empty list of edit operations")

        artifact = _resolve_source_artifact(tool_input)
        if not artifact:
            return _err(
                "no source site artifact found — generate_site first or provide artifact_id"
            )

        prev_files = read_site_files_as_dict(artifact)
        new_files = revise_site_files(prev_files, ops)
        if not new_files:
            return _err("revision produced no files")

        zip_bytes = build_zip_from_files(new_files)
        title = (tool_input.get("summary") or artifact.get("filename") or "Revised Site").strip()
        filename = _safe_filename(title.replace(".zip", ""))
        entry = _store_zip(zip_bytes=zip_bytes, filename=filename, tool_name="revise_site")

        elapsed_ms = int((time.time() - started) * 1000)
        return json.dumps({
            "status":        "success",
            "tool":          "revise_site",
            "file_id":       entry.file_id,
            "filename":      entry.filename,
            "based_on_artifact_id": artifact["id"],
            "size_kb":       entry.size_kb,
            "file_count":    len(new_files),
            "ops_applied":   len(ops),
            "download_url":  f"/files/{entry.file_id}/download",
            "exec_time_ms":  elapsed_ms,
            "message":       f"Revised site ({len(ops)} ops, {len(new_files)} files).",
        })
    except ValueError as e:
        return json.dumps({"status": "error", "error": str(e), "tool": "revise_site"})
    except Exception as e:
        logger.exception("revise_site failed")
        return json.dumps({"status": "error", "error": f"revise_site failed: {e}", "tool": "revise_site"})


# =============================================================================
# Helpers
# =============================================================================

def _resolve_source_artifact(tool_input: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Find the artifact to revise. Priority: explicit artifact_id, then the
    latest site artifact for the active conversation's project.
    """
    try:
        from db.supabase_client import get_supabase
        db = get_supabase()
    except Exception:
        return None

    aid = tool_input.get("artifact_id")
    if aid:
        res = db.table("studio_artifacts").select("*").eq("id", aid).limit(1).execute()
        return res.data[0] if res.data else None

    # Try the chat-context conversation_id (set by core/tools.py when known).
    conv_id = tool_input.get("conversation_id")
    if not conv_id:
        return None

    proj = (
        db.table("studio_projects")
        .select("id")
        .eq("conversation_id", conv_id)
        .limit(1)
        .execute()
    )
    if not proj.data:
        return None
    project_id = proj.data[0]["id"]

    res = (
        db.table("studio_artifacts")
        .select("*")
        .eq("project_id", project_id)
        .eq("kind", "site")
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def _store_zip(*, zip_bytes: bytes, filename: str, tool_name: str):
    from core.file_store import store_file
    return store_file(
        data=zip_bytes,
        filename=filename,
        file_type="zip",
        tool_name=tool_name,
    )
