"""
Self-hosted authentication routes.

The backend owns the full auth lifecycle (passwords hashed with bcrypt in
user_profiles.password_hash; access/refresh tokens are HS256 JWTs signed with
SECRET_KEY). No external identity provider.
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
import logging

from config import get_settings
from db.supabase_client import get_supabase
from api.dependencies import get_current_user
from core.encryption import encrypt_value
from core.auth_local import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    new_user_id,
    TokenExpired,
    TokenInvalid,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()
logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models
# ============================================================================

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    expires_in: int = 3600
    refresh_token: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    email: str
    name: Optional[str] = None
    nickname: Optional[str] = None
    is_admin: bool = False
    is_active: bool = True
    has_api_keys: bool = False
    created_at: Optional[str] = None


class APIKeyUpdate(BaseModel):
    claude_api_key: Optional[str] = None
    tavily_api_key: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    nickname: Optional[str] = None
    claude_api_key: Optional[str] = None
    tavily_api_key: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordUpdate(BaseModel):
    new_password: str = Field(..., min_length=8)


# ============================================================================
# Authentication Endpoints
# ============================================================================

@router.post("/register", response_model=Token)
async def register(data: UserRegister):
    """Register a new user (self-hosted). Returns access + refresh tokens."""
    db = get_supabase()
    settings = get_settings()
    email = data.email.lower().strip()

    # Reject duplicates.
    existing = db.table("user_profiles").select("id").eq("email", email).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_id = new_user_id()
    is_admin = email in settings.get_admin_emails()
    try:
        db.table("user_profiles").insert({
            "id": user_id,
            "email": email,
            "password_hash": hash_password(data.password),
            "name": data.name,
            "nickname": data.name or email.split("@")[0],
            "is_admin": is_admin,
            "is_active": True,
        }).execute()
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        raise HTTPException(status_code=400, detail="Registration failed")

    return Token(
        access_token=create_access_token(user_id, email),
        refresh_token=create_refresh_token(user_id, email),
        token_type="bearer",
        user_id=user_id,
        email=email,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/login", response_model=Token)
async def login(data: UserLogin):
    """Authenticate with email + password. Returns access + refresh tokens."""
    db = get_supabase()
    settings = get_settings()
    email = data.email.lower().strip()

    result = db.table("user_profiles").select(
        "id, email, password_hash, is_active"
    ).eq("email", email).execute()
    row = result.data[0] if result.data else None

    if not row or not verify_password(data.password, row.get("password_hash")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not row.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account has been deactivated. Contact support.")

    user_id = row["id"]
    try:
        db.table("user_profiles").update(
            {"last_active_at": datetime.utcnow().isoformat()}
        ).eq("id", user_id).execute()
    except Exception:
        pass

    return Token(
        access_token=create_access_token(user_id, email),
        refresh_token=create_refresh_token(user_id, email),
        token_type="bearer",
        user_id=user_id,
        email=email,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user)):
    """Logout. JWTs are stateless; the client discards the token."""
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    """Get current user profile."""
    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user.get("name"),
        nickname=user.get("nickname"),
        is_admin=user.get("is_admin", False),
        is_active=user.get("is_active", True),
        has_api_keys=user.get("has_claude_key", False) or user.get("has_tavily_key", False),
        created_at=user.get("created_at"),
    )


@router.put("/me")
async def update_user(data: UserUpdate, user: dict = Depends(get_current_user)):
    """Update current user profile (including API keys)."""
    db = get_supabase()

    update_data = {"updated_at": datetime.utcnow().isoformat()}
    if data.name is not None:
        update_data["name"] = data.name
    if data.nickname is not None:
        update_data["nickname"] = data.nickname

    # Handle API keys — encrypt before storage
    if data.claude_api_key is not None:
        if data.claude_api_key.strip():
            update_data["claude_api_key_encrypted"] = encrypt_value(data.claude_api_key.strip())
        else:
            update_data["claude_api_key_encrypted"] = None

    if data.tavily_api_key is not None:
        if data.tavily_api_key.strip():
            update_data["tavily_api_key_encrypted"] = encrypt_value(data.tavily_api_key.strip())
        else:
            update_data["tavily_api_key_encrypted"] = None

    result = db.table("user_profiles").update(update_data).eq("id", user["id"]).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update user")

    return {"message": "User updated successfully"}


# ============================================================================
# API Key Management
# ============================================================================

@router.put("/api-keys")
async def update_api_keys(data: APIKeyUpdate, user: dict = Depends(get_current_user)):
    """
    Update user's API keys.
    
    Keys are encrypted with AES-256 before storage.
    Only the presence flag is returned (not the actual keys).
    """
    db = get_supabase()

    update_data = {"updated_at": datetime.utcnow().isoformat()}

    if data.claude_api_key is not None:
        if data.claude_api_key.strip():
            update_data["claude_api_key_encrypted"] = encrypt_value(data.claude_api_key.strip())
        else:
            update_data["claude_api_key_encrypted"] = None

    if data.tavily_api_key is not None:
        if data.tavily_api_key.strip():
            update_data["tavily_api_key_encrypted"] = encrypt_value(data.tavily_api_key.strip())
        else:
            update_data["tavily_api_key_encrypted"] = None

    try:
        result = db.table("user_profiles").update(update_data).eq("id", user["id"]).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update API keys")

        return {"message": "API keys updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update API keys: {e}")
        raise HTTPException(status_code=500, detail="Failed to update API keys")


@router.get("/api-keys")
async def get_api_keys_status(user: dict = Depends(get_current_user)):
    """Get status of user's API keys (not the actual values)."""
    return {
        "has_claude_key": user.get("has_claude_key", False),
        "has_tavily_key": user.get("has_tavily_key", False),
    }


