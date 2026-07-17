"""Task 7 citation-source and durable conversation-share contracts."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.knowledge.models import Document
from apps.spaces.models import KnowledgeSpace, Organization, SpaceMembership

from .models import ChatSession, Citation, ConversationShare, Message

User = get_user_model()


class SharingAndCitationSourceTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="share-owner", email="share-owner@example.com", password="test")
        self.viewer = User.objects.create_user(
            username="share-viewer", email="share-viewer@example.com", password="test"
        )
        self.guest = User.objects.create_user(username="share-guest", email="share-guest@example.com", password="test")
        self.outsider = User.objects.create_user(
            username="share-outsider", email="share-outsider@example.com", password="test"
        )
        self.org = Organization.objects.create(name="Share Org", slug="share-org")
        self.other_org = Organization.objects.create(name="Other Org", slug="other-share-org")
        self.space = KnowledgeSpace.objects.create(organization=self.org, name="Share Space", code="share-space")
        self.other_space = KnowledgeSpace.objects.create(
            organization=self.other_org, name="Other Space", code="other-share-space"
        )
        for user, role in [
            (self.owner, SpaceMembership.ROLE_OWNER),
            (self.viewer, SpaceMembership.ROLE_REVIEWER),
            (self.guest, SpaceMembership.ROLE_GUEST),
        ]:
            SpaceMembership.objects.create(user=user, space=self.space, role=role)
        SpaceMembership.objects.create(user=self.outsider, space=self.other_space, role=SpaceMembership.ROLE_OWNER)
        self.session = ChatSession.objects.create(user=self.owner, space=self.space, title="Shareable decision")
        Message.objects.create(session=self.session, space=self.space, role="user", content="What changed?")
        self.answer = Message.objects.create(
            session=self.session,
            space=self.space,
            role="assistant",
            content="<script>unsafe()</script> Approved answer",
        )
        self.document = Document.objects.create(
            space=self.space,
            title="Policy source",
            file="documents/policy.pdf",
            file_type="pdf",
            file_size=128,
            uploaded_by=self.owner,
            status="active",
        )
        self.citation = Citation.objects.create(
            space=self.space,
            message=self.answer,
            document=self.document,
            relevance_score=0.92,
            page_number=7,
            quoted_text="<b>Approved</b> " + "source text " * 80,
        )

    def create_share(self):
        self.client.force_authenticate(self.owner)
        return self.client.post(
            f"/api/v1/chat/sessions/{self.session.id}/shares/",
            {},
            format="json",
        )

    def test_citation_metadata_has_safe_snippet_and_permission_checked_source(self):
        self.client.force_authenticate(self.owner)
        messages = self.client.get(f"/api/v1/chat/sessions/{self.session.id}/messages/")

        answer = next(row for row in messages.data["results"] if row["role"] == "assistant")
        citation = answer["citations"][0]
        self.assertEqual(citation["source_id"], str(self.citation.id))
        self.assertEqual(citation["page_number"], 7)
        self.assertNotIn("<b>", citation["snippet"])
        self.assertLessEqual(len(citation["snippet"]), 280)
        self.assertEqual(citation["source_url"], f"/api/v1/chat/citations/{self.citation.id}/source/")

        source = self.client.get(citation["source_url"])
        self.assertEqual(source.status_code, 200)
        self.assertEqual(source.data["title"], "Policy source")
        self.assertNotIn("file", source.data)
        self.assertNotIn("content", source.data)

    def test_guest_gets_no_source_link_and_direct_source_is_denied(self):
        share = self.create_share()
        self.client.force_authenticate(self.guest)
        view = self.client.get(f"/api/v1/chat/shares/{share.data['token']}/view/")

        self.assertEqual(view.status_code, 200)
        citation = view.data["messages"][1]["citations"][0]
        self.assertIsNone(citation["source_url"])
        direct = self.client.get(f"/api/v1/chat/citations/{self.citation.id}/source/")
        self.assertEqual(direct.status_code, 403)

    def test_share_create_list_view_revoke_and_expiry_contract(self):
        created = self.create_share()

        self.assertEqual(created.status_code, 201)
        self.assertGreater(
            timezone.datetime.fromisoformat(created.data["expires_at"].replace("Z", "+00:00")),
            timezone.now() + timedelta(days=6),
        )
        listing = self.client.get(f"/api/v1/chat/sessions/{self.session.id}/shares/")
        self.assertEqual([row["id"] for row in listing.data], [created.data["id"]])

        self.client.force_authenticate(self.viewer)
        shared = self.client.get(f"/api/v1/chat/shares/{created.data['token']}/view/")
        self.assertEqual(shared.status_code, 200)
        self.assertTrue(shared.data["read_only"])
        self.assertNotIn("<script>", shared.data["messages"][1]["content"])

        self.client.force_authenticate(self.owner)
        revoked = self.client.delete(f"/api/v1/chat/shares/{created.data['id']}/")
        self.assertEqual(revoked.status_code, 204)
        self.client.force_authenticate(self.viewer)
        self.assertEqual(
            self.client.get(f"/api/v1/chat/shares/{created.data['token']}/view/").status_code,
            404,
        )

    def test_guest_create_is_denied_and_cross_org_token_is_non_disclosing(self):
        guest_session = ChatSession.objects.create(user=self.guest, space=self.space, title="Guest session")
        self.client.force_authenticate(self.guest)
        denied = self.client.post(f"/api/v1/chat/sessions/{guest_session.id}/shares/", {})
        self.assertEqual(denied.status_code, 403)

        share = self.create_share()
        self.client.force_authenticate(self.outsider)
        hidden = self.client.get(f"/api/v1/chat/shares/{share.data['token']}/view/")
        self.assertEqual(hidden.status_code, 404)

    def test_expired_share_is_non_disclosing(self):
        share = self.create_share()
        ConversationShare.objects.filter(pk=share.data["id"]).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.client.force_authenticate(self.viewer)

        response = self.client.get(f"/api/v1/chat/shares/{share.data['token']}/view/")

        self.assertEqual(response.status_code, 404)

    def test_owner_can_revoke_after_losing_workspace_membership(self):
        share = self.create_share()
        SpaceMembership.objects.filter(user=self.owner, space=self.space).delete()
        self.client.force_authenticate(self.owner)

        response = self.client.delete(f"/api/v1/chat/shares/{share.data['id']}/")

        self.assertEqual(response.status_code, 204)
        self.assertIsNotNone(ConversationShare.objects.get(pk=share.data["id"]).revoked_at)
