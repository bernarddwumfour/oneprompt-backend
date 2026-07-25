from django.urls import path

from apps.support.views.ticket_views import (
    user_ticket_detail_view,
    user_ticket_reply_view,
    user_tickets_view,
)

urlpatterns = [
    path("tickets", user_tickets_view, name="support-tickets"),
    path("tickets/<uuid:ticket_id>", user_ticket_detail_view, name="support-ticket-detail"),
    path("tickets/<uuid:ticket_id>/messages", user_ticket_reply_view, name="support-ticket-reply"),
]
