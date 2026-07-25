"""
Shared utilities — small helpers used across the project.
"""

import secrets
import unicodedata
from typing import Optional


def generate_token(length: int = 32) -> str:
    """Return a URL-safe random token string."""
    return secrets.token_urlsafe(length)


def parse_pagination(request, default_limit: int = 20, max_limit: int = 100) -> tuple[int, int]:
    """Parse and validate ``page``/``limit`` query params.

    Raises ValueError (with a user-facing message — callers should map it to
    APIResponse.bad_request) instead of letting a non-integer value raise an
    uncaught exception. Clamps limit to *max_limit* regardless of what the
    caller requests.
    """
    try:
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", default_limit))
    except ValueError:
        raise ValueError("page and limit must be integers.")

    if page < 1 or limit < 1:
        raise ValueError("page and limit must be positive integers.")

    return page, min(limit, max_limit)


def parse_int_query_param(
    request, name: str, default: int, *, min_value: int = 1, max_value: int | None = None
) -> int:
    """Parse and validate a single integer query param.

    Same purpose as ``parse_pagination`` (guards against the recurring
    ``int(request.GET.get(...))`` crash on non-numeric input) generalized to
    any single named param, e.g. ``days`` on the analytics endpoints.
    Raises ValueError — callers should map it to APIResponse.bad_request.
    """
    try:
        value = int(request.GET.get(name, default))
    except ValueError:
        raise ValueError(f"{name} must be an integer.")

    if value < min_value:
        raise ValueError(f"{name} must be at least {min_value}.")
    if max_value is not None and value > max_value:
        raise ValueError(f"{name} must be at most {max_value}.")

    return value


def slugify(value: str, max_length: int = 120) -> str:
    """Poor man's slug — normalize unicode, lowercase, replace spaces with dashes."""
    value = (
        unicodedata.normalize("NFKD", str(value))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    value = value.strip().lower()
    # Replace runs of whitespace / hyphens with a single dash
    import re

    value = re.sub(r"[-\s]+", "-", value)
    return value[:max_length].strip("-")
