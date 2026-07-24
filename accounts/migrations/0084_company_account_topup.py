from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0083_companyexpenseaccount_bank_account_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyexpenseaccount",
            name="balance",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=14,
                verbose_name="Current balance",
            ),
        ),
        migrations.CreateModel(
            name="CompanyAccountTopup",
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
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                (
                    "source_note",
                    models.TextField(
                        help_text="Where this income came from.",
                        verbose_name="Source note",
                    ),
                ),
                (
                    "balance_after",
                    models.DecimalField(decimal_places=2, max_digits=14),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="topups",
                        to="accounts.companyexpenseaccount",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="company_account_topups_created",
                        to="accounts.employee",
                    ),
                ),
            ],
            options={
                "verbose_name": "Company account top-up",
                "verbose_name_plural": "Company account top-ups",
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
