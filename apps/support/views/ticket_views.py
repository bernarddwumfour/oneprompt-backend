"""User-facing ticket views — create, list own, view own, reply."""

import json

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.support.schemas.support_schemas import serialize_message, serialize_ticket
from apps.support.selectors.support_selectors import (
    get_ticket_for_user,
    list_tickets_for_user,
)
from apps.support.services.support_service import add_message, create_ticket
from common.decorators import jwt_required
from common.responses import APIResponse


@csrf_exempt
@require_http_methods(["GET", "POST"])
@jwt_required
def user_tickets_view(request):
    """GET: list user's own tickets. POST: create ticket {subject, content}."""
    if request.method == "GET":
        tickets = list_tickets_for_user(request.user)
        return APIResponse.success(
            data={"tickets": [serialize_ticket(t) for t in tickets]}
        )

    # POST
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")
    subject = (body.get("subject") or "").strip()
    content = (body.get("content") or "").strip()
    if not subject:
        return APIResponse.bad_request("Subject is required.")
    if not content:
        return APIResponse.bad_request("Content is required.")
    ticket = create_ticket(user=request.user, subject=subject, content=content)
    return APIResponse.created(
        data={"ticket": serialize_ticket(ticket)},
        message="Ticket created.",
    )


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def user_ticket_detail_view(request, ticket_id):
    ticket = get_ticket_for_user(ticket_id, request.user)
    if ticket is None:
        return APIResponse.not_found("Ticket not found.")
    messages = ticket.messages.order_by("created_at")
    return APIResponse.success(
        data={
            "ticket": serialize_ticket(ticket),
            "messages": [serialize_message(m) for m in messages],
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
def user_ticket_reply_view(request, ticket_id):
    ticket = get_ticket_for_user(ticket_id, request.user)
    if ticket is None:
        return APIResponse.not_found("Ticket not found.")
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")
    content = (body.get("content") or "").strip()
    if not content:
        return APIResponse.bad_request("Content is required.")
    msg = add_message(ticket=ticket, author=request.user, content=content)
    return APIResponse.created(
        data={"message": serialize_message(msg)},
        message="Reply added.",
    )
