from django.db import migrations

BLOG_ACTIVITIES = {"my-blogs", "my-blogs-new", "company-blogs"}


def _unique_lookup(row, *, module_slug, activity_slug=None):
    lookup = {
        "module_slug": module_slug,
        "activity_slug": activity_slug or row.activity_slug,
    }
    if hasattr(row, "role"):
        lookup["role"] = row.role
    if hasattr(row, "employee_id"):
        lookup["employee_id"] = row.employee_id
    if hasattr(row, "action"):
        lookup["action"] = row.action
    return lookup


def _defaults_from(row):
    defaults = {"is_allowed": row.is_allowed}
    if hasattr(row, "updated_by_id"):
        defaults["updated_by_id"] = row.updated_by_id
    return defaults


def forwards(apps, schema_editor):
    RoleActivityPermission = apps.get_model("accounts", "RoleActivityPermission")
    EmployeeActivityPermission = apps.get_model(
        "accounts", "EmployeeActivityPermission"
    )

    for model in (RoleActivityPermission, EmployeeActivityPermission):
        for row in list(model.objects.filter(module_slug="research-blogs")):
            if row.activity_slug == "research-blogs":
                for module_slug, activity_slug in (
                    ("research", "research"),
                    ("blogs", "blogs"),
                ):
                    model.objects.update_or_create(
                        **_unique_lookup(
                            row,
                            module_slug=module_slug,
                            activity_slug=activity_slug,
                        ),
                        defaults=_defaults_from(row),
                    )
                row.delete()
                continue

            new_module = (
                "blogs" if row.activity_slug in BLOG_ACTIVITIES else "research"
            )
            lookup = _unique_lookup(row, module_slug=new_module)
            if model.objects.filter(**lookup).exclude(pk=row.pk).exists():
                row.delete()
            else:
                row.module_slug = new_module
                row.save(update_fields=["module_slug"])


def backwards(apps, schema_editor):
    RoleActivityPermission = apps.get_model("accounts", "RoleActivityPermission")
    EmployeeActivityPermission = apps.get_model(
        "accounts", "EmployeeActivityPermission"
    )
    for model in (RoleActivityPermission, EmployeeActivityPermission):
        model.objects.filter(module_slug__in={"research", "blogs"}).update(
            module_slug="research-blogs"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0103_employeeblogpost_review_note"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
