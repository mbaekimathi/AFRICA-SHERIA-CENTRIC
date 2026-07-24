"""Helpers for creating and serialising client portal notifications."""

from __future__ import annotations

from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from .models import ClientNotification, Invoice


CATEGORY_LABELS = {
    ClientNotification.Category.BILLING: "Finance & Billing",
    ClientNotification.Category.MESSAGE: "Messages",
}


def notify_invoice_issued(invoice: Invoice) -> tuple[ClientNotification, bool]:
    """Notify the client that an invoice was issued to their portal."""
    amount = invoice.total_amount
    try:
        amount_display = f"KES {float(amount):,.2f}"
    except (TypeError, ValueError):
        amount_display = f"KES {amount}"

    return ClientNotification.objects.get_or_create(
        recipient=invoice.client,
        source_key=f"invoice_issued:{invoice.pk}",
        defaults={
            "category": ClientNotification.Category.BILLING,
            "title": f"New invoice: {invoice.invoice_number}",
            "body": (
                f"Amount due: {amount_display}."
                + (
                    f" Due {invoice.due_date:%d %b %Y}."
                    if invoice.due_date
                    else ""
                )
                + " Open Finance & Billing to view or pay."
            ),
            "target_url": reverse(
                "accounts:client_invoice",
                kwargs={"invoice_id": invoice.pk},
            ),
        },
    )


def serialize_client_notification(notification: ClientNotification) -> dict:
    created = timezone.localtime(notification.created_at)
    return {
        "id": notification.pk,
        "category": notification.category,
        "category_label": notification.get_category_display(),
        "title": notification.title,
        "body": notification.body,
        "url": reverse(
            "accounts:client_notification_open",
            kwargs={"notification_id": notification.pk},
        ),
        "is_read": notification.is_read,
        "created_at": created.isoformat(),
        "created_display": created.strftime("%d %b · %H:%M"),
    }


def unread_counts_by_category(client) -> dict[str, int]:
    rows = (
        ClientNotification.objects.filter(recipient=client, is_read=False)
        .values("category")
        .annotate(total=Count("id"))
    )
    counts = {category: 0 for category, _label in ClientNotification.Category.choices}
    for row in rows:
        counts[row["category"]] = row["total"]
    return counts


def client_notifications_payload(client, *, limit: int = 40) -> dict:
    """Build the live-poll payload for the client portal bell."""
    by_category = unread_counts_by_category(client)
    unread_count = sum(by_category.values())

    per_category = max(1, limit // max(1, len(ClientNotification.Category.choices)))
    recent = []
    ordered_groups = []
    for category, label in ClientNotification.Category.choices:
        items_qs = list(
            ClientNotification.objects.filter(
                recipient=client, category=category
            ).order_by("-created_at")[:per_category]
        )
        recent.extend(items_qs)
        ordered_groups.append(
            {
                "category": category,
                "label": CATEGORY_LABELS.get(category, label),
                "page_url": reverse("accounts:client_billing"),
                "unread": by_category.get(category, 0),
                "items": [serialize_client_notification(item) for item in items_qs],
            }
        )

    revision = (
        "|".join(f"{n.pk}:{'1' if n.is_read else '0'}" for n in recent)
        + f"|u:{unread_count}"
    )

    return {
        "unread_count": unread_count,
        "has_unread": unread_count > 0,
        "badges": {},
        "revision": revision,
        "groups": ordered_groups,
    }
