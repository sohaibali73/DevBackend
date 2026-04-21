"""
core/yang/completion_verifier.py — Double-Check Completion Verifier
====================================================================
After the primary assistant response is fully assembled, a secondary
Haiku LLM call checks whether the response satisfies the original user
request.  If it doesn't, the critique is appended and the model gets one
more turn to correct itself.

Design:
- Hooks on `stop_reason = "end_turn"` (the main chat flow, not a tool).
- Verifier model: Haiku (cheap, ~0.5–2 s overhead).
- One retry only (two total attempts).  The second attempt always passes
  regardless of the verifier verdict — prevents infinite loops.
- On verifier failure (timeout, API error): log + accept original response.
- The retry is streamed to the user so they see the correction in real time.

Protocol:
  1. Verifier call:
       System: "Reply VERIFIED if the response fully satisfies the user's
                request.  Otherwise list 1-3 specific unmet requirements in
                ≤100 words."
       User:   "<original_request>…</original_request>\n
                <proposed_response>…</proposed_response>"
  2. If response == "VERIFIED": done, accept original.
  3. If response != "VERIFIED": return (False, critique_text).
  4. Caller streams a separator, appends critique to messages, runs one
     more Claude streaming turn, replaces accumulated_content.

Usage (from api/routes/chat.py):
    from core.yang.completion_verifier import verify_completion

    is_ok, critique = await verify_completion(
        user_message=data.content,
        final_text=accumulated_content,
        api_key=api_keys["claude"],
        yang_cfg=yang_cfg,
    )
    if not is_ok and critique:
        # stream separator + do retry turn
        ...
"""

import asyncio
import logging
from typing import Any, Tuple

logger = logging.getLogger(__name__)

# Sentinel returned by the verifier when the response is accepted
_VERIFIED_SENTINEL = "VERIFIED"

# Maximum characters of the assistant response sent to the verifier
# (keeps the Haiku input small and the call cheap)
_MAX_RESPONSE_CHARS = 4000


async def verify_completion(
    user_message: str,
    final_text: str,
    api_key: str,
    yang_cfg: Any,
    timeout_s: float = 15.0,
) -> Tuple[bool, str]:
    """
    Run the double-check verifier and return (is_verified, critique).

    Args:
        user_message:  The original user message from the request.
        final_text:    The assistant's proposed final response.
        api_key:       Claude API key (uses Haiku model).
        yang_cfg:      YangConfig (provides double_check_model).
        timeout_s:     How long to wait for the verifier call before giving up.

    Returns:
        (True,  "")           — response passes verification.
        (False, critique_str) — response has gaps; critique describes them.
        (True,  "")           — also returned on any error (safe fallback).
    """
    if not api_key or not final_text.strip():
        return True, ""  # nothing to verify

    # Truncate long responses to keep the verifier call cheap
    truncated = final_text[:_MAX_RESPONSE_CHARS]
    if len(final_text) > _MAX_RESPONSE_CHARS:
        truncated += "\n… [response truncated for verification]"

    # Strip any would-be closing tags from user content so a malicious prompt
    # can't break out of the <original_request> / <proposed_response> wrapper
    # and inject a fake "VERIFIED" into the verifier's input.
    def _safe(s: str) -> str:
        return (
            s.replace("</original_request>", "[/original_request]")
             .replace("</proposed_response>", "[/proposed_response]")
             .replace("<original_request>", "[original_request]")
             .replace("<proposed_response>", "[proposed_response]")
        )

    prompt = (
        f"<original_request>\n{_safe(user_message[:500])}\n</original_request>\n\n"
        f"<proposed_response>\n{_safe(truncated)}\n</proposed_response>"
    )


    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_call_verifier, api_key, yang_cfg, prompt),
            timeout=timeout_s,
        )
        verdict = result.strip()

        if verdict == _VERIFIED_SENTINEL:
            logger.debug("double_check: VERIFIED")
            return True, ""

        logger.info("double_check: critique received — %s", verdict[:120])
        return False, verdict

    except asyncio.TimeoutError:
        logger.warning("double_check: verifier timed out after %.1f s — accepting", timeout_s)
        return True, ""
    except Exception as e:
        logger.warning("double_check: verifier error (non-fatal) — %s", e)
        return True, ""


def _call_verifier(api_key: str, yang_cfg: Any, prompt: str) -> str:
    """
    Synchronous Haiku call (runs in thread-pool via asyncio.to_thread).
    Returns the raw text of the verifier response.
    """
    import anthropic as _anth

    client = _anth.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=yang_cfg.double_check_model,
        max_tokens=256,
        system=(
            "You are a strict requirement checker. "
            f"Reply EXACTLY '{_VERIFIED_SENTINEL}' (nothing else) if the proposed "
            "response fully satisfies the original request. "
            "If requirements are unmet, list them in ≤100 words. "
            "Do NOT be lenient — only reply VERIFIED if the response is genuinely complete."
        ),
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text if response.content else _VERIFIED_SENTINEL
