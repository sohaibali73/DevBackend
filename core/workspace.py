"""Per-conversation IDE workspace service.

Each conversation owns a flat namespace of named files (e.g.
`agri_cycle_rotator.py`) persisted in Supabase. The agent and the user both
read/write through the same surface — the agent via tool calls, the user via
the IDE panel in the frontend.

Supabase is the source of truth. The sandbox working directory at
`$SANDBOX_HOME/conversations/<conversation_id>/` is a derived staging copy
populated on execute; we do NOT consider the disk authoritative.

Public surface
--------------
list_files(conversation_id, user_id)               -> list[dict]
read_file(conversation_id, user_id, filename)      -> dict | None
write_file(conversation_id, user_id, filename,
           content, language, author)              -> dict
delete_file(conversation_id, user_id, filename)    -> bool
execute_file(conversation_id, user_id, filename,
             api_key=None)                         -> dict   # python/js result

All functions are synchronous (mirroring the rest of the repo's tool layer);
they may be awaited via `asyncio.to_thread` from async callers.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────── constants
VALID_LANGUAGES: set = {
    "python", "javascript", "typescript",
    "afl", "sql", "json", "yaml", "markdown", "text",
}

# Languages the workspace can execute. Anything else is read-only persistence.
EXECUTABLE_LANGUAGES: set = {"python", "javascript"}

# Filenames are flat — no directories. Allow letters, digits, underscore,
# hyphen, single dots for extensions. Disallow path separators and traversal.
_FILENAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-.]{0,127}$")

MAX_CONTENT_BYTES = 1_000_000  # 1 MB per file — generous for code, blocks abuse.


class WorkspaceError(ValueError):
    """User-facing workspace failure (bad filename, oversize content, etc.)."""


# ───────────────────────────────────────────────────────────────────── helpers
def _validate_filename(filename: str) -> str:
    if not filename or not isinstance(filename, str):
        raise WorkspaceError("filename is required")
    name = filename.strip()
    if not _FILENAME_RE.match(name):
        raise WorkspaceError(
            f"invalid filename {filename!r}; allowed: A-Z a-z 0-9 _ - . "
            f"(no path separators, max 128 chars)"
        )
    if name in {".", ".."} or ".." in name or name.startswith("."):
        raise WorkspaceError(f"invalid filename {filename!r}; no traversal allowed")
    return name


def _infer_language(filename: str, explicit: Optional[str]) -> str:
    if explicit:
        lang = explicit.strip().lower()
        if lang in VALID_LANGUAGES:
            return lang
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "py": "python",
        "js": "javascript",
        "mjs": "javascript",
        "ts": "typescript",
        "tsx": "typescript",
        "afl": "afl",
        "sql": "sql",
        "json": "json",
        "yaml": "yaml",
        "yml": "yaml",
        "md": "markdown",
        "txt": "text",
    }.get(ext, "text")


def _row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id":               row.get("id"),
        "conversation_id":  row.get("conversation_id"),
        "filename":         row.get("filename"),
        "language":         row.get("language"),
        "content":          row.get("content", ""),
        "version":          row.get("version", 1),
        "last_author":      row.get("last_author", "agent"),
        "created_at":       row.get("created_at"),
        "updated_at":       row.get("updated_at"),
        "size_bytes":       len(row.get("content") or ""),
    }


def _row_to_summary(row: Dict[str, Any]) -> Dict[str, Any]:
    """Listing entry — no content, just metadata."""
    return {
        "id":               row.get("id"),
        "filename":         row.get("filename"),
        "language":         row.get("language"),
        "version":          row.get("version", 1),
        "last_author":      row.get("last_author", "agent"),
        "created_at":       row.get("created_at"),
        "updated_at":       row.get("updated_at"),
        "size_bytes":       len(row.get("content") or ""),
    }


def _sandbox_dir_for(conversation_id: str) -> Path:
    """Resolve the on-disk staging dir the Python sandbox uses for this conv."""
    try:
        from core.sandbox.db import _SANDBOX_HOME as _SBHOME
        base = Path(_SBHOME) / "conversations" / str(conversation_id)
    except Exception:
        import os as _os
        base = Path(_os.environ.get(
            "SANDBOX_DATA_DIR", str(Path.home() / ".sandbox")
        )) / "conversations" / str(conversation_id)
    base.mkdir(parents=True, exist_ok=True)
    return base


# ─────────────────────────────────────── file-mirror after execution
# Files the running script writes (output.csv, plot_data.json, scratch.py)
# should appear in the IDE panel so the user can inspect them. The sandbox
# already drops them in the per-conversation dir; this helper mirrors any
# NEW or MODIFIED text file into the workspace_files DB after a run.
#
# Binary files (.png, .pdf, .xlsx, .pkl, ...) are intentionally skipped —
# the synchronous main-sandbox path captures those as downloadable
# artifacts. Mirroring them here would just pollute the IDE tab bar.

# Extensions we'll mirror into the workspace. Anything not in this set is
# skipped (binary, archives, compiled artifacts, screenshots).
_TEXT_EXTENSIONS: set = {
    "py", "js", "mjs", "cjs", "ts", "tsx", "jsx",
    "json", "yaml", "yml", "toml", "ini", "cfg", "env",
    "csv", "tsv", "txt", "md", "markdown", "log",
    "html", "htm", "xml", "css", "scss", "sass",
    "sql", "afl", "sh", "ps1", "rst",
}

# Files matching these prefixes are noise (caches, hidden, lock files).
_SKIP_PREFIXES: tuple = ("__", ".")
_SKIP_NAMES: set = {"__pycache__", ".DS_Store"}
# Hard size cap for mirrored content — IDE wants source-sized files, not data dumps.
_MIRROR_MAX_BYTES = 500_000


def _is_mirrorable(path: Path) -> bool:
    """Return True iff ``path`` is a text file the IDE should surface."""
    if not path.is_file():
        return False
    name = path.name
    if name in _SKIP_NAMES:
        return False
    if name.startswith(_SKIP_PREFIXES):
        return False
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in _TEXT_EXTENSIONS:
        return False
    try:
        if path.stat().st_size > _MIRROR_MAX_BYTES:
            return False
    except OSError:
        return False
    return True


def snapshot_sandbox_mtimes(conversation_id: str) -> Dict[str, float]:
    """Snapshot mtimes of every file currently in the per-conv sandbox dir.

    Call BEFORE executing user code; pair with ``mirror_new_files`` after.
    Returns a dict ``{filename: mtime}`` — files not in the snapshot, OR
    with a later mtime, are considered "newly written" by the run.
    """
    out: Dict[str, float] = {}
    try:
        d = _sandbox_dir_for(conversation_id)
        for entry in d.iterdir():
            if not entry.is_file():
                continue
            try:
                out[entry.name] = entry.stat().st_mtime
            except OSError:
                continue
    except Exception as e:
        logger.debug("snapshot_sandbox_mtimes failed: %s", e)
    return out


def mirror_new_files(
    conversation_id: str,
    user_id: str,
    before: Dict[str, float],
    *,
    skip_filenames: Optional[set] = None,
) -> List[str]:
    """Mirror any files written by the just-finished execution into the
    workspace_files table.

    Compares current mtimes against ``before`` (from
    ``snapshot_sandbox_mtimes``). Anything missing from ``before`` OR with
    a newer mtime is upserted. ``skip_filenames`` lets the caller exclude
    the file that was just executed (otherwise re-runs would flip
    ``last_author`` from 'user' to 'system' every time).

    Best-effort: per-file failures are logged and skipped; the caller's
    response is never broken by a mirror error.

    Returns the list of filenames that were mirrored.
    """
    if not conversation_id or not user_id:
        return []
    mirrored: List[str] = []
    skip = skip_filenames or set()
    try:
        d = _sandbox_dir_for(conversation_id)
    except Exception:
        return []

    for entry in d.iterdir():
        if not entry.is_file():
            continue
        name = entry.name
        if name in skip:
            continue
        if not _is_mirrorable(entry):
            continue
        try:
            mt = entry.stat().st_mtime
        except OSError:
            continue
        prior = before.get(name)
        if prior is not None and mt <= prior:
            continue  # unchanged
        # Read content; skip if it suddenly grew or isn't UTF-decodable.
        try:
            content = entry.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if len(content) > _MIRROR_MAX_BYTES:
            continue
        try:
            write_file(
                conversation_id, user_id, name, content,
                language=None, author="system",
            )
            mirrored.append(name)
        except Exception as e:
            logger.debug("mirror %s skipped: %s", name, e)
    return mirrored


# ─────────────────────────────────────────────────────────────────── public API
def list_files(conversation_id: str, user_id: str) -> List[Dict[str, Any]]:
    """All files in this conversation's workspace, newest-updated first."""
    db = get_supabase()
    resp = (
        db.table("workspace_files")
        .select("id, filename, language, version, last_author, created_at, updated_at, content")
        .eq("conversation_id", conversation_id)
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )
    rows = resp.data or []
    return [_row_to_summary(r) for r in rows]


