from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0074_casetask_access_permissions"),
    ]

    operations = [
        migrations.AddField(
            model_name="mattertask",
            name="allow_view",
            field=models.BooleanField(
                default=True,
                help_text="Assignee may view matter details and documents.",
            ),
        ),
        migrations.AddField(
            model_name="mattertask",
            name="allow_edit",
            field=models.BooleanField(
                default=True,
                help_text="Assignee may edit matter details and rename documents.",
            ),
        ),
        migrations.AddField(
            model_name="mattertask",
            name="allow_download",
            field=models.BooleanField(
                default=True,
                help_text="Assignee may download matter documents.",
            ),
        ),
        migrations.AddField(
            model_name="mattertask",
            name="allow_delete",
            field=models.BooleanField(
                default=True,
                help_text="Assignee may delete matter documents.",
            ),
        ),
        migrations.AddField(
            model_name="mattertask",
            name="allow_upload",
            field=models.BooleanField(
                default=True,
                help_text="Assignee may upload or create matter documents.",
            ),
        ),
    ]
