"""
Skill Registry
==============
Load, store, and retrieve skill definitions.
"""

import logging
from typing import Dict, List, Optional

from core.skills_v2.base import SkillDefinition

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Registry of available skills."""

    def __init__(self):
        self._skills: Dict[str, SkillDefinition] = {}

    def register(self, skill: SkillDefinition) -> None:
        """Register a skill."""
        self._skills[skill.slug] = skill
        logger.info("Registered skill: %s (%s)", skill.slug, skill.name)

    def get(self, slug: str) -> Optional[SkillDefinition]:
        """Get a skill by slug."""
        return self._skills.get(slug)

    def list_enabled(self) -> List[SkillDefinition]:
        """List all enabled skills."""
        return [s for s in self._skills.values() if s.enabled]

    def list_all(self) -> List[SkillDefinition]:
        """List all skills (enabled and disabled)."""
        return list(self._skills.values())

    def list_by_category(self, category: str) -> List[SkillDefinition]:
        """Filter skills by category."""
        return [
            s for s in self._skills.values()
            if s.category == category and s.enabled
        ]

    def get_tool_definitions(self) -> List[Dict]:
        """
        Get tool definitions for all enabled skills.
        These can be added to any provider's tool list.
        """
        return [s.to_tool_definition() for s in self.list_enabled()]

    def has_skill(self, slug: str) -> bool:
        """Check if a skill is registered."""
        return slug in self._skills

    def __repr__(self) -> str:
        return (
            f"<SkillRegistry skills={len(self._skills)} "
            f"enabled={len(self.list_enabled())}>"
        )