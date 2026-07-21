"""Audit and safely repair Stage-A canonical ownership data."""

import csv
import io
import json

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db.migrations.recorder import MigrationRecorder

from apps.spaces.models import KnowledgeSpace, SpaceMembership
from apps.spaces.ownership import effective_space_membership


class Command(BaseCommand):
    help = "Report ownership-continuity anomalies; optionally backfill only unambiguous legacy owners."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Backfill only spaces with exactly one effective legacy owner.")
        parser.add_argument("--format", choices=("json", "csv"), default="json")

    def handle(self, *args, **options):
        applied = set(MigrationRecorder.Migration.objects.values_list("app", "name"))
        required_migrations = {("spaces", "0009_ownership_continuity_stage_a"), ("users", "0004_user_offboarding_metadata")}
        missing = required_migrations - applied
        if missing:
            rendered = ", ".join(f"{app}.{name.split('_', 1)[0]}" for app, name in sorted(missing))
            raise CommandError(
                f"Ownership-continuity migrations are not applied; apply {rendered} before auditing."
            )
        report = {
            "backfilled_space_ids": [],
            "zero_owner_space_ids": [],
            "multiple_owner_space_ids": [],
            "inactive_canonical_owner_space_ids": [],
        }
        spaces = KnowledgeSpace.objects.filter(
            status__in=("active", "archived")
        ).select_related("owner")
        for space in spaces.order_by("id"):
            owners = [
                membership
                for membership in SpaceMembership.objects.select_related("user").filter(
                    space=space, role=SpaceMembership.ROLE_OWNER
                )
                if effective_space_membership(membership)
            ]
            if space.owner_id is None:
                if len(owners) == 1:
                    if options["apply"]:
                        space.owner_id = owners[0].user_id
                        space.save(update_fields=["owner", "updated_at"])
                        report["backfilled_space_ids"].append(str(space.id))
                elif not owners:
                    report["zero_owner_space_ids"].append(str(space.id))
                else:
                    report["multiple_owner_space_ids"].append(str(space.id))
            elif not any(membership.user_id == space.owner_id for membership in owners):
                report["inactive_canonical_owner_space_ids"].append(str(space.id))
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, sort_keys=True))
            return
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(("category", "space_id"))
        for category, ids in report.items():
            for space_id in ids:
                writer.writerow((category, space_id))
        self.stdout.write(output.getvalue().rstrip())
