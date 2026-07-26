"""GET/PATCH /api/v1/operations/capability-routes — admin provider management."""

import json
import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.platform.selectors import get_platform_mode
from apps.providers.models import CapabilityRoute
from apps.providers.registry import provider_has_api_key
from common.audit import log_admin_action
from common.bulk import serialize_bulk_result
from common.decorators import jwt_required, role_required
from common.responses import APIResponse
from common.utils import parse_optional_bool, parse_ordering
from common.validators import validate_bulk_action

logger = logging.getLogger(__name__)

PROVIDER_BULK_ACTIONS = ["activate", "deactivate"]

# Fields allowed for PATCH — never provider_key/upstream_model/slug
BOOLEAN_FIELDS = {"is_active", "is_default", "is_free"}
DECIMAL_FIELDS = {
    "credit_rate_input", "credit_rate_output",
    "provider_cost_input", "provider_cost_output",
}
PATCHABLE_FIELDS = BOOLEAN_FIELDS | DECIMAL_FIELDS


def _serialize_route(route: CapabilityRoute) -> dict:
    return {
        "id": str(route.id),
        "slug": route.slug,
        "label": route.label,
        "description": route.description,
        "provider_key": route.provider_key,
        "upstream_model": route.upstream_model,
        "credit_rate_input": str(route.credit_rate_input),
        "credit_rate_output": str(route.credit_rate_output),
        "provider_cost_input": str(route.provider_cost_input),
        "provider_cost_output": str(route.provider_cost_output),
        "is_active": route.is_active,
        "is_default": route.is_default,
        "is_free": route.is_free,
        "sort_order": route.sort_order,
    }


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def capability_route_list_view(request):
    try:
        is_active = parse_optional_bool(request, "is_active")
        is_default = parse_optional_bool(request, "is_default")
        is_free = parse_optional_bool(request, "is_free")
        ordering = parse_ordering(request, {
            "sort_order": "sort_order", "label": "label",
            "provider_key": "provider_key", "upstream_model": "upstream_model",
            "credit_rate_input": "credit_rate_input",
            "credit_rate_output": "credit_rate_output",
            "provider_cost_input": "provider_cost_input",
            "provider_cost_output": "provider_cost_output",
        }, "sort_order")
    except ValueError as e:
        return APIResponse.bad_request(str(e))
    routes = CapabilityRoute.objects.all()
    search = request.GET.get("search", "").strip()
    if search:
        from django.db.models import Q
        routes = routes.filter(
            Q(label__icontains=search) | Q(slug__icontains=search)
            | Q(upstream_model__icontains=search)
        )
    provider_key = request.GET.get("provider_key", "").strip()
    if provider_key:
        routes = routes.filter(provider_key=provider_key)
    if is_active is not None:
        routes = routes.filter(is_active=is_active)
    if is_default is not None:
        routes = routes.filter(is_default=is_default)
    if is_free is not None:
        routes = routes.filter(is_free=is_free)
    routes = routes.order_by(ordering, "label")
    return APIResponse.success(data={"routes": [_serialize_route(r) for r in routes]})


def _validate_route_patch(body: dict) -> tuple[dict, str | None]:
    """Validate/cast the fields present in *body*. Returns (cleaned, error)."""
    invalid = set(body.keys()) - PATCHABLE_FIELDS
    if invalid:
        return {}, f"Cannot modify: {', '.join(sorted(invalid))}"

    cleaned: dict = {}

    for field in BOOLEAN_FIELDS:
        if field in body:
            if not isinstance(body[field], bool):
                return {}, f"{field} must be a boolean."
            cleaned[field] = body[field]

    for field in DECIMAL_FIELDS:
        if field in body:
            try:
                value = Decimal(str(body[field]))
            except (InvalidOperation, ValueError, TypeError):
                return {}, f"{field} must be a valid number."
            if value < 0:
                return {}, f"{field} cannot be negative."
            cleaned[field] = value

    return cleaned, None


