"""Self-hosted authentication primitives: password hashing + JWT issuance/verify.

Replaces Supabase Auth. The backend now owns the full auth lifecycle:
    * passwords are hashed with bcrypt and stored in user_profiles.password_hash
    * access/refresh tokens are HS256 JWTs signed with settings.secret_key
    * tokens carry: sub (user id), email, type, iss, aud, exp, iat

Verification stays local (no network round-trip), exactly like the previous
fast-path — only the signing key changed from SUPABASE_JWT_SECRET to our own
SECRET_KEY.
"""

from __future__ import annotations

import datetime as _dt
import logging
import uuid
from typing import Any, Dict, Optional

import bcrypt
import jwt  # PyJWT

from config import get_settings

logger = logging.getLogger(__name__)


# ── Passwords ───────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: Optional[str]) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ── JWT ───────────────────────────────────────────────────────────────────────

class TokenExpired(Exception):
    pass


class TokenInvalid(Exception):
    pass


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _encode(claims: Dict[str, Any], expires_minutes: int, token_type: str) -> str:
    s = get_settings()
    now = _now()
    payload = {
        **claims,
        "type": token_type,
        "iss": s.jwt_issuer,
        "aud": s.jwt_audience,
        "iat": now,
        "exp": now + _dt.timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, s.secret_key, algorithm=s.algorithm)


def create_access_token(user_id: str, email: str) -> str:
    s = get_settings()
    return _encode({"sub": user_id, "email": email}, s.access_token_expire_minutes, "access")


def create_refresh_token(user_id: str, email: str) -> str:
    s = get_settings()
    return _encode({"sub": user_id, "email": email}, s.refresh_token_expire_minutes, "refresh")


def decode_token(token: str, *, expected_type: Optional[str] = None) -> Dict[str, Any]:
    """Verify + decode a token. Raises TokenExpired / TokenInvalid."""
    s = get_settings()
    try:
        payload = jwt.decode(
            token,
            s.secret_key,
            algorithms=[s.algorithm],
            audience=s.jwt_audience,
            issuer=s.jwt_issuer,
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        raise TokenExpired()
    except jwt.InvalidTokenError as exc:
        raise TokenInvalid(str(exc))
    if expected_type and payload.get("type") != expected_type:
        raise TokenInvalid(f"expected {expected_type} token, got {payload.get('type')}")
    return payload


def new_user_id() -> str:
    """Generate a user id (uuid4) for new self-hosted accounts."""
    return str(uuid.uuid4())
