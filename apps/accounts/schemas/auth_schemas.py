"""
Validation + serialization for auth endpoints. Plain functions, no DRF.
"""

from apps.accounts.models import User


class ValidationError(ValueError):
    """Raised by validate_* functions with a dict of field errors."""

    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__("Validation failed")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_signup(data: dict) -> dict:
    """Validate signup input. Returns cleaned data or raises ValidationError."""
    errors = {}

    email = (data.get("email") or "").strip().lower()
    if not email:
        errors["email"] = "Email is required."

    password = data.get("password") or ""
    if len(password) < 8:
        errors["password"] = "Password must be at least 8 characters."

    full_name = (data.get("full_name") or "").strip()
    if not full_name:
        errors["full_name"] = "Full name is required."

    country = (data.get("country") or "").strip().upper()
    if not country or len(country) != 2:
        errors["country"] = "A valid 2-letter country code is required."

    age_confirmed = data.get("age_confirmed", False)
    if not age_confirmed:
        errors["age_confirmed"] = "You must confirm you meet the minimum age."

    terms_accepted = data.get("terms_accepted", False)
    if not terms_accepted:
        errors["terms_accepted"] = "You must accept the terms and privacy notice."

    if errors:
        raise ValidationError(errors)

    return {
        "email": email,
        "password": password,
        "full_name": full_name,
        "country": country,
        "age_confirmed": True,
        "terms_accepted": True,
    }


def validate_login(data: dict) -> dict:
    """Validate login input."""
    errors = {}

    email = (data.get("email") or "").strip().lower()
    if not email:
        errors["email"] = "Email is required."

    password = data.get("password") or ""
    if not password:
        errors["password"] = "Password is required."

    if errors:
        raise ValidationError(errors)

    return {"email": email, "password": password}


def validate_google_login(data: dict) -> str:
    code = (data.get("code") or "").strip()
    if not code:
        raise ValidationError({"code": "Google authorization code is required."})
    return code


def validate_verify_email(data: dict) -> str:
    """Return the token string or raise ValidationError."""
    token = (data.get("token") or "").strip()
    if not token:
        raise ValidationError({"token": "Verification token is required."})
    return token


def validate_forgot_password(data: dict) -> str:
    email = (data.get("email") or "").strip().lower()
    if not email:
        raise ValidationError({"email": "Email is required."})
    return email


def validate_reset_password(data: dict) -> dict:
    token = (data.get("token") or "").strip()
    password = data.get("password") or ""
    errors = {}

    if not token:
        errors["token"] = "Reset token is required."
    if len(password) < 8:
        errors["password"] = "Password must be at least 8 characters."
    if errors:
        raise ValidationError(errors)

    return {"token": token, "password": password}


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def serialize_user(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "country": user.country,
        "is_email_verified": user.is_email_verified,
        "is_staff": user.is_staff,
        "date_joined": user.date_joined.isoformat(),
    }
