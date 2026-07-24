# Generated manually for CompanyDigitalStampSetting

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0097_company_letterhead_footer_template"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyDigitalStampSetting",
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
                    "template",
                    models.CharField(
                        choices=[
                            ("classic", "Classic ring"),
                            ("square", "Square seal"),
                            ("oval", "Oval seal"),
                            ("badge", "Shield badge"),
                            ("ribbon", "Ribbon banner"),
                            ("wax", "Wax stamp"),
                        ],
                        default="classic",
                        help_text="Digital stamp layout sample used on invoices and receipts.",
                        max_length=32,
                    ),
                ),
                (
                    "accent",
                    models.CharField(
                        choices=[
                            ("forest", "Forest"),
                            ("navy", "Navy"),
                            ("charcoal", "Charcoal"),
                            ("burgundy", "Burgundy"),
                            ("teal", "Teal"),
                            ("gold", "Gold"),
                        ],
                        default="forest",
                        help_text="Accent colour for the stamp ink and borders.",
                        max_length=32,
                    ),
                ),
                (
                    "show_firm_name",
                    models.BooleanField(
                        default=True,
                        help_text="Show the firm display name on the stamp.",
                    ),
                ),
                (
                    "show_status",
                    models.BooleanField(
                        default=True,
                        help_text="Show the document status (Paid, Issued, etc.).",
                    ),
                ),
                (
                    "show_approver",
                    models.BooleanField(
                        default=True,
                        help_text="Show the approver / recorder name when available.",
                    ),
                ),
                (
                    "show_date",
                    models.BooleanField(
                        default=True,
                        help_text="Show the approval or payment date when available.",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="company_digital_stamp_updates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Company digital stamp setting",
                "verbose_name_plural": "Company digital stamp setting",
            },
        ),
    ]
