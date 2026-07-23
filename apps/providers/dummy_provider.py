"""DummyProvider — test-mode stand-in for any real-provider route.

No network call; response text names the route so switching models in test
mode is visibly different. Prices using the ROUTE's real credit rates,
mirroring OpenAIChatCompatibleProvider's per-1K-token formula.
"""

import time
from decimal import ROUND_UP, Decimal

from django.core.cache import cache

from apps.providers.base import AIProvider


def _to_credits(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_UP)


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class DummyProvider(AIProvider):
    """Test-mode stand-in for any non-stub route. Uses the route's real
    credit rates so the ledger flow exercises real pricing, just without
    any actual network call or real cost."""

    def __init__(self, *, route):
        self.route = route
        self.credit_rate_input = route.credit_rate_input
        self.credit_rate_output = route.credit_rate_output

    def list_capabilities(self) -> list[dict]:
        return []

    def estimate(self, *, prompt: str, history: list[dict]) -> Decimal:
        history_text = " ".join(
            m.get("content", "") for m in history if m.get("content")
        )
        input_tokens = _approx_tokens(prompt) + _approx_tokens(history_text)
        estimated_output = max(50, _approx_tokens(prompt) * 3)
        cost = (
            Decimal(input_tokens) / 1000 * self.credit_rate_input
            + Decimal(estimated_output) / 1000 * self.credit_rate_output
        )
        return max(_to_credits(cost), Decimal("0.01"))

    def stream_response(
        self, *, prompt: str, history: list[dict], invocation_id: str
    ):
        text = (
            f"[Test mode — {self.route.label}] This is a simulated response "
            f"from {self.route.label} ({self.route.upstream_model}). No real "
            f"API call was made. Your prompt: \"{prompt[:100]}\""
        )
        words = text.split(" ")
        for i, word in enumerate(words):
            if cache.get(f"cancel:{invocation_id}"):
                return
            yield word + (" " if i < len(words) - 1 else "")
            time.sleep(0.03)

    def normalize_usage(self, *, raw_usage) -> dict:
        output_text = raw_usage.get("output_text", "") or ""
        prompt_text = raw_usage.get("prompt", "") or ""
        input_tokens = _approx_tokens(prompt_text)
        output_tokens = _approx_tokens(output_text)
        cost = (
            Decimal(input_tokens) / 1000 * self.credit_rate_input
            + Decimal(output_tokens) / 1000 * self.credit_rate_output
        )
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "credits": max(_to_credits(cost), Decimal("0.01")),
        }

    def moderate(self, *, text: str) -> bool:
        return True

    def health_check(self) -> bool:
        return True
