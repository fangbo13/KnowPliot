"""Atomic ownership-transfer state transitions."""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import KnowledgeSpace, OwnershipTransfer, SpaceMembership
from .ownership import (
    effective_business_admin,
    effective_org_admin,
    effective_platform_admin,
    effective_space_membership,
    effective_user,
)


class OwnershipConflict(Exception):
    """A stable domain conflict to map to the documented HTTP 409 errors."""


class OwnershipTransferService:
    @staticmethod
    def _audit_transition(*, actor, transfer, event):
        """Persist a scope-addressable, secret-free ownership transition audit."""

        from apps.audit.views import create_audit_log

        create_audit_log(
            user=actor,
            action="space_update",
            target_type="OwnershipTransfer",
            target_id=transfer.id,
            details={
                "ownership_event": event,
                "transfer_id": str(transfer.id),
                "mode": transfer.mode,
                "from_owner_id": str(transfer.from_owner_id),
                "to_owner_id": str(transfer.to_owner_id),
                "ownership_version": transfer.expected_ownership_version,
            },
            space_id=transfer.space_id,
        )

    @staticmethod
    def _notify_after_commit(recipient, *, title, body, metadata):
        """Queue best-effort delivery only after the state transaction commits."""

        from apps.notifications.services import notify

        transaction.on_commit(
            lambda: notify(
                recipient,
                "account",
                title=title,
                body=body,
                level="info",
                link="/spaces/manage",
                metadata=metadata,
            )
        )

    @staticmethod
    def _idempotency_replay(*, actor, idempotency_key, space_id, to_owner_id, expected_ownership_version, reason_code, mode):
        existing = OwnershipTransfer.objects.filter(
            requested_by=actor,
            idempotency_key=idempotency_key,
        ).first()
        if existing is None:
            return None
        if (
            existing.space_id == space_id
            and existing.to_owner_id == to_owner_id
            and existing.expected_ownership_version == expected_ownership_version
            and existing.reason_code == reason_code
            and existing.mode == mode
        ):
            return existing
        raise OwnershipConflict("idempotency_conflict")

    @staticmethod
    def request(*, actor, space_id, to_owner_id, expected_ownership_version, idempotency_key, reason_code):
        with transaction.atomic():
            replay = OwnershipTransferService._idempotency_replay(
                actor=actor,
                idempotency_key=idempotency_key,
                space_id=space_id,
                to_owner_id=to_owner_id,
                expected_ownership_version=expected_ownership_version,
                reason_code=reason_code,
                mode=OwnershipTransfer.MODE_VOLUNTARY,
            )
            if replay:
                return replay
            space = KnowledgeSpace.objects.select_for_update().get(pk=space_id)
            if space.owner_id != actor.id:
                raise OwnershipConflict("only_current_owner_may_request")
            if space.ownership_version != expected_ownership_version:
                raise OwnershipConflict("ownership_changed")
            if space.owner_id is None:
                raise OwnershipConflict("owner_continuity_required")
            target_membership = SpaceMembership.objects.select_for_update().select_related("user").filter(
                space=space, user_id=to_owner_id
            ).first()
            if not target_membership or target_membership.role == SpaceMembership.ROLE_GUEST or not effective_space_membership(target_membership):
                raise OwnershipConflict("invalid_successor")
            if target_membership.user_id == actor.id:
                raise OwnershipConflict("invalid_successor")
            try:
                transfer = OwnershipTransfer.objects.create(
                    space=space,
                    from_owner=actor,
                    to_owner=target_membership.user,
                    requested_by=actor,
                    mode=OwnershipTransfer.MODE_VOLUNTARY,
                    status=OwnershipTransfer.STATUS_PENDING,
                    expected_ownership_version=expected_ownership_version,
                    reason_code=reason_code,
                    idempotency_key=idempotency_key,
                    expires_at=timezone.now() + timedelta(hours=72),
                )
                OwnershipTransferService._audit_transition(
                    actor=actor, transfer=transfer, event="ownership_transfer_requested"
                )
                OwnershipTransferService._notify_after_commit(
                    target_membership.user,
                    title="Ownership transfer requested",
                    body="You have been nominated to take ownership of a knowledge space.",
                    metadata={"transfer_id": str(transfer.id), "space_id": str(space.id)},
                )
                return transfer
            except IntegrityError as exc:
                raise OwnershipConflict("transfer_already_pending") from exc

    @staticmethod
    def accept(*, actor, transfer_id):
        conflict = None
        with transaction.atomic():
            transfer = OwnershipTransfer.objects.select_for_update().get(pk=transfer_id)
            space = KnowledgeSpace.objects.select_for_update().get(pk=transfer.space_id)
            if transfer.status != OwnershipTransfer.STATUS_PENDING:
                raise OwnershipConflict("transfer_not_pending")
            if transfer.to_owner_id != actor.id:
                raise OwnershipConflict("transfer_not_for_actor")
            if transfer.expires_at and transfer.expires_at <= timezone.now():
                transfer.status = OwnershipTransfer.STATUS_EXPIRED
                transfer.save(update_fields=["status"])
                conflict = "transfer_expired"
            else:
                target = SpaceMembership.objects.select_for_update().select_related("user").get(
                    space=space, user_id=actor.id
                )
                current = SpaceMembership.objects.select_for_update().get(space=space, user_id=space.owner_id)
                if space.owner_id != transfer.from_owner_id or space.ownership_version != transfer.expected_ownership_version:
                    conflict = "transfer_invalidated"
                elif target.role == SpaceMembership.ROLE_GUEST or not effective_user(actor) or not effective_space_membership(target):
                    conflict = "transfer_invalidated"
                if conflict:
                    transfer.status = OwnershipTransfer.STATUS_INVALIDATED
                    transfer.save(update_fields=["status"])
                else:
                    current.role = SpaceMembership.ROLE_MEMBER
                    current.save(update_fields=["role", "updated_at"])
                    target.role = SpaceMembership.ROLE_OWNER
                    target.save(update_fields=["role", "updated_at"])
                    space.owner_id = actor.id
                    space.ownership_version += 1
                    space.save(update_fields=["owner", "ownership_version", "updated_at"])
                    transfer.status = OwnershipTransfer.STATUS_COMPLETED
                    transfer.accepted_by = actor
                    transfer.completed_at = timezone.now()
                    transfer.save(update_fields=["status", "accepted_by", "completed_at"])
                    OwnershipTransferService._audit_transition(
                        actor=actor, transfer=transfer, event="ownership_transfer_accepted"
                    )
                    OwnershipTransferService._notify_after_commit(
                        transfer.from_owner,
                        title="Ownership transfer completed",
                        body="The nominated successor accepted ownership of a knowledge space.",
                        metadata={"transfer_id": str(transfer.id), "space_id": str(space.id)},
                    )
        if conflict:
            raise OwnershipConflict(conflict)
        return transfer

    @staticmethod
    def decline(*, actor, transfer_id):
        with transaction.atomic():
            transfer = OwnershipTransfer.objects.select_for_update().get(pk=transfer_id)
            if transfer.status != OwnershipTransfer.STATUS_PENDING:
                raise OwnershipConflict("transfer_not_pending")
            if transfer.to_owner_id != actor.id:
                raise OwnershipConflict("transfer_not_for_actor")
            transfer.status = OwnershipTransfer.STATUS_DECLINED
            transfer.save(update_fields=["status"])
            OwnershipTransferService._audit_transition(
                actor=actor, transfer=transfer, event="ownership_transfer_declined"
            )
            OwnershipTransferService._notify_after_commit(
                transfer.from_owner,
                title="Ownership transfer declined",
                body="The nominated successor declined the ownership transfer request.",
                metadata={"transfer_id": str(transfer.id), "space_id": str(transfer.space_id)},
            )
        return transfer

    @staticmethod
    def cancel(*, actor, transfer_id):
        with transaction.atomic():
            transfer = OwnershipTransfer.objects.select_for_update().get(pk=transfer_id)
            if transfer.status != OwnershipTransfer.STATUS_PENDING:
                raise OwnershipConflict("transfer_not_pending")
            if transfer.requested_by_id != actor.id:
                raise OwnershipConflict("transfer_not_for_actor")
            transfer.status = OwnershipTransfer.STATUS_CANCELLED
            transfer.save(update_fields=["status"])
            OwnershipTransferService._audit_transition(
                actor=actor, transfer=transfer, event="ownership_transfer_cancelled"
            )
        return transfer

    @staticmethod
    def force(*, actor, space_id, to_owner_id, expected_ownership_version, idempotency_key, reason_code):
        """Immediately transfer ownership when the actor governs the space scope."""

        from django.contrib.auth import get_user_model

        with transaction.atomic():
            replay = OwnershipTransferService._idempotency_replay(
                actor=actor,
                idempotency_key=idempotency_key,
                space_id=space_id,
                to_owner_id=to_owner_id,
                expected_ownership_version=expected_ownership_version,
                reason_code=reason_code,
                mode=OwnershipTransfer.MODE_FORCED,
            )
            if replay:
                return replay
            space = KnowledgeSpace.objects.select_for_update().get(pk=space_id)
            can_force = (
                effective_platform_admin(actor)
                or effective_org_admin(actor, space.organization)
                or (space.business_line_id and effective_business_admin(actor, space.business_line))
            )
            if not can_force:
                raise OwnershipConflict("insufficient_scope")
            if space.ownership_version != expected_ownership_version:
                raise OwnershipConflict("ownership_changed")
            if space.owner_id is None:
                raise OwnershipConflict("owner_continuity_required")
            if space.owner_id == to_owner_id:
                raise OwnershipConflict("invalid_successor")
            target = get_user_model().objects.select_for_update().get(pk=to_owner_id)
            if not effective_user(target):
                raise OwnershipConflict("invalid_successor")
            belongs_to_org = SpaceMembership.objects.select_related("user").filter(
                user=target,
                space__organization=space.organization,
                status="active",
            ).exists()
            if not belongs_to_org:
                raise OwnershipConflict("invalid_successor")
            target_membership, _ = SpaceMembership.objects.select_for_update().get_or_create(
                space=space,
                user=target,
                defaults={"role": SpaceMembership.ROLE_MEMBER, "status": "active"},
            )
            if target_membership.status != "active":
                target_membership.status = "active"
            target_membership.role = SpaceMembership.ROLE_OWNER
            pending_transfers = list(
                OwnershipTransfer.objects.select_for_update().filter(
                    space=space,
                    status=OwnershipTransfer.STATUS_PENDING,
                )
            )
            for pending in pending_transfers:
                pending.status = OwnershipTransfer.STATUS_INVALIDATED
                pending.save(update_fields=["status"])
            current = SpaceMembership.objects.select_for_update().filter(
                space=space, user_id=space.owner_id
            ).first()
            if current is None:
                raise OwnershipConflict("owner_continuity_required")
            current.role = SpaceMembership.ROLE_MEMBER
            current.save(update_fields=["role", "updated_at"])
            target_membership.save(update_fields=["role", "status", "updated_at"])
            space.owner_id = target.id
            space.ownership_version += 1
            space.save(update_fields=["owner", "ownership_version", "updated_at"])
            transfer = OwnershipTransfer.objects.create(
                space=space,
                from_owner_id=current.user_id,
                to_owner=target,
                requested_by=actor,
                mode=OwnershipTransfer.MODE_FORCED,
                status=OwnershipTransfer.STATUS_COMPLETED,
                expected_ownership_version=expected_ownership_version,
                reason_code=reason_code,
                idempotency_key=idempotency_key,
                completed_at=timezone.now(),
            )
            OwnershipTransferService._audit_transition(
                actor=actor, transfer=transfer, event="ownership_transfer_forced"
            )
            OwnershipTransferService._notify_after_commit(
                target,
                title="Ownership transferred by an administrator",
                body="An administrator transferred ownership of a knowledge space to you.",
                metadata={"transfer_id": str(transfer.id), "space_id": str(space.id)},
            )
        return transfer
