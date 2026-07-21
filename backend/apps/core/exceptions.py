# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Custom DRF exception handler."""

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """Return stable, safe API error responses.

    Internal exception details are logged server-side only. The response keeps
    the historical ``error`` key while adding Phase 6A's stable ``detail`` and
    ``code`` fields for management clients.
    """
    response = exception_handler(exc, context)

    if response is None:
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return Response(
            {
                "detail": "Internal server error",
                "code": "internal_error",
                "error": "Internal server error",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Governed mutations persist safe failures for exact idempotent replay.
    # Let those domain exceptions own one canonical primitive-only envelope so
    # the initial response and every replay have identical status/body pairs.
    safe_response_body = getattr(exc, "safe_response_body", None)
    if callable(safe_response_body):
        return Response(safe_response_body(), status=response.status_code)

    raw_detail = (
        response.data.get("detail", response.data)
        if isinstance(response.data, dict)
        else response.data
    )
    if hasattr(raw_detail, "code"):
        detail = str(raw_detail)
        code = raw_detail.code
    else:
        detail = str(raw_detail)
        code = getattr(exc, "default_code", "error")

    headers = {}
    if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        code = "rate_limited"
        if response.has_header("Retry-After"):
            headers["Retry-After"] = response["Retry-After"]

    return Response(
        {
            "detail": detail,
            "code": code,
            "error": detail,
            "errors": response.data,
        },
        status=response.status_code,
        headers=headers,
    )
