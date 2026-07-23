"""Paystack webhook view — idempotent, signature-verified.

Per plan 0002: never trust the webhook body alone. Verify HMAC signature
first, then independently verify the transaction with Paystack's API.
"""

import json
import logging

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.billing.services.paystack_client import PaystackError
from apps.billing.services.purchase_service import confirm_purchase
from common.responses import APIResponse

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def paystack_webhook_view(request):
    """POST /api/v1/billing/webhooks/paystack

    Reads the raw body for HMAC signature verification before any JSON
    parsing. Returns 200 once a payment outcome is actually settled
    (success or a status Paystack itself reports as failed), 401 for a
    genuinely invalid signature, and 5xx when *our* verify call couldn't
    reach Paystack — a 5xx tells Paystack to retry delivery instead of us
    guessing at an outcome we don't actually know yet.
    """
    raw_body = request.body
    signature = request.headers.get("X-Paystack-Signature", "")

    # 1. Verify signature
    if not signature:
        logger.warning("Paystack webhook: missing signature header")
        return APIResponse.unauthorized("Missing signature")

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON body")

    reference = body.get("data", {}).get("reference", "")

    try:
        confirm_purchase(
            reference=reference,
            raw_body=raw_body,
            signature=signature,
            webhook_body=body,
        )
    except ValueError as e:
        if "Invalid webhook signature" in str(e):
            return APIResponse.unauthorized("Invalid signature")
        if "Unknown purchase reference" in str(e):
            return APIResponse.not_found(str(e))
        logger.exception("Webhook processing failed")
        return APIResponse.server_error("Webhook processing failed")
    except PaystackError as e:
        logger.error("Paystack verify unavailable for %s: %s", reference, e)
        return APIResponse.server_error("Temporarily unable to verify payment.")

    return APIResponse.success(message="Webhook received.")
