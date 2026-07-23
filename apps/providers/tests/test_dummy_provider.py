from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.providers.dummy_provider import DummyProvider
from apps.providers.models import CapabilityRoute


class DummyProviderTests(TestCase):
    def setUp(self):
        cache.clear()
        sleep_patcher = patch("apps.providers.dummy_provider.time.sleep")
        sleep_patcher.start()
        self.addCleanup(sleep_patcher.stop)

        self.cheap_route = CapabilityRoute(
            slug="claude-fast",
            label="Claude Haiku",
            provider_key="claude",
            upstream_model="claude-haiku-4-5",
            credit_rate_input=Decimal("0.05"),
            credit_rate_output=Decimal("0.15"),
        )
        self.expensive_route = CapabilityRoute(
            slug="claude-pro",
            label="Claude Opus (Reasoning)",
            provider_key="claude",
            upstream_model="claude-opus-4-8",
            credit_rate_input=Decimal("0.20"),
            credit_rate_output=Decimal("0.60"),
        )

    def test_estimate_scales_with_the_routes_real_credit_rates(self):
        cheap = DummyProvider(route=self.cheap_route)
        expensive = DummyProvider(route=self.expensive_route)

        prompt = "Explain quantum entanglement in detail, please." * 5
        cheap_cost = cheap.estimate(prompt=prompt, history=[])
        expensive_cost = expensive.estimate(prompt=prompt, history=[])

        self.assertGreater(expensive_cost, cheap_cost)

    def test_stream_response_names_the_route(self):
        provider = DummyProvider(route=self.expensive_route)
        chunks = list(
            provider.stream_response(
                prompt="hi", history=[], invocation_id="dummy-1"
            )
        )
        text = "".join(chunks)
        self.assertIn(self.expensive_route.label, text)
        self.assertIn(self.expensive_route.upstream_model, text)

    def test_stream_response_respects_the_cancellation_flag(self):
        provider = DummyProvider(route=self.cheap_route)
        cache.set("cancel:dummy-2", True, timeout=60)
        chunks = list(
            provider.stream_response(prompt="hi", history=[], invocation_id="dummy-2")
        )
        self.assertEqual(chunks, [])

    def test_normalize_usage_scales_with_the_routes_real_credit_rates(self):
        # Long enough that both costs clear the Decimal("0.01") floor —
        # otherwise a short reply floors both routes to the same value and
        # hides the real per-rate difference this test is checking for.
        raw = {"output_text": "word " * 150, "prompt": "hi"}
        cheap = DummyProvider(route=self.cheap_route).normalize_usage(raw_usage=raw)
        expensive = DummyProvider(route=self.expensive_route).normalize_usage(
            raw_usage=raw
        )

        self.assertEqual(set(cheap.keys()), {"input_tokens", "output_tokens", "credits"})
        self.assertGreater(expensive["credits"], cheap["credits"])

    def test_moderate_and_health_check(self):
        provider = DummyProvider(route=self.cheap_route)
        self.assertTrue(provider.moderate(text="anything"))
        self.assertTrue(provider.health_check())
