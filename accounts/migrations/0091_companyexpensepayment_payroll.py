import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0090_company_expense_payment"),
    ]

    operations = [
        migrations.AlterField(
            model_name="companyexpensepayment",
            name="expense_type",
            field=models.CharField(
                choices=[
                    ("office_supplies", "Office supplies"),
                    ("transport", "Transport / travel"),
                    ("utilities", "Utilities"),
                    ("communication", "Communication"),
                    ("court_fees", "Court fees"),
                    ("filing_fees", "Filing fees"),
                    ("professional_fees", "Professional fees"),
                    ("payroll", "Payroll"),
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
        migrations.AddField(
            model_name="companyexpensepayment",
            name="employee",
            field=models.ForeignKey(
                blank=True,
                help_text="Set when expense type is Payroll.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="company_expense_payments",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="companyexpensepayment",
            name="payroll_payment",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="expense_payments",
                to="accounts.payrollpayment",
            ),
        ),
    ]
