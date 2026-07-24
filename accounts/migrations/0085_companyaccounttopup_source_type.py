from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0084_company_account_topup"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyaccounttopup",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("client", "Client"),
                    ("company_account", "Company account"),
                    ("other", "Others"),
                ],
                default="other",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="companyaccounttopup",
            name="source_client",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="company_account_topups",
                to="accounts.client",
            ),
        ),
        migrations.AddField(
            model_name="companyaccounttopup",
            name="source_company_account",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="topups_as_source",
                to="accounts.companyexpenseaccount",
            ),
        ),
        migrations.AlterField(
            model_name="companyaccounttopup",
            name="source_note",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Free-text source when Others is selected.",
                verbose_name="Source note",
            ),
        ),
    ]
