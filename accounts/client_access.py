"""Session-scoped query helpers for the client portal.

Every queryset is filtered to the authenticated client from the session.
Never trust a client id from the URL without matching the session client.
"""

from __future__ import annotations

from datetime import date

from django.db.models import Q, QuerySet
from django.urls import reverse

from .models import (
    Client,
    CourtAttendance,
    Document,
    LitigationCase,
    MatterAttendance,
    NonLitigationMatter,
)

# Statuses clients may see (hide pending approval / rejected internals).
CLIENT_VISIBLE_CASE_STATUSES = (
    LitigationCase.Status.ACTIVE,
    LitigationCase.Status.CLOSED,
)
CLIENT_VISIBLE_MATTER_STATUSES = (
    NonLitigationMatter.Status.ACTIVE,
    NonLitigationMatter.Status.CLOSED,
)


def client_cases(client: Client) -> QuerySet[LitigationCase]:
    return (
        LitigationCase.objects.filter(
            client=client,
            status__in=CLIENT_VISIBLE_CASE_STATUSES,
        )
        .select_related("assigned_to", "client")
        .order_by("-filing_date", "-created_at")
    )


def get_object_or_404_case(client: Client, case_id: int) -> LitigationCase:
    from django.shortcuts import get_object_or_404

    return get_object_or_404(client_cases(client), pk=case_id)


def client_matters(client: Client) -> QuerySet[NonLitigationMatter]:
    return (
        NonLitigationMatter.objects.filter(
            client=client,
            status__in=CLIENT_VISIBLE_MATTER_STATUSES,
        )
        .select_related("assigned_to", "client")
        .order_by("-date_opened", "-created_at")
    )


def get_object_or_404_matter(client: Client, matter_id: int) -> NonLitigationMatter:
    from django.shortcuts import get_object_or_404

    return get_object_or_404(client_matters(client), pk=matter_id)


def client_documents(client: Client) -> QuerySet[Document]:
    """Documents on this client's cases/matters, or explicitly linked to them."""
    # Any matter/case owned by this client (except rejected / still pending).
    visible_case = ~Q(
        case__status__in=(
            LitigationCase.Status.PENDING_APPROVAL,
            LitigationCase.Status.REJECTED,
        )
    )
    visible_matter = ~Q(
        matter__status__in=(
            NonLitigationMatter.Status.PENDING_APPROVAL,
            NonLitigationMatter.Status.REJECTED,
        )
    )
    return (
        Document.objects.filter(
            (Q(case__client=client) & visible_case)
            | (Q(matter__client=client) & visible_matter)
            | Q(linked_client=client)
        )
        .select_related("case", "matter", "case__client", "matter__client", "uploaded_by")
        .distinct()
        .order_by("-updated_at", "-created_at")
    )


def get_object_or_404_document(client: Client, document_id: int) -> Document:
    from django.shortcuts import get_object_or_404

    return get_object_or_404(client_documents(client), pk=document_id)


def _drive_type_label(mime_type: str) -> str:
    mime = (mime_type or "").strip()
    if mime == "application/vnd.google-apps.document":
        return "Google Docs"
    if mime == "application/vnd.google-apps.spreadsheet":
        return "Google Sheets"
    if mime == "application/vnd.google-apps.presentation":
        return "Google Slides"
    if mime == "application/pdf":
        return "PDF"
    if mime.startswith("image/"):
        return "Image"
    if mime.startswith("text/"):
        return "Text"
    if "word" in mime:
        return "Word"
    return "File"


def _list_drive_files_under(folder_id: str, *, depth: int = 0) -> list[dict]:
    """Non-folder Drive children under folder_id (one level of subfolders)."""
    from .google_drive import FOLDER_MIME, GoogleDriveAPIError, list_drive_children

    folder_id = (folder_id or "").strip()
    if not folder_id:
        return []
    try:
        children = list_drive_children(folder_id)
    except GoogleDriveAPIError:
        return []

    files: list[dict] = []
    for item in children:
        mime = (item.get("mimeType") or "").strip()
        if mime == FOLDER_MIME:
            if depth < 2:
                files.extend(
                    _list_drive_files_under(item.get("id") or "", depth=depth + 1)
                )
            continue
        files.append(item)
    return files


