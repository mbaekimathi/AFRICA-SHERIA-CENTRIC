"""
Employee Communications: who staff wrote to, on which channel, and what they said.

Email and SMS are read back from :class:`EmployeeCommunication`, WhatsApp from the
conversation store, so every channel page can render the same row shape.
"""

from __future__ import annotations

from django.db.models import Count, Max, Q

from .models import Client, Employee, EmployeeCommunication, WhatsAppMessage

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
    """Every employee with their message count and last send on this channel."""
    if channel_key == "whatsapp":
        counts = {
            row["sent_by"]: row
            for row in _whatsapp_sent_messages()
            .values("sent_by")
            .annotate(total=Count("id"), last_at=Max("created_at"))
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


def _communication_row(record) -> dict:
    return {
        "id": record.pk,
        "sent_at": record.created_at,
        "recipient_name": record.recipient_display,
        "recipient_kind": record.recipient_kind,
        "to_address": record.to_address,
        "subject": record.subject,
        "body": record.body,
        "status": record.status,
        "status_label": record.get_status_display(),
        "error_message": record.error_message,
        "from_identity": record.from_identity,
    }


def employee_messages(channel_key: str, employee, *, search: str = "") -> list[dict]:
    """Messages this employee sent on a channel, newest first."""
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

    queryset = EmployeeCommunication.objects.filter(
        sender=employee, channel=channel_key
    ).select_related("to_client", "to_employee")
    if term:
        queryset = queryset.filter(
            Q(subject__icontains=term)
            | Q(body__icontains=term)
            | Q(to_address__icontains=term)
            | Q(to_client__first_name__icontains=term)
            | Q(to_client__last_name__icontains=term)
            | Q(to_client__company_name__icontains=term)
            | Q(to_employee__first_name__icontains=term)
            | Q(to_employee__last_name__icontains=term)
        )
    return [_communication_row(record) for record in queryset]


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

    record = (
        EmployeeCommunication.objects.filter(
            pk=message_id, sender=employee, channel=channel_key
        )
        .select_related("to_client", "to_employee")
        .first()
    )
    return _communication_row(record) if record else None
