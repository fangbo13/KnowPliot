"""Model/constraint contracts for workspace join v2 persistence."""

import uuid

from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from django.contrib.auth import get_user_model

from apps.notifications.models import Notification

from apps.spaces.models import (
    InviteCode,
    Organization,
    SpaceAccessCode,
    SpaceAccessRequest,
    SpaceInvitation,
    SpaceMembership,
)
from apps.spaces.ownership import create_space_with_owner

User = get_user_model()


class JoinV2PersistenceContractTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="join-v2-owner",
            email="join-v2-owner@example.test",
            password="safe-password",
        )
        self.target = User.objects.create_user(
            username="join-v2-target",
            email="join-v2-target@example.test",
            password="safe-password",
        )
        self.organization = Organization.objects.create(
            name="Join v2 org",
            slug="join-v2-org",
        )
        self.space = create_space_with_owner(
            organization=self.organization,
            owner=self.owner,
            name="Join v2 space",
            code="join-v2-space",
        )

    def _access_code(self, **overrides):
        values = {
            "space": self.space,
            "created_by": self.owner,
            "secret_hash": "a" * 64,
            "pepper_version": 1,
            "display_prefix": "JOIN-123",
            "role_ceiling": "member",
            "max_uses": 20,
            "used_count": 0,
            "max_pending": 20,
            "pending_count": 0,
            "policy_version": 1,
            "expires_at": timezone.now() + timezone.timedelta(days=7),
        }
        values.update(overrides)
        return SpaceAccessCode.objects.create(**values)

    def _user_invitation(self, **overrides):
        values = {
            "space": self.space,
            "inviter": self.owner,
            "inviter_uuid": self.owner.pk,
            "target_user": self.target,
            "target_user_uuid": self.target.pk,
            "target_key": f"user:{self.target.pk}",
            "role": "member",
            "token_hash": "b" * 64,
            "token_pepper_version": 1,
            "token_prefix": "INV-123",
            "policy_version": 1,
            "ownership_version": self.space.ownership_version,
            "expires_at": timezone.now() + timezone.timedelta(days=7),
        }
        values.update(overrides)
        return SpaceInvitation.objects.create(**values)

    def test_access_code_is_hash_only_and_counters_cannot_exceed_ceilings(self):
        code = self._access_code()
        self.assertEqual(code.secret_hash, "a" * 64)
        self.assertFalse(hasattr(code, "raw_code"))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._access_code(
                    secret_hash="c" * 64,
                    used_count=2,
                    max_uses=1,
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._access_code(
                    secret_hash="d" * 64,
                    pending_count=2,
                    max_pending=1,
                )

    def test_access_request_source_shape_and_pending_uniqueness(self):
        code = self._access_code()
        SpaceAccessRequest.objects.create(
            space=self.space,
            user=self.target,
            role="guest",
            role_ceiling="guest",
            source_kind="access_code",
            access_code=code,
            access_code_version=code.version,
            discovery_policy_version=None,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SpaceAccessRequest.objects.create(
                    space=self.space,
                    user=self.target,
                    role="guest",
                    role_ceiling="guest",
                    source_kind="access_code",
                    access_code=code,
                    access_code_version=code.version,
                    discovery_policy_version=None,
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SpaceAccessRequest.objects.create(
                    space=self.space,
                    user=self.owner,
                    source_kind="access_code",
                    access_code=code,
                    access_code_version=code.version,
                    discovery_policy_version=1,
                )

    def test_guest_ceiling_cannot_request_member_role(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SpaceAccessRequest.objects.create(
                    space=self.space,
                    user=self.target,
                    role="member",
                    role_ceiling="guest",
                )

    def test_invitation_is_target_bound_non_owner_and_single_pending(self):
        invitation = self._user_invitation()
        self.assertEqual(invitation.target_user_uuid, self.target.pk)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._user_invitation(
                    token_hash="c" * 64,
                    target_user_uuid=uuid.uuid4(),
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._user_invitation(token_hash="d" * 64, role="owner")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._user_invitation(token_hash="e" * 64)

    def test_email_invitation_requires_hmac_and_encrypted_delivery_address(self):
        invitation = SpaceInvitation.objects.create(
            space=self.space,
            inviter=self.owner,
            inviter_uuid=self.owner.pk,
            target_email_hmac="f" * 64,
            encrypted_delivery_address="ciphertext",
            target_key=f"email:{'f' * 64}",
            role="guest",
            token_hash="1" * 64,
            token_pepper_version=1,
            token_prefix="EMAIL-1",
            policy_version=1,
            ownership_version=self.space.ownership_version,
            expires_at=timezone.now() + timezone.timedelta(days=7),
        )
        self.assertIsNone(invitation.target_user_id)

    def test_accepted_invitation_requires_consumption_and_membership_evidence(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._user_invitation(status="accepted")

    def test_membership_version_and_owner_guard_are_persisted(self):
        membership = SpaceMembership.objects.get(
            space=self.space,
            user=self.owner,
        )
        self.assertEqual(membership.membership_version, 1)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SpaceMembership.objects.filter(pk=membership.pk).update(
                    invited_by=self.target,
                )
        membership.refresh_from_db()
        self.assertIsNone(membership.invited_by_id)

    def test_legacy_invitation_code_cannot_persist_owner_role(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InviteCode.objects.create(
                    space=self.space,
                    code_hash="9" * 64,
                    role="owner",
                )

    def test_deleted_resource_notification_retains_identity_but_no_action_or_link(self):
        notification = Notification.objects.create(
            recipient=self.target,
            type=Notification.TYPE_SPACE_INVITATION,
            title="Deleted workspace resource",
            action_kind=Notification.ACTION_KIND_RESOURCE_DELETED,
            resource_type="space_invitation",
            resource_uuid=uuid.uuid4(),
            resource_version=3,
            allowed_actions=[],
            action_state=Notification.ACTION_STALE,
            deep_link="",
        )

        self.assertEqual(notification.action_state, Notification.ACTION_STALE)
        self.assertEqual(notification.allowed_actions, [])
        self.assertEqual(notification.deep_link, "")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Notification.objects.create(
                    recipient=self.target,
                    type=Notification.TYPE_SPACE_INVITATION,
                    title="Unsafe deleted workspace resource",
                    action_kind=Notification.ACTION_KIND_RESOURCE_DELETED,
                    resource_type="space_invitation",
                    resource_uuid=uuid.uuid4(),
                    allowed_actions=["accept"],
                    action_state=Notification.ACTION_STALE,
                    deep_link="/spaces/discover",
                )


class PgJoinV2ConstraintRegressionTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("requires PostgreSQL; run through docker compose")

    def test_source_shape_constraint_trigger_is_deferred(self):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tgdeferrable, tginitdeferred
                  FROM pg_trigger
                 WHERE tgname = 'spaces_access_request_source_guard'
                """
            )
            self.assertEqual(cursor.fetchone(), (True, True))
