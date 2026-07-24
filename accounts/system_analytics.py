from collections import defaultdict
from datetime import timedelta
from statistics import mean
from time import perf_counter

import psutil
from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import connection
from django.db.models import Count, Sum
from django.utils import timezone

from .models import (
    CaseTask,
    Client,
    ClientNotification,
    Document,
    DocumentActivity,
    DocumentOpenSession,
    Employee,
    EmployeeBlogPost,
    GoogleDriveConnection,
    LitigationCase,
    MatterTask,
    MpesaStkRequest,
    NewsSearchJob,
    NewsWatch,
    NewsWatchArticle,
    NonLitigationMatter,
    Notification,
    SystemRequestMetric,
)


RANGES = {
    "24h": ("Last 24 hours", timedelta(hours=24), "hour"),
    "7d": ("Last 7 days", timedelta(days=7), "day"),
    "30d": ("Last 30 days", timedelta(days=30), "day"),
}
RETENTION_DAYS = 30


def _percentile(values, percentile):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _average(values):
    return mean(values) if values else 0.0


def _bucket_start(value, grain):
    value = timezone.localtime(value)
    if grain == "hour":
        return value.replace(minute=0, second=0, microsecond=0)
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _read_latency_hours(model, start):
    rows = model.objects.filter(
        created_at__gte=start,
        read_at__isnull=False,
    ).values_list("created_at", "read_at")
    values = [
        max(0, (read_at - created_at).total_seconds() / 3600)
        for created_at, read_at in rows
    ]
    return _average(values)


def _runtime_snapshot():
    process = psutil.Process()
    disk = psutil.disk_usage(str(settings.BASE_DIR))
    memory = psutil.virtual_memory()
    db_started = perf_counter()
    db_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        db_ok = False
    db_latency_ms = (perf_counter() - db_started) * 1000
    uptime_seconds = max(0, timezone.now().timestamp() - process.create_time())
    return {
        "cpu_percent": round(psutil.cpu_percent(interval=None), 1),
        "process_cpu_percent": round(process.cpu_percent(interval=None), 1),
        "memory_percent": round(memory.percent, 1),
        "process_memory_mb": round(process.memory_info().rss / (1024 * 1024), 1),
        "disk_percent": round(disk.percent, 1),
        "disk_free_gb": round(disk.free / (1024**3), 1),
        "uptime_hours": round(uptime_seconds / 3600, 1),
        "db_ok": db_ok,
        "db_latency_ms": round(db_latency_ms, 1),
    }


def _route_analytics(rows):
    grouped = defaultdict(
        lambda: {
            "requests": 0,
            "durations": [],
            "db_durations": [],
            "query_counts": [],
            "errors": 0,
        }
    )
    for row in rows:
        route = grouped[row["endpoint"]]
        route["requests"] += 1
        route["durations"].append(row["duration_ms"])
        route["db_durations"].append(row["db_duration_ms"])
        route["query_counts"].append(row["db_query_count"])
        route["errors"] += int(row["status_code"] >= 500)

    result = []
    for endpoint, values in grouped.items():
        result.append(
            {
                "endpoint": endpoint,
                "requests": values["requests"],
                "p95_ms": round(_percentile(values["durations"], 0.95), 1),
                "avg_ms": round(_average(values["durations"]), 1),
                "avg_db_ms": round(_average(values["db_durations"]), 1),
                "avg_queries": round(_average(values["query_counts"]), 1),
                "error_rate": round(
                    values["errors"] * 100 / values["requests"],
                    1,
                ),
            }
        )
    return sorted(
        result,
        key=lambda item: (item["p95_ms"], item["requests"]),
        reverse=True,
    )[:10]


def _job_article_counts(jobs):
    articles = 0
    enriched = 0
    for result in jobs.filter(status=NewsSearchJob.Status.SUCCEEDED).values_list(
        "result", flat=True
    ):
        if not isinstance(result, dict):
            continue
        articles += len(result.get("articles") or [])
        try:
            enriched += int(result.get("enriched_count") or 0)
        except (TypeError, ValueError):
            continue
    return articles, enriched


def _module_route_stats(rows, markers):
    matched = [
        row
        for row in rows
        if any(marker in (row.get("endpoint") or "") for marker in markers)
    ]
    if not matched:
        return {
            "requests": 0,
            "p95_ms": 0.0,
            "avg_ms": 0.0,
            "error_rate": 0.0,
            "avg_queries": 0.0,
        }
    durations = [row["duration_ms"] for row in matched]
    errors = sum(1 for row in matched if row["status_code"] >= 500)
    return {
        "requests": len(matched),
        "p95_ms": round(_percentile(durations, 0.95), 1),
        "avg_ms": round(_average(durations), 1),
        "error_rate": round(errors * 100 / len(matched), 1),
        "avg_queries": round(
            _average([row["db_query_count"] for row in matched]),
            1,
        ),
    }


LONG_RUNNING_ENDPOINTS = (
    "latest_news_watch_check",
    "latest_news_job",
    "latest_news_watch_status",
)


def _is_long_running_endpoint(endpoint):
    value = endpoint or ""
    return any(marker in value for marker in LONG_RUNNING_ENDPOINTS)


def _format_duration(ms):
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms:.0f} ms"


def _format_endpoint(endpoint):
    value = (endpoint or "").replace("accounts:", "")
    return value or "unknown endpoint"


