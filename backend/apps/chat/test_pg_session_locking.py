# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""PostgreSQL regression tests for chat session/Turn row-locking queries.

These exercise the real ORM repositories (`DjangoSessionRepository`,
`DjangoTurnRepository`) against a live database. SQLite silently ignores
`SELECT ... FOR UPDATE` on the nullable side of an outer join, so the chat
send path's 500 (`NotSupportedError: FOR UPDATE cannot be applied to the
nullable side of an outer join`) only reproduces on PostgreSQL. Run against
the docker PostgreSQL::

    docker compose exec backend python manage.py test \
        apps.chat.test_pg_session_locking --settings=config.settings.test

The tests pass on SQLite too (FOR UPDATE is ignored there), but they only
*catch* the regression on PostgreSQL — which is the deployment database and
the one the previous SQLite-only suite could not cover.
"""

import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TransactionTestCase

from apps.chat.models import ChatSession, ChatTurn, Message
from apps.chat.services import DjangoSessionRepository, DjangoTurnRepository
from apps.spaces.models import KnowledgeSpace, Organization
from apps.spaces.test_utils import create_test_space

User = get_user_model()


class PgSessionLockingRegressionTest(TransactionTestCase):
    """Reproduce the FOR UPDATE + nullable-FK outer-join failure on PostgreSQL.

    `ChatSession.space` and `ChatTurn.assistant_message` are nullable FKs, so
    `select_for_update()` combined with `select_related(...)` produces a LEFT
    OUTER JOIN. PostgreSQL rejects `FOR UPDATE` on the nullable side of an
    outer join; SQLite does not enforce it, which is why this only surfaces on
    the real deployment database.
    """

    serialized_rollback = True

    def setUp(self):
        self.org = Organization.objects.create(
            name="PG Lock Test Org", slug="pg-lock-test"
        )
        self.space = create_test_space(
            code="pg-lock-space",
            organization=self.org,
            name="PG Lock Space",
            visibility="organization",
        )
        self.user = User(email="pg-lock@example.test", username="pg-lock@example.test")
        self.user.set_password("x")
        self.user.save()

        # A session WITH a space — the LEFT OUTER JOIN still occurs because
        # the FK is nullable, so this path is at risk even when space is set.
        self.session_with_space = ChatSession.objects.create(
            user=self.user, space=self.space, title="with-space"
        )
        # A session WITHOUT a space — the nullable FK is actually NULL.
        self.session_no_space = ChatSession.objects.create(
            user=self.user, space=None, title="no-space"
        )

        self.question = Message.objects.create(
            session=self.session_with_space,
            role="user",
            content="hello",
            space=self.space,
        )
        self.client_request_id = uuid.uuid4()
        # A Turn with NO assistant message — the nullable OneToOne LEFT JOIN
        # is the at-risk path for `find_turn`.
        self.turn = ChatTurn.objects.create(
            client_request_id=self.client_request_id,
            session=self.session_with_space,
            space=self.space,
            user=self.user,
            question_message=self.question,
            assistant_message=None,
            status=ChatTurn.STATUS_ACCEPTED,
            answer_mode=ChatTurn.ANSWER_MODE_FAST,
        )

    def test_find_session_with_space_locks_without_error(self):
        with transaction.atomic():
            found = DjangoSessionRepository().find_session(self.session_with_space.id)
        self.assertIsNotNone(found)
        self.assertEqual(found.id, self.session_with_space.id)
        self.assertEqual(found.space_id, self.space.id)

    def test_find_session_with_null_space_locks_without_error(self):
        with transaction.atomic():
            found = DjangoSessionRepository().find_session(self.session_no_space.id)
        self.assertIsNotNone(found)
        self.assertEqual(found.id, self.session_no_space.id)
        self.assertIsNone(found.space_id)

    def test_lock_session_locks_without_error(self):
        with transaction.atomic():
            found = DjangoTurnRepository().lock_session(self.session_with_space.id)
        self.assertIsNotNone(found)
        self.assertEqual(found.id, self.session_with_space.id)

    def test_find_turn_with_null_assistant_message_locks_without_error(self):
        with transaction.atomic():
            found = DjangoTurnRepository().find_turn(self.user, self.client_request_id)
        self.assertIsNotNone(found)
        self.assertEqual(found.id, self.turn.id)
        self.assertIsNone(found.assistant_message_id)

    def test_find_turn_missing_returns_none_without_error(self):
        with transaction.atomic():
            found = DjangoTurnRepository().find_turn(self.user, uuid.uuid4())
        self.assertIsNone(found)
