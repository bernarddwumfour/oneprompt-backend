from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.accounts.tests.factories import UserFactory
from apps.billing.models import Purchase
from apps.billing.services.paystack_client import PaystackClient, PaystackError
from apps.billing.services.purchase_service import create_purchase
from apps.billing.tests.factories import CreditPackFactory
from apps.credits.models import CreditWallet


class CreatePurchaseTests(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.wallet = CreditWallet.objects.create(user=self.user, currency="GHS")
        self.pack = CreditPackFactory(currency="GHS")

    def test_happy_path_creates_pending_purchase_and_payment(self):
        with patch.object(
            PaystackClient,
            "initialize_transaction",
            return_value={
                "data": {
                    "reference": "paystack-ref-1",
                    "authorization_url": "https://paystack.test/pay/abc",
                }
            },
        ):
            result = create_purchase(user=self.user, credit_pack_id=str(self.pack.id))

        self.assertEqual(result["authorization_url"], "https://paystack.test/pay/abc")
        purchase = Purchase.objects.get(reference=result["reference"])
        self.assertEqual(purchase.status, "pending")
        self.assertTrue(hasattr(purchase, "payment"))

    def test_rejects_unsupported_wallet_currency(self):
        wallet = CreditWallet.objects.create(
            user=UserFactory(), currency="RWF"
        )
        with self.assertRaises(ValueError):
            create_purchase(user=wallet.user, credit_pack_id=str(self.pack.id))

    def test_rejects_currency_mismatch_between_pack_and_wallet(self):
        ngn_pack = CreditPackFactory(currency="NGN")
        with self.assertRaises(ValueError):
            create_purchase(user=self.user, credit_pack_id=str(ngn_pack.id))

    def test_unknown_credit_pack_is_rejected(self):
        with self.assertRaises(ValueError):
            create_purchase(user=self.user, credit_pack_id="00000000-0000-0000-0000-000000000000")

    def test_paystack_initialize_failure_still_persists_an_auditable_purchase(self):
        with patch.object(
            PaystackClient,
            "initialize_transaction",
            side_effect=PaystackError("Paystack unreachable"),
        ):
            with self.assertRaises(PaystackError):
                create_purchase(user=self.user, credit_pack_id=str(self.pack.id))

        purchases = Purchase.objects.filter(user=self.user)
        self.assertEqual(purchases.count(), 1)
        self.assertEqual(purchases.first().status, "failed")
