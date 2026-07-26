"""Billing operations — purchase list, refund, credit-pack CRUD."""

import json
import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.billing.models import CreditPack, Purchase
from apps.billing.schemas.purchase_schemas import (
    serialize_credit_pack,
    serialize_purchase,
)
from apps.credits.services.ledger_service import refund
from apps.operations.selectors.operations_selectors import list_purchases
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

CREDIT_PACK_BULK_ACTIONS = ["activate", "deactivate"]


# ---------------------------------------------------------------------------
# Purchases
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def purchase_list_view(request):
    status = request.GET.get("status", "")
    currency = request.GET.get("currency", "")
    try:
        page, limit = parse_pagination(request)
        ordering = parse_ordering(request, {
            "created_at": "created_at", "status": "status",
            "currency": "currency", "amount_minor_units": "amount_minor_units",
            "amount_credits": "amount_credits", "user_email": "user__email",
        }, "-created_at")
    except ValueError as e:
        return APIResponse.bad_request(str(e))
    created_from, created_to = parse_date_range_param(request, "created_at")
    result = list_purchases(
        search=request.GET.get("search", ""), status=status, currency=currency,
        created_from=created_from, created_to=created_to,
        page=page, limit=limit, ordering=ordering,
    )
    return APIResponse.success(data=result)


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
@transaction.atomic
def purchase_refund_view(request, purchase_id):
    try:
        purchase = Purchase.objects.select_related(
            "credit_pack", "user__wallet"
        ).get(id=purchase_id)
    except Purchase.DoesNotExist:
        return APIResponse.not_found("Purchase not found.")

    if purchase.status != "success":
        return APIResponse.bad_request("Only successful purchases can be refunded.")

    if purchase.refunded_at is not None:
        return APIResponse.conflict("This purchase has already been refunded.")

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")

    reason = (body.get("reason") or "").strip()
    if not reason:
        return APIResponse.bad_request("A reason is required for refunds.")

    idempotency_key = body.get("idempotency_key", "")
    if not idempotency_key:
        return APIResponse.bad_request("idempotency_key is required.")

    # Issue refund via ledger
    entry = refund(
        wallet=purchase.user.wallet,
        amount=purchase.amount_credits,
        idempotency_key=f"refund:{purchase.id}:{idempotency_key}",
        reference={
            "purchase_id": str(purchase.id),
            "purchase_reference": purchase.reference,
        },
        reason=reason,
        actor=request.user,
    )

    purchase.refunded_at = timezone.now()
    purchase.save(update_fields=["refunded_at"])

    logger.info(
        "Refund processed for purchase %s by admin %s: %s",
        purchase.reference,
        request.user.email,
        reason,
    )

    log_admin_action(
        actor=request.user, app_name="billing", action="purchase_refund",
        description=f"Refunded purchase {purchase.reference}",
        request=request,
    )
    return APIResponse.success(
        data={
            "refund_entry_id": str(entry.id),
            "amount_refunded": str(entry.amount),
            "purchase": serialize_purchase(purchase),
        },
        message="Refund processed.",
    )


# ---------------------------------------------------------------------------
# Credit packs (admin CRUD)
# ---------------------------------------------------------------------------


def _validate_pack_fields(body: dict, *, partial: bool) -> tuple[dict, str | None]:
    """Validate/cast credit-pack fields present in *body*.

    *partial* controls whether missing fields are allowed (PATCH) or must be
    present (POST — callers pass sensible defaults for missing keys before
    calling this, matching the previous create behavior).
    Returns (cleaned_fields, error_message). error_message is None on success.
    """
    cleaned: dict = {}

    if "label" in body:
        label = (body.get("label") or "").strip()
        if not label:
            return {}, "label cannot be empty."
        cleaned["label"] = label

    if "currency" in body:
        currency = (body.get("currency") or "").strip().upper()
        if not currency:
            return {}, "currency cannot be empty."
        cleaned["currency"] = currency

    if "amount_credits" in body:
        try:
            amount_credits = Decimal(str(body["amount_credits"]))
        except (InvalidOperation, ValueError, TypeError):
            return {}, "amount_credits must be a valid number."
        if amount_credits <= 0:
            return {}, "amount_credits must be positive."
        cleaned["amount_credits"] = amount_credits

    if "price_minor_units" in body:
        try:
            price_minor_units = int(body["price_minor_units"])
        except (ValueError, TypeError):
            return {}, "price_minor_units must be a whole number."
        if price_minor_units <= 0:
            return {}, "price_minor_units must be positive."
        cleaned["price_minor_units"] = price_minor_units

    if "is_active" in body:
        if not isinstance(body["is_active"], bool):
            return {}, "is_active must be a boolean."
        cleaned["is_active"] = body["is_active"]

    if "sort_order" in body:
        try:
            cleaned["sort_order"] = int(body["sort_order"])
        except (ValueError, TypeError):
            return {}, "sort_order must be a whole number."

    if not partial:
        # Creation path — required fields must be present.
        for required in ("label", "currency", "amount_credits", "price_minor_units"):
            if required not in cleaned:
                return {}, f"{required} is required."

    return cleaned, None


