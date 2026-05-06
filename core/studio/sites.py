"""
Content Studio — Sites (Lovable-style website builder).

Public surface:

    build_zip_from_files(files: dict[str, str|bytes]) -> bytes
    extract_site_bundle(project_id, version, zip_bytes) -> str       # site root dir
    site_root_for_artifact(artifact: dict) -> str                    # extracted dir path
    count_files_in_zip(zip_bytes) -> int

    publish_site(user_id, project_id, artifact_id, subdomain)        -> dict
    unpublish_site(user_id, publication_id)                          -> bool
    list_publications(user_id, project_id=None)                      -> list[dict]
    resolve_subdomain(subdomain) -> dict | None                      # public path
    record_request(publication_id) -> None                           # fire-and-forget
    serve_site_file(site_root, request_path) -> (bytes, mime, status)

    revise_site_files(prev_files: dict, ops: list[dict]) -> dict     # for revise_site tool

Volume layout for site artifacts:
    $STORAGE_ROOT/projects/{project_id}/v{n}.zip
    $STORAGE_ROOT/projects/{project_id}/v{n}_files/<files...>
    $STORAGE_ROOT/published/{subdomain}/  (symlink/copy of the latest published version)
"""

from __future__ import annotations

import io
import logging
import mimetypes
import os
import re
import shutil
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Volume layout
# -----------------------------------------------------------------------------

STORAGE_ROOT = os.getenv("STORAGE_ROOT", "/data")
PROJECTS_ROOT = os.path.join(STORAGE_ROOT, "projects")
PUBLISHED_ROOT = os.path.join(STORAGE_ROOT, "published")

# Reserved subdomains that cannot be claimed by users.
RESERVED_SUBDOMAINS = frozenset({
    "api", "www", "admin", "studio", "app", "auth", "login", "signup",
    "dashboard", "static", "assets", "cdn", "files", "uploads", "ws",
    "websocket", "health", "status", "mail", "smtp", "ftp", "blog",
    "docs", "support", "help", "settings", "billing", "pay", "stripe",
    "webhook", "webhooks", "internal", "test", "staging", "prod",
    "dev", "beta", "alpha", "site", "sites", "s",
})

_SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$")

# Files that are blocked from being served to the public (server-side
# templates, executables, etc.). Site bundles are pure static; reject
# anything that smells like a server-side script.
_BLOCKED_EXTS = frozenset({
    "py", "rb", "php", "exe", "dll", "sh", "bat", "ps1", "cmd",
    "jar", "war", "class",
})

# Maximum site bundle size — sanity-bound to avoid runaway zips.
MAX_BUNDLE_BYTES = 50 * 1024 * 1024     # 50 MB
MAX_FILE_BYTES = 10 * 1024 * 1024       # 10 MB per individual file
MAX_FILES = 200


def _db():
    from db.supabase_client import get_supabase
    return get_supabase()


# =============================================================================
# Subdomain validation
# =============================================================================

def is_valid_subdomain(subdomain: str) -> Tuple[bool, str]:
    """
    Return (ok, reason). Subdomain must be 1-32 chars, lowercase a-z/0-9/-,
    not reserved, not start/end with dash.
    """
    if not subdomain or not isinstance(subdomain, str):
        return False, "subdomain is required"
    sub = subdomain.lower().strip()
    if not _SUBDOMAIN_RE.match(sub):
        return False, (
            "subdomain must be 1–32 chars, lowercase letters, digits, "
            "or hyphens (cannot start or end with a hyphen)"
        )
    if sub in RESERVED_SUBDOMAINS:
        return False, f"'{sub}' is a reserved subdomain"
    return True, ""


# =============================================================================
# Zip helpers
# =============================================================================

def _safe_relpath(path: str) -> Optional[str]:
    """Normalize a zip member path; reject path-traversal & absolute paths."""
    if not path:
        return None
    p = path.replace("\\", "/").lstrip("/")
    if p.startswith("../") or "/../" in p or p == "..":
        return None
    if p.endswith("/"):  # directory entry
        return None
    parts = []
    for seg in p.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            return None
        parts.append(seg)
    if not parts:
        return None
    rel = "/".join(parts)
    ext = rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
    if ext in _BLOCKED_EXTS:
        return None
    return rel