def _recent_job_errors(start, limit=3):
    rows = (
        NewsSearchJob.objects.filter(
            status=NewsSearchJob.Status.FAILED,
            created_at__gte=start,
        )
        .exclude(error="")
        .order_by("-finished_at", "-id")
        .values_list("error", flat=True)[:limit]
    )
    cleaned = []
    seen = set()
    for error in rows:
        text = " ".join(str(error).split())
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text[:140])
    return cleaned


def _recommendations(
    performance,
    runtime,
    routes,
    operations,
    scraping,
    blogs,
    documents,
    *,
    recent_job_errors=None,
):
    recommendations = []

    def add(level, title, detail, *, impact="", actions=None):
        recommendations.append(
            {
                "level": level,
                "title": title,
                "detail": detail,
                "impact": impact,
                "actions": actions or [],
            }
        )

    interactive_routes = [
        route for route in routes if not _is_long_running_endpoint(route["endpoint"])
    ]
    slowest_interactive = interactive_routes[0] if interactive_routes else None
    slowest_background = next(
        (route for route in routes if _is_long_running_endpoint(route["endpoint"])),
        None,
    )
    # Prefer interactive-only guidance when long-running scrape endpoints dominate.
    background_skew = bool(slowest_background and performance["p95_ms"] > 1000)

    if not performance["request_count"]:
        add(
            "info",
            "Telemetry is warming up",
            "No request samples are available yet for this range.",
            impact="Charts and route diagnostics stay empty until traffic is recorded.",
            actions=[
                "Browse the workspace and Latest News normally for a few minutes.",
                "Return to this page and switch between 24h / 7d to confirm trends.",
            ],
        )

    if runtime["memory_percent"] > 85:
        add(
            "critical",
            "Lower system memory pressure",
            (
                f"Host memory is at {runtime['memory_percent']:.0f}% "
                f"({runtime['process_memory_mb']:.0f} MB used by this Django process)."
            ),
            impact="High memory use slows every request and raises the risk of process crashes during scrapes.",
            actions=[
                "Restart the app process if this is a long-lived local runserver session.",
                "Limit Latest News result size and avoid keeping large HTML/article payloads in memory.",
                "Check for unbounded lists in scrapers, blog drafts, and notification payloads.",
                "If memory stays high after restart, inspect the slowest routes for large queryset materialisation.",
            ],
        )

    if runtime["disk_percent"] > 85:
        add(
            "critical",
            "Free disk capacity",
            (
                f"Disk usage is {runtime['disk_percent']:.0f}%, with only "
                f"{runtime['disk_free_gb']:.1f} GB free."
            ),
            impact="Low disk space breaks uploads, logs, scrapes, and database writes.",
            actions=[
                "Clear old media/temp files and rotate application logs.",
                "Prune retained telemetry older than 30 days if the table has grown large.",
            ],
        )

    if performance["error_rate"] > 2:
        add(
            "critical",
            "Resolve server errors",
            f"{performance['error_rate']:.1f}% of measured requests returned HTTP 5xx ({performance['error_count']} responses).",
            impact="Users see failed actions and scrapes/jobs stop completing reliably.",
            actions=[
                "Filter the slowest/error-prone routes table for 5xx responses.",
                "Reproduce the failing endpoint and capture the exception from the runserver log.",
                "Add guarding for missing relations and external API timeouts.",
            ],
        )

    if slowest_background and slowest_background["p95_ms"] > 3000:
        endpoint = _format_endpoint(slowest_background["endpoint"])
        add(
            "warning",
            "Make watch/scrape checks non-blocking",
            (
                f"`{endpoint}` has a p95 of {_format_duration(slowest_background['p95_ms'])} "
                f"across {slowest_background['requests']} calls."
            ),
            impact="Manual watch checks that block the HTTP request inflate latency and freeze the Latest News UI.",
            actions=[
                "Ensure watch checks only launch work and return 202 immediately.",
                "Move provider scraping fully into the background worker/thread and poll status endpoints.",
                "Add timeouts around each news provider so one slow source cannot hold the request open.",
                "Cache repeated publisher lookups and avoid re-fetching unchanged articles.",
            ],
        )

    if not background_skew and performance["p95_ms"] > 1000:
        add(
            "critical",
            "Cut interactive response latency",
            f"Overall p95 is {_format_duration(performance['p95_ms'])}, well above the 500 ms target.",
            impact="Workspace navigation and forms feel sluggish for every role.",
            actions=[
                "Start with the top interactive routes by p95 and average DB time.",
                "Add select_related/prefetch_related where query counts are high.",
                "Defer expensive analytics/scraping work off the request path.",
            ],
        )
    elif not background_skew and performance["p95_ms"] > 500:
        add(
            "warning",
            "Interactive pages are slower than target",
            f"Overall p95 is {_format_duration(performance['p95_ms'])} (target ≤ 500 ms).",
            impact="Frequent workspace actions feel delayed, especially under concurrent use.",
            actions=[
                "Compare p50 vs p95 to see whether a few outliers are dragging the tail.",
                "Optimise the slowest interactive endpoint first before broad changes.",
            ],
        )
    elif background_skew and slowest_interactive and slowest_interactive["p95_ms"] > 500:
        add(
            "warning",
            "Interactive pages are slower than target",
            (
                f"After excluding long-running scrape endpoints, interactive p95 is "
                f"{_format_duration(slowest_interactive['p95_ms'])}."
            ),
            impact="Users still feel delay even though scrape jobs explain most of the overall latency spike.",
            actions=[
                f"Profile `{_format_endpoint(slowest_interactive['endpoint'])}` separately from watch checks.",
                "Keep scrape work on async endpoints so interactive pages stay under 500 ms.",
            ],
        )

    if (
        slowest_interactive
        and slowest_interactive["p95_ms"] > 750
        and not _is_long_running_endpoint(slowest_interactive["endpoint"])
    ):
        endpoint = _format_endpoint(slowest_interactive["endpoint"])
        add(
            "warning",
            "Optimise the slowest interactive endpoint",
            (
                f"`{endpoint}` averages {slowest_interactive['avg_queries']:.0f} queries and "
                f"{_format_duration(slowest_interactive['avg_db_ms'])} DB time, "
                f"with p95 {_format_duration(slowest_interactive['p95_ms'])}."
            ),
            impact="This route is the main interactive bottleneck for the selected range.",
            actions=[
                "Inspect the view for N+1 queries and missing select_related/prefetch_related.",
                "Cache stable lookup data and paginate large result sets.",
                "Move heavy aggregation into the analytics service rather than the page view.",
            ],
        )

    if performance["avg_db_ratio"] > 60:
        add(
            "warning",
            "Database work dominates request time",
            f"Database time is {performance['avg_db_ratio']:.0f}% of average request duration ({performance['avg_db_ms']:.0f} ms DB / request).",
            impact="CPU waits on SQL, so page rendering cannot get faster until queries improve.",
            actions=[
                "Review indexes on filtered/sorted columns used by slow routes.",
                "Replace broad .all() loads with values()/only() where full models are unnecessary.",
            ],
        )

    if performance["avg_queries"] > 25:
        add(
            "warning",
            "Reduce queries per request",
            f"Requests average {performance['avg_queries']:.1f} database queries.",
            impact="High query counts amplify latency and memory use under concurrency.",
            actions=[
                "Hunt N+1 patterns in templates and serializers.",
                "Prefetch related collections used in loops (tasks, parties, notifications).",
            ],
        )

    if operations["failed_jobs"]:
        errors = recent_job_errors or []
        detail = (
            f"{operations['failed_jobs']} Latest News scrape jobs failed in this period."
        )
        if errors:
            detail += " Recent errors: " + " | ".join(errors)
        add(
            "warning",
            "Fix failing news scrape jobs",
            detail,
            impact="Failed scrapes reduce article coverage and leave watches/jobs in a broken state.",
            actions=[
                "Open Latest News and retry a failed search while watching the job error text.",
                "Add provider-level timeouts and clearer error classification (network vs parse vs cancel).",
                "Skip or circuit-break providers that repeatedly fail within the same window.",
            ],
        )

    if operations["watch_errors"]:
        add(
            "warning",
            "Repair scheduled news watches",
            f"{operations['watch_errors']} active watches currently store a last_error.",
            impact="Broken watches stop discovering new articles and miss firm monitoring alerts.",
            actions=[
                "Run a manual check on each failing watch and capture the provider error.",
                "Disable stale watches or widen filters if publishers repeatedly return empty/error responses.",
            ],
        )

    if scraping["job_count"] and scraping["success_rate"] < 80:
        add(
            "warning",
            "Improve scrape reliability",
            f"Only {scraping['success_rate']:.0f}% of news scrapes succeeded ({scraping['successful_jobs']}/{scraping['job_count']}).",
            impact="Researchers and blog drafts get incomplete source material.",
            actions=[
                "Compare cancelled vs failed counts to separate user cancels from true provider failures.",
                "Log provider success rates so one unstable source cannot sink the whole job.",
            ],
        )

    if scraping["p95_job_seconds"] > 90:
        add(
            "warning",
            "Speed up news scraping",
            f"p95 scrape duration is {scraping['p95_job_seconds']:.0f}s (avg {scraping['avg_job_seconds']:.0f}s).",
            impact="Long scrapes hold workers, increase memory use, and delay blog drafting.",
            actions=[
                "Parallelise providers with hard per-provider timeouts.",
                "Enrich only the top-ranked articles instead of every result.",
                "Cache publisher responses briefly to avoid repeat downloads.",
            ],
        )

    if scraping["avg_queue_seconds"] > 20:
        add(
            "info",
            "Reduce scrape queue wait",
            f"Jobs wait {scraping['avg_queue_seconds']:.0f}s on average before starting.",
            impact="Users perceive Latest News as stuck even before scraping begins.",
            actions=[
                "Confirm the thread/worker pool is not saturated by concurrent watch checks.",
                "Reject or queue overflow jobs instead of blocking the launch request.",
            ],
        )

    if scraping["route_p95_ms"] > 800 and not background_skew:
        add(
            "warning",
            "Profile Latest News pages",
            f"News workspace routes have a p95 of {_format_duration(scraping['route_p95_ms'])}.",
            impact="Opening Latest News feels slow before any scrape starts.",
            actions=[
                "Lazy-load watch lists and job history.",
                "Avoid re-serializing large previous result payloads on every page render.",
            ],
        )

    if blogs["pending_approval"] > 5:
        add(
            "info",
            "Clear blog approval backlog",
            f"{blogs['pending_approval']} posts are awaiting approval.",
            impact="Content sits unpublished and authors lose feedback latency signals.",
            actions=[
                "Review submitted posts in Company Blogs / Research & Blogs.",
                "Publish or return drafts with SEO guidance where meta fields are empty.",
            ],
        )

    if blogs["created"] and blogs["seo_coverage"] < 60:
        add(
            "info",
            "Improve blog SEO completeness",
            f"Only {blogs['seo_coverage']:.0f}% of recent posts have both a focus keyword and meta description.",
            impact="Published posts underperform in search snippets and social previews.",
            actions=[
                "Require focus keyword + meta description before submit.",
                "Reuse the SEO coach checklist already shown in the blog editor.",
            ],
        )

    if blogs["route_p95_ms"] > 800:
        add(
            "warning",
            "Profile blog editor routes",
            f"Blog workspace routes have a p95 of {_format_duration(blogs['route_p95_ms'])}.",
            impact="Authors wait longer while drafting and submitting posts.",
            actions=[
                "Defer SEO analysis and preview rendering until after the initial page paint.",
                "Ensure blog list queries are indexed by status and updated_at.",
            ],
        )

    if not documents["connected"]:
        add(
            "critical",
            "Reconnect Google Drive",
            "Document Settings has no active Google Drive connection.",
            impact="Staff cannot create Google Docs, sync content, or browse Drive-backed matter files.",
            actions=[
                "Open Document Settings and complete Google OAuth for the firm account.",
                "Confirm the connected account has permission to create firm folders.",
            ],
        )
    elif not documents["folder_structure"]:
        add(
            "warning",
            "Bootstrap Drive folder structure",
            "Google Drive is connected, but the firm Clients/Employees folder tree is incomplete.",
            impact="New case/matter documents may fail folder placement or land in the wrong location.",
            actions=[
                "Run folder bootstrap from Document Settings.",
                "Verify root, Clients, and Employees folder IDs are saved on the connection.",
            ],
        )
    elif documents["missing_refresh_token"]:
        add(
            "warning",
            "Reconnect Google Drive for lasting access",
            "Google Drive is connected without a refresh token, so access cannot renew automatically.",
            impact="Document create/open/sync will stop when the short-lived access token expires.",
            actions=[
                "Disconnect and connect again from Google Drive Settings.",
                "Approve consent so Google returns an offline refresh token.",
            ],
        )

    if documents["stale_open_sessions"] > 0:
        add(
            "info",
            "Close stale document sessions",
            f"{documents['stale_open_sessions']} document sessions have been open longer than 6 hours.",
            impact="Stale sessions inflate active-document counts and can misreport editing time.",
            actions=[
                "End abandoned open sessions from the document heartbeat/timeout path.",
                "Ensure browser unload and heartbeat failures always call session close.",
            ],
        )

    if documents["connected"] and documents["events"] == 0 and documents["total_documents"] > 0:
        add(
            "info",
            "Document usage is quiet",
            f"{documents['total_documents']} documents exist, but no activity was recorded in this range.",
            impact="Adoption of Drive-backed workflows may be low or tracking may be skipped.",
            actions=[
                "Confirm open/edit/download actions still write DocumentActivity rows.",
                "Spot-check a matter library open session while watching analytics refresh.",
            ],
        )

    if documents["route_p95_ms"] > 800:
        add(
            "warning",
            "Profile document/Drive routes",
            f"Document connection routes have a p95 of {_format_duration(documents['route_p95_ms'])}.",
            impact="Opening libraries or syncing Drive files feels slow for advocates.",
            actions=[
                "Prefetch document activities/sessions only when the analytics panel is opened.",
                "Avoid synchronous Drive API calls on every library page render.",
            ],
        )

    if not recommendations:
        add(
            "healthy",
            "Performance is within target",
            "No high-priority issues were detected for this time range.",
            impact="Interactive latency, scrape health, and resource usage look healthy.",
            actions=[
                "Keep watching p95 latency, scrape success rate, and memory after larger traffic days.",
            ],
        )

    priority = {"critical": 0, "warning": 1, "info": 2, "healthy": 3}
    return sorted(recommendations, key=lambda item: priority[item["level"]])


