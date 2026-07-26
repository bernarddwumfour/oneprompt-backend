from decimal import Decimal

from django.test import TestCase, override_settings

from apps.platform.models import PlatformSettings
from apps.providers import registry
from apps.providers.anthropic_provider import AnthropicProvider
from apps.providers.dummy_provider import DummyProvider
from apps.providers.models import CapabilityRoute
from apps.providers.openai_compatible_provider import OpenAIChatCompatibleProvider
from apps.providers.stub_provider import StubProvider


def _set_mode(mode: str) -> None:
    PlatformSettings.objects.update(mode=mode)


class RegistryTests(TestCase):
    def setUp(self):
        CapabilityRoute.objects.all().delete()

    def test_get_provider_returns_none_for_unknown_slug(self):
        self.assertIsNone(registry.get_provider("does-not-exist"))

    def test_get_provider_returns_none_for_inactive_route(self):
        CapabilityRoute.objects.create(
            slug="inactive-route",
            label="Inactive",
            provider_key="stub",
            upstream_model="stub",
            is_active=False,
        )
        self.assertIsNone(registry.get_provider("inactive-route"))

    def test_get_provider_instantiates_stub_provider(self):
        CapabilityRoute.objects.create(
            slug="fast",
            label="Fast",
            provider_key="stub",
            upstream_model="stub",
            is_active=True,
        )
        provider = registry.get_provider("fast")
        self.assertIsInstance(provider, StubProvider)

    def test_get_provider_instantiates_real_provider_with_route_config(self):
        # Live mode + a configured key: get_provider() should return the
        # real adapter, not the test-mode DummyProvider.
        _set_mode("live")
        CapabilityRoute.objects.create(
            slug="deepseek-flash",
            label="DeepSeek Flash",
            provider_key="deepseek",
            upstream_model="deepseek-v4-flash",
            credit_rate_input=Decimal("0.05"),
            credit_rate_output=Decimal("0.15"),
            is_active=True,
        )
        with override_settings(DEEPSEEK_API_KEY="test-key"):
            provider = registry.get_provider("deepseek-flash")
        self.assertIsInstance(provider, OpenAIChatCompatibleProvider)
        self.assertEqual(provider.model, "deepseek-v4-flash")
        self.assertEqual(provider.credit_rate_input, Decimal("0.05"))

    def test_get_provider_returns_dummy_in_test_mode_for_keyless_route(self):
        # Default seeded mode is "test" — no API key needed, no real
        # adapter instantiated.
        CapabilityRoute.objects.create(
            slug="claude-fast",
            label="Claude Haiku",
            provider_key="claude",
            upstream_model="claude-haiku-4-5",
            credit_rate_input=Decimal("0.05"),
            credit_rate_output=Decimal("0.15"),
            is_active=True,
        )
        with override_settings(ANTHROPIC_API_KEY=""):
            provider = registry.get_provider("claude-fast")
        self.assertIsInstance(provider, DummyProvider)
        self.assertEqual(provider.credit_rate_input, Decimal("0.05"))

    def test_get_provider_returns_none_in_live_mode_for_keyless_route(self):
        _set_mode("live")
        CapabilityRoute.objects.create(
            slug="gemini-flash",
            label="Gemini Flash",
            provider_key="gemini",
            upstream_model="gemini-3.5-flash",
            is_active=True,
        )
        with override_settings(GEMINI_API_KEY=""):
            self.assertIsNone(registry.get_provider("gemini-flash"))

    def test_stub_route_unaffected_by_mode(self):
        CapabilityRoute.objects.create(
            slug="fast", label="Fast", provider_key="stub",
            upstream_model="stub", is_active=True,
        )
        for mode in ("test", "live"):
            _set_mode(mode)
            self.assertIsInstance(registry.get_provider("fast"), StubProvider)

    def test_provider_has_api_key(self):
        self.assertTrue(registry.provider_has_api_key("stub"))
        with override_settings(GEMINI_API_KEY=""):
            self.assertFalse(registry.provider_has_api_key("gemini"))
        with override_settings(GEMINI_API_KEY="a-key"):
            self.assertTrue(registry.provider_has_api_key("gemini"))
        with override_settings(
            CLOUDFLARE_API_KEY="a-key",
            CLOUDFLARE_BASE_URL="",
        ):
            self.assertFalse(registry.provider_has_api_key("cloudflare"))
        with override_settings(
            CLOUDFLARE_API_KEY="a-key",
            CLOUDFLARE_BASE_URL="https://api.cloudflare.test/account/ai/v1",
        ):
            self.assertTrue(registry.provider_has_api_key("cloudflare"))

    def test_list_active_routes_excludes_inactive(self):
        CapabilityRoute.objects.create(
            slug="active-1", label="Active", provider_key="stub",
            upstream_model="stub", is_active=True, sort_order=1,
        )
        CapabilityRoute.objects.create(
            slug="inactive-1", label="Inactive", provider_key="stub",
            upstream_model="stub", is_active=False, sort_order=2,
        )
        slugs = [r.slug for r in registry.list_active_routes()]
        self.assertEqual(slugs, ["active-1"])

    def test_list_active_routes_excludes_keyless_non_stub_routes_in_live_mode(self):
        _set_mode("live")
        CapabilityRoute.objects.create(
            slug="fast", label="Fast", provider_key="stub",
            upstream_model="stub", is_active=True, sort_order=1,
        )
        CapabilityRoute.objects.create(
            slug="claude-fast", label="Claude Haiku", provider_key="claude",
            upstream_model="claude-haiku-4-5", is_active=True, sort_order=2,
        )
        with override_settings(ANTHROPIC_API_KEY=""):
            slugs = [r.slug for r in registry.list_active_routes()]
        self.assertEqual(slugs, ["fast"])

    def test_get_provider_instantiates_anthropic_provider_when_keyed(self):
        _set_mode("live")
        CapabilityRoute.objects.create(
            slug="claude-fast", label="Claude Haiku", provider_key="claude",
            upstream_model="claude-haiku-4-5",
            credit_rate_input=Decimal("0.05"), credit_rate_output=Decimal("0.15"),
            is_active=True,
        )
        with override_settings(ANTHROPIC_API_KEY="a-key"):
            provider = registry.get_provider("claude-fast")
        self.assertIsInstance(provider, AnthropicProvider)
        self.assertEqual(provider.model, "claude-haiku-4-5")

    def test_get_default_route_prefers_the_flagged_default(self):
        CapabilityRoute.objects.create(
            slug="not-default", label="Not default", provider_key="stub",
            upstream_model="stub", is_active=True, is_default=False, sort_order=1,
        )
        CapabilityRoute.objects.create(
            slug="the-default", label="The default", provider_key="stub",
            upstream_model="stub", is_active=True, is_default=True, sort_order=2,
        )
        self.assertEqual(registry.get_default_route().slug, "the-default")

    def test_get_default_route_falls_back_to_first_active_when_none_flagged(self):
        CapabilityRoute.objects.create(
            slug="only-active", label="Only active", provider_key="stub",
            upstream_model="stub", is_active=True, is_default=False,
        )
        self.assertEqual(registry.get_default_route().slug, "only-active")

    def test_get_default_route_returns_none_when_nothing_is_active(self):
        self.assertIsNone(registry.get_default_route())


class SeedMigrationTests(TestCase):
    """The data migration should install the free route as the default."""

    def test_seed_migration_state(self):
        active = list(CapabilityRoute.objects.filter(is_active=True))
        self.assertEqual([r.slug for r in active], ["oneprompt-free"])
        free_route = CapabilityRoute.objects.get(slug="oneprompt-free")
        self.assertTrue(free_route.is_default)
        self.assertTrue(free_route.is_free)
        stub_route = CapabilityRoute.objects.get(slug="fast")
        self.assertFalse(stub_route.is_default)
        self.assertFalse(stub_route.is_active)

        inactive_slugs = set(
            CapabilityRoute.objects.filter(is_active=False).values_list(
                "slug", flat=True
            )
        )
        self.assertEqual(
            inactive_slugs,
            {
                "fast",
                "deepseek-flash", "deepseek-pro",
                "qwen-turbo", "qwen-plus", "qwen-max",
                "chatgpt-fast", "chatgpt-pro",
                "gemini-flash", "gemini-pro",
                "claude-fast", "claude-pro",
            },
        )
