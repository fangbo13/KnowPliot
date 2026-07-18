import io
import json

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from unittest.mock import patch
from django.test import TestCase

from apps.spaces.models import KnowledgeSpace, Organization, SpaceMembership


class OwnershipAuditCommandTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Audit Org", slug="audit-command-org")
        self.owner = get_user_model().objects.create_user(
            username="legacy-owner", email="legacy-owner@example.test", password="safe-password"
        )

    def test_clean_stage_c_schema_reports_no_legacy_anomalies(self):
        space = KnowledgeSpace.objects.create(
            organization=self.organization,
            name="Repairable",
            code="repairable-owner",
            owner=self.owner,
            created_by=self.owner,
        )
        SpaceMembership.objects.create(
            space=space, user=self.owner, role=SpaceMembership.ROLE_OWNER, status="active"
        )

        output = io.StringIO()
        call_command("audit_ownership_continuity", "--apply", "--format=json", stdout=output)

        space.refresh_from_db()
        report = json.loads(output.getvalue())
        self.assertEqual(space.owner_id, self.owner.id)
        self.assertEqual(report["backfilled_space_ids"], [])
        self.assertEqual(report["zero_owner_space_ids"], [])
        self.assertEqual(report["multiple_owner_space_ids"], [])

    def test_stage_c_schema_rejects_ownerless_spaces(self):
        with self.assertRaises(IntegrityError):
            KnowledgeSpace.objects.create(
                organization=self.organization,
                name="Zero",
                code="zero-owner",
            )

    def test_unapplied_stage_a_schema_has_a_safe_actionable_error(self):
        with patch(
            "apps.spaces.management.commands.audit_ownership_continuity.MigrationRecorder.Migration.objects.values_list",
            return_value=[],
        ):
            with self.assertRaisesRegex(CommandError, "spaces.0009.*users.0004"):
                call_command("audit_ownership_continuity", "--format=json")
