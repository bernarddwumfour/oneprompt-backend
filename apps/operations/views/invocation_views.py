"""GET /api/v1/operations/invocations — admin invocation listing."""

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.operations.selectors.operations_selectors import list_invocations
from common.decorators import jwt_required, role_required
from common.responses import APIResponse
from common.utils import parse_pagination


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def invocation_list_view(request):
    status = request.GET.get("status", "")
    capability = request.GET.get("capability", "")
    try:
        page, limit = parse_pagination(request)
    except ValueError as e:
        return APIResponse.bad_request(str(e))
    result = list_invocations(status=status, capability=capability, page=page, limit=limit)
    return APIResponse.success(data=result)
