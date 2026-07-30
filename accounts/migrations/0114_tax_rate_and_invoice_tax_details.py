from decimal import Decimal

import django.core.validators
from django.db import migrations, models


def seed_tax_rates(apps, schema_editor):
    TaxRate = apps.get_model("accounts", "TaxRate")
    for name, percentage in (
        ("VAT - Standard rated", Decimal("16.00")),
        ("VAT - Zero-rated", Decimal("0.00")),
        ("Exempt", Decimal("0.00")),
    ):
        TaxRate.objects.get_or_create(
            name=name,
            defaults={"percentage": percentage, "is_active": True},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0113_pettycashexpenserequest_payment_attachment"),
    ]

    operations = [
        migrations.CreateModel(
            name="TaxRate",
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
                ("name", models.CharField(max_length=80, unique=True)),
                (
                    "percentage",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=6,
                        validators=[
                            django.core.validators.MinValueValidator(
                                Decimal("0.00")
                            ),
                            django.core.validators.MaxValueValidator(
                                Decimal("100.00")
                            ),
                        ],
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Tax rate",
                "verbose_name_plural": "Tax rates",
                "ordering": ["name", "percentage"],
            },
        ),
        migrations.AddField(
            model_name="invoice",
            name="tax_name",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="invoice",
            name="tax_rate",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=6,
                null=True,
            ),
        ),
        migrations.RunPython(seed_tax_rates, migrations.RunPython.noop),
    ]
