"""Customer management services — activate, deactivate, bulk grant credits.

Per plan 0008: activate/deactivate for customer accounts (no last-active-staff
guard needed here). Bulk grant-credits loops the existing ``correct_wallet``
service with deterministic per-user idempotency keys derived from a
client-supplied batch key.
"""

import logging
from decimal import Decimal

from apps.accounts.models import User
from apps.operations.services.operations_service import correct_wallet
from common.audit import log_admin_action

logger = logging.getLogger(__name__)


def _user_label(user: User) -> str:
    return user.email or str(user.id)


# ---------------------------------------------------------------------------
# Single-target
# ---------------------------------------------------------------------------


def activate_customer(*, user: User, actor: User, request=None) -> dict:
    if user.is_active:
        raise ValueError(f"{user.email} is already active.")
    user.is_active = True
    user.save(update_fields=["is_active"])
    log_admin_action(
        actor=actor, app_name="accounts", action="customer_activated",
        description=f"{actor.email} activated customer {user.email}",
        request=request,
    )
    return {"id": str(user.id), "name": _user_label(user)}


def deactivate_customer(*, user: User, actor: User, request=None) -> dict:
    if not user.is_active:
        raise ValueError(f"{user.email} is already inactive.")
    user.is_active = False
    user.save(update_fields=["is_active"])
    log_admin_action(
        actor=actor, app_name="accounts", action="customer_deactivated",
        description=f"{actor.email} deactivated customer {user.email}",
        request=request,
    )
    return {"id": str(user.id), "name": _user_label(user)}


# ---------------------------------------------------------------------------
# Bulk
# ---------------------------------------------------------------------------


def bulk_update_customer_status(*, ids: list[str], action: str, actor, request=None) -> dict:
    """Activate or deactivate a batch of customer accounts."""
    results: dict = {"success": [], "failed": [], "total": len(ids)}

    for item_id in ids:
        try:
            user = User.objects.get(id=item_id)
        except User.DoesNotExist:
            results["failed"].append({
                "id": item_id, "name": "Unknown", "reason": "Not found.",
            })
            continue

        if action == "activate":
            if user.is_active:
                results["failed"].append({
                    "id": str(user.id), "name": _user_label(user),
                    "reason": "Already active.",
                })
                continue
            user.is_active = True
            user.save(update_fields=["is_active"])
            log_admin_action(
                actor=actor, app_name="accounts", action="customer_activated",
                description=f"{actor.email} activated customer {user.email} (bulk)",
                request=request,
            )
            results["success"].append({"id": str(user.id), "name": _user_label(user)})

        elif action == "deactivate":
            if not user.is_active:
                results["failed"].append({
                    "id": str(user.id), "name": _user_label(user),
                    "reason": "Already inactive.",
                })
                continue
            user.is_active = False
            user.save(update_fields=["is_active"])
            log_admin_action(
                actor=actor, app_name="accounts", action="customer_deactivated",
                description=f"{actor.email} deactivated customer {user.email} (bulk)",
                request=request,
            )
            results["success"].append({"id": str(user.id), "name": _user_label(user)})

    return results


def bulk_grant_credits(
    *,
    ids: list[str],
    amount: Decimal,
    direction: str,
    reason: str,
    batch_key: str,
    actor,
    request=None,
) -> dict:
    """Grant credits to a batch of customers via the existing ``correct_wallet``.

    Each customer gets a deterministic idempotency key derived from the
    client-supplied *batch_key* and the user's id, so retrying the same
    bulk request is safe — users who already succeeded will no-op.
    """
    results: dict = {"success": [], "failed": [], "total": len(ids)}

    for item_id in ids:
        try:
            user = User.objects.get(id=item_id)
        except User.DoesNotExist:
            results["failed"].append({
                "id": item_id, "name": "Unknown", "reason": "Not found.",
            })
            continue

        try:
            idempotency_key = f"{batch_key}:{user.id}"
            correct_wallet(
                user=user,
                amount=amount,
                direction=direction,
                reason=reason,
                actor=actor,
                idempotency_key=idempotency_key,
            )
        except ValueError as e:
            results["failed"].append({
                "id": str(user.id), "name": _user_label(user),
                "reason": str(e),
            })
            continue

        log_admin_action(
            actor=actor, app_name="credits", action="bulk_grant_credits",
            description=(
                f"{actor.email} granted {amount} credits ({direction}) to "
                f"{user.email}, reason: {reason}"
            ),
            request=request,
        )
        results["success"].append({"id": str(user.id), "name": _user_label(user)})

    return results
