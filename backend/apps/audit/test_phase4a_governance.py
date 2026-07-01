"""Phase 4A scoped audit-governance regression tests."""

from uuid import uuid4

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.audit.views import create_audit_log
from apps.spaces.models import (
    BusinessLine,
    KnowledgeSpace,
    Organization,
    OrganizationMembership,
)


User = get_user_model()


class ScopedAuditGovernanceTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(name="Audit Org A", slug="audit-org-a")
        cls.org_b = Organization.objects.create(name="Audit Org B", slug="audit-org-b")
        cls.bl_a = BusinessLine.objects.create(
            organization=cls.org_a,
            name="Audit A",
            code="audit-a",
        )
        cls.bl_b = BusinessLine.objects.create(
            organization=cls.org_b,
            name="Audit B",
            code="audit-b",
        )
        cls.space_a = KnowledgeSpace.objects.create(
            organization=cls.org_a,
            business_line=cls.bl_a,
            name="Space A",
            code="audit-space-a",
        )
        cls.space_b = KnowledgeSpace.objects.create(
            organization=cls.org_b,
            business_line=cls.bl_b,
            name="Space B",
            code="audit-space-b",
        )
        cls.superuser = User.objects.create_superuser(
            username="audit-super",
            email="audit-super@example.com",
            password="test",
        )
        cls.org_admin = User.objects.create_user(
            username="audit-org-admin",
            email="audit-org-admin@example.com",
            password="test",
        )
        cls.business_admin = User.objects.create_user(
            username="audit-business-admin",
            email="audit-business-admin@example.com",
            password="test",
        )
        cls.legacy_hr = User.objects.create_user(
            username="audit-legacy-hr",
            email="audit-legacy-hr@example.com",
            password="test",
            is_hr_admin=True,
        )
        OrganizationMembership.objects.create(
            user=cls.org_admin,
            organization=cls.org_a,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )
        OrganizationMembership.objects.create(
            user=cls.business_admin,
            organization=cls.org_a,
            business_line=cls.bl_a,
            role=OrganizationMembership.ROLE_BUSINESS_ADMIN,
        )

    def setUp(self):
        self.log_a = AuditLog.objects.create(
            user=self.superuser,
            action="document_download",
            target_type="Document",
            target_id=uuid4(),
            organization_id=self.org_a.id,
            business_line_id=self.bl_a.id,
            space_id=self.space_a.id,
            result="success",
            role_used="super_admin",
        )
        self.log_b = AuditLog.objects.create(
            user=self.superuser,
            action="permission_denied",
            target_type="Document",
            target_id=uuid4(),
            organization_id=self.org_b.id,
            business_line_id=self.bl_b.id,
            space_id=self.space_b.id,
            result="denied",
        )
        self.unscoped = AuditLog.objects.create(
            user=self.superuser,
            action="user_login",
            target_type="User",
            target_id=self.superuser.id,
        )

    def get_logs(self, user, params=None):
        self.client.force_authenticate(user)
        return self.client.get("/api/v1/audit/logs/", params or {})

    def result_ids(self, response):
        body = response.json()
        self.assertIn("results", body)
        return {row["id"] for row in body["results"]}

    def test_platform_admin_sees_scoped_and_legacy_unscoped_logs(self):
        response = self.get_logs(self.superuser)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.result_ids(response),
            {str(self.log_a.id), str(self.log_b.id), str(self.unscoped.id)},
        )

    def test_org_admin_sees_only_its_organization_and_no_unscoped_logs(self):
        response = self.get_logs(self.org_admin)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.result_ids(response), {str(self.log_a.id)})

    def test_business_admin_sees_only_its_business_line(self):
        response = self.get_logs(self.business_admin)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.result_ids(response), {str(self.log_a.id)})

    def test_legacy_hr_flag_does_not_grant_global_audit_access(self):
        response = self.get_logs(self.legacy_hr)

        self.assertEqual(response.status_code, 403)

    def test_filters_and_serialized_scope_fields_are_available(self):
        response = self.get_logs(
            self.superuser,
            {
                "result": "denied",
                "organization": str(self.org_b.id),
                "business_line": str(self.bl_b.id),
                "space": str(self.space_b.id),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.result_ids(response), {str(self.log_b.id)})
        row = response.json()["results"][0]
        self.assertEqual(row["result"], "denied")
        self.assertEqual(row["organization_id"], str(self.org_b.id))
        self.assertEqual(row["business_line_id"], str(self.bl_b.id))
        self.assertEqual(row["space_id"], str(self.space_b.id))
        self.assertIn("role_used", row)

    def test_audit_log_api_is_read_only(self):
        self.client.force_authenticate(self.superuser)

        response = self.client.post(
            "/api/v1/audit/logs/",
            {"action": "config_change"},
            format="json",
        )

        self.assertEqual(response.status_code, 405)

    def test_create_audit_log_infers_scope_from_knowledge_space(self):
        log = create_audit_log(
            user=self.superuser,
            action="permission_denied",
            target_type="KnowledgeSpace",
            target_id=self.space_a.id,
            result="denied",
        )

        self.assertEqual(log.organization_id, self.org_a.id)
        self.assertEqual(log.business_line_id, self.bl_a.id)
        self.assertEqual(log.space_id, self.space_a.id)
        self.assertEqual(log.result, "denied")
