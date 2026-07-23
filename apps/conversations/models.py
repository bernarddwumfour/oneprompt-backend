"""Conversations models — Conversation, Message, ModelInvocation.

Per plan 0001 §Backend-architecture.
"""

import uuid

from django.conf import settings
from django.db import models

INVOCATION_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("streaming", "Streaming"),
    ("succeeded", "Succeeded"),
    ("failed", "Failed"),
    ("cancelled", "Cancelled"),
]


class Conversation(models.Model):
    """A chat conversation belonging to one user."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="conversations",
    )
    title = models.CharField(max_length=255, default="New conversation")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.title} ({self.user.email})"


class Message(models.Model):
    """A single message in a conversation — user or assistant."""

    ROLE_CHOICES = [("user", "User"), ("assistant", "Assistant")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class ModelInvocation(models.Model):
    """Tracks a single provider call — billing, usage, and status."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(
        Message,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invocations",
        help_text="The assistant Message this invocation produced (nullable until created).",
    )
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="invocations"
    )
    capability = models.CharField(max_length=50, default="fast")
    status = models.CharField(
        max_length=20, choices=INVOCATION_STATUS_CHOICES, default="pending", db_index=True
    )
    input_tokens = models.IntegerField(null=True, blank=True)
    output_tokens = models.IntegerField(null=True, blank=True)
    credits_estimated = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    credits_charged = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    provider_cost_usd = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Actual wholesale USD cost (computed from real token usage × route wholesale rates).",
    )
    reservation_entry = models.ForeignKey(
        "credits.CreditLedgerEntry",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    capture_entry = models.ForeignKey(
        "credits.CreditLedgerEntry",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    error_message = models.CharField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Invocation {self.id} [{self.status}]"
