"""Read-only support ticket queries."""

from typing import Optional

from django.db.models import Count, Q

from apps.support.models import SupportTicket


def list_tickets_for_user(user):
    """A user's own tickets, newest-updated first."""
    return (
        SupportTicket.objects.filter(user=user)
        .annotate(message_count=Count("messages"))
        .order_by("-updated_at")
    )


def get_ticket_for_user(ticket_id: str, user) -> Optional[SupportTicket]:
    """A single ticket, scoped to its owner — never trust a bare id lookup."""
    return SupportTicket.objects.filter(user=user, id=ticket_id).first()


def list_all_tickets(
    *, search: str = "", status: str = "", ordering: str = "-updated_at",
    updated_from=None, updated_to=None,
):
    """Admin view — every ticket, optionally filtered by status."""
    qs = SupportTicket.objects.select_related("user").annotate(
        message_count=Count("messages")
    )
    if search:
        qs = qs.filter(
            Q(subject__icontains=search) | Q(user__email__icontains=search)
        )
    if status:
        qs = qs.filter(status=status)
    if updated_from:
        qs = qs.filter(updated_at__gte=updated_from)
    if updated_to:
        qs = qs.filter(updated_at__lte=updated_to)
    return qs.order_by(ordering, "id")


def get_ticket(ticket_id: str) -> Optional[SupportTicket]:
    """Admin view — any ticket, unscoped."""
    return SupportTicket.objects.filter(id=ticket_id).first()
