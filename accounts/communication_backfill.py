"""Match logged emails to their mailbox copies and import attachments.

EmployeeCommunication rows only keep subject/body; the files travelled with the
real email on the mail server. Each attachment-less log row can be matched to
its copy in the sender's Sent folder (or a colleague recipient's Inbox) so the
files can be copied onto the record.

Used by the ``backfill_communication_attachments`` command (bulk) and by the
message detail page (one email on demand).
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from .employee_communications import save_communication_attachments
from .work_mailbox import WorkMailbox, WorkMailboxError

_NO_SUBJECT = "(no subject)"
DEFAULT_TOLERANCE_MINUTES = 15
DEFAULT_LIMIT = 500


def norm_subject(value: str) -> str:
    text = " ".join((value or "").split()).lower()
    return "" if text == _NO_SUBJECT else text


def aware(value):
    if value is None:
        return None
    if timezone.is_naive(value):
        return timezone.make_aware(value)
    return value


def candidate_sources(record) -> list[tuple]:
    """(employee, mailbox_or_None, folder) lookups that may hold the email."""
    sources = []
    sender = record.sender
    from_identity = (record.from_identity or "").strip().lower()
    if sender is not None:
        mailbox = None
        usable = False
        if from_identity:
            for row in sender.mailbox_rows():
                if row["email"] == from_identity and row["connected"]:
                    mailbox = sender.linked_mailbox_for(row["key"])
                    usable = True
                    break
        elif sender.mailbox_connected:
            usable = True
        if usable:
            sources.append((sender, mailbox, "sent"))
    recipient = record.to_employee
    if recipient is not None and recipient.mailbox_connected:
        sources.append((recipient, None, "inbox"))
    return sources


def best_match(record, summaries, folder, tolerance: timedelta):
    """Closest mail summary for a log row: same subject + address + timestamp."""
    subject = norm_subject(record.subject)
    needle = (
        record.to_address if folder == "sent" else (record.from_identity or "")
    ).strip().lower()
    created = aware(record.created_at)
    best, best_delta = None, None
    for summary in summaries:
        if norm_subject(summary.subject) != subject:
            continue
        haystack = (
            summary.to_addrs if folder == "sent" else summary.from_addr
        ) or ""
        if needle and needle not in haystack.lower():
            continue
        sent_at = aware(summary.sent_at)
        if sent_at is None or created is None:
            if best is None:
                best = summary
            continue
        delta = abs(sent_at - created)
        if delta > tolerance:
            continue
        if best_delta is None or delta < best_delta:
            best, best_delta = summary, delta
    return best


def import_attachments(
    record,
    *,
    limit: int = DEFAULT_LIMIT,
    tolerance_minutes: int = DEFAULT_TOLERANCE_MINUTES,
    save: bool = True,
) -> tuple[int, str]:
    """Copy mailbox attachments onto one log row; returns (count, error)."""
    if record.channel != "email":
        return 0, "Only email messages can carry attachments."
    if record.attachments.exists():
        return 0, "Attachments are already stored for this email."

    sources = candidate_sources(record)
    if not sources:
        return (
            0,
            "No connected mailbox could hold a copy of this email — "
            "the sender's mailbox may be disconnected.",
        )

    tolerance = timedelta(minutes=max(1, tolerance_minutes))
    last_error = ""
    matched_empty = False
    for employee, mailbox, folder in sources:
        try:
            client = WorkMailbox(employee, mailbox=mailbox)
            summaries = client.list_messages(folder, limit=limit)
        except WorkMailboxError as exc:
            last_error = f"{employee.get_full_name()}'s {folder} folder: {exc}"
            continue

        summary = best_match(record, summaries, folder, tolerance)
        if summary is None:
            continue
        try:
            detail = client.get_message(folder, summary.uid, mark_seen=False)
        except WorkMailboxError as exc:
            last_error = (
                f"matched in {employee.get_full_name()}'s {folder} folder "
                f"but could not be read — {exc}"
            )
            continue
        if not detail.attachments:
            matched_empty = True
            continue
        if save:
            save_communication_attachments(
                record,
                [
                    (a.filename, a.payload, a.content_type)
                    for a in detail.attachments
                ],
            )
        return len(detail.attachments), ""

    if last_error:
        return 0, f"Could not reach a mailbox copy — {last_error}."
    if matched_empty:
        return 0, "The matching mailbox copy has no attachments."
    return (
        0,
        "No matching email was found in the sender's Sent folder or "
        "the recipient's Inbox.",
    )
