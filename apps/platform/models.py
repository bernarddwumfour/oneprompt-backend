"""Platform models — PlatformSettings singleton (test/live mode)."""

import uuid

from django.conf import settings
from django.db import models

MODE_CHOICES = [("test", "Test"), ("live", "Live")]


class PlatformSettings(models.Model):
    """Singleton row — test/live mode with audit trail."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default="test")
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    def __str__(self):
        return f"PlatformSettings(mode={self.mode})"
