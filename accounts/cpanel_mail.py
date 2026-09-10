"""Work mailbox provisioning through the cPanel UAPI (Email::add_pop)."""

from __future__ import annotations

import json
import logging
import re
import secrets
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 25
DEFAULT_CPANEL_PORT = 2083
PASSWORD_LENGTH = 18

# cPanel rejects weak passwords; mix all four classes, skip look-alike glyphs.
_PASSWORD_LOWER = "abcdefghijkmnopqrstuvwxyz"
_PASSWORD_UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_PASSWORD_DIGITS = "23456789"
_PASSWORD_SYMBOLS = "!@#$%^*-_=+"


class CpanelMailError(Exception):
    """Raised when a work mailbox cannot be provisioned on cPanel."""


def generate_password(length: int = PASSWORD_LENGTH) -> str:
    alphabet = (
        _PASSWORD_LOWER + _PASSWORD_UPPER + _PASSWORD_DIGITS + _PASSWORD_SYMBOLS
    )
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c in _PASSWORD_LOWER for c in candidate)
            and any(c in _PASSWORD_UPPER for c in candidate)
            and any(c in _PASSWORD_DIGITS for c in candidate)
            and any(c in _PASSWORD_SYMBOLS for c in candidate)
        ):
            return candidate


def _name_part(value: str) -> str:
    """Reduce a personal name to the mailbox-safe form used in addresses."""
    text = unicodedata.normalize("NFKD", (value or "").strip())
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def base_local_part(first_name: str, last_name: str) -> str:
    """Build the default `first.second` local part for a work address."""
    first = _name_part(first_name)
    last = _name_part(last_name)
    parts = [p for p in (first, last) if p]
    if not parts:
        return ""
    return ".".join(parts)


def suggest_work_email(
    first_name: str,
    last_name: str,
    domain: str,
    *,
    taken: set[str] | None = None,
) -> str:
    """
    Default work address for an employee, e.g. `john.doe@firm.com`.

    Adds a numeric suffix when the address is already in use.
    """
    domain = (domain or "").strip().lstrip("@").lower()
    if not domain:
        raise CpanelMailError("No work email domain is configured.")

    base = base_local_part(first_name, last_name)
    if not base:
        raise CpanelMailError(
            "The employee has no usable first or last name for an address."
        )

    used = {value.strip().lower() for value in (taken or set()) if value}
    candidate = f"{base}@{domain}"
    suffix = 2
    while candidate in used:
        candidate = f"{base}{suffix}@{domain}"
        suffix += 1
    return candidate


def preferred_work_email(first_name: str, last_name: str, domain: str) -> str:
    """The natural `first.last@domain` address before any suffix is applied."""
    return suggest_work_email(first_name, last_name, domain, taken=set())


def _require_provisioning_ready(setting) -> str:
    if not setting.work_email_provisioning_ready:
        reason = setting.work_email_provisioning_block_reason()
        raise CpanelMailError(
            reason
            or (
                "Work email provisioning is not configured under System Settings "
                "→ Communication Settings → Work emails (cPanel)."
            )
        )
    return (setting.work_email_domain or "").strip().lstrip("@").lower()


def find_reusable_mailbox(setting, employee, *, reserved=None) -> str:
    """
    Return the preferred work address when it already exists on cPanel and is
    not assigned to another employee in Sheria Centric.
    """
    domain = _require_provisioning_ready(setting)
    preferred = preferred_work_email(
        employee.first_name, employee.last_name, domain
    )
    reserved_set = {
        str(value).strip().lower() for value in (reserved or set()) if value
    }
    if preferred in reserved_set:
        return ""
    existing = list_mailboxes(setting, domain)
    if preferred in existing:
        return preferred
    return ""


def adopt_existing_mailbox(setting, email: str) -> tuple[str, str]:
    """
    Reuse an existing cPanel mailbox by rotating its password.

    Returns the address and the new one-time password for notification.
    """
    _require_provisioning_ready(setting)
    address = (email or "").strip().lower()
    if "@" not in address:
        raise CpanelMailError("A full work email address is required.")
    domain = (setting.work_email_domain or "").strip().lstrip("@").lower()
    _, _, mailbox_domain = address.partition("@")
    if domain and mailbox_domain != domain:
        raise CpanelMailError(
            f"Only mailboxes on @{domain} can be allocated as work email."
        )
    existing = list_mailboxes(setting, mailbox_domain)
    if address not in existing:
        raise CpanelMailError(
            f"{address} is no longer on the mail server. Create a new mailbox instead."
        )
    password = generate_password()
    change_mailbox_password(setting, address, password)
    logger.info("Adopted existing cPanel mailbox %s", address)
    return address, password


