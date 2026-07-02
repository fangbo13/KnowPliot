"""Phase 5C quality analytics and compliance exports."""

import csv
import hashlib
import io
import os
from collections import Counter, defaultdict
from datetime import timedelta, timezone as dt_timezone

from django.conf import settings
from django.db.models import Count
from django.http import Http404, HttpResponse
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.views import create_audit_log
from apps.knowledge.models import Document
from apps.notifications.models import Notification
from apps.spaces.models import KnowledgeSpace
from apps.spaces.permissions import accessible_spaces
from .models import (
    Citation,
    ComplianceExportJob,
    Feedback,
    KnowledgeGapTicket,
    Message,
    ModelInvocation,
)
from .quality_views import _can_review


MAX_DAYS = 365
DEFAULT_DAYS = 30
MAX_EXPORT_ROWS = 10000
ASYNC_EXPORT_RETENTION_DAYS = 7


class CSVRenderer(BaseRenderer):
    media_type = "text/csv"
    format = "csv"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if isinstance(data, (bytes, bytearray)):
            return data
        return str(data or "").encode("utf-8")


def _report_spaces(user):
    return [space for space in accessible_spaces(user) if _can_review(user, space)]


def _parse_range(request):
    now = timezone.now()
    start = now - timedelta(days=DEFAULT_DAYS)
    end = now
    date_from = request.query_params.get("date_from")
    date_to = request.query_params.get("date_to")
    if date_from:
        start = timezone.datetime.fromisoformat(date_from.replace("Z", "+00:00"))
        if timezone.is_naive(start):
            start = timezone.make_aware(start)
    if date_to:
        end = timezone.datetime.fromisoformat(date_to.replace("Z", "+00:00"))
        if timezone.is_naive(end):
            end = timezone.make_aware(end)
    if end - start > timedelta(days=MAX_DAYS):
        start = end - timedelta(days=MAX_DAYS)
    return start, end


def _parse_data_range(data):
    now = timezone.now()
    start = now - timedelta(days=DEFAULT_DAYS)
    end = now
    date_from = data.get("date_from")
    date_to = data.get("date_to")
    if date_from:
        start = timezone.datetime.fromisoformat(str(date_from).replace("Z", "+00:00"))
        if timezone.is_naive(start):
            start = timezone.make_aware(start)
    if date_to:
        end = timezone.datetime.fromisoformat(str(date_to).replace("Z", "+00:00"))
        if timezone.is_naive(end):
            end = timezone.make_aware(end)
    if end - start > timedelta(days=MAX_DAYS):
        start = end - timedelta(days=MAX_DAYS)
    return start, end


def _safe_question_hash(question):
    normalized = KnowledgeGapTicket.normalize_question(question)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _previous_question(answer):
    return (
        Message.objects.filter(
            session=answer.session,
            role="user",
            created_at__lt=answer.created_at,
        )
        .order_by("-created_at")
        .first()
    )


class KnowledgeQualityReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        spaces = _report_spaces(request.user)
        if not spaces:
            return Response({"detail": "You do not have report access."}, status=403)
        start, end = _parse_range(request)
        feedback_qs = Feedback.objects.filter(
            space__in=spaces,
            created_at__gte=start,
            created_at__lte=end,
        )
        total_feedback = feedback_qs.count()
        negative_types = ["unhelpful", "incorrect", "outdated", "missing_source"]
        negative = feedback_qs.filter(feedback_type__in=negative_types).count()
        flagged = feedback_qs.filter(flag_for_review=True).count()
        type_counts = dict(feedback_qs.values_list("feedback_type").annotate(count=Count("id")))

        review_qs = feedback_qs.filter(
            status__in=[
                Feedback.STATUS_PENDING_REVIEW,
                Feedback.STATUS_IN_REVIEW,
                Feedback.STATUS_RESOLVED,
                Feedback.STATUS_DISMISSED,
            ]
        )
        resolved_rows = [
            (f.resolved_at - f.created_at).total_seconds()
            for f in review_qs
            if f.resolved_at
        ]
        avg_resolution_seconds = (
            sum(resolved_rows) / len(resolved_rows) if resolved_rows else None
        )

        gaps = KnowledgeGapTicket.objects.filter(space__in=spaces, created_at__gte=start, created_at__lte=end)

        unanswered = Counter()
        unanswered_display = {}
        zero_retrieval_answers = Message.objects.filter(
            space__in=spaces,
            role="assistant",
            retrieval_count=0,
            created_at__gte=start,
            created_at__lte=end,
        ).select_related("session")
        for answer in zero_retrieval_answers:
            question = _previous_question(answer)
            if question:
                key = _safe_question_hash(question.content)
                unanswered[key] += 1
                unanswered_display[key] = question.content
        failed_invocations = ModelInvocation.objects.filter(
            space__in=spaces,
            status__in=["failure", "timeout"],
            created_at__gte=start,
            created_at__lte=end,
        ).select_related("question_message")
        for invocation in failed_invocations:
            if invocation.question_message_id:
                key = _safe_question_hash(invocation.question_message.content)
                unanswered[key] += 1
                unanswered_display[key] = invocation.question_message.content

        high_citation = [
            {
                "id": str(row["document_id"]),
                "title": row["document__title"],
                "citation_count": row["count"],
            }
            for row in Citation.objects.filter(space__in=spaces)
            .values("document_id", "document__title")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        ]
        cited_document_ids = Citation.objects.filter(space__in=spaces).values_list("document_id", flat=True)
        uncited = [
            {"id": str(doc.id), "title": doc.title}
            for doc in Document.objects.filter(space__in=spaces, status="active")
            .exclude(id__in=list(cited_document_ids))[:10]
        ]
        stale_cited = [
            {"id": str(doc.id), "title": doc.title}
            for doc in Document.objects.filter(space__in=spaces, status="stale", id__in=list(cited_document_ids))[:10]
        ]

        trend_counter = defaultdict(lambda: {"feedback": 0, "negative": 0})
        for feedback in feedback_qs:
            day = feedback.created_at.date().isoformat()
            trend_counter[day]["feedback"] += 1
            if feedback.feedback_type in negative_types:
                trend_counter[day]["negative"] += 1

        return Response({
            "range": {"date_from": start.isoformat(), "date_to": end.isoformat(), "max_days": MAX_DAYS},
            "feedback": {
                "total": total_feedback,
                "by_type": type_counts,
                "negative_rate": round(negative / total_feedback, 4) if total_feedback else 0,
                "flagged_rate": round(flagged / total_feedback, 4) if total_feedback else 0,
            },
            "reviews": {
                "pending": review_qs.filter(status=Feedback.STATUS_PENDING_REVIEW).count(),
                "in_review": review_qs.filter(status=Feedback.STATUS_IN_REVIEW).count(),
                "resolved": review_qs.filter(status=Feedback.STATUS_RESOLVED).count(),
                "dismissed": review_qs.filter(status=Feedback.STATUS_DISMISSED).count(),
                "average_resolution_seconds": avg_resolution_seconds,
            },
            "unanswered_questions": [
                {"question": unanswered_display[key], "count": count}
                for key, count in unanswered.most_common(10)
            ],
            "knowledge_gaps": {
                "open": gaps.filter(status=KnowledgeGapTicket.STATUS_OPEN).count(),
                "in_progress": gaps.filter(status=KnowledgeGapTicket.STATUS_IN_PROGRESS).count(),
                "resolved": gaps.filter(status=KnowledgeGapTicket.STATUS_RESOLVED).count(),
                "wont_fix": gaps.filter(status=KnowledgeGapTicket.STATUS_WONT_FIX).count(),
            },
            "documents": {
                "high_citation": high_citation,
                "uncited": uncited,
                "stale_cited": stale_cited,
            },
            "trends": [
                {"date": day, **values}
                for day, values in sorted(trend_counter.items())
            ],
        })


