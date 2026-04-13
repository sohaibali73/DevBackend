"""
Skill Loader
=============
Auto-discovers skill definitions from core/skills/ subdirectories.

Each skill folder contains:
  - skill.json  — metadata (slug, name, tools, etc.)
  - prompt.md   — system prompt (the expertise)
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Path to skills directory ──────────────────────────────────────────────
SKILLS_DIR = Path(__file__).parent  # core/skills/


# ── SkillDefinition dataclass ─────────────────────────────────────────────
@dataclass
class SkillDefinition:
    slug: str
    name: str
    description: str
    category: str
    system_prompt: str                          # Loaded from prompt.md
    tools: List[str] = field(default_factory=list)
    output_type: str = "text"
    max_tokens: int = 8192
    timeout: int = 120
    enabled: bool = True
    aliases: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize for REST API responses."""
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
        }


# ── Global registry ──────────────────────────────────────────────────────
_REGISTRY: Dict[str, SkillDefinition] = {}
_LOADED = False


def _load_all() -> None:
    """Scan SKILLS_DIR for skill folders and populate the registry."""
    global _REGISTRY, _LOADED
    if _LOADED:
        return

    for folder in sorted(SKILLS_DIR.iterdir()):
        if not folder.is_dir():
            continue
        if folder.name.startswith("__"):  # Skip __pycache__
            continue
            
        skill_json = folder / "skill.json"
        prompt_md = folder / "prompt.md"
        if not skill_json.exists():
            continue  # Not a skill folder

        try:
            meta = json.loads(skill_json.read_text(encoding="utf-8"))
            system_prompt = ""
            if prompt_md.exists():
                system_prompt = prompt_md.read_text(encoding="utf-8").strip()

            skill = SkillDefinition(
                slug=meta["slug"],
                name=meta["name"],
                description=meta.get("description", ""),
                category=meta.get("category", "general"),
                system_prompt=system_prompt,
                tools=meta.get("tools", []),
                output_type=meta.get("output_type", "text"),
                max_tokens=meta.get("max_tokens", 8192),
                timeout=meta.get("timeout", 120),
                enabled=meta.get("enabled", True),
                aliases=meta.get("aliases", []),
            )

            # Register by primary slug
            _REGISTRY[skill.slug] = skill

            # Register aliases (old slugs still work)
            for alias in skill.aliases:
                _REGISTRY[alias] = skill

            logger.info("Loaded skill: %s (%s)", skill.slug, skill.name)

        except Exception as e:
            logger.warning("Failed to load skill from %s: %s", folder.name, e)

    _LOADED = True
    # Use id()-based dedup — SkillDefinition is a mutable dataclass, not hashable
    num_unique = len({id(v) for v in _REGISTRY.values()})
    logger.info("Skill loader: %d skills loaded (%d total registry entries with aliases)",
                num_unique, len(_REGISTRY))


# ── Public API ────────────────────────────────────────────────────────────

def load_skills() -> Dict[str, SkillDefinition]:
    """Return the full registry dict (slug → SkillDefinition)."""
    _load_all()
    return dict(_REGISTRY)


def get_skill(slug: str) -> Optional[SkillDefinition]:
    """Get a skill by slug or alias. Returns None if not found."""
    _load_all()
    return _REGISTRY.get(slug)


def list_skills(
    category: Optional[str] = None,
    enabled_only: bool = True,
    include_builtins: bool = True,   # accepted but ignored — legacy compat
) -> List[SkillDefinition]:
    """List unique skills, optionally filtered."""
    _load_all()
    # Deduplicate (aliases point to same object)
    seen = set()
    result = []
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