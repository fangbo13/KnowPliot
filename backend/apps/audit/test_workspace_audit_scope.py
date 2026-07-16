"""Workspace-scoped audit-list authorization contracts."""

from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.spaces.models import (
    BusinessLine,
    KnowledgeSpace,
    Organization,
    OrganizationMembership,
    SpaceMembership,
)

User = get_user_model()


class WorkspaceAuditScopeTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(
            name="Workspace audit organization",
            slug="workspace-audit",
        )
        cls.business_line = BusinessLine.objects.create(
            organization=cls.organization,
            name="Workspace audit line",
            code="WORKSPACE-AUDIT",
        )
        cls.space = KnowledgeSpace.objects.create(
            organization=cls.organization,
            business_line=cls.business_line,
            name="Audited workspace",
            code="audited-workspace",
        )
        cls.other_space = KnowledgeSpace.objects.create(
            organization=cls.organization,
            business_line=cls.business_line,
            name="Other workspace",
            code="other-audit-workspace",
        )
        cls.log = AuditLog.objects.create(
            action="space_update",
            target_type="KnowledgeSpace",
            target_id=cls.space.id,
            organization_id=cls.organization.id,
            business_line_id=cls.business_line.id,
            space_id=cls.space.id,
        )
        cls.other_log = AuditLog.objects.create(
            action="space_update",
            target_type="KnowledgeSpace",
            target_id=cls.other_space.id,
            organization_id=cls.organization.id,
            business_line_id=cls.business_line.id,
            space_id=cls.other_space.id,
        )
        cls.unscoped_log = AuditLog.objects.create(
            action="user_login",
            target_type="User",
        )

        cls.users = {}
        for role in (
            SpaceMembership.ROLE_OWNER,
            SpaceMembership.ROLE_REVIEWER,
            SpaceMembership.ROLE_KNOWLEDGE_ADMIN,
            SpaceMembership.ROLE_MEMBER,
            SpaceMembership.ROLE_GUEST,
        ):
            user = User.objects.create_user(
                username=f"workspace-audit-{role}",
                email=f"workspace-audit-{role}@example.test",
                password="not-used",
            )
            SpaceMembership.objects.create(user=user, space=cls.space, role=role)
            cls.users[role] = user

        cls.expired_owner = User.objects.create_user(
            username="workspace-audit-expired-owner",
            email="workspace-audit-expired-owner@example.test",
            password="not-used",
        )
        cls.expired_membership = SpaceMembership.objects.create(
            user=cls.expired_owner,
            space=cls.space,
            role=SpaceMembership.ROLE_OWNER,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        cls.org_admin = User.objects.create_user(
            username="workspace-audit-org-admin",
            email="workspace-audit-org-admin@example.test",
            password="not-used",
        )
        OrganizationMembership.objects.create(
            user=cls.org_admin,
            organization=cls.organization,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )
        cls.platform_admin = User.objects.create_superuser(
            username="workspace-audit-platform-admin",
            email="workspace-audit-platform-admin@example.test",
            password="not-used",
        )

    def get_logs(self, user, space_id=None):
        self.client.force_authenticate(user)
        params = {} if space_id is None else {"space": str(space_id)}
        return self.client.get("/api/v1/audit/logs/", params)

    def result_ids(self, response):
        return {row["id"] for row in response.json()["results"]}

    def test_owner_and_reviewer_may_read_only_the_requested_workspace_logs(self):
        for role in (SpaceMembership.ROLE_OWNER, SpaceMembership.ROLE_REVIEWER):
            with self.subTest(role=role):
                response = self.get_logs(self.users[role], self.space.id)

                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(self.result_ids(response), {str(self.log.id)})

    def test_workspace_roles_without_audit_permission_are_denied(self):
        for role in (
            SpaceMembership.ROLE_KNOWLEDGE_ADMIN,
            SpaceMembership.ROLE_MEMBER,
            SpaceMembership.ROLE_GUEST,
        ):
            with self.subTest(role=role):
                response = self.get_logs(self.users[role], self.space.id)

                self.assertEqual(response.status_code, 403)

    def test_workspace_roles_cannot_use_the_unqualified_global_audit_list(self):
        for role in (SpaceMembership.ROLE_OWNER, SpaceMembership.ROLE_REVIEWER):
            with self.subTest(role=role):
                response = self.get_logs(self.users[role])

                self.assertEqual(response.status_code, 403)

    def test_inaccessible_and_nonexistent_workspace_ids_do_not_disclose(self):
        owner = self.users[SpaceMembership.ROLE_OWNER]

        self.assertEqual(self.get_logs(owner, self.other_space.id).status_code, 404)
        self.assertEqual(self.get_logs(owner, uuid4()).status_code, 404)

    def test_query_workspace_cannot_be_authorized_by_a_different_header_workspace(self):
        owner = self.users[SpaceMembership.ROLE_OWNER]
        self.client.force_authenticate(owner)

        response = self.client.get(
            "/api/v1/audit/logs/",
            {"space": str(self.other_space.id)},
            HTTP_X_SPACE_ID=str(self.space.id),
        )

        self.assertEqual(response.status_code, 404)

    def test_expired_or_archived_workspace_scope_does_not_disclose(self):
        self.assertEqual(
            self.get_logs(self.expired_owner, self.space.id).status_code,
            404,
        )

        self.space.status = "archived"
        self.space.save(update_fields=["status"])
        owner = self.users[SpaceMembership.ROLE_OWNER]
        self.assertEqual(self.get_logs(owner, self.space.id).status_code, 404)

    def test_governance_and_platform_admins_keep_requested_workspace_access(self):
        for user in (self.org_admin, self.platform_admin):
            with self.subTest(user=user.username):
                response = self.get_logs(user, self.space.id)

                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(self.result_ids(response), {str(self.log.id)})
