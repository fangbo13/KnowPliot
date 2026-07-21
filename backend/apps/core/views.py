"""Readiness endpoints with deliberately different public/platform detail."""

from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.rbac.capabilities import resolve_capabilities

from .readiness import collect_readiness


def _status(snapshot: dict) -> int:
    return status.HTTP_200_OK if snapshot["status"] == "ready" else status.HTTP_503_SERVICE_UNAVAILABLE


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def public_readiness(_request):
    snapshot = collect_readiness()
    public = {
        key: snapshot[key]
        for key in ("status", "build_revision", "configuration_revision", "checks")
    }
    return Response(public, status=_status(snapshot))


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def system_readiness(request):
    capabilities = resolve_capabilities(request.user).get("capabilities", [])
    if "platform.access" not in capabilities:
        return Response({"code": "permission_denied"}, status=status.HTTP_403_FORBIDDEN)
    snapshot = collect_readiness()
    return Response(snapshot, status=_status(snapshot))
