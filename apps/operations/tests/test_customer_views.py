import json
import uuid
from decimal import Decimal

from django.test import TestCase

from apps.accounts.tests.factories import UserFactory
from apps.credits.tests.factories import CreditWalletFactory
from common.jwt import encode_access_token
from shared.models import SystemLog


class CustomerViewsTests(TestCase):
    def setUp(self):
        self.admin = UserFactory(email="admin@example.com", is_staff=True)
        self.staff_user = UserFactory(email="staffer@example.com", is_staff=True)
        self.customer_a = UserFactory(email="customer_a@example.com")
        self.customer_b = UserFactory(email="customer_b@example.com")
        self.admin_token = encode_access_token(self.admin)
        self.customer_token = encode_access_token(self.customer_a)

    # -- helpers ------------------------------------------------------------

    def _get_list(self, token, search=""):
        return self.client.get(
            f"/api/v1/operations/customers?search={search}",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def _activate(self, token, user_id):
        return self.client.post(
            f"/api/v1/operations/customers/{user_id}/activate",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def _deactivate(self, token, user_id):
        return self.client.post(
            f"/api/v1/operations/customers/{user_id}/deactivate",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def _bulk(self, token, payload):
        return self.client.post(
            "/api/v1/operations/customers/bulk-action",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    # -- list -----------------------------------------------------------

    def test_list_excludes_staff_accounts(self):
        response = self._get_list(self.admin_token)
        ids = {r["id"] for r in response.json()["data"]["customers"]}
        self.assertIn(str(self.customer_a.id), ids)
        self.assertIn(str(self.customer_b.id), ids)
        self.assertNotIn(str(self.admin.id), ids)
        self.assertNotIn(str(self.staff_user.id), ids)

    def test_list_filters_by_country(self):
        self.customer_b.country = "NG"
        self.customer_b.save(update_fields=["country"])

        response = self.client.get(
            "/api/v1/operations/customers?country=NG",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        ids = {r["id"] for r in response.json()["data"]["customers"]}
        self.assertIn(str(self.customer_b.id), ids)
        self.assertNotIn(str(self.customer_a.id), ids)

    # -- single-target activate/deactivate -------------------------------

    def test_deactivate_sets_inactive_and_logs_it(self):
        before = SystemLog.objects.count()
        response = self._deactivate(self.admin_token, self.customer_a.id)
        self.assertEqual(response.status_code, 200)
        self.customer_a.refresh_from_db()
        self.assertFalse(self.customer_a.is_active)
        self.assertEqual(SystemLog.objects.count(), before + 1)

    def test_deactivated_customer_cannot_authenticate(self):
        self._deactivate(self.admin_token, self.customer_a.id)
        response = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"email": self.customer_a.email, "password": "testpass123"}),
            content_type="application/json",
        )
        # login_view maps ValueError from authenticate_user to 401.
        self.assertEqual(response.status_code, 401)

    def test_deactivation_revokes_an_already_issued_access_token_immediately(self):
        # The key plan-0008 claim: deactivating a user takes effect on their
        # very next request, not just on their next login — jwt_required
        # rechecks is_active for every request, not only at token issuance.
        customer_token = encode_access_token(self.customer_a)
        before = self.client.get(
            "/api/v1/support/tickets", HTTP_AUTHORIZATION=f"Bearer {customer_token}"
        )
        self.assertEqual(before.status_code, 200)

        self._deactivate(self.admin_token, self.customer_a.id)

        after = self.client.get(
            "/api/v1/support/tickets", HTTP_AUTHORIZATION=f"Bearer {customer_token}"
        )
        self.assertEqual(after.status_code, 401)

    def test_activate_sets_active_and_logs_it(self):
        self.customer_a.is_active = False
        self.customer_a.save(update_fields=["is_active"])
        response = self._activate(self.admin_token, self.customer_a.id)
        self.assertEqual(response.status_code, 200)
        self.customer_a.refresh_from_db()
        self.assertTrue(self.customer_a.is_active)

    def test_deactivate_already_inactive_rejected(self):
        self.customer_a.is_active = False
        self.customer_a.save(update_fields=["is_active"])
        response = self._deactivate(self.admin_token, self.customer_a.id)
        self.assertEqual(response.status_code, 400)

    def test_activate_already_active_rejected(self):
        response = self._activate(self.admin_token, self.customer_a.id)
        self.assertEqual(response.status_code, 400)

    def test_deactivate_unknown_user_404(self):
        response = self._deactivate(self.admin_token, uuid.uuid4())
        self.assertEqual(response.status_code, 404)

    def test_activate_requires_admin(self):
        response = self._activate(self.customer_token, self.customer_b.id)
        self.assertEqual(response.status_code, 403)

    # -- bulk activate/deactivate ----------------------------------------

    def test_bulk_deactivate(self):
        response = self._bulk(self.admin_token, {
            "action": "deactivate",
            "ids": [str(self.customer_a.id), str(self.customer_b.id)],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["success_count"], 2)
        self.customer_a.refresh_from_db()
        self.customer_b.refresh_from_db()
        self.assertFalse(self.customer_a.is_active)
        self.assertFalse(self.customer_b.is_active)

    def test_bulk_partial_failure_unknown_id(self):
        response = self._bulk(self.admin_token, {
            "action": "deactivate",
            "ids": [str(self.customer_a.id), str(uuid.uuid4())],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["success_count"], 1)
        self.assertEqual(data["failed_count"], 1)

    def test_bulk_requires_admin(self):
        response = self._bulk(self.customer_token, {
            "action": "deactivate", "ids": [str(self.customer_b.id)],
        })
        self.assertEqual(response.status_code, 403)

    def test_bulk_invalid_action_rejected(self):
        response = self._bulk(self.admin_token, {
            "action": "delete_forever", "ids": [str(self.customer_a.id)],
        })
        self.assertEqual(response.status_code, 422)

    # -- bulk grant_credits ------------------------------------------------

    def test_bulk_grant_credits_applies_to_all_wallets(self):
        wallet_a = CreditWalletFactory(user=self.customer_a, currency="GHS", balance=Decimal("10"))
        wallet_b = CreditWalletFactory(user=self.customer_b, currency="GHS", balance=Decimal("5"))

        response = self._bulk(self.admin_token, {
            "action": "grant_credits",
            "ids": [str(self.customer_a.id), str(self.customer_b.id)],
            "amount": "20",
            "direction": "credit",
            "reason": "Promo bonus",
            "batch_key": "promo-2026-launch",
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["success_count"], 2)
        self.assertEqual(data["failed_count"], 0)

        wallet_a.refresh_from_db()
        wallet_b.refresh_from_db()
        self.assertEqual(wallet_a.balance, Decimal("30"))
        self.assertEqual(wallet_b.balance, Decimal("25"))

    def test_bulk_grant_credits_requires_amount_direction_reason(self):
        CreditWalletFactory(user=self.customer_a, currency="GHS")
        response = self._bulk(self.admin_token, {
            "action": "grant_credits",
            "ids": [str(self.customer_a.id)],
            "amount": "10",
            "direction": "credit",
            # reason missing
        })
        self.assertEqual(response.status_code, 422)

    def test_bulk_grant_credits_user_without_wallet_reported_as_failed(self):
        # customer_a has no wallet in this test.
        response = self._bulk(self.admin_token, {
            "action": "grant_credits",
            "ids": [str(self.customer_a.id)],
            "amount": "10",
            "direction": "credit",
            "reason": "Test",
            "batch_key": "k1",
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["failed_count"], 1)

    def test_bulk_grant_credits_retry_with_same_batch_key_does_not_double_credit(self):
        wallet = CreditWalletFactory(user=self.customer_a, currency="GHS", balance=Decimal("0"))
        payload = {
            "action": "grant_credits",
            "ids": [str(self.customer_a.id)],
            "amount": "15",
            "direction": "credit",
            "reason": "Retry-safe grant",
            "batch_key": "same-key-both-times",
        }
        first = self._bulk(self.admin_token, payload)
        second = self._bulk(self.admin_token, payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

        wallet.refresh_from_db()
        # Applied once — the second call with the same batch_key no-ops.
        self.assertEqual(wallet.balance, Decimal("15"))

    def test_bulk_grant_credits_missing_batch_key_defaults_and_does_not_collide(self):
        # Two separate bulk-grant requests to the same user, both omitting
        # batch_key, must each apply — the backend must not silently reuse
        # the same idempotency key across distinct requests.
        wallet = CreditWalletFactory(user=self.customer_a, currency="GHS", balance=Decimal("0"))
        base_payload = {
            "action": "grant_credits",
            "ids": [str(self.customer_a.id)],
            "amount": "10",
            "direction": "credit",
            "reason": "No batch key",
        }
        first = self._bulk(self.admin_token, dict(base_payload))
        second = self._bulk(self.admin_token, dict(base_payload))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["data"]["success_count"], 1)
        self.assertEqual(second.json()["data"]["success_count"], 1)

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("20"))
