"""
Skill Router
=============
Routes skill invocation requests to the SkillExecutor.

Usage:
    from core.skills.router import SkillRouter

    router = SkillRouter(provider=my_llm_provider, sandbox_manager=my_sandbox)
    result = await router.execute("backtest-expert", "Analyze this strategy...")
"""

import logging
from typing import Dict, Any, List, Optional

from core.skills.loader import get_skill, list_skills, SkillDefinition
from core.skills.executor import SkillExecutor
from core.llm.base import BaseLLMProvider
from core.sandbox.manager import SandboxManager

logger = logging.getLogger(__name__)


class SkillRouter:
    """
    Routes skill requests to the executor.

    Provides the same interface as the old SkillGateway but runs
    skills through any LLM provider instead of Anthropic only.
    """

    def __init__(
        self,
        provider: BaseLLMProvider,
        sandbox_manager: SandboxManager,
    ):
        self.provider = provider
        self.sandbox_manager = sandbox_manager
        self.executor = SkillExecutor(
            provider=provider,
            sandbox_manager=sandbox_manager,
        )

    async def execute(
        self,
        skill_slug: str,
        message: str,
        *,
        context: str = "",
        conversation_history: Optional[List[Dict]] = None,
        model: str = "",
    ) -> Dict[str, Any]:
        """
        Execute a skill by slug.

        Parameters
        ----------
        skill_slug : str
            Slug or alias of the skill.
        message : str
            User's request message.
        context : str
            Additional context appended to system prompt.
        conversation_history : list, optional
            Prior messages for context.
        model : str
            Model override (defaults to provider's default).

        Returns
        -------
        dict
            {success, text, usage, execution_time_ms, skill, skill_name, ...}
        """
        # Resolve skill
        skill = get_skill(skill_slug)
        if skill is None:
            available = sorted(s.slug for s in list_skills())
            return {
                "success": False,
                "error": f"Unknown skill '{skill_slug}'. Available: {available}",
            }

        if not skill.enabled:
            return {
                "success": False,
                "error": f"Skill '{skill_slug}' is currently disabled.",
            }

        logger.info("Routing skill: %s (%s)", skill.slug, skill.name)

        return await self.executor.execute(
            skill=skill,
            message=message,
            context=context,
            conversation_history=conversation_history,
            model=model,
        )

    def list_available(self, category: Optional[str] = None) -> List[Dict]:
        """List available skills as dicts (for REST API)."""
        return [s.to_dict() for s in list_skills(category=category)]