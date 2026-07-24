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

    model_prompt = (data.get("model_prompt") or prompt).strip()
    if not model_prompt:
        errors["model_prompt"] = "Message must include text in addition to model mentions."

    raw_capabilities = data.get("capabilities")
    if raw_capabilities is None:
        legacy_capability = (data.get("capability") or "").strip()
        capabilities = [legacy_capability] if legacy_capability else []
    elif not isinstance(raw_capabilities, list):
        capabilities = []
        errors["capabilities"] = "Must be a list of model capabilities."
    else:
        capabilities = [
            str(capability).strip()
            for capability in raw_capabilities
            if str(capability).strip()
        ]

    capabilities = list(dict.fromkeys(capabilities))
    if len(capabilities) > 3:
        errors["capabilities"] = "You can reference at most 3 models."

    if capabilities:
        from apps.providers.registry import get_provider

        unavailable = [
            capability
            for capability in capabilities
            if get_provider(capability) is None
        ]
        if unavailable:
            errors["capabilities"] = (
                f"Unknown or unavailable capabilities: {', '.join(unavailable)}"
            )

    if errors:
        raise ValidationError(errors)
    return {
        "prompt": prompt,
        "model_prompt": model_prompt,
        "capabilities": capabilities,
    }


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
