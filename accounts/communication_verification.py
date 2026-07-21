"""Live verification of Communication Settings (email SMTP, SMS, WhatsApp)."""

from __future__ import annotations

import base64
import json
import re
import smtplib
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from email.utils import parseaddr
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone

from .models import CommunicationSettings

USER_AGENT = (
    "SheriaCentricCommVerify/1.0 (+https://sheria-centric.local; communication check)"
)
SMTP_TIMEOUT_SECONDS = 12
HTTP_TIMEOUT_SECONDS = 10
DNS_TIMEOUT_SECONDS = 4
TCP_PROBE_TIMEOUT_SECONDS = 6


def _tcp_port_open(host: str, port: int, *, timeout: float = TCP_PROBE_TIMEOUT_SECONDS) -> tuple[bool, str]:
    """Fast TCP probe so we can tell firewall blocks from SMTP/auth failures."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "TCP port open."
    except TimeoutError:
        return False, "Connection timed out (port closed or blocked)."
    except OSError as exc:
        return False, f"TCP connect failed ({exc})."

STATUS_CONNECTED = "connected"
STATUS_REACHABLE = "reachable"
STATUS_NOT_SET = "not_set"
STATUS_DISABLED = "disabled"
STATUS_INVALID = "invalid"
STATUS_UNREACHABLE = "unreachable"
STATUS_CHECKING = "checking"

TONE_BY_STATUS = {
    STATUS_CONNECTED: "active",
    STATUS_REACHABLE: "active",
    STATUS_NOT_SET: "suspended",
    STATUS_DISABLED: "suspended",
    STATUS_INVALID: "pending",
    STATUS_UNREACHABLE: "pending",
    STATUS_CHECKING: "partial",
}

LABEL_BY_STATUS = {
    STATUS_CONNECTED: "Connected",
    STATUS_REACHABLE: "Reachable",
    STATUS_NOT_SET: "Not set",
    STATUS_DISABLED: "Disabled",
    STATUS_INVALID: "Invalid",
    STATUS_UNREACHABLE: "Unreachable",
    STATUS_CHECKING: "Checking…",
}

PHONE_RE = re.compile(r"^\+?[0-9][0-9\s\-().]{6,22}[0-9]$")

OVERRIDE_KEYS = (
    "email_enabled",
    "email_host",
    "email_port",
    "email_use_tls",
    "email_use_ssl",
    "email_host_user",
    "email_host_password",
    "email_from_email",
    "email_from_name",
    "sms_enabled",
    "sms_provider",
    "sms_username",
    "sms_api_key",
    "sms_api_secret",
    "sms_sender_id",
    "whatsapp_enabled",
    "whatsapp_business_number",
    "whatsapp_default_message",
    "whatsapp_api_enabled",
    "whatsapp_provider",
    "whatsapp_api_token",
    "whatsapp_phone_number_id",
    "whatsapp_webhook_url",
)


@dataclass
class ChannelStatus:
    key: str
    label: str
    kind: str
    value: str
    status: str
    tone: str
    status_label: str
    detail: str
    required: bool = False
    href: str = ""
    problem_fields: list[str] | None = None
    problem_labels: list[str] | None = None
    fix_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


FIELD_LABELS = {
    "email_enabled": "Enable email",
    "email_host": "SMTP host",
    "email_port": "SMTP port",
    "email_use_tls": "Use TLS",
    "email_use_ssl": "Use SSL",
    "email_host_user": "SMTP username",
    "email_host_password": "SMTP password",
    "email_from_email": "From email address",
    "email_from_name": "From display name",
    "sms_enabled": "Enable SMS",
    "sms_provider": "SMS provider",
    "sms_username": "API username / Account SID",
    "sms_api_key": "API key",
    "sms_api_secret": "API secret / Auth token",
    "sms_sender_id": "Sender ID / From number",
    "whatsapp_enabled": "Enable WhatsApp",
    "whatsapp_business_number": "Business WhatsApp number",
    "whatsapp_default_message": "Default chat message",
    "whatsapp_api_enabled": "Enable WhatsApp Business API",
    "whatsapp_provider": "WhatsApp API provider",
    "whatsapp_api_token": "API access token",
    "whatsapp_phone_number_id": "Phone number ID / sender",
    "whatsapp_webhook_url": "Webhook URL",
}

CHANNEL_PANEL_IDS = {
    "email": "communication-email-panel",
    "sms": "communication-sms-panel",
    "whatsapp": "communication-whatsapp-panel",
}


def _blank(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _blank(value).lower() in {"1", "true", "yes", "on"}


def _problem_labels(fields: list[str] | None) -> list[str]:
    return [FIELD_LABELS.get(field, field.replace("_", " ")) for field in (fields or [])]


def _fix_hint(fields: list[str] | None) -> str:
    labels = _problem_labels(fields)
    if not labels:
        return ""
    if len(labels) == 1:
        return f'Fix: check the "{labels[0]}" field below.'
    joined = ", ".join(f'"{label}"' for label in labels[:-1])
    return f'Fix: check {joined} and "{labels[-1]}" below.'


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
    problem_fields: list[str] | None = None,
) -> ChannelStatus:
    fields = list(problem_fields or [])
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
        problem_fields=fields,
        problem_labels=_problem_labels(fields),
        fix_hint=_fix_hint(fields),
    )


def _digits_only(phone: str) -> str:
    return re.sub(r"\D+", "", phone or "")


def _host_resolves(hostname: str) -> tuple[bool, str]:
    host = _blank(hostname).rstrip(".").lower()
    if not host:
        return False, "Host is empty."
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True, "Local host accepted for testing."
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


def _http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    timeout: float = HTTP_TIMEOUT_SECONDS,
) -> tuple[int, dict[str, Any] | None, str]:
    req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, method=method, headers=req_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                payload = None
            return resp.getcode(), payload if isinstance(payload, dict) else None, body
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        payload = None
        try:
            parsed = json.loads(body) if body else None
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            pass
        return exc.code, payload, body or str(exc.reason)
    except urllib.error.URLError as exc:
        return 0, None, str(exc.reason or exc)
    except Exception as exc:  # noqa: BLE001 — surface any transport failure
        return 0, None, str(exc)


def values_from_settings(setting: CommunicationSettings) -> dict[str, Any]:
    return {key: getattr(setting, key, "") for key in OVERRIDE_KEYS}


def merge_overrides(
    base: dict[str, Any], overrides: dict[str, Any] | None
) -> dict[str, Any]:
    values = dict(base)
    if not overrides:
        return values
    for key in OVERRIDE_KEYS:
        if key not in overrides:
            continue
        raw = overrides[key]
        if key.endswith("_enabled") or key in {
            "email_use_tls",
            "email_use_ssl",
            "whatsapp_api_enabled",
        }:
            values[key] = _as_bool(raw)
        elif key == "email_port":
            try:
                values[key] = int(_blank(raw) or 0)
            except ValueError:
                values[key] = 0
        else:
            values[key] = "" if raw is None else str(raw)
    return values


def verify_email_smtp(values: dict[str, Any]) -> ChannelStatus:
    enabled = _as_bool(values.get("email_enabled"))
    host = _blank(values.get("email_host"))
    from_email = _blank(values.get("email_from_email"))
    user = _blank(values.get("email_host_user"))
    password = _blank(values.get("email_host_password"))
    display = from_email or host or "Email"

    if not enabled:
        return _result(
            key="email",
            label="Email (SMTP)",
            kind="email",
            value=display if host or from_email else "",
            status=STATUS_DISABLED,
            detail="Email channel is turned off.",
            required=False,
        )

    if not host:
        return _result(
            key="email",
            label="Email (SMTP)",
            kind="email",
            value="",
            status=STATUS_NOT_SET,
            detail="SMTP host is not set.",
            required=True,
            problem_fields=["email_host"],
        )

    try:
        port = int(values.get("email_port") or 0)
    except (TypeError, ValueError):
        port = 0
    if port < 1 or port > 65535:
        return _result(
            key="email",
            label="Email (SMTP)",
            kind="email",
            value=f"{host}:{port or '?'}",
            status=STATUS_INVALID,
            detail="SMTP port must be between 1 and 65535.",
            required=True,
            problem_fields=["email_port"],
        )

    use_tls, use_ssl = CommunicationSettings.smtp_security_for_port(port)
    security_label = CommunicationSettings.smtp_security_label(port)

    if not from_email:
        return _result(
            key="email",
            label="Email (SMTP)",
            kind="email",
            value=host,
            status=STATUS_INVALID,
            detail="From email address is required when email is enabled.",
            required=True,
            problem_fields=["email_from_email"],
        )

    _, addr = parseaddr(from_email)
    candidate = addr or from_email
    try:
        validate_email(candidate)
    except ValidationError:
        return _result(
            key="email",
            label="Email (SMTP)",
            kind="email",
            value=from_email,
            status=STATUS_INVALID,
            detail="From email address format is invalid.",
            required=True,
            problem_fields=["email_from_email"],
        )

    ok, dns_detail = _host_resolves(host)
    if not ok:
        return _result(
            key="email",
            label="Email (SMTP)",
            kind="email",
            value=f"{host}:{port}",
            status=STATUS_UNREACHABLE,
            detail=(
                f'SMTP host "{host}" is unreachable ({dns_detail}). '
                "Confirm the host name with your mail provider."
            ),
            required=True,
            problem_fields=["email_host"],
        )

    tcp_ok, tcp_detail = _tcp_port_open(host, port)
    if not tcp_ok:
        alt_port = 465 if port == 587 else 587 if port == 465 else None
        alt_note = ""
        if alt_port is not None:
            alt_ok, _ = _tcp_port_open(host, alt_port)
            if alt_ok:
                alt_sec = CommunicationSettings.smtp_security_label(alt_port)
                alt_note = (
                    f' Port {alt_port} ({alt_sec}) is reachable — try changing '
                    f'the SMTP port to {alt_port}.'
                )
            else:
                alt_note = (
                    f" Port {alt_port} is also blocked from this network."
                )
        return _result(
            key="email",
            label="Email (SMTP)",
            kind="email",
            value=f"{host}:{port}",
            status=STATUS_UNREACHABLE,
            detail=(
                f'Cannot reach "{host}:{port}" — {tcp_detail} '
                "The host name resolves, but SMTP traffic is blocked "
                "(ISP, local firewall, or hosting remote-SMTP rules)."
                f"{alt_note}"
            ),
            required=True,
            problem_fields=["email_host", "email_port"],
        )

    server: smtplib.SMTP | smtplib.SMTP_SSL | None = None
    try:
        if use_ssl:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(
                host, port, timeout=SMTP_TIMEOUT_SECONDS, context=context
            )
        else:
            server = smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT_SECONDS)
            server.ehlo()
            if use_tls:
                context = ssl.create_default_context()
                server.starttls(context=context)
                server.ehlo()

        auth_note = "anonymous session (no username)"
        if user:
            if not password:
                return _result(
                    key="email",
                    label="Email (SMTP)",
                    kind="email",
                    value=f"{host}:{port}",
                    status=STATUS_INVALID,
                    detail="SMTP username is set but password is empty.",
                    required=True,
                    problem_fields=["email_host_password"],
                )
            server.login(user, password)
            auth_note = f"authenticated as {user}"

        return _result(
            key="email",
            label="Email (SMTP)",
            kind="email",
            value=f"{host}:{port}",
            status=STATUS_CONNECTED,
            detail=f"SMTP live check OK ({security_label}) — {auth_note}.",
            required=True,
        )
    except smtplib.SMTPAuthenticationError:
        return _result(
            key="email",
            label="Email (SMTP)",
            kind="email",
            value=f"{host}:{port}",
            status=STATUS_INVALID,
            detail=(
                f'SMTP rejected login for "{user or "this account"}". '
                "Check username and password."
            ),
            required=True,
            problem_fields=["email_host_user", "email_host_password"],
        )
    except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, TimeoutError, OSError) as exc:
        return _result(
            key="email",
            label="Email (SMTP)",
            kind="email",
            value=f"{host}:{port}",
            status=STATUS_UNREACHABLE,
            detail=(
                f'Could not complete SMTP handshake with "{host}:{port}" '
                f"({security_label}): {exc}."
            ),
            required=True,
            problem_fields=["email_host", "email_port"],
        )
    except smtplib.SMTPException as exc:
        return _result(
            key="email",
            label="Email (SMTP)",
            kind="email",
            value=f"{host}:{port}",
            status=STATUS_UNREACHABLE,
            detail=f'SMTP error on "{host}:{port}" ({security_label}): {exc}',
            required=True,
            problem_fields=["email_host", "email_port"],
        )
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                try:
                    server.close()
                except Exception:
                    pass


def verify_sms_provider(values: dict[str, Any]) -> ChannelStatus:
    enabled = _as_bool(values.get("sms_enabled"))
    provider = _blank(values.get("sms_provider")) or CommunicationSettings.SmsProvider.NONE
    username = _blank(values.get("sms_username"))
    api_key = _blank(values.get("sms_api_key"))
    api_secret = _blank(values.get("sms_api_secret"))
    sender = _blank(values.get("sms_sender_id"))
    label = "SMS"

    if not enabled:
        return _result(
            key="sms",
            label=label,
            kind="sms",
            value="",
            status=STATUS_DISABLED,
            detail="SMS channel is turned off.",
        )

    if provider in {"", CommunicationSettings.SmsProvider.NONE}:
        return _result(
            key="sms",
            label=label,
            kind="sms",
            value="",
            status=STATUS_NOT_SET,
            detail="Choose an SMS provider.",
            required=True,
            problem_fields=["sms_provider"],
        )

    if provider == CommunicationSettings.SmsProvider.AFRICASTALKING:
        missing = []
        if not username:
            missing.append("sms_username")
        if not api_key:
            missing.append("sms_api_key")
        if not sender:
            missing.append("sms_sender_id")
        if missing:
            return _result(
                key="sms",
                label=label,
                kind="sms",
                value="Africa's Talking",
                status=STATUS_INVALID,
                detail="Username, API key, and sender ID are required for Africa's Talking.",
                required=True,
                problem_fields=missing,
            )
        query = urllib.parse.urlencode({"username": username})
        url = f"https://api.africastalking.com/version1/user?{query}"
        code, payload, err = _http_json(
            url,
            headers={
                "apiKey": api_key,
                "Accept": "application/json",
            },
        )
        if code == 200 and payload:
            balance = ""
            user_data = payload.get("UserData") or payload.get("userData") or {}
            if isinstance(user_data, dict):
                balance = _blank(user_data.get("balance") or user_data.get("Balance"))
            detail = "Africa's Talking credentials accepted."
            if balance:
                detail = f"Africa's Talking connected — balance {balance}."
            return _result(
                key="sms",
                label=label,
                kind="sms",
                value=f"Africa's Talking · {sender}",
                status=STATUS_CONNECTED,
                detail=detail,
                required=True,
            )
        if code in {401, 403}:
            return _result(
                key="sms",
                label=label,
                kind="sms",
                value="Africa's Talking",
                status=STATUS_INVALID,
                detail="Africa's Talking rejected the API key or username.",
                required=True,
                problem_fields=["sms_username", "sms_api_key"],
            )
        return _result(
            key="sms",
            label=label,
            kind="sms",
            value="Africa's Talking",
            status=STATUS_UNREACHABLE,
            detail=(
                f"Could not reach Africa's Talking API (HTTP {code or '—'}): "
                f"{err[:160]}. Check your network or provider status."
            ),
            required=True,
            problem_fields=["sms_provider", "sms_api_key"],
        )

    if provider == CommunicationSettings.SmsProvider.TWILIO:
        missing = []
        if not username:
            missing.append("sms_username")
        if not api_secret:
            missing.append("sms_api_secret")
        if not sender:
            missing.append("sms_sender_id")
        if missing:
            return _result(
                key="sms",
                label=label,
                kind="sms",
                value="Twilio",
                status=STATUS_INVALID,
                detail="Account SID, Auth Token, and from-number are required for Twilio.",
                required=True,
                problem_fields=missing,
            )
        token = base64.b64encode(f"{username}:{api_secret}".encode()).decode()
        url = f"https://api.twilio.com/2010-04-01/Accounts/{urllib.parse.quote(username)}.json"
        code, payload, err = _http_json(
            url,
            headers={"Authorization": f"Basic {token}"},
        )
        if code == 200 and payload:
            status = _blank(payload.get("status")) or "active"
            friendly = _blank(payload.get("friendly_name"))
            detail = f"Twilio account {status}."
            if friendly:
                detail = f"Twilio connected ({friendly}) — status {status}."
            return _result(
                key="sms",
                label=label,
                kind="sms",
                value=f"Twilio · {sender}",
                status=STATUS_CONNECTED,
                detail=detail,
                required=True,
            )
        if code in {401, 403}:
            return _result(
                key="sms",
                label=label,
                kind="sms",
                value="Twilio",
                status=STATUS_INVALID,
                detail="Twilio rejected the Account SID or Auth Token.",
                required=True,
                problem_fields=["sms_username", "sms_api_secret"],
            )
        return _result(
            key="sms",
            label=label,
            kind="sms",
            value="Twilio",
            status=STATUS_UNREACHABLE,
            detail=(
                f"Could not reach Twilio API (HTTP {code or '—'}): {err[:160]}. "
                "Check your network or Twilio status."
            ),
            required=True,
            problem_fields=["sms_provider", "sms_username"],
        )

    return _result(
        key="sms",
        label=label,
        kind="sms",
        value=provider,
        status=STATUS_INVALID,
        detail=f"Unknown SMS provider: {provider}.",
        required=True,
        problem_fields=["sms_provider"],
    )


def _whatsapp_msisdn(phone: str) -> str:
    digits = _digits_only(phone)
    if digits.startswith("0") and len(digits) == 10:
        return "254" + digits[1:]
    if digits.startswith("254") and len(digits) == 12:
        return digits
    if len(digits) == 9 and not digits.startswith("0"):
        return "254" + digits
    return digits


def verify_whatsapp(values: dict[str, Any]) -> ChannelStatus:
    enabled = _as_bool(values.get("whatsapp_enabled"))
    number = _blank(values.get("whatsapp_business_number"))
    api_on = _as_bool(values.get("whatsapp_api_enabled"))
    provider = _blank(values.get("whatsapp_provider")) or (
        CommunicationSettings.WhatsAppProvider.NONE
    )
    token = _blank(values.get("whatsapp_api_token"))
    phone_id = _blank(values.get("whatsapp_phone_number_id"))
    webhook = _blank(values.get("whatsapp_webhook_url"))
    label = "WhatsApp"

    if not enabled:
        return _result(
            key="whatsapp",
            label=label,
            kind="whatsapp",
            value="",
            status=STATUS_DISABLED,
            detail="WhatsApp channel is turned off.",
        )

    if not number:
        return _result(
            key="whatsapp",
            label=label,
            kind="whatsapp",
            value="",
            status=STATUS_NOT_SET,
            detail="Business WhatsApp number is not set.",
            required=True,
            problem_fields=["whatsapp_business_number"],
        )

    digits = _digits_only(number)
    if not PHONE_RE.match(number) or len(digits) < 9 or len(digits) > 15:
        return _result(
            key="whatsapp",
            label=label,
            kind="whatsapp",
            value=number,
            status=STATUS_INVALID,
            detail="Business WhatsApp number format looks invalid.",
            required=True,
            problem_fields=["whatsapp_business_number"],
        )

    msisdn = _whatsapp_msisdn(number)
    wa_href = f"https://wa.me/{msisdn}"

    if not api_on:
        return _result(
            key="whatsapp",
            label=label,
            kind="whatsapp",
            value=number,
            status=STATUS_CONNECTED,
            detail="Click-to-chat number is valid — Business API not enabled.",
            required=True,
            href=wa_href,
        )

    if webhook and not webhook.lower().startswith("https://"):
        return _result(
            key="whatsapp",
            label=label,
            kind="whatsapp",
            value=number,
            status=STATUS_INVALID,
            detail="Webhook URL must use HTTPS.",
            required=True,
            href=wa_href,
            problem_fields=["whatsapp_webhook_url"],
        )

    if provider in {"", CommunicationSettings.WhatsAppProvider.NONE}:
        return _result(
            key="whatsapp",
            label=label,
            kind="whatsapp",
            value=number,
            status=STATUS_INVALID,
            detail="Choose a WhatsApp API provider.",
            required=True,
            href=wa_href,
            problem_fields=["whatsapp_provider"],
        )

    missing = []
    if not token:
        missing.append("whatsapp_api_token")
    if not phone_id:
        missing.append("whatsapp_phone_number_id")
    if missing:
        return _result(
            key="whatsapp",
            label=label,
            kind="whatsapp",
            value=number,
            status=STATUS_INVALID,
            detail="API token and phone number ID / sender are required.",
            required=True,
            href=wa_href,
            problem_fields=missing,
        )

    if provider == CommunicationSettings.WhatsAppProvider.META:
        url = (
            "https://graph.facebook.com/v19.0/"
            f"{urllib.parse.quote(phone_id)}"
            "?fields=display_phone_number,verified_name,quality_rating"
        )
        code, payload, err = _http_json(
            url,
            headers={"Authorization": f"Bearer {token}"},
        )
        if code == 200 and payload:
            display = _blank(payload.get("display_phone_number")) or phone_id
            name = _blank(payload.get("verified_name"))
            detail = f"Meta Cloud API connected ({display})."
            if name:
                detail = f"Meta Cloud API connected — {name} ({display})."
            return _result(
                key="whatsapp",
                label=label,
                kind="whatsapp",
                value=display,
                status=STATUS_CONNECTED,
                detail=detail,
                required=True,
                href=wa_href,
            )
        if code in {401, 403}:
            return _result(
                key="whatsapp",
                label=label,
                kind="whatsapp",
                value=number,
                status=STATUS_INVALID,
                detail="Meta rejected the access token or phone number ID.",
                required=True,
                href=wa_href,
                problem_fields=["whatsapp_api_token", "whatsapp_phone_number_id"],
            )
        error_msg = ""
        if payload and isinstance(payload.get("error"), dict):
            error_msg = _blank(payload["error"].get("message"))
        return _result(
            key="whatsapp",
            label=label,
            kind="whatsapp",
            value=number,
            status=STATUS_UNREACHABLE,
            detail=(
                error_msg
                or (
                    f"Could not reach Meta Graph API (HTTP {code or '—'}): "
                    f"{err[:160]}"
                )
            ),
            required=True,
            href=wa_href,
            problem_fields=["whatsapp_provider", "whatsapp_phone_number_id"],
        )

    if provider == CommunicationSettings.WhatsAppProvider.TWILIO:
        sender = phone_id
        if not sender.lower().startswith("whatsapp:") and sender.startswith("+"):
            sender = f"whatsapp:{sender}"
        if ":" not in token:
            return _result(
                key="whatsapp",
                label=label,
                kind="whatsapp",
                value=number,
                status=STATUS_INVALID,
                detail="For Twilio WhatsApp, set API token as AccountSID:AuthToken.",
                required=True,
                href=wa_href,
                problem_fields=["whatsapp_api_token"],
            )

        sid, auth = token.split(":", 1)
        sid = sid.strip()
        auth = auth.strip()
        basic = base64.b64encode(f"{sid}:{auth}".encode()).decode()
        url = f"https://api.twilio.com/2010-04-01/Accounts/{urllib.parse.quote(sid)}.json"
        code, payload, err = _http_json(
            url,
            headers={"Authorization": f"Basic {basic}"},
        )
        if code == 200 and payload:
            return _result(
                key="whatsapp",
                label=label,
                kind="whatsapp",
                value=sender,
                status=STATUS_CONNECTED,
                detail=f"Twilio WhatsApp credentials accepted for {sender}.",
                required=True,
                href=wa_href,
            )
        if code in {401, 403}:
            return _result(
                key="whatsapp",
                label=label,
                kind="whatsapp",
                value=number,
                status=STATUS_INVALID,
                detail="Twilio rejected the Account SID or Auth Token.",
                required=True,
                href=wa_href,
                problem_fields=["whatsapp_api_token"],
            )
        return _result(
            key="whatsapp",
            label=label,
            kind="whatsapp",
            value=number,
            status=STATUS_UNREACHABLE,
            detail=(
                f"Could not reach Twilio (HTTP {code or '—'}): {err[:160]}. "
                "Check the API token and network."
            ),
            required=True,
            href=wa_href,
            problem_fields=["whatsapp_api_token", "whatsapp_provider"],
        )

    return _result(
        key="whatsapp",
        label=label,
        kind="whatsapp",
        value=number,
        status=STATUS_INVALID,
        detail=f"Unknown WhatsApp provider: {provider}.",
        required=True,
        href=wa_href,
        problem_fields=["whatsapp_provider"],
    )


def pending_connection_snapshot(setting: CommunicationSettings) -> dict[str, Any]:
    """Placeholders so the page paints immediately; JS runs live verification."""
    channels = []
    specs = (
        ("email", "Email (SMTP)", "email", setting.email_enabled, setting.email_host),
        ("sms", "SMS", "sms", setting.sms_enabled, setting.get_sms_provider_display()),
        (
            "whatsapp",
            "WhatsApp",
            "whatsapp",
            setting.whatsapp_enabled,
            setting.whatsapp_business_number,
        ),
    )
    for key, label, kind, enabled, value in specs:
        value = _blank(value)
        if not enabled:
            status = STATUS_DISABLED
            detail = f"{label} is turned off."
        elif not value or (key == "sms" and setting.sms_provider == "none"):
            status = STATUS_NOT_SET
            detail = f"{label} is not configured yet."
        else:
            status = STATUS_CHECKING
            detail = "Verifying live connection…"
        channels.append(
            _result(
                key=key,
                label=label,
                kind=kind,
                value=value if enabled else "",
                status=status,
                detail=detail,
                required=bool(enabled),
            ).to_dict()
        )

    enabled_count = sum(1 for c in channels if c["status"] != STATUS_DISABLED)
    return {
        "verified_at": "",
        "overall_status": "checking" if enabled_count else "empty",
        "overall_tone": "partial" if enabled_count else "suspended",
        "overall_label": (
            "Verifying configuration…" if enabled_count else "No channels enabled"
        ),
        "overall_detail": (
            "Running live checks against SMTP and provider APIs."
            if enabled_count
            else "Enable Email, SMS, or WhatsApp, then verify."
        ),
        "connected_count": 0,
        "problem_count": 0,
        "not_set_count": sum(1 for c in channels if c["status"] == STATUS_NOT_SET),
        "channel_count": len(channels),
        "problem_locations": [],
        "connection_channels": channels,
        "by_key": {c["key"]: c for c in channels},
    }


def verify_communication_settings(
    setting: CommunicationSettings | None = None,
    *,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Live-check email SMTP, SMS provider APIs, and WhatsApp configuration."""
    setting = setting or CommunicationSettings.get_solo()
    values = merge_overrides(values_from_settings(setting), overrides)

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(verify_email_smtp, values): "email",
            pool.submit(verify_sms_provider, values): "sms",
            pool.submit(verify_whatsapp, values): "whatsapp",
        }
        by_key: dict[str, ChannelStatus] = {}
        for future in as_completed(futures):
            result = future.result()
            by_key[result.key] = result

    order = ("email", "sms", "whatsapp")
    channels = [by_key[key] for key in order if key in by_key]

    connected = sum(
        1 for c in channels if c.status in {STATUS_CONNECTED, STATUS_REACHABLE}
    )
    disabled = sum(1 for c in channels if c.status == STATUS_DISABLED)
    not_set = sum(1 for c in channels if c.status == STATUS_NOT_SET)
    problems = sum(
        1 for c in channels if c.status in {STATUS_INVALID, STATUS_UNREACHABLE}
    )
    required_problems = [
        c
        for c in channels
        if c.required and c.status in {STATUS_NOT_SET, STATUS_INVALID, STATUS_UNREACHABLE}
    ]

    problem_locations: list[dict[str, Any]] = []
    for channel in channels:
        if channel.status not in {
            STATUS_NOT_SET,
            STATUS_INVALID,
            STATUS_UNREACHABLE,
        }:
            continue
        labels = channel.problem_labels or []
        problem_locations.append(
            {
                "channel": channel.key,
                "channel_label": channel.label,
                "status": channel.status,
                "status_label": channel.status_label,
                "detail": channel.detail,
                "fix_hint": channel.fix_hint,
                "fields": list(channel.problem_fields or []),
                "field_labels": labels,
                "panel_id": CHANNEL_PANEL_IDS.get(channel.key, ""),
            }
        )

    if required_problems:
        overall_status = "issues"
        overall_tone = "pending"
        overall_label = "Needs attention"
        bits = []
        for loc in problem_locations:
            if loc["field_labels"]:
                bits.append(
                    f"{loc['channel_label']}: {', '.join(loc['field_labels'])}"
                )
            else:
                bits.append(loc["channel_label"])
        overall_detail = (
            "Problem in "
            + ("; ".join(bits) if bits else "an enabled channel")
            + "."
        )
    elif problems:
        overall_status = "partial"
        overall_tone = "partial"
        overall_label = "Partially configured"
        overall_detail = (
            f"{connected} connected — {problems} channel"
            f"{'s' if problems != 1 else ''} need fixing."
        )
    elif connected and (disabled or not_set):
        overall_status = "partial"
        overall_tone = "partial"
        overall_label = "Partially configured"
        overall_detail = (
            f"{connected} channel{'s' if connected != 1 else ''} verified live."
        )
    elif connected:
        overall_status = "connected"
        overall_tone = "active"
        overall_label = "Configuration healthy"
        overall_detail = f"All enabled channels verified live ({connected})."
    else:
        overall_status = "empty"
        overall_tone = "suspended"
        overall_label = "No channels enabled"
        overall_detail = "Enable Email, SMS, or WhatsApp, save, then verify again."

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
        "problem_locations": problem_locations,
        "connection_channels": [c.to_dict() for c in channels],
        "by_key": {c.key: c.to_dict() for c in channels},
    }
