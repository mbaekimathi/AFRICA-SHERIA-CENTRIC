from django.db import migrations, models
from django.utils.text import slugify


def populate_slugs(apps, schema_editor):
    FirmPracticeArea = apps.get_model("accounts", "FirmPracticeArea")
    FirmGalleryImage = apps.get_model("accounts", "FirmGalleryImage")

    def unique_slug(model, base, pk):
        candidate = base or "item"
        n = 2
        while model.objects.filter(slug=candidate).exclude(pk=pk).exists():
            candidate = f"{base}-{n}"
            n += 1
        return candidate

    for area in FirmPracticeArea.objects.all():
        if not (area.slug or "").strip():
            area.slug = unique_slug(
                FirmPracticeArea, slugify(area.name)[:160] or "practice-area", area.pk
            )
            area.save(update_fields=["slug"])

    for item in FirmGalleryImage.objects.all():
        if not (item.slug or "").strip():
            item.slug = unique_slug(
                FirmGalleryImage, slugify(item.title)[:160] or "gallery-item", item.pk
            )
            item.save(update_fields=["slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0042_company_terms_and_gallery"),
    ]

    operations = [
        migrations.AddField(
            model_name="firmpracticearea",
            name="slug",
            field=models.SlugField(
                blank=True,
                default="",
                help_text="Public URL slug for /practice/<slug>/",
                max_length=180,
            ),
        ),
        migrations.AddField(
            model_name="firmgalleryimage",
            name="slug",
            field=models.SlugField(
                blank=True,
                default="",
                help_text="Public URL slug for /gallery/<slug>/",
                max_length=180,
            ),
        ),
        migrations.RunPython(populate_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="firmpracticearea",
            name="slug",
            field=models.SlugField(
                blank=True,
                default="",
                help_text="Public URL slug for /practice/<slug>/",
                max_length=180,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name="firmgalleryimage",
            name="slug",
            field=models.SlugField(
                blank=True,
                default="",
                help_text="Public URL slug for /gallery/<slug>/",
                max_length=180,
                unique=True,
            ),
        ),
    ]
