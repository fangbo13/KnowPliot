"""Phase 7A long-run operations baseline tests."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.chat.models import ComplianceExportJob
from apps.spaces.admin_operations import collect_system_health
from apps.spaces.models import BusinessLine, Organization, OrganizationMembership
from apps.spaces.test_utils import create_test_space


User = get_user_model()


class Phase7ALongRunOpsBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Ops Org", slug="ops-org")
        cls.line = BusinessLine.objects.create(
            organization=cls.org, name="Ops Line", code="ops-line"
        )
        cls.space = create_test_space(
            organization=cls.org,
            business_line=cls.line,
            name="Ops Space",
            code="ops-space",
        )
        cls.admin = User.objects.create_user(
            username="ops-admin",
            email="ops-admin@example.com",
            password="test",
        )
        OrganizationMembership.objects.create(
            user=cls.admin,
            organization=cls.org,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )


class LongRunHealthTest(Phase7ALongRunOpsBase):
    @override_settings(
        EXPORT_JOB_RETENTION_DAYS=7,
        AUDIT_LOG_RETENTION_DAYS=365,
        NOTIFICATION_RETENTION_DAYS=90,
        STALE_JOB_RETENTION_DAYS=30,
        STATIC_ROOT="/srv/knowpilot/static",
        MEDIA_ROOT="/srv/knowpilot/media",
    )
    @patch("apps.spaces.admin_operations._check_redis")
    @patch("apps.spaces.admin_operations._check_celery")
    def test_health_payload_includes_long_run_operations_without_secrets(self, celery, redis):
        celery.return_value = None
        redis.return_value = None

        payload = collect_system_health()

        self.assertIn("readiness", payload)
        self.assertIn("liveness", payload)
        self.assertIn("dependency_health", payload)
        self.assertIn("background_worker_health", payload)
        self.assertIn("long_run_operations", payload["services"])
        ops = payload["services"]["long_run_operations"]
        self.assertEqual(ops["status"], "configured")
        self.assertEqual(ops["code"], "long_run_operations_configured")
        self.assertIn("last_checked_at", ops)
        self.assertIn(ops["latency_bucket"], {"fast", "normal", "slow"})
        self.assertEqual(ops["retention"]["export_job_days"], 7)
        self.assertEqual(ops["cleanup"]["expired_export_jobs"], 0)
        self.assertNotIn("SECRET_KEY", str(ops))
        self.assertNotIn("DASHSCOPE_API_KEY", str(ops))
        self.assertNotIn("/srv/knowpilot", str(ops))

    @override_settings(
        EXPORT_JOB_RETENTION_DAYS=None,
        AUDIT_LOG_RETENTION_DAYS=None,
        NOTIFICATION_RETENTION_DAYS=None,
        STALE_JOB_RETENTION_DAYS=None,
    )
    def test_missing_long_run_retention_config_degrades_safely(self):
        payload = collect_system_health()

        ops = payload["services"]["long_run_operations"]
        self.assertEqual(ops["status"], "degraded")
        self.assertIn("EXPORT_JOB_RETENTION_DAYS", ops["missing"])
        self.assertIn("AUDIT_LOG_RETENTION_DAYS", ops["missing"])
        self.assertNotIn("SECRET", str(ops))


class ExportCleanupCommandTest(Phase7ALongRunOpsBase):
    def setUp(self):
        self.expired_job = ComplianceExportJob.objects.create(
            requested_by=self.admin,
            space=self.space,
            dataset=ComplianceExportJob.DATASET_FEEDBACK,
            status=ComplianceExportJob.STATUS_SUCCEEDED,
            result_file="exports/compliance/missing-expired.csv",
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.active_job = ComplianceExportJob.objects.create(
            requested_by=self.admin,
            space=self.space,
            dataset=ComplianceExportJob.DATASET_FEEDBACK,
            status=ComplianceExportJob.STATUS_SUCCEEDED,
            result_file="exports/compliance/missing-active.csv",
            expires_at=timezone.now() + timedelta(days=1),
        )

    def test_cleanup_export_jobs_dry_run_does_not_mutate(self):
        call_command("cleanup_export_jobs", "--dry-run")

        self.expired_job.refresh_from_db()
        self.active_job.refresh_from_db()
        self.assertEqual(self.expired_job.status, ComplianceExportJob.STATUS_SUCCEEDED)
        self.assertEqual(self.active_job.status, ComplianceExportJob.STATUS_SUCCEEDED)

    def test_cleanup_export_jobs_marks_only_expired_jobs(self):
        call_command("cleanup_export_jobs")

        self.expired_job.refresh_from_db()
        self.active_job.refresh_from_db()
        self.assertEqual(self.expired_job.status, ComplianceExportJob.STATUS_EXPIRED)
        self.assertEqual(self.expired_job.result_file, "")
        self.assertEqual(self.active_job.status, ComplianceExportJob.STATUS_SUCCEEDED)
