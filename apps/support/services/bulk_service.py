"""Bulk support-ticket operations — close, resolve.

Per plan 0008: loops the existing ``update_ticket_status`` per ticket,
catching ``SupportTicket.DoesNotExist`` and any transition-validation errors
into a per-item ``failed`` entry so one bad ID never sinks the batch.
"""

import logging

from apps.support.models import SupportTicket
from apps.support.services.support_service import update_ticket_status

logger = logging.getLogger(__name__)


def bulk_update_ticket_status(*, ids: list[str], status: str, actor, request=None) -> dict:
    """Close or resolve a batch of support tickets."""
    results: dict = {"success": [], "failed": [], "total": len(ids)}

    for ticket_id in ids:
        try:
            ticket = SupportTicket.objects.get(id=ticket_id)
        except SupportTicket.DoesNotExist:
            results["failed"].append({
                "id": ticket_id, "name": "Unknown", "reason": "Not found.",
            })
            continue

        try:
            update_ticket_status(ticket=ticket, status=status, actor=actor)
        except ValueError as e:
            results["failed"].append({
                "id": str(ticket.id), "name": ticket.subject,
                "reason": str(e),
            })
            continue

        results["success"].append({
            "id": str(ticket.id), "name": ticket.subject,
        })

    return results
