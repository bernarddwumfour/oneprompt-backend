"""Read-only support ticket queries."""

from typing import Optional

from django.db.models import Count

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


def list_all_tickets(*, status: str = ""):
    """Admin view — every ticket, optionally filtered by status."""
    qs = SupportTicket.objects.annotate(message_count=Count("messages")).order_by(
        "-updated_at"
    )
    if status:
        qs = qs.filter(status=status)
    return qs


def get_ticket(ticket_id: str) -> Optional[SupportTicket]:
    """Admin view — any ticket, unscoped."""
    return SupportTicket.objects.filter(id=ticket_id).first()
