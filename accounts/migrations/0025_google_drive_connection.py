from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0024_task_title"),
    ]

    operations = [
        migrations.CreateModel(
            name="GoogleDriveConnection",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("access_token", models.TextField(blank=True, default="")),
                ("refresh_token", models.TextField(blank=True, default="")),
                ("token_expiry", models.DateTimeField(blank=True, null=True)),
                ("scopes", models.TextField(blank=True, default="")),
                ("account_email", models.EmailField(blank=True, default="", max_length=254)),
                ("account_name", models.CharField(blank=True, default="", max_length=255)),
                ("connected_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "connected_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="google_drive_connections",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Google Drive connection",
                "verbose_name_plural": "Google Drive connection",
            },
        ),
    ]
