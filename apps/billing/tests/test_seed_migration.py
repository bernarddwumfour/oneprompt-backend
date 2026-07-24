"""Test that the Plan 0006 GHS credit pack seed migration produces the
expected rows."""

from decimal import Decimal

from django.test import TestCase

from apps.billing.models import CreditPack


class GhsSeedMigrationTests(TestCase):
    """The data migration should leave exactly 4 active GHS packs."""

    def test_four_ghs_packs_exist(self):
        packs = CreditPack.objects.filter(currency="GHS").order_by("sort_order")
        self.assertEqual(
            [p.label for p in packs],
            ["Starter", "Popular", "Best Value", "Power"],
        )
        self.assertTrue(all(p.is_active for p in packs))

    def test_starter_pack_pricing(self):
        pack = CreditPack.objects.get(label="Starter", currency="GHS")
        self.assertEqual(pack.price_minor_units, 1000)
        self.assertEqual(pack.amount_credits, Decimal("50.00"))

    def test_power_pack_pricing(self):
        pack = CreditPack.objects.get(label="Power", currency="GHS")
        self.assertEqual(pack.price_minor_units, 10000)
        self.assertEqual(pack.amount_credits, Decimal("650.00"))

    def test_best_value_ratio(self):
        """Best Value: ₵50 → 300 credits = 6.0 credits/GHS (bonus over Starter's 5.0)"""
        pack = CreditPack.objects.get(label="Best Value", currency="GHS")
        ratio = float(pack.amount_credits) / (pack.price_minor_units / 100)
        self.assertGreater(ratio, 5.5)
        self.assertEqual(pack.amount_credits, Decimal("300.00"))
