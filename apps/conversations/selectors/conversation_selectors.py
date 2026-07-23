"""
Read-only conversation queries.
"""

from apps.conversations.models import Conversation


def get_conversation_for_user(conversation_id: str, user):
    """Return the conversation if it belongs to *user*, else None."""
    try:
        return Conversation.objects.filter(user=user).get(id=conversation_id)
    except Conversation.DoesNotExist:
        return None


def list_conversations_for_user(user):
    """Return all conversations for *user*, newest first."""
    return Conversation.objects.filter(user=user).order_by("-updated_at")


def list_messages_for_conversation(conversation: Conversation):
    """Return messages for *conversation*, oldest first."""
    return conversation.messages.prefetch_related("invocations").order_by("created_at")
