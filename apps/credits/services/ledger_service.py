"""
Ledger service — all wallet mutations go through here.

Per plan 0001 §Backend-architecture / README §7:
- Every function is @transaction.atomic + select_for_update() on the wallet.
- Idempotency keys prevent double-processing.
- capture() and release() take the originating reservation entry so they can
  enforce "released credits cannot also be captured".
"""

import logging
from decimal import Decimal

from django.db import IntegrityError, transaction

from apps.credits.models import CreditLedgerEntry, CreditWallet

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _wallet_lock(wallet: CreditWallet) -> CreditWallet:
    """Re-fetch *wallet* with a row-level lock inside a transaction."""
    return CreditWallet.objects.select_for_update().get(id=wallet.id)


def _create_entry(
    *,
    wallet: CreditWallet,
    entry_type: str,
    amount: Decimal,
    idempotency_key: str,
    reference: dict | None = None,
    reason: str = "",
    created_by=None,
) -> tuple[CreditLedgerEntry, bool]:
    """Create a ledger entry, or return the existing one if the idempotency
    key is a duplicate. Returns ``(entry, created)``.

    The create attempt runs inside a savepoint (nested ``transaction.atomic``)
    so that an ``IntegrityError`` on the duplicate key only rolls back the
    savepoint, not the whole enclosing transaction — without this, the
    subsequent lookup query would fail with ``TransactionManagementError``
    because the outer atomic block is left in a broken state.
    """
    try:
        with transaction.atomic():
            entry = CreditLedgerEntry.objects.create(
                wallet=wallet,
                entry_type=entry_type,
                amount=amount,
                idempotency_key=idempotency_key,
                reference=reference or {},
                reason=reason,
                created_by=created_by,
            )
        return entry, True
    except IntegrityError:
        # Idempotency — key already exists from a prior attempt
        return CreditLedgerEntry.objects.get(idempotency_key=idempotency_key), False


def _apply_balance(wallet: CreditWallet, delta: Decimal):
    wallet.balance += delta


def _apply_reserved(wallet: CreditWallet, delta: Decimal):
    wallet.reserved += delta


class ReservationConflict(Exception):
    """Raised when attempting to capture a reservation that was already released."""

    pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@transaction.atomic
def purchase_credit(
    *,
    wallet: CreditWallet,
    amount: Decimal,
    idempotency_key: str,
    reference: dict | None = None,
):
    w = _wallet_lock(wallet)
    entry, created = _create_entry(
        wallet=w,
        entry_type="purchase_credit",
        amount=amount,
        idempotency_key=idempotency_key,
        reference=reference,
    )
    if created:
        _apply_balance(w, amount)
        w.save(update_fields=["balance", "updated_at"])
    return entry


@transaction.atomic
def promotional_credit(
    *,
    wallet: CreditWallet,
    amount: Decimal,
    idempotency_key: str,
    reference: dict | None = None,
):
    w = _wallet_lock(wallet)
    entry, created = _create_entry(
        wallet=w,
        entry_type="promotional_credit",
        amount=amount,
        idempotency_key=idempotency_key,
        reference=reference,
    )
    if created:
        _apply_balance(w, amount)
        w.save(update_fields=["balance", "updated_at"])
    return entry


@transaction.atomic
def reserve(
    *,
    wallet: CreditWallet,
    amount: Decimal,
    idempotency_key: str,
    reference: dict | None = None,
):
    """Reserve credits before a provider call. Raises ValueError if insufficient.

    Checks for an existing entry under *idempotency_key* first so that a
    retried reservation is a safe no-op even if the wallet's available
    balance has since dropped below *amount* (e.g. because the original,
    successful reservation already consumed it).
    """
    w = _wallet_lock(wallet)

    existing = CreditLedgerEntry.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing

    if w.available < amount:
        raise ValueError(
            f"Insufficient credits: available {w.available}, required {amount}"
        )

    entry, created = _create_entry(
        wallet=w,
        entry_type="usage_reservation",
        amount=amount,
        idempotency_key=idempotency_key,
        reference=reference,
    )
    if created:
        _apply_reserved(w, amount)
        w.save(update_fields=["reserved", "updated_at"])
    return entry


