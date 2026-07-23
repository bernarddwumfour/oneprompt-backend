"""Conversation CRUD views."""

import json
import logging

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.conversations.models import Conversation
from apps.conversations.schemas.conversation_schemas import (
    serialize_conversation,
    serialize_message,
    validate_create_conversation,
)
from apps.conversations.selectors.conversation_selectors import (
    get_conversation_for_user,
    list_conversations_for_user,
    list_messages_for_conversation,
)
from common.decorators import jwt_required
from common.responses import APIResponse

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@jwt_required
def conversations_view(request):
    """GET /conversations — list; POST /conversations — create."""
    if request.method == "GET":
        conversations = list_conversations_for_user(request.user)
        return APIResponse.success(
            data={
                "conversations": [serialize_conversation(c) for c in conversations]
            }
        )

    # POST
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")

    cleaned = validate_create_conversation(body)
    conversation = Conversation.objects.create(
        user=request.user,
        title=cleaned["title"],
    )
    logger.info("Conversation created: %s by %s", conversation.id, request.user.email)
    return APIResponse.created(
        data={"conversation": serialize_conversation(conversation)},
        message="Conversation created.",
    )


@csrf_exempt
@require_http_methods(["GET", "DELETE"])
@jwt_required
def conversation_detail_view(request, conversation_id):
    """GET /conversations/{id} — detail; DELETE /conversations/{id} — delete."""
    conversation = get_conversation_for_user(conversation_id, request.user)
    if conversation is None:
        return APIResponse.not_found("Conversation not found.")

    if request.method == "DELETE":
        conversation.delete()
        return APIResponse.success(message="Conversation deleted.")

    messages = list_messages_for_conversation(conversation)
    return APIResponse.success(
        data={
            "conversation": serialize_conversation(conversation),
            "messages": [serialize_message(m) for m in messages],
        }
    )
