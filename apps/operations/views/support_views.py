"""Admin support views — list all tickets, detail, reply, status change."""

import json

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.support.schemas.support_schemas import serialize_message, serialize_ticket
from apps.support.selectors.support_selectors import get_ticket, list_all_tickets
from apps.support.services.support_service import add_message, update_ticket_status
from common.audit import log_admin_action
from common.decorators import jwt_required, role_required
from common.responses import APIResponse
from common.utils import parse_pagination


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def admin_ticket_list_view(request):
    status = request.GET.get("status", "")
    qs = list_all_tickets(status=status)
    try:
        page, limit = parse_pagination(request)
    except ValueError as e:
        return APIResponse.bad_request(str(e))
    total = qs.count()
    offset = (page - 1) * limit
    tickets = qs[offset : offset + limit]
    return APIResponse.success(
        data={
            "tickets": [serialize_ticket(t) for t in tickets],
            "total": total, "page": page, "limit": limit,
        }
    )


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def admin_ticket_detail_view(request, ticket_id):
    ticket = get_ticket(ticket_id)
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
@role_required("admin")
def admin_ticket_reply_view(request, ticket_id):
    ticket = get_ticket(ticket_id)
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


@csrf_exempt
@require_http_methods(["PATCH"])
@jwt_required
@role_required("admin")
def admin_ticket_status_view(request, ticket_id):
    ticket = get_ticket(ticket_id)
    if ticket is None:
        return APIResponse.not_found("Ticket not found.")
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON.")
    status = (body.get("status") or "").strip()
    if not status:
        return APIResponse.bad_request("Status is required.")
    try:
        ticket = update_ticket_status(ticket=ticket, status=status, actor=request.user)
    except ValueError as e:
        return APIResponse.bad_request(str(e))
    log_admin_action(
        actor=request.user, app_name="support", action="ticket_status_change",
        description=f"Changed ticket {ticket.id} status to {status}",
        request=request,
    )
    return APIResponse.success(
        data={"ticket": serialize_ticket(ticket)},
        message="Ticket status updated.",
    )
