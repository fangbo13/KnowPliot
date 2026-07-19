"""Phase 5B scoped feedback review and knowledge-gap admin APIs."""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.views import create_audit_log
from apps.spaces.models import SpaceMembership
from apps.spaces.permissions import (
    ROLE_BUSINESS_ADMIN,
    ROLE_ORG_ADMIN,
    ROLE_SUPER_ADMIN,
    effective_space_role,
    accessible_spaces,
)
from .models import Feedback, FeedbackReviewEvent, KnowledgeGapTicket
from .serializers import FeedbackReviewSerializer, KnowledgeGapTicketSerializer


User = get_user_model()


REVIEW_ROLES = {
    ROLE_SUPER_ADMIN,
    ROLE_ORG_ADMIN,
    ROLE_BUSINESS_ADMIN,
    SpaceMembership.ROLE_OWNER,
    SpaceMembership.ROLE_KNOWLEDGE_ADMIN,
    SpaceMembership.ROLE_REVIEWER,
}
ASSIGN_ROLES = {
    ROLE_SUPER_ADMIN,
    ROLE_ORG_ADMIN,
    ROLE_BUSINESS_ADMIN,
    SpaceMembership.ROLE_OWNER,
    SpaceMembership.ROLE_KNOWLEDGE_ADMIN,
}


def _role(user, space):
    return effective_space_role(user, space)


def _can_review(user, space):
    return _role(user, space) in REVIEW_ROLES


def _can_assign(user, space):
    return _role(user, space) in ASSIGN_ROLES


def _forbidden():
    return Response({"detail": "You do not have review access."}, status=403)


def _conflict(detail):
    return Response({"detail": detail}, status=status.HTTP_409_CONFLICT)


def _audit(request, action, target, *, result="success", details=None):
    space = target.space
    create_audit_log(
        user=request.user,
        action=action,
        target_type=target.__class__.__name__,
        target_id=target.id,
        request=request,
        organization_id=space.organization_id,
        business_line_id=space.business_line_id,
        space_id=space.id,
        result=result,
        details=details or {},
    )


def _event(feedback, request, event_type, from_status, to_status, reviewer=None, notes=""):
    return FeedbackReviewEvent.objects.create(
        feedback=feedback,
        space=feedback.space,
        actor=request.user,
        reviewer=reviewer,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        notes=notes,
    )


def _scoped_feedback_queryset(user):
    spaces = accessible_spaces(user)
    return Feedback.objects.filter(space__in=spaces).select_related(
        "space", "user", "message", "reviewer"
    ).prefetch_related("review_events")


class FeedbackReviewListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = _scoped_feedback_queryset(request.user)
        qs = [feedback for feedback in qs if _can_review(request.user, feedback.space)]
        if not qs:
            if not any(_can_review(request.user, space) for space in accessible_spaces(request.user)):
                return _forbidden()
        status_filter = request.query_params.get("status")
        type_filter = request.query_params.get("type")
        reviewer_id = request.query_params.get("reviewer")
        space_id = request.query_params.get("space")
        if status_filter:
            qs = [f for f in qs if f.status == status_filter]
        if type_filter:
            qs = [f for f in qs if f.feedback_type == type_filter]
        if reviewer_id:
            qs = [f for f in qs if str(f.reviewer_id) == reviewer_id]
        if space_id:
            qs = [f for f in qs if str(f.space_id) == space_id]
        return Response({
            "count": len(qs),
            "results": FeedbackReviewSerializer(qs, many=True).data,
        })


class FeedbackReviewDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, request, pk, for_update=False):
        qs = Feedback.objects.select_related("space", "reviewer", "user", "message")
        if for_update:
            qs = qs.select_for_update(of=("self",))
        feedback = qs.get(id=pk)
        if not _can_review(request.user, feedback.space):
            return None
        return feedback

    def get(self, request, pk):
        feedback = self.get_object(request, pk)
        if feedback is None:
            return _forbidden()
        return Response(FeedbackReviewSerializer(feedback).data)


class FeedbackClaimView(FeedbackReviewDetailView):
    def post(self, request, pk):
        with transaction.atomic():
            feedback = self.get_object(request, pk, for_update=True)
            if feedback is None:
                return _forbidden()
            if feedback.status != Feedback.STATUS_PENDING_REVIEW:
                return _conflict("Only pending review feedback can be claimed.")
            feedback.status = Feedback.STATUS_IN_REVIEW
            feedback.reviewer = request.user
            feedback.save(update_fields=["status", "reviewer", "updated_at"])
            _event(feedback, request, "claim", Feedback.STATUS_PENDING_REVIEW, feedback.status, request.user)
            _audit(request, "feedback_review_claim", feedback, details={"status": feedback.status})
        return Response(FeedbackReviewSerializer(feedback).data)


