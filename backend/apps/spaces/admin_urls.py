# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Admin governance URLs — V7.0, mounted at /api/v1/admin/."""

from django.urls import path

from .admin_views import (
    AdminRegistrationCodeListCreateView,
    BusinessLineListCreateView,
    BusinessLineDetailView,
    DocumentQualityListView,
    IngestionJobListView,
    IngestionJobRetryView,
    OrganizationListView,
    OrganizationDetailView,
    SpaceAccessRequestListView,
    SystemHealthView,
    SystemMetricsView,
    admin_code_revoke,
    organization_archive,
    organization_restore,
    space_access_request_approve,
    ScopedAdminUserListView,
    scoped_user_assignment,
    business_line_archive,
    business_line_restore,
)
from apps.chat.quality_views import (
    FeedbackAssignView,
    FeedbackClaimView,
    FeedbackDismissView,
    FeedbackReopenView,
    FeedbackResolveView,
    FeedbackReviewDetailView,
    FeedbackReviewListView,
    KnowledgeGapAssignView,
    KnowledgeGapListCreateView,
    KnowledgeGapReopenView,
    KnowledgeGapResolveView,
)
from apps.chat.report_views import (
    ComplianceExportJobDetailView,
    ComplianceExportJobDownloadView,
    ComplianceExportJobListCreateView,
    ComplianceExportJobRetryView,
    ComplianceExportView,
    KnowledgeQualityReportView,
)
from apps.rag.evaluation_views import RAGEvaluationRunListView

urlpatterns = [
    path("registration-codes/", AdminRegistrationCodeListCreateView.as_view(),
         name="admin-code-list"),
    path("registration-codes/<uuid:pk>/revoke/", admin_code_revoke,
         name="admin-code-revoke"),
    path("organizations/", OrganizationListView.as_view(), name="admin-org-list"),
    path("organizations/<uuid:pk>/", OrganizationDetailView.as_view(), name="admin-org-detail"),
    path("organizations/<uuid:pk>/archive/", organization_archive, name="admin-org-archive"),
    path("organizations/<uuid:pk>/restore/", organization_restore, name="admin-org-restore"),
    path("business-lines/", BusinessLineListCreateView.as_view(), name="admin-bl-list"),
    path("business-lines/<uuid:pk>/", BusinessLineDetailView.as_view(), name="admin-bl-detail"),
    path("business-lines/<uuid:pk>/archive/", business_line_archive, name="admin-bl-archive"),
    path("business-lines/<uuid:pk>/restore/", business_line_restore, name="admin-bl-restore"),
    path("spaces/<uuid:pk>/access-requests/", SpaceAccessRequestListView.as_view(), name="admin-space-access-request-list"),
    path("spaces/<uuid:pk>/access-requests/<uuid:request_id>/approve/", space_access_request_approve, name="admin-space-access-request-approve"),
    path("users/", ScopedAdminUserListView.as_view(), name="admin-scoped-user-list"),
    path("users/<uuid:user_id>/assignments/", scoped_user_assignment, name="admin-scoped-user-assignment"),
    path("health/", SystemHealthView.as_view(), name="admin-health"),
    path("metrics/", SystemMetricsView.as_view(), name="admin-metrics"),
    path("ingestion-jobs/", IngestionJobListView.as_view(), name="admin-ingestion-jobs"),
    path(
        "ingestion-jobs/<uuid:pk>/retry/",
        IngestionJobRetryView.as_view(),
        name="admin-ingestion-job-retry",
    ),
    path(
        "quality/documents/",
        DocumentQualityListView.as_view(),
        name="admin-document-quality",
    ),
    path(
        "quality/evaluations/",
        RAGEvaluationRunListView.as_view(),
        name="admin-quality-evaluations",
    ),
    path("quality/feedback/", FeedbackReviewListView.as_view(), name="admin-quality-feedback"),
    path("quality/feedback/<uuid:pk>/", FeedbackReviewDetailView.as_view(), name="admin-quality-feedback-detail"),
    path("quality/feedback/<uuid:pk>/claim/", FeedbackClaimView.as_view(), name="admin-quality-feedback-claim"),
    path("quality/feedback/<uuid:pk>/assign/", FeedbackAssignView.as_view(), name="admin-quality-feedback-assign"),
    path("quality/feedback/<uuid:pk>/resolve/", FeedbackResolveView.as_view(), name="admin-quality-feedback-resolve"),
    path("quality/feedback/<uuid:pk>/dismiss/", FeedbackDismissView.as_view(), name="admin-quality-feedback-dismiss"),
    path("quality/feedback/<uuid:pk>/reopen/", FeedbackReopenView.as_view(), name="admin-quality-feedback-reopen"),
    path("quality/gaps/", KnowledgeGapListCreateView.as_view(), name="admin-quality-gaps"),
    path("quality/gaps/<uuid:pk>/assign/", KnowledgeGapAssignView.as_view(), name="admin-quality-gap-assign"),
    path("quality/gaps/<uuid:pk>/resolve/", KnowledgeGapResolveView.as_view(), name="admin-quality-gap-resolve"),
    path("quality/gaps/<uuid:pk>/reopen/", KnowledgeGapReopenView.as_view(), name="admin-quality-gap-reopen"),
    path("reports/knowledge-quality/", KnowledgeQualityReportView.as_view(), name="admin-report-knowledge-quality"),
    path("reports/export/", ComplianceExportView.as_view(), name="admin-report-export"),
    path("reports/export-jobs/", ComplianceExportJobListCreateView.as_view(), name="admin-report-export-jobs"),
    path("reports/export-jobs/<uuid:pk>/", ComplianceExportJobDetailView.as_view(), name="admin-report-export-job-detail"),
    path("reports/export-jobs/<uuid:pk>/download/", ComplianceExportJobDownloadView.as_view(), name="admin-report-export-job-download"),
    path("reports/export-jobs/<uuid:pk>/retry/", ComplianceExportJobRetryView.as_view(), name="admin-report-export-job-retry"),
]
