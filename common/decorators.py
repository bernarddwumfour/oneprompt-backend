"""
Shared decorators — jwt_required, role_required, rate_limit.

Per BACKEND-RULES.main.md §6 & §11: auth decorators are the single enforcement
point; never check auth inline in a view.
"""

import functools
import logging
import time

from django.core.cache import cache
from django.http import HttpRequest, JsonResponse

from common.jwt import decode_token
from common.responses import APIResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_bearer_token(request: HttpRequest) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None


def _resolve_user(token: str):
    """Decode *token* and return the corresponding User, or None."""
    from apps.accounts.models import User

    try:
        payload = decode_token(token)
    except Exception:
        return None

    if payload.get("type") != "access":
        return None

    try:
        return User.objects.get(id=payload["sub"])
    except User.DoesNotExist:
        return None


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def jwt_required(view_func):
    """Require a valid ``Authorization: Bearer <access_token>`` header.

    On success attaches ``request.user``. Returns 401 on any failure.
    """

    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        token = _get_bearer_token(request)
        if not token:
            return APIResponse.unauthorized("Authentication required")

        user = _resolve_user(token)
        if user is None:
            return APIResponse.unauthorized("Invalid or expired token")

        if not user.is_active:
            return APIResponse.unauthorized("Account is disabled")

        request.user = user
        return view_func(request, *args, **kwargs)

    return wrapper


def role_required(*allowed_roles: str):
    """Require ``request.user`` to have one of *allowed_roles*.

    Must be stacked **below** ``@jwt_required`` so ``request.user`` exists.
    Currently only supports ``"admin"`` (checks ``is_staff``) per plan §Decisions.
    """

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = getattr(request, "user", None)
            if user is None:
                return APIResponse.unauthorized("Authentication required")

            if "admin" in allowed_roles and user.is_staff:
                return view_func(request, *args, **kwargs)

            return APIResponse.forbidden("Insufficient permissions")

        return wrapper

    return decorator


def rate_limit(key_func, limit: int, window_seconds: int = 60):
    """Simple local-memory rate limiter backed by Django's default cache.

    *key_func* receives (request) and must return a string key (e.g.
    ``f"login:{email}:{ip}"``). Returns 429 once *limit* is exceeded inside
    *window_seconds*.

    NOTE: single-process only until Redis is introduced; documented per plan.
    """

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            key = f"rl:{key_func(request)}"
            attempts = cache.get(key, 0)
            if attempts >= limit:
                logger.warning("Rate limit hit: %s", key)
                return JsonResponse(
                    {"success": False, "message": "Too many requests. Try again shortly."},
                    status=429,
                )
            cache.set(key, attempts + 1, timeout=window_seconds)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
