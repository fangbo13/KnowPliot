"""V4.2 KB-V4.2-BATCH-011: Add batch import action choices to AuditLog."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0004_alter_auditlog_action"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                choices=[
                    # Content domain (V3.8)
                    ("document_upload", "Document Upload"),
                    ("document_delete", "Document Delete"),
                    ("document_reindex", "Document Reindex"),
                    ("document_status_change", "Document Status Change"),
                    ("template_create", "Template Create"),
                    ("template_update", "Template Update"),
                    ("template_delete", "Template Delete"),
                    ("user_login", "User Login"),
                    ("export_data", "Export Data"),
                    ("category_create", "Category Create"),
                    ("category_update", "Category Update"),
                    # System domain (V4.0)
                    ("role_assign", "Role Assign"),
                    ("role_revoke", "Role Revoke"),
                    ("user_create", "User Create"),
                    ("user_update", "User Update"),
                    ("user_deactivate", "User Deactivate"),
                    ("config_change", "Config Change"),
                    ("system_health_view", "System Health View"),
                    ("audit_export", "Audit Export"),
                    ("role_change_log", "Role Change Log"),
                    # Crawler domain (V4.1)
                    ("document_crawl", "Document Crawl"),
                    ("document_crawl_withdraw", "Document Crawl Withdraw"),
                    # Batch domain (V4.2)
                    ("document_batch_import", "Document Batch Import"),
                    ("document_batch_result_view", "Document Batch Result View"),
                ],
                max_length=30,
            ),
        ),
    ]
