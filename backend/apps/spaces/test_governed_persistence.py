"""Minimal persistence contracts for the governed-workflow aggregates."""

import hashlib
import uuid

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from django.contrib.auth import get_user_model

from apps.spaces.models import (
    BusinessLine,
    GovernedActionRequest,
    Organization,
    WorkspaceCreationPolicy,
    WorkspaceLocatorReservation,
    WriteIdempotencyRecord,
)

User = get_user_model()


class GovernedPersistenceContractTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="governed-persistence-user",
            email="governed-persistence-user@example.test",
            password="safe-password",
        )
        self.organization = Organization.objects.create(
            name="Governed persistence org",
            slug="governed-persistence-org",
        )
        self.business_line = BusinessLine.objects.create(
            organization=self.organization,
            name="Assurance",
            code="assurance",
        )

    def test_policy_revision_is_unique_and_locator_live_state_requires_space(self):
        WorkspaceCreationPolicy.objects.create(
            business_line=self.business_line,
            revision=1,
            created_by=self.user,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WorkspaceCreationPolicy.objects.create(
                    business_line=self.business_line,
                    revision=1,
                    created_by=self.user,
                )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WorkspaceLocatorReservation.objects.create(
                    organization=self.organization,
                    normalized_code="live-without-space",
                    state=WorkspaceLocatorReservation.STATE_LIVE,
                )

    def test_request_and_idempotency_digest_shape_is_database_enforced(self):
        bad_digest = "not-a-sha256"
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                GovernedActionRequest.objects.create(
                    action_type=GovernedActionRequest.ACTION_WORKSPACE_CREATE,
                    requester=self.user,
                    requester_uuid=self.user.pk,
                    organization=self.organization,
                    business_line=self.business_line,
                    idempotency_key=uuid.uuid4(),
                    request_digest=bad_digest,
                )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WriteIdempotencyRecord.objects.create(
                    actor_uuid=self.user.pk,
                    operation_code="workspace.create",
                    key=uuid.uuid4(),
                    request_digest=bad_digest,
                    expires_at=timezone.now() + timezone.timedelta(days=1),
                )

    def test_idempotency_key_is_unique_per_actor_operation(self):
        digest = hashlib.sha256(b"same request").hexdigest()
        key = uuid.uuid4()
        WriteIdempotencyRecord.objects.create(
            actor_uuid=self.user.pk,
            operation_code="workspace.create",
            key=key,
            request_digest=digest,
            expires_at=timezone.now() + timezone.timedelta(days=1),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WriteIdempotencyRecord.objects.create(
                    actor_uuid=self.user.pk,
                    operation_code="workspace.create",
                    key=key,
                    request_digest=digest,
                    expires_at=timezone.now() + timezone.timedelta(days=1),
                )
