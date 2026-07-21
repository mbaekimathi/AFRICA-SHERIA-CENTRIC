"""Helpers for creating and serialising employee notifications."""

from __future__ import annotations

from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from .models import CaseTask, Employee, MatterTask, Notification
from .workspace import workspace_reverse


CATEGORY_LABELS = {
    Notification.Category.TASK: "Tasks",
    Notification.Category.REMINDER: "Reminders",
    Notification.Category.MESSAGE: "Messages",
}

CATEGORY_PAGE = {
    Notification.Category.TASK: "tasks",
    Notification.Category.REMINDER: "reminders",
    Notification.Category.MESSAGE: "messages",
}

# Sidebar / utility badge keys driven by unread notification categories
UTILITY_BADGE_CATEGORIES = {
    "tasks": Notification.Category.TASK,
    "calendar": Notification.Category.REMINDER,
    "reminders": Notification.Category.REMINDER,
    "messages": Notification.Category.MESSAGE,
}

# Tasks that still need assignee attention / reminders
ACTIVE_TASK_STATUSES = (
    CaseTask.Status.PENDING,
    CaseTask.Status.ACCEPTED,
)


def _utility_url(employee, page_slug: str) -> str:
    return workspace_reverse(employee.role_slug, "dashboard", page_slug)


def _tasks_url(employee, *, kind: str | None = None, task_id: int | None = None) -> str:
    url = _utility_url(employee, "tasks")
    if kind and task_id:
        return f"{url}?kind={kind}&id={task_id}"
    return url


def notify_case_task(task: CaseTask) -> tuple[Notification, bool]:
    """Notify only the assignee about a new case task. Returns (notification, created)."""
    assignee = task.assignee
    title_label = (task.title or "").strip() or str(task.case)
    body = (task.instructions or "").strip() or f"Due {task.due_date:%d %b %Y}."
    body = f"{body}\n\nAccept or reject this task from your Tasks list."
    return Notification.objects.get_or_create(
        recipient=assignee,
        source_key=f"case_task:{task.pk}",
        defaults={
            "category": Notification.Category.TASK,
            "title": f"New task: {title_label}",
            "body": body.strip(),
            "target_url": _tasks_url(assignee, kind="case", task_id=task.pk),
        },
    )


def notify_matter_task(task: MatterTask) -> tuple[Notification, bool]:
    """Notify only the assignee about a new matter task. Returns (notification, created)."""
    assignee = task.assignee
    title_label = (task.title or "").strip() or str(task.matter)
    body = (task.instructions or "").strip() or f"Due {task.due_date:%d %b %Y}."
    body = f"{body}\n\nAccept or reject this task from your Tasks list."
    return Notification.objects.get_or_create(
        recipient=assignee,
        source_key=f"matter_task:{task.pk}",
        defaults={
            "category": Notification.Category.TASK,
            "title": f"New task: {title_label}",
            "body": body.strip(),
            "target_url": _tasks_url(assignee, kind="matter", task_id=task.pk),
        },
    )


def notify_task_accepted(task, *, kind: str) -> Notification | None:
    """Notify the employee who tasked the assignee that the task was accepted."""
    assigner = task.created_by
    if not assigner or assigner.pk == task.assignee_id:
        return None

    subject = task.case if kind == "case" else task.matter
    return notify_message(
        assigner,
        title=f"Task accepted: {subject}",
        body=(
            f"{task.assignee.get_full_name()} accepted the task "
            f"(due {task.due_date:%d %b %Y})."
        ),
        source_key=f"{kind}_task_accepted:{task.pk}",
        target_url=_utility_url(assigner, "messages"),
    )


def notify_task_rejected(task, *, kind: str) -> Notification | None:
    """Notify the employee who tasked the assignee that the task was rejected."""
    assigner = task.created_by
    if not assigner or assigner.pk == task.assignee_id:
        return None

    subject = task.case if kind == "case" else task.matter
    reason = (task.rejection_reason or "").strip() or "No reason given."
    return notify_message(
        assigner,
        title=f"Task rejected: {subject}",
        body=(
            f"{task.assignee.get_full_name()} rejected the task.\n\n"
            f"Reason: {reason}"
        ),
        source_key=f"{kind}_task_rejected:{task.pk}",
        target_url=_utility_url(assigner, "messages"),
    )


def ensure_due_reminders(employee) -> int:
    """
    Materialise reminder notifications for tasks whose reminder_at has passed.

    Returns the number of new reminder notifications created.
    """
    now = timezone.now()
    created = 0

    for task in CaseTask.objects.filter(
        assignee=employee,
        status__in=ACTIVE_TASK_STATUSES,
        reminder_at__isnull=False,
        reminder_at__lte=now,
    ).select_related("case", "assignee"):
        _, was_created = Notification.objects.get_or_create(
            recipient=employee,
            source_key=f"case_task_reminder:{task.pk}",
            defaults={
                "category": Notification.Category.REMINDER,
                "title": f"Reminder: {task.case}",
                "body": (task.instructions or "").strip()
                or f"Due {task.due_date:%d %b %Y}.",
                "target_url": _utility_url(employee, "reminders"),
            },
        )
        if was_created:
            created += 1

    for task in MatterTask.objects.filter(
        assignee=employee,
        status__in=ACTIVE_TASK_STATUSES,
        reminder_at__isnull=False,
        reminder_at__lte=now,
    ).select_related("matter", "assignee"):
        _, was_created = Notification.objects.get_or_create(
            recipient=employee,
            source_key=f"matter_task_reminder:{task.pk}",
            defaults={
                "category": Notification.Category.REMINDER,
                "title": f"Reminder: {task.matter}",
                "body": (task.instructions or "").strip()
                or f"Due {task.due_date:%d %b %Y}.",
                "target_url": _utility_url(employee, "reminders"),
            },
        )
        if was_created:
            created += 1

    return created


