"""Admin analytics views — trends and provider comparison."""

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.operations.selectors.analytics_selectors import (
    get_active_users_trend,
    get_provider_comparison,
    get_revenue_trend,
    get_usage_trend,
)
from common.decorators import jwt_required, role_required
from common.responses import APIResponse
from common.utils import parse_int_query_param


def _trend_to_list(qs) -> list:
    return [
        {"day": row["day"].isoformat(), "value": row["value"]}
        for row in qs
    ]


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def analytics_trends_view(request):
    currency = request.GET.get("currency", "GHS").upper()
    try:
        days = parse_int_query_param(request, "days", 30, min_value=1, max_value=365)
    except ValueError as e:
        return APIResponse.bad_request(str(e))
    return APIResponse.success(
        data={
            "revenue": _trend_to_list(get_revenue_trend(currency=currency, days=days)),
            "usage": _trend_to_list(get_usage_trend(currency=currency, days=days)),
            "active_users": _trend_to_list(get_active_users_trend(days=days)),
        }
    )


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def analytics_providers_view(request):
    currency = request.GET.get("currency", "GHS").upper()
    period = request.GET.get("period", "month")
    rows = get_provider_comparison(currency=currency, period=period)
    return APIResponse.success(
        data={
            "providers": [
                {
                    "capability": r["capability"],
                    "invocation_count": r["invocation_count"],
                    "credits_charged": str(r["credits_charged"] or 0),
                    "provider_cost_usd": str(r["provider_cost_usd"] or 0),
                }
                for r in rows
            ]
        }
    )
