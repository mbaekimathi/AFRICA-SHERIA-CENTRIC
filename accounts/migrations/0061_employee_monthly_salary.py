from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0060_employee_activity_permission"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="monthly_salary",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Gross monthly salary used for payroll.",
                max_digits=14,
                null=True,
            ),
        ),
    ]
