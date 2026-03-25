"""
Tool Registry
=============
Single source of truth for all tools available to any model.

Tools come from:
1. Existing core/tools.py definitions (built-in tools)
2. Skills (each skill registers as a tool via SkillRegistry)

The registry can normalize tools for any provider format.
"""

import json
import logging
from typing import Dict, Any, List, Optional, Callable

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Unified tool registry for all providers.

    Usage:
        registry = ToolRegistry()

        # Get tools for a specific provider
        tools = registry.get_tools_for_provider("openai")

        # Handle a tool call
        result = await registry.handle_tool_call("get_stock_data", {"symbol": "AAPL"})
    """

    def __init__(self):
        self._tools: Dict[str, Dict] = {}
        self._handlers: Dict[str, Callable] = {}
        self._initialized = False

    def _ensure_initialized(self):
        """Lazy-load built-in tools from core/tools.py."""
        if self._initialized:
            return
        self._initialized = True

        try:
            from core.tools import TOOL_DEFINITIONS, handle_tool_call

            # Convert existing tools to canonical format
            for tool in TOOL_DEFINITIONS:
                name = tool.get("name", "")
                if not name:
                    continue

                # Store in canonical format
                canonical = self._to_canonical(tool)
                if canonical:
                    self._tools[name] = canonical

            # Register the existing handle_tool_call as the dispatcher
            self._main_handler = handle_tool_call

            logger.info("Loaded %d built-in tools", len(self._tools))

        except Exception as e:
            logger.warning("Failed to load built-in tools: %s", e)
            self._main_handler = None

    def _to_canonical(self, tool: Dict) -> Optional[Dict]:
        """Convert any tool format to canonical format."""
        name = tool.get("name", "")
        description = tool.get("description", "")

        # Anthropic format
        if "input_schema" in tool:
            return {
                "name": name,
                "description": description,
                "parameters": tool["input_schema"],
            }

        # OpenAI format
        if tool.get("type") == "function" and "function" in tool:
            func = tool["function"]
            return {
                "name": func.get("name", name),
                "description": func.get("description", description),
                "parameters": func.get("parameters", {"type": "object", "properties": {}}),
            }

        # Canonical format (already has parameters)
        if "parameters" in tool:
            return {
                "name": name,
                "description": description,
                "parameters": tool["parameters"],
            }

        # Built-in type (web_search, etc.)
        if tool.get("type", "").startswith("web_search"):
            return tool

        return None

    def get_tools_for_provider(self, provider_name: str) -> List[Dict]:
        """
        Return all tools normalized for a specific provider.

        Args:
            provider_name: "anthropic", "openai", or "openrouter"
        """
        self._ensure_initialized()
        tools = list(self._tools.values())

        if provider_name == "anthropic":
            return self._normalize_anthropic(tools)
        elif provider_name in ("openai", "openrouter"):
            return self._normalize_openai(tools)
        else:
            return tools

    def _normalize_anthropic(self, tools: List[Dict]) -> List[Dict]:
        """Canonical → Anthropic format."""
        converted = []
        for tool in tools:
            if tool.get("type", "").startswith("web_search"):
                converted.append(tool)
            elif "parameters" in tool:
                converted.append({
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": tool["parameters"],
                })
            else:
                converted.append(tool)
        return converted

    def _normalize_openai(self, tools: List[Dict]) -> List[Dict]:
        """Canonical → OpenAI format."""
        converted = []
        for tool in tools:
            # Skip Anthropic built-in tools
            tool_type = tool.get("type", "")
            if tool_type.startswith("web_search"):
                continue
            if tool_type in ("tool_search_tool_regex", "tool_search_tool_bm25"):
                continue

            if "parameters" in tool:
                converted.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool["parameters"],
                    },
                })
        return converted

    async def handle_tool_call(
        self,
        name: str,
        args: Dict[str, Any],
        supabase_client=None,
        api_key: str = None,
    ) -> str:
        """
        Dispatch a tool call and return a JSON string.

        Uses the existing core/tools.py handle_tool_call for compatibility.
        """
        self._ensure_initialized()

        if self._main_handler:
            return self._main_handler(
                tool_name=name,
                tool_input=args,
                supabase_client=supabase_client,
                api_key=api_key,
            )

        return json.dumps({"error": f"Unknown tool: {name}"})

    def register_tool(self, tool_def: Dict, handler: Optional[Callable] = None):
        """Register a custom tool."""
        canonical = self._to_canonical(tool_def)
        if canonical:
            self._tools[canonical["name"]] = canonical
            if handler:
                self._handlers[canonical["name"]] = handler

    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        self._ensure_initialized()
        return list(self._tools.keys())

    def get_tool(self, name: str) -> Optional[Dict]:
        """Get a tool definition by name."""
        self._ensure_initialized()
        return self._tools.get(name)