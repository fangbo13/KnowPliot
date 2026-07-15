# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Chat URLs."""

from django.urls import path

from .views import (
    ChatSessionDetailView,
    ChatSessionListCreateView,
    ChatSessionMessagesView,
    chat_turn_status,
    export_session,
    quick_actions,
    send_message,
    submit_feedback,
)

urlpatterns = [
    path("sessions/", ChatSessionListCreateView.as_view(), name="chat-session-list"),
    path("sessions/<uuid:pk>/", ChatSessionDetailView.as_view(), name="chat-session-detail"),
    path("sessions/<uuid:session_id>/messages/", ChatSessionMessagesView.as_view(), name="chat-session-messages"),
    path("sessions/<uuid:session_id>/send/", send_message, name="chat-send-message"),
    path("turns/<uuid:turn_id>/", chat_turn_status, name="chat-turn-status"),
    path("sessions/<uuid:session_id>/export/", export_session, name="chat-session-export"),
    path("messages/<uuid:message_id>/feedback/", submit_feedback, name="chat-feedback"),
    path("quick-actions/", quick_actions, name="chat-quick-actions"),
]