@csrf_exempt
@require_http_methods(["GET", "POST"])
@jwt_required
@role_required("admin")
def credit_packs_admin_view(request):
    """GET: all packs (incl. inactive). POST: create new pack."""
    if request.method == "GET":
        try:
            is_active = parse_optional_bool(request, "is_active")
            ordering = parse_ordering(request, {
                "sort_order": "sort_order", "label": "label",
                "currency": "currency", "amount_credits": "amount_credits",
                "price_minor_units": "price_minor_units",
                "created_at": "created_at",
            }, "sort_order")
        except ValueError as e:
            return APIResponse.bad_request(str(e))
        packs = CreditPack.objects.all()
        search = request.GET.get("search", "").strip()
        if search:
            packs = packs.filter(label__icontains=search)
        currency = request.GET.get("currency", "").strip()
        if currency:
            packs = packs.filter(currency=currency.upper())
        if is_active is not None:
            packs = packs.filter(is_active=is_active)
        packs = packs.order_by(ordering, "label")
        return APIResponse.success(
            data={"packs": [serialize_credit_pack(p) for p in packs]}
        )

    # POST
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")

    body.setdefault("is_active", True)
    body.setdefault("sort_order", 0)

    cleaned, error = _validate_pack_fields(body, partial=False)
    if error:
        return APIResponse.bad_request(error)

    pack = CreditPack.objects.create(**cleaned)
    return APIResponse.created(
        data={"pack": serialize_credit_pack(pack)},
        message="Credit pack created.",
    )


@csrf_exempt
@require_http_methods(["PATCH"])
@jwt_required
@role_required("admin")
def credit_pack_update_view(request, pack_id):
    try:
        pack = CreditPack.objects.get(id=pack_id)
    except CreditPack.DoesNotExist:
        return APIResponse.not_found("Credit pack not found.")

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")

    cleaned, error = _validate_pack_fields(body, partial=True)
    if error:
        return APIResponse.bad_request(error)

    for field, value in cleaned.items():
        setattr(pack, field, value)

    if cleaned:
        pack.save(update_fields=list(cleaned.keys()))

    return APIResponse.success(data={"pack": serialize_credit_pack(pack)})


# ---------------------------------------------------------------------------
# Credit pack bulk action
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
def credit_pack_bulk_action_view(request):
    """POST /operations/credit-packs/bulk-action

    Body: {"action": "activate" | "deactivate", "ids": [...]}
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")

    cleaned, errors = validate_bulk_action(body, CREDIT_PACK_BULK_ACTIONS)
    if errors:
        return APIResponse.validation_error(errors)

    target_active = cleaned["action"] == "activate"

    results: dict = {"success": [], "failed": [], "total": len(cleaned["ids"])}

    for pack_id in cleaned["ids"]:
        try:
            pack = CreditPack.objects.get(id=pack_id)
        except CreditPack.DoesNotExist:
            results["failed"].append({
                "id": pack_id, "name": "Unknown", "reason": "Not found.",
            })
            continue

        if pack.is_active == target_active:
            state = "active" if target_active else "inactive"
            results["failed"].append({
                "id": str(pack.id), "name": pack.label,
                "reason": f"Already {state}.",
            })
            continue

        pack.is_active = target_active
        pack.save(update_fields=["is_active"])

        log_admin_action(
            actor=request.user, app_name="billing",
            action="credit_pack_activate" if target_active else "credit_pack_deactivate",
            description=(
                f"{'Activated' if target_active else 'Deactivated'} credit pack "
                f"{pack.label} (bulk)"
            ),
            request=request,
        )
        results["success"].append({"id": str(pack.id), "name": pack.label})

    data = serialize_bulk_result(results)
    message = (
        f"Bulk {cleaned['action']} finished: "
        f"{data['success_count']} succeeded, {data['failed_count']} failed."
    )
    return APIResponse.success(data=data, message=message)
