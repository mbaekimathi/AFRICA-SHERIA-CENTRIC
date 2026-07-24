"""Document Management Drive browser helpers."""

from __future__ import annotations

from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .google_drive import (
    FOLDER_MIME,
    GOOGLE_DOC_MIME,
    GOOGLE_SHEET_MIME,
    GOOGLE_SLIDE_MIME,
    GoogleDriveAPIError,
    GoogleDriveOAuthError,
    build_drive_folder_breadcrumbs,
    firm_root_folder_name,
    google_edit_url,
    list_drive_children,
)
from .models import (
    CaseParty,
    Client,
    Document,
    GoogleDriveConnection,
    LitigationCase,
    MatterParty,
    NonLitigationMatter,
)


def _human_size(raw) -> str:
    try:
        size = int(raw or 0)
    except (TypeError, ValueError):
        return ""
    if size <= 0:
        return ""
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return ""


def _parse_modified(value: str | None):
    if not value:
        return None
    dt = parse_datetime(value)
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone=timezone.utc)
    return dt


def _type_label(mime_type: str, *, is_folder: bool) -> str:
    if is_folder:
        return "Folder"
    mime = (mime_type or "").strip()
    if mime == GOOGLE_DOC_MIME:
        return "Google Docs"
    if mime == GOOGLE_SHEET_MIME:
        return "Google Sheets"
    if mime == GOOGLE_SLIDE_MIME:
        return "Google Slides"
    if mime == "application/pdf":
        return "PDF"
    if mime.startswith("image/"):
        return "Image"
    if "word" in mime or mime.endswith("msword"):
        return "Word"
    if "excel" in mime or "spreadsheet" in mime:
        return "Excel"
    if "powerpoint" in mime or "presentation" in mime:
        return "PowerPoint"
    if mime.startswith("text/"):
        return "Text"
    if "/" in mime:
        return mime.split("/", 1)[-1].upper()[:18] or "File"
    return "File"


def _kind_class(mime_type: str, *, is_folder: bool) -> str:
    if is_folder:
        return "folder"
    mime = (mime_type or "").strip()
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
    return "file"


def _open_url(item: dict, *, is_folder: bool) -> str:
    file_id = (item.get("id") or "").strip()
    mime = (item.get("mimeType") or "").strip()
    if is_folder:
        return (item.get("webViewLink") or "").strip() or (
            f"https://drive.google.com/drive/folders/{file_id}" if file_id else ""
        )
    edit = google_edit_url(file_id, mime)
    if edit:
        return edit
    return (item.get("webViewLink") or "").strip() or (
        f"https://drive.google.com/file/d/{file_id}/view" if file_id else ""
    )


def _folder_workspace_links(
    folder_ids: list[str], *, role_slug: str
) -> dict[str, dict]:
    """Map Drive folder ids to in-app upload-documents URLs when known."""
    ids = [fid for fid in folder_ids if fid]
    if not ids or not role_slug:
        return {}

    links: dict[str, dict] = {}
    for case in LitigationCase.objects.filter(drive_folder_id__in=ids).only(
        "id", "drive_folder_id"
    ):
        fid = (case.drive_folder_id or "").strip()
        if not fid or fid in links:
            continue
        links[fid] = {
            "label": "Open case library",
            "url": reverse(
                "accounts:upload_case_documents",
                kwargs={"role": role_slug, "case_id": case.id},
            ),
            "entity": "case",
            "entity_id": case.id,
        }
    for matter in NonLitigationMatter.objects.filter(drive_folder_id__in=ids).only(
        "id", "drive_folder_id"
    ):
        fid = (matter.drive_folder_id or "").strip()
        if not fid or fid in links:
            continue
        links[fid] = {
            "label": "Open matter library",
            "url": reverse(
                "accounts:upload_matter_documents",
                kwargs={"role": role_slug, "matter_id": matter.id},
            ),
            "entity": "matter",
            "entity_id": matter.id,
        }
    return links


def _document_links(file_ids: list[str]) -> dict[str, Document]:
    ids = [fid for fid in file_ids if fid]
    if not ids:
        return {}
    return {
        (doc.drive_file_id or "").strip(): doc
        for doc in Document.objects.filter(drive_file_id__in=ids).select_related(
            "case", "matter", "uploaded_by"
        )
        if (doc.drive_file_id or "").strip()
    }


