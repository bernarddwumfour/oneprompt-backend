"""GET /api/v1/operations/invocations — admin invocation listing."""

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.operations.selectors.operations_selectors import list_invocations
from common.decorators import jwt_required, role_required
from common.responses import APIResponse
from common.utils import parse_date_range_param, parse_ordering, parse_pagination


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def invocation_list_view(request):
    status = request.GET.get("status", "")
    capability = request.GET.get("capability", "")
    try:
        page, limit = parse_pagination(request)
        ordering = parse_ordering(request, {
            "created_at": "created_at", "status": "status",
            "capability": "capability", "input_tokens": "input_tokens",
            "output_tokens": "output_tokens", "credits_charged": "credits_charged",
            "provider_cost_usd": "provider_cost_usd",
        }, "-created_at")
    except ValueError as e:
        return APIResponse.bad_request(str(e))
    created_from, created_to = parse_date_range_param(request, "created_at")
    result = list_invocations(
        search=request.GET.get("search", ""), status=status,
        capability=capability, created_from=created_from, created_to=created_to,
        page=page, limit=limit, ordering=ordering,
    )
    return APIResponse.success(data=result)
