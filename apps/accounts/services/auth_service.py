"""
Authentication service — signup, login, token management, email verification.

Per plan 0001:
- signup creates User + CreditWallet atomically
- Email verification token is logged to console (stubbed send)
- Refresh tokens are single-use
- Country → currency mapping for wallet default
"""

import logging

import requests
from django.conf import settings
from django.contrib.auth import authenticate as django_authenticate
from django.core import signing
from django.db import transaction

from apps.accounts.models import EmailVerificationToken, RefreshToken, User
from apps.credits.models import CreditWallet
from apps.credits.services.ledger_service import promotional_credit
from common.jwt import decode_token, encode_access_token, encode_refresh_token
from common.utils import generate_token

logger = logging.getLogger(__name__)

# ISO 3166-1 alpha-2 → ISO 4217 currency code
COUNTRY_CURRENCY = {
    "GH": "GHS",
    "NG": "NGN",
    "KE": "KES",
    "ZA": "ZAR",
    "RW": "RWF",
    "TZ": "TZS",
    "UG": "UGX",
    "CM": "XAF",
    "CI": "XOF",
    "SN": "XOF",
}
FALLBACK_CURRENCY = "USD"

# Small promotional grant on signup (plan verifies credit balance shows)
SIGNUP_PROMO_CREDITS = 5


def _currency_for_country(country: str) -> str:
    return COUNTRY_CURRENCY.get(country.upper(), FALLBACK_CURRENCY)


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------

@transaction.atomic
def signup(
    *,
    email: str,
    password: str,
    full_name: str,
    country: str,
    age_confirmed: bool,
    terms_accepted: bool,
) -> User:
    """Create a new user, wallet, and verification token. Returns the user."""

    if not age_confirmed:
        raise ValueError("You must confirm you meet the minimum age requirement.")
    if not terms_accepted:
        raise ValueError("You must accept the terms and privacy notice.")

    email = email.lower().strip()
    if User.objects.filter(email=email).exists():
        raise ValueError("A user with this email already exists.")

    user = User.objects.create_user(
        email=email,
        password=password,
        full_name=full_name,
        country=country.upper(),
        username=email,  # AbstractUser requires username; we use email
    )

    # Create wallet (same transaction)
    wallet = CreditWallet.objects.create(
        user=user,
        currency=_currency_for_country(country),
    )

    # Seed a small promotional credit grant
    promotional_credit(
        wallet=wallet,
        amount=SIGNUP_PROMO_CREDITS,
        idempotency_key=f"signup_promo:{user.id}",
        reference={"reason": "signup_promotional_grant"},
    )

    # Create verification token + log the link (stubbed email)
    token = EmailVerificationToken.create_for_user(user)
    verify_link = f"{_frontend_url()}/verify-email?token={token.token}"
    logger.info("[DEV EMAIL] Verify email for %s: %s", email, verify_link)

    return user


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def authenticate_user(*, email: str, password: str) -> dict:
    """Validate credentials and return an access + refresh token pair.

    Raises ValueError on bad credentials.
    """
    email = email.lower().strip()
    user = django_authenticate(request=None, username=email, password=password)
    if user is None:
        raise ValueError("Invalid email or password.")
    if not user.is_active:
        raise ValueError("This account has been disabled.")

    return issue_token_pair(user)


class GoogleOAuthError(ValueError):
    """A safe, user-facing Google authentication failure."""


@transaction.atomic
def authenticate_google_user(*, code: str) -> dict:
    """Exchange a Google authorization code and issue OnePrompt JWTs."""
    if not (
        settings.GOOGLE_CLIENT_ID
        and settings.GOOGLE_CLIENT_SECRET
        and settings.GOOGLE_REDIRECT_URI
    ):
        raise GoogleOAuthError("Google login is not configured.")

    try:
        token_response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        if not access_token:
            raise GoogleOAuthError("Google returned an invalid token response.")

        profile_response = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        profile_response.raise_for_status()
        profile = profile_response.json()
    except requests.RequestException as exc:
        logger.warning("Google OAuth request failed: %s", exc)
        raise GoogleOAuthError("Google authentication failed. Please try again.") from exc

    email = (profile.get("email") or "").lower().strip()
    if not email or not profile.get("verified_email"):
        raise GoogleOAuthError("Google did not provide a verified email address.")

    full_name = (profile.get("name") or "").strip()
    user = User.objects.filter(email=email).first()
    if user is None:
        user = User.objects.create_user(
            username=email,
            email=email,
            full_name=full_name,
            country="",
            is_email_verified=True,
        )
        wallet = CreditWallet.objects.create(user=user, currency=FALLBACK_CURRENCY)
        promotional_credit(
            wallet=wallet,
            amount=SIGNUP_PROMO_CREDITS,
            idempotency_key=f"signup_promo:{user.id}",
            reference={"reason": "google_signup_promotional_grant"},
        )
    else:
        fields_to_update = []
        if not user.is_email_verified:
            user.is_email_verified = True
            fields_to_update.append("is_email_verified")
        if not user.full_name and full_name:
            user.full_name = full_name
            fields_to_update.append("full_name")
        if fields_to_update:
            user.save(update_fields=fields_to_update)
        CreditWallet.objects.get_or_create(
            user=user,
            defaults={"currency": _currency_for_country(user.country)},
        )

    return issue_token_pair(user)


