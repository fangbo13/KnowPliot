# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Pure contracts for the scoped capability resolver."""

from uuid import UUID

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from apps.spaces.models import OrganizationMembership

try:
    from apps.rbac.capabilities import (
        BUSINESS_ADMIN_CAPABILITIES,
        ARCHIVED_OWNER_CAPABILITIES,
        ORGANIZATION_ADMIN_CAPABILITIES,
        PLATFORM_CAPABILITIES,
        SPACE_ROLE_CAPABILITIES,
        CapabilityGrantSnapshot,
        build_capability_payload,
    )
except ImportError:  # RED: the capability service does not exist yet.
    BUSINESS_ADMIN_CAPABILITIES = None
    ARCHIVED_OWNER_CAPABILITIES = None
    ORGANIZATION_ADMIN_CAPABILITIES = None
    PLATFORM_CAPABILITIES = None
    SPACE_ROLE_CAPABILITIES = None
    CapabilityGrantSnapshot = None
    build_capability_payload = None


SPACE_A = UUID("00000000-0000-0000-0000-00000000000a")
SPACE_B = UUID("00000000-0000-0000-0000-00000000000b")
ORG_A = UUID("10000000-0000-0000-0000-00000000000a")
LINE_A = UUID("20000000-0000-0000-0000-00000000000a")

MEMBER = {
    "chat.ask",
    "chat.export",
    "chat.history",
    "chat.share",
    # KB read-only access spec (amended): members browse AND manage documents.
    "knowledge.read",
    "knowledge.manage",
    "workspace.ownership.transfer.accept",
}
BASE_CHAT = {"chat.ask", "chat.history"}
OWNER_MANAGEMENT = {
    "audit.read",
    "knowledge.download",
    "knowledge.index",
    "knowledge.manage",
    "knowledge.read",
    "quality.read",
    "quality.review",
    "workspace.access_requests.manage",
    "workspace.invites.manage",
    "workspace.lifecycle.manage",
    "workspace.manage",
    "workspace.members.manage",
    "workspace.settings.manage",
    "workspace.ownership.read",
    "workspace.ownership.transfer.request",
}


