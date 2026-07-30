from decimal import Decimal

from django.db import migrations


# Kenya VAT classifications relevant to professional / legal services invoices.
# Petroleum VAT is not applicable to law-firm billing.
CORRECT_TAXES = (
    ("VAT - Standard rated", Decimal("16.00")),
    ("VAT - Zero-rated", Decimal("0.00")),
    ("Exempt", Decimal("0.00")),
)

LEGACY_NAMES = {
    "VAT - Petroleum",
    "VAT - Standard",
    "VAT - Zero Rated",
}


def correct_tax_rates(apps, schema_editor):
    TaxRate = apps.get_model("accounts", "TaxRate")

    # Retire incorrect / legacy labels so they no longer appear in the dropdown.
    TaxRate.objects.filter(name__in=LEGACY_NAMES).update(is_active=False)

    for name, percentage in CORRECT_TAXES:
        tax, created = TaxRate.objects.get_or_create(
            name=name,
            defaults={"percentage": percentage, "is_active": True},
        )
        if not created:
            tax.percentage = percentage
            tax.is_active = True
            tax.save(update_fields=["percentage", "is_active", "updated_at"])


def revert_tax_rates(apps, schema_editor):
    TaxRate = apps.get_model("accounts", "TaxRate")
    TaxRate.objects.filter(name__in={name for name, _ in CORRECT_TAXES}).update(
        is_active=False
    )
    for name, percentage in (
        ("VAT - Standard", Decimal("16.00")),
        ("VAT - Petroleum", Decimal("8.00")),
        ("VAT - Zero Rated", Decimal("0.00")),
    ):
        tax, created = TaxRate.objects.get_or_create(
            name=name,
            defaults={"percentage": percentage, "is_active": True},
        )
        if not created:
            tax.percentage = percentage
            tax.is_active = True
            tax.save(update_fields=["percentage", "is_active", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0114_tax_rate_and_invoice_tax_details"),
    ]

    operations = [
        migrations.RunPython(correct_tax_rates, revert_tax_rates),
    ]
