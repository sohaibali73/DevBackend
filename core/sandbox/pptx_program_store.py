"""
PPTX Program Store
==================
Persistent "source code" of every generated presentation so the agent can
edit / revert / re-render without starting from scratch.

Persistence
-----------
- Supabase table ``pptx_programs``          → program rows  (source of truth)
- Supabase table ``pptx_program_versions``  → append-only version history
- Railway volume ``/data/pptx_programs/{id}/`` → local cache + rendered artifacts
    ├── program.json          mirror of latest program
    ├── versions/v{n}.json    per-version snapshot
    └── renders/v{n}.pptx     rendered file per version

Edit patches are JSON-patch-like operations:
    {"op":"update", "slide":1, "path":"data.title", "value":"New title"}
    {"op":"insert", "index":3, "slide": {...}}
    {"op":"delete", "slide":5}
    {"op":"reorder","from":2, "to":0}
    {"op":"set_canvas", "canvas": {"preset":"standard"}}
    {"op":"set_title", "title":"..."}
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "/data"))
_PROGRAMS_ROOT = _STORAGE_ROOT / "pptx_programs"


@dataclass
class ProgramRecord:
    id: str
    user_id: str
    title: str
    canvas: Dict[str, Any]
    program: Dict[str, Any]
    version: int = 1
    file_id: Optional[str] = None
    last_render_sha: Optional[str] = None
    asset_snapshot: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _db():
    try:
        from db.supabase_client import get_supabase
        return get_supabase()
    except Exception as exc:
        logger.warning("Supabase unavailable for pptx_programs: %s", exc)
        return None


def _program_dir(program_id: str) -> Path:
    p = _PROGRAMS_ROOT / program_id
    p.mkdir(parents=True, exist_ok=True)
    (p / "versions").mkdir(exist_ok=True)
    (p / "renders").mkdir(exist_ok=True)
    return p


def _hash_program(program: Dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(program, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Save / load
# ─────────────────────────────────────────────────────────────────────────────

def save_program(
    *, user_id: str, title: str, canvas: Dict[str, Any],
    program: Dict[str, Any], file_id: Optional[str] = None,
    asset_snapshot: Optional[Dict[str, Any]] = None,
    program_id: Optional[str] = None,
) -> ProgramRecord:
    """
    Create (if program_id is None) or update a program.  Writes a new version
    row every time.  Program stored on Railway volume + Supabase.
    """
    program_id = program_id or str(uuid.uuid4())
    snap = asset_snapshot or {}

    rec = ProgramRecord(
        id=program_id, user_id=user_id, title=title, canvas=canvas,
        program=program, file_id=file_id, asset_snapshot=snap,
        last_render_sha=_hash_program(program),
    )

    # ── Volume ──────────────────────────────────────────────────────────────
    try:
        pdir = _program_dir(program_id)
        (pdir / "program.json").write_text(
            json.dumps({
                "id": program_id, "user_id": user_id, "title": title,
                "canvas": canvas, "program": program,
                "file_id": file_id, "asset_snapshot": snap,
                "updated_at": rec.updated_at,
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("Volume write failed for %s: %s", program_id, exc)

    # ── Supabase: upsert program + append version ──────────────────────────
    db = _db()
    if db is None:
        return rec

    try:
        # Check existing version
        existing = (
            db.table("pptx_programs")
            .select("version")
            .eq("id", program_id)
            .execute()
        )
        version = 1
        if existing.data:
            version = int(existing.data[0].get("version") or 1) + 1
        rec.version = version

        payload = {
            "id":              program_id,
            "user_id":         user_id,
            "title":           title,
            "canvas":          canvas,
            "program":         program,
            "asset_snapshot":  snap,
            "version":         version,
            "file_id":         file_id,
            "last_render_sha": rec.last_render_sha,
        }
        db.table("pptx_programs").upsert(payload, on_conflict="id").execute()

        # Append to versions table
        db.table("pptx_program_versions").insert({
            "program_id": program_id,
            "version":    version,
            "program":    program,
            "title":      title,
            "canvas":     canvas,
        }).execute()

        # Write version snapshot to volume
        try:
            pdir = _program_dir(program_id)
            (pdir / "versions" / f"v{version}.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass
    except Exception as exc:
        logger.warning("Supabase program upsert failed: %s", exc)

    return rec


def load_program(program_id: str, *, user_id: Optional[str] = None) -> Optional[ProgramRecord]:
    """
    Load a program by id.  Tries volume first, falls back to Supabase.
    """
    # Volume
    pdir = _PROGRAMS_ROOT / program_id
    volume_file = pdir / "program.json"
    if volume_file.exists():
        try:
            data = json.loads(volume_file.read_text(encoding="utf-8"))
            if user_id and data.get("user_id") and data["user_id"] != user_id:
                pass  # fall through to Supabase check for authz
            else:
                return ProgramRecord(
                    id=data["id"],
                    user_id=data.get("user_id") or "",
                    title=data.get("title") or "",
                    canvas=data.get("canvas") or {},
                    program=data.get("program") or {},
                    file_id=data.get("file_id"),
                    asset_snapshot=data.get("asset_snapshot") or {},
                    updated_at=data.get("updated_at") or time.time(),
                )
        except Exception:
            pass

    # Supabase fallback
    db = _db()
    if db is None:
        return None
    try:
        q = db.table("pptx_programs").select("*").eq("id", program_id)
        if user_id:
            q = q.eq("user_id", user_id)
        res = q.execute()
        if not res.data:
            return None
        row = res.data[0]
        rec = ProgramRecord(
            id=row["id"],
            user_id=row["user_id"],
            title=row.get("title") or "",
            canvas=row.get("canvas") or {},
            program=row.get("program") or {},
            version=int(row.get("version") or 1),
            file_id=row.get("file_id"),
            last_render_sha=row.get("last_render_sha"),
            asset_snapshot=row.get("asset_snapshot") or {},
        )
        # Warm volume cache
        try:
            pdir = _program_dir(program_id)
            (pdir / "program.json").write_text(
                json.dumps({
                    "id": rec.id, "user_id": rec.user_id, "title": rec.title,
                    "canvas": rec.canvas, "program": rec.program,
                    "file_id": rec.file_id, "asset_snapshot": rec.asset_snapshot,
                    "updated_at": rec.updated_at,
                }, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass
        return rec
    except Exception as exc:
        logger.warning("load_program failed: %s", exc)
        return None


def list_programs(*, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    db = _db()
    if db is None:
        return []
    try:
        res = (
            db.table("pptx_programs")
            .select("id,title,canvas,version,file_id,created_at,updated_at")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        logger.warning("list_programs failed: %s", exc)
        return []


def list_versions(*, program_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    db = _db()
    if db is None:
        return []
    try:
        res = (
            db.table("pptx_program_versions")
            .select("version,title,canvas,created_at")
            .eq("program_id", program_id)
            .order("version", desc=True)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        logger.warning("list_versions failed: %s", exc)
        return []


def get_version(*, program_id: str, version: int) -> Optional[Dict[str, Any]]:
    # Try volume
    vf = _PROGRAMS_ROOT / program_id / "versions" / f"v{version}.json"
    if vf.exists():
        try:
            return json.loads(vf.read_text(encoding="utf-8"))
        except Exception:
            pass
    db = _db()
    if db is None:
        return None
    try:
        res = (
            db.table("pptx_program_versions")
            .select("*")
            .eq("program_id", program_id)
            .eq("version", version)
            .execute()
        )
        if res.data:
            return res.data[0]
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Patching
# ─────────────────────────────────────────────────────────────────────────────

def _apply_path(d: Dict[str, Any], path: str, value: Any) -> None:
    """Apply dotted-path update on a dict in place.  Supports [idx] indexing."""
    parts: List[Any] = []
    buf = ""
    i = 0
    while i < len(path):
        ch = path[i]
        if ch == ".":
            if buf:
                parts.append(buf); buf = ""
        elif ch == "[":
            if buf: parts.append(buf); buf = ""
            j = path.index("]", i)
            parts.append(int(path[i+1:j]))
            i = j
        else:
            buf += ch
        i += 1
    if buf: parts.append(buf)

    cur: Any = d
    for k in parts[:-1]:
        cur = cur[k]
    cur[parts[-1]] = value


def apply_patches(
    program: Dict[str, Any], patches: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Return a new program dict with patches applied.  Does not mutate input.
    """
    result = copy.deepcopy(program)
    slides: List[Any] = result.setdefault("slides", [])

    for p in patches:
        op = p.get("op")
        try:
            if op == "update":
                idx = int(p["slide"])
                if idx < 0 or idx >= len(slides):
                    continue
                path = p.get("path", "")
                value = p.get("value")
                if not path:
                    # Whole-slide replace
                    slides[idx] = value
                else:
                    _apply_path(slides[idx], path, value)
            elif op == "insert":
                idx = int(p.get("index", len(slides)))
                idx = max(0, min(len(slides), idx))
                slides.insert(idx, p.get("slide") or {})
            elif op == "delete":
                idx = int(p["slide"])
                if 0 <= idx < len(slides):
                    slides.pop(idx)
            elif op == "reorder":
                i = int(p["from"]); j = int(p["to"])
                if 0 <= i < len(slides):
                    item = slides.pop(i)
                    j = max(0, min(len(slides), j))
                    slides.insert(j, item)
            elif op == "set_canvas":
                result["canvas"] = p.get("canvas") or {}
            elif op == "set_title":
                result["title"] = p.get("title") or result.get("title", "")
            elif op == "set_filename":
                result["filename"] = p.get("filename")
            else:
                logger.warning("Unknown patch op: %s", op)
        except Exception as exc:
            logger.warning("Patch failed (%s): %s", op, exc)

    return result


