"""RBAC URL routes — V4.0 dual-track permission system."""

from django.urls import path
from .views import (
    RoleListView,
    PermissionListView,
    RolePermissionsView,
    UserRoleListView,
    UserRoleDetailView,
    AdminUserListView,
    AdminUserCreateView,
    AdminUserUpdateView,
    admin_user_deactivate,
)

urlpatterns = [
    # ── RBAC Management ──
    path("roles/", RoleListView.as_view(), name="rbac-roles"),
    path("permissions/", PermissionListView.as_view(), name="rbac-permissions"),
    path("roles/<uuid:role_id>/permissions/", RolePermissionsView.as_view(), name="rbac-role-permissions"),
    path("user-roles/", UserRoleListView.as_view(), name="rbac-user-roles"),
    path("user-roles/<uuid:pk>/", UserRoleDetailView.as_view(), name="rbac-user-role-detail"),

    # ── Admin User Management ──
    path("users/", AdminUserListView.as_view(), name="admin-users-list"),
    path("users/create/", AdminUserCreateView.as_view(), name="admin-users-create"),
    path("users/<uuid:pk>/", AdminUserUpdateView.as_view(), name="admin-users-update"),
    path("users/<uuid:pk>/deactivate/", admin_user_deactivate, name="admin-users-deactivate"),
]
