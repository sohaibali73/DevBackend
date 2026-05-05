"""
Thin Anthropic call helper used by humanizer passes.

Centralized so we can later swap to OpenRouter / OpenAI without touching the
individual pass modules.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def claude_rewrite(
    *,
    api_key: str,
    user_prompt: str,
    system_prompt: Optional[str] = None,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 2200,
    temperature: float = 0.85,
) -> str:
    """
    Single-turn Claude completion. Returns the assistant's text response,
    or "" on any failure (caller decides whether to fall back).
    """
    if not api_key or not user_prompt:
        return ""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        kwargs = {
            "model":       model,
            "max_tokens":  max_tokens,
            "temperature": temperature,
            "messages":    [{"role": "user", "content": user_prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        msg = client.messages.create(**kwargs)
        out = ""
        for block in msg.content:
            if getattr(block, "type", "") == "text":
                out += block.text
        return out.strip()
    except Exception as e:
        logger.warning("claude_rewrite failed: %s", e)
        return ""
