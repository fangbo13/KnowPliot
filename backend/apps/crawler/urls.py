# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Crawler URL configuration — V4.1 KB-V4.1-011~017."""

from django.urls import path
from .views import (
    CrawlRequestView,
    CrawledDocumentListView,
    CrawledDocumentDetailView,
    CrawledDocumentWithdrawView,
    CrawlWithdrawByURLView,
)

urlpatterns = [
    path("crawl/", CrawlRequestView.as_view(), name="crawl-submit"),
    path("", CrawledDocumentListView.as_view(), name="crawl-list"),
    path("<uuid:pk>/", CrawledDocumentDetailView.as_view(), name="crawl-detail"),
    path("<uuid:pk>/withdraw/", CrawledDocumentWithdrawView.as_view(), name="crawl-withdraw"),
    path("withdraw-by-url/", CrawlWithdrawByURLView.as_view(), name="crawl-withdraw-by-url"),
]
