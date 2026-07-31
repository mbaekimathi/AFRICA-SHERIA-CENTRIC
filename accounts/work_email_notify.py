"""Notify employees when a firm work mailbox is provisioned."""

from __future__ import annotations

import logging

from django.core import signing
from django.urls import reverse

from .cpanel_mail import CpanelMailError
from .models import CommunicationSettings, Employee
from .outbound_messaging import OutboundMessageError, send_firm_email

logger = logging.getLogger(__name__)

SET_PASSWORD_SALT = "work-email-set-password"
SET_PASSWORD_MAX_AGE_SECONDS = 60 * 60 * 24 * 7  # 7 days
MIN_PASSWORD_LENGTH = 6


def make_set_password_token(*, employee_id: int, work_email: str) -> str:
    return signing.dumps(
        {"e": int(employee_id), "m": (work_email or "").strip().lower()},
        salt=SET_PASSWORD_SALT,
    )


def load_set_password_token(token: str) -> dict:
    payload = signing.loads(
        token,
        salt=SET_PASSWORD_SALT,
        max_age=SET_PASSWORD_MAX_AGE_SECONDS,
    )
    if not isinstance(payload, dict):
        raise signing.BadSignature("Invalid token payload.")
    employee_id = payload.get("e")
    work_email = (payload.get("m") or "").strip().lower()
    if not employee_id or not work_email:
        raise signing.BadSignature("Incomplete token payload.")
    return {"employee_id": int(employee_id), "work_email": work_email}


def set_password_path(token: str) -> str:
    return reverse("accounts:set_work_email_password", kwargs={"token": token})


def webmail_url_for_domain(domain: str) -> str:
    host = (domain or "").strip().lstrip("@").lower()
    if not host:
        return ""
    return f"https://mail.{host}"


def validate_work_email_password(password: str) -> str:
    """Enforce the minimum mailbox password rule. Returns the cleaned password."""
    value = password or ""
    if len(value) < MIN_PASSWORD_LENGTH:
        raise CpanelMailError(
            f"Choose a password of at least {MIN_PASSWORD_LENGTH} "
            "characters or digits."
        )
    return value


def build_credentials_email(
    *,
    employee: Employee,
    work_email: str,
    password: str,
    set_password_url: str,
    domain: str = "",
) -> tuple[str, str]:
    name = employee.get_full_name() or "there"
    domain = (domain or work_email.partition("@")[2]).strip().lower()
    webmail = webmail_url_for_domain(domain)
    subject = f"Your Sheria Centric work email — {work_email}"
    lines = [
        f"Hello {name},",
        "",
        "Your firm work email has been created.",
        "",
        f"Work email: {work_email}",
        f"Temporary password: {password}",
        "",
        "Please change this password as soon as you can using this secure link "
        f"(valid for 7 days):",
        set_password_url,
        "",
        "After you set a new password you can sign into webmail or any mail app "
        "with these settings:",
        f"  Username: {work_email}",
        f"  Incoming / outgoing server: mail.{domain}" if domain else "",
        "  IMAP: 993 · POP3: 995 · SMTP: 465 (SSL/TLS)",
    ]
    if webmail:
        lines.extend(["", f"Webmail: {webmail}"])
    lines.extend(
        [
            "",
            "Do not share this email. If you did not expect a work mailbox, "
            "contact your managing partner.",
            "",
            "— Sheria Centric",
        ]
    )
    body = "\n".join(line for line in lines if line is not None)
    return subject, body


def notify_work_email_created(
    request,
    employee: Employee,
    *,
    work_email: str,
    password: str,
    setting: CommunicationSettings | None = None,
) -> dict:
    """
    Email credentials to the employee's personal address.

    Returns a status dict for the approver modal. Never raises for SMTP
    failures — approval already succeeded and the password is still shown once.
    """
    setting = setting or CommunicationSettings.get_solo()
    personal = (employee.personal_email or "").strip().lower()
    token = make_set_password_token(employee_id=employee.pk, work_email=work_email)
    path = set_password_path(token)
    set_password_url = request.build_absolute_uri(path)
    domain = (setting.work_email_domain or work_email.partition("@")[2]).strip()

    result = {
        "personal_email": personal,
        "email_sent": False,
        "email_error": "",
        "set_password_url": set_password_url,
    }
    if not personal:
        result["email_error"] = "No personal email on the employee record."
        return result

    subject, body = build_credentials_email(
        employee=employee,
        work_email=work_email,
        password=password,
        set_password_url=set_password_url,
        domain=domain,
    )
    try:
        send_firm_email(
            to_email=personal,
            subject=subject,
            body=body,
            setting=setting,
        )
    except OutboundMessageError as exc:
        logger.warning(
            "Could not email work mailbox credentials to %s: %s",
            personal,
            exc,
        )
        result["email_error"] = str(exc)
        return result

    result["email_sent"] = True
    return result


__all__ = [
    "MIN_PASSWORD_LENGTH",
    "SET_PASSWORD_MAX_AGE_SECONDS",
    "SET_PASSWORD_SALT",
    "build_credentials_email",
    "load_set_password_token",
    "make_set_password_token",
    "notify_work_email_created",
    "set_password_path",
    "validate_work_email_password",
    "webmail_url_for_domain",
]
