"""Support service — create tickets, add messages, change status."""

from apps.support.models import TICKET_STATUS_CHOICES, SupportTicket, TicketMessage


def create_ticket(*, user, subject: str, content: str) -> SupportTicket:
    ticket = SupportTicket.objects.create(user=user, subject=subject)
    TicketMessage.objects.create(ticket=ticket, author=user, content=content)
    return ticket


def add_message(*, ticket: SupportTicket, author, content: str) -> TicketMessage:
    msg = TicketMessage.objects.create(
        ticket=ticket, author=author, content=content
    )
    ticket.save(update_fields=["updated_at"])
    return msg


def update_ticket_status(
    *, ticket: SupportTicket, status: str, actor
) -> SupportTicket:
    valid = dict(TICKET_STATUS_CHOICES)
    if status not in valid:
        raise ValueError(f"Invalid status: {status}")
    ticket.status = status
    ticket.save(update_fields=["status", "updated_at"])
    return ticket
