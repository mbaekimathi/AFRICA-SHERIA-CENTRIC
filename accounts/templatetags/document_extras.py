from django import template

from accounts.document_tracking import format_duration
from accounts.google_drive import (
    GOOGLE_DOC_MIME,
    GOOGLE_SHEET_MIME,
    GOOGLE_SLIDE_MIME,
)

register = template.Library()


@register.filter(name="duration")
def duration_filter(seconds):
    return format_duration(seconds)


@register.filter(name="drive_kind")
def drive_kind_filter(document):
    """Map a Document to a drive-file-3d kind key."""
    mime = (getattr(document, "mime_type", "") or "").strip()
    if mime == GOOGLE_DOC_MIME:
        return "docs"
    if mime == GOOGLE_SHEET_MIME:
        return "sheets"
    if mime == GOOGLE_SLIDE_MIME:
        return "slides"
    if mime == "application/pdf":
        return "pdf"
    if mime.startswith("image/"):
        return "image"
    source = (getattr(document, "source", "") or "").strip()
    if source == "google_doc":
        return "docs"
    return "file"
