"""
Skill Loader
=============
Auto-discovers skill definitions from two on-disk roots:

  • core/skills/<slug>/        — lightweight: skill.json + prompt.md
  • ClaudeSkills/<slug>/       — Anthropic SKILL.md bundle (frontmatter + body)

For each discovered skill we attach optional metadata from the
`user_skills` Supabase table (source / created_by / created_at / enabled).
The filesystem is the source of truth; DB rows just decorate it.

The cache is invalidated when either root's mtime changes, OR when
`invalidate_cache()` is called explicitly (after upload/delete).
"""

from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── On-disk roots ────────────────────────────────────────────────────────
SKILLS_DIR = Path(__file__).parent                          # core/skills/
CLAUDE_SKILLS_DIR = SKILLS_DIR.parent.parent / "ClaudeSkills"


# ── SkillDefinition dataclass ────────────────────────────────────────────
@dataclass
class SkillDefinition:
    slug: str
    name: str
    description: str
    category: str
    system_prompt: str
    tools: List[str] = field(default_factory=list)
    output_type: str = "text"
    max_tokens: int = 8192
    timeout: int = 120
    enabled: bool = True
    aliases: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    # New fields (optional; surface upload metadata to API consumers)
    storage_kind: str = "lightweight"           # 'lightweight' | 'bundle'
    source: str = "system"                       # 'system' | 'upload' | 'inline'
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    storage_path: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "tools": self.tools,
            "output_type": self.output_type,
            "max_tokens": self.max_tokens,
            "enabled": self.enabled,
            "aliases": self.aliases,
            "tags": self.tags,
            "storage_kind": self.storage_kind,
            "source": self.source,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }


# ── Cache state ──────────────────────────────────────────────────────────
_REGISTRY: Dict[str, SkillDefinition] = {}
_MTIMES: Dict[str, float] = {}
_LOCK = threading.RLock()


# ── YAML frontmatter parsing (mirrors uploads.py) ────────────────────────
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def _parse_frontmatter(text: str) -> Tuple[dict, str]:
    m = _FRONTMATTER_RE.match(text.lstrip("\ufeff"))
    if not m:
        return {}, text
    try:
        import yaml
        meta = yaml.safe_load(m.group(1)) or {}
        if not isinstance(meta, dict):
            meta = {}
    except Exception as e:
        logger.warning("Frontmatter parse failed: %s", e)
        meta = {}
    return meta, m.group(2)


def _dir_mtime(p: Path) -> float:
    if not p.exists():
        return 0.0
    try:
        # Top-level dir mtime captures additions/removals of skill folders
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _needs_reload() -> bool:
    return (
        _MTIMES.get("core_skills") != _dir_mtime(SKILLS_DIR)
        or _MTIMES.get("claude_skills") != _dir_mtime(CLAUDE_SKILLS_DIR)
    )


# ── Loaders for each on-disk format ──────────────────────────────────────


def _load_lightweight(folder: Path) -> Optional[SkillDefinition]:
    skill_json = folder / "skill.json"
    prompt_md = folder / "prompt.md"
    if not skill_json.exists():
        return None
    try:
        meta = json.loads(skill_json.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Bad skill.json in %s: %s", folder.name, e)
        return None

    system_prompt = ""
    if prompt_md.exists():
        try:
            system_prompt = prompt_md.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    return SkillDefinition(
        slug=meta.get("slug") or folder.name,
        name=meta.get("name") or folder.name,
        description=meta.get("description", ""),
        category=meta.get("category", "general"),
        system_prompt=system_prompt,
        tools=list(meta.get("tools") or []),
        output_type=meta.get("output_type", "text"),
        max_tokens=int(meta.get("max_tokens", 8192)),
        timeout=int(meta.get("timeout", 120)),
        enabled=bool(meta.get("enabled", True)),
        aliases=list(meta.get("aliases") or []),
        tags=list(meta.get("tags") or []),
        storage_kind="lightweight",
        storage_path=str(folder),
    )


def _load_bundle(folder: Path) -> Optional[SkillDefinition]:
    skill_md = folder / "SKILL.md"
    if not skill_md.exists():
        return None
    try:
        text = skill_md.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("Bad SKILL.md in %s: %s", folder.name, e)
        return None

    fm, body = _parse_frontmatter(text)
    slug = (fm.get("slug") or fm.get("name") or folder.name).strip().lower()
    name = fm.get("name") or folder.name
    description = (fm.get("description") or "").strip()
    category = fm.get("category", "general")
    tags = fm.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in re.split(r"[,;\s]+", tags) if t.strip()]

    return SkillDefinition(
        slug=slug,
        name=name,
        description=description,
        category=category,
        system_prompt=body.strip(),
        tools=list(fm.get("allowed-tools") or fm.get("tools") or []),
        output_type=fm.get("output_type", "text"),
        max_tokens=int(fm.get("max_tokens", 16384)),
        timeout=int(fm.get("timeout", 180)),
        enabled=bool(fm.get("enabled", True)),
        aliases=list(fm.get("aliases") or []),
        tags=list(tags),
        storage_kind="bundle",
        storage_path=str(folder),
    )