def _client_folder_map(folder_ids: list[str]) -> dict[str, Client]:
    ids = [fid for fid in folder_ids if fid]
    if not ids:
        return {}
    return {
        (client.drive_folder_id or "").strip(): client
        for client in Client.objects.filter(drive_folder_id__in=ids).only(
            "id",
            "drive_folder_id",
            "client_type",
            "corporate_kind",
            "first_name",
            "last_name",
            "company_name",
            "email",
            "phone",
        )
        if (client.drive_folder_id or "").strip()
    }


def _build_client_category_groups(items: list[dict]) -> list[dict]:
    """Split Clients-folder items into individual / corporate / other."""
    buckets = {
        Client.ClientType.INDIVIDUAL: [],
        Client.ClientType.CORPORATE: [],
        "other": [],
    }
    for item in items:
        key = item.get("client_category") or "other"
        if key not in buckets:
            key = "other"
        buckets[key].append(item)

    groups = [
        {
            "key": Client.ClientType.INDIVIDUAL,
            "label": "Individual clients",
            "hint": "Personal client folders",
            "icon": "client",
            "tone": 2,
            "items": buckets[Client.ClientType.INDIVIDUAL],
            "count": len(buckets[Client.ClientType.INDIVIDUAL]),
        },
        {
            "key": Client.ClientType.CORPORATE,
            "label": "Corporate clients",
            "hint": "Business and company folders",
            "icon": "building",
            "tone": 5,
            "items": buckets[Client.ClientType.CORPORATE],
            "count": len(buckets[Client.ClientType.CORPORATE]),
        },
    ]
    if buckets["other"]:
        groups.append(
            {
                "key": "other",
                "label": "Other items",
                "hint": "Folders or files not linked to a registered client",
                "icon": "folder",
                "tone": 3,
                "items": buckets["other"],
                "count": len(buckets["other"]),
            }
        )
    return groups


_PARTY_GROUP_META = {
    "plaintiff": {"icon": "scales", "tone": 1, "hint": "Plaintiff filings"},
    "defendant": {"icon": "gavel", "tone": 4, "hint": "Defendant filings"},
    "applicant": {"icon": "scales", "tone": 5, "hint": "Applicant filings"},
    "respondent": {"icon": "gavel", "tone": 3, "hint": "Respondent filings"},
    "petitioner": {"icon": "scroll", "tone": 7, "hint": "Petitioner filings"},
    "appellant": {"icon": "courthouse", "tone": 3, "hint": "Appellant filings"},
    "accused": {"icon": "gavel", "tone": 4, "hint": "Accused filings"},
    "interested_party": {"icon": "clients", "tone": 2, "hint": "Interested party filings"},
    "third_party": {"icon": "handshake", "tone": 1, "hint": "Third party filings"},
    "client": {"icon": "client", "tone": 2, "hint": "Client filings"},
    "counterparty": {"icon": "handshake", "tone": 4, "hint": "Counterparty filings"},
    "beneficiary": {"icon": "shield", "tone": 6, "hint": "Beneficiary filings"},
    "witness": {"icon": "search-doc", "tone": 7, "hint": "Witness filings"},
    "instructing_party": {"icon": "briefcase", "tone": 5, "hint": "Instructing party filings"},
    "other": {"icon": "document", "tone": 3, "hint": "Other party filings"},
    "uncategorized": {
        "icon": "folder",
        "tone": 3,
        "hint": "Files without a party type",
    },
}


def _resolve_entity_drive_folder(folder_id: str) -> dict | None:
    """Return case/matter context when folder_id is an entity Drive folder."""
    folder_id = (folder_id or "").strip()
    if not folder_id:
        return None
    case = (
        LitigationCase.objects.filter(drive_folder_id=folder_id)
        .only("id", "drive_folder_id")
        .first()
    )
    if case is not None:
        return {
            "kind": "case",
            "entity_id": case.pk,
            "party_type_choices": list(CaseParty.PartyType.choices),
            "label_map": dict(CaseParty.PartyType.choices),
        }
    matter = (
        NonLitigationMatter.objects.filter(drive_folder_id=folder_id)
        .only("id", "drive_folder_id")
        .first()
    )
    if matter is not None:
        return {
            "kind": "matter",
            "entity_id": matter.pk,
            "party_type_choices": list(MatterParty.PartyType.choices),
            "label_map": dict(MatterParty.PartyType.choices),
        }
    return None


