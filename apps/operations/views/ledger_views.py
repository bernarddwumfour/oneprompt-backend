"""GET /api/v1/operations/ledger — admin global ledger view."""

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.operations.selectors.operations_selectors import list_ledger_entries
from common.decorators import jwt_required, role_required
from common.responses import APIResponse
from common.utils import parse_date_range_param, parse_ordering, parse_pagination


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def ledger_list_view(request):
    entry_type = request.GET.get("entry_type", "")
    currency = request.GET.get("currency", "")
    try:
        page, limit = parse_pagination(request)
        ordering = parse_ordering(request, {
            "created_at": "created_at", "entry_type": "entry_type",
            "amount": "amount", "currency": "wallet__currency",
            "user_email": "wallet__user__email",
        }, "-created_at")
    except ValueError as e:
        return APIResponse.bad_request(str(e))
    created_from, created_to = parse_date_range_param(request, "created_at")
    result = list_ledger_entries(
        search=request.GET.get("search", ""), entry_type=entry_type,
        currency=currency, created_from=created_from, created_to=created_to,
        page=page, limit=limit, ordering=ordering,
    )
    return APIResponse.success(data=result)
