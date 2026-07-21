"""Track employee login, logout, and working session analytics."""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import mean

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Employee, EmployeeWorkSession, IDLE_TIMEOUT_SECONDS
from .workspace import SESSION_STARTED_AT_KEY

SESSION_PK_KEY = "employee_work_session_id"
IDLE_TIMEOUT = timedelta(seconds=IDLE_TIMEOUT_SECONDS)


def _ensure_session_key(request) -> str:
    session_key = getattr(request.session, "session_key", None) or ""
    if session_key:
        return session_key
    request.session.save()
    return request.session.session_key or ""


def _parse_session_started_at(request) -> datetime:
    raw = request.session.get(SESSION_STARTED_AT_KEY)
    if raw:
        parsed = parse_datetime(str(raw))
        if parsed is not None:
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
            return parsed
    return timezone.now()


def _accumulate_working_time(session: EmployeeWorkSession, now) -> None:
    if session.last_active_at:
        gap = (now - session.last_active_at).total_seconds()
        if gap <= IDLE_TIMEOUT.total_seconds():
            session.working_seconds += int(gap)
    session.last_active_at = now


def _format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _format_clock(minutes_from_midnight: float) -> str:
    total = int(round(minutes_from_midnight)) % (24 * 60)
    hour, minute = divmod(total, 60)
    moment = datetime(2000, 1, 1, hour, minute)
    return moment.strftime("%I:%M %p").lstrip("0")


def start_employee_session(request, employee: Employee) -> EmployeeWorkSession:
    """Open a tracked work session when an employee signs in."""
    now = timezone.now()
    session_key = _ensure_session_key(request)
    EmployeeWorkSession.objects.filter(
        session_key=session_key,
        logout_at__isnull=True,
    ).update(
        logout_at=now,
        logout_kind=EmployeeWorkSession.LogoutKind.REPLACED,
    )
    work_session = EmployeeWorkSession.objects.create(
        employee=employee,
        session_key=session_key,
        login_at=now,
        last_active_at=now,
    )
    request.session[SESSION_PK_KEY] = work_session.pk
    return work_session


def ensure_employee_work_session(request) -> EmployeeWorkSession | None:
    """Ensure the signed-in employee has an open tracked session."""
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return None
    if not isinstance(user, Employee):
        return None
    if user.status != Employee.Status.ACTIVE:
        return None

    session_pk = request.session.get(SESSION_PK_KEY)
    if session_pk:
        existing = EmployeeWorkSession.objects.filter(
            pk=session_pk,
            employee=user,
            logout_at__isnull=True,
        ).first()
        if existing:
            return existing

    now = timezone.now()
    session_key = _ensure_session_key(request)
    login_at = _parse_session_started_at(request)
    work_session = EmployeeWorkSession.objects.create(
        employee=user,
        session_key=session_key,
        login_at=login_at,
        last_active_at=now,
    )
    request.session[SESSION_PK_KEY] = work_session.pk
    return work_session


def touch_employee_session(request) -> None:
    """Extend active working time while the employee uses the workspace."""
    session = ensure_employee_work_session(request)
    if not session:
        return
    now = timezone.now()
    _accumulate_working_time(session, now)
    session.save(update_fields=["last_active_at", "working_seconds"])


def end_employee_session(
    request,
    *,
    kind: str = EmployeeWorkSession.LogoutKind.MANUAL,
) -> None:
    """Close the tracked work session on sign-out."""
    now = timezone.now()
    session_pk = request.session.get(SESSION_PK_KEY)
    session = None
    if session_pk:
        session = EmployeeWorkSession.objects.filter(
            pk=session_pk,
            logout_at__isnull=True,
        ).first()
    if session is None and request.user.is_authenticated:
        session = EmployeeWorkSession.objects.filter(
            employee=request.user,
            logout_at__isnull=True,
        ).order_by("-login_at").first()
    if session:
        _accumulate_working_time(session, now)
        session.logout_at = now
        session.logout_kind = kind
        session.save(
            update_fields=["last_active_at", "working_seconds", "logout_at", "logout_kind"]
        )
    request.session.pop(SESSION_PK_KEY, None)


