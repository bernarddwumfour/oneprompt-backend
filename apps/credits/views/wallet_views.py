"""Wallet views — GET wallet, GET wallet/ledger."""

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.credits.schemas.wallet_schemas import (
    serialize_ledger_entry,
    serialize_wallet,
)
from apps.credits.selectors.wallet_selectors import get_wallet_for_user, get_wallet_ledger
from common.decorators import jwt_required
from common.responses import APIResponse
from common.utils import parse_pagination


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def wallet_view(request):
    wallet = get_wallet_for_user(request.user)
    if wallet is None:
        return APIResponse.not_found("Wallet not found.")
    return APIResponse.success(data={"wallet": serialize_wallet(wallet)})


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def wallet_ledger_view(request):
    wallet = get_wallet_for_user(request.user)
    if wallet is None:
        return APIResponse.not_found("Wallet not found.")

    try:
        page, limit = parse_pagination(request)
    except ValueError as e:
        return APIResponse.bad_request(str(e))

    entry_type = request.GET.get("entry_type", "")

    results, total = get_wallet_ledger(wallet, page=page, limit=limit, entry_type=entry_type)
    return APIResponse.success(
        data={
            "entries": [serialize_ledger_entry(e) for e in results],
            "total": total,
            "page": page,
            "limit": limit,
        }
    )
