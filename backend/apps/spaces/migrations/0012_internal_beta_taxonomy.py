import uuid

from django.conf import settings
from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


CLASSIFICATION_LEGACY = "legacy_unclassified"
TAXONOMY_ASSERT_FUNCTION = "spaces_assert_taxonomy_consistency"
TAXONOMY_TRIGGER_FUNCTION = "spaces_check_taxonomy_consistency"


def mark_historical_spaces_legacy(apps, schema_editor):
    """Never infer taxonomy from names/tags during the additive migration."""

    KnowledgeSpace = apps.get_model("spaces", "KnowledgeSpace")
    KnowledgeSpace.objects.all().update(
        classification_state=CLASSIFICATION_LEGACY,
        work_group=None,
    )


def install_postgresql_taxonomy_triggers(apps, schema_editor):
    """Install deferred cross-table checks only on PostgreSQL.

    SQLite intentionally receives no trigger emulation; its model checks cover
    local shape while the acceptance evidence for cross-table consistency is
    the PostgreSQL suite.
    """

    if schema_editor.connection.vendor != "postgresql":
        return

    schema_editor.execute(
        f"""
        CREATE OR REPLACE FUNCTION {TAXONOMY_ASSERT_FUNCTION}(p_space uuid)
        RETURNS void
        LANGUAGE plpgsql
        AS $$
        DECLARE
            v_organization uuid;
            v_business_line uuid;
            v_work_group uuid;
            v_state text;
            v_parent_organization uuid;
            v_group_business_line uuid;
        BEGIN
            SELECT organization_id, business_line_id, work_group_id,
                   classification_state
              INTO v_organization, v_business_line, v_work_group, v_state
              FROM spaces_knowledgespace
             WHERE id = p_space;
            IF NOT FOUND THEN
                RETURN;
            END IF;

            IF v_business_line IS NOT NULL THEN
                SELECT organization_id
                  INTO v_parent_organization
                  FROM spaces_businessline
                 WHERE id = v_business_line;
                IF NOT FOUND OR v_parent_organization IS DISTINCT FROM v_organization THEN
                    RAISE EXCEPTION USING ERRCODE = '23514',
                        MESSAGE = 'workspace business line organization mismatch for space ' || p_space::text;
                END IF;
            END IF;

            IF v_work_group IS NOT NULL THEN
                SELECT business_line_id
                  INTO v_group_business_line
                  FROM spaces_workgroup
                 WHERE id = v_work_group;
                IF NOT FOUND
                   OR v_business_line IS NULL
                   OR v_group_business_line IS DISTINCT FROM v_business_line THEN
                    RAISE EXCEPTION USING ERRCODE = '23514',
                        MESSAGE = 'workspace work group business line mismatch for space ' || p_space::text;
                END IF;
            END IF;

            IF EXISTS (
                SELECT 1
                  FROM spaces_knowledgespace_office_locations link
                  JOIN spaces_officelocation location
                    ON location.id = link.office_location_id
                 WHERE link.space_id = p_space
                   AND location.organization_id IS DISTINCT FROM v_organization
            ) THEN
                RAISE EXCEPTION USING ERRCODE = '23514',
                    MESSAGE = 'workspace office location organization mismatch for space ' || p_space::text;
            END IF;

            IF v_state = 'complete'
               AND (v_business_line IS NULL OR v_work_group IS NULL
                    OR NOT EXISTS (
                        SELECT 1
                          FROM spaces_knowledgespace_office_locations link
                         WHERE link.space_id = p_space
                    )) THEN
                RAISE EXCEPTION USING ERRCODE = '23514',
                    MESSAGE = 'complete workspace classification is incomplete for space ' || p_space::text;
            END IF;
        END;
        $$;
        """
    )
    schema_editor.execute(
        f"""
        CREATE OR REPLACE FUNCTION {TAXONOMY_TRIGGER_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            v_id uuid;
            v_space uuid;
        BEGIN
            IF TG_TABLE_NAME = 'spaces_knowledgespace' THEN
                IF TG_OP <> 'DELETE' THEN
                    PERFORM {TAXONOMY_ASSERT_FUNCTION}(NEW.id);
                END IF;
                IF TG_OP <> 'INSERT' THEN
                    PERFORM {TAXONOMY_ASSERT_FUNCTION}(OLD.id);
                END IF;
            ELSIF TG_TABLE_NAME = 'spaces_knowledgespace_office_locations' THEN
                IF TG_OP <> 'DELETE' THEN
                    PERFORM {TAXONOMY_ASSERT_FUNCTION}(NEW.space_id);
                END IF;
                IF TG_OP <> 'INSERT' THEN
                    PERFORM {TAXONOMY_ASSERT_FUNCTION}(OLD.space_id);
                END IF;
            ELSIF TG_TABLE_NAME = 'spaces_workgroup' THEN
                v_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END;
                FOR v_space IN
                    SELECT id
                      FROM spaces_knowledgespace
                     WHERE work_group_id = v_id
                LOOP
                    PERFORM {TAXONOMY_ASSERT_FUNCTION}(v_space);
                END LOOP;
            ELSIF TG_TABLE_NAME = 'spaces_businessline' THEN
                v_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END;
                FOR v_space IN
                    SELECT id
                      FROM spaces_knowledgespace
                     WHERE business_line_id = v_id
                        OR work_group_id IN (
                            SELECT id FROM spaces_workgroup
                             WHERE business_line_id = v_id
                        )
                LOOP
                    PERFORM {TAXONOMY_ASSERT_FUNCTION}(v_space);
                END LOOP;
            ELSIF TG_TABLE_NAME = 'spaces_officelocation' THEN
                v_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END;
                FOR v_space IN
                    SELECT space_id
                      FROM spaces_knowledgespace_office_locations
                     WHERE office_location_id = v_id
                LOOP
                    PERFORM {TAXONOMY_ASSERT_FUNCTION}(v_space);
                END LOOP;
            END IF;

            RETURN NULL;
        END;
        $$;
        """
    )
    for table_name, trigger_name in (
        ("spaces_knowledgespace", "spaces_taxonomy_space_guard"),
        ("spaces_businessline", "spaces_taxonomy_business_line_guard"),
        ("spaces_workgroup", "spaces_taxonomy_work_group_guard"),
        ("spaces_officelocation", "spaces_taxonomy_office_guard"),
        (
            "spaces_knowledgespace_office_locations",
            "spaces_taxonomy_space_office_guard",
        ),
    ):
        schema_editor.execute(
            f"""
            CREATE CONSTRAINT TRIGGER {trigger_name}
            AFTER INSERT OR UPDATE OR DELETE ON {table_name}
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION {TAXONOMY_TRIGGER_FUNCTION}();
            """
        )


