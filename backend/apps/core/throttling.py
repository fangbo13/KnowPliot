"""Separate navigation-read and security-sensitive mutation rate contracts."""

from rest_framework.permissions import SAFE_METHODS
from rest_framework.throttling import UserRateThrottle


class _AuthenticatedMethodThrottle(UserRateThrottle):
    apply_to_safe_methods = True

    def allow_request(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return True
        is_safe = request.method in SAFE_METHODS
        if is_safe != self.apply_to_safe_methods:
            return True
        return super().allow_request(request, view)


class AuthenticatedReadSustainedThrottle(_AuthenticatedMethodThrottle):
    """Internal-beta sustained navigation allowance: 240 requests/min/user."""

    scope = "navigation_read_sustained"
    rate = "240/minute"


class AuthenticatedReadBurstThrottle(_AuthenticatedMethodThrottle):
    """Internal-beta burst allowance: 60 requests per ten seconds per user."""

    scope = "navigation_read_burst"
    rate = "60/10seconds"

    def parse_rate(self, _rate):
        return 60, 10


class AuthenticatedMutationThrottle(_AuthenticatedMethodThrottle):
    """Default mutation guard; sensitive actions keep their stricter classes."""

    apply_to_safe_methods = False
    scope = "user_mutation"
    rate = "30/minute"
