"""Admin conversation views — read-only list + detail."""

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.conversations.models import Conversation
from apps.conversations.schemas.conversation_schemas import (
    serialize_conversation,
    serialize_message,
)
from apps.conversations.selectors.conversation_selectors import (
    list_messages_for_conversation,
)
from apps.operations.selectors.operations_selectors import list_conversations
from common.decorators import jwt_required, role_required
from common.responses import APIResponse
from common.utils import parse_date_range_param, parse_ordering, parse_pagination


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def conversation_list_view(request):
    search = request.GET.get("search", request.GET.get("user_email", ""))
    try:
        page, limit = parse_pagination(request)
        ordering = parse_ordering(request, {
            "updated_at": "updated_at", "created_at": "created_at",
            "title": "title", "user_email": "user__email",
            "message_count": "message_count",
        }, "-updated_at")
    except ValueError as e:
        return APIResponse.bad_request(str(e))
    updated_from, updated_to = parse_date_range_param(request, "updated_at")
    result = list_conversations(
        search=search, page=page, limit=limit, ordering=ordering,
        updated_from=updated_from, updated_to=updated_to,
    )
    return APIResponse.success(data=result)


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def conversation_detail_view(request, conversation_id):
    try:
        conversation = Conversation.objects.select_related("user").get(id=conversation_id)
    except Conversation.DoesNotExist:
        return APIResponse.not_found("Conversation not found.")

    messages = list_messages_for_conversation(conversation)
    return APIResponse.success(
        data={
            "conversation": {
                **serialize_conversation(conversation),
                "user_email": conversation.user.email,
                "user_full_name": conversation.user.full_name,
            },
            "messages": [serialize_message(m) for m in messages],
        }
    )
