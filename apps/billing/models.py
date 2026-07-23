"""Billing models — CreditPack, Purchase, Payment.

Per plan 0002: pay-as-you-go credit packs via Paystack.
"""

import uuid

from django.conf import settings
from django.db import models

# Currencies Paystack supports. Other currencies get a clear rejection.
PAYSTACK_CURRENCIES = {"NGN", "GHS", "ZAR", "KES"}

PURCHASE_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("success", "Success"),
    ("failed", "Failed"),
]


class CreditPack(models.Model):
    """A purchasable credit pack — admin-editable."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    label = models.CharField(max_length=100, help_text="e.g. 'GH₵10 Top-up'")
    currency = models.CharField(max_length=3, help_text="ISO 4217")
    amount_credits = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Wallet credits granted after successful payment.",
    )
    price_minor_units = models.IntegerField(
        help_text="Price in kobo/pesewas/cents, e.g. 1000 = GH₵10.00"
    )
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "label"]

    def __str__(self):
        return f"{self.label} — {self.amount_credits} credits"


class Purchase(models.Model):
    """A customer's purchase attempt — immutable reference per README §5.3."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="purchases",
    )
    credit_pack = models.ForeignKey(
        CreditPack, on_delete=models.PROTECT, related_name="purchases"
    )
    reference = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Immutable reference generated before calling Paystack.",
    )
    status = models.CharField(
        max_length=10,
        choices=PURCHASE_STATUS_CHOICES,
        default="pending",
        db_index=True,
    )
    currency = models.CharField(max_length=3)
    amount_minor_units = models.IntegerField(
        help_text="Snapshot of pack price at purchase time"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Purchase {self.reference} [{self.status}]"


class Payment(models.Model):
    """Paystack payment record — one per Purchase."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase = models.OneToOneField(
        Purchase, on_delete=models.PROTECT, related_name="payment"
    )
    paystack_reference = models.CharField(
        max_length=64, blank=True, help_text="Paystack's transaction reference."
    )
    paystack_status = models.CharField(max_length=30, blank=True)
    raw_webhook_payload = models.JSONField(
        default=dict, help_text="Full webhook body for audit trail."
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Payment for {self.purchase.reference}"
