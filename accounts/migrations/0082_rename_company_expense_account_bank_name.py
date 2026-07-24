from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0081_company_expense_account"),
    ]

    operations = [
        migrations.RenameField(
            model_name="companyexpenseaccount",
            old_name="company_name",
            new_name="bank_name",
        ),
        migrations.AlterField(
            model_name="companyexpenseaccount",
            name="bank_name",
            field=models.CharField(
                help_text="Bank holding the money for this expense account.",
                max_length=255,
                verbose_name="Bank name",
            ),
        ),
    ]
