"""Support serialization."""


def serialize_ticket(ticket) -> dict:
    return {
        "id": str(ticket.id),
        "user_email": ticket.user.email,
        "subject": ticket.subject,
        "status": ticket.status,
        "message_count": getattr(ticket, "message_count", ticket.messages.count()),
        "created_at": ticket.created_at.isoformat(),
        "updated_at": ticket.updated_at.isoformat(),
    }


def serialize_message(message) -> dict:
    return {
        "id": str(message.id),
        "author_email": message.author.email,
        "author_is_admin": message.author.is_staff,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }
