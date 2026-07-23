"""Conversation serialization."""

from apps.conversations.models import Conversation, Message, ModelInvocation


class ValidationError(ValueError):
    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__("Validation failed")


def validate_create_conversation(data: dict) -> dict:
    title = (data.get("title") or "").strip()
    if not title:
        title = "New conversation"
    return {"title": title}


def validate_send_message(data: dict) -> dict:
    errors = {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        errors["prompt"] = "Prompt is required."

    capability = (data.get("capability") or "").strip()
    if capability:
        from apps.providers.registry import get_provider

        if get_provider(capability) is None:
            errors["capability"] = f"Unknown or unavailable capability: {capability}"

    if errors:
        raise ValidationError(errors)
    return {"prompt": prompt, "capability": capability or None}


def serialize_conversation(conversation: Conversation) -> dict:
    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    }


def serialize_message(message: Message) -> dict:
    invocation = next(iter(message.invocations.all()), None)
    return {
        "id": str(message.id),
        "role": message.role,
        "content": message.content,
        "capability": invocation.capability if invocation else None,
        "created_at": message.created_at.isoformat(),
    }


def serialize_invocation(invocation: ModelInvocation) -> dict:
    return {
        "id": str(invocation.id),
        "capability": invocation.capability,
        "status": invocation.status,
        "input_tokens": invocation.input_tokens,
        "output_tokens": invocation.output_tokens,
        "credits_estimated": str(invocation.credits_estimated) if invocation.credits_estimated else None,
        "credits_charged": str(invocation.credits_charged) if invocation.credits_charged else None,
        "error_message": invocation.error_message,
        "created_at": invocation.created_at.isoformat(),
        "completed_at": invocation.completed_at.isoformat() if invocation.completed_at else None,
    }
