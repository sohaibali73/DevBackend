"""
Unified Tool Registry
=====================
Provider-agnostic tool definitions and dispatch for Yang.

All tools — built-in tools and skills-as-tools — are registered here.
The registry can normalize tools for any provider format.
"""

from core.tools_v2.registry import ToolRegistry

# Singleton
_registry: "ToolRegistry | None" = None


def get_tool_registry() -> ToolRegistry:
    """Get or create the singleton tool registry."""
    global _registry
    if _registry is not None:
        return _registry

    _registry = ToolRegistry()
    return _registry


__all__ = ["ToolRegistry", "get_tool_registry"]