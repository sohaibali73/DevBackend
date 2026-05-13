"""
core.desktop_pending
====================

In-memory registry of *pending* desktop-agent tool calls.

When the Claude agent loop in ``/chat/agent`` emits a tool call whose name is
in :data:`core.desktop_tools.DESKTOP_TOOL_NAMES`, the server cannot execute
the tool itself — it has to be executed by the Electron client on the user's
machine. The server therefore:

1. Streams a ``tool-input-available`` UI Message Stream event to the client.
2. Pauses the agent loop on an :class:`asyncio.Future` that lives in this
   registry, keyed by ``(conversation_id, tool_call_id)``.
3. Resumes when the client POSTs the result back to
   ``POST /chat/agent/tool-result``, which calls :func:`resolve`.

The registry is **per-process / in-memory only**. Horizontal scaling on
Railway with multiple replicas would require a shared store (Redis pub/sub).
A single Railway dyno is fine for the current rollout.

A tiny background sweeper drops futures older than ``DEFAULT_TTL_SECONDS`` so
abandoned conversations don't leak memory if the client never replies.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Optional, Tuple

DEFAULT_TTL_SECONDS = 600  # 10 minutes — well beyond the 5-min wait budget


@dataclass
class PendingCall:
    future: asyncio.Future
    started_at: float
    tool_name: str = ""


# Keyed by (conversation_id, tool_call_id)
_pending: dict[Tuple[str, str], PendingCall] = {}
_lock = asyncio.Lock()  # purely defensive; CPython asyncio is single-threaded


def register(conv_id: str, call_id: str, tool_name: str = "") -> asyncio.Future:
    """
    Create and return a Future that will be completed when the desktop client
    POSTs a result for ``(conv_id, call_id)``.
    """
    loop = asyncio.get_event_loop()
    fut: asyncio.Future = loop.create_future()
    _pending[(conv_id, call_id)] = PendingCall(
        future=fut,
        started_at=time.time(),
        tool_name=tool_name,
    )
    return fut


def resolve(
    conv_id: str,
    call_id: str,
    result: Any,
    error: Optional[str],
) -> bool:
    """
    Complete a pending Future. Returns ``True`` if the key existed and the
    Future was completed (or was already done — we still pop it), ``False``
    if no such pending call was registered.
    """
    key = (conv_id, call_id)
    pc = _pending.pop(key, None)
    if pc is None:
        return False
    if pc.future.done():
        # Lost race with the agent loop's own timeout — that's fine.
        return True
    if error:
        # We *don't* raise on the agent side; instead we set_result with an
        # error envelope so the loop can feed `{"error": ...}` back to the
        # model and keep going. This matches the recipe's UX guidance:
        # "If a tool returns { error: "..." }, do not retry the same call".
        pc.future.set_result({"error": error})
    else:
        pc.future.set_result(result)
    return True


def cancel(conv_id: str, call_id: str) -> None:
    """Best-effort drop of a pending entry (used when the loop times out)."""
    pc = _pending.pop((conv_id, call_id), None)
    if pc and not pc.future.done():
        pc.future.set_exception(asyncio.CancelledError("desktop call cancelled"))


def sweep(now: Optional[float] = None, ttl: float = DEFAULT_TTL_SECONDS) -> int:
    """Drop expired pending entries. Returns count removed."""
    now = now or time.time()
    dropped = 0
    for key, pc in list(_pending.items()):
        if (now - pc.started_at) > ttl:
            _pending.pop(key, None)
            if not pc.future.done():
                pc.future.set_result(
                    {"error": f"client never returned result for {pc.tool_name or 'tool'}"}
                )
            dropped += 1
    return dropped


def size() -> int:
    """Number of pending desktop tool calls (diagnostics / health)."""
    return len(_pending)


# ---------------------------------------------------------------------------
# Optional background sweeper. Started lazily by ``ensure_sweeper_running()``
# from the agent loop. We don't auto-start at import time because there's no
# event loop yet at import.
# ---------------------------------------------------------------------------

_sweeper_task: Optional[asyncio.Task] = None


async def _sweep_loop():  # pragma: no cover - background coroutine
    while True:
        try:
            await asyncio.sleep(60)
            sweep()
        except asyncio.CancelledError:
            break
        except Exception:
            # Never let the sweeper die silently — but also never crash.
            pass


def ensure_sweeper_running() -> None:
    """Idempotently start the background sweeper on the current event loop."""
    global _sweeper_task
    if _sweeper_task and not _sweeper_task.done():
        return
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return
    _sweeper_task = loop.create_task(_sweep_loop())


# ---------------------------------------------------------------------------
# Future audit-table notes (recipe §7).  We deliberately do NOT create a
# migration here — the existing ``tool_results`` table already captures most
# of the fields and any addition is best done as a real DB migration through
# the team's normal process.  The columns we'd want are:
#
#     CREATE TABLE tool_invocations (
#       id BIGSERIAL PRIMARY KEY,
#       user_id BIGINT,
#       conversation_id TEXT,
#       tool_call_id TEXT,
#       tool_name TEXT,
#       client_kind TEXT,
#       status TEXT,
#       started_at TIMESTAMPTZ DEFAULT now(),
#       ended_at TIMESTAMPTZ,
#       error TEXT
#     );
# ---------------------------------------------------------------------------
