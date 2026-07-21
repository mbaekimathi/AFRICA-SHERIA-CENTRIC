"""Background execution for cancellable Latest News searches."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from django.db import close_old_connections
from django.utils import timezone

from .models import NewsSearchJob
from .news_scraper import (
    NewsScrapeError,
    NewsSearchCancelled,
    search_latest_news,
)


logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="news-search")


def _run_news_search(job_id: int) -> None:
    close_old_connections()
    try:
        updated = NewsSearchJob.objects.filter(
            pk=job_id,
            status=NewsSearchJob.Status.QUEUED,
            cancel_requested=False,
        ).update(
            status=NewsSearchJob.Status.RUNNING,
            progress=1,
            progress_label="Starting search",
            started_at=timezone.now(),
        )
        if not updated:
            return

        def cancelled() -> bool:
            return NewsSearchJob.objects.filter(
                pk=job_id,
                cancel_requested=True,
            ).exists()

        def progress(percent: int, label: str) -> None:
            NewsSearchJob.objects.filter(
                pk=job_id,
                status=NewsSearchJob.Status.RUNNING,
                cancel_requested=False,
            ).update(
                progress=max(0, min(100, percent)),
                progress_label=label[:160],
            )

        job = NewsSearchJob.objects.get(pk=job_id)
        result = search_latest_news(
            **job.filters,
            progress_callback=progress,
            cancel_callback=cancelled,
        )
        if cancelled():
            raise NewsSearchCancelled()
        NewsSearchJob.objects.filter(pk=job_id).update(
            status=NewsSearchJob.Status.SUCCEEDED,
            progress=100,
            progress_label="Search complete",
            result=asdict(result),
            error="",
            finished_at=timezone.now(),
        )
    except NewsSearchCancelled:
        NewsSearchJob.objects.filter(pk=job_id).update(
            status=NewsSearchJob.Status.CANCELLED,
            progress_label="Search cancelled",
            finished_at=timezone.now(),
        )
    except NewsScrapeError as exc:
        NewsSearchJob.objects.filter(
            pk=job_id,
            cancel_requested=False,
        ).exclude(status=NewsSearchJob.Status.CANCELLED).update(
            status=NewsSearchJob.Status.FAILED,
            progress_label="Search failed",
            error=str(exc)[:500],
            finished_at=timezone.now(),
        )
    except Exception:
        logger.exception("Unexpected Latest News search failure for job %s", job_id)
        NewsSearchJob.objects.filter(
            pk=job_id,
            cancel_requested=False,
        ).exclude(status=NewsSearchJob.Status.CANCELLED).update(
            status=NewsSearchJob.Status.FAILED,
            progress_label="Search failed",
            error="The search could not be completed. Please try again.",
            finished_at=timezone.now(),
        )
    finally:
        close_old_connections()


def launch_news_search(job_id: int) -> None:
    """Queue a search in the process-local worker pool."""
    _executor.submit(_run_news_search, job_id)
