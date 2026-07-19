from django.test import TestCase
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.spaces.models import GovernancePolicy, Organization, create_policy_revision, resolve_effective_policy
from apps.spaces.retention import run_retention
from apps.spaces.test_utils import create_test_space


class Phase9CGovernanceTests(TestCase):
    def test_space_policy_overrides_organization_and_defaults(self):
        org = Organization.objects.create(name="Policy Org", slug="policy-org")
        space = create_test_space(organization=org, name="Policy Space", code="policy-space")
        GovernancePolicy.objects.create(organization=org, values={"retrieval_top_k": 9, "retention_days": 50})
        GovernancePolicy.objects.create(space=space, values={"retrieval_top_k": 3})
        policy = resolve_effective_policy(space)
        self.assertEqual(policy["retrieval_top_k"], 3)
        self.assertEqual(policy["retention_days"], 50)
        self.assertNotIn("citation_required", policy)

    def test_policy_revision_is_immutable(self):
        policy = GovernancePolicy.objects.create(values={"retention_days": 30})
        policy.values = {"retention_days": 90}
        with self.assertRaises(ValidationError):
            policy.save()

    def test_create_revision_preserves_prior_revision(self):
        org = Organization.objects.create(name="Revision Org", slug="revision-org")
        first = create_policy_revision(organization=org, values={"retention_days": 30})
        second = create_policy_revision(organization=org, values={"retention_days": 60})
        self.assertEqual((first.revision, second.revision), (1, 2))
        self.assertEqual(GovernancePolicy.objects.get(pk=first.pk).values["retention_days"], 30)

    def test_retention_defaults_to_dry_run(self):
        result = run_retention(days=30)
        self.assertTrue(result["dry_run"])


class Phase9CGovernanceApiTests(APITestCase):
    def test_regular_user_cannot_manage_model_profiles(self):
        user = get_user_model().objects.create_user(username="regular", email="regular@example.com", password="Strong-pass-123!")
        self.client.force_authenticate(user)
        response = self.client.get("/api/v1/admin/model-profiles/")
        self.assertEqual(response.status_code, 403)
