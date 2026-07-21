# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Knowledge URLs — V4.2: Added batch upload endpoints."""

from django.urls import path
from .views import (
    DocumentListCreateView,
    DocumentDetailView,
    DocumentDownloadView,
    DocumentReindexView,
    DocumentChunksView,
    CategoryListView,
    AnswerTemplateListView,
    AnswerTemplateDetailView,
    DocumentTextEditView,
    DocumentPreviewDiffView,
    DocumentVersionCreateView,
    DocumentRollbackView,
)
from .batch_views import BatchDocumentUploadView, BatchImportResultDetailView

urlpatterns = [
    path("", DocumentListCreateView.as_view(), name="document-list"),
    path("<uuid:pk>/", DocumentDetailView.as_view(), name="document-detail"),
    path("<uuid:pk>/download/", DocumentDownloadView.as_view(), name="document-download"),
    path("<uuid:pk>/reindex/", DocumentReindexView.as_view(), name="document-reindex"),
    path("<uuid:document_id>/chunks/", DocumentChunksView.as_view(), name="document-chunks"),
    path("categories/", CategoryListView.as_view(), name="category-list"),
    path("templates/", AnswerTemplateListView.as_view(), name="template-list"),
    path("templates/<uuid:pk>/", AnswerTemplateDetailView.as_view(), name="template-detail"),
    # V4.2 KB-V4.2-BATCH-001~012: Batch upload endpoints
    path("batch/upload/", BatchDocumentUploadView.as_view(), name="batch-upload"),
    path("batch/result/<uuid:pk>/", BatchImportResultDetailView.as_view(), name="batch-result"),
    # Part 1 (§1.10): KB version化 endpoints
    path("<uuid:pk>/text/", DocumentTextEditView.as_view(), name="document-text-edit"),
    path("<uuid:pk>/preview-diff/", DocumentPreviewDiffView.as_view(), name="document-preview-diff"),
    path("<uuid:pk>/versions/", DocumentVersionCreateView.as_view(), name="document-versions"),
    path("<uuid:pk>/rollback/", DocumentRollbackView.as_view(), name="document-rollback"),
]
