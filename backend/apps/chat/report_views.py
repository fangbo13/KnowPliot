"""Phase 5C quality analytics and compliance exports."""

import csv
import hashlib
import io
from collections import Counter, defaultdict
from datetime import timedelta, timezone as dt_timezone

from django.db.models import Count
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.views import create_audit_log
from apps.knowledge.models import Document
from apps.spaces.permissions import accessible_spaces
from .models import Citation, Feedback, KnowledgeGapTicket, Message, ModelInvocation
from .quality_views import _can_review


MAX_DAYS = 365
DEFAULT_DAYS = 30
MAX_EXPORT_ROWS = 10000


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
                return Response({"detail": "Export too large. Narrow the date range."}, status=413)
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