def client_document_catalog(client: Client) -> list[dict]:
    """
    View-only document list for the session client.

    Combines Document rows with files found under the client's matter/case
    Drive folders (so Drive uploads still appear even without a DB row).
    """
    from django.utils.dateparse import parse_datetime
    from django.utils import timezone as dj_tz
    from datetime import datetime as dt

    entries: list[dict] = []
    seen_drive_ids: set[str] = set()

    for doc in client_documents(client):
        drive_id = (doc.drive_file_id or "").strip()
        if drive_id:
            seen_drive_ids.add(drive_id)
        if doc.case_id:
            matter_label = str(doc.case)
            matter_url = reverse(
                "accounts:client_matter_case", kwargs={"case_id": doc.case_id}
            )
        elif doc.matter_id:
            matter_label = doc.matter.matter_title
            matter_url = reverse(
                "accounts:client_matter_detail", kwargs={"matter_id": doc.matter_id}
            )
        else:
            matter_label = "Your account"
            matter_url = ""
        entries.append(
            {
                "key": f"doc-{doc.pk}",
                "document_id": doc.pk,
                "drive_file_id": drive_id,
                "title": doc.title,
                "description": doc.description or "",
                "type_label": doc.type_label,
                "matter_label": matter_label,
                "matter_url": matter_url,
                "updated_at": doc.updated_at,
                "can_view": bool(doc.local_file or drive_id),
                "view_url": reverse(
                    "accounts:client_document_view", kwargs={"document_id": doc.pk}
                ),
            }
        )

    # Walk case / matter Drive folders for any files not yet linked as Document.
    for case in client_cases(client):
        folder_id = (case.drive_folder_id or "").strip()
        if not folder_id:
            continue
        matter_url = reverse(
            "accounts:client_matter_case", kwargs={"case_id": case.pk}
        )
        for item in _list_drive_files_under(folder_id):
            file_id = (item.get("id") or "").strip()
            if not file_id or file_id in seen_drive_ids:
                continue
            seen_drive_ids.add(file_id)
            modified = parse_datetime(item.get("modifiedTime") or "")
            if modified and dj_tz.is_naive(modified):
                modified = dj_tz.make_aware(modified, timezone=dj_tz.utc)
            entries.append(
                {
                    "key": f"drive-{file_id}",
                    "document_id": None,
                    "drive_file_id": file_id,
                    "title": item.get("name") or "Untitled",
                    "description": "",
                    "type_label": _drive_type_label(item.get("mimeType") or ""),
                    "matter_label": str(case),
                    "matter_url": matter_url,
                    "updated_at": modified,
                    "can_view": True,
                    "mime_type": item.get("mimeType") or "",
                    "view_url": reverse(
                        "accounts:client_drive_document_view",
                        kwargs={"drive_file_id": file_id},
                    ),
                }
            )

    for matter in client_matters(client):
        folder_id = (matter.drive_folder_id or "").strip()
        if not folder_id:
            continue
        matter_url = reverse(
            "accounts:client_matter_detail", kwargs={"matter_id": matter.pk}
        )
        for item in _list_drive_files_under(folder_id):
            file_id = (item.get("id") or "").strip()
            if not file_id or file_id in seen_drive_ids:
                continue
            seen_drive_ids.add(file_id)
            modified = parse_datetime(item.get("modifiedTime") or "")
            if modified and dj_tz.is_naive(modified):
                modified = dj_tz.make_aware(modified, timezone=dj_tz.utc)
            entries.append(
                {
                    "key": f"drive-{file_id}",
                    "document_id": None,
                    "drive_file_id": file_id,
                    "title": item.get("name") or "Untitled",
                    "description": "",
                    "type_label": _drive_type_label(item.get("mimeType") or ""),
                    "matter_label": matter.matter_title,
                    "matter_url": matter_url,
                    "updated_at": modified,
                    "can_view": True,
                    "mime_type": item.get("mimeType") or "",
                    "view_url": reverse(
                        "accounts:client_drive_document_view",
                        kwargs={"drive_file_id": file_id},
                    ),
                }
            )

    def _sort_ts(row):
        ts = row.get("updated_at")
        if ts is None:
            return dt.min.replace(tzinfo=dj_tz.utc)
        return ts

    entries.sort(key=_sort_ts, reverse=True)
    return entries


