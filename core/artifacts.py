"""
core.artifacts
==============

YANG goal artifact storage (Phase: artifacts → workspace).

Bytes live on the Railway volume at
``$STORAGE_ROOT/yang_artifacts/{goal_id}/{artifact_id}__{safe_name}``.
Metadata lives in the ``goal_artifacts`` Supabase table (migration 033).

Public API used by :mod:`core.yang_autopilot` and the router:

* :func:`register_artifact` — copy/move a file into the goal's artifact dir,
  compute size+sha256, insert the DB row, return a frontend-ready dict.
* :func:`register_artifact_bytes` — same but for in-memory bytes.
* :func:`list_artifacts` — used by ``GET /goals/{id}/artifacts``.
* :func:`get_artifact` — used by ``GET|HEAD /goals/{id}/artifacts/{aid}``.
* :func:`gc_loop` — background task started from main lifespan; deletes bytes
  for artifacts older than 24h whose goal is in a terminal status.

Frontend contract (the dict shape returned by :func:`register_artifact`):

::

    {
      "id":         "<uuid>",
      "name":       "Q4_Report.docx",
      "mime":       "application/vnd.openxmlformats-...",
      "bytes":      48213,
      "sha256":     "ab12...",
      "url":        "/goals/{goalId}/artifacts/{id}",
      "producedBy": "tool-call-id or tool-name",
      "createdAt":  1736544000000   # ms epoch
    }
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import mimetypes
import os
import re
import shutil
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Paths / retention
# ────────────────────────────────────────────────────────────────────────────

_STORAGE_ROOT = os.getenv("STORAGE_ROOT", "/data")
_ARTIFACT_ROOT = os.path.join(_STORAGE_ROOT, "yang_artifacts")

# Bytes deleted after this many hours past the goal's terminal status. The
# metadata row stays so download returns 410 Gone, not 404.
RETENTION_HOURS = float(os.getenv("YANG_ARTIFACT_RETENTION_HOURS", "24"))

# How often the GC loop checks for stale artifacts.
GC_INTERVAL_S = float(os.getenv("YANG_ARTIFACT_GC_INTERVAL_S", "3600"))


def _db():
    return get_supabase()


async def _to_thread(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def _ensure_root() -> None:
    try:
        os.makedirs(_ARTIFACT_ROOT, exist_ok=True)
    except Exception as e:
        logger.warning("artifacts: could not create %s: %s", _ARTIFACT_ROOT, e)


def _safe_name(name: str) -> str:
    """Make a filename safe for disk + Content-Disposition headers."""
    name = (name or "artifact").strip().replace("\x00", "")
    # Drop path separators, keep extension.
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    name = name[:160] or "artifact"
    return name


def _storage_path(goal_id: str, artifact_id: str, name: str) -> str:
    safe = _safe_name(name)
    return os.path.join(_ARTIFACT_ROOT, goal_id, f"{artifact_id}__{safe}")


def _guess_mime(name: str, fallback: str = "application/octet-stream") -> str:
    mime, _ = mimetypes.guess_type(name)
    return mime or fallback


def _to_public_dict(row: dict) -> dict:
    """Translate a DB row into the frontend-facing artifact dict."""
    created_at = row.get("created_at")
    if isinstance(created_at, str):
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            created_ms = int(dt.timestamp() * 1000)
        except Exception:
            created_ms = int(time.time() * 1000)
    elif isinstance(created_at, datetime):
        created_ms = int(created_at.timestamp() * 1000)
    else:
        created_ms = int(time.time() * 1000)

    return {
        "id":         row["id"],
        "name":       row["name"],
        "mime":       row["mime"],
        "bytes":      int(row.get("bytes") or 0),
        "sha256":     row.get("sha256") or "",
        "url":        f"/goals/{row['goal_id']}/artifacts/{row['id']}",
        "producedBy": row.get("produced_by"),
        "createdAt":  created_ms,
        "deletedAt":  row.get("deleted_at"),
    }


# ────────────────────────────────────────────────────────────────────────────
# Hashing
# ────────────────────────────────────────────────────────────────────────────

def _sha256_file(path: str, chunk: int = 1 << 20) -> tuple[str, int]:
    h = hashlib.sha256()
    n = 0
    with open(path, "rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
            n += len(buf)
    return h.hexdigest(), n


def _sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


# ────────────────────────────────────────────────────────────────────────────
# Dedup helpers
# ────────────────────────────────────────────────────────────────────────────

async def _find_existing_by_sha(goal_id: str, sha256: str) -> Optional[dict]:
    def _q():
        return (
            _db()
            .table("goal_artifacts")
            .select("*")
            .eq("goal_id", goal_id)
            .eq("sha256", sha256)
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
        )
    try:
        r = await _to_thread(_q)
        return (r.data or [None])[0]
    except Exception as e:
        logger.debug("artifacts: dedup lookup failed: %s", e)
        return None


# ────────────────────────────────────────────────────────────────────────────
# Registration
# ────────────────────────────────────────────────────────────────────────────

async def register_artifact(
    *,
    goal_id: str,
    user_id: str,
    src_path: str,
    name: Optional[str] = None,
    mime: Optional[str] = None,
    produced_by: Optional[str] = None,
    move: bool = False,
) -> Optional[dict]:
    """
    Copy (or move) a file into the goal's artifact dir, hash it, register the
    DB row, and return a frontend-ready dict. Dedupes by (goal_id, sha256)
    within the same goal — re-registering an identical file is a no-op.

    Returns ``None`` on failure (logged, never raises into the agent loop).
    """
    if not src_path or not os.path.exists(src_path):
        logger.debug("artifacts: src_path missing: %r", src_path)
        return None

    _ensure_root()
    name = _safe_name(name or os.path.basename(src_path) or "artifact")
    mime = mime or _guess_mime(name)

    # Hash first (before copying) so dedup works without touching disk twice.
    try:
        sha, size = await _to_thread(_sha256_file, src_path)
    except Exception as e:
        logger.warning("artifacts: hashing failed for %s: %s", src_path, e)
        return None

    existing = await _find_existing_by_sha(goal_id, sha)
    if existing:
        return _to_public_dict(existing)

    # We need an ID up front to name the destination file.
    import uuid as _uuid
    artifact_id = str(_uuid.uuid4())
    dest = _storage_path(goal_id, artifact_id, name)
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if move:
            try:
                shutil.move(src_path, dest)
            except Exception:
                shutil.copy2(src_path, dest)
        else:
            shutil.copy2(src_path, dest)
    except Exception as e:
        logger.warning("artifacts: copy to %s failed: %s", dest, e)
        return None

    def _ins():
        return (
            _db()
            .table("goal_artifacts")
            .insert({
                "id":           artifact_id,
                "goal_id":      goal_id,
                "user_id":      user_id,
                "name":         name,
                "mime":         mime,
                "bytes":        size,
                "sha256":       sha,
                "storage_path": dest,
                "produced_by":  produced_by,
            })
            .execute()
        )
    try:
        r = await _to_thread(_ins)
        row = (r.data or [None])[0]
        if not row:
            # Insert returned nothing — best-effort cleanup of disk.
            try: os.remove(dest)
            except Exception: pass
            return None
        return _to_public_dict(row)
    except Exception as e:
        logger.warning("artifacts: insert failed: %s", e)
        try: os.remove(dest)
        except Exception: pass
        return None


async def register_artifact_bytes(
    *,
    goal_id: str,
    user_id: str,
    data: bytes,
    name: str,
    mime: Optional[str] = None,
    produced_by: Optional[str] = None,
) -> Optional[dict]:
    """Like :func:`register_artifact` but for in-memory bytes."""
    if not data:
        return None
    _ensure_root()
    sha = _sha256_bytes(data)
    existing = await _find_existing_by_sha(goal_id, sha)
    if existing:
        return _to_public_dict(existing)

    import uuid as _uuid
    artifact_id = str(_uuid.uuid4())
    name = _safe_name(name or "artifact")
    mime = mime or _guess_mime(name)
    dest = _storage_path(goal_id, artifact_id, name)
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
    except Exception as e:
        logger.warning("artifacts: write to %s failed: %s", dest, e)
        return None

    def _ins():
        return (
            _db()
            .table("goal_artifacts")
            .insert({
                "id":           artifact_id,
                "goal_id":      goal_id,
                "user_id":      user_id,
                "name":         name,
                "mime":         mime,
                "bytes":        len(data),
                "sha256":       sha,
                "storage_path": dest,
                "produced_by":  produced_by,
            })
            .execute()
        )
    try:
        r = await _to_thread(_ins)
        row = (r.data or [None])[0]
        if not row:
            try: os.remove(dest)
            except Exception: pass
            return None
        return _to_public_dict(row)
    except Exception as e:
        logger.warning("artifacts: insert failed: %s", e)
        try: os.remove(dest)
        except Exception: pass
        return None


# ────────────────────────────────────────────────────────────────────────────
# Lookup / list
# ────────────────────────────────────────────────────────────────────────────

async def list_artifacts(goal_id: str, user_id: str) -> list[dict]:
    """Used by ``GET /goals/{id}/artifacts``."""
    def _q():
        return (
            _db()
            .table("goal_artifacts")
            .select("*")
            .eq("goal_id", goal_id)
            .eq("user_id", user_id)
            .order("created_at")
            .execute()
        )
    try:
        r = await _to_thread(_q)
        return [_to_public_dict(row) for row in (r.data or [])]
    except Exception as e:
        logger.warning("artifacts: list failed: %s", e)
        return []


async def get_artifact(goal_id: str, artifact_id: str, user_id: str) -> Optional[dict]:
    """Return the raw DB row (incl. storage_path) for download/HEAD."""
    def _q():
        return (
            _db()
            .table("goal_artifacts")
            .select("*")
            .eq("id", artifact_id)
            .eq("goal_id", goal_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    try:
        r = await _to_thread(_q)
        return (r.data or [None])[0]
    except Exception as e:
        logger.warning("artifacts: get failed: %s", e)
        return None


# ────────────────────────────────────────────────────────────────────────────
# Retention GC
# ────────────────────────────────────────────────────────────────────────────

_TERMINAL_STATUSES = ("done", "failed", "cancelled")


async def _gc_once() -> None:
    """Delete bytes for artifacts whose goal is terminal and older than retention."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=RETENTION_HOURS)).isoformat()

    def _q():
        # Join via two queries — Supabase python client doesn't do FK joins
        # cleanly. Pull candidate artifacts first.
        return (
            _db()
            .table("goal_artifacts")
            .select("id, goal_id, storage_path, created_at")
            .is_("deleted_at", "null")
            .lt("created_at", cutoff)
            .limit(500)
            .execute()
        )
    try:
        r = await _to_thread(_q)
    except Exception as e:
        logger.debug("artifacts: gc query failed: %s", e)
        return
    cands = r.data or []
    if not cands:
        return

    goal_ids = list({c["goal_id"] for c in cands})

    def _qg():
        return (
            _db()
            .table("goals")
            .select("id, status, finished_at")
            .in_("id", goal_ids)
            .execute()
        )
    try:
        gr = await _to_thread(_qg)
    except Exception as e:
        logger.debug("artifacts: gc goal status query failed: %s", e)
        return
    status_by_id = {g["id"]: g for g in (gr.data or [])}

    for c in cands:
        g = status_by_id.get(c["goal_id"])
        if not g or g.get("status") not in _TERMINAL_STATUSES:
            continue
        # Goal is terminal — drop the bytes.
        path = c.get("storage_path")
        if path:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.debug("artifacts: gc unlink %s failed: %s", path, e)

        def _u(aid=c["id"]):
            return (
                _db()
                .table("goal_artifacts")
                .update({"deleted_at": datetime.now(timezone.utc).isoformat()})
                .eq("id", aid)
                .execute()
            )
        try:
            await _to_thread(_u)
        except Exception as e:
            logger.debug("artifacts: gc mark deleted failed: %s", e)


