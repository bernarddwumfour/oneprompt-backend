"""AnthropicProvider — Claude via the official anthropic Python SDK.

Per plan 0005: Anthropic's Messages API has a different shape from
OpenAI-compatible APIs (system as top-level field, content_block_delta
events), so it needs its own adapter using the official SDK.
"""

from decimal import ROUND_UP, Decimal

import anthropic
from django.core.cache import cache

from apps.providers.base import AIProvider


def _to_credits(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_UP)


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class ProviderError(Exception):
    """Raised when an Anthropic API call fails."""


class AnthropicProvider(AIProvider):
    """Claude adapter using the official anthropic SDK."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        credit_rate_input: Decimal,
        credit_rate_output: Decimal,
    ):
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = anthropic.Anthropic(**kwargs)
        self.model = model
        self.credit_rate_input = credit_rate_input
        self.credit_rate_output = credit_rate_output
        self.last_usage: dict | None = None

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
        messages = []
        for msg in history[-20:]:
            role = "assistant" if msg.get("role") == "assistant" else "user"
            messages.append({"role": role, "content": msg.get("content", "")})
        messages.append({"role": "user", "content": prompt})

        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=4096,
                system="You are a helpful AI assistant.",
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    if cache.get(f"cancel:{invocation_id}"):
                        return
                    yield text
                final = stream.get_final_message()
                self.last_usage = {
                    "input_tokens": final.usage.input_tokens,
                    "output_tokens": final.usage.output_tokens,
                }
        except anthropic.APIError as exc:
            raise ProviderError(str(exc)) from exc

    def normalize_usage(self, *, raw_usage) -> dict:
        if self.last_usage:
            input_tokens = self.last_usage["input_tokens"]
            output_tokens = self.last_usage["output_tokens"]
        else:
            input_tokens = _approx_tokens(raw_usage.get("prompt", "") or "")
            output_tokens = _approx_tokens(
                raw_usage.get("output_text", "") or ""
            )
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
        try:
            self.client.models.retrieve(self.model)
            return True
        except Exception:
            return False
