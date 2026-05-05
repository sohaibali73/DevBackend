"""
Thin Anthropic call helper used by humanizer passes.

Centralized so we can later swap to OpenRouter / OpenAI without touching the
individual pass modules.

The default model is configurable via env var HUMANIZE_MODEL — set this to
a Haiku-class model in Railway for ~3x speedup with minimal quality loss
on rewrite tasks.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Default rewrite model — overridable via env. Haiku-class models are
# dramatically faster for the kind of constrained-rewrite passes the
# humanizer runs, with very small fidelity loss.
DEFAULT_MODEL = os.getenv("HUMANIZE_MODEL", "claude-haiku-4-5-20251001")
FALLBACK_MODEL = os.getenv("HUMANIZE_FALLBACK_MODEL", "claude-sonnet-4-20250514")


def claude_rewrite(
    *,
    api_key: str,
    user_prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 2200,
    temperature: float = 0.85,
    timeout_s: float = 45.0,
) -> str:
    """
    Single-turn Claude completion. Returns the assistant's text response,
    or "" on any failure (caller decides whether to fall back).

    Tries the configured fast model first, then falls back to a stronger
    one if the first attempt errors (e.g. model not available on the key).
    """
    if not api_key or not user_prompt:
        return ""
    chosen = model or DEFAULT_MODEL
    tried: list[str] = []
    last_err: Optional[Exception] = None
    for m in [chosen] + ([FALLBACK_MODEL] if FALLBACK_MODEL and FALLBACK_MODEL != chosen else []):
        if m in tried:
            continue
        tried.append(m)
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s)
            kwargs = {
                "model":       m,
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
            last_err = e
            logger.warning("claude_rewrite(model=%s) failed: %s", m, e)
            continue
    logger.warning("claude_rewrite exhausted models %s: %s", tried, last_err)
    return ""
