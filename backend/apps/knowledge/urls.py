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
    DocumentTemplateView,
    DocumentConvertView,
    document_links,
    link_suggest,
)
from .batch_views import BatchDocumentUploadView, BatchImportResultDetailView
from . import review_views, taxonomy_views, viz_views, library_views

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
    # KB-12-Features §8: Markdown document templates (list + detail by slug)
    path("document-templates/", DocumentTemplateView.as_view(), name="document-template-list"),
    path("document-templates/<slug:slug>/", DocumentTemplateView.as_view(), name="document-template-detail"),
    # KB-12-Features §9: Synchronous Word/PDF→Markdown conversion
    path("convert/", DocumentConvertView.as_view(), name="document-convert"),
    # Knowledge iteration spec §2: taxonomy (dimensions/terms/tags/ownership)
    path("taxonomy/dimensions/", taxonomy_views.taxonomy_dimensions, name="taxonomy-dimensions"),
    path("taxonomy/dimensions/<uuid:pk>/", taxonomy_views.taxonomy_dimension_detail, name="taxonomy-dimension-detail"),
    path("taxonomy/terms/", taxonomy_views.taxonomy_terms, name="taxonomy-terms"),
    path("taxonomy/terms/<uuid:pk>/", taxonomy_views.taxonomy_term_detail, name="taxonomy-term-detail"),
    # KB optimization spec §3.1: presets catalog + one-click default seeding
    path("taxonomy/presets/", taxonomy_views.taxonomy_presets, name="taxonomy-presets"),
    path("taxonomy/seed-defaults/", taxonomy_views.taxonomy_seed_defaults, name="taxonomy-seed-defaults"),
    path("<uuid:pk>/tags/", taxonomy_views.document_tags, name="document-tags"),
    path("term-owners/", taxonomy_views.term_owners, name="term-owners"),
    path("term-owners/<uuid:pk>/", taxonomy_views.term_owner_delete, name="term-owner-delete"),
    path("my-terms/", taxonomy_views.my_terms, name="my-terms"),
    path("<uuid:pk>/confirm-fresh/", taxonomy_views.confirm_fresh, name="document-confirm-fresh"),
    # Knowledge iteration spec §3: review gate
    path("<uuid:pk>/submit-review/", review_views.submit_review, name="document-submit-review"),
    path("review-queue/", review_views.review_queue, name="review-queue"),
    path("reviews/<uuid:pk>/approve/", review_views.review_approve, name="review-approve"),
    path("reviews/<uuid:pk>/reject/", review_views.review_reject, name="review-reject"),
    # Knowledge iteration spec §5: visualization
    path("graph/", viz_views.knowledge_graph, name="knowledge-graph"),
    path("timeline/", viz_views.knowledge_timeline, name="knowledge-timeline"),
    path("dashboard/", viz_views.knowledge_dashboard, name="knowledge-dashboard"),
    # KB optimization spec §3.4: Obsidian-style backlinks
    path("<uuid:pk>/backlinks/", viz_views.document_backlinks, name="document-backlinks"),
    # KB/RAG audit spec P3 §B1: link tooling (autocomplete + outgoing links)
    path("link-suggest/", link_suggest, name="document-link-suggest"),
    path("<uuid:pk>/links/", document_links, name="document-links"),
    # KB optimization spec §3.2: platform-official reference libraries
    path("libraries/", library_views.libraries, name="reference-libraries"),
    path("libraries/catalog/", library_views.libraries_catalog, name="reference-libraries-catalog"),
    path("libraries/<uuid:pk>/", library_views.library_detail, name="reference-library-detail"),
    path("library-references/", library_views.library_references, name="space-library-references"),
    path("library-references/<uuid:pk>/", library_views.library_reference_detail, name="space-library-reference-detail"),
]
