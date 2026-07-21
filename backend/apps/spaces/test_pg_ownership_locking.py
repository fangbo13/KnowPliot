# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.

"""PostgreSQL regressions for ownership-transfer row locks and constraints.

Run this module in Compose so the assertions exercise PostgreSQL rather than
SQLite's no-op ``SELECT ... FOR UPDATE`` implementation::

    docker compose exec -T backend python manage.py test \
        apps.spaces.test_pg_ownership_locking --settings=config.settings.test
"""

import queue
import threading
import uuid

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections, transaction
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext

from apps.spaces.models import Organization, OwnershipTransfer, SpaceMembership
from apps.spaces.ownership import create_space_with_owner
from apps.spaces.ownership_services import OwnershipConflict, OwnershipTransferService

User = get_user_model()


class PgOwnershipLockingRegressionTests(TransactionTestCase):
    """Verify the ownership state machine against PostgreSQL's real locking."""

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("requires PostgreSQL; run through docker compose")
        self.owner = User.objects.create_user(
            username="pg-owner", email="pg-owner@example.test", password="safe-password"
        )
        self.successor = User.objects.create_user(
            username="pg-successor", email="pg-successor@example.test", password="safe-password"
        )
        organization = Organization.objects.create(name="PG ownership org", slug="pg-ownership-org")
        self.space = create_space_with_owner(
            organization=organization,
            owner=self.owner,
            name="PG ownership space",
            code="pg-ownership-space",
        )
        SpaceMembership.objects.create(
            space=self.space,
            user=self.successor,
            role=SpaceMembership.ROLE_MEMBER,
            status="active",
        )

    def _request(self):
        return OwnershipTransferService.request(
            actor=self.owner,
            space_id=self.space.id,
            to_owner_id=self.successor.id,
            expected_ownership_version=1,
            idempotency_key=uuid.uuid4(),
            reason_code="voluntary",
        )

    def test_accept_uses_postgresql_row_locks_and_switches_owner(self):
        transfer = self._request()

        with CaptureQueriesContext(connection) as queries:
            OwnershipTransferService.accept(actor=self.successor, transfer_id=transfer.id)

        lock_sql = [query["sql"].upper() for query in queries.captured_queries if "FOR UPDATE" in query["sql"].upper()]
        self.assertTrue(lock_sql, "accept must lock users, space, memberships, and transfer")
        self.assertTrue(all("FOR UPDATE OF" in sql for sql in lock_sql), lock_sql)
        joined = "\n".join(lock_sql)
        self.assertLess(joined.index('"USERS_USER"'), joined.index('"SPACES_KNOWLEDGESPACE"'))
        self.assertLess(joined.index('"SPACES_KNOWLEDGESPACE"'), joined.index('"SPACES_SPACEMEMBERSHIP"'))
        self.assertLess(joined.index('"SPACES_SPACEMEMBERSHIP"'), joined.index('"SPACES_OWNERSHIPTRANSFER"'))
        self.space.refresh_from_db()
        transfer.refresh_from_db()
        self.assertEqual(self.space.owner_id, self.successor.id)
        self.assertEqual(self.space.ownership_version, 2)

    def test_deferred_owner_trigger_rejects_canonical_mirror_divergence(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.space.owner = self.successor
                self.space.save(update_fields=["owner"])

        self.space.refresh_from_db()
        self.assertEqual(self.space.owner_id, self.owner.id)
        owner_membership = SpaceMembership.objects.get(
            space=self.space,
            role=SpaceMembership.ROLE_OWNER,
            status="active",
        )
        self.assertEqual(owner_membership.user_id, self.owner.id)

    def test_postgresql_pending_transfer_constraint_rejects_second_pending_row(self):
        first = self._request()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OwnershipTransfer.objects.create(
                    space=self.space,
                    from_owner=self.owner,
                    to_owner=self.successor,
                    requested_by=self.owner,
                    mode=OwnershipTransfer.MODE_VOLUNTARY,
                    status=OwnershipTransfer.STATUS_PENDING,
                    expected_ownership_version=1,
                    reason_code="voluntary",
                    idempotency_key=uuid.uuid4(),
                )

        first.refresh_from_db()
        self.assertEqual(first.status, OwnershipTransfer.STATUS_PENDING)

    def test_two_concurrent_accepts_have_exactly_one_success(self):
        transfer = self._request()
        barrier = threading.Barrier(2)
        results = queue.Queue()

        def accept_once():
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                OwnershipTransferService.accept(actor=self.successor, transfer_id=transfer.id)
                results.put("completed")
            except OwnershipConflict as exc:
                results.put(str(exc))
            finally:
                connections.close_all()

        threads = [threading.Thread(target=accept_once), threading.Thread(target=accept_once)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
            self.assertFalse(thread.is_alive(), "concurrent acceptance did not finish")

        outcomes = [results.get_nowait(), results.get_nowait()]
        self.assertEqual(outcomes.count("completed"), 1)
        self.assertEqual(outcomes.count("transfer_not_pending"), 1)
        self.space.refresh_from_db()
        self.assertEqual(self.space.owner_id, self.successor.id)
        self.assertEqual(self.space.ownership_version, 2)
