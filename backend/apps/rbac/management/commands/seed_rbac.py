"""Seed RBAC data — V4.0 dual-track permission system.

Creates 2 Roles (hr, admin), 35 Permission codenames, and RolePermission
mappings. Run after migrations:

    python manage.py seed_rbac

Safe to re-run: skips existing records.
"""

from django.core.management.base import BaseCommand
from apps.rbac.models import Role, Permission, RolePermission


# ── 35 Codename Definitions ──────────────────────────────────────────

PERMISSIONS_DATA = [
    # Knowledge Base Domain (16 codenames) — HR + Admin
    ("document.create", "document", "create", "Create/Upload documents"),
    ("document.read", "document", "read", "View document list and details"),
    ("document.update", "document", "update", "Update document metadata"),
    ("document.delete", "document", "delete", "Delete documents"),
    ("document.reindex", "document", "reindex", "Trigger document re-indexing"),
    ("document.read_chunks", "document", "read_chunks", "View document chunk details"),
    ("document.create_version", "document", "create_version", "Create document versions"),
    ("document.set_effective_date", "document", "set_effective_date", "Set effective date on documents"),
    ("category.create", "category", "create", "Create document categories"),
    ("category.read", "category", "read", "View document categories"),
    ("category.update", "category", "update", "Update document categories"),
    ("category.delete", "category", "delete", "Delete document categories"),
    ("template.create", "template", "create", "Create answer templates"),
    ("template.read", "template", "read", "View answer templates"),
    ("template.update", "template", "update", "Update answer templates"),
    ("template.delete", "template", "delete", "Delete answer templates"),

    # Workflow Domain (6 codenames)
    ("workflow.create", "workflow", "create", "Create onboarding workflow templates"),
    ("workflow.update", "workflow", "update", "Update onboarding workflow templates"),
    ("workflow.read", "workflow", "read", "View onboarding workflow templates"),
    ("workflow.assign", "workflow", "assign", "Assign workflow to individual user"),
    ("workflow.bulk_assign", "workflow", "bulk_assign", "Bulk assign workflow to users"),
    ("workflow.read_all", "workflow", "read_all", "View all workflow assignments across users"),

    # User Management Domain (5 codenames) — Admin only
    ("user.read", "user", "read", "View user list and profiles"),
    ("user.create", "user", "create", "Create new user accounts"),
    ("user.update", "user", "update", "Edit user profiles and settings"),
    ("user.deactivate", "user", "deactivate", "Deactivate user accounts"),
    ("user.assign_role", "user", "assign_role", "Assign/revoke RBAC roles to users"),

    # System Config Domain (3 codenames) — Admin only
    ("config.manage_service_lines", "config", "manage_service_lines", "Manage ServiceLine configuration"),
    ("config.manage_office_locations", "config", "manage_office_locations", "Manage OfficeLocation configuration"),
    ("config.manage_parameters", "config", "manage_parameters", "Manage global system parameters"),

    # Audit & Monitoring Domain (5 codenames)
    ("audit.view_content", "audit", "view_content", "View content-domain audit logs"),
    ("audit.view_system", "audit", "view_system", "View system-domain audit logs"),
    ("audit.view_role_changes", "audit", "view_role_changes", "View role change audit logs"),
    ("audit.export", "audit", "export", "Export audit logs to CSV"),
    ("health.view", "health", "view", "View system health dashboard"),
]

# HR role gets 22 codenames (content domain)
HR_CODENAMES = [
    "document.create", "document.read", "document.update", "document.delete",
    "document.reindex", "document.read_chunks", "document.create_version", "document.set_effective_date",
    "category.create", "category.read", "category.update", "category.delete",
    "template.create", "template.read", "template.update", "template.delete",
    "workflow.create", "workflow.update", "workflow.read", "workflow.assign",
    "audit.view_content",
]

# Admin role gets all 35 codenames
ADMIN_CODENAMES = [p[0] for p in PERMISSIONS_DATA]


class Command(BaseCommand):
    help = "Seed RBAC roles, permissions, and role-permission mappings for V4.0 dual-track system"

    def handle(self, *args, **options):
        self.stdout.write("Seeding RBAC data...\n")

        # ── Create Permissions ──
        perm_count = 0
        for codename, resource, action, label in PERMISSIONS_DATA:
            try:
                perm = Permission.objects.get(codename=codename)
            except Permission.DoesNotExist:
                perm = Permission.objects.create(
                    codename=codename,
                    resource=resource,
                    action=action,
                    label=label,
                )
                perm_count += 1
                self.stdout.write(f"  ✓ Permission: {codename}")

        self.stdout.write(f"\n  Created {perm_count} new permissions (total: {Permission.objects.count()})\n")

        # ── Create Roles ──
        hr_role, _ = Role.objects.get_or_create(
            name="hr",
            defaults={"label": "HR Content Manager", "scope": "content"},
        )
        admin_role, _ = Role.objects.get_or_create(
            name="admin",
            defaults={"label": "System Administrator", "scope": "system"},
        )

        self.stdout.write(f"  Roles: hr={hr_role.id}, admin={admin_role.id}\n")

        # ── Assign HR permissions (22 codenames) ──
        hr_perm_count = 0
        for codename in HR_CODENAMES:
            perm = Permission.objects.get(codename=codename)
            try:
                RolePermission.objects.get(role=hr_role, permission=perm)
            except RolePermission.DoesNotExist:
                RolePermission.objects.create(role=hr_role, permission=perm)
                hr_perm_count += 1

        self.stdout.write(f"  HR role: {hr_perm_count} new permission mappings (total: {RolePermission.objects.filter(role=hr_role).count()})\n")

        # ── Assign Admin permissions (35 codenames) ──
        admin_perm_count = 0
        for codename in ADMIN_CODENAMES:
            perm = Permission.objects.get(codename=codename)
            try:
                RolePermission.objects.get(role=admin_role, permission=perm)
            except RolePermission.DoesNotExist:
                RolePermission.objects.create(role=admin_role, permission=perm)
                admin_perm_count += 1

        self.stdout.write(f"  Admin role: {admin_perm_count} new permission mappings (total: {RolePermission.objects.filter(role=admin_role).count()})\n")

        self.stdout.write(self.style.SUCCESS(
            f"\n✓ RBAC seed complete: {Permission.objects.count()} permissions, "
            f"HR={RolePermission.objects.filter(role=hr_role).count()} perms, "
            f"Admin={RolePermission.objects.filter(role=admin_role).count()} perms"
        ))
