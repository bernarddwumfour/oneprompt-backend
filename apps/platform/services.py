"""Platform services — mutation operations."""

from apps.platform.selectors import get_platform_settings

VALID_MODES = {"test", "live"}


def set_platform_mode(*, mode: str, actor):
    """Set the platform mode. Raises ValueError for invalid modes."""
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid mode '{mode}'. Must be 'test' or 'live'.")
    obj = get_platform_settings()
    obj.mode = mode
    obj.updated_by = actor
    obj.save(update_fields=["mode", "updated_by", "updated_at"])
    return obj
