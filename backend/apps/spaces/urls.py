# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Space platform URLs — V6.0 (SPEC.MD §6.1)."""

from django.urls import path

from .views import (
    InviteCodeListCreateView,
    SpaceDetailView,
    SpaceListCreateView,
    SpaceMembersView,
    invite_revoke,
    space_archive,
    space_restore,
    space_transfer,
    space_access_request,
    space_clone,
    space_transfer_owner,
    discoverable_spaces,
    space_join,
    space_member_detail,
    space_switch,
)

urlpatterns = [
    path("", SpaceListCreateView.as_view(), name="space-list"),
    path("join/", space_join, name="space-join"),
    path("discoverable/", discoverable_spaces, name="space-discoverable"),
    path("<uuid:pk>/", SpaceDetailView.as_view(), name="space-detail"),
    path("<uuid:pk>/archive/", space_archive, name="space-archive"),
    path("<uuid:pk>/restore/", space_restore, name="space-restore"),
    path("<uuid:pk>/transfer/", space_transfer, name="space-transfer"),
    path("<uuid:pk>/clone/", space_clone, name="space-clone"),
    path("<uuid:pk>/transfer-owner/", space_transfer_owner, name="space-transfer-owner"),
    path("<uuid:pk>/access-requests/", space_access_request, name="space-access-request"),
    path("<uuid:pk>/switch/", space_switch, name="space-switch"),
    path("<uuid:pk>/members/", SpaceMembersView.as_view(), name="space-members"),
    path("<uuid:pk>/members/<uuid:user_id>/", space_member_detail, name="space-member-detail"),
    path("<uuid:pk>/invites/", InviteCodeListCreateView.as_view(), name="space-invite-list"),
    path("<uuid:pk>/invites/<uuid:invite_id>/revoke/", invite_revoke, name="space-invite-revoke"),
]
