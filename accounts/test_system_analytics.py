from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from config.observability import (
    SystemObservabilityMiddleware,
    _normalised_endpoint,
)

from .models import (
    Client,
    Document,
    DocumentActivity,
    DocumentOpenSession,
    Employee,
    EmployeeBlogPost,
    GoogleDriveConnection,
    LitigationCase,
    NewsSearchJob,
    SystemRequestMetric,
)
from .system_analytics import build_system_analytics


class ObservabilityMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = Employee.objects.create_user(
            login_code="920001",
            password="test-password",
            role=Employee.Role.IT_SUPPORT,
            status=Employee.Status.ACTIVE,
        )

    def test_records_privacy_safe_request_and_query_timing(self):
        def response(request):
            Employee.objects.exists()
            return HttpResponse("ok")

        request = self.factory.get("/it-support/dashboard/cases/123/")
        request.user = self.user
        request.resolver_match = SimpleNamespace(
            view_name="accounts:workspace",
            route="<slug:role>/<path:pages>/",
            kwargs={"pages": "dashboard/cases/123"},
        )

        result = SystemObservabilityMiddleware(response)(request)

        self.assertEqual(result.status_code, 200)
        metric = SystemRequestMetric.objects.get()
        self.assertEqual(
            metric.endpoint,
            "accounts:workspace:dashboard/cases/:param",
        )
        self.assertEqual(metric.user_role, Employee.Role.IT_SUPPORT)
        self.assertGreaterEqual(metric.db_query_count, 1)
        self.assertNotIn("123", metric.endpoint)

    def test_static_and_analytics_requests_are_excluded(self):
        middleware = SystemObservabilityMiddleware(lambda request: HttpResponse("ok"))
        for path in (
            "/static/css/app.css",
            "/it-support/dashboard/system-settings/",
        ):
            request = self.factory.get(path)
            request.user = self.user
            middleware(request)

        self.assertFalse(SystemRequestMetric.objects.exists())

    def test_endpoint_normalisation_does_not_retain_unsafe_segments(self):
        request = self.factory.get("/anything/")
        request.resolver_match = SimpleNamespace(
            view_name="accounts:workspace",
            route="<slug:role>/<path:pages>/",
            kwargs={"pages": "documents/client@example.com/550e8400-e29b"},
        )
        endpoint = _normalised_endpoint(request)
        self.assertEqual(
            endpoint,
            "accounts:workspace:documents/:param/:param",
        )
        self.assertNotIn("@", endpoint)


