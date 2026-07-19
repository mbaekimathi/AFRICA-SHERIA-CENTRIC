# Generated manually for SEO-ready employee blog posts

import accounts.models
from django.db import migrations, models
from django.utils.text import slugify


def populate_slugs(apps, schema_editor):
    EmployeeBlogPost = apps.get_model("accounts", "EmployeeBlogPost")
    used = set(
        EmployeeBlogPost.objects.exclude(slug="")
        .exclude(slug__isnull=True)
        .values_list("slug", flat=True)
    )
    for post in EmployeeBlogPost.objects.all().iterator():
        if post.slug:
            continue
        base = slugify(post.title)[:200] or f"post-{post.pk}"
        candidate = base
        n = 2
        while candidate in used:
            suffix = f"-{n}"
            candidate = f"{base[: 220 - len(suffix)]}{suffix}"
            n += 1
        post.slug = candidate
        post.save(update_fields=["slug"])
        used.add(candidate)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0038_firm_faqs"),
    ]

    operations = [
        migrations.AddField(
            model_name="employeeblogpost",
            name="cover_image",
            field=models.ImageField(
                blank=True,
                help_text="Optional cover image for social sharing and the blog list.",
                null=True,
                upload_to=accounts.models.blog_cover_upload_to,
            ),
        ),
        migrations.AddField(
            model_name="employeeblogpost",
            name="excerpt",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Short summary shown on the blog list and used as a fallback meta description.",
                max_length=320,
            ),
        ),
        migrations.AddField(
            model_name="employeeblogpost",
            name="focus_keyword",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Primary phrase you want this post to rank for.",
                max_length=80,
            ),
        ),
        migrations.AddField(
            model_name="employeeblogpost",
            name="meta_description",
            field=models.CharField(
                blank=True,
                default="",
                help_text="SEO description (about 120–160 characters) for Google snippets.",
                max_length=160,
            ),
        ),
        migrations.AddField(
            model_name="employeeblogpost",
            name="meta_title",
            field=models.CharField(
                blank=True,
                default="",
                help_text="SEO title (about 50–60 characters). Falls back to the post title.",
                max_length=70,
            ),
        ),
        migrations.AddField(
            model_name="employeeblogpost",
            name="slug",
            field=models.SlugField(
                blank=True,
                default="",
                help_text="URL path under /blog/. Auto-generated from the title if left blank.",
                max_length=220,
            ),
        ),
        migrations.AddField(
            model_name="employeeblogpost",
            name="tags",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Comma-separated topics, e.g. employment law, contracts, Kenya.",
                max_length=240,
            ),
        ),
        migrations.RunPython(populate_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="employeeblogpost",
            name="slug",
            field=models.SlugField(
                blank=True,
                help_text="URL path under /blog/. Auto-generated from the title if left blank.",
                max_length=220,
                unique=True,
            ),
        ),
        migrations.AddIndex(
            model_name="employeeblogpost",
            index=models.Index(
                fields=["status", "-published_at"],
                name="accounts_em_status_7f2c1a_idx",
            ),
        ),
    ]
