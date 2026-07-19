# Generated manually for blog submit-for-approval workflow

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0040_employee_blog_index_rename"),
    ]

    operations = [
        migrations.AddField(
            model_name="employeeblogpost",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="employeeblogpost",
            name="approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="approved_blog_posts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="employeeblogpost",
            name="submitted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="employeeblogpost",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("submitted", "Submitted"),
                    ("published", "Published"),
                ],
                default="draft",
                max_length=16,
            ),
        ),
    ]
