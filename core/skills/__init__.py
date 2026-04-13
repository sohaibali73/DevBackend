"""
Skills package - Model-agnostic skill definitions

Public API:
    from core.skills import get_skill, list_skills, load_skills, SkillDefinition
    from core.skills import SkillRouter   # heavy — lazy-import when needed
    from core.skills import SkillExecutor # heavy — lazy-import when needed
"""

from core.skills.loader import (
    load_skills,
    get_skill,
    list_skills,
    SkillDefinition,
)

# SkillExecutor and SkillRouter are NOT imported here at module level.
# They transitively import SandboxManager (→ docker/llm-sandbox), which can
# fail on environments where Docker is not available.
# Import them lazily at call sites instead:
#
#   from core.skills.executor import SkillExecutor
#   from core.skills.router import SkillRouter

__all__ = [
    "load_skills",
    "get_skill",
    "list_skills",
    "SkillDefinition",
]
