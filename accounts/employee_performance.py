"""Performance and compliance analytics for firm employees."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from .employee_sessions import build_employee_session_analytics
from .models import (
    CaseTask,
    CourtAttendance,
    Document,
    Employee,
    EmployeeBlogPost,
    EmployeeWorkSession,
    LitigationCase,
    MatterAttendance,
    MatterTask,
    NonLitigationMatter,
)

OPEN_TASK_STATUSES = (
    CaseTask.Status.PENDING,
    CaseTask.Status.ACCEPTED,
)
DONE_TASK_STATUS = CaseTask.Status.DONE
CANCELLED_TASK_STATUS = CaseTask.Status.CANCELLED


def _task_completion_rate(done: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((done / total) * 100, 1)


def _parse_range_days(raw: str | None) -> int:
    value = (raw or "90").strip()
    if value in {"7", "30", "90"}:
        return int(value)
    return 90


def annotate_employee_performance_summaries(queryset):
    """Annotate employees with headline metrics for the list page."""
    today = timezone.localdate()
    return queryset.annotate(
        case_tasks_total=Count(
            "case_tasks",
            filter=~Q(case_tasks__status=CANCELLED_TASK_STATUS),
            distinct=True,
        ),
        case_tasks_done=Count(
            "case_tasks",
            filter=Q(case_tasks__status=DONE_TASK_STATUS),
            distinct=True,
        ),
        matter_tasks_total=Count(
            "matter_tasks",
            filter=~Q(matter_tasks__status=CANCELLED_TASK_STATUS),
            distinct=True,
        ),
        matter_tasks_done=Count(
            "matter_tasks",
            filter=Q(matter_tasks__status=DONE_TASK_STATUS),
            distinct=True,
        ),
        active_assigned_cases=Count(
            "assigned_cases",
            filter=Q(assigned_cases__status=LitigationCase.Status.ACTIVE),
            distinct=True,
        ),
        active_assigned_matters=Count(
            "assigned_matters",
            filter=Q(assigned_matters__status=NonLitigationMatter.Status.ACTIVE),
            distinct=True,
        ),
        published_blogs=Count(
            "blog_posts",
            filter=Q(blog_posts__status=EmployeeBlogPost.Status.PUBLISHED),
            distinct=True,
        ),
        overdue_case_tasks=Count(
            "case_tasks",
            filter=Q(
                case_tasks__due_date__lt=today,
                case_tasks__status__in=OPEN_TASK_STATUSES,
            ),
            distinct=True,
        ),
        overdue_matter_tasks=Count(
            "matter_tasks",
            filter=Q(
                matter_tasks__due_date__lt=today,
                matter_tasks__status__in=OPEN_TASK_STATUSES,
            ),
            distinct=True,
        ),
    )


def employee_summary_metrics(employee) -> dict:
    """Lightweight summary for a single annotated employee row."""
    total_tasks = employee.case_tasks_total + employee.matter_tasks_total
    done_tasks = employee.case_tasks_done + employee.matter_tasks_done
    return {
        "active_workload": employee.active_assigned_cases + employee.active_assigned_matters,
        "tasks_total": total_tasks,
        "tasks_done": done_tasks,
        "completion_rate": _task_completion_rate(done_tasks, total_tasks),
        "overdue_tasks": employee.overdue_case_tasks + employee.overdue_matter_tasks,
        "published_blogs": employee.published_blogs,
    }


def _date_range(days: int):
    today = timezone.localdate()
    start = today - timedelta(days=max(0, days - 1))
    day = start
    while day <= today:
        yield day
        day += timedelta(days=1)


def _series_from_counts(days: int, counts: dict) -> list[dict]:
    return [
        {"label": day.strftime("%d %b"), "value": counts.get(day, 0)}
        for day in _date_range(days)
    ]


def build_employee_performance_charts(
    employee: Employee,
    *,
    days: int,
    analytics: dict,
) -> dict:
    """Trend series for the employee performance visuals tab."""
    since = timezone.now() - timedelta(days=days)
    since_date = since.date()

    completion_counts: dict = defaultdict(int)
    for row in analytics["daily_completions"]:
        completion_counts[row["day"]] = row["total"]

    working_counts: dict = defaultdict(int)
    for session in EmployeeWorkSession.objects.filter(
        employee=employee,
        login_at__gte=since,
    ):
        day = timezone.localtime(session.login_at).date()
        seconds = (
            session.live_working_seconds
            if session.is_active
            else session.working_seconds
        )
        working_counts[day] += round(seconds / 60)

    session_counts: dict = defaultdict(int)
    for session in EmployeeWorkSession.objects.filter(
        employee=employee,
        login_at__gte=since,
    ):
        session_counts[timezone.localtime(session.login_at).date()] += 1

    compliance_counts: dict = defaultdict(int)
    for attendance_date in CourtAttendance.objects.filter(
        recorded_by=employee,
        attendance_date__gte=since_date,
    ).values_list("attendance_date", flat=True):
        compliance_counts[attendance_date] += 1
    for attendance_date in MatterAttendance.objects.filter(
        recorded_by=employee,
        attendance_date__gte=since_date,
    ).values_list("attendance_date", flat=True):
        compliance_counts[attendance_date] += 1
    for created_at in Document.objects.filter(
        uploaded_by=employee,
        created_at__gte=since,
    ).values_list("created_at", flat=True):
        compliance_counts[timezone.localdate(created_at)] += 1

    task_completions_series = _series_from_counts(days, completion_counts)
    working_minutes_series = _series_from_counts(days, working_counts)
    login_sessions_series = _series_from_counts(days, session_counts)
    compliance_series = _series_from_counts(days, compliance_counts)

    def _total(series):
        return sum(point["value"] for point in series)

    def _peak(series):
        return max((point["value"] for point in series), default=0)

    def _streak(series):
        best = current = 0
        for point in series:
            if point["value"] > 0:
                current += 1
                best = max(best, current)
            else:
                current = 0
        return best

    return {
        "trends": [
            {
                "id": "task-completions",
                "title": "Task completions",
                "subtitle": "Tasks completed per day",
                "total": _total(task_completions_series),
                "peak": _peak(task_completions_series),
                "streak": _streak(task_completions_series),
                "unit": "tasks",
                "series": task_completions_series,
            },
            {
                "id": "working-time",
                "title": "Working time",
                "subtitle": "Active workspace minutes per day",
                "total": _total(working_minutes_series),
                "peak": _peak(working_minutes_series),
                "streak": _streak(working_minutes_series),
                "unit": "min",
                "series": working_minutes_series,
            },
            {
                "id": "login-sessions",
                "title": "Login sessions",
                "subtitle": "Workspace sign-ins per day",
                "total": _total(login_sessions_series),
                "peak": _peak(login_sessions_series),
                "streak": _streak(login_sessions_series),
                "unit": "logins",
                "series": login_sessions_series,
            },
            {
                "id": "compliance-activity",
                "title": "Compliance activity",
                "subtitle": "Court, matter, and document events per day",
                "total": _total(compliance_series),
                "peak": _peak(compliance_series),
                "streak": _streak(compliance_series),
                "unit": "events",
                "series": compliance_series,
            },
        ],
    }


def build_employee_performance_analytics(employee: Employee, *, days: int = 90) -> dict:
    """Detailed performance analytics for one employee."""
    days = _parse_range_days(str(days))
    today = timezone.localdate()
    since = timezone.now() - timedelta(days=days)
    since_date = (timezone.now() - timedelta(days=days)).date()

    case_tasks = list(
        CaseTask.objects.filter(assignee=employee)
        .exclude(status=CANCELLED_TASK_STATUS)
        .select_related("case", "case__client")
        .order_by("-created_at")
    )
    matter_tasks = list(
        MatterTask.objects.filter(assignee=employee)
        .exclude(status=CANCELLED_TASK_STATUS)
        .select_related("matter", "matter__client")
        .order_by("-created_at")
    )

    all_tasks = case_tasks + matter_tasks
    tasks_in_range = [
        task
        for task in all_tasks
        if task.created_at >= since
        or (
            task.status == DONE_TASK_STATUS
            and task.updated_at >= since
        )
    ]

    done_tasks = [task for task in all_tasks if task.status == DONE_TASK_STATUS]
    pending_tasks = [task for task in all_tasks if task.status == CaseTask.Status.PENDING]
    accepted_tasks = [task for task in all_tasks if task.status == CaseTask.Status.ACCEPTED]
    rejected_tasks = [task for task in all_tasks if task.status == CaseTask.Status.REJECTED]
    overdue_tasks = [
        task
        for task in all_tasks
        if task.due_date < today and task.status in OPEN_TASK_STATUSES
    ]
    on_time_done = [
        task
        for task in done_tasks
        if task.updated_at.date() <= task.due_date
    ]

    assigned_cases = LitigationCase.objects.filter(
        assigned_to=employee,
        status=LitigationCase.Status.ACTIVE,
    ).count()
    assigned_matters = NonLitigationMatter.objects.filter(
        assigned_to=employee,
        status=NonLitigationMatter.Status.ACTIVE,
    ).count()
    registered_cases = LitigationCase.objects.filter(
        registered_by=employee,
        created_at__gte=since,
    ).count()
    registered_matters = NonLitigationMatter.objects.filter(
        registered_by=employee,
        created_at__gte=since,
    ).count()

    court_attendances = CourtAttendance.objects.filter(
        recorded_by=employee,
        attendance_date__gte=since_date,
    ).count()
    matter_attendances = MatterAttendance.objects.filter(
        recorded_by=employee,
        attendance_date__gte=since_date,
    ).count()
    documents_uploaded = Document.objects.filter(
        uploaded_by=employee,
        created_at__gte=since,
    ).count()

    blog_posts = EmployeeBlogPost.objects.filter(author=employee)
    blog_published = blog_posts.filter(
        status=EmployeeBlogPost.Status.PUBLISHED
    ).count()
    blog_submitted = blog_posts.filter(
        status=EmployeeBlogPost.Status.SUBMITTED
    ).count()
    blog_drafts = blog_posts.filter(status=EmployeeBlogPost.Status.DRAFT).count()
    blog_published_in_range = blog_posts.filter(
        status=EmployeeBlogPost.Status.PUBLISHED,
        published_at__gte=since,
    ).count()

    daily_completions: dict = defaultdict(int)
    for task in done_tasks:
        if task.updated_at >= since:
            daily_completions[task.updated_at.date()] += 1
    daily_completion_rows = [
        {"day": day, "total": total}
        for day, total in sorted(daily_completions.items(), reverse=True)
    ]

    status_labels = dict(CaseTask.Status.choices)
    recent_tasks = []
    for task in sorted(all_tasks, key=lambda item: item.created_at, reverse=True)[:12]:
        status_display = status_labels.get(task.status, task.status)
        if isinstance(task, CaseTask):
            recent_tasks.append(
                {
                    "kind": "case",
                    "title": (task.title or "").strip() or f"Case task #{task.pk}",
                    "subject": str(task.case),
                    "status": task.status,
                    "status_display": status_display,
                    "due_date": task.due_date,
                    "created_at": task.created_at,
                    "is_overdue": (
                        task.due_date < today and task.status in OPEN_TASK_STATUSES
                    ),
                }
            )
        else:
            recent_tasks.append(
                {
                    "kind": "matter",
                    "title": (task.title or "").strip() or f"Matter task #{task.pk}",
                    "subject": str(task.matter),
                    "status": task.status,
                    "status_display": status_display,
                    "due_date": task.due_date,
                    "created_at": task.created_at,
                    "is_overdue": (
                        task.due_date < today and task.status in OPEN_TASK_STATUSES
                    ),
                }
            )

    recent_activity = []
    for attendance in (
        CourtAttendance.objects.filter(recorded_by=employee, attendance_date__gte=since_date)
        .select_related("case")
        .order_by("-attendance_date", "-created_at")[:8]
    ):
        recent_activity.append(
            {
                "kind": "court",
                "label": attendance.activity_type,
                "subject": str(attendance.case),
                "when": attendance.attendance_date,
            }
        )
    for attendance in (
        MatterAttendance.objects.filter(
            recorded_by=employee,
            attendance_date__gte=since_date,
        )
        .select_related("matter")
        .order_by("-attendance_date", "-created_at")[:8]
    ):
        recent_activity.append(
            {
                "kind": "matter",
                "label": attendance.activity_type,
                "subject": str(attendance.matter),
                "when": attendance.attendance_date,
            }
        )
    for document in (
        Document.objects.filter(uploaded_by=employee, created_at__gte=since)
        .select_related("case", "matter")
        .order_by("-created_at")[:8]
    ):
        subject = ""
        if document.case_id:
            subject = str(document.case)
        elif document.matter_id:
            subject = str(document.matter)
        recent_activity.append(
            {
                "kind": "document",
                "label": document.title,
                "subject": subject,
                "when": document.created_at.date(),
            }
        )
    recent_activity.sort(key=lambda item: item["when"], reverse=True)
    recent_activity = recent_activity[:15]

    total_tasks = len(all_tasks)
    done_count = len(done_tasks)
    sessions = build_employee_session_analytics(employee, days=days)

    payload = {
        "days": days,
        "tasks_total": total_tasks,
        "tasks_done": done_count,
        "tasks_pending": len(pending_tasks),
        "tasks_accepted": len(accepted_tasks),
        "tasks_rejected": len(rejected_tasks),
        "tasks_overdue": len(overdue_tasks),
        "tasks_in_range": len(tasks_in_range),
        "completion_rate": _task_completion_rate(done_count, total_tasks),
        "on_time_rate": _task_completion_rate(len(on_time_done), len(done_tasks)),
        "active_cases": assigned_cases,
        "active_matters": assigned_matters,
        "active_workload": assigned_cases + assigned_matters,
        "registered_cases": registered_cases,
        "registered_matters": registered_matters,
        "court_attendances": court_attendances,
        "matter_attendances": matter_attendances,
        "documents_uploaded": documents_uploaded,
        "blog_published": blog_published,
        "blog_submitted": blog_submitted,
        "blog_drafts": blog_drafts,
        "blog_published_in_range": blog_published_in_range,
        "daily_completions": daily_completion_rows,
        "recent_tasks": recent_tasks,
        "recent_activity": recent_activity,
        "sessions": sessions,
    }
    payload["charts"] = build_employee_performance_charts(
        employee,
        days=days,
        analytics=payload,
    )
    return payload
