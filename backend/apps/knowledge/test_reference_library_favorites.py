"""User-level official reference-library contract tests."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.chat.views import _canonical_selected_libraries
from apps.rag.library_routing import resolve_selected_libraries
from apps.spaces.models import Organization, SpaceMembership
from apps.spaces.test_utils import create_test_space

from .models import ReferenceLibrary, UserReferenceLibraryFavorite

User = get_user_model()


class OfficialReferenceLibraryTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="reference-member",
            email="reference-member@example.test",
            password="test",
        )
        cls.guest = User.objects.create_user(
            username="reference-guest",
            email="reference-guest@example.test",
            password="test",
        )
        cls.superadmin = User.objects.create_superuser(
            username="reference-admin",
            email="reference-admin@example.test",
            password="test",
        )
        cls.organization = Organization.objects.create(
            name="Reference Org", slug="reference-org"
        )
        cls.active_space = create_test_space(
            organization=cls.organization,
            name="Active Space",
            code="reference-active",
        )
        SpaceMembership.objects.create(
            space=cls.active_space,
            user=cls.user,
            role=SpaceMembership.ROLE_MEMBER,
            status="active",
        )
        SpaceMembership.objects.create(
            space=cls.active_space,
            user=cls.guest,
            role=SpaceMembership.ROLE_GUEST,
            status="active",
        )

        cls.libraries = []
        for index in range(6):
            source_space = create_test_space(
                organization=cls.organization,
                name=f"Official Source {index}",
                code=f"official-source-{index}",
            )
            cls.libraries.append(
                ReferenceLibrary.objects.create(
                    space=source_space,
                    name=f"Official Library {index}",
                    category="policy",
                    status=ReferenceLibrary.STATUS_PUBLISHED,
                    is_official=True,
                )
            )
        hidden_space = create_test_space(
            organization=cls.organization,
            name="Hidden Source",
            code="hidden-source",
        )
        cls.hidden_library = ReferenceLibrary.objects.create(
            space=hidden_space,
            name="Hidden Library",
            category="other",
            status=ReferenceLibrary.STATUS_PUBLISHED,
            is_official=False,
        )

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_member_catalog_contains_all_and_only_official_libraries(self):
        response = self.client_for(self.user).get("/api/v1/reference-libraries/")

        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.data}
        self.assertEqual(ids, {str(library.id) for library in self.libraries})
        self.assertTrue(all(item["is_official"] for item in response.data))
        self.assertTrue(all(not item["is_favorite"] for item in response.data))

    def test_guest_cannot_open_reference_library_catalog(self):
        response = self.client_for(self.guest).get("/api/v1/reference-libraries/")

        self.assertEqual(response.status_code, 403)

    def test_user_can_favorite_and_unfavorite_an_official_library(self):
        library = self.libraries[0]
        client = self.client_for(self.user)

        created = client.post(
            f"/api/v1/reference-libraries/{library.id}/favorite/",
            {"position": 1},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertTrue(
            UserReferenceLibraryFavorite.objects.filter(
                user=self.user, library=library, position=1
            ).exists()
        )

        catalog = client.get("/api/v1/reference-libraries/")
        item = next(row for row in catalog.data if row["id"] == str(library.id))
        self.assertTrue(item["is_favorite"])
        self.assertEqual(item["favorite_position"], 1)

        deleted = client.delete(
            f"/api/v1/reference-libraries/{library.id}/favorite/"
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(
            UserReferenceLibraryFavorite.objects.filter(
                user=self.user, library=library
            ).exists()
        )

    def test_sixth_favorite_is_rejected_server_side(self):
        for position, library in enumerate(self.libraries[:5], start=1):
            UserReferenceLibraryFavorite.objects.create(
                user=self.user,
                library=library,
                position=position,
            )

        response = self.client_for(self.user).post(
            f"/api/v1/reference-libraries/{self.libraries[5].id}/favorite/",
            {"position": 5},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            UserReferenceLibraryFavorite.objects.filter(user=self.user).count(), 5
        )

    def test_unofficial_library_cannot_be_favorited(self):
        response = self.client_for(self.user).post(
            f"/api/v1/reference-libraries/{self.hidden_library.id}/favorite/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_unmarking_official_immediately_hides_and_removes_favorite(self):
        library = self.libraries[0]
        UserReferenceLibraryFavorite.objects.create(
            user=self.user, library=library, position=1
        )

        response = self.client_for(self.superadmin).patch(
            f"/api/v1/documents/libraries/{library.id}/",
            {"is_official": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            UserReferenceLibraryFavorite.objects.filter(library=library).exists()
        )
        catalog = self.client_for(self.user).get("/api/v1/reference-libraries/")
        self.assertNotIn(str(library.id), {item["id"] for item in catalog.data})

    @override_settings(CHAT_LIBRARY_MAX_FAST=1, CHAT_LIBRARY_MAX_DEEP=3)
    def test_explicit_selection_uses_only_the_users_favorite_official_libraries(self):
        for position, library in enumerate(self.libraries[:4], start=1):
            UserReferenceLibraryFavorite.objects.create(
                user=self.user,
                library=library,
                position=position,
            )
        selected = [str(library.id) for library in self.libraries[:4]]

        canonical = _canonical_selected_libraries(
            self.user, self.active_space, selected, "deep"
        )
        space_ids, names = resolve_selected_libraries(
            self.active_space, canonical, max_count=3
        )

        self.assertEqual(canonical, selected[:3])
        self.assertEqual(
            space_ids,
            [str(library.space_id) for library in self.libraries[:3]],
        )
        self.assertEqual(len(names), 3)

    def test_official_but_not_favorite_library_cannot_be_selected_in_chat(self):
        favorite = self.libraries[0]
        not_favorite = self.libraries[1]
        UserReferenceLibraryFavorite.objects.create(
            user=self.user,
            library=favorite,
            position=1,
        )

        self.assertEqual(
            _canonical_selected_libraries(
                self.user,
                self.active_space,
                [str(not_favorite.id), str(favorite.id)],
                "deep",
            ),
            [str(favorite.id)],
        )

    def test_unofficial_selection_is_immediately_ignored(self):
        self.assertEqual(
            _canonical_selected_libraries(
                self.user,
                self.active_space,
                [str(self.hidden_library.id)],
                "deep",
            ),
            [],
        )
