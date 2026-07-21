"""Live verification of firm contact channels (email, phone, website, social)."""

from __future__ import annotations

import re
import socket
import ssl
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from email.utils import parseaddr
from typing import Any
from urllib.parse import urlparse

from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import FirmCompanyInformation

USER_AGENT = (
    "SheriaCentricContactVerify/1.0 (+https://sheria-centric.local; firm contact check)"
)
URL_TIMEOUT_SECONDS = 8
DNS_TIMEOUT_SECONDS = 4

# Status tones map to existing .status-pill modifiers.
STATUS_CONNECTED = "connected"
STATUS_REACHABLE = "reachable"
STATUS_NOT_SET = "not_set"
STATUS_INVALID = "invalid"
STATUS_UNREACHABLE = "unreachable"
STATUS_CHECKING = "checking"

TONE_BY_STATUS = {
    STATUS_CONNECTED: "active",
    STATUS_REACHABLE: "active",
    STATUS_NOT_SET: "suspended",
    STATUS_INVALID: "pending",
    STATUS_UNREACHABLE: "pending",
    STATUS_CHECKING: "partial",
}

LABEL_BY_STATUS = {
    STATUS_CONNECTED: "Connected",
    STATUS_REACHABLE: "Reachable",
    STATUS_NOT_SET: "Not set",
    STATUS_INVALID: "Invalid",
    STATUS_UNREACHABLE: "Unreachable",
    STATUS_CHECKING: "Checking…",
}

PHONE_RE = re.compile(
    r"^\+?[0-9][0-9\s\-().]{6,22}[0-9]$"
)


@dataclass
class ChannelStatus:
    key: str
    label: str
    kind: str  # email | phone | url | address
    value: str
    status: str
    tone: str
    status_label: str
    detail: str
    required: bool = False
    href: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _blank(value: str | None) -> str:
    return (value or "").strip()


def _result(
    *,
    key: str,
    label: str,
    kind: str,
    value: str,
    status: str,
    detail: str,
    required: bool = False,
    href: str = "",
) -> ChannelStatus:
    return ChannelStatus(
        key=key,
        label=label,
        kind=kind,
        value=value,
        status=status,
        tone=TONE_BY_STATUS.get(status, "suspended"),
        status_label=LABEL_BY_STATUS.get(status, status.replace("_", " ").title()),
        detail=detail,
        required=required,
        href=href,
    )


def _normalize_url(raw: str) -> str:
    value = _blank(raw)
    if not value:
        return ""
    if not re.match(r"^[a-z][a-z0-9+.-]*://", value, re.I):
        value = f"https://{value}"
    return value


def _host_resolves(hostname: str) -> tuple[bool, str]:
    host = _blank(hostname).rstrip(".").lower()
    if not host or host in {"localhost", "127.0.0.1", "::1"}:
        return False, "Host cannot be verified."
    try:
        socket.setdefaulttimeout(DNS_TIMEOUT_SECONDS)
        infos = socket.getaddrinfo(host, None)
        if not infos:
            return False, "Domain did not resolve."
        return True, "Domain resolves."
    except OSError as exc:
        return False, f"DNS lookup failed ({exc})."
    finally:
        socket.setdefaulttimeout(None)


def verify_email(value: str, *, required: bool = True) -> ChannelStatus:
    email = _blank(value)
    if not email:
        return _result(
            key="email",
            label="Primary email",
            kind="email",
            value="",
            status=STATUS_NOT_SET,
            detail="No primary email registered.",
            required=required,
        )

    _, addr = parseaddr(email)
    candidate = addr or email
    try:
        validate_email(candidate)
    except ValidationError:
        return _result(
            key="email",
            label="Primary email",
            kind="email",
            value=email,
            status=STATUS_INVALID,
            detail="Email format is invalid.",
            required=required,
            href=f"mailto:{email}",
        )

    domain = candidate.rsplit("@", 1)[-1]
    ok, detail = _host_resolves(domain)
    if not ok:
        return _result(
            key="email",
            label="Primary email",
            kind="email",
            value=email,
            status=STATUS_UNREACHABLE,
            detail=f"Mail domain unreachable: {detail}",
            required=required,
            href=f"mailto:{email}",
        )

    return _result(
        key="email",
        label="Primary email",
        kind="email",
        value=email,
        status=STATUS_CONNECTED,
        detail=f"Format valid — {detail}",
        required=required,
        href=f"mailto:{email}",
    )


def _digits_only(phone: str) -> str:
    return re.sub(r"\D+", "", phone or "")


