# Generated manually for CompanyDigitalSignatureSetting

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0098_company_digital_stamp_setting"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyDigitalSignatureSetting",
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
                            ("classic", "Classic line"),
                            ("script", "Script flourish"),
                            ("formal", "Formal block"),
                            ("monogram", "Monogram mark"),
                            ("stacked", "Stacked authority"),
                            ("compact", "Compact strip"),
                        ],
                        default="classic",
                        help_text="Digital signature layout sample used on invoices and receipts.",
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
                        default="navy",
                        help_text="Accent colour for the signature ink and rules.",
                        max_length=32,
                    ),
                ),
                (
                    "default_title",
                    models.CharField(
                        blank=True,
                        default="Authorized Signatory",
                        help_text="Default title / capacity shown under the signatory name.",
                        max_length=120,
                    ),
                ),
                (
                    "show_firm_name",
                    models.BooleanField(
                        default=True,
                        help_text="Show the firm display name on the signature block.",
                    ),
                ),
                (
                    "show_name",
                    models.BooleanField(
                        default=True,
                        help_text="Show the signatory name when available.",
                    ),
                ),
                (
                    "show_title",
                    models.BooleanField(
                        default=True,
                        help_text="Show the signatory title / capacity.",
                    ),
                ),
                (
                    "show_date",
                    models.BooleanField(
                        default=True,
                        help_text="Show the signature date when available.",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="company_digital_signature_updates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Company digital signature setting",
                "verbose_name_plural": "Company digital signature setting",
            },
        ),
    ]