class SystemAnalyticsTests(TestCase):
    def setUp(self):
        self.runtime = {
            "cpu_percent": 12.0,
            "process_cpu_percent": 3.0,
            "memory_percent": 42.0,
            "process_memory_mb": 120.0,
            "disk_percent": 35.0,
            "disk_free_gb": 80.0,
            "uptime_hours": 10.0,
            "db_ok": True,
            "db_latency_ms": 4.0,
        }
        self.author = Employee.objects.create_user(
            login_code="920010",
            password="test-password",
            role=Employee.Role.ADVOCATE,
            status=Employee.Status.ACTIVE,
        )

    @patch("accounts.system_analytics._runtime_snapshot")
    def test_aggregates_metrics_and_generates_recommendations(self, runtime):
        runtime.return_value = self.runtime
        SystemRequestMetric.objects.create(
            endpoint="accounts:slow",
            method="GET",
            status_code=500,
            duration_ms=1400,
            db_duration_ms=900,
            db_query_count=40,
            response_bytes=2048,
        )

        analytics = build_system_analytics("24h")

        self.assertEqual(analytics["performance"]["request_count"], 1)
        self.assertEqual(analytics["performance"]["error_rate"], 100)
        self.assertEqual(analytics["routes"][0]["endpoint"], "accounts:slow")
        levels = {item["level"] for item in analytics["recommendations"]}
        self.assertIn("critical", levels)

    @patch("accounts.system_analytics._runtime_snapshot")
    def test_tracks_scraping_and_blog_analytics(self, runtime):
        runtime.return_value = self.runtime
        now = timezone.now()
        job = NewsSearchJob.objects.create(
            requested_by=self.author,
            status=NewsSearchJob.Status.SUCCEEDED,
            progress=100,
            progress_label="Search complete",
            filters={"country_code": "KE"},
            result={
                "articles": [{"title": "One"}, {"title": "Two"}],
                "enriched_count": 1,
            },
            started_at=now - timedelta(seconds=40),
            finished_at=now - timedelta(seconds=5),
        )
        NewsSearchJob.objects.filter(pk=job.pk).update(
            created_at=now - timedelta(seconds=55)
        )
        NewsSearchJob.objects.create(
            requested_by=self.author,
            status=NewsSearchJob.Status.FAILED,
            progress=40,
            progress_label="Search failed",
            filters={"country_code": "KE"},
            error="Provider timeout",
            started_at=now - timedelta(seconds=20),
            finished_at=now - timedelta(seconds=10),
        )
        EmployeeBlogPost.objects.create(
            author=self.author,
            title="Court reforms explained",
            slug="court-reforms-explained",
            body="Body",
            status=EmployeeBlogPost.Status.DRAFT,
            focus_keyword="court reforms",
            meta_description="A short explanation of recent court reforms.",
        )
        EmployeeBlogPost.objects.create(
            author=self.author,
            title="Pending approval post",
            slug="pending-approval-post",
            body="Body",
            status=EmployeeBlogPost.Status.SUBMITTED,
            submitted_at=now - timedelta(hours=2),
        )
        SystemRequestMetric.objects.create(
            endpoint="accounts:workspace:dashboard/research-blogs/latest-news",
            method="GET",
            status_code=200,
            duration_ms=920,
            db_duration_ms=220,
            db_query_count=18,
            response_bytes=4096,
        )
        SystemRequestMetric.objects.create(
            endpoint="accounts:workspace:dashboard/my-blogs",
            method="GET",
            status_code=200,
            duration_ms=410,
            db_duration_ms=90,
            db_query_count=8,
            response_bytes=2048,
        )

        analytics = build_system_analytics("24h")

        self.assertEqual(analytics["scraping"]["job_count"], 2)
        self.assertEqual(analytics["scraping"]["successful_jobs"], 1)
        self.assertEqual(analytics["scraping"]["failed_jobs"], 1)
        self.assertEqual(analytics["scraping"]["articles_found"], 2)
        self.assertEqual(analytics["scraping"]["articles_enriched"], 1)
        self.assertGreater(analytics["scraping"]["avg_job_seconds"], 0)
        self.assertEqual(analytics["scraping"]["route_requests"], 1)
        self.assertEqual(analytics["blogs"]["created"], 2)
        self.assertEqual(analytics["blogs"]["drafts"], 1)
        self.assertEqual(analytics["blogs"]["submitted"], 1)
        self.assertEqual(analytics["blogs"]["pending_approval"], 1)
        self.assertEqual(analytics["blogs"]["seo_coverage"], 50.0)
        self.assertEqual(analytics["blogs"]["route_requests"], 1)
        titles = {item["title"] for item in analytics["recommendations"]}
        self.assertIn("Improve scrape reliability", titles)
        scrape_rec = next(
            item
            for item in analytics["recommendations"]
            if item["title"] == "Improve scrape reliability"
        )
        self.assertTrue(scrape_rec["actions"])
        self.assertTrue(scrape_rec["impact"])

    @patch("accounts.system_analytics._runtime_snapshot")
    def test_recommendations_are_actionable_for_watch_and_memory(self, runtime):
        runtime.return_value = {
            **self.runtime,
            "memory_percent": 88.0,
            "process_memory_mb": 420.0,
        }
        SystemRequestMetric.objects.create(
            endpoint="accounts:latest_news_watch_check",
            method="POST",
            status_code=202,
            duration_ms=15011,
            db_duration_ms=120,
            db_query_count=6,
            response_bytes=256,
        )
        SystemRequestMetric.objects.create(
            endpoint="accounts:workspace:dashboard",
            method="GET",
            status_code=200,
            duration_ms=640,
            db_duration_ms=180,
            db_query_count=12,
            response_bytes=2048,
        )
        NewsSearchJob.objects.create(
            requested_by=self.author,
            status=NewsSearchJob.Status.FAILED,
            progress=20,
            progress_label="Search failed",
            filters={"country_code": "KE"},
            error="Provider timeout while contacting Google News",
            finished_at=timezone.now(),
        )

        analytics = build_system_analytics("24h")
        by_title = {item["title"]: item for item in analytics["recommendations"]}

        self.assertIn("Lower system memory pressure", by_title)
        self.assertIn("Make watch/scrape checks non-blocking", by_title)
        self.assertIn("Fix failing news scrape jobs", by_title)
        self.assertIn(
            "Provider timeout",
            by_title["Fix failing news scrape jobs"]["detail"],
        )
        self.assertGreaterEqual(len(by_title["Lower system memory pressure"]["actions"]), 3)
        self.assertNotIn("Investigate slower requests", by_title)
        self.assertNotIn("Profile the slowest endpoint", by_title)

    @patch("accounts.system_analytics._runtime_snapshot")
    def test_tracks_document_connection_and_usage(self, runtime):
        runtime.return_value = self.runtime
        drive = GoogleDriveConnection.get_solo()
        drive.access_token = "token"
        drive.refresh_token = "refresh"
        drive.account_email = "drive@firm.test"
        drive.account_name = "Firm Drive"
        drive.root_folder_id = "root"
        drive.clients_folder_id = "clients"
        drive.work_folder_id = "work"
        drive.connected_at = timezone.now() - timedelta(days=3)
        drive.token_expiry = timezone.now() + timedelta(hours=6)
        drive.save()

        client = Client.objects.create(
            email="client@example.com",
            first_name="Ada",
            last_name="Client",
            status=Client.Status.ACTIVE,
        )
        case = LitigationCase.objects.create(
            filing_date=timezone.localdate(),
            client=client,
            court_rank="high_court",
            case_category="civil",
            case_type="suit",
            station="nairobi",
            status=LitigationCase.Status.ACTIVE,
        )
        document = Document.objects.create(
            case=case,
            title="Pleadings draft",
            source=Document.Source.GOOGLE_DOC,
            drive_file_id="file-1",
            uploaded_by=self.author,
            content_synced_at=timezone.now(),
        )
        DocumentActivity.objects.create(
            document=document,
            actor=self.author,
            action=DocumentActivity.Action.OPENED,
        )
        DocumentActivity.objects.create(
            document=document,
            actor=self.author,
            action=DocumentActivity.Action.CONTENT_EDITED,
        )
        DocumentOpenSession.objects.create(
            document=document,
            actor=self.author,
            kind=DocumentOpenSession.Kind.EDITING,
            duration_seconds=1800,
            ended_at=timezone.now(),
        )
        SystemRequestMetric.objects.create(
            endpoint="accounts:workspace:dashboard/document-settings",
            method="GET",
            status_code=200,
            duration_ms=880,
            db_duration_ms=140,
            db_query_count=10,
            response_bytes=1024,
        )

        analytics = build_system_analytics("24h")
        docs = analytics["documents"]

        self.assertTrue(docs["connected"])
        self.assertTrue(docs["folder_structure"])
        self.assertEqual(docs["account_email"], "drive@firm.test")
        self.assertEqual(docs["total_documents"], 1)
        self.assertEqual(docs["google_documents"], 1)
        self.assertEqual(docs["opens"], 1)
        self.assertEqual(docs["edits"], 1)
        self.assertEqual(docs["active_users"], 1)
        self.assertEqual(docs["editing_hours"], 0.5)
        self.assertFalse(docs["token_expiring_soon"])
        self.assertFalse(docs["missing_refresh_token"])
        self.assertEqual(docs["route_requests"], 1)
        titles = {item["title"] for item in analytics["recommendations"]}
        self.assertNotIn("Refresh Google Drive token soon", titles)
        self.assertNotIn("Reconnect Google Drive for lasting access", titles)

    @patch("accounts.system_analytics._runtime_snapshot")
    def test_invalid_range_falls_back_and_prunes_old_metrics(self, runtime):
        runtime.return_value = self.runtime
        old = SystemRequestMetric.objects.create(
            endpoint="accounts:old",
            method="GET",
            status_code=200,
            duration_ms=10,
        )
        SystemRequestMetric.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=31)
        )

        analytics = build_system_analytics("invalid")

        self.assertEqual(analytics["range_key"], "24h")
        self.assertFalse(SystemRequestMetric.objects.filter(pk=old.pk).exists())


