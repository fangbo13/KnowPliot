"""Core middleware — V4.1 SYS security hardening + KB-V4.1-007 media auth.

SafeErrorResponseMiddleware: Intercepts ALL 500 errors (not just DRF views)
and returns generic JSON, preventing stack trace / SQL / settings leakage
even when DEBUG=True.

AuthenticatedMediaMiddleware (KB-V4.1-007): Requires JWT authentication for
/media/ URLs, preventing unauthenticated access to uploaded documents when
DEBUG=True (Django's static() serves media publicly without auth).

RbacCacheMiddleware (V4.2 SYS-V4.2-006): Populates request._rbac_cache on
each authenticated request so has_permission() + has_role() share the same
data and avoid 3 separate DB queries per request (N+1 problem).
"""

import logging

from django.http import JsonResponse, HttpResponseForbidden

logger = logging.getLogger(__name__)


class SafeErrorResponseMiddleware:
    """Wrap ALL unhandled exceptions with generic error response.

    When DEBUG=True, Django's default handler returns full HTML stack traces
    for non-DRF views. This middleware catches those before they reach the
    default handler and returns generic JSON instead.

    DRF views are already handled by custom_exception_handler (V4.0 DEFECT-012),
    but this middleware provides coverage for:
    - Django admin views
    - allauth views
    - Any other Django view that raises an unhandled exception

    Note: process_exception() only fires when a VIEW function raises an exception.
    Middleware-layer exceptions are not caught here. For full coverage, a
    custom handler500 can be added in future production deployments.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_exception(self, request, exception):
        """Catch ALL unhandled exceptions and return generic JSON.

        Logs full exception details server-side (exc_info=True) for debugging,
        but returns only a generic message to the client.
        """
        # Log full exception details server-side only
        logger.error(
            "Unhandled exception on %s %s: %s",
            request.method,
            request.path,
            exception,
            exc_info=True,
        )
        # Return generic error to client — no stack trace, no settings, no SQL
        return JsonResponse(
            {"error": "Internal server error"},
            status=500,
        )


class AuthenticatedMediaMiddleware:
    """Require JWT authentication for /media/ URLs — V4.1 KB-V4.1-007.

    When DEBUG=True, Django's static() helper serves MEDIA_ROOT files
    publicly via /media/ with no authentication. This means any unauthenticated
    user can access uploaded PDFs, DOCXs, etc. by guessing the URL.

    This middleware intercepts /media/ requests and requires a valid JWT
    Bearer token, providing defense-in-depth even in DEBUG mode.

    Note: Ant Design Upload component uses /api/v1/documents/ (not /media/),
    so this middleware does not interfere with file upload functionality.
    """

    MEDIA_PREFIX = "/media/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(self.MEDIA_PREFIX):
            # V4.2 SYS-V4.2-020: Use BlacklistCheckingJWTAuthentication so
            # media access is also denied for blacklisted tokens (e.g. after logout).
            from apps.users.authentication import BlacklistCheckingJWTAuthentication

            try:
                validated = BlacklistCheckingJWTAuthentication().authenticate(request)
                if validated is None:
                    # No auth header provided
                    logger.warning(
                        "Unauthenticated media access attempt: %s %s",
                        request.method, request.path,
                    )
                    return HttpResponseForbidden(
                        "Authentication required for media files."
                    )
            except Exception as exc:
                # Invalid/expired token
                logger.warning(
                    "Invalid token for media access: %s — %s",
                    request.path, exc,
                )
                return HttpResponseForbidden(
                    "Invalid or expired authentication token."
                )

        return self.get_response(request)


class RbacCacheMiddleware:
    """Populate request._rbac_cache for authenticated users — V4.2 SYS-V4.2-006.

    Without this middleware, each has_permission() + has_role() call makes
    independent DB queries (2 for has_permission via get_permissions, 1 for
    has_role via UserRole filter = 3 queries per request).

    With this middleware, both calls share the same cached data dict:
    {"permissions": set, "roles": set}, populated on first access.
    This reduces RBAC DB queries from 3/request to 0-1/request.

    The cache is set on request.user._rbac_cache, which is the User model
    instance attached to the request by AuthenticationMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only set cache for authenticated users with a User model instance
        if hasattr(request, "user") and request.user.is_authenticated:
            # V4.2 SYS-V4.2-006: Initialize RBAC cache dict
            # Permissions and roles will be lazily populated by
            # User.get_permissions() on first access.
            request.user._rbac_cache = {"permissions": None, "roles": None}

        response = self.get_response(request)

        # Clear cache after response (prevent stale data between requests)
        if hasattr(request, "user") and hasattr(request.user, "_rbac_cache"):
            request.user._rbac_cache = None

        return response
