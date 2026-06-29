"""RBAC views — V4.0 dual-track permission system API endpoints.

V4.2 SYS-V4.2-008: Added throttle_classes to admin_user_deactivate.
V4.2 SYS-V4.2-022: Added self-deactivation prevention.

10 endpoints:
  - /api/v1/rbac/roles/               GET    HasRole('admin')
  - /api/v1/rbac/permissions/          GET    HasPermission('user.assign_role')
  - /api/v1/rbac/roles/<id>/permissions/  GET    HasPermission('user.assign_role')
  - /api/v1/rbac/user-roles/           GET    HasPermission('user.assign_role')
  - /api/v1/rbac/user-roles/           POST   HasPermission('user.assign_role')
  - /api/v1/rbac/user-roles/<id>/      DELETE HasPermission('user.assign_role')
  - /api/v1/users/                     GET    HasPermission('user.read')
  - /api/v1/users/                     POST   HasPermission('user.create')
  - /api/v1/users/<id>/                PATCH  HasPermission('user.update')
  - /api/v1/users/<id>/deactivate/     POST   HasPermission('user.deactivate')
"""

from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.core.permissions import HasPermission, HasRole
from apps.audit.views import create_audit_log
from .models import Role, Permission, RolePermission, UserRole
from .serializers import (
    RoleSerializer,
    PermissionSerializer,
    RolePermissionSerializer,
    UserRoleSerializer,
    UserRoleAssignSerializer,
)
from apps.users.models import User
from apps.users.serializers import UserManageSerializer


# V4.2 SYS-V4.2-008: Dedicated throttle for admin_user_deactivate
# Previous: @api_view bypassed DEFAULT_THROTTLE_CLASSES — no rate limit at all.
# Now: 5/min per user — prevents rapid bulk deactivation attacks.
class DeactivateUserRateThrottle(UserRateThrottle):
    rate = "5/minute"


# V4.2 SYS-V4.2-023: Dedicated throttle for role assignment endpoints
# Previous: inherited global 30/min — too lenient for privilege assignment.
# Now: 5/min per user — prevents rapid bulk role escalation attacks.
class RoleAssignmentRateThrottle(UserRateThrottle):
    rate = "5/minute"


# ── RBAC Management Endpoints ──────────────────────────────────────────


class RoleListView(generics.ListAPIView):
    """List all RBAC roles — Admin only."""

    serializer_class = RoleSerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasRole("admin")]

    def get_queryset(self):
        return Role.objects.all()


class PermissionListView(generics.ListAPIView):
    """List all 35 RBAC permission codenames — requires user.assign_role."""

    serializer_class = PermissionSerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasPermission("user.assign_role")]

    def get_queryset(self):
        qs = Permission.objects.all()
        resource = self.request.query_params.get("resource")
        if resource:
            qs = qs.filter(resource=resource)
        return qs


class RolePermissionsView(generics.ListAPIView):
    """List permissions for a specific role — requires user.assign_role."""

    serializer_class = RolePermissionSerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasPermission("user.assign_role")]

    def get_queryset(self):
        return RolePermission.objects.filter(role_id=self.kwargs["role_id"])


