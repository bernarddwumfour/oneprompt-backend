from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.providers.stub_provider import StubProvider


class StubProviderTests(TestCase):
    def setUp(self):
        self.provider = StubProvider()
        cache.clear()
        sleep_patcher = patch("apps.providers.stub_provider.time.sleep")
        sleep_patcher.start()
        self.addCleanup(sleep_patcher.stop)

    def test_estimate_returns_a_positive_decimal(self):
        cost = self.provider.estimate(prompt="Hello there", history=[])
        self.assertGreater(cost, Decimal("0"))

    def test_stream_response_yields_the_full_canned_response(self):
        chunks = list(
            self.provider.stream_response(prompt="hi", history=[], invocation_id="test-1")
        )
        self.assertGreater(len(chunks), 0)
        self.assertTrue("".join(chunks).strip())

    def test_stream_response_respects_the_cancellation_flag(self):
        cache.set("cancel:test-2", True, timeout=60)
        chunks = list(
            self.provider.stream_response(prompt="hi", history=[], invocation_id="test-2")
        )
        self.assertEqual(chunks, [])

    def test_stream_response_stops_mid_way_once_cancelled(self):
        gen = self.provider.stream_response(prompt="hi", history=[], invocation_id="test-3")
        next(gen)
        next(gen)
        cache.set("cancel:test-3", True, timeout=60)
        remaining = list(gen)
        self.assertEqual(remaining, [])

    def test_normalize_usage_is_deterministic_and_shaped_correctly(self):
        raw = {"output_text": "hello world", "prompt": "hi"}
        usage1 = self.provider.normalize_usage(raw_usage=raw)
        usage2 = self.provider.normalize_usage(raw_usage=raw)

        self.assertEqual(usage1, usage2)
        self.assertIn("input_tokens", usage1)
        self.assertIn("output_tokens", usage1)
        self.assertIn("credits", usage1)
        self.assertGreater(usage1["credits"], Decimal("0"))

    def test_moderate_and_health_check(self):
        self.assertTrue(self.provider.moderate(text="anything"))
        self.assertTrue(self.provider.health_check())
