"""FastAPI dependencies for authentication and user context."""

from typing import Optional, Dict, Any
from fastapi import Header, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging

from db.supabase_client import get_supabase
from core.encryption import decrypt_value

logger = logging.getLogger(__name__)

security = HTTPBearer()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """
    Extract and validate user ID from Supabase JWT token.
    Returns the user ID (UUID string).
    """
    token = credentials.credentials
    db = get_supabase()

    try:
        user = db.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return user.user.id
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token validation failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    Get current user with profile data from user_profiles table.
    Does NOT include API keys — only presence flags.
    Enforces is_active check.
    """
    token = credentials.credentials
    db = get_supabase()

    try:
        auth_user = db.auth.get_user(token)
        if not auth_user or not auth_user.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        user_id = auth_user.user.id
        email = auth_user.user.email or ""

        # Get profile from user_profiles — only fetch non-sensitive columns
        profile_result = db.table("user_profiles").select(
            "id, name, nickname, is_admin, is_active, created_at, last_active_at, claude_api_key_encrypted, tavily_api_key_encrypted"
        ).eq("id", user_id).execute()

        if not profile_result.data:
            # Auto-create profile if trigger didn't fire
            profile_data = {
                "id": user_id,
                "name": auth_user.user.user_metadata.get("name"),
                "nickname": auth_user.user.user_metadata.get("nickname", email.split("@")[0]),
            }
            db.table("user_profiles").insert(profile_data).execute()
            profile = profile_data
        else:
            profile = profile_result.data[0]

        # Enforce is_active check — deactivated users cannot authenticate
        if not profile.get("is_active", True):
            raise HTTPException(
                status_code=403,
                detail="Account has been deactivated. Contact support."
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
            # Include key presence flags (not the actual keys)
            "has_claude_key": bool(profile.get("claude_api_key_encrypted")),
            "has_tavily_key": bool(profile.get("tavily_api_key_encrypted")),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get current user: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def _fetch_api_keys_for_user(user_id: str) -> Dict[str, str]:
    """
    Internal helper: Get user's API keys from user_profiles table.
    Keys are stored encrypted (AES-256) and decrypted here for use.
    Falls back to server-side API keys from environment variables if user hasn't set their own.
    """
    from config import get_settings
    settings = get_settings()
    db = get_supabase()

    claude_key = ""
    tavily_key = ""

    try:
        result = db.table("user_profiles").select(
            "claude_api_key_encrypted, tavily_api_key_encrypted"
        ).eq("id", user_id).execute()

        if result.data:
            row = result.data[0]
            raw_claude = row.get("claude_api_key_encrypted") or ""
            raw_tavily = row.get("tavily_api_key_encrypted") or ""

            # Decrypt (handles both encrypted 'enc:...' and legacy plain text)
            claude_key = decrypt_value(raw_claude) if raw_claude else ""
            tavily_key = decrypt_value(raw_tavily) if raw_tavily else ""

    except Exception as e:
        logger.error(f"Failed to get user API keys: {e}")

    # Fallback to server-side keys from environment variables
    if not claude_key and settings.anthropic_api_key:
        claude_key = settings.anthropic_api_key
        logger.info("Using server-side ANTHROPIC_API_KEY as fallback")
    if not tavily_key and settings.tavily_api_key:
        tavily_key = settings.tavily_api_key
        logger.info("Using server-side TAVILY_API_KEY as fallback")

    return {"claude": claude_key, "tavily": tavily_key}


async def get_user_api_keys(
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, str]:
    """
    FastAPI dependency: Get user's decrypted API keys.
    Chains from get_current_user_id so user_id comes from the JWT token,
    NOT from query parameters.
    """
    return await _fetch_api_keys_for_user(user_id)


async def get_user_with_api_keys(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    Get current user with decrypted API keys.
    Use this dependency when you need the actual API keys.
    """
    user = await get_current_user(credentials)
    api_keys = await _fetch_api_keys_for_user(user["id"])
    user["claude_api_key"] = api_keys["claude"]
    user["tavily_api_key"] = api_keys["tavily"]
    return user


async def verify_admin(user: Dict[str, Any] = Depends(get_current_user)) -> str:
    """Verify the current user is an admin. Returns user ID."""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user["id"]
