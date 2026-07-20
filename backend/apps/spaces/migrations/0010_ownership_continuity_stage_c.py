# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_canonical_owners(apps, schema_editor):
    """Backfill only an unambiguous, eligible, non-expiring owner mirror."""

    KnowledgeSpace = apps.get_model("spaces", "KnowledgeSpace")
    SpaceMembership = apps.get_model("spaces", "SpaceMembership")
    alias = schema_editor.connection.alias
    blocked = []

    for space in KnowledgeSpace.objects.using(alias).all().order_by("pk").iterator():
        eligible_owner_ids = list(
            SpaceMembership.objects.using(alias)
            .filter(
                space_id=space.pk,
                role="owner",
                status="active",
                expires_at__isnull=True,
                user__is_active=True,
            )
            .order_by("user_id")
            .values_list("user_id", flat=True)
        )
        if len(eligible_owner_ids) != 1:
            blocked.append(f"{space.pk}:{len(eligible_owner_ids)}")
            continue
        owner_id = eligible_owner_ids[0]
        if space.owner_id is not None and space.owner_id != owner_id:
            blocked.append(f"{space.pk}:canonical_mismatch")
            continue
        if space.owner_id is None:
            KnowledgeSpace.objects.using(alias).filter(pk=space.pk).update(owner_id=owner_id)

    if blocked:
        raise RuntimeError(
            "ownership_continuity_stage_c_blocked:" + ",".join(blocked)
        )


class Migration(migrations.Migration):
    # atomic = False: when this migration runs against a database that already
    # holds spaces_knowledgespace rows (e.g. the ownership stage_c
    # migration-contract test, which seeds user/space/membership rows before
    # migrating forward), the DEFERRABLE INITIALLY DEFERRED FK on
    # spaces_knowledgespace.owner queues a pending trigger event during the
    # backfill_canonical_owners UPDATE. Within one atomic transaction that
    # pending event blocks the subsequent AlterField (ALTER TABLE) with
    # "cannot ALTER TABLE spaces_knowledgespace because it has pending trigger
    # events" -> PostgreSQL rejects the DDL and the test stalls at the migrate
    # call. Running each operation in its own transaction lets the deferred FK
    # fire at the backfill commit before the next ALTER. On a fresh DB (normal
    # `migrate`) there are no pre-existing rows, so the issue does not arise
    # (mirrors 0012, 0014, 0015 atomic = False).
    atomic = False

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("users", "0004_user_offboarding_metadata"),
        ("spaces", "0009_ownership_continuity_stage_a"),
    ]

    operations = [
        migrations.RunPython(backfill_canonical_owners, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="knowledgespace",
            name="owner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="owned_spaces",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
