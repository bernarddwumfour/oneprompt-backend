"""Shared SystemLog writer — used by every admin mutation this plan touches."""

from shared.models import SystemLog


def log_admin_action(
    *,
    actor,
    app_name: str,
    action: str,
    description: str,
    severity: str = "info",
    request=None,
    extra_data: dict | None = None,
) -> SystemLog:
    """Write one SystemLog row for an admin-initiated action."""
    kwargs = dict(
        app_name=app_name,
        action=action,
        severity=severity,
        description=description,
        user_id=str(actor.id) if actor else None,
        user_email=actor.email if actor else None,
        extra_data=extra_data or {},
    )
    if request is not None:
        kwargs["path"] = request.path
        kwargs["method"] = request.method
        kwargs["ip_address"] = request.META.get("REMOTE_ADDR")
    return SystemLog.objects.create(**kwargs)
