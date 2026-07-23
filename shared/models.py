"""Cross-cutting models — SystemLog per BACKEND-RULES.main.md §12."""

import uuid

from django.db import models

SEVERITY_CHOICES = [
    ("debug", "Debug"),
    ("info", "Info"),
    ("warning", "Warning"),
    ("error", "Error"),
    ("critical", "Critical"),
]


class SystemLog(models.Model):
    """Structured audit/error log model used across all apps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    app_name = models.CharField(max_length=50, db_index=True)
    action = models.CharField(max_length=100, db_index=True)
    severity = models.CharField(
        max_length=20, choices=SEVERITY_CHOICES, db_index=True, default="info"
    )
    description = models.TextField(max_length=1000)
    status_code = models.IntegerField(db_index=True, null=True, blank=True)
    user_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    user_email = models.CharField(max_length=255, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    path = models.CharField(max_length=500, null=True, blank=True)
    method = models.CharField(max_length=10, null=True, blank=True)
    extra_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.severity}] {self.app_name}.{self.action}"
