"""
PPTX Asset Library
==================
User-uploadable icon / graphic / background library for the PPTX sandbox.

Persistence strategy (dual)
---------------------------
- Supabase table ``pptx_assets``  → source of truth, queryable, RLS-scoped.
- Railway volume ``/data/pptx_assets/{scope}/{owner_id}/{sha}.{ext}`` → binary cache.

Scopes
------
- ``global`` — shared brand assets (owner_id = NULL).
- ``user``   — personal uploads (owner_id = user's UUID).
- ``org``    — reserved for future org-level sharing.

A single ``key`` identifies an asset *within* a scope (unique per scope+owner).
Assets are referenced by key from templates and freestyle code.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import mimetypes
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "/data"))
_ASSETS_ROOT = _STORAGE_ROOT / "pptx_assets"
_GLOBAL_DIR = _ASSETS_ROOT / "global"

_REPO_BRAND_ASSETS = (
    Path(__file__).parent.parent.parent
    / "ClaudeSkills" / "potomac-pptx" / "brand-assets" / "logos"
)

# Default global seed — the Potomac logos shipped with the repo.
_DEFAULT_GLOBAL_LOGOS = {
    "potomac_full":        "potomac-full-logo.png",
    "potomac_full_black":  "potomac-full-logo-black.png",
    "potomac_full_white":  "potomac-full-logo-white.png",
    "potomac_icon_black":  "potomac-icon-black.png",
    "potomac_icon_white":  "potomac-icon-white.png",
    "potomac_icon_yellow": "potomac-icon-yellow.png",
}

_ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
_MAX_ASSET_BYTES = 8 * 1024 * 1024   # 8 MB per asset


@dataclass
class AssetRecord:
    id: Optional[str]
    scope: str                       # 'global' | 'org' | 'user'
    owner_id: Optional[str]
    key: str
    kind: str                        # 'icon' | 'graphic' | 'background' | 'logo'
    file_path: str                   # absolute path on Railway volume
    file_sha: str
    mime: str
    aspect: Optional[float] = None
    tags: List[str] = field(default_factory=list)
    use_when: Optional[str] = None
    on_colors: List[str] = field(default_factory=list)
    bytes_size: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

def _asset_dir(scope: str, owner_id: Optional[str]) -> Path:
    if scope == "global":
        return _GLOBAL_DIR
    if scope == "user" and owner_id:
        return _ASSETS_ROOT / "user" / owner_id
    if scope == "org" and owner_id:
        return _ASSETS_ROOT / "org" / owner_id
    raise ValueError(f"Invalid scope/owner: scope={scope} owner_id={owner_id}")


def _safe_name(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "._-")[:80]


# ─────────────────────────────────────────────────────────────────────────────
# Supabase helpers
# ─────────────────────────────────────────────────────────────────────────────

def _db():
    try:
        from db.supabase_client import get_supabase
        return get_supabase()
    except Exception as exc:
        logger.warning("Supabase unavailable for pptx_assets: %s", exc)
        return None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _aspect_for_image(data: bytes, mime: str) -> Optional[float]:
    """Best-effort aspect ratio (width/height).  Uses Pillow if installed."""
    try:
        if mime.startswith("image/svg"):
            return None  # SVG aspect requires parsing viewBox
        from io import BytesIO
        from PIL import Image  # type: ignore
        with Image.open(BytesIO(data)) as img:
            w, h = img.size
            if h == 0:
                return None
            return round(w / h, 4)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap
# ─────────────────────────────────────────────────────────────────────────────

def ensure_global_seed() -> None:
    """Copy repo brand logos into the global asset directory & DB if missing."""
    _GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    if not _REPO_BRAND_ASSETS.exists():
        return
    db = _db()
    for key, filename in _DEFAULT_GLOBAL_LOGOS.items():
        src = _REPO_BRAND_ASSETS / filename
        if not src.exists():
            continue
        dst = _GLOBAL_DIR / filename
        if not dst.exists():
            try:
                dst.write_bytes(src.read_bytes())
            except Exception as exc:
                logger.warning("Global seed copy failed %s: %s", filename, exc)
                continue

        if db is not None:
            try:
                existing = (
                    db.table("pptx_assets")
                    .select("id")
                    .eq("scope", "global")
                    .eq("key", key)
                    .execute()
                )
                if existing.data:
                    continue
                data = dst.read_bytes()
                db.table("pptx_assets").insert({
                    "scope":     "global",
                    "owner_id":  None,
                    "key":       key,
                    "kind":      "logo",
                    "file_path": str(dst),
                    "file_sha":  _sha256(data),
                    "mime":      "image/png",
                    "aspect":    _aspect_for_image(data, "image/png") or 1.0,
                    "tags":      ["potomac", "brand", "logo"],
                    "use_when":  "Brand wordmark/icon — use on title, closing, and cta slides.",
                    "on_colors": ["DARK_GRAY", "WHITE", "YELLOW"],
                    "bytes_size": len(data),
                }).execute()
            except Exception as exc:
                logger.debug("Global seed DB insert skipped for %s: %s", key, exc)


# ─────────────────────────────────────────────────────────────────────────────
# Upload / list / resolve
# ─────────────────────────────────────────────────────────────────────────────

def upload_asset(
    *, scope: str, owner_id: Optional[str], key: str, kind: str,
    filename: str, content: bytes, tags: Optional[List[str]] = None,
    use_when: Optional[str] = None, on_colors: Optional[List[str]] = None,
) -> AssetRecord:
    """
    Save a new asset.

    Writes to Railway volume, then upserts the pptx_assets row in Supabase.
    Raises ValueError for validation issues.
    """
    if scope not in ("global", "org", "user"):
        raise ValueError(f"Invalid scope: {scope}")
    if scope != "global" and not owner_id:
        raise ValueError("owner_id required for non-global scope")
    if len(content) > _MAX_ASSET_BYTES:
        raise ValueError(f"Asset too large: {len(content)} bytes")
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_EXTS:
        raise ValueError(f"Unsupported extension: {ext}")

    key = _safe_name(key)
    if not key:
        raise ValueError("Invalid key")

    sha = _sha256(content)
    target_dir = _asset_dir(scope, owner_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    disk_name = f"{key}_{sha[:12]}{ext}"
    disk_path = target_dir / disk_name

    if not disk_path.exists():
        disk_path.write_bytes(content)

    mime, _ = mimetypes.guess_type(filename)
    mime = mime or "application/octet-stream"
    aspect = _aspect_for_image(content, mime)

    record = AssetRecord(
        id=None, scope=scope, owner_id=owner_id,
        key=key, kind=kind, file_path=str(disk_path),
        file_sha=sha, mime=mime, aspect=aspect,
        tags=tags or [], use_when=use_when, on_colors=on_colors or [],
        bytes_size=len(content),
    )

    db = _db()
    if db is None:
        return record

    try:
        payload = {
            "scope":     scope,
            "owner_id":  owner_id,
            "key":       key,
            "kind":      kind,
            "file_path": str(disk_path),
            "file_sha":  sha,
            "mime":      mime,
            "aspect":    aspect,
            "tags":      tags or [],
            "use_when":  use_when,
            "on_colors": on_colors or [],
            "bytes_size": len(content),
        }
        res = db.table("pptx_assets").upsert(
            payload,
            on_conflict="scope,owner_id,key",
        ).execute()
        if res.data:
            record.id = res.data[0].get("id")
    except Exception as exc:
        logger.warning("Supabase asset upsert failed for %s: %s", key, exc)

    return record


def list_assets(
    *, user_id: Optional[str] = None, kind: Optional[str] = None,
    tag: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Return all assets visible to user_id: global + their own user-scoped.
    """
    db = _db()
    if db is None:
        return []

    out: List[Dict[str, Any]] = []
    try:
        q = db.table("pptx_assets").select("*")
        if kind:
            q = q.eq("kind", kind)
        res = q.execute()
        rows = res.data or []
        for r in rows:
            if r.get("scope") == "global":
                out.append(r); continue
            if user_id and r.get("owner_id") == user_id:
                out.append(r); continue
        if tag:
            out = [r for r in out if tag in (r.get("tags") or [])]
    except Exception as exc:
        logger.warning("list_assets failed: %s", exc)
    return out


