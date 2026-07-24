from decimal import Decimal

from django.db import migrations, models


def seed_main_client_accounts(apps, schema_editor):
    CompanyExpenseAccount = apps.get_model("accounts", "CompanyExpenseAccount")
    CompanyExpenseAccount.objects.get_or_create(
        system_key="main_client_accounts",
        defaults={
            "name": "Main Client Accounts",
            "bank_name": "System ledger",
            "bank_account_number": "MAIN-CLIENT",
            "description": "Money from invoices and clients",
            "payment_methods": [
                "mpesa",
                "bank_transfer",
                "cash",
                "cheque",
            ],
            "balance": Decimal("0.00"),
        },
    )


def unseed_main_client_accounts(apps, schema_editor):
    CompanyExpenseAccount = apps.get_model("accounts", "CompanyExpenseAccount")
    CompanyExpenseAccount.objects.filter(system_key="main_client_accounts").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0087_alter_companyexpenseaccount_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyexpenseaccount",
            name="system_key",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Stable key for system default accounts. Null for user-created accounts.",
                max_length=64,
                null=True,
                unique=True,
            ),
        ),
        migrations.RunPython(seed_main_client_accounts, unseed_main_client_accounts),
    ]