def _rows_for_dataset(dataset, spaces, start, end):
    if dataset == "feedback":
        columns = ["id", "space_id", "message_id", "user_id", "feedback_type", "status", "flag_for_review", "created_at"]
        qs = Feedback.objects.filter(space__in=spaces, created_at__gte=start, created_at__lte=end).order_by("created_at")
        rows = ([str(f.id), str(f.space_id), str(f.message_id), str(f.user_id), f.feedback_type, f.status, str(f.flag_for_review).lower(), f.created_at.astimezone(dt_timezone.utc).isoformat()] for f in qs)
        return columns, rows
    if dataset == "reviews":
        columns = ["id", "space_id", "feedback_id", "status", "reviewer_id", "resolution_code", "resolved_at", "updated_at"]
        qs = Feedback.objects.filter(space__in=spaces).exclude(status=Feedback.STATUS_SUBMITTED).order_by("updated_at")
        rows = ([str(f.id), str(f.space_id), str(f.id), f.status, str(f.reviewer_id or ""), f.resolution_code, f.resolved_at.astimezone(dt_timezone.utc).isoformat() if f.resolved_at else "", f.updated_at.astimezone(dt_timezone.utc).isoformat()] for f in qs)
        return columns, rows
    if dataset == "gaps":
        columns = ["id", "space_id", "feedback_id", "status", "priority", "assignee_id", "created_at", "updated_at"]
        qs = KnowledgeGapTicket.objects.filter(space__in=spaces, created_at__gte=start, created_at__lte=end).order_by("created_at")
        rows = ([str(g.id), str(g.space_id), str(g.feedback_id or ""), g.status, g.priority, str(g.assignee_id or ""), g.created_at.astimezone(dt_timezone.utc).isoformat(), g.updated_at.astimezone(dt_timezone.utc).isoformat()] for g in qs)
        return columns, rows
    if dataset == "unanswered":
        columns = ["question", "count"]
        report = []
        counter = Counter()
        display = {}
        for answer in Message.objects.filter(space__in=spaces, role="assistant", retrieval_count=0, created_at__gte=start, created_at__lte=end):
            question = _previous_question(answer)
            if question:
                key = _safe_question_hash(question.content)
                counter[key] += 1
                display[key] = question.content
        for key, count in counter.items():
            report.append([display[key], count])
        return columns, iter(report)
    if dataset == "documents":
        columns = ["id", "space_id", "title", "status", "chunk_count", "citation_count", "updated_at"]
        citation_counts = Counter(Citation.objects.filter(space__in=spaces).values_list("document_id", flat=True))
        qs = Document.objects.filter(space__in=spaces).order_by("title")
        rows = ([str(d.id), str(d.space_id or ""), d.title, d.status, d.chunk_count, citation_counts[d.id], d.updated_at.astimezone(dt_timezone.utc).isoformat()] for d in qs)
        return columns, rows
    return None, None


def _serialize_export_job(job):
    return {
        "id": str(job.id),
        "dataset": job.dataset,
        "status": job.status,
        "space": str(job.space_id) if job.space_id else None,
        "requested_by": str(job.requested_by_id),
        "row_count": job.row_count,
        "error_code": job.error_code,
        "safe_error_summary": job.safe_error_summary,
        "date_from": job.date_from.isoformat() if job.date_from else None,
        "date_to": job.date_to.isoformat() if job.date_to else None,
        "expires_at": job.expires_at.isoformat() if job.expires_at else None,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "download_url": f"/api/v1/admin/reports/export-jobs/{job.id}/download/"
        if job.status == ComplianceExportJob.STATUS_SUCCEEDED
        else "",
    }


