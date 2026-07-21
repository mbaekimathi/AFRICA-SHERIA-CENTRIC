from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0055_systemrequestmetric"),
    ]

    operations = [
        migrations.AddField(
            model_name="newswatch",
            name="frequency",
            field=models.CharField(
                choices=[
                    ("1h", "Every hour"),
                    ("6h", "Every 6 hours"),
                    ("24h", "Daily"),
                ],
                default="24h",
                max_length=8,
            ),
        ),
    ]
