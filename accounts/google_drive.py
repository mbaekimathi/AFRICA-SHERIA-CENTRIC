"""Google Drive OAuth and firm folder structure helpers."""

from __future__ import annotations

import json
import logging
import mimetypes
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import (
    Client,
    Employee,
    GoogleDriveConnection,
    LitigationCase,
    NonLitigationMatter,
    client_folder_name,
    employee_folder_name,
)

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER_MIME = "application/vnd.google-apps.folder"
GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
GOOGLE_SLIDE_MIME = "application/vnd.google-apps.presentation"

GOOGLE_WORKSPACE_TYPES = {
    "document": {
        "mime": GOOGLE_DOC_MIME,
        "label": "Google Docs",
        "short": "Docs (Word)",
        "edit_path": "https://docs.google.com/document/d/{id}/edit",
    },
    "spreadsheet": {
        "mime": GOOGLE_SHEET_MIME,
        "label": "Google Sheets",
        "short": "Sheets (Excel)",
        "edit_path": "https://docs.google.com/spreadsheets/d/{id}/edit",
    },
    "presentation": {
        "mime": GOOGLE_SLIDE_MIME,
        "label": "Google Slides",
        "short": "Slides",
        "edit_path": "https://docs.google.com/presentation/d/{id}/edit",
    },
}

CLIENTS_FOLDER_NAME = "Clients"
WORK_FOLDER_NAME = "Employees"
TEMPLATES_FORMS_FOLDER_NAME = "Templates and Forms"
PERSONAL_FOLDER_NAME = "Personal"
PERSONAL_DOCUMENTS_FOLDER_NAME = "Personal Documents"
LITIGATION_FOLDER_NAME = "Litigation"
NON_LITIGATION_FOLDER_NAME = "Non-Litigation"

# Firm template library categories under Templates and Forms/.
TEMPLATES_FORMS_CATEGORIES = (
    ("court-forms", "Court forms"),
    ("affidavits", "Affidavits"),
    ("notices", "Notices"),
    ("agreements", "Agreements"),
    ("letters", "Letters"),
    ("applications", "Applications"),
)
TEMPLATES_FORMS_CATEGORY_SLUGS = {slug for slug, _label in TEMPLATES_FORMS_CATEGORIES}
TEMPLATES_FORMS_CATEGORY_LABELS = dict(TEMPLATES_FORMS_CATEGORIES)

EMPLOYEE_PERSONAL_DETAIL_FIELDS = (
    ("profile_photo", "Profile Photo"),
    ("employment_contract", "Employment Contract"),
    ("national_id_or_passport", "National ID or Passport"),
    ("kra_pin_certificate", "KRA PIN Certificate"),
)

CLIENT_PERSONAL_DOCUMENT_FIELDS = (
    ("profile_photo", "Profile Photo"),
    ("identification_document", "National ID"),
    ("alien_document", "Alien Document"),
    ("business_document", "Business Certificate"),
    ("company_registration_document", "CR12"),
    ("kra_pin_document", "KRA PIN Certificate"),
    ("signed_instruction_note", "Signed Instruction Note"),
)

# Drive files created/opened by this app + identity for the connected account.
GOOGLE_DRIVE_SCOPES = (
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/drive.file",
)

SESSION_OAUTH_STATE = "google_drive_oauth_state"
SESSION_OAUTH_RETURN = "google_drive_oauth_return"
SESSION_OAUTH_REDIRECT = "google_drive_oauth_redirect"

DRIVE_FILE_FIELDS = "id,name,mimeType,webViewLink,webContentLink,trashed"
DRIVE_CONTENT_FIELDS = (
    "id,name,mimeType,modifiedTime,version,md5Checksum,headRevisionId,"
    "lastModifyingUser(displayName,emailAddress)"
)
DRIVE_REVISIONS_URL = "https://www.googleapis.com/drive/v3/files/{file_id}/revisions"
DRIVE_EXPORT_URL = "https://www.googleapis.com/drive/v3/files/{file_id}/export"

EXPORT_MIME_BY_WORKSPACE = {
    GOOGLE_DOC_MIME: "text/plain",
    GOOGLE_SHEET_MIME: "text/csv",
    GOOGLE_SLIDE_MIME: "text/plain",
}

# Office-friendly downloads for Google Workspace files.
DOWNLOAD_EXPORT_BY_WORKSPACE = {
    GOOGLE_DOC_MIME: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    GOOGLE_SHEET_MIME: (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    GOOGLE_SLIDE_MIME: (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
}


class GoogleDriveOAuthError(Exception):
    pass


class GoogleDriveAPIError(Exception):
    pass


def google_oauth_configured() -> bool:
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "") or ""
    client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", "") or ""
    return bool(client_id.strip() and client_secret.strip())


def firm_root_folder_name() -> str:
    return (
        getattr(settings, "FIRM_DRIVE_ROOT_NAME", "") or ""
    ).strip() or "Sheria-Centric"


def is_loopback_host(host: str) -> bool:
    hostname = (host or "").split(":")[0].strip().lower()
    return hostname in {"localhost", "127.0.0.1", "::1"}


def is_private_lan_host(host: str) -> bool:
    """True for RFC1918 / link-local IPs Google OAuth rejects."""
    hostname = (host or "").split(":")[0].strip().lower()
    if not hostname or is_loopback_host(hostname):
        return False
    if hostname.endswith(".local"):
        return True
    parts = hostname.split(".")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        return False
    a, b = int(parts[0]), int(parts[1])
    if a == 10:
        return True
    if a == 172 and 16 <= b <= 31:
        return True
    if a == 192 and b == 168:
        return True
    if a == 169 and b == 254:
        return True
    return False


def can_start_google_oauth(host: str) -> bool:
    """
    Connect works:
    - offline/local: localhost / 127.0.0.1
    - online: public domain (cPanel, etc.)
    Not from private LAN IPs (Google rejects those redirect URIs).
    """
    if is_loopback_host(host):
        return True
    if is_private_lan_host(host):
        return False
    hostname = (host or "").split(":")[0].strip()
    return bool(hostname)


def _origin_from_request(request) -> str:
    origin = (getattr(request, "auto_site_origin", "") or "").strip().rstrip("/")
    if origin:
        return origin
    return request.build_absolute_uri("/").rstrip("/")


def build_redirect_uri(request=None) -> str:
    """
    Auto-pick OAuth callback for local (offline) and public (online) hosts.
    Private LAN IPs fall back to localhost — Google rejects 192.168.x.x.
    """
    path = "/integrations/google/callback/"
    configured = (getattr(settings, "GOOGLE_OAUTH_REDIRECT_URI", "") or "").strip()
    if configured:
        return configured if configured.endswith("/") else configured + "/"

    if request is None:
        return f"http://localhost:8000{path}"

    host = request.get_host()
    if is_private_lan_host(host):
        return f"http://localhost:8000{path}"

    if is_loopback_host(host):
        # Keep whatever loopback host/port the user is on.
        return _origin_from_request(request).rstrip("/") + path

    # Public / production domain (https://yourdomain.com, …).
    return _origin_from_request(request).rstrip("/") + path


def sanitize_drive_name(name: str, *, fallback: str = "Untitled") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", (name or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:100] or fallback


def begin_oauth(request, return_path: str) -> str:
    """Store CSRF state and return the Google consent URL (offline refresh token)."""
    if not google_oauth_configured():
        raise GoogleDriveOAuthError(
            "Google OAuth is not configured. Set GOOGLE_CLIENT_ID and "
            "GOOGLE_CLIENT_SECRET in the environment."
        )

    host = request.get_host()
    if not can_start_google_oauth(host):
        raise GoogleDriveOAuthError(
            "Google OAuth cannot start from a private LAN address. "
            "Open settings on http://localhost:8000/ (local) or your "
            "public domain (online), then connect."
        )

    state = secrets.token_urlsafe(32)
    redirect_uri = build_redirect_uri(request)
    request.session[SESSION_OAUTH_STATE] = state
    request.session[SESSION_OAUTH_RETURN] = return_path or "/"
    request.session[SESSION_OAUTH_REDIRECT] = redirect_uri

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_DRIVE_SCOPES),
        # Offline = refresh token so Drive keeps working after the user leaves.
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    return GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params)


