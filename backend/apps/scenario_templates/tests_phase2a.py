# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APITestCase
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
        self.assertEqual(revision.snapshot["template_code"], "new-template")

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
        self.assertEqual(revisions.data[0]["snapshot"]["description"], "Updated description")
        self.assertEqual(revisions.data[1]["snapshot"]["quick_questions"], ["Original question"])

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
        self.assertEqual(
            ScenarioTemplateRevision.objects.filter(
                template=self.active_template,
                change_note="archived",
            ).count(),
            1,
        )

        restore = self.client.post(f"/api/v1/templates/{self.active_template.id}/restore/")
        self.assertEqual(restore.status_code, 200, restore.data)
        self.active_template.refresh_from_db()
        self.assertTrue(self.active_template.is_active)
        self.assertEqual(
            ScenarioTemplateRevision.objects.filter(
                template=self.active_template,
                change_note="restored",
            ).count(),
            1,
        )

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
        self.assertEqual(archive.data["latest_version"], 2)

        restore = self.client.post(f"/api/v1/templates/{template.id}/restore/")
        self.assertEqual(restore.status_code, 200, restore.data)
        template.refresh_from_db()
        self.assertTrue(template.is_active)
        self.assertEqual(restore.data["latest_version"], 3)

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
        self.assertEqual(revision.change_note, "cloned from active-template")

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
        """Admin can instantiate a space from an active template."""
        self.client.force_authenticate(self.org_admin)
        r = self.client.post(
            f"/api/v1/templates/{self.active_template.id}/create-space/",
            {
                "name": "New Space from Template",
                "code": "new-space-code",
                "organization": str(self.org.id),
                "visibility": "private",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        
        # Verify space exists
        space = KnowledgeSpace.objects.get(code="new-space-code")
        self.assertEqual(space.name, "New Space from Template")
        self.assertEqual(space.created_by, self.org_admin)
        self.assertEqual(space.visibility, "private")
        
        # Verify settings contain template metadata
        self.assertEqual(space.settings["template_id"], str(self.active_template.id))
        self.assertEqual(space.settings["template_code"], self.active_template.code)
        self.assertEqual(space.settings["scenario_type"], self.active_template.scenario_type)
        self.assertEqual(space.settings["quick_questions"], self.active_template.quick_questions)

        # Verify creator is owner
        membership = SpaceMembership.objects.filter(space=space, user=self.org_admin).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, SpaceMembership.ROLE_OWNER)
        self.assertEqual(membership.status, "active")

        application = ScenarioTemplateApplication.objects.get(space=space)
        self.assertEqual(application.template, self.active_template)
        self.assertEqual(application.organization, self.org)
        self.assertEqual(application.created_by, self.org_admin)
        self.assertEqual(application.template_snapshot["template_code"], self.active_template.code)
        self.assertIn("latest_version", application.template_snapshot)

    def test_template_usage_count_is_scoped_to_admin(self):
        """Usage stats for global templates are scoped to the requesting admin."""
        self.client.force_authenticate(self.org_admin)
        self.client.post(
            f"/api/v1/templates/{self.active_template.id}/create-space/",
            {
                "name": "Org Space",
                "code": "org-space",
                "organization": str(self.org.id),
            },
            format="json",
        )

        self.client.force_authenticate(self.superuser)
        self.client.post(
            f"/api/v1/templates/{self.active_template.id}/create-space/",
            {
                "name": "Other Org Space",
                "code": "other-org-space",
                "organization": str(self.other_org.id),
            },
            format="json",
        )

        self.client.force_authenticate(self.org_admin)
        detail = self.client.get(f"/api/v1/templates/{self.active_template.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["usage_count"], 1)
        self.assertIsNotNone(detail.data["last_applied_at"])

        self.client.force_authenticate(self.superuser)
        detail = self.client.get(f"/api/v1/templates/{self.active_template.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["usage_count"], 2)

    def test_template_applications_endpoint_is_scoped(self):
        """Application history hides out-of-scope usage records."""
        self.client.force_authenticate(self.org_admin)
        self.client.post(
            f"/api/v1/templates/{self.active_template.id}/create-space/",
            {
                "name": "Scoped App Space",
                "code": "scoped-app-space",
                "organization": str(self.org.id),
            },
            format="json",
        )

        self.client.force_authenticate(self.superuser)
        self.client.post(
            f"/api/v1/templates/{self.active_template.id}/create-space/",
            {
                "name": "Hidden App Space",
                "code": "hidden-app-space",
                "organization": str(self.other_org.id),
            },
            format="json",
        )

        self.client.force_authenticate(self.org_admin)
        r = self.client.get(f"/api/v1/templates/{self.active_template.id}/applications/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]["space_code"], "scoped-app-space")

        self.client.force_authenticate(self.superuser)
        r = self.client.get(f"/api/v1/templates/{self.active_template.id}/applications/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 2)

    def test_org_admin_cannot_create_space_outside_own_org(self):
        """Org admins cannot instantiate template spaces in another organization."""
        self.client.force_authenticate(self.org_admin)
        r = self.client.post(
            f"/api/v1/templates/{self.active_template.id}/create-space/",
            {
                "name": "Foreign Org Space",
                "code": "foreign-org-space",
                "organization": str(self.other_org.id),
            },
            format="json",
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(KnowledgeSpace.objects.filter(code="foreign-org-space").exists())

    def test_org_admin_cannot_attach_business_line_from_other_org(self):
        """Business line must belong to the selected organization."""
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
        )
        self.assertEqual(r.status_code, 400)
        self.assertFalse(KnowledgeSpace.objects.filter(code="mismatched-bl-space").exists())

    def test_business_admin_defaults_to_own_business_line_scope(self):
        """Business admins can instantiate templates only inside their business line."""
        self.client.force_authenticate(self.business_admin)
        r = self.client.post(
            f"/api/v1/templates/{self.active_template.id}/create-space/",
            {
                "name": "Business Admin Space",
                "code": "business-admin-space",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        space = KnowledgeSpace.objects.get(code="business-admin-space")
        self.assertEqual(space.organization, self.org)
        self.assertEqual(space.business_line, self.audit_line)

    def test_business_admin_cannot_create_space_in_other_business_line(self):
        """Business admins cannot instantiate spaces outside their assigned line."""
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
        )
        self.assertEqual(r.status_code, 403)
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
        """Creating a space with an existing code returns 400 Bad Request."""
        self.client.force_authenticate(self.org_admin)
        
        # Create first space
        self.client.post(
            f"/api/v1/templates/{self.active_template.id}/create-space/",
            {"name": "Space 1", "code": "dup-code"},
            format="json",
        )
        
        # Try creating second space with same code
        r = self.client.post(
            f"/api/v1/templates/{self.active_template.id}/create-space/",
            {"name": "Space 2", "code": "dup-code"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("code", r.data.get("detail", r.data))

    def test_seed_scenario_templates_command(self):
        """Seeding command runs idempotently and doesn't duplicate templates."""
        # Clear existing templates to start fresh
        ScenarioTemplate.objects.all().delete()
        
        # First call
        call_command("seed_scenario_templates")
        count = ScenarioTemplate.objects.count()
        self.assertGreaterEqual(count, 5)

        # Second call
        call_command("seed_scenario_templates")
        self.assertEqual(ScenarioTemplate.objects.count(), count)
