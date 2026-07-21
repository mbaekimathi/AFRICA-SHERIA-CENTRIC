from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0064_employee_work_session"),
    ]

    operations = [
        migrations.AddField(
            model_name="payrollrun",
            name="pay_frequency",
            field=models.CharField(
                choices=[
                    ("daily", "Daily"),
                    ("weekly", "Weekly"),
                    ("monthly", "Monthly"),
                    ("annually", "Annually"),
                ],
                default="monthly",
                max_length=16,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="payrollrun",
            name="unique_payroll_period_per_employee",
        ),
        migrations.AddConstraint(
            model_name="payrollrun",
            constraint=models.UniqueConstraint(
                fields=("employee", "pay_frequency", "pay_period_start"),
                name="unique_payroll_period_per_employee",
            ),
        ),
    ]
