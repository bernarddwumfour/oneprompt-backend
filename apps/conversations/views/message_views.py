"""Message views — SSE streaming and cancellation."""

import json
import logging

from django.core.cache import cache
from django.http import StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.conversations.models import ModelInvocation
from apps.conversations.schemas.conversation_schemas import (
    ValidationError,
    validate_send_message,
)
from apps.conversations.selectors.conversation_selectors import (
    get_conversation_for_user,
)
from apps.conversations.services.chat_service import send_message
from common.decorators import jwt_required
from common.responses import APIResponse

logger = logging.getLogger(__name__)


def _sse_frame(event: str, data: dict) -> str:
    """Format a single SSE frame."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
def send_message_view(request, conversation_id):
    """POST /conversations/{id}/messages — returns text/event-stream."""
    conversation = get_conversation_for_user(conversation_id, request.user)
    if conversation is None:
        return APIResponse.not_found("Conversation not found.")

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")

    try:
        cleaned = validate_send_message(body)
    except ValidationError as e:
        return APIResponse.validation_error(e.errors)

    try:
        gen = send_message(
            conversation=conversation,
            user=request.user,
            prompt=cleaned["prompt"],
            capability=cleaned.get("capability", "fast"),
        )
    except ValueError as e:
        return APIResponse.bad_request(str(e))

    def event_stream():
        for event_type, data in gen:
            yield _sse_frame(event_type, data)

    response = StreamingHttpResponse(
        event_stream(),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
def cancel_invocation_view(request, invocation_id):
    """POST /invocations/{id}/cancel — sets the cancellation flag."""
    try:
        invocation = ModelInvocation.objects.get(id=invocation_id)
    except ModelInvocation.DoesNotExist:
        return APIResponse.not_found("Invocation not found.")

    if invocation.conversation.user != request.user:
        return APIResponse.forbidden("Access denied.")

    cache.set(f"cancel:{invocation_id}", True, timeout=60)
    return APIResponse.success(message="Cancellation requested.")
