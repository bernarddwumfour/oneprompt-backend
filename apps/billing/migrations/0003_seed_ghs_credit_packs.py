"""Seed 4 GHS credit packs — per plan 0006.

Launch scope is GHS-only (matches the admin account's country). NGN/ZAR/KES
packs can be added later purely through the /admin/billing admin UI, no
migration needed.
"""

from decimal import Decimal

from django.db import migrations

GHS_PACKS = [
    {
        "label": "Starter",
        "currency": "GHS",
        "price_minor_units": 1000,
        "amount_credits": Decimal("50.00"),
        "is_active": True,
        "sort_order": 10,
    },
    {
        "label": "Popular",
        "currency": "GHS",
        "price_minor_units": 2500,
        "amount_credits": Decimal("140.00"),
        "is_active": True,
        "sort_order": 20,
    },
    {
        "label": "Best Value",
        "currency": "GHS",
        "price_minor_units": 5000,
        "amount_credits": Decimal("300.00"),
        "is_active": True,
        "sort_order": 30,
    },
    {
        "label": "Power",
        "currency": "GHS",
        "price_minor_units": 10000,
        "amount_credits": Decimal("650.00"),
        "is_active": True,
        "sort_order": 40,
    },
]


def seed(apps, schema_editor):
    CreditPack = apps.get_model("billing", "CreditPack")
    for pack in GHS_PACKS:
        CreditPack.objects.get_or_create(
            label=pack["label"], currency=pack["currency"], defaults=pack
        )


def unseed(apps, schema_editor):
    CreditPack = apps.get_model("billing", "CreditPack")
    CreditPack.objects.filter(
        label__in=[p["label"] for p in GHS_PACKS], currency="GHS"
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0002_purchase_refunded_at"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
