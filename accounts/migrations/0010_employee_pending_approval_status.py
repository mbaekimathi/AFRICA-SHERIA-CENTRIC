from django.db import migrations, models


FINAL_STATUS_ENUM = (
    "ENUM('pending_onboarding','pending_approval','active','suspended') "
    "NOT NULL DEFAULT 'pending_onboarding'"
)

EXPANDED_STATUS_ENUM = (
    "ENUM('pending_onboarding','pending','pending_approval','active','suspended') "
    "NOT NULL DEFAULT 'pending_onboarding'"
)


def forwards(apps, schema_editor):
    Employee = apps.get_model("accounts", "Employee")

    if schema_editor.connection.vendor == "mysql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE accounts_employee MODIFY COLUMN status {EXPANDED_STATUS_ENUM}"
            )

    to_onboarding = []
    to_approval = []
    for emp in Employee.objects.filter(status="pending"):
        has_docs = bool(
            emp.employment_contract
            or emp.national_id_or_passport
            or emp.kra_pin_certificate
        )
        has_pay = bool(emp.payment_method)
        if has_docs or has_pay:
            to_approval.append(emp.pk)
        else:
            to_onboarding.append(emp.pk)

    if to_onboarding:
        Employee.objects.filter(pk__in=to_onboarding).update(
            status="pending_onboarding"
        )
    if to_approval:
        Employee.objects.filter(pk__in=to_approval).update(
            status="pending_approval"
        )

    # Any leftover legacy value
    Employee.objects.filter(status="pending").update(status="pending_approval")

    if schema_editor.connection.vendor == "mysql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE accounts_employee MODIFY COLUMN status {FINAL_STATUS_ENUM}"
            )


def backwards(apps, schema_editor):
    Employee = apps.get_model("accounts", "Employee")

    if schema_editor.connection.vendor == "mysql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE accounts_employee MODIFY COLUMN status {EXPANDED_STATUS_ENUM}"
            )

    Employee.objects.filter(status="pending_approval").update(status="pending")

    if schema_editor.connection.vendor == "mysql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE accounts_employee MODIFY COLUMN status "
                "ENUM('pending_onboarding','pending','active','suspended') "
                "NOT NULL DEFAULT 'pending_onboarding'"
            )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_employee_onboarding_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="employee",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending_onboarding", "Pending Onboarding"),
                    ("pending_approval", "Pending Approval"),
                    ("active", "Active"),
                    ("suspended", "Suspended"),
                ],
                default="pending_onboarding",
                max_length=32,
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
