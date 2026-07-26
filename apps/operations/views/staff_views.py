"""Staff management — list, activate, deactivate (single + bulk).

Per plan 0008: promote/demote is removed. Staff accounts are provisioned
directly in the backend (Django shell / createsuperuser). The admin-facing
actions here are Activate and Deactivate only.
"""

import json
import logging

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.accounts.models import User
from apps.operations.selectors.operations_selectors import search_customers
from apps.operations.services.staff_service import (
    activate_staff,
    bulk_update_staff_status,
    deactivate_staff,
)
from common.bulk import serialize_bulk_result
from common.decorators import jwt_required, role_required
from common.responses import APIResponse
from common.utils import (
    parse_date_range_param,
    parse_optional_bool,
    parse_ordering,
    parse_pagination,
)
from common.validators import validate_bulk_action

logger = logging.getLogger(__name__)

STAFF_BULK_ACTIONS = ["activate", "deactivate"]


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def staff_list_view(request):
    """GET /operations/staff?search=&page=&limit=

    Lists only staff accounts (is_staff=True), per plan 0008.
    """
    search = request.GET.get("search", "")
    try:
        page, limit = parse_pagination(request)
        is_active = parse_optional_bool(request, "is_active")
        is_email_verified = parse_optional_bool(request, "is_email_verified")
        ordering = parse_ordering(request, {
            "date_joined": "date_joined", "email": "email",
            "full_name": "full_name", "country": "country",
        }, "-date_joined")
    except ValueError as e:
        return APIResponse.bad_request(str(e))
    date_joined_from, date_joined_to = parse_date_range_param(request, "date_joined")
    result = search_customers(
        search=search, page=page, limit=limit, is_staff=True,
        is_active=is_active, is_email_verified=is_email_verified,
        country=request.GET.get("country", ""),
        date_joined_from=date_joined_from, date_joined_to=date_joined_to,
        ordering=ordering,
    )
    return APIResponse.success(data=result)


# ---------------------------------------------------------------------------
# Single-target activate / deactivate
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
def staff_activate_view(request, user_id):
    """POST /operations/staff/{id}/activate"""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return APIResponse.not_found("User not found.")

    try:
        result = activate_staff(user=user, actor=request.user, request=request)
    except ValueError as e:
        return APIResponse.bad_request(str(e))

    return APIResponse.success(data=result, message=f"{user.email} activated.")


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
def staff_deactivate_view(request, user_id):
    """POST /operations/staff/{id}/deactivate"""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return APIResponse.not_found("User not found.")

    try:
        result = deactivate_staff(user=user, actor=request.user, request=request)
    except ValueError as e:
        return APIResponse.bad_request(str(e))

    return APIResponse.success(data=result, message=f"{user.email} deactivated.")


# ---------------------------------------------------------------------------
# Bulk action
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
def staff_bulk_action_view(request):
    """POST /operations/staff/bulk-action

    Body: {"action": "activate" | "deactivate", "ids": [...]}
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")

    cleaned, errors = validate_bulk_action(body, STAFF_BULK_ACTIONS)
    if errors:
        return APIResponse.validation_error(errors)

    results = bulk_update_staff_status(
        ids=cleaned["ids"], action=cleaned["action"], actor=request.user, request=request,
    )

    data = serialize_bulk_result(results)
    message = (
        f"Bulk {cleaned['action']} finished: "
        f"{data['success_count']} succeeded, {data['failed_count']} failed."
    )
    return APIResponse.success(data=data, message=message)
