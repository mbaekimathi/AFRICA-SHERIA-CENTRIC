"""Helpers for document activity, open-session, and Google content tracking."""

from __future__ import annotations

import hashlib
import logging

from django.utils import timezone

from .google_drive import (
    GoogleDriveAPIError,
    export_google_workspace_text,
    get_drive_file_meta,
    parse_drive_datetime,
)
from .models import (
    Document,
    DocumentActivity,
    DocumentContentSnapshot,
    DocumentOpenSession,
    Employee,
)

logger = logging.getLogger(__name__)

CONTENT_PREVIEW_CHARS = 500
# Near-empty docs: typing into them counts as creating.
EMPTY_CONTENT_CHARS = 40
# Net growth that looks like typing/adding content.
TYPING_GROWTH_CHARS = 15


def format_duration(seconds: int | None) -> str:
    total = max(0, int(seconds or 0))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def log_document_activity(
    document: Document,
    actor: Employee | None,
    action: str,
    *,
    detail: str = "",
    metadata: dict | None = None,
) -> DocumentActivity:
    return DocumentActivity.objects.create(
        document=document,
        actor=actor,
        action=action,
        detail=(detail or "")[:255],
        metadata=metadata or {},
    )


def _content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _sanitize_content_text(text: str) -> str:
    """Normalize exported Drive text for MySQL-safe storage."""
    cleaned = (text or "").replace("\ufeff", "").replace("\x00", "")
    return cleaned


