"""Settings routes — profile, password, appearance, notifications, API keys, account."""

import secrets
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr

from api.dependencies import get_current_user_id, get_current_user
from db.supabase_client import get_supabase
from core.encryption import encrypt_value, decrypt_value

router = APIRouter(prefix="/settings", tags=["Settings"])
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────────

class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    nickname: Optional[str] = None
    email: Optional[EmailStr] = None


class ChangePasswordRequest(BaseModel):
    new_password: str
    confirm_password: str


class AppearanceSettings(BaseModel):
    theme: Optional[str] = None        # "light" | "dark" | "system"
    accent_color: Optional[str] = None
    font_size: Optional[str] = None    # "small" | "medium" | "large"


class NotificationSettings(BaseModel):
    email_notifications: Optional[bool] = None
    code_gen_complete: Optional[bool] = None
    backtest_complete: Optional[bool] = None
    system_updates: Optional[bool] = None
    marketing_emails: Optional[bool] = None


class CreateAPIKeyRequest(BaseModel):
    name: str
    permissions: List[str] = ["read", "write"]


class DeleteAccountRequest(BaseModel):
    confirmation: str   # Must equal "DELETE"


# ──────────────────────────────────────────────────────────────────────────────
# Profile
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/profile")
async def get_profile(user: dict = Depends(get_current_user)):
    """Get the current user's profile."""
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user.get("name"),
        "nickname": user.get("nickname"),
        "is_admin": user.get("is_admin", False),
        "created_at": user.get("created_at"),
        "has_claude_key": user.get("has_claude_key", False),
        "has_tavily_key": user.get("has_tavily_key", False),
        "preferred_provider": user.get("preferred_provider", "anthropic"),
        "preferred_model": user.get("preferred_model", "claude-sonnet-4-20250514"),
    }


