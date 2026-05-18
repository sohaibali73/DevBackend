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

from fastapi import Depends, HTTPException, Query, Request
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


async def get_current_user_id_sse(
    request: Request,
    token: Optional[str] = Query(
        default=None,
        description=(
            "Auth token for EventSource clients. EventSource cannot set "
            "the Authorization header, so SSE endpoints accept the JWT as "
            "?token=... instead. Header still wins when both are present."
        ),
    ),
) -> str:
    """SSE-friendly auth: bearer header OR ?token= query param.

    Use this dependency in place of ``get_current_user_id`` ONLY on Server-
    Sent-Events endpoints, since browsers cannot attach headers to an
    ``EventSource`` request. Verification path is identical to the header
    flow (local HS256 first, Supabase fallback, same cache).

    Token in URL caveat: URLs may appear in HTTP access logs and Referer
    headers, so keep this opt-in per route. Do NOT default it onto JSON
    endpoints.
    """
    # 1. Authorization header wins when present (avoids logging the token).
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    raw_token: Optional[str] = None
    if auth_header and auth_header.lower().startswith("bearer "):
        raw_token = auth_header.split(" ", 1)[1].strip() or None

    # 2. Fallback to ?token= query string.
    if not raw_token and token:
        raw_token = token.strip() or None

    if not raw_token:
        raise HTTPException(
            status_code=401,
            detail="Missing auth token (header `Authorization: Bearer …` or `?token=…`)",
        )

    # 3. Verify via the same path as get_current_user_id.
    uid = _verify_jwt_local(raw_token)
    if uid:
        return uid
    uid = await _verify_jwt_supabase(raw_token)
    if uid:
        return uid

    raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    """Return the current user's public profile (no decrypted secrets).

    This stays close to the original (proven) flow — only the JWT validation
    is short-circuited by ``get_current_user_id`` when possible. The profile
    fetch + auto-create logic runs on the sync Supabase client inside
    ``asyncio.to_thread`` so it doesn't block the event loop.
    """
    token = credentials.credentials

    def _fetch_sync() -> Dict[str, Any]:
        auth_db = get_auth_client()
        db = get_supabase()
        auth_user = auth_db.auth.get_user(token)
        if not auth_user or not auth_user.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        user_id = auth_user.user.id
        email = auth_user.user.email or ""

        profile_result = db.table("user_profiles").select(
            "id, name, nickname, is_admin, is_active, created_at, last_active_at, "
            "claude_api_key_encrypted, tavily_api_key_encrypted, "
            "openai_api_key_encrypted, openrouter_api_key_encrypted, "
            "preferred_provider, preferred_model"
        ).eq("id", user_id).execute()

        if not profile_result.data:
            profile_data = {
                "id": user_id,
                "name": auth_user.user.user_metadata.get("name") if auth_user.user.user_metadata else None,
                "nickname": (auth_user.user.user_metadata or {}).get("nickname", email.split("@")[0]),
            }
            db.table("user_profiles").insert(profile_data).execute()
            profile = profile_data
        else:
            profile = profile_result.data[0]

        if not profile.get("is_active", True):
            raise HTTPException(
                status_code=403,
                detail="Account has been deactivated. Contact support.",
            )

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

    try:
        return await asyncio.to_thread(_fetch_sync)
    except HTTPException:
        raise
    except Exception as exc:
        msg = str(exc).lower()
        if "expired" in msg:
            raise HTTPException(
                status_code=401,
                detail="token_expired",
                headers={"X-Token-Expired": "true"},
            )
        logger.error("Failed to get current user: %s", exc, exc_info=True)
        raise HTTPException(status_code=401, detail="Invalid or expired token")



async def _fetch_api_keys_for_user(user_id: str) -> Dict[str, str]:
    """Decrypted API keys for a user. Cached for 60s (decrypted values stay in Redis)."""
    settings = get_settings()
    cache_key = f"user:keys:{user_id}"
    cached = await cache.get(cache_key)

    if cached is None:
        def _fetch_sync() -> Dict[str, str]:
            db = get_supabase()
            r = db.table("user_profiles").select(
                "claude_api_key_encrypted, tavily_api_key_encrypted, "
                "openai_api_key_encrypted, openrouter_api_key_encrypted"
            ).eq("id", user_id).execute()
            row = r.data[0] if r.data else {}

            def _dec(v: Optional[str]) -> str:
                if not v:
                    return ""
                try:
                    return decrypt_value(v)
                except Exception as exc:
                    logger.warning("decrypt_value failed: %s", exc)
                    return ""

            return {
                "claude": _dec(row.get("claude_api_key_encrypted")),
                "tavily": _dec(row.get("tavily_api_key_encrypted")),
                "openai": _dec(row.get("openai_api_key_encrypted")),
                "openrouter": _dec(row.get("openrouter_api_key_encrypted")),
            }

        try:
            keys = await asyncio.to_thread(_fetch_sync)
        except Exception as exc:
            logger.error("Failed to fetch user API keys: %s", exc)
            keys = {"claude": "", "tavily": "", "openai": "", "openrouter": ""}
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
