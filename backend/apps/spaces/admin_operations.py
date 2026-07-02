"""Bounded health checks and scoped operational metrics."""

import time
from datetime import timedelta

from celery import current_app
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.chat.models import ChatSession, Citation, Message, ModelInvocation
from apps.knowledge.models import Document
from .models import KnowledgeSpace, OrganizationMembership, SpaceMembership
from .permissions import admin_scope, is_platform_admin


def _timed_check(check):
    started = time.monotonic()
    try:
        check()
        return {
            "status": "up",
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
        }
    except Exception as exc:
        return {
            "status": "down",
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
            "error": exc.__class__.__name__,
        }


def _check_database():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()


def _check_redis():
    from redis import Redis

    client = Redis.from_url(
        settings.CELERY_BROKER_URL,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )
    client.ping()


def _check_celery():
    replies = current_app.control.inspect(timeout=0.75).ping()
    if not replies:
        raise RuntimeError("No Celery workers replied")


def _vector_status():
    if connection.vendor != "postgresql":
        return {"status": "not_configured", "detail": "SQLite fallback"}

    def check_extension():
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_extension WHERE extname = %s", ["vector"])
            if cursor.fetchone() is None:
                raise RuntimeError("pgvector extension is not installed")

    return _timed_check(check_extension)


def collect_system_health():
    services = {
        "backend": {"status": "up"},
        "database": _timed_check(_check_database),
        "redis": _timed_check(_check_redis),
        "celery": _timed_check(_check_celery),
        "vector_db": _vector_status(),
        "llm": {
            "status": (
                "configured"
                if bool(getattr(settings, "DASHSCOPE_API_KEY", ""))
                else "not_configured"
            )
        },
    }
    statuses = {service["status"] for service in services.values()}
    if services["database"]["status"] == "down":
        overall = "down"
    elif "down" in statuses:
        overall = "degraded"
    else:
        overall = "up"
    return {"overall": overall, "services": services}


def scoped_space_ids(user):
    if is_platform_admin(user):
        return None
    org_ids, business_line_ids = admin_scope(user)
    return list(
        KnowledgeSpace.objects.filter(
            Q(organization_id__in=org_ids)
            | Q(business_line_id__in=business_line_ids)
        ).values_list("id", flat=True)
    )


def _scope(queryset, space_ids):
    return queryset if space_ids is None else queryset.filter(space_id__in=space_ids)


def collect_scoped_metrics(user):
    space_ids = scoped_space_ids(user)
    documents = _scope(Document.objects.all(), space_ids)
    sessions = _scope(ChatSession.objects.all(), space_ids)
    messages = _scope(Message.objects.all(), space_ids)
    citations = _scope(Citation.objects.all(), space_ids)
    assistant_messages = messages.filter(role="assistant")
    invocations = _scope(ModelInvocation.objects.all(), space_ids)
    assistant_count = assistant_messages.count()
    cited_message_count = (
        citations.values("message_id").distinct().count()
        if assistant_count
        else 0
    )
    no_evidence_count = assistant_messages.filter(retrieval_count=0).count()

    if space_ids is None:
        users = get_user_model().objects.all()
        denied_logs = AuditLog.objects.filter(action="permission_denied")
    else:
        member_ids = SpaceMembership.objects.filter(
            space_id__in=space_ids,
            status="active",
        ).values_list("user_id", flat=True)
        org_ids, business_line_ids = admin_scope(user)
        admin_ids = OrganizationMembership.objects.filter(
            Q(organization_id__in=org_ids)
            | Q(business_line_id__in=business_line_ids)
        ).values_list("user_id", flat=True)
        users = get_user_model().objects.filter(
            Q(id__in=member_ids) | Q(id__in=admin_ids)
        ).distinct()
        denied_logs = AuditLog.objects.filter(
            action="permission_denied",
            space_id__in=space_ids,
        )

    today = timezone.localdate()
    expiring_cutoff = today + timedelta(days=30)
    average_response = assistant_messages.aggregate(
        value=Avg("response_time_ms")
    )["value"]
    completed_invocations = invocations.exclude(status="cancelled")
    call_count = completed_invocations.count()
    failures = completed_invocations.filter(status__in=["failure", "timeout"]).count()
    successful_invocations = completed_invocations.filter(status="success")
    token_summary = successful_invocations.aggregate(
        total=Sum("token_count"),
        average=Avg("token_count"),
    )
    by_model = list(
        completed_invocations.exclude(model="")
        .values("model")
        .annotate(calls=Count("id"))
        .order_by("model")
    )
    quality_documents = documents.filter(status__in=["active", "stale"]).annotate(
        citation_count=Count("citation")
    )
    return {
        "users": {
            "total": users.count(),
            "active": users.filter(is_active=True).count(),
        },
        "usage": {
            "sessions": sessions.count(),
            "questions": messages.filter(role="user").count(),
            "citations": citations.count(),
        },
        "documents": {
            "total": documents.count(),
            "processing": documents.filter(status="processing").count(),
            "failed": documents.filter(status="failed").count(),
            "stale": documents.filter(status="stale").count(),
            "expiring": documents.filter(
                status="active",
                effective_to__gte=today,
                effective_to__lte=expiring_cutoff,
            ).count(),
        },
        "quality": {
            "average_response_time_ms": (
                round(float(average_response), 1)
                if average_response is not None
                else None
            ),
            "no_evidence_rate": (
                round(no_evidence_count / assistant_count, 4)
                if assistant_count
                else 0.0
            ),
            "citation_coverage_rate": (
                round(cited_message_count / assistant_count, 4)
                if assistant_count
                else 0.0
            ),
        },
        "model_api": {
            "calls": call_count,
            "failures": failures,
            "error_rate": round(failures / call_count, 4) if call_count else 0.0,
            "total_tokens": token_summary["total"] or 0,
            "average_tokens": (
                round(float(token_summary["average"]), 1)
                if token_summary["average"] is not None
                else 0.0
            ),
            "by_model": by_model,
        },
        "knowledge_quality": {
            "unused_documents": quality_documents.filter(
                status="active", citation_count=0
            ).count(),
            "high_usage_documents": quality_documents.filter(
                citation_count__gte=3
            ).count(),
            "stale_cited_documents": quality_documents.filter(
                status="stale", citation_count__gt=0
            ).count(),
        },
        "security": {
            "permission_denied": denied_logs.count(),
        },
    }
