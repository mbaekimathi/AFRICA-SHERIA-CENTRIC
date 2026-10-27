"""
Employee Communications: who staff wrote to, on which channel, and what they said.

Email and SMS are read back from :class:`EmployeeCommunication`, WhatsApp from the
conversation store, so every channel page can render the same row shape.
"""

from __future__ import annotations

from django.db.models import Count, Max, Q

from .models import (
    Client,
    Employee,
    EmployeeCommunication,
    EmployeeCommunicationAttachment,
    WhatsAppMessage,
)

CHANNEL_PAGES = {
    "email-communications": {
        "key": "email",
        "slug": "email-communications",
        "label": "Email communications",
        "noun": "email",
        "noun_plural": "emails",
    },
    "whatsapp-communications": {
        "key": "whatsapp",
        "slug": "whatsapp-communications",
        "label": "WhatsApp communications",
        "noun": "WhatsApp message",
        "noun_plural": "WhatsApp messages",
    },
    "sms-communications": {
        "key": "sms",
        "slug": "sms-communications",
        "label": "SMS communications",
        "noun": "SMS",
        "noun_plural": "SMS messages",
    },
}

CHANNEL_PAGE_SLUGS = frozenset(CHANNEL_PAGES)
_CHANNELS_BY_KEY = {meta["key"]: meta for meta in CHANNEL_PAGES.values()}

# Folder tabs on the email communications log — drafts are read live from
# the employee's own work mailbox because they are never logged as records.
EMAIL_LOG_FOLDERS = (
    {"key": "all", "label": "All mail"},
    {"key": "inbox", "label": "Inbox"},
    {"key": "sent", "label": "Sent"},
    {"key": "drafts", "label": "Drafts"},
)
EMAIL_LOG_FOLDER_KEYS = frozenset(item["key"] for item in EMAIL_LOG_FOLDERS)


def channel_page(slug: str) -> dict | None:
    """Channel metadata for an Employee Communications page slug."""
    return CHANNEL_PAGES.get((slug or "").strip().lower())


def channel_by_key(key: str) -> dict | None:
    return _CHANNELS_BY_KEY.get((key or "").strip().lower())


# --- Compose recipients -------------------------------------------------


def _client_reachable(client, channel: str) -> bool:
    return bool(client.email if channel == "email" else client.phone)


def _employee_reachable(employee, channel: str) -> bool:
    return bool(employee.work_email if channel == "email" else employee.work_phone)


def message_recipient_groups(channel: str, *, exclude_employee=None) -> list[dict]:
    """Clients and colleagues who can be reached on this channel."""
    clients = [
        {
            "value": f"client:{client.pk}",
            "label": client.get_full_name(),
            "hint": (client.email if channel == "email" else client.phone) or "",
        }
        for client in Client.objects.filter(status=Client.Status.ACTIVE).order_by(
            "company_name", "first_name", "last_name", "email"
        )
        if _client_reachable(client, channel)
    ]

    colleagues_qs = Employee.objects.filter(status=Employee.Status.ACTIVE).order_by(
        "first_name", "last_name"
    )
    if exclude_employee is not None:
        colleagues_qs = colleagues_qs.exclude(pk=exclude_employee.pk)
    colleagues = [
        {
            "value": f"employee:{employee.pk}",
            "label": employee.get_full_name(),
            "hint": (
                employee.work_email if channel == "email" else employee.work_phone
            )
            or "",
        }
        for employee in colleagues_qs
        if _employee_reachable(employee, channel)
    ]

    groups = []
    if clients:
        groups.append({"label": "Clients", "options": clients})
    if colleagues:
        groups.append({"label": "Employees", "options": colleagues})
    return groups


def _looks_like_email(value: str) -> bool:
    text = (value or "").strip()
    if "@" not in text or " " in text or ":" in text:
        return False
    local, _, domain = text.partition("@")
    return bool(local and domain and "." in domain)


