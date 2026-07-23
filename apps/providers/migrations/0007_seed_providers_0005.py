"""Seed 6 new provider routes — Gemini, Claude, ChatGPT — per plan 0005.

All seeded is_active=False, is_default=False. Stub route stays the only
active one until an admin flips them on.

ChatGPT/Gemini provider_cost figures are rough placeholders flagged here;
they're editable via the Providers & Models admin page. Claude figures are
exact per Anthropic's published pricing as of July 2026.
"""

from decimal import Decimal

from django.db import migrations

NEW_ROUTES = [
    {
        "slug": "chatgpt-fast",
        "label": "ChatGPT Fast",
        "description": "Economical, fast responses from OpenAI.",
        "provider_key": "chatgpt",
        "upstream_model": "gpt-5.4-mini",
        "credit_rate_input": Decimal("0.0400"),
        "credit_rate_output": Decimal("0.1200"),
        "provider_cost_input": Decimal("0.0003"),   # placeholder
        "provider_cost_output": Decimal("0.0012"),  # placeholder
        "is_active": False,
        "is_default": False,
        "sort_order": 60,
    },
    {
        "slug": "chatgpt-pro",
        "label": "ChatGPT Pro",
        "description": "Advanced reasoning from OpenAI.",
        "provider_key": "chatgpt",
        "upstream_model": "gpt-5.5",
        "credit_rate_input": Decimal("0.1500"),
        "credit_rate_output": Decimal("0.4500"),
        "provider_cost_input": Decimal("0.0030"),   # placeholder
        "provider_cost_output": Decimal("0.0120"),  # placeholder
        "is_active": False,
        "is_default": False,
        "sort_order": 70,
    },
    {
        "slug": "gemini-flash",
        "label": "Gemini Flash",
        "description": "Fast, economical Gemini model.",
        "provider_key": "gemini",
        "upstream_model": "gemini-3.5-flash",
        "credit_rate_input": Decimal("0.0400"),
        "credit_rate_output": Decimal("0.1200"),
        "provider_cost_input": Decimal("0.0002"),   # placeholder
        "provider_cost_output": Decimal("0.0008"),  # placeholder
        "is_active": False,
        "is_default": False,
        "sort_order": 80,
    },
    {
        "slug": "gemini-pro",
        "label": "Gemini Pro (Reasoning)",
        "description": "Advanced reasoning from Google.",
        "provider_key": "gemini",
        "upstream_model": "gemini-3.1-pro",
        "credit_rate_input": Decimal("0.1200"),
        "credit_rate_output": Decimal("0.3600"),
        "provider_cost_input": Decimal("0.0020"),   # placeholder
        "provider_cost_output": Decimal("0.0100"),  # placeholder
        "is_active": False,
        "is_default": False,
        "sort_order": 90,
    },
    {
        "slug": "claude-fast",
        "label": "Claude Haiku",
        "description": "Fast, cost-effective Claude.",
        "provider_key": "claude",
        "upstream_model": "claude-haiku-4-5",
        "credit_rate_input": Decimal("0.0500"),
        "credit_rate_output": Decimal("0.1500"),
        "provider_cost_input": Decimal("0.0010"),   # $1/1M → $0.001/1K
        "provider_cost_output": Decimal("0.0050"),  # $5/1M → $0.005/1K
        "is_active": False,
        "is_default": False,
        "sort_order": 100,
    },
    {
        "slug": "claude-pro",
        "label": "Claude Opus (Reasoning)",
        "description": "Most powerful Claude for complex tasks.",
        "provider_key": "claude",
        "upstream_model": "claude-opus-4-8",
        "credit_rate_input": Decimal("0.2000"),
        "credit_rate_output": Decimal("0.6000"),
        "provider_cost_input": Decimal("0.0050"),   # $5/1M → $0.005/1K
        "provider_cost_output": Decimal("0.0250"),  # $25/1M → $0.025/1K
        "is_active": False,
        "is_default": False,
        "sort_order": 110,
    },
]


def seed(apps, schema_editor):
    CapabilityRoute = apps.get_model("providers", "CapabilityRoute")
    for route in NEW_ROUTES:
        CapabilityRoute.objects.get_or_create(
            slug=route["slug"], defaults=route
        )


def unseed(apps, schema_editor):
    CapabilityRoute = apps.get_model("providers", "CapabilityRoute")
    CapabilityRoute.objects.filter(
        slug__in=[r["slug"] for r in NEW_ROUTES]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("providers", "0006_alter_capabilityroute_provider_key"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
