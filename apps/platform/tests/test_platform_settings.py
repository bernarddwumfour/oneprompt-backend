import json

from django.test import TestCase

from apps.accounts.tests.factories import UserFactory
from apps.platform.models import PlatformSettings
from apps.platform.selectors import get_platform_mode, get_platform_settings
from apps.platform.services import set_platform_mode
from common.jwt import encode_access_token


class PlatformSettingsSelectorsTests(TestCase):
    def test_singleton_seeded_by_migration(self):
        obj = get_platform_settings()
        self.assertIsNotNone(obj)
        self.assertEqual(obj.mode, "test")

    def test_get_platform_mode_returns_seeded_mode(self):
        self.assertEqual(get_platform_mode(), "test")


class SetPlatformModeTests(TestCase):
    def test_sets_mode_and_actor(self):
        user = UserFactory()
        obj = set_platform_mode(mode="live", actor=user)
        self.assertEqual(obj.mode, "live")
        self.assertEqual(obj.updated_by, user)
        self.assertEqual(get_platform_mode(), "live")

    def test_rejects_invalid_mode(self):
        with self.assertRaises(ValueError):
            set_platform_mode(mode="bogus", actor=None)
        # unchanged
        self.assertEqual(get_platform_mode(), "test")


class PlatformSettingsViewTests(TestCase):
    def setUp(self):
        self.admin = UserFactory(is_staff=True)
        self.user = UserFactory()
        self.admin_token = encode_access_token(self.admin)
        self.user_token = encode_access_token(self.user)

    def _get(self, token):
        return self.client.get(
            "/api/v1/operations/settings", HTTP_AUTHORIZATION=f"Bearer {token}"
        )

    def _patch(self, token, body):
        return self.client.patch(
            "/api/v1/operations/settings",
            data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def test_get_requires_admin(self):
        self.assertEqual(self._get(self.user_token).status_code, 403)
        self.assertEqual(self._get(self.admin_token).status_code, 200)

    def test_get_returns_current_settings(self):
        response = self._get(self.admin_token)
        data = response.json()["data"]
        self.assertEqual(data["mode"], "test")
        self.assertIsNone(data["updated_by_email"])

    def test_patch_requires_admin(self):
        response = self._patch(self.user_token, {"mode": "live"})
        self.assertEqual(response.status_code, 403)

    def test_patch_updates_mode_and_records_actor(self):
        response = self._patch(self.admin_token, {"mode": "live"})
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["mode"], "live")
        self.assertEqual(data["updated_by_email"], self.admin.email)
        self.assertEqual(get_platform_mode(), "live")

    def test_patch_rejects_invalid_mode(self):
        response = self._patch(self.admin_token, {"mode": "bogus"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(get_platform_mode(), "test")

    def test_patch_rejects_missing_mode(self):
        response = self._patch(self.admin_token, {})
        self.assertEqual(response.status_code, 400)
