import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrate_published_to_official(apps, schema_editor):
    ReferenceLibrary = apps.get_model("knowledge", "ReferenceLibrary")
    ReferenceLibrary.objects.filter(status="published").update(is_official=True)


class Migration(migrations.Migration):
    dependencies = [
        ("knowledge", "0020_document_feedback_score"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="referencelibrary",
            name="is_official",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.CreateModel(
            name="UserReferenceLibraryFavorite",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("position", models.PositiveSmallIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "library",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_favorites",
                        to="knowledge.referencelibrary",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reference_library_favorites",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "knowledge_userreferencelibraryfavorite",
                "ordering": ["position", "created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="userreferencelibraryfavorite",
            constraint=models.UniqueConstraint(
                fields=("user", "library"),
                name="knowledge_user_reflib_favorite_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="userreferencelibraryfavorite",
            constraint=models.UniqueConstraint(
                fields=("user", "position"),
                name="knowledge_user_reflib_position_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="userreferencelibraryfavorite",
            constraint=models.CheckConstraint(
                check=models.Q(("position__gte", 1), ("position__lte", 5)),
                name="knowledge_user_reflib_position_range",
            ),
        ),
        migrations.RunPython(migrate_published_to_official, migrations.RunPython.noop),
    ]
