"""GET /api/v1/capabilities — list active routes for the frontend selector."""

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.platform.selectors import get_platform_mode
from apps.providers.registry import get_default_route, list_active_routes
from common.decorators import jwt_required
from common.responses import APIResponse


def _serialize_route(route) -> dict:
    return {
        "slug": route.slug,
        "label": route.label,
        "description": route.description,
        "is_default": route.is_default,
        "is_free": route.is_free,
    }


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def capabilities_view(request):
    routes = list_active_routes()
    default = get_default_route()

    return APIResponse.success(
        data={
            "capabilities": [_serialize_route(r) for r in routes],
            "default_slug": default.slug if default else None,
            "mode": get_platform_mode(),
        }
    )
