# Generated manually for CompanyLetterheadSetting

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0094_petty_cash_expense_request"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyLetterheadSetting",
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
                            ("classic", "Classic split"),
                            ("centered", "Centered seal"),
                            ("banner", "Accent banner"),
                            ("ruled", "Ruled header"),
                            ("split", "Modern split"),
                            ("minimal", "Minimal stack"),
                        ],
                        default="classic",
                        help_text="Letterhead layout sample used on invoices and receipts.",
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
                        help_text="Accent colour applied to rules, marks, and banners.",
                        max_length=32,
                    ),
                ),
                (
                    "show_logo",
                    models.BooleanField(
                        default=True,
                        help_text="Show the company profile image (or initials mark) when available.",
                    ),
                ),
                (
                    "show_tagline",
                    models.BooleanField(
                        default=True,
                        help_text="Show the company tagline under the firm name when set.",
                    ),
                ),
                (
                    "show_address",
                    models.BooleanField(
                        default=False,
                        help_text="Include physical or postal address lines.",
                    ),
                ),
                (
                    "show_contacts",
                    models.BooleanField(
                        default=True,
                        help_text="Show phone, email, and website contact lines.",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="company_letterhead_updates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Company letterhead setting",
                "verbose_name_plural": "Company letterhead setting",
            },
        ),
    ]
