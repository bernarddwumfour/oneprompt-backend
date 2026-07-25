"""GET /api/v1/operations/audit-logs — read-only admin audit log list."""

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from shared.models import SystemLog
from common.decorators import jwt_required, role_required
from common.responses import APIResponse
from common.utils import parse_pagination


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def audit_log_list_view(request):
    severity = request.GET.get("severity", "")
    app_name = request.GET.get("app_name", "")
    action = request.GET.get("action", "")

    qs = SystemLog.objects.order_by("-created_at")
    if severity:
        qs = qs.filter(severity=severity)
    if app_name:
        qs = qs.filter(app_name=app_name)
    if action:
        qs = qs.filter(action=action)

    try:
        page, limit = parse_pagination(request)
    except ValueError as e:
        return APIResponse.bad_request(str(e))

    total = qs.count()
    offset = (page - 1) * limit
    logs = qs[offset : offset + limit]

    return APIResponse.success(
        data={
            "logs": [
                {
                    "id": str(log.id),
                    "app_name": log.app_name,
                    "action": log.action,
                    "severity": log.severity,
                    "description": log.description,
                    "user_email": log.user_email,
                    "ip_address": log.ip_address,
                    "path": log.path,
                    "created_at": log.created_at.isoformat(),
                }
                for log in logs
            ],
            "total": total,
            "page": page,
            "limit": limit,
        }
    )
