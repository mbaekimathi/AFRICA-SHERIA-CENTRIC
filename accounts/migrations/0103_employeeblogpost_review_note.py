from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0102_invoice_due_date_optional"),
    ]

    operations = [
        migrations.AddField(
            model_name="employeeblogpost",
            name="review_note",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Optional feedback when a reviewer returns or unpublishes a post.",
            ),
        ),
    ]
