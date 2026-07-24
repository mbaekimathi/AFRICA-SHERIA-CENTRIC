import logging
import re
from time import perf_counter

from django.apps import apps
from django.db import DatabaseError, connection
from django.utils.deprecation import MiddlewareMixin


logger = logging.getLogger(__name__)

_SAFE_SEGMENT = re.compile(r"^[a-z][a-z-]*$")
_EXCLUDED_PREFIXES = ("/static/", "/media/", "/health/", "/favicon")
_EXCLUDED_SUFFIXES = ("/dashboard/system-settings/",)
# High-frequency live polls — skip telemetry inserts unless the request is slow.
_HIGH_FREQ_PATHS = (
    "/api/workspace/notifications/",
    "/api/workspace/list-revision/",
    "/api/workspace/entity-status/",
    "/employee/api/status/",
    "/client/api/status/",
    "/client/api/notifications/",
)
_SLOW_POLL_MS = 750.0


class _QueryTimer:
    def __init__(self):
        self.count = 0
        self.duration_ms = 0.0

    def __call__(self, execute, sql, params, many, context):
        started = perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            self.count += 1
            self.duration_ms += (perf_counter() - started) * 1000


def _normalised_endpoint(request):
    match = getattr(request, "resolver_match", None)
    if not match:
        return "unresolved"

    endpoint = match.view_name or str(match.route or "unresolved")
    pages = (match.kwargs or {}).get("pages")
    if pages:
        safe_parts = [
            part if _SAFE_SEGMENT.fullmatch(part) else ":param"
            for part in str(pages).strip("/").split("/")
            if part
        ]
        if safe_parts:
            endpoint = f"{endpoint}:{'/'.join(safe_parts)}"
    return endpoint[:255]


class SystemObservabilityMiddleware(MiddlewareMixin):
    """Capture low-overhead, privacy-safe request telemetry."""

    def process_exception(self, request, exception):
        request._observability_error_type = type(exception).__name__
        return None

    def __call__(self, request):
        path = request.path
        if path.startswith(_EXCLUDED_PREFIXES) or path.endswith(_EXCLUDED_SUFFIXES):
            return self.get_response(request)

        is_high_freq = path in _HIGH_FREQ_PATHS or path.endswith("/ping/")
        request._observability_error_type = ""
        timer = _QueryTimer()
        started = perf_counter()
        with connection.execute_wrapper(timer):
            response = self.get_response(request)

        duration_ms = (perf_counter() - started) * 1000
        # Poll traffic dominates write load under many concurrent tabs — only
        # keep outlier timings so diagnostics stay useful without drowning MySQL.
        if is_high_freq and duration_ms < _SLOW_POLL_MS:
            return response
        self._record(request, response, duration_ms, timer)
        return response

    @staticmethod
    def _record(request, response, duration_ms, timer):
        try:
            metric_model = apps.get_model("accounts", "SystemRequestMetric")
            content_length = response.get("Content-Length")
            if content_length and str(content_length).isdigit():
                response_bytes = int(content_length)
            elif not getattr(response, "streaming", False):
                response_bytes = len(getattr(response, "content", b""))
            else:
                response_bytes = 0

            user = getattr(request, "user", None)
            metric_model.objects.create(
                endpoint=_normalised_endpoint(request),
                method=request.method[:8],
                status_code=response.status_code,
                duration_ms=round(duration_ms, 3),
                db_duration_ms=round(timer.duration_ms, 3),
                db_query_count=timer.count,
                response_bytes=response_bytes,
                user_role=getattr(user, "role", "") if user and user.is_authenticated else "",
                error_type=getattr(request, "_observability_error_type", "")[:120],
            )
        except DatabaseError:
            # Startup and migrations must continue before the telemetry table exists.
            logger.debug("System telemetry could not be persisted.", exc_info=True)
