from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0062_payroll_run"),
    ]

    operations = [
        migrations.AddField(
            model_name="payrollrun",
            name="basic_salary",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="house_allowance",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="transport_allowance",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="medical_allowance",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="other_allowances",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="bonuses_overtime_commissions",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="nssf_employee_rate",
            field=models.DecimalField(decimal_places=2, default=Decimal("6"), max_digits=6),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="nssf_employer_rate",
            field=models.DecimalField(decimal_places=2, default=Decimal("1.5"), max_digits=6),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="nssf_tier1_limit",
            field=models.DecimalField(decimal_places=2, default=Decimal("7000"), max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="nssf_pensionable_cap",
            field=models.DecimalField(decimal_places=2, default=Decimal("36000"), max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="shif_rate",
            field=models.DecimalField(decimal_places=2, default=Decimal("2.75"), max_digits=6),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="housing_levy_employee_rate",
            field=models.DecimalField(decimal_places=2, default=Decimal("1.5"), max_digits=6),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="housing_levy_employer_rate",
            field=models.DecimalField(decimal_places=2, default=Decimal("1.5"), max_digits=6),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="paye_personal_relief",
            field=models.DecimalField(decimal_places=2, default=Decimal("2400"), max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="paye_band_1_max",
            field=models.DecimalField(decimal_places=2, default=Decimal("24000"), max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="paye_band_1_rate",
            field=models.DecimalField(decimal_places=2, default=Decimal("10"), max_digits=6),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="paye_band_2_max",
            field=models.DecimalField(decimal_places=2, default=Decimal("32333"), max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="paye_band_2_rate",
            field=models.DecimalField(decimal_places=2, default=Decimal("25"), max_digits=6),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="paye_band_3_max",
            field=models.DecimalField(decimal_places=2, default=Decimal("500000"), max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="paye_band_3_rate",
            field=models.DecimalField(decimal_places=2, default=Decimal("30"), max_digits=6),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="paye_band_4_rate",
            field=models.DecimalField(decimal_places=2, default=Decimal("35"), max_digits=6),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="nssf_employee_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="shif_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="housing_levy_employee_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="paye_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="taxable_income",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="nssf_employer_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="housing_levy_employer_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="nita_levy_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("50"), max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="wiba_insurance_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="total_employer_cost",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
    ]
