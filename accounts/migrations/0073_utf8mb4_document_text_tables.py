# Convert legacy latin1 tables so Google-exported UTF-8 text (incl. BOM) can save.

from django.db import migrations


def _convert_accounts_tables_to_utf8mb4(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME LIKE 'accounts\\_%%' "
            "AND (TABLE_COLLATION IS NULL OR TABLE_COLLATION NOT LIKE 'utf8mb4%%') "
            "ORDER BY TABLE_NAME"
        )
        tables = [row[0] for row in cursor.fetchall()]
        for table in tables:
            cursor.execute(
                f"ALTER TABLE `{table}` "
                "CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0072_court_attendance_virtual_link"),
    ]

    operations = [
        migrations.RunPython(
            _convert_accounts_tables_to_utf8mb4,
            migrations.RunPython.noop,
        ),
    ]
