from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0112_stamp_image_upload"),
    ]

    operations = [
        migrations.AddField(
            model_name="pettycashexpenserequest",
            name="payment_attachment",
            field=models.FileField(
                blank=True,
                help_text="Optional proof of payment (receipt, M-Pesa message, invoice).",
                null=True,
                upload_to="petty-cash/receipts/%Y/%m/",
            ),
        ),
    ]
