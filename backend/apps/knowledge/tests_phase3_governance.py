# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Phase 3 knowledge-governance regression tests.

Run with:
    python manage.py test apps.knowledge.tests_phase3_governance \
        --settings=config.settings.local_test
"""

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZIP_STORED, ZipFile

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.core.validators import validate_file_content_type
from apps.knowledge.batch import validate_inner_file_type, validate_zip_content
from apps.knowledge.models import Document
from apps.knowledge.serializers import DocumentSerializer
from apps.spaces.models import KnowledgeSpace, Organization, SpaceMembership


User = get_user_model()


def make_docx_bytes() -> bytes:
    """Build a minimal DOCX package without relying on test fixture files."""
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_STORED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            (
                '<?xml version="1.0"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Override PartName="/word/document.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.'
                'wordprocessingml.document.main+xml"/>'
                "</Types>"
            ),
        )
        archive.writestr(
            "_rels/.rels",
            (
                '<?xml version="1.0"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="word/document.xml"/>'
                "</Relationships>"
            ),
        )
        archive.writestr(
            "word/document.xml",
            (
                '<?xml version="1.0"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>Phase 3B</w:t></w:r></w:p></w:body>"
                "</w:document>"
            ),
        )
        archive.writestr("word/media/padding.bin", bytes(range(256)) * 8)
    return buffer.getvalue()


class FileValidationPolicyTest(SimpleTestCase):
    """Single and batch upload must share one current-version file policy."""

    text_payload = ("KnowPilot safe UTF-8 content.\n" * 64).encode("utf-8")
    pdf_payload = b"%PDF-1.7\n" + (b"0 0 obj\n<<>>\nendobj\n" * 64)

    def serializer_for(self, filename, content, **data):
        payload = {
            "file": SimpleUploadedFile(
                filename,
                content,
                content_type="application/octet-stream",
            ),
            **data,
        }
        return DocumentSerializer(data=payload)

    def test_pdf_type_and_size_are_derived_from_upload(self):
        serializer = self.serializer_for("policy.pdf", self.pdf_payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["file_type"], "pdf")
        self.assertEqual(serializer.validated_data["file_size"], len(self.pdf_payload))

    def test_docx_type_is_derived_from_upload(self):
        serializer = self.serializer_for("policy.docx", make_docx_bytes())

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["file_type"], "docx")

    def test_html_type_is_derived_from_safe_text_upload(self):
        serializer = self.serializer_for(
            "policy.html",
            b"<html><body>" + self.text_payload + b"</body></html>",
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["file_type"], "html")

    def test_txt_type_is_derived_from_safe_text_upload(self):
        serializer = self.serializer_for("policy.txt", self.text_payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["file_type"], "txt")

    def test_markdown_type_is_derived_from_safe_text_upload(self):
        serializer = self.serializer_for(
            "policy.markdown",
            b"# Phase 3B\n\n" + self.text_payload,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["file_type"], "md")

    def test_binary_bytes_without_known_signature_are_rejected_as_text(self):
        serializer = self.serializer_for(
            "payload.txt",
            b"\x00\x01\x02\x03" * 300,
            title="Binary",
            file_type="txt",
            file_size=1200,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("file", serializer.errors)

    def test_content_signature_must_match_filename_extension(self):
        serializer = self.serializer_for(
            "renamed.docx",
            self.pdf_payload,
            title="Renamed PDF",
            file_type="docx",
            file_size=len(self.pdf_payload),
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("file", serializer.errors)

    def test_supplied_type_must_match_filename_extension(self):
        serializer = self.serializer_for(
            "actually-text.pdf",
            self.text_payload,
            title="Mismatch",
            file_type="txt",
            file_size=len(self.text_payload),
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("file_type", serializer.errors)

    def test_actual_size_overrides_false_client_value(self):
        serializer = self.serializer_for(
            "actual-size.txt",
            self.text_payload,
            title="Actual size",
            file_type="txt",
            file_size=1,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["file_size"], len(self.text_payload))

    def test_metadata_cannot_change_without_replacing_file(self):
        document = Document(
            title="Existing",
            file="documents/existing.txt",
            file_type="txt",
            file_size=len(self.text_payload),
        )
        serializer = DocumentSerializer(
            document,
            data={"file_type": "pdf", "file_size": 1},
            partial=True,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("file_type", serializer.errors)
        self.assertIn("file_size", serializer.errors)

    def test_missing_title_defaults_to_sanitized_filename(self):
        serializer = self.serializer_for(
            "<script>Policy</script>.txt",
            self.text_payload,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("<", serializer.validated_data["title"])
        self.assertTrue(serializer.validated_data["title"])

    def test_unsupported_current_version_extensions_are_rejected(self):
        for extension in ("doc", "csv", "xlsx", "pptx", "exe"):
            with self.subTest(extension=extension):
                serializer = self.serializer_for(
                    f"unsupported.{extension}",
                    self.text_payload,
                    title="Unsupported",
                    file_type="txt",
                    file_size=len(self.text_payload),
                )
                self.assertFalse(serializer.is_valid())
                self.assertIn("file", serializer.errors)

    def test_batch_unknown_extension_is_rejected_instead_of_falling_back_to_txt(self):
        archive_buffer = BytesIO()
        with ZipFile(archive_buffer, "w", ZIP_STORED) as archive:
            archive.writestr("payload.exe", self.text_payload)
        archive_upload = SimpleUploadedFile(
            "batch.zip",
            archive_buffer.getvalue(),
            content_type="application/zip",
        )

        with self.assertRaises(DjangoValidationError):
            validate_zip_content(archive_upload)

    def test_batch_accepts_every_current_version_format(self):
        archive_buffer = BytesIO()
        with ZipFile(archive_buffer, "w", ZIP_STORED) as archive:
            archive.writestr("policy.pdf", self.pdf_payload)
            archive.writestr("policy.docx", make_docx_bytes())
            archive.writestr(
                "policy.html",
                b"<html><body>" + self.text_payload + b"</body></html>",
            )
            archive.writestr("policy.txt", self.text_payload)
            archive.writestr(
                "policy.md",
                b"# Phase 3B\n\n" + self.text_payload,
            )
        archive_upload = SimpleUploadedFile(
            "batch.zip",
            archive_buffer.getvalue(),
            content_type="application/zip",
        )

        result = validate_zip_content(archive_upload)

        self.assertEqual(result["rejected_count"], 0)
        self.assertEqual(
            {entry["extension"] for entry in result["valid_files"]},
            {"pdf", "docx", "html", "txt", "md"},
        )

    def test_legacy_single_file_validator_rejects_binary_text(self):
        upload = SimpleUploadedFile(
            "payload.txt",
            b"\x00\x01\x02\x03" * 300,
            content_type="text/plain",
        )

        with self.assertRaises(DjangoValidationError):
            validate_file_content_type(upload, "txt")

    def test_legacy_batch_validator_uses_current_text_policy(self):
        binary_valid, _ = validate_inner_file_type(
            b"\x00\x01\x02\x03" * 300,
            "txt",
        )
        markdown_valid, _ = validate_inner_file_type(
            b"# Safe Markdown\n" + self.text_payload,
            "md",
        )

        self.assertFalse(binary_valid)
        self.assertTrue(markdown_valid)


class DocumentUploadPolicyIntegrationTest(APITestCase):
    """The real upload endpoint must work with server-derived metadata."""

    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(
            name="Upload Policy Organization",
            slug="upload-policy-organization",
        )
        cls.space = KnowledgeSpace.objects.create(
            organization=cls.organization,
            name="Upload Policy Space",
            code="upload-policy-space",
            status="active",
            visibility="private",
        )
        cls.knowledge_admin = User.objects.create_user(
            username="upload-policy-admin",
            email="upload-policy-admin@example.com",
            password="test-password",
        )
        SpaceMembership.objects.create(
            space=cls.space,
            user=cls.knowledge_admin,
            role=SpaceMembership.ROLE_KNOWLEDGE_ADMIN,
            status="active",
        )

    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        media_override.enable()
        self.addCleanup(media_override.disable)

    @patch("apps.rag.services.ingest_document.delay")
    def test_file_only_upload_derives_metadata_and_starts_ingestion(self, delay):
        content = FileValidationPolicyTest.text_payload
        self.client.force_authenticate(self.knowledge_admin)

        response = self.client.post(
            "/api/v1/documents/",
            {
                "file": SimpleUploadedFile(
                    "policy.txt",
                    content,
                    content_type="text/plain",
                ),
            },
            format="multipart",
            HTTP_X_SPACE_ID=str(self.space.id),
        )

        self.assertEqual(response.status_code, 201, response.json())
        document = Document.objects.get(id=response.json()["id"])
        self.assertEqual(document.title, "policy")
        self.assertEqual(document.file_type, "txt")
        self.assertEqual(document.file_size, len(content))
        self.assertEqual(document.space, self.space)
        delay.assert_called_once_with(str(document.id))


class DocumentDownloadSecurityTest(APITestCase):
    """Document delivery must enforce the document space's download permission."""

    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(
            name="Phase 3 Organization",
            slug="phase-3-organization",
        )
        cls.space = KnowledgeSpace.objects.create(
            organization=cls.organization,
            name="Protected Knowledge",
            code="phase-3-protected",
            status="active",
            visibility="private",
        )
        cls.other_space = KnowledgeSpace.objects.create(
            organization=cls.organization,
            name="Other Knowledge",
            code="phase-3-other",
            status="active",
            visibility="private",
        )
        cls.reviewer = User.objects.create_user(
            username="phase3-reviewer",
            email="phase3-reviewer@example.com",
            password="test-password",
        )
        cls.member = User.objects.create_user(
            username="phase3-member",
            email="phase3-member@example.com",
            password="test-password",
        )
        cls.outsider = User.objects.create_user(
            username="phase3-outsider",
            email="phase3-outsider@example.com",
            password="test-password",
        )
        SpaceMembership.objects.create(
            space=cls.space,
            user=cls.reviewer,
            role=SpaceMembership.ROLE_REVIEWER,
            status="active",
        )
        SpaceMembership.objects.create(
            space=cls.other_space,
            user=cls.reviewer,
            role=SpaceMembership.ROLE_REVIEWER,
            status="active",
        )
        SpaceMembership.objects.create(
            space=cls.space,
            user=cls.member,
            role=SpaceMembership.ROLE_MEMBER,
            status="active",
        )

    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        media_override.enable()
        self.addCleanup(media_override.disable)

        self.file_bytes = b"Phase 3 protected source content."
        self.document = Document.objects.create(
            space=self.space,
            title="Protected source",
            file=SimpleUploadedFile(
                "protected-source.txt",
                self.file_bytes,
                content_type="text/plain",
            ),
            file_type="txt",
            file_size=len(self.file_bytes),
            status="active",
            uploaded_by=self.reviewer,
        )

    def download_url(self, document=None):
        document = document or self.document
        return f"/api/v1/documents/{document.id}/download/"

    def test_reviewer_download_streams_file_with_security_headers(self):
        self.client.force_authenticate(self.reviewer)

        response = self.client.get(
            self.download_url(),
            HTTP_X_SPACE_ID=str(self.space.id),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), self.file_bytes)
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_successful_download_is_audited(self):
        self.client.force_authenticate(self.reviewer)

        response = self.client.get(
            self.download_url(),
            HTTP_X_SPACE_ID=str(self.space.id),
        )

        self.assertEqual(response.status_code, 200)
        response.close()
        log = AuditLog.objects.get(
            user=self.reviewer,
            action="document_download",
            target_id=self.document.id,
        )
        self.assertEqual(log.details["result"], "success")
        self.assertEqual(log.details["space_id"], str(self.space.id))

    def test_member_without_download_permission_gets_403_and_audit_log(self):
        self.client.force_authenticate(self.member)

        response = self.client.get(
            self.download_url(),
            HTTP_X_SPACE_ID=str(self.space.id),
        )

        self.assertEqual(response.status_code, 403)
        log = AuditLog.objects.get(
            user=self.member,
            action="permission_denied",
            target_id=self.document.id,
        )
        self.assertEqual(log.details["permission"], "document.download")
        self.assertEqual(log.details["result"], "denied")

    def test_outsider_cannot_discover_document(self):
        self.client.force_authenticate(self.outsider)

        response = self.client.get(
            self.download_url(),
            HTTP_X_SPACE_ID=str(self.space.id),
        )

        self.assertEqual(response.status_code, 404)

    def test_active_space_mismatch_is_concealed(self):
        self.client.force_authenticate(self.reviewer)

        response = self.client.get(
            self.download_url(),
            HTTP_X_SPACE_ID=str(self.other_space.id),
        )

        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_download_is_rejected(self):
        response = self.client.get(
            self.download_url(),
            HTTP_X_SPACE_ID=str(self.space.id),
        )

        self.assertEqual(response.status_code, 401)

    def test_missing_storage_object_returns_404_without_path_disclosure(self):
        stored_path = Path(self.document.file.path)
        stored_path.unlink()
        self.client.force_authenticate(self.reviewer)

        response = self.client.get(
            self.download_url(),
            HTTP_X_SPACE_ID=str(self.space.id),
        )

        self.assertEqual(response.status_code, 404)
        self.assertNotIn(str(stored_path), response.content.decode("utf-8"))

    def test_document_json_hides_raw_media_url_and_exposes_download_url(self):
        self.client.force_authenticate(self.reviewer)

        response = self.client.get(
            f"/api/v1/documents/{self.document.id}/",
            HTTP_X_SPACE_ID=str(self.space.id),
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("file", response.json())
        self.assertEqual(
            response.json()["download_url"],
            f"http://testserver{self.download_url()}",
        )
