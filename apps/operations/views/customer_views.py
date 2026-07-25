"""Admin customer operations — search, detail, wallet correction."""

import json
import logging

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.accounts.models import User
from apps.operations.schemas.operations_schemas import (
    ValidationError,
    validate_correction,
)
from apps.operations.selectors.operations_selectors import (
    get_customer_detail,
    search_customers,
)
from apps.operations.services.operations_service import correct_wallet
from common.audit import log_admin_action
from common.decorators import jwt_required, role_required
from common.responses import APIResponse
from common.utils import parse_pagination

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def customer_list_view(request):
    """GET /operations/customers?search=&page=&limit="""
    search = request.GET.get("search", "")
    try:
        page, limit = parse_pagination(request)
    except ValueError as e:
        return APIResponse.bad_request(str(e))

    result = search_customers(search=search, page=page, limit=limit)
    return APIResponse.success(data=result)


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def customer_detail_view(request, user_id):
    """GET /operations/customers/{id}"""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return APIResponse.not_found("User not found.")

    detail = get_customer_detail(user)
    return APIResponse.success(data=detail)


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
def customer_correct_view(request, user_id):
    """POST /operations/customers/{id}/correct"""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return APIResponse.not_found("User not found.")

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")

    try:
        cleaned = validate_correction(body)
    except ValidationError as e:
        return APIResponse.validation_error(e.errors)

    try:
        result = correct_wallet(
            user=user,
            amount=cleaned["amount"],
            direction=cleaned["direction"],
            reason=cleaned["reason"],
            actor=request.user,
            idempotency_key=cleaned.get("idempotency_key"),
        )
    except ValueError as e:
        return APIResponse.bad_request(str(e))

    log_admin_action(
        actor=request.user, app_name="credits", action="wallet_correction",
        description=f"Corrected {user.email}'s wallet by {cleaned['amount']} ({cleaned['direction']})",
        request=request,
    )
    return APIResponse.success(
        data=result, message="Wallet correction applied."
    )
