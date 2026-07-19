"""Runtime batch imports must always carry exact authorized workspace scope."""

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.spaces.models import Organization
from apps.spaces.ownership import create_space_with_owner

from .batch_views import BatchDocumentUploadView
from .models import BatchImportResultRecord


class BatchImportScopeContractTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="batch-scope-owner",
            email="batch-scope-owner@example.test",
            password="pw",
        )
        organization = Organization.objects.create(
            name="Batch scope organization",
            slug="batch-scope-organization",
        )
        self.space = create_space_with_owner(
            organization=organization,
            owner=self.owner,
            name="Batch scope workspace",
            code="batch-scope-workspace",
            visibility="private",
        )
        self.factory = APIRequestFactory()

    def _request(self, *, include_space: bool):
        headers = (
            {"HTTP_X_SPACE_ID": str(self.space.pk)} if include_space else {}
        )
        raw = self.factory.post("/api/v1/knowledge/batch/upload/", {}, **headers)
        force_authenticate(raw, user=self.owner)
        view = BatchDocumentUploadView()
        request = view.initialize_request(raw)
        view.request = request
        view.args = ()
        view.kwargs = {}
        return view, request

    @staticmethod
    def _validated_serializer():
        return SimpleNamespace(
            validated_data={"source_tag": "EY_Batch"},
            _validation_result={
                "valid_files": [],
                "valid_count": 0,
                "rejected_count": 0,
                "rejected_files": [],
            },
            is_valid=lambda **_kwargs: None,
        )

    @patch("apps.knowledge.batch_views.create_audit_log")
    def test_new_batch_persists_exact_workspace_and_never_legacy_unknown(
        self,
        _audit,
    ):
        view, request = self._request(include_space=True)
        with patch.object(
            view,
            "get_serializer",
            return_value=self._validated_serializer(),
        ):
            response = view.create(request)

        self.assertEqual(response.status_code, 201, response.data)
        row = BatchImportResultRecord.objects.get(pk=response.data["batch_id"])
        self.assertEqual(row.space_id, self.space.pk)
        self.assertEqual(row.space_uuid, self.space.pk)
        self.assertEqual(row.organization_uuid, self.space.organization_id)
        self.assertFalse(row.legacy_scope_unknown)

    @patch("apps.knowledge.batch_views.create_audit_log")
    def test_missing_workspace_is_rejected_before_any_batch_row(
        self,
        _audit,
    ):
        view, request = self._request(include_space=False)
        with patch.object(
            view,
            "get_serializer",
            return_value=self._validated_serializer(),
        ):
            with self.assertRaises(PermissionDenied):
                view.create(request)

        self.assertFalse(BatchImportResultRecord.objects.exists())
