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
    admin_space_archive,
    admin_space_list,
    admin_space_restore,
    organization_archive,
    organization_restore,
    space_access_request_approve,
    space_access_request_reject,
    ScopedAdminUserListView,
    scoped_user_assignment,
    ModelProfileListCreateView,
    governance_policies,
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
from apps.knowledge.platform_views import platform_document_metadata
from apps.rbac.offboarding import offboard_user, offboarding_admin_successor_candidates, offboarding_impact
from apps.rbac.views import expired_test_principals
from .governed_views import (
    admin_governed_request_approve,
    admin_governed_request_impact,
    admin_governed_request_reject,
    admin_governed_requests,
)
from .taxonomy_views import (
    admin_taxonomy_collection,
    admin_taxonomy_detail,
    workspace_creation_policies,
    workspace_creation_policy_transition,
)

urlpatterns = [
    path("test-principals/", expired_test_principals, name="admin-test-principals"),
    path("governed-requests/", admin_governed_requests, name="admin-governed-request-list"),
    path("documents/", platform_document_metadata, name="admin-platform-document-metadata"),
    path("governed-requests/<uuid:request_id>/impact/", admin_governed_request_impact, name="admin-governed-request-impact"),
    path("governed-requests/<uuid:request_id>/approve/", admin_governed_request_approve, name="admin-governed-request-approve"),
    path("governed-requests/<uuid:request_id>/reject/", admin_governed_request_reject, name="admin-governed-request-reject"),
    path("taxonomy/<str:kind>/", admin_taxonomy_collection, name="admin-taxonomy-collection"),
    path("taxonomy/<str:kind>/<uuid:item_id>/", admin_taxonomy_detail, name="admin-taxonomy-detail"),
    path("workspace-creation-policies/", workspace_creation_policies, name="admin-workspace-creation-policy-list"),
    path("workspace-creation-policies/<uuid:policy_id>/<str:action>/", workspace_creation_policy_transition, name="admin-workspace-creation-policy-transition"),
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
    path("spaces/<uuid:pk>/access-requests/<uuid:request_id>/reject/", space_access_request_reject, name="admin-space-access-request-reject"),
    path("users/", ScopedAdminUserListView.as_view(), name="admin-scoped-user-list"),
    path("users/<uuid:user_id>/assignments/", scoped_user_assignment, name="admin-scoped-user-assignment"),
    path("users/<uuid:user_id>/offboarding-impact/", offboarding_impact, name="admin-user-offboarding-impact"),
    path("users/<uuid:user_id>/offboarding-admin-candidates/", offboarding_admin_successor_candidates, name="admin-user-offboarding-admin-candidates"),
    path("users/<uuid:user_id>/offboard/", offboard_user, name="admin-user-offboard"),
    path("model-profiles/", ModelProfileListCreateView.as_view(), name="admin-model-profiles"),
    path("governance/policies/", governance_policies, name="admin-governance-policies"),
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
    # V7.5 Admin workspace overview
    path("spaces/", admin_space_list, name="admin-space-list"),
    path("spaces/<uuid:pk>/archive/", admin_space_archive, name="admin-space-archive"),
    path("spaces/<uuid:pk>/restore/", admin_space_restore, name="admin-space-restore"),
]
