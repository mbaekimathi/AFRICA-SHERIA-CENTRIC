"""Send client email/SMS from the signed-in employee's work identity."""

from __future__ import annotations

import json
import logging
import re
import smtplib
import ssl
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

from .models import CommunicationSettings

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 30
HTTP_TIMEOUT_SECONDS = 20


class OutboundMessageError(Exception):
    """Raised when a client email or SMS cannot be sent."""


def _blank(value) -> str:
    return "" if value is None else str(value).strip()


def _digits_msisdn(phone: str) -> str:
    digits = re.sub(r"\D+", "", phone or "")
    return digits


def employee_work_email(employee) -> str:
    return _blank(getattr(employee, "work_email", None)).lower()


def employee_work_phone(employee) -> str:
    return _blank(getattr(employee, "work_phone", None))


def smtp_connection(setting: CommunicationSettings | None = None):
    """Open an authenticated SMTP session from Communication Settings."""
    setting = setting or CommunicationSettings.get_solo()
    if not setting.email_ready:
        raise OutboundMessageError(
            "Firm email (SMTP) is not configured. Open Communication Settings "
            "and verify the connection."
        )

    host = setting.email_host.strip()
    port = int(setting.email_port or 0)
    user = setting.email_host_user.strip()
    password = setting.email_host_password
    use_tls, use_ssl = CommunicationSettings.smtp_security_for_port(port)

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
        if user:
            if not password:
                raise OutboundMessageError("SMTP password is missing.")
            server.login(user, password)
        return server
    except OutboundMessageError:
        raise
    except smtplib.SMTPAuthenticationError as exc:
        raise OutboundMessageError(
            "SMTP rejected the firm mail credentials. Re-verify Communication Settings."
        ) from exc
    except (smtplib.SMTPException, OSError, TimeoutError) as exc:
        raise OutboundMessageError(f"Could not connect to SMTP: {exc}") from exc


def send_firm_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    setting: CommunicationSettings | None = None,
) -> str:
    """
    Send email from the firm SMTP identity in Communication Settings.

    Returns the From address used. Raises OutboundMessageError on failure.
    """
    setting = setting or CommunicationSettings.get_solo()
    if not setting.email_ready:
        raise OutboundMessageError(
            "Firm email (SMTP) is not configured. Open Communication Settings "
            "and verify the connection."
        )

    recipient = _blank(to_email).lower()
    if not recipient:
        raise OutboundMessageError("No recipient email address was provided.")

    subject_text = _blank(subject)
    body_text = _blank(body)
    if not subject_text:
        raise OutboundMessageError("Enter a subject.")
    if not body_text:
        raise OutboundMessageError("Enter a message.")

    from_email = _blank(setting.email_from_email).lower()
    display_name = _blank(setting.email_from_name) or from_email
    envelope_from = _blank(setting.email_host_user).lower() or from_email

    message = EmailMessage()
    message["Subject"] = subject_text
    message["From"] = f"{display_name} <{from_email}>"
    message["To"] = recipient
    message["Reply-To"] = from_email
    message.set_content(body_text)

    server = None
    try:
        server = smtp_connection(setting)
        server.send_message(message, from_addr=envelope_from, to_addrs=[recipient])
    except OutboundMessageError:
        raise
    except smtplib.SMTPSenderRefused as exc:
        raise OutboundMessageError(
            f"The mail server refused sending as {from_email}."
        ) from exc
    except smtplib.SMTPRecipientsRefused as exc:
        raise OutboundMessageError(
            f"The mail server refused the recipient {recipient}."
        ) from exc
    except (smtplib.SMTPException, OSError, TimeoutError) as exc:
        raise OutboundMessageError(f"Email could not be sent: {exc}") from exc
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                try:
                    server.close()
                except Exception:
                    pass

    logger.info("Firm email sent from=%s to=%s", from_email, recipient)
    return from_email


def send_client_email(
    *,
    employee,
    to_email: str,
    subject: str,
    body: str,
    client_name: str = "",
    setting: CommunicationSettings | None = None,
) -> str:
    """
    Send email as the employee's work address only.

    Returns the From address used. Raises OutboundMessageError on failure.
    """
    work_email = employee_work_email(employee)
    if not work_email:
        raise OutboundMessageError(
            "You need a work email before you can email clients. "
            "Ask a managing partner to create one when approving your account."
        )

    recipient = _blank(to_email).lower()
    if not recipient:
        raise OutboundMessageError("Choose a client with an email address.")

    subject_text = _blank(subject)
    body_text = _blank(body)
    if not subject_text:
        raise OutboundMessageError("Enter a subject.")
    if not body_text:
        raise OutboundMessageError("Enter a message.")

    setting = setting or CommunicationSettings.get_solo()
    display_name = (
        _blank(getattr(employee, "get_full_name", lambda: "")())
        or _blank(setting.email_from_name)
        or work_email
    )

    message = EmailMessage()
    message["Subject"] = subject_text
    message["From"] = f"{display_name} <{work_email}>"
    message["To"] = recipient
    message["Reply-To"] = work_email
    if client_name:
        message["X-Sheria-Client"] = client_name[:120]
    message.set_content(body_text)

    server = None
    try:
        server = smtp_connection(setting)
        server.send_message(message, from_addr=work_email, to_addrs=[recipient])
    except OutboundMessageError:
        raise
    except smtplib.SMTPSenderRefused as exc:
        raise OutboundMessageError(
            f"The mail server refused sending as {work_email}. "
            "Confirm that mailbox exists on the firm domain."
        ) from exc
    except smtplib.SMTPRecipientsRefused as exc:
        raise OutboundMessageError(
            f"The mail server refused the recipient {recipient}."
        ) from exc
    except (smtplib.SMTPException, OSError, TimeoutError) as exc:
        raise OutboundMessageError(f"Email could not be sent: {exc}") from exc
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                try:
                    server.close()
                except Exception:
                    pass

    logger.info(
        "Client email sent by employee=%s from=%s to=%s",
        getattr(employee, "pk", None),
        work_email,
        recipient,
    )
    return work_email