# ============================================================================
# Password Management
# ============================================================================

@router.post("/refresh-token", response_model=Token)
async def refresh_token(data: RefreshTokenRequest):
    """Exchange a valid refresh token for a fresh access + refresh token pair."""
    settings = get_settings()
    try:
        payload = decode_token(data.refresh_token, expected_type="refresh")
    except TokenExpired:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except TokenInvalid:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = payload["sub"]
    email = payload.get("email", "")
    return Token(
        access_token=create_access_token(user_id, email),
        refresh_token=create_refresh_token(user_id, email),
        token_type="bearer",
        user_id=user_id,
        email=email,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/forgot-password")
async def forgot_password(data: PasswordResetRequest, background_tasks: BackgroundTasks):
    """Issue a short-lived password-reset token and email a reset link.

    Email delivery depends on SMTP settings being configured; when they are
    not, the link is logged server-side. Always returns success to prevent
    email enumeration.
    """
    from core.auth_local import _encode  # local import: reset tokens are a niche path
    db = get_supabase()
    settings = get_settings()
    email = data.email.lower().strip()

    try:
        result = db.table("user_profiles").select("id, email").eq("email", email).execute()
        if result.data:
            row = result.data[0]
            reset_token = _encode({"sub": row["id"], "email": row["email"]}, 30, "reset")
            reset_link = f"{settings.frontend_url}/reset-password?token={reset_token}"
            # TODO: wire SMTP send here; for now log the link for operators.
            logger.info("Password reset link for %s: %s", email, reset_link)
    except Exception as e:
        logger.info(f"Password reset requested: {e}")

    return {"message": "If this email is registered, a password reset link has been sent"}


@router.post("/reset-password")
async def reset_password(
    data: PasswordUpdate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Reset password using the reset token from the email link."""
    db = get_supabase()
    try:
        payload = decode_token(credentials.credentials, expected_type="reset")
    except (TokenExpired, TokenInvalid):
        raise HTTPException(status_code=401, detail="Invalid or expired reset token")

    result = db.table("user_profiles").update(
        {"password_hash": hash_password(data.new_password),
         "updated_at": datetime.utcnow().isoformat()}
    ).eq("id", payload["sub"]).execute()
    if not result.data:
        raise HTTPException(status_code=400, detail="Failed to reset password")
    return {"message": "Password reset successfully"}


@router.put("/change-password")
async def change_password(
    data: PasswordUpdate,
    user: dict = Depends(get_current_user),
):
    """Change password for the logged-in user."""
    db = get_supabase()
    result = db.table("user_profiles").update(
        {"password_hash": hash_password(data.new_password),
         "updated_at": datetime.utcnow().isoformat()}
    ).eq("id", user["id"]).execute()
    if not result.data:
        raise HTTPException(status_code=400, detail="Failed to change password")
    return {"message": "Password changed successfully"}


# ============================================================================
# Admin Endpoints
# ============================================================================

@router.get("/admin/users")
async def list_users(user: dict = Depends(get_current_user)):
    """List all users (admin only)."""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    db = get_supabase()
    try:
        result = db.table("user_profiles").select(
            "id, name, nickname, email, is_admin, is_active, created_at, last_active_at"
        ).order("created_at", desc=True).execute()
        return result.data
    except Exception as e:
        logger.error(f"Failed to list users: {e}")
        raise HTTPException(status_code=500, detail="Failed to list users")


@router.post("/admin/users/{user_id}/make-admin")
async def make_user_admin(user_id: str, user: dict = Depends(get_current_user)):
    """Make a user an admin (admin only)."""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    db = get_supabase()
    result = db.table("user_profiles").update({"is_admin": True}).eq("id", user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": f"User {user_id} is now an admin"}


@router.post("/admin/users/{user_id}/revoke-admin")
async def revoke_admin(user_id: str, user: dict = Depends(get_current_user)):
    """Revoke admin privileges (admin only)."""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot revoke your own admin privileges")

    db = get_supabase()
    result = db.table("user_profiles").update({"is_admin": False}).eq("id", user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": f"Admin privileges revoked from user {user_id}"}


@router.post("/admin/users/{user_id}/deactivate")
async def deactivate_user(user_id: str, user: dict = Depends(get_current_user)):
    """Deactivate a user account (admin only)."""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    db = get_supabase()
    result = db.table("user_profiles").update({"is_active": False}).eq("id", user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": f"User {user_id} deactivated"}


@router.post("/admin/users/{user_id}/activate")
async def activate_user(user_id: str, user: dict = Depends(get_current_user)):
    """Activate a user account (admin only)."""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    db = get_supabase()
    result = db.table("user_profiles").update({"is_active": True}).eq("id", user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": f"User {user_id} activated"}