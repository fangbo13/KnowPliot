"""Custom permissions."""

from rest_framework.permissions import BasePermission


class IsHROrAdmin(BasePermission):
    """Permission class for HR admin and superuser access."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            getattr(request.user, "is_hr_admin", False) or request.user.is_superuser
        )


class IsOwnerOrReadOnly(BasePermission):
    """Object-level permission to only allow owners to edit."""

    def has_object_permission(self, request, view, obj):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return getattr(obj, "user", None) == request.user
