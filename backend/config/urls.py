# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Root URL Configuration — V4.0 RBAC dual-track + V4.1 KB-V4.1-007 media auth."""

from django.contrib import admin
from django.conf import settings
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("apps.users.urls")),
    path("api/v1/chat/", include("apps.chat.urls")),
    path("api/v1/documents/", include("apps.knowledge.urls")),
    path("api/v1/audit/", include("apps.audit.urls")),
    path("api/v1/rbac/", include("apps.rbac.urls")),
    path("api/v1/spaces/", include("apps.spaces.urls")),  # V6.0: multi-space platform
    path("api/v1/notifications/", include("apps.notifications.urls")),  # V7.0: notifications
    path("api/v1/admin/", include("apps.spaces.admin_urls")),  # V7.0: admin governance
    path("api/v1/templates/", include("apps.scenario_templates.urls")),  # V7.1: Scenario templates center
    # V6.0: Web crawler feature removed. The crawler API is no longer exposed.
    # The apps.crawler Django app and its tables are retained inert for historical
    # data/migration safety, but no routes, tasks, or UI reference it.
]

# V4.1 KB-V4.1-007: Removed DEBUG-only media serving.
# Media files are now served via AuthenticatedMediaMiddleware which
# requires JWT authentication for /media/ URLs regardless of DEBUG mode.
# This prevents unauthenticated access to uploaded documents.
