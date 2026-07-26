from django.test import TestCase

from apps.accounts.tests.factories import UserFactory
from apps.providers.models import CapabilityRoute
from common.jwt import encode_access_token


class CapabilitiesViewTests(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.token = encode_access_token(self.user)

    def _get(self):
        return self.client.get(
            "/api/v1/capabilities", HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

    def test_requires_authentication(self):
        response = self.client.get("/api/v1/capabilities")
        self.assertEqual(response.status_code, 401)

    def test_lists_only_active_routes_without_internal_fields(self):
        response = self._get()
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]

        slugs = [c["slug"] for c in data["capabilities"]]
        self.assertIn("oneprompt-free", slugs)
        self.assertNotIn("fast", slugs)  # legacy development stub is disabled
        self.assertNotIn("deepseek-flash", slugs)  # seeded inactive

        for capability in data["capabilities"]:
            self.assertEqual(
                set(capability.keys()),
                {"slug", "label", "description", "is_default", "is_free"},
            )

        self.assertEqual(data["default_slug"], "oneprompt-free")
        free_route = next(
            item for item in data["capabilities"]
            if item["slug"] == "oneprompt-free"
        )
        self.assertTrue(free_route["is_free"])

    def test_activating_a_route_makes_it_appear(self):
        CapabilityRoute.objects.filter(slug="deepseek-flash").update(is_active=True)
        response = self._get()
        slugs = [c["slug"] for c in response.json()["data"]["capabilities"]]
        self.assertIn("deepseek-flash", slugs)
