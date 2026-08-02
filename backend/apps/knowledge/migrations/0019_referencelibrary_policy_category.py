# Reference library "policy" category (company policy public libraries).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("knowledge", "0018_documentlink_unresolved_title_taxonomyterm_synonyms_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="referencelibrary",
            name="category",
            field=models.CharField(
                choices=[
                    ("ifrs", "IFRS"),
                    ("cas", "China Accounting Standards"),
                    ("ipo_cases", "IPO Cases"),
                    ("policy", "Company Policy"),
                    ("other", "Other"),
                ],
                default="other",
                max_length=20,
            ),
        ),
    ]
