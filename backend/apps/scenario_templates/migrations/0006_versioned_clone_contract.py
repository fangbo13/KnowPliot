import hashlib
import json
import unicodedata

from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


COMPONENT_KEYS = (
    "category_tree",
    "scenario_definitions",
    "quality_rubric",
    "workspace_defaults",
    "model_policy_refs",
)
FORBIDDEN_KEYS = {
    "document", "documents", "document_ids", "file", "files", "file_url",
    "storage_path", "chunks", "chunk_ids", "indexes", "index_ids", "chat",
    "chats", "messages", "history", "members", "memberships", "owner",
    "ownership", "invitations", "access_codes", "audit", "audit_history",
    "secret", "secrets", "credentials", "api_credentials", "shares", "tasks",
    "task_ids", "retention_holds", "holds",
}


def _assert_no_reserved_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in FORBIDDEN_KEYS:
                raise RuntimeError(f"excluded component key {key!r}")
            _assert_no_reserved_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_reserved_keys(nested)


def _normalize_json_strings(value):
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_normalize_json_strings(item) for item in value]
    if isinstance(value, dict):
        normalized = {}
        for key, nested in value.items():
            normalized_key = unicodedata.normalize("NFC", str(key))
            if normalized_key in normalized:
                raise RuntimeError("Unicode-normalized component keys collide")
            normalized[normalized_key] = _normalize_json_strings(nested)
        return normalized
    return value


def _components(snapshot):
    source = snapshot if isinstance(snapshot, dict) else {}
    if (
        source.get("schema_version") == 1
        and set(source) == {"schema_version", "components"}
        and isinstance(source.get("components"), dict)
        and set(source["components"]) == set(COMPONENT_KEYS)
    ):
        return {key: source["components"][key] for key in COMPONENT_KEYS}

    category_tree = []
    if source.get("category"):
        category_tree.append({"category_id": str(source["category"])})
    return {
        "category_tree": category_tree,
        "scenario_definitions": [
            {
                "scenario_type": source.get("scenario_type", "onboarding"),
                "prompt_policy": source.get("prompt_policy") or {},
                "quick_questions": source.get("quick_questions") or [],
            }
        ],
        "quality_rubric": {},
        "workspace_defaults": {
            "default_language": source.get("default_language", "en"),
            "default_visibility": source.get("default_visibility", "private"),
            "retrieval_policy": source.get("retrieval_policy") or {},
            "classification_tags": source.get("tags") or [],
        },
        "model_policy_refs": [],
    }


def _snapshot(value):
    components = _normalize_json_strings(_components(value))
    expected_types = {
        "category_tree": list,
        "scenario_definitions": list,
        "quality_rubric": dict,
        "workspace_defaults": dict,
        "model_policy_refs": list,
    }
    for key, expected in expected_types.items():
        if not isinstance(components[key], expected):
            raise RuntimeError(f"component {key!r} has an invalid shape")
    _assert_no_reserved_keys(components)
    return {"schema_version": 1, "components": components}


