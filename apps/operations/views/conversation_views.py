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
from common.utils import parse_pagination


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def conversation_list_view(request):
    user_email = request.GET.get("user_email", "")
    try:
        page, limit = parse_pagination(request)
    except ValueError as e:
        return APIResponse.bad_request(str(e))
    result = list_conversations(user_email=user_email, page=page, limit=limit)
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