def verify_phone(value: str, *, required: bool = True) -> ChannelStatus:
    phone = _blank(value)
    if not phone:
        return _result(
            key="phone",
            label="Primary phone",
            kind="phone",
            value="",
            status=STATUS_NOT_SET,
            detail="No primary phone registered.",
            required=required,
        )

    digits = _digits_only(phone)
    if not PHONE_RE.match(phone) or len(digits) < 9 or len(digits) > 15:
        return _result(
            key="phone",
            label="Primary phone",
            kind="phone",
            value=phone,
            status=STATUS_INVALID,
            detail="Phone number format looks invalid.",
            required=required,
            href=f"tel:{digits}" if digits else "",
        )

    # Normalize to WhatsApp-friendly MSISDN (Kenya 0… → 254…).
    wa = digits
    if wa.startswith("0") and len(wa) == 10:
        wa = "254" + wa[1:]
    elif wa.startswith("254") and len(wa) == 12:
        pass
    elif len(wa) == 9 and not wa.startswith("0"):
        wa = "254" + wa

    return _result(
        key="phone",
        label="Primary phone",
        kind="phone",
        value=phone,
        status=STATUS_CONNECTED,
        detail="Format valid — WhatsApp / dial ready.",
        required=required,
        href=f"https://wa.me/{wa}",
    )


def verify_url(
    *,
    key: str,
    label: str,
    value: str,
    required: bool = False,
) -> ChannelStatus:
    raw = _blank(value)
    if not raw:
        return _result(
            key=key,
            label=label,
            kind="url",
            value="",
            status=STATUS_NOT_SET,
            detail=f"{label} is not set.",
            required=required,
        )

    url = _normalize_url(raw)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return _result(
            key=key,
            label=label,
            kind="url",
            value=raw,
            status=STATUS_INVALID,
            detail="URL must be a valid http(s) address.",
            required=required,
        )

    host = parsed.hostname or ""
    ok, dns_detail = _host_resolves(host)
    if not ok:
        return _result(
            key=key,
            label=label,
            kind="url",
            value=raw,
            status=STATUS_UNREACHABLE,
            detail=dns_detail,
            required=required,
            href=url,
        )

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
    }
    last_error = ""
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=URL_TIMEOUT_SECONDS) as resp:
                code = getattr(resp, "status", None) or resp.getcode()
                if 200 <= int(code) < 400:
                    return _result(
                        key=key,
                        label=label,
                        kind="url",
                        value=raw,
                        status=STATUS_CONNECTED,
                        detail=f"HTTP {code} — live connection confirmed.",
                        required=required,
                        href=url,
                    )
                if int(code) in {401, 403, 405}:
                    return _result(
                        key=key,
                        label=label,
                        kind="url",
                        value=raw,
                        status=STATUS_REACHABLE,
                        detail=f"HTTP {code} — host responds (access restricted).",
                        required=required,
                        href=url,
                    )
                last_error = f"HTTP {code}"
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403, 405}:
                return _result(
                    key=key,
                    label=label,
                    kind="url",
                    value=raw,
                    status=STATUS_REACHABLE,
                    detail=f"HTTP {exc.code} — host responds (access restricted).",
                    required=required,
                    href=url,
                )
            if method == "HEAD" and exc.code in {400, 404, 405, 501}:
                last_error = f"HTTP {exc.code}"
                continue
            last_error = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
            last_error = str(exc.reason if hasattr(exc, "reason") else exc)
            if method == "HEAD":
                continue

    return _result(
        key=key,
        label=label,
        kind="url",
        value=raw,
        status=STATUS_UNREACHABLE,
        detail=f"Could not reach URL ({last_error or 'timeout'}).",
        required=required,
        href=url,
    )


def verify_address_field(
    *,
    key: str,
    label: str,
    value: str,
    required: bool = False,
) -> ChannelStatus:
    text = _blank(value)
    if not text:
        return _result(
            key=key,
            label=label,
            kind="address",
            value="",
            status=STATUS_NOT_SET,
            detail=f"{label} is not registered.",
            required=required,
        )
    return _result(
        key=key,
        label=label,
        kind="address",
        value=text,
        status=STATUS_CONNECTED,
        detail="Registered.",
        required=required,
    )


def _values_from_company(company: FirmCompanyInformation) -> dict[str, str]:
    return {
        "email": company.email or "",
        "phone": company.phone or "",
        "website": company.website or "",
        "linkedin_url": company.linkedin_url or "",
        "facebook_url": company.facebook_url or "",
        "instagram_url": company.instagram_url or "",
        "x_url": company.x_url or "",
        "youtube_url": company.youtube_url or "",
        "physical_address": company.physical_address or "",
        "postal_address": company.postal_address or "",
        "city": company.city or "",
        "country": company.country or "",
    }


