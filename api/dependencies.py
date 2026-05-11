"""FastAPI dependencies for authentication and user context.

Performance notes:
    * JWT is now verified LOCALLY using ``SUPABASE_JWT_SECRET`` (HS256) — no
      Supabase round-trip on every authenticated request. Saves ~150–400 ms.
    * When the JWT secret is not configured we fall back to the slower
      ``supabase.auth.get_user()`` path, but cache that result in Redis for
      60s so repeat requests within the same minute are free.
    * User profile + API keys are also Redis-cached (60s) and read via
      asyncpg when available — no PostgREST round-trip in the hot path.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import get_settings
from core.cache import cache
from core.encryption import decrypt_value
from db import async_db
from db.supabase_client import get_auth_client, get_supabase

logger = logging.getLogger(__name__)
security = HTTPBearer()

# JWT cache TTL (seconds). Should be < typical token lifetime (Supabase = 1 h).
_JWT_CACHE_TTL = 300

# ── Local JWT verification (fast path) ─────────────────────────────────────────

try:
    import jwt as _pyjwt  # PyJWT
    _PYJWT_AVAILABLE = True
except Exception:  # pragma: no cover
    _pyjwt = None
    _PYJWT_AVAILABLE = False


def _verify_jwt_local(token: str) -> Optional[str]:
    """Verify a Supabase HS256 JWT locally. Returns the user id (``sub``) or None.

    Raises HTTPException(401, "token_expired") when the token is expired so the
    frontend can refresh.
    """
    settings = get_settings()
    secret = settings.supabase_jwt_secret
    if not secret or not _PYJWT_AVAILABLE:
        return None
    try:
        payload = _pyjwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"verify_aud": True, "require": ["sub", "exp"]},
        )
        return payload.get("sub")
    except _pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="token_expired",
            headers={"X-Token-Expired": "true"},
        )
    except _pyjwt.InvalidTokenError as exc:
        logger.debug("Local JWT verification failed: %s", exc)
        return None  # caller will try the Supabase fallback path


async def _verify_jwt_supabase(token: str) -> Optional[str]:
    """Slow-path: ask Supabase to verify the JWT. Cached for 60s."""
    cache_key = f"jwt:uid:{token[-32:]}"  # tail-suffix keeps key bounded
    cached = await cache.get(cache_key)
    if cached:
        return cached

    def _call():
        auth_db = get_auth_client()
        return auth_db.auth.get_user(token)

    try:
        result = await asyncio.to_thread(_call)
        if not result or not getattr(result, "user", None):
            return None
        uid = result.user.id
        await cache.set(cache_key, uid, ttl=60)
        return uid
    except Exception as exc:
        msg = str(exc).lower()
        if "expired" in msg:
            raise HTTPException(
                status_code=401,
                detail="token_expired",
                headers={"X-Token-Expired": "true"},
            )
        logger.error("Token validation failed: %s", exc)
        return None


# ── Public dependencies ───────────────────────────────────────────────────────

async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Extract and validate user ID from the bearer JWT."""
    token = credentials.credentials

    # 1. Try local JWT verification (fast path).
    uid = _verify_jwt_local(token)
    if uid:
        return uid

    # 2. Fall back to Supabase round-trip (cached).
    uid = await _verify_jwt_supabase(token)
    if uid:
        return uid

    raise HTTPException(status_code=401, detail="Invalid or expired token")


