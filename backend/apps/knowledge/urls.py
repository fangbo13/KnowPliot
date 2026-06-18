"""Knowledge URLs."""

from django.urls import path
from .views import (
    DocumentListCreateView,
    DocumentDetailView,
    DocumentReindexView,
    DocumentChunksView,
    CategoryListView,
    AnswerTemplateListView,
    AnswerTemplateDetailView,
)

urlpatterns = [
    path("", DocumentListCreateView.as_view(), name="document-list"),
    path("<uuid:pk>/", DocumentDetailView.as_view(), name="document-detail"),
    path("<uuid:pk>/reindex/", DocumentReindexView.as_view(), name="document-reindex"),
    path("<uuid:document_id>/chunks/", DocumentChunksView.as_view(), name="document-chunks"),
    path("categories/", CategoryListView.as_view(), name="category-list"),
    path("templates/", AnswerTemplateListView.as_view(), name="template-list"),
    path("templates/<uuid:pk>/", AnswerTemplateDetailView.as_view(), name="template-detail"),
]
