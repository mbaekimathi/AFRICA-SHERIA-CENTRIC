from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Employee,
    EmployeeBlogPost,
    NewsSearchJob,
    NewsWatch,
    NewsWatchArticle,
    Notification,
)
from .news_blog import build_news_blog_draft
from .news_scraper import (
    NewsArticle,
    NewsSearchResult,
    _build_query,
    search_latest_news,
)
from .news_watch import check_news_watch, seed_watch
from .utils import render_blog_body


class NewsScraperTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = Employee.objects.create_user(
            login_code="909090",
            password="secret1",
            personal_email="researcher@example.com",
            personal_phone="+254700000000",
            id_type=Employee.IdType.CITIZEN,
            role=Employee.Role.IT_SUPPORT,
            status=Employee.Status.ACTIVE,
        )

    def test_query_contains_selected_filters(self):
        query = _build_query(
            "KE",
            "legal",
            "employment court compensation",
            "7d",
            exact_phrase="unfair termination",
            excluded_words="sports, weather",
            source_domain="judiciary.go.ke",
        )

        self.assertIn('"Kenya"', query)
        self.assertIn("(law OR legal OR courts OR justice)", query)
        # Topic keywords are ANDed, not ORed, so one weak word cannot satisfy the query.
        self.assertIn("compensation", query)
        self.assertIn("court", query)
        self.assertIn("employment", query)
        self.assertNotIn("(employment OR court OR compensation)", query)
        self.assertIn('"unfair termination"', query)
        self.assertIn("-sports", query)
        self.assertIn("site:judiciary.go.ke", query)
        self.assertIn("when:7d", query)

    @patch(
        "accounts.news_scraper._enrich_article",
        side_effect=lambda article, _terms: article,
    )
    @patch("accounts.news_scraper._fetch_feed")
    def test_search_deduplicates_and_ranks_articles(self, fetch_feed, _enrich):
        first = NewsArticle(
            title="High Court issues employment compensation ruling",
            url="https://example.test/ruling",
            source_name="Judiciary News",
            published_at="20 Jul 2026, 09:30",
            published_timestamp=1784539800,
            provider="Google News",
        )
        duplicate = NewsArticle(
            title="High Court issues employment compensation ruling",
            url="https://duplicate.test/ruling",
            source_name="Legal Daily",
            published_at="20 Jul 2026, 09:00",
            published_timestamp=1784538000,
            provider="Bing News",
        )
        unrelated = NewsArticle(
            title="Markets close higher after banking gains",
            url="https://example.test/markets",
            source_name="Business Daily",
            published_at="20 Jul 2026, 08:00",
            published_timestamp=1784534400,
            provider="Google News",
        )
        fetch_feed.side_effect = lambda provider, _url: (
            [first, unrelated] if provider == "Google News" else [duplicate]
        )

        result = search_latest_news(
            country_code="KE",
            industry="legal",
            requested_details="employment court compensation",
            period="7d",
        )

        self.assertEqual(result.country_name, "Kenya")
        self.assertEqual(len(result.articles), 1)
        self.assertEqual(result.articles[0].title, first.title)
        self.assertEqual(result.providers, ("Bing News", "Google News"))

    @patch(
        "accounts.news_scraper._enrich_article",
        side_effect=lambda article, _terms: article,
    )
    @patch("accounts.news_scraper._fetch_feed")
    def test_search_requires_topic_filters_not_just_industry(self, fetch_feed, _enrich):
        on_topic = NewsArticle(
            title="New practice management software for Kenyan law firms",
            url="https://example.test/software",
            source_name="Legal Tech Weekly",
            published_at="23 Jul 2026, 10:00",
            published_timestamp=1784800800,
            provider="Google News",
            description="Law firms adopt management software platforms.",
        )
        industry_only = NewsArticle(
            title="Lawyers announce nationwide court boycotts",
            url="https://example.test/boycott",
            source_name="The Star",
            published_at="23 Jul 2026, 09:00",
            published_timestamp=1784797200,
            provider="Google News",
        )
        weak_keyword = NewsArticle(
            title="Kenya mangrove restoration management drive",
            url="https://example.test/mangrove",
            source_name="Eastleigh Voice",
            published_at="23 Jul 2026, 08:00",
            published_timestamp=1784793600,
            provider="Bing News",
        )
        fetch_feed.side_effect = lambda provider, _url: (
            [on_topic, industry_only]
            if provider == "Google News"
            else [weak_keyword]
        )

        result = search_latest_news(
            country_code="KE",
            industry="legal",
            requested_details="management softwares for lawfirms",
            period="7d",
        )

        self.assertEqual([article.title for article in result.articles], [on_topic.title])
        self.assertIn("software", " ".join(result.articles[0].match_reasons).lower() + on_topic.title.lower())

    @patch(
        "accounts.news_scraper._enrich_article",
        side_effect=lambda article, _terms: article,
    )
    @patch("accounts.news_scraper._fetch_feed")
    def test_exact_phrase_and_period_filters_drop_non_matches(self, fetch_feed, _enrich):
        matching = NewsArticle(
            title="Court rules on unfair termination claims",
            url="https://example.test/phrase",
            source_name="Legal Daily",
            published_at="23 Jul 2026, 10:00",
            published_timestamp=1784800800,
            provider="Google News",
            description="The bench addressed unfair termination and employment compensation evidence.",
        )
        missing_phrase = NewsArticle(
            title="Court rules on employment compensation claims",
            url="https://example.test/no-phrase",
            source_name="Legal Daily",
            published_at="23 Jul 2026, 09:30",
            published_timestamp=1784799000,
            provider="Google News",
            description="Compensation factors were clarified.",
        )
        too_old = NewsArticle(
            title="Older note on unfair termination policy",
            url="https://example.test/old",
            source_name="Legal Daily",
            published_at="01 Jan 2020, 09:00",
            published_timestamp=1577869200,
            provider="Bing News",
        )
        fetch_feed.side_effect = lambda provider, _url: (
            [matching, missing_phrase] if provider == "Google News" else [too_old]
        )

        result = search_latest_news(
            country_code="KE",
            industry="legal",
            requested_details="employment court compensation",
            period="7d",
            exact_phrase="unfair termination",
        )

        self.assertEqual([article.title for article in result.articles], [matching.title])
        self.assertIn("Contains the exact phrase", result.articles[0].match_reasons)

    @patch("accounts.news_jobs.launch_news_search")
    def test_job_endpoints_start_report_and_cancel(self, launch):
        self.client.force_login(self.user)
        start_url = reverse(
            "accounts:latest_news_job_start",
            kwargs={"role": self.user.role_slug},
        )
        response = self.client.post(
            start_url,
            {
                "country": "KE",
                "industry": "legal",
                "period": "7d",
                "language": "en",
                "sort_by": "relevance",
                "requested_details": "employment court compensation",
                "exact_phrase": "",
                "excluded_words": "",
                "source_domain": "",
            },
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 202)
        job = NewsSearchJob.objects.get(requested_by=self.user)
        launch.assert_called_once_with(job.pk)

        status_url = reverse(
            "accounts:latest_news_job_status",
            kwargs={"role": self.user.role_slug, "job_id": job.pk},
        )
        status_response = self.client.get(status_url)
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["progress"], 0)

        cancel_url = reverse(
            "accounts:latest_news_job_cancel",
            kwargs={"role": self.user.role_slug, "job_id": job.pk},
        )
        cancel_response = self.client.post(cancel_url)
        self.assertEqual(cancel_response.status_code, 200)
        job.refresh_from_db()
        self.assertTrue(job.cancel_requested)
        self.assertEqual(job.status, NewsSearchJob.Status.CANCELLED)

    def test_build_news_blog_draft_is_attributed_and_editor_ready(self):
        initial, source = build_news_blog_draft(
            article={
                "title": "Court clarifies compensation in employment disputes",
                "url": "https://publisher.example/employment-ruling",
                "source_name": "Legal Daily",
                "published_at": "21 Jul 2026",
                "description": "The court explained the factors relevant to compensation.",
                "passages": ["The decision identifies evidence the parties should preserve."],
            },
            filters={
                "requested_details": "employment compensation",
                "industry": "legal",
            },
            country_name="Kenya",
        )

        self.assertIn("Source: Legal Daily", initial["body"])
        self.assertIn(
            "https://publisher.example/employment-ruling", initial["body"]
        )
        self.assertGreaterEqual(len(initial["body"].split()), 300)
        self.assertEqual(initial["status"], "draft")
        self.assertEqual(source["source_name"], "Legal Daily")
        checks = {
            check["id"]: check["ok"]
            for check in EmployeeBlogPost(**initial).seo_checklist()["checks"]
        }
        for check_id in (
            "title_length",
            "meta_title",
            "meta_description",
            "focus_keyword",
            "keyword_in_title",
            "keyword_in_meta",
            "keyword_in_body",
            "headings",
            "source_link",
            "slug",
            "keyword_in_slug",
            "tags",
        ):
            self.assertTrue(checks[check_id], check_id)
        self.assertEqual(source["facts_count"], 2)

    def test_blog_renderer_supports_safe_editor_formatting(self):
        html, _toc = render_blog_body(
            "## Update\n\n**Important** and *clear*.\n\n"
            "> Verify this.\n\n[Source](https://example.com/report)"
        )

        self.assertIn("<strong>Important</strong>", html)
        self.assertIn("<em>clear</em>", html)
        self.assertIn("<blockquote>Verify this.</blockquote>", html)
        self.assertIn('href="https://example.com/report"', html)

    def test_selected_news_generates_prefilled_blog_editor(self):
        self.client.force_login(self.user)
        job = NewsSearchJob.objects.create(
            requested_by=self.user,
            status=NewsSearchJob.Status.SUCCEEDED,
            progress=100,
            filters={
                "country": "KE",
                "industry": "legal",
                "requested_details": "employment compensation",
            },
            result={
                "articles": [
                    {
                        "title": "Court clarifies employment compensation",
                        "url": "https://publisher.example/ruling",
                        "source_name": "Legal Daily",
                        "published_at": "21 Jul 2026",
                        "description": "A new decision explains compensation factors.",
                        "passages": [],
                    }
                ]
            },
        )
        generate_url = reverse(
            "accounts:latest_news_blog_draft",
            kwargs={
                "role": self.user.role_slug,
                "job_id": job.pk,
                "article_index": 0,
            },
        )

        response = self.client.post(generate_url)

        self.assertRedirects(
            response,
            self.user.workspace_url("dashboard", "my-blogs-new"),
            fetch_redirect_response=False,
        )
        editor = self.client.get(response.url)
        self.assertContains(editor, "News-based draft generated")
        self.assertContains(editor, "Legal Daily")
        self.assertContains(editor, "employment compensation")

    def test_completed_search_can_be_saved_as_daily_watch(self):
        self.client.force_login(self.user)
        article = {
            "title": "Court issues employment decision",
            "url": "https://publisher.example/ruling",
            "source_name": "Legal Daily",
            "published_at": "21 Jul 2026",
            "description": "The court issued a new decision.",
        }
        job = NewsSearchJob.objects.create(
            requested_by=self.user,
            status=NewsSearchJob.Status.SUCCEEDED,
            filters={
                "country_code": "KE",
                "industry": "legal",
                "requested_details": "employment decision",
                "period": "7d",
                "language": "en",
                "sort_by": "relevance",
                "exact_phrase": "",
                "excluded_words": "",
                "source_domain": "",
            },
            result={"articles": [article]},
        )

        response = self.client.post(
            reverse(
                "accounts:latest_news_watch_search",
                kwargs={"role": self.user.role_slug, "job_id": job.pk},
            )
        )

        self.assertEqual(response.status_code, 302)
        watch = NewsWatch.objects.get(requested_by=self.user)
        self.assertEqual(watch.kind, NewsWatch.Kind.SEARCH)
        self.assertIsNotNone(watch.next_check_at)
        self.assertEqual(watch.articles.count(), 1)
        self.assertEqual(Notification.objects.count(), 0)

    def test_each_watch_can_have_its_own_frequency(self):
        self.client.force_login(self.user)
        hourly = NewsWatch.objects.create(
            requested_by=self.user,
            kind=NewsWatch.Kind.SEARCH,
            name="Hourly court updates",
            key="hourly-courts",
            filters={},
        )
        daily = NewsWatch.objects.create(
            requested_by=self.user,
            kind=NewsWatch.Kind.PUBLISHER,
            name="Daily publisher",
            key="daily-publisher",
            filters={},
        )

        response = self.client.post(
            reverse(
                "accounts:latest_news_watch_update",
                kwargs={"role": self.user.role_slug, "watch_id": hourly.pk},
            ),
            {"frequency": NewsWatch.Frequency.HOURLY},
        )

        self.assertEqual(response.status_code, 302)
        hourly.refresh_from_db()
        daily.refresh_from_db()
        self.assertEqual(hourly.frequency, NewsWatch.Frequency.HOURLY)
        self.assertEqual(daily.frequency, NewsWatch.Frequency.DAILY)
        self.assertLess(hourly.next_check_at, timezone.now() + timedelta(hours=2))

    @patch("accounts.news_watch._executor.submit")
    def test_user_can_trigger_watch_manually(self, submit):
        self.client.force_login(self.user)
        watch = NewsWatch.objects.create(
            requested_by=self.user,
            kind=NewsWatch.Kind.SEARCH,
            name="Manual court watch",
            key="manual-watch",
            filters={
                "country_code": "KE",
                "industry": "legal",
                "requested_details": "employment",
                "period": "7d",
            },
            next_check_at=timezone.now() + timedelta(days=1),
        )

        response = self.client.post(
            reverse(
                "accounts:latest_news_watch_check",
                kwargs={"role": self.user.role_slug, "watch_id": watch.pk},
            ),
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertIn("status_url", payload)
        self.assertIn("cancel_url", payload)
        submit.assert_called_once()
        watch.refresh_from_db()
        self.assertIsNotNone(watch.check_started_at)

        status = self.client.get(payload["status_url"])
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "running")

    @patch("accounts.news_watch.search_latest_news")
    def test_daily_watch_notifies_only_for_new_articles(self, search):
        self.client.force_login(self.user)
        watch = NewsWatch.objects.create(
            requested_by=self.user,
            kind=NewsWatch.Kind.PUBLISHER,
            name="Legal Daily",
            key="publisher-watch",
            filters={
                "country_code": "KE",
                "industry": "legal",
                "requested_details": "employment",
                "period": "7d",
                "source_domain": "publisher.example",
            },
            publisher_domain="publisher.example",
        )
        old = {
            "title": "Existing report",
            "url": "https://publisher.example/old",
            "source_name": "Legal Daily",
            "published_at": "20 Jul 2026",
        }
        seed_watch(watch, [old])
        new = NewsArticle(
            title="New employment update",
            url="https://publisher.example/new",
            source_name="Legal Daily",
            published_at="21 Jul 2026",
            published_timestamp=1784610000,
            provider="Google News",
        )
        existing = NewsArticle(
            title=old["title"],
            url=old["url"],
            source_name=old["source_name"],
            published_at=old["published_at"],
            published_timestamp=1784523600,
            provider="Google News",
        )
        search.return_value = NewsSearchResult(
            country_code="KE",
            country_name="Kenya",
            industry="legal",
            requested_details="employment",
            period="7d",
            query="employment",
            articles=[existing, new],
            retrieved_at="21 Jul 2026",
            providers=("Google News",),
            enriched_count=0,
        )

        self.assertEqual(check_news_watch(watch.pk), 1)
        self.assertEqual(check_news_watch(watch.pk), 0)
        self.assertEqual(NewsWatchArticle.objects.filter(watch=watch).count(), 2)
        notification = Notification.objects.get(recipient=self.user)
        self.assertIn("New employment update", notification.title)
        self.assertIn(f"?watch={watch.pk}&article=", notification.target_url)
        watch_list = self.client.get(
            self.user.workspace_url(
                "dashboard", "research", "latest-news"
            )
        )
        self.assertContains(watch_list, "news-watch__notification")
        self.assertContains(watch_list, "1 unread news update")

        self.client.get(notification.target_url)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_watch_results_prefill_form_and_expose_actions(self):
        self.client.force_login(self.user)
        from .news_watch import remember_article

        watch = NewsWatch.objects.create(
            requested_by=self.user,
            kind=NewsWatch.Kind.SEARCH,
            name="Employment updates",
            key="watch-actions",
            filters={
                "country_code": "KE",
                "industry": "legal",
                "requested_details": "employment compensation awards",
                "period": "7d",
                "language": "en",
                "sort_by": "relevance",
                "exact_phrase": "unfair dismissal",
                "excluded_words": "",
                "source_domain": "",
            },
        )
        article = {
            "title": "Court clarifies unfair dismissal awards",
            "url": "https://publisher.example/awards",
            "source_name": "Legal Daily",
            "published_at": "24 Jul 2026",
            "description": "The court clarified compensation factors.",
            "passages": [],
            "relevance_score": 82,
            "credibility_score": 16,
        }
        seen = {
            "title": "Older employment report",
            "url": "https://publisher.example/old",
            "source_name": "Legal Daily",
            "published_at": "20 Jul 2026",
            "description": "Earlier coverage.",
            "passages": [],
            "relevance_score": 40,
            "credibility_score": 10,
        }
        item, _ = remember_article(watch, article)
        remember_article(watch, seen)
        notification = Notification.objects.create(
            recipient=self.user,
            category=Notification.Category.MESSAGE,
            title=f"News update: {item.title}",
            body="New update",
            target_url=(
                f"{self.user.workspace_url('dashboard', 'research', 'latest-news')}"
                f"?watch={watch.pk}&article={item.pk}"
            ),
            source_key=f"news_watch:{watch.pk}:{item.fingerprint[:32]}",
        )

        new_only = self.client.get(
            f"{self.user.workspace_url('dashboard', 'research', 'latest-news')}"
            f"?watch={watch.pk}&new=1"
        )
        self.assertEqual(new_only.status_code, 200)
        self.assertContains(new_only, "Court clarifies unfair dismissal awards")
        self.assertNotContains(new_only, "Older employment report")
        self.assertContains(new_only, "news-article__badge")
        self.assertContains(new_only, "Create blog draft")

        notification.is_read = False
        notification.read_at = None
        notification.save(update_fields=["is_read", "read_at"])

        page = self.client.get(
            f"{self.user.workspace_url('dashboard', 'research', 'latest-news')}"
            f"?watch={watch.pk}&article={item.pk}"
        )

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "employment compensation awards")
        self.assertContains(page, "unfair dismissal")
        self.assertContains(page, "news-article__badge")
        self.assertContains(page, "New only")
        self.assertContains(page, "Create blog draft")
        self.assertContains(page, "Watch publisher")
        self.assertContains(page, "news-article--focused")
        self.assertContains(
            page,
            reverse(
                "accounts:latest_news_watch_article_blog_draft",
                kwargs={
                    "role": self.user.role_slug,
                    "watch_id": watch.pk,
                    "article_id": item.pk,
                },
            ),
        )

        draft = self.client.post(
            reverse(
                "accounts:latest_news_watch_article_blog_draft",
                kwargs={
                    "role": self.user.role_slug,
                    "watch_id": watch.pk,
                    "article_id": item.pk,
                },
            )
        )
        self.assertRedirects(
            draft,
            self.user.workspace_url("dashboard", "my-blogs-new"),
            fetch_redirect_response=False,
        )

        publisher = self.client.post(
            reverse(
                "accounts:latest_news_watch_article_publisher",
                kwargs={
                    "role": self.user.role_slug,
                    "watch_id": watch.pk,
                    "article_id": item.pk,
                },
            )
        )
        self.assertEqual(publisher.status_code, 302)
        self.assertTrue(
            NewsWatch.objects.filter(
                requested_by=self.user,
                kind=NewsWatch.Kind.PUBLISHER,
                publisher_domain="publisher.example",
            ).exists()
        )

    def test_job_results_prefill_search_filters(self):
        self.client.force_login(self.user)
        job = NewsSearchJob.objects.create(
            requested_by=self.user,
            status=NewsSearchJob.Status.SUCCEEDED,
            filters={
                "country_code": "KE",
                "industry": "finance",
                "requested_details": "central bank rate decision",
                "period": "30d",
                "language": "en",
                "sort_by": "newest",
                "exact_phrase": "",
                "excluded_words": "",
                "source_domain": "reuters.com",
            },
            result={"articles": []},
        )

        page = self.client.get(
            f"{self.user.workspace_url('dashboard', 'research', 'latest-news')}"
            f"?job={job.pk}"
        )

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "central bank rate decision")
        self.assertContains(page, 'value="reuters.com"')
        self.assertContains(page, 'option value="finance" selected')
        self.assertContains(page, 'option value="30d" selected')
