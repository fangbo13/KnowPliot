# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Pure contracts for the scoped capability resolver."""

from uuid import UUID

from django.test import SimpleTestCase
from django.utils import timezone

from apps.spaces.models import OrganizationMembership

try:
    from apps.rbac.capabilities import (
        BUSINESS_ADMIN_CAPABILITIES,
        ORGANIZATION_ADMIN_CAPABILITIES,
        PLATFORM_CAPABILITIES,
        SPACE_ROLE_CAPABILITIES,
        CapabilityGrantSnapshot,
        build_capability_payload,
    )
except ImportError:  # RED: the capability service does not exist yet.
    BUSINESS_ADMIN_CAPABILITIES = None
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
}


class CapabilityMatrixTest(SimpleTestCase):
    def test_space_role_matrix_is_locked_and_least_privilege(self):
        self.assertIsNotNone(SPACE_ROLE_CAPABILITIES)
        self.assertEqual(SPACE_ROLE_CAPABILITIES["guest"], frozenset({"chat.ask"}))
        self.assertEqual(SPACE_ROLE_CAPABILITIES["member"], frozenset(MEMBER))
        self.assertEqual(
            SPACE_ROLE_CAPABILITIES["reviewer"],
            frozenset(BASE_CHAT | {"workspace.manage", "quality.read", "quality.review", "audit.read"}),
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
                    "platform.metrics.read",
                    "platform.models.manage",
                    "platform.organizations.manage",
                    "platform.roles.manage",
                    "platform.users.manage",
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
                    "governance.templates.manage",
                    "governance.users.manage",
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
                    "governance.templates.manage",
                    "governance.users.manage",
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
