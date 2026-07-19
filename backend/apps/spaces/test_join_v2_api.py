"""End-to-end API tests for access requests and targeted invitations."""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.notifications.models import ActionOutboxEvent, Notification

from .models import (
    KnowledgeSpace,
    Organization,
    SpaceAccessCode,
    SpaceAccessRequest,
    SpaceInvitation,
    SpaceMembership,
)
from .ownership import create_space_with_owner


@override_settings(
    WORKSPACE_JOIN_V2=True,
    SPACE_CREDENTIAL_PEPPER_VERSION=1,
    SPACE_CREDENTIAL_PEPPERS={1: "join-test-pepper-with-independent-secret"},
    SPACE_INVITATION_ENCRYPTION_KEY="join-test-independent-encryption-secret",
)
class WorkspaceJoinV2ApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="join-owner", email="join-owner@example.com", password="pw"
        )
        self.requester = User.objects.create_user(
            username="join-requester", email="join-requester@example.com", password="pw"
        )
        self.invitee = User.objects.create_user(
            username="join-invitee", email="join-invitee@example.com", password="pw"
        )
        self.other = User.objects.create_user(
            username="join-other", email="join-other@example.com", password="pw"
        )
        self.org = Organization.objects.create(name="Join Org", slug="join-org")
        self.space = create_space_with_owner(
            organization=self.org,
            owner=self.owner,
            name="Join workspace",
            code="join-workspace-v2",
            visibility="organization",
        )
        self.client = APIClient()

    def auth(self, user):
        self.client.force_authenticate(user)

    def key(self):
        return {"HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4())}

    def issue_code(self, *, max_pending=10, role_ceiling="member"):
        self.auth(self.owner)
        return self.client.post(
            f"/api/v1/spaces/{self.space.id}/access-codes/",
            {
                "role_ceiling": role_ceiling,
                "expires_at": (timezone.now() + timedelta(days=2)).isoformat(),
                "max_uses": 20,
                "max_pending": max_pending,
            },
            format="json",
            **self.key(),
        )

    def archive_space(self):
        self.space.status = "archived"
        self.space.archived_at = timezone.now()
        self.space.save(update_fields=["status", "archived_at", "updated_at"])

    def test_access_code_is_hmac_only_and_redemption_never_creates_membership(self):
        issued = self.issue_code()
        self.assertEqual(issued.status_code, 201, issued.data)
        raw = issued.data["code"]
        stored = SpaceAccessCode.objects.get(pk=issued.data["id"])
        self.assertNotIn(raw, stored.secret_hash)
        self.assertNotEqual(stored.secret_hash, hashlib.sha256(raw.encode()).hexdigest())
        listed = self.client.get(f"/api/v1/spaces/{self.space.id}/access-codes/")
        self.assertNotIn("code", listed.data["results"][0])
        self.assertNotIn("secret_hash", listed.data["results"][0])

        self.auth(self.requester)
        redeemed = self.client.post(
            "/api/v1/spaces/access-code-requests/",
            {"code": raw, "reason": "Need governed access"},
            format="json",
            **self.key(),
        )
        self.assertEqual(redeemed.status_code, 202, redeemed.data)
        self.assertEqual(redeemed.data["status"], "pending")
        self.assertFalse(
            SpaceMembership.objects.filter(space=self.space, user=self.requester).exists()
        )
        request_row = SpaceAccessRequest.objects.get(pk=redeemed.data["id"])
        self.assertEqual(request_row.source_kind, "access_code")
        self.assertEqual(request_row.access_code, stored)
        notice = Notification.objects.get(
            recipient=self.owner,
            resource_type="space_access_request",
            resource_uuid=request_row.id,
        )
        self.assertEqual(notice.allowed_actions, ["approve", "reject"])
        self.assertNotIn(raw, str(notice.metadata))
        outbox = ActionOutboxEvent.objects.get(
            aggregate_type="space_access_request",
            aggregate_uuid=request_row.id,
            transition="submitted",
        )
        self.assertEqual(outbox.recipient_key, f"user:{self.owner.id}")
        self.assertNotIn(raw, str(outbox.payload))

        # A second operation converges on the same pending request without
        # consuming another code use or creating another row.
        again = self.client.post(
            "/api/v1/spaces/access-code-requests/",
            {"code": raw, "reason": "Need governed access"},
            format="json",
            **self.key(),
        )
        self.assertEqual(again.status_code, 202, again.data)
        self.assertEqual(again.data["id"], redeemed.data["id"])
        stored.refresh_from_db()
        self.assertEqual(stored.used_count, 1)
        self.assertEqual(stored.pending_count, 1)

    def test_archived_workspace_blocks_new_grants_but_allows_rejection(self):
        issued = self.issue_code()
        self.assertEqual(issued.status_code, 201, issued.data)
        self.auth(self.requester)
        requested = self.client.post(
            "/api/v1/spaces/access-code-requests/",
            {"code": issued.data["code"], "reason": "Need access"},
            format="json",
            **self.key(),
        )
        self.assertEqual(requested.status_code, 202, requested.data)
        self.archive_space()

        self.auth(self.owner)
        new_code = self.issue_code()
        self.assertEqual(new_code.status_code, 409, new_code.data)
        self.assertEqual(new_code.data["code"], "workspace_not_writable")

        approve = self.client.post(
            f"/api/v1/spaces/{self.space.id}/access-requests/{requested.data['id']}/approve/",
            {"expected_request_version": 1, "role": "member"},
            format="json",
            **self.key(),
        )
        self.assertEqual(approve.status_code, 409, approve.data)
        self.assertEqual(approve.data["code"], "workspace_not_writable")

        reject = self.client.post(
            f"/api/v1/spaces/{self.space.id}/access-requests/{requested.data['id']}/reject/",
            {
                "expected_request_version": 1,
                "reason_code": "workspace_archived",
                "reason_text": "Workspace is archived",
            },
            format="json",
            **self.key(),
        )
        self.assertEqual(reject.status_code, 200, reject.data)
        self.assertEqual(reject.data["status"], "rejected")

    def test_owner_approval_creates_one_non_owner_membership_atomically(self):
        issued = self.issue_code()
        self.auth(self.requester)
        redeemed = self.client.post(
            "/api/v1/spaces/access-code-requests/",
            {"code": issued.data["code"], "reason": "Please approve"},
            format="json",
            **self.key(),
        )
        self.auth(self.owner)
        approved = self.client.post(
            f"/api/v1/spaces/{self.space.id}/access-requests/{redeemed.data['id']}/approve/",
            {"expected_request_version": 1, "role": "member"},
            format="json",
            **self.key(),
        )
        self.assertEqual(approved.status_code, 200, approved.data)
        membership = SpaceMembership.objects.get(space=self.space, user=self.requester)
        self.assertEqual(membership.role, "member")
        self.assertEqual(membership.source_kind, "access_request")
        self.assertEqual(approved.data["resulting_membership_uuid"], str(membership.id))
        row = SpaceAccessRequest.objects.get(pk=redeemed.data["id"])
        self.assertEqual(row.status, "approved")
        self.assertEqual(
            Notification.objects.get(resource_uuid=row.id).action_state,
            "actioned",
        )
        self.assertEqual(
            SpaceMembership.objects.filter(space=self.space, user=self.requester).count(),
            1,
        )
        terminal_outbox = ActionOutboxEvent.objects.get(
            aggregate_type="space_access_request",
            aggregate_uuid=row.id,
            transition="approved",
        )
        self.assertEqual(terminal_outbox.transition_version, row.request_version)
        self.assertEqual(terminal_outbox.recipient_key, f"user:{self.requester.id}")

    def test_terminal_transition_rolls_back_when_outbox_write_fails(self):
        issued = self.issue_code()
        self.auth(self.requester)
        redeemed = self.client.post(
            "/api/v1/spaces/access-code-requests/",
            {"code": issued.data["code"], "reason": "Atomic outbox"},
            format="json",
            **self.key(),
        )
        request_row = SpaceAccessRequest.objects.get(pk=redeemed.data["id"])
        notification = Notification.objects.get(resource_uuid=request_row.id)

        self.auth(self.owner)
        with patch(
            "apps.notifications.outbox_services.enqueue_action_outbox",
            side_effect=RuntimeError("simulated outbox persistence failure"),
        ):
            failed = self.client.post(
                f"/api/v1/spaces/{self.space.id}/access-requests/{request_row.id}/approve/",
                {"expected_request_version": 1, "role": "member"},
                format="json",
                **self.key(),
            )
        self.assertEqual(failed.status_code, 500)

        request_row.refresh_from_db()
        notification.refresh_from_db()
        self.assertEqual(request_row.status, SpaceAccessRequest.STATUS_PENDING)
        self.assertEqual(request_row.request_version, 1)
        self.assertEqual(notification.action_state, Notification.ACTION_AVAILABLE)
        self.assertFalse(
            SpaceMembership.objects.filter(
                space=self.space,
                user=self.requester,
            ).exists()
        )
        self.assertFalse(
            ActionOutboxEvent.objects.filter(
                aggregate_uuid=request_row.id,
                transition="approved",
            ).exists()
        )

    def test_only_current_owner_can_review_and_code_role_ceiling_is_enforced(self):
        issued = self.issue_code(role_ceiling="guest")
        self.auth(self.requester)
        pending = self.client.post(
            "/api/v1/spaces/access-code-requests/",
            {"code": issued.data["code"], "reason": "Guest access"},
            format="json",
            **self.key(),
        )

        self.auth(self.other)
        denied = self.client.post(
            f"/api/v1/spaces/{self.space.id}/access-requests/{pending.data['id']}/approve/",
            {"expected_request_version": 1, "role": "guest"},
            format="json",
            **self.key(),
        )
        self.assertEqual(denied.status_code, 404, denied.data)

        self.auth(self.owner)
        over_ceiling = self.client.post(
            f"/api/v1/spaces/{self.space.id}/access-requests/{pending.data['id']}/approve/",
            {"expected_request_version": 1, "role": "member"},
            format="json",
            **self.key(),
        )
        self.assertEqual(over_ceiling.status_code, 400, over_ceiling.data)
        self.assertEqual(
            SpaceAccessRequest.objects.get(pk=pending.data["id"]).status,
            SpaceAccessRequest.STATUS_PENDING,
        )
        self.assertFalse(
            SpaceMembership.objects.filter(
                space=self.space,
                user=self.requester,
            ).exists()
        )

    def test_access_code_revoke_blocks_new_redemption_not_existing_request(self):
        issued = self.issue_code()
        self.auth(self.requester)
        pending = self.client.post(
            "/api/v1/spaces/access-code-requests/",
            {"code": issued.data["code"], "reason": "Before rotation"},
            format="json",
            **self.key(),
        )
        self.auth(self.owner)
        revoked = self.client.post(
            f"/api/v1/spaces/{self.space.id}/access-codes/{issued.data['id']}/revoke/",
            {"expected_code_version": 1, "reason_code": "rotated"},
            format="json",
            **self.key(),
        )
        self.assertEqual(revoked.status_code, 200, revoked.data)
        self.auth(self.other)
        blocked = self.client.post(
            "/api/v1/spaces/access-code-requests/",
            {"code": issued.data["code"], "reason": "After rotation"},
            format="json",
            **self.key(),
        )
        self.assertEqual(blocked.status_code, 404, blocked.data)
        self.assertEqual(blocked.data["code"], "access_code_not_available")
        self.assertEqual(
            SpaceAccessRequest.objects.get(pk=pending.data["id"]).status,
            "pending",
        )

    def issue_invitation(self, target=None, role="reviewer"):
        self.auth(self.owner)
        return self.client.post(
            f"/api/v1/spaces/{self.space.id}/invitations/",
            {
                "target_user_id": str((target or self.invitee).id),
                "target_email": None,
                "role": role,
                "expires_in_days": 7,
            },
            format="json",
            **self.key(),
        )

    def test_targeted_invitation_is_single_use_and_target_bound(self):
        issued = self.issue_invitation()
        self.assertEqual(issued.status_code, 201, issued.data)
        raw = issued.data["token"]
        invitation = SpaceInvitation.objects.get(pk=issued.data["id"])
        self.assertNotIn(raw, invitation.token_hash)
        listed = self.client.get(f"/api/v1/spaces/{self.space.id}/invitations/")
        self.assertNotIn("token", listed.data["results"][0])
        self.assertNotIn("token_hash", listed.data["results"][0])

        self.auth(self.other)
        wrong_key = uuid.uuid4()
        wrong = self.client.post(
            "/api/v1/space-invitations/redeem/",
            {"token": raw, "action": "accept"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(wrong_key),
        )
        wrong_replay = self.client.post(
            "/api/v1/space-invitations/redeem/",
            {"token": raw, "action": "accept"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(wrong_key),
        )
        self.assertEqual(wrong.status_code, 404, wrong.data)
        self.assertEqual(wrong_replay.status_code, 404, wrong_replay.data)
        self.assertEqual(wrong_replay["Idempotency-Replayed"], "true")
        self.assertFalse(
            SpaceMembership.objects.filter(space=self.space, user=self.other).exists()
        )

        self.auth(self.invitee)
        accepted = self.client.post(
            "/api/v1/space-invitations/redeem/",
            {"token": raw, "action": "accept"},
            format="json",
            **self.key(),
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)
        membership = SpaceMembership.objects.get(space=self.space, user=self.invitee)
        self.assertEqual(membership.role, "reviewer")
        self.assertEqual(membership.source_kind, "invitation")
        created_outbox = ActionOutboxEvent.objects.get(
            aggregate_type="space_invitation",
            aggregate_uuid=invitation.id,
            transition="created",
        )
        accepted_outbox = ActionOutboxEvent.objects.get(
            aggregate_type="space_invitation",
            aggregate_uuid=invitation.id,
            transition="accepted",
        )
        self.assertEqual(created_outbox.recipient_key, f"user:{self.invitee.id}")
        self.assertEqual(accepted_outbox.recipient_key, f"user:{self.owner.id}")
        self.assertNotIn(raw, str(created_outbox.payload))
        resolved = self.client.post(
            "/api/v1/space-invitations/redeem/",
            {"token": raw, "action": "accept"},
            format="json",
            **self.key(),
        )
        self.assertEqual(resolved.status_code, 409, resolved.data)
        self.assertEqual(resolved.data["code"], "invitation_already_resolved")

    def test_notification_action_delegates_to_invitation_service(self):
        issued = self.issue_invitation(target=self.other, role="guest")
        notification = Notification.objects.get(
            recipient=self.other,
            resource_uuid=issued.data["id"],
        )
        self.auth(self.other)
        feed = self.client.get("/api/v1/notifications/")
        actionable = next(
            row for row in feed.data["results"] if row["id"] == str(notification.id)
        )
        self.assertEqual(actionable["allowed_actions"], ["accept", "decline"])
        self.assertEqual(actionable["action_state"], "available")
        self.assertTrue(actionable["deep_link"].startswith("/spaces/discover"))
        self.assertNotIn(issued.data["token"], str(actionable))
        operation_key = uuid.uuid4()
        accepted = self.client.post(
            f"/api/v1/notifications/{notification.id}/actions/accept/",
            {"expected_resource_version": 1},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(operation_key),
        )
        replay = self.client.post(
            f"/api/v1/notifications/{notification.id}/actions/accept/",
            {"expected_resource_version": 1},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(operation_key),
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(replay["Idempotency-Replayed"], "true")
        membership = SpaceMembership.objects.get(space=self.space, user=self.other)
        self.assertEqual(membership.role, "guest")
        notification.refresh_from_db()
        self.assertEqual(notification.action_state, "actioned")
        self.assertEqual(notification.allowed_actions, [])

    def test_failed_action_keeps_notification_available_and_revoke_lists_it_stale(self):
        issued = self.issue_invitation(target=self.other, role="guest")
        notification = Notification.objects.get(
            recipient=self.other,
            resource_uuid=issued.data["id"],
        )
        self.auth(self.other)
        stale_version = self.client.post(
            f"/api/v1/notifications/{notification.id}/actions/accept/",
            {"expected_resource_version": 99},
            format="json",
            **self.key(),
        )
        self.assertEqual(stale_version.status_code, 409, stale_version.data)
        notification.refresh_from_db()
        self.assertEqual(notification.action_state, Notification.ACTION_AVAILABLE)
        self.assertEqual(notification.allowed_actions, ["accept", "decline"])
        self.assertFalse(
            SpaceMembership.objects.filter(space=self.space, user=self.other).exists()
        )

        self.auth(self.owner)
        revoked = self.client.post(
            f"/api/v1/spaces/{self.space.id}/invitations/{issued.data['id']}/revoke/",
            {"expected_invitation_version": 1, "reason_code": "access_no_longer_needed"},
            format="json",
            **self.key(),
        )
        self.assertEqual(revoked.status_code, 200, revoked.data)
        self.auth(self.other)
        feed = self.client.get("/api/v1/notifications/")
        stale_item = next(
            row for row in feed.data["results"] if row["id"] == str(notification.id)
        )
        self.assertEqual(stale_item["action_state"], Notification.ACTION_STALE)
        self.assertEqual(stale_item["allowed_actions"], [])

    def test_access_request_notification_delegates_to_owner_approval_service(self):
        issued = self.issue_code()
        self.auth(self.requester)
        pending = self.client.post(
            "/api/v1/spaces/access-code-requests/",
            {"code": issued.data["code"], "reason": "Notification approval"},
            format="json",
            **self.key(),
        )
        notification = Notification.objects.get(
            recipient=self.owner,
            resource_uuid=pending.data["id"],
        )
        self.auth(self.owner)

        approved = self.client.post(
            f"/api/v1/notifications/{notification.id}/actions/approve/",
            {"expected_resource_version": 1, "role": "member"},
            format="json",
            **self.key(),
        )

        self.assertEqual(approved.status_code, 200, approved.data)
        membership = SpaceMembership.objects.get(
            space=self.space,
            user=self.requester,
        )
        self.assertEqual(membership.role, SpaceMembership.ROLE_MEMBER)
        notification.refresh_from_db()
        self.assertEqual(notification.action_state, Notification.ACTION_ACTIONED)
        self.assertEqual(notification.allowed_actions, [])

    def test_access_approval_then_invitation_accept_converges_on_same_membership(self):
        invitation = self.issue_invitation(target=self.requester, role="reviewer")
        code = self.issue_code()
        self.auth(self.requester)
        pending = self.client.post(
            "/api/v1/spaces/access-code-requests/",
            {"code": code.data["code"], "reason": "Convergent access"},
            format="json",
            **self.key(),
        )
        self.auth(self.owner)
        approved = self.client.post(
            f"/api/v1/spaces/{self.space.id}/access-requests/{pending.data['id']}/approve/",
            {"expected_request_version": 1, "role": "member"},
            format="json",
            **self.key(),
        )
        self.assertEqual(approved.status_code, 200, approved.data)
        membership = SpaceMembership.objects.get(
            space=self.space,
            user=self.requester,
        )

        self.auth(self.requester)
        accepted = self.client.post(
            "/api/v1/space-invitations/redeem/",
            {"token": invitation.data["token"], "action": "accept"},
            format="json",
            **self.key(),
        )

        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertEqual(accepted.data["result"], "already_member")
        self.assertEqual(
            accepted.data["resulting_membership_uuid"],
            str(membership.id),
        )
        membership.refresh_from_db()
        self.assertEqual(membership.role, SpaceMembership.ROLE_MEMBER)
        self.assertEqual(
            SpaceMembership.objects.filter(
                space=self.space,
                user=self.requester,
            ).count(),
            1,
        )

    def test_email_target_requires_verified_binding_before_acceptance(self):
        self.auth(self.owner)
        issued = self.client.post(
            f"/api/v1/spaces/{self.space.id}/invitations/",
            {
                "target_user_id": None,
                "target_email": self.invitee.email,
                "role": "member",
                "expires_in_days": 7,
            },
            format="json",
            **self.key(),
        )
        self.assertEqual(issued.status_code, 201, issued.data)
        self.assertEqual(issued.data["target_kind"], "email")
        invitation = SpaceInvitation.objects.get(pk=issued.data["id"])
        self.assertIsNone(invitation.target_user_id)
        email_outbox = ActionOutboxEvent.objects.get(
            aggregate_type="space_invitation",
            aggregate_uuid=invitation.id,
            transition="created",
        )
        self.assertTrue(email_outbox.recipient_key.startswith("email_hmac:"))
        self.assertNotIn(self.invitee.email, str(email_outbox.payload))
        self.assertNotIn(issued.data["token"], str(email_outbox.payload))

        self.auth(self.invitee)
        unverified = self.client.post(
            "/api/v1/space-invitations/redeem/",
            {"token": issued.data["token"], "action": "accept"},
            format="json",
            **self.key(),
        )
        self.assertEqual(unverified.status_code, 404, unverified.data)

        from allauth.account.models import EmailAddress

        EmailAddress.objects.create(
            user=self.invitee,
            email=self.invitee.email,
            verified=True,
            primary=True,
        )
        accepted = self.client.post(
            "/api/v1/space-invitations/redeem/",
            {"token": issued.data["token"], "action": "accept"},
            format="json",
            **self.key(),
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertTrue(
            SpaceMembership.objects.filter(
                space=self.space,
                user=self.invitee,
                status="active",
            ).exists()
        )

    def test_owner_role_is_rejected_from_every_join_surface(self):
        owner_offer = self.issue_invitation(role="owner")
        self.assertEqual(owner_offer.status_code, 400, owner_offer.data)
        self.assertFalse(SpaceInvitation.objects.exists())
