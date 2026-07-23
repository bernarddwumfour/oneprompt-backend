"""GET/PATCH /api/v1/operations/settings — platform settings management."""

import json

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.platform.schemas import serialize_platform_settings
from apps.platform.selectors import get_platform_settings
from apps.platform.services import set_platform_mode
from common.decorators import jwt_required, role_required
from common.responses import APIResponse


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
@jwt_required
@role_required("admin")
def platform_settings_view(request):
    if request.method == "PATCH":
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return APIResponse.bad_request("Invalid JSON.")
        try:
            obj = set_platform_mode(
                mode=body.get("mode", ""), actor=request.user
            )
        except ValueError as e:
            return APIResponse.bad_request(str(e))
        return APIResponse.success(
            data=serialize_platform_settings(obj),
            message="Platform mode updated.",
        )

    return APIResponse.success(
        data=serialize_platform_settings(get_platform_settings())
    )