class CapabilityMatrixTest(SimpleTestCase):
    def test_space_role_matrix_is_locked_and_least_privilege(self):
        self.assertIsNotNone(SPACE_ROLE_CAPABILITIES)
        self.assertEqual(
            SPACE_ROLE_CAPABILITIES["guest"],
            frozenset({"chat.ask", "knowledge.read"}),
        )
        self.assertEqual(SPACE_ROLE_CAPABILITIES["member"], frozenset(MEMBER))
        self.assertEqual(
            SPACE_ROLE_CAPABILITIES["reviewer"],
            frozenset(
                BASE_CHAT
                | {
                    "workspace.manage",
                    "knowledge.read",
                    "quality.read",
                    "quality.review",
                    "audit.read",
                }
            ),
        )
        self.assertEqual(
            SPACE_ROLE_CAPABILITIES["knowledge_admin"],
            frozenset(
                BASE_CHAT
                | {
                    "workspace.manage",
                    "knowledge.read",
                    "knowledge.manage",
                    "knowledge.index",
                    "knowledge.download",
                    "quality.read",
                    "quality.review",
                }
            ),
        )
        self.assertEqual(
            SPACE_ROLE_CAPABILITIES["owner"],
            frozenset(MEMBER | OWNER_MANAGEMENT),
        )
        for role in ("knowledge_admin", "reviewer", "guest"):
            with self.subTest(role=role):
                self.assertNotIn("chat.share", SPACE_ROLE_CAPABILITIES[role])
                self.assertNotIn("chat.export", SPACE_ROLE_CAPABILITIES[role])

    def test_governance_and_platform_matrices_are_scope_specific(self):
        self.assertEqual(
            PLATFORM_CAPABILITIES,
            frozenset(
                {
                    "platform.access",
                    "platform.audit.read",
                    "platform.knowledge.read",
                    "platform.metrics.read",
                    "platform.models.manage",
                    "platform.organizations.manage",
                    "platform.roles.manage",
                    "platform.taxonomy.manage",
                    "platform.templates.manage",
                    "platform.users.manage",
                    "platform.users.offboard",
                    "platform.workspace_creation_policies.manage",
                    "platform.workspace_creation_requests.manage",
                    "workspace.ownership.read",
                    "workspace.ownership.transfer.force",
                    "governance.admin_succession.manage",
                    "governance.users.suspend",
                }
            ),
        )
        self.assertEqual(
            ORGANIZATION_ADMIN_CAPABILITIES,
            frozenset(
                {
                    "governance.access",
                    "governance.audit.read",
                    "governance.business_lines.manage",
                    "governance.metrics.read",
                    "governance.models.bind",
                    "governance.organization.settings.manage",
                    "governance.spaces.manage",
                    "governance.taxonomy.manage",
                    "governance.templates.manage",
                    "governance.users.manage",
                    "workspace.ownership.read",
                    "workspace.ownership.transfer.force",
                    "governance.admin_succession.manage",
                    "governance.users.suspend",
                }
            ),
        )
        self.assertEqual(
            BUSINESS_ADMIN_CAPABILITIES,
            frozenset(
                {
                    "governance.access",
                    "governance.audit.read",
                    "governance.metrics.read",
                    "governance.spaces.manage",
                    "governance.taxonomy.manage",
                    "governance.templates.manage",
                    "governance.users.manage",
                    "workspace.ownership.read",
                    "workspace.ownership.transfer.force",
                    "governance.users.suspend",
                }
            ),
        )
        self.assertFalse(
            {"platform.access", "governance.organization.settings.manage"}
            & BUSINESS_ADMIN_CAPABILITIES
        )

    def test_payload_is_sorted_unique_and_preserves_governance_priority(self):
        self.assertIsNotNone(build_capability_payload)
        snapshot = CapabilityGrantSnapshot(
            organization_ids=(ORG_A, ORG_A),
            business_line_ids=(LINE_A, LINE_A),
            space_roles={SPACE_B: "member", SPACE_A: "owner"},
            selected_space_id=SPACE_A,
        )

        payload = build_capability_payload(snapshot)

        self.assertEqual(
            payload["scopes"],
            {
                "platform": False,
                "organization_ids": [str(ORG_A)],
                "business_line_ids": [str(LINE_A)],
                "space_ids": [str(SPACE_A), str(SPACE_B)],
            },
        )
        self.assertEqual(payload["capabilities"], sorted(set(payload["capabilities"])))
        self.assertIn("workspace.manage", payload["capabilities"])
        self.assertEqual(payload["default_console"], "/governance")

    def test_default_console_priority_is_platform_then_governance_then_workspace_then_chat(self):
        cases = [
            (
                CapabilityGrantSnapshot(platform=True),
                "/platform-admin",
            ),
            (
                CapabilityGrantSnapshot(organization_ids=(ORG_A,)),
                "/governance",
            ),
            (
                CapabilityGrantSnapshot(business_line_ids=(LINE_A,)),
                "/governance",
            ),
            (
                CapabilityGrantSnapshot(space_roles={SPACE_B: "owner", SPACE_A: "reviewer"}),
                f"/workspace/{SPACE_A}/manage",
            ),
            (
                CapabilityGrantSnapshot(space_roles={SPACE_A: "member"}),
                "/chat",
            ),
            (
                CapabilityGrantSnapshot(),
                "/chat",
            ),
        ]

        for snapshot, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(build_capability_payload(snapshot)["default_console"], expected)

    @override_settings(
        CAPABILITY_NAV=True,
        DEEP_ANSWER_MODE=True,
        THINKING_MODE=False,
        WORKSPACE_CREATION_APPROVAL=True,
        WORKSPACE_JOIN_V2=False,
        WORKSPACE_PERMANENT_DELETE=True,
    )
    def test_v2_bootstrap_shape_reports_navigation_and_non_authorizing_availability(self):
        payload = build_capability_payload(CapabilityGrantSnapshot())

        self.assertEqual(payload["navigation_mode"], "capability")
        self.assertTrue(payload["configuration_revision"])
        self.assertEqual(
            payload["feature_availability"],
            {
                "deep": True,
                "thinking": False,
                "workspace_creation_approval": True,
                "workspace_join_v2": False,
                "workspace_permanent_delete": True,
            },
        )
        self.assertEqual(payload["capabilities"], [])

    def test_deep_capability_is_selected_space_governed_and_guest_denied(self):
        member = build_capability_payload(
            CapabilityGrantSnapshot(
                space_roles={SPACE_A: "member", SPACE_B: "member"},
                selected_space_id=SPACE_A,
                deep_space_ids=(SPACE_A,),
            )
        )
        wrong_space = build_capability_payload(
            CapabilityGrantSnapshot(
                space_roles={SPACE_A: "member", SPACE_B: "member"},
                selected_space_id=SPACE_B,
                deep_space_ids=(SPACE_A,),
            )
        )
        guest = build_capability_payload(
            CapabilityGrantSnapshot(
                space_roles={SPACE_A: "guest"},
                selected_space_id=SPACE_A,
                deep_space_ids=(SPACE_A,),
            )
        )

        self.assertIn("chat.deep", member["capabilities"])
        self.assertNotIn("chat.deep", wrong_space["capabilities"])
        self.assertNotIn("chat.deep", guest["capabilities"])

    def test_thinking_capability_is_independent_and_requires_non_guest_membership(self):
        member = build_capability_payload(
            CapabilityGrantSnapshot(
                space_roles={SPACE_A: "member"},
                selected_space_id=SPACE_A,
                thinking_space_ids=(SPACE_A,),
            )
        )
        deep_only = build_capability_payload(
            CapabilityGrantSnapshot(
                space_roles={SPACE_A: "member"},
                selected_space_id=SPACE_A,
                deep_space_ids=(SPACE_A,),
            )
        )
        guest = build_capability_payload(
            CapabilityGrantSnapshot(
                space_roles={SPACE_A: "guest"},
                selected_space_id=SPACE_A,
                thinking_space_ids=(SPACE_A,),
            )
        )
        platform_without_membership = build_capability_payload(
            CapabilityGrantSnapshot(
                platform=True,
                selected_space_id=SPACE_A,
                thinking_space_ids=(SPACE_A,),
            )
        )

        self.assertIn("chat.thinking", member["capabilities"])
        self.assertNotIn("chat.deep", member["capabilities"])
        self.assertIn("chat.deep", deep_only["capabilities"])
        self.assertNotIn("chat.thinking", deep_only["capabilities"])
        self.assertNotIn("chat.thinking", guest["capabilities"])
        self.assertNotIn("chat.thinking", platform_without_membership["capabilities"])

    @override_settings(WORKSPACE_PERMANENT_DELETE=True)
    def test_permanent_delete_is_flagged_canonical_owner_only_and_archived_is_bounded(self):
        noncanonical = build_capability_payload(
            CapabilityGrantSnapshot(
                space_roles={SPACE_A: "owner"},
                selected_space_id=SPACE_A,
            )
        )
        active_owner = build_capability_payload(
            CapabilityGrantSnapshot(
                space_roles={SPACE_A: "owner"},
                selected_space_id=SPACE_A,
                canonical_owner_space_ids=(SPACE_A,),
            )
        )
        archived_owner = build_capability_payload(
            CapabilityGrantSnapshot(
                space_roles={SPACE_A: "owner"},
                selected_space_id=SPACE_A,
                canonical_owner_space_ids=(SPACE_A,),
                archived_owner_space_ids=(SPACE_A,),
            )
        )

        self.assertNotIn("workspace.delete.permanent", noncanonical["capabilities"])
        self.assertIn("workspace.delete.permanent", active_owner["capabilities"])
        self.assertEqual(
            set(archived_owner["capabilities"]),
            set(ARCHIVED_OWNER_CAPABILITIES) | {"workspace.delete.permanent"},
        )
        self.assertFalse(
            {
                "chat.ask",
                "chat.history",
                "knowledge.read",
                "knowledge.download",
                "workspace.invites.manage",
                "workspace.members.manage",
            }
            & set(archived_owner["capabilities"])
        )


class OrganizationMembershipEffectivenessTest(SimpleTestCase):
    def test_governance_membership_has_explicit_active_and_expiry_state(self):
        field_names = {field.name for field in OrganizationMembership._meta.fields}
        self.assertIn("is_active", field_names)
        self.assertIn("expires_at", field_names)

        active = OrganizationMembership(is_active=True)
        inactive = OrganizationMembership(is_active=False)
        expired = OrganizationMembership(
            is_active=True,
            expires_at=timezone.now() - timezone.timedelta(seconds=1),
        )

        self.assertTrue(active.is_effective)
        self.assertFalse(inactive.is_effective)
        self.assertFalse(expired.is_effective)
