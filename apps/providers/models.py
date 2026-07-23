"""Providers models — CapabilityRoute (DB-backed, admin-editable routing).

Per plan 0002: formalizing from a static Python dict into a real DB model.
"""

import uuid

from django.db import models

PROVIDER_KEY_CHOICES = [
    ("stub", "Stub (Dev/Testing)"),
    ("deepseek", "DeepSeek"),
    ("qwen", "Qwen (Alibaba)"),
    ("gemini", "Gemini (Google)"),
    ("claude", "Claude (Anthropic)"),
    ("chatgpt", "ChatGPT (OpenAI)"),
]


class CapabilityRoute(models.Model):
    """A selectable model route — admin-editable kill-switch per plan 0002.

    Maps a public slug (e.g. "deepseek-pro") to a provider adapter + upstream
    model id + retail credit rates.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Wire value, e.g. 'fast', 'deepseek-pro', 'qwen-max'.",
    )
    label = models.CharField(
        max_length=100,
        help_text="User-facing label, e.g. 'DeepSeek Pro (Reasoning)'.",
    )
    description = models.TextField(
        max_length=500,
        blank=True,
        help_text="Short description shown in the capability selector.",
    )
    provider_key = models.CharField(
        max_length=20,
        choices=PROVIDER_KEY_CHOICES,
        help_text="Which adapter class to instantiate.",
    )
    upstream_model = models.CharField(
        max_length=100,
        help_text="Exact model id sent to the provider API, e.g. 'deepseek-v4-pro'.",
    )
    credit_rate_input = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=0,
        help_text="Retail credits per 1K input tokens (includes margin).",
    )
    credit_rate_output = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=0,
        help_text="Retail credits per 1K output tokens (includes margin).",
    )
    provider_cost_input = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=0,
        help_text="Wholesale USD per 1K input tokens (what we pay DeepSeek/Qwen).",
    )
    provider_cost_output = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=0,
        help_text="Wholesale USD per 1K output tokens (what we pay DeepSeek/Qwen).",
    )
    is_active = models.BooleanField(
        default=False,
        db_index=True,
        help_text="If False, this route is invisible and unusable — the kill-switch.",
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Exactly one active route should be the default selection.",
    )
    sort_order = models.IntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "label"]

    def __str__(self):
        return f"{self.label} ({self.slug}) [{self.provider_key}]"
