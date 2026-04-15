"""
Skill Gateway – Execute skills using our server-side skill system
=================================================================
Uses core/skills/ (loader + router) with the standard Anthropic API.

No Claude beta skills, no code execution container, no beta headers.
File generation is handled by dedicated server-side tools
(generate_docx, generate_pptx, generate_xlsx) — not by this gateway.

All public methods maintain the same interface as the old beta-based
SkillGateway so every caller (tools.py, tasks.py, ai.py,
skills_execute.py) works without changes.
"""

import json
import logging
import time
from typing import Any, Dict, Generator, List, Optional

import anthropic

from core.skills.loader import (
    SkillDefinition,
    SKILL_REGISTRY,
    get_skill,
    list_skills,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"


class SkillGateway:
    """Execute any registered skill via the standard Claude API."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model = model
        self._client: Optional[anthropic.Anthropic] = None

    # ------------------------------------------------------------------
    # Client lifecycle
    # ------------------------------------------------------------------
    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    # ------------------------------------------------------------------
    # Public API – blocking
    # ------------------------------------------------------------------
    def execute(
        self,
        skill_slug: str,
        user_message: str,
        *,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None,
        extra_context: str = "",
    ) -> Dict[str, Any]:
        """Execute a skill and return the full response."""
        skill = self._resolve_skill(skill_slug)
        sys_prompt = self._build_system_prompt(skill, system_prompt, extra_context)
        messages = self._build_messages(user_message, conversation_history)
        tokens = max_tokens or skill.max_tokens

        start = time.time()
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=tokens,
                system=sys_prompt,
                messages=messages,
            )
            text = "\n".join(
                block.text
                for block in response.content
                if hasattr(block, "text")
            )
            elapsed = time.time() - start

            return {
                "text": text,
                "skill": skill.slug,
                "skill_name": skill.name,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
                "model": response.model,
                "execution_time": round(elapsed, 2),
                "stop_reason": response.stop_reason,
                # No file artifacts — use generate_docx/generate_pptx tools
                "files": [],
            }

        except anthropic.APIError as exc:
            logger.error("Skill %s API error: %s", skill_slug, exc)
            raise
        except Exception as exc:
            logger.error("Skill %s execution error: %s", skill_slug, exc, exc_info=True)
            raise

    def download_files(self, file_refs: list) -> list:
        """
        No-op — file generation is handled by server-side tools, not beta skills.
        Kept for interface compatibility with existing callers.
        """
        return []

    # ------------------------------------------------------------------
    # Public API – streaming (plain chunks)
    # ------------------------------------------------------------------
    def stream(
        self,
        skill_slug: str,
        user_message: str,
        *,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None,
        extra_context: str = "",
    ) -> Generator[Dict[str, Any], None, None]:
        """Stream a skill response chunk-by-chunk."""
        skill = self._resolve_skill(skill_slug)
        sys_prompt = self._build_system_prompt(skill, system_prompt, extra_context)
        messages = self._build_messages(user_message, conversation_history)
        tokens = max_tokens or skill.max_tokens

        start = time.time()
        full_text = ""

        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=tokens,
                system=sys_prompt,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    full_text += text
                    yield {"type": "chunk", "content": text}

            elapsed = time.time() - start
            yield {
                "type": "complete",
                "text": full_text,
                "skill": skill.slug,
                "skill_name": skill.name,
                "execution_time": round(elapsed, 2),
            }

        except Exception as exc:
            logger.error("Skill %s stream error: %s", skill_slug, exc, exc_info=True)
            yield {"type": "error", "error": str(exc), "skill": skill_slug}

    # ------------------------------------------------------------------
    # Public API – Vercel AI SDK Data Stream Protocol streaming
    # ------------------------------------------------------------------
    def stream_ai_sdk(
        self,
        skill_slug: str,
        user_message: str,
        *,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None,
        extra_context: str = "",
    ) -> Generator[str, None, None]:
        """
        Stream response in Vercel AI SDK Data Stream Protocol format.

        Yields pre-formatted JSON strings::

            {"type":"start","messageId":"msg_…"}\\n
            {"type":"text-start","id":"text_…"}\\n
            {"type":"text-delta","id":"text_…","delta":"chunk of text"}\\n
            {"type":"text-end","id":"text_…"}\\n
            {"type":"finish","finishReason":"stop"}\\n
        """
        skill = self._resolve_skill(skill_slug)
        sys_prompt = self._build_system_prompt(skill, system_prompt, extra_context)
        messages = self._build_messages(user_message, conversation_history)
        tokens = max_tokens or skill.max_tokens

        start = time.time()
        full_text = ""
        message_id = f"msg_{int(time.time() * 1000)}"
        text_id = f"text_{int(time.time() * 1000)}"

        try:
            yield json.dumps({"type": "start", "messageId": message_id}) + "\n"

            with self.client.messages.stream(
                model=self.model,
                max_tokens=tokens,
                system=sys_prompt,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    full_text += text

                final_msg = stream.get_final_message()

            elapsed = time.time() - start

            if full_text:
                yield json.dumps({"type": "text-start", "id": text_id}) + "\n"
                yield json.dumps({"type": "text-delta", "id": text_id, "delta": full_text}) + "\n"
                yield json.dumps({"type": "text-end", "id": text_id}) + "\n"

            usage = {"promptTokens": 0, "completionTokens": 0}
            if final_msg and hasattr(final_msg, "usage"):
                usage = {
                    "promptTokens": final_msg.usage.input_tokens,
                    "completionTokens": final_msg.usage.output_tokens,
                }

            yield json.dumps({
                "type": "finish",
                "finishReason": "stop",
                "usage": usage,
                "skill": skill.slug,
                "skillName": skill.name,
                "executionTime": round(elapsed, 2),
            }) + "\n"

        except Exception as exc:
            logger.error("Skill %s AI SDK stream error: %s", skill_slug, exc, exc_info=True)
            yield json.dumps({"type": "error", "errorText": str(exc)}) + "\n"

    # ------------------------------------------------------------------
    # Multi-skill execution
    # ------------------------------------------------------------------
    def execute_multi(self, skill_requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute multiple skills sequentially and collect results."""
        results = []
        for req in skill_requests:
            slug = req["skill_slug"]
            message = req["message"]
            try:
                result = self.execute(
                    slug,
                    message,
                    system_prompt=req.get("system_prompt"),
                    max_tokens=req.get("max_tokens"),
                    extra_context=req.get("extra_context", ""),
                )
                results.append(result)
            except Exception as exc:
                results.append({"skill": slug, "error": str(exc), "text": ""})
        return results

    # ------------------------------------------------------------------
    # Async wrappers for FastAPI / asyncio contexts
    # ------------------------------------------------------------------
    async def execute_async(
        self,
        skill_slug: str,
        user_message: str,
        *,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None,
        extra_context: str = "",
    ) -> Dict[str, Any]:
        """Async wrapper around execute() for use in FastAPI routes."""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.execute(
                skill_slug,
                user_message,
                system_prompt=system_prompt,
                conversation_history=conversation_history,
                max_tokens=max_tokens,
                extra_context=extra_context,
            ),
        )

    async def execute_multi_async(self, skill_requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Async wrapper around execute_multi() for use in FastAPI routes."""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.execute_multi(skill_requests))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_skill(slug: str) -> SkillDefinition:
        """Look up a skill or raise ValueError."""
        skill = get_skill(slug)
        if skill is None:
            available = ", ".join(sorted(SKILL_REGISTRY.keys()))
            raise ValueError(f"Unknown skill '{slug}'. Available skills: {available}")
        if not skill.enabled:
            raise ValueError(f"Skill '{slug}' is currently disabled.")
        return skill

    @staticmethod
    def _build_system_prompt(
        skill: SkillDefinition,
        override: Optional[str],
        extra_context: str,
    ) -> str:
        prompt = override or skill.system_prompt or ""
        if extra_context:
            prompt += f"\n\n## Additional Context\n{extra_context}"
        return prompt

    @staticmethod
    def _build_messages(
        user_message: str,
        history: Optional[List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return messages
