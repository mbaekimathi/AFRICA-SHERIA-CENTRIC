# Generated manually for letterhead footer templates

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0096_firmcompanyinformation_logo"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyletterheadsetting",
            name="footer_template",
            field=models.CharField(
                choices=[
                    ("compact", "Compact line"),
                    ("centered", "Centered stack"),
                    ("ruled", "Ruled footer"),
                    ("stacked", "Left stack"),
                    ("split", "Split thanks"),
                    ("bar", "Accent bar"),
                ],
                default="compact",
                help_text="Footer layout sample used on invoices and receipts.",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="companyletterheadsetting",
            name="show_address",
            field=models.BooleanField(
                default=True,
                help_text="Show physical, postal, city, and country in the document footer.",
            ),
        ),
        migrations.AlterField(
            model_name="companyletterheadsetting",
            name="show_contacts",
            field=models.BooleanField(
                default=True,
                help_text="Show phone and email contact lines on the letterhead.",
            ),
        ),
    ]