def resolve_message_recipient(
    raw: str, channel: str, *, exclude_employee=None
) -> tuple[object | None, object | None, str, str]:
    """
    Resolve a recipient value for Messages compose.

    Accepts:
    - ``client:<pk>`` / ``employee:<pk>`` for registered people
    - a bare email address on the email channel (registered or external)

    Returns ``(client, employee, external_email, error)``. Exactly one of
    client/employee/external_email is set when there is no error.
    """
    value = (raw or "").strip()
    kind, _, pk = value.partition(":")
    if kind in {"client", "employee"} and pk.isdigit():
        if kind == "client":
            client = Client.objects.filter(
                pk=int(pk), status=Client.Status.ACTIVE
            ).first()
            if client is None:
                return None, None, "", "Select an active client."
            if not _client_reachable(client, channel):
                missing = "email address" if channel == "email" else "phone number"
                return (
                    None,
                    None,
                    "",
                    f"{client.get_full_name()} has no {missing} on file.",
                )
            return client, None, "", ""

        employee = Employee.objects.filter(
            pk=int(pk), status=Employee.Status.ACTIVE
        ).first()
        if employee is None:
            return None, None, "", "Select an active employee."
        if exclude_employee is not None and employee.pk == exclude_employee.pk:
            return None, None, "", "You cannot send this message to yourself."
        if not _employee_reachable(employee, channel):
            missing = "work email" if channel == "email" else "work phone"
            return (
                None,
                None,
                "",
                f"{employee.get_full_name()} has no {missing} yet.",
            )
        return None, employee, "", ""

    if channel == "email" and _looks_like_email(value):
        email = value.lower()
        if exclude_employee is not None:
            own = (getattr(exclude_employee, "work_email", None) or "").strip().lower()
            if own and own == email:
                return None, None, "", "You cannot send this message to yourself."

        client = Client.objects.filter(
            email__iexact=email, status=Client.Status.ACTIVE
        ).first()
        if client is not None:
            return client, None, "", ""

        employee = Employee.objects.filter(
            work_email__iexact=email, status=Employee.Status.ACTIVE
        ).first()
        if employee is not None:
            return None, employee, "", ""

        return None, None, email, ""

    if channel == "email":
        return None, None, "", "Select a recipient or type a valid email address."
    return None, None, "", "Select who this message is going to."


# --- Reading the log ----------------------------------------------------


def _whatsapp_sent_messages():
    return WhatsAppMessage.objects.filter(
        direction=WhatsAppMessage.Direction.OUTBOUND,
        sent_by__isnull=False,
    )


def employee_channel_summaries(channel_key: str) -> list[dict]:
    """Every employee with their message count and last activity on this channel."""
    if channel_key == "whatsapp":
        counts = {
            row["sent_by"]: row
            for row in _whatsapp_sent_messages()
            .values("sent_by")
            .annotate(total=Count("id"), last_at=Max("created_at"))
        }
    elif channel_key == "email":
        # Emails they sent or received (colleague mail) both count as dealing with.
        sent = {
            row["sender"]: row
            for row in EmployeeCommunication.objects.filter(channel=channel_key)
            .values("sender")
            .annotate(total=Count("id"), last_at=Max("created_at"))
        }
        received = {
            row["to_employee"]: row
            for row in EmployeeCommunication.objects.filter(
                channel=channel_key, to_employee__isnull=False
            )
            .values("to_employee")
            .annotate(total=Count("id"), last_at=Max("created_at"))
        }
        employee_ids = set(sent) | set(received)
        counts = {}
        for employee_id in employee_ids:
            sent_row = sent.get(employee_id) or {}
            received_row = received.get(employee_id) or {}
            last_candidates = [
                value
                for value in (sent_row.get("last_at"), received_row.get("last_at"))
                if value is not None
            ]
            counts[employee_id] = {
                "total": (sent_row.get("total") or 0) + (received_row.get("total") or 0),
                "last_at": max(last_candidates) if last_candidates else None,
            }
    else:
        counts = {
            row["sender"]: row
            for row in EmployeeCommunication.objects.filter(channel=channel_key)
            .values("sender")
            .annotate(total=Count("id"), last_at=Max("created_at"))
        }

    summaries = []
    employees = Employee.objects.exclude(
        status=Employee.Status.PENDING_ONBOARDING
    ).order_by("first_name", "last_name")
    for employee in employees:
        row = counts.get(employee.pk) or {}
        summaries.append(
            {
                "employee": employee,
                "total": row.get("total", 0),
                "last_at": row.get("last_at"),
            }
        )
    summaries.sort(key=lambda item: (-item["total"], item["employee"].get_full_name()))
    return summaries