def client_owns_drive_file(client: Client, drive_file_id: str) -> bool:
    """True when drive_file_id belongs to a Document or folder under this client."""
    drive_file_id = (drive_file_id or "").strip()
    if not drive_file_id:
        return False
    if client_documents(client).filter(drive_file_id=drive_file_id).exists():
        return True
    for case in client_cases(client):
        if any(
            (item.get("id") or "").strip() == drive_file_id
            for item in _list_drive_files_under(case.drive_folder_id or "")
        ):
            return True
    for matter in client_matters(client):
        if any(
            (item.get("id") or "").strip() == drive_file_id
            for item in _list_drive_files_under(matter.drive_folder_id or "")
        ):
            return True
    return False


def client_calendar_by_day(
    client: Client,
    month_start: date,
    month_end: date,
) -> dict[int, list]:
    """Court and matter attendances for this client's matters only."""
    from .views import (
        _append_calendar_event,
        _court_appearance_calendar_extras,
        _matter_appearance_calendar_extras,
    )

    by_day: dict[int, list] = {}
    case_ids = list(client_cases(client).values_list("pk", flat=True))
    matter_ids = list(client_matters(client).values_list("pk", flat=True))

    court_attendances = (
        CourtAttendance.objects.filter(case_id__in=case_ids)
        .filter(
            Q(attendance_date__gte=month_start, attendance_date__lte=month_end)
            | Q(next_court_date__gte=month_start, next_court_date__lte=month_end)
        )
        .select_related("case", "case__client", "case__assigned_to")
        .order_by("attendance_date", "pk")
    )
    for attendance in court_attendances:
        case_url = reverse(
            "accounts:client_matter_case",
            kwargs={"case_id": attendance.case_id},
        )
        counsel = (
            attendance.case.assigned_to.get_full_name()
            if attendance.case.assigned_to_id
            else "Counsel assigned by firm"
        )
        if month_start <= attendance.attendance_date <= month_end:
            activity = attendance.activity_type or "Court attendance"
            _append_calendar_event(
                by_day,
                attendance.attendance_date,
                {
                    "kind": "court",
                    "due_date": attendance.attendance_date,
                    "status": "done",
                    "status_label": "Recorded",
                    "subject": f"{activity} — {attendance.case}",
                    "subject_meta": counsel,
                    "url": case_url,
                },
            )
        if (
            attendance.next_court_date
            and month_start <= attendance.next_court_date <= month_end
        ):
            activity = (
                attendance.next_activity_type
                or attendance.activity_type
                or "Court appearance"
            )
            extras = _court_appearance_calendar_extras(attendance)
            _append_calendar_event(
                by_day,
                attendance.next_court_date,
                {
                    "kind": "court",
                    "due_date": attendance.next_court_date,
                    "status": "active",
                    "status_label": extras["status_label"],
                    "subject": f"{activity} — {attendance.case}",
                    "subject_meta": counsel,
                    "virtual_link": extras["virtual_link"],
                    "is_virtual": extras["is_virtual"],
                    "url": case_url,
                },
            )

    matter_attendances = (
        MatterAttendance.objects.filter(matter_id__in=matter_ids)
        .filter(
            Q(attendance_date__gte=month_start, attendance_date__lte=month_end)
            | Q(
                next_attendance_date__gte=month_start,
                next_attendance_date__lte=month_end,
            )
        )
        .select_related("matter", "matter__client", "matter__assigned_to")
        .order_by("attendance_date", "pk")
    )
    for attendance in matter_attendances:
        matter_url = reverse(
            "accounts:client_matter_detail",
            kwargs={"matter_id": attendance.matter_id},
        )
        counsel = (
            attendance.matter.assigned_to.get_full_name()
            if attendance.matter.assigned_to_id
            else "Counsel assigned by firm"
        )
        if month_start <= attendance.attendance_date <= month_end:
            activity = attendance.activity_type or "Matter attendance"
            _append_calendar_event(
                by_day,
                attendance.attendance_date,
                {
                    "kind": "matter_attendance",
                    "due_date": attendance.attendance_date,
                    "status": "done",
                    "status_label": "Recorded",
                    "subject": f"{activity} — {attendance.matter.matter_title}",
                    "subject_meta": counsel,
                    "url": matter_url,
                },
            )
        if (
            attendance.next_attendance_date
            and month_start <= attendance.next_attendance_date <= month_end
        ):
            activity = (
                attendance.next_activity_type
                or attendance.activity_type
                or "Matter attendance"
            )
            extras = _matter_appearance_calendar_extras(attendance)
            _append_calendar_event(
                by_day,
                attendance.next_attendance_date,
                {
                    "kind": "matter_attendance",
                    "due_date": attendance.next_attendance_date,
                    "status": "active",
                    "status_label": extras["status_label"],
                    "subject": f"{activity} — {attendance.matter.matter_title}",
                    "subject_meta": counsel,
                    "virtual_link": extras["virtual_link"],
                    "is_virtual": extras["is_virtual"],
                    "url": matter_url,
                },
            )

    return by_day