def build_zip_from_files(files: Dict[str, Union[str, bytes]]) -> bytes:
    """
    Build a zip from a {relpath: content} dict. Strings are utf-8 encoded.
    Performs the same path safety checks as extraction.
    """
    if not isinstance(files, dict) or not files:
        raise ValueError("files must be a non-empty dict")
    if len(files) > MAX_FILES:
        raise ValueError(f"too many files (max {MAX_FILES})")

    buf = io.BytesIO()
    total = 0
    has_index = False
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for raw_path, content in files.items():
            rel = _safe_relpath(raw_path)
            if not rel:
                logger.warning("Skipping unsafe site path: %r", raw_path)
                continue
            if isinstance(content, str):
                blob = content.encode("utf-8")
            elif isinstance(content, (bytes, bytearray)):
                blob = bytes(content)
            else:
                raise ValueError(f"file {rel!r} must be str or bytes")
            if len(blob) > MAX_FILE_BYTES:
                raise ValueError(f"file {rel!r} exceeds {MAX_FILE_BYTES} bytes")
            total += len(blob)
            if total > MAX_BUNDLE_BYTES:
                raise ValueError(f"bundle exceeds {MAX_BUNDLE_BYTES} bytes")
            if rel.lower() == "index.html":
                has_index = True
            zf.writestr(rel, blob)

    if not has_index:
        raise ValueError("site bundle must contain an index.html at the root")

    return buf.getvalue()


def count_files_in_zip(zip_bytes: bytes) -> int:
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            return sum(1 for n in zf.namelist() if not n.endswith("/"))
    except Exception:
        return 0