def _post_form(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise GoogleDriveOAuthError(
            f"Google token request failed ({exc.code}). {detail}".strip()
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GoogleDriveOAuthError("Could not reach Google OAuth.") from exc


def _request_json(
    method: str,
    url: str,
    *,
    access_token: str,
    payload: dict | None = None,
    timeout: int = 30,
) -> dict:
    data = None
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise GoogleDriveAPIError(
            f"Google Drive API error ({exc.code}). {detail}".strip()
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GoogleDriveAPIError("Could not reach Google Drive.") from exc


def _get_json(url: str, access_token: str) -> dict:
    return _request_json("GET", url, access_token=access_token)


def _request_bytes(
    method: str,
    url: str,
    *,
    access_token: str,
    timeout: int = 60,
) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "*/*",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read() or b""
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise GoogleDriveAPIError(
            f"Google Drive API error ({exc.code}). {detail}".strip()
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise GoogleDriveAPIError("Could not reach Google Drive.") from exc


def get_drive_file_meta(file_id: str) -> dict:
    """Fetch Drive metadata used for content-change tracking."""
    if not file_id:
        raise GoogleDriveAPIError("Missing Drive file id.")
    token = get_valid_access_token()
    return _request_json(
        "GET",
        f"{DRIVE_FILES_URL}/{urllib.parse.quote(file_id)}"
        f"?fields={DRIVE_CONTENT_FIELDS}&supportsAllDrives=true",
        access_token=token,
    )


DRIVE_BROWSER_FIELDS = (
    "id,name,mimeType,webViewLink,webContentLink,modifiedTime,size,"
    "owners(displayName,emailAddress),lastModifyingUser(displayName)"
)


def list_drive_children(
    folder_id: str,
    *,
    page_size: int = 200,
) -> list[dict]:
    """
    List non-trashed children of a Drive folder (folders first, then name).
    """
    folder_id = (folder_id or "").strip()
    if not folder_id:
        raise GoogleDriveAPIError("Missing Drive folder id.")

    token = get_valid_access_token()
    q = f"'{folder_id}' in parents and trashed = false"
    files: list[dict] = []
    page_token = ""
    while True:
        params: dict[str, str] = {
            "q": q,
            "fields": f"nextPageToken,files({DRIVE_BROWSER_FIELDS})",
            "orderBy": "folder,name",
            "pageSize": str(max(1, min(int(page_size or 200), 1000))),
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        if page_token:
            params["pageToken"] = page_token
        data = _request_json(
            "GET",
            f"{DRIVE_FILES_URL}?{urllib.parse.urlencode(params)}",
            access_token=token,
        )
        files.extend(data.get("files") or [])
        page_token = (data.get("nextPageToken") or "").strip()
        if not page_token:
            break
    return files


def get_drive_folder_meta(folder_id: str) -> dict:
    """Fetch folder metadata including parents for breadcrumb walks."""
    folder_id = (folder_id or "").strip()
    if not folder_id:
        raise GoogleDriveAPIError("Missing Drive folder id.")
    token = get_valid_access_token()
    return _request_json(
        "GET",
        (
            f"{DRIVE_FILES_URL}/{urllib.parse.quote(folder_id)}"
            "?fields=id,name,mimeType,trashed,parents,webViewLink"
            "&supportsAllDrives=true"
        ),
        access_token=token,
    )


def build_drive_folder_breadcrumbs(
    folder_id: str,
    *,
    root_folder_id: str,
    root_name: str = "",
) -> list[dict]:
    """
    Walk parents from folder_id up to root_folder_id (inclusive).

    Returns crumbs ordered root → current. Raises if folder is outside root.
    """
    folder_id = (folder_id or "").strip()
    root_folder_id = (root_folder_id or "").strip()
    if not folder_id or not root_folder_id:
        raise GoogleDriveAPIError("Missing Drive folder id.")

    chain: list[dict] = []
    seen: set[str] = set()
    current = folder_id
    while current and current not in seen:
        seen.add(current)
        meta = get_drive_folder_meta(current)
        if meta.get("trashed") or meta.get("mimeType") != FOLDER_MIME:
            raise GoogleDriveAPIError("That Drive folder is not available.")
        name = (meta.get("name") or "").strip() or "Untitled"
        if current == root_folder_id and root_name:
            name = root_name
        chain.append(
            {
                "id": current,
                "name": name,
                "web_view_link": (meta.get("webViewLink") or "").strip(),
            }
        )
        if current == root_folder_id:
            chain.reverse()
            return chain
        parents = meta.get("parents") or []
        current = (parents[0] if parents else "") or ""

    raise GoogleDriveAPIError(
        "That folder is outside the firm Google Drive structure."
    )


def list_drive_revisions(file_id: str, *, page_size: int = 20) -> list[dict]:
    """Return recent Drive revisions for a file (newest first when available)."""
    if not file_id:
        return []
    token = get_valid_access_token()
    url = (
        DRIVE_REVISIONS_URL.format(file_id=urllib.parse.quote(file_id))
        + "?"
        + urllib.parse.urlencode(
            {
                "fields": (
                    "revisions(id,modifiedTime,keepForever,published,"
                    "lastModifyingUser(displayName,emailAddress))"
                ),
                "pageSize": str(max(1, min(page_size, 100))),
            }
        )
    )
    try:
        payload = _request_json("GET", url, access_token=token)
    except GoogleDriveAPIError as exc:
        logger.info("Could not list revisions for %s: %s", file_id, exc)
        return []
    revisions = payload.get("revisions") or []
    return list(reversed(revisions)) if revisions else []


def export_google_workspace_text(file_id: str, mime_type: str = "") -> str:
    """
    Export Google Docs/Sheets/Slides content as plain text/CSV.
    Returns empty string for unsupported mime types.
    """
    if not file_id:
        return ""
    export_mime = EXPORT_MIME_BY_WORKSPACE.get((mime_type or "").strip())
    if not export_mime:
        return ""
    token = get_valid_access_token()
    url = (
        DRIVE_EXPORT_URL.format(file_id=urllib.parse.quote(file_id))
        + "?"
        + urllib.parse.urlencode({"mimeType": export_mime})
    )
    raw = _request_bytes("GET", url, access_token=token, timeout=90)
    text = raw.decode("utf-8-sig", errors="replace")
    # Drop leftover BOM / nulls that some exports embed and MySQL rejects on latin1.
    text = text.replace("\ufeff", "").replace("\x00", "")
    # Keep snapshots bounded for DB/UI.
    max_chars = 120_000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[Content truncated]"
    return text


def download_drive_file(
    file_id: str,
    *,
    mime_type: str = "",
    title: str = "",
    original_filename: str = "",
) -> tuple[bytes, str, str]:
    """
    Download a Drive file for browser download.

    Google Workspace files are exported to Office formats; other files use
    binary media download. Returns (content, filename, content_type).
    """
    if not file_id:
        raise GoogleDriveAPIError("Missing Drive file id.")

    token = get_valid_access_token()
    mime = (mime_type or "").strip()
    base_name = sanitize_drive_name(title or original_filename or "document")
    # Strip a trailing extension from the title so we can append the right one.
    stem = re.sub(r"\.[A-Za-z0-9]{1,8}$", "", base_name).strip() or "document"

    export = DOWNLOAD_EXPORT_BY_WORKSPACE.get(mime)
    if export:
        export_mime, extension = export
        url = (
            DRIVE_EXPORT_URL.format(file_id=urllib.parse.quote(file_id))
            + "?"
            + urllib.parse.urlencode({"mimeType": export_mime})
        )
        content = _request_bytes("GET", url, access_token=token, timeout=120)
        return content, f"{stem}{extension}", export_mime

    url = (
        f"{DRIVE_FILES_URL}/{urllib.parse.quote(file_id)}"
        f"?{urllib.parse.urlencode({'alt': 'media'})}"
    )
    content = _request_bytes("GET", url, access_token=token, timeout=120)
    filename = (original_filename or "").strip() or base_name
    if "." not in filename and mime:
        guessed = mimetypes.guess_extension(mime) or ""
        if guessed:
            filename = f"{stem}{guessed}"
    content_type = mime or _guess_mime(filename)
    return content, filename, content_type


def preview_drive_file(
    file_id: str,
    *,
    mime_type: str = "",
    title: str = "",
    original_filename: str = "",
) -> tuple[bytes, str, str]:
    """
    Fetch a Drive file for in-browser viewing (prefer PDF for Workspace docs).

    Returns (content, filename, content_type).
    """
    if not file_id:
        raise GoogleDriveAPIError("Missing Drive file id.")

    mime = (mime_type or "").strip()
    base_name = sanitize_drive_name(title or original_filename or "document")
    stem = re.sub(r"\.[A-Za-z0-9]{1,8}$", "", base_name).strip() or "document"
    token = get_valid_access_token()

    # Prefer PDF for Docs/Slides so the portal can embed a read-only preview.
    if mime == GOOGLE_DOC_MIME:
        url = (
            DRIVE_EXPORT_URL.format(file_id=urllib.parse.quote(file_id))
            + "?"
            + urllib.parse.urlencode({"mimeType": "application/pdf"})
        )
        content = _request_bytes("GET", url, access_token=token, timeout=120)
        return content, f"{stem}.pdf", "application/pdf"
    if mime == GOOGLE_SLIDE_MIME:
        url = (
            DRIVE_EXPORT_URL.format(file_id=urllib.parse.quote(file_id))
            + "?"
            + urllib.parse.urlencode({"mimeType": "application/pdf"})
        )
        content = _request_bytes("GET", url, access_token=token, timeout=120)
        return content, f"{stem}.pdf", "application/pdf"
    if mime == GOOGLE_SHEET_MIME:
        # Sheets preview as CSV text in the viewer.
        url = (
            DRIVE_EXPORT_URL.format(file_id=urllib.parse.quote(file_id))
            + "?"
            + urllib.parse.urlencode({"mimeType": "text/csv"})
        )
        content = _request_bytes("GET", url, access_token=token, timeout=120)
        return content, f"{stem}.csv", "text/csv; charset=utf-8"

    return download_drive_file(
        file_id,
        mime_type=mime,
        title=title,
        original_filename=original_filename,
    )

def parse_drive_datetime(value: str | None):
    """Parse Drive RFC3339 timestamps into aware datetimes."""
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = parse_datetime(raw)
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, dt_timezone.utc)
    return parsed


def _invalidate_dead_google_drive_auth() -> None:
    """
    Mark Drive disconnected after permanent OAuth failure.

    Short-lived access tokens renew via refresh_token and must not disconnect
    the firm. Only call this when refresh is impossible (missing / rejected).
    Keeps firm folder IDs so reconnect can reuse the existing Drive tree.
    """
    connection = GoogleDriveConnection.get_solo()
    if not connection.is_connected:
        return
    logger.warning(
        "Google Drive auth invalidated; clearing local tokens "
        "(account=%s).",
        connection.account_email or "unknown",
    )
    connection.clear_tokens(keep_folder_ids=True)
    try:
        from .notifications import notify_google_drive_auth_expired

        notify_google_drive_auth_expired()
    except Exception:
        logger.exception("Failed to notify employees after Drive auth expiry.")


def get_valid_access_token(connection: GoogleDriveConnection | None = None) -> str:
    """
    Return a usable access token, refreshing when the short-lived token expires.

    The firm connection itself does not expire while a valid refresh_token
    exists. Permanent refresh failures disconnect Drive automatically so the
    UI never stays stuck on a dead “Connected” state.
    """
    connection = connection or GoogleDriveConnection.get_solo()
    if not connection.is_connected:
        raise GoogleDriveAPIError("Google Drive is not connected.")

    token = (connection.access_token or "").strip()
    expiry = connection.token_expiry
    needs_refresh = not token or (
        expiry is not None and expiry <= timezone.now() + timedelta(seconds=60)
    )
    if not needs_refresh:
        return token

    refresh = (connection.refresh_token or "").strip()
    if not refresh:
        _invalidate_dead_google_drive_auth()
        raise GoogleDriveAPIError(
            "Google Drive was disconnected because authorization expired. "
            "Connect again in Google Drive Settings."
        )

    try:
        payload = _post_form(
            GOOGLE_TOKEN_URL,
            {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            },
        )
    except GoogleDriveOAuthError as exc:
        detail = str(exc).lower()
        if "unauthorized_client" in detail or "invalid_grant" in detail:
            _invalidate_dead_google_drive_auth()
            raise GoogleDriveAPIError(
                "Google Drive was disconnected because authorization expired "
                "or no longer matches this app's OAuth credentials. "
                "Connect again in Google Drive Settings."
            ) from exc
        raise GoogleDriveAPIError(
            "Could not refresh Google Drive access right now. Try again shortly."
        ) from exc
    access_token = (payload.get("access_token") or "").strip()
    if not access_token:
        raise GoogleDriveAPIError("Could not refresh Google Drive access.")

    expires_in = int(payload.get("expires_in") or 0)
    connection.access_token = access_token
    connection.token_expiry = (
        timezone.now() + timedelta(seconds=max(expires_in - 60, 0))
        if expires_in
        else None
    )
    connection.save(update_fields=["access_token", "token_expiry", "updated_at"])
    return access_token


def folder_exists(access_token: str, folder_id: str) -> bool:
    if not folder_id:
        return False
    url = (
        f"{DRIVE_FILES_URL}/{urllib.parse.quote(folder_id)}"
        "?fields=id,mimeType,trashed"
    )
    try:
        meta = _request_json("GET", url, access_token=access_token)
    except GoogleDriveAPIError:
        return False
    return (
        meta.get("mimeType") == FOLDER_MIME
        and not meta.get("trashed")
        and bool(meta.get("id"))
    )


def create_folder(
    access_token: str, name: str, *, parent_id: str | None = None
) -> str:
    payload: dict = {
        "name": sanitize_drive_name(name),
        "mimeType": FOLDER_MIME,
    }
    if parent_id:
        payload["parents"] = [parent_id]
    created = _request_json(
        "POST",
        f"{DRIVE_FILES_URL}?fields=id,name,webViewLink",
        access_token=access_token,
        payload=payload,
    )
    folder_id = (created.get("id") or "").strip()
    if not folder_id:
        raise GoogleDriveAPIError(f"Failed to create Drive folder “{name}”.")
    return folder_id


def _ensure_folder_name(access_token: str, folder_id: str, name: str) -> None:
    """Rename an existing Drive folder when its title no longer matches."""
    safe_name = sanitize_drive_name(name)
    if not folder_id or not safe_name:
        return
    url = (
        f"{DRIVE_FILES_URL}/{urllib.parse.quote(folder_id)}"
        "?fields=id,name"
    )
    try:
        meta = _request_json("GET", url, access_token=access_token)
    except GoogleDriveAPIError:
        return
    current = (meta.get("name") or "").strip()
    if current == safe_name:
        return
    try:
        _request_json(
            "PATCH",
            url,
            access_token=access_token,
            payload={"name": safe_name},
        )
    except GoogleDriveAPIError as exc:
        logger.warning(
            "Could not rename Drive folder %s to %s: %s",
            folder_id,
            safe_name,
            exc,
        )


def ensure_folder(
    access_token: str,
    *,
    name: str,
    parent_id: str | None = None,
    existing_id: str = "",
) -> str:
    if existing_id and folder_exists(access_token, existing_id):
        _ensure_folder_name(access_token, existing_id, name)
        return existing_id
    if parent_id:
        found = find_child_folder_by_name(access_token, parent_id, name)
        if found:
            return found
    return create_folder(access_token, name, parent_id=parent_id)


def _escape_drive_query_value(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace("'", "\\'")


def find_child_folder_by_name(
    access_token: str, parent_id: str, name: str
) -> str:
    """Return the first non-trashed child folder with this exact name, if any."""
    parent_id = (parent_id or "").strip()
    safe_name = sanitize_drive_name(name)
    if not parent_id or not safe_name:
        return ""
    q = (
        f"'{parent_id}' in parents and trashed = false "
        f"and mimeType = '{FOLDER_MIME}' "
        f"and name = '{_escape_drive_query_value(safe_name)}'"
    )
    params = {
        "q": q,
        "fields": "files(id,name)",
        "pageSize": "1",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }
    data = _request_json(
        "GET",
        f"{DRIVE_FILES_URL}?{urllib.parse.urlencode(params)}",
        access_token=access_token,
    )
    files = data.get("files") or []
    if not files:
        return ""
    return (files[0].get("id") or "").strip()


def ensure_firm_folder_structure(
    connection: GoogleDriveConnection | None = None,
) -> GoogleDriveConnection:
    """
    Ensure Company / Clients / Employees / Templates and Forms folders exist.
    """
    connection = connection or GoogleDriveConnection.get_solo()
    if not connection.is_connected:
        raise GoogleDriveAPIError("Google Drive is not connected.")

    token = get_valid_access_token(connection)
    root_id = ensure_folder(
        token,
        name=firm_root_folder_name(),
        existing_id=connection.root_folder_id,
    )
    clients_id = ensure_folder(
        token,
        name=CLIENTS_FOLDER_NAME,
        parent_id=root_id,
        existing_id=connection.clients_folder_id,
    )
    work_id = ensure_folder(
        token,
        name=WORK_FOLDER_NAME,
        parent_id=root_id,
        existing_id=connection.work_folder_id,
    )
    templates_forms_id = ensure_folder(
        token,
        name=TEMPLATES_FORMS_FOLDER_NAME,
        parent_id=root_id,
        existing_id=connection.templates_forms_folder_id,
    )

    connection.root_folder_id = root_id
    connection.clients_folder_id = clients_id
    connection.work_folder_id = work_id
    connection.templates_forms_folder_id = templates_forms_id
    connection.save(
        update_fields=[
            "root_folder_id",
            "clients_folder_id",
            "work_folder_id",
            "templates_forms_folder_id",
            "updated_at",
        ]
    )
    return ensure_templates_forms_categories(connection)


def ensure_templates_forms_folder(
    connection: GoogleDriveConnection | None = None,
) -> GoogleDriveConnection:
    """Ensure Templates and Forms plus its category subfolders exist."""
    return ensure_firm_folder_structure(connection)


def ensure_templates_forms_categories(
    connection: GoogleDriveConnection | None = None,
) -> GoogleDriveConnection:
    """
    Ensure category folders under Templates and Forms and cache their Drive ids.
    """
    connection = connection or GoogleDriveConnection.get_solo()
    if not connection.is_connected:
        raise GoogleDriveAPIError("Google Drive is not connected.")
    parent_id = (connection.templates_forms_folder_id or "").strip()
    if not parent_id:
        connection = ensure_firm_folder_structure(connection)
        parent_id = (connection.templates_forms_folder_id or "").strip()
    if not parent_id:
        raise GoogleDriveAPIError("Templates and Forms folder is not available.")

    token = get_valid_access_token(connection)
    stored = dict(connection.templates_forms_category_folder_ids or {})
    updated = False
    for slug, label in TEMPLATES_FORMS_CATEGORIES:
        existing = (stored.get(slug) or "").strip()
        folder_id = ensure_folder(
            token,
            name=label,
            parent_id=parent_id,
            existing_id=existing,
        )
        if stored.get(slug) != folder_id:
            stored[slug] = folder_id
            updated = True
    # Drop stale keys that are no longer categories.
    stale = [key for key in stored if key not in TEMPLATES_FORMS_CATEGORY_SLUGS]
    for key in stale:
        stored.pop(key, None)
        updated = True
    if updated or connection.templates_forms_category_folder_ids != stored:
        connection.templates_forms_category_folder_ids = stored
        connection.save(
            update_fields=["templates_forms_category_folder_ids", "updated_at"]
        )
    return connection


def templates_forms_category_folder_id(
    category_slug: str,
    *,
    connection: GoogleDriveConnection | None = None,
) -> str:
    """Return the Drive folder id for a template category, creating it if needed."""
    slug = (category_slug or "").strip()
    if slug not in TEMPLATES_FORMS_CATEGORY_SLUGS:
        raise GoogleDriveAPIError("Unknown template category.")
    connection = ensure_templates_forms_categories(connection)
    folder_id = (
        (connection.templates_forms_category_folder_ids or {}).get(slug) or ""
    ).strip()
    if not folder_id:
        raise GoogleDriveAPIError(
            f"Could not prepare the {TEMPLATES_FORMS_CATEGORY_LABELS[slug]} folder."
        )
    return folder_id


def list_templates_forms_library(
    connection: GoogleDriveConnection | None = None,
) -> list[dict]:
    """
    List each Templates and Forms category with its non-folder Drive files.
    """
    connection = ensure_templates_forms_categories(connection)
    library: list[dict] = []
    for slug, label in TEMPLATES_FORMS_CATEGORIES:
        folder_id = (
            (connection.templates_forms_category_folder_ids or {}).get(slug) or ""
        ).strip()
        files: list[dict] = []
        folder_url = (
            f"https://drive.google.com/drive/folders/{folder_id}" if folder_id else ""
        )
        if folder_id:
            try:
                children = list_drive_children(folder_id)
            except GoogleDriveAPIError:
                children = []
            for raw in children:
                mime = (raw.get("mimeType") or "").strip()
                file_id = (raw.get("id") or "").strip()
                if not file_id or mime == FOLDER_MIME:
                    continue
                open_url = google_edit_url(file_id, mime) or (
                    raw.get("webViewLink") or ""
                ).strip() or (
                    f"https://drive.google.com/file/d/{file_id}/view"
                )
                files.append(
                    {
                        "id": file_id,
                        "name": (raw.get("name") or "Untitled").strip() or "Untitled",
                        "mime_type": mime,
                        "modified_at": raw.get("modifiedTime") or "",
                        "open_url": open_url,
                        "category": slug,
                        "category_label": label,
                    }
                )
        library.append(
            {
                "slug": slug,
                "label": label,
                "folder_id": folder_id,
                "folder_url": folder_url,
                "files": files,
                "count": len(files),
            }
        )
    return library


def get_drive_file_meta(file_id: str) -> dict:
    """Fetch basic Drive file metadata."""
    file_id = (file_id or "").strip()
    if not file_id:
        raise GoogleDriveAPIError("Missing Drive file id.")
    token = get_valid_access_token()
    return _request_json(
        "GET",
        (
            f"{DRIVE_FILES_URL}/{urllib.parse.quote(file_id)}"
            f"?fields={DRIVE_FILE_FIELDS},parents,trashed"
            "&supportsAllDrives=true"
        ),
        access_token=token,
    )


def copy_drive_file(
    file_id: str,
    *,
    name: str,
    parent_id: str | None = None,
) -> dict:
    """Copy a Drive file into a destination folder (used for Start from template)."""
    file_id = (file_id or "").strip()
    if not file_id:
        raise GoogleDriveAPIError("Missing template file id.")
    token = get_valid_access_token()
    payload: dict = {"name": sanitize_drive_name(name)}
    if parent_id:
        payload["parents"] = [parent_id]
    created = _request_json(
        "POST",
        (
            f"{DRIVE_FILES_URL}/{urllib.parse.quote(file_id)}/copy"
            f"?fields={DRIVE_FILE_FIELDS}"
            "&supportsAllDrives=true"
        ),
        access_token=token,
        payload=payload,
    )
    new_id = (created.get("id") or "").strip()
    if not new_id:
        raise GoogleDriveAPIError(f"Failed to copy “{name}” from the template.")
    return created


def ensure_employee_folder_structure(employee: Employee) -> Employee:
    """
    Ensure Employees/{Employee Name}/Personal.
    """
    connection = GoogleDriveConnection.get_solo()
    if not connection.is_connected or not connection.work_folder_id:
        return employee

    token = get_valid_access_token(connection)
    if not folder_exists(token, connection.work_folder_id):
        connection = ensure_firm_folder_structure(connection)
        token = get_valid_access_token(connection)

    parent_id = connection.work_folder_id
    if not parent_id:
        return employee

    person_name = sanitize_drive_name(
        employee_folder_name(employee),
        fallback=f"Employee {employee.pk}",
    )
    employee_folder_id = ensure_folder(
        token,
        name=person_name,
        parent_id=parent_id,
        existing_id=employee.drive_folder_id,
    )
    personal_folder_id = ensure_folder(
        token,
        name=PERSONAL_FOLDER_NAME,
        parent_id=employee_folder_id,
        existing_id=employee.drive_personal_details_folder_id,
    )

    employee.drive_folder_id = employee_folder_id
    employee.drive_personal_details_folder_id = personal_folder_id
    employee.save(
        update_fields=[
            "drive_folder_id",
            "drive_personal_details_folder_id",
        ]
    )
    return employee


def _read_employee_field_bytes(field_file) -> tuple[bytes, str]:
    """Read local FileField/ImageField content and a usable filename."""
    name = (getattr(field_file, "name", "") or "upload").replace("\\", "/").split("/")[-1]
    field_file.open("rb")
    try:
        content = field_file.read()
    finally:
        field_file.close()
    return content, name


def sync_employee_personal_detail_uploads(
    employee: Employee,
    *,
    field_names: tuple[str, ...] | list[str] | None = None,
) -> dict:
    """
    Upload selected employee personal-detail files into
    Employees/{Name}/Personal on Google Drive.

    Skips quietly when Drive is not connected. Returns a small summary.
    """
    summary = {"uploaded": 0, "skipped": 0, "errors": 0}
    connection = GoogleDriveConnection.get_solo()
    if not connection.is_connected:
        return summary

    try:
        employee = ensure_employee_folder_structure(employee)
    except (GoogleDriveAPIError, GoogleDriveOAuthError) as exc:
        logger.warning(
            "Drive employee folder skipped for %s: %s", employee.pk, exc
        )
        summary["errors"] += 1
        return summary

    parent_id = (employee.drive_personal_details_folder_id or "").strip()
    if not parent_id:
        summary["errors"] += 1
        return summary

    wanted = set(field_names) if field_names is not None else None
    for field_name, label in EMPLOYEE_PERSONAL_DETAIL_FIELDS:
        if wanted is not None and field_name not in wanted:
            continue
        field_file = getattr(employee, field_name, None)
        if not field_file:
            summary["skipped"] += 1
            continue
        try:
            content, original_name = _read_employee_field_bytes(field_file)
            if not content:
                summary["skipped"] += 1
                continue
            ext = ""
            if "." in original_name:
                ext = original_name.rsplit(".", 1)[-1].strip().lower()
            drive_name = f"{label}.{ext}" if ext else label
            upload_drive_file(
                name=drive_name,
                content=content,
                mime_type=getattr(field_file, "content_type", "") or "",
                parent_id=parent_id,
                original_filename=original_name,
            )
            summary["uploaded"] += 1
        except (GoogleDriveAPIError, GoogleDriveOAuthError, OSError, ValueError) as exc:
            summary["errors"] += 1
            logger.warning(
                "Drive upload failed for employee %s field %s: %s",
                employee.pk,
                field_name,
                exc,
            )
    return summary


def ensure_client_folder_structure(client: Client) -> Client:
    """
    Ensure Clients/{Client}/Personal Documents, Litigation, and Non-Litigation.
    """
    connection = GoogleDriveConnection.get_solo()
    if not connection.is_connected or not connection.clients_folder_id:
        return client

    token = get_valid_access_token(connection)
    if not folder_exists(token, connection.clients_folder_id):
        connection = ensure_firm_folder_structure(connection)
        token = get_valid_access_token(connection)

    client_name = sanitize_drive_name(
        client_folder_name(client) or client.get_full_name(),
        fallback=f"Client {client.pk}",
    )
    client_folder_id = ensure_folder(
        token,
        name=client_name,
        parent_id=connection.clients_folder_id,
        existing_id=client.drive_folder_id,
    )
    personal_documents_id = ensure_folder(
        token,
        name=PERSONAL_DOCUMENTS_FOLDER_NAME,
        parent_id=client_folder_id,
        existing_id=client.drive_personal_documents_folder_id,
    )
    litigation_id = ensure_folder(
        token,
        name=LITIGATION_FOLDER_NAME,
        parent_id=client_folder_id,
        existing_id=client.drive_litigation_folder_id,
    )
    non_litigation_id = ensure_folder(
        token,
        name=NON_LITIGATION_FOLDER_NAME,
        parent_id=client_folder_id,
        existing_id=client.drive_non_litigation_folder_id,
    )

    client.drive_folder_id = client_folder_id
    client.drive_personal_documents_folder_id = personal_documents_id
    client.drive_litigation_folder_id = litigation_id
    client.drive_non_litigation_folder_id = non_litigation_id
    client.save(
        update_fields=[
            "drive_folder_id",
            "drive_personal_documents_folder_id",
            "drive_litigation_folder_id",
            "drive_non_litigation_folder_id",
        ]
    )
    return client


def sync_client_personal_document_uploads(
    client: Client,
    *,
    field_names: tuple[str, ...] | list[str] | None = None,
) -> dict:
    """
    Upload selected client personal documents into
    Clients/{Name}/Personal Documents on Google Drive.

    Skips quietly when Drive is not connected.
    """
    summary = {"uploaded": 0, "skipped": 0, "errors": 0}
    connection = GoogleDriveConnection.get_solo()
    if not connection.is_connected:
        return summary

    try:
        client = ensure_client_folder_structure(client)
    except (GoogleDriveAPIError, GoogleDriveOAuthError) as exc:
        logger.warning(
            "Drive client folder skipped for %s: %s", client.pk, exc
        )
        summary["errors"] += 1
        return summary

    parent_id = (client.drive_personal_documents_folder_id or "").strip()
    if not parent_id:
        summary["errors"] += 1
        return summary

    wanted = set(field_names) if field_names is not None else None
    for field_name, label in CLIENT_PERSONAL_DOCUMENT_FIELDS:
        if wanted is not None and field_name not in wanted:
            continue
        field_file = getattr(client, field_name, None)
        if not field_file:
            summary["skipped"] += 1
            continue
        try:
            content, original_name = _read_employee_field_bytes(field_file)
            if not content:
                summary["skipped"] += 1
                continue
            ext = ""
            if "." in original_name:
                ext = original_name.rsplit(".", 1)[-1].strip().lower()
            drive_name = f"{label}.{ext}" if ext else label
            upload_drive_file(
                name=drive_name,
                content=content,
                mime_type=getattr(field_file, "content_type", "") or "",
                parent_id=parent_id,
                original_filename=original_name,
            )
            summary["uploaded"] += 1
        except (GoogleDriveAPIError, GoogleDriveOAuthError, OSError, ValueError) as exc:
            summary["errors"] += 1
            logger.warning(
                "Drive upload failed for client %s field %s: %s",
                client.pk,
                field_name,
                exc,
            )
    return summary


def ensure_case_drive_folder(case: LitigationCase) -> str:
    """Ensure a Drive folder for the case under the client's Litigation folder."""
    client = ensure_client_folder_structure(case.client)
    if not client.drive_litigation_folder_id:
        raise GoogleDriveAPIError(
            "Client Litigation folder is not ready. Reconnect Google Drive."
        )
    token = get_valid_access_token()
    folder_name = sanitize_drive_name(
        case.court_case_number or f"Case {case.pk}",
        fallback=f"Case {case.pk}",
    )
    folder_id = ensure_folder(
        token,
        name=folder_name,
        parent_id=client.drive_litigation_folder_id,
        existing_id=case.drive_folder_id,
    )
    if case.drive_folder_id != folder_id:
        case.drive_folder_id = folder_id
        case.save(update_fields=["drive_folder_id", "updated_at"])
    return folder_id


def ensure_matter_drive_folder(matter: NonLitigationMatter) -> str:
    """Ensure a Drive folder for the matter under Non-Litigation."""
    client = ensure_client_folder_structure(matter.client)
    if not client.drive_non_litigation_folder_id:
        raise GoogleDriveAPIError(
            "Client Non-Litigation folder is not ready. Reconnect Google Drive."
        )
    token = get_valid_access_token()
    folder_name = sanitize_drive_name(
        f"{matter.reference_code} — {matter.matter_title}",
        fallback=matter.reference_code,
    )
    folder_id = ensure_folder(
        token,
        name=folder_name,
        parent_id=client.drive_non_litigation_folder_id,
        existing_id=matter.drive_folder_id,
    )
    if matter.drive_folder_id != folder_id:
        matter.drive_folder_id = folder_id
        matter.save(update_fields=["drive_folder_id", "updated_at"])
    return folder_id


def resolve_google_workspace_type(type_key: str) -> dict:
    key = (type_key or "").strip().lower()
    info = GOOGLE_WORKSPACE_TYPES.get(key)
    if not info:
        raise GoogleDriveAPIError("Choose Docs, Sheets, or Slides.")
    return {"key": key, **info}


def google_edit_url(file_id: str, mime_type: str = "") -> str:
    """Return the Google editor URL for a Workspace file."""
    if not file_id:
        return ""
    mime = (mime_type or "").strip()
    for info in GOOGLE_WORKSPACE_TYPES.values():
        if info["mime"] == mime:
            return info["edit_path"].format(id=file_id)
    if mime == GOOGLE_DOC_MIME or not mime:
        return f"https://docs.google.com/document/d/{file_id}/edit"
    if mime == GOOGLE_SHEET_MIME:
        return f"https://docs.google.com/spreadsheets/d/{file_id}/edit"
    if mime == GOOGLE_SLIDE_MIME:
        return f"https://docs.google.com/presentation/d/{file_id}/edit"
    return f"https://drive.google.com/file/d/{file_id}/view"


def create_google_workspace_file(
    name: str,
    *,
    type_key: str = "document",
    parent_id: str | None = None,
) -> dict:
    """Create an empty Google Docs / Sheets / Slides file."""
    info = resolve_google_workspace_type(type_key)
    token = get_valid_access_token()
    payload: dict = {
        "name": sanitize_drive_name(name),
        "mimeType": info["mime"],
    }
    if parent_id:
        payload["parents"] = [parent_id]
    created = _request_json(
        "POST",
        f"{DRIVE_FILES_URL}?fields={DRIVE_FILE_FIELDS}",
        access_token=token,
        payload=payload,
    )
    file_id = (created.get("id") or "").strip()
    if not file_id:
        raise GoogleDriveAPIError(
            f"Failed to create {info['label']} “{name}”."
        )
    if not created.get("webViewLink"):
        created["webViewLink"] = info["edit_path"].format(id=file_id)
    if not created.get("mimeType"):
        created["mimeType"] = info["mime"]
    created["_workspace_type"] = info["key"]
    created["_workspace_label"] = info["label"]
    return created


def create_google_doc(
    name: str, *, parent_id: str | None = None
) -> dict:
    """Create an empty Google Doc and return Drive file metadata."""
    return create_google_workspace_file(
        name, type_key="document", parent_id=parent_id
    )


DOCS_API_URL = "https://docs.googleapis.com/v1/documents"


def _hex_to_rgb_color(hex_color: str) -> dict:
    raw = (hex_color or "").lstrip("#").strip()
    if len(raw) != 6:
        raw = "1f4d3a"
    return {
        "red": int(raw[0:2], 16) / 255.0,
        "green": int(raw[2:4], 16) / 255.0,
        "blue": int(raw[4:6], 16) / 255.0,
    }


def apply_company_letterhead_to_google_doc(document_id: str) -> None:
    """
    Seed a newly created Google Doc with the firm letterhead header
    (and address footer when enabled in letterhead settings).
    """
    from .letterhead import (
        accent_hex,
        firm_address_compact,
        firm_contact_lines,
        get_letterhead_setting,
    )
    from .models import FirmCompanyInformation

    document_id = (document_id or "").strip()
    if not document_id:
        return

    firm = FirmCompanyInformation.get_solo()
    setting = get_letterhead_setting()
    accent = _hex_to_rgb_color(accent_hex(setting.accent))
    name = (firm.display_name or "").strip() or "Firm"

    header_lines = [name]
    if setting.show_tagline:
        tagline = (firm.tagline or "").strip()
        if tagline:
            header_lines.append(tagline)
    if setting.show_contacts:
        header_lines.extend(firm_contact_lines(firm))

    footer_parts: list[str] = []
    if setting.show_address:
        address = firm_address_compact(firm)
        if address:
            footer_parts.append(address)
        website = (firm.website or "").strip()
        if website:
            footer_parts.append(website)
    footer_text = " · ".join(footer_parts)

    token = get_valid_access_token()
    create_requests: list[dict] = [{"createHeader": {"type": "DEFAULT"}}]
    if footer_text:
        create_requests.append({"createFooter": {"type": "DEFAULT"}})

    created = _request_json(
        "POST",
        f"{DOCS_API_URL}/{urllib.parse.quote(document_id)}:batchUpdate",
        access_token=token,
        payload={"requests": create_requests},
    )
    header_id = ""
    footer_id = ""
    for reply in created.get("replies") or []:
        header_id = header_id or (reply.get("createHeader") or {}).get(
            "headerId", ""
        )
        footer_id = footer_id or (reply.get("createFooter") or {}).get(
            "footerId", ""
        )
    if not header_id:
        raise GoogleDriveAPIError(
            "Could not create the letterhead header on this Google Doc."
        )

    # Empty headers/footers only contain a trailing newline (endIndex=1), so
    # insert before that newline via endOfSegmentLocation (index 1 is invalid).
    header_text = "\n".join(header_lines)
    name_end = len(name)
    header_end = len(header_text)
    muted = {"red": 0.35, "green": 0.4, "blue": 0.45}

    content_requests: list[dict] = [
        {
            "insertText": {
                "endOfSegmentLocation": {"segmentId": header_id},
                "text": header_text,
            }
        },
        {
            "updateTextStyle": {
                "range": {
                    "segmentId": header_id,
                    "startIndex": 0,
                    "endIndex": name_end,
                },
                "textStyle": {
                    "bold": True,
                    "fontSize": {"magnitude": 14, "unit": "PT"},
                    "foregroundColor": {"color": {"rgbColor": accent}},
                },
                "fields": "bold,fontSize,foregroundColor",
            }
        },
        {
            "updateParagraphStyle": {
                "range": {
                    "segmentId": header_id,
                    "startIndex": 0,
                    "endIndex": min(name_end + 1, header_end + 1),
                },
                "paragraphStyle": {
                    "borderBottom": {
                        "color": {"color": {"rgbColor": accent}},
                        "width": {"magnitude": 1.5, "unit": "PT"},
                        "padding": {"magnitude": 3, "unit": "PT"},
                        "dashStyle": "SOLID",
                    }
                },
                "fields": "borderBottom",
            }
        },
    ]
    if header_end > name_end + 1:
        content_requests.append(
            {
                "updateTextStyle": {
                    "range": {
                        "segmentId": header_id,
                        "startIndex": name_end + 1,
                        "endIndex": header_end,
                    },
                    "textStyle": {
                        "fontSize": {"magnitude": 9, "unit": "PT"},
                        "foregroundColor": {"color": {"rgbColor": muted}},
                    },
                    "fields": "fontSize,foregroundColor",
                }
            }
        )

    if footer_id and footer_text:
        content_requests.extend(
            [
                {
                    "insertText": {
                        "endOfSegmentLocation": {"segmentId": footer_id},
                        "text": footer_text,
                    }
                },
                {
                    "updateTextStyle": {
                        "range": {
                            "segmentId": footer_id,
                            "startIndex": 0,
                            "endIndex": len(footer_text),
                        },
                        "textStyle": {
                            "fontSize": {"magnitude": 8, "unit": "PT"},
                            "foregroundColor": {
                                "color": {"rgbColor": muted}
                            },
                        },
                        "fields": "fontSize,foregroundColor",
                    }
                },
            ]
        )

    _request_json(
        "POST",
        f"{DOCS_API_URL}/{urllib.parse.quote(document_id)}:batchUpdate",
        access_token=token,
        payload={"requests": content_requests},
    )


def _guess_mime(filename: str, fallback: str = "application/octet-stream") -> str:
    guessed, _ = mimetypes.guess_type(filename or "")
    return guessed or fallback


def upload_drive_file(
    *,
    name: str,
    content: bytes,
    mime_type: str = "",
    parent_id: str | None = None,
    original_filename: str = "",
) -> dict:
    """Upload binary content to Drive via multipart upload."""
    token = get_valid_access_token()
    safe_name = sanitize_drive_name(name)
    content_type = (mime_type or "").strip() or _guess_mime(
        original_filename or safe_name
    )
    metadata: dict = {"name": safe_name}
    if parent_id:
        metadata["parents"] = [parent_id]

    boundary = f"sheria_boundary_{secrets.token_hex(12)}"
    meta_json = json.dumps(metadata)
    body = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{meta_json}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: {content_type}\r\n"
        "Content-Transfer-Encoding: binary\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--".encode("utf-8")

    url = f"{DRIVE_UPLOAD_URL}?uploadType=multipart&fields={DRIVE_FILE_FIELDS}"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            raw = response.read().decode("utf-8")
            created = json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise GoogleDriveAPIError(
            f"Google Drive upload failed ({exc.code}). {detail}".strip()
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GoogleDriveAPIError("Could not upload file to Google Drive.") from exc

    file_id = (created.get("id") or "").strip()
    if not file_id:
        raise GoogleDriveAPIError(f"Failed to upload “{safe_name}”.")
    return created


def rename_drive_file(file_id: str, name: str) -> dict:
    """Rename a Drive file created by this app."""
    if not file_id:
        raise GoogleDriveAPIError("Missing Drive file id.")
    token = get_valid_access_token()
    return _request_json(
        "PATCH",
        f"{DRIVE_FILES_URL}/{urllib.parse.quote(file_id)}"
        f"?fields={DRIVE_FILE_FIELDS}",
        access_token=token,
        payload={"name": sanitize_drive_name(name)},
    )


def trash_drive_file(file_id: str) -> None:
    """Move a Drive file to trash."""
    if not file_id:
        return
    token = get_valid_access_token()
    try:
        _request_json(
            "PATCH",
            f"{DRIVE_FILES_URL}/{urllib.parse.quote(file_id)}?fields=id,trashed",
            access_token=token,
            payload={"trashed": True},
        )
    except GoogleDriveAPIError as exc:
        logger.warning("Could not trash Drive file %s: %s", file_id, exc)


def bootstrap_drive_folders(connection: GoogleDriveConnection | None = None) -> dict:
    """
    Create the firm tree, a folder for every active/suspended client,
    and Employees/{Name}/Personal for employees.
    Returns counts for messaging.
    """
    connection = ensure_firm_folder_structure(connection)
    created = 0
    skipped = 0
    errors = 0
    clients = Client.objects.filter(
        status__in=[Client.Status.ACTIVE, Client.Status.SUSPENDED]
    ).order_by("id")
    for client in clients.iterator():
        try:
            had_folder = bool(client.drive_folder_id)
            ensure_client_folder_structure(client)
            if had_folder:
                skipped += 1
            else:
                created += 1
        except (GoogleDriveAPIError, GoogleDriveOAuthError) as exc:
            errors += 1
            logger.warning(
                "Could not create Drive folders for client %s: %s",
                client.pk,
                exc,
            )

    employees_created = 0
    employees_skipped = 0
    employees_errors = 0
    employees = Employee.objects.exclude(
        status=Employee.Status.SUSPENDED
    ).order_by("id")
    for employee in employees.iterator():
        try:
            had_folder = bool(employee.drive_folder_id)
            ensure_employee_folder_structure(employee)
            if had_folder:
                employees_skipped += 1
            else:
                employees_created += 1
        except (GoogleDriveAPIError, GoogleDriveOAuthError) as exc:
            employees_errors += 1
            logger.warning(
                "Could not create Drive folders for employee %s: %s",
                employee.pk,
                exc,
            )

    return {
        "clients_created": created,
        "clients_existing": skipped,
        "clients_errors": errors,
        "employees_created": employees_created,
        "employees_existing": employees_skipped,
        "employees_errors": employees_errors,
        "root_folder_id": connection.root_folder_id,
        "clients_folder_id": connection.clients_folder_id,
        "work_folder_id": connection.work_folder_id,
    }


def exchange_code(request, code: str) -> GoogleDriveConnection:
    """Exchange authorization code for tokens and persist the firm connection."""
    if not google_oauth_configured():
        raise GoogleDriveOAuthError("Google OAuth is not configured.")

    redirect_uri = (
        (request.session.pop(SESSION_OAUTH_REDIRECT, None) or "").strip()
        or build_redirect_uri(request)
    )

    payload = _post_form(
        GOOGLE_TOKEN_URL,
        {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )

    access_token = (payload.get("access_token") or "").strip()
    if not access_token:
        raise GoogleDriveOAuthError("Google did not return an access token.")

    refresh_token = (payload.get("refresh_token") or "").strip()
    expires_in = int(payload.get("expires_in") or 0)
    scope = (payload.get("scope") or "").strip()

    profile = _get_json(GOOGLE_USERINFO_URL, access_token)
    email = (profile.get("email") or "").strip()
    name = (profile.get("name") or "").strip()

    connection = GoogleDriveConnection.get_solo()
    # Keep prior refresh token if Google omits a new one on reconnect.
    if refresh_token:
        connection.refresh_token = refresh_token
    elif not connection.refresh_token:
        raise GoogleDriveOAuthError(
            "Google did not return a refresh token. Disconnect any prior "
            "Sheria-Centric access in your Google Account and try again."
        )

    connection.access_token = access_token
    connection.token_expiry = (
        timezone.now() + timedelta(seconds=max(expires_in - 60, 0))
        if expires_in
        else None
    )
    connection.scopes = scope or " ".join(GOOGLE_DRIVE_SCOPES)
    connection.account_email = email
    connection.account_name = name
    if getattr(request, "user", None) and request.user.is_authenticated:
        connection.connected_by = request.user
    connection.connected_at = timezone.now()
    connection.save()
    return connection


def disconnect_google_drive(revoke: bool = True) -> None:
    connection = GoogleDriveConnection.get_solo()
    token = connection.refresh_token or connection.access_token
    if revoke and token:
        try:
            _post_form(GOOGLE_REVOKE_URL, {"token": token})
        except GoogleDriveOAuthError:
            # Still clear local credentials if revoke fails.
            pass
    # Clear per-client / case / matter / employee Drive IDs so a later reconnect rebuilds cleanly.
    Client.objects.exclude(drive_folder_id="").update(
        drive_folder_id="",
        drive_personal_documents_folder_id="",
        drive_litigation_folder_id="",
        drive_non_litigation_folder_id="",
    )
    LitigationCase.objects.exclude(drive_folder_id="").update(drive_folder_id="")
    NonLitigationMatter.objects.exclude(drive_folder_id="").update(
        drive_folder_id=""
    )
    Employee.objects.exclude(drive_folder_id="").update(
        drive_folder_id="",
        drive_personal_details_folder_id="",
    )
    connection.clear_tokens()


def pop_oauth_return(request) -> str:
    return request.session.pop(SESSION_OAUTH_RETURN, "") or "/"


def validate_oauth_state(request, state: str) -> None:
    expected = request.session.pop(SESSION_OAUTH_STATE, None)
    if not expected or not state or not secrets.compare_digest(expected, state):
        raise GoogleDriveOAuthError("Invalid OAuth state. Please try connecting again.")