@csrf_exempt
@require_http_methods(["PATCH"])
@jwt_required
@role_required("admin")
@transaction.atomic
def capability_route_update_view(request, route_id):
    try:
        # Locks this row (and, on Postgres, the bulk update below) for the
        # duration of the transaction so a concurrent PATCH setting a
        # different route as default can't race past the "clear others"
        # step and leave two routes marked default.
        route = CapabilityRoute.objects.select_for_update().get(id=route_id)
    except CapabilityRoute.DoesNotExist:
        return APIResponse.not_found("Capability route not found.")

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")

    cleaned, error = _validate_route_patch(body)
    if error:
        return APIResponse.bad_request(error)

    # Live mode: a non-stub route can't be (or stay) active without a
    # configured API key. Checked here — not just at registry read-time —
    # so the admin gets an immediate, clear error instead of a silently
    # inert "active" route. Applies even when this PATCH doesn't touch
    # is_active (e.g. editing a rate on a route that was already active
    # while in test mode, then the platform flipped to live).
    effective_active = cleaned.get("is_active", route.is_active)
    if (
        effective_active
        and route.provider_key != "stub"
        and get_platform_mode() == "live"
        and not provider_has_api_key(route.provider_key)
    ):
        return APIResponse.bad_request(
            f"Cannot activate '{route.label}': no API key configured for "
            f"provider '{route.provider_key}'. Switch the platform to test "
            "mode or configure the key first."
        )

    # If setting is_default=True, clear it on all others first.
    if cleaned.get("is_default"):
        CapabilityRoute.objects.select_for_update().filter(
            is_default=True
        ).exclude(id=route.id).update(is_default=False)

    for field, value in cleaned.items():
        setattr(route, field, value)

    if cleaned:
        route.save(update_fields=list(cleaned.keys()))

    log_admin_action(
        actor=request.user, app_name="providers", action="capability_route_update",
        description=f"Updated route {route.slug}: {list(cleaned.keys())}",
        request=request,
    )
    return APIResponse.success(data={"route": _serialize_route(route)})


# ---------------------------------------------------------------------------
# Bulk action
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
def capability_route_bulk_action_view(request):
    """POST /operations/capability-routes/bulk-action

    Body: {"action": "activate" | "deactivate", "ids": [...]}

    Only toggles ``is_active``. ``is_default`` is inherently exclusive and
    stays single-target only (via the existing PATCH endpoint).
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")

    cleaned, errors = validate_bulk_action(body, PROVIDER_BULK_ACTIONS)
    if errors:
        return APIResponse.validation_error(errors)

    target_active = cleaned["action"] == "activate"

    results: dict = {"success": [], "failed": [], "total": len(cleaned["ids"])}

    for route_id in cleaned["ids"]:
        try:
            route = CapabilityRoute.objects.get(id=route_id)
        except CapabilityRoute.DoesNotExist:
            results["failed"].append({
                "id": route_id, "name": "Unknown", "reason": "Not found.",
            })
            continue

        if route.is_active == target_active:
            state = "active" if target_active else "inactive"
            results["failed"].append({
                "id": str(route.id), "name": route.label,
                "reason": f"Already {state}.",
            })
            continue

        # Live-mode guard: activating a non-stub route without a configured
        # API key is rejected (mirrors the single-PATCH guard).
        if target_active and route.provider_key != "stub":
            if get_platform_mode() == "live" and not provider_has_api_key(route.provider_key):
                results["failed"].append({
                    "id": str(route.id), "name": route.label,
                    "reason": (
                        f"No API key configured for provider "
                        f"'{route.provider_key}' (platform is live)."
                    ),
                })
                continue

        route.is_active = target_active
        route.save(update_fields=["is_active"])

        log_admin_action(
            actor=request.user, app_name="providers",
            action="capability_route_activate" if target_active else "capability_route_deactivate",
            description=(
                f"{'Activated' if target_active else 'Deactivated'} route "
                f"{route.slug} (bulk)"
            ),
            request=request,
        )
        results["success"].append({"id": str(route.id), "name": route.label})

    data = serialize_bulk_result(results)
    message = (
        f"Bulk {cleaned['action']} finished: "
        f"{data['success_count']} succeeded, {data['failed_count']} failed."
    )
    return APIResponse.success(data=data, message=message)