def extract_site_bundle(project_id: str, version: int, zip_bytes: bytes) -> str:
    """
    Extract the zip into $STORAGE_ROOT/projects/{project_id}/v{n}_files/ and
    return that directory's absolute path. Idempotent — clears any prior
    contents first so re-extraction always reflects the artifact bytes.
    """
    site_root = os.path.join(PROJECTS_ROOT, project_id, f"v{version}_files")
    if os.path.isdir(site_root):
        shutil.rmtree(site_root, ignore_errors=True)
    os.makedirs(site_root, exist_ok=True)

    if len(zip_bytes) > MAX_BUNDLE_BYTES:
        raise ValueError(f"bundle exceeds {MAX_BUNDLE_BYTES} bytes")

    extracted = 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            rel = _safe_relpath(name)
            if not rel:
                continue
            info = zf.getinfo(name)
            if info.file_size > MAX_FILE_BYTES:
                logger.warning("Skipping oversized file %r", name)
                continue
            dest = os.path.join(site_root, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with zf.open(name) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted += 1
            if extracted > MAX_FILES:
                raise ValueError(f"bundle has more than {MAX_FILES} files")

    logger.info("✓ extracted %d site files → %s", extracted, site_root)
    return site_root


def site_root_for_artifact(artifact: Dict[str, Any]) -> str:
    """
    Return the directory holding the extracted site bundle for an artifact,
    extracting on demand if it's missing (e.g. older artifact, container restart).
    """
    if not artifact or artifact.get("kind") != "site":
        raise ValueError("artifact is not a site")
    project_id = artifact["project_id"]
    version = int(artifact["version"])
    site_root = os.path.join(PROJECTS_ROOT, project_id, f"v{version}_files")
    if os.path.isdir(site_root) and os.path.exists(os.path.join(site_root, "index.html")):
        return site_root

    zip_path = artifact.get("volume_path")
    if not zip_path or not os.path.exists(zip_path):
        raise FileNotFoundError(f"artifact zip missing: {zip_path}")
    with open(zip_path, "rb") as f:
        return extract_site_bundle(project_id, version, f.read())


def read_site_files_as_dict(artifact: Dict[str, Any]) -> Dict[str, str]:
    """
    Load all text-decodable files in the artifact's bundle into a {path: text}
    dict. Binary files are returned as base64-prefixed strings ('b64:<...>').
    Used by the `revise_site` tool so the LLM has full context.
    """
    import base64
    root = site_root_for_artifact(artifact)
    out: Dict[str, str] = {}
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            try:
                with open(full, "rb") as f:
                    blob = f.read()
                try:
                    out[rel] = blob.decode("utf-8")
                except UnicodeDecodeError:
                    out[rel] = "b64:" + base64.b64encode(blob).decode("ascii")
            except Exception as e:
                logger.warning("could not read %s: %s", full, e)
    return out


def revise_site_files(
    prev_files: Dict[str, str],
    ops: List[Dict[str, Any]],
) -> Dict[str, Union[str, bytes]]:
    """
    Apply a list of edit ops to a {path: content} dict and return the new dict.
    Supported ops:
        {"op": "write",  "path": "...", "content": "..."}     # add or replace
        {"op": "delete", "path": "..."}
        {"op": "rename", "from": "...", "to": "..."}
    """
    import base64
    new: Dict[str, Union[str, bytes]] = {}
    for path, val in prev_files.items():
        if isinstance(val, str) and val.startswith("b64:"):
            new[path] = base64.b64decode(val[4:])
        else:
            new[path] = val

    for op in ops or []:
        kind = (op.get("op") or "").lower()
        if kind == "write":
            p = op.get("path")
            content = op.get("content", "")
            if not p:
                continue
            new[p] = content
        elif kind == "delete":
            p = op.get("path")
            new.pop(p, None)
        elif kind == "rename":
            src, dst = op.get("from"), op.get("to")
            if src in new and dst:
                new[dst] = new.pop(src)
        else:
            logger.warning("Unknown revise_site op: %r", op)
    return new


# =============================================================================
# Publication CRUD
# =============================================================================

def publish_site(
    *,
    user_id: str,
    project_id: str,
    artifact_id: str,
    subdomain: str,
) -> Dict[str, Any]:
    """
    Publish (or re-point) a subdomain to the given site artifact version.
    If the user already has an active publication on this subdomain, it is
    updated to point at the new artifact (acts like an atomic "promote").
    """
    sub = (subdomain or "").lower().strip()
    ok, reason = is_valid_subdomain(sub)
    if not ok:
        raise ValueError(reason)

    db = _db()

    # Validate artifact ownership + kind
    art_res = (
        db.table("studio_artifacts")
        .select("*")
        .eq("id", artifact_id)
        .eq("user_id", user_id)
        .eq("project_id", project_id)
        .limit(1)
        .execute()
    )
    if not art_res.data:
        raise ValueError("artifact not found")
    artifact = art_res.data[0]
    if artifact.get("kind") != "site":
        raise ValueError("artifact is not a site")

    # Make sure the static files are on disk and serveable
    site_root = site_root_for_artifact(artifact)

    # Check subdomain availability — if owned by someone else and active, fail.
    existing_res = (
        db.table("published_sites")
        .select("id, user_id, is_active")
        .eq("subdomain", sub)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if existing_res.data and existing_res.data[0]["user_id"] != user_id:
        raise ValueError(f"subdomain '{sub}' is already taken")

    # Upsert publication
    own_existing = None
    if existing_res.data and existing_res.data[0]["user_id"] == user_id:
        own_existing = existing_res.data[0]["id"]

    payload = {
        "user_id":        user_id,
        "project_id":     project_id,
        "artifact_id":    artifact["id"],
        "subdomain":      sub,
        "site_root_path": site_root,
        "is_active":      True,
        "published_at":   datetime.now(timezone.utc).isoformat(),
    }

    if own_existing:
        upd = (
            db.table("published_sites")
            .update(payload)
            .eq("id", own_existing)
            .execute()
        )
        pub = upd.data[0] if upd.data else None
    else:
        ins = db.table("published_sites").insert(payload).execute()
        pub = ins.data[0] if ins.data else None

    if not pub:
        raise RuntimeError("publish failed (db insert/update returned no row)")

    # Maintain a stable /data/published/{subdomain}/ alias pointing at the
    # current version. Use a copy (not symlink) for portability across FS.
    alias_root = os.path.join(PUBLISHED_ROOT, sub)
    try:
        if os.path.isdir(alias_root):
            shutil.rmtree(alias_root, ignore_errors=True)
        shutil.copytree(site_root, alias_root)
    except Exception as e:
        logger.warning("could not refresh published alias for %s: %s", sub, e)

    return pub


def unpublish_site(user_id: str, publication_id: str) -> bool:
    db = _db()
    row = (
        db.table("published_sites")
        .select("id, subdomain, user_id")
        .eq("id", publication_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not row.data:
        return False
    sub = row.data[0]["subdomain"]

    db.table("published_sites").update({"is_active": False}).eq("id", publication_id).execute()

    alias_root = os.path.join(PUBLISHED_ROOT, sub)
    try:
        if os.path.isdir(alias_root):
            shutil.rmtree(alias_root, ignore_errors=True)
    except Exception as e:
        logger.warning("could not remove published alias for %s: %s", sub, e)
    return True


def list_publications(user_id: str, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
    db = _db()
    q = (
        db.table("published_sites")
        .select(
            "id, project_id, artifact_id, subdomain, custom_domain, is_active,"
            " published_at, last_request_at, request_count, created_at, updated_at"
        )
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
    )
    if project_id:
        q = q.eq("project_id", project_id)
    res = q.execute()
    return res.data or []


def resolve_subdomain(subdomain: str) -> Optional[Dict[str, Any]]:
    """Public lookup — used by the unauthenticated public router."""
    if not subdomain:
        return None
    sub = subdomain.lower().strip()
    db = _db()
    res = (
        db.table("published_sites")
        .select("id, user_id, project_id, artifact_id, subdomain, site_root_path, is_active")
        .eq("subdomain", sub)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def record_request(publication_id: str) -> None:
    """Fire-and-forget request counter; never raises."""
    try:
        db = _db()
        db.rpc(
            "increment_published_site_request",
            {"_pub_id": publication_id},
        ).execute()
    except Exception:
        # The RPC may not exist — fall back to a simple update.
        try:
            db = _db()
            now_iso = datetime.now(timezone.utc).isoformat()
            db.table("published_sites").update(
                {"last_request_at": now_iso}
            ).eq("id", publication_id).execute()
        except Exception:
            pass


# =============================================================================
# Static-file serving (used by both auth-gated preview and public router)
# =============================================================================

# In-memory mtime/size cache for content-type guesses
mimetypes.init()
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("application/json", ".webmanifest")


def serve_site_file(
    site_root: str,
    request_path: str,
) -> Tuple[Optional[bytes], str, int]:
    """
    Resolve a request path under site_root into (bytes, content_type, status).

    Rules (Lovable / Vercel-style static hosting):
      - "" or "/" → /index.html
      - if a file exists at the path → serve it
      - if a directory exists → serve <dir>/index.html
      - otherwise SPA fallback: serve /index.html with status 200
        (so client-side routers work)
      - 404 only if there's no index.html either
    """
    if not site_root or not os.path.isdir(site_root):
        return None, "text/plain", 404

    # Sanitise — prevent escaping site_root
    rel = (request_path or "").lstrip("/")
    safe = _safe_relpath(rel) if rel else "index.html"
    if rel and not safe:
        return None, "text/plain", 400

    candidate = os.path.join(site_root, safe) if rel else os.path.join(site_root, "index.html")

    # Make sure we stay inside site_root (defence in depth)
    try:
        cand_abs = os.path.realpath(candidate)
        root_abs = os.path.realpath(site_root)
        if not cand_abs.startswith(root_abs + os.sep) and cand_abs != root_abs:
            return None, "text/plain", 403
    except Exception:
        return None, "text/plain", 400

    # File hit
    if os.path.isfile(cand_abs):
        return _read_file_with_mime(cand_abs, 200)

    # Directory hit → serve its index.html
    if os.path.isdir(cand_abs):
        idx = os.path.join(cand_abs, "index.html")
        if os.path.isfile(idx):
            return _read_file_with_mime(idx, 200)

    # SPA fallback
    fallback = os.path.join(site_root, "index.html")
    if os.path.isfile(fallback):
        return _read_file_with_mime(fallback, 200)

    return None, "text/plain", 404


def _read_file_with_mime(abs_path: str, status: int) -> Tuple[bytes, str, int]:
    mime, _ = mimetypes.guess_type(abs_path)
    if not mime:
        mime = "application/octet-stream"
    with open(abs_path, "rb") as f:
        return f.read(), mime, status
