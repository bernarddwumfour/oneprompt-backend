"""StubProvider — fake streaming adapter for dev/testing.

Per plan 0001 §Backend-architecture: simulates token-by-token streaming and
usage, so the full chat flow (reserve → stream → capture) works end-to-end
without needing a real API key.
"""

import logging
import time
from decimal import ROUND_UP, Decimal
from typing import Iterator

from django.core.cache import cache

from apps.providers.base import AIProvider

logger = logging.getLogger(__name__)

STUB_CAPABILITIES = [
    {
        "id": "fast",
        "label": "Fast",
        "description": "Quick responses for everyday tasks.",
    },
]

# Simple cost model: credits = input_tokens * rate + output_tokens * rate
CREDITS_PER_TOKEN_IN = Decimal("0.0001")
CREDITS_PER_TOKEN_OUT = Decimal("0.0003")


def _approx_tokens(text: str) -> int:
    """Very rough token estimate — ~4 chars per token."""
    return max(1, len(text) // 4)


def _to_credits(amount: Decimal) -> Decimal:
    """Quantize to 2 decimal places (rounding up) — matches the precision of
    CreditWallet/CreditLedgerEntry, so what's shown on a ModelInvocation
    exactly matches what the ledger actually records/deducts."""
    return amount.quantize(Decimal("0.01"), rounding=ROUND_UP)


class StubProvider(AIProvider):
    """Fake provider that echoes prompts in a streaming fashion."""

    def list_capabilities(self) -> list[dict]:
        return STUB_CAPABILITIES

    def estimate(self, *, prompt: str, history: list[dict]) -> Decimal:
        # Estimate input tokens from prompt + history
        history_text = " ".join(m.get("content", "") for m in history if m.get("content"))
        input_tokens = _approx_tokens(prompt + history_text)
        # Assume a small output
        estimated_output = max(50, _approx_tokens(prompt) * 3)
        cost = Decimal(input_tokens) * CREDITS_PER_TOKEN_IN + Decimal(
            estimated_output
        ) * CREDITS_PER_TOKEN_OUT
        return max(_to_credits(cost), Decimal("0.01"))  # floor at 0.01

    def stream_response(
        self, *, prompt: str, history: list[dict], invocation_id: str
    ) -> Iterator[str]:
        """Yield canned response chunks with a short delay.

        Checks ``cache.get(f"cancel:{invocation_id}")`` between chunks.
        """
        # Build a simple echo response
        response = self._build_response(prompt)
        words = response.split()

        for i, word in enumerate(words):
            # Check cancellation flag
            if cache.get(f"cancel:{invocation_id}"):
                logger.info("StubProvider: cancellation flag set for %s", invocation_id)
                return

            yield word + (" " if i < len(words) - 1 else "")
            time.sleep(0.08)  # simulate streaming latency

    def normalize_usage(self, *, raw_usage) -> dict:
        """Convert our stub output into a standard usage report."""
        output_text = raw_usage.get("output_text", "")
        prompt_text = raw_usage.get("prompt", "")
        input_tokens = _approx_tokens(prompt_text)
        output_tokens = _approx_tokens(output_text)
        credits = (
            Decimal(input_tokens) * CREDITS_PER_TOKEN_IN
            + Decimal(output_tokens) * CREDITS_PER_TOKEN_OUT
        )
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "credits": max(_to_credits(credits), Decimal("0.01")),
        }

    def moderate(self, *, text: str) -> bool:
        # Stub: everything passes
        return True

    def health_check(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_response(self, prompt: str) -> str:
        """Generate a canned response that echoes/rephrases the prompt.

        In production this is replaced by a real provider call.
        """
        return (
            f"Thank you for your message! Here's my response to: \"{prompt[:100]}{'...' if len(prompt) > 100 else ''}\". "
            "This is a stubbed response from the OnePrompt development environment. "
            "When a real AI provider is configured, you'll receive actual model responses here. "
            "Until then, this stub demonstrates the full streaming, credit reservation, and cancellation flow. "
            "You can stop generation, see your credit balance update, and verify that the ledger is working correctly."
        )
