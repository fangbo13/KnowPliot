# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.

"""Persistence contracts for controlled workspace taxonomy (SPEC §§13/23)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase

from django.contrib.auth import get_user_model

from apps.spaces.models import (
    BusinessLine,
    KnowledgeSpace,
    KnowledgeSpaceOfficeLocation,
    OfficeLocation,
    Organization,
    SpaceMembership,
    WorkGroup,
    WorkspaceUsageDaily,
    WorkspaceUsageSummary,
)
from apps.spaces.ownership import create_space_with_owner

User = get_user_model()


class TaxonomyPersistenceModelTests(TestCase):
    """SQLite-safe model/constraint contracts; no trigger evidence is implied."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="taxonomy-owner",
            email="taxonomy-owner@example.test",
            password="safe-password",
        )
        self.organization = Organization.objects.create(
            name="Taxonomy org",
            slug="taxonomy-org",
        )
        self.other_organization = Organization.objects.create(
            name="Other taxonomy org",
            slug="other-taxonomy-org",
        )
        self.business_line = BusinessLine.objects.create(
            organization=self.organization,
            name="Assurance",
            code="assurance",
        )
        self.other_business_line = BusinessLine.objects.create(
            organization=self.other_organization,
            name="Tax",
            code="tax",
        )
        self.space = create_space_with_owner(
            organization=self.organization,
            owner=self.owner,
            name="Legacy taxonomy space",
            code="legacy-taxonomy-space",
        )

    def test_existing_space_is_legacy_without_guessed_classification(self):
        self.assertEqual(
            self.space.classification_state,
            KnowledgeSpace.CLASSIFICATION_LEGACY,
        )
        self.assertIsNone(self.space.work_group_id)
        self.assertEqual(list(self.space.office_locations.all()), [])

    def test_work_group_code_is_unique_per_business_line(self):
        WorkGroup.objects.create(
            business_line=self.business_line,
            normalized_code="ag-12345",
            display_name="Assurance Group 12345",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WorkGroup.objects.create(
                    business_line=self.business_line,
                    normalized_code="ag-12345",
                    display_name="Duplicate code",
                )
        # The same normalized code is valid in a different parent scope.
        WorkGroup.objects.create(
            business_line=self.other_business_line,
            normalized_code="ag-12345",
            display_name="Other scope code",
        )

    def test_office_location_code_is_unique_per_organization(self):
        OfficeLocation.objects.create(
            organization=self.organization,
            normalized_code="london",
            display_name="London",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OfficeLocation.objects.create(
                    organization=self.organization,
                    normalized_code="london",
                    display_name="Duplicate London",
                )
        OfficeLocation.objects.create(
            organization=self.other_organization,
            normalized_code="london",
            display_name="Other London",
        )

    def test_space_location_through_row_is_unique(self):
        location = OfficeLocation.objects.create(
            organization=self.organization,
            normalized_code="london",
            display_name="London",
        )
        KnowledgeSpaceOfficeLocation.objects.create(
            space=self.space,
            office_location=location,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                KnowledgeSpaceOfficeLocation.objects.create(
                    space=self.space,
                    office_location=location,
                )

    def test_usage_daily_and_summary_have_required_idempotency_keys(self):
        day = "2026-07-18"
        WorkspaceUsageDaily.objects.create(
            user=self.owner,
            space=self.space,
            date=day,
            interaction_count=2,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WorkspaceUsageDaily.objects.create(
                    user=self.owner,
                    space=self.space,
                    date=day,
                    interaction_count=3,
                )
        WorkspaceUsageSummary.objects.create(
            user=self.owner,
            space=self.space,
            interaction_count_30d=2,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WorkspaceUsageSummary.objects.create(
                    user=self.owner,
                    space=self.space,
                    interaction_count_30d=3,
                )

    def test_complete_state_requires_business_line_and_work_group_locally(self):
        self.space.classification_state = KnowledgeSpace.CLASSIFICATION_COMPLETE
        with self.assertRaises(ValidationError):
            self.space.full_clean()

    def test_exempt_state_can_omit_classification(self):
        self.space.classification_state = KnowledgeSpace.CLASSIFICATION_EXEMPT
        self.space.save(update_fields=["classification_state"])
        self.space.refresh_from_db()
        self.assertEqual(
            self.space.classification_state,
            KnowledgeSpace.CLASSIFICATION_EXEMPT,
        )


class PgTaxonomyConsistencyRegressionTests(TransactionTestCase):
    """Deferred cross-table checks; skipped on SQLite by design."""

    reset_sequences = True

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("requires PostgreSQL; run through docker compose")
        self.owner = User.objects.create_user(
            username="pg-taxonomy-owner",
            email="pg-taxonomy-owner@example.test",
            password="safe-password",
        )
        self.organization = Organization.objects.create(
            name="PG taxonomy org",
            slug="pg-taxonomy-org",
        )
        self.other_organization = Organization.objects.create(
            name="PG other taxonomy org",
            slug="pg-other-taxonomy-org",
        )
        self.business_line = BusinessLine.objects.create(
            organization=self.organization,
            name="Assurance",
            code="assurance",
        )
        self.other_business_line = BusinessLine.objects.create(
            organization=self.other_organization,
            name="Tax",
            code="tax",
        )
        self.work_group = WorkGroup.objects.create(
            business_line=self.business_line,
            normalized_code="ag-12345",
            display_name="Assurance Group 12345",
        )
        self.other_work_group = WorkGroup.objects.create(
            business_line=self.other_business_line,
            normalized_code="tax-1",
            display_name="Tax Group",
        )
        self.location = OfficeLocation.objects.create(
            organization=self.organization,
            normalized_code="london",
            display_name="London",
        )
        self.other_location = OfficeLocation.objects.create(
            organization=self.other_organization,
            normalized_code="paris",
            display_name="Paris",
        )
        self.space = create_space_with_owner(
            organization=self.organization,
            owner=self.owner,
            name="PG taxonomy space",
            code="pg-taxonomy-space",
        )

    def _make_complete(self):
        with transaction.atomic():
            self.space.business_line = self.business_line
            self.space.work_group = self.work_group
            self.space.classification_state = KnowledgeSpace.CLASSIFICATION_COMPLETE
            self.space.save(
                update_fields=[
                    "business_line",
                    "work_group",
                    "classification_state",
                ]
            )
            KnowledgeSpaceOfficeLocation.objects.create(
                space=self.space,
                office_location=self.location,
            )

    def test_valid_complete_classification_commits(self):
        self._make_complete()
        self.space.refresh_from_db()
        self.assertEqual(self.space.classification_state, KnowledgeSpace.CLASSIFICATION_COMPLETE)

    def test_complete_classification_requires_an_office_location(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.space.business_line = self.business_line
                self.space.work_group = self.work_group
                self.space.classification_state = KnowledgeSpace.CLASSIFICATION_COMPLETE
                self.space.save(
                    update_fields=["business_line", "work_group", "classification_state"]
                )

    def test_deferred_trigger_rejects_cross_business_line_group(self):
        self._make_complete()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.space.business_line = self.other_business_line
                self.space.save(update_fields=["business_line"])

    def test_deferred_trigger_rejects_cross_organization_office(self):
        self._make_complete()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                KnowledgeSpaceOfficeLocation.objects.create(
                    space=self.space,
                    office_location=self.other_location,
                )

    def test_deferred_parent_trigger_rejects_business_line_organization_move(self):
        self._make_complete()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BusinessLine.objects.filter(pk=self.business_line.pk).update(
                    organization=self.other_organization,
                )

