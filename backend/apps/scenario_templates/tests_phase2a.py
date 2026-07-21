# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APITestCase
from apps.scenario_templates.contract import normalize_revision_snapshot
from apps.scenario_templates.models import (
    ScenarioTemplate,
    ScenarioTemplateApplication,
    ScenarioTemplateRevision,
)
from apps.spaces.models import (
    BusinessLine,
    KnowledgeSpace,
    SpaceMembership,
    Organization,
    OrganizationMembership,
)

User = get_user_model()
PW = "StrongPass123!"


class ScenarioTemplateTests(APITestCase):
    def publish_legacy_template(self, template):
        revision = ScenarioTemplateRevision.objects.create(
            template=template,
            version=1,
            snapshot=normalize_revision_snapshot(
                {
                    "scenario_type": template.scenario_type,
                    "quick_questions": template.quick_questions,
                    "prompt_policy": template.prompt_policy,
                    "default_language": template.default_language,
                    "default_visibility": template.default_visibility,
                    "retrieval_policy": template.retrieval_policy,
                }
            ),
            published_at=timezone.now(),
            created_by=self.superuser,
            change_note="published test fixture",
        )
        template.current_revision = revision
        template.save(update_fields=["current_revision", "updated_at"])
        return revision

    def setUp(self):
        # Setup organization
        self.org, _ = Organization.objects.get_or_create(
            slug="default", defaults={"name": "Default Org"}
        )
        self.other_org = Organization.objects.create(
            slug="other", name="Other Org"
        )
        self.audit_line = BusinessLine.objects.create(
            organization=self.org, name="Audit", code="audit"
        )
        self.tax_line = BusinessLine.objects.create(
            organization=self.other_org, name="Tax", code="tax"
        )
        
        # Setup users
        self.superuser = User.objects.create_superuser(
            username="root@test.com", email="root@test.com", password=PW
        )
        self.employee = User.objects.create_user(
            username="emp@test.com", email="emp@test.com", password=PW
        )
        self.org_admin = User.objects.create_user(
            username="oa@test.com", email="oa@test.com", password=PW
        )
        self.business_admin = User.objects.create_user(
            username="ba@test.com", email="ba@test.com", password=PW
        )
        OrganizationMembership.objects.create(
            user=self.org_admin, organization=self.org, role="org_admin"
        )
        OrganizationMembership.objects.create(
            user=self.business_admin,
            organization=self.org,
            business_line=self.audit_line,
            role="business_admin",
        )

        # Setup templates
        self.active_template = ScenarioTemplate.objects.create(
            name="Active Template",
            code="active-template",
            scenario_type="onboarding",
            description="Active template desc",
            default_language="en",
            icon="user",
            quick_questions=["Q1", "Q2"],
            is_active=True,
        )
        self.inactive_template = ScenarioTemplate.objects.create(
            name="Inactive Template",
            code="inactive-template",
            scenario_type="audit",
            description="Inactive template desc",
            is_active=False,
        )
        self.other_org_template = ScenarioTemplate.objects.create(
            name="Other Org Template",
            code="other-org-template",
            scenario_type="tax",
            organization=self.other_org,
            description="Other org scoped template",
            is_active=True,
        )
        self.active_revision = self.publish_legacy_template(self.active_template)
        self.inactive_revision = self.publish_legacy_template(self.inactive_template)
        self.other_org_revision = self.publish_legacy_template(self.other_org_template)

    def submit_template_request(self, user, **overrides):
        payload = {
            "name": "Requested Workspace",
            "code": f"requested-{uuid.uuid4().hex[:8]}",
            "purpose": "Use an immutable template revision",
            "visibility": "private",
            "business_line_id": str(self.audit_line.id),
            "work_group_id": str(uuid.uuid4()),
            "office_location_ids": [str(uuid.uuid4())],
            **overrides,
        }
        self.client.force_authenticate(user)
        with patch(
            "apps.spaces.creation_services.submit_creation_request",
            return_value={"request_id": str(uuid.uuid4()), "status": "pending"},
        ) as submit:
            response = self.client.post(
                f"/api/v1/templates/{self.active_template.id}/create-space/",
                payload,
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            )
        return response, submit

    def test_authenticated_user_can_list_active_templates(self):
        """Ordinary logged in users can list active templates, but inactive templates are hidden."""
        self.client.force_authenticate(self.employee)
        r = self.client.get("/api/v1/templates/")
        self.assertEqual(r.status_code, 200)
        
        # Should only contain active templates
        results = r.data.get("results", r.data)
        codes = [t["code"] for t in results]
        self.assertIn("active-template", codes)
        self.assertNotIn("inactive-template", codes)
        self.assertNotIn("other-org-template", codes)

    def test_admin_user_can_see_inactive_templates_in_list(self):
        """Admin users can see both active and inactive templates in list."""
        self.client.force_authenticate(self.org_admin)
        r = self.client.get("/api/v1/templates/")
        self.assertEqual(r.status_code, 200)
        
        results = r.data.get("results", r.data)
        codes = [t["code"] for t in results]
        self.assertIn("active-template", codes)
        self.assertIn("inactive-template", codes)
        self.assertNotIn("other-org-template", codes)

        by_code = {t["code"]: t for t in results}
        self.assertFalse(by_code["active-template"]["can_manage"])

    def test_template_list_q_searches_visible_name_code_description(self):
        """q searches only within the user's visible templates."""
        self.client.force_authenticate(self.org_admin)
        scoped = ScenarioTemplate.objects.create(
            name="China Audit Launch",
            code="china-audit-launch",
            scenario_type="audit",
            description="SOX rollout assistant",
            organization=self.org,
            is_active=True,
        )
        hidden = ScenarioTemplate.objects.create(
            name="Hidden China Audit",
            code="hidden-china-audit",
            scenario_type="audit",
            organization=self.other_org,
            is_active=True,
        )

        r = self.client.get("/api/v1/templates/", {"q": "china"})
        self.assertEqual(r.status_code, 200)
        codes = {t["code"] for t in r.data.get("results", r.data)}
        self.assertIn(scoped.code, codes)
        self.assertNotIn(hidden.code, codes)

        r = self.client.get("/api/v1/templates/", {"q": "SOX"})
        self.assertEqual(r.status_code, 200)
        codes = {t["code"] for t in r.data.get("results", r.data)}
        self.assertIn(scoped.code, codes)

    def test_template_list_filters_by_scope_and_scenario_type(self):
        """scope and scenario filters narrow the already visible queryset."""
        ScenarioTemplate.objects.create(
            name="Org Audit Template",
            code="org-audit-template",
            scenario_type="audit",
            organization=self.org,
            is_active=True,
        )
        ScenarioTemplate.objects.create(
            name="BL Tax Template",
            code="bl-tax-template",
            scenario_type="tax",
            organization=self.org,
            business_line=self.audit_line,
            is_active=True,
        )
        self.client.force_authenticate(self.org_admin)

        r = self.client.get("/api/v1/templates/", {"scope": "organization"})
        self.assertEqual(r.status_code, 200)
        codes = {t["code"] for t in r.data.get("results", r.data)}
        self.assertIn("org-audit-template", codes)
        self.assertNotIn("active-template", codes)
        self.assertNotIn("bl-tax-template", codes)

        r = self.client.get("/api/v1/templates/", {"scope": "business_line"})
        self.assertEqual(r.status_code, 200)
        codes = {t["code"] for t in r.data.get("results", r.data)}
        self.assertIn("bl-tax-template", codes)
        self.assertNotIn("org-audit-template", codes)

        r = self.client.get("/api/v1/templates/", {"scenario_type": "tax"})
        self.assertEqual(r.status_code, 200)
        codes = {t["code"] for t in r.data.get("results", r.data)}
        self.assertIn("bl-tax-template", codes)
        self.assertNotIn("org-audit-template", codes)

    def test_template_list_filters_by_organization_and_business_line_within_scope(self):
        """Organization and business-line filters cannot expand the visible queryset."""
        org_template = ScenarioTemplate.objects.create(
            name="Org Discovery Template",
            code="org-discovery-template",
            scenario_type="audit",
            organization=self.org,
            is_active=True,
        )
        line_template = ScenarioTemplate.objects.create(
            name="Line Discovery Template",
            code="line-discovery-template",
            scenario_type="audit",
            organization=self.org,
            business_line=self.audit_line,
            is_active=True,
        )
        hidden_line_template = ScenarioTemplate.objects.create(
            name="Hidden Line Discovery Template",
            code="hidden-line-discovery-template",
            scenario_type="tax",
            organization=self.other_org,
            business_line=self.tax_line,
            is_active=True,
        )

        self.client.force_authenticate(self.org_admin)
        r = self.client.get("/api/v1/templates/", {"organization": str(self.org.id)})
        self.assertEqual(r.status_code, 200)
        codes = {t["code"] for t in r.data.get("results", r.data)}
        self.assertIn(org_template.code, codes)
        self.assertIn(line_template.code, codes)
        self.assertNotIn(hidden_line_template.code, codes)

        r = self.client.get("/api/v1/templates/", {"organization": str(self.other_org.id)})
        self.assertEqual(r.status_code, 200)
        codes = {t["code"] for t in r.data.get("results", r.data)}
        self.assertNotIn(hidden_line_template.code, codes)

        self.client.force_authenticate(self.business_admin)
        r = self.client.get("/api/v1/templates/", {"business_line": str(self.audit_line.id)})
        self.assertEqual(r.status_code, 200)
        codes = {t["code"] for t in r.data.get("results", r.data)}
        self.assertIn(line_template.code, codes)
        self.assertNotIn(hidden_line_template.code, codes)

        r = self.client.get("/api/v1/templates/", {"business_line": str(self.tax_line.id)})
        self.assertEqual(r.status_code, 200)
        codes = {t["code"] for t in r.data.get("results", r.data)}
        self.assertNotIn(hidden_line_template.code, codes)

    def test_template_list_inactive_filter_admin_only(self):
        """Admins can filter inactive templates; employees still only see active global templates."""
        self.client.force_authenticate(self.org_admin)
        r = self.client.get("/api/v1/templates/", {"is_active": "false"})
        self.assertEqual(r.status_code, 200)
        codes = {t["code"] for t in r.data.get("results", r.data)}
        self.assertIn("inactive-template", codes)
        self.assertNotIn("active-template", codes)

        self.client.force_authenticate(self.employee)
        r = self.client.get("/api/v1/templates/", {"is_active": "false"})
        self.assertEqual(r.status_code, 200)
        codes = {t["code"] for t in r.data.get("results", r.data)}
        self.assertIn("active-template", codes)
        self.assertNotIn("inactive-template", codes)

    def test_superuser_can_create_template(self):
        """Superuser can create a scenario template."""
        self.client.force_authenticate(self.superuser)
        r = self.client.post(
            "/api/v1/templates/",
            {
                "name": "New Template",
                "code": "new-template",
                "scenario_type": "tax",
                "quick_questions": ["TQ1"],
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        self.assertTrue(ScenarioTemplate.objects.filter(code="new-template").exists())
        template = ScenarioTemplate.objects.get(code="new-template")
        revision = ScenarioTemplateRevision.objects.get(template=template)
        self.assertEqual(revision.version, 1)
        self.assertEqual(revision.snapshot["schema_version"], 1)
        scenario = revision.snapshot["components"]["scenario_definitions"][0]
        self.assertEqual(scenario["scenario_type"], "tax")
        self.assertEqual(scenario["quick_questions"], ["TQ1"])

    def test_employee_cannot_create_template(self):
        """Normal employee user cannot create a scenario template."""
        self.client.force_authenticate(self.employee)
        r = self.client.post(
            "/api/v1/templates/",
            {
                "name": "Employee Template",
                "code": "emp-template",
                "scenario_type": "consulting",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(ScenarioTemplate.objects.filter(code="emp-template").exists())

    def test_org_admin_creates_template_scoped_to_own_org_by_default(self):
        """Org admins create organization-scoped templates, not global templates."""
        self.client.force_authenticate(self.org_admin)
        r = self.client.post(
            "/api/v1/templates/",
            {
                "name": "Org Template",
                "code": "org-template",
                "scenario_type": "audit",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        template = ScenarioTemplate.objects.get(code="org-template")
        self.assertEqual(template.organization, self.org)
        self.assertIsNone(template.business_line)

        detail = self.client.get(f"/api/v1/templates/{template.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.data["can_manage"])
        self.assertEqual(detail.data["latest_version"], 1)

    def test_template_update_records_revision_history(self):
        """Template create/update appends immutable revisions."""
        self.client.force_authenticate(self.superuser)
        create = self.client.post(
            "/api/v1/templates/",
            {
                "name": "Revision Template",
                "code": "revision-template",
                "scenario_type": "audit",
                "quick_questions": ["Original question"],
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201, create.data)
        template_id = create.data["id"]

        update = self.client.patch(
            f"/api/v1/templates/{template_id}/",
            {
                "description": "Updated description",
                "quick_questions": ["Updated question"],
            },
            format="json",
        )
        self.assertEqual(update.status_code, 200, update.data)
        self.assertEqual(update.data["latest_version"], 2)

        revisions = self.client.get(f"/api/v1/templates/{template_id}/revisions/")
        self.assertEqual(revisions.status_code, 200)
        self.assertEqual([r["version"] for r in revisions.data], [2, 1])
        self.assertNotIn("description", revisions.data[0]["snapshot"])
        self.assertEqual(
            revisions.data[0]["snapshot"]["components"]["scenario_definitions"][0]["quick_questions"],
            ["Updated question"],
        )
        self.assertEqual(
            revisions.data[1]["snapshot"]["components"]["scenario_definitions"][0]["quick_questions"],
            ["Original question"],
        )

    def test_business_admin_creates_template_scoped_to_own_business_line_by_default(self):
        """Business admins create business-line-scoped templates."""
        self.client.force_authenticate(self.business_admin)
        r = self.client.post(
            "/api/v1/templates/",
            {
                "name": "BL Template",
                "code": "bl-template",
                "scenario_type": "audit",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        template = ScenarioTemplate.objects.get(code="bl-template")
        self.assertEqual(template.organization, self.org)
        self.assertEqual(template.business_line, self.audit_line)

    def test_scoped_admin_cannot_update_global_template(self):
        """Global templates are platform-owned and cannot be edited by scoped admins."""
        self.client.force_authenticate(self.org_admin)
        r = self.client.patch(
            f"/api/v1/templates/{self.active_template.id}/",
            {"description": "changed"},
            format="json",
        )
        self.assertEqual(r.status_code, 403)
        self.active_template.refresh_from_db()
        self.assertNotEqual(self.active_template.description, "changed")

    def test_superuser_can_archive_and_restore_global_template(self):
        """Platform admins can archive and restore global templates."""
        self.client.force_authenticate(self.superuser)
        archive = self.client.post(f"/api/v1/templates/{self.active_template.id}/archive/")
        self.assertEqual(archive.status_code, 200, archive.data)
        self.active_template.refresh_from_db()
        self.assertFalse(self.active_template.is_active)
        self.assertEqual(self.active_template.revisions.count(), 1)
        self.assertEqual(self.active_template.current_revision_id, self.active_revision.id)

        restore = self.client.post(f"/api/v1/templates/{self.active_template.id}/restore/")
        self.assertEqual(restore.status_code, 200, restore.data)
        self.active_template.refresh_from_db()
        self.assertTrue(self.active_template.is_active)
        self.assertEqual(self.active_template.revisions.count(), 1)
        self.assertEqual(self.active_template.current_revision_id, self.active_revision.id)

    def test_scoped_admin_cannot_archive_global_template(self):
        """Scoped admins can use global templates but cannot archive them."""
        self.client.force_authenticate(self.org_admin)
        r = self.client.post(f"/api/v1/templates/{self.active_template.id}/archive/")
        self.assertEqual(r.status_code, 403)
        self.active_template.refresh_from_db()
        self.assertTrue(self.active_template.is_active)

    def test_org_admin_can_archive_and_restore_own_template(self):
        """Org admins can archive and restore templates in their org scope."""
        self.client.force_authenticate(self.org_admin)
        create = self.client.post(
            "/api/v1/templates/",
            {
                "name": "Scoped Lifecycle Template",
                "code": "scoped-lifecycle-template",
                "scenario_type": "audit",
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201, create.data)
        template = ScenarioTemplate.objects.get(code="scoped-lifecycle-template")

        archive = self.client.post(f"/api/v1/templates/{template.id}/archive/")
        self.assertEqual(archive.status_code, 200, archive.data)
        template.refresh_from_db()
        self.assertFalse(template.is_active)
        self.assertEqual(archive.data["latest_version"], 1)

        restore = self.client.post(f"/api/v1/templates/{template.id}/restore/")
        self.assertEqual(restore.status_code, 200, restore.data)
        template.refresh_from_db()
        self.assertTrue(template.is_active)
        self.assertEqual(restore.data["latest_version"], 1)

    def test_business_admin_cannot_create_template_outside_own_business_line(self):
        """Business admins cannot create templates in another business line."""
        self.client.force_authenticate(self.business_admin)
        r = self.client.post(
            "/api/v1/templates/",
            {
                "name": "Foreign Template",
                "code": "foreign-template",
                "scenario_type": "tax",
                "organization": str(self.other_org.id),
                "business_line": str(self.tax_line.id),
            },
            format="json",
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(ScenarioTemplate.objects.filter(code="foreign-template").exists())

    def test_superuser_can_clone_template(self):
        """Platform admins can clone a visible template and receive revision v1."""
        self.client.force_authenticate(self.superuser)
        r = self.client.post(
            f"/api/v1/templates/{self.active_template.id}/clone/",
            {
                "name": "Cloned Template",
                "code": "cloned-template",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        clone = ScenarioTemplate.objects.get(code="cloned-template")
        self.assertEqual(clone.description, self.active_template.description)
        self.assertEqual(clone.quick_questions, self.active_template.quick_questions)
        self.assertIsNone(clone.organization)
        revision = ScenarioTemplateRevision.objects.get(template=clone)
        self.assertEqual(revision.version, 1)
        self.assertEqual(
            revision.change_note,
            "cloned draft from active-template revision 1",
        )

    def test_org_admin_clones_global_template_into_own_org(self):
        """Org admins can clone platform-global templates into their own organization."""
        self.client.force_authenticate(self.org_admin)
        r = self.client.post(
            f"/api/v1/templates/{self.active_template.id}/clone/",
            {
                "name": "Org Cloned Template",
                "code": "org-cloned-template",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        clone = ScenarioTemplate.objects.get(code="org-cloned-template")
        self.assertEqual(clone.organization, self.org)
        self.assertIsNone(clone.business_line)
        self.assertTrue(r.data["can_manage"])

    def test_business_admin_clones_global_template_into_own_business_line(self):
        """Business admins can clone platform-global templates into their own business line."""
        self.client.force_authenticate(self.business_admin)
        r = self.client.post(
            f"/api/v1/templates/{self.active_template.id}/clone/",
            {
                "name": "BL Cloned Template",
                "code": "bl-cloned-template",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        clone = ScenarioTemplate.objects.get(code="bl-cloned-template")
        self.assertEqual(clone.organization, self.org)
        self.assertEqual(clone.business_line, self.audit_line)
        self.assertTrue(r.data["can_manage"])

    def test_business_admin_cannot_clone_template_outside_own_business_line(self):
        """Business admins cannot clone into another business line."""
        self.client.force_authenticate(self.business_admin)
        r = self.client.post(
            f"/api/v1/templates/{self.active_template.id}/clone/",
            {
                "name": "Bad Clone",
                "code": "bad-clone",
                "organization": str(self.other_org.id),
                "business_line": str(self.tax_line.id),
            },
            format="json",
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(ScenarioTemplate.objects.filter(code="bad-clone").exists())

    def test_create_space_from_template(self):
        """The compatibility route submits a governed request and pins current."""
        response, submit = self.submit_template_request(
            self.org_admin,
            name="New Space from Template",
            code="new-space-code",
        )

        self.assertEqual(response.status_code, 202, response.data)
        self.assertFalse(KnowledgeSpace.objects.filter(code="new-space-code").exists())
        submitted = submit.call_args.kwargs["payload"]
        self.assertEqual(submitted["template_version_id"], str(self.active_revision.id))
        self.assertNotIn("documents", submitted)
        self.assertNotIn("assets", submitted)

    def test_template_usage_count_is_scoped_to_admin(self):
        """Pending governed requests are not counted as template applications."""
        first, _ = self.submit_template_request(self.org_admin, code="org-space")
        second, _ = self.submit_template_request(self.superuser, code="other-org-space")
        self.assertEqual(first.status_code, 202, first.data)
        self.assertEqual(second.status_code, 202, second.data)

        self.client.force_authenticate(self.org_admin)
        detail = self.client.get(f"/api/v1/templates/{self.active_template.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["usage_count"], 0)
        self.assertIsNone(detail.data["last_applied_at"])

        self.client.force_authenticate(self.superuser)
        detail = self.client.get(f"/api/v1/templates/{self.active_template.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["usage_count"], 0)

    def test_template_applications_endpoint_is_scoped(self):
        """Unapproved governed requests never appear as applications."""
        self.submit_template_request(self.org_admin, code="scoped-app-space")
        self.submit_template_request(self.superuser, code="hidden-app-space")

        self.client.force_authenticate(self.org_admin)
        r = self.client.get(f"/api/v1/templates/{self.active_template.id}/applications/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, [])

        self.client.force_authenticate(self.superuser)
        r = self.client.get(f"/api/v1/templates/{self.active_template.id}/applications/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, [])

    def test_org_admin_cannot_create_space_outside_own_org(self):
        """The v3 adapter rejects legacy organization authority fields."""
        self.client.force_authenticate(self.org_admin)
        r = self.client.post(
            f"/api/v1/templates/{self.active_template.id}/create-space/",
            {
                "name": "Foreign Org Space",
                "code": "foreign-org-space",
                "organization": str(self.other_org.id),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(r.status_code, 400)
        self.assertFalse(KnowledgeSpace.objects.filter(code="foreign-org-space").exists())

    def test_org_admin_cannot_attach_business_line_from_other_org(self):
        """The adapter accepts only controlled taxonomy identifier fields."""
        self.client.force_authenticate(self.org_admin)
        r = self.client.post(
            f"/api/v1/templates/{self.active_template.id}/create-space/",
            {
                "name": "Mismatched BL Space",
                "code": "mismatched-bl-space",
                "organization": str(self.org.id),
                "business_line": str(self.tax_line.id),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(r.status_code, 400)
        self.assertFalse(KnowledgeSpace.objects.filter(code="mismatched-bl-space").exists())

    def test_business_admin_defaults_to_own_business_line_scope(self):
        """Business admins submit the same governed request as other users."""
        response, submit = self.submit_template_request(
            self.business_admin,
            name="Business Admin Space",
            code="business-admin-space",
            business_line_id=str(self.audit_line.id),
        )
        self.assertEqual(response.status_code, 202, response.data)
        self.assertFalse(KnowledgeSpace.objects.filter(code="business-admin-space").exists())
        self.assertEqual(
            submit.call_args.kwargs["payload"]["business_line_id"],
            str(self.audit_line.id),
        )

    def test_business_admin_cannot_create_space_in_other_business_line(self):
        """Legacy target-scope fields cannot bypass governed taxonomy."""
        self.client.force_authenticate(self.business_admin)
        r = self.client.post(
            f"/api/v1/templates/{self.active_template.id}/create-space/",
            {
                "name": "Foreign BL Space",
                "code": "foreign-bl-space",
                "organization": str(self.other_org.id),
                "business_line": str(self.tax_line.id),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(r.status_code, 400)
        self.assertFalse(KnowledgeSpace.objects.filter(code="foreign-bl-space").exists())

    def test_create_space_from_inactive_template_fails_for_non_platform_admin(self):
        """Non-platform admins cannot instantiate from inactive templates."""
        self.client.force_authenticate(self.org_admin)
        r = self.client.post(
            f"/api/v1/templates/{self.inactive_template.id}/create-space/",
            {
                "name": "New Space from Inactive",
                "code": "new-inactive-space-code",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 404)

    def test_duplicate_space_code_returns_400(self):
        """Every adapter submission requires a per-operation idempotency key."""
        self.client.force_authenticate(self.org_admin)
        r = self.client.post(
            f"/api/v1/templates/{self.active_template.id}/create-space/",
            {
                "name": "Space 1",
                "code": "dup-code",
                "business_line_id": str(self.audit_line.id),
                "work_group_id": str(uuid.uuid4()),
                "office_location_ids": [str(uuid.uuid4())],
            },
            format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("Idempotency-Key", str(r.data))
        self.assertFalse(KnowledgeSpace.objects.filter(code="dup-code").exists())

    def test_seed_scenario_templates_command(self):
        """Seeding command runs idempotently and doesn't duplicate templates."""
        seeded_codes = {
            "new-hire-onboarding",
            "audit-methodology-qa",
            "tax-policy-assistant",
            "consulting-engagement",
            "core-services-helpdesk",
        }
        self.assertFalse(ScenarioTemplate.objects.filter(code__in=seeded_codes).exists())

        # First call
        call_command("seed_scenario_templates")
        self.assertEqual(
            ScenarioTemplate.objects.filter(code__in=seeded_codes).count(),
            len(seeded_codes),
        )

        # Second call
        call_command("seed_scenario_templates")
        self.assertEqual(
            ScenarioTemplate.objects.filter(code__in=seeded_codes).count(),
            len(seeded_codes),
        )
