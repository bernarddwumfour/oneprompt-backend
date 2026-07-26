"""Admin customer operations — list, activate, deactivate, bulk actions, detail, correction."""

import json
import logging
import uuid
from decimal import Decimal, InvalidOperation

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
from apps.operations.services.customer_service import (
    activate_customer,
    bulk_grant_credits,
    bulk_update_customer_status,
    deactivate_customer,
)
from apps.operations.services.operations_service import correct_wallet
from common.audit import log_admin_action
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

CUSTOMER_BULK_ACTIONS = ["activate", "deactivate", "grant_credits"]


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def customer_list_view(request):
    """GET /operations/customers?search=&page=&limit=

    Lists only non-staff customers (is_staff=False), per plan 0008.
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
        search=search, page=page, limit=limit, is_staff=False,
        is_active=is_active, is_email_verified=is_email_verified,
        country=request.GET.get("country", ""),
        date_joined_from=date_joined_from, date_joined_to=date_joined_to,
        ordering=ordering,
    )
    return APIResponse.success(data=result)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Wallet correction
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Single-target activate / deactivate
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
def customer_activate_view(request, user_id):
    """POST /operations/customers/{id}/activate"""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return APIResponse.not_found("User not found.")

    try:
        result = activate_customer(user=user, actor=request.user, request=request)
    except ValueError as e:
        return APIResponse.bad_request(str(e))

    return APIResponse.success(data=result, message=f"{user.email} activated.")


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
def customer_deactivate_view(request, user_id):
    """POST /operations/customers/{id}/deactivate"""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return APIResponse.not_found("User not found.")

    try:
        result = deactivate_customer(user=user, actor=request.user, request=request)
    except ValueError as e:
        return APIResponse.bad_request(str(e))

    return APIResponse.success(data=result, message=f"{user.email} deactivated.")


# ---------------------------------------------------------------------------
# Bulk action
# ---------------------------------------------------------------------------


def _validate_grant_credits_fields(body: dict) -> tuple[dict, dict]:
    """Validate the extra fields required when action is ``grant_credits``."""
    errors: dict = {}
    cleaned: dict = {}

    # amount — required, positive Decimal
    raw = body.get("amount")
    if raw is None:
        errors["amount"] = "Amount is required for grant_credits."
    else:
        try:
            cleaned["amount"] = Decimal(str(raw))
        except (InvalidOperation, ValueError, TypeError):
            errors["amount"] = "Amount must be a valid number."
        else:
            if cleaned["amount"] <= 0:
                errors["amount"] = "Amount must be positive."

    # direction — required
    direction = (body.get("direction") or "").strip().lower()
    if direction not in ("credit", "debit"):
        errors["direction"] = "Direction must be 'credit' or 'debit'."
    else:
        cleaned["direction"] = direction

    # reason — required
    reason = (body.get("reason") or "").strip()
    if not reason:
        errors["reason"] = "Reason is required for grant_credits."
    else:
        cleaned["reason"] = reason

    # batch_key — the client should supply a stable key per submit attempt so
    # retries no-op instead of double-granting. If missing, generate one so a
    # caller that omits it still gets a correct (if non-retry-safe) request
    # instead of silently colliding with every other batch_key-less request
    # for the same user.
    cleaned["batch_key"] = (body.get("batch_key") or "").strip() or uuid.uuid4().hex

    return cleaned, errors


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
def customer_bulk_action_view(request):
    """POST /operations/customers/bulk-action

    Body: {"action": "activate"|"deactivate"|"grant_credits", "ids": [...],
           ...extra fields for grant_credits}
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")

    cleaned, errors = validate_bulk_action(body, CUSTOMER_BULK_ACTIONS)
    if errors:
        return APIResponse.validation_error(errors)

    action = cleaned["action"]

    if action == "grant_credits":
        extra, extra_errors = _validate_grant_credits_fields(body)
        if extra_errors:
            return APIResponse.validation_error(extra_errors)

        results = bulk_grant_credits(
            ids=cleaned["ids"],
            amount=extra["amount"],
            direction=extra["direction"],
            reason=extra["reason"],
            batch_key=extra["batch_key"],
            actor=request.user,
            request=request,
        )
    else:
        results = bulk_update_customer_status(
            ids=cleaned["ids"], action=action, actor=request.user, request=request,
        )

    data = serialize_bulk_result(results)
    message = (
        f"Bulk {action} finished: "
        f"{data['success_count']} succeeded, {data['failed_count']} failed."
    )
    return APIResponse.success(data=data, message=message)
