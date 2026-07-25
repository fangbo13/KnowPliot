"""Atomic ownership-transfer state transitions."""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    BusinessLine,
    KnowledgeSpace,
    Organization,
    OrganizationMembership,
    OwnershipTransfer,
    SpaceMembership,
)
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
    def _lock_users(*user_ids):
        from django.contrib.auth import get_user_model

        rows = list(
            get_user_model()
            .objects.select_for_update(of=("self",))
            .filter(pk__in=set(user_ids))
            .order_by("pk")
        )
        return {str(row.pk): row for row in rows}

    @staticmethod
    def _lock_space(space_id):
        return (
            KnowledgeSpace.objects.select_for_update(of=("self",))
            .order_by("pk")
            .get(pk=space_id)
        )

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
            locked_users = OwnershipTransferService._lock_users(actor.pk, to_owner_id)
            locked_actor = locked_users.get(str(actor.pk))
            target_user = locked_users.get(str(to_owner_id))
            if locked_actor is None or target_user is None or not effective_user(target_user):
                raise OwnershipConflict("invalid_successor")
            replay = OwnershipTransferService._idempotency_replay(
                actor=locked_actor,
                idempotency_key=idempotency_key,
                space_id=space_id,
                to_owner_id=to_owner_id,
                expected_ownership_version=expected_ownership_version,
                reason_code=reason_code,
                mode=OwnershipTransfer.MODE_VOLUNTARY,
            )
            if replay:
                return replay
            space = OwnershipTransferService._lock_space(space_id)
            if space.owner_id != locked_actor.id:
                raise OwnershipConflict("only_current_owner_may_request")
            if space.ownership_version != expected_ownership_version:
                raise OwnershipConflict("ownership_changed")
            if space.owner_id is None:
                raise OwnershipConflict("owner_continuity_required")
            target_membership = SpaceMembership.objects.select_for_update(of=("self",)).filter(
                space=space, user_id=to_owner_id
            ).order_by("pk").first()
            if target_membership is not None:
                # Already a space member — must be effective and not a guest.
                if target_membership.role == SpaceMembership.ROLE_GUEST or not effective_space_membership(target_membership):
                    raise OwnershipConflict("invalid_successor")
            else:
                # Not a space member — verify the target belongs to the same
                # organization so ownership can be granted on acceptance.
                target_org_memberships = list(
                    SpaceMembership.objects.select_for_update(of=("self",)).filter(
                        user_id=to_owner_id,
                        space__organization=space.organization,
                        status="active",
                    ).order_by("pk")
                )
                if not target_org_memberships:
                    raise OwnershipConflict("invalid_successor")
            if to_owner_id == locked_actor.id:
                raise OwnershipConflict("invalid_successor")
            try:
                transfer = OwnershipTransfer.objects.create(
                    space=space,
                    from_owner=locked_actor,
                    to_owner=target_user,
                    requested_by=locked_actor,
                    mode=OwnershipTransfer.MODE_VOLUNTARY,
                    status=OwnershipTransfer.STATUS_PENDING,
                    expected_ownership_version=expected_ownership_version,
                    reason_code=reason_code,
                    idempotency_key=idempotency_key,
                    expires_at=timezone.now() + timedelta(hours=72),
                )
                OwnershipTransferService._audit_transition(
                    actor=locked_actor, transfer=transfer, event="ownership_transfer_requested"
                )
                OwnershipTransferService._notify_after_commit(
                    target_user,
                    title="Ownership transfer requested",
                    body="You have been nominated to take ownership of a knowledge space.",
                    metadata={"transfer_id": str(transfer.id), "space_id": str(space.id)},
                )
                return transfer
            except IntegrityError as exc:
                raise OwnershipConflict("transfer_already_pending") from exc

    @staticmethod
    def accept(*, actor, transfer_id):
        reference = OwnershipTransfer.objects.only(
            "space_id", "from_owner_id", "to_owner_id"
        ).get(pk=transfer_id)
        conflict = None
        with transaction.atomic():
            locked_users = OwnershipTransferService._lock_users(
                actor.pk, reference.from_owner_id, reference.to_owner_id
            )
            locked_actor = locked_users.get(str(actor.pk))
            space = OwnershipTransferService._lock_space(reference.space_id)
            membership_rows = list(
                SpaceMembership.objects.select_for_update(of=("self",))
                .filter(
                    space_id=reference.space_id,
                    user_id__in={reference.from_owner_id, reference.to_owner_id},
                )
                .order_by("pk")
            )
            memberships = {row.user_id: row for row in membership_rows}
            transfer = (
                OwnershipTransfer.objects.select_for_update(of=("self",))
                .order_by("pk")
                .get(pk=transfer_id)
            )
            if (
                transfer.space_id != reference.space_id
                or transfer.from_owner_id != reference.from_owner_id
                or transfer.to_owner_id != reference.to_owner_id
            ):
                raise OwnershipConflict("transfer_invalidated")
            if transfer.status != OwnershipTransfer.STATUS_PENDING:
                raise OwnershipConflict("transfer_not_pending")
            if locked_actor is None or transfer.to_owner_id != locked_actor.id:
                raise OwnershipConflict("transfer_not_for_actor")
            if transfer.expires_at and transfer.expires_at <= timezone.now():
                transfer.status = OwnershipTransfer.STATUS_EXPIRED
                transfer.save(update_fields=["status"])
                conflict = "transfer_expired"
            else:
                target = memberships.get(transfer.to_owner_id)
                current = memberships.get(transfer.from_owner_id)
                if current is None:
                    conflict = "transfer_invalidated"
                elif space.owner_id != transfer.from_owner_id or space.ownership_version != transfer.expected_ownership_version:
                    conflict = "transfer_invalidated"
                elif not effective_user(locked_actor):
                    conflict = "transfer_invalidated"
                elif target is not None and (target.role == SpaceMembership.ROLE_GUEST or not effective_space_membership(target)):
                    conflict = "transfer_invalidated"
                if conflict:
                    transfer.status = OwnershipTransfer.STATUS_INVALIDATED
                    transfer.save(update_fields=["status"])
                else:
                    # Downgrade the current owner to a regular member first
                    # so the single-active-owner-membership constraint is
                    # not violated when creating or updating the new owner.
                    current.role = SpaceMembership.ROLE_MEMBER
                    current.save(update_fields=["role", "updated_at"])
                    if target is None:
                        # Successor is not yet a space member — create the
                        # membership as part of accepting the ownership transfer.
                        target = SpaceMembership.objects.create(
                            space=space,
                            user_id=transfer.to_owner_id,
                            role=SpaceMembership.ROLE_OWNER,
                            status="active",
                            source_kind=SpaceMembership.SOURCE_OWNERSHIP,
                        )
                    else:
                        target.role = SpaceMembership.ROLE_OWNER
                        target.save(update_fields=["role", "updated_at"])
                    space.owner_id = locked_actor.id
                    space.ownership_version += 1
                    space.save(update_fields=["owner", "ownership_version", "updated_at"])
                    transfer.status = OwnershipTransfer.STATUS_COMPLETED
                    transfer.accepted_by = locked_actor
                    transfer.completed_at = timezone.now()
                    transfer.save(update_fields=["status", "accepted_by", "completed_at"])
                    OwnershipTransferService._audit_transition(
                        actor=locked_actor, transfer=transfer, event="ownership_transfer_accepted"
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
            transfer = OwnershipTransfer.objects.select_for_update(of=("self",)).order_by("pk").get(pk=transfer_id)
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
            transfer = OwnershipTransfer.objects.select_for_update(of=("self",)).order_by("pk").get(pk=transfer_id)
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

        if str(actor.pk) == str(to_owner_id):
            raise OwnershipConflict("actor_target_separation_required")

        space_reference = KnowledgeSpace.objects.only(
            "id", "organization_id", "business_line_id"
        ).get(pk=space_id)

        with transaction.atomic():
            locked_users = OwnershipTransferService._lock_users(actor.pk, to_owner_id)
            locked_actor = locked_users.get(str(actor.pk))
            target = locked_users.get(str(to_owner_id))
            if locked_actor is None or target is None or not effective_user(target):
                raise OwnershipConflict("invalid_successor")
            replay = OwnershipTransferService._idempotency_replay(
                actor=locked_actor,
                idempotency_key=idempotency_key,
                space_id=space_id,
                to_owner_id=to_owner_id,
                expected_ownership_version=expected_ownership_version,
                reason_code=reason_code,
                mode=OwnershipTransfer.MODE_FORCED,
            )
            if replay:
                return replay
            organization = (
                Organization.objects.select_for_update(of=("self",))
                .order_by("pk")
                .get(pk=space_reference.organization_id)
            )
            business_line = None
            if space_reference.business_line_id:
                business_line = (
                    BusinessLine.objects.select_for_update(of=("self",))
                    .order_by("pk")
                    .get(pk=space_reference.business_line_id)
                )
            space = OwnershipTransferService._lock_space(space_id)
            list(
                OrganizationMembership.objects.select_for_update(of=("self",))
                .filter(user_id=locked_actor.pk, organization_id=organization.pk)
                .order_by("pk")
            )
            from apps.rbac.models import UserRole

            list(
                UserRole.objects.select_for_update(of=("self",))
                .filter(user_id=locked_actor.pk)
                .order_by("pk")
            )
            can_force = (
                effective_platform_admin(locked_actor)
                or effective_org_admin(locked_actor, organization)
                or (business_line is not None and effective_business_admin(locked_actor, business_line))
            )
            if not can_force:
                raise OwnershipConflict("insufficient_scope")
            if space.ownership_version != expected_ownership_version:
                raise OwnershipConflict("ownership_changed")
            if space.owner_id is None:
                raise OwnershipConflict("owner_continuity_required")
            if space.owner_id == to_owner_id:
                raise OwnershipConflict("invalid_successor")
            target_org_memberships = list(
                SpaceMembership.objects.select_for_update(of=("self",)).filter(
                user=target,
                space__organization=space.organization,
                status="active",
                ).order_by("pk")
            )
            if not target_org_memberships:
                raise OwnershipConflict("invalid_successor")
            current_space_memberships = list(
                SpaceMembership.objects.select_for_update(of=("self",))
                .filter(space=space, user_id__in={space.owner_id, target.pk})
                .order_by("pk")
            )
            membership_by_user = {row.user_id: row for row in current_space_memberships}
            target_membership = membership_by_user.get(target.pk)
            if target_membership is None:
                target_membership = SpaceMembership.objects.create(
                    space=space,
                    user=target,
                    role=SpaceMembership.ROLE_MEMBER,
                    status="active",
                )
            if target_membership.status != "active":
                target_membership.status = "active"
            target_membership.role = SpaceMembership.ROLE_OWNER
            pending_transfers = list(
                OwnershipTransfer.objects.select_for_update(of=("self",)).filter(
                    space=space,
                    status=OwnershipTransfer.STATUS_PENDING,
                ).order_by("pk")
            )
            for pending in pending_transfers:
                pending.status = OwnershipTransfer.STATUS_INVALIDATED
                pending.save(update_fields=["status"])
            current = membership_by_user.get(space.owner_id)
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
                requested_by=locked_actor,
                mode=OwnershipTransfer.MODE_FORCED,
                status=OwnershipTransfer.STATUS_COMPLETED,
                expected_ownership_version=expected_ownership_version,
                reason_code=reason_code,
                idempotency_key=idempotency_key,
                completed_at=timezone.now(),
            )
            OwnershipTransferService._audit_transition(
                actor=locked_actor, transfer=transfer, event="ownership_transfer_forced"
            )
            OwnershipTransferService._notify_after_commit(
                target,
                title="Ownership transferred by an administrator",
                body="An administrator transferred ownership of a knowledge space to you.",
                metadata={"transfer_id": str(transfer.id), "space_id": str(space.id)},
            )
        return transfer