def send_client_sms(
    *,
    employee,
    to_phone: str,
    body: str,
    setting: CommunicationSettings | None = None,
) -> str:
    """
    Send SMS using the employee's work phone as the sending identity.

    Returns the From number/sender used.
    """
    work_phone = employee_work_phone(employee)
    if not work_phone:
        raise OutboundMessageError(
            "You need a work phone number before you can text clients."
        )

    recipient = _digits_msisdn(to_phone)
    if len(recipient) < 9:
        raise OutboundMessageError("Choose a client with a valid phone number.")

    text = _blank(body)
    if not text:
        raise OutboundMessageError("Enter a message.")
    if len(text) > 640:
        raise OutboundMessageError("SMS messages are limited to 640 characters.")

    setting = setting or CommunicationSettings.get_solo()
    if not setting.sms_ready:
        raise OutboundMessageError(
            "Firm SMS is not configured. Open Communication Settings "
            "and verify the SMS provider."
        )

    from_identity = _digits_msisdn(work_phone) or work_phone
    if setting.sms_provider == CommunicationSettings.SmsProvider.TWILIO:
        _send_twilio_sms(setting, to=recipient, body=text, from_number=from_identity)
        sender = from_identity
    elif setting.sms_provider == CommunicationSettings.SmsProvider.AFRICASTALKING:
        # Africa's Talking requires a registered sender ID; the employee's work
        # phone is still required so only provisioned staff can send.
        sender_id = setting.sms_sender_id.strip()
        _send_africastalking_sms(setting, to=recipient, body=text, sender_id=sender_id)
        sender = sender_id or from_identity
    else:
        raise OutboundMessageError("Choose an SMS provider in Communication Settings.")

    logger.info(
        "Client SMS sent by employee=%s from=%s to=%s",
        getattr(employee, "pk", None),
        sender,
        recipient,
    )
    return sender


def _send_africastalking_sms(setting, *, to: str, body: str, sender_id: str) -> None:
    username = setting.sms_username.strip()
    api_key = setting.sms_api_key.strip()
    if not username or not api_key:
        raise OutboundMessageError("Africa's Talking credentials are incomplete.")

    payload = {
        "username": username,
        "to": to if to.startswith("+") else f"+{to}",
        "message": body,
    }
    if sender_id:
        payload["from"] = sender_id

    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.africastalking.com/version1/messaging",
        data=data,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "apiKey": api_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise OutboundMessageError(
            f"Africa's Talking error ({exc.code}): {detail[:200]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise OutboundMessageError(
            f"Could not reach Africa's Talking: {exc.reason}"
        ) from exc

    try:
        result = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        result = {}
    recipients = (
        ((result.get("SMSMessageData") or {}).get("Recipients"))
        if isinstance(result, dict)
        else None
    )
    if isinstance(recipients, list) and recipients:
        status = str(recipients[0].get("status") or "")
        if status.lower() not in {"success", "sent"}:
            raise OutboundMessageError(
                f"Africa's Talking did not accept the SMS ({status})."
            )


def _send_twilio_sms(setting, *, to: str, body: str, from_number: str) -> None:
    sid = setting.sms_username.strip()
    token = setting.sms_api_secret.strip()
    if not sid or not token:
        raise OutboundMessageError("Twilio credentials are incomplete.")

    from_value = from_number if from_number.startswith("+") else f"+{from_number}"
    to_value = to if to.startswith("+") else f"+{to}"
    payload = urllib.parse.urlencode(
        {"To": to_value, "From": from_value, "Body": body}
    ).encode("utf-8")
    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/"
        f"{urllib.parse.quote(sid)}/Messages.json"
    )
    import base64

    basic = base64.b64encode(f"{sid}:{token}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise OutboundMessageError(
            f"Twilio error ({exc.code}): {detail[:200]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise OutboundMessageError(f"Could not reach Twilio: {exc.reason}") from exc
