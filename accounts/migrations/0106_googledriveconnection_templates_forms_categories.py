from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0105_googledriveconnection_templates_forms_folder"),
    ]

    operations = [
        migrations.AddField(
            model_name="googledriveconnection",
            name="templates_forms_category_folder_ids",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Map of template category slug → Google Drive folder id under "
                    "Templates and Forms."
                ),
            ),
        ),
    ]
