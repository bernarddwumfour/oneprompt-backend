"""Audit log selectors — read-only queries over SystemLog."""

from django.db.models import Q

from shared.models import SystemLog


def list_audit_logs(
    *, search: str = "", severity: str = "", app_name: str = "", action: str = "",
    ordering: str = "-created_at",
):
    """Filtered, ordered SystemLog queryset for the admin audit log list."""
    qs = SystemLog.objects.all()
    if search:
        qs = qs.filter(
            Q(description__icontains=search)
            | Q(user_email__icontains=search)
            | Q(path__icontains=search)
        )
    if severity:
        qs = qs.filter(severity=severity)
    if app_name:
        qs = qs.filter(app_name=app_name)
    if action:
        qs = qs.filter(action=action)
    return qs.order_by(ordering, "id")
