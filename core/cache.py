"""
Unified cache layer (Redis with in-process LRU fallback).

Design goals:
    * One import line in callers: ``from core.cache import cache``.
    * Never raise on cache miss / cache-down — degrade silently.
    * JSON-serializable values only (keeps Redis + in-proc fallback identical).
    * Async API; safe to call from FastAPI handlers.

Usage:
    from core.cache import cache

    val = await cache.get("user:123")
    await cache.set("user:123", {"id": 123}, ttl=300)
    await cache.delete("user:123")

    # Memoize an expensive coroutine:
    @cache.memoize(ttl=60, key=lambda uid: f"profile:{uid}")
    async def load_profile(uid: str) -> dict: ...
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Callable, Optional

from config import get_settings

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis  # type: ignore
    _REDIS_AVAILABLE = True
except Exception:  # pragma: no cover
    aioredis = None  # type: ignore
    _REDIS_AVAILABLE = False


# ── In-process LRU+TTL fallback ───────────────────────────────────────────────

class _LRUTTLCache:
    """Tiny thread-unsafe (but asyncio-safe) LRU + TTL cache."""

    def __init__(self, maxsize: int = 4096) -> None:
        self.maxsize = maxsize
        self._store: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()

    def get(self, key: str) -> Any:
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at and expires_at < time.time():
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: Optional[int]) -> None:
        expires_at = (time.time() + ttl) if ttl else 0
        self._store[key] = (expires_at, value)
        self._store.move_to_end(key)
        while len(self._store) > self.maxsize:
            self._store.popitem(last=False)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()


# ── Cache facade ──────────────────────────────────────────────────────────────

class Cache:
    """
    Redis-backed cache with transparent in-process fallback.

    All methods are best-effort: any underlying error is logged and ``None`` is
    returned (for get) or silently swallowed (for set/delete). This keeps cache
    issues from cascading into request failures.
    """

    def __init__(self) -> None:
        self._redis: Optional["aioredis.Redis"] = None  # type: ignore
        self._local = _LRUTTLCache()
        self._init_lock = asyncio.Lock()
        self._init_attempted = False

    async def _ensure_redis(self) -> Optional["aioredis.Redis"]:
        if self._redis is not None or self._init_attempted:
            return self._redis
        async with self._init_lock:
            if self._init_attempted:
                return self._redis
            self._init_attempted = True
            settings = get_settings()
            if not settings.enable_redis_cache or not settings.redis_url or not _REDIS_AVAILABLE:
                if not settings.redis_url:
                    logger.info("Redis URL not set — using in-process cache only.")
                return None
            try:
                self._redis = aioredis.from_url(
                    settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                    health_check_interval=30,
                )
                # Sanity ping
                await asyncio.wait_for(self._redis.ping(), timeout=2)
                logger.info("Redis cache connected.")
            except Exception as exc:
                logger.warning("Redis unavailable, falling back to in-process cache: %s", exc)
                self._redis = None
        return self._redis

    # ── core ops ───────────────────────────────────────────────────────────

    async def get(self, key: str) -> Any:
        # in-proc first (microsecond hit); then redis
        val = self._local.get(key)
        if val is not None:
            return val
        r = await self._ensure_redis()
        if r is None:
            return None
        try:
            raw = await r.get(key)
            if raw is None:
                return None
            value = json.loads(raw)
            # Mirror into local cache briefly to avoid repeated round-trips.
            self._local.set(key, value, ttl=30)
            return value
        except Exception as exc:
            logger.debug("cache.get(%s) failed: %s", key, exc)
            return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        # Always populate local mirror
        self._local.set(key, value, ttl=min(ttl, 60))
        r = await self._ensure_redis()
        if r is None:
            return
        try:
            await r.set(key, json.dumps(value, default=str), ex=ttl)
        except Exception as exc:
            logger.debug("cache.set(%s) failed: %s", key, exc)

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self._local.delete(k)
        r = await self._ensure_redis()
        if r is None or not keys:
            return
        try:
            await r.delete(*keys)
        except Exception as exc:
            logger.debug("cache.delete failed: %s", exc)

    async def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching a Redis glob pattern (e.g. ``user:123:*``)."""
        r = await self._ensure_redis()
        if r is None:
            return 0
        try:
            deleted = 0
            async for key in r.scan_iter(match=pattern, count=500):
                await r.delete(key)
                deleted += 1
            return deleted
        except Exception as exc:
            logger.debug("cache.delete_pattern failed: %s", exc)
            return 0

    # ── decorator ──────────────────────────────────────────────────────────

    def memoize(
        self,
        ttl: int = 60,
        key: Optional[Callable[..., str]] = None,
        prefix: Optional[str] = None,
    ):
        """Decorator to memoize an async function's return value.

        ``key`` builds the cache key from the args; if omitted, repr(args, kwargs).
        """

        def decorator(func: Callable):
            fn_prefix = prefix or f"memo:{func.__module__}.{func.__qualname__}"

            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                try:
                    if key is not None:
                        suffix = key(*args, **kwargs)
                    else:
                        suffix = repr((args, sorted(kwargs.items())))
                    cache_key = f"{fn_prefix}:{suffix}"
                except Exception:
                    return await func(*args, **kwargs)

                cached = await self.get(cache_key)
                if cached is not None:
                    return cached

                value = await func(*args, **kwargs)
                if value is not None:
                    await self.set(cache_key, value, ttl=ttl)
                return value

            return wrapper

        return decorator

    async def close(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.close()
            except Exception:
                pass
            self._redis = None


# Module-level singleton
cache = Cache()
