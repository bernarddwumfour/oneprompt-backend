"""GET /api/v1/operations/ledger — admin global ledger view."""

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.operations.selectors.operations_selectors import list_ledger_entries
from common.decorators import jwt_required, role_required
from common.responses import APIResponse
from common.utils import parse_pagination


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def ledger_list_view(request):
    entry_type = request.GET.get("entry_type", "")
    currency = request.GET.get("currency", "")
    try:
        page, limit = parse_pagination(request)
    except ValueError as e:
        return APIResponse.bad_request(str(e))
    result = list_ledger_entries(entry_type=entry_type, currency=currency, page=page, limit=limit)
    return APIResponse.success(data=result)
