# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Migration-command contracts for unscoped legacy administrator flags."""

import json
from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.rbac.models import Role, UserRole
from apps.spaces.models import (
    BusinessLine,
    KnowledgeSpace,
    Organization,
    OrganizationMembership,
    SpaceMembership,
)

User = get_user_model()


class LegacyAdministratorScopeCommandTest(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Legacy command organization",
            slug="legacy-command",
        )
        self.business_line = BusinessLine.objects.create(
            organization=self.organization,
            name="Legacy command line",
            code="LEGACY-CMD",
        )
        self.space = KnowledgeSpace.objects.create(
            organization=self.organization,
            business_line=self.business_line,
            name="Legacy command space",
            code="legacy-command-space",
        )
        self.space_user = User.objects.create_user(
            email="legacy-space@example.test",
            username="legacy-space",
            password="not-used",
            is_hr_admin=True,
        )
        self.organization_user = User.objects.create_user(
            email="legacy-organization@example.test",
            username="legacy-organization",
            password="not-used",
        )
        hr_role = Role.objects.create(name="hr", label="Legacy HR", scope="content")
        UserRole.objects.create(user=self.organization_user, role=hr_role)
        self.business_user = User.objects.create_user(
            email="legacy-business@example.test",
            username="legacy-business",
            password="not-used",
            is_hr_admin=True,
        )
        self.unscoped_user = User.objects.create_user(
            email="legacy-unscoped@example.test",
            username="legacy-unscoped",
            password="not-used",
            is_hr_admin=True,
        )
        self.nonlegacy_user = User.objects.create_user(
            email="ordinary@example.test",
            username="ordinary",
            password="not-used",
        )
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)

    def write_mapping(self, mappings):
        path = Path(self.temporary_directory.name) / "mapping.json"
        path.write_text(
            json.dumps({"version": 1, "mappings": mappings}),
            encoding="utf-8",
        )
        return path

    def all_mappings(self):
        return [
            {
                "user_id": str(self.space_user.id),
                "scope_type": "space",
                "scope_id": str(self.space.id),
                "role": "knowledge_admin",
            },
            {
                "user_id": str(self.organization_user.id),
                "scope_type": "organization",
                "scope_id": str(self.organization.id),
                "role": "org_admin",
            },
            {
                "user_id": str(self.business_user.id),
                "scope_type": "business_line",
                "scope_id": str(self.business_line.id),
                "role": "business_admin",
            },
        ]

    def test_dry_run_is_default_writes_no_grants_and_emits_stable_exception_report(self):
        mapping_path = self.write_mapping(self.all_mappings())
        exception_path = Path(self.temporary_directory.name) / "exceptions.json"
        stdout = StringIO()

        call_command(
            "audit_legacy_admin_scopes",
            mapping_file=str(mapping_path),
            exception_report=str(exception_path),
            stdout=stdout,
        )

        self.assertFalse(SpaceMembership.objects.filter(user=self.space_user).exists())
        self.assertFalse(
            OrganizationMembership.objects.filter(
                user__in=[self.organization_user, self.business_user]
            ).exists()
        )
        self.assertEqual(AuditLog.objects.filter(action="role_assign").count(), 0)
        output = stdout.getvalue()
        self.assertIn("mode=dry-run", output)
        self.assertIn("mapped=3", output)
        self.assertIn("exceptions=1", output)
        self.assertNotIn(self.space_user.email, output)
        report = json.loads(exception_path.read_text(encoding="utf-8"))
        self.assertEqual(report, {"unscoped_user_ids": [str(self.unscoped_user.id)]})

    def test_apply_creates_only_explicit_scopes_and_is_idempotently_audited(self):
        mapping_path = self.write_mapping(self.all_mappings())
        first_stdout = StringIO()

        call_command(
            "audit_legacy_admin_scopes",
            mapping_file=str(mapping_path),
            apply=True,
            stdout=first_stdout,
        )

        self.assertTrue(
            SpaceMembership.objects.filter(
                user=self.space_user,
                space=self.space,
                role=SpaceMembership.ROLE_KNOWLEDGE_ADMIN,
                status="active",
            ).exists()
        )
        self.assertTrue(
            OrganizationMembership.objects.filter(
                user=self.organization_user,
                organization=self.organization,
                business_line=None,
                role=OrganizationMembership.ROLE_ORG_ADMIN,
                is_active=True,
            ).exists()
        )
        self.assertTrue(
            OrganizationMembership.objects.filter(
                user=self.business_user,
                organization=self.organization,
                business_line=self.business_line,
                role=OrganizationMembership.ROLE_BUSINESS_ADMIN,
                is_active=True,
            ).exists()
        )
        self.assertFalse(SpaceMembership.objects.filter(user=self.unscoped_user).exists())
        self.assertFalse(
            OrganizationMembership.objects.filter(user=self.unscoped_user).exists()
        )
        self.assertFalse(
            SpaceMembership.objects.filter(user=self.nonlegacy_user).exists()
        )
        self.assertEqual(AuditLog.objects.filter(action="role_assign").count(), 3)
        self.assertIn("created=3", first_stdout.getvalue())

        second_stdout = StringIO()
        call_command(
            "audit_legacy_admin_scopes",
            mapping_file=str(mapping_path),
            apply=True,
            stdout=second_stdout,
        )

        self.assertEqual(AuditLog.objects.filter(action="role_assign").count(), 3)
        self.assertIn("created=0", second_stdout.getvalue())
        self.assertIn("unchanged=3", second_stdout.getvalue())

    def test_apply_requires_mapping_file_and_rejects_nonlegacy_or_invalid_scope(self):
        with self.assertRaises(CommandError):
            call_command("audit_legacy_admin_scopes", apply=True, stdout=StringIO())

        invalid_user_mapping = self.write_mapping(
            [
                {
                    "user_id": str(self.nonlegacy_user.id),
                    "scope_type": "space",
                    "scope_id": str(self.space.id),
                    "role": "knowledge_admin",
                }
            ]
        )
        with self.assertRaises(CommandError):
            call_command(
                "audit_legacy_admin_scopes",
                mapping_file=str(invalid_user_mapping),
                apply=True,
                stdout=StringIO(),
            )

        invalid_role_mapping = self.write_mapping(
            [
                {
                    "user_id": str(self.space_user.id),
                    "scope_type": "space",
                    "scope_id": str(self.space.id),
                    "role": "super_admin",
                }
            ]
        )
        with self.assertRaises(CommandError):
            call_command(
                "audit_legacy_admin_scopes",
                mapping_file=str(invalid_role_mapping),
                apply=True,
                stdout=StringIO(),
            )

        self.assertFalse(SpaceMembership.objects.filter(user=self.space_user).exists())
        self.assertEqual(AuditLog.objects.filter(action="role_assign").count(), 0)

    def test_conflicting_roles_for_the_same_explicit_scope_are_rejected(self):
        mapping_path = self.write_mapping(
            [
                {
                    "user_id": str(self.space_user.id),
                    "scope_type": "space",
                    "scope_id": str(self.space.id),
                    "role": "knowledge_admin",
                },
                {
                    "user_id": str(self.space_user.id),
                    "scope_type": "space",
                    "scope_id": str(self.space.id),
                    "role": "reviewer",
                },
            ]
        )

        with self.assertRaises(CommandError):
            call_command(
                "audit_legacy_admin_scopes",
                mapping_file=str(mapping_path),
                apply=True,
                stdout=StringIO(),
            )

        self.assertFalse(SpaceMembership.objects.filter(user=self.space_user).exists())
        self.assertEqual(AuditLog.objects.filter(action="role_assign").count(), 0)

    def test_existing_different_role_rejects_the_entire_apply_before_any_write(self):
        existing = SpaceMembership.objects.create(
            user=self.space_user,
            space=self.space,
            role=SpaceMembership.ROLE_OWNER,
            status="active",
        )
        mapping_path = self.write_mapping(
            [
                {
                    "user_id": str(self.space_user.id),
                    "scope_type": "space",
                    "scope_id": str(self.space.id),
                    "role": "reviewer",
                },
                {
                    "user_id": str(self.organization_user.id),
                    "scope_type": "organization",
                    "scope_id": str(self.organization.id),
                    "role": "org_admin",
                },
            ]
        )

        with self.assertRaises(CommandError):
            call_command(
                "audit_legacy_admin_scopes",
                mapping_file=str(mapping_path),
                apply=True,
                stdout=StringIO(),
            )

        existing.refresh_from_db()
        self.assertEqual(existing.role, SpaceMembership.ROLE_OWNER)
        self.assertEqual(existing.status, "active")
        self.assertFalse(
            OrganizationMembership.objects.filter(user=self.organization_user).exists()
        )
        self.assertEqual(AuditLog.objects.filter(action="role_assign").count(), 0)

    def test_revoked_or_expired_existing_grants_are_conflicts_not_reactivated(self):
        revoked = SpaceMembership.objects.create(
            user=self.space_user,
            space=self.space,
            role=SpaceMembership.ROLE_KNOWLEDGE_ADMIN,
            status="revoked",
        )
        expired_space = SpaceMembership.objects.create(
            user=self.business_user,
            space=self.space,
            role=SpaceMembership.ROLE_KNOWLEDGE_ADMIN,
            status="active",
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        expired_org = OrganizationMembership.objects.create(
            user=self.organization_user,
            organization=self.organization,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        mapping_path = self.write_mapping(
            [
                {
                    "user_id": str(self.space_user.id),
                    "scope_type": "space",
                    "scope_id": str(self.space.id),
                    "role": "knowledge_admin",
                },
                {
                    "user_id": str(self.business_user.id),
                    "scope_type": "space",
                    "scope_id": str(self.space.id),
                    "role": "knowledge_admin",
                },
                {
                    "user_id": str(self.organization_user.id),
                    "scope_type": "organization",
                    "scope_id": str(self.organization.id),
                    "role": "org_admin",
                },
            ]
        )

        with self.assertRaises(CommandError):
            call_command(
                "audit_legacy_admin_scopes",
                mapping_file=str(mapping_path),
                apply=True,
                stdout=StringIO(),
            )

        revoked.refresh_from_db()
        expired_space.refresh_from_db()
        expired_org.refresh_from_db()
        self.assertEqual(revoked.status, "revoked")
        self.assertIsNotNone(expired_space.expires_at)
        self.assertIsNotNone(expired_org.expires_at)
        self.assertEqual(AuditLog.objects.filter(action="role_assign").count(), 0)

    def test_existing_effective_explicit_scopes_are_not_reported_as_unscoped(self):
        SpaceMembership.objects.create(
            user=self.unscoped_user,
            space=self.space,
            role=SpaceMembership.ROLE_MEMBER,
            status="active",
        )
        OrganizationMembership.objects.create(
            user=self.organization_user,
            organization=self.organization,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
            expires_at=timezone.now() + timedelta(days=1),
        )
        exception_path = Path(self.temporary_directory.name) / "existing-scopes.json"
        stdout = StringIO()

        call_command(
            "audit_legacy_admin_scopes",
            exception_report=str(exception_path),
            stdout=stdout,
        )

        report = json.loads(exception_path.read_text(encoding="utf-8"))
        self.assertNotIn(str(self.unscoped_user.id), report["unscoped_user_ids"])
        self.assertNotIn(str(self.organization_user.id), report["unscoped_user_ids"])
        self.assertIn("already_scoped=2", stdout.getvalue())
        self.assertEqual(AuditLog.objects.filter(action="role_assign").count(), 0)

    @override_settings(SERVICE_LINE_DEFAULT_SPACE={})
    def test_seed_identity_no_longer_promotes_unscoped_hr_to_general(self):
        user = User.objects.create_user(
            email="legacy-seed@example.test",
            username="legacy-seed",
            password="not-used",
            is_hr_admin=True,
        )

        call_command("seed_identity", stdout=StringIO())

        self.assertFalse(SpaceMembership.objects.filter(user=user).exists())
