from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0082_rename_company_expense_account_bank_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyexpenseaccount",
            name="bank_account_number",
            field=models.CharField(
                default="",
                max_length=64,
                verbose_name="Bank account number",
            ),
            preserve_default=False,
        ),
    ]
