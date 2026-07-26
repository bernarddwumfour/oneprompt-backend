"""
Shared utilities — small helpers used across the project.
"""

import secrets
import unicodedata
from datetime import datetime
from typing import Optional
from urllib.parse import parse_qs


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


def parse_ordering(request, allowed_fields: dict[str, str], default: str) -> str:
    """Return a validated Django ``order_by`` expression from URL params."""
    sort_by = request.GET.get("sort_by", "").strip()
    sort_order = request.GET.get("sort_order", "desc").strip().lower()
    if sort_order not in {"asc", "desc"}:
        raise ValueError("sort_order must be either asc or desc.")
    if not sort_by:
        return default
    field = allowed_fields.get(sort_by)
    if field is None:
        raise ValueError(
            f"sort_by must be one of: {', '.join(sorted(allowed_fields))}."
        )
    return field if sort_order == "asc" else f"-{field}"


def parse_optional_bool(request, name: str) -> bool | None:
    """Parse an optional true/false query parameter."""
    raw = request.GET.get(name, "").strip().lower()
    if not raw:
        return None
    if raw not in {"true", "false"}:
        raise ValueError(f"{name} must be either true or false.")
    return raw == "true"


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


def parse_date_range_param(request, name: str) -> tuple[datetime | None, datetime | None]:
    """Parse a `date_range` filter param encoded as ``from=<iso>&to=<iso>``.

    Matches the wire format produced by the frontend's `CustomFilterFromUrl`
    `date_range` field type (`valueToUrlParam` in
    `CustomFilterFromUrl.tsx`), which packs both bounds into one query param
    value. Either bound may be absent. Malformed values are treated as
    absent rather than raising — a bad date filter should show unfiltered
    results, not a 500.
    """
    raw = request.GET.get(name, "")
    if not raw:
        return None, None
    parsed = parse_qs(raw)
    from_str = parsed.get("from", [None])[0]
    to_str = parsed.get("to", [None])[0]
    from_dt = _parse_iso_datetime(from_str) if from_str else None
    to_dt = _parse_iso_datetime(to_str) if to_str else None
    return from_dt, to_dt


def _parse_iso_datetime(value: str) -> datetime | None:
    from django.utils.dateparse import parse_datetime

    try:
        return parse_datetime(value)
    except (ValueError, TypeError):
        return None


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
