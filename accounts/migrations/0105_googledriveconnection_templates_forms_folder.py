from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0104_split_research_blogs_modules"),
    ]

    operations = [
        migrations.AddField(
            model_name="googledriveconnection",
            name="templates_forms_folder_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Google Drive folder for firm templates and forms.",
                max_length=128,
            ),
        ),
    ]
