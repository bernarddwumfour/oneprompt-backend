"""GET /api/v1/operations/audit-logs — read-only admin audit log list."""

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.operations.selectors.audit_selectors import list_audit_logs
from common.decorators import jwt_required, role_required
from common.responses import APIResponse
from common.utils import parse_ordering, parse_pagination


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def audit_log_list_view(request):
    try:
        page, limit = parse_pagination(request)
        ordering = parse_ordering(request, {
            "created_at": "created_at", "severity": "severity",
            "app_name": "app_name", "action": "action",
            "status_code": "status_code", "user_email": "user_email",
        }, "-created_at")
    except ValueError as e:
        return APIResponse.bad_request(str(e))

    qs = list_audit_logs(
        search=request.GET.get("search", ""),
        severity=request.GET.get("severity", ""),
        app_name=request.GET.get("app_name", ""),
        action=request.GET.get("action", ""),
        ordering=ordering,
    )
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
                    "status_code": log.status_code,
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
