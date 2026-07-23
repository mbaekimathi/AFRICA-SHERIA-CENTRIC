from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0073_utf8mb4_document_text_tables"),
    ]

    operations = [
        migrations.AddField(
            model_name="casetask",
            name="allow_view",
            field=models.BooleanField(
                default=True,
                help_text="Assignee may view case details and documents.",
            ),
        ),
        migrations.AddField(
            model_name="casetask",
            name="allow_edit",
            field=models.BooleanField(
                default=True,
                help_text="Assignee may edit case details and rename documents.",
            ),
        ),
        migrations.AddField(
            model_name="casetask",
            name="allow_download",
            field=models.BooleanField(
                default=True,
                help_text="Assignee may download case documents.",
            ),
        ),
        migrations.AddField(
            model_name="casetask",
            name="allow_delete",
            field=models.BooleanField(
                default=True,
                help_text="Assignee may delete case documents.",
            ),
        ),
        migrations.AddField(
            model_name="casetask",
            name="allow_upload",
            field=models.BooleanField(
                default=True,
                help_text="Assignee may upload or create case documents.",
            ),
        ),
    ]
