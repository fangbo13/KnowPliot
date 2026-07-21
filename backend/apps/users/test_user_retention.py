from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase

from apps.users.models import User


class UserRetentionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="retained-user",
            email="retained-user@example.test",
            password="safe-password",
        )

    def test_direct_hard_delete_is_denied(self):
        with self.assertRaisesRegex(PermissionDenied, "hard deletion is disabled"):
            self.user.delete()

        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_django_admin_does_not_offer_user_deletion(self):
        request = RequestFactory().get("/admin/users/user/")
        model_admin = admin.site._registry[User]

        self.assertFalse(model_admin.has_delete_permission(request, self.user))