def _build_party_type_groups(
    items: list[dict], *, party_type_choices: list[tuple[str, str]]
) -> list[dict]:
    """Group case/matter Drive items by linked document party type."""
    buckets: dict[str, list[dict]] = {key: [] for key, _label in party_type_choices}
    uncategorized: list[dict] = []
    for item in items:
        key = (item.get("party_category") or "").strip()
        if key in buckets:
            buckets[key].append(item)
        else:
            uncategorized.append(item)

    groups: list[dict] = []
    for key, label in party_type_choices:
        bucket_items = buckets.get(key) or []
        if not bucket_items:
            continue
        meta = _PARTY_GROUP_META.get(key) or _PARTY_GROUP_META["other"]
        groups.append(
            {
                "key": key,
                "label": label,
                "hint": meta["hint"],
                "icon": meta["icon"],
                "tone": meta["tone"],
                "items": bucket_items,
                "count": len(bucket_items),
            }
        )
    if uncategorized:
        meta = _PARTY_GROUP_META["uncategorized"]
        groups.append(
            {
                "key": "uncategorized",
                "label": "Uncategorized",
                "hint": meta["hint"],
                "icon": meta["icon"],
                "tone": meta["tone"],
                "items": uncategorized,
                "count": len(uncategorized),
            }
        )
    return groups


