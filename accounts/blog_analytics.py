"""Public blog view and conversion tracking helpers."""

from __future__ import annotations

import hashlib
import re

from django.utils.http import url_has_allowed_host_and_scheme

from .models import BlogPostEvent, EmployeeBlogPost

BOT_UA_RE = re.compile(
    r"bot|crawl|spider|slurp|bingpreview|facebookexternalhit|embedly|"
    r"quora link preview|preview|monitor|uptime|python-requests|curl/",
    re.IGNORECASE,
)

ALLOWED_EVENT_TYPES = {choice.value for choice in BlogPostEvent.EventType}


def _is_bot(user_agent: str) -> bool:
    return bool(user_agent and BOT_UA_RE.search(user_agent))


def _session_fingerprint(request) -> str:
    session_key = getattr(request.session, "session_key", None) or ""
    if not session_key:
        try:
            request.session.save()
            session_key = request.session.session_key or ""
        except Exception:
            session_key = ""
    if not session_key:
        raw = "|".join(
            [
                request.META.get("HTTP_USER_AGENT", "")[:120],
                request.META.get("REMOTE_ADDR", "")[:64],
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]
    return hashlib.sha256(session_key.encode("utf-8")).hexdigest()[:40]


def _clean_referrer(value: str, *, host: str = "") -> str:
    text = (value or "").strip()[:255]
    if not text:
        return ""
    if host and url_has_allowed_host_and_scheme(text, allowed_hosts={host}):
        return text
    return text


def record_blog_event(request, post: EmployeeBlogPost, event_type: str) -> bool:
    """Persist one privacy-safe interaction. Returns True when stored."""
    event_type = (event_type or "").strip()
    if event_type not in ALLOWED_EVENT_TYPES:
        return False
    if post.status != EmployeeBlogPost.Status.PUBLISHED:
        return False
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    if event_type == BlogPostEvent.EventType.VIEW and _is_bot(user_agent):
        return False

    referrer = _clean_referrer(
        request.META.get("HTTP_REFERER", ""),
        host=request.get_host(),
    )
    BlogPostEvent.objects.create(
        post=post,
        event_type=event_type,
        session_key=_session_fingerprint(request),
        referrer=referrer,
    )
    return True
