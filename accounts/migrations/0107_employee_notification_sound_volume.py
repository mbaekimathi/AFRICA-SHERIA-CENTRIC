from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0106_googledriveconnection_templates_forms_categories"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="notification_sound_volume",
            field=models.PositiveSmallIntegerField(
                default=70,
                help_text="Notification alert volume from 0 (mute) to 100 (loudest).",
                validators=[
                    MinValueValidator(0),
                    MaxValueValidator(100),
                ],
            ),
        ),
    ]