class UserRoleListView(generics.ListCreateAPIView):
    """List and create user-role assignments — requires user.assign_role.

    V4.2 SYS-V4.2-023: Added RoleAssignmentRateThrottle (5/min) — previously
    inherited global 30/min which is too lenient for privilege assignment.
    """

    # V4.2 SYS-V4.2-023: Stricter throttle for role assignment operations
    throttle_classes = [RoleAssignmentRateThrottle]

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasPermission("user.assign_role")]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return UserRoleAssignSerializer
        return UserRoleSerializer

    def get_queryset(self):
        qs = UserRole.objects.all()
        user_id = self.request.query_params.get("user")
        if user_id:
            qs = qs.filter(user_id=user_id)
        role_name = self.request.query_params.get("role")
        if role_name:
            qs = qs.filter(role__name=role_name)
        return qs.select_related("user", "role", "assigned_by")

    def create(self, request, *args, **kwargs):
        """Assign role to user — auto-fills assigned_by.

        V4.2 SYS-V4.2-021: If user already has an inactive UserRole for this
        role, re-activate it instead of creating a new one (which would cause
        IntegrityError due to unique_together constraint).
        """
        serializer = UserRoleAssignSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        user = User.objects.get(id=serializer.validated_data["user_id"])
        role = Role.objects.get(name=serializer.validated_data["role_name"])

        # V4.2 SYS-V4.2-021: Re-activate existing inactive UserRole instead of create()
        # Previous: UserRole.objects.create() with unique_together=("user","role") would
        # fail with IntegrityError if an inactive record exists. Now: update the existing
        # inactive record to is_active=True, avoiding the unique constraint violation.
        existing = UserRole.objects.filter(user=user, role=role).first()
        if existing:
            if existing.is_active:
                return Response(
                    {"detail": f"User already has active role '{role.name}'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Re-activate existing inactive record
            existing.is_active = True
            existing.assigned_by = request.user
            existing.save(update_fields=["is_active", "assigned_by", "updated_at"])
            user_role = existing
        else:
            user_role = UserRole.objects.create(
                user=user,
                role=role,
                assigned_by=request.user,
            )

        # Audit log
        create_audit_log(
            user=request.user,
            action="role_assign",
            target_type="UserRole",
            target_id=str(user_role.id),
            details={
                "assigned_user": user.email,
                "assigned_role": role.name,
            },
            role_used="admin",
            request=request,
        )

        return Response(
            UserRoleSerializer(user_role).data,
            status=status.HTTP_201_CREATED,
        )


class UserRoleDetailView(generics.DestroyAPIView):
    """Revoke a user-role assignment — requires user.assign_role.

    V4.2 SYS-V4.2-023: Added RoleAssignmentRateThrottle (5/min).
    """

    # V4.2 SYS-V4.2-023: Stricter throttle for role revocation operations
    throttle_classes = [RoleAssignmentRateThrottle]

    serializer_class = UserRoleSerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasPermission("user.assign_role")]

    def get_queryset(self):
        return UserRole.objects.all()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active"])

        # Audit log
        create_audit_log(
            user=request.user,
            action="role_revoke",
            target_type="UserRole",
            target_id=str(instance.id),
            details={
                "revoked_user": instance.user.email,
                "revoked_role": instance.role.name,
            },
            role_used="admin",
            request=request,
        )

        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Admin User Management Endpoints ────────────────────────────────────


class AdminUserListView(generics.ListAPIView):
    """List all users — requires user.read permission (Admin only)."""

    serializer_class = UserManageSerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasPermission("user.read")]

    def get_queryset(self):
        return User.objects.all().order_by("email")


class AdminUserCreateView(generics.CreateAPIView):
    """Create a new user — requires user.create permission (Admin only)."""

    serializer_class = UserManageSerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasPermission("user.create")]

    def perform_create(self, serializer):
        user = serializer.save()
        create_audit_log(
            user=self.request.user,
            action="user_create",
            target_type="User",
            target_id=str(user.id),
            details={"email": user.email, "username": user.username},
            role_used="admin",
            request=self.request,
        )


class AdminUserUpdateView(generics.UpdateAPIView):
    """Update user profile — requires user.update permission (Admin only)."""

    serializer_class = UserManageSerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasPermission("user.update")]

    def get_queryset(self):
        return User.objects.all()


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
@throttle_classes([DeactivateUserRateThrottle])  # V4.2 SYS-V4.2-008: 5/min per user
def admin_user_deactivate(request, pk):
    """Deactivate a user account — requires user.deactivate (Admin only).

    V4.2 SYS-V4.2-008: Added throttle_classes (5/min) — previously bypassed
    DEFAULT_THROTTLE_CLASSES via @api_view decorator.
    V4.2 SYS-V4.2-022: Added self-deactivation prevention — admin cannot
    deactivate their own account (prevents accidental lockout with no recovery).
    """

    # Permission check
    if not request.user.has_permission("user.deactivate"):
        return Response(
            {"detail": "You do not have permission to deactivate users."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        user = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return Response(
            {"detail": "User not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # V4.2 SYS-V4.2-022: Prevent self-deactivation — no recovery mechanism exists
    if user.id == request.user.id:
        return Response(
            {"detail": "Cannot deactivate your own account."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if user.is_superuser:
        return Response(
            {"detail": "Cannot deactivate superuser."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user.is_active = False
    user.save(update_fields=["is_active"])

    # Also deactivate all user roles
    UserRole.objects.filter(user=user).update(is_active=False)

    create_audit_log(
        user=request.user,
        action="user_deactivate",
        target_type="User",
        target_id=str(user.id),
        details={"deactivated_user": user.email},
        role_used="admin",
        request=request,
    )

    return Response({"detail": f"User {user.email} deactivated successfully."})
