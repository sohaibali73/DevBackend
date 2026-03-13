"""
Simplified Authentication Routes using Supabase Auth.

Supabase handles all authentication (JWT, sessions, password reset).
This module just wraps the Supabase auth API and manages user profiles.
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


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordUpdate(BaseModel):
    new_password: str = Field(..., min_length=8)


# ============================================================================
# Authentication Endpoints
# ============================================================================

@router.post("/register", response_model=Token)
async def register(data: UserRegister):
    """
    Register a new user using Supabase Auth.
    
    Supabase sends a confirmation email (if enabled in Supabase dashboard).
    User must confirm email before they can login.
    """
    db = get_supabase()
    settings = get_settings()

    try:
        auth_response = db.auth.sign_up({
            "email": data.email,
            "password": data.password,
            "options": {
                "data": {
                    "name": data.name,
                    "nickname": data.name or data.email.split("@")[0],
                }
            }
        })

        if not auth_response.user:
            raise HTTPException(status_code=400, detail="Failed to create user")

        # Grant admin if email is in admin list
        admin_emails = settings.get_admin_emails()
        if data.email.lower() in admin_emails:
            try:
                db.table("user_profiles").update({"is_admin": True}).eq(
                    "id", auth_response.user.id
                ).execute()
            except Exception as e:
                logger.warning(f"Could not grant admin: {e}")

        # Email confirmation required - no session yet
        if not auth_response.session:
            return Token(
                access_token="",
                token_type="bearer",
                user_id=auth_response.user.id,
                email=data.email,
                expires_in=0
            )

        return Token(
            access_token=auth_response.session.access_token,
            token_type="bearer",
            user_id=auth_response.user.id,
            email=data.email,
            expires_in=auth_response.session.expires_in or 3600
        )

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        if "already" in error_msg or "exists" in error_msg:
            raise HTTPException(status_code=400, detail="Email already registered")
        logger.error(f"Registration failed: {e}")
        raise HTTPException(status_code=400, detail="Registration failed")


@router.post("/login", response_model=Token)
async def login(data: UserLogin):
    """
    Login using Supabase Auth.
    
    Returns JWT token that should be used in Authorization header.
    """
    db = get_supabase()

    try:
        auth_response = db.auth.sign_in_with_password({
            "email": data.email,
            "password": data.password
        })

        if not auth_response.user or not auth_response.session:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Update last active timestamp
        try:
            db.table("user_profiles").update({
                "last_active_at": datetime.utcnow().isoformat()
            }).eq("id", auth_response.user.id).execute()
        except Exception:
            pass

        return Token(
            access_token=auth_response.session.access_token,
            token_type="bearer",
            user_id=auth_response.user.id,
            email=data.email,
            expires_in=auth_response.session.expires_in or 3600
        )

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        if "invalid" in error_msg or "credentials" in error_msg:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        logger.error(f"Login failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid credentials")


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user)):
    """Logout user (client should discard token)."""
    try:
        db = get_supabase()
        db.auth.sign_out()
    except Exception:
        pass
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
async def refresh_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Refresh the access token."""
    db = get_supabase()
    token = credentials.credentials

    try:
        user = db.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid token")

        session = db.auth.get_session()
        if session:
            return Token(
                access_token=session.access_token,
                token_type="bearer",
                user_id=user.user.id,
                email=user.user.email or "",
                expires_in=session.expires_in or 3600
            )
        else:
            return Token(
                access_token=token,
                token_type="bearer",
                user_id=user.user.id,
                email=user.user.email or "",
                expires_in=3600
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post("/forgot-password")
async def forgot_password(
    data: PasswordResetRequest,
    background_tasks: BackgroundTasks
):
    """Request password reset via Supabase Auth."""
    db = get_supabase()
    settings = get_settings()

    try:
        db.auth.reset_password_email(
            data.email,
            {"redirect_to": f"{settings.frontend_url}/reset-password"}
        )
    except Exception as e:
        logger.info(f"Password reset requested: {e}")

    # Always return success to prevent email enumeration
    return {"message": "If this email is registered, a password reset link has been sent"}


@router.post("/reset-password")
async def reset_password(
    data: PasswordUpdate,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Reset password using token from reset email."""
    db = get_supabase()
    token = credentials.credentials

    try:
        user = db.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid reset token")

        db.auth.update_user({"password": data.new_password})
        return {"message": "Password reset successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password reset failed: {e}")
        raise HTTPException(status_code=400, detail="Failed to reset password")


@router.put("/change-password")
async def change_password(
    data: PasswordUpdate,
    user: dict = Depends(get_current_user)
):
    """Change password for logged-in user."""
    db = get_supabase()

    try:
        db.auth.update_user({"password": data.new_password})
        return {"message": "Password changed successfully"}
    except Exception as e:
        logger.error(f"Password change failed: {e}")
        raise HTTPException(status_code=400, detail="Failed to change password")


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