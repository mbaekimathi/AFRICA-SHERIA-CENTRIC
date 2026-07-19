"""Build a chronological audit timeline for a litigation case."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from django.urls import reverse
from django.utils import timezone

from .document_tracking import format_duration
from .models import (
    CaseTask,
    DocumentActivity,
    DocumentOpenSession,
    LitigationCase,
)


@dataclass
class AuditEvent:
    at: datetime
    kind: str
    title: str
    summary: str = ""
    actor_name: str = ""
    href: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def kind_label(self) -> str:
        return self.kind.replace("_", " ").title()


def _actor_name(employee) -> str:
    if employee is None:
        return ""
    return employee.get_full_name() or str(employee)


def _aware(value):
    if value is None:
        return None
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def build_case_audit_events(case: LitigationCase, *, role: str) -> list[AuditEvent]:
    """Aggregate all reconstructable lifecycle events for a case."""
    events: list[AuditEvent] = []
    detail_url = reverse(
        "accounts:view_litigation_case",
        kwargs={"role": role, "case_id": case.pk},
    )
    docs_url = reverse(
        "accounts:upload_case_documents",
        kwargs={"role": role, "case_id": case.pk},
    )
    tasks_url = reverse(
        "accounts:create_case_task",
        kwargs={"role": role, "case_id": case.pk},
    )
    attendance_url = reverse(
        "accounts:update_court_attendance",
        kwargs={"role": role, "case_id": case.pk},
    )

    # Registration
    events.append(
        AuditEvent(
            at=_aware(case.created_at),
            kind="registration",
            title="Case registered",
            summary=(
                f"{case.get_case_type_display()} · {case.get_court_rank_display()} · "
                f"{case.get_station_display()}"
                + (
                    f" · Filing {case.filing_date.strftime('%d %b %Y')}"
                    if case.filing_date
                    else ""
                )
            ),
            actor_name=_actor_name(case.registered_by),
            href=detail_url,
            meta={"status": case.get_status_display()},
        )
    )

    # Approval + allocation
    if case.approved_at:
        assignee = _actor_name(case.assigned_to)
        events.append(
            AuditEvent(
                at=_aware(case.approved_at),
                kind="approval",
                title="Case approved",
                summary=(
                    f"Status set to {case.get_status_display()}"
                    + (f" · Allocated to {assignee}" if assignee else "")
                ),
                actor_name=_actor_name(case.approved_by),
                href=detail_url,
                meta={"allocated_to": assignee},
            )
        )
    elif case.assigned_to_id:
        events.append(
            AuditEvent(
                at=_aware(case.updated_at or case.created_at),
                kind="allocation",
                title="Case allocated",
                summary=f"Assigned to {_actor_name(case.assigned_to)}",
                actor_name=_actor_name(case.assigned_to),
                href=detail_url,
            )
        )

    # Soft signal for later case updates (avoid duplicating create/approve)
    if case.updated_at and case.created_at:
        updated = _aware(case.updated_at)
        created = _aware(case.created_at)
        approved = _aware(case.approved_at) if case.approved_at else None
        if updated and created and (updated - created).total_seconds() > 5:
            if not approved or abs((updated - approved).total_seconds()) > 5:
                events.append(
                    AuditEvent(
                        at=updated,
                        kind="case_update",
                        title="Case details updated",
                        summary="Case record was saved after registration.",
                        href=detail_url,
                    )
                )

    # Parties snapshot (no timestamps — show as registration context event)
    parties = list(case.parties.all())
    if parties:
        names = ", ".join(p.party_name for p in parties[:6])
        if len(parties) > 6:
            names += f" (+{len(parties) - 6} more)"
        events.append(
            AuditEvent(
                at=_aware(case.created_at),
                kind="parties",
                title=f"{len(parties)} part{'ies' if len(parties) != 1 else 'y'} on record",
                summary=names,
                actor_name=_actor_name(case.registered_by),
                href=detail_url,
            )
        )

    # Tasks
    for task in case.tasks.select_related("assignee", "created_by").all():
        label = (task.title or "").strip() or f"Task #{task.pk}"
        events.append(
            AuditEvent(
                at=_aware(task.created_at),
                kind="task_created",
                title="Task created",
                summary=(
                    f"{label} · Assigned to {_actor_name(task.assignee)}"
                    + (
                        f" · Due {task.due_date.strftime('%d %b %Y')}"
                        if task.due_date
                        else ""
                    )
                ),
                actor_name=_actor_name(task.created_by),
                href=tasks_url,
                meta={"task_status": task.get_status_display()},
            )
        )
        if task.responded_at:
            if task.status == CaseTask.Status.ACCEPTED:
                events.append(
                    AuditEvent(
                        at=_aware(task.responded_at),
                        kind="task_accepted",
                        title="Task accepted",
                        summary=label,
                        actor_name=_actor_name(task.assignee),
                        href=tasks_url,
                    )
                )
            elif task.status == CaseTask.Status.REJECTED:
                reason = (task.rejection_reason or "").strip()
                events.append(
                    AuditEvent(
                        at=_aware(task.responded_at),
                        kind="task_rejected",
                        title="Task rejected",
                        summary=f"{label}" + (f" · {reason}" if reason else ""),
                        actor_name=_actor_name(task.assignee),
                        href=tasks_url,
                    )
                )
            elif task.status == CaseTask.Status.DONE:
                events.append(
                    AuditEvent(
                        at=_aware(task.responded_at),
                        kind="task_done",
                        title="Task completed",
                        summary=label,
                        actor_name=_actor_name(task.assignee),
                        href=tasks_url,
                    )
                )

    # Court attendance
    for attendance in case.court_attendances.select_related("recorded_by").all():
        activity = (attendance.activity_type or "").strip() or "Court attendance"
        date_label = (
            attendance.attendance_date.strftime("%d %b %Y")
            if attendance.attendance_date
            else ""
        )
        events.append(
            AuditEvent(
                at=_aware(attendance.created_at),
                kind="court_attendance",
                title="Court attendance recorded",
                summary=(
                    f"{activity}"
                    + (f" · {date_label}" if date_label else "")
                    + (
                        f" · {attendance.court_room}"
                        if (attendance.court_room or "").strip()
                        else ""
                    )
                ),
                actor_name=_actor_name(attendance.recorded_by),
                href=attendance_url,
            )
        )

    # Document activities (skip noisy open heartbeats; keep lifecycle)
    noisy = {
        DocumentActivity.Action.OPENED,
        DocumentActivity.Action.SESSION_ENDED,
    }
    doc_activities = (
        DocumentActivity.objects.filter(document__case=case)
        .exclude(action__in=noisy)
        .select_related("actor", "document")
        .order_by("-created_at")
    )
    for activity in doc_activities:
        doc_title = activity.document.title if activity.document_id else "Document"
        try:
            doc_href = reverse(
                "accounts:document_activity",
                kwargs={"role": role, "document_id": activity.document_id},
            )
        except Exception:
            doc_href = docs_url
        events.append(
            AuditEvent(
                at=_aware(activity.created_at),
                kind=f"document_{activity.action}",
                title=activity.get_action_display(),
                summary=(
                    f"“{doc_title}”"
                    + (f" · {activity.detail}" if activity.detail else "")
                ),
                actor_name=_actor_name(activity.actor),
                href=doc_href,
            )
        )

    # Document open sessions (summary-level time use)
    sessions = (
        DocumentOpenSession.objects.filter(document__case=case, ended_at__isnull=False)
        .select_related("actor", "document")
        .order_by("-started_at")[:40]
    )
    for session in sessions:
        if not session.duration_seconds:
            continue
        doc_title = session.document.title if session.document_id else "Document"
        try:
            doc_href = reverse(
                "accounts:document_activity",
                kwargs={"role": role, "document_id": session.document_id},
            )
        except Exception:
            doc_href = docs_url
        events.append(
            AuditEvent(
                at=_aware(session.ended_at or session.started_at),
                kind=f"document_{session.kind}",
                title=f"Document {session.get_kind_display().lower()}",
                summary=(
                    f"“{doc_title}” · {format_duration(session.duration_seconds)}"
                ),
                actor_name=_actor_name(session.actor),
                href=doc_href,
            )
        )

    # Sort newest first; stable by kind for same timestamp
    events.sort(key=lambda e: (e.at or timezone.now(), e.kind), reverse=True)
    return [e for e in events if e.at is not None]


def case_audit_summary(events: list[AuditEvent]) -> dict[str, int]:
    counts: dict[str, int] = {
        "total": len(events),
        "registration": 0,
        "approval": 0,
        "allocation": 0,
        "tasks": 0,
        "court": 0,
        "documents": 0,
        "updates": 0,
    }
    for event in events:
        kind = event.kind
        if kind == "registration":
            counts["registration"] += 1
        elif kind == "approval":
            counts["approval"] += 1
        elif kind == "allocation":
            counts["allocation"] += 1
        elif kind.startswith("task_"):
            counts["tasks"] += 1
        elif kind == "court_attendance":
            counts["court"] += 1
        elif kind.startswith("document_"):
            counts["documents"] += 1
        elif kind in {"case_update", "parties"}:
            counts["updates"] += 1
    return counts
