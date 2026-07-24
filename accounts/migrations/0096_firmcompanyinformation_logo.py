from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0095_company_letterhead_setting"),
    ]

    operations = [
        migrations.AddField(
            model_name="firmcompanyinformation",
            name="logo",
            field=models.ImageField(
                blank=True,
                help_text="Firm logo for letterhead, invoices, and brand mark.",
                null=True,
                upload_to="company/logo/",
            ),
        ),
    ]
