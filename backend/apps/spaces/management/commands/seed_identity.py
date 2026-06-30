# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Seed V7 identity scaffolding — idempotent first-run bootstrap.

Creates:
  - a default Organization;
  - one BusinessLine per Service Line;
  - the 'general' space + per-Service-Line onboarding spaces
    (matching settings.SERVICE_LINE_DEFAULT_SPACE);
  - a Super Admin if none exists (credentials printed once);
  - a first batch of Admin Registration Codes (plaintext printed once).

Run after migrations:  python manage.py seed_identity
Safe to re-run: existing records are skipped.
"""

import os
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.spaces.models import (
    AdminRegistrationCode,
    BusinessLine,
    KnowledgeSpace,
    Organization,
)
from apps.spaces.services import generate_admin_code, hash_code

User = get_user_model()

SERVICE_LINES = [
    ("assurance", "Assurance"),
    ("consulting", "Consulting"),
    ("tax", "Tax"),
    ("strategy_transactions", "Strategy & Transactions"),
    ("core", "Core Business Services"),
]


class Command(BaseCommand):
    help = "Seed V7 identity scaffolding (org, business lines, spaces, super admin, admin codes)."

    def handle(self, *args, **options):
        out = self.stdout
        out.write("Seeding V7 identity scaffolding...\n")

        # 1. Organization
        org, created = Organization.objects.get_or_create(
            slug="default", defaults={"name": "KnowPilot Demo Org"}
        )
        out.write(f"  {'+' if created else '='} Organization: {org.name}")

        # 2. Business lines
        bls = {}
        for code, name in SERVICE_LINES:
            bl, created = BusinessLine.objects.get_or_create(
                organization=org, code=code, defaults={"name": name}
            )
            bls[code] = bl
            out.write(f"    {'+' if created else '='} BusinessLine: {name}")

        # 3. Spaces — general + per Service Line onboarding
        general, created = KnowledgeSpace.objects.get_or_create(
            code="general",
            defaults={
                "organization": org, "name": "General Knowledge",
                "visibility": "organization", "description": "Default shared space.",
            },
        )
        out.write(f"  {'+' if created else '='} Space: general")

        space_map = getattr(settings, "SERVICE_LINE_DEFAULT_SPACE", {}) or {}
        for sl_code, space_code in space_map.items():
            if space_code == "general":
                continue
            bl = bls.get(sl_code)
            _, created = KnowledgeSpace.objects.get_or_create(
                code=space_code,
                defaults={
                    "organization": org,
                    "business_line": bl,
                    "name": f"{bl.name if bl else sl_code.title()} Onboarding",
                    "visibility": "business_line",
                    "description": f"Onboarding space for {bl.name if bl else sl_code}.",
                },
            )
            out.write(f"    {'+' if created else '='} Space: {space_code}")

        # 4. Super Admin
        if not User.objects.filter(is_superuser=True).exists():
            email = os.environ.get("SEED_SUPERUSER_EMAIL", "admin@knowpilot.local")
            password = os.environ.get("SEED_SUPERUSER_PASSWORD") or secrets.token_urlsafe(12)
            su = User(email=email, username=email, is_staff=True, is_superuser=True)
            su.set_password(password)
            su.save()
            out.write(self.style.WARNING(
                f"\n  *** Created Super Admin: {email}  /  password: {password}"
                f"\n    (shown once - store it now)\n"
            ))
        else:
            out.write("  = Super Admin already exists (skipped)")

        super_user = User.objects.filter(is_superuser=True).first()

        # 5. First batch of admin registration codes (printed once)
        if not AdminRegistrationCode.objects.exists():
            out.write(self.style.WARNING("\n  Admin registration codes (shown once):"))
            org_raw = generate_admin_code("ORG")
            AdminRegistrationCode.objects.create(
                code_hash=hash_code(org_raw), code_prefix=org_raw[:8],
                grants_role="org_admin", organization=org, created_by=super_user,
            )
            out.write(self.style.WARNING(f"    org_admin       : {org_raw}"))
            for code, bl in bls.items():
                ba_raw = generate_admin_code("BIZ")
                AdminRegistrationCode.objects.create(
                    code_hash=hash_code(ba_raw), code_prefix=ba_raw[:8],
                    grants_role="business_admin", organization=org,
                    business_line=bl, created_by=super_user,
                )
                out.write(self.style.WARNING(f"    business_admin/{code:<22}: {ba_raw}"))
        else:
            out.write("  = Admin registration codes already exist (skipped)")

        # 6. Backfill: legacy is_hr_admin users -> knowledge_admin of 'general'
        #    (V7 deprecation of the global hr flag — see spec §10). Best-effort.
        from apps.spaces.models import SpaceMembership
        backfilled = 0
        for u in User.objects.filter(is_hr_admin=True, is_superuser=False):
            _, created = SpaceMembership.objects.get_or_create(
                space=general, user=u,
                defaults={"role": SpaceMembership.ROLE_KNOWLEDGE_ADMIN, "status": "active"},
            )
            if created:
                backfilled += 1
        if backfilled:
            out.write(f"  + Backfilled {backfilled} is_hr_admin user(s) as knowledge_admin of 'general'")

        out.write(self.style.SUCCESS("\n[OK] seed_identity complete."))
