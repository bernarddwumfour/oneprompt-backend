"""Accounts models — User, EmailVerificationToken, RefreshToken.

Per plan 0001 §Backend-architecture: email is the login identifier
(USERNAME_FIELD = "email"), UUID pk, country for currency defaulting.
"""

import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from common.utils import generate_token


class User(AbstractUser):
    """Custom user — email login, UUID pk, country, email verification."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=255, blank=True)
    country = models.CharField(
        max_length=2,
        blank=True,
        help_text="ISO 3166-1 alpha-2 country code",
    )
    is_email_verified = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]  # kept for admin createsuperuser; not used in API

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return self.email


class EmailVerificationToken(models.Model):
    """Single-use token for email verification. Logged instead of emailed (stub)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="verification_tokens"
    )
    token = models.CharField(max_length=64, unique=True, default=generate_token)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def create_for_user(cls, user: User, ttl_hours: int = 24):
        return cls.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=ttl_hours),
        )

    @property
    def is_valid(self) -> bool:
        return self.used_at is None and timezone.now() < self.expires_at

    def consume(self):
        """Mark token as used. Saves immediately."""
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])


class RefreshToken(models.Model):
    """Tracks issued refresh tokens so they can be single-use.

    On each refresh: the old token is deleted, a new one is created.
    This is the mechanism for session revocation — deleting a user's
    RefreshToken rows logs them out everywhere.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="refresh_tokens"
    )
    jti = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
