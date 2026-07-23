"""AIProvider abstract base class — all provider adapters implement this.

Per README §10 and plan 0001: provider-specific response objects must not
leak into business logic or frontend components.
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Iterator


class AIProvider(ABC):
    """Shared interface for every AI model provider.

    When adding a real provider (Anthropic, OpenAI, Groq, …):
    1. Subclass this.
    2. Implement every abstract method.
    3. Register it in the registry (apps/providers/registry.py).
    """

    @abstractmethod
    def list_capabilities(self) -> list[dict]:
        """Return available capabilities for this provider.

        Each entry: {"id": str, "label": str, "description": str}.
        """
        ...

    @abstractmethod
    def estimate(self, *, prompt: str, history: list[dict]) -> Decimal:
        """Return the estimated credit cost for processing *prompt* with
        the given conversation *history*."""
        ...

    @abstractmethod
    def stream_response(
        self, *, prompt: str, history: list[dict], invocation_id: str
    ) -> Iterator[str]:
        """Yield response chunks (word/token level) for SSE streaming.

        The caller caches a cancellation flag under
        ``cache.set(f"cancel:{invocation_id}", True)`` — this generator
        should check that flag between yields and stop early if set.
        """
        ...

    @abstractmethod
    def normalize_usage(self, *, raw_usage) -> dict:
        """Convert provider-specific usage data into a standard dict:
        {"input_tokens": int, "output_tokens": int, "credits": Decimal}.
        """
        ...

    @abstractmethod
    def moderate(self, *, text: str) -> bool:
        """Return True if *text* passes safety checks."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the provider is reachable and accepting requests."""
        ...
