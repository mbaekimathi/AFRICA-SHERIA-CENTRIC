from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0026_drive_folder_structure"),
    ]

    operations = [
        migrations.AddField(
            model_name="litigationcase",
            name="drive_folder_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Google Drive folder for this case under the client's Litigation folder.",
                max_length=128,
            ),
        ),
        migrations.AddField(
            model_name="nonlitigationmatter",
            name="drive_folder_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Google Drive folder for this matter under the client's Non-Litigation folder.",
                max_length=128,
            ),
        ),
        migrations.CreateModel(
            name="Document",
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
                ("title", models.CharField(max_length=255)),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("google_doc", "Google Doc"),
                            ("uploaded", "Uploaded file"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "drive_file_id",
                    models.CharField(blank=True, default="", max_length=128),
                ),
                ("web_view_link", models.URLField(blank=True, default="")),
                (
                    "mime_type",
                    models.CharField(blank=True, default="", max_length=120),
                ),
                (
                    "original_filename",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "local_file",
                    models.FileField(
                        blank=True,
                        null=True,
                        upload_to="matter-documents/%Y/%m/",
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "case",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="accounts.litigationcase",
                    ),
                ),
                (
                    "matter",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="accounts.nonlitigationmatter",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="uploaded_documents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Document",
                "verbose_name_plural": "Documents",
                "ordering": ["-updated_at", "-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="document",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(case__isnull=False, matter__isnull=True)
                    | models.Q(case__isnull=True, matter__isnull=False)
                ),
                name="document_case_xor_matter",
            ),
        ),
    ]