def api_base_url(host: str, port: int | None) -> str:
    """Normalise a stored cPanel host into an `https://host:port` base URL."""
    raw = (host or "").strip()
    if not raw:
        raise CpanelMailError("No cPanel host is configured.")
    if "//" not in raw:
        raw = f"https://{raw}"

    parsed = urllib.parse.urlsplit(raw)
    hostname = parsed.hostname
    if not hostname:
        raise CpanelMailError(f"“{host}” is not a valid cPanel host.")

    resolved_port = parsed.port or port or DEFAULT_CPANEL_PORT
    return f"https://{hostname}:{resolved_port}"


def _uapi(setting, module: str, function: str, params: dict) -> dict:
    """Call a cPanel UAPI endpoint and return its `data` payload."""
    base = api_base_url(setting.cpanel_host, setting.cpanel_port)
    username = (setting.cpanel_username or "").strip()
    token = (setting.cpanel_api_token or "").strip()
    if not username or not token:
        raise CpanelMailError(
            "cPanel username and API token are required for work email."
        )

    url = f"{base}/execute/{module}/{function}"
    body = urllib.parse.urlencode(
        {k: v for k, v in params.items() if v is not None}
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"cpanel {username}:{token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(
            request, timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise CpanelMailError(
                "cPanel rejected the API token. Check the username and token, "
                "and that the token allows email management."
            ) from exc
        raise CpanelMailError(
            f"cPanel returned HTTP {exc.code} for {module}::{function}."
        ) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if "certificate" in str(reason).lower():
            raise CpanelMailError(
                f"The TLS certificate for {base} was rejected. Use the exact "
                "server hostname shown in cPanel."
            ) from exc
        raise CpanelMailError(f"Could not reach {base}: {reason}") from exc
    except (TimeoutError, OSError) as exc:
        raise CpanelMailError(f"Could not reach {base}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CpanelMailError(
            "cPanel returned a response that was not JSON. Check the host and "
            "port — the login page is not the API."
        ) from exc

    if not payload.get("status"):
        errors = payload.get("errors") or []
        detail = "; ".join(str(e) for e in errors) or "cPanel refused the request."
        raise CpanelMailError(detail)
    return payload.get("data") or {}


def list_mailboxes(setting, domain: str) -> set[str]:
    """Existing mailbox addresses on the domain, lowercased."""
    data = _uapi(setting, "Email", "list_pops", {"domain": domain})
    addresses = set()
    if isinstance(data, list):
        for row in data:
            email = (row or {}).get("email") if isinstance(row, dict) else None
            if email:
                addresses.add(str(email).strip().lower())
    return addresses


def create_mailbox(setting, email: str, password: str) -> None:
    """Create a single mailbox on the configured domain."""
    local_part, _, domain = email.partition("@")
    quota = setting.work_email_quota_mb or 0
    _uapi(
        setting,
        "Email",
        "add_pop",
        {
            "email": local_part,
            "domain": domain,
            "password": password,
            "quota": quota,
            "send_welcome_email": 0,
            "skip_update_db": 1,
        },
    )


def change_mailbox_password(setting, email: str, password: str) -> None:
    """Update the password for an existing firm mailbox via Email::passwd_pop."""
    address = (email or "").strip().lower()
    if "@" not in address:
        raise CpanelMailError("A full work email address is required.")
    local_part, _, domain = address.partition("@")
    if not local_part or not domain:
        raise CpanelMailError("A full work email address is required.")
    _uapi(
        setting,
        "Email",
        "passwd_pop",
        {
            "email": address,
            "domain": domain,
            "password": password,
        },
    )


def provision_work_email(setting, employee, *, reserved=None) -> tuple[str, str]:
    """
    Create the firm mailbox for an employee.

    Returns the new address and its one-time password. Raises
    `CpanelMailError` with a message meant for the approving user.

    Existing cPanel addresses are skipped (a numeric suffix is used). Call
    :func:`find_reusable_mailbox` / :func:`adopt_existing_mailbox` when the
    manager should be offered the natural matching mailbox first.
    """
    domain = _require_provisioning_ready(setting)
    taken = set(reserved or set()) | list_mailboxes(setting, domain)
    email = suggest_work_email(
        employee.first_name, employee.last_name, domain, taken=taken
    )
    password = generate_password()
    create_mailbox(setting, email, password)
    logger.info("Created cPanel mailbox %s for employee %s", email, employee.pk)
    return email, password
