"""Helpers for the Messages work-mailbox email client."""

from __future__ import annotations

import mimetypes
import re

from .models import Document
from .work_mailbox import WorkMailbox, WorkMailboxError
from .workspace import (
    employee_can_access_case_documents,
    employee_can_access_matter_documents,
)


FOLDER_LABELS = {
    "inbox": "Inbox",
    "sent": "Sent",
    "drafts": "Drafts",
    "trash": "Trash",
}


def split_address_list(raw: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;]+", raw or "") if part.strip()]


def _employee_can_attach_document(employee, document) -> bool:
    if document.case_id:
        return employee_can_access_case_documents(employee, document.case)
    if document.matter_id:
        return employee_can_access_matter_documents(employee, document.matter)
    return False


def attachable_documents_for(employee, *, limit: int = 40) -> list[dict]:
    """Firm documents with a local file the employee can attach."""
    queryset = (
        Document.objects.filter(local_file__isnull=False)
        .exclude(local_file="")
        .select_related("case", "matter")
        .order_by("-id")[:200]
    )
    rows = []
    for document in queryset:
        if not _employee_can_attach_document(employee, document):
            continue
        subject = ""
        if document.case_id:
            subject = str(document.case)
        elif document.matter_id:
            subject = str(document.matter)
        rows.append(
            {
                "id": document.pk,
                "title": document.title,
                "filename": document.original_filename or document.title,
                "subject": subject,
            }
        )
        if len(rows) >= limit:
            break
    return rows


def collect_attachments(request, *, employee) -> list[tuple[str, bytes, str]]:
    """Build (filename, bytes, content_type) tuples from uploads and firm docs."""
    attachments: list[tuple[str, bytes, str]] = []
    for upload in request.FILES.getlist("attachments"):
        content_type = (
            getattr(upload, "content_type", None) or "application/octet-stream"
        )
        attachments.append(
            (upload.name, upload.read(), content_type)
        )

    for raw_id in request.POST.getlist("document_ids"):
        if not str(raw_id).isdigit():
            continue
        document = (
            Document.objects.filter(pk=int(raw_id))
            .exclude(local_file="")
            .filter(local_file__isnull=False)
            .select_related("case", "matter")
            .first()
        )
        if (
            document is None
            or not document.local_file
            or not _employee_can_attach_document(employee, document)
        ):
            continue
        filename = document.original_filename or document.title or f"document-{document.pk}"
        content_type = (
            document.mime_type
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )
        with document.local_file.open("rb") as handle:
            attachments.append((filename, handle.read(), content_type))
    return attachments


def mail_client_context(
    employee, request, *, form_errors=None, form_data=None, list_mail=True
) -> dict:
    """IMAP inbox state for the Messages email channel."""
    folder = (request.GET.get("folder") or "inbox").strip().lower()
    if folder not in {"inbox", "sent", "drafts", "trash"}:
        folder = "inbox"
    uid = (request.GET.get("uid") or "").strip()
    compose = (request.GET.get("compose") or "").strip() in {"1", "true", "yes"}
    reply_uid = (request.GET.get("reply") or "").strip()
    reply_all = (request.GET.get("reply_all") or "").strip() in {"1", "true", "yes"}
    forward_uid = (request.GET.get("forward") or "").strip()
    search = (request.GET.get("q") or "").strip()
    # Set by the redirect after send/save/delete: each Passenger worker holds
    # its own cache, so the acting worker's invalidation may not be the one
    # that serves the redirect.
    refresh = (request.GET.get("refresh") or "").strip() in {"1", "true", "yes"}

    posted = form_data or {}
    context = {
        "mail_connected": employee.mailbox_connected,
        "mail_folder": folder,
        "mail_folder_label": FOLDER_LABELS.get(folder, "Inbox"),
        "mail_folders": [
            {"key": key, "label": label, "unread": 0}
            for key, label in FOLDER_LABELS.items()
        ],
        "mail_messages": [],
        "mail_active": None,
        "mail_error": "",
        "mail_search": search,
        "mail_compose_open": compose
        or bool(form_errors)
        or bool(reply_uid)
        or bool(forward_uid)
        or bool(posted.get("subject") or posted.get("body") or posted.get("to")),
        "mail_attachable_documents": attachable_documents_for(employee),
        "mail_compose": {
            "to": posted.get("to", ""),
            "cc": posted.get("cc", ""),
            "bcc": posted.get("bcc", ""),
            "subject": posted.get("subject", ""),
            "body": posted.get("body", ""),
            "in_reply_to": posted.get("in_reply_to", ""),
            "references": posted.get("references", ""),
        },
        "mail_form_errors": form_errors or {},
    }

    if not list_mail:
        return context

    if not (employee.work_email or "").strip():
        context["mail_error"] = "Your account has no work email yet."
        return context

    if not employee.mailbox_connected:
        return context

    try:
        mailbox = WorkMailbox(employee)
        overview = mailbox.folder_overview(folder, search=search, refresh=refresh)
        context["mail_messages"] = overview.get("messages") or []
        unread = overview.get("unread") or {}
        for row in context["mail_folders"]:
            row["unread"] = unread.get(row["key"], 0)
        if uid:
            context["mail_active"] = mailbox.get_message(folder, uid)
            context["mail_compose_open"] = context["mail_compose_open"] or False
        if reply_uid or forward_uid:
            source_uid = reply_uid or forward_uid
            detail = mailbox.get_message(folder, source_uid)
            if forward_uid:
                context["mail_compose"].update(
                    {
                        "to": "",
                        "cc": "",
                        "subject": f"Fwd: {detail.subject}",
                        "body": (
                            f"\n\n---------- Forwarded message ----------\n"
                            f"From: {detail.from_addr}\n"
                            f"Date: {detail.date_display}\n"
                            f"Subject: {detail.subject}\n\n"
                            f"{detail.body_text}"
                        ),
                    }
                )
            else:
                to_value = detail.from_addr
                cc_value = ""
                if reply_all:
                    # Keep other recipients except self.
                    own = (employee.work_email or "").lower()
                    others = []
                    for chunk in split_address_list(
                        f"{detail.to_addrs},{detail.cc_addrs}"
                    ):
                        if own and own in chunk.lower():
                            continue
                        others.append(chunk)
                    cc_value = ", ".join(others)
                context["mail_compose"].update(
                    {
                        "to": to_value,
                        "cc": cc_value,
                        "subject": (
                            detail.subject
                            if detail.subject.lower().startswith("re:")
                            else f"Re: {detail.subject}"
                        ),
                        "body": (
                            f"\n\nOn {detail.date_display}, {detail.from_addr} wrote:\n"
                            + "\n".join(
                                f"> {line}" for line in detail.body_text.splitlines()
                            )
                        ),
                        "in_reply_to": detail.message_id,
                        "references": detail.message_id,
                    }
                )
            context["mail_compose_open"] = True
    except WorkMailboxError as exc:
        context["mail_error"] = str(exc)

    return context
