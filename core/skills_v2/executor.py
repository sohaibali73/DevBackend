"""
Skill Executor
==============
Executes a skill workflow using a sub-agent conversation.

The executor:
1. Takes the skill definition + user message
2. Creates a sub-conversation with the skill's system prompt
3. Runs a multi-turn tool loop with the SAME provider
4. Returns the result (text, files, etc.)
"""

import json
import logging
import time
import asyncio
from typing import Dict, Any, List, Optional

from core.llm.base import BaseLLMProvider, LLMResponse
from core.skills_v2.base import SkillDefinition
from core.sandbox.manager import SandboxManager

logger = logging.getLogger(__name__)


class SkillExecutor:
    """
    Executes a skill workflow using a sub-agent conversation.

    The same provider that initiated the parent call is used
    for the skill's sub-agent. Tools are provided by the sandbox
    and other handlers.
    """

    def __init__(self, provider: BaseLLMProvider, sandbox_manager: SandboxManager):
        self.provider = provider
        self.sandbox = sandbox_manager

    async def execute(
        self,
        skill: SkillDefinition,
        message: str,
        context: str = "",
        conversation_history: Optional[List[Dict]] = None,
        model: str = "",
    ) -> Dict[str, Any]:
        """
        Execute a skill and return results.

        Args:
            skill: The skill to execute.
            message: User's request message.
            context: Additional context.
            conversation_history: Prior messages for context.
            model: Model to use (defaults to provider's default).

        Returns:
            Dict with success, text, files, usage, etc.
        """
        start_time = time.time()

        if not skill.enabled:
            return {"success": False, "error": f"Skill '{skill.slug}' is disabled"}

        # Build the system prompt
        system = skill.system_prompt
        if context:
            system += f"\n\n## Additional Context:\n{context}"

        # Build messages
        messages = list(conversation_history or [])
        messages.append({"role": "user", "content": message})

        # Get tools available to this skill
        tools = self._get_skill_tools(skill)

        # Run the tool loop
        try:
            result = await asyncio.wait_for(
                self._run_tool_loop(
                    system=system,
                    messages=messages,
                    tools=tools,
                    max_tokens=skill.max_tokens,
                    model=model,
                ),
                timeout=skill.timeout,
            )
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Skill execution timed out after {skill.timeout}s",
                "skill": skill.slug,
            }

        elapsed = round((time.time() - start_time) * 1000, 2)
        result["execution_time_ms"] = elapsed
        result["skill"] = skill.slug
        result["skill_name"] = skill.name

        return result

    async def _run_tool_loop(
        self,
        system: str,
        messages: List[Dict],
        tools: List[Dict],
        max_tokens: int,
        model: str,
    ) -> Dict[str, Any]:
        """
        Multi-turn tool loop: call model -> execute tools -> feed back.

        This is the CORE of the universal skill system.
        Works with ANY provider because tools are normalized.
        """
        accumulated_text = ""
        total_usage = {"input_tokens": 0, "output_tokens": 0}

        for iteration in range(10):  # max 10 tool rounds
            # Call the model
            kwargs = {}
            if model:
                kwargs["model"] = model

            response = await self.provider.chat(
                messages=messages,
                model=model or self._get_default_model(),
                system=system,
                tools=tools if tools else None,
                max_tokens=max_tokens,
                **kwargs,
            )

            # Accumulate usage
            for key in total_usage:
                total_usage[key] += response.usage.get(key, 0)

            # If text response, accumulate it
            if response.text:
                accumulated_text += response.text

            # If no tool calls, we're done
            if not response.tool_calls:
                return {
                    "success": True,
                    "text": accumulated_text,
                    "usage": total_usage,
                    "iterations": iteration + 1,
                }

            # Execute each tool call
            messages.append({
                "role": "assistant",
                "content": response.text or "",
            })

            for tc in response.tool_calls:
                tool_result = await self._execute_tool(tc)

                # Feed tool result back to model
                messages.append({
                    "role": "user",
                    "content": json.dumps({
                        "tool_result": tc["name"],
                        "tool_call_id": tc["id"],
                        "result": tool_result,
                    }),
                    })

        # Exhausted iterations
        return {
            "success": True,
            "text": accumulated_text,
            "usage": total_usage,
            "iterations": 10,
            "note": "Max iterations reached",
        }

    async def _execute_tool(self, tool_call: Dict) -> Any:
        """Execute a single tool call."""
        name = tool_call["name"]
        args = tool_call.get("args", {})

        try:
            if name == "execute_code" or name == "execute_python":
                lang = args.get("language", "python")
                code = args.get("code", "")
                result = await self.sandbox.execute(lang, code)
                return {
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                    "execution_time_ms": result.execution_time_ms,
                }

            elif name == "search_knowledge_base":
                from core.tools import search_knowledge_base
                return search_knowledge_base(
                    query=args.get("query", ""),
                    category=args.get("category"),
                    limit=args.get("limit", 3),
                )

            elif name == "get_stock_data":
                from core.tools import get_stock_data
                return get_stock_data(
                    symbol=args.get("symbol", ""),
                    period=args.get("period", "1mo"),
                    info_type=args.get("info_type", "price"),
                )

            else:
                # Try to find the tool in the existing tool dispatch
                from core.tools import handle_tool_call
                result_str = handle_tool_call(
                    tool_name=name,
                    tool_input=args,
                )
                return json.loads(result_str) if isinstance(result_str, str) else result_str

        except Exception as e:
            logger.error("Tool execution error for %s: %s", name, e)
            return {"error": str(e)}

    def _get_skill_tools(self, skill: SkillDefinition) -> List[Dict]:
        """Get tool definitions for a skill's required tools."""
        from core.tools import get_all_tools

        all_tools = get_all_tools()
        if not skill.required_tools:
            # If no specific tools required, provide execute_code + basics
            skill_tool_names = {"execute_code", "execute_python", "search_knowledge_base"}
        else:
            skill_tool_names = set(skill.required_tools)

        # Also include skill-specific tools
        skill_tool_names.add("execute_code")

        return [
            t for t in all_tools
            if t.get("name") in skill_tool_names
        ]

    def _get_default_model(self) -> str:
        """Get a default model for the current provider."""
        models = self.provider.supported_models
        return models[0] if models else ""