# Generated manually for RoleActivityPermission

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0058_communication_settings"),
    ]

    operations = [
        migrations.CreateModel(
            name="RoleActivityPermission",
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
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("firm_admin", "Firm Administrator"),
                            ("managing_partner", "Managing Partner"),
                            ("advocate", "Advocate"),
                            ("intern", "Intern"),
                            ("it_support", "IT Support"),
                            ("employee", "Employee"),
                        ],
                        max_length=32,
                    ),
                ),
                ("module_slug", models.SlugField(max_length=64)),
                ("activity_slug", models.SlugField(max_length=64)),
                ("is_allowed", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="role_activity_permission_updates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Role activity permission",
                "verbose_name_plural": "Role activity permissions",
                "ordering": ["module_slug", "activity_slug", "role"],
            },
        ),
        migrations.AddConstraint(
            model_name="roleactivitypermission",
            constraint=models.UniqueConstraint(
                fields=("role", "module_slug", "activity_slug"),
                name="uniq_role_module_activity_permission",
            ),
        ),
    ]