def ensure_task_notifications(employee) -> int:
    """Backfill task notifications for pending assignments that lack one."""
    created = 0

    for task in CaseTask.objects.filter(
        assignee=employee,
        status=CaseTask.Status.PENDING,
    ).select_related("case", "assignee"):
        _, was_created = notify_case_task(task)
        if was_created:
            created += 1

    for task in MatterTask.objects.filter(
        assignee=employee,
        status=MatterTask.Status.PENDING,
    ).select_related("matter", "assignee"):
        _, was_created = notify_matter_task(task)
        if was_created:
            created += 1

    return created


def notify_message(
    recipient,
    *,
    title: str,
    body: str = "",
    source_key: str,
    target_url: str | None = None,
) -> Notification:
    """Create or return a message notification."""
    notification, _created = Notification.objects.get_or_create(
        recipient=recipient,
        source_key=source_key,
        defaults={
            "category": Notification.Category.MESSAGE,
            "title": title,
            "body": body,
            "target_url": target_url or _utility_url(recipient, "messages"),
        },
    )
    return notification


def notify_google_drive_disconnected(*, disconnected_by: Employee) -> int:
    """
    Notify every active employee that firm Google Drive was disconnected.

    Returns the number of notifications created.
    """
    actor = disconnected_by.get_full_name() or disconnected_by.login_code
    event_key = f"google_drive_disconnected:{timezone.now().strftime('%Y%m%d%H%M%S%f')}"
    title = "Google Drive disconnected"
    body = (
        f"{actor} disconnected the firm Google Drive account. "
        "Document features that rely on Drive will not work until it is connected again."
    )
    created = 0
    for employee in Employee.objects.filter(status=Employee.Status.ACTIVE).iterator():
        settings_url = workspace_reverse(
            employee.role_slug, "dashboard", "google-drive-settings"
        )
        _, was_created = Notification.objects.get_or_create(
            recipient=employee,
            source_key=f"{event_key}:{employee.pk}",
            defaults={
                "category": Notification.Category.MESSAGE,
                "title": title,
                "body": body,
                "target_url": settings_url,
            },
        )
        if was_created:
            created += 1
    return created


def serialize_notification(notification: Notification) -> dict:
    created = timezone.localtime(notification.created_at)
    return {
        "id": notification.pk,
        "category": notification.category,
        "category_label": notification.get_category_display(),
        "title": notification.title,
        "body": notification.body,
        "url": reverse(
            "accounts:workspace_notification_open",
            kwargs={"notification_id": notification.pk},
        ),
        "is_read": notification.is_read,
        "created_at": created.isoformat(),
        "created_display": created.strftime("%d %b · %H:%M"),
    }


def unread_counts_by_category(employee) -> dict[str, int]:
    """Return total unread notification counts keyed by category."""
    rows = (
        Notification.objects.filter(recipient=employee, is_read=False)
        .values("category")
        .annotate(total=Count("id"))
    )
    counts = {category: 0 for category, _label in Notification.Category.choices}
    for row in rows:
        counts[row["category"]] = row["total"]
    return counts


def utility_badge_counts(employee) -> dict[str, int]:
    """Unread counts for sidebar utility icons (and related pages)."""
    by_category = unread_counts_by_category(employee)
    return {
        slug: by_category.get(category, 0)
        for slug, category in UTILITY_BADGE_CATEGORIES.items()
    }


def notifications_payload(employee, *, limit: int = 40) -> dict:
    """Build the live-poll payload, grouped by category (latest first)."""
    ensure_task_notifications(employee)
    ensure_due_reminders(employee)
    # The polling request only claims work; network checks run off-request.
    from .news_watch import launch_due_news_watches

    launch_due_news_watches(employee_id=employee.pk)

    by_category = unread_counts_by_category(employee)
    unread_count = sum(by_category.values())
    badges = {
        slug: by_category.get(category, 0)
        for slug, category in UTILITY_BADGE_CATEGORIES.items()
    }

    # Fetch each category independently so Tasks / Reminders / Messages
    # each surface their own latest items (newest first).
    per_category = max(1, limit // 3)
    recent = []
    ordered_groups = []
    for category in (
        Notification.Category.TASK,
        Notification.Category.REMINDER,
        Notification.Category.MESSAGE,
    ):
        items_qs = list(
            Notification.objects.filter(recipient=employee, category=category).order_by(
                "-created_at"
            )[:per_category]
        )
        recent.extend(items_qs)
        ordered_groups.append(
            {
                "category": category,
                "label": CATEGORY_LABELS[category],
                "page_url": _utility_url(employee, CATEGORY_PAGE[category]),
                "unread": by_category.get(category, 0),
                "items": [serialize_notification(item) for item in items_qs],
            }
        )

    revision = (
        "|".join(f"{n.pk}:{'1' if n.is_read else '0'}" for n in recent)
        + f"|u:{unread_count}"
        + "|b:"
        + ",".join(f"{slug}:{count}" for slug, count in sorted(badges.items()))
    )

    return {
        "unread_count": unread_count,
        "has_unread": unread_count > 0,
        "badges": badges,
        "revision": revision,
        "groups": ordered_groups,
    }
