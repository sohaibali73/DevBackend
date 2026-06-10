"""FastAPI dependencies for authentication and user context.

Auth model:
    * Tokens are HS256 JWTs the backend issues and verifies locally with
      ``SECRET_KEY`` (see core.auth_local). No external identity provider, no
      network round-trip per request.
    * The JWT carries ``sub`` (user id) and ``email``, so the user's identity
      is read straight from the token — no auth-server lookup needed.
    * User profile + API keys are Redis-cached (60s) and read via asyncpg when
      available — no extra round-trip in the hot path.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import get_settings
from core.cache import cache
from core.encryption import decrypt_value
from core.auth_local import decode_token, TokenExpired, TokenInvalid
from db import async_db
from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)
# auto_error=False so missing/empty Authorization yields None (not an auto 403),
# letting the AUTH_BYPASS path and our own 401s take over.
security = HTTPBearer(auto_error=False)

# TEMPORARY: AUTH_BYPASS=1 disables auth entirely and runs every request as a
# fixed dev user. Pairs with NEXT_PUBLIC_AUTH_BYPASS=1 on the frontend. Remove
# (unset the env var) before launch.
_AUTH_BYPASS = os.getenv("AUTH_BYPASS", "").lower() in ("1", "true", "yes")
_BYPASS_UID = "00000000-0000-0000-0000-000000000001"
_BYPASS_EMAIL = "dev@potomac.com"


# ── Local JWT verification ──────────────────────────────────────────────────

def _verify_jwt(token: str) -> Optional[Dict[str, Any]]:
    """Verify our own HS256 JWT locally. Returns the payload, or None if invalid.

    Raises HTTPException(401, "token_expired") when expired so the frontend
    knows to refresh.
    """
    try:
        return decode_token(token, expected_type="access")
    except TokenExpired:
        raise HTTPException(
            status_code=401,
            detail="token_expired",
            headers={"X-Token-Expired": "true"},
        )
    except TokenInvalid as exc:
        logger.debug("JWT verification failed: %s", exc)
        return None


# ── Public dependencies ───────────────────────────────────────────────────────

async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Extract and validate user ID from the bearer JWT."""
    if _AUTH_BYPASS:
        return _BYPASS_UID
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = _verify_jwt(credentials.credentials)
    if payload and payload.get("sub"):
        return payload["sub"]
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
    if _AUTH_BYPASS:
        return _BYPASS_UID
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
    payload = _verify_jwt(raw_token)
    if payload and payload.get("sub"):
        return payload["sub"]

    raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict[str, Any]:
    """Return the current user's public profile (no decrypted secrets).

    The user's id + email come straight from the verified JWT (no auth-server
    lookup). The profile fetch + auto-create runs on the sync DB client inside
    ``asyncio.to_thread`` so it doesn't block the event loop.
    """
    if _AUTH_BYPASS:
        user_id = _BYPASS_UID
        email = _BYPASS_EMAIL
        def _ensure_dev() -> Dict[str, Any]:
            db = get_supabase()
            r = db.table("user_profiles").select("id").eq("id", user_id).execute()
            if not r.data:
                db.table("user_profiles").insert({
                    "id": user_id, "email": email, "name": "Dev User",
                    "nickname": "Dev", "is_admin": True, "is_active": True,
                }).execute()
            return {
                "id": user_id, "email": email, "name": "Dev User", "nickname": "Dev",
                "is_admin": True, "is_active": True, "created_at": None,
                "last_active_at": None, "has_claude_key": False, "has_tavily_key": False,
                "has_openai_key": False, "has_openrouter_key": False,
                "preferred_provider": "anthropic", "preferred_model": "claude-sonnet-4-20250514",
            }
        return await asyncio.to_thread(_ensure_dev)

    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = credentials.credentials
    payload = _verify_jwt(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_id = payload["sub"]
    email = payload.get("email", "")

    def _fetch_sync() -> Dict[str, Any]:
        db = get_supabase()

        profile_result = db.table("user_profiles").select(
            "id, email, name, nickname, is_admin, is_active, created_at, last_active_at, "
            "claude_api_key_encrypted, tavily_api_key_encrypted, "
            "openai_api_key_encrypted, openrouter_api_key_encrypted, "
            "preferred_provider, preferred_model"
        ).eq("id", user_id).execute()

        if not profile_result.data:
            profile_data = {
                "id": user_id,
                "email": email,
                "nickname": email.split("@")[0] if email else None,
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
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
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
