"""Requirement tests for the v3 owner-managed member lifecycle."""

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.chat.coordination import session_lease_key
from apps.chat.models import ChatSession, ChatTurn, ConversationShare, Message

from .models import (
    Organization,
    OwnershipTransfer,
    SpaceMembership,
)
from .ownership import create_space_with_owner


class _LeaseStore:
    def __init__(self):
        self.deleted = []

    def delete(self, *keys):
        self.deleted.extend(keys)
        return len(keys)


@override_settings(WORKSPACE_JOIN_V2=True)
class WorkspaceMemberV2ApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="member-v2-owner",
            email="member-v2-owner@example.test",
            password="pw",
        )
        self.member_user = User.objects.create_user(
            username="member-v2-target",
            email="member-v2-target@example.test",
            password="pw",
        )
        self.other = User.objects.create_user(
            username="member-v2-other",
            email="member-v2-other@example.test",
            password="pw",
        )
        self.organization = Organization.objects.create(
            name="Member v2 Org",
            slug="member-v2-org",
        )
        self.space = create_space_with_owner(
            organization=self.organization,
            owner=self.owner,
            name="Member v2 Space",
            code="member-v2-space",
            visibility="private",
        )
        self.membership = SpaceMembership.objects.create(
            space=self.space,
            user=self.member_user,
            role=SpaceMembership.ROLE_MEMBER,
            status="active",
            source_kind=SpaceMembership.SOURCE_ACCESS_REQUEST,
            invited_by=self.owner,
        )
        self.owner_membership = SpaceMembership.objects.get(
            space=self.space,
            user=self.owner,
        )
        self.client = APIClient()

    def _auth(self, user):
        self.client.force_authenticate(user)

    def _key(self, value=None):
        return {"HTTP_IDEMPOTENCY_KEY": str(value or uuid.uuid4())}

    def _detail_url(self, membership=None):
        membership = membership or self.membership
        return f"/api/v1/spaces/{self.space.id}/members/{membership.id}/"

    def archive_space(self):
        self.space.status = "archived"
        self.space.archived_at = timezone.now()
        self.space.save(update_fields=["status", "archived_at", "updated_at"])

    def test_list_and_writes_require_exact_owner_capability(self):
        self._auth(self.owner)
        listed = self.client.get(f"/api/v1/spaces/{self.space.id}/members/")
        self.assertEqual(listed.status_code, 200, listed.data)
        by_id = {row["id"]: row for row in listed.data["results"]}
        self.assertTrue(by_id[str(self.owner_membership.id)]["immutable_owner"])
        self.assertFalse(by_id[str(self.membership.id)]["immutable_owner"])

        for unauthorized in (self.member_user, self.other):
            with self.subTest(user=unauthorized.username):
                self._auth(unauthorized)
                denied = self.client.get(
                    f"/api/v1/spaces/{self.space.id}/members/"
                )
                self.assertEqual(denied.status_code, 404, denied.data)

    def test_patch_is_shape_strict_versioned_and_controls_role_status_and_expiry(self):
        self._auth(self.owner)
        expires_at = timezone.now() + timedelta(days=3)
        changed = self.client.patch(
            self._detail_url(),
            {
                "expected_membership_version": 1,
                "role": "space_admin",
                "status": "active",
                "expires_at": expires_at.isoformat(),
                "reason_code": "role_change",
                "reason_text": "Review access is required",
            },
            format="json",
            **self._key(),
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(changed.data["role"], "space_admin")
        self.assertEqual(changed.data["membership_version"], 2)

        stale = self.client.patch(
            self._detail_url(),
            {
                "expected_membership_version": 1,
                "role": "guest",
                "reason_code": "role_change",
            },
            format="json",
            **self._key(),
        )
        self.assertEqual(stale.status_code, 409, stale.data)
        self.assertEqual(stale.data["code"], "stale_membership_version")

        unknown = self.client.patch(
            self._detail_url(),
            {
                "expected_membership_version": 2,
                "role": "member",
                "owner": str(self.owner.id),
                "reason_code": "role_change",
            },
            format="json",
            **self._key(),
        )
        self.assertEqual(unknown.status_code, 400, unknown.data)

    @patch("apps.chat.coordination.create_redis_client", return_value=_LeaseStore())
    def test_archived_workspace_blocks_role_grants_but_allows_member_removal(
        self,
        _redis,
    ):
        self.archive_space()
        self._auth(self.owner)

        grant = self.client.patch(
            self._detail_url(),
            {
                "expected_membership_version": 1,
                "role": "space_admin",
                "reason_code": "role_change",
                "reason_text": "Must be fenced",
            },
            format="json",
            **self._key(),
        )
        self.assertEqual(grant.status_code, 409, grant.data)
        self.assertEqual(grant.data["code"], "workspace_not_writable")

        removed = self.client.delete(
            self._detail_url(),
            {
                "reason_code": "archive_cleanup",
                "reason_text": "Reduce deletion blockers",
            },
            format="json",
            HTTP_IF_MATCH='"membership-v1"',
            **self._key(),
        )
        self.assertEqual(removed.status_code, 200, removed.data)
        self.assertTrue(removed.data["removed"])

    def test_owner_mirror_is_protected_and_safe_failure_is_replayed(self):
        self._auth(self.owner)
        operation_key = uuid.uuid4()
        url = self._detail_url(self.owner_membership)
        payload = {"reason_code": "access_removed", "reason_text": "forged"}

        first = self.client.delete(
            url,
            payload,
            format="json",
            HTTP_IF_MATCH='"membership-v1"',
            **self._key(operation_key),
        )
        replay = self.client.delete(
            url,
            payload,
            format="json",
            HTTP_IF_MATCH='"membership-v1"',
            **self._key(operation_key),
        )

        self.assertEqual(first.status_code, 409, first.data)
        self.assertEqual(first.data["code"], "ownership_workflow_required")
        self.assertEqual(replay.status_code, 409, replay.data)
        self.assertEqual(replay["Idempotency-Replayed"], "true")
        self.owner_membership.refresh_from_db()
        self.assertEqual(self.owner_membership.role, SpaceMembership.ROLE_OWNER)
        self.assertEqual(self.owner_membership.status, "active")
        self.assertEqual(self.space.owner_id, self.owner.id)

    def test_remove_fences_turn_session_share_and_invalidates_voluntary_transfer(self):
        session = ChatSession.objects.create(
            space=self.space,
            user=self.member_user,
            title="Active member session",
        )
        question = Message.objects.create(
            space=self.space,
            session=session,
            role="user",
            content="Question that must not finish after revocation",
        )
        turn = ChatTurn.objects.create(
            client_request_id=uuid.uuid4(),
            session=session,
            space=self.space,
            user=self.member_user,
            question_message=question,
            status=ChatTurn.STATUS_ANSWERING,
        )
        share = ConversationShare.objects.create(
            session=session,
            owner=self.member_user,
            organization=self.organization,
        )
        transfer = OwnershipTransfer.objects.create(
            space=self.space,
            from_owner=self.owner,
            to_owner=self.member_user,
            requested_by=self.owner,
            mode=OwnershipTransfer.MODE_VOLUNTARY,
            status=OwnershipTransfer.STATUS_PENDING,
            space_uuid=self.space.id,
            organization_uuid=self.organization.id,
            locator_digest="a" * 64,
            expected_ownership_version=self.space.ownership_version,
            reason_code="succession",
            idempotency_key=uuid.uuid4(),
            expires_at=timezone.now() + timedelta(hours=24),
        )
        lease_store = _LeaseStore()
        operation_key = uuid.uuid4()
        self._auth(self.owner)

        with patch(
            "apps.chat.coordination.create_redis_client",
            return_value=lease_store,
        ):
            removed = self.client.delete(
                self._detail_url(),
                {
                    "reason_code": "access_removed",
                    "reason_text": "No longer assigned",
                },
                format="json",
                HTTP_IF_MATCH='"membership-v1"',
                **self._key(operation_key),
            )
            replay = self.client.delete(
                self._detail_url(),
                {
                    "reason_code": "access_removed",
                    "reason_text": "No longer assigned",
                },
                format="json",
                HTTP_IF_MATCH='"membership-v1"',
                **self._key(operation_key),
            )

        self.assertEqual(removed.status_code, 200, removed.data)
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(replay["Idempotency-Replayed"], "true")
        self.membership.refresh_from_db()
        session.refresh_from_db()
        turn.refresh_from_db()
        share.refresh_from_db()
        transfer.refresh_from_db()
        self.assertEqual(self.membership.status, "revoked")
        self.assertEqual(self.membership.membership_version, 2)
        self.assertFalse(session.is_active)
        self.assertEqual(turn.status, ChatTurn.STATUS_CANCELLED)
        self.assertEqual(turn.error_code, "membership_revoked")
        self.assertIsNotNone(share.revoked_at)
        self.assertEqual(transfer.status, OwnershipTransfer.STATUS_INVALIDATED)
        self.assertIn(session_lease_key(session.id), lease_store.deleted)
        self.assertEqual(
            AuditLog.objects.filter(
                target_type="OwnershipTransfer",
                target_id=transfer.id,
                details__ownership_event="ownership_transfer_invalidated_member_removed",
            ).count(),
            1,
        )
