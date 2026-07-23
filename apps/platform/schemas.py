"""Platform serialization."""


def serialize_platform_settings(settings_obj) -> dict:
    return {
        "mode": settings_obj.mode,
        "updated_at": settings_obj.updated_at.isoformat(),
        "updated_by_email": (
            settings_obj.updated_by.email if settings_obj.updated_by else None
        ),
    }
