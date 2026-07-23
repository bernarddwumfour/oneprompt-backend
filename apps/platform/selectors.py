"""Platform selectors — read-only access to PlatformSettings."""

from apps.platform.models import PlatformSettings


def get_platform_settings():
    """Return the singleton PlatformSettings row (guaranteed by migration)."""
    return PlatformSettings.objects.select_related("updated_by").first()


def get_platform_mode() -> str:
    """Return the current platform mode ('test' or 'live')."""
    obj = get_platform_settings()
    return obj.mode if obj else "test"
