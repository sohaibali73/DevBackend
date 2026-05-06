"""
Chat ↔ Studio bridge.

The /chat/agent endpoint emits tool_result blocks for tools like
`create_pptx_with_skill`, `create_word_document`, `generate_pptx`,
`generate_docx`, etc.  Those tool results contain a `file_id` referring to
core.file_store, plus a `download_url` like /files/{file_id}/download.

When a chat is operating *inside a Studio project* (i.e. the conversation_id
matches a row in studio_projects), we want every newly-generated pptx/docx
to also become a versioned artifact under that project — with bytes copied
to /data/projects/{project_id}/v{n}.{ext}.

Public API (used by api/routes/chat.py):

    materialize_tool_result(
        user_id, conversation_id, message_id, tool_name, tool_input, result
    ) → Optional[artifact_dict]

This is fire-and-forget safe — it never raises and returns None when the
conversation is not a studio project or the tool result is not a generated
file we know how to capture.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# Map: tool name → file kind ('pptx' | 'docx' | 'site')
_FILE_TOOL_MAP = {
    "create_pptx_with_skill": "pptx",
    "create_word_document":   "docx",
    "generate_pptx":          "pptx",
    "generate_pptx_freestyle":"pptx",
    "generate_pptx_template": "pptx",
    "revise_pptx":            "pptx",
    "generate_docx":          "docx",
    "generate_site":          "site",
    "revise_site":            "site",
}


def _project_for_conversation(conversation_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    if not conversation_id:
        return None
    try:
        from db.supabase_client import get_supabase
        db = get_supabase()
        res = (
            db.table("studio_projects")
            .select("id, user_id, kind, conversation_id")
            .eq("conversation_id", conversation_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception as e:
        logger.debug("project_for_conversation lookup failed: %s", e)
        return None


def _extract_file_id_and_name(result: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """
    Tool results vary in shape. Try the most common keys.
    Returns (file_id, filename) or (None, None).
    """
    if not isinstance(result, dict):
        return None, None
    fid = (
        result.get("file_id")
        or result.get("document_id")
        or result.get("presentation_id")
    )
    fname = result.get("filename") or result.get("title")
    if not fid:
        # Some tools embed the id inside a download_url like /files/{id}/download
        url = result.get("download_url") or ""
        if isinstance(url, str) and "/files/" in url:
            try:
                fid = url.split("/files/", 1)[1].split("/", 1)[0]
            except Exception:
                fid = None
    return fid, fname


def materialize_tool_result(
    *,
    user_id: str,
    conversation_id: str,
    message_id: Optional[str],
    tool_name: str,
    tool_input: Optional[Dict[str, Any]],
    result: Any,
) -> Optional[Dict[str, Any]]:
    """
    If the tool produced a pptx/docx file AND the conversation is bound to a
    studio project, copy the bytes into the project's volume dir and insert a
    studio_artifacts row. Returns the new artifact dict on success, else None.

    Never raises — logs and returns None on failure.
    """
    try:
        if tool_name not in _FILE_TOOL_MAP:
            return None
        if not isinstance(result, dict) or not result.get("success", True):
            # Some tools use status="success"/"error"
            if isinstance(result, dict) and result.get("status") == "error":
                return None
        kind = _FILE_TOOL_MAP[tool_name]

        project = _project_for_conversation(conversation_id, user_id)
        if not project:
            return None
        # Allow either matching kind or kind="chat" projects to capture both.
        if project["kind"] not in (kind, "chat"):
            logger.debug(
                "Skipping artifact capture: project kind=%s but tool produced %s",
                project["kind"], kind,
            )
            return None

        file_id, filename = _extract_file_id_and_name(result if isinstance(result, dict) else {})
        if not file_id:
            return None

        # Resolve bytes via core.file_store
        try:
            from core.file_store import get_file
        except Exception as e:
            logger.warning("Could not import core.file_store: %s", e)
            return None

        entry = get_file(file_id)
        if not entry or not entry.data:
            logger.warning("file_store miss for %s — cannot materialize artifact", file_id)
            return None

        if not filename:
            filename = entry.filename or f"output.{kind}"

        from core.studio.projects import register_artifact_from_bytes

        artifact = register_artifact_from_bytes(
            user_id=user_id,
            project_id=project["id"],
            kind=kind,
            data=entry.data,
            filename=filename,
            conversation_id=conversation_id,
            message_id=message_id,
            source_file_id=file_id,
            meta={
                "source_tool":  tool_name,
                "tool_result":  {
                    k: v for k, v in (result or {}).items()
                    if k in ("title", "subtitle", "slide_count", "page_count",
                             "doc_type", "method", "skill_used")
                },
            },
        )
        return artifact

    except Exception as e:
        logger.error("materialize_tool_result failed for %s: %s", tool_name, e, exc_info=True)
        return None