def build_document_management_browser(
    *,
    folder_id: str = "",
    role_slug: str = "",
) -> dict:
    """
    Build context for browsing firm Drive folders as they appear in Google Drive.
    """
    connection = GoogleDriveConnection.get_solo()
    root_name = firm_root_folder_name()
    root_id = (connection.root_folder_id or "").strip()
    settings_url = ""
    if role_slug:
        settings_url = (
            f"/{role_slug}/dashboard/system-settings/document-settings/"
            "google-drive-settings/"
        )

    base = {
        "google_drive": connection,
        "google_drive_connected": connection.is_connected,
        "google_drive_has_structure": connection.has_folder_structure,
        "google_drive_settings_url": settings_url,
        "firm_drive_root_name": root_name,
        "current_folder_id": "",
        "current_folder_name": root_name,
        "breadcrumbs": [],
        "items": [],
        "folder_count": 0,
        "file_count": 0,
        "item_count": 0,
        "parent_folder_id": "",
        "drive_web_url": "",
        "drive_error": "",
        "is_clients_folder": False,
        "is_party_folder": False,
        "grouping_mode": "",
        "item_groups": [],
        "generated_at": timezone.now(),
    }

    if not connection.is_connected:
        base["drive_error"] = "Connect Google Drive to browse firm documents."
        return base
    if not connection.has_folder_structure or not root_id:
        base["drive_error"] = (
            "Firm Drive folders are not ready yet. Reconnect Google Drive "
            "in settings to create the company structure."
        )
        return base

    requested = (folder_id or "").strip() or root_id
    try:
        crumbs = build_drive_folder_breadcrumbs(
            requested,
            root_folder_id=root_id,
            root_name=root_name,
        )
        children = list_drive_children(requested)
    except (GoogleDriveAPIError, GoogleDriveOAuthError) as exc:
        base["drive_error"] = str(exc) or "Could not load Google Drive contents."
        base["current_folder_id"] = root_id
        base["breadcrumbs"] = [
            {"id": root_id, "name": root_name, "web_view_link": ""}
        ]
        base["drive_web_url"] = (
            f"https://drive.google.com/drive/folders/{root_id}"
        )
        return base

    current = crumbs[-1] if crumbs else {"id": requested, "name": root_name}
    parent_id = crumbs[-2]["id"] if len(crumbs) > 1 else ""
    clients_folder_id = (connection.clients_folder_id or "").strip()
    is_clients_folder = bool(clients_folder_id and requested == clients_folder_id)
    entity_folder = None if is_clients_folder else _resolve_entity_drive_folder(requested)
    is_party_folder = entity_folder is not None
    party_label_map = (entity_folder or {}).get("label_map") or {}

    folder_ids = [
        (item.get("id") or "").strip()
        for item in children
        if (item.get("mimeType") or "") == FOLDER_MIME
    ]
    file_ids = [
        (item.get("id") or "").strip()
        for item in children
        if (item.get("mimeType") or "") != FOLDER_MIME
    ]
    folder_links = _folder_workspace_links(folder_ids, role_slug=role_slug)
    documents = _document_links(file_ids)
    client_folders = _client_folder_map(folder_ids) if is_clients_folder else {}

    items = []
    folder_count = 0
    file_count = 0
    for raw in children:
        item_id = (raw.get("id") or "").strip()
        if not item_id:
            continue
        mime = (raw.get("mimeType") or "").strip()
        is_folder = mime == FOLDER_MIME
        if is_folder:
            folder_count += 1
        else:
            file_count += 1

        modified = _parse_modified(raw.get("modifiedTime"))
        owner = ""
        owners = raw.get("owners") or []
        if owners:
            owner = (
                (owners[0].get("displayName") or owners[0].get("emailAddress") or "")
                .strip()
            )
        if not owner:
            last_user = raw.get("lastModifyingUser") or {}
            owner = (last_user.get("displayName") or "").strip()

        workspace = folder_links.get(item_id) if is_folder else None
        document = documents.get(item_id) if not is_folder else None
        activity_url = ""
        if document and role_slug:
            activity_url = reverse(
                "accounts:document_activity",
                kwargs={"role": role_slug, "document_id": document.pk},
            )

        client = client_folders.get(item_id) if is_folder else None
        client_category = ""
        client_type_label = ""
        party_category = ""
        party_type_label = ""
        type_label = _type_label(mime, is_folder=is_folder)
        if client is not None:
            client_category = client.client_type or Client.ClientType.INDIVIDUAL
            if client_category == Client.ClientType.CORPORATE:
                kind_label = (
                    client.get_corporate_kind_display() if client.corporate_kind else ""
                )
                client_type_label = kind_label or "Corporate client"
            else:
                client_type_label = "Individual client"
            type_label = client_type_label
        elif is_clients_folder:
            client_category = "other"
        elif is_party_folder:
            if document is not None:
                party_category = (document.party_type or "").strip()
                party_type_label = (
                    party_label_map.get(party_category)
                    or document.party_type_label
                    or party_category.replace("_", " ").title()
                )
                if party_type_label:
                    type_label = party_type_label
            else:
                party_category = "uncategorized"
                party_type_label = "Uncategorized"

        items.append(
            {
                "id": item_id,
                "name": (raw.get("name") or "").strip() or "Untitled",
                "is_folder": is_folder,
                "mime_type": mime,
                "type_label": type_label,
                "kind": _kind_class(mime, is_folder=is_folder),
                "size_label": "" if is_folder else _human_size(raw.get("size")),
                "modified_at": modified,
                "owner": owner,
                "open_url": _open_url(raw, is_folder=is_folder),
                "browse_url": f"?folder={item_id}" if is_folder else "",
                "workspace_url": (workspace or {}).get("url", ""),
                "workspace_label": (workspace or {}).get("label", ""),
                "document_id": document.pk if document else None,
                "activity_url": activity_url,
                "client_category": client_category,
                "client_type_label": client_type_label,
                "client_id": client.pk if client else None,
                "party_category": party_category,
                "party_type_label": party_type_label,
            }
        )

    # Folders already first from Drive orderBy, but keep a stable local sort.
    items.sort(key=lambda row: (not row["is_folder"], row["name"].lower()))
    item_groups: list[dict] = []
    grouping_mode = ""
    if is_clients_folder:
        grouping_mode = "clients"
        item_groups = _build_client_category_groups(items)
    elif is_party_folder:
        grouping_mode = "party"
        item_groups = _build_party_type_groups(
            items,
            party_type_choices=entity_folder["party_type_choices"],
        )

    base.update(
        {
            "current_folder_id": current.get("id") or requested,
            "current_folder_name": current.get("name") or root_name,
            "breadcrumbs": crumbs,
            "items": items,
            "item_groups": item_groups,
            "is_clients_folder": is_clients_folder,
            "is_party_folder": is_party_folder,
            "grouping_mode": grouping_mode,
            "folder_count": folder_count,
            "file_count": file_count,
            "item_count": folder_count + file_count,
            "parent_folder_id": parent_id,
            "drive_web_url": current.get("web_view_link")
            or f"https://drive.google.com/drive/folders/{requested}",
            "drive_error": "",
        }
    )
    return base
