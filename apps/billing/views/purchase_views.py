"""Purchase views — list packs, create purchase, check status."""

import json
import logging

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.billing.schemas.purchase_schemas import (
    serialize_credit_pack,
    serialize_purchase,
)
from apps.billing.selectors.purchase_selectors import (
    get_purchase_for_user,
    list_active_credit_packs,
)
from apps.billing.services.purchase_service import create_purchase
from common.decorators import jwt_required
from common.responses import APIResponse

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET"])
def credit_packs_view(request):
    """GET /billing/credit-packs — public list of available packs."""
    packs = list_active_credit_packs()
    return APIResponse.success(
        data={"packs": [serialize_credit_pack(p) for p in packs]}
    )


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
def create_purchase_view(request):
    """POST /billing/purchases — start a new purchase."""
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")

    credit_pack_id = body.get("credit_pack_id", "")
    if not credit_pack_id:
        return APIResponse.bad_request("credit_pack_id is required.")

    try:
        result = create_purchase(user=request.user, credit_pack_id=credit_pack_id)
    except ValueError as e:
        return APIResponse.bad_request(str(e))
    except Exception as e:
        logger.error("Purchase creation failed: %s", e)
        return APIResponse.server_error("Unable to initialize payment. Please try again.")

    return APIResponse.created(data=result, message="Purchase created.")


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def purchase_detail_view(request, purchase_id):
    """GET /billing/purchases/{id} — poll for purchase status."""
    purchase = get_purchase_for_user(purchase_id, request.user)
    if purchase is None:
        return APIResponse.not_found("Purchase not found.")

    return APIResponse.success(data={"purchase": serialize_purchase(purchase)})