def _export_job_path(job):
    export_root = os.path.join(settings.MEDIA_ROOT, "exports", "compliance")
    os.makedirs(export_root, exist_ok=True)
    return os.path.join(export_root, f"{job.id}.csv")


def _complete_export_job(job, request=None):
    job.status = ComplianceExportJob.STATUS_PROCESSING
    job.save(update_fields=["status", "updated_at"])
    try:
        spaces = [job.space] if job.space_id else _report_spaces(job.requested_by)
        columns, rows_iter = _rows_for_dataset(job.dataset, spaces, job.date_from, job.date_to)
        if columns is None:
            raise ValueError("unknown_dataset")

        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(columns)
        count = 0
        for row in rows_iter:
            count += 1
            writer.writerow(row)

        path = _export_job_path(job)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(output.getvalue())

        job.status = ComplianceExportJob.STATUS_SUCCEEDED
        job.result_file = path
        job.row_count = count
        job.error_code = ""
        job.safe_error_summary = ""
        job.expires_at = timezone.now() + timedelta(days=ASYNC_EXPORT_RETENTION_DAYS)
        job.save(
            update_fields=[
                "status",
                "result_file",
                "row_count",
                "error_code",
                "safe_error_summary",
                "expires_at",
                "updated_at",
            ]
        )
        create_audit_log(
            user=job.requested_by,
            action="export_job_complete",
            target_type="ComplianceExportJob",
            target_id=job.id,
            request=request,
            space_id=job.space_id,
            details={"dataset": job.dataset, "row_count": count},
        )
        Notification.objects.create(
            recipient=job.requested_by,
            type=Notification.TYPE_SYSTEM,
            title="Compliance export is ready",
            body=f"Your {job.dataset} export completed with {count} rows.",
            level="success",
            link="/admin/quality",
            metadata={
                "event": "export_job_complete",
                "export_job_id": str(job.id),
                "dataset": job.dataset,
                "row_count": count,
            },
        )
    except Exception as exc:  # pragma: no cover - defensive production path
        job.status = ComplianceExportJob.STATUS_FAILED
        job.error_code = "export_failed"
        job.safe_error_summary = "Export job failed before completion."
        job.save(
            update_fields=[
                "status",
                "error_code",
                "safe_error_summary",
                "updated_at",
            ]
        )
        create_audit_log(
            user=job.requested_by,
            action="export_job_complete",
            target_type="ComplianceExportJob",
            target_id=job.id,
            request=request,
            result="failure",
            space_id=job.space_id,
            details={"dataset": job.dataset, "error_code": job.error_code},
        )
        raise exc


def _can_access_job(user, job):
    if job.requested_by_id == user.id:
        return True
    if job.space_id and _can_review(user, job.space):
        return True
    return False