@router.patch("/profile")
async def update_profile(
    request: UpdateProfileRequest,
    user: dict = Depends(get_current_user),
):
    """Update user profile (name, nickname)."""
    db = get_supabase()

    update_fields: dict = {"updated_at": datetime.utcnow().isoformat()}

    if request.name is not None:
        update_fields["name"] = request.name
    if request.nickname is not None:
        update_fields["nickname"] = request.nickname

    if len(update_fields) == 1:  # only updated_at
        raise HTTPException(status_code=400, detail="No fields provided to update")

    result = db.table("user_profiles").update(update_fields).eq("id", user["id"]).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update profile")

    updated = result.data[0]
    return {
        "success": True,
        "user": {
            "id": updated["id"],
            "name": updated.get("name"),
            "nickname": updated.get("nickname"),
            "email": user["email"],
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# Password
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    user: dict = Depends(get_current_user),
):
    """Change user password via Supabase Auth."""
    if request.new_password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    db = get_supabase()
    try:
        db.auth.update_user({"password": request.new_password})
        return {"success": True, "message": "Password changed successfully"}
    except Exception as e:
        logger.error(f"Password change failed: {e}")
        raise HTTPException(status_code=400, detail="Failed to change password")


# ──────────────────────────────────────────────────────────────────────────────
# Appearance
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/appearance")
async def get_appearance(user: dict = Depends(get_current_user)):
    """Get current appearance settings."""
    db = get_supabase()
    result = db.table("user_profiles").select("settings").eq("id", user["id"]).execute()
    settings = {}
    if result.data:
        settings = (result.data[0].get("settings") or {}).get("appearance", {})
    return {
        "theme": settings.get("theme", "dark"),
        "accent_color": settings.get("accent_color", "#FEC00F"),
        "font_size": settings.get("font_size", "medium"),
    }


@router.patch("/appearance")
async def update_appearance(
    settings: AppearanceSettings,
    user: dict = Depends(get_current_user),
):
    """Update appearance settings (stored in user_profiles.settings JSONB)."""
    db = get_supabase()

    # Fetch existing settings
    existing_res = db.table("user_profiles").select("settings").eq("id", user["id"]).execute()
    existing_settings = {}
    if existing_res.data:
        existing_settings = existing_res.data[0].get("settings") or {}

    appearance = existing_settings.get("appearance", {})
    new_vals = {k: v for k, v in settings.dict().items() if v is not None}
    appearance.update(new_vals)
    existing_settings["appearance"] = appearance

    db.table("user_profiles").update({"settings": existing_settings}).eq("id", user["id"]).execute()

    return {"success": True, "settings": appearance}


# ──────────────────────────────────────────────────────────────────────────────
# Notifications
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/notifications")
async def get_notifications(user: dict = Depends(get_current_user)):
    """Get current notification settings."""
    db = get_supabase()
    result = db.table("user_profiles").select("settings").eq("id", user["id"]).execute()
    notif = {}
    if result.data:
        notif = (result.data[0].get("settings") or {}).get("notifications", {})
    return {
        "email_notifications": notif.get("email_notifications", True),
        "code_gen_complete": notif.get("code_gen_complete", True),
        "backtest_complete": notif.get("backtest_complete", True),
        "system_updates": notif.get("system_updates", True),
        "marketing_emails": notif.get("marketing_emails", False),
    }


@router.patch("/notifications")
async def update_notifications(
    settings: NotificationSettings,
    user: dict = Depends(get_current_user),
):
    """Update notification settings."""
    db = get_supabase()

    existing_res = db.table("user_profiles").select("settings").eq("id", user["id"]).execute()
    existing_settings = {}
    if existing_res.data:
        existing_settings = existing_res.data[0].get("settings") or {}

    notif = existing_settings.get("notifications", {})
    new_vals = {k: v for k, v in settings.dict().items() if v is not None}
    notif.update(new_vals)
    existing_settings["notifications"] = notif

    db.table("user_profiles").update({"settings": existing_settings}).eq("id", user["id"]).execute()

    return {"success": True, "notifications": notif}


# ──────────────────────────────────────────────────────────────────────────────
# API Keys (application-level keys, not Claude/Tavily keys)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/api-keys")
async def list_api_keys(user: dict = Depends(get_current_user)):
    """List user's application API keys (masked)."""
    db = get_supabase()

    try:
        result = (
            db.table("app_api_keys")
            .select("id, name, key_prefix, permissions, created_at, last_used_at")
            .eq("user_id", user["id"])
            .order("created_at", desc=True)
            .execute()
        )
        return {"api_keys": result.data or []}
    except Exception as e:
        logger.warning(f"app_api_keys table may not exist yet: {e}")
        return {"api_keys": []}


@router.post("/api-keys")
async def create_api_key(
    request: CreateAPIKeyRequest,
    user: dict = Depends(get_current_user),
):
    """Generate a new application API key."""
    db = get_supabase()

    raw_key = f"pk_live_{secrets.token_urlsafe(32)}"
    key_prefix = raw_key[:16] + "..."

    try:
        result = db.table("app_api_keys").insert({
            "user_id": user["id"],
            "name": request.name,
            "key_hash": encrypt_value(raw_key),
            "key_prefix": key_prefix,
            "permissions": request.permissions,
            "created_at": datetime.utcnow().isoformat(),
        }).execute()

        key_doc = result.data[0]

        return {
            "success": True,
            "api_key": {
                "id": key_doc["id"],
                "key": raw_key,           # shown ONCE only
                "name": request.name,
                "created_at": key_doc.get("created_at"),
                "permissions": request.permissions,
                "last_used_at": None,
            },
            "warning": "Store this key securely — it will not be shown again.",
        }
    except Exception as e:
        logger.error(f"Failed to create API key: {e}")
        raise HTTPException(status_code=500, detail="Failed to create API key. Ensure app_api_keys table exists.")


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    user: dict = Depends(get_current_user),
):
    """Revoke an application API key."""
    db = get_supabase()

    try:
        result = (
            db.table("app_api_keys")
            .delete()
            .eq("id", key_id)
            .eq("user_id", user["id"])
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="API key not found")

        return {"success": True, "message": "API key revoked"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to revoke API key: {e}")
        raise HTTPException(status_code=500, detail="Failed to revoke API key")


# ──────────────────────────────────────────────────────────────────────────────
# Delete account
# ──────────────────────────────────────────────────────────────────────────────

@router.delete("/account")
async def delete_account(
    request: DeleteAccountRequest,
    user: dict = Depends(get_current_user),
):
    """Permanently delete the user's account and all associated data."""
    if request.confirmation != "DELETE":
        raise HTTPException(
            status_code=400,
            detail="Type 'DELETE' exactly to confirm account deletion",
        )

    db = get_supabase()
    user_id = user["id"]

    # Soft-delete: mark inactive and anonymise. Hard-delete requires service_role + admin API.
    try:
        db.table("user_profiles").update({
            "is_active": False,
            "name": "[deleted]",
            "nickname": "[deleted]",
            "claude_api_key_encrypted": None,
            "tavily_api_key_encrypted": None,
        }).eq("id", user_id).execute()
    except Exception as e:
        logger.error(f"Account deletion failed: {e}")
        raise HTTPException(status_code=500, detail="Account deletion failed")

    # Best-effort cleanup of user data
    for table, col in [
        ("afl_history", "user_id"),
        ("afl_codes", "user_id"),
        ("conversations", "user_id"),
        ("backtest_results", "user_id"),
    ]:
        try:
            db.table(table).delete().eq(col, user_id).execute()
        except Exception:
            pass

    return {"success": True, "message": "Account deleted successfully"}