def client_reminders(client: Client, *, today: date | None = None) -> list[dict]:
    """Upcoming dates that involve the client (attendance required / optional / virtual)."""
    from django.utils import timezone

    if today is None:
        today = timezone.localdate()

    relevant = {
        CourtAttendance.ClientAttendance.REQUIRED,
        CourtAttendance.ClientAttendance.OPTIONAL,
        CourtAttendance.ClientAttendance.VIRTUAL,
    }
    reminders: list[dict] = []

    case_ids = list(client_cases(client).values_list("pk", flat=True))
    matter_ids = list(client_matters(client).values_list("pk", flat=True))

    for attendance in (
        CourtAttendance.objects.filter(
            case_id__in=case_ids,
            next_court_date__isnull=False,
            next_client_attendance__in=relevant,
        )
        .select_related("case", "case__assigned_to")
        .order_by("next_court_date")
    ):
        reminders.append(
            {
                "kind": "court",
                "due_date": attendance.next_court_date,
                "subject": (
                    f"{attendance.next_activity_type or attendance.activity_type or 'Court'} "
                    f"— {attendance.case}"
                ),
                "subject_meta": attendance.get_next_client_attendance_display(),
                "url": reverse(
                    "accounts:client_matter_case",
                    kwargs={"case_id": attendance.case_id},
                ),
                "is_due": attendance.next_court_date <= today,
                "virtual_link": (
                    attendance.virtual_link
                    if attendance.next_client_attendance
                    == CourtAttendance.ClientAttendance.VIRTUAL
                    else ""
                ),
            }
        )

    for attendance in (
        MatterAttendance.objects.filter(
            matter_id__in=matter_ids,
            next_attendance_date__isnull=False,
            next_client_attendance__in=relevant,
        )
        .select_related("matter", "matter__assigned_to")
        .order_by("next_attendance_date")
    ):
        reminders.append(
            {
                "kind": "matter_attendance",
                "due_date": attendance.next_attendance_date,
                "subject": (
                    f"{attendance.next_activity_type or attendance.activity_type or 'Attendance'} "
                    f"— {attendance.matter.matter_title}"
                ),
                "subject_meta": attendance.get_next_client_attendance_display(),
                "url": reverse(
                    "accounts:client_matter_detail",
                    kwargs={"matter_id": attendance.matter_id},
                ),
                "is_due": attendance.next_attendance_date <= today,
                "virtual_link": (
                    attendance.virtual_link
                    if attendance.next_client_attendance
                    == MatterAttendance.ClientAttendance.VIRTUAL
                    else ""
                ),
            }
        )

    reminders.sort(key=lambda item: item["due_date"] or date.max)
    return reminders
