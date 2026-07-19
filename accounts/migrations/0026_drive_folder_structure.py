from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0025_google_drive_connection"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="drive_folder_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Google Drive folder for this client under Clients/.",
                max_length=128,
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="drive_litigation_folder_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Google Drive Litigation subfolder for this client.",
                max_length=128,
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="drive_non_litigation_folder_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Google Drive Non-Litigation subfolder for this client.",
                max_length=128,
            ),
        ),
        migrations.AddField(
            model_name="googledriveconnection",
            name="clients_folder_id",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="googledriveconnection",
            name="root_folder_id",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="googledriveconnection",
            name="work_folder_id",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
    ]