class FeedbackAssignView(FeedbackReviewDetailView):
    def post(self, request, pk):
        with transaction.atomic():
            feedback = self.get_object(request, pk, for_update=True)
            if feedback is None:
                return _forbidden()
            if not _can_assign(request.user, feedback.space):
                return _forbidden()
            reviewer = User.objects.get(id=request.data.get("reviewer"))
            if not _can_review(reviewer, feedback.space):
                return Response({"detail": "Assignee is not a reviewer for this space."}, status=400)
            previous = feedback.status
            feedback.reviewer = reviewer
            if feedback.status == Feedback.STATUS_SUBMITTED:
                feedback.status = Feedback.STATUS_PENDING_REVIEW
            feedback.save(update_fields=["reviewer", "status", "updated_at"])
            _event(feedback, request, "assign", previous, feedback.status, reviewer)
            _audit(request, "feedback_review_assign", feedback, details={"reviewer": str(reviewer.id)})
        return Response(FeedbackReviewSerializer(feedback).data)


class FeedbackResolveView(FeedbackReviewDetailView):
    def post(self, request, pk):
        with transaction.atomic():
            feedback = self.get_object(request, pk, for_update=True)
            if feedback is None:
                return _forbidden()
            if feedback.status != Feedback.STATUS_IN_REVIEW:
                return _conflict("Only in-review feedback can be resolved.")
            if feedback.reviewer_id and feedback.reviewer_id != request.user.id and not _can_assign(request.user, feedback.space):
                return _forbidden()
            previous = feedback.status
            feedback.status = Feedback.STATUS_RESOLVED
            feedback.resolution_code = request.data.get("resolution_code", "")
            feedback.resolution_notes = request.data.get("resolution_notes", "")
            feedback.resolved_at = timezone.now()
            feedback.save(update_fields=["status", "resolution_code", "resolution_notes", "resolved_at", "updated_at"])
            _event(feedback, request, "resolve", previous, feedback.status, feedback.reviewer, feedback.resolution_code)
            _audit(request, "feedback_review_resolve", feedback, details={"resolution_code": feedback.resolution_code})
        return Response(FeedbackReviewSerializer(feedback).data)


class FeedbackDismissView(FeedbackReviewDetailView):
    def post(self, request, pk):
        with transaction.atomic():
            feedback = self.get_object(request, pk, for_update=True)
            if feedback is None:
                return _forbidden()
            if feedback.status != Feedback.STATUS_IN_REVIEW:
                return _conflict("Only in-review feedback can be dismissed.")
            previous = feedback.status
            feedback.status = Feedback.STATUS_DISMISSED
            feedback.resolution_code = request.data.get("resolution_code", "dismissed")
            feedback.resolution_notes = request.data.get("resolution_notes", "")
            feedback.resolved_at = timezone.now()
            feedback.save(update_fields=["status", "resolution_code", "resolution_notes", "resolved_at", "updated_at"])
            _event(feedback, request, "dismiss", previous, feedback.status, feedback.reviewer, feedback.resolution_code)
            _audit(request, "feedback_review_dismiss", feedback, details={"resolution_code": feedback.resolution_code})
        return Response(FeedbackReviewSerializer(feedback).data)


class FeedbackReopenView(FeedbackReviewDetailView):
    def post(self, request, pk):
        with transaction.atomic():
            feedback = self.get_object(request, pk, for_update=True)
            if feedback is None:
                return _forbidden()
            if feedback.status not in {Feedback.STATUS_RESOLVED, Feedback.STATUS_DISMISSED}:
                return _conflict("Only resolved or dismissed feedback can be reopened.")
            previous = feedback.status
            feedback.status = Feedback.STATUS_PENDING_REVIEW
            feedback.resolved_at = None
            feedback.save(update_fields=["status", "resolved_at", "updated_at"])
            _event(feedback, request, "reopen", previous, feedback.status, feedback.reviewer)
            _audit(request, "feedback_review_reopen", feedback)
        return Response(FeedbackReviewSerializer(feedback).data)


class KnowledgeGapListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = KnowledgeGapTicket.objects.filter(space__in=accessible_spaces(request.user)).select_related("space", "feedback", "assignee")
        qs = [ticket for ticket in qs if _can_review(request.user, ticket.space)]
        if not qs and not any(_can_review(request.user, space) for space in accessible_spaces(request.user)):
            return _forbidden()
        for param, attr in [("status", "status"), ("priority", "priority"), ("assignee", "assignee_id"), ("space", "space_id")]:
            value = request.query_params.get(param)
            if value:
                qs = [ticket for ticket in qs if str(getattr(ticket, attr)) == value]
        return Response({"count": len(qs), "results": KnowledgeGapTicketSerializer(qs, many=True).data})

    def post(self, request):
        space_id = request.data.get("space")
        space = next((s for s in accessible_spaces(request.user) if str(s.id) == str(space_id)), None)
        if space is None or not _can_review(request.user, space):
            return _forbidden()
        question = request.data.get("question") or ""
        feedback = None
        if request.data.get("feedback"):
            feedback = Feedback.objects.filter(id=request.data["feedback"], space=space).first()
        question_hash = KnowledgeGapTicket.hash_question(question)
        existing = KnowledgeGapTicket.objects.filter(
            space=space,
            normalized_question_hash=question_hash,
            status__in=[KnowledgeGapTicket.STATUS_OPEN, KnowledgeGapTicket.STATUS_IN_PROGRESS],
        ).first()
        if existing:
            if feedback and existing.feedback_id != feedback.id:
                existing.feedback = feedback
                existing.save(update_fields=["feedback", "updated_at"])
            return Response(KnowledgeGapTicketSerializer(existing).data, status=200)
        ticket = KnowledgeGapTicket.objects.create(
            space=space,
            feedback=feedback,
            question_snapshot=question,
            normalized_question_hash=question_hash,
            priority=request.data.get("priority", "medium"),
            suggested_source=request.data.get("suggested_source", ""),
        )
        _audit(request, "knowledge_gap_create", ticket, details={"priority": ticket.priority})
        return Response(KnowledgeGapTicketSerializer(ticket).data, status=201)


class KnowledgeGapActionView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    action = ""

    def post(self, request, pk):
        with transaction.atomic():
            ticket = (
                KnowledgeGapTicket.objects.select_for_update(of=("self",))
                .select_related("space")
                .get(id=pk)
            )
            if not _can_review(request.user, ticket.space):
                return _forbidden()
            if self.action == "assign":
                if not _can_assign(request.user, ticket.space):
                    return _forbidden()
                assignee = User.objects.get(id=request.data.get("assignee"))
                if not _can_review(assignee, ticket.space):
                    return Response({"detail": "Assignee is not a reviewer for this space."}, status=400)
                ticket.assignee = assignee
                if ticket.status == KnowledgeGapTicket.STATUS_OPEN:
                    ticket.status = KnowledgeGapTicket.STATUS_IN_PROGRESS
                ticket.save(update_fields=["assignee", "status", "updated_at"])
                _audit(request, "knowledge_gap_assign", ticket, details={"assignee": str(assignee.id)})
            elif self.action == "resolve":
                if ticket.status not in {KnowledgeGapTicket.STATUS_OPEN, KnowledgeGapTicket.STATUS_IN_PROGRESS}:
                    return _conflict("Only open or in-progress tickets can be resolved.")
                ticket.mark_resolved(request.data.get("resolution_notes", ""), request.data.get("wont_fix", False))
                ticket.save(update_fields=["status", "resolution_notes", "resolved_at", "updated_at"])
                _audit(request, "knowledge_gap_resolve", ticket, details={"status": ticket.status})
            elif self.action == "reopen":
                if ticket.status not in {KnowledgeGapTicket.STATUS_RESOLVED, KnowledgeGapTicket.STATUS_WONT_FIX}:
                    return _conflict("Only closed tickets can be reopened.")
                ticket.status = KnowledgeGapTicket.STATUS_OPEN
                ticket.resolved_at = None
                ticket.save(update_fields=["status", "resolved_at", "updated_at"])
                _audit(request, "knowledge_gap_reopen", ticket)
        return Response(KnowledgeGapTicketSerializer(ticket).data)


class KnowledgeGapAssignView(KnowledgeGapActionView):
    action = "assign"


class KnowledgeGapResolveView(KnowledgeGapActionView):
    action = "resolve"


class KnowledgeGapReopenView(KnowledgeGapActionView):
    action = "reopen"
