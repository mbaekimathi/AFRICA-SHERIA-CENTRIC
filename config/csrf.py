"""Recover from expired CSRF tokens instead of dead-ending on a 403 page."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

RETRY_MESSAGE = (
    "This page was open too long and its security token expired. "
    "Please try again."
)


def _wants_json(request) -> bool:
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    # Only scripted callers send the token as a header; a redirect would leave
    # them parsing a login page as JSON.
    if settings.CSRF_HEADER_NAME in request.META:
        return True
    if "application/json" in (request.content_type or ""):
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept and "text/html" not in accept


def _retry_url(request) -> str:
    """Send the visitor back to the page they submitted from."""
    referer = request.META.get("HTTP_REFERER", "")
    if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts={request.get_host()}
    ):
        # Relative, so a proxied http referer cannot downgrade the redirect.
        parts = urlsplit(referer)
        return urlunsplit(("", "", parts.path, parts.query, ""))
    return reverse("accounts:login")


def csrf_failure(request, reason="", template_name=""):
    """Issue a fresh token and bounce the form back to its own page."""
    get_token(request)

    if _wants_json(request):
        return JsonResponse(
            {"error": "csrf_expired", "detail": RETRY_MESSAGE}, status=403
        )

    messages.error(request, RETRY_MESSAGE)
    return redirect(_retry_url(request))