def read_file(
    conversation_id: str,
    user_id: str,
    filename: str,
) -> Optional[Dict[str, Any]]:
    """Return one file with its full content, or None if it doesn't exist."""
    name = _validate_filename(filename)
    db = get_supabase()
    resp = (
        db.table("workspace_files")
        .select("*")
        .eq("conversation_id", conversation_id)
        .eq("user_id", user_id)
        .eq("filename", name)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if not rows:
        return None
    return _row_to_dict(rows[0])


def write_file(
    conversation_id: str,
    user_id: str,
    filename: str,
    content: str,
    language: Optional[str] = None,
    author: str = "agent",
) -> Dict[str, Any]:
    """Insert or update a file. Bumps `version` on every write.

    Returns the persisted row. Raises WorkspaceError on validation failure.
    """
    name = _validate_filename(filename)
    if content is None:
        content = ""
    if not isinstance(content, str):
        raise WorkspaceError("content must be a string")
    if len(content) > MAX_CONTENT_BYTES:
        raise WorkspaceError(
            f"content too large ({len(content)} bytes); max {MAX_CONTENT_BYTES}"
        )
    if author not in {"agent", "user", "system"}:
        author = "agent"
    lang = _infer_language(name, language)

    db = get_supabase()
    existing = (
        db.table("workspace_files")
        .select("id, version")
        .eq("conversation_id", conversation_id)
        .eq("user_id", user_id)
        .eq("filename", name)
        .limit(1)
        .execute()
    )
    if existing.data:
        row_id = existing.data[0]["id"]
        new_version = int(existing.data[0].get("version", 1)) + 1
        upd = (
            db.table("workspace_files")
            .update({
                "content": content,
                "language": lang,
                "version": new_version,
                "last_author": author,
            })
            .eq("id", row_id)
            .execute()
        )
        row = (upd.data or [{}])[0]
    else:
        ins = (
            db.table("workspace_files")
            .insert({
                "conversation_id": conversation_id,
                "user_id": user_id,
                "filename": name,
                "language": lang,
                "content": content,
                "version": 1,
                "last_author": author,
            })
            .execute()
        )
        row = (ins.data or [{}])[0]

    # Best-effort: also drop a copy onto the sandbox staging dir so a follow-up
    # execute_python (anonymous code) can import it. Source of truth stays DB.
    try:
        path = _sandbox_dir_for(conversation_id) / name
        path.write_text(content, encoding="utf-8")
    except Exception as e:
        logger.debug("workspace stage to disk failed (non-fatal): %s", e)

    return _row_to_dict(row)


def delete_file(
    conversation_id: str,
    user_id: str,
    filename: str,
) -> bool:
    """Delete a file. Returns True if a row was removed, False if not found."""
    name = _validate_filename(filename)
    db = get_supabase()
    resp = (
        db.table("workspace_files")
        .delete()
        .eq("conversation_id", conversation_id)
        .eq("user_id", user_id)
        .eq("filename", name)
        .execute()
    )
    removed = bool(resp.data)
    # Also remove the staged copy if present.
    try:
        p = _sandbox_dir_for(conversation_id) / name
        if p.exists():
            p.unlink()
    except Exception as e:
        logger.debug("workspace unstage failed (non-fatal): %s", e)
    return removed


# ──────────────────────────────────────────────────────────────────── execution
def execute_file(
    conversation_id: str,
    user_id: str,
    filename: str,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a Python or JavaScript file from the workspace and return result.

    Output shape matches the existing execute_python tool so the frontend's
    console renderer can reuse one path. Streaming is NOT done here — for that
    use the SSE endpoint in api/routes/workspace.py.
    """
    file_row = read_file(conversation_id, user_id, filename)
    if file_row is None:
        return {
            "success": False,
            "error": f"file {filename!r} not found in this conversation's workspace",
        }

    lang = (file_row.get("language") or "python").lower()
    if lang not in EXECUTABLE_LANGUAGES:
        return {
            "success": False,
            "error": (
                f"language {lang!r} is not executable here; "
                f"only {sorted(EXECUTABLE_LANGUAGES)} are run."
            ),
        }

    content = file_row.get("content") or ""

    # Make sure the on-disk staged copy is up to date with what we're about to
    # run (in case someone wrote via the API and the inline write_file disk
    # write was skipped). Then call the existing sandbox.
    try:
        (_sandbox_dir_for(conversation_id) / file_row["filename"]).write_text(
            content, encoding="utf-8"
        )
    except Exception as e:
        logger.debug("workspace exec stage failed (non-fatal): %s", e)

    # Snapshot the sandbox dir BEFORE running so we can detect which files
    # the script wrote and mirror them into the workspace_files table.
    before = snapshot_sandbox_mtimes(conversation_id)

    if lang == "python":
        result = _execute_python(content, conversation_id=conversation_id, filename=filename)
    else:
        result = _execute_javascript(content, conversation_id=conversation_id, filename=filename)

    # Mirror any new text files the script wrote. Skip the file that was
    # executed — its `last_author` should stay whatever wrote it (agent / user).
    try:
        mirrored = mirror_new_files(
            conversation_id, user_id, before,
            skip_filenames={file_row["filename"]},
        )
        if mirrored:
            result["workspace_files_changed"] = mirrored
    except Exception as e:
        logger.debug("post-exec file mirror failed: %s", e)
    return result


def _execute_python(code: str, *, conversation_id: str, filename: str) -> Dict[str, Any]:
    """Run via the existing PythonSandbox; thread conversation_id as session_id."""
    try:
        from core.tools import execute_python as _ep
    except Exception as e:
        return {"success": False, "error": f"sandbox unavailable: {e}"}
    try:
        result = _ep(
            code=code,
            description=f"Run workspace file {filename}",
            session_id=conversation_id,
        )
    except TypeError:
        # Older signature without session_id — degrade gracefully.
        result = _ep(code=code, description=f"Run workspace file {filename}")
    if isinstance(result, dict):
        result.setdefault("filename", filename)
    return result


def _execute_javascript(
    code: str,
    *,
    conversation_id: str,
    filename: str,
) -> Dict[str, Any]:
    """Run JS via node in the sandbox dir. Stdout/stderr captured.

    Kept intentionally minimal — no NPM, no network. The sandbox dir is
    persistent per conversation so the file can `require('./other.js')` from
    sibling workspace files (they're already staged on disk).
    """
    import subprocess
    import shutil

    node = shutil.which("node")
    if not node:
        return {
            "success": False,
            "error": "node is not installed on this host; JavaScript execution unavailable.",
        }
    work_dir = _sandbox_dir_for(conversation_id)
    file_path = work_dir / filename
    file_path.write_text(code, encoding="utf-8")
    try:
        proc = subprocess.run(
            [node, str(file_path)],
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "success": proc.returncode == 0,
            "filename": filename,
            "output": proc.stdout,
            "error": proc.stderr if proc.returncode != 0 else "",
            "exit_code": proc.returncode,
            "language": "javascript",
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "filename": filename,
            "error": "execution timed out after 30s",
            "language": "javascript",
        }
    except Exception as e:
        return {
            "success": False,
            "filename": filename,
            "error": f"node execution failed: {e}",
            "language": "javascript",
        }