def build_system_analytics(range_key="24h"):
    if range_key not in RANGES:
        range_key = "24h"
    range_label, duration, grain = RANGES[range_key]
    now = timezone.now()
    start = now - duration
    retention_cutoff = now - timedelta(days=RETENTION_DAYS)
    SystemRequestMetric.objects.filter(created_at__lt=retention_cutoff).delete()

    rows = list(
        SystemRequestMetric.objects.filter(created_at__gte=start)
        .order_by("created_at")
        .values(
            "endpoint",
            "status_code",
            "duration_ms",
            "db_duration_ms",
            "db_query_count",
            "response_bytes",
            "created_at",
        )
    )
    durations = [row["duration_ms"] for row in rows]
    db_durations = [row["db_duration_ms"] for row in rows]
    queries = [row["db_query_count"] for row in rows]
    errors = sum(1 for row in rows if row["status_code"] >= 500)
    total_duration = sum(durations)
    total_db_duration = sum(db_durations)
    performance = {
        "request_count": len(rows),
        "p50_ms": round(_percentile(durations, 0.50), 1),
        "p95_ms": round(_percentile(durations, 0.95), 1),
        "avg_ms": round(_average(durations), 1),
        "error_count": errors,
        "error_rate": round(errors * 100 / len(rows), 1) if rows else 0,
        "avg_queries": round(_average(queries), 1),
        "avg_db_ms": round(_average(db_durations), 1),
        "avg_db_ratio": round(total_db_duration * 100 / total_duration, 1)
        if total_duration
        else 0,
        "response_mb": round(
            sum(row["response_bytes"] for row in rows) / (1024 * 1024),
            2,
        ),
    }

    buckets = defaultdict(lambda: {"requests": 0, "durations": [], "errors": 0})
    for row in rows:
        bucket = buckets[_bucket_start(row["created_at"], grain)]
        bucket["requests"] += 1
        bucket["durations"].append(row["duration_ms"])
        bucket["errors"] += int(row["status_code"] >= 500)
    trend = []
    for bucket_at, values in sorted(buckets.items()):
        trend.append(
            {
                "label": bucket_at.strftime("%H:%M" if grain == "hour" else "%d %b"),
                "requests": values["requests"],
                "latency": round(_percentile(values["durations"], 0.95), 1),
                "errors": values["errors"],
            }
        )

    status_counts = {
        "success": sum(1 for row in rows if 200 <= row["status_code"] < 400),
        "client_error": sum(1 for row in rows if 400 <= row["status_code"] < 500),
        "server_error": errors,
    }
    routes = _route_analytics(rows)
    runtime = _runtime_snapshot()

    active_sessions = Session.objects.filter(expire_date__gt=now).count()
    active_employees = Employee.objects.filter(
        status=Employee.Status.ACTIVE,
        last_login__gte=start,
    ).count()
    active_clients = Client.objects.filter(
        status=Client.Status.ACTIVE,
        last_login__gte=start,
    ).count()
    document_events = DocumentActivity.objects.filter(created_at__gte=start).count()
    open_documents = DocumentOpenSession.objects.filter(ended_at__isnull=True).count()
    case_tasks = CaseTask.objects.filter(created_at__gte=start)
    matter_tasks = MatterTask.objects.filter(created_at__gte=start)
    completed_tasks = case_tasks.filter(status=CaseTask.Status.DONE).count()
    completed_tasks += matter_tasks.filter(status=MatterTask.Status.DONE).count()
    task_count = case_tasks.count() + matter_tasks.count()

    employee_notifications = Notification.objects.filter(created_at__gte=start)
    client_notifications = ClientNotification.objects.filter(created_at__gte=start)
    notification_count = employee_notifications.count() + client_notifications.count()
    unread_notifications = employee_notifications.filter(is_read=False).count()
    unread_notifications += client_notifications.filter(is_read=False).count()
    read_latencies = [
        value
        for value in (
            _read_latency_hours(Notification, start),
            _read_latency_hours(ClientNotification, start),
        )
        if value
    ]
    usage = {
        "active_sessions": active_sessions,
        "active_employees": active_employees,
        "active_clients": active_clients,
        "document_events": document_events,
        "open_documents": open_documents,
        "active_cases": LitigationCase.objects.filter(
            status=LitigationCase.Status.ACTIVE
        ).count(),
        "active_matters": NonLitigationMatter.objects.filter(
            status=NonLitigationMatter.Status.ACTIVE
        ).count(),
        "tasks_created": task_count,
        "tasks_completed": completed_tasks,
        "notification_count": notification_count,
        "unread_notifications": unread_notifications,
        "notification_read_hours": round(_average(read_latencies), 1),
    }

    jobs = NewsSearchJob.objects.filter(created_at__gte=start)
    successful_jobs = jobs.filter(status=NewsSearchJob.Status.SUCCEEDED).count()
    failed_jobs = jobs.filter(status=NewsSearchJob.Status.FAILED).count()
    cancelled_jobs = jobs.filter(status=NewsSearchJob.Status.CANCELLED).count()
    running_jobs = jobs.filter(
        status__in=[NewsSearchJob.Status.QUEUED, NewsSearchJob.Status.RUNNING]
    ).count()
    job_count = jobs.count()
    job_durations = [
        max(0, (finished - started).total_seconds())
        for started, finished in jobs.filter(
            started_at__isnull=False,
            finished_at__isnull=False,
        ).values_list("started_at", "finished_at")
    ]
    queue_waits = [
        max(0, (started - created).total_seconds())
        for created, started in jobs.filter(started_at__isnull=False).values_list(
            "created_at", "started_at"
        )
    ]
    avg_job_seconds = round(_average(job_durations), 1)
    articles_found, articles_enriched = _job_article_counts(jobs)
    watches = NewsWatch.objects.filter(is_active=True)
    watch_articles = NewsWatchArticle.objects.filter(first_seen_at__gte=start)
    scrape_routes = _module_route_stats(
        rows,
        (
            "latest-news",
            "research-blogs",
            "news-watch",
        ),
    )
    scraping = {
        "job_count": job_count,
        "successful_jobs": successful_jobs,
        "failed_jobs": failed_jobs,
        "cancelled_jobs": cancelled_jobs,
        "running_jobs": running_jobs,
        "success_rate": round(successful_jobs * 100 / job_count, 1) if job_count else 0,
        "avg_job_seconds": avg_job_seconds,
        "p95_job_seconds": round(_percentile(job_durations, 0.95), 1),
        "avg_queue_seconds": round(_average(queue_waits), 1),
        "articles_found": articles_found,
        "articles_enriched": articles_enriched,
        "avg_articles_per_job": round(articles_found / successful_jobs, 1)
        if successful_jobs
        else 0,
        "active_watches": watches.count(),
        "watch_errors": watches.exclude(last_error="").count(),
        "overdue_watches": watches.filter(
            next_check_at__lt=now,
            check_started_at__isnull=True,
        ).count(),
        "watch_articles": watch_articles.count(),
        "watch_notified": watch_articles.filter(notified_at__isnull=False).count(),
        "route_requests": scrape_routes["requests"],
        "route_p95_ms": scrape_routes["p95_ms"],
        "route_avg_ms": scrape_routes["avg_ms"],
        "route_error_rate": scrape_routes["error_rate"],
        "route_avg_queries": scrape_routes["avg_queries"],
    }

    blog_posts = EmployeeBlogPost.objects.filter(created_at__gte=start)
    published_posts = EmployeeBlogPost.objects.filter(
        status=EmployeeBlogPost.Status.PUBLISHED,
        published_at__gte=start,
    )
    approved_latency = [
        max(0, (approved - submitted).total_seconds() / 3600)
        for submitted, approved in EmployeeBlogPost.objects.filter(
            submitted_at__isnull=False,
            approved_at__gte=start,
        ).values_list("submitted_at", "approved_at")
        if submitted and approved
    ]
    seo_ready = blog_posts.exclude(focus_keyword="").exclude(meta_description="").count()
    blog_routes = _module_route_stats(
        rows,
        (
            "my-blogs",
            "company-blogs",
            "my-blogs-new",
        ),
    )
    blogs = {
        "created": blog_posts.count(),
        "drafts": blog_posts.filter(status=EmployeeBlogPost.Status.DRAFT).count(),
        "submitted": blog_posts.filter(
            status=EmployeeBlogPost.Status.SUBMITTED
        ).count(),
        "published": published_posts.count(),
        "pending_approval": EmployeeBlogPost.objects.filter(
            status=EmployeeBlogPost.Status.SUBMITTED
        ).count(),
        "active_authors": blog_posts.values("author_id").distinct().count(),
        "avg_approval_hours": round(_average(approved_latency), 1),
        "seo_coverage": round(seo_ready * 100 / blog_posts.count(), 1)
        if blog_posts.count()
        else 0,
        "route_requests": blog_routes["requests"],
        "route_p95_ms": blog_routes["p95_ms"],
        "route_avg_ms": blog_routes["avg_ms"],
        "route_error_rate": blog_routes["error_rate"],
        "route_avg_queries": blog_routes["avg_queries"],
    }

    drive = GoogleDriveConnection.get_solo()
    all_documents = Document.objects.all()
    range_documents = all_documents.filter(created_at__gte=start)
    activities = DocumentActivity.objects.filter(created_at__gte=start)
    sessions = DocumentOpenSession.objects.filter(started_at__gte=start)
    open_doc_sessions = DocumentOpenSession.objects.filter(ended_at__isnull=True)
    stale_cutoff = now - timedelta(hours=6)
    session_durations = list(
        sessions.exclude(duration_seconds=0).values_list("duration_seconds", flat=True)
    )
    kind_totals = {
        row["kind"]: row["total"] or 0
        for row in sessions.values("kind").annotate(total=Sum("duration_seconds"))
    }
    viewing_seconds = kind_totals.get(DocumentOpenSession.Kind.VIEWING, 0)
    editing_seconds = kind_totals.get(DocumentOpenSession.Kind.EDITING, 0)
    creating_seconds = kind_totals.get(DocumentOpenSession.Kind.CREATING, 0)
    token_expires_in_hours = None
    if drive.token_expiry:
        token_expires_in_hours = round(
            (drive.token_expiry - now).total_seconds() / 3600,
            1,
        )
    # Short-lived access tokens renew automatically via refresh_token.
    # Only flag when connected without a refresh token (cannot stay connected).
    missing_refresh_token = drive.is_connected and not (
        drive.refresh_token or ""
    ).strip()
    document_routes = _module_route_stats(
        rows,
        (
            "google-drive",
            "document",
            "documents",
            "drive",
        ),
    )
    action_counts = {
        row["action"]: row["total"]
        for row in activities.values("action").annotate(total=Count("id"))
    }
    documents = {
        "connected": drive.is_connected,
        "folder_structure": drive.has_folder_structure,
        "account_email": drive.account_email or "",
        "account_name": drive.account_name or "",
        "connected_at": drive.connected_at,
        "token_expires_in_hours": token_expires_in_hours
        if token_expires_in_hours is not None
        else 0,
        "missing_refresh_token": missing_refresh_token,
        # Kept for older callers; access-token age is not a connection expiry.
        "token_expiring_soon": missing_refresh_token,
        "total_documents": all_documents.count(),
        "google_documents": all_documents.filter(
            source=Document.Source.GOOGLE_DOC
        ).count(),
        "uploaded_documents": all_documents.filter(
            source=Document.Source.UPLOADED
        ).count(),
        "case_documents": all_documents.filter(case__isnull=False).count(),
        "matter_documents": all_documents.filter(matter__isnull=False).count(),
        "created_in_range": range_documents.count(),
        "events": activities.count(),
        "opens": action_counts.get(DocumentActivity.Action.OPENED, 0),
        "uploads": action_counts.get(DocumentActivity.Action.UPLOADED, 0),
        "downloads": action_counts.get(DocumentActivity.Action.DOWNLOADED, 0),
        "edits": action_counts.get(DocumentActivity.Action.CONTENT_EDITED, 0),
        "creates": action_counts.get(DocumentActivity.Action.CREATED, 0),
        "renames": action_counts.get(DocumentActivity.Action.RENAMED, 0),
        "active_open_sessions": open_doc_sessions.count(),
        "stale_open_sessions": open_doc_sessions.filter(
            last_seen_at__lt=stale_cutoff
        ).count(),
        "sessions_started": sessions.count(),
        "avg_session_minutes": round(_average(session_durations) / 60, 1)
        if session_durations
        else 0,
        "viewing_hours": round(viewing_seconds / 3600, 2),
        "editing_hours": round(editing_seconds / 3600, 2),
        "creating_hours": round(creating_seconds / 3600, 2),
        "active_users": activities.exclude(actor_id=None)
        .values("actor_id")
        .distinct()
        .count(),
        "synced_documents": all_documents.exclude(content_synced_at=None).count(),
        "route_requests": document_routes["requests"],
        "route_p95_ms": document_routes["p95_ms"],
        "route_avg_ms": document_routes["avg_ms"],
        "route_error_rate": document_routes["error_rate"],
        "route_avg_queries": document_routes["avg_queries"],
    }

    payments = MpesaStkRequest.objects.filter(created_at__gte=start)
    operations = {
        "successful_jobs": successful_jobs,
        "failed_jobs": failed_jobs,
        "running_jobs": running_jobs,
        "avg_job_seconds": avg_job_seconds,
        "active_watches": scraping["active_watches"],
        "watch_errors": scraping["watch_errors"],
        "overdue_watches": scraping["overdue_watches"],
        "payment_success": payments.filter(status=MpesaStkRequest.Status.SUCCESS).count(),
        "payment_failed": payments.filter(status=MpesaStkRequest.Status.FAILED).count(),
        "payment_pending": payments.filter(status=MpesaStkRequest.Status.PENDING).count(),
    }

    health_score = 100
    health_score -= min(35, round(performance["error_rate"] * 5))
    health_score -= 20 if performance["p95_ms"] > 1000 else 10 if performance["p95_ms"] > 500 else 0
    health_score -= 15 if runtime["memory_percent"] > 85 else 0
    health_score -= 15 if runtime["disk_percent"] > 85 else 0
    health_score -= 15 if not runtime["db_ok"] else 0
    health_score -= 10 if scraping["job_count"] and scraping["success_rate"] < 80 else 0
    health_score -= 15 if not documents["connected"] else 0
    health_score -= 5 if documents["connected"] and not documents["folder_structure"] else 0
    health_score = max(0, health_score)
    health_label = "Healthy" if health_score >= 85 else "Needs attention" if health_score >= 65 else "Degraded"
    health_tone = (
        "good" if health_score >= 85 else "warning" if health_score >= 65 else "critical"
    )

    def _tone(good, warning=False):
        if good:
            return "good"
        if warning:
            return "warning"
        return "critical"

    latency_tone = _tone(
        performance["p95_ms"] <= 500,
        warning=performance["p95_ms"] <= 1000,
    )
    error_tone = _tone(
        performance["error_rate"] <= 1,
        warning=performance["error_rate"] <= 2,
    )
    memory_tone = _tone(
        runtime["memory_percent"] <= 75,
        warning=runtime["memory_percent"] <= 85,
    )
    cpu_tone = _tone(
        runtime["cpu_percent"] <= 70,
        warning=runtime["cpu_percent"] <= 85,
    )
    disk_tone = _tone(
        runtime["disk_percent"] <= 75,
        warning=runtime["disk_percent"] <= 85,
    )
    scrape_tone = _tone(
        not scraping["job_count"] or scraping["success_rate"] >= 90,
        warning=not scraping["job_count"] or scraping["success_rate"] >= 80,
    )
    drive_tone = _tone(
        documents["connected"] and documents["folder_structure"],
        warning=documents["connected"],
    )
    blog_tone = _tone(
        blogs["pending_approval"] <= 5 and (not blogs["created"] or blogs["seo_coverage"] >= 60),
        warning=blogs["pending_approval"] <= 10,
    )

    recommendations = _recommendations(
        performance,
        runtime,
        routes,
        operations,
        scraping,
        blogs,
        documents,
        recent_job_errors=_recent_job_errors(start),
    )
    top_decisions = recommendations[:3]
    critical_count = sum(1 for item in recommendations if item["level"] == "critical")
    warning_count = sum(1 for item in recommendations if item["level"] == "warning")

    snapshot = {
        "latency": {
            "tone": latency_tone,
            "label": "Fast" if latency_tone == "good" else "Slow" if latency_tone == "critical" else "Watch",
            "value": f"{performance['p95_ms']:.0f} ms",
            "hint": "Page speed (p95)",
        },
        "errors": {
            "tone": error_tone,
            "label": "Stable" if error_tone == "good" else "Failing" if error_tone == "critical" else "Watch",
            "value": f"{performance['error_rate']:.1f}%",
            "hint": "Server errors",
        },
        "memory": {
            "tone": memory_tone,
            "label": "OK" if memory_tone == "good" else "High" if memory_tone == "critical" else "Elevated",
            "value": f"{runtime['memory_percent']:.0f}%",
            "hint": "Host memory",
        },
        "drive": {
            "tone": drive_tone,
            "label": "Connected" if documents["connected"] and documents["folder_structure"] else "Setup needed" if documents["connected"] else "Offline",
            "value": "Ready" if drive_tone == "good" else "Action",
            "hint": "Google Drive",
        },
        "scraping": {
            "tone": scrape_tone,
            "label": "Healthy" if scrape_tone == "good" else "Unreliable" if scrape_tone == "critical" else "Watch",
            "value": f"{scraping['success_rate']:.0f}%" if scraping["job_count"] else "—",
            "hint": "News scrape success",
        },
        "blogs": {
            "tone": blog_tone,
            "label": "On track" if blog_tone == "good" else "Backlog" if blogs["pending_approval"] > 5 else "Improve SEO",
            "value": str(blogs["pending_approval"]),
            "hint": "Posts awaiting approval",
        },
    }

    visual = {
        "resources": [
            {
                "id": "cpu",
                "label": "CPU",
                "value": runtime["cpu_percent"],
                "display": f"{runtime['cpu_percent']:.0f}%",
                "tone": cpu_tone,
                "hint": f"App process {runtime['process_cpu_percent']:.0f}%",
            },
            {
                "id": "memory",
                "label": "Memory",
                "value": runtime["memory_percent"],
                "display": f"{runtime['memory_percent']:.0f}%",
                "tone": memory_tone,
                "hint": f"{runtime['process_memory_mb']:.0f} MB by Django",
            },
            {
                "id": "disk",
                "label": "Disk",
                "value": runtime["disk_percent"],
                "display": f"{runtime['disk_percent']:.0f}%",
                "tone": disk_tone,
                "hint": f"{runtime['disk_free_gb']:.1f} GB free",
            },
            {
                "id": "database",
                "label": "Database",
                "value": min(100, round(runtime["db_latency_ms"] / 5, 1)),
                "display": f"{runtime['db_latency_ms']:.0f} ms",
                "tone": "good" if runtime["db_ok"] and runtime["db_latency_ms"] <= 100 else "warning" if runtime["db_ok"] else "critical",
                "hint": "Online" if runtime["db_ok"] else "Unavailable",
            },
        ],
        "modules": [
            {
                "id": "usage",
                "title": "Who is active",
                "tone": "good" if usage["active_sessions"] else "info",
                "primary": str(usage["active_sessions"]),
                "primary_label": "live sessions",
                "bars": [
                    {"label": "Employees", "value": usage["active_employees"], "max": max(1, usage["active_employees"], usage["active_clients"])},
                    {"label": "Clients", "value": usage["active_clients"], "max": max(1, usage["active_employees"], usage["active_clients"])},
                    {"label": "Open docs", "value": usage["open_documents"], "max": max(1, usage["open_documents"], usage["document_events"])},
                ],
                "footer": f"{usage['tasks_completed']}/{usage['tasks_created']} tasks done",
            },
            {
                "id": "documents",
                "title": "Documents",
                "tone": drive_tone,
                "primary": "On" if documents["connected"] else "Off",
                "primary_label": "Google Drive",
                "bars": [
                    {"label": "Opens", "value": documents["opens"], "max": max(1, documents["events"])},
                    {"label": "Edits", "value": documents["edits"], "max": max(1, documents["events"])},
                    {"label": "Downloads", "value": documents["downloads"], "max": max(1, documents["events"])},
                ],
                "footer": f"{documents['total_documents']} files · {documents['active_open_sessions']} open now",
            },
            {
                "id": "scraping",
                "title": "News scraping",
                "tone": scrape_tone,
                "primary": f"{scraping['success_rate']:.0f}%" if scraping["job_count"] else "—",
                "primary_label": "success rate",
                "bars": [
                    {"label": "Succeeded", "value": scraping["successful_jobs"], "max": max(1, scraping["job_count"])},
                    {"label": "Failed", "value": scraping["failed_jobs"], "max": max(1, scraping["job_count"])},
                    {"label": "Articles", "value": scraping["articles_found"], "max": max(1, scraping["articles_found"], 10)},
                ],
                "footer": f"{scraping['active_watches']} watches · {scraping['watch_errors']} errors",
            },
            {
                "id": "blogs",
                "title": "Blogs",
                "tone": blog_tone,
                "primary": str(blogs["published"]),
                "primary_label": "published",
                "bars": [
                    {"label": "Drafts", "value": blogs["drafts"], "max": max(1, blogs["created"])},
                    {"label": "Submitted", "value": blogs["submitted"], "max": max(1, blogs["created"], blogs["pending_approval"])},
                    {"label": "SEO ready", "value": round(blogs["seo_coverage"]), "max": 100},
                ],
                "footer": f"{blogs['pending_approval']} awaiting approval",
            },
        ],
        "route_bars": [
            {
                "endpoint": route["endpoint"],
                "label": route["endpoint"].replace("accounts:", ""),
                "p95_ms": route["p95_ms"],
                "requests": route["requests"],
                "error_rate": route["error_rate"],
                "width": min(100, max(8, round(route["p95_ms"] / max(1, routes[0]["p95_ms"]) * 100))) if routes else 0,
                "tone": "critical" if route["p95_ms"] >= 3000 or route["error_rate"] >= 5 else "warning" if route["p95_ms"] >= 750 else "good",
            }
            for route in routes[:6]
        ],
    }

    return {
        "range_key": range_key,
        "range_label": range_label,
        "range_options": [
            {"value": key, "label": value[0]} for key, value in RANGES.items()
        ],
        "generated_at": now,
        "performance": performance,
        "trend": trend,
        "status_counts": status_counts,
        "routes": routes,
        "runtime": runtime,
        "usage": usage,
        "operations": operations,
        "scraping": scraping,
        "blogs": blogs,
        "documents": documents,
        "health_score": health_score,
        "health_label": health_label,
        "health_tone": health_tone,
        "snapshot": snapshot,
        "visual": visual,
        "top_decisions": top_decisions,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "recommendations": recommendations,
    }
