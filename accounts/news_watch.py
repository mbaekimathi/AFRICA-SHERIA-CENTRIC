"""Persistent configurable news watches and in-app update notifications."""

from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.core.cache import cache
from django.db import close_old_connections, models
from django.utils import timezone

from .models import NewsWatch, NewsWatchArticle, Notification
from .news_scraper import NewsScrapeError, NewsSearchCancelled, search_latest_news


logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="news-watch")
_TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "oc",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


def watch_interval(frequency: str) -> timedelta:
    return {
        NewsWatch.Frequency.HOURLY: timedelta(hours=1),
        NewsWatch.Frequency.SIX_HOURS: timedelta(hours=6),
        NewsWatch.Frequency.DAILY: timedelta(days=1),
    }.get(frequency, timedelta(days=1))


def publisher_domain(url: str) -> str:
    return (urlsplit(url or "").hostname or "").lower().removeprefix("www.")


def _canonical_url(url: str) -> str:
    parts = urlsplit(url or "")
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in _TRACKING_PARAMS
        ]
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, query, "")
    )


def article_fingerprint(article: dict) -> str:
    identity = _canonical_url(article.get("url") or "")
    if not identity:
        identity = " ".join((article.get("title") or "").lower().split())
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def watch_key(kind: str, filters: dict, domain: str = "") -> str:
    payload = json.dumps(
        {"kind": kind, "filters": filters, "domain": domain},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def filter_country_code(filters: dict | None) -> str:
    filters = filters or {}
    return (filters.get("country_code") or filters.get("country") or "").upper()


def form_initial_from_news_filters(
    filters: dict | None,
    *,
    fallback_details: str = "",
) -> dict:
    """Map stored job/watch filters onto LatestNewsScrapeForm initials."""
    filters = filters or {}
    details = " ".join((filters.get("requested_details") or "").split())
    if not details:
        details = " ".join((fallback_details or "").split())
    initial: dict[str, str] = {}
    country = filter_country_code(filters)
    if country:
        initial["country"] = country
    for key, default in (
        ("industry", "legal"),
        ("period", "7d"),
        ("language", "en"),
        ("sort_by", "relevance"),
    ):
        value = (filters.get(key) or default).strip()
        if value:
            initial[key] = value
    if details:
        initial["requested_details"] = details[:500]
    for key in ("exact_phrase", "excluded_words", "source_domain"):
        value = " ".join((filters.get(key) or "").split())
        if value:
            initial[key] = value[:200] if key == "excluded_words" else value[:160]
    return initial


def watch_article_as_dict(item: NewsWatchArticle) -> dict:
    """Prefer stored article_data, falling back to denormalised watch fields."""
    payload = dict(item.article_data or {})
    payload.setdefault("title", item.title)
    payload.setdefault("url", item.url)
    payload.setdefault("source_name", item.source_name)
    payload.setdefault("published_at", item.published_at)
    payload.setdefault("description", item.description)
    payload.setdefault("passages", [])
    payload.setdefault("match_reasons", [])
    payload.setdefault("relevance_score", 0)
    payload.setdefault("credibility_score", 0)
    return payload


def create_or_reactivate_publisher_watch(
    *,
    user,
    article: dict,
    base_filters: dict | None,
    baseline_articles: list[dict],
) -> tuple[NewsWatch, bool]:
    """Create (or reactivate) a publisher watch seeded from matching articles."""
    domain = publisher_domain(article.get("url") or "")
    if not domain:
        raise ValueError("The publisher domain could not be identified.")

    filters = dict(base_filters or {})
    # A publisher watch follows the source broadly rather than repeating the
    # original topic query. Country and language still localise the feed.
    filters["requested_details"] = ""
    filters["industry"] = "other"
    filters["exact_phrase"] = ""
    filters["excluded_words"] = ""
    filters["sort_by"] = "newest"
    filters["source_domain"] = domain
    if "country_code" not in filters and filters.get("country"):
        filters["country_code"] = filters.pop("country")
    key = watch_key(NewsWatch.Kind.PUBLISHER, filters, domain)
    publisher = article.get("source_name") or domain
    watch, created = NewsWatch.objects.get_or_create(
        requested_by=user,
        key=key,
        defaults={
            "kind": NewsWatch.Kind.PUBLISHER,
            "name": publisher[:180],
            "filters": filters,
            "publisher_domain": domain,
            "last_checked_at": timezone.now(),
            "next_check_at": timezone.now() + timedelta(days=1),
        },
    )
    if not watch.is_active:
        watch.is_active = True
        watch.next_check_at = timezone.now() + timedelta(days=1)
        watch.save(update_fields=["is_active", "next_check_at", "updated_at"])
    matching = [
        item
        for item in baseline_articles
        if publisher_domain(item.get("url") or "") == domain
        or item.get("source_name") == article.get("source_name")
    ]
    seed_watch(watch, matching or [article])
    return watch, created


def remember_article(
    watch: NewsWatch, article: dict
) -> tuple[NewsWatchArticle, bool]:
    fingerprint = article_fingerprint(article)
    return NewsWatchArticle.objects.get_or_create(
        watch=watch,
        fingerprint=fingerprint,
        defaults={
            "title": (article.get("title") or "News update")[:500],
            "url": article.get("url") or "",
            "source_name": (article.get("source_name") or "")[:180],
            "published_at": (article.get("published_at") or "")[:100],
            "description": article.get("description") or "",
            "article_data": article,
        },
    )


def seed_watch(watch: NewsWatch, articles: list[dict]) -> None:
    """Remember current results so only future articles trigger alerts."""
    for article in articles:
        remember_article(watch, article)


def _notify_new_article(item: NewsWatchArticle) -> None:
    watch = item.watch
    details = [item.source_name, item.published_at]
    details = [detail for detail in details if detail]
    body = f"New update for “{watch.name}”."
    if details:
        body += f"\n\n{' · '.join(details)}"
    target_url = watch.requested_by.workspace_url(
        "dashboard", "research", "latest-news"
    )
    target_url = f"{target_url}?watch={watch.pk}&article={item.pk}"
    Notification.objects.get_or_create(
        recipient=watch.requested_by,
        source_key=f"news_watch:{watch.pk}:{item.fingerprint[:32]}",
        defaults={
            "category": Notification.Category.MESSAGE,
            "title": f"News update: {item.title}"[:200],
            "body": body,
            "target_url": target_url,
        },
    )
    item.notified_at = timezone.now()
    item.save(update_fields=["notified_at"])


def _manual_check_cache_key(watch_id: int) -> str:
    return f"news-watch-check:{watch_id}"


def get_manual_check_status(watch_id: int) -> dict:
    return cache.get(_manual_check_cache_key(watch_id)) or {}


def _set_manual_check_status(watch_id: int, **payload) -> dict:
    current = get_manual_check_status(watch_id)
    current.update(payload)
    cache.set(_manual_check_cache_key(watch_id), current, timeout=15 * 60)
    return current


def request_manual_check_cancel(watch_id: int) -> dict:
    return _set_manual_check_status(
        watch_id,
        cancel_requested=True,
        label="Cancelling check…",
    )


def check_news_watch(
    watch_id: int,
    *,
    progress_callback=None,
    cancel_callback=None,
) -> int:
    """Check one claimed watch and return its number of new articles."""
    now = timezone.now()
    interval = timedelta(days=1)
    try:
        watch = NewsWatch.objects.select_related("requested_by").get(
            pk=watch_id,
            is_active=True,
        )
        interval = watch_interval(watch.frequency)

        def report(percent: int, label: str) -> None:
            if progress_callback:
                progress_callback(percent, label)

        result = search_latest_news(
            **watch.filters,
            progress_callback=report,
            cancel_callback=cancel_callback,
        )
        if cancel_callback and cancel_callback():
            raise NewsSearchCancelled()
        new_items = []
        for article in (asdict(result).get("articles") or []):
            item, created = remember_article(watch, article)
            if created:
                new_items.append(item)
        for item in new_items:
            _notify_new_article(item)
        watch.last_checked_at = now
        watch.next_check_at = now + interval
        watch.check_started_at = None
        watch.last_error = ""
        watch.save(
            update_fields=[
                "last_checked_at",
                "next_check_at",
                "check_started_at",
                "last_error",
                "updated_at",
            ]
        )
        return len(new_items)
    except NewsSearchCancelled:
        NewsWatch.objects.filter(pk=watch_id).update(
            next_check_at=now + interval,
            check_started_at=None,
            last_error="",
        )
        return -2
    except NewsWatch.DoesNotExist:
        return 0
    except NewsScrapeError as exc:
        NewsWatch.objects.filter(pk=watch_id).update(
            next_check_at=now + interval,
            check_started_at=None,
            last_error=str(exc)[:500],
        )
        return 0
    except Exception as exc:
        logger.exception("News watch %s failed", watch_id)
        NewsWatch.objects.filter(pk=watch_id).update(
            next_check_at=now + interval,
            check_started_at=None,
            last_error=str(exc)[:500],
        )
        return 0


def _run_news_watch(watch_id: int) -> None:
    close_old_connections()
    try:
        check_news_watch(watch_id)
    finally:
        close_old_connections()


def _run_manual_news_watch(watch_id: int) -> None:
    close_old_connections()
    try:
        def progress(percent: int, label: str) -> None:
            status = get_manual_check_status(watch_id)
            if status.get("cancel_requested"):
                return
            _set_manual_check_status(
                watch_id,
                status="running",
                progress=max(0, min(99, percent)),
                label=label[:160],
            )

        def cancelled() -> bool:
            return bool(get_manual_check_status(watch_id).get("cancel_requested"))

        _set_manual_check_status(
            watch_id,
            status="running",
            progress=3,
            label="Starting watch check…",
            cancel_requested=False,
            error="",
            found=0,
        )
        found = check_news_watch(
            watch_id,
            progress_callback=progress,
            cancel_callback=cancelled,
        )
        watch = NewsWatch.objects.filter(pk=watch_id).first()
        result_url = ""
        if watch is not None:
            result_url = (
                f"{watch.requested_by.workspace_url('dashboard', 'research', 'latest-news')}"
                f"?watch={watch.pk}"
            )
        if found == -2 or cancelled():
            _set_manual_check_status(
                watch_id,
                status="cancelled",
                progress=0,
                label="Check cancelled",
                terminal=True,
                result_url=result_url,
            )
            return
        if watch is not None and watch.last_error:
            _set_manual_check_status(
                watch_id,
                status="failed",
                progress=100,
                label="Check failed",
                error=watch.last_error,
                terminal=True,
                result_url=result_url,
            )
            return
        if found:
            label = (
                f"Found {found} new update"
                f"{'' if found == 1 else 's'}"
            )
        else:
            label = "No new updates"
        _set_manual_check_status(
            watch_id,
            status="succeeded",
            progress=100,
            label=label,
            found=found,
            terminal=True,
            result_url=result_url,
        )
    except Exception:
        logger.exception("Manual news watch %s failed", watch_id)
        _set_manual_check_status(
            watch_id,
            status="failed",
            progress=100,
            label="Check failed",
            error="The watch could not be checked. Please try again.",
            terminal=True,
        )
        NewsWatch.objects.filter(pk=watch_id).update(check_started_at=None)
    finally:
        close_old_connections()


def launch_news_watch_now(watch_id: int) -> str:
    """Queue a manual check and return busy|started|missing."""
    now = timezone.now()
    watch = NewsWatch.objects.filter(pk=watch_id, is_active=True).first()
    if watch is None:
        return "missing"
    current = get_manual_check_status(watch_id)
    if current.get("status") == "running" and not current.get("terminal"):
        return "busy"
    if watch.check_started_at and watch.check_started_at > now - timedelta(seconds=30):
        return "busy"
    NewsWatch.objects.filter(pk=watch_id).update(check_started_at=now)
    _set_manual_check_status(
        watch_id,
        status="running",
        progress=1,
        label="Queued watch check…",
        cancel_requested=False,
        terminal=False,
        error="",
        found=0,
        result_url="",
    )
    _executor.submit(_run_manual_news_watch, watch_id)
    return "started"


def run_news_watch_now(watch_id: int) -> int:
    """Synchronously check one watch, ignoring its next scheduled time."""
    now = timezone.now()
    watch = NewsWatch.objects.filter(pk=watch_id, is_active=True).first()
    if watch is None:
        return 0
    if watch.check_started_at and watch.check_started_at > now - timedelta(seconds=30):
        return -1
    NewsWatch.objects.filter(pk=watch_id).update(check_started_at=now)
    return check_news_watch(watch_id)


def claim_due_news_watches(*, employee_id: int | None = None) -> list[int]:
    """Atomically claim due watches so web workers do not duplicate checks."""
    now = timezone.now()
    stale_before = now - timedelta(hours=2)
    queryset = NewsWatch.objects.filter(
        is_active=True,
        next_check_at__lte=now,
    ).filter(
        models.Q(check_started_at__isnull=True)
        | models.Q(check_started_at__lt=stale_before)
    )
    if employee_id is not None:
        queryset = queryset.filter(requested_by_id=employee_id)

    claimed = []
    for watch_id in queryset.values_list("pk", flat=True)[:50]:
        updated = (
            NewsWatch.objects.filter(
                pk=watch_id,
                is_active=True,
                next_check_at__lte=now,
            )
            .filter(
                models.Q(check_started_at__isnull=True)
                | models.Q(check_started_at__lt=stale_before)
            )
            .update(
                check_started_at=now,
                next_check_at=now + timedelta(days=1),
            )
        )
        if updated:
            claimed.append(watch_id)
    return claimed


def launch_due_news_watches(*, employee_id: int | None = None) -> int:
    watch_ids = claim_due_news_watches(employee_id=employee_id)
    for watch_id in watch_ids:
        _executor.submit(_run_news_watch, watch_id)
    return len(watch_ids)


def run_due_news_watches() -> tuple[int, int]:
    """Synchronously run due watches; intended for the daily command."""
    watch_ids = claim_due_news_watches()
    updates = sum(check_news_watch(watch_id) for watch_id in watch_ids)
    return len(watch_ids), updates
