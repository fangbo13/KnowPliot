"""Custom DRF exception handler."""

import logging

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """Custom exception handler for consistent error responses.

    V4.0 DEFECT-012: 500 responses must NOT leak str(exc) to clients.
    Internal exception details (stack traces, file paths, DB connection strings)
    are logged server-side only, never returned in API responses.
    """
    response = exception_handler(exc, context)

    if response is None:
        # Unhandled exception — log internally, return generic message to client
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        {
            "error": response.data.get("detail", str(response.data)),
            "detail": response.data,
        },
        status=response.status_code,
    )
