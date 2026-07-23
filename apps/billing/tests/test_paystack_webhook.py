import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.accounts.tests.factories import UserFactory
from apps.billing.models import Purchase
from apps.billing.services.paystack_client import PaystackClient, PaystackError
from apps.billing.services.purchase_service import create_purchase
from apps.billing.tests.factories import CreditPackFactory
from apps.credits.models import CreditWallet

TEST_SECRET = "test-paystack-secret"


def _sign(body: bytes) -> str:
    return hmac.new(TEST_SECRET.encode(), body, hashlib.sha512).hexdigest()


@override_settings(PAYSTACK_SECRET_KEY=TEST_SECRET)
class PaystackWebhookTests(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.wallet = CreditWallet.objects.create(user=self.user, currency="GHS")
        self.pack = CreditPackFactory(currency="GHS", amount_credits=Decimal("50.00"))

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
        self.reference = result["reference"]
        self.purchase = Purchase.objects.get(reference=self.reference)

    def _post_webhook(self, body: bytes, signature: str | None = None):
        headers = {}
        if signature is not None:
            headers["HTTP_X_PAYSTACK_SIGNATURE"] = signature
        return self.client.post(
            "/api/v1/billing/webhooks/paystack",
            data=body,
            content_type="application/json",
            **headers,
        )

    def _body(self):
        return json.dumps({"event": "charge.success", "data": {"reference": self.reference}}).encode()

    def test_missing_signature_is_rejected(self):
        response = self._post_webhook(self._body())
        self.assertEqual(response.status_code, 401)

    def test_invalid_signature_is_rejected_and_purchase_stays_pending(self):
        response = self._post_webhook(self._body(), signature="not-the-real-signature")
        self.assertEqual(response.status_code, 401)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "pending")

    def test_unknown_reference_returns_404(self):
        body = json.dumps({"event": "charge.success", "data": {"reference": "does-not-exist"}}).encode()
        response = self._post_webhook(body, signature=_sign(body))
        self.assertEqual(response.status_code, 404)

    def test_confirmed_success_credits_wallet_exactly_once(self):
        body = self._body()
        with patch.object(
            PaystackClient,
            "verify_transaction",
            return_value={"data": {"status": "success", "reference": self.reference}},
        ):
            response = self._post_webhook(body, signature=_sign(body))
        self.assertEqual(response.status_code, 200)

        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "success")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("50.00"))

        self.assertTrue(self.purchase.payment.raw_webhook_payload)
        self.assertIn("verify_response", self.purchase.payment.raw_webhook_payload)

    def test_duplicate_webhook_delivery_credits_wallet_only_once(self):
        body = self._body()
        with patch.object(
            PaystackClient,
            "verify_transaction",
            return_value={"data": {"status": "success", "reference": self.reference}},
        ) as verify_mock:
            self._post_webhook(body, signature=_sign(body))
            second_response = self._post_webhook(body, signature=_sign(body))

        self.assertEqual(second_response.status_code, 200)
        # Second delivery short-circuits before re-verifying with Paystack.
        self.assertEqual(verify_mock.call_count, 1)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("50.00"))

    def test_paystack_confirmed_failure_marks_purchase_failed_without_crediting(self):
        body = self._body()
        with patch.object(
            PaystackClient,
            "verify_transaction",
            return_value={"data": {"status": "abandoned", "reference": self.reference}},
        ):
            response = self._post_webhook(body, signature=_sign(body))
        self.assertEqual(response.status_code, 200)

        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "failed")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("0.00"))

    def test_transient_verify_failure_leaves_purchase_pending_and_returns_5xx(self):
        body = self._body()
        with patch.object(
            PaystackClient, "verify_transaction", side_effect=PaystackError("timeout")
        ):
            response = self._post_webhook(body, signature=_sign(body))

        self.assertEqual(response.status_code, 500)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "pending")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("0.00"))
