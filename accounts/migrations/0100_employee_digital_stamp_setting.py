# Generated manually for EmployeeDigitalStampSetting

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0099_company_digital_signature_setting"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmployeeDigitalStampSetting",
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
                        help_text="Personal digital stamp layout sample.",
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
                        help_text="Show your name on the stamp.",
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
                    "employee",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="digital_stamp_setting",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Employee digital stamp setting",
                "verbose_name_plural": "Employee digital stamp settings",
            },
        ),
    ]
