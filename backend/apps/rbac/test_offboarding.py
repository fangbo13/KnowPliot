from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from unittest.mock import patch

from apps.chat.models import ChatSession, ConversationShare, Feedback, KnowledgeGapTicket, Message
from apps.spaces.models import Organization
from apps.spaces.models import AdminRegistrationCode, InviteCode, SpaceEmailInvite, OrganizationMembership
from apps.spaces.ownership import create_space_with_owner
from apps.users.models import AuthSession
from apps.rbac.models import Permission, Role, RolePermission, UserRole


class OffboardingImpactTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.actor = user_model.objects.create_superuser(
            username="platform", email="platform@example.test", password="safe-password"
        )
        self.subject = user_model.objects.create_user(
            username="departing-owner", email="departing-owner@example.test", password="safe-password"
        )
        organization = Organization.objects.create(name="Offboarding Org", slug="offboarding-org")
        self.space = create_space_with_owner(
            organization=organization,
            owner=self.subject,
            name="Departing owner space",
            code="departing-owner-space",
        )

    def test_impact_reports_canonical_owner_as_a_blocker(self):
        from apps.audit.models import AuditLog
        from apps.chat.models import ComplianceExportJob
        from apps.rbac.offboarding import OffboardingImpactService

        impact = OffboardingImpactService.inspect(actor=self.actor, subject=self.subject)

        self.assertEqual(impact["subject"]["id"], str(self.subject.id))
        self.assertEqual(impact["blockers"]["owned_spaces"], [str(self.space.id)])
        self.assertEqual(impact["blockers"]["owned_space_details"], [{
            "id": str(self.space.id),
            "display_name": self.space.name,
            "status": "active",
            "ownership_version": 1,
        }])
        self.assertFalse(impact["can_deactivate_without_successor"])
        self.assertTrue(impact["impact_version"])
        AuditLog.objects.create(
            user=self.subject,
            action="user_update",
            target_type="User",
            target_id=self.subject.id,
        )
        ComplianceExportJob.objects.create(
            requested_by=self.subject,
            dataset=ComplianceExportJob.DATASET_DOCUMENTS,
            status=ComplianceExportJob.STATUS_SUCCEEDED,
        )
        protected_impact = OffboardingImpactService.inspect(actor=self.actor, subject=self.subject)
        self.assertEqual(protected_impact["protected_history"]["audit_records"], 1)
        self.assertEqual(protected_impact["protected_history"]["completed_export_jobs"], 1)

    def test_offboard_rejects_unmapped_canonical_owner_without_mutation(self):
        from apps.rbac.offboarding import OffboardingConflict, OffboardingImpactService, OffboardingService

        impact = OffboardingImpactService.inspect(actor=self.actor, subject=self.subject)

        with self.assertRaisesRegex(OffboardingConflict, "owner_successor_required"):
            OffboardingService.offboard(
                actor=self.actor,
                subject_id=self.subject.id,
                impact_version=impact["impact_version"],
                reason_code="employment_ended",
                space_transfers=[],
            )

        self.subject.refresh_from_db()
        self.space.refresh_from_db()
        self.assertTrue(self.subject.is_active)
        self.assertEqual(self.space.owner_id, self.subject.id)

    def test_admin_successor_candidates_are_limited_to_active_users_in_the_scope(self):
        OrganizationMembership.objects.create(
            user=self.subject,
            organization=self.space.organization,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )
        eligible = get_user_model().objects.create_user(
            username="eligible-admin-successor", email="eligible@example.test", password="safe-password"
        )
        inactive = get_user_model().objects.create_user(
            username="inactive-admin-successor", email="inactive@example.test", password="safe-password", is_active=False
        )
        create_space_with_owner(
            organization=self.space.organization,
            owner=eligible,
            name="Eligible successor space",
            code="eligible-successor-space",
        )
        create_space_with_owner(
            organization=self.space.organization,
            owner=inactive,
            name="Inactive successor space",
            code="inactive-successor-space",
        )

        self.client.force_authenticate(self.actor)
        response = self.client.get(
            f"/api/v1/admin/users/{self.subject.id}/offboarding-admin-candidates/",
            {
                "organization_id": str(self.space.organization_id),
                "role": OrganizationMembership.ROLE_ORG_ADMIN,
            },
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["results"], [
            {"id": str(eligible.id), "display_name": eligible.username},
        ])

    def test_platform_offboarding_api_exposes_impact_and_blocks_unmapped_owner(self):
        self.client.force_authenticate(self.actor)
        impact = self.client.get(f"/api/v1/admin/users/{self.subject.id}/offboarding-impact/")
        response = self.client.post(
            f"/api/v1/admin/users/{self.subject.id}/offboard/",
            {"impact_version": impact.data["impact_version"], "reason_code": "employment_ended", "space_transfers": []},
            format="json",
        )

        self.assertEqual(impact.status_code, 200)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error_code"], "owner_successor_required")

    def test_legacy_deactivate_returns_offboarding_required_for_unmapped_owner(self):
        self.client.force_authenticate(self.actor)
        response = self.client.post(f"/api/v1/rbac/users/{self.subject.id}/deactivate/", {}, format="json")

        self.subject.refresh_from_db()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error_code"], "offboarding_required")
        self.assertIn("impact_url", response.data)
        self.assertTrue(self.subject.is_active)

    def test_impact_blocks_offboarding_the_final_platform_admin(self):
        from apps.rbac.models import Role, UserRole
        from apps.rbac.offboarding import OffboardingImpactService

        role = Role.objects.create(name="admin", label="Administrator", scope="system")
        UserRole.objects.create(user=self.subject, role=role, assigned_by=self.actor)

        impact = OffboardingImpactService.inspect(actor=self.actor, subject=self.subject)

        self.assertTrue(impact["blockers"]["last_platform_admin"])
        self.assertFalse(impact["can_deactivate_without_successor"])

    def test_offboarding_can_atomically_succeed_the_final_platform_admin(self):
        from apps.rbac.offboarding import OffboardingImpactService, OffboardingService

        role = Role.objects.create(name="admin", label="Administrator", scope="system")
        UserRole.objects.create(user=self.subject, role=role, assigned_by=self.actor)
        successor = get_user_model().objects.create_user(
            username="platform-admin-successor", email="platform-admin-successor@example.test", password="safe-password"
        )
        create_space_with_owner(
            organization=self.space.organization,
            owner=successor,
            name="Platform successor space",
            code="platform-successor-space",
        )
        impact = OffboardingImpactService.inspect(actor=self.actor, subject=self.subject)

        result = OffboardingService.offboard(
            actor=self.actor,
            subject_id=self.subject.id,
            impact_version=impact["impact_version"],
            reason_code="employment_ended",
            space_transfers=[{
                "space_id": str(self.space.id),
                "successor_user_id": str(successor.id),
                "expected_ownership_version": self.space.ownership_version,
            }],
            admin_successions=[{
                "scope_type": "platform",
                "role": "admin",
                "successor_user_id": str(successor.id),
            }],
        )

        self.subject.refresh_from_db()
        self.assertTrue(result["offboarded"])
        self.assertFalse(self.subject.is_active)
        self.assertTrue(UserRole.objects.filter(user=successor, role=role, is_active=True).exists())

    def test_offboard_with_successor_transfers_owner_revokes_sessions_and_deactivates_subject(self):
        from apps.audit.models import AuditLog
        from apps.rbac.offboarding import OffboardingImpactService, OffboardingService

        successor = get_user_model().objects.create_user(
            username="successor", email="successor@example.test", password="safe-password"
        )
        create_space_with_owner(
            organization=self.space.organization,
            owner=successor,
            name="Successor space",
            code="successor-offboarding-space",
        )
        AuthSession.objects.create(
            user=self.subject,
            refresh_jti="offboarding-session",
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        session = ChatSession.objects.create(user=self.subject, space=self.space, title="Private history")
        message = Message.objects.create(
            session=session, space=self.space, role="user", content="Please review this answer."
        )
        feedback = Feedback.objects.create(
            message=message,
            space=self.space,
            user=self.subject,
            status=Feedback.STATUS_IN_REVIEW,
            reviewer=self.subject,
        )
        ticket = KnowledgeGapTicket.objects.create(
            space=self.space,
            feedback=feedback,
            question_snapshot="Please review this answer.",
            normalized_question_hash=KnowledgeGapTicket.hash_question("Please review this answer."),
            status=KnowledgeGapTicket.STATUS_IN_PROGRESS,
            assignee=self.subject,
        )
        share = ConversationShare.objects.create(
            session=session, owner=self.subject, organization=self.space.organization
        )
        invite = InviteCode.objects.create(
            space=self.space,
            code_hash="a" * 64,
            created_by=self.subject,
            status="active",
        )
        admin_code = AdminRegistrationCode.objects.create(
            code_hash="b" * 64,
            grants_role=OrganizationMembership.ROLE_ORG_ADMIN,
            organization=self.space.organization,
            created_by=self.subject,
            status="active",
        )
        email_invite = SpaceEmailInvite.objects.create(
            email="pending@example.test", space=self.space, invited_by=self.subject, status="pending"
        )
        impact = OffboardingImpactService.inspect(actor=self.actor, subject=self.subject)
        self.assertEqual(impact["actions"]["open_feedback_reviews"], 1)
        self.assertEqual(impact["actions"]["open_knowledge_gap_tickets"], 1)

        with self.captureOnCommitCallbacks(execute=True):
            result = OffboardingService.offboard(
                actor=self.actor,
                subject_id=self.subject.id,
                impact_version=impact["impact_version"],
                reason_code="employment_ended",
                space_transfers=[
                    {
                        "space_id": str(self.space.id),
                        "successor_user_id": str(successor.id),
                        "expected_ownership_version": self.space.ownership_version,
                    }
                ],
            )

        self.subject.refresh_from_db()
        self.space.refresh_from_db()
        self.assertTrue(result["offboarded"])
        self.assertFalse(self.subject.is_active)
        self.assertEqual(self.subject.deactivated_by_id, self.actor.id)
        self.assertEqual(self.subject.deactivation_reason_code, "employment_ended")
        self.assertIsNotNone(self.subject.deactivated_at)
        self.assertEqual(self.space.owner_id, successor.id)
        self.assertEqual(self.subject.space_memberships.get(space=self.space).status, "revoked")
        self.assertIsNotNone(self.subject.auth_sessions.get().revoked_at)
        share.refresh_from_db()
        invite.refresh_from_db()
        admin_code.refresh_from_db()
        email_invite.refresh_from_db()
        self.assertIsNotNone(share.revoked_at)
        self.assertEqual(invite.status, "revoked")
        self.assertEqual(admin_code.status, "revoked")
        self.assertEqual(email_invite.status, "revoked")
        feedback.refresh_from_db()
        ticket.refresh_from_db()
        self.assertIsNone(feedback.reviewer_id)
        self.assertEqual(feedback.status, Feedback.STATUS_PENDING_REVIEW)
        self.assertIsNone(ticket.assignee_id)
        self.assertEqual(ticket.status, KnowledgeGapTicket.STATUS_OPEN)
        self.assertTrue(AuditLog.objects.filter(
            action="user_deactivate",
            target_id=self.subject.id,
            details__event="account_offboarding",
        ).exists())

    def test_failure_during_a_multi_space_offboard_rolls_back_every_prior_change(self):
        from apps.rbac.offboarding import OffboardingImpactService, OffboardingService
        from apps.spaces.ownership_services import OwnershipTransferService

        second_space = create_space_with_owner(
            organization=self.space.organization,
            owner=self.subject,
            name="Second departing owner space",
            code="second-departing-owner-space",
        )
        successor = get_user_model().objects.create_user(
            username="rollback-successor", email="rollback-successor@example.test", password="safe-password"
        )
        create_space_with_owner(
            organization=self.space.organization,
            owner=successor,
            name="Rollback successor home",
            code="rollback-successor-home",
        )
        impact = OffboardingImpactService.inspect(actor=self.actor, subject=self.subject)
        original_force = OwnershipTransferService.force
        calls = 0

        def fail_on_second_force(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected transfer failure")
            return original_force(**kwargs)

        with patch("apps.rbac.offboarding.OwnershipTransferService.force", side_effect=fail_on_second_force):
            with self.assertRaisesRegex(RuntimeError, "injected transfer failure"):
                OffboardingService.offboard(
                    actor=self.actor,
                    subject_id=self.subject.id,
                    impact_version=impact["impact_version"],
                    reason_code="employment_ended",
                    space_transfers=[
                        {
                            "space_id": str(self.space.id),
                            "successor_user_id": str(successor.id),
                            "expected_ownership_version": self.space.ownership_version,
                        },
                        {
                            "space_id": str(second_space.id),
                            "successor_user_id": str(successor.id),
                            "expected_ownership_version": second_space.ownership_version,
                        },
                    ],
                )

        self.subject.refresh_from_db()
        self.space.refresh_from_db()
        second_space.refresh_from_db()
        self.assertTrue(self.subject.is_active)
        self.assertEqual(self.space.owner_id, self.subject.id)
        self.assertEqual(second_space.owner_id, self.subject.id)

    def test_stale_impact_is_rejected_without_mutation(self):
        from apps.rbac.offboarding import OffboardingConflict, OffboardingImpactService, OffboardingService

        successor = get_user_model().objects.create_user(
            username="stale-successor", email="stale-successor@example.test", password="safe-password"
        )
        create_space_with_owner(
            organization=self.space.organization,
            owner=successor,
            name="Stale successor home",
            code="stale-successor-home",
        )
        impact = OffboardingImpactService.inspect(actor=self.actor, subject=self.subject)
        self.space.ownership_version += 1
        self.space.save(update_fields=["ownership_version"])

        with self.assertRaisesRegex(OffboardingConflict, "offboarding_impact_changed"):
            OffboardingService.offboard(
                actor=self.actor,
                subject_id=self.subject.id,
                impact_version=impact["impact_version"],
                reason_code="employment_ended",
                space_transfers=[
                    {
                        "space_id": str(self.space.id),
                        "successor_user_id": str(successor.id),
                        "expected_ownership_version": 1,
                    }
                ],
            )

        self.subject.refresh_from_db()
        self.space.refresh_from_db()
        self.assertTrue(self.subject.is_active)
        self.assertEqual(self.space.owner_id, self.subject.id)

    def test_reactivation_does_not_restore_revoked_authority_or_credentials(self):
        from apps.rbac.offboarding import OffboardingImpactService, OffboardingService

        successor = get_user_model().objects.create_user(
            username="reactivation-successor", email="reactivation-successor@example.test", password="safe-password"
        )
        create_space_with_owner(
            organization=self.space.organization,
            owner=successor,
            name="Reactivation successor home",
            code="reactivation-successor-home",
        )
        role = Role.objects.create(name="retained-reader", label="Retained reader", scope="content")
        assignment = UserRole.objects.create(user=self.subject, role=role, assigned_by=self.actor)
        session = AuthSession.objects.create(
            user=self.subject,
            refresh_jti="reactivation-session",
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        chat_session = ChatSession.objects.create(user=self.subject, space=self.space, title="Private history")
        share = ConversationShare.objects.create(
            session=chat_session, owner=self.subject, organization=self.space.organization
        )
        impact = OffboardingImpactService.inspect(actor=self.actor, subject=self.subject)
        OffboardingService.offboard(
            actor=self.actor,
            subject_id=self.subject.id,
            impact_version=impact["impact_version"],
            reason_code="employment_ended",
            space_transfers=[
                {
                    "space_id": str(self.space.id),
                    "successor_user_id": str(successor.id),
                    "expected_ownership_version": self.space.ownership_version,
                }
            ],
        )

        self.client.force_authenticate(self.actor)
        response = self.client.post(f"/api/v1/rbac/users/{self.subject.id}/activate/", {}, format="json")

        self.subject.refresh_from_db()
        assignment.refresh_from_db()
        session.refresh_from_db()
        share.refresh_from_db()
        self.space.refresh_from_db()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(self.subject.is_active)
        self.assertEqual(self.space.owner_id, successor.id)
        self.assertEqual(self.subject.space_memberships.get(space=self.space).status, "revoked")
        self.assertFalse(assignment.is_active)
        self.assertIsNotNone(session.revoked_at)
        self.assertIsNotNone(share.revoked_at)

    def test_offboarding_can_atomically_succeed_the_final_organization_admin(self):
        from apps.rbac.offboarding import OffboardingImpactService, OffboardingService

        successor = get_user_model().objects.create_user(
            username="admin-successor", email="admin-successor@example.test", password="safe-password"
        )
        create_space_with_owner(
            organization=self.space.organization,
            owner=successor,
            name="Admin successor home",
            code="admin-successor-home",
        )
        OrganizationMembership.objects.create(
            user=self.subject,
            organization=self.space.organization,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )
        impact = OffboardingImpactService.inspect(actor=self.actor, subject=self.subject)

        result = OffboardingService.offboard(
            actor=self.actor,
            subject_id=self.subject.id,
            impact_version=impact["impact_version"],
            reason_code="employment_ended",
            space_transfers=[
                {
                    "space_id": str(self.space.id),
                    "successor_user_id": str(successor.id),
                    "expected_ownership_version": self.space.ownership_version,
                }
            ],
            admin_successions=[
                {
                    "organization_id": str(self.space.organization_id),
                    "business_line_id": None,
                    "role": OrganizationMembership.ROLE_ORG_ADMIN,
                    "successor_user_id": str(successor.id),
                }
            ],
        )

        self.subject.refresh_from_db()
        self.assertTrue(result["offboarded"])
        self.assertFalse(self.subject.is_active)
        self.assertTrue(OrganizationMembership.objects.filter(
            user=successor,
            organization=self.space.organization,
            business_line__isnull=True,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
            is_active=True,
        ).exists())


class AdministratorContinuityTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.operator = user_model.objects.create_user(
            username="role-operator", email="role-operator@example.test", password="safe-password"
        )
        self.target = user_model.objects.create_user(
            username="last-admin", email="last-admin@example.test", password="safe-password"
        )
        self.organization = Organization.objects.create(name="Continuity Org", slug="continuity-org")

        permission = Permission.objects.create(
            codename="user.assign_role", resource="user", action="assign_role", label="Assign roles"
        )
        operator_role = Role.objects.create(name="role-operator", label="Role operator", scope="system")
        RolePermission.objects.create(role=operator_role, permission=permission)
        UserRole.objects.create(user=self.operator, role=operator_role, assigned_by=self.operator)
        self.admin_role = Role.objects.create(name="admin", label="Administrator", scope="system")

    def test_cannot_revoke_the_final_active_platform_admin_role(self):
        assignment = UserRole.objects.create(user=self.target, role=self.admin_role, assigned_by=self.operator)
        self.client.force_authenticate(self.operator)

        response = self.client.delete(f"/api/v1/rbac/user-roles/{assignment.id}/")

        assignment.refresh_from_db()
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["error_code"], "last_platform_admin")
        self.assertTrue(assignment.is_active)

    def test_cannot_remove_the_final_active_organization_admin(self):
        OrganizationMembership.objects.create(
            user=self.target,
            organization=self.organization,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )
        superuser = get_user_model().objects.create_superuser(
            username="continuity-root", email="continuity-root@example.test", password="safe-password"
        )
        self.client.force_authenticate(superuser)

        response = self.client.delete(
            f"/api/v1/admin/users/{self.target.id}/assignments/",
            {
                "scope": "organization",
                "scope_id": str(self.organization.id),
                "role": OrganizationMembership.ROLE_ORG_ADMIN,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["error_code"], "last_organization_admin")
        self.assertTrue(
            OrganizationMembership.objects.filter(
                user=self.target,
                organization=self.organization,
                role=OrganizationMembership.ROLE_ORG_ADMIN,
                is_active=True,
            ).exists()
        )
