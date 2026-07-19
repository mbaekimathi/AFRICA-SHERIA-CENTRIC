from django.db import migrations


ROLE_ENUM = (
    "ENUM("
    "'firm_admin','managing_partner','advocate',"
    "'intern','it_support','employee'"
    ") NOT NULL DEFAULT 'employee'"
)

STATUS_ENUM = (
    "ENUM('pending','active','suspended') NOT NULL DEFAULT 'pending'"
)


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            f"ALTER TABLE accounts_employee MODIFY COLUMN role {ROLE_ENUM}"
        )
        cursor.execute(
            f"ALTER TABLE accounts_employee MODIFY COLUMN status {STATUS_ENUM}"
        )


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE accounts_employee "
            "MODIFY COLUMN role VARCHAR(32) NOT NULL DEFAULT 'employee'"
        )
        cursor.execute(
            "ALTER TABLE accounts_employee "
            "MODIFY COLUMN status VARCHAR(20) NOT NULL DEFAULT 'pending'"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_id_country"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
