"""Low-cardinality Prometheus metrics and the private scrape endpoint."""

from __future__ import annotations

import os
import re
import secrets
import time
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)

_SAFE_ROUTE = re.compile(r"^[a-zA-Z0-9_.:-]{1,96}$")
_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})

HTTP_REQUESTS = Counter(
    "knowpilot_http_requests_total",
    "Completed HTTP requests by resolved route, method, and status.",
    ("route", "method", "status"),
)
HTTP_DURATION = Histogram(
    "knowpilot_http_request_duration_seconds",
    "HTTP response latency by resolved route and method.",
    ("route", "method"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 15, 60, 180),
)
SSE_CONNECTIONS = Gauge(
    "knowpilot_sse_connections",
    "Currently open recoverable SSE connections.",
    multiprocess_mode="livesum",
)
SSE_RECONNECTS = Counter(
    "knowpilot_sse_reconnects_total",
    "Recoverable SSE requests that resumed after a non-zero cursor.",
)
GENERATION_OUTSTANDING = Gauge(
    "knowpilot_generation_outstanding",
    "Reserved generation Turns, including queued and active work.",
    multiprocess_mode="livemax",
)
GENERATION_QUEUED = Gauge(
    "knowpilot_generation_queued",
    "Generation Turns waiting for a worker.",
    multiprocess_mode="livesum",
)
GENERATION_ACTIVE = Gauge(
    "knowpilot_generation_active",
    "Generation Turns currently executing.",
    multiprocess_mode="livesum",
)
GENERATION_REJECTIONS = Counter(
    "knowpilot_generation_rejections_total",
    "Generation requests rejected by the global capacity gate.",
)
QUEUE_WAIT = Histogram(
    "knowpilot_generation_queue_wait_seconds",
    "Time from Turn creation until worker execution.",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
FIRST_EVENT = Histogram(
    "knowpilot_generation_first_event_seconds",
    "Time from generation start until the first public stream event.",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
FIRST_ANSWER = Histogram(
    "knowpilot_generation_first_answer_seconds",
    "Time from generation start until the first answer delta.",
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 45, 90),
)
GENERATION_DURATION = Histogram(
    "knowpilot_generation_duration_seconds",
    "Total generation duration.",
    buckets=(0.25, 0.5, 1, 2, 5, 10, 20, 45, 90, 180),
)
PROVIDER_FAILURES = Counter(
    "knowpilot_provider_failures_total",
    "Provider failures grouped into a fixed outcome set.",
    ("code",),
)
TASK_RETRIES = Counter("knowpilot_generation_task_retries_total", "Generation task retries.")
LEASE_LOSSES = Counter("knowpilot_generation_lease_losses_total", "Generation lease losses.")
CANCELLATIONS = Counter("knowpilot_generation_cancellations_total", "Accepted cancellations.")


def _route_name(request: HttpRequest) -> str:
    match = getattr(request, "resolver_match", None)
    candidate = getattr(match, "url_name", None)
    return candidate if isinstance(candidate, str) and _SAFE_ROUTE.fullmatch(candidate) else "unmatched"


class PrometheusRequestMiddleware:
    """Measure requests without using paths or request-owned identifiers as labels."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        started = time.monotonic()
        response = self.get_response(request)
        route = _route_name(request)
        method = request.method if request.method in _METHODS else "OTHER"
        status = str(response.status_code)
        HTTP_REQUESTS.labels(route=route, method=method, status=status).inc()
        HTTP_DURATION.labels(route=route, method=method).observe(time.monotonic() - started)
        return response


def prometheus_metrics(request: HttpRequest) -> HttpResponse:
    expected = settings.PROMETHEUS_METRICS_TOKEN
    supplied = request.headers.get("Authorization", "")
    token = supplied[7:] if supplied.startswith("Bearer ") else ""
    if not expected or not token or not secrets.compare_digest(token, expected):
        return HttpResponseNotFound()
    registry = REGISTRY
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    return HttpResponse(generate_latest(registry), content_type=CONTENT_TYPE_LATEST)
