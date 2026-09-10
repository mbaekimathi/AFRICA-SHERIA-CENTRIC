"""Notify employees when a firm work mailbox is provisioned."""

from __future__ import annotations

import html
import logging

from django.core import signing
from django.urls import reverse

from .cpanel_mail import CpanelMailError
from .models import CommunicationSettings, Employee, get_firm_display_name
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


def _credentials_plain_body(
    *,
    name: str,
    intro: str,
    work_email: str,
    password: str,
    set_password_url: str,
    domain: str,
    webmail: str,
) -> str:
    lines = [
        f"Hello {name},",
        "",
        intro,
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
    return "\n".join(line for line in lines if line is not None)


def _credentials_html_body(
    *,
    name: str,
    intro: str,
    work_email: str,
    password: str,
    set_password_url: str,
    domain: str,
    webmail: str,
    firm_name: str,
) -> str:
    safe_name = html.escape(name)
    safe_intro = html.escape(intro)
    safe_email = html.escape(work_email)
    safe_password = html.escape(password)
    safe_url = html.escape(set_password_url, quote=True)
    safe_domain = html.escape(domain)
    safe_webmail = html.escape(webmail, quote=True) if webmail else ""
    safe_webmail_label = html.escape(webmail) if webmail else ""
    safe_firm = html.escape(firm_name or "Your firm")

    mail_server_row = ""
    if domain:
        mail_server_row = f"""
                          <tr>
                            <td style="padding:10px 0 0;font-size:13px;line-height:1.45;color:#5c6370;">
                              Server
                            </td>
                            <td style="padding:10px 0 0;font-size:14px;line-height:1.45;color:#12141a;text-align:right;font-family:'IBM Plex Mono',Consolas,Monaco,monospace;">
                              mail.{safe_domain}
                            </td>
                          </tr>"""

    webmail_block = ""
    if webmail:
        webmail_block = f"""
                      <tr>
                        <td style="padding:0 32px 8px;">
                          <p style="margin:0;font-size:14px;line-height:1.5;color:#5c6370;">
                            Webmail:
                            <a href="{safe_webmail}" style="color:#1a1d26;font-weight:600;text-decoration:underline;">
                              {safe_webmail_label}
                            </a>
                          </p>
                        </td>
                      </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>Your work email</title>
</head>
<body style="margin:0;padding:0;background:#eef0f3;-webkit-font-smoothing:antialiased;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#eef0f3;">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;background:#ffffff;border:1px solid #e2e5ea;border-radius:12px;overflow:hidden;">
          <tr>
            <td style="height:4px;background:#fca311;font-size:0;line-height:0;">&nbsp;</td>
          </tr>
          <tr>
            <td style="padding:28px 32px 8px;font-family:'IBM Plex Sans','Segoe UI',Helvetica,Arial,sans-serif;">
              <p style="margin:0;font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:#8a9099;font-weight:600;">
                {safe_firm}
              </p>
              <h1 style="margin:10px 0 0;font-family:Georgia,'Times New Roman',serif;font-size:24px;line-height:1.3;font-weight:600;color:#12141a;">
                Your work email is ready
              </h1>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 32px 0;font-family:'IBM Plex Sans','Segoe UI',Helvetica,Arial,sans-serif;font-size:15px;line-height:1.6;color:#3d4450;">
              <p style="margin:0 0 8px;">Hello {safe_name},</p>
              <p style="margin:0;">{safe_intro}</p>
            </td>
          </tr>
          <tr>
            <td style="padding:24px 32px 8px;font-family:'IBM Plex Sans','Segoe UI',Helvetica,Arial,sans-serif;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f7f8fa;border:1px solid #e8eaee;border-radius:10px;">
                <tr>
                  <td style="padding:18px 20px;">
                    <p style="margin:0 0 4px;font-size:12px;letter-spacing:0.04em;text-transform:uppercase;color:#8a9099;font-weight:600;">
                      Work email
                    </p>
                    <p style="margin:0 0 16px;font-size:16px;line-height:1.4;color:#12141a;font-family:'IBM Plex Mono',Consolas,Monaco,monospace;word-break:break-all;">
                      {safe_email}
                    </p>
                    <p style="margin:0 0 4px;font-size:12px;letter-spacing:0.04em;text-transform:uppercase;color:#8a9099;font-weight:600;">
                      Temporary password
                    </p>
                    <p style="margin:0;font-size:16px;line-height:1.4;color:#12141a;font-family:'IBM Plex Mono',Consolas,Monaco,monospace;word-break:break-all;">
                      {safe_password}
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:24px 32px 8px;font-family:'IBM Plex Sans','Segoe UI',Helvetica,Arial,sans-serif;">
              <a href="{safe_url}" style="display:inline-block;padding:13px 28px;background:#12141a;color:#ffffff;font-size:15px;font-weight:600;line-height:1.2;text-decoration:none;border-radius:8px;">
                Set your password
              </a>
              <p style="margin:12px 0 0;font-size:13px;line-height:1.45;color:#8a9099;">
                This link expires in 7 days.
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:28px 32px 8px;font-family:'IBM Plex Sans','Segoe UI',Helvetica,Arial,sans-serif;">
              <p style="margin:0 0 12px;font-size:12px;letter-spacing:0.06em;text-transform:uppercase;color:#8a9099;font-weight:600;">
                Mail app settings
              </p>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-top:1px solid #e8eaee;">
                <tr>
                  <td style="padding:12px 0 0;font-size:13px;line-height:1.45;color:#5c6370;">
                    Username
                  </td>
                  <td style="padding:12px 0 0;font-size:14px;line-height:1.45;color:#12141a;text-align:right;font-family:'IBM Plex Mono',Consolas,Monaco,monospace;word-break:break-all;">
                    {safe_email}
                  </td>
                </tr>
                {mail_server_row}
                <tr>
                  <td style="padding:10px 0 0;font-size:13px;line-height:1.45;color:#5c6370;">
                    Ports
                  </td>
                  <td style="padding:10px 0 0;font-size:14px;line-height:1.45;color:#12141a;text-align:right;">
                    IMAP 993 · POP3 995 · SMTP 465
                  </td>
                </tr>
                <tr>
                  <td colspan="2" style="padding:8px 0 0;font-size:12px;line-height:1.45;color:#8a9099;text-align:right;">
                    SSL/TLS
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          {webmail_block}
          <tr>
            <td style="padding:24px 32px 28px;font-family:'IBM Plex Sans','Segoe UI',Helvetica,Arial,sans-serif;border-top:1px solid #e8eaee;">
              <p style="margin:0;font-size:12px;line-height:1.55;color:#8a9099;">
                Do not share this email. If you did not expect a work mailbox,
                contact your managing partner.
              </p>
              <p style="margin:14px 0 0;font-size:12px;line-height:1.45;color:#8a9099;">
                — Sheria Centric
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def build_credentials_email(
    *,
    employee: Employee,
    work_email: str,
    password: str,
    set_password_url: str,
    domain: str = "",
    reused: bool = False,
    firm_name: str = "",
) -> tuple[str, str, str]:
    name = employee.get_full_name() or "there"
    domain = (domain or work_email.partition("@")[2]).strip().lower()
    webmail = webmail_url_for_domain(domain)
    subject = f"Your Sheria Centric work email — {work_email}"
    intro = (
        "Your firm work email has been allocated to you."
        if reused
        else "Your firm work email has been created."
    )
    brand = (firm_name or "").strip() or get_firm_display_name() or "Your firm"
    body = _credentials_plain_body(
        name=name,
        intro=intro,
        work_email=work_email,
        password=password,
        set_password_url=set_password_url,
        domain=domain,
        webmail=webmail,
    )
    html_body = _credentials_html_body(
        name=name,
        intro=intro,
        work_email=work_email,
        password=password,
        set_password_url=set_password_url,
        domain=domain,
        webmail=webmail,
        firm_name=brand,
    )
    return subject, body, html_body


def notify_work_email_created(
    request,
    employee: Employee,
    *,
    work_email: str,
    password: str,
    setting: CommunicationSettings | None = None,
    reused: bool = False,
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

    firm_name = (setting.email_from_name or "").strip() or get_firm_display_name()
    subject, body, html_body = build_credentials_email(
        employee=employee,
        work_email=work_email,
        password=password,
        set_password_url=set_password_url,
        domain=domain,
        reused=reused,
        firm_name=firm_name,
    )
    try:
        send_firm_email(
            to_email=personal,
            subject=subject,
            body=body,
            html_body=html_body,
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


def _status_plain_body(*, name: str, paragraphs: list[str]) -> str:
    lines = [f"Hello {name},", ""]
    for paragraph in paragraphs:
        lines.append(paragraph)
        lines.append("")
    lines.extend(
        [
            "If you have questions, contact your managing partner.",
            "",
            "— Sheria Centric",
        ]
    )
    return "\n".join(lines)


def _status_html_body(*, name: str, paragraphs: list[str], firm_name: str) -> str:
    safe_name = html.escape(name)
    safe_brand = html.escape(firm_name)
    body_blocks = "".join(
        f'<p style="margin:0 0 14px;font-size:15px;line-height:1.55;color:#2a2f36;">'
        f"{html.escape(paragraph)}</p>"
        for paragraph in paragraphs
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Work email update</title></head>
<body style="margin:0;padding:0;background:#f4f6f8;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f6f8;padding:28px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="560" cellspacing="0" cellpadding="0" style="max-width:560px;width:100%;background:#ffffff;border:1px solid #e8eaee;border-radius:12px;">
          <tr>
            <td style="padding:28px 32px 8px;font-family:'IBM Plex Sans','Segoe UI',Helvetica,Arial,sans-serif;">
              <p style="margin:0 0 18px;font-size:15px;line-height:1.55;color:#2a2f36;">
                Hello {safe_name},
              </p>
              {body_blocks}
            </td>
          </tr>
          <tr>
            <td style="padding:8px 32px 28px;font-family:'IBM Plex Sans','Segoe UI',Helvetica,Arial,sans-serif;border-top:1px solid #e8eaee;">
              <p style="margin:16px 0 0;font-size:12px;line-height:1.55;color:#8a9099;">
                If you have questions, contact your managing partner.
              </p>
              <p style="margin:14px 0 0;font-size:12px;line-height:1.45;color:#8a9099;">
                — {safe_brand}
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def notify_work_email_suspended(
    employee: Employee,
    *,
    work_email: str,
    setting: CommunicationSettings | None = None,
    mailbox_suspended: bool = True,
) -> dict:
    """Email the employee's personal address that their work mailbox is suspended."""
    setting = setting or CommunicationSettings.get_solo()
    personal = (employee.personal_email or "").strip().lower()
    result = {
        "personal_email": personal,
        "email_sent": False,
        "email_error": "",
    }
    if not personal:
        result["email_error"] = "No personal email on the employee record."
        return result

    name = employee.get_full_name() or "there"
    address = (work_email or "").strip().lower()
    firm_name = (setting.email_from_name or "").strip() or get_firm_display_name()
    brand = firm_name or "Your firm"
    if mailbox_suspended and address:
        subject = f"Your work email has been suspended — {address}"
        paragraphs = [
            "Your Sheria Centric staff account has been suspended.",
            (
                f"Your work email ({address}) has also been suspended. "
                "You cannot sign in to webmail or send mail from that address "
                "until your account is restored."
            ),
            "Incoming mail may still be delivered and will be available again "
            "when access is restored.",
        ]
    elif address:
        subject = f"Your staff account has been suspended — {address}"
        paragraphs = [
            "Your Sheria Centric staff account has been suspended.",
            (
                f"Your work email ({address}) could not be suspended on the "
                "mail server automatically. Do not use that mailbox until "
                "your managing partner confirms access."
            ),
        ]
    else:
        subject = "Your Sheria Centric staff account has been suspended"
        paragraphs = [
            "Your Sheria Centric staff account has been suspended.",
            "You cannot sign in until your managing partner restores access.",
        ]

    body = _status_plain_body(name=name, paragraphs=paragraphs)
    html_body = _status_html_body(
        name=name, paragraphs=paragraphs, firm_name=brand
    )
    try:
        send_firm_email(
            to_email=personal,
            subject=subject,
            body=body,
            html_body=html_body,
            setting=setting,
        )
    except OutboundMessageError as exc:
        logger.warning(
            "Could not email work-email suspension notice to %s: %s",
            personal,
            exc,
        )
        result["email_error"] = str(exc)
        return result

    result["email_sent"] = True
    return result


def notify_work_email_restored(
    employee: Employee,
    *,
    work_email: str,
    setting: CommunicationSettings | None = None,
    mailbox_restored: bool = True,
) -> dict:
    """Email the employee's personal address that their work mailbox is active again."""
    setting = setting or CommunicationSettings.get_solo()
    personal = (employee.personal_email or "").strip().lower()
    result = {
        "personal_email": personal,
        "email_sent": False,
        "email_error": "",
    }
    if not personal:
        result["email_error"] = "No personal email on the employee record."
        return result

    name = employee.get_full_name() or "there"
    address = (work_email or "").strip().lower()
    firm_name = (setting.email_from_name or "").strip() or get_firm_display_name()
    brand = firm_name or "Your firm"
    if not address:
        result["email_error"] = "No work email on the employee record."
        return result

    if mailbox_restored:
        subject = f"Your work email has been restored — {address}"
        paragraphs = [
            "Your Sheria Centric staff account is active again.",
            (
                f"Your work email ({address}) login has been restored. "
                "You can sign in to webmail and reconnect the mailbox in Messages."
            ),
        ]
    else:
        subject = f"Your staff account has been restored — {address}"
        paragraphs = [
            "Your Sheria Centric staff account is active again.",
            (
                f"Your work email ({address}) could not be restored on the "
                "mail server automatically. Ask your managing partner to "
                "confirm mailbox access."
            ),
        ]

    body = _status_plain_body(name=name, paragraphs=paragraphs)
    html_body = _status_html_body(
        name=name, paragraphs=paragraphs, firm_name=brand
    )
    try:
        send_firm_email(
            to_email=personal,
            subject=subject,
            body=body,
            html_body=html_body,
            setting=setting,
        )
    except OutboundMessageError as exc:
        logger.warning(
            "Could not email work-email restore notice to %s: %s",
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
    "notify_work_email_restored",
    "notify_work_email_suspended",
    "set_password_path",
    "validate_work_email_password",
    "webmail_url_for_domain",
]
