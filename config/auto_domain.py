"""Trust whatever domain the visitor used (cPanel / local / LAN)."""

from __future__ import annotations

from django.conf import settings


class AutoDomainMiddleware:
    """
    Domain auto-pick:
    - ALLOWED_HOSTS is '*' so any Host header is accepted
    - each request's origin is added to CSRF_TRUSTED_ORIGINS
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self._trust_origin(request)
        return self.get_response(request)

    def _trust_origin(self, request) -> None:
        host = (request.META.get("HTTP_HOST") or "").strip()
        if not host:
            return

        forwarded = (
            request.META.get("HTTP_X_FORWARDED_PROTO")
            or request.headers.get("X-Forwarded-Proto", "")
        )
        if forwarded:
            scheme = forwarded.split(",")[0].strip().lower()
        elif request.is_secure():
            scheme = "https"
        else:
            scheme = "http"

        if scheme not in {"http", "https"}:
            scheme = "https"

        origin = f"{scheme}://{host}"
        trusted = settings.CSRF_TRUSTED_ORIGINS
        if origin not in trusted:
            trusted.append(origin)

        # Remember for OAuth / absolute URLs in the same request cycle.
        request.auto_site_origin = origin
