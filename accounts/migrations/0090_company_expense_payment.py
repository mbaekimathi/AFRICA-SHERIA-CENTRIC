from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0089_seed_petty_cash_book_account"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyExpensePayment",
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
                    "expense_type",
                    models.CharField(
                        choices=[
                            ("office_supplies", "Office supplies"),
                            ("transport", "Transport / travel"),
                            ("utilities", "Utilities"),
                            ("communication", "Communication"),
                            ("court_fees", "Court fees"),
                            ("filing_fees", "Filing fees"),
                            ("professional_fees", "Professional fees"),
                            ("staff_welfare", "Staff welfare"),
                            ("maintenance", "Maintenance / repairs"),
                            ("bank_charges", "Bank charges"),
                            ("rent", "Rent"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=32,
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        help_text="What this expense payment covers.",
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                (
                    "balance_after",
                    models.DecimalField(decimal_places=2, max_digits=14),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="expense_payments",
                        to="accounts.companyexpenseaccount",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="company_expense_payments_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Company expense payment",
                "verbose_name_plural": "Company expense payments",
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