def remove_postgresql_taxonomy_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table_name, trigger_name in (
        ("spaces_knowledgespace_office_locations", "spaces_taxonomy_space_office_guard"),
        ("spaces_officelocation", "spaces_taxonomy_office_guard"),
        ("spaces_workgroup", "spaces_taxonomy_work_group_guard"),
        ("spaces_businessline", "spaces_taxonomy_business_line_guard"),
        ("spaces_knowledgespace", "spaces_taxonomy_space_guard"),
    ):
        schema_editor.execute(
            f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name};"
        )
    schema_editor.execute(f"DROP FUNCTION IF EXISTS {TAXONOMY_TRIGGER_FUNCTION}();")
    schema_editor.execute(
        f"DROP FUNCTION IF EXISTS {TAXONOMY_ASSERT_FUNCTION}(uuid);"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("spaces", "0011_ownership_invariant_hardening"),
        ("scenario_templates", "0006_versioned_clone_contract"),
    ]

    operations = [
        migrations.CreateModel(
            name="OfficeLocation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("normalized_code", models.CharField(max_length=120)),
                ("display_name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                ("active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("version", models.PositiveBigIntegerField(default=1)),
                ("locale", models.CharField(blank=True, default="", max_length=32)),
                ("time_zone", models.CharField(blank=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="office_locations",
                        to="spaces.organization",
                    ),
                ),
            ],
            options={
                "db_table": "spaces_officelocation",
                "ordering": ["sort_order", "display_name", "id"],
                "indexes": [
                    models.Index(
                        fields=["organization", "active", "sort_order"],
                        name="spaces_office_org_active_order",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization", "normalized_code"),
                        name="spaces_office_org_normalized_code",
                    ),
                    models.CheckConstraint(
                        check=~Q(normalized_code=""),
                        name="spaces_office_code_nonempty",
                    ),
                    models.CheckConstraint(
                        check=~Q(display_name=""),
                        name="spaces_office_name_nonempty",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="WorkGroup",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("normalized_code", models.CharField(max_length=120)),
                ("display_name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                ("active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("version", models.PositiveBigIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "business_line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="work_groups",
                        to="spaces.businessline",
                    ),
                ),
            ],
            options={
                "db_table": "spaces_workgroup",
                "ordering": ["sort_order", "display_name", "id"],
                "indexes": [
                    models.Index(
                        fields=["business_line", "active", "sort_order"],
                        name="spaces_wg_bl_active_order",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("business_line", "normalized_code"),
                        name="spaces_wg_bl_normalized_code",
                    ),
                    models.CheckConstraint(
                        check=~Q(normalized_code=""),
                        name="spaces_wg_code_nonempty",
                    ),
                    models.CheckConstraint(
                        check=~Q(display_name=""),
                        name="spaces_wg_name_nonempty",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="WorkspaceUsageDaily",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("date", models.DateField()),
                ("interaction_count", models.PositiveIntegerField(default=0)),
                ("last_interacted_at", models.DateTimeField(blank=True, null=True)),
                (
                    "space",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="usage_daily",
                        to="spaces.knowledgespace",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workspace_usage_daily",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "spaces_workspaceusagedaily",
                "indexes": [
                    models.Index(fields=["user", "date"], name="spaces_usage_daily_user_date"),
                    models.Index(fields=["space", "date"], name="spaces_usage_daily_space_date"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "space", "date"),
                        name="spaces_usage_daily_user_space_date",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="businessline",
            name="version",
            field=models.PositiveBigIntegerField(default=1),
        ),
        migrations.CreateModel(
            name="WorkspaceUsageSummary",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("interaction_count_30d", models.PositiveIntegerField(default=0)),
                ("last_interacted_at", models.DateTimeField(blank=True, null=True)),
                ("computed_through", models.DateField(blank=True, null=True)),
                (
                    "space",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="usage_summaries",
                        to="spaces.knowledgespace",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workspace_usage_summaries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "spaces_workspaceusagesummary",
                "indexes": [
                    models.Index(
                        fields=["user", "interaction_count_30d", "last_interacted_at"],
                        name="spaces_usage_summary_rank",
                    ),
                    models.Index(fields=["space"], name="spaces_usage_summary_space"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "space"),
                        name="spaces_usage_summary_user_space",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="knowledgespace",
            name="classification_state",
            field=models.CharField(
                choices=[
                    ("complete", "Complete"),
                    ("legacy_unclassified", "Legacy Unclassified"),
                    ("exempt", "Exempt"),
                ],
                default=CLASSIFICATION_LEGACY,
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="knowledgespace",
            name="work_group",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="spaces",
                to="spaces.workgroup",
            ),
        ),
        migrations.CreateModel(
            name="KnowledgeSpaceOfficeLocation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "office_location",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="space_links",
                        to="spaces.officelocation",
                    ),
                ),
                (
                    "space",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="office_location_links",
                        to="spaces.knowledgespace",
                    ),
                ),
            ],
            options={
                "db_table": "spaces_knowledgespace_office_locations",
                "indexes": [
                    models.Index(fields=["office_location", "space"], name="spaces_office_space_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("space", "office_location"),
                        name="spaces_space_office_unique",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="knowledgespace",
            name="office_locations",
            field=models.ManyToManyField(
                blank=True,
                related_name="spaces",
                through="spaces.KnowledgeSpaceOfficeLocation",
                to="spaces.officelocation",
            ),
        ),
        migrations.AddConstraint(
            model_name="knowledgespace",
            constraint=models.CheckConstraint(
                check=Q(
                    classification_state__in=[
                        "complete",
                        "legacy_unclassified",
                        "exempt",
                    ]
                ),
                name="spaces_classification_state_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="knowledgespace",
            constraint=models.CheckConstraint(
                check=(
                    ~Q(classification_state="complete")
                    | (Q(business_line__isnull=False) & Q(work_group__isnull=False))
                ),
                name="spaces_complete_classification_fields",
            ),
        ),
        migrations.AddIndex(
            model_name="knowledgespace",
            index=models.Index(
                fields=["organization", "classification_state"],
                name="spaces_org_class_state",
            ),
        ),
        migrations.AddIndex(
            model_name="knowledgespace",
            index=models.Index(
                fields=["business_line", "classification_state"],
                name="spaces_bl_class_state",
            ),
        ),
        migrations.AddIndex(
            model_name="knowledgespace",
            index=models.Index(fields=["work_group"], name="spaces_work_group_idx"),
        ),
        migrations.RunPython(mark_historical_spaces_legacy, migrations.RunPython.noop),
        migrations.RunPython(
            install_postgresql_taxonomy_triggers,
            remove_postgresql_taxonomy_triggers,
        ),
    ]