def resolve_assets(
    *, keys: List[str], user_id: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Load asset content + metadata for a set of keys.

    Returns a dict ``{ key: {dataUrl, aspect, mime} }`` suitable for
    injection as the spec's ``asset_registry`` field.

    Lookup order per key:
      1. global scope exact key match
      2. user scope (user_id) exact key match
      3. None (skip)
    """
    db = _db()
    out: Dict[str, Dict[str, Any]] = {}
    if not keys:
        return out

    # Try DB first
    rows: List[Dict[str, Any]] = []
    if db is not None:
        try:
            res = (
                db.table("pptx_assets")
                .select("*")
                .in_("key", keys)
                .execute()
            )
            rows = res.data or []
        except Exception as exc:
            logger.warning("resolve_assets DB query failed: %s", exc)

    # Build a priority-sorted map
    by_key: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        k = r.get("key")
        if not k:
            continue
        if r.get("scope") == "user" and r.get("owner_id") != user_id:
            continue
        # Prefer user scope over global when both match
        if k in by_key:
            if r.get("scope") == "user":
                by_key[k] = r
        else:
            by_key[k] = r

    for k, r in by_key.items():
        try:
            p = Path(r.get("file_path") or "")
            if not p.exists():
                # Try volume fallback paths
                alt = _asset_dir(r["scope"], r.get("owner_id"))
                candidates = list(alt.glob(f"{k}_*")) if alt.exists() else []
                if candidates:
                    p = candidates[0]
            if not p.exists():
                continue
            data = p.read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            out[k] = {
                "dataUrl": f"data:{r.get('mime', 'image/png')};base64,{b64}",
                "aspect":  r.get("aspect") or 1.0,
                "mime":    r.get("mime", "image/png"),
            }
        except Exception as exc:
            logger.debug("resolve_assets load fail for %s: %s", k, exc)

    # Volume-only fallback for keys not in DB (rare)
    for k in keys:
        if k in out:
            continue
        for scope_dir in [_GLOBAL_DIR] + (
            [ _ASSETS_ROOT / "user" / user_id ] if user_id else []
        ):
            if not scope_dir.exists():
                continue
            matches = list(scope_dir.glob(f"{k}_*")) + list(scope_dir.glob(f"{k}.*"))
            if matches:
                p = matches[0]
                try:
                    data = p.read_bytes()
                    mime, _ = mimetypes.guess_type(str(p))
                    mime = mime or "image/png"
                    b64 = base64.b64encode(data).decode("ascii")
                    out[k] = {
                        "dataUrl": f"data:{mime};base64,{b64}",
                        "aspect":  _aspect_for_image(data, mime) or 1.0,
                        "mime":    mime,
                    }
                    break
                except Exception:
                    continue
    return out


def delete_asset(*, user_id: str, key: str) -> bool:
    """Delete a user-scoped asset (not global)."""
    db = _db()
    if db is None:
        return False
    try:
        res = (
            db.table("pptx_assets")
            .select("*")
            .eq("scope", "user")
            .eq("owner_id", user_id)
            .eq("key", key)
            .execute()
        )
        rows = res.data or []
        for r in rows:
            try:
                p = Path(r.get("file_path") or "")
                if p.exists(): p.unlink()
            except Exception:
                pass
            db.table("pptx_assets").delete().eq("id", r["id"]).execute()
        return bool(rows)
    except Exception as exc:
        logger.warning("delete_asset failed: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Manifest for the AGENT (LLM context)
# ─────────────────────────────────────────────────────────────────────────────

def build_manifest(*, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Compact description the agent can consult to decide which assets to use.

    Example output::

        {
          "icons": [
            { "key": "globe_fist", "tags": ["global","growth"],
              "use_when": "Strategy card for global growth.",
              "on_colors": ["YELLOW","DARK_GRAY"], "aspect": 1.0 },
            ...
          ],
          "logos":       [...],
          "backgrounds": [...],
          "graphics":    [...],
        }
    """
    buckets: Dict[str, List[Dict[str, Any]]] = {
        "icons": [], "logos": [], "graphics": [], "backgrounds": [],
    }
    for a in list_assets(user_id=user_id):
        kind = a.get("kind") or "icon"
        section = {
            "icon": "icons", "logo": "logos",
            "graphic": "graphics", "background": "backgrounds",
        }.get(kind, "icons")
        buckets[section].append({
            "key":       a.get("key"),
            "tags":      a.get("tags") or [],
            "use_when":  a.get("use_when"),
            "on_colors": a.get("on_colors") or [],
            "aspect":    a.get("aspect"),
            "scope":     a.get("scope"),
        })
    return buckets