def _hash(value):
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def backfill_versioned_contract(apps, schema_editor):
    Template = apps.get_model("scenario_templates", "ScenarioTemplate")
    Revision = apps.get_model("scenario_templates", "ScenarioTemplateRevision")
    Application = apps.get_model("scenario_templates", "ScenarioTemplateApplication")
    now = timezone.now()

    for template in Template.objects.order_by("pk").iterator():
        revisions = list(Revision.objects.filter(template_id=template.pk).order_by("version", "pk"))
        if not revisions:
            legacy = {
                "category": str(template.category_id) if template.category_id else None,
                "tags": list(template.tags.order_by("slug").values_list("slug", flat=True)),
                "scenario_type": template.scenario_type,
                "prompt_policy": template.prompt_policy,
                "quick_questions": template.quick_questions,
                "default_language": template.default_language,
                "default_visibility": template.default_visibility,
                "retrieval_policy": template.retrieval_policy,
            }
            normalized = _snapshot(legacy)
            revision = Revision.objects.create(
                template_id=template.pk,
                version=1,
                snapshot=normalized,
                snapshot_hash=_hash(normalized),
                published_at=now,
                change_note="v3 normalized backfill",
                created_by_id=template.created_by_id,
            )
            revisions = [revision]
        else:
            for revision in revisions:
                try:
                    normalized = _snapshot(revision.snapshot)
                except RuntimeError as exc:
                    raise RuntimeError(
                        f"ScenarioTemplateRevision {revision.pk} cannot be normalized: {exc}"
                    ) from exc
                revision.snapshot = normalized
                revision.snapshot_hash = _hash(normalized)
                revision.published_at = revision.created_at or now
                revision.save(
                    update_fields=("snapshot", "snapshot_hash", "published_at")
                )

        latest = revisions[-1]
        Template.objects.filter(pk=template.pk).update(current_revision_id=latest.pk)

    for application in Application.objects.select_related("template").order_by("pk").iterator():
        revisions = list(
            Revision.objects.filter(template_id=application.template_id).order_by("version", "pk")
        )
        by_version = {row.version: row for row in revisions}
        by_hash = {row.snapshot_hash: row for row in revisions}
        snapshot = application.template_snapshot if isinstance(application.template_snapshot, dict) else {}
        explicit_version = snapshot.get("template_version", snapshot.get("latest_version", snapshot.get("revision")))
        explicit_hash = snapshot.get("snapshot_hash")
        match = None
        try:
            if explicit_version is not None:
                match = by_version.get(int(explicit_version))
        except (TypeError, ValueError):
            match = None
        if match is None and isinstance(explicit_hash, str):
            match = by_hash.get(explicit_hash)
        if match is None and len(revisions) == 1:
            match = revisions[0]
        Application.objects.filter(pk=application.pk).update(
            template_revision_id=match.pk if match else None,
            legacy_revision_unknown=match is None,
        )


def install_published_revision_guard(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        """
        CREATE OR REPLACE FUNCTION scenario_templates_guard_published_revision()
        RETURNS trigger AS $$
        BEGIN
            IF OLD.published_at IS NOT NULL THEN
                RAISE EXCEPTION 'published scenario template revisions are immutable'
                    USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS scenario_templates_published_revision_guard
            ON scenario_templates_revision;
        CREATE TRIGGER scenario_templates_published_revision_guard
            BEFORE UPDATE OR DELETE ON scenario_templates_revision
            FOR EACH ROW EXECUTE FUNCTION scenario_templates_guard_published_revision();
        """
    )


def remove_published_revision_guard(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        """
        DROP TRIGGER IF EXISTS scenario_templates_published_revision_guard
            ON scenario_templates_revision;
        DROP FUNCTION IF EXISTS scenario_templates_guard_published_revision();
        """
    )


class Migration(migrations.Migration):
    # atomic=False: scenario_templates_revision has DEFERRABLE INITIALLY DEFERRED
    # FK constraint triggers (created_by -> users_user, template -> ScenarioTemplate).
    # The backfill RunPython UPDATEs rows on this table, queuing deferred trigger
    # events that block the subsequent AddConstraint ALTER TABLE within the same
    # transaction ("cannot ALTER TABLE ... pending trigger events"). Running each
    # operation in its own transaction lets the deferred triggers fire at commit
    # before the ALTER, clearing the pending events.
    atomic = False

    dependencies = [
        ("scenario_templates", "0005_phase8b_catalog_assets"),
        ("chat", "0017_independent_thinking_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="scenariotemplaterevision",
            name="snapshot_hash",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="scenariotemplaterevision",
            name="published_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="scenariotemplate",
            name="current_revision",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="current_for_templates",
                to="scenario_templates.scenariotemplaterevision",
            ),
        ),
        migrations.AddField(
            model_name="scenariotemplateapplication",
            name="legacy_revision_unknown",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="scenariotemplateapplication",
            name="template_revision",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="applications",
                to="scenario_templates.scenariotemplaterevision",
            ),
        ),
        migrations.RunPython(backfill_versioned_contract, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="scenariotemplaterevision",
            name="snapshot_hash",
            field=models.CharField(max_length=64),
        ),
        migrations.AddConstraint(
            model_name="scenariotemplaterevision",
            constraint=models.CheckConstraint(
                check=models.Q(("snapshot_hash__regex", "^[0-9a-f]{64}$")),
                name="scenario_revision_hash_shape",
            ),
        ),
        migrations.RunPython(
            install_published_revision_guard,
            remove_published_revision_guard,
        ),
    ]
