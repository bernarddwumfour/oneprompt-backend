from decimal import Decimal
from unittest.mock import MagicMock, patch

import anthropic
from django.core.cache import cache
from django.test import TestCase

from apps.providers.anthropic_provider import AnthropicProvider, ProviderError


def _make_provider(**overrides):
    kwargs = dict(
        base_url="",
        api_key="test-key",
        model="claude-haiku-4-5",
        credit_rate_input=Decimal("0.05"),
        credit_rate_output=Decimal("0.15"),
    )
    kwargs.update(overrides)
    return AnthropicProvider(**kwargs)


class AnthropicProviderTests(TestCase):
    def setUp(self):
        cache.clear()
        patcher = patch("apps.providers.anthropic_provider.anthropic.Anthropic")
        self.mock_anthropic_cls = patcher.start()
        self.addCleanup(patcher.stop)
        self.mock_client = self.mock_anthropic_cls.return_value

    def _mock_stream(self, chunks, input_tokens=10, output_tokens=20):
        stream_cm = MagicMock()
        stream_cm.__enter__.return_value.text_stream = iter(chunks)
        final_message = MagicMock()
        final_message.usage.input_tokens = input_tokens
        final_message.usage.output_tokens = output_tokens
        stream_cm.__enter__.return_value.get_final_message.return_value = final_message
        self.mock_client.messages.stream.return_value = stream_cm
        return stream_cm

    def test_constructs_client_with_api_key_only_when_no_base_url(self):
        _make_provider(api_key="my-key", base_url="")
        self.mock_anthropic_cls.assert_called_once_with(api_key="my-key")

    def test_constructs_client_with_base_url_when_provided(self):
        _make_provider(api_key="my-key", base_url="https://proxy.example.com")
        self.mock_anthropic_cls.assert_called_once_with(
            api_key="my-key", base_url="https://proxy.example.com"
        )

    def test_stream_response_yields_text_and_builds_messages_correctly(self):
        self._mock_stream(["Hello", " there"])
        provider = _make_provider()

        history = [
            {"role": "user", "content": "previous question"},
            {"role": "assistant", "content": "previous answer"},
        ]
        chunks = list(
            provider.stream_response(
                prompt="new question", history=history, invocation_id="anthropic-1"
            )
        )
        self.assertEqual(chunks, ["Hello", " there"])

        call_kwargs = self.mock_client.messages.stream.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "claude-haiku-4-5")
        self.assertEqual(call_kwargs["system"], "You are a helpful AI assistant.")
        messages = call_kwargs["messages"]
        self.assertEqual(messages[0], {"role": "user", "content": "previous question"})
        self.assertEqual(
            messages[1], {"role": "assistant", "content": "previous answer"}
        )
        self.assertEqual(messages[-1], {"role": "user", "content": "new question"})

    def test_stream_response_respects_the_cancellation_flag(self):
        self._mock_stream(["Hello", " there", " world"])
        provider = _make_provider()
        cache.set("cancel:anthropic-2", True, timeout=60)

        chunks = list(
            provider.stream_response(
                prompt="hi", history=[], invocation_id="anthropic-2"
            )
        )
        self.assertEqual(chunks, [])

    def test_normalize_usage_uses_real_usage_after_streaming(self):
        self._mock_stream(["hi"], input_tokens=100, output_tokens=200)
        provider = _make_provider()
        list(
            provider.stream_response(
                prompt="hi", history=[], invocation_id="anthropic-3"
            )
        )

        usage = provider.normalize_usage(raw_usage={})
        self.assertEqual(usage["input_tokens"], 100)
        self.assertEqual(usage["output_tokens"], 200)
        self.assertGreater(usage["credits"], Decimal("0"))

    def test_normalize_usage_falls_back_to_heuristic_without_prior_streaming(self):
        provider = _make_provider()
        usage = provider.normalize_usage(
            raw_usage={"prompt": "hi", "output_text": "a reply"}
        )
        self.assertIn("input_tokens", usage)
        self.assertIn("output_tokens", usage)
        self.assertIn("credits", usage)

    def test_stream_response_wraps_api_errors_as_provider_error(self):
        self.mock_client.messages.stream.side_effect = anthropic.APIError(
            "boom", request=MagicMock(), body=None
        )
        provider = _make_provider()
        with self.assertRaises(ProviderError):
            list(
                provider.stream_response(
                    prompt="hi", history=[], invocation_id="anthropic-4"
                )
            )

    def test_moderate_always_true(self):
        self.assertTrue(_make_provider().moderate(text="anything"))

    def test_health_check_true_when_client_call_succeeds(self):
        provider = _make_provider()
        self.mock_client.models.retrieve.return_value = MagicMock()
        self.assertTrue(provider.health_check())

    def test_health_check_false_when_client_call_raises(self):
        provider = _make_provider()
        self.mock_client.models.retrieve.side_effect = Exception("network error")
        self.assertFalse(provider.health_check())
