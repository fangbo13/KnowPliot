# Generated for review_policy default change: require_review → direct_publish

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('spaces', '0022_alter_spacemembership_role'),
    ]

    operations = [
        migrations.AlterField(
            model_name='knowledgespace',
            name='review_policy',
            field=models.CharField(
                choices=[('direct_publish', 'Direct Publish'), ('require_review', 'Require Review')],
                default='direct_publish',
                help_text='Whether new document versions need reviewer approval before indexing.',
                max_length=20,
            ),
        ),
    ]
