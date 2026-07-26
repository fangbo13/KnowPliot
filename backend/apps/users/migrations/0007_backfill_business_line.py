# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Knowledge iteration spec §1.2: backfill User.business_line FK from the
legacy service_line CharField. The five service_line codes match the
BusinessLine codes seeded by seed_taxonomy.py exactly."""

from django.db import migrations


def backfill_business_line(apps, schema_editor):
    User = apps.get_model("users", "User")
    BusinessLine = apps.get_model("spaces", "BusinessLine")

    # Map service_line code -> first matching BusinessLine (single-org deploys
    # have exactly one line per code; multi-org ambiguity resolves to oldest).
    lines_by_code = {}
    for line in BusinessLine.objects.order_by("created_at" if hasattr(BusinessLine, "created_at") else "id"):
        lines_by_code.setdefault(line.code, line)

    for code, line in lines_by_code.items():
        User.objects.filter(
            service_line=code, business_line__isnull=True
        ).update(business_line=line)


def unbackfill(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.update(business_line=None)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0006_user_business_line"),
    ]

    operations = [
        migrations.RunPython(backfill_business_line, unbackfill),
    ]