def revert_to(program_id: str, *, version: int, user_id: str) -> Optional[ProgramRecord]:
    """Roll a program back to a prior version by loading and re-saving it."""
    v = get_version(program_id=program_id, version=version)
    if not v:
        return None
    program = v.get("program") or {}
    title = v.get("title") or "Untitled"
    canvas = v.get("canvas") or {}
    return save_program(
        user_id=user_id, title=title, canvas=canvas,
        program=program, program_id=program_id,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Render artifact storage
# ─────────────────────────────────────────────────────────────────────────────

def save_render_artifact(program_id: str, version: int, data: bytes) -> Path:
    """Store the rendered .pptx alongside a program version on the volume."""
    p = _program_dir(program_id) / "renders" / f"v{version}.pptx"
    try:
        p.write_bytes(data)
        # Also write a `latest.pptx` alias
        latest = _program_dir(program_id) / "renders" / "latest.pptx"
        latest.write_bytes(data)
    except Exception as exc:
        logger.warning("Could not save render artifact: %s", exc)
    return p


def load_render_artifact(program_id: str, *, version: Optional[int] = None) -> Optional[bytes]:
    dir_ = _program_dir(program_id) / "renders"
    if version:
        p = dir_ / f"v{version}.pptx"
    else:
        p = dir_ / "latest.pptx"
    if p.exists():
        try:
            return p.read_bytes()
        except Exception:
            return None
    return None
