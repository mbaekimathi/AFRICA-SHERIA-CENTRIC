from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0061_employee_monthly_salary"),
    ]

    operations = [
        migrations.CreateModel(
            name="PayrollRun",
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
                ("pay_period_start", models.DateField()),
                ("pay_period_end", models.DateField()),
                (
                    "gross_salary",
                    models.DecimalField(decimal_places=2, max_digits=14),
                ),
                (
                    "total_deductions",
                    models.DecimalField(
                        decimal_places=2, default=0, max_digits=14
                    ),
                ),
                ("net_pay", models.DecimalField(decimal_places=2, max_digits=14)),
                (
                    "payment_method",
                    models.CharField(blank=True, default="", max_length=16),
                ),
                (
                    "payment_method_label",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                (
                    "payout_destination",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("registered", "Registered"),
                            ("paid", "Paid"),
                        ],
                        default="registered",
                        max_length=16,
                    ),
                ),
                ("registered_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payroll_runs",
                        to="accounts.employee",
                    ),
                ),
                (
                    "registered_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payroll_runs_registered",
                        to="accounts.employee",
                    ),
                ),
            ],
            options={
                "verbose_name": "Payroll run",
                "verbose_name_plural": "Payroll runs",
                "ordering": ["-pay_period_end", "-registered_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="PayrollDeduction",
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
                    "deduction_type",
                    models.CharField(
                        choices=[
                            ("paye", "PAYE"),
                            ("nssf", "NSSF"),
                            ("nhif_shif", "NHIF / SHIF"),
                            ("pension", "Pension"),
                            ("loan", "Loan repayment"),
                            ("advance", "Salary advance"),
                            ("other", "Other"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "description",
                    models.CharField(blank=True, default="", max_length=120),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                (
                    "payroll_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deductions",
                        to="accounts.payrollrun",
                    ),
                ),
            ],
            options={
                "verbose_name": "Payroll deduction",
                "verbose_name_plural": "Payroll deductions",
                "ordering": ["id"],
            },
        ),
        migrations.AddConstraint(
            model_name="payrollrun",
            constraint=models.UniqueConstraint(
                fields=("employee", "pay_period_start", "pay_period_end"),
                name="unique_payroll_period_per_employee",
            ),
        ),
    ]
