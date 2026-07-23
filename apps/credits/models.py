"""Credits models — CreditWallet + append-only CreditLedgerEntry.

Per plan 0001 §Backend-architecture:
- balance is a denormalized cache, mutated only inside transactions alongside
  a new ledger entry.
- reserved tracks active holds; available = balance - reserved.
- Ledger entries are immutable (created_at only, no updated_at).
"""

import uuid

from django.conf import settings
from django.db import models

ENTRY_TYPE_CHOICES = [
    ("purchase_credit", "Purchase Credit"),
    ("promotional_credit", "Promotional Credit"),
    ("usage_reservation", "Usage Reservation"),
    ("usage_capture", "Usage Capture"),
    ("reservation_release", "Reservation Release"),
    ("refund", "Refund"),
    ("expiration", "Expiration"),
    ("administrative_correction", "Administrative Correction"),
]


class CreditWallet(models.Model):
    """One wallet per user (for now). balance and reserved are denormalized."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="wallet",
    )
    currency = models.CharField(
        max_length=3, help_text="ISO 4217 currency code (e.g. GHS, NGN)"
    )
    balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, db_index=True
    )
    reserved = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def available(self):
        return self.balance - self.reserved

    def __str__(self):
        return f"Wallet {self.user.email} — {self.balance} {self.currency}"


class CreditLedgerEntry(models.Model):
    """Append-only ledger entry. Never updated, never deleted."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(
        CreditWallet, on_delete=models.PROTECT, related_name="ledger_entries"
    )
    entry_type = models.CharField(
        max_length=30, choices=ENTRY_TYPE_CHOICES, db_index=True
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Always positive; effect on wallet depends on entry_type.",
    )
    idempotency_key = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Globally unique — exactly-once guarantee.",
    )
    reference = models.JSONField(
        default=dict,
        help_text="e.g. {'invocation_id': '...', 'payment_ref': '...'}",
    )
    reason = models.CharField(
        max_length=500,
        blank=True,
        help_text="Required for administrative_correction entries.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # NO updated_at — ledger entries are immutable

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.entry_type} — {self.amount} — {self.idempotency_key[:20]}"