def issue_token_pair(user: User) -> dict:
    """Create access + refresh tokens, persist the refresh token jti."""
    from datetime import datetime, timedelta, timezone

    access = encode_access_token(user)
    refresh = encode_refresh_token(user)
    payload = decode_token(refresh)

    RefreshToken.objects.create(
        user=user,
        jti=payload["jti"],
        expires_at=datetime.now(tz=timezone.utc)
        + timedelta(seconds=settings.REFRESH_TOKEN_TTL),
    )

    return {
        "access": access,
        "refresh": refresh,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "country": user.country,
            "is_email_verified": user.is_email_verified,
            "is_staff": user.is_staff,
        },
    }


def refresh_token_pair(refresh_token_str: str) -> dict:
    """Validate a refresh token, delete it (single-use), issue a new pair."""
    try:
        payload = decode_token(refresh_token_str)
    except Exception:
        raise ValueError("Invalid or expired refresh token.")

    if payload.get("type") != "refresh":
        raise ValueError("Invalid token type.")

    try:
        rt = RefreshToken.objects.select_related("user").get(jti=payload["jti"])
    except RefreshToken.DoesNotExist:
        raise ValueError("Refresh token has already been used or revoked.")

    user = rt.user
    rt.delete()  # single-use

    if not user.is_active:
        raise ValueError("Account is disabled.")

    return issue_token_pair(user)


def revoke_user_tokens(user: User):
    """Delete all refresh tokens for *user* — logs them out everywhere."""
    RefreshToken.objects.filter(user=user).delete()


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------


def verify_email(*, token_str: str) -> User:
    """Consume a verification token and mark the user as verified.

    Raises ValueError if the token is invalid, expired, or already used.
    """
    try:
        token = EmailVerificationToken.objects.select_related("user").get(
            token=token_str
        )
    except EmailVerificationToken.DoesNotExist:
        raise ValueError("Invalid verification token.")

    if not token.is_valid:
        raise ValueError("Verification token has expired or already been used.")

    user = token.user
    user.is_email_verified = True
    user.save(update_fields=["is_email_verified"])
    token.consume()

    logger.info("Email verified for user %s", user.email)
    return user


# ---------------------------------------------------------------------------
# Password recovery
# ---------------------------------------------------------------------------


PASSWORD_RESET_SALT = "oneprompt.password-reset"
PASSWORD_RESET_MAX_AGE = 60 * 60


def request_password_reset(*, email: str) -> None:
    """Log a one-hour reset link when the account exists.

    The caller always returns the same response to avoid exposing registered
    email addresses.
    """
    user = User.objects.filter(email=email.lower().strip(), is_active=True).first()
    if not user:
        return

    token = signing.dumps(user.email, salt=PASSWORD_RESET_SALT)
    reset_link = f"{_frontend_url()}/reset-password?token={token}"
    logger.info("[DEV EMAIL] Reset password for %s: %s", user.email, reset_link)


def reset_password(*, token: str, password: str) -> User:
    try:
        email = signing.loads(
            token,
            salt=PASSWORD_RESET_SALT,
            max_age=PASSWORD_RESET_MAX_AGE,
        )
    except signing.SignatureExpired as exc:
        raise ValueError("This password reset link has expired.") from exc
    except signing.BadSignature as exc:
        raise ValueError("This password reset link is invalid.") from exc

    try:
        user = User.objects.get(email=email, is_active=True)
    except User.DoesNotExist as exc:
        raise ValueError("This password reset link is invalid.") from exc

    user.set_password(password)
    user.save(update_fields=["password"])
    revoke_user_tokens(user)
    logger.info("Password reset completed for %s", user.email)
    return user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _frontend_url():
    return getattr(settings, "FRONTEND_URL", "http://localhost:3000")
