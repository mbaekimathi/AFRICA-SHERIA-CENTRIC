# Generated manually for BAUNILAWGROUP terms + gallery

import accounts.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0041_employee_blog_submit_approval"),
    ]

    operations = [
        migrations.AddField(
            model_name="firmcompanyinformation",
            name="terms_and_conditions",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Public terms and conditions shown on the firm website.",
            ),
        ),
        migrations.CreateModel(
            name="FirmGalleryImage",
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
                ("title", models.CharField(max_length=160)),
                (
                    "caption",
                    models.CharField(blank=True, default="", max_length=320),
                ),
                (
                    "image",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to=accounts.models.gallery_image_upload_to,
                    ),
                ),
                (
                    "rank",
                    models.PositiveIntegerField(
                        default=1,
                        help_text="Lower numbers appear first (1 = highest priority).",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gallery_updates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Company gallery image",
                "verbose_name_plural": "Company gallery images",
                "ordering": ["rank", "title"],
            },
        ),
    ]
