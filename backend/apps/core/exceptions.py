"""Custom DRF exception handler."""

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    """Custom exception handler for consistent error responses."""
    response = exception_handler(exc, context)

    if response is None:
        return Response(
            {"error": "Internal server error", "detail": str(exc)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        {
            "error": response.data.get("detail", str(response.data)),
            "detail": response.data,
        },
        status=response.status_code,
    )
