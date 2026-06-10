"""
Model router — pick the right (fastest/cheapest) model for each task.

Maps semantic task tags to concrete Claude/OpenAI model IDs. The router lets
us cheaply downshift trivial work (classification, routing, short summaries,
focus-chain updates) to Haiku without changing every call site.

Usage:
    from core.llm.router import pick_model, Task

    model = pick_model(Task.CLASSIFICATION)   # → "claude-haiku-4-5-20251001"
    model = pick_model(Task.CONTENT)          # → "claude-sonnet-4-5"
    model = pick_model(Task.REASONING)        # → "claude-opus-4-6"

Override per env var:
    LLM_MODEL_CLASSIFICATION=claude-sonnet-4-5   # force Sonnet for classifiers
    LLM_MODEL_CONTENT=...                        # etc
"""

from __future__ import annotations

import os
from enum import Enum


class Task(str, Enum):
    """Semantic task tags. Map → models in ``_DEFAULT_MAP`` below."""

    # Trivial / mechanical — Haiku
    CLASSIFICATION = "classification"
    ROUTING        = "routing"
    SHORT_SUMMARY  = "short_summary"
    FOCUS_CHAIN    = "focus_chain"
    EXTRACTION     = "extraction"
    EMBEDDING_PREP = "embedding_prep"
    VALIDATION     = "validation"

    # Real generation / chat — Sonnet
    CONTENT        = "content"
    AGENT          = "agent"
    TOOL_USE       = "tool_use"
    REVISION       = "revision"

    # Hard reasoning — Opus (only when explicitly asked)
    REASONING      = "reasoning"
    DEEP_ANALYSIS  = "deep_analysis"


# Cheap / fast
_HAIKU  = "claude-haiku-4-5-20251001"
# Default workhorse
_SONNET = "claude-sonnet-4-5"
# Hardest reasoning — Fable 5 (most capable widely-released model). Override with
# LLM_MODEL_REASONING / LLM_MODEL_DEEP_ANALYSIS to fall back to Opus if desired.
_FABLE  = "claude-fable-5"
_OPUS   = "claude-opus-4-6"


_DEFAULT_MAP: dict[Task, str] = {
    Task.CLASSIFICATION: _HAIKU,
    Task.ROUTING:        _HAIKU,
    Task.SHORT_SUMMARY:  _HAIKU,
    Task.FOCUS_CHAIN:    _HAIKU,
    Task.EXTRACTION:     _HAIKU,
    Task.EMBEDDING_PREP: _HAIKU,
    Task.VALIDATION:     _HAIKU,

    Task.CONTENT:        _SONNET,
    Task.AGENT:          _SONNET,
    Task.TOOL_USE:       _SONNET,
    Task.REVISION:       _SONNET,

    Task.REASONING:      _FABLE,
    Task.DEEP_ANALYSIS:  _FABLE,
}


def pick_model(task: Task | str) -> str:
    """Return the model ID to use for *task*.

    Env-var override: ``LLM_MODEL_<TASK_NAME_UPPER>``.
    Examples:
        LLM_MODEL_CLASSIFICATION=claude-sonnet-4-5
        LLM_MODEL_CONTENT=gpt-4.1
        LLM_MODEL_REASONING=claude-opus-4-6
    """
    t = task.value if isinstance(task, Task) else str(task).lower()
    env_key = f"LLM_MODEL_{t.upper()}"
    override = os.getenv(env_key)
    if override:
        return override

    try:
        return _DEFAULT_MAP[Task(t)]
    except Exception:
        # Unknown task → safe default
        return _SONNET


# Convenience shortcuts (so callers don't have to import the enum)
def haiku() -> str:  return _HAIKU
def sonnet() -> str: return _SONNET
def opus() -> str:   return _OPUS
def fable() -> str:  return _FABLE
