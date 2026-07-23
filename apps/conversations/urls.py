from django.urls import path

from apps.conversations.views.conversation_views import (
    conversation_detail_view,
    conversations_view,
)
from apps.conversations.views.message_views import send_message_view

urlpatterns = [
    path("", conversations_view, name="conversations"),
    path("<uuid:conversation_id>", conversation_detail_view, name="conversation-detail"),
    path("<uuid:conversation_id>/messages", send_message_view, name="send-message"),
]
