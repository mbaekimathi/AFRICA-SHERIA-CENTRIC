# Generated manually for FirmFAQ

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0037_firm_practice_areas"),
    ]

    operations = [
        migrations.CreateModel(
            name="FirmFAQ",
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
                (
                    "question",
                    models.CharField(max_length=255, verbose_name="Question"),
                ),
                ("answer", models.TextField(verbose_name="Answer")),
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
                        related_name="faq_updates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Company FAQ",
                "verbose_name_plural": "Company FAQs",
                "ordering": ["rank", "question"],
            },
        ),
    ]
