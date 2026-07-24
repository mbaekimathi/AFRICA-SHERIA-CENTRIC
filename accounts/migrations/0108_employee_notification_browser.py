from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0107_employee_notification_sound_volume"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="notification_browser",
            field=models.BooleanField(
                default=True,
                help_text="Show browser desktop notifications for new unread alerts.",
            ),
        ),
    ]
