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

from .models import Client, GoogleDriveConnection, LitigationCase, NonLitigationMatter

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
WORK_FOLDER_NAME = "Work"
LITIGATION_FOLDER_NAME = "Litigation"
NON_LITIGATION_FOLDER_NAME = "Non-Litigation"

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
    text = raw.decode("utf-8", errors="replace")
    # Keep snapshots bounded for DB/UI.
    max_chars = 120_000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[Content truncated]"
    return text


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


def get_valid_access_token(connection: GoogleDriveConnection | None = None) -> str:
    """Return a usable access token, refreshing when expired."""
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
        raise GoogleDriveAPIError(
            "Google Drive access expired. Reconnect Google Drive in settings."
        )

    payload = _post_form(
        GOOGLE_TOKEN_URL,
        {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        },
    )
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


def ensure_folder(
    access_token: str,
    *,
    name: str,
    parent_id: str | None = None,
    existing_id: str = "",
) -> str:
    if existing_id and folder_exists(access_token, existing_id):
        return existing_id
    return create_folder(access_token, name, parent_id=parent_id)


def ensure_firm_folder_structure(
    connection: GoogleDriveConnection | None = None,
) -> GoogleDriveConnection:
    """
    Ensure Company / Clients / Work folders exist on the connected Drive.
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

    connection.root_folder_id = root_id
    connection.clients_folder_id = clients_id
    connection.work_folder_id = work_id
    connection.save(
        update_fields=[
            "root_folder_id",
            "clients_folder_id",
            "work_folder_id",
            "updated_at",
        ]
    )
    return connection


def ensure_client_folder_structure(client: Client) -> Client:
    """
    Ensure Clients/{Client}/Litigation and Clients/{Client}/Non-Litigation.
    """
    connection = GoogleDriveConnection.get_solo()
    if not connection.is_connected or not connection.clients_folder_id:
        return client

    token = get_valid_access_token(connection)
    if not folder_exists(token, connection.clients_folder_id):
        connection = ensure_firm_folder_structure(connection)
        token = get_valid_access_token(connection)

    client_name = sanitize_drive_name(
        client.get_full_name(), fallback=f"Client {client.pk}"
    )
    client_folder_id = ensure_folder(
        token,
        name=client_name,
        parent_id=connection.clients_folder_id,
        existing_id=client.drive_folder_id,
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
    client.drive_litigation_folder_id = litigation_id
    client.drive_non_litigation_folder_id = non_litigation_id
    client.save(
        update_fields=[
            "drive_folder_id",
            "drive_litigation_folder_id",
            "drive_non_litigation_folder_id",
        ]
    )
    return client


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
    Create the firm tree and a folder for every active/suspended client.
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
    return {
        "clients_created": created,
        "clients_existing": skipped,
        "clients_errors": errors,
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
    # Clear per-client / case / matter Drive IDs so a later reconnect rebuilds cleanly.
    Client.objects.exclude(drive_folder_id="").update(
        drive_folder_id="",
        drive_litigation_folder_id="",
        drive_non_litigation_folder_id="",
    )
    LitigationCase.objects.exclude(drive_folder_id="").update(drive_folder_id="")
    NonLitigationMatter.objects.exclude(drive_folder_id="").update(
        drive_folder_id=""
    )
    connection.clear_tokens()


def pop_oauth_return(request) -> str:
    return request.session.pop(SESSION_OAUTH_RETURN, "") or "/"


def validate_oauth_state(request, state: str) -> None:
    expected = request.session.pop(SESSION_OAUTH_STATE, None)
    if not expected or not state or not secrets.compare_digest(expected, state):
        raise GoogleDriveOAuthError("Invalid OAuth state. Please try connecting again.")
