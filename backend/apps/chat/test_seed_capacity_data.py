from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.audit.models import AuditLog
from apps.chat.models import ChatSession, Message
from apps.notifications.models import Notification
from apps.spaces.generation_policy import resolve_generation_policy
from apps.spaces.models import KnowledgeSpace, SpaceMembership


@override_settings(CAPACITY_SEED_ALLOWED=True)
class CapacitySeedTest(TestCase):
    options = {
        "users": 3,
        "spaces": 2,
        "sessions_per_user": 2,
        "messages_per_session": 4,
        "notifications_per_user": 1,
        "audits_per_user": 1,
        "batch_size": 100,
    }

    def test_two_runs_have_identical_counts_without_duplicates(self):
        expected = {
            "users": 3,
            "spaces": 2,
            "memberships": 3,
            "sessions": 6,
            "messages": 24,
            "notifications": 3,
            "audits": 3,
        }
        for _ in range(2):
            call_command("seed_capacity_data", **self.options)
            self.assertEqual(self._counts(), expected)

    def test_command_is_disabled_without_explicit_capacity_guard(self):
        with override_settings(CAPACITY_SEED_ALLOWED=False):
            with self.assertRaisesMessage(Exception, "capacity_seed_disabled"):
                call_command("seed_capacity_data", **self.options)

    def test_capacity_principals_can_authenticate_without_shared_ip_login_throttle(self):
        call_command("seed_capacity_data", **self.options)
        for _ in range(6):
            response = self.client.post(
                "/api/v1/auth/token/",
                {
                    "email": "capacity00000@example.invalid",
                    "password": "CapacityOnly!2026",
                },
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200)

    def test_seeded_space_has_a_runnable_canonical_generation_policy(self):
        call_command("seed_capacity_data", **self.options)
        space = KnowledgeSpace.objects.get(code="capacity-space-00")

        policy = resolve_generation_policy(space, "fast")

        self.assertEqual(policy.provider, "dashscope")
        self.assertEqual(policy.model_id, "qwen3.6-flash")

    def _counts(self):
        return {
            "users": get_user_model().objects.filter(test_run_id="capacity-500").count(),
            "spaces": KnowledgeSpace.objects.filter(code__startswith="capacity-space-").count(),
            "memberships": SpaceMembership.objects.count(),
            "sessions": ChatSession.objects.count(),
            "messages": Message.objects.count(),
            "notifications": Notification.objects.count(),
            "audits": AuditLog.objects.count(),
        }
