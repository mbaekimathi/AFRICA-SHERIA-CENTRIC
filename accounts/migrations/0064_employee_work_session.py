import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0063_payroll_statutory_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmployeeWorkSession",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("session_key", models.CharField(blank=True, default="", max_length=64)),
                ("login_at", models.DateTimeField()),
                ("logout_at", models.DateTimeField(blank=True, null=True)),
                ("last_active_at", models.DateTimeField()),
                ("working_seconds", models.PositiveIntegerField(default=0)),
                (
                    "logout_kind",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("manual", "Signed out"),
                            ("expired", "Session expired"),
                            ("replaced", "New login"),
                        ],
                        default="",
                        max_length=16,
                    ),
                ),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="work_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Employee work session",
                "verbose_name_plural": "Employee work sessions",
                "ordering": ["-login_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["employee", "-login_at"],
                        name="accounts_em_employe_853ad4_idx",
                    ),
                    models.Index(
                        fields=["session_key", "logout_at"],
                        name="accounts_em_session_e91f32_idx",
                    ),
                ],
            },
        ),
    ]