class SystemAnalyticsAccessTests(TestCase):
    def _employee(self, code, role):
        return Employee.objects.create_user(
            login_code=code,
            password="test-password",
            role=role,
            status=Employee.Status.ACTIVE,
        )

    @patch("accounts.system_analytics._runtime_snapshot")
    def test_it_support_receives_analytics_dashboard(self, runtime):
        runtime.return_value = {
            "cpu_percent": 0,
            "process_cpu_percent": 0,
            "memory_percent": 0,
            "process_memory_mb": 0,
            "disk_percent": 0,
            "disk_free_gb": 0,
            "uptime_hours": 0,
            "db_ok": True,
            "db_latency_ms": 0,
        }
        user = self._employee("920002", Employee.Role.IT_SUPPORT)
        self.client.force_login(user)

        response = self.client.get(
            reverse(
                "accounts:workspace",
                kwargs={
                    "role": user.role_slug,
                    "pages": "dashboard/system-settings",
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/system_settings.html")
        self.assertContains(response, "What needs attention now")
        self.assertContains(response, "Top actions")
        self.assertContains(response, "Live resource gauges")
        self.assertContains(response, "Modules at a glance")
        self.assertContains(response, "News scraping")
        self.assertContains(response, "Google Drive")

    def test_other_roles_keep_generic_system_settings_page(self):
        user = self._employee("920003", Employee.Role.ADVOCATE)
        self.client.force_login(user)

        response = self.client.get(
            reverse(
                "accounts:workspace",
                kwargs={
                    "role": user.role_slug,
                    "pages": "dashboard/system-settings",
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/workspace_page.html")
        self.assertNotContains(response, "Developer observability")
