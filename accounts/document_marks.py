"""Placing a signatory's own stamp and signature on a document."""

from __future__ import annotations

from django.utils import timezone

from .digital_signature import resolve_signature_setting, signature_render_context
from .digital_stamp import resolve_stamp_setting, stamp_render_context
from .models import (
    DocumentMark,
    EmployeeDigitalSignatureSetting,
    EmployeeDigitalStampSetting,
    FirmCompanyInformation,
)

DRIVE_PREVIEW_URL = "https://drive.google.com/file/d/{file_id}/preview"
GOOGLE_EDITOR_PREVIEW = {
    "application/vnd.google-apps.document": (
        "https://docs.google.com/document/d/{file_id}/preview"
    ),
    "application/vnd.google-apps.spreadsheet": (
        "https://docs.google.com/spreadsheets/d/{file_id}/preview"
    ),
    "application/vnd.google-apps.presentation": (
        "https://docs.google.com/presentation/d/{file_id}/preview"
    ),
}


def _signer_name(signer) -> str:
    if signer is None:
        return ""
    getter = getattr(signer, "get_full_name", None)
    name = (getter() if callable(getter) else "") or ""
    return name.strip() or (getattr(signer, "login_code", "") or "").strip()


def signatory_marks_context(signer, *, date_display: str = "") -> dict:
    """
    Context for the session user's own stamp and signature marks.

    Both fall back to the firm defaults when the signatory has not saved a
    personal stamp or signature under My tools.
    """
    firm = FirmCompanyInformation.get_solo()
    name = _signer_name(signer)
    date_display = date_display or timezone.localdate().strftime("%d %b %Y")

    stamp_setting = resolve_stamp_setting(signer)
    signature_setting = resolve_signature_setting(signer)

    context = stamp_render_context(
        firm=firm,
        setting=stamp_setting,
        status="Signed",
        status_key="signed",
        label="Signed by",
        name=name or firm.display_name,
        date_display=date_display,
    )
    context.update(
        signature_render_context(
            firm=firm,
            setting=signature_setting,
            name=name or firm.display_name,
            signer=signer,
            date_display=date_display,
        )
    )
    context.update(
        {
            "mark_date": date_display,
            "mark_owner_name": name,
            "mark_uses_own_stamp": isinstance(
                stamp_setting, EmployeeDigitalStampSetting
            ),
            "mark_uses_own_signature": isinstance(
                signature_setting, EmployeeDigitalSignatureSetting
            ),
        }
    )
    return context


def document_preview(document) -> dict:
    """How the placement studio should show this document behind the marks."""
    mime = (document.mime_type or "").strip()
    drive_id = (document.drive_file_id or "").strip()

    if drive_id:
        template = GOOGLE_EDITOR_PREVIEW.get(mime, DRIVE_PREVIEW_URL)
        return {"kind": "frame", "url": template.format(file_id=drive_id)}

    local = document.local_file
    if local:
        try:
            url = local.url
        except ValueError:
            url = ""
        if url and mime.startswith("image/"):
            return {"kind": "image", "url": url}
        if url:
            return {"kind": "frame", "url": url}

    return {"kind": "blank", "url": ""}


def attach_document_marks(documents, signer) -> list:
    """Annotate documents with the signatory's saved marks for the template."""
    documents = list(documents)
    if signer is None or not getattr(signer, "pk", None) or not documents:
        for document in documents:
            document.my_marks = []
            document.has_my_signature = False
            document.has_my_stamp = False
            document.preview = document_preview(document)
        return documents

    saved = DocumentMark.objects.filter(
        document__in=documents, employee=signer
    )
    by_document: dict[int, list[DocumentMark]] = {}
    for mark in saved:
        by_document.setdefault(mark.document_id, []).append(mark)

    for document in documents:
        marks = by_document.get(document.pk, [])
        kinds = {mark.kind for mark in marks}
        document.my_marks = [
            {
                **mark.as_payload(),
                "date": timezone.localtime(mark.updated_at).strftime("%d %b %Y"),
            }
            for mark in marks
        ]
        document.has_my_signature = DocumentMark.Kind.SIGNATURE in kinds
        document.has_my_stamp = DocumentMark.Kind.STAMP in kinds
        document.preview = document_preview(document)
    return documents
