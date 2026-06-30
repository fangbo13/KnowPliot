# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Admin governance URLs — V7.0, mounted at /api/v1/admin/."""

from django.urls import path

from .admin_views import (
    AdminRegistrationCodeListCreateView,
    BusinessLineListCreateView,
    OrganizationListView,
    admin_code_revoke,
)

urlpatterns = [
    path("registration-codes/", AdminRegistrationCodeListCreateView.as_view(),
         name="admin-code-list"),
    path("registration-codes/<uuid:pk>/revoke/", admin_code_revoke,
         name="admin-code-revoke"),
    path("organizations/", OrganizationListView.as_view(), name="admin-org-list"),
    path("business-lines/", BusinessLineListCreateView.as_view(), name="admin-bl-list"),
]
