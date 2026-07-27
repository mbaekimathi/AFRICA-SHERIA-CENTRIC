"""WhatsApp Business Cloud API helpers (send + webhook ingest)."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib import error, request

from django.utils import timezone

from .utils import normalize_whatsapp_msisdn

logger = logging.getLogger(__name__)

WHATSAPP_WEBHOOK_PATH = "/integrations/whatsapp/webhook/"
META_GRAPH_VERSION = "v19.0"
META_GRAPH_BASE = f"https://graph.facebook.com/{META_GRAPH_VERSION}"


class WhatsAppError(Exception):
    """Raised when a WhatsApp API operation cannot complete."""


def _communication_settings():
    try:
        from .models import CommunicationSettings

        return CommunicationSettings.get_solo()
    except Exception:
        return None


def is_whatsapp_api_ready(setting=None) -> bool:
    setting = setting if setting is not None else _communication_settings()
    return bool(setting and setting.whatsapp_api_ready)


def find_client_for_msisdn(msisdn: str):
    """Best-effort match a Client by normalized phone digits."""
    from .models import Client

    digits = normalize_whatsapp_msisdn(msisdn)
    if not digits:
        return None

    candidates = Client.objects.exclude(phone="").only("id", "phone", "first_name", "last_name", "company_name")
    for client in candidates.iterator(chunk_size=200):
        if normalize_whatsapp_msisdn(client.phone) == digits:
            return client

    # Suffix match for numbers stored without country code
    suffix = digits[-9:] if len(digits) >= 9 else digits
    for client in candidates.filter(phone__icontains=suffix).iterator(chunk_size=100):
        if normalize_whatsapp_msisdn(client.phone).endswith(suffix):
            return client
    return None


def get_or_create_conversation(*, msisdn: str, display_name: str = ""):
    from .models import WhatsAppConversation

    digits = normalize_whatsapp_msisdn(msisdn)
    if not digits:
        raise WhatsAppError("A valid phone number is required.")

    conversation, created = WhatsAppConversation.objects.get_or_create(
        msisdn=digits,
        defaults={
            "display_name": (display_name or "")[:180],
            "client": find_client_for_msisdn(digits),
        },
    )
    updates = []
    if display_name and not conversation.display_name:
        conversation.display_name = display_name[:180]
        updates.append("display_name")
    if conversation.client_id is None:
        client = find_client_for_msisdn(digits)
        if client is not None:
            conversation.client = client
            updates.append("client")
    if updates:
        conversation.save(update_fields=updates + ["updated_at"])
    return conversation, created


def _meta_send_text(*, phone_number_id: str, token: str, to: str, body: str) -> dict:
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{META_GRAPH_BASE}/{phone_number_id}/messages",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.warning("WhatsApp Meta send failed status=%s body=%s", exc.code, detail)
        raise WhatsAppError(f"Meta API error ({exc.code}): {detail[:200]}") from exc
    except error.URLError as exc:
        raise WhatsAppError(f"Could not reach Meta API: {exc.reason}") from exc


def send_text(*, to: str, body: str, sent_by=None):
    """
    Send an outbound WhatsApp text via Meta Cloud API and persist the message.
    """
    from .models import WhatsAppMessage

    setting = _communication_settings()
    if not is_whatsapp_api_ready(setting):
        raise WhatsAppError(
            "WhatsApp Business API is not configured. "
            "Enable it under Communication Settings."
        )
    if setting.whatsapp_provider != setting.WhatsAppProvider.META:
        raise WhatsAppError(
            "Only Meta Cloud API sending is implemented in this release."
        )

    text = (body or "").strip()
    if not text:
        raise WhatsAppError("Message text is required.")

    msisdn = normalize_whatsapp_msisdn(to)
    if not msisdn:
        raise WhatsAppError("A valid recipient phone number is required.")

    conversation, _ = get_or_create_conversation(msisdn=msisdn)
    message = WhatsAppMessage.objects.create(
        conversation=conversation,
        direction=WhatsAppMessage.Direction.OUTBOUND,
        body=text,
        status=WhatsAppMessage.Status.QUEUED,
        sent_by=sent_by,
    )

    try:
        result = _meta_send_text(
            phone_number_id=setting.whatsapp_phone_number_id.strip(),
            token=setting.whatsapp_api_token.strip(),
            to=msisdn,
            body=text,
        )
    except WhatsAppError as exc:
        message.status = WhatsAppMessage.Status.FAILED
        message.error_message = str(exc)[:255]
        message.save(update_fields=["status", "error_message", "updated_at"])
        raise

    messages = (result or {}).get("messages") or []
    wamid = ""
    if messages:
        wamid = str(messages[0].get("id") or "")
    message.provider_message_id = wamid[:120]
    message.status = WhatsAppMessage.Status.SENT
    message.save(
        update_fields=["provider_message_id", "status", "updated_at"]
    )

    conversation.last_message_at = timezone.now()
    conversation.last_message_preview = text[:255]
    conversation.save(
        update_fields=["last_message_at", "last_message_preview", "updated_at"]
    )
    return message


def verify_webhook_challenge(params: dict[str, Any], setting=None) -> str | None:
    """
    Handle Meta hub.challenge verification.
    Returns the challenge string when valid, else None.
    """
    setting = setting if setting is not None else _communication_settings()
    mode = (params.get("hub.mode") or params.get("hub_mode") or "").strip()
    token = (
        params.get("hub.verify_token") or params.get("hub_verify_token") or ""
    ).strip()
    challenge = (
        params.get("hub.challenge") or params.get("hub_challenge") or ""
    ).strip()
    expected = (
        (setting.whatsapp_webhook_verify_token if setting else "") or ""
    ).strip()
    if mode == "subscribe" and expected and token == expected and challenge:
        return challenge
    return None


def _status_from_meta(value: str) -> str | None:
    from .models import WhatsAppMessage

    mapping = {
        "sent": WhatsAppMessage.Status.SENT,
        "delivered": WhatsAppMessage.Status.DELIVERED,
        "read": WhatsAppMessage.Status.READ,
        "failed": WhatsAppMessage.Status.FAILED,
    }
    return mapping.get((value or "").lower())


def process_webhook_payload(payload: dict[str, Any]) -> dict[str, int]:
    """
    Ingest Meta Cloud API webhook notifications.
    Returns counts of created/updated rows.
    """
    from .models import WhatsAppMessage

    created = 0
    updated = 0
    entries = (payload or {}).get("entry") or []
    for entry in entries:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            contacts = {
                str(c.get("wa_id") or ""): (c.get("profile") or {}).get("name") or ""
                for c in (value.get("contacts") or [])
            }

            for status in value.get("statuses") or []:
                wamid = str(status.get("id") or "")
                if not wamid:
                    continue
                new_status = _status_from_meta(str(status.get("status") or ""))
                if not new_status:
                    continue
                qs = WhatsAppMessage.objects.filter(provider_message_id=wamid)
                msg = qs.first()
                if not msg:
                    continue
                msg.status = new_status
                errors = status.get("errors") or []
                if errors:
                    err = errors[0]
                    msg.error_message = str(
                        err.get("title") or err.get("message") or err
                    )[:255]
                msg.save(update_fields=["status", "error_message", "updated_at"])
                updated += 1

            for inbound in value.get("messages") or []:
                from_msisdn = str(inbound.get("from") or "")
                wamid = str(inbound.get("id") or "")
                if not from_msisdn:
                    continue
                if wamid and WhatsAppMessage.objects.filter(
                    provider_message_id=wamid
                ).exists():
                    continue

                msg_type = (inbound.get("type") or "text").lower()
                body = ""
                if msg_type == "text":
                    body = ((inbound.get("text") or {}).get("body") or "").strip()
                elif msg_type == "button":
                    body = ((inbound.get("button") or {}).get("text") or "").strip()
                elif msg_type == "interactive":
                    interactive = inbound.get("interactive") or {}
                    body = (
                        ((interactive.get("button_reply") or {}).get("title"))
                        or ((interactive.get("list_reply") or {}).get("title"))
                        or ""
                    ).strip()
                else:
                    body = f"[{msg_type} message]"

                display = contacts.get(from_msisdn, "")
                conversation, _ = get_or_create_conversation(
                    msisdn=from_msisdn,
                    display_name=display,
                )
                WhatsAppMessage.objects.create(
                    conversation=conversation,
                    direction=WhatsAppMessage.Direction.INBOUND,
                    body=body,
                    status=WhatsAppMessage.Status.RECEIVED,
                    provider_message_id=wamid[:120],
                )
                conversation.unread_count = (conversation.unread_count or 0) + 1
                conversation.last_message_at = timezone.now()
                conversation.last_message_preview = (body or f"[{msg_type}]")[:255]
                if display and not conversation.display_name:
                    conversation.display_name = display[:180]
                conversation.save(
                    update_fields=[
                        "unread_count",
                        "last_message_at",
                        "last_message_preview",
                        "display_name",
                        "updated_at",
                    ]
                )
                created += 1

    return {"created": created, "updated": updated}


def mark_conversation_read(conversation) -> None:
    if conversation.unread_count:
        conversation.unread_count = 0
        conversation.save(update_fields=["unread_count", "updated_at"])


def conversation_poll_payload(*, after_id: int = 0, conversation_id: int | None = None):
    """Lightweight JSON payload for inbox polling."""
    from .models import WhatsAppConversation, WhatsAppMessage

    conversations = list(
        WhatsAppConversation.objects.select_related("client").order_by(
            "-last_message_at", "-id"
        )[:80]
    )
    thread_messages = []
    if conversation_id:
        qs = WhatsAppMessage.objects.filter(conversation_id=conversation_id)
        if after_id:
            qs = qs.filter(id__gt=after_id)
        thread_messages = [
            {
                "id": m.id,
                "direction": m.direction,
                "body": m.body,
                "status": m.status,
                "created_at": m.created_at.isoformat(),
            }
            for m in qs.order_by("id")[:200]
        ]

    return {
        "conversations": [
            {
                "id": c.id,
                "title": c.title,
                "msisdn": c.msisdn,
                "unread_count": c.unread_count,
                "preview": c.last_message_preview,
                "last_message_at": (
                    c.last_message_at.isoformat() if c.last_message_at else ""
                ),
            }
            for c in conversations
        ],
        "messages": thread_messages,
        "unread_total": sum(c.unread_count for c in conversations),
    }
