from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase

from apps.providers.openai_compatible_provider import (
    OpenAIChatCompatibleProvider,
    ProviderError,
)


def _fake_stream_response(lines, ok=True):
    """Build a MagicMock resembling a requests streaming Response."""
    resp = MagicMock()
    resp.ok = ok
    resp.status_code = 200 if ok else 500
    resp.text = "error" if not ok else ""
    resp.iter_lines.return_value = iter(lines)
    return resp


class OpenAIChatCompatibleProviderTests(TestCase):
    def setUp(self):
        cache.clear()
        self.provider = OpenAIChatCompatibleProvider(
            base_url="https://api.deepseek.com",
            api_key="test-key",
            model="deepseek-v4-flash",
            credit_rate_input=Decimal("0.1500"),
            credit_rate_output=Decimal("0.4500"),
        )

    def test_estimate_returns_a_quantized_positive_decimal(self):
        cost = self.provider.estimate(prompt="Hello there", history=[])
        self.assertGreater(cost, Decimal("0"))
        self.assertGreaterEqual(cost.as_tuple().exponent, -2)

    def test_stream_response_yields_delta_content_and_captures_usage(self):
        lines = [
            'data: {"choices": [{"delta": {"content": "Hello"}}]}',
            'data: {"choices": [{"delta": {"content": " world"}}]}',
            'data: {"choices": [{"delta": {}}], "usage": {"prompt_tokens": 10, "completion_tokens": 2}}',
            "data: [DONE]",
        ]
        with patch(
            "apps.providers.openai_compatible_provider.requests.post",
            return_value=_fake_stream_response(lines),
        ):
            chunks = list(
                self.provider.stream_response(
                    prompt="hi", history=[], invocation_id="inv-1"
                )
            )

        self.assertEqual(chunks, ["Hello", " world"])
        self.assertEqual(
            self.provider.last_usage, {"prompt_tokens": 10, "completion_tokens": 2}
        )

    def test_stream_response_stops_early_when_cancelled(self):
        lines = [
            'data: {"choices": [{"delta": {"content": "one "}}]}',
            'data: {"choices": [{"delta": {"content": "two "}}]}',
            'data: {"choices": [{"delta": {"content": "three"}}]}',
        ]

        def line_iter():
            yield lines[0]
            cache.set("cancel:inv-2", True, timeout=60)
            yield lines[1]
            yield lines[2]

        fake_resp = _fake_stream_response([])
        fake_resp.iter_lines.return_value = line_iter()

        with patch(
            "apps.providers.openai_compatible_provider.requests.post",
            return_value=fake_resp,
        ):
            chunks = list(
                self.provider.stream_response(
                    prompt="hi", history=[], invocation_id="inv-2"
                )
            )

        # Stops after the cancellation flag is observed — before "two "/"three".
        self.assertEqual(chunks, ["one "])

    def test_stream_response_raises_provider_error_on_bad_status(self):
        with patch(
            "apps.providers.openai_compatible_provider.requests.post",
            return_value=_fake_stream_response([], ok=False),
        ):
            with self.assertRaises(ProviderError):
                list(
                    self.provider.stream_response(
                        prompt="hi", history=[], invocation_id="inv-3"
                    )
                )

    def test_normalize_usage_prefers_real_usage_over_heuristic(self):
        self.provider.last_usage = {"prompt_tokens": 100, "completion_tokens": 200}
        usage = self.provider.normalize_usage(
            raw_usage={"output_text": "x", "prompt": "y"}
        )
        self.assertEqual(usage["input_tokens"], 100)
        self.assertEqual(usage["output_tokens"], 200)

    def test_normalize_usage_falls_back_to_heuristic_without_real_usage(self):
        self.provider.last_usage = None
        usage = self.provider.normalize_usage(
            raw_usage={"output_text": "hello world", "prompt": "hi", "usage": None}
        )
        self.assertGreater(usage["input_tokens"], 0)
        self.assertGreater(usage["output_tokens"], 0)

    def test_normalize_usage_credits_are_quantized_to_two_decimal_places(self):
        self.provider.last_usage = {"prompt_tokens": 137, "completion_tokens": 53}
        usage = self.provider.normalize_usage(raw_usage={})
        self.assertGreaterEqual(usage["credits"].as_tuple().exponent, -2)

    def test_moderate_and_health_check(self):
        self.assertTrue(self.provider.moderate(text="anything"))
        with patch(
            "apps.providers.openai_compatible_provider.requests.get",
            return_value=MagicMock(ok=True),
        ):
            self.assertTrue(self.provider.health_check())
