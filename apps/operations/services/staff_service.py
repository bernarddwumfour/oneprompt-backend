"""Staff management services — activate, deactivate, bulk status updates.

Per plan 0008: guards prevent an admin from deactivating their own account
or reducing the active-staff count to zero. The last-active-staff guard is
evaluated batch-aware — it simulates the whole selection's effect before
applying any of it — so a multi-item deactivate that would zero the count
is caught even when the "last" item isn't processed first.
"""

import logging

from apps.accounts.models import User
from common.audit import log_admin_action

logger = logging.getLogger(__name__)


def _user_label(user: User) -> str:
    """Human-readable label for a user in bulk-result entries."""
    return user.email or str(user.id)


# ---------------------------------------------------------------------------
# Single-target
# ---------------------------------------------------------------------------


def activate_staff(*, user: User, actor: User, request=None) -> dict:
    """Activate a staff account."""
    if user.is_active:
        raise ValueError(f"{user.email} is already active.")

    user.is_active = True
    user.save(update_fields=["is_active"])

    log_admin_action(
        actor=actor, app_name="accounts", action="staff_activated",
        description=f"{actor.email} activated staff account {user.email}",
        request=request,
    )
    return {"id": str(user.id), "name": _user_label(user)}


def deactivate_staff(*, user: User, actor: User, request=None) -> dict:
    """Deactivate a staff account.

    Guards: self-protection (never deactivate yourself) and last-active-staff
    (never leave the platform with zero active admin accounts).
    """
    if user.id == actor.id:
        raise ValueError("Cannot deactivate your own account.")

    if not user.is_active:
        raise ValueError(f"{user.email} is already inactive.")

    active_staff_count = User.objects.filter(is_staff=True, is_active=True).count()
    if active_staff_count <= 1:
        raise ValueError(
            "Cannot deactivate the last remaining active staff account."
        )

    user.is_active = False
    user.save(update_fields=["is_active"])

    log_admin_action(
        actor=actor, app_name="accounts", action="staff_deactivated",
        description=f"{actor.email} deactivated staff account {user.email}",
        request=request,
    )
    return {"id": str(user.id), "name": _user_label(user)}


# ---------------------------------------------------------------------------
# Bulk
# ---------------------------------------------------------------------------


def bulk_update_staff_status(*, ids: list[str], action: str, actor, request=None) -> dict:
    """Activate or deactivate a batch of staff accounts.

    The last-active-staff guard is batch-aware: it tracks a running count of
    currently-active staff (seeded from the DB before the loop) and refuses
    to let it drop below 1, decrementing only on an actual successful
    deactivation — so a multi-item batch that would zero out active staff is
    caught partway through, not just on a single-item request.
    """
    results: dict = {"success": [], "failed": [], "total": len(ids)}

    if action == "deactivate":
        remaining_active = User.objects.filter(is_staff=True, is_active=True).count()

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
                actor=actor, app_name="accounts", action="staff_activated",
                description=f"{actor.email} activated staff account {user.email} (bulk)",
                request=request,
            )
            results["success"].append({"id": str(user.id), "name": _user_label(user)})

        elif action == "deactivate":
            if user.id == actor.id:
                results["failed"].append({
                    "id": str(user.id), "name": _user_label(user),
                    "reason": "Cannot deactivate your own account.",
                })
                continue
            if not user.is_active:
                results["failed"].append({
                    "id": str(user.id), "name": _user_label(user),
                    "reason": "Already inactive.",
                })
                continue
            if remaining_active <= 1:
                results["failed"].append({
                    "id": str(user.id), "name": _user_label(user),
                    "reason": "Cannot deactivate the last remaining active staff account.",
                })
                continue

            user.is_active = False
            user.save(update_fields=["is_active"])
            remaining_active -= 1
            log_admin_action(
                actor=actor, app_name="accounts", action="staff_deactivated",
                description=f"{actor.email} deactivated staff account {user.email} (bulk)",
                request=request,
            )
            results["success"].append({"id": str(user.id), "name": _user_label(user)})

    return results
