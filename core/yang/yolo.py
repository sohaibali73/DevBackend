"""
core/yang/yolo.py — Yolo Mode Gate
===================================
When Yolo Mode is active:

1. Plan Mode is OVERRIDDEN — all tools are allowed (Yolo wins).
2. The `ask_followup_question` tool is removed from Claude's tool list so
   the model never pauses to ask for confirmation.
3. `max_iterations` is capped at 10 to prevent runaway loops.
4. A `data-yolo-active` stream event is emitted so the frontend can display
   a warning banner.
5. A checkpoint is auto-created BEFORE execution begins (safety net).

Safety guarantees:
- Yolo mode NEVER disables the YANG checkpoint system — if checkpoints are
  on, a pre-yolo snapshot is always taken before any tool is run.
- max_iterations cap is non-negotiable (cannot be raised via overrides).
- If the cap is hit, a `data-yolo-capped` event is emitted with a clear
  message before the stream ends normally.

Usage (from api/routes/chat.py):
    from core.yang.yolo import filter_tools_for_yolo, YOLO_MAX_ITERATIONS

    if yang_cfg.yolo_mode:
        tools = filter_tools_for_yolo(tools)
        max_iterations = min(max_iterations, YOLO_MAX_ITERATIONS)
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Hard cap on iterations in Yolo mode — cannot be overridden.
YOLO_MAX_ITERATIONS: int = 10

# Tools that are hidden from Claude in Yolo mode.
# These tools ask for human confirmation / input, which defeats the purpose
# of no-confirmation execution.  Add any future "wait for user" tools here.
_YOLO_HIDDEN_TOOLS: frozenset = frozenset({
    "ask_followup_question",  # Ask user a clarifying question
    "ask_for_confirmation",   # future-proofing
    "request_approval",       # future-proofing
})


def filter_tools_for_yolo(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove confirmation / human-in-the-loop tools from the tool list.

    In Yolo mode Claude should never pause to ask the user a question.
    All other tools (including write/generate tools) remain available.

    NOTE: This does NOT apply plan_guard filtering — Yolo Mode overrides
    Plan Mode by design.  If plan_mode and yolo_mode are both True, Yolo wins
    (enforced by the chat route: plan guard is skipped when yolo_mode=True).

    Args:
        tools: Full tool list (may have already been filtered for tool search).

    Returns:
        Tools list with hidden tools removed. Never raises.
    """
    if not tools:
        return []

    filtered = [t for t in tools if t.get("name", "") not in _YOLO_HIDDEN_TOOLS]
    removed = len(tools) - len(filtered)

    if removed:
        logger.debug("yolo_mode: removed %d tool(s): %s", removed, _YOLO_HIDDEN_TOOLS & {t.get("name", "") for t in tools})

    logger.info("yolo_mode: %d/%d tools allowed (no confirmation tools)", len(filtered), len(tools))
    return filtered


def apply_yolo_iteration_cap(requested_max: int) -> int:
    """
    Enforce the Yolo iteration cap.

    Args:
        requested_max: The max_iterations from the request (or default 5).

    Returns:
        min(requested_max, YOLO_MAX_ITERATIONS)
    """
    capped = min(requested_max, YOLO_MAX_ITERATIONS)
    if capped < requested_max:
        logger.info(
            "yolo_mode: max_iterations capped at %d (requested %d)",
            capped, requested_max,
        )
    return capped


def get_yolo_stream_events(encoder: Any) -> List[str]:
    """
    Generate the stream events to emit when Yolo Mode is active.

    Args:
        encoder: VercelAIStreamEncoder instance (has encode_data method).

    Returns:
        List of encoded stream event strings to yield.
    """
    return [
        encoder.encode_data({
            "yang_yolo_active": True,
            "max_iterations": YOLO_MAX_ITERATIONS,
            "message": (
                "⚡ Yolo Mode active — executing without confirmation. "
                f"Max {YOLO_MAX_ITERATIONS} iterations. "
                "A checkpoint was saved before execution began."
            ),
        })
    ]


def get_yolo_cap_event(encoder: Any, iteration: int) -> str:
    """
    Generate the stream event to emit when the Yolo iteration cap is hit.

    Args:
        encoder: VercelAIStreamEncoder instance.
        iteration: The current iteration count when the cap was reached.

    Returns:
        Encoded stream event string.
    """
    return encoder.encode_data({
        "yang_yolo_capped": True,
        "iteration": iteration,
        "max_iterations": YOLO_MAX_ITERATIONS,
        "message": (
            f"⚡ Yolo Mode: iteration limit ({YOLO_MAX_ITERATIONS}) reached. "
            "Stopping to prevent runaway execution. "
            "Restore from the pre-yolo checkpoint if needed."
        ),
    })