class ComplianceExportView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    renderer_classes = [CSVRenderer, JSONRenderer]

    def get(self, request):
        spaces = _report_spaces(request.user)
        if not spaces:
            return Response({"detail": "You do not have export access."}, status=403)
        dataset = request.query_params.get("dataset", "")
        export_format = request.query_params.get("format", "csv")
        if export_format != "csv":
            return Response({"detail": "Only csv format is supported."}, status=400)
        start, end = _parse_range(request)
        columns, rows_iter = _rows_for_dataset(dataset, spaces, start, end)
        if columns is None:
            return Response({"detail": "Unknown dataset."}, status=400)

        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(columns)
        count = 0
        for row in rows_iter:
            count += 1
            if count > MAX_EXPORT_ROWS:
                return Response(
                    {
                        "detail": "Export too large for synchronous download. Use async export jobs.",
                        "code": "sync_export_too_large",
                        "async_export_url": "/api/v1/admin/reports/export-jobs/",
                    },
                    status=413,
                )
            writer.writerow(row)

        create_audit_log(
            user=request.user,
            action="audit_export",
            target_type="QualityReport",
            request=request,
            result="success",
            details={
                "dataset": dataset,
                "format": export_format,
                "date_from": start.isoformat(),
                "date_to": end.isoformat(),
                "row_count": count,
            },
        )
        response = HttpResponse(output.getvalue().encode("utf-8"), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{dataset}.csv"'
        return response


class ComplianceExportJobListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        spaces = _report_spaces(request.user)
        space_ids = [space.id for space in spaces]
        qs = ComplianceExportJob.objects.filter(requested_by=request.user)
        if space_ids:
            qs = qs | ComplianceExportJob.objects.filter(space_id__in=space_ids)
        qs = qs.select_related("space", "requested_by").distinct().order_by("-created_at")
        return Response({
            "count": qs.count(),
            "results": [_serialize_export_job(job) for job in qs[:100]],
        })

    def post(self, request):
        spaces = _report_spaces(request.user)
        if not spaces:
            return Response({"detail": "You do not have export access."}, status=403)
        dataset = request.data.get("dataset")
        valid_datasets = {choice[0] for choice in ComplianceExportJob.DATASET_CHOICES}
        if dataset not in valid_datasets:
            return Response({"detail": "Unknown dataset."}, status=400)

        requested_space_id = request.data.get("space")
        selected_space = None
        if requested_space_id:
            selected_space = KnowledgeSpace.objects.filter(id=requested_space_id).first()
            if not selected_space or selected_space not in spaces:
                return Response({"detail": "You do not have export access for this space."}, status=403)

        start, end = _parse_data_range(request.data)
        job = ComplianceExportJob.objects.create(
            requested_by=request.user,
            space=selected_space,
            dataset=dataset,
            date_from=start,
            date_to=end,
            expires_at=timezone.now() + timedelta(days=ASYNC_EXPORT_RETENTION_DAYS),
        )
        create_audit_log(
            user=request.user,
            action="export_job_create",
            target_type="ComplianceExportJob",
            target_id=job.id,
            request=request,
            space_id=job.space_id,
            details={
                "dataset": dataset,
                "space_id": str(job.space_id) if job.space_id else "",
                "date_from": start.isoformat(),
                "date_to": end.isoformat(),
            },
        )
        _complete_export_job(job, request=request)
        return Response(_serialize_export_job(job), status=status.HTTP_201_CREATED)


class ComplianceExportJobDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, request, pk):
        try:
            job = ComplianceExportJob.objects.select_related("space", "requested_by").get(pk=pk)
        except ComplianceExportJob.DoesNotExist:
            raise Http404
        if not _can_access_job(request.user, job):
            return None
        return job

    def get(self, request, pk):
        job = self.get_object(request, pk)
        if job is None:
            return Response({"detail": "You do not have access to this export job."}, status=403)
        return Response(_serialize_export_job(job))


class ComplianceExportJobDownloadView(ComplianceExportJobDetailView):
    renderer_classes = [CSVRenderer, JSONRenderer]

    def get(self, request, pk):
        job = self.get_object(request, pk)
        if job is None:
            return Response({"detail": "You do not have access to this export job."}, status=403)
        if job.status != ComplianceExportJob.STATUS_SUCCEEDED:
            return Response({"detail": "Export job is not ready."}, status=409)
        if job.expires_at and job.expires_at < timezone.now():
            job.status = ComplianceExportJob.STATUS_EXPIRED
            job.save(update_fields=["status", "updated_at"])
            return Response({"detail": "Export job has expired."}, status=410)
        if not job.result_file or not os.path.exists(job.result_file):
            return Response({"detail": "Export file is unavailable."}, status=404)

        create_audit_log(
            user=request.user,
            action="audit_export_download",
            target_type="ComplianceExportJob",
            target_id=job.id,
            request=request,
            space_id=job.space_id,
            details={"dataset": job.dataset, "row_count": job.row_count},
        )
        with open(job.result_file, "rb") as handle:
            content = handle.read()
        response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{job.dataset}-{job.id}.csv"'
        return response
