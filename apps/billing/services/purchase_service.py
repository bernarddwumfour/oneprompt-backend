"""Purchase service — create_purchase, confirm_purchase.

Per plan 0002 trust model: webhook payload and browser redirect are both
untrusted. Every credit is granted only after independently verifying with
Paystack's API.
"""

import logging
from decimal import Decimal
from urllib.parse import urlencode

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


def create_purchase(
    *,
    user,
    credit_pack_id: str | None = None,
    flexible_amount: int | None = None,
    return_context: dict[str, str] | None = None,
) -> dict:
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
        wallet = user.wallet
        if wallet.currency not in PAYSTACK_CURRENCIES:
            supported = ", ".join(sorted(PAYSTACK_CURRENCIES))
            raise ValueError(
                f"Paystack only supports {supported}. "
                f"Your wallet currency ({wallet.currency}) is not supported yet."
            )

        if flexible_amount is not None:
            if wallet.currency != "GHS":
                raise ValueError("Flexible top-ups are currently available for GHS wallets.")
            if (
                isinstance(flexible_amount, bool)
                or not isinstance(flexible_amount, int)
                or flexible_amount < 10
            ):
                raise ValueError(
                    "Flexible top-up must be a positive whole number of at least GH₵10."
                )
            pack = None
            currency = "GHS"
            amount_minor_units = flexible_amount * 100
            amount_credits = Decimal(flexible_amount) * Decimal("5.00")
        else:
            try:
                pack = CreditPack.objects.get(id=credit_pack_id, is_active=True)
            except (CreditPack.DoesNotExist, ValueError):
                raise ValueError("Credit pack not found or unavailable.")

            if pack.currency != wallet.currency:
                raise ValueError(
                    f"This pack is denominated in {pack.currency} "
                    f"but your wallet is {wallet.currency}."
                )
            currency = pack.currency
            amount_minor_units = pack.price_minor_units
            amount_credits = pack.amount_credits

        reference = generate_token(32)

        purchase = Purchase.objects.create(
            user=user,
            credit_pack=pack,
            reference=reference,
            status="pending",
            currency=currency,
            amount_minor_units=amount_minor_units,
            amount_credits=amount_credits,
        )

    # Deliberately outside the transaction above: if Paystack initialize
    # fails, we still want the Purchase row (and the "failed" mark below)
    # to persist as an audit trail, not be rolled back with it.
    client = PaystackClient()
    callback_query = urlencode(
        {
            "purchase_id": str(purchase.id),
            **(return_context or {}),
        }
    )
    callback_url = f"{settings.FRONTEND_URL}/billing/return?{callback_query}"

    try:
        result = client.initialize_transaction(
            email=user.email,
            amount_minor_units=purchase.amount_minor_units,
            currency=purchase.currency,
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
def settle_purchase(*, purchase: Purchase, webhook_body: dict | None = None) -> Purchase:
    """Independently verify *purchase* with Paystack and apply the settled
    status. Idempotent — a purchase that's already resolved (anything but
    "pending") is returned unchanged, so it's safe to call this more than
    once for the same purchase.

    Per plan 0006's follow-up: called from two trigger points that share
    this exact settlement logic —
    - the Paystack webhook (`confirm_purchase`, below), after verifying the
      webhook's HMAC signature; only reachable when the webhook URL is
      publicly resolvable (i.e. never in local dev against localhost).
    - the frontend's verify-on-return call (`purchase_detail_view`'s POST
      handler) the moment the user's browser lands back on
      /billing/return?purchase_id=... — this is a normal outbound call from
      our server to Paystack's API, so it works identically in local dev
      and in production. This is the primary confirmation path; the webhook
      remains as an idempotent backup for when the browser never returns.

    Raises PaystackError if Paystack's verify call itself fails (network,
    timeout, 5xx) — deliberately NOT caught here and NOT treated as a
    confirmed payment failure: the purchase stays "pending" so a retry
    (another webhook delivery, or the frontend polling again) can still
    resolve it correctly once Paystack is reachable again.
    """
    if purchase.status != "pending":
        return purchase

    result = PaystackClient().verify_transaction(reference=purchase.reference)

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

        # Credit wallet — idempotency key guarantees exactly-once even if
        # both the webhook and the verify-on-return call race each other.
        purchase_credit(
            wallet=purchase.user.wallet,
            amount=purchase.amount_credits,
            idempotency_key=f"paystack:{purchase.reference}",
            reference={
                "purchase_id": str(purchase.id),
                "paystack_reference": payment.paystack_reference,
            },
        )
        logger.info("Purchase %s confirmed, wallet credited.", purchase.reference)
    else:
        purchase.status = "failed"
        purchase.save(update_fields=["status"])
        logger.info(
            "Purchase %s marked failed (Paystack status: %s)",
            purchase.reference,
            paystack_status,
        )

    return purchase


def confirm_purchase(
    *, reference: str, raw_body: bytes, signature: str, webhook_body: dict
) -> Purchase:
    """Process a Paystack webhook: verify signature, then delegate to the
    shared settlement logic in `settle_purchase`.

    Raises ValueError on invalid signature or unknown reference.
    """
    if not PaystackClient.verify_signature(raw_body, signature):
        raise ValueError("Invalid webhook signature")

    try:
        purchase = Purchase.objects.select_related("credit_pack", "user__wallet").get(
            reference=reference
        )
    except Purchase.DoesNotExist:
        raise ValueError(f"Unknown purchase reference: {reference}")

    return settle_purchase(purchase=purchase, webhook_body=webhook_body)