@transaction.atomic
def capture(
    *,
    reservation_entry: CreditLedgerEntry,
    actual_amount: Decimal,
    idempotency_key: str,
):
    """Capture *actual_amount* from a reservation, auto-releasing the remainder.

    Raises ReservationConflict if the reservation was already released.
    """
    w = _wallet_lock(reservation_entry.wallet)

    # Idempotency check first: a retry of an already-successful capture must
    # short-circuit here, before the already-released guard below — otherwise
    # it would trip over the remainder-release entry that THIS capture itself
    # creates on success.
    existing = CreditLedgerEntry.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing

    # Guard: has this reservation already been fully released (failure/cancel
    # path)?
    already_released = CreditLedgerEntry.objects.filter(
        wallet=w,
        entry_type="reservation_release",
        reference__reservation_id=str(reservation_entry.id),
    ).exists()
    if already_released:
        raise ReservationConflict("Cannot capture a reservation that was released.")

    capture_entry, created = _create_entry(
        wallet=w,
        entry_type="usage_capture",
        amount=actual_amount,
        idempotency_key=idempotency_key,
        reference={
            "reservation_id": str(reservation_entry.id),
            **(reservation_entry.reference or {}),
        },
    )

    if created:
        _apply_balance(w, -actual_amount)
        # Resolve the *entire* original hold in one step, regardless of
        # whether actual usage came in under, over, or exactly at the
        # estimate — releasing `actual_amount` instead (when it exceeds the
        # original reservation) would over-release and drive `reserved`
        # negative.
        _apply_reserved(w, -reservation_entry.amount)

        # Record the unused remainder for audit purposes (only meaningful
        # when actual usage came in under the estimate).
        remainder = reservation_entry.amount - actual_amount
        if remainder > 0:
            _create_entry(
                wallet=w,
                entry_type="reservation_release",
                amount=remainder,
                idempotency_key=f"{idempotency_key}:release",
                reference={
                    "reservation_id": str(reservation_entry.id),
                    "released_amount": str(remainder),
                },
            )

        w.save(update_fields=["balance", "reserved", "updated_at"])
    return capture_entry


@transaction.atomic
def release(
    *,
    reservation_entry: CreditLedgerEntry,
    idempotency_key: str,
):
    """Fully release a reservation (provider failure / cancellation path)."""
    w = _wallet_lock(reservation_entry.wallet)

    release_entry, created = _create_entry(
        wallet=w,
        entry_type="reservation_release",
        amount=reservation_entry.amount,
        idempotency_key=idempotency_key,
        reference={"reservation_id": str(reservation_entry.id)},
    )

    if created:
        _apply_reserved(w, -reservation_entry.amount)
        w.save(update_fields=["reserved", "updated_at"])
    return release_entry


@transaction.atomic
def refund(
    *,
    wallet: CreditWallet,
    amount: Decimal,
    idempotency_key: str,
    reference: dict | None = None,
    reason: str = "",
    actor=None,
):
    w = _wallet_lock(wallet)
    entry, created = _create_entry(
        wallet=w,
        entry_type="refund",
        amount=amount,
        idempotency_key=idempotency_key,
        reference=reference,
        reason=reason,
        created_by=actor,
    )
    if created:
        _apply_balance(w, amount)
        w.save(update_fields=["balance", "updated_at"])
    return entry


@transaction.atomic
def expire(
    *,
    wallet: CreditWallet,
    amount: Decimal,
    idempotency_key: str,
    reference: dict | None = None,
):
    w = _wallet_lock(wallet)
    entry, created = _create_entry(
        wallet=w,
        entry_type="expiration",
        amount=amount,
        idempotency_key=idempotency_key,
        reference=reference,
    )
    if created:
        _apply_balance(w, -amount)
        w.save(update_fields=["balance", "updated_at"])
    return entry


@transaction.atomic
def admin_correct(
    *,
    wallet: CreditWallet,
    amount: Decimal,
    direction: str,  # "credit" or "debit"
    reason: str,
    actor,
    idempotency_key: str,
):
    """Administrative correction — reason is required."""
    if not reason.strip():
        raise ValueError("A reason is required for administrative corrections.")
    if direction not in ("credit", "debit"):
        raise ValueError("direction must be 'credit' or 'debit'.")

    w = _wallet_lock(wallet)
    entry, created = _create_entry(
        wallet=w,
        entry_type="administrative_correction",
        amount=amount,
        idempotency_key=idempotency_key,
        reference={"direction": direction},
        reason=reason,
        created_by=actor,
    )
    if created:
        delta = amount if direction == "credit" else -amount
        _apply_balance(w, delta)
        w.save(update_fields=["balance", "updated_at"])
    return entry
