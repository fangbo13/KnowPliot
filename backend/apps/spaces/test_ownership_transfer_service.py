import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.notifications.models import Notification
from apps.spaces.models import Organization, OrganizationMembership, OwnershipTransfer, SpaceMembership
from apps.spaces.ownership import create_space_with_owner


class OwnershipTransferServiceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="owner", email="owner@example.test", password="safe-password"
        )
        self.successor = user_model.objects.create_user(
            username="successor", email="successor@example.test", password="safe-password"
        )
        organization = Organization.objects.create(name="Transfer Org", slug="transfer-org")
        self.space = create_space_with_owner(
            organization=organization, owner=self.owner, name="Transfer space", code="transfer-space"
        )
        SpaceMembership.objects.create(
            space=self.space, user=self.successor, role=SpaceMembership.ROLE_MEMBER, status="active"
        )

    def _request(self):
        from apps.spaces.ownership_services import OwnershipTransferService

        return OwnershipTransferService.request(
            actor=self.owner,
            space_id=self.space.id,
            to_owner_id=self.successor.id,
            expected_ownership_version=1,
            idempotency_key=uuid.uuid4(),
            reason_code="voluntary",
        )

    def test_voluntary_request_keeps_current_owner_until_successor_accepts(self):
        from apps.spaces.ownership_services import OwnershipTransferService

        transfer = self._request()

        self.space.refresh_from_db()
        self.assertEqual(transfer.status, OwnershipTransfer.STATUS_PENDING)
        self.assertEqual(self.space.owner_id, self.owner.id)
        self.assertEqual(
            SpaceMembership.objects.get(space=self.space, user=self.owner).role,
            SpaceMembership.ROLE_OWNER,
        )

    def test_transfer_audits_and_notifies_only_after_commit(self):
        from apps.spaces.ownership_services import OwnershipTransferService

        with self.captureOnCommitCallbacks(execute=True):
            transfer = self._request()

        audit = AuditLog.objects.get(target_id=transfer.id)
        notification = Notification.objects.get(recipient=self.successor)
        self.assertEqual(audit.action, "space_update")
        self.assertEqual(audit.details["ownership_event"], "ownership_transfer_requested")
        self.assertEqual(audit.details["to_owner_id"], str(self.successor.id))
        self.assertEqual(notification.metadata["transfer_id"], str(transfer.id))
        self.assertEqual(notification.metadata["space_id"], str(self.space.id))

        with self.captureOnCommitCallbacks(execute=True):
            OwnershipTransferService.accept(actor=self.successor, transfer_id=transfer.id)

        self.assertTrue(
            AuditLog.objects.filter(
                target_id=transfer.id,
                details__ownership_event="ownership_transfer_accepted",
            ).exists()
        )
        self.assertTrue(Notification.objects.filter(recipient=self.owner).exists())

    def test_acceptance_switches_canonical_owner_and_owner_mirror_atomically(self):
        from apps.spaces.ownership_services import OwnershipTransferService

        transfer = self._request()
        completed = OwnershipTransferService.accept(actor=self.successor, transfer_id=transfer.id)

        self.space.refresh_from_db()
        self.assertEqual(completed.status, OwnershipTransfer.STATUS_COMPLETED)
        self.assertEqual(completed.accepted_by_id, self.successor.id)
        self.assertEqual(self.space.owner_id, self.successor.id)
        self.assertEqual(self.space.ownership_version, 2)
        self.assertEqual(
            SpaceMembership.objects.get(space=self.space, user=self.owner).role,
            SpaceMembership.ROLE_MEMBER,
        )
        self.assertEqual(
            SpaceMembership.objects.get(space=self.space, user=self.successor).role,
            SpaceMembership.ROLE_OWNER,
        )

    def test_decline_and_cancel_are_terminal_without_changing_owner(self):
        from apps.spaces.ownership_services import OwnershipTransferService

        declined = OwnershipTransferService.decline(actor=self.successor, transfer_id=self._request().id)
        cancelled = OwnershipTransferService.cancel(actor=self.owner, transfer_id=self._request().id)

        self.space.refresh_from_db()
        self.assertEqual(declined.status, OwnershipTransfer.STATUS_DECLINED)
        self.assertEqual(cancelled.status, OwnershipTransfer.STATUS_CANCELLED)
        self.assertEqual(self.space.owner_id, self.owner.id)
        self.assertEqual(self.space.ownership_version, 1)

    def test_expired_or_invalidated_transfer_keeps_owner_and_records_terminal_state(self):
        from apps.spaces.ownership_services import OwnershipConflict, OwnershipTransferService

        expired = self._request()
        OwnershipTransfer.objects.filter(pk=expired.id).update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaisesRegex(OwnershipConflict, "transfer_expired"):
            OwnershipTransferService.accept(actor=self.successor, transfer_id=expired.id)
        expired.refresh_from_db()

        invalidated = self._request()
        SpaceMembership.objects.filter(space=self.space, user=self.successor).update(status="revoked")
        with self.assertRaisesRegex(OwnershipConflict, "transfer_invalidated"):
            OwnershipTransferService.accept(actor=self.successor, transfer_id=invalidated.id)
        invalidated.refresh_from_db()
        self.space.refresh_from_db()

        self.assertEqual(expired.status, OwnershipTransfer.STATUS_EXPIRED)
        self.assertEqual(invalidated.status, OwnershipTransfer.STATUS_INVALIDATED)
        self.assertEqual(self.space.owner_id, self.owner.id)

    def test_org_admin_can_force_transfer_to_active_same_org_user_without_membership(self):
        from apps.spaces.ownership_services import OwnershipTransferService

        governor = get_user_model().objects.create_user(
            username="governor", email="governor@example.test", password="safe-password"
        )
        successor = get_user_model().objects.create_user(
            username="external-successor", email="external-successor@example.test", password="safe-password"
        )
        OrganizationMembership.objects.create(
            user=governor,
            organization=self.space.organization,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )
        create_space_with_owner(
            organization=self.space.organization,
            owner=successor,
            name="Successor home",
            code="successor-home",
        )

        transfer = OwnershipTransferService.force(
            actor=governor,
            space_id=self.space.id,
            to_owner_id=successor.id,
            expected_ownership_version=1,
            idempotency_key=uuid.uuid4(),
            reason_code="employment_ended",
        )

        self.space.refresh_from_db()
        membership = SpaceMembership.objects.get(space=self.space, user=successor)
        self.assertEqual(transfer.mode, OwnershipTransfer.MODE_FORCED)
        self.assertEqual(transfer.status, OwnershipTransfer.STATUS_COMPLETED)
        self.assertIsNone(transfer.accepted_by_id)
        self.assertEqual(self.space.owner_id, successor.id)
        self.assertEqual(membership.role, SpaceMembership.ROLE_OWNER)

    def test_force_rejects_actor_as_target_even_when_actor_is_same_org_member(self):
        from apps.spaces.ownership_services import OwnershipConflict, OwnershipTransferService

        governor = get_user_model().objects.create_user(
            username="self-target-governor",
            email="self-target-governor@example.test",
            password="safe-password",
        )
        OrganizationMembership.objects.create(
            user=governor,
            organization=self.space.organization,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )
        create_space_with_owner(
            organization=self.space.organization,
            owner=governor,
            name="Governor home",
            code="self-target-governor-home",
        )

        with self.assertRaisesRegex(OwnershipConflict, "actor_target_separation_required"):
            OwnershipTransferService.force(
                actor=governor,
                space_id=self.space.id,
                to_owner_id=governor.id,
                expected_ownership_version=1,
                idempotency_key=uuid.uuid4(),
                reason_code="forced",
            )

        self.space.refresh_from_db()
        self.assertEqual(self.space.owner_id, self.owner.id)

    def test_idempotency_replay_returns_original_but_changed_request_conflicts(self):
        from apps.spaces.ownership_services import OwnershipConflict, OwnershipTransferService

        key = uuid.uuid4()
        first = OwnershipTransferService.request(
            actor=self.owner,
            space_id=self.space.id,
            to_owner_id=self.successor.id,
            expected_ownership_version=1,
            idempotency_key=key,
            reason_code="voluntary",
        )
        replay = OwnershipTransferService.request(
            actor=self.owner,
            space_id=self.space.id,
            to_owner_id=self.successor.id,
            expected_ownership_version=1,
            idempotency_key=key,
            reason_code="voluntary",
        )

        self.assertEqual(replay.id, first.id)
        with self.assertRaisesRegex(OwnershipConflict, "idempotency_conflict"):
            OwnershipTransferService.request(
                actor=self.owner,
                space_id=self.space.id,
                to_owner_id=self.owner.id,
                expected_ownership_version=1,
                idempotency_key=key,
                reason_code="voluntary",
            )

    def test_force_idempotency_replay_does_not_repeat_the_transfer(self):
        from apps.spaces.ownership_services import OwnershipConflict, OwnershipTransferService

        governor = get_user_model().objects.create_user(
            username="idempotent-governor", email="idempotent-governor@example.test", password="safe-password"
        )
        OrganizationMembership.objects.create(
            user=governor,
            organization=self.space.organization,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )
        key = uuid.uuid4()
        first = OwnershipTransferService.force(
            actor=governor,
            space_id=self.space.id,
            to_owner_id=self.successor.id,
            expected_ownership_version=1,
            idempotency_key=key,
            reason_code="employment_ended",
        )
        replay = OwnershipTransferService.force(
            actor=governor,
            space_id=self.space.id,
            to_owner_id=self.successor.id,
            expected_ownership_version=1,
            idempotency_key=key,
            reason_code="employment_ended",
        )

        self.assertEqual(replay.id, first.id)
        with self.assertRaisesRegex(OwnershipConflict, "idempotency_conflict"):
            OwnershipTransferService.force(
                actor=governor,
                space_id=self.space.id,
                to_owner_id=self.owner.id,
                expected_ownership_version=1,
                idempotency_key=key,
                reason_code="employment_ended",
            )

    def test_forced_transfer_invalidates_existing_pending_voluntary_transfer(self):
        from apps.spaces.ownership_services import OwnershipTransferService

        pending = self._request()
        governor = get_user_model().objects.create_user(
            username="force-governor", email="force-governor@example.test", password="safe-password"
        )
        replacement = get_user_model().objects.create_user(
            username="forced-replacement", email="forced-replacement@example.test", password="safe-password"
        )
        OrganizationMembership.objects.create(
            user=governor,
            organization=self.space.organization,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )
        create_space_with_owner(
            organization=self.space.organization,
            owner=replacement,
            name="Replacement home",
            code="replacement-home",
        )

        OwnershipTransferService.force(
            actor=governor,
            space_id=self.space.id,
            to_owner_id=replacement.id,
            expected_ownership_version=1,
            idempotency_key=uuid.uuid4(),
            reason_code="emergency",
        )

        pending.refresh_from_db()
        self.assertEqual(pending.status, OwnershipTransfer.STATUS_INVALIDATED)