_gc_task: Optional[asyncio.Task] = None


async def _gc_loop() -> None:
    while True:
        try:
            await _gc_once()
        except Exception as e:
            logger.debug("artifacts: gc loop non-fatal: %s", e)
        await asyncio.sleep(GC_INTERVAL_S)


def start_gc_loop() -> None:
    """Idempotently start the GC loop on the current event loop."""
    global _gc_task
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return
    if _gc_task is None or _gc_task.done():
        _gc_task = loop.create_task(_gc_loop())
        logger.info("artifacts: gc loop started (retention=%sh)", RETENTION_HOURS)


async def stop_gc_loop() -> None:
    if _gc_task and not _gc_task.done():
        _gc_task.cancel()
        try:
            await _gc_task
        except Exception:
            pass


# ────────────────────────────────────────────────────────────────────────────
# Auto-wrap: extract artifact candidates from a tool result
# ────────────────────────────────────────────────────────────────────────────

def extract_artifact_candidates(tool_name: str, result: Any) -> list[dict]:
    """
    Scan a tool's return value for things that look like a produced file and
    return a list of dicts the caller can hand to :func:`register_artifact` /
    :func:`register_artifact_bytes`. Each candidate has:

      { "path": str, "name": str, "mime": str|None }              # disk file
      { "file_id": str, "name": str, "mime": str|None }           # file_store
      { "bytes": bytes, "name": str, "mime": str|None }           # raw data

    The agent loop calls this after every server-side ``tool-result`` and
    after every client-executed tool result POSTed back. We deliberately keep
    this lenient — better to register one extra artifact than to miss a real
    one.
    """
    out: list[dict] = []
    if not isinstance(result, dict):
        return out

    # 1) Top-level absolute/relative path
    p = result.get("path") or result.get("file_path")
    if isinstance(p, str) and p:
        out.append({
            "path": p,
            "name": result.get("name") or os.path.basename(p),
            "mime": result.get("mime") or result.get("mime_type"),
        })

    # 2) Top-level file_id (core.file_store)
    fid = result.get("file_id")
    if isinstance(fid, str) and fid:
        out.append({
            "file_id": fid,
            "name":    result.get("filename") or result.get("name") or "artifact",
            "mime":    result.get("mime") or result.get("mime_type"),
        })

    # 3) execute_python — `charts[]: [{file_id, filename, type}]`
    for ch in (result.get("charts") or []):
        if isinstance(ch, dict) and ch.get("file_id"):
            out.append({
                "file_id": ch["file_id"],
                "name":    ch.get("filename") or "chart.png",
                "mime":    ch.get("type") or "image/png",
            })

    # 4) execute_python — `artifacts[]: [{artifact_id, type, data, metadata}]`
    for a in (result.get("artifacts") or []):
        if not isinstance(a, dict):
            continue
        data = a.get("data")
        meta = a.get("metadata") or {}
        # If data is a /files/{id}/download URL, file_store already has it.
        if isinstance(data, str) and data.startswith("/files/") and data.endswith("/download"):
            try:
                fid2 = data.split("/")[2]
            except Exception:
                fid2 = None
            if fid2:
                out.append({
                    "file_id": fid2,
                    "name":    meta.get("filename") or "artifact",
                    "mime":    a.get("type") or meta.get("mime"),
                })

    # 5) Workspace file lists from execute_python sandbox.
    for wf in (result.get("workspace_files") or []):
        if isinstance(wf, dict) and wf.get("path"):
            out.append({
                "path": wf["path"],
                "name": os.path.basename(wf["path"]),
                "mime": None,
            })

    return out


