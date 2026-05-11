"""
Async, cached Voyage AI embeddings.

Replaces the blocking ``urllib`` calls in ``core/rag_chunker.py`` for hot-path
retrieval. Two big wins:

1. **Async** — uses the shared ``httpx.AsyncClient`` (HTTP/2 + keep-alive), so
   embedding a query doesn't block the FastAPI event loop and reuses TCP
   connections.

2. **Cached** — embeddings are deterministic for a given (model, text), so we
   cache them in Redis keyed on ``sha1(text)``. Re-embedding the same text
   (RAG query repetition, re-indexing identical chunks) is now free.

Usage:
    from core.embeddings import embed_one, embed_many

    vec = await embed_one("user query")
    vecs = await embed_many(["chunk 1", "chunk 2", ...])
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from typing import List, Optional, Sequence

from core.cache import cache
from core.http_client import get_http_client

logger = logging.getLogger(__name__)

VOYAGE_BATCH_SIZE = 64
VOYAGE_TIMEOUT = 30
VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
DEFAULT_MODEL = "voyage-2"
# Cache embeddings for 30 days — they never change for a given model+text.
_CACHE_TTL = 60 * 60 * 24 * 30


def _key(text: str, model: str) -> str:
    h = hashlib.sha1(f"{model}::{text}".encode("utf-8")).hexdigest()
    return f"emb:{model}:{h}"


async def embed_many(
    texts: Sequence[str],
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
) -> List[Optional[List[float]]]:
    """Return embeddings for *texts*, using cache + batched HTTP."""
    api_key = api_key or os.getenv("VOYAGE_API_KEY")
    if not api_key:
        return [None] * len(texts)

    out: List[Optional[List[float]]] = [None] * len(texts)

    # ── 1. Cache lookup ────────────────────────────────────────────────────
    miss_idx: List[int] = []
    miss_texts: List[str] = []
    for i, t in enumerate(texts):
        if not t:
            continue
        cached = await cache.get(_key(t, model))
        if cached is not None:
            out[i] = cached
        else:
            miss_idx.append(i)
            miss_texts.append(t[:8000])  # Voyage per-input limit

    if not miss_texts:
        return out

    # ── 2. Fetch misses in batches ─────────────────────────────────────────
    client = await get_http_client()

    async def _batch(start: int):
        batch = miss_texts[start : start + VOYAGE_BATCH_SIZE]
        try:
            resp = await client.post(
                VOYAGE_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"input": batch, "model": model},
                timeout=VOYAGE_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            for j, item in enumerate(data):
                emb = item.get("embedding")
                if emb is None:
                    continue
                local_i = start + j
                if local_i >= len(miss_texts):
                    continue
                src_idx = miss_idx[local_i]
                out[src_idx] = emb
                await cache.set(_key(miss_texts[local_i], model), emb, ttl=_CACHE_TTL)
        except Exception as exc:
            logger.warning("Voyage embed batch (start=%d) failed: %s", start, exc)

    await asyncio.gather(*[_batch(s) for s in range(0, len(miss_texts), VOYAGE_BATCH_SIZE)])
    return out


async def embed_one(
    text: str,
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
) -> Optional[List[float]]:
    res = await embed_many([text], model=model, api_key=api_key)
    return res[0] if res else None
