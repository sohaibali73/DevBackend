"""
Skill Upload Endpoints
======================
HTTP routes that let authenticated users upload, edit, delete, download,
and duplicate skills. All uploaded skills are visible org-wide; only the
uploader (or an admin) may edit or delete them.

Routes
------
POST   /skills/upload         multipart  (file=<zip>, metadata=<json string>)
PATCH  /skills/{slug}         body: { name?, description?, category?, tags?[],
                                       enabled?, system_prompt? }
DELETE /skills/{slug}
GET    /skills/{slug}/download
POST   /skills/{slug}/duplicate    body: { new_slug? }
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Response, UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.dependencies import get_current_user_id
from db.supabase_client import get_supabase
from core.skills import invalidate_cache as invalidate_skills_cache
from core.skills.loader import get_skill as fs_get_skill
from core.skills.uploads import (
    SLUG_RE,
    SkillUploadError,
    decide_storage_kind,
    delete_on_disk,
    extract_and_validate,
    materialize,
    repack_folder_to_zip,
    synthesize_inline_bundle,
)
from core.skills import skill_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skills", tags=["Skills Upload"])


# ── Helpers ────────────────────────────────────────────────────────────────


def _is_admin(user_id: str) -> bool:
    try:
        sb = get_supabase()
        row = sb.table("user_profiles").select("is_admin").eq("id", user_id).limit(1).execute().data
        return bool(row and row[0].get("is_admin"))
    except Exception:
        return False


def _slug_taken(slug: str) -> Optional[str]:
    """Return the source name of an existing slug ('portal' / 'fs' / 'db'), else None."""
    # Hardcoded portal registry
    try:
        from api.routes.skills import SKILL_REGISTRY
        if slug in SKILL_REGISTRY:
            return "portal"
    except Exception:
        pass

    # Filesystem
    if fs_get_skill(slug) is not None:
        return "fs"

    # DB row (handles cases where folder was wiped but row remains)
    try:
        sb = get_supabase()
        row = sb.table("user_skills").select("slug").eq("slug", slug).limit(1).execute().data
        if row:
            return "db"
    except Exception:
        pass
    return None


def _audit(slug: str, actor_id: Optional[str], action: str, **detail) -> None:
    try:
        get_supabase().table("user_skill_audit").insert({
            "slug": slug,
            "actor_id": actor_id,
            "action": action,
            "detail": detail or {},
        }).execute()
    except Exception as e:
        logger.warning("audit insert failed (%s/%s): %s", slug, action, e)


def _err(code: str, message: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "error": message})


def _can_modify(user_id: str, slug: str) -> tuple[bool, Optional[dict]]:
    """Return (allowed, db_row). Allowed if user owns the row or is admin."""
    sb = get_supabase()
    rows = sb.table("user_skills").select(
        "slug, source, created_by, storage_kind, storage_path, enabled"
    ).eq("slug", slug).limit(1).execute().data or []
    if not rows:
        return False, None
    row = rows[0]
    if row.get("source") == "system":
        return _is_admin(user_id), row
    if row.get("created_by") == user_id:
        return True, row
    return _is_admin(user_id), row


# ── POST /skills/upload ────────────────────────────────────────────────────


@router.post("/upload")
async def upload_skill(
    file: UploadFile = File(..., description="Skill bundle .zip (max 25 MB)"),
    metadata: Optional[str] = Form(None, description="Optional JSON string with override fields"),
    user_id: str = Depends(get_current_user_id),
):
    """
    Upload a skill bundle. Accepts:
      • An Anthropic SKILL.md bundle (with frontmatter), OR
      • A {skill.json + prompt.md} lightweight bundle, OR
      • An "inline" bundle: caller passes mode='inline' in metadata plus
        name/description/system_prompt — frontend can also synthesize the zip.

    Auto-routes to core/skills/<slug>/ (lightweight) or ClaudeSkills/<slug>/ (bundle).
    """
    raw = await file.read()
    # Parse metadata overrides (optional)
    overrides: dict = {}
    if metadata:
        try:
            overrides = json.loads(metadata)
            if not isinstance(overrides, dict):
                overrides = {}
        except json.JSONDecodeError:
            raise _err("INVALID_METADATA", "metadata field must be valid JSON")

    mode = (overrides.get("mode") or "upload").lower()
    if mode not in ("upload", "inline"):
        mode = "upload"

    try:
        if mode == "inline":
            zip_bytes, parsed = synthesize_inline_bundle(
                name=overrides.get("name") or "",
                description=overrides.get("description") or "",
                system_prompt=overrides.get("system_prompt") or "",
                slug=overrides.get("slug"),
                category=overrides.get("category") or "general",
                tags=overrides.get("tags") or [],
            )
        else:
            zip_bytes = raw
            parsed = extract_and_validate(zip_bytes, metadata_overrides=overrides)
    except SkillUploadError as e:
        raise _err(e.code, e.message)

    taken_in = _slug_taken(parsed.slug)
    if taken_in is not None:
        raise _err(
            "SLUG_TAKEN",
            f"Skill slug '{parsed.slug}' is already in use ({taken_in}).",
        )

    kind = decide_storage_kind(parsed)

    try:
        target_dir = materialize(parsed, kind)
    except SkillUploadError as e:
        raise _err(e.code, e.message)
    except Exception as e:
        logger.error("materialize failed for %s: %s", parsed.slug, e, exc_info=True)
        raise _err("MATERIALIZE_FAILED", f"Failed to write skill to disk: {e}", status=500)

    # Archive zip in Supabase Storage so we can rehydrate after redeploys
    archived = skill_storage.upload_zip(parsed.slug, zip_bytes)

    # Insert DB row
    try:
        sb = get_supabase()
        sb.table("user_skills").insert({
            "slug": parsed.slug,
            "name": parsed.name,
            "description": parsed.description,
            "category": parsed.category,
            "tags": parsed.tags,
            "storage_kind": kind,
            "storage_path": str(target_dir),
            "bundle_size": len(zip_bytes),
            "file_count": parsed.file_count,
            "enabled": True,
            "source": "inline" if mode == "inline" else "upload",
            "created_by": user_id,
        }).execute()
    except Exception as e:
        logger.error("DB insert failed for %s, rolling back disk: %s", parsed.slug, e)
        delete_on_disk(parsed.slug)
        skill_storage.delete_zip(parsed.slug)
        raise _err("DB_INSERT_FAILED", f"Could not register skill in database: {e}", status=500)

    _audit(parsed.slug, user_id, "create",
           kind=kind, mode=mode, archived=archived, file_count=parsed.file_count)

    invalidate_skills_cache()

    fs = fs_get_skill(parsed.slug)
    skill_dict = fs.to_dict() if fs else {
        "slug": parsed.slug,
        "name": parsed.name,
        "description": parsed.description,
        "category": parsed.category,
        "tags": parsed.tags,
        "enabled": True,
        "storage_kind": kind,
        "source": "inline" if mode == "inline" else "upload",
        "created_by": user_id,
    }

    return {
        "skill": skill_dict,
        "warnings": parsed.warnings,
        "archived": archived,
        "storage_kind": kind,
        "storage_path": str(target_dir.relative_to(target_dir.parent.parent.parent)),
    }


# ── PATCH /skills/{slug} ───────────────────────────────────────────────────


class SkillPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    enabled: Optional[bool] = None
    system_prompt: Optional[str] = None  # Lightweight skills only


@router.patch("/{slug}")
async def patch_skill(
    slug: str,
    patch: SkillPatch,
    user_id: str = Depends(get_current_user_id),
):
    if not SLUG_RE.match(slug):
        raise _err("BAD_SLUG", f"Invalid slug: {slug}")

    allowed, row = _can_modify(user_id, slug)
    if row is None:
        raise _err("NOT_FOUND", f"Skill '{slug}' not found", status=404)
    if not allowed:
        raise _err("FORBIDDEN", "You do not have permission to modify this skill", status=403)

    sb = get_supabase()
    updates: dict = {}
    if patch.name is not None:
        updates["name"] = patch.name.strip()
    if patch.description is not None:
        updates["description"] = patch.description.strip()
    if patch.category is not None:
        updates["category"] = patch.category.strip().lower() or "general"
    if patch.tags is not None:
        updates["tags"] = [t.strip() for t in patch.tags if t.strip()]
    if patch.enabled is not None:
        updates["enabled"] = bool(patch.enabled)

    if updates:
        try:
            sb.table("user_skills").update(updates).eq("slug", slug).execute()
        except Exception as e:
            raise _err("DB_UPDATE_FAILED", str(e), status=500)

    # Rewrite skill.json / prompt.md for lightweight skills
    storage_path = Path(row.get("storage_path") or "")
    storage_kind = row.get("storage_kind") or "lightweight"

    if storage_path.exists():
        try:
            if storage_kind == "lightweight":
                skill_json_p = storage_path / "skill.json"
                if skill_json_p.exists():
                    meta = json.loads(skill_json_p.read_text(encoding="utf-8"))
                    if "name" in updates: meta["name"] = updates["name"]
                    if "description" in updates: meta["description"] = updates["description"]
                    if "category" in updates: meta["category"] = updates["category"]
                    if "tags" in updates: meta["tags"] = updates["tags"]
                    if "enabled" in updates: meta["enabled"] = updates["enabled"]
                    skill_json_p.write_text(json.dumps(meta, indent=2), encoding="utf-8")
                if patch.system_prompt is not None:
                    (storage_path / "prompt.md").write_text(
                        patch.system_prompt.strip() + "\n", encoding="utf-8"
                    )
            # bundle skills: regenerate SKILL.md frontmatter on metadata changes
            elif storage_kind == "bundle" and updates:
                skill_md_p = storage_path / "SKILL.md"
                if skill_md_p.exists():
                    text = skill_md_p.read_text(encoding="utf-8")
                    new_text = _patch_frontmatter(text, updates)
                    skill_md_p.write_text(new_text, encoding="utf-8")
        except Exception as e:
            logger.warning("Disk update for %s failed (DB already updated): %s", slug, e)

    _audit(slug, user_id, "update", **updates)
    invalidate_skills_cache()

    fs = fs_get_skill(slug)
    return {"skill": fs.to_dict() if fs else {"slug": slug, **updates}}


def _patch_frontmatter(text: str, updates: dict) -> str:
    """Best-effort YAML frontmatter patcher for SKILL.md."""
    import re
    import yaml

    m = re.match(r"^(---\s*\n)(.*?)(\n---\s*\n?)(.*)$", text, re.DOTALL)
    if not m:
        return text
    try:
        meta = yaml.safe_load(m.group(2)) or {}
        if not isinstance(meta, dict):
            meta = {}
    except Exception:
        meta = {}
    for k, v in updates.items():
        if k in ("name", "description", "category", "tags", "enabled"):
            meta[k] = v
    return m.group(1) + yaml.safe_dump(meta, sort_keys=False).rstrip() + m.group(3) + m.group(4)


# ── DELETE /skills/{slug} ──────────────────────────────────────────────────


@router.delete("/{slug}", status_code=204)
async def delete_skill(
    slug: str,
    user_id: str = Depends(get_current_user_id),
):
    if not SLUG_RE.match(slug):
        raise _err("BAD_SLUG", f"Invalid slug: {slug}")

    allowed, row = _can_modify(user_id, slug)
    if row is None:
        raise _err("NOT_FOUND", f"Skill '{slug}' not found", status=404)
    if not allowed:
        raise _err("FORBIDDEN", "You do not have permission to delete this skill", status=403)
    if (row.get("source") or "system") == "system" and not _is_admin(user_id):
        raise _err("FORBIDDEN", "System skills cannot be deleted", status=403)

    try:
        delete_on_disk(slug)
    except Exception as e:
        logger.warning("delete_on_disk failed for %s: %s", slug, e)

    skill_storage.delete_zip(slug)

    try:
        get_supabase().table("user_skills").delete().eq("slug", slug).execute()
    except Exception as e:
        raise _err("DB_DELETE_FAILED", str(e), status=500)

    _audit(slug, user_id, "delete")
    invalidate_skills_cache()
    return Response(status_code=204)


# ── GET /skills/{slug}/download ────────────────────────────────────────────


@router.get("/{slug}/download")
async def download_skill(
    slug: str,
    user_id: str = Depends(get_current_user_id),
):
    if not SLUG_RE.match(slug):
        raise _err("BAD_SLUG", f"Invalid slug: {slug}")

    fs = fs_get_skill(slug)
    if fs is None or not fs.storage_path:
        raise _err("NOT_FOUND", f"Skill '{slug}' not found", status=404)
    folder = Path(fs.storage_path)
    if not folder.exists():
        # Try rehydrate from Storage as a last resort
        zip_bytes = skill_storage.download_zip(slug)
        if zip_bytes is None:
            raise _err("NOT_FOUND", f"Skill folder for '{slug}' missing", status=404)

        def _iter1():
            yield zip_bytes
        return StreamingResponse(
            _iter1(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{slug}.zip"'},
        )

    zip_bytes = repack_folder_to_zip(folder)

    def _iter2():
        yield zip_bytes
    return StreamingResponse(
        _iter2(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}.zip"'},
    )


# ── POST /skills/{slug}/duplicate ──────────────────────────────────────────


class DuplicateBody(BaseModel):
    new_slug: Optional[str] = None
    new_name: Optional[str] = None


@router.post("/{slug}/duplicate")
async def duplicate_skill(
    slug: str,
    body: DuplicateBody,
    user_id: str = Depends(get_current_user_id),
):
    if not SLUG_RE.match(slug):
        raise _err("BAD_SLUG", f"Invalid slug: {slug}")

    fs = fs_get_skill(slug)
    if fs is None or not fs.storage_path:
        raise _err("NOT_FOUND", f"Skill '{slug}' not found", status=404)

    src_folder = Path(fs.storage_path)
    if not src_folder.exists():
        raise _err("NOT_FOUND", f"Skill folder for '{slug}' missing", status=404)

    new_slug = (body.new_slug or f"{slug}-copy").strip().lower()
    if not SLUG_RE.match(new_slug):
        raise _err("BAD_SLUG", f"Invalid new slug: {new_slug}")
    if _slug_taken(new_slug):
        raise _err("SLUG_TAKEN", f"Slug '{new_slug}' is already in use")

    # Repack the existing folder, then run it through extract_and_validate
    # so the same path is used (validation + materialize).
    zip_bytes = repack_folder_to_zip(src_folder)
    try:
        parsed = extract_and_validate(
            zip_bytes,
            metadata_overrides={
                "slug": new_slug,
                "name": body.new_name or f"{fs.name} (Copy)",
            },
        )
    except SkillUploadError as e:
        raise _err(e.code, e.message)

    kind = decide_storage_kind(parsed)
    try:
        target_dir = materialize(parsed, kind)
    except SkillUploadError as e:
        raise _err(e.code, e.message)

    skill_storage.upload_zip(new_slug, zip_bytes)

    try:
        get_supabase().table("user_skills").insert({
            "slug": new_slug,
            "name": parsed.name,
            "description": parsed.description,
            "category": parsed.category,
            "tags": parsed.tags,
            "storage_kind": kind,
            "storage_path": str(target_dir),
            "bundle_size": len(zip_bytes),
            "file_count": parsed.file_count,
            "enabled": True,
            "source": "upload",
            "created_by": user_id,
        }).execute()
    except Exception as e:
        delete_on_disk(new_slug)
        skill_storage.delete_zip(new_slug)
        raise _err("DB_INSERT_FAILED", str(e), status=500)

    _audit(new_slug, user_id, "create", duplicated_from=slug, kind=kind)
    invalidate_skills_cache()

    new_fs = fs_get_skill(new_slug)
    return {"skill": new_fs.to_dict() if new_fs else {"slug": new_slug, "name": parsed.name}}
