"""
Model-Agnostic Skills Package
==============================
Universal skills system that works with any LLM provider.

Skills are defined as:
  - System prompt template
  - Required tools
  - Execution workflow (server-side tool loop)

Unlike Claude's beta skills (which are provider-specific), these skills
work by having the server execute the skill workflow using the SAME
provider that initiated the call.

Usage:
    from core.skills_v2 import get_skill_registry, get_skill_executor
    
    registry = get_skill_registry()
    skill = registry.get("potomac-docx-skill")
    
    executor = get_skill_executor(provider, sandbox_manager)
    result = await executor.execute(skill, message="Create a report...")
"""

from core.skills_v2.base import SkillDefinition
from core.skills_v2.registry import SkillRegistry
from core.skills_v2.executor import SkillExecutor

# Singleton registry
_registry: "SkillRegistry | None" = None


def get_skill_registry() -> SkillRegistry:
    """Get or create the singleton skill registry with built-in skills loaded."""
    global _registry
    if _registry is not None:
        return _registry

    _registry = SkillRegistry()

    # Load built-in skills
    try:
        from core.skills_v2.builtins import ALL_BUILTIN_SKILLS
        for skill in ALL_BUILTIN_SKILLS:
            _registry.register(skill)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to load built-in skills: %s", e
        )

    return _registry


def get_skill_executor(provider, sandbox_manager) -> SkillExecutor:
    """Create a skill executor for a given provider."""
    return SkillExecutor(provider=provider, sandbox_manager=sandbox_manager)


__all__ = [
    "SkillDefinition",
    "SkillRegistry",
    "SkillExecutor",
    "get_skill_registry",
    "get_skill_executor",
]