def _whatsapp_row(message) -> dict:
    conversation = message.conversation
    client = conversation.client
    return {
        "id": message.pk,
        "sent_at": message.created_at,
        "direction": "sent",
        "direction_label": "Sent",
        "counterpart_name": conversation.title,
        "counterpart_kind": "Client" if client else "Contact",
        "recipient_name": conversation.title,
        "recipient_kind": "Client" if client else "Contact",
        "to_address": conversation.msisdn,
        "subject": "",
        "body": message.body,
        "status": message.status,
        "status_label": message.get_status_display(),
        "error_message": message.error_message,
        "from_identity": "",
    }


def _communication_row(record, *, viewer=None) -> dict:
    is_received = (
        viewer is not None
        and record.to_employee_id == viewer.pk
        and record.sender_id != viewer.pk
    )
    if is_received:
        counterpart_name = record.sender.get_full_name() if record.sender_id else ""
        counterpart_kind = "Employee"
        counterpart_address = record.from_identity or ""
        direction = "received"
        direction_label = "Received"
    else:
        counterpart_name = record.recipient_display
        counterpart_kind = record.recipient_kind
        counterpart_address = record.to_address
        direction = "sent"
        direction_label = "Sent"
    return {
        "id": record.pk,
        "sent_at": record.created_at,
        "direction": direction,
        "direction_label": direction_label,
        "counterpart_name": counterpart_name,
        "counterpart_kind": counterpart_kind,
        "recipient_name": counterpart_name,
        "recipient_kind": counterpart_kind,
        "to_address": counterpart_address or record.to_address,
        "subject": record.subject,
        "body": record.body,
        "status": record.status,
        "status_label": record.get_status_display(),
        "error_message": record.error_message,
        "from_identity": record.from_identity,
    }


def employee_messages(
    channel_key: str,
    employee,
    *,
    search: str = "",
    folder: str = "all",
    mailbox_email: str = "",
) -> list[dict]:
    """Messages this employee dealt with on a channel, newest first."""
    term = (search or "").strip()
    if channel_key == "whatsapp":
        queryset = (
            _whatsapp_sent_messages()
            .filter(sent_by=employee)
            .select_related("conversation", "conversation__client")
            .order_by("-created_at", "-id")
        )
        if term:
            queryset = queryset.filter(
                Q(body__icontains=term)
                | Q(conversation__display_name__icontains=term)
                | Q(conversation__msisdn__icontains=term)
            )
        return [_whatsapp_row(message) for message in queryset]

    queryset = EmployeeCommunication.objects.filter(channel=channel_key)
    if channel_key == "email":
        address = (mailbox_email or "").strip().lower()
        if folder == "inbox":
            queryset = queryset.filter(to_employee=employee).exclude(
                sender=employee
            )
            if address:
                queryset = queryset.filter(to_address__iexact=address)
        elif folder == "sent":
            queryset = queryset.filter(sender=employee)
            if address:
                queryset = queryset.filter(from_identity__iexact=address)
        elif address:
            queryset = queryset.filter(
                Q(sender=employee, from_identity__iexact=address)
                | Q(to_employee=employee, to_address__iexact=address)
            )
        else:
            queryset = queryset.filter(
                Q(sender=employee) | Q(to_employee=employee)
            )
    else:
        queryset = queryset.filter(sender=employee)
    queryset = queryset.select_related("sender", "to_client", "to_employee").order_by(
        "-created_at", "-id"
    )
    if term:
        queryset = queryset.filter(
            Q(subject__icontains=term)
            | Q(body__icontains=term)
            | Q(to_address__icontains=term)
            | Q(from_identity__icontains=term)
            | Q(to_client__first_name__icontains=term)
            | Q(to_client__last_name__icontains=term)
            | Q(to_client__company_name__icontains=term)
            | Q(to_employee__first_name__icontains=term)
            | Q(to_employee__last_name__icontains=term)
            | Q(sender__first_name__icontains=term)
            | Q(sender__last_name__icontains=term)
        )
    return [_communication_row(record, viewer=employee) for record in queryset]


def employee_email_folder_counts(employee, *, mailbox_email: str = "") -> dict:
    """Row counts behind each email-log folder tab (drafts are live-only)."""
    base = EmployeeCommunication.objects.filter(
        channel=EmployeeCommunication.Channel.EMAIL
    )
    address = (mailbox_email or "").strip().lower()
    inbox = base.filter(to_employee=employee).exclude(sender=employee)
    sent = base.filter(sender=employee)
    both = base.filter(Q(sender=employee) | Q(to_employee=employee))
    if address:
        inbox = inbox.filter(to_address__iexact=address)
        sent = sent.filter(from_identity__iexact=address)
        both = base.filter(
            Q(sender=employee, from_identity__iexact=address)
            | Q(to_employee=employee, to_address__iexact=address)
        )
    return {"all": both.count(), "inbox": inbox.count(), "sent": sent.count()}


def employee_mailbox_drafts(
    employee, *, mailbox=None, all_mailboxes: bool = False,
    search: str = "", limit: int = 60,
):
    """Live Drafts folder from the employee's connected work mailbox(es).

    ``mailbox`` is an :class:`EmployeeMailbox` for one linked address, ``None``
    for the primary work email; ``all_mailboxes`` merges every connected
    mailbox. Returns ``(summaries, error)`` — ``error`` is ``"not-connected"``
    when the target has no mailbox credentials, or a message when IMAP failed.
    """
    from .work_mailbox import WorkMailbox, WorkMailboxError

    boxes = []
    if all_mailboxes:
        if employee.mailbox_connected:
            boxes.append((None, (employee.work_email or "").strip()))
        boxes += [
            (extra, (extra.email or "").strip())
            for extra in employee.extra_mailboxes.all()
            if extra.mailbox_connected
        ]
    else:
        if mailbox is not None:
            target, address = mailbox, (mailbox.email or "").strip()
        else:
            target, address = employee, (employee.work_email or "").strip()
        if target.mailbox_connected:
            boxes.append((mailbox, address))
    if not boxes:
        return [], "not-connected"

    merged, errors = [], []
    for extra, address in boxes:
        try:
            rows = WorkMailbox(employee, mailbox=extra).list_messages(
                "drafts", limit=limit, search=search
            )
        except WorkMailboxError as exc:
            errors.append(f"{address}: {exc}")
            continue
        for row in rows:
            row.mailbox_address = address
        merged += rows
    merged.sort(
        key=lambda row: row.sent_at.timestamp() if row.sent_at else 0,
        reverse=True,
    )
    if merged:
        return merged[:limit], ""
    return [], "; ".join(errors) or "not-connected"


def save_communication_attachments(record, attachments) -> None:
    """Persist (filename, bytes, content_type) tuples onto a logged record."""
    from django.core.files.base import ContentFile

    for filename, payload, content_type in attachments:
        name = (filename or "").strip() or "attachment"
        EmployeeCommunicationAttachment.objects.create(
            communication=record,
            filename=name,
            content_type=content_type or "",
            size=len(payload or b""),
            file=ContentFile(payload or b"", name=name),
        )


def employee_communication_record(channel_key: str, employee, message_id: int):
    """The EmployeeCommunication row behind a log message, or None."""
    if channel_key == "whatsapp":
        return None
    queryset = EmployeeCommunication.objects.filter(pk=message_id, channel=channel_key)
    if channel_key == "email":
        queryset = queryset.filter(Q(sender=employee) | Q(to_employee=employee))
    else:
        queryset = queryset.filter(sender=employee)
    return queryset.select_related("sender", "to_client", "to_employee").first()


def employee_message(channel_key: str, employee, message_id: int) -> dict | None:
    """One message from this employee's log, or None when it is not theirs."""
    if channel_key == "whatsapp":
        message = (
            _whatsapp_sent_messages()
            .filter(pk=message_id, sent_by=employee)
            .select_related("conversation", "conversation__client")
            .first()
        )
        return _whatsapp_row(message) if message else None

    record = employee_communication_record(channel_key, employee, message_id)
    if record is None:
        return None
    row = _communication_row(record, viewer=employee)
    row["attachments"] = [
        {
            "id": attachment.pk,
            "filename": attachment.filename,
            "size": attachment.size,
            "content_type": attachment.content_type,
        }
        for attachment in record.attachments.all()
    ]
    return row
