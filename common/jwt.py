"""
JWT encode / decode helpers — manual PyJWT per BACKEND-RULES.main.md §6.

No DRF simplejwt. Access tokens are short-lived (15 min), refresh tokens are
single-use (tracked via RefreshToken model — see apps/accounts/models.py).
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings

ALGORITHM = getattr(settings, "JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_TTL = getattr(settings, "ACCESS_TOKEN_TTL", 60 * 15)
REFRESH_TOKEN_TTL = getattr(settings, "REFRESH_TOKEN_TTL", 60 * 60 * 24 * 7)


def _signing_key():
    return getattr(settings, "JWT_SECRET_KEY", "") or settings.SECRET_KEY


def encode_access_token(user) -> str:
    """Return a short-lived access token for *user*."""
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "iat": now,
        "exp": now + timedelta(seconds=ACCESS_TOKEN_TTL),
        "type": "access",
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _signing_key(), algorithm=ALGORITHM)


def encode_refresh_token(user) -> str:
    """Return a longer-lived refresh token whose jti is stored in the DB."""
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": str(user.id),
        "iat": now,
        "exp": now + timedelta(seconds=REFRESH_TOKEN_TTL),
        "type": "refresh",
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _signing_key(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT. Returns the payload dict on success.

    Raises jwt.ExpiredSignatureError, jwt.InvalidTokenError, etc. on failure.
    """
    return jwt.decode(token, _signing_key(), algorithms=[ALGORITHM])
