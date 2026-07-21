from django.contrib.auth import get_user_model
from django.test import SimpleTestCase


class TestPrincipalMetadataContractTest(SimpleTestCase):
    def test_metadata_is_explicit_nullable_and_never_guessed_from_identity(self):
        User = get_user_model()
        fields = {field.name: field for field in User._meta.get_fields()}

        self.assertIn("account_purpose", fields)
        self.assertIn("test_principal_expires_at", fields)
        self.assertIn("test_run_id", fields)
        user = User(email="qa-looking-name@example.test")
        self.assertIsNone(user.account_purpose)
        self.assertIsNone(user.test_principal_expires_at)
        self.assertEqual(user.test_run_id, "")
