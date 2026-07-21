# Generated manually for EmployeeActivityPermission

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0059_role_activity_permission"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmployeeActivityPermission",
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
                ("module_slug", models.SlugField(max_length=64)),
                ("activity_slug", models.SlugField(max_length=64)),
                ("action", models.CharField(max_length=32)),
                ("is_allowed", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="activity_action_permissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="employee_activity_permission_updates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Employee activity permission",
                "verbose_name_plural": "Employee activity permissions",
                "ordering": [
                    "module_slug",
                    "activity_slug",
                    "employee_id",
                    "action",
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="employeeactivitypermission",
            constraint=models.UniqueConstraint(
                fields=("employee", "module_slug", "activity_slug", "action"),
                name="uniq_employee_module_activity_action",
            ),
        ),
    ]
