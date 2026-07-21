"""Safe public and platform-only readiness API contracts."""

from datetime import timedelta
from types import SimpleNamespace
from unittest import mock
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.views import public_readiness, system_readiness
from apps.core.readiness import (
    _creation_policy_state,
    _creation_reviewer_state,
    _join_contract_details,
    _paired_rollout_state,
    _purge_registry_details,
    collect_readiness,
)
from apps.spaces.models import (
    BusinessLine,
    Organization,
    WorkspaceCreationPolicy,
)


def _readiness_test_delivery_adapter(_event):
    return None


READY = {
    "status": "ready",
    "build_revision": "test-build",
    "configuration_revision": "test-config",
    "checks": {
        "database": "ok",
        "migrations": "ok",
        "canonical_models": "ok",
        "creation_reviewers": "disabled",
        "creation_policy": "disabled",
        "join_credentials": "disabled",
        "template_clone_contract": "ok",
        "shared_rate_limit": "ok",
        "purge_registry": "disabled",
    },
    "details": {
        "expected_models": {"fast": "qwen3.6-flash", "deep": "qwen3.7-plus"},
        "effective_models": {"fast": "qwen3.6-flash", "deep": "qwen3.7-plus"},
        "profile_ids": {"fast": "profile-fast", "deep": "profile-deep"},
        "policy_revisions": [3],
        "legacy_alias_matches": True,
        "rollout": {"deep": False, "thinking": False},
        "cache_backend_kind": "shared",
        "worker_count_bucket": "2-4",
        "expired_test_principal_count": 0,
    },
}


