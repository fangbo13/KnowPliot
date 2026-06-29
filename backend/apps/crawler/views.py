"""Crawler views — V4.1 KB-V4.1-011~017.

5 endpoints:
1. CrawlRequestView (POST) — submit URL for crawling, requires document.create
2. CrawledDocumentListView (GET) — list crawled documents, requires document.read
3. CrawledDocumentDetailView (GET) — detail view, requires document.read
4. CrawledDocumentWithdrawView (POST) — withdraw/takedown, requires document.delete
5. CrawlWithdrawByURLView (POST) — bulk withdraw by source_url, requires document.delete
"""

from rest_framework import generics, permissions, status
from rest_framework.response import Response

from apps.core.permissions import HasPermission
from apps.audit.views import create_audit_log
from .models import CrawledDocument
from .serializers import (
    CrawlRequestSerializer,
    CrawledDocumentSerializer,
    CrawledDocumentWithdrawSerializer,
)


class CrawlRequestView(generics.CreateAPIView):
    """Submit a URL for crawling — requires document.create permission.

    Creates a CrawledDocument record and triggers a Celery task for
    async processing (validate → fetch → clean → embed → store).
    """

    serializer_class = CrawlRequestSerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasPermission("document.create")]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        url = serializer.validated_data["url"]
        category_id = serializer.validated_data.get("category_id")
        internal_only = serializer.validated_data.get("internal_only", False)

        # Create CrawledDocument record
        crawl_doc = CrawledDocument.objects.create(
            source_url=url,
            submitted_by=request.user,
            internal_only=internal_only,
            crawl_status="pending",
        )

        # Trigger Celery task for async processing
        # V4.1: Use Celery's send_task to avoid import-based registration issues
        # when the worker uses gevent pool with Redis password authentication.
        from config.celery import app as celery_app
        try:
            celery_app.send_task(
                "apps.crawler.tasks.crawl_and_ingest",
                args=[str(crawl_doc.id)],
            )
        except Exception as exc:
            # If Celery is unavailable, mark as failed immediately
            crawl_doc.crawl_status = "failed"
            crawl_doc.error_message = f"Celery task dispatch failed: {exc}"
            crawl_doc.save(update_fields=["crawl_status", "error_message", "updated_at"])
            return Response(
                CrawledDocumentSerializer(crawl_doc).data,
                status=status.HTTP_201_CREATED,
            )

        # Audit log
        create_audit_log(
            user=request.user,
            action="document_crawl",
            target_type="CrawledDocument",
            target_id=str(crawl_doc.id),
            details={"url": url, "internal_only": internal_only},
            role_used="hr" if request.user.has_role("hr") else "admin",
            request=request,
        )

        return Response(
            CrawledDocumentSerializer(crawl_doc).data,
            status=status.HTTP_201_CREATED,
        )


class CrawledDocumentListView(generics.ListAPIView):
    """List crawled documents — requires document.read permission."""

    serializer_class = CrawledDocumentSerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasPermission("document.read")]

    def get_queryset(self):
        return CrawledDocument.objects.all().select_related("document", "submitted_by")


class CrawledDocumentDetailView(generics.RetrieveAPIView):
    """View crawled document details — requires document.read permission."""

    serializer_class = CrawledDocumentSerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasPermission("document.read")]

    def get_queryset(self):
        return CrawledDocument.objects.all()


class CrawledDocumentWithdrawView(generics.GenericAPIView):
    """Withdraw (takedown) a crawled document — KB-V4.1-017 copyright takedown.

    Marks the CrawledDocument as 'withdrawn' and the linked Document as 'expired'.
    This removes the content from active search while preserving the record.
    """

    serializer_class = CrawledDocumentWithdrawSerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasPermission("document.delete")]

    def get_queryset(self):
        return CrawledDocument.objects.all()

    def post(self, request, pk):
        crawl_doc = self.get_object()

        if crawl_doc.crawl_status == "withdrawn":
            return Response(
                {"detail": "Document already withdrawn."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update crawl status
        crawl_doc.crawl_status = "withdrawn"
        reason = request.data.get("reason", "")
        if reason:
            crawl_doc.copyright_disclaimer = reason
        crawl_doc.save(update_fields=["crawl_status", "copyright_disclaimer", "updated_at"])

        # Also mark linked Document as expired
        if crawl_doc.document:
            crawl_doc.document.status = "expired"
            crawl_doc.document.save(update_fields=["status"])

        # Audit log
        create_audit_log(
            user=request.user,
            action="document_crawl_withdraw",
            target_type="CrawledDocument",
            target_id=str(crawl_doc.id),
            details={"url": crawl_doc.source_url, "reason": reason},
            role_used="hr" if request.user.has_role("hr") else "admin",
            request=request,
        )

        return Response(
            CrawledDocumentSerializer(crawl_doc).data,
            status=status.HTTP_200_OK,
        )


class CrawlWithdrawByURLView(generics.GenericAPIView):
    """Bulk withdraw crawled documents by source_url — KB-V4.1-017.

    V4.2 SYS-V4.2-004: Added URL validation (CrawlURLValidator + max length).
    Previous: url parameter had no validation — could be used for long-string DoS
    or internal URL probing. Now: validates URL format, length, and SSRF checks
    (same as CrawlRequestView) to ensure consistency across all crawl endpoints.
    """

    serializer_class = CrawledDocumentWithdrawSerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasPermission("document.delete")]

    def post(self, request):
        url = request.data.get("url")
        if not url:
            return Response(
                {"detail": "URL parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # V4.2 SYS-V4.2-004: Validate URL format and length
        # Same validation as CrawlRequestView — ensures consistent protection
        from .validators import CrawlURLValidator, MAX_URL_LENGTH

        url_validator = CrawlURLValidator()

        # URL length check (prevent long-string DoS)
        if len(url) > MAX_URL_LENGTH:
            return Response(
                {"detail": f"URL exceeds maximum length of {MAX_URL_LENGTH} characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # URL format validation (protocol, hostname, SSRF)
        is_valid, reason = url_validator.validate(url)
        if not is_valid:
            return Response(
                {"detail": f"URL validation failed: {reason}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # V4.2 SYS-V4.2-019: Use transaction.atomic() + select_for_update()
        # Previous: individual updates without transaction — if concurrent crawl
        # creates new documents during withdrawal, same URL can have mixed status
        # (active + withdrawn). Now: atomic transaction + row-level lock prevents
        # concurrent modifications, ensuring consistent bulk withdrawal.
        from django.db import transaction

        with transaction.atomic():
            # select_for_update() locks rows until transaction commits
            crawl_docs = CrawledDocument.objects.filter(
                source_url=url,
                crawl_status="active",
            ).select_for_update()

            count = 0
            for crawl_doc in crawl_docs:
                crawl_doc.crawl_status = "withdrawn"
                reason = request.data.get("reason", "Bulk takedown by URL")
                crawl_doc.copyright_disclaimer = reason
                crawl_doc.save(update_fields=["crawl_status", "copyright_disclaimer", "updated_at"])

                if crawl_doc.document:
                    crawl_doc.document.status = "expired"
                    crawl_doc.document.save(update_fields=["status"])

                count += 1

        # Audit log
        create_audit_log(
            user=request.user,
            action="document_crawl_withdraw",
            target_type="CrawledDocument",
            target_id="",
            details={"url": url, "count_withdrawn": count, "bulk": True},
            role_used="hr" if request.user.has_role("hr") else "admin",
            request=request,
        )

        return Response(
            {"detail": f"Withdrawn {count} documents from {url}.", "count": count},
            status=status.HTTP_200_OK,
        )
