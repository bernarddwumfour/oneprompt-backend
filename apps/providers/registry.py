"""DB-backed provider registry — mode-aware per plan 0005.

Test mode: every active non-stub route returns a DummyProvider (no network
call, priced from real route rates). Live mode: only routes with configured
API keys are usable; keyless routes are silently excluded.
"""

import logging
from typing import Optional

from django.conf import settings

from apps.providers.base import AIProvider
from apps.providers.models import CapabilityRoute

logger = logging.getLogger(__name__)

_PROVIDER_CLASSES: dict[str, type] = {}


def _load_provider_classes():
    if _PROVIDER_CLASSES:
        return
    from apps.providers.stub_provider import StubProvider

    _PROVIDER_CLASSES["stub"] = StubProvider

    try:
        from apps.providers.openai_compatible_provider import (
            OpenAIChatCompatibleProvider,
        )
        _PROVIDER_CLASSES["deepseek"] = OpenAIChatCompatibleProvider
        _PROVIDER_CLASSES["qwen"] = OpenAIChatCompatibleProvider
        _PROVIDER_CLASSES["gemini"] = OpenAIChatCompatibleProvider
        _PROVIDER_CLASSES["chatgpt"] = OpenAIChatCompatibleProvider
    except ImportError:
        logger.warning("openai_compatible_provider not available yet")

    try:
        from apps.providers.anthropic_provider import AnthropicProvider
        _PROVIDER_CLASSES["claude"] = AnthropicProvider
    except ImportError:
        logger.warning("anthropic_provider not available yet")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def provider_has_api_key(provider_key: str) -> bool:
    """Return True if the provider has a configured API key (or is stub)."""
    if provider_key == "stub":
        return True
    return bool(_provider_api_key(provider_key))


def get_provider(slug: str) -> Optional[AIProvider]:
    _load_provider_classes()
    try:
        route = CapabilityRoute.objects.get(slug=slug, is_active=True)
    except CapabilityRoute.DoesNotExist:
        return None

    if route.provider_key == "stub":
        return _PROVIDER_CLASSES["stub"]()

    # Test mode: return DummyProvider for any non-stub route
    from apps.platform.selectors import get_platform_mode

    if get_platform_mode() == "test":
        from apps.providers.dummy_provider import DummyProvider

        return DummyProvider(route=route)

    # Live mode: require a configured API key
    if not provider_has_api_key(route.provider_key):
        return None

    provider_class = _PROVIDER_CLASSES.get(route.provider_key)
    if provider_class is None:
        logger.error(
            "Unknown provider_key %s for route %s", route.provider_key, slug
        )
        return None

    return provider_class(
        base_url=_provider_base_url(route.provider_key),
        api_key=_provider_api_key(route.provider_key),
        model=route.upstream_model,
        credit_rate_input=route.credit_rate_input,
        credit_rate_output=route.credit_rate_output,
    )


def list_active_routes() -> list[CapabilityRoute]:
    routes = list(
        CapabilityRoute.objects.filter(is_active=True).order_by("sort_order")
    )
    from apps.platform.selectors import get_platform_mode

    if get_platform_mode() == "live":
        routes = [r for r in routes if provider_has_api_key(r.provider_key)]
    return routes


def get_default_route() -> Optional[CapabilityRoute]:
    routes = list_active_routes()
    for r in routes:
        if r.is_default:
            return r
    return routes[0] if routes else None


# ---------------------------------------------------------------------------
# Provider configuration (env-var based)
# ---------------------------------------------------------------------------


def _provider_base_url(provider_key: str) -> str:
    mapping = {
        "deepseek": getattr(
            settings, "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        ),
        "qwen": getattr(
            settings,
            "QWEN_BASE_URL",
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        ),
        "gemini": getattr(
            settings,
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai",
        ),
        "chatgpt": getattr(
            settings, "OPENAI_BASE_URL", "https://api.openai.com/v1"
        ),
        "claude": getattr(settings, "ANTHROPIC_BASE_URL", ""),
    }
    return mapping.get(provider_key, "")


def _provider_api_key(provider_key: str) -> str:
    mapping = {
        "deepseek": getattr(settings, "DEEPSEEK_API_KEY", ""),
        "qwen": getattr(settings, "QWEN_API_KEY", ""),
        "gemini": getattr(settings, "GEMINI_API_KEY", ""),
        "chatgpt": getattr(settings, "OPENAI_API_KEY", ""),
        "claude": getattr(settings, "ANTHROPIC_API_KEY", ""),
    }
    return mapping.get(provider_key, "")
