"""Database contracts for actionable notification resources and deep links."""

import uuid

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from django.contrib.auth import get_user_model

from apps.notifications.models import Notification

User = get_user_model()


class ActionableNotificationPersistenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="actionable-notification-user",
            email="actionable-notification-user@example.test",
            password="safe-password",
        )

    def test_legacy_non_actionable_notification_remains_valid(self):
        notification = Notification.objects.create(
            recipient=self.user,
            title="Legacy notice",
        )
        self.assertEqual(notification.action_state, Notification.ACTION_NONE)
        self.assertEqual(notification.allowed_actions, [])

    def test_actionable_notification_requires_bound_resource_and_safe_link(self):
        resource_uuid = uuid.uuid4()
        notification = Notification.objects.create(
            recipient=self.user,
            type=Notification.TYPE_SPACE_INVITATION,
            title="Invitation",
            action_kind="space_invitation",
            resource_type="space_invitation",
            resource_uuid=resource_uuid,
            resource_version=1,
            allowed_actions=["accept", "decline"],
            action_state=Notification.ACTION_AVAILABLE,
            deep_link="/spaces/discover",
        )
        self.assertEqual(notification.resource_uuid, resource_uuid)

        for unsafe_link in ("https://evil.example", "//evil.example/path"):
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    Notification.objects.create(
                        recipient=self.user,
                        title="Unsafe",
                        action_kind="space_invitation",
                        resource_type="space_invitation",
                        resource_uuid=uuid.uuid4(),
                        action_state=Notification.ACTION_AVAILABLE,
                        deep_link=unsafe_link,
                    )

    def test_actioned_state_requires_timestamp(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Notification.objects.create(
                    recipient=self.user,
                    title="Missing timestamp",
                    action_kind="space_access_request",
                    resource_type="space_access_request",
                    resource_uuid=uuid.uuid4(),
                    action_state=Notification.ACTION_ACTIONED,
                    deep_link="/workspace/access",
                )

        notification = Notification.objects.create(
            recipient=self.user,
            title="Actioned",
            action_kind="space_access_request",
            resource_type="space_access_request",
            resource_uuid=uuid.uuid4(),
            action_state=Notification.ACTION_ACTIONED,
            actioned_at=timezone.now(),
            deep_link="/workspace/access",
        )
        self.assertIsNotNone(notification.actioned_at)