def _scan_root(root: Path, kind: str) -> Dict[str, SkillDefinition]:
    out: Dict[str, SkillDefinition] = {}
    if not root.exists():
        return out
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or folder.name.startswith((".", "_")):
            continue
        try:
            skill = _load_lightweight(folder) if kind == "lightweight" else _load_bundle(folder)
        except Exception as e:
            logger.warning("Failed to load skill from %s: %s", folder, e)
            skill = None
        if skill is None:
            continue
        out[skill.slug] = skill
        for alias in skill.aliases:
            out[alias] = skill
    return out


def _decorate_with_db(reg: Dict[str, SkillDefinition]) -> None:
    """Left-join discovered skills with the user_skills table (best-effort)."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        rows = sb.table("user_skills").select(
            "slug, source, created_by, created_at, enabled"
        ).execute().data or []
    except Exception as e:
        logger.info("user_skills DB join skipped: %s", e)
        return

    by_slug = {r["slug"]: r for r in rows}
    seen = set()
    for slug, skill in reg.items():
        if id(skill) in seen:
            continue
        seen.add(id(skill))
        row = by_slug.get(skill.slug)
        if not row:
            continue
        skill.source = row.get("source") or skill.source
        skill.created_by = row.get("created_by")
        skill.created_at = (row.get("created_at") or "")
        if isinstance(skill.created_at, str) and not skill.created_at:
            skill.created_at = None
        # DB enabled flag only DISABLES (never re-enables a folder marked disabled)
        if row.get("enabled") is False:
            skill.enabled = False


def _load_all() -> None:
    with _LOCK:
        if _REGISTRY and not _needs_reload():
            return
        reg: Dict[str, SkillDefinition] = {}
        # Bundle skills first, then lightweight (lightweight wins on slug collision)
        reg.update(_scan_root(CLAUDE_SKILLS_DIR, "bundle"))
        reg.update(_scan_root(SKILLS_DIR, "lightweight"))
        _decorate_with_db(reg)

        _REGISTRY.clear()
        _REGISTRY.update(reg)
        _MTIMES["core_skills"] = _dir_mtime(SKILLS_DIR)
        _MTIMES["claude_skills"] = _dir_mtime(CLAUDE_SKILLS_DIR)
        unique = {id(v) for v in _REGISTRY.values()}
        logger.info(
            "Skill loader: %d skills loaded (%d total registry entries with aliases)",
            len(unique), len(_REGISTRY),
        )


def invalidate_cache() -> None:
    """Force a full rescan on the next access. Call after upload/delete."""
    with _LOCK:
        _REGISTRY.clear()
        _MTIMES.clear()


# ── Public API ───────────────────────────────────────────────────────────


def load_skills() -> Dict[str, SkillDefinition]:
    _load_all()
    return dict(_REGISTRY)


def get_skill(slug: str) -> Optional[SkillDefinition]:
    _load_all()
    return _REGISTRY.get(slug)


def list_skills(
    category: Optional[str] = None,
    enabled_only: bool = True,
    include_builtins: bool = True,   # accepted but ignored — legacy compat
) -> List[SkillDefinition]:
    _load_all()
    seen: set[int] = set()
    result: List[SkillDefinition] = []
    for skill in _REGISTRY.values():
        if id(skill) in seen:
            continue
        seen.add(id(skill))
        if enabled_only and not skill.enabled:
            continue
        if category and skill.category != category:
            continue
        result.append(skill)
    return result
