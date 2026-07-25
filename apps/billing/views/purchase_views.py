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
from apps.billing.services.paystack_client import PaystackError
from apps.billing.services.purchase_service import create_purchase, settle_purchase
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

    credit_pack_id = body.get("credit_pack_id")
    flexible_amount = body.get("flexible_amount")
    if not credit_pack_id and flexible_amount is None:
        return APIResponse.bad_request(
            "credit_pack_id or flexible_amount is required."
        )

    try:
        result = create_purchase(
            user=request.user,
            credit_pack_id=credit_pack_id,
            flexible_amount=flexible_amount,
        )
    except ValueError as e:
        return APIResponse.bad_request(str(e))
    except Exception as e:
        logger.error("Purchase creation failed: %s", e)
        return APIResponse.server_error("Unable to initialize payment. Please try again.")

    return APIResponse.created(data=result, message="Purchase created.")


@csrf_exempt
@require_http_methods(["GET", "POST"])
@jwt_required
def purchase_detail_view(request, purchase_id):
    """GET /billing/purchases/{id} — read current purchase status.

    POST /billing/purchases/{id} — verify-on-return: synchronously re-check
    with Paystack right now instead of only waiting on the webhook, which
    can't reach a local dev server at all (and can be slow/lost even in
    production). This is what the frontend's /billing/return page calls the
    moment the user's browser lands back from Paystack's checkout.
    Idempotent — safe to call more than once for the same purchase.
    """
    purchase = get_purchase_for_user(purchase_id, request.user)
    if purchase is None:
        return APIResponse.not_found("Purchase not found.")

    if request.method == "POST":
        try:
            purchase = settle_purchase(purchase=purchase)
        except PaystackError as e:
            logger.error("Verify-on-return failed for purchase %s: %s", purchase_id, e)
            return APIResponse.server_error(
                "Unable to verify payment right now. Please try again shortly."
            )

    return APIResponse.success(data={"purchase": serialize_purchase(purchase)})
