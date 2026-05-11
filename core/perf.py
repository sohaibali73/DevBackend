"""
Lightweight per-request performance instrumentation.

Adds a ``Server-Timing`` HTTP header to every non-streaming response so the
browser DevTools "Timings" tab shows exactly where the request spent its
time. Zero overhead when nothing is recorded; ~1 µs per measurement.

Usage:
    from core.perf import perf

    @router.get("/something")
    async def something():
        with perf.span("db"):
            row = await asyncio.to_thread(blocking_query)
        with perf.span("llm"):
            answer = await call_llm(row)
        return {"answer": answer}

    # Response will include:
    #   Server-Timing: db;dur=42.3, llm;dur=812.5

The middleware also auto-adds a ``total;dur=<ms>`` measurement for every
request.
"""

from __future__ import annotations

import contextlib
import contextvars
import time
from typing import Iterator, List, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp


# Per-request list of (label, duration_ms) entries.
_perf_ctx: contextvars.ContextVar[List[Tuple[str, float]]] = contextvars.ContextVar(
    "_perf_ctx", default=None  # type: ignore
)


class _Perf:
    @contextlib.contextmanager
    def span(self, label: str) -> Iterator[None]:
        """Record the wall-clock duration of the with-block as ``label``."""
        ctx = _perf_ctx.get()
        if ctx is None:
            # No middleware active; act as a no-op.
            yield
            return
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            ctx.append((label, elapsed_ms))

    def record(self, label: str, duration_ms: float) -> None:
        """Record an externally-measured duration."""
        ctx = _perf_ctx.get()
        if ctx is not None:
            ctx.append((label, duration_ms))


perf = _Perf()


class PerfMiddleware(BaseHTTPMiddleware):
    """Attach a Server-Timing header to each response.

    Streaming responses are passed through unchanged — the header is set on
    the initial response message before chunks start flowing, so it's visible
    in DevTools immediately.
    """

    async def dispatch(self, request: Request, call_next):
        token = _perf_ctx.set([])
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            spans = _perf_ctx.get()
            _perf_ctx.reset(token)

        total_ms = (time.perf_counter() - start) * 1000.0
        parts = [f"total;dur={total_ms:.1f}"]
        if spans:
            # Sanitize label characters per Server-Timing spec — keep it
            # ASCII alpha-numeric + hyphen/underscore.
            for label, dur in spans:
                safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:32]
                parts.append(f"{safe};dur={dur:.1f}")
        try:
            response.headers["Server-Timing"] = ", ".join(parts)
            # Expose so JS can read it from CORS responses
            existing_expose = response.headers.get("Access-Control-Expose-Headers", "")
            if "Server-Timing" not in existing_expose:
                response.headers["Access-Control-Expose-Headers"] = (
                    (existing_expose + ", Server-Timing") if existing_expose else "Server-Timing"
                )
        except Exception:
            pass
        return response
