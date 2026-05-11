"""
Shared async HTTP client.

A single process-wide ``httpx.AsyncClient`` with connection pooling, HTTP/2,
sane timeouts, and keep-alive. Used by:

* LLM providers (Anthropic / OpenAI / OpenRouter / Vercel Gateway)
* Voyage embeddings
* Tavily / generic outbound HTTP

Why centralize:
    Creating a new ``httpx.Client`` per request triggers fresh TLS handshakes
    (50–200 ms) and prevents HTTP/2 multiplexing. A shared client reuses TCP
    connections and slashes per-call overhead.

Lifecycle:
    * ``await get_http_client()`` lazily constructs the client.
    * ``await close_http_client()`` at app shutdown.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from config import get_settings

logger = logging.getLogger(__name__)

_client: Optional[httpx.AsyncClient] = None
_lock = asyncio.Lock()


async def get_http_client() -> httpx.AsyncClient:
    """Return the shared httpx.AsyncClient, building it on first call."""
    global _client
    if _client is not None and not _client.is_closed:
        return _client
    async with _lock:
        if _client is not None and not _client.is_closed:
            return _client
        settings = get_settings()
        limits = httpx.Limits(
            max_connections=settings.llm_http_pool_size,
            max_keepalive_connections=settings.llm_http_pool_size,
            keepalive_expiry=30.0,
        )
        timeout = httpx.Timeout(connect=10.0, read=180.0, write=60.0, pool=10.0)
        try:
            _client = httpx.AsyncClient(
                http2=True,
                limits=limits,
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": "DevBackend/1.0 (+httpx)"},
            )
            logger.info(
                "Shared httpx.AsyncClient created (pool=%d, http2=True)",
                settings.llm_http_pool_size,
            )
        except Exception as exc:
            # http2 requires the 'h2' package; fall back to HTTP/1.1 if missing.
            logger.warning("HTTP/2 unavailable, falling back to HTTP/1.1: %s", exc)
            _client = httpx.AsyncClient(
                limits=limits,
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": "DevBackend/1.0 (+httpx)"},
            )
    return _client


async def close_http_client() -> None:
    global _client
    if _client is not None:
        try:
            await _client.aclose()
            logger.info("Shared httpx.AsyncClient closed")
        except Exception as exc:
            logger.warning("Error closing shared HTTP client: %s", exc)
        finally:
            _client = None