def _preview_text(text: str, limit: int = CONTENT_PREVIEW_CHARS) -> str:
    cleaned = _sanitize_content_text(text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _add_time_to_document(document: Document, kind: str, seconds: int) -> None:
    seconds = max(0, int(seconds or 0))
    if seconds <= 0:
        return
    if kind == DocumentOpenSession.Kind.EDITING:
        document.editing_seconds = (document.editing_seconds or 0) + seconds
        field = "editing_seconds"
    elif kind == DocumentOpenSession.Kind.CREATING:
        document.creating_seconds = (document.creating_seconds or 0) + seconds
        field = "creating_seconds"
    else:
        document.viewing_seconds = (document.viewing_seconds or 0) + seconds
        field = "viewing_seconds"
    document.save(update_fields=[field, "updated_at"])


def classify_content_behavior(
    *,
    baseline_hash: str,
    baseline_chars: int,
    current_hash: str,
    current_chars: int,
) -> str:
    """
    Infer what the user is doing from content deltas.

    - No change → viewing
    - Typing / adding content (or filling an empty doc) → creating
    - Changing existing details without much growth → editing
    """
    baseline_hash = (baseline_hash or "").strip()
    current_hash = (current_hash or "").strip()
    if not current_hash or current_hash == baseline_hash:
        return DocumentOpenSession.Kind.VIEWING

    growth = int(current_chars or 0) - int(baseline_chars or 0)
    if int(baseline_chars or 0) <= EMPTY_CONTENT_CHARS or growth >= TYPING_GROWTH_CHARS:
        return DocumentOpenSession.Kind.CREATING
    return DocumentOpenSession.Kind.EDITING


def sync_google_document_content(
    document: Document,
    actor: Employee | None = None,
    *,
    force: bool = False,
) -> tuple[DocumentContentSnapshot | None, bool, int]:
    """
    Pull Google Drive metadata + exported text content for a document.

    Returns (snapshot, content_changed, char_count).
    """
    file_id = (document.drive_file_id or "").strip()
    if not file_id:
        return None, False, 0

    try:
        meta = get_drive_file_meta(file_id)
    except GoogleDriveAPIError as exc:
        logger.info("Content sync meta failed for document %s: %s", document.pk, exc)
        return None, False, 0

    mime = (meta.get("mimeType") or document.mime_type or "").strip()
    revision_id = (meta.get("headRevisionId") or "").strip()
    version = str(meta.get("version") or "").strip()
    modified_at = parse_drive_datetime(meta.get("modifiedTime"))
    last_user = meta.get("lastModifyingUser") or {}
    modifier_name = (last_user.get("displayName") or "").strip()
    modifier_email = (last_user.get("emailAddress") or "").strip()

    content_text = ""
    try:
        content_text = export_google_workspace_text(file_id, mime)
    except GoogleDriveAPIError as exc:
        logger.info(
            "Content export failed for document %s: %s", document.pk, exc
        )
    content_text = _sanitize_content_text(content_text)

    char_count = len(content_text or "")
    digest = _content_hash(
        content_text
        or f"{revision_id}|{version}|{meta.get('modifiedTime')}|{meta.get('md5Checksum')}"
    )
    unchanged = (
        not force
        and document.content_hash == digest
        and document.drive_head_revision_id == revision_id
    )

    document.mime_type = mime or document.mime_type
    document.drive_modified_at = modified_at
    document.drive_head_revision_id = revision_id
    document.drive_version = version
    document.content_hash = digest
    if content_text:
        document.content_preview = _preview_text(content_text)
    document.content_synced_at = timezone.now()
    document.save(
        update_fields=[
            "mime_type",
            "drive_modified_at",
            "drive_head_revision_id",
            "drive_version",
            "content_hash",
            "content_preview",
            "content_synced_at",
            "updated_at",
        ]
    )

    if unchanged:
        latest = document.content_snapshots.first()
        return latest, False, (latest.char_count if latest else char_count)

    snapshot = DocumentContentSnapshot.objects.create(
        document=document,
        revision_id=revision_id,
        content_hash=digest,
        content_text=content_text,
        char_count=char_count,
        modifier_name=modifier_name,
        modifier_email=modifier_email,
        drive_modified_at=modified_at,
        captured_by=actor,
    )

    prior_count = document.content_snapshots.count()
    content_changed = prior_count > 1 or force
    if content_changed:
        who = modifier_name or modifier_email or (actor.get_full_name() if actor else "")
        detail_bits = []
        if who:
            detail_bits.append(who)
        if snapshot.char_count:
            detail_bits.append(f"{snapshot.char_count} chars")
        if revision_id:
            detail_bits.append(f"rev {revision_id[:10]}")
        log_document_activity(
            document,
            actor,
            DocumentActivity.Action.CONTENT_EDITED,
            detail=" · ".join(detail_bits) or "Content updated in Google",
            metadata={
                "snapshot_id": snapshot.pk,
                "revision_id": revision_id,
                "version": version,
                "modifier_name": modifier_name,
                "modifier_email": modifier_email,
                "char_count": snapshot.char_count,
            },
        )

    return snapshot, content_changed, char_count


def detect_session_behavior(
    session: DocumentOpenSession,
    *,
    sync: bool = True,
) -> str:
    """
    Compare live Google content to the session baseline and update detected kind.
    """
    document = session.document
    char_count = session.baseline_char_count or 0
    if sync:
        _, _, char_count = sync_google_document_content(
            document, actor=session.actor
        )
        document.refresh_from_db(fields=["content_hash"])

    current_hash = document.content_hash or ""
    behavior = classify_content_behavior(
        baseline_hash=session.baseline_content_hash or "",
        baseline_chars=session.baseline_char_count or 0,
        current_hash=current_hash,
        current_chars=char_count,
    )

    update_fields: list[str] = []
    if behavior != DocumentOpenSession.Kind.VIEWING:
        if not session.first_change_at:
            session.first_change_at = timezone.now()
            update_fields.append("first_change_at")
        if not session.content_changed:
            session.content_changed = True
            update_fields.append("content_changed")
        if session.kind != behavior:
            session.kind = behavior
            update_fields.append("kind")
    elif session.kind != DocumentOpenSession.Kind.VIEWING and not session.content_changed:
        session.kind = DocumentOpenSession.Kind.VIEWING
        update_fields.append("kind")

    if update_fields:
        session.save(update_fields=update_fields)
    return session.kind


def start_open_session(
    document: Document,
    actor: Employee | None,
) -> DocumentOpenSession:
    session = DocumentOpenSession.objects.create(
        document=document,
        actor=actor,
        kind=DocumentOpenSession.Kind.VIEWING,
    )
    snapshot, _, char_count = sync_google_document_content(document, actor=actor)
    document.refresh_from_db(fields=["content_hash"])
    session.baseline_content_hash = document.content_hash or ""
    session.baseline_char_count = (
        snapshot.char_count if snapshot else char_count
    )
    session.save(
        update_fields=["baseline_content_hash", "baseline_char_count"]
    )

    log_document_activity(
        document,
        actor,
        DocumentActivity.Action.OPENED,
        detail="Opened — detecting viewing, editing, or creating",
        metadata={"session_id": session.pk},
    )
    return session


def end_open_session(
    session: DocumentOpenSession,
    *,
    reason: str = "closed",
) -> DocumentOpenSession:
    if session.ended_at:
        return session

    detect_session_behavior(session, sync=True)
    if not session.close(reason=reason):
        return session

    total = session.duration_seconds or 0
    if session.first_change_at and session.content_changed:
        viewing_part = max(
            0,
            int((session.first_change_at - session.started_at).total_seconds()),
        )
        viewing_part = min(viewing_part, total)
        active_part = max(0, total - viewing_part)
        active_kind = session.kind or DocumentOpenSession.Kind.EDITING
        if active_kind == DocumentOpenSession.Kind.VIEWING:
            active_kind = DocumentOpenSession.Kind.EDITING
        _add_time_to_document(
            session.document, DocumentOpenSession.Kind.VIEWING, viewing_part
        )
        _add_time_to_document(session.document, active_kind, active_part)
    else:
        session.kind = DocumentOpenSession.Kind.VIEWING
        session.save(update_fields=["kind"])
        _add_time_to_document(
            session.document, DocumentOpenSession.Kind.VIEWING, total
        )

    log_document_activity(
        session.document,
        session.actor,
        DocumentActivity.Action.SESSION_ENDED,
        detail=(
            f"{session.get_kind_display()}: "
            f"{format_duration(session.duration_seconds)}"
        ),
        metadata={
            "session_id": session.pk,
            "duration_seconds": session.duration_seconds,
            "ended_reason": session.ended_reason,
            "kind": session.kind,
            "content_changed": session.content_changed,
            "first_change_at": (
                session.first_change_at.isoformat()
                if session.first_change_at
                else None
            ),
        },
    )
    return session
