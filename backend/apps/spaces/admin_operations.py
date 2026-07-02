"""Bounded health checks and scoped operational metrics."""

import time
from datetime import timedelta

from celery import current_app
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.chat.models import (
    ChatSession,
    Citation,
    ComplianceExportJob,
    Feedback,
    KnowledgeGapTicket,
    Message,
    ModelInvocation,
)
from apps.knowledge.models import Document, IngestionJob
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


def _migration_status():
    def check_migrations():
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if plan:
            raise RuntimeError("Unapplied migrations")

    result = _timed_check(check_migrations)
    if result["status"] == "down":
        result["status"] = "degraded"
        result["detail"] = "Unapplied migrations detected"
        result.pop("error", None)
    else:
        result["detail"] = "All migrations applied"
    return result


def _path_config_status(name, value):
    if value:
        return {"status": "configured", "detail": f"{name} configured"}
    return {"status": "degraded", "detail": f"{name} is not configured"}


def _security_config_status():
    missing = []
    if getattr(settings, "DEBUG", False):
        missing.append("DEBUG")
    allowed_hosts = list(getattr(settings, "ALLOWED_HOSTS", []) or [])
    if not allowed_hosts or "*" in allowed_hosts:
        missing.append("ALLOWED_HOSTS")
    if getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False):
        missing.append("CORS_ALLOW_ALL_ORIGINS")
    if not getattr(settings, "SESSION_COOKIE_SECURE", False):
        missing.append("SESSION_COOKIE_SECURE")
    if not getattr(settings, "CSRF_COOKIE_SECURE", False):
        missing.append("CSRF_COOKIE_SECURE")
    if not getattr(settings, "SECURE_SSL_REDIRECT", False):
        missing.append("SECURE_SSL_REDIRECT")
    return {
        "status": "degraded" if missing else "configured",
        "missing": missing,
        "detail": (
            "Production security settings need attention"
            if missing
            else "Production security settings configured"
        ),
    }


def _export_limits_status():
    try:
        from apps.chat.report_views import MAX_EXPORT_ROWS
    except Exception:
        max_export_rows = 10000
    else:
        max_export_rows = MAX_EXPORT_ROWS
    return {
        "status": "configured",
        "max_sync_rows": max_export_rows,
        "detail": "Synchronous export row limit configured",
    }


def _latency_bucket(latency_ms):
    if latency_ms < 50:
        return "fast"
    if latency_ms < 250:
        return "normal"
    return "slow"


def _configured_positive_int(name, default):
    value = getattr(settings, name, default)
    if isinstance(value, bool) or value is None:
        return None
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _long_run_operations_status():
    started = time.monotonic()
    required = {
        "EXPORT_JOB_RETENTION_DAYS": 7,
        "AUDIT_LOG_RETENTION_DAYS": 365,
        "NOTIFICATION_RETENTION_DAYS": 90,
        "STALE_JOB_RETENTION_DAYS": 30,
    }
    configured = {
        name: _configured_positive_int(name, default)
        for name, default in required.items()
    }
    missing = [name for name, value in configured.items() if value is None]
    now = timezone.now()
    pending_feedback_cutoff = now - timedelta(days=3)
    in_review_feedback_cutoff = now - timedelta(days=5)
    open_gap_cutoff = now - timedelta(days=3)
    expired_exports = ComplianceExportJob.objects.filter(
        expires_at__lt=now,
    ).exclude(status=ComplianceExportJob.STATUS_EXPIRED)
    failed_exports = ComplianceExportJob.objects.filter(
        status=ComplianceExportJob.STATUS_FAILED
    )
    failed_ingestion = IngestionJob.objects.filter(status="failed")
    sla_backlog = (
        Feedback.objects.filter(
            status=Feedback.STATUS_PENDING_REVIEW,
            created_at__lt=pending_feedback_cutoff,
        ).count()
        + Feedback.objects.filter(
            status=Feedback.STATUS_IN_REVIEW,
            created_at__lt=in_review_feedback_cutoff,
        ).count()
        + KnowledgeGapTicket.objects.filter(
            status__in=[
                KnowledgeGapTicket.STATUS_OPEN,
                KnowledgeGapTicket.STATUS_IN_PROGRESS,
            ],
            created_at__lt=open_gap_cutoff,
        ).count()
    )
    latency_ms = round((time.monotonic() - started) * 1000, 1)
    return {
        "status": "degraded" if missing else "configured",
        "code": (
            "long_run_operations_config_missing"
            if missing
            else "long_run_operations_configured"
        ),
        "detail": (
            "Long-run cleanup configuration needs attention"
            if missing
            else "Long-run cleanup configuration is ready"
        ),
        "missing": missing,
        "last_checked_at": now.isoformat(),
        "latency_ms": latency_ms,
        "latency_bucket": _latency_bucket(latency_ms),
        "retention": {
            "export_job_days": configured["EXPORT_JOB_RETENTION_DAYS"],
            "audit_log_days": configured["AUDIT_LOG_RETENTION_DAYS"],
            "notification_days": configured["NOTIFICATION_RETENTION_DAYS"],
            "stale_job_days": configured["STALE_JOB_RETENTION_DAYS"],
        },
        "cleanup": {
            "expired_export_jobs": expired_exports.count(),
            "failed_export_jobs": failed_exports.count(),
            "failed_ingestion_jobs": failed_ingestion.count(),
        },
        "backlog": {
            "sla_overdue_items": sla_backlog,
            "stale_documents": Document.objects.filter(status="stale").count(),
        },
    }


def collect_system_health():
    services = {
        "backend": {"status": "up"},
        "database": _timed_check(_check_database),
        "migrations": _migration_status(),
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
        "static_files": _path_config_status(
            "STATIC_ROOT",
            str(getattr(settings, "STATIC_ROOT", "") or ""),
        ),
        "media_storage": _path_config_status(
            "MEDIA_ROOT",
            str(getattr(settings, "MEDIA_ROOT", "") or ""),
        ),
        "security_config": _security_config_status(),
        "export_limits": _export_limits_status(),
        "long_run_operations": _long_run_operations_status(),
    }
    statuses = {service["status"] for service in services.values()}
    if services["database"]["status"] == "down":
        overall = "down"
    elif "down" in statuses or "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "up"
    dependencies = {
        key: services[key]["status"]
        for key in ["database", "redis", "celery", "vector_db", "llm"]
        if key in services
    }
    return {
        "overall": overall,
        "readiness": overall,
        "liveness": "up" if services["backend"]["status"] == "up" else "down",
        "dependency_health": dependencies,
        "background_worker_health": services["celery"],
        "services": services,
    }


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
