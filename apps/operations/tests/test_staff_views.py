import json
import uuid

from django.test import TestCase

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from common.jwt import encode_access_token
from shared.models import SystemLog


class StaffViewsTests(TestCase):
    def setUp(self):
        self.admin = UserFactory(email="admin@example.com", is_staff=True)
        self.other_admin = UserFactory(email="admin2@example.com", is_staff=True)
        self.third_admin = UserFactory(email="admin3@example.com", is_staff=True)
        self.user = UserFactory(email="user@example.com")
        self.admin_token = encode_access_token(self.admin)
        self.user_token = encode_access_token(self.user)

    # -- helpers ----------------------------------------------------------------

    def _get_list(self, token, search=""):
        return self.client.get(
            f"/api/v1/operations/staff?search={search}",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def _activate(self, token, user_id):
        return self.client.post(
            f"/api/v1/operations/staff/{user_id}/activate",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def _deactivate(self, token, user_id):
        return self.client.post(
            f"/api/v1/operations/staff/{user_id}/deactivate",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def _bulk(self, token, action, ids):
        return self.client.post(
            "/api/v1/operations/staff/bulk-action",
            data=json.dumps({"action": action, "ids": ids}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    # -- list ------------------------------------------------------------------

    def test_list_requires_admin(self):
        self.assertEqual(self._get_list(self.user_token).status_code, 403)
        self.assertEqual(self._get_list(self.admin_token).status_code, 200)

    def test_list_only_includes_staff(self):
        """List filtered to is_staff=True per plan 0008."""
        response = self._get_list(self.admin_token)
        rows = response.json()["data"]["customers"]
        ids = {r["id"] for r in rows}
        self.assertIn(str(self.admin.id), ids)
        self.assertIn(str(self.other_admin.id), ids)
        self.assertIn(str(self.third_admin.id), ids)
        # Non-staff user should NOT appear in staff list
        self.assertNotIn(str(self.user.id), ids)

    def test_list_includes_is_active_field(self):
        response = self._get_list(self.admin_token)
        row = response.json()["data"]["customers"][0]
        self.assertIn("is_active", row)
        self.assertTrue(row["is_active"])  # UserFactory defaults to active

    def test_list_filters_by_country(self):
        self.other_admin.country = "KE"
        self.other_admin.save(update_fields=["country"])

        response = self.client.get(
            "/api/v1/operations/staff?country=KE",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        ids = {r["id"] for r in response.json()["data"]["customers"]}
        self.assertIn(str(self.other_admin.id), ids)
        self.assertNotIn(str(self.admin.id), ids)

    # -- activate (single) ----------------------------------------------------

    def test_activate_sets_user_active_and_logs_it(self):
        self.other_admin.is_active = False
        self.other_admin.save(update_fields=["is_active"])

        before = SystemLog.objects.count()
        response = self._activate(self.admin_token, self.other_admin.id)
        self.assertEqual(response.status_code, 200)

        self.other_admin.refresh_from_db()
        self.assertTrue(self.other_admin.is_active)
        self.assertEqual(SystemLog.objects.count(), before + 1)

    def test_activate_already_active_is_rejected(self):
        self.assertTrue(self.other_admin.is_active)
        response = self._activate(self.admin_token, self.other_admin.id)
        self.assertEqual(response.status_code, 400)

    def test_activate_requires_admin(self):
        response = self._activate(self.user_token, self.user.id)
        self.assertEqual(response.status_code, 403)

    def test_activate_unknown_user_404(self):
        response = self._activate(self.admin_token, uuid.uuid4())
        self.assertEqual(response.status_code, 404)

    # -- deactivate (single) --------------------------------------------------

    def test_deactivate_sets_user_inactive_and_logs_it(self):
        before = SystemLog.objects.count()
        response = self._deactivate(self.admin_token, self.other_admin.id)
        self.assertEqual(response.status_code, 200)

        self.other_admin.refresh_from_db()
        self.assertFalse(self.other_admin.is_active)
        self.assertEqual(SystemLog.objects.count(), before + 1)

    def test_deactivate_already_inactive_is_rejected(self):
        self.other_admin.is_active = False
        self.other_admin.save(update_fields=["is_active"])

        response = self._deactivate(self.admin_token, self.other_admin.id)
        self.assertEqual(response.status_code, 400)

    def test_cannot_deactivate_self(self):
        response = self._deactivate(self.admin_token, self.admin.id)
        self.assertEqual(response.status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_last_active_staff_cannot_be_deactivated(self):
        # Make self.admin the only active staff member
        User.objects.filter(is_staff=True, is_active=True).exclude(
            id=self.admin.id
        ).update(is_active=False)
        self.assertEqual(
            User.objects.filter(is_staff=True, is_active=True).count(), 1
        )

        response = self._deactivate(self.admin_token, self.admin.id)
        self.assertEqual(response.status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    # -- bulk -----------------------------------------------------------------

    def test_bulk_activate(self):
        self.other_admin.is_active = False
        self.other_admin.save(update_fields=["is_active"])
        self.third_admin.is_active = False
        self.third_admin.save(update_fields=["is_active"])

        response = self._bulk(
            self.admin_token, "activate",
            [str(self.other_admin.id), str(self.third_admin.id)],
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["success_count"], 2)
        self.assertEqual(body["data"]["failed_count"], 0)

        self.other_admin.refresh_from_db()
        self.third_admin.refresh_from_db()
        self.assertTrue(self.other_admin.is_active)
        self.assertTrue(self.third_admin.is_active)

    def test_bulk_deactivate(self):
        response = self._bulk(
            self.admin_token, "deactivate",
            [str(self.other_admin.id), str(self.third_admin.id)],
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["success_count"], 2)
        self.assertEqual(body["data"]["failed_count"], 0)

        self.other_admin.refresh_from_db()
        self.third_admin.refresh_from_db()
        self.assertFalse(self.other_admin.is_active)
        self.assertFalse(self.third_admin.is_active)

    def test_bulk_partial_failure(self):
        """One valid + one nonexistent id → 1 success, 1 failed."""
        self.other_admin.is_active = False
        self.other_admin.save(update_fields=["is_active"])

        response = self._bulk(
            self.admin_token, "activate",
            [str(self.other_admin.id), str(uuid.uuid4())],
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["success_count"], 1)
        self.assertEqual(body["data"]["failed_count"], 1)

    def test_bulk_mixed_already_active(self):
        """One already active, one not → 1 success, 1 failed."""
        self.assertTrue(self.other_admin.is_active)  # already active
        self.third_admin.is_active = False
        self.third_admin.save(update_fields=["is_active"])

        response = self._bulk(
            self.admin_token, "activate",
            [str(self.other_admin.id), str(self.third_admin.id)],
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["success_count"], 1)
        self.assertEqual(body["data"]["failed_count"], 1)

    def test_bulk_cannot_deactivate_self(self):
        """Self is in the batch → self fails, others succeed."""
        response = self._bulk(
            self.admin_token, "deactivate",
            [str(self.admin.id), str(self.other_admin.id)],
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["success_count"], 1)
        self.assertEqual(body["data"]["failed_count"], 1)

        failed_id = body["data"]["failed"][0]["id"]
        self.assertEqual(failed_id, str(self.admin.id))

        self.admin.refresh_from_db()
        self.other_admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)  # self-protection held
        self.assertFalse(self.other_admin.is_active)

    def test_bulk_deactivate_multiple_non_actor_staff_leaves_actor_active(self):
        """Batch-deactivating every OTHER active staff member in one request
        is allowed and must all succeed, since the actor (never targetable —
        see test_bulk_cannot_deactivate_self) always remains active. This is
        the realistic ceiling of the last-active-staff guard: given
        self-protection already guarantees the actor stays active, active
        staff can be driven down to exactly 1 (never 0) via this endpoint,
        by construction. The running-counter guard in
        bulk_update_staff_status exists as defense in depth for that
        invariant rather than something reachable through this view today.
        """
        # Active staff: admin (actor), other_admin, third_admin.
        response = self._bulk(
            self.admin_token, "deactivate",
            [str(self.other_admin.id), str(self.third_admin.id)],
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["data"]["success_count"], 2)
        self.assertEqual(body["data"]["failed_count"], 0)

        self.admin.refresh_from_db()
        self.other_admin.refresh_from_db()
        self.third_admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertFalse(self.other_admin.is_active)
        self.assertFalse(self.third_admin.is_active)
        # Scoped to just this test's own staff accounts — the environment may
        # also have a bootstrap admin (see apps/accounts/signals.py, seeded
        # from DJANGO_ADMIN_EMAIL at migration time), so a global count would
        # be environment-dependent rather than testing this batch's effect.
        self.assertEqual(
            User.objects.filter(
                id__in=[self.admin.id, self.other_admin.id, self.third_admin.id],
                is_active=True,
            ).count(),
            1,
        )

    def test_bulk_requires_admin(self):
        response = self._bulk(
            self.user_token, "activate",
            [str(self.user.id)],
        )
        self.assertEqual(response.status_code, 403)

    def test_bulk_invalid_action(self):
        response = self._bulk(
            self.admin_token, "promote",  # not a valid action
            [str(self.other_admin.id)],
        )
        self.assertEqual(response.status_code, 422)

    def test_bulk_empty_ids(self):
        response = self._bulk(self.admin_token, "activate", [])
        self.assertEqual(response.status_code, 422)
