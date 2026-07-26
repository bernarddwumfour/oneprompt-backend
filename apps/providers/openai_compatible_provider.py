"""OpenAICompatibleProvider — shared adapter for OpenAI-compatible chat APIs.

Both DeepSeek and Qwen (international endpoint) expose an OpenAI-compatible
``/chat/completions`` endpoint. This base class handles HTTP, SSE streaming
parsing, and usage normalization. Per-provider sub-configuration (base_url,
api_key, model id, credit rates) is passed via constructor args — zero
hardcoding per plan 0002.
"""

import json
import logging
from decimal import ROUND_UP, Decimal
from typing import Iterator

import requests
from django.core.cache import cache

from apps.providers.base import AIProvider

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Raised when a provider HTTP call fails."""


class OpenAIChatCompatibleProvider(AIProvider):
    """Shared adapter for any OpenAI-compatible chat-completions API.

    Constructor args:
        base_url:       e.g. "https://api.deepseek.com"
        api_key:        provider API key (empty string = not configured)
        model:          upstream model id, e.g. "deepseek-v4-pro"
        credit_rate_input:   Decimal, retail credits per 1K input tokens
        credit_rate_output:  Decimal, retail credits per 1K output tokens
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        credit_rate_input: Decimal,
        credit_rate_output: Decimal,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.credit_rate_input = credit_rate_input
        self.credit_rate_output = credit_rate_output
        self.last_usage: dict | None = None  # populated after stream_response

    # ------------------------------------------------------------------
    # AIProvider interface
    # ------------------------------------------------------------------

    def list_capabilities(self) -> list[dict]:
        # Capabilities are managed via CapabilityRoute in the DB;
        # a single adapter instance serves exactly one model.
        return []

    def estimate(self, *, prompt: str, history: list[dict]) -> Decimal:
        """Rough heuristic: token-count the prompt + history, price at
        the route's configured credit rates."""
        history_text = " ".join(
            m.get("content", "") for m in history if m.get("content")
        )
        input_tokens = _approx_tokens(prompt + history_text)
        # Assume output ~3× input for estimation
        estimated_output = max(50, input_tokens * 3)
        cost = (
            Decimal(input_tokens) / 1000 * self.credit_rate_input
            + Decimal(estimated_output) / 1000 * self.credit_rate_output
        )
        return Decimal("0.00") if cost == 0 else max(
            _to_credits(cost), Decimal("0.01")
        )

    def stream_response(
        self, *, prompt: str, history: list[dict], invocation_id: str
    ) -> Iterator[str]:
        """POST to /chat/completions with stream=True, parse SSE data: lines.

        Stashes the final chunk's ``usage`` on ``self.last_usage`` so
        ``normalize_usage`` can prefer real token counts over the heuristic.
        """
        messages = [
            {"role": "system", "content": "You are a helpful AI assistant."},
        ]
        for m in history[-20:]:  # last 20 messages for context
            role = m.get("role", "user")
            if role == "assistant":
                role = "assistant"
            else:
                role = "user"
            messages.append({"role": role, "content": m.get("content", "")})

        # Add the current prompt
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        try:
            response = requests.post(
                url,
                json=body,
                headers=headers,
                stream=True,
                timeout=120,
            )
            if not response.ok:
                raise ProviderError(
                    f"Provider returned {response.status_code}: {response.text[:300]}"
                )
        except requests.RequestException as e:
            raise ProviderError(f"Provider request failed: {e}") from e

        self.last_usage = None

        try:
            for line in response.iter_lines(decode_unicode=True):
                # Check cancellation flag between lines
                if cache.get(f"cancel:{invocation_id}"):
                    logger.info(
                        "OpenAICompat: cancellation flag set for %s", invocation_id
                    )
                    response.close()
                    return

                if not line or not line.startswith("data: "):
                    continue

                data_str = line[6:]  # strip "data: " prefix
                if data_str == "[DONE]":
                    break

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                # Stash the usage object from the final chunk
                if "usage" in data and data["usage"]:
                    self.last_usage = data["usage"]

                # Extract delta content
                choices = data.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content

        except requests.RequestException as e:
            raise ProviderError(f"Stream interrupted: {e}") from e
        finally:
            response.close()

    def normalize_usage(self, *, raw_usage) -> dict:
        """Return {input_tokens, output_tokens, credits}.

        Prefers real provider usage data (from ``self.last_usage`` or
        ``raw_usage["usage"]``) over the text-length heuristic.
        """
        usage = (
            self.last_usage
            or raw_usage.get("usage")
        )

        if usage and isinstance(usage, dict):
            input_tokens = int(usage.get("prompt_tokens") or 0)
            output_tokens = int(usage.get("completion_tokens") or 0)
        else:
            # Fallback: text-length heuristic
            output_text = raw_usage.get("output_text", "")
            prompt_text = raw_usage.get("prompt", "")
            input_tokens = _approx_tokens(prompt_text)
            output_tokens = _approx_tokens(output_text)

        credits = (
            Decimal(input_tokens) / 1000 * self.credit_rate_input
            + Decimal(output_tokens) / 1000 * self.credit_rate_output
        )
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "credits": (
                Decimal("0.00")
                if credits == 0
                else max(_to_credits(credits), Decimal("0.01"))
            ),
        }

    def moderate(self, *, text: str) -> bool:
        # Neither DeepSeek nor Qwen expose a moderation endpoint via the
        # OpenAI-compatible API yet. Default to pass.
        return True

    def health_check(self) -> bool:
        """Cheap call: list models (only needs auth, no inference cost)."""
        try:
            resp = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=15,
            )
            return resp.ok
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _approx_tokens(text: str) -> int:
    """Very rough token estimate — ~4 chars per token."""
    return max(1, len(text) // 4)


def _to_credits(amount: Decimal) -> Decimal:
    """Quantize to 2 decimal places (rounding up) — matches the precision of
    CreditWallet/CreditLedgerEntry, so what's shown to the client (e.g. the
    SSE "done" event's credits_charged) exactly matches what the ledger
    actually records/deducts."""
    return amount.quantize(Decimal("0.01"), rounding=ROUND_UP)
