import json
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.billing.models import CreditPack, Purchase
from apps.billing.tests.factories import CreditPackFactory
from common.jwt import encode_access_token


class CreditPackAdminViewsTests(TestCase):
    def setUp(self):
        self.admin = UserFactory(is_staff=True)
        self.user = UserFactory()
        self.admin_token = encode_access_token(self.admin)
        self.user_token = encode_access_token(self.user)

    def test_create_pack(self):
        response = self.client.post(
            "/api/v1/operations/credit-packs",
            data=json.dumps({
                "label": "Starter", "currency": "GHS",
                "amount_credits": "50", "price_minor_units": 1000,
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(CreditPack.objects.filter(label="Starter").exists())

    def test_update_pack_edits_fields(self):
        pack = CreditPackFactory(label="Old label")
        response = self.client.patch(
            f"/api/v1/operations/credit-packs/{pack.id}",
            data=json.dumps({"label": "New label"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        self.assertEqual(response.status_code, 200)
        pack.refresh_from_db()
        self.assertEqual(pack.label, "New label")

    def test_update_pack_toggle_active(self):
        pack = CreditPackFactory(is_active=True)
        response = self.client.patch(
            f"/api/v1/operations/credit-packs/{pack.id}",
            data=json.dumps({"is_active": False}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        self.assertEqual(response.status_code, 200)
        pack.refresh_from_db()
        self.assertFalse(pack.is_active)

    def test_requires_admin(self):
        response = self.client.get(
            "/api/v1/operations/credit-packs",
            HTTP_AUTHORIZATION=f"Bearer {self.user_token}",
        )
        self.assertEqual(response.status_code, 403)


class PurchaseListViewDateRangeFilterTests(TestCase):
    def setUp(self):
        self.admin = UserFactory(is_staff=True)
        self.admin_token = encode_access_token(self.admin)
        self.pack = CreditPackFactory(currency="GHS")

        now = timezone.now()
        self.old = Purchase.objects.create(
            user=self.admin, credit_pack=self.pack, reference="ref-old",
            status="success", currency="GHS", amount_minor_units=1000,
            amount_credits=self.pack.amount_credits,
        )
        Purchase.objects.filter(id=self.old.id).update(
            created_at=now - timezone.timedelta(days=10)
        )
        self.recent = Purchase.objects.create(
            user=self.admin, credit_pack=self.pack, reference="ref-recent",
            status="success", currency="GHS", amount_minor_units=1000,
            amount_credits=self.pack.amount_credits,
        )
        Purchase.objects.filter(id=self.recent.id).update(created_at=now)

    @staticmethod
    def _js_iso(dt):
        # Mirrors JS `Date.prototype.toISOString()` — always a "Z" suffix,
        # never a "+00:00" offset, which would need URL-encoding to survive
        # Django's QueryDict parsing (it treats a literal "+" as a space).
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def test_created_at_range_filters_out_purchases_before_from(self):
        from_iso = self._js_iso(timezone.now() - timezone.timedelta(days=1))
        response = self.client.get(
            f"/api/v1/operations/purchases?created_at=from={from_iso}",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        self.assertEqual(response.status_code, 200)
        refs = {p["reference"] for p in response.json()["data"]["purchases"]}
        self.assertIn("ref-recent", refs)
        self.assertNotIn("ref-old", refs)

    def test_created_at_range_filters_out_purchases_after_to(self):
        to_iso = self._js_iso(timezone.now() - timezone.timedelta(days=1))
        response = self.client.get(
            f"/api/v1/operations/purchases?created_at=to={to_iso}",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        self.assertEqual(response.status_code, 200)
        refs = {p["reference"] for p in response.json()["data"]["purchases"]}
        self.assertIn("ref-old", refs)
        self.assertNotIn("ref-recent", refs)

    def test_no_range_returns_all(self):
        response = self.client.get(
            "/api/v1/operations/purchases",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        refs = {p["reference"] for p in response.json()["data"]["purchases"]}
        self.assertIn("ref-old", refs)
        self.assertIn("ref-recent", refs)


class CreditPackBulkActionViewTests(TestCase):
    def setUp(self):
        self.admin = UserFactory(is_staff=True)
        self.user = UserFactory()
        self.admin_token = encode_access_token(self.admin)
        self.user_token = encode_access_token(self.user)
        self.pack_a = CreditPackFactory(label="Pack A", is_active=False)
        self.pack_b = CreditPackFactory(label="Pack B", is_active=True)

    def _bulk(self, token, action, ids):
        return self.client.post(
            "/api/v1/operations/credit-packs/bulk-action",
            data=json.dumps({"action": action, "ids": [str(i) for i in ids]}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def test_bulk_activate(self):
        response = self._bulk(self.admin_token, "activate", [self.pack_a.id])
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["success_count"], 1)
        self.pack_a.refresh_from_db()
        self.assertTrue(self.pack_a.is_active)

    def test_bulk_deactivate(self):
        response = self._bulk(self.admin_token, "deactivate", [self.pack_b.id])
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["success_count"], 1)
        self.pack_b.refresh_from_db()
        self.assertFalse(self.pack_b.is_active)

    def test_bulk_already_in_target_state_reported_as_failed(self):
        response = self._bulk(self.admin_token, "activate", [self.pack_b.id])
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["failed_count"], 1)
        self.assertEqual(data["failed"][0]["reason"], "Already active.")

    def test_bulk_unknown_id_reported_as_failed(self):
        import uuid

        response = self._bulk(self.admin_token, "activate", [uuid.uuid4()])
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["failed_count"], 1)
        self.assertEqual(data["failed"][0]["reason"], "Not found.")

    def test_bulk_requires_admin(self):
        response = self._bulk(self.user_token, "activate", [self.pack_a.id])
        self.assertEqual(response.status_code, 403)

    def test_bulk_invalid_action_rejected(self):
        response = self._bulk(self.admin_token, "delete", [self.pack_a.id])
        self.assertEqual(response.status_code, 422)
