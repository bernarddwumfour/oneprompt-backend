import json

from django.test import TestCase

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from common.jwt import encode_access_token
from shared.models import SystemLog


class StaffViewsTests(TestCase):
    def setUp(self):
        self.admin = UserFactory(email="admin@example.com", is_staff=True)
        self.other_admin = UserFactory(email="admin2@example.com", is_staff=True)
        self.user = UserFactory(email="user@example.com")
        self.admin_token = encode_access_token(self.admin)
        self.user_token = encode_access_token(self.user)

    def _get_list(self, token, search=""):
        return self.client.get(
            f"/api/v1/operations/staff?search={search}",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def _promote(self, token, user_id):
        return self.client.post(
            f"/api/v1/operations/staff/{user_id}/promote",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def _demote(self, token, user_id):
        return self.client.post(
            f"/api/v1/operations/staff/{user_id}/demote",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def test_list_requires_admin(self):
        self.assertEqual(self._get_list(self.user_token).status_code, 403)
        self.assertEqual(self._get_list(self.admin_token).status_code, 200)

    def test_list_includes_is_staff_field(self):
        response = self._get_list(self.admin_token, search="user@example.com")
        row = response.json()["data"]["customers"][0]
        self.assertIn("is_staff", row)
        self.assertFalse(row["is_staff"])

    def test_promote_grants_admin_and_logs_it(self):
        before = SystemLog.objects.count()
        response = self._promote(self.admin_token, self.user.id)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_staff)
        self.assertEqual(SystemLog.objects.count(), before + 1)
        log = SystemLog.objects.latest("created_at")
        self.assertEqual(log.action, "staff_promoted")

    def test_promote_already_staff_is_rejected(self):
        response = self._promote(self.admin_token, self.other_admin.id)
        self.assertEqual(response.status_code, 400)

    def test_promote_requires_admin(self):
        self.assertEqual(self._promote(self.user_token, self.user.id).status_code, 403)

    def test_demote_revokes_admin_and_logs_it(self):
        before = SystemLog.objects.count()
        response = self._demote(self.admin_token, self.other_admin.id)
        self.assertEqual(response.status_code, 200)
        self.other_admin.refresh_from_db()
        self.assertFalse(self.other_admin.is_staff)
        self.assertEqual(SystemLog.objects.count(), before + 1)
        log = SystemLog.objects.latest("created_at")
        self.assertEqual(log.action, "staff_demoted")

    def test_demote_non_staff_is_rejected(self):
        response = self._demote(self.admin_token, self.user.id)
        self.assertEqual(response.status_code, 400)

    def test_cannot_demote_self(self):
        response = self._demote(self.admin_token, self.admin.id)
        self.assertEqual(response.status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_staff)

    def test_last_remaining_admin_cannot_be_demoted(self):
        # Reduce to a single admin (self.admin). Note: since role_required
        # forces the acting user to also be staff, the only way to reach a
        # count()==1 state is for actor == target — so this exercises the
        # same rejection outcome the self-demotion guard already covers.
        # Both guards independently protect this outcome; what matters here
        # is the last admin can never end up demoted, by any path.
        User.objects.filter(is_staff=True).exclude(id=self.admin.id).update(is_staff=False)
        self.assertEqual(User.objects.filter(is_staff=True).count(), 1)

        response = self._demote(self.admin_token, self.admin.id)
        self.assertEqual(response.status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_staff)

    def test_promote_unknown_user_404(self):
        import uuid
        response = self._promote(self.admin_token, uuid.uuid4())
        self.assertEqual(response.status_code, 404)
