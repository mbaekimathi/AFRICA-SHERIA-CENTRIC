from django.db import migrations, models


def publish_existing_active_employees(apps, schema_editor):
    Employee = apps.get_model("accounts", "Employee")
    Employee.objects.filter(status="active").update(website_published=True)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0134_company_website_section_images"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="website_published",
            field=models.BooleanField(
                default=False,
                help_text="Show this employee on the public firm website team.",
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="website_rank",
            field=models.PositiveIntegerField(
                default=100,
                help_text="Lower numbers appear first on the public team page.",
            ),
        ),
        migrations.RunPython(
            publish_existing_active_employees,
            migrations.RunPython.noop,
        ),
    ]
