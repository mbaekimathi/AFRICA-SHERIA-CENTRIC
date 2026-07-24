from decimal import Decimal

from django.db import migrations


def seed_petty_cash_book(apps, schema_editor):
    CompanyExpenseAccount = apps.get_model("accounts", "CompanyExpenseAccount")
    CompanyExpenseAccount.objects.get_or_create(
        system_key="petty_cash_book",
        defaults={
            "name": "Petty Cash Book",
            "bank_name": "System ledger",
            "bank_account_number": "PETTY-CASH",
            "description": "Daily unplanned expenses",
            "payment_methods": ["cash", "mpesa"],
            "balance": Decimal("0.00"),
        },
    )


def unseed_petty_cash_book(apps, schema_editor):
    CompanyExpenseAccount = apps.get_model("accounts", "CompanyExpenseAccount")
    CompanyExpenseAccount.objects.filter(system_key="petty_cash_book").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0088_companyexpenseaccount_system_key_and_main_client"),
    ]

    operations = [
        migrations.RunPython(seed_petty_cash_book, unseed_petty_cash_book),
    ]