async def _fetch_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """Fetch user profile (cached). Uses asyncpg when available."""
    cache_key = f"user:profile:{user_id}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    profile: Optional[Dict[str, Any]] = None
    cols = (
        "id, name, nickname, is_admin, is_active, created_at, last_active_at, "
        "claude_api_key_encrypted, tavily_api_key_encrypted, "
        "openai_api_key_encrypted, openrouter_api_key_encrypted, "
        "preferred_provider, preferred_model"
    )

    if async_db.is_configured():
        try:
            profile = await async_db.fetch_one(
                f"SELECT {cols} FROM user_profiles WHERE id = $1::uuid",
                user_id,
            )
        except Exception as exc:
            logger.warning("asyncpg profile fetch failed, falling back: %s", exc)

    if profile is None:
        def _sync():
            db = get_supabase()
            r = db.table("user_profiles").select(cols).eq("id", user_id).execute()
            return r.data[0] if r.data else None

        try:
            profile = await asyncio.to_thread(_sync)
        except Exception as exc:
            logger.error("Supabase profile fetch failed: %s", exc)
            profile = None

    if profile:
        await cache.set(cache_key, profile, ttl=60)
    return profile


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    """Return the current user's public profile (no decrypted secrets)."""
    user_id = await get_current_user_id(credentials)

    profile = await _fetch_profile(user_id)

    if not profile:
        # Auto-create on first login (rare path; trigger usually handles this).
        def _insert():
            auth_db = get_auth_client()
            auth_user = auth_db.auth.get_user(credentials.credentials)
            email = (auth_user.user.email or "") if auth_user and auth_user.user else ""
            data = {
                "id": user_id,
                "name": (auth_user.user.user_metadata or {}).get("name") if auth_user and auth_user.user else None,
                "nickname": (auth_user.user.user_metadata or {}).get("nickname", email.split("@")[0]) if auth_user and auth_user.user else email.split("@")[0],
            }
            get_supabase().table("user_profiles").insert(data).execute()
            return data, email

        try:
            data, email = await asyncio.to_thread(_insert)
            profile = data
        except Exception as exc:
            logger.error("Auto-create profile failed: %s", exc)
            raise HTTPException(status_code=500, detail="Could not load user profile")
    else:
        email = ""  # not stored on profile; left empty for response

    if not profile.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account has been deactivated. Contact support.")

    return {
        "id": user_id,
        "email": email,
        "name": profile.get("name"),
        "nickname": profile.get("nickname"),
        "is_admin": profile.get("is_admin", False),
        "is_active": profile.get("is_active", True),
        "created_at": profile.get("created_at"),
        "last_active_at": profile.get("last_active_at"),
        "has_claude_key": bool(profile.get("claude_api_key_encrypted")),
        "has_tavily_key": bool(profile.get("tavily_api_key_encrypted")),
        "has_openai_key": bool(profile.get("openai_api_key_encrypted")),
        "has_openrouter_key": bool(profile.get("openrouter_api_key_encrypted")),
        "preferred_provider": profile.get("preferred_provider", "anthropic"),
        "preferred_model": profile.get("preferred_model", "claude-sonnet-4-20250514"),
    }


async def _fetch_api_keys_for_user(user_id: str) -> Dict[str, str]:
    """Decrypted API keys for a user. Cached for 60s (decrypted values stay in Redis)."""
    settings = get_settings()
    cache_key = f"user:keys:{user_id}"
    cached = await cache.get(cache_key)

    if cached is None:
        profile = await _fetch_profile(user_id)
        row = profile or {}

        def _dec(v: Optional[str]) -> str:
            if not v:
                return ""
            try:
                return decrypt_value(v)
            except Exception as exc:
                logger.warning("decrypt_value failed: %s", exc)
                return ""

        keys = {
            "claude": _dec(row.get("claude_api_key_encrypted")),
            "tavily": _dec(row.get("tavily_api_key_encrypted")),
            "openai": _dec(row.get("openai_api_key_encrypted")),
            "openrouter": _dec(row.get("openrouter_api_key_encrypted")),
        }
        cached = keys
        await cache.set(cache_key, keys, ttl=60)

    # Fallback to server-side keys
    claude = cached.get("claude") or settings.anthropic_api_key
    tavily = cached.get("tavily") or settings.tavily_api_key
    openai_k = cached.get("openai") or settings.openai_api_key
    openrouter = cached.get("openrouter") or settings.openrouter_api_key
    vercel_gw = settings.vercel_gateway_api_key

    return {
        "claude": claude or "",
        "tavily": tavily or "",
        "openai": openai_k or "",
        "openrouter": openrouter or "",
        "vercel_gateway": vercel_gw or "",
    }


async def get_user_api_keys(
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, str]:
    """Return the user's decrypted API keys (server-side fallbacks applied)."""
    return await _fetch_api_keys_for_user(user_id)


async def get_user_with_api_keys(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    """Return user profile + decrypted Claude / Tavily keys."""
    user = await get_current_user(credentials)
    api_keys = await _fetch_api_keys_for_user(user["id"])
    user["claude_api_key"] = api_keys["claude"]
    user["tavily_api_key"] = api_keys["tavily"]
    return user


async def verify_admin(user: Dict[str, Any] = Depends(get_current_user)) -> str:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user["id"]


async def invalidate_user_cache(user_id: str) -> None:
    """Call after the user updates their profile / API keys."""
    await cache.delete(f"user:profile:{user_id}", f"user:keys:{user_id}")
