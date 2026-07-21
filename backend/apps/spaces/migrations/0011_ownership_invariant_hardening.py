from django.db import migrations, models
from django.db.models import F, Q


ASSERT_FUNCTION = "spaces_assert_canonical_owner_mirror"
TRIGGER_FUNCTION = "spaces_check_canonical_owner_mirror"


def install_postgresql_owner_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    schema_editor.execute(
        f"""
        CREATE OR REPLACE FUNCTION {ASSERT_FUNCTION}(p_space uuid)
        RETURNS void
        LANGUAGE plpgsql
        AS $$
        DECLARE
            canonical_owner uuid;
            owner_is_active boolean;
            mirror_count integer;
            canonical_mirror_count integer;
        BEGIN
            SELECT owner_id
              INTO canonical_owner
              FROM spaces_knowledgespace
             WHERE id = p_space;
            IF NOT FOUND THEN
                RETURN;
            END IF;

            SELECT is_active
              INTO owner_is_active
              FROM users_user
             WHERE id = canonical_owner;

            SELECT COUNT(*),
                   COUNT(*) FILTER (WHERE user_id = canonical_owner)
              INTO mirror_count, canonical_mirror_count
              FROM spaces_spacemembership
             WHERE space_id = p_space
               AND role = 'owner'
               AND status = 'active'
               AND expires_at IS NULL;

            IF canonical_owner IS NULL
               OR owner_is_active IS DISTINCT FROM TRUE
               OR mirror_count <> 1
               OR canonical_mirror_count <> 1 THEN
                RAISE EXCEPTION USING ERRCODE = '23514',
                    MESSAGE = 'canonical owner mirror invariant failed for space ' || p_space::text;
            END IF;
        END;
        $$;
        """
    )
    schema_editor.execute(
        f"""
        CREATE OR REPLACE FUNCTION {TRIGGER_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            affected_space uuid;
            affected_user uuid;
        BEGIN
            IF TG_TABLE_NAME = 'spaces_knowledgespace' THEN
                IF TG_OP <> 'DELETE' THEN
                    PERFORM {ASSERT_FUNCTION}(NEW.id);
                END IF;
                IF TG_OP <> 'INSERT' THEN
                    PERFORM {ASSERT_FUNCTION}(OLD.id);
                END IF;
            ELSIF TG_TABLE_NAME = 'spaces_spacemembership' THEN
                IF TG_OP <> 'DELETE' THEN
                    PERFORM {ASSERT_FUNCTION}(NEW.space_id);
                END IF;
                IF TG_OP <> 'INSERT' THEN
                    PERFORM {ASSERT_FUNCTION}(OLD.space_id);
                END IF;
            ELSE
                affected_user := COALESCE(NEW.id, OLD.id);
                FOR affected_space IN
                    SELECT id FROM spaces_knowledgespace WHERE owner_id = affected_user
                    UNION
                    SELECT space_id FROM spaces_spacemembership WHERE user_id = affected_user
                LOOP
                    PERFORM {ASSERT_FUNCTION}(affected_space);
                END LOOP;
            END IF;
            RETURN NULL;
        END;
        $$;
        """
    )
    schema_editor.execute(
        f"""
        CREATE CONSTRAINT TRIGGER spaces_owner_space_guard
        AFTER INSERT OR UPDATE OR DELETE ON spaces_knowledgespace
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION {TRIGGER_FUNCTION}();
        """
    )
    schema_editor.execute(
        f"""
        CREATE CONSTRAINT TRIGGER spaces_owner_membership_guard
        AFTER INSERT OR UPDATE OR DELETE ON spaces_spacemembership
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION {TRIGGER_FUNCTION}();
        """
    )
    schema_editor.execute(
        f"""
        CREATE CONSTRAINT TRIGGER spaces_owner_user_guard
        AFTER UPDATE ON users_user
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION {TRIGGER_FUNCTION}();
        """
    )


def remove_postgresql_owner_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP TRIGGER IF EXISTS spaces_owner_user_guard ON users_user;")
    schema_editor.execute(
        "DROP TRIGGER IF EXISTS spaces_owner_membership_guard ON spaces_spacemembership;"
    )
    schema_editor.execute(
        "DROP TRIGGER IF EXISTS spaces_owner_space_guard ON spaces_knowledgespace;"
    )
    schema_editor.execute(f"DROP FUNCTION IF EXISTS {TRIGGER_FUNCTION}();")
    schema_editor.execute(f"DROP FUNCTION IF EXISTS {ASSERT_FUNCTION}(uuid);")


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0004_user_offboarding_metadata"),
        ("spaces", "0010_ownership_continuity_stage_c"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="spacemembership",
            constraint=models.UniqueConstraint(
                fields=("space",),
                condition=Q(role="owner", status="active"),
                name="spaces_one_active_owner_membership",
            ),
        ),
        migrations.AddConstraint(
            model_name="spacemembership",
            constraint=models.CheckConstraint(
                check=(
                    ~Q(role="owner")
                    | (Q(status="active") & Q(expires_at__isnull=True))
                ),
                name="spaces_owner_membership_effective",
            ),
        ),
        migrations.AddConstraint(
            model_name="ownershiptransfer",
            constraint=models.CheckConstraint(
                check=~Q(requested_by=F("to_owner")),
                name="spaces_owner_transfer_actor_target",
            ),
        ),
        migrations.RunPython(
            install_postgresql_owner_triggers,
            remove_postgresql_owner_triggers,
        ),
    ]
