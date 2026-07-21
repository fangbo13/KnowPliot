"""Phase 8C pinned sessions and safe export tests."""

import subprocess
import sys
import unittest
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.spaces.models import (
    GovernancePolicy,
    KnowledgeSpace,
    ModelProfile,
    Organization,
    OrganizationMembership,
    SpaceMembership,
)
from apps.spaces.test_utils import create_test_space

from .coordination import CoordinationUnavailableError
from .models import ChatSession, ChatTurn, Message

User = get_user_model()
BACKEND_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = BACKEND_ROOT.parent / "frontend" / "dist"


class V10ProductSmokeScriptTest(SimpleTestCase):
    @unittest.skipUnless(FRONTEND_DIST.exists(), "frontend build is not mounted")
    def test_v10_smoke_validates_frontend_build(self):
        result = subprocess.run(
            [
                sys.executable,
                str(BACKEND_ROOT / "scripts" / "smoke_v10_product.py"),
                "--frontend-dist",
                str(FRONTEND_DIST),
                "--check-build-only",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"status": "pass"', result.stdout)


@override_settings(RAG_LLM_MODEL="qwen3.6-flash", QWEN_CHAT_MODEL="qwen3.6-flash")
class SessionProductClosureTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="phase8c",
            email="phase8c@example.com",
            password="test",
        )
        self.other = User.objects.create_user(
            username="phase8c-other",
            email="phase8c-other@example.com",
            password="test",
        )
        self.org = Organization.objects.create(name="Phase 8C", slug="phase-8c")
        self.space = create_test_space(
            organization=self.org,
            name="Phase 8C",
            code="phase-8c",
        )
        self.fast_profile = ModelProfile.objects.create(
            name=f"phase8c-fast-{uuid.uuid4()}",
            provider="dashscope",
            model_id="qwen3.6-flash",
        )
        self.deep_profile = ModelProfile.objects.create(
            name=f"phase8c-deep-{uuid.uuid4()}",
            provider="dashscope",
            model_id="qwen3.7-plus",
        )
        GovernancePolicy.objects.create(
            space=self.space,
            values={
                "fast_model_profile_id": str(self.fast_profile.id),
                "deep_model_profile_id": str(self.deep_profile.id),
                "fast_thinking_budget": 1024,
                "deep_thinking_budget": 2048,
            },
        )
        SpaceMembership.objects.create(
            user=self.user,
            space=self.space,
            role=SpaceMembership.ROLE_MEMBER,
        )
        self.session = ChatSession.objects.create(
            user=self.user,
            space=self.space,
            title="Export me",
        )
        Message.objects.create(
            session=self.session,
            space=self.space,
            role="user",
            content="<script>alert('x')</script> Question",
        )
        Message.objects.create(
            session=self.session,
            space=self.space,
            role="assistant",
            content="Safe answer",
        )
        self.client.force_authenticate(self.user)

    def test_patch_pin_and_list_pinned_before_recent(self):
        newer = ChatSession.objects.create(
            user=self.user,
            space=self.space,
            title="Newer",
        )
        response = self.client.patch(
            f"/api/v1/chat/sessions/{self.session.id}/",
            {"is_pinned": True},
            format="json",
        )
        listing = self.client.get(
            "/api/v1/chat/sessions/",
            HTTP_X_SPACE_ID=str(self.space.id),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_pinned"])
        self.assertEqual(listing.data["results"][0]["id"], str(self.session.id))
        self.assertNotEqual(listing.data["results"][0]["id"], str(newer.id))

    def test_markdown_and_html_exports_validate_owner_and_escape_html(self):
        markdown = self.client.get(
            f"/api/v1/chat/sessions/{self.session.id}/export/",
            {"format": "markdown"},
        )
        html = self.client.get(
            f"/api/v1/chat/sessions/{self.session.id}/export/",
            {"format": "html"},
        )

        self.assertEqual(markdown.status_code, 200)
        self.assertIn("# Export me", markdown.content.decode())
        self.assertIn("attachment;", markdown["Content-Disposition"])
        self.assertEqual(html.status_code, 200)
        body = html.content.decode()
        self.assertNotIn("<script>", body)
        self.assertIn("&lt;script&gt;", body)
        self.assertNotIn("javascript:", body.lower())

        self.client.force_authenticate(self.other)
        denied = self.client.get(
            f"/api/v1/chat/sessions/{self.session.id}/export/",
            {"format": "markdown"},
        )
        self.assertEqual(denied.status_code, 404)

    def test_export_denies_owner_after_space_access_is_revoked(self):
        membership = SpaceMembership.objects.get(user=self.user, space=self.space)
        membership.status = "revoked"
        membership.save(update_fields=["status"])

        response = self.client.get(
            f"/api/v1/chat/sessions/{self.session.id}/export/",
            {"format": "markdown"},
        )

        self.assertEqual(response.status_code, 403)

    def test_history_and_export_require_the_current_space_capability(self):
        membership = SpaceMembership.objects.get(user=self.user, space=self.space)
        membership.role = SpaceMembership.ROLE_GUEST
        membership.save(update_fields=["role"])

        listing = self.client.get(
            "/api/v1/chat/sessions/",
            HTTP_X_SPACE_ID=str(self.space.id),
        )
        unscoped_listing = self.client.get("/api/v1/chat/sessions/")
        messages = self.client.get(
            f"/api/v1/chat/sessions/{self.session.id}/messages/",
        )
        detail = self.client.get(f"/api/v1/chat/sessions/{self.session.id}/")
        exported = self.client.get(
            f"/api/v1/chat/sessions/{self.session.id}/export/",
            {"format": "markdown"},
        )

        self.assertEqual(listing.status_code, 403)
        self.assertEqual(unscoped_listing.status_code, 200)
        self.assertNotIn(
            str(self.session.id),
            [row["id"] for row in unscoped_listing.data["results"]],
        )
        self.assertEqual(messages.status_code, 403)
        self.assertEqual(detail.status_code, 404)
        self.assertEqual(exported.status_code, 403)

    def test_guest_cannot_recover_or_derive_from_completed_history(self):
        membership = SpaceMembership.objects.get(user=self.user, space=self.space)
        membership.role = SpaceMembership.ROLE_GUEST
        membership.save(update_fields=["role"])
        question = self.session.messages.get(role="user")
        assistant = self.session.messages.get(role="assistant")
        turn = ChatTurn.objects.create(
            client_request_id=uuid.uuid4(),
            session=self.session,
            space=self.space,
            user=self.user,
            question_message=question,
            assistant_message=assistant,
            status=ChatTurn.STATUS_COMPLETED,
            completed_at=timezone.now(),
        )

        status_response = self.client.get(f"/api/v1/chat/turns/{turn.id}/")
        self.assertEqual(status_response.status_code, 404)

        events = self.client.get(f"/api/v1/chat/turns/{turn.id}/events/")
        branch = self.client.post(
            f"/api/v1/chat/messages/{assistant.id}/branch/",
            {"client_request_id": str(uuid.uuid4())},
            format="json",
        )
        regenerate = self.client.post(
            f"/api/v1/chat/messages/{assistant.id}/regenerate/",
            {"client_request_id": str(uuid.uuid4())},
            format="json",
        )

        self.assertEqual(events.status_code, 404)
        self.assertEqual(branch.status_code, 403)
        self.assertEqual(regenerate.status_code, 403)

    def test_guest_can_recover_own_active_turn(self):
        membership = SpaceMembership.objects.get(user=self.user, space=self.space)
        membership.role = SpaceMembership.ROLE_GUEST
        membership.save(update_fields=["role"])
        question = self.session.messages.get(role="user")
        turn = ChatTurn.objects.create(
            client_request_id=uuid.uuid4(),
            session=self.session,
            space=self.space,
            user=self.user,
            question_message=question,
            status=ChatTurn.STATUS_ACCEPTED,
        )

        with patch(
            "apps.chat.views.create_redis_client",
            side_effect=CoordinationUnavailableError(),
        ):
            response = self.client.get(f"/api/v1/chat/turns/{turn.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], ChatTurn.STATUS_ACCEPTED)

    @override_settings(ENABLE_PUBLIC_DEMO_SPACES=True)
    def test_public_demo_guest_without_membership_cannot_recover_active_turn(self):
        SpaceMembership.objects.filter(user=self.user, space=self.space).delete()
        self.space.visibility = "public_demo"
        self.space.save(update_fields=["visibility"])
        question = self.session.messages.get(role="user")
        turn = ChatTurn.objects.create(
            client_request_id=uuid.uuid4(),
            session=self.session,
            space=self.space,
            user=self.user,
            question_message=question,
            status=ChatTurn.STATUS_ACCEPTED,
        )

        with patch(
            "apps.chat.views.create_redis_client",
            side_effect=CoordinationUnavailableError(),
        ):
            response = self.client.get(f"/api/v1/chat/turns/{turn.id}/")

        self.assertEqual(response.status_code, 404)

    def test_org_admin_without_membership_cannot_recover_active_turn(self):
        SpaceMembership.objects.filter(user=self.user, space=self.space).delete()
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )
        question = self.session.messages.get(role="user")
        turn = ChatTurn.objects.create(
            client_request_id=uuid.uuid4(),
            session=self.session,
            space=self.space,
            user=self.user,
            question_message=question,
            status=ChatTurn.STATUS_ACCEPTED,
        )

        with patch(
            "apps.chat.views.create_redis_client",
            side_effect=CoordinationUnavailableError(),
        ):
            response = self.client.get(f"/api/v1/chat/turns/{turn.id}/")

        self.assertEqual(response.status_code, 404)

    def test_export_rejects_unknown_format(self):
        response = self.client.get(
            f"/api/v1/chat/sessions/{self.session.id}/export/",
            {"format": "pdf"},
        )
        self.assertEqual(response.status_code, 400)

    def test_history_query_is_server_filtered_and_surfaces_recovery_state(self):
        recovering = ChatSession.objects.create(
            user=self.user,
            space=self.space,
            title="Alpha recovery",
        )
        question = Message.objects.create(
            session=recovering,
            space=self.space,
            role="user",
            content="Recover this turn",
        )
        ChatTurn.objects.create(
            client_request_id=uuid.uuid4(),
            session=recovering,
            space=self.space,
            user=self.user,
            question_message=question,
            status=ChatTurn.STATUS_REASONING,
        )
        ChatSession.objects.create(
            user=self.user,
            space=self.space,
            title="Beta unrelated",
        )

        response = self.client.get(
            "/api/v1/chat/sessions/",
            {"q": "alpha", "time": "today", "status": "recovering"},
            HTTP_X_SPACE_ID=str(self.space.id),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["results"]], [str(recovering.id)])
        self.assertEqual(response.data["results"][0]["recovery_state"], "recovering")

    def test_history_time_and_terminal_status_filters_do_not_load_all_sessions(self):
        old_session = ChatSession.objects.create(
            user=self.user,
            space=self.space,
            title="Alpha archived history",
        )
        old_question = Message.objects.create(
            session=old_session,
            space=self.space,
            role="user",
            content="Old question",
        )
        ChatTurn.objects.create(
            client_request_id=uuid.uuid4(),
            session=old_session,
            space=self.space,
            user=self.user,
            question_message=old_question,
            status=ChatTurn.STATUS_COMPLETED,
            completed_at=timezone.now() - timedelta(days=45),
        )
        ChatSession.objects.filter(pk=old_session.pk).update(
            updated_at=timezone.now() - timedelta(days=45),
        )

        response = self.client.get(
            "/api/v1/chat/sessions/",
            {"time": "older", "status": "terminal"},
            HTTP_X_SPACE_ID=str(self.space.id),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["results"]], [str(old_session.id)])
        self.assertIsNone(response.data["next"])

    def test_history_rejects_unknown_filter_values(self):
        response = self.client.get(
            "/api/v1/chat/sessions/",
            {"time": "forever", "status": "mystery"},
            HTTP_X_SPACE_ID=str(self.space.id),
        )

        self.assertEqual(response.status_code, 400)

    def test_history_search_matches_message_content_without_loading_all_sessions(self):
        response = self.client.get(
            "/api/v1/chat/sessions/",
            {"q": "alert"},
            HTTP_X_SPACE_ID=str(self.space.id),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["id"] for row in response.data["results"]],
            [str(self.session.id)],
        )

    def test_branch_copies_through_selected_message_and_preserves_scope(self):
        selected = self.session.messages.filter(role="assistant").get()

        response = self.client.post(
            f"/api/v1/chat/messages/{selected.id}/branch/",
            {"client_request_id": str(uuid.uuid4()), "title": "Decision branch"},
            format="json",
            HTTP_X_SPACE_ID=str(self.space.id),
        )

        self.assertEqual(response.status_code, 201)
        branch = ChatSession.objects.get(pk=response.data["id"])
        self.assertEqual(branch.space_id, self.space.id)
        self.assertEqual(branch.user_id, self.user.id)
        self.assertEqual(branch.title, "Decision branch")
        self.assertEqual(
            list(branch.messages.values_list("role", "content")),
            [("user", "<script>alert('x')</script> Question"), ("assistant", "Safe answer")],
        )

    def test_branch_is_idempotent_and_non_disclosing_for_other_users(self):
        selected = self.session.messages.filter(role="assistant").get()
        request_id = uuid.uuid4()

        first = self.client.post(
            f"/api/v1/chat/messages/{selected.id}/branch/",
            {"client_request_id": str(request_id)},
            format="json",
        )
        second = self.client.post(
            f"/api/v1/chat/messages/{selected.id}/branch/",
            {"client_request_id": str(request_id)},
            format="json",
        )
        self.client.force_authenticate(self.other)
        denied = self.client.post(
            f"/api/v1/chat/messages/{selected.id}/branch/",
            {"client_request_id": str(uuid.uuid4())},
            format="json",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(denied.status_code, 404)

    def test_branch_copies_only_the_selected_current_assistant_version(self):
        superseded = self.session.messages.filter(role="assistant").get()
        superseded.is_current_version = False
        superseded.save(update_fields=["is_current_version"])
        selected = Message.objects.create(
            session=self.session,
            space=self.space,
            role="assistant",
            content="Replacement answer",
            version_group_id=superseded.version_group_id,
            version_number=2,
            supersedes_message=superseded,
        )

        response = self.client.post(
            f"/api/v1/chat/messages/{selected.id}/branch/",
            {"client_request_id": str(uuid.uuid4())},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        branch = ChatSession.objects.get(pk=response.data["id"])
        self.assertEqual(
            list(branch.messages.values_list("role", "content")),
            [
                ("user", "<script>alert('x')</script> Question"),
                ("assistant", "Replacement answer"),
            ],
        )

    def test_only_one_current_message_version_is_allowed(self):
        assistant = self.session.messages.filter(role="assistant").get()

        with self.assertRaises(IntegrityError), transaction.atomic():
            Message.objects.create(
                session=self.session,
                space=self.space,
                role="assistant",
                content="Conflicting current answer",
                version_group_id=assistant.version_group_id,
                version_number=2,
                is_current_version=True,
            )

    def test_regenerate_reuses_question_and_creates_one_idempotent_turn(self):
        question = self.session.messages.filter(role="user").get()
        assistant = self.session.messages.filter(role="assistant").get()
        ChatTurn.objects.create(
            client_request_id=uuid.uuid4(),
            session=self.session,
            space=self.space,
            user=self.user,
            question_message=question,
            assistant_message=assistant,
            status=ChatTurn.STATUS_COMPLETED,
            completed_at=timezone.now(),
        )
        request_id = uuid.uuid4()

        class Lease:
            def acquire(self): return True
            def start_renewal(self): return None
            def ensure_owned(self): return None
            def release(self): return None

        with patch("apps.chat.views.create_redis_client", return_value=object()), patch(
            "apps.chat.views.RedisSessionLease", return_value=Lease()
        ):
            first = self.client.post(
                f"/api/v1/chat/messages/{assistant.id}/regenerate/",
                {"client_request_id": str(request_id), "answer_mode": "fast"},
                format="json",
            )
            second = self.client.post(
                f"/api/v1/chat/messages/{assistant.id}/regenerate/",
                {"client_request_id": str(request_id), "answer_mode": "fast"},
                format="json",
            )

        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.streaming)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.data["code"], "turn_in_progress")
        self.assertEqual(self.session.messages.filter(role="user").count(), 1)
        regenerated = ChatTurn.objects.get(client_request_id=request_id)
        self.assertEqual(regenerated.question_message_id, question.id)
        self.assertNotEqual(regenerated.id, assistant.assistant_turn.id)
