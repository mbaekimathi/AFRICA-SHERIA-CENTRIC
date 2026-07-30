from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0116_company_signature_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="drive_my_templates_folder_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Google Drive My Templates folder for this employee.",
                max_length=128,
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="drive_my_templates_category_folder_ids",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Map of template category slug → Google Drive folder id under "
                    "this employee's My Templates folder."
                ),
            ),
        ),
    ]
