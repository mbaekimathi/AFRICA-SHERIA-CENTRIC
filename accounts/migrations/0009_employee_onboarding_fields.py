from django.db import migrations, models


STATUS_ENUM = (
    "ENUM('pending_onboarding','pending','active','suspended') "
    "NOT NULL DEFAULT 'pending_onboarding'"
)


def forwards_mysql_status(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            f"ALTER TABLE accounts_employee MODIFY COLUMN status {STATUS_ENUM}"
        )


def backwards_mysql_status(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "UPDATE accounts_employee SET status='pending' "
            "WHERE status='pending_onboarding'"
        )
        cursor.execute(
            "ALTER TABLE accounts_employee MODIFY COLUMN status "
            "ENUM('pending','active','suspended') NOT NULL DEFAULT 'pending'"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_client_corporate_kind"),
    ]

    operations = [
        migrations.AlterField(
            model_name="employee",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending_onboarding", "Pending Onboarding"),
                    ("pending", "Pending Approval"),
                    ("active", "Active"),
                    ("suspended", "Suspended"),
                ],
                default="pending_onboarding",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="payment_method",
            field=models.CharField(
                blank=True,
                choices=[
                    ("mobile", "Mobile money"),
                    ("bank", "Bank transfer"),
                    ("cash", "Cash"),
                ],
                default="",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="mobile_money_company",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Mobile money provider, e.g. M-Pesa.",
                max_length=80,
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="mobile_money_number",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Number that receives mobile money payouts.",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="bank_name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="employee",
            name="bank_account_number",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="employee",
            name="employment_contract",
            field=models.FileField(
                blank=True, null=True, upload_to="employees/contracts/"
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="national_id_or_passport",
            field=models.FileField(
                blank=True, null=True, upload_to="employees/identity/"
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="kra_pin_certificate",
            field=models.FileField(blank=True, null=True, upload_to="employees/kra/"),
        ),
        migrations.RunPython(forwards_mysql_status, backwards_mysql_status),
    ]