class ReadinessViewContractTest(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    @patch("apps.core.views.collect_readiness", return_value=READY)
    def test_public_readiness_is_auth_exempt_and_bounded(self, _collect):
        response = public_readiness(self.factory.get("/api/v1/health/ready/"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.data),
            {"status", "build_revision", "configuration_revision", "checks"},
        )
        serialized = repr(response.data)
        self.assertNotIn("qwen3.7", serialized)
        self.assertNotIn("profile-fast", serialized)

    @patch(
        "apps.core.views.collect_readiness",
        return_value={**READY, "status": "not_ready"},
    )
    def test_public_not_ready_uses_503_without_raw_errors(self, _collect):
        response = public_readiness(self.factory.get("/api/v1/health/ready/"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["status"], "not_ready")

    @patch("apps.core.views.collect_readiness", return_value=READY)
    @patch(
        "apps.core.views.resolve_capabilities",
        return_value={"capabilities": []},
    )
    def test_system_readiness_requires_exact_platform_access(self, _caps, _collect):
        request = self.factory.get("/api/v1/admin/system/readiness/")
        force_authenticate(
            request,
            user=get_user_model()(id=1, email="non-platform@example.test"),
        )

        response = system_readiness(request)

        self.assertEqual(response.status_code, 403)
        _collect.assert_not_called()

    @patch("apps.core.views.collect_readiness", return_value=READY)
    @patch(
        "apps.core.views.resolve_capabilities",
        return_value={"capabilities": ["platform.access"]},
    )
    def test_platform_detail_exposes_safe_expected_and_effective_truth(
        self,
        _caps,
        _collect,
    ):
        request = self.factory.get("/api/v1/admin/system/readiness/")
        force_authenticate(
            request,
            user=get_user_model()(id=2, email="platform@example.test"),
        )

        response = system_readiness(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["details"], READY["details"])
        self.assertNotIn("connection", repr(response.data).lower())
        self.assertNotIn("secret", repr(response.data).lower())


class TemplateCloneReadinessTests(SimpleTestCase):
    @patch(
        "apps.scenario_templates.models.TemplateAssetApplication.objects.exists",
        return_value=False,
    )
    @patch(
        "apps.scenario_templates.models.ScenarioTemplateAsset.objects.exists",
        return_value=False,
    )
    @patch("apps.core.readiness._expired_test_principal_count", return_value=0)
    @patch(
        "apps.core.readiness._model_policy_details",
        return_value=("ok", {}),
    )
    @patch("apps.core.readiness._migration_state", return_value="ok")
    @patch("apps.core.readiness._database_state", return_value="ok")
    def test_unsafe_historical_asset_copy_configuration_is_not_ready(
        self,
        _database,
        _migrations,
        _models,
        _principals,
        _assets,
        _asset_applications,
    ):
        with override_settings(TEMPLATE_ASSET_COPY_ENABLED=True):
            unsafe = collect_readiness()
        with override_settings(TEMPLATE_ASSET_COPY_ENABLED=False):
            safe = collect_readiness()

        self.assertEqual(unsafe["checks"]["template_clone_contract"], "not_ready")
        self.assertTrue(unsafe["details"]["template_asset_copy_enabled"])
        self.assertEqual(safe["checks"]["template_clone_contract"], "ok")
        self.assertFalse(safe["details"]["template_asset_copy_enabled"])

        with patch("apps.core.views.collect_readiness", return_value=unsafe):
            public = public_readiness(
                APIRequestFactory().get("/api/v1/health/ready/")
            )
        self.assertNotIn("details", public.data)
        self.assertNotIn("template_asset_copy_enabled", repr(public.data))

    @patch(
        "apps.scenario_templates.models.TemplateAssetApplication.objects.exists",
        return_value=False,
    )
    @patch(
        "apps.scenario_templates.models.ScenarioTemplateAsset.objects.exists",
        return_value=True,
    )
    def test_historical_asset_rows_fail_closed_even_with_switch_off(
        self,
        _assets,
        _asset_applications,
    ):
        from apps.core.readiness import _template_clone_details

        with override_settings(TEMPLATE_ASSET_COPY_ENABLED=False):
            state, details = _template_clone_details()

        self.assertEqual(state, "not_ready")
        self.assertTrue(details["template_historical_assets_present"])
        self.assertFalse(details["template_asset_copy_enabled"])


class CreationReadinessTruthTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.reviewer_a = User.objects.create_user(
            username="readiness-reviewer-a",
            email="readiness-reviewer-a@example.test",
            password="pw",
            is_staff=True,
        )
        self.reviewer_b = User.objects.create_user(
            username="readiness-reviewer-b",
            email="readiness-reviewer-b@example.test",
            password="pw",
            is_staff=True,
        )
        self.organization = Organization.objects.create(
            name="Readiness organization",
            slug="readiness-organization",
        )
        self.business_line = BusinessLine.objects.create(
            organization=self.organization,
            name="Readiness line",
            code="readiness-line",
        )

    def test_two_active_reviewers_and_effective_beta_policy_are_required(self):
        policy = WorkspaceCreationPolicy.objects.create(
            business_line=self.business_line,
            revision=1,
            status=WorkspaceCreationPolicy.STATUS_ACTIVE,
            audience=WorkspaceCreationPolicy.AUDIENCE_REGISTERED_BETA,
            review_route=WorkspaceCreationPolicy.ROUTE_PLATFORM,
            reviewer_separation_required=True,
            effective_from=timezone.now() - timedelta(minutes=1),
            effective_until=timezone.now() + timedelta(minutes=1),
        )

        self.assertEqual(_creation_reviewer_state(), "ok")
        self.assertEqual(_creation_policy_state(), "ok")

        self.reviewer_b.is_active = False
        self.reviewer_b.save(update_fields=["is_active"])
        self.assertEqual(_creation_reviewer_state(), "not_ready")

        policy.effective_until = timezone.now() - timedelta(seconds=1)
        policy.save(update_fields=["effective_until"])
        self.assertEqual(_creation_policy_state(), "not_ready")


class JoinAndDeleteReadinessTruthTests(SimpleTestCase):
    @override_settings(
        SPACE_CREDENTIAL_PEPPER_VERSION=2,
        SPACE_CREDENTIAL_PEPPERS={
            1: "retained-rotation-pepper-material-0001",
            2: "current-rotation-pepper-material-0002",
        },
        SPACE_INVITATION_ENCRYPTION_KEY="independent-invitation-key-material-0001",
        ACTION_OUTBOX_DELIVERY_ADAPTER=(
            "apps.core.test_readiness._readiness_test_delivery_adapter"
        ),
    )
    def test_join_requires_current_pepper_and_independent_encryption(self):
        state, details = _join_contract_details()
        self.assertEqual(state, "ok")
        self.assertTrue(all(details.values()))

        with override_settings(SPACE_CREDENTIAL_PEPPER_VERSION=3):
            missing_current, missing_details = _join_contract_details()
        self.assertEqual(missing_current, "not_ready")
        self.assertFalse(missing_details["credential_current_version_configured"])

        with override_settings(
            SPACE_INVITATION_ENCRYPTION_KEY="replace-with-an-independent-random-secret"
        ):
            placeholder, placeholder_details = _join_contract_details()
        self.assertEqual(placeholder, "not_ready")
        self.assertFalse(placeholder_details["invitation_encryption_configured"])

        with override_settings(ACTION_OUTBOX_DELIVERY_ADAPTER=""):
            missing_delivery, delivery_details = _join_contract_details()
        self.assertEqual(missing_delivery, "not_ready")
        self.assertFalse(delivery_details["external_delivery_adapter_configured"])

    @patch("apps.spaces.deletion_registry.audit_purge_registry")
    def test_delete_readiness_uses_registry_audit_truth(self, audit):
        audit.return_value = SimpleNamespace(ready=True, code="purge_registry_ready")
        state, details = _purge_registry_details()
        self.assertEqual(state, "ok")
        self.assertEqual(
            details,
            {
                "purge_registry_ready": True,
                "purge_registry_code": "purge_registry_ready",
            },
        )

        audit.return_value = SimpleNamespace(
            ready=False,
            code="purge_registry_pending_migration",
        )
        state, details = _purge_registry_details()
        self.assertEqual(state, "not_ready")
        self.assertFalse(details["purge_registry_ready"])

    @override_settings(
        CAPABILITY_NAV=True,
        DEEP_ANSWER_MODE=True,
        THINKING_MODE=False,
        WORKSPACE_CREATION_APPROVAL=True,
        WORKSPACE_JOIN_V2=True,
        WORKSPACE_PERMANENT_DELETE=True,
    )
    def test_paired_rollout_reports_creation_join_and_delete(self):
        with mock.patch.dict(
            "os.environ",
            {
                "VITE_CAPABILITY_NAV": "true",
                "VITE_DEEP_ANSWER_MODE": "true",
                "VITE_THINKING_MODE": "false",
                "VITE_WORKSPACE_CREATION_APPROVAL": "true",
                "VITE_WORKSPACE_JOIN_V2": "true",
                "VITE_WORKSPACE_PERMANENT_DELETE": "true",
            },
            clear=False,
        ):
            rollout = _paired_rollout_state()

        self.assertEqual(
            set(rollout),
            {"capability_nav", "deep", "thinking", "creation", "join", "delete"},
        )
        self.assertTrue(rollout["creation"]["frontend"])
        self.assertTrue(rollout["join"]["backend"])
        self.assertTrue(rollout["delete"]["frontend"])
