"""Purchase service — create_purchase, confirm_purchase.

Per plan 0002 trust model: webhook payload and browser redirect are both
untrusted. Every credit is granted only after independently verifying with
Paystack's API.
"""

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.billing.models import (
    PAYSTACK_CURRENCIES,
    CreditPack,
    Payment,
    Purchase,
)
from apps.billing.services.paystack_client import PaystackClient, PaystackError
from apps.credits.services.ledger_service import purchase_credit
from common.utils import generate_token

logger = logging.getLogger(__name__)


def create_purchase(*, user, credit_pack_id: str) -> dict:
    """Create a pending Purchase + Payment, call Paystack, return auth URL.

    Raises ValueError if:
    - The credit pack doesn't exist or is inactive
    - The user's wallet currency isn't supported by Paystack
    Raises PaystackError if Paystack itself can't be reached/rejects the
    request — the Purchase row still persists (status="failed") so the
    attempt is auditable, since it's created in its own transaction below
    rather than one shared with the Paystack call.
    """
    with transaction.atomic():
        try:
            pack = CreditPack.objects.get(id=credit_pack_id, is_active=True)
        except CreditPack.DoesNotExist:
            raise ValueError("Credit pack not found or unavailable.")

        wallet = user.wallet
        if wallet.currency not in PAYSTACK_CURRENCIES:
            supported = ", ".join(sorted(PAYSTACK_CURRENCIES))
            raise ValueError(
                f"Paystack only supports {supported}. "
                f"Your wallet currency ({wallet.currency}) is not supported yet."
            )

        if pack.currency != wallet.currency:
            raise ValueError(
                f"This pack is denominated in {pack.currency} "
                f"but your wallet is {wallet.currency}."
            )

        reference = generate_token(32)

        purchase = Purchase.objects.create(
            user=user,
            credit_pack=pack,
            reference=reference,
            status="pending",
            currency=pack.currency,
            amount_minor_units=pack.price_minor_units,
        )

    # Deliberately outside the transaction above: if Paystack initialize
    # fails, we still want the Purchase row (and the "failed" mark below)
    # to persist as an audit trail, not be rolled back with it.
    client = PaystackClient()
    callback_url = f"{settings.FRONTEND_URL}/billing/return?purchase_id={purchase.id}"

    try:
        result = client.initialize_transaction(
            email=user.email,
            amount_minor_units=pack.price_minor_units,
            currency=pack.currency,
            reference=reference,
            callback_url=callback_url,
        )
    except Exception as e:
        purchase.status = "failed"
        purchase.save(update_fields=["status"])
        logger.error("Paystack initialize failed for %s: %s", reference, e)
        raise

    paystack_ref = result.get("data", {}).get("reference", reference)
    authorization_url = result.get("data", {}).get("authorization_url", "")

    Payment.objects.create(
        purchase=purchase,
        paystack_reference=paystack_ref,
    )

    return {
        "purchase_id": str(purchase.id),
        "reference": reference,
        "authorization_url": authorization_url,
    }


@transaction.atomic
def confirm_purchase(
    *, reference: str, raw_body: bytes, signature: str, webhook_body: dict
) -> Purchase:
    """Process a Paystack webhook: verify signature, verify with Paystack,
    credit wallet exactly once.

    Raises ValueError on invalid signature or unknown reference.
    Raises PaystackError if Paystack's verify call itself fails (network,
    timeout, 5xx) — this is deliberately NOT caught here and NOT treated as
    a confirmed payment failure: the purchase stays "pending" and the
    caller (the webhook view) should return a non-2xx so Paystack retries
    delivery rather than us guessing at an outcome we don't actually know.
    Returns the Purchase.
    """
    # 1. Verify HMAC signature before touching the DB
    if not PaystackClient.verify_signature(raw_body, signature):
        raise ValueError("Invalid webhook signature")

    # 2. Look up the purchase
    try:
        purchase = Purchase.objects.select_related("credit_pack", "user__wallet").get(
            reference=reference
        )
    except Purchase.DoesNotExist:
        raise ValueError(f"Unknown purchase reference: {reference}")

    # Already settled — idempotent
    if purchase.status != "pending":
        return purchase

    # 3. Independently verify with Paystack (never trust webhook body alone).
    # Let PaystackError propagate on failure — see docstring.
    result = PaystackClient().verify_transaction(reference=reference)

    paystack_data = result.get("data", {})
    paystack_status = paystack_data.get("status", "")

    payment = purchase.payment
    payment.paystack_status = paystack_status
    payment.raw_webhook_payload = {
        "webhook_body": webhook_body,
        "verify_response": result,
    }
    payment.verified_at = timezone.now()
    payment.save()

    if paystack_status == "success":
        purchase.status = "success"
        purchase.confirmed_at = timezone.now()
        purchase.save(update_fields=["status", "confirmed_at"])

        # 4. Credit wallet — idempotency key guarantees exactly-once
        purchase_credit(
            wallet=purchase.user.wallet,
            amount=purchase.credit_pack.amount_credits,
            idempotency_key=f"paystack:{reference}",
            reference={
                "purchase_id": str(purchase.id),
                "paystack_reference": payment.paystack_reference,
            },
        )
        logger.info("Purchase %s confirmed, wallet credited.", reference)
    else:
        purchase.status = "failed"
        purchase.save(update_fields=["status"])
        logger.info("Purchase %s marked failed (Paystack status: %s)", reference, paystack_status)

    return purchase
