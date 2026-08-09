import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_lineages(apps, schema_editor):
    Document = apps.get_model("knowledge", "Document")
    rows = list(Document.objects.all().values_list("id", "parent_document_id"))
    parents = {doc_id: parent_id for doc_id, parent_id in rows}
    roots = {}

    def root_for(doc_id):
        if doc_id in roots:
            return roots[doc_id]
        seen = set()
        current = doc_id
        while parents.get(current) is not None and current not in seen:
            seen.add(current)
            current = parents[current]
        root = current if current not in seen else doc_id
        for visited in seen:
            roots[visited] = root
        roots[doc_id] = root
        return root

    for document in Document.objects.all().only("id", "lineage_id"):
        document.lineage_id = root_for(document.id)
        document.save(update_fields=["lineage_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("knowledge", "0021_reference_library_official_favorites"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="lineage_id",
            field=models.UUIDField(db_index=True, editable=False, null=True),
        ),
        migrations.RunPython(backfill_lineages, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="document",
            name="lineage_id",
            field=models.UUIDField(default=uuid.uuid4, db_index=True, editable=False),
        ),
        migrations.CreateModel(
            name="DocumentLinkOccurrence",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("ordinal", models.PositiveIntegerField(default=0)),
                ("syntax", models.CharField(blank=True, default="wikilink", max_length=20)),
                ("anchor_text", models.CharField(blank=True, default="", max_length=255)),
                ("char_start", models.PositiveIntegerField(blank=True, null=True)),
                ("char_end", models.PositiveIntegerField(blank=True, null=True)),
                ("heading_path", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("link", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="occurrences", to="knowledge.documentlink")),
            ],
            options={"db_table": "knowledge_documentlinkoccurrence", "ordering": ["ordinal", "id"]},
        ),
        migrations.AddConstraint(
            model_name="documentlinkoccurrence",
            constraint=models.UniqueConstraint(fields=("link", "ordinal"), name="knowledge_linkocc_link_ordinal_uniq"),
        ),
        migrations.CreateModel(
            name="KnowledgeGraphState",
            fields=[
                ("space", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name="knowledge_graph_state", serialize=False, to="spaces.knowledgespace")),
                ("revision", models.PositiveBigIntegerField(default=1)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "knowledge_graphstate"},
        ),
        migrations.CreateModel(
            name="GraphScene",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120)),
                ("visibility", models.CharField(choices=[("private", "Private"), ("workspace", "Workspace")], default="private", max_length=20)),
                ("canonical_query", models.JSONField(default=dict)),
                ("layout", models.JSONField(blank=True, default=dict)),
                ("resolved_versions", models.JSONField(blank=True, default=dict)),
                ("schema_version", models.CharField(default="graph.scene.v1", max_length=40)),
                ("graph_revision", models.PositiveBigIntegerField(default=1)),
                ("revision", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="graph_scenes", to=settings.AUTH_USER_MODEL)),
                ("space", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="graph_scenes", to="spaces.knowledgespace")),
            ],
            options={"db_table": "knowledge_graphscene", "ordering": ["-updated_at"]},
        ),
        migrations.AddIndex(
            model_name="graphscene",
            index=models.Index(fields=["space", "visibility", "-updated_at"], name="knowledge_g_space_i_4298ea_idx"),
        ),
        migrations.AddIndex(
            model_name="graphscene",
            index=models.Index(fields=["owner", "-updated_at"], name="knowledge_g_owner_i_b347be_idx"),
        ),
    ]
