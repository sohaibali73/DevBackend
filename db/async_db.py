"""
Async Postgres pool via asyncpg.

Connects directly to Supabase's transaction-mode pooler (port 6543) so we
bypass PostgREST entirely for hot-path reads/writes. The existing
``db.supabase_client.get_supabase()`` remains available for code paths that
need PostgREST/Storage/Auth features — but anything in the request hot path
should migrate to this module to keep the FastAPI event loop unblocked.

Usage:
    from db.async_db import get_pool, fetch_one, fetch_all, execute

    row = await fetch_one("SELECT * FROM user_profiles WHERE id = $1", user_id)
    rows = await fetch_all("SELECT id FROM files WHERE user_id = $1", user_id)
    await execute("UPDATE user_profiles SET last_active_at = now() WHERE id = $1", user_id)

Lifecycle:
    - Pool is created lazily on first use, or eagerly in main.py startup via
      ``await init_pool()``.
    - Close on shutdown via ``await close_pool()``.

The pool is process-local. Each gunicorn worker creates its own pool sized
``[async_db_pool_min, async_db_pool_max]``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Iterable, Optional

from config import get_settings

logger = logging.getLogger(__name__)

try:
    import asyncpg  # type: ignore
    _ASYNCPG_AVAILABLE = True
except Exception as _exc:  # pragma: no cover
    asyncpg = None  # type: ignore
    _ASYNCPG_AVAILABLE = False
    logger.warning("asyncpg not available — hot-path DB queries will use the sync Supabase client (%s)", _exc)

_pool = None  # type: ignore
_pool_lock = asyncio.Lock()



async def init_pool():
    """Eagerly create the pool. Safe to call multiple times."""
    global _pool
    if _pool is not None:
        return _pool

    if not _ASYNCPG_AVAILABLE:
        return None

    settings = get_settings()
    dsn = settings.supabase_db_url
    if not dsn:
        logger.warning(
            "SUPABASE_DB_URL is not set — asyncpg pool disabled. "
            "Hot-path queries will fall back to the sync Supabase client."
        )
        return None


    async with _pool_lock:
        if _pool is not None:
            return _pool
        try:
            _pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=settings.async_db_pool_min,
                max_size=settings.async_db_pool_max,
                command_timeout=60,
                # Supabase pooler in transaction mode does NOT support
                # session-level features (LISTEN/NOTIFY, prepared statements
                # outside a single statement). Disable statement cache to
                # avoid "prepared statement does not exist" errors.
                statement_cache_size=0,
                # Connections from the pooler are short-lived; recycle
                # ours every 30 min to stay healthy.
                max_inactive_connection_lifetime=1800,
            )
            logger.info(
                "asyncpg pool ready (min=%d, max=%d)",
                settings.async_db_pool_min,
                settings.async_db_pool_max,
            )
        except Exception as exc:
            logger.error("Failed to create asyncpg pool: %s", exc, exc_info=True)
            _pool = None
    return _pool


async def get_pool():
    """Return the pool, creating it on first call. Returns None if not configured."""
    if not _ASYNCPG_AVAILABLE:
        return None
    if _pool is None:
        return await init_pool()
    return _pool



async def close_pool() -> None:
    """Close the pool on application shutdown."""
    global _pool
    if _pool is not None:
        try:
            await _pool.close()
            logger.info("asyncpg pool closed")
        except Exception as exc:
            logger.warning("Error closing asyncpg pool: %s", exc)
        finally:
            _pool = None


# ── Convenience helpers ────────────────────────────────────────────────────────

async def fetch_one(query: str, *args: Any) -> Optional[dict]:
    """Run a SELECT and return the first row as a dict, or None."""
    pool = await get_pool()
    if pool is None:
        raise RuntimeError("async DB pool not configured (SUPABASE_DB_URL missing)")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None


async def fetch_all(query: str, *args: Any) -> list[dict]:
    """Run a SELECT and return all rows as a list of dicts."""
    pool = await get_pool()
    if pool is None:
        raise RuntimeError("async DB pool not configured (SUPABASE_DB_URL missing)")
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *args)
        return [dict(r) for r in rows]


async def fetch_val(query: str, *args: Any) -> Any:
    """Run a SELECT returning a single scalar."""
    pool = await get_pool()
    if pool is None:
        raise RuntimeError("async DB pool not configured (SUPABASE_DB_URL missing)")
    async with pool.acquire() as conn:
        return await conn.fetchval(query, *args)


async def execute(query: str, *args: Any) -> str:
    """Run an INSERT/UPDATE/DELETE. Returns the status string."""
    pool = await get_pool()
    if pool is None:
        raise RuntimeError("async DB pool not configured (SUPABASE_DB_URL missing)")
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


async def executemany(query: str, args_iter: Iterable[Iterable[Any]]) -> None:
    """Batch INSERT/UPDATE."""
    pool = await get_pool()
    if pool is None:
        raise RuntimeError("async DB pool not configured (SUPABASE_DB_URL missing)")
    async with pool.acquire() as conn:
        await conn.executemany(query, list(args_iter))


def is_configured() -> bool:
    """True iff asyncpg is installed AND SUPABASE_DB_URL is set."""
    return _ASYNCPG_AVAILABLE and bool(get_settings().supabase_db_url)