def build_employee_session_analytics(employee: Employee, *, days: int = 90) -> dict:
    """Login, logout, active session, and working session metrics."""
    since = timezone.now() - timedelta(days=days)
    sessions = list(
        EmployeeWorkSession.objects.filter(
            employee=employee,
            login_at__gte=since,
        ).order_by("-login_at")
    )
    active_session = EmployeeWorkSession.objects.filter(
        employee=employee,
        logout_at__isnull=True,
    ).order_by("-login_at").first()

    login_minutes = []
    for session in sessions:
        local = timezone.localtime(session.login_at)
        login_minutes.append(local.hour * 60 + local.minute)
    average_login_time = (
        _format_clock(mean(login_minutes)) if login_minutes else None
    )

    logout_minutes = []
    for session in sessions:
        if session.logout_at:
            local = timezone.localtime(session.logout_at)
            logout_minutes.append(local.hour * 60 + local.minute)
    average_logout_time = (
        _format_clock(mean(logout_minutes)) if logout_minutes else None
    )

    working_sessions = [
        session
        for session in sessions
        if session.working_seconds > 0 or session.is_active
    ]
    total_working_seconds = sum(
        session.live_working_seconds if session.is_active else session.working_seconds
        for session in sessions
    )
    total_session_seconds = sum(session.duration_seconds for session in sessions)
    completed_sessions = [session for session in sessions if session.logout_at]

    active_payload = None
    if active_session:
        active_payload = {
            "login_at": active_session.login_at,
            "last_active_at": active_session.last_active_at,
            "session_duration": _format_duration(active_session.duration_seconds),
            "working_duration": _format_duration(
                active_session.live_working_seconds
            ),
            "is_active": True,
        }

    recent_sessions = []
    for session in sessions[:20]:
        logout_label = "Active now"
        if session.logout_at:
            logout_label = session.get_logout_kind_display() or "Signed out"
        recent_sessions.append(
            {
                "login_at": session.login_at,
                "logout_at": session.logout_at,
                "logout_label": logout_label,
                "is_active": session.is_active,
                "session_duration": _format_duration(session.duration_seconds),
                "working_duration": _format_duration(
                    session.live_working_seconds
                    if session.is_active
                    else session.working_seconds
                ),
            }
        )

    return {
        "average_login_time": average_login_time,
        "average_logout_time": average_logout_time,
        "active_session": active_payload,
        "working_sessions_count": len(working_sessions),
        "total_working_seconds": total_working_seconds,
        "total_working_duration": _format_duration(total_working_seconds),
        "average_working_duration": _format_duration(
            int(total_working_seconds / len(working_sessions))
            if working_sessions
            else 0
        ),
        "average_session_duration": _format_duration(
            int(total_session_seconds / len(completed_sessions))
            if completed_sessions
            else 0
        ),
        "total_sessions": len(sessions),
        "completed_sessions": len(completed_sessions),
        "recent_sessions": recent_sessions,
    }


def batch_employee_session_summaries(
    employee_ids: list[int],
    *,
    days: int = 30,
) -> dict[int, dict]:
    """Headline session metrics for many employees at once."""
    if not employee_ids:
        return {}

    since = timezone.now() - timedelta(days=days)
    rows = EmployeeWorkSession.objects.filter(
        employee_id__in=employee_ids,
        login_at__gte=since,
    ).order_by("employee_id", "-login_at")

    grouped: dict[int, list[EmployeeWorkSession]] = {}
    for row in rows:
        grouped.setdefault(row.employee_id, []).append(row)

    active_rows = {
        row.employee_id: row
        for row in EmployeeWorkSession.objects.filter(
            employee_id__in=employee_ids,
            logout_at__isnull=True,
        ).order_by("employee_id", "-login_at")
    }

    summaries: dict[int, dict] = {}
    for employee_id in employee_ids:
        sessions = grouped.get(employee_id, [])
        login_minutes = [
            timezone.localtime(session.login_at).hour * 60
            + timezone.localtime(session.login_at).minute
            for session in sessions
        ]
        working_sessions = [
            session
            for session in sessions
            if session.working_seconds > 0 or session.is_active
        ]
        active = active_rows.get(employee_id)
        summaries[employee_id] = {
            "average_login_time": (
                _format_clock(mean(login_minutes)) if login_minutes else "—"
            ),
            "working_sessions_count": len(working_sessions),
            "is_online": active is not None,
            "active_session_duration": (
                _format_duration(active.duration_seconds) if active else "—"
            ),
        }
    return summaries
