import json
from decimal import Decimal

from django.test import TestCase, override_settings

from apps.accounts.tests.factories import UserFactory
from apps.platform.models import PlatformSettings
from apps.providers.models import CapabilityRoute
from common.jwt import encode_access_token


def _set_mode(mode: str) -> None:
    PlatformSettings.objects.update(mode=mode)


class CapabilityRouteUpdateViewTests(TestCase):
    def setUp(self):
        self.admin = UserFactory(is_staff=True)
        self.user = UserFactory()
        self.admin_token = encode_access_token(self.admin)
        self.user_token = encode_access_token(self.user)

        self.route = CapabilityRoute.objects.create(
            slug="claude-test-route",
            label="Claude Haiku",
            provider_key="claude",
            upstream_model="claude-haiku-4-5",
            credit_rate_input=Decimal("0.05"),
            credit_rate_output=Decimal("0.15"),
            is_active=False,
        )

    def _patch(self, token, body, route=None):
        route = route or self.route
        return self.client.patch(
            f"/api/v1/operations/capability-routes/{route.id}",
            data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def test_requires_admin(self):
        response = self._patch(self.user_token, {"is_active": True})
        self.assertEqual(response.status_code, 403)

    def test_activating_a_keyless_route_succeeds_in_test_mode(self):
        # PlatformSettings defaults to "test" per the seed migration.
        with override_settings(ANTHROPIC_API_KEY=""):
            response = self._patch(self.admin_token, {"is_active": True})
        self.assertEqual(response.status_code, 200)
        self.route.refresh_from_db()
        self.assertTrue(self.route.is_active)

    def test_activating_a_keyless_route_is_rejected_in_live_mode(self):
        _set_mode("live")
        with override_settings(ANTHROPIC_API_KEY=""):
            response = self._patch(self.admin_token, {"is_active": True})
        self.assertEqual(response.status_code, 400)
        self.route.refresh_from_db()
        self.assertFalse(self.route.is_active)

    def test_activating_a_keyed_route_succeeds_in_live_mode(self):
        _set_mode("live")
        with override_settings(ANTHROPIC_API_KEY="a-real-key"):
            response = self._patch(self.admin_token, {"is_active": True})
        self.assertEqual(response.status_code, 200)
        self.route.refresh_from_db()
        self.assertTrue(self.route.is_active)

    def test_guard_applies_even_when_is_active_is_not_in_this_patch(self):
        # Route was activated in test mode (no key needed there), then the
        # platform flips to live — the guard must catch this on ANY edit,
        # not just one that explicitly sets is_active.
        with override_settings(ANTHROPIC_API_KEY=""):
            self._patch(self.admin_token, {"is_active": True})
        self.route.refresh_from_db()
        self.assertTrue(self.route.is_active)

        _set_mode("live")
        with override_settings(ANTHROPIC_API_KEY=""):
            response = self._patch(
                self.admin_token, {"credit_rate_input": "0.10"}
            )
        self.assertEqual(response.status_code, 400)
        self.route.refresh_from_db()
        self.assertEqual(self.route.credit_rate_input, Decimal("0.05"))

    def test_stub_route_can_always_be_activated_regardless_of_mode(self):
        stub_route = CapabilityRoute.objects.create(
            slug="fast-2", label="Fast 2", provider_key="stub",
            upstream_model="stub", is_active=False,
        )
        _set_mode("live")
        response = self._patch(self.admin_token, {"is_active": True}, route=stub_route)
        self.assertEqual(response.status_code, 200)

    def test_deactivating_a_keyless_route_in_live_mode_is_still_allowed(self):
        # The guard only blocks a route ending up active without a key —
        # turning one off is never blocked.
        with override_settings(ANTHROPIC_API_KEY=""):
            self._patch(self.admin_token, {"is_active": True})
        _set_mode("live")
        with override_settings(ANTHROPIC_API_KEY=""):
            response = self._patch(self.admin_token, {"is_active": False})
        self.assertEqual(response.status_code, 200)
        self.route.refresh_from_db()
        self.assertFalse(self.route.is_active)
