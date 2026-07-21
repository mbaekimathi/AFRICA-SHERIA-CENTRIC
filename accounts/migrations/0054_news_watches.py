import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0053_newssearchjob"),
    ]

    operations = [
        migrations.CreateModel(
            name="NewsWatch",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("search", "Saved search"),
                            ("publisher", "Publisher"),
                        ],
                        max_length=16,
                    ),
                ),
                ("name", models.CharField(max_length=180)),
                ("key", models.CharField(max_length=64)),
                ("filters", models.JSONField(default=dict)),
                (
                    "publisher_domain",
                    models.CharField(blank=True, default="", max_length=180),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("last_checked_at", models.DateTimeField(blank=True, null=True)),
                ("next_check_at", models.DateTimeField(blank=True, null=True)),
                ("check_started_at", models.DateTimeField(blank=True, null=True)),
                (
                    "last_error",
                    models.CharField(blank=True, default="", max_length=500),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "requested_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="news_watches",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["is_active", "next_check_at"],
                        name="news_watch_due_idx",
                    ),
                    models.Index(
                        fields=["requested_by", "is_active"],
                        name="news_watch_owner_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("requested_by", "key"),
                        name="unique_employee_news_watch",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="NewsWatchArticle",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("fingerprint", models.CharField(max_length=64)),
                ("title", models.CharField(max_length=500)),
                ("url", models.URLField(max_length=1000)),
                (
                    "source_name",
                    models.CharField(blank=True, default="", max_length=180),
                ),
                (
                    "published_at",
                    models.CharField(blank=True, default="", max_length=100),
                ),
                ("description", models.TextField(blank=True, default="")),
                ("article_data", models.JSONField(blank=True, default=dict)),
                ("first_seen_at", models.DateTimeField(auto_now_add=True)),
                ("notified_at", models.DateTimeField(blank=True, null=True)),
                (
                    "watch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="articles",
                        to="accounts.newswatch",
                    ),
                ),
            ],
            options={
                "ordering": ["-first_seen_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["watch", "-first_seen_at"],
                        name="news_watch_article_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("watch", "fingerprint"),
                        name="unique_news_watch_article",
                    )
                ],
            },
        ),
    ]
