"""
Auth views — signup, login, logout, refresh, verify-email, me.

Per BACKEND-RULES.main.md §4: function-based views, thin coordinators.
"""

import json
import logging

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.accounts.schemas.auth_schemas import (
    ValidationError,
    serialize_user,
    validate_login,
    validate_forgot_password,
    validate_google_login,
    validate_reset_password,
    validate_signup,
    validate_verify_email,
)
from apps.accounts.services.auth_service import (
    authenticate_user,
    authenticate_google_user,
    GoogleOAuthError,
    request_password_reset,
    reset_password,
    refresh_token_pair,
    revoke_user_tokens,
    signup,
    verify_email,
)
from common.decorators import jwt_required, rate_limit
from common.responses import APIResponse

logger = logging.getLogger(__name__)


def _client_ip(request):
    # NOTE: X-Forwarded-For is client-supplied and trivially spoofable unless
    # this app sits behind a proxy configured to strip/overwrite it. Until
    # that trusted-proxy setup exists, only REMOTE_ADDR is safe to key
    # rate-limiting on.
    return request.META.get("REMOTE_ADDR", "")


def _login_rate_limit_key(request):
    try:
        body = json.loads(request.body or b"{}")
        email = (body.get("email") or "").strip().lower()
    except (json.JSONDecodeError, UnicodeDecodeError):
        email = ""
    return f"login:{email}:{_client_ip(request)}"


# ---------------------------------------------------------------------------
# POST /api/v1/auth/signup
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
def signup_view(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")

    try:
        cleaned = validate_signup(body)
    except ValidationError as e:
        return APIResponse.validation_error(e.errors)

    try:
        user = signup(**cleaned)
    except ValueError as e:
        return APIResponse.bad_request(str(e))

    logger.info("User signed up: %s", user.email)
    return APIResponse.created(
        data={"user": serialize_user(user)},
        message="Account created. Check your console/dev log for the verification link.",
    )


# ---------------------------------------------------------------------------
# POST /api/v1/auth/login
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
@rate_limit(_login_rate_limit_key, limit=10, window_seconds=60)
def login_view(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")

    try:
        cleaned = validate_login(body)
    except ValidationError as e:
        return APIResponse.validation_error(e.errors)

    try:
        result = authenticate_user(email=cleaned["email"], password=cleaned["password"])
    except ValueError as e:
        return APIResponse.unauthorized(str(e))

    return APIResponse.success(data=result, message="Login successful.")


@csrf_exempt
@require_http_methods(["POST"])
@rate_limit(lambda r: f"google-login:{_client_ip(r)}", limit=10, window_seconds=60)
def google_login_view(request):
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return APIResponse.bad_request("Invalid Google login request.")

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")

    try:
        code = validate_google_login(body)
    except ValidationError as e:
        return APIResponse.validation_error(e.errors)

    try:
        result = authenticate_google_user(code=code)
    except GoogleOAuthError as e:
        return APIResponse.bad_request(str(e))

    return APIResponse.success(data=result, message="Google login successful.")


# ---------------------------------------------------------------------------
# POST /api/v1/auth/logout
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
def logout_view(request):
    revoke_user_tokens(request.user)
    return APIResponse.success(message="Logged out.")


# ---------------------------------------------------------------------------
# POST /api/v1/auth/refresh
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
def refresh_view(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")

    refresh_token = body.get("refresh_token", "")
    if not refresh_token:
        return APIResponse.bad_request("refresh_token is required.")

    try:
        result = refresh_token_pair(refresh_token)
    except ValueError as e:
        return APIResponse.unauthorized(str(e))

    return APIResponse.success(data=result, message="Token refreshed.")


# ---------------------------------------------------------------------------
# POST /api/v1/auth/verify-email
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
def verify_email_view(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")

    try:
        token_str = validate_verify_email(body)
    except ValidationError as e:
        return APIResponse.validation_error(e.errors)

    try:
        user = verify_email(token_str=token_str)
    except ValueError as e:
        return APIResponse.bad_request(str(e))

    return APIResponse.success(
        data={"user": serialize_user(user)},
        message="Email verified successfully.",
    )


# ---------------------------------------------------------------------------
# POST /api/v1/auth/forgot-password
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
def forgot_password_view(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")

    try:
        email = validate_forgot_password(body)
    except ValidationError as e:
        return APIResponse.validation_error(e.errors)

    request_password_reset(email=email)
    return APIResponse.success(
        message=(
            "If an account exists for that email, a password reset link has "
            "been sent."
        )
    )


# ---------------------------------------------------------------------------
# POST /api/v1/auth/reset-password
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
def reset_password_view(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")

    try:
        cleaned = validate_reset_password(body)
    except ValidationError as e:
        return APIResponse.validation_error(e.errors)

    try:
        reset_password(token=cleaned["token"], password=cleaned["password"])
    except ValueError as e:
        return APIResponse.bad_request(str(e))

    return APIResponse.success(message="Password reset successfully.")


# ---------------------------------------------------------------------------
# GET /api/v1/me
# ---------------------------------------------------------------------------


@csrf_exempt
@jwt_required
def me_view(request):
    return APIResponse.success(data={"user": serialize_user(request.user)})