CHANNEL_SPECS: list[dict[str, Any]] = [
    {"key": "email", "label": "Primary email", "kind": "email", "required": True},
    {"key": "phone", "label": "Primary phone", "kind": "phone", "required": True},
    {"key": "website", "label": "Website", "kind": "url", "required": False},
    {"key": "linkedin_url", "label": "LinkedIn", "kind": "url", "required": False},
    {"key": "facebook_url", "label": "Facebook", "kind": "url", "required": False},
    {"key": "instagram_url", "label": "Instagram", "kind": "url", "required": False},
    {"key": "x_url", "label": "X (Twitter)", "kind": "url", "required": False},
    {"key": "youtube_url", "label": "YouTube", "kind": "url", "required": False},
    {
        "key": "physical_address",
        "label": "Physical address",
        "kind": "address",
        "required": True,
    },
    {
        "key": "postal_address",
        "label": "Postal address",
        "kind": "address",
        "required": False,
    },
    {"key": "city", "label": "City", "kind": "address", "required": True},
    {"key": "country", "label": "Country", "kind": "address", "required": True},
]


def _verify_one(spec: dict[str, Any], values: dict[str, str]) -> ChannelStatus:
    key = spec["key"]
    value = values.get(key, "")
    kind = spec["kind"]
    label = spec["label"]
    required = bool(spec.get("required"))
    if kind == "email":
        return verify_email(value, required=required)
    if kind == "phone":
        return verify_phone(value, required=required)
    if kind == "url":
        return verify_url(key=key, label=label, value=value, required=required)
    return verify_address_field(
        key=key, label=label, value=value, required=required
    )


def verify_company_contacts(
    company: FirmCompanyInformation | None = None,
    *,
    overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Live-check all company contact channels.

    URL checks run in parallel. Email/phone/address checks are local + DNS.
    """
    company = company or FirmCompanyInformation.get_solo()
    values = _values_from_company(company)
    if overrides:
        for key, raw in overrides.items():
            if key in values:
                values[key] = "" if raw is None else str(raw)

    channels: list[ChannelStatus] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(_verify_one, spec, values): spec["key"]
            for spec in CHANNEL_SPECS
        }
        by_key: dict[str, ChannelStatus] = {}
        for future in as_completed(futures):
            result = future.result()
            by_key[result.key] = result
        channels = [by_key[spec["key"]] for spec in CHANNEL_SPECS if spec["key"] in by_key]

    connected = sum(
        1
        for c in channels
        if c.status in {STATUS_CONNECTED, STATUS_REACHABLE}
    )
    not_set = sum(1 for c in channels if c.status == STATUS_NOT_SET)
    problems = sum(
        1
        for c in channels
        if c.status in {STATUS_INVALID, STATUS_UNREACHABLE}
    )
    required_problems = [
        c
        for c in channels
        if c.required and c.status in {STATUS_NOT_SET, STATUS_INVALID, STATUS_UNREACHABLE}
    ]

    if required_problems:
        overall_status = "issues"
        overall_tone = "pending"
        overall_label = "Needs attention"
        overall_detail = (
            f"{len(required_problems)} required channel"
            f"{'s' if len(required_problems) != 1 else ''} need fixing."
        )
    elif problems:
        overall_status = "partial"
        overall_tone = "partial"
        overall_label = "Partially connected"
        overall_detail = (
            f"{connected} connected — {problems} optional channel"
            f"{'s' if problems != 1 else ''} unreachable or invalid."
        )
    elif not_set and connected:
        overall_status = "partial"
        overall_tone = "partial"
        overall_label = "Partially connected"
        overall_detail = f"{connected} connected — {not_set} optional not set."
    elif connected:
        overall_status = "connected"
        overall_tone = "active"
        overall_label = "Connections healthy"
        overall_detail = f"All set channels verified live ({connected})."
    else:
        overall_status = "empty"
        overall_tone = "suspended"
        overall_label = "No contacts set"
        overall_detail = "Register contact details, then verify connections."

    connection_channels = [c for c in channels if c.kind in {"email", "phone", "url"}]

    return {
        "verified_at": timezone.now().isoformat(),
        "overall_status": overall_status,
        "overall_tone": overall_tone,
        "overall_label": overall_label,
        "overall_detail": overall_detail,
        "connected_count": connected,
        "problem_count": problems,
        "not_set_count": not_set,
        "channel_count": len(channels),
        "channels": [c.to_dict() for c in channels],
        "connection_channels": [c.to_dict() for c in connection_channels],
        "by_key": {c.key: c.to_dict() for c in channels},
    }
