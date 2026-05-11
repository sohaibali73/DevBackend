"""
Anthropic prompt-caching helpers.

Wrap large *static* prompt content (system prompts, tool definitions, RAG
context that doesn't change between turns) with ``cache_control: ephemeral``
so Anthropic caches the prefix server-side. Hits charge 10% of normal input
tokens AND cut TTFT (time-to-first-token) by 0.5–2 s.

Docs: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching

Usage — system prompt:

    from core.prompt_cache import as_cached_system

    system_blocks = as_cached_system(SYSTEM_PROMPT_BIG)
    response = await client.messages.create(
        model="claude-sonnet-4-5",
        system=system_blocks,            # list of blocks instead of str
        messages=messages,
    )

Usage — tool definitions:

    from core.prompt_cache import mark_tools_cached
    tools = mark_tools_cached(get_tools_for_api())

Caching threshold: Anthropic requires ≥1024 tokens (≈4000 chars) for Sonnet.
The helpers no-op when the input is too small.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Union

# Anthropic's minimum cacheable size for Sonnet/Opus (≈1024 tokens)
_MIN_CHARS_TO_CACHE = 4000

# Global kill switch (set ENABLE_PROMPT_CACHE=false to disable)
def _enabled() -> bool:
    v = os.getenv("ENABLE_PROMPT_CACHE", "true").lower()
    return v not in ("false", "0", "no", "off")


def as_cached_system(
    system: Union[str, List[Dict[str, Any]]],
    *,
    ttl: str = "5m",
) -> Union[str, List[Dict[str, Any]]]:
    """Convert a system prompt string into a cached-block list.

    Returns the original input unchanged if caching is disabled or the prompt
    is too small to benefit from caching.

    ``ttl`` can be ``"5m"`` (default) or ``"1h"`` (extended cache, beta).
    """
    if not _enabled():
        return system

    if isinstance(system, str):
        if len(system) < _MIN_CHARS_TO_CACHE:
            return system
        cache_ctrl: Dict[str, Any] = {"type": "ephemeral"}
        if ttl and ttl != "5m":
            cache_ctrl["ttl"] = ttl
        return [{"type": "text", "text": system, "cache_control": cache_ctrl}]

    # Already a list of blocks — add cache_control to the last text block.
    if isinstance(system, list) and system:
        out = list(system)
        for i in range(len(out) - 1, -1, -1):
            blk = out[i]
            if isinstance(blk, dict) and blk.get("type") == "text":
                text = blk.get("text", "")
                if len(text) >= _MIN_CHARS_TO_CACHE:
                    new_blk = dict(blk)
                    new_blk["cache_control"] = {"type": "ephemeral"}
                    out[i] = new_blk
                break
        return out
    return system


def mark_tools_cached(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach ``cache_control`` to the LAST tool so Anthropic caches the
    whole tool definitions block. (Only the last cache_control mark matters
    for the tools array — everything up to it is cached.)
    """
    if not _enabled() or not tools:
        return tools
    out = [dict(t) for t in tools]
    out[-1]["cache_control"] = {"type": "ephemeral"}
    return out


def mark_message_cached(
    message: Dict[str, Any],
    *,
    min_chars: int = _MIN_CHARS_TO_CACHE,
) -> Dict[str, Any]:
    """Add cache_control to a single user/assistant message containing a large
    content block (e.g. retrieved KB context, file contents). Returns the
    original message if it's too small.
    """
    if not _enabled():
        return message
    content = message.get("content")
    if isinstance(content, str):
        if len(content) < min_chars:
            return message
        return {
            **message,
            "content": [
                {
                    "type": "text",
                    "text": content,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
        }
    if isinstance(content, list) and content:
        new_content = [dict(b) if isinstance(b, dict) else b for b in content]
        # Find the largest text block and cache it.
        idx, size = -1, 0
        for i, blk in enumerate(new_content):
            if isinstance(blk, dict) and blk.get("type") == "text":
                txt = blk.get("text", "")
                if len(txt) > size:
                    size, idx = len(txt), i
        if idx >= 0 and size >= min_chars:
            new_content[idx]["cache_control"] = {"type": "ephemeral"}
            return {**message, "content": new_content}
    return message