async def register_from_candidates(
    *,
    goal_id: str,
    user_id: str,
    candidates: list[dict],
    produced_by: Optional[str],
) -> list[dict]:
    """
    Try each candidate in order. Returns the list of public-shape dicts for
    every artifact we managed to register (deduped by sha256 per goal).
    """
    out: list[dict] = []
    seen_keys: set[str] = set()

    for c in candidates:
        try:
            entry: Optional[dict] = None
            if c.get("path"):
                key = f"p:{c['path']}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                entry = await register_artifact(
                    goal_id=goal_id, user_id=user_id,
                    src_path=c["path"], name=c.get("name"), mime=c.get("mime"),
                    produced_by=produced_by, move=False,
                )
            elif c.get("file_id"):
                key = f"f:{c['file_id']}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                # Pull bytes from file_store.
                try:
                    from core.file_store import get_file_bytes
                    blob = get_file_bytes(c["file_id"])
                except Exception as e:
                    logger.debug("artifacts: file_store fetch failed: %s", e)
                    blob = None
                if blob:
                    entry = await register_artifact_bytes(
                        goal_id=goal_id, user_id=user_id,
                        data=blob, name=c.get("name") or c["file_id"],
                        mime=c.get("mime"), produced_by=produced_by,
                    )
            elif c.get("bytes"):
                entry = await register_artifact_bytes(
                    goal_id=goal_id, user_id=user_id,
                    data=c["bytes"], name=c.get("name") or "artifact",
                    mime=c.get("mime"), produced_by=produced_by,
                )
            if entry:
                out.append(entry)
        except Exception as e:
            logger.debug("artifacts: register candidate failed: %s", e)
            continue
    return out
