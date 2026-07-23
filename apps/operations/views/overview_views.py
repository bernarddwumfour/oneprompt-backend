"""GET /api/v1/operations/overview — admin-only commercial metrics."""

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.operations.selectors.operations_selectors import get_overview
from common.decorators import jwt_required, role_required
from common.responses import APIResponse


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def overview_view(request):
    currency = request.GET.get("currency", "GHS").upper()
    period = request.GET.get("period", "month")
    metrics = get_overview(currency=currency, period=period)
    return APIResponse.success(data=metrics)
