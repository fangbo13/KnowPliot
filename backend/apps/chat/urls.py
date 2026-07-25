# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Chat URLs."""

from django.urls import path

from .views import (
    ChatSessionDetailView,
    ChatSessionListCreateView,
    ChatSessionMessagesView,
    branch_from_message,
    citation_source,
    conversation_share_collection,
    chat_turn_status,
    export_session,
    quick_actions,
    revoke_conversation_share,
    send_message,
    submit_feedback,
    view_conversation_share,
)
from .v3_views import cancel_chat_turn_v3, chat_turn_events_dispatch

urlpatterns = [
    path("sessions/", ChatSessionListCreateView.as_view(), name="chat-session-list"),
    path("sessions/<uuid:pk>/", ChatSessionDetailView.as_view(), name="chat-session-detail"),
    path("sessions/<uuid:session_id>/messages/", ChatSessionMessagesView.as_view(), name="chat-session-messages"),
    path("messages/<uuid:message_id>/branch/", branch_from_message, name="chat-message-branch"),
    path("sessions/<uuid:session_id>/shares/", conversation_share_collection, name="chat-share-collection"),
    path("shares/<uuid:share_id>/", revoke_conversation_share, name="chat-share-revoke"),
    path("shares/<uuid:token>/view/", view_conversation_share, name="chat-share-view"),
    path("citations/<uuid:citation_id>/source/", citation_source, name="chat-citation-source"),
    path("sessions/<uuid:session_id>/send/", send_message, name="chat-send-message"),
    path("messages/<uuid:message_id>/regenerate/", send_message, name="chat-message-regenerate"),
    path("turns/<uuid:turn_id>/", chat_turn_status, name="chat-turn-status"),
    path(
        "turns/<uuid:turn_id>/events/",
        chat_turn_events_dispatch,
        name="chat-turn-events",
    ),
    path(
        "turns/<uuid:turn_id>/cancel/",
        cancel_chat_turn_v3,
        name="chat-turn-cancel",
    ),
    path("sessions/<uuid:session_id>/export/", export_session, name="chat-session-export"),
    path("messages/<uuid:message_id>/feedback/", submit_feedback, name="chat-feedback"),
    path("quick-actions/", quick_actions, name="chat-quick-actions"),
]
