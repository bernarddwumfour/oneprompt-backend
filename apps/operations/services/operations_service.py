"""Operations service — thin wrapper for admin actions with audit logging."""

import logging
import uuid
from decimal import Decimal

from apps.credits.services.ledger_service import admin_correct
from apps.credits.selectors.wallet_selectors import get_wallet_for_user

logger = logging.getLogger(__name__)


def correct_wallet(
    *,
    user,
    amount: Decimal,
    direction: str,
    reason: str,
    actor,
    idempotency_key: str | None = None,
) -> dict:
    """Issue an administrative wallet correction.

    Calls ledger_service.admin_correct with idempotency + audit logging.
    Returns the updated wallet summary.

    *idempotency_key* should be supplied by the caller (the frontend
    generates one per correction attempt and reuses it across retries of
    that same attempt) so that a double-click or network retry safely
    no-ops instead of applying the correction twice. Only falls back to a
    freshly generated key when none is supplied, e.g. from a script or the
    Django shell — never from the UI, where a retry would then always look
    like a new correction.
    """
    wallet = get_wallet_for_user(user)
    if wallet is None:
        raise ValueError("User has no wallet.")

    key = idempotency_key or uuid.uuid4().hex
    full_key = f"admin_correct:{user.id}:{key}"

    entry = admin_correct(
        wallet=wallet,
        amount=amount,
        direction=direction,
        reason=reason,
        actor=actor,
        idempotency_key=full_key,
    )

    logger.info(
        "Admin correction by %s on user %s: %s %s credits, reason: %s",
        actor.email,
        user.email,
        direction,
        amount,
        reason,
    )

    wallet.refresh_from_db()
    return {
        "entry_id": str(entry.id),
        "entry_type": entry.entry_type,
        "amount": str(entry.amount),
        "wallet_balance": str(wallet.balance),
        "wallet_reserved": str(wallet.reserved),
    }
