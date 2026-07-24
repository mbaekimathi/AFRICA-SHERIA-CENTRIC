"""Client portal layout context helpers."""

from django.urls import reverse
from django.utils import timezone

from .appearance import (
    resolve_client_portal_density,
    resolve_client_portal_font,
    resolve_client_portal_theme,
    sync_session_client_appearance,
)
from .client_auth import is_staff_impersonating
from .models import Client, ClientNotification, get_firm_display_name
from .workspace import (
    ICON_BELL,
    ICON_BRIEF,
    ICON_CALENDAR,
    ICON_DOC,
    ICON_FINANCE,
    ICON_HOME,
    ICON_LOGOUT,
    ICON_MESSAGE,
    ICON_SETTINGS,
    ICON_USERS,
    mark_session_start,
)


def client_home_url(client: Client) -> str:
    if client.status == Client.Status.PENDING_ONBOARDING:
        return reverse("accounts:client_onboarding")
    if client.status == Client.Status.PENDING_APPROVAL:
        return reverse("accounts:client_pending")
    if client.status == Client.Status.ACTIVE:
        return reverse("accounts:client_dashboard")
    return reverse("accounts:client_login")


def client_portal_context(request, client, *, page_title="My profile", active="profile"):
    home_url = client_home_url(client)
    billing_url = reverse("accounts:client_billing")
    matters_url = reverse("accounts:client_matters")
    documents_url = reverse("accounts:client_documents")
    messages_url = reverse("accounts:client_messages")
    reminders_url = reverse("accounts:client_reminders")
    calendar_url = reverse("accounts:client_calendar")
    settings_url = reverse("accounts:client_settings")
    theme_url = reverse("accounts:client_theme_settings")

    hour = timezone.localtime().hour
    if hour < 12:
        tod = "Good morning"
    elif hour < 17:
        tod = "Good afternoon"
    else:
        tod = "Good evening"
    greeting_name = client.first_name or client.company_name or "there"
    greeting = f"{tod}, {greeting_name}"

    if not request.session.get("session_started_at"):
        mark_session_start(request)

    # Keep appearance session snapshot current for live theme application.
    sync_session_client_appearance(request, client)

    page_nav_items = [
        {
            "label": "My profile",
            "url": home_url,
            "icon": ICON_USERS,
            "active": active in {"profile", "dashboard"},
        },
        {
            "label": "My matters",
            "url": matters_url,
            "icon": ICON_BRIEF,
            "active": active == "matters",
        },
        {
            "label": "Documents",
            "url": documents_url,
            "icon": ICON_DOC,
            "active": active == "documents",
        },
        {
            "label": "Finance & Billing",
            "url": billing_url,
            "icon": ICON_FINANCE,
            "active": active in {"billing", "finance-billing"},
        },
    ]

    utility_items = [
        {
            "label": "Messages",
            "url": messages_url,
            "icon": ICON_MESSAGE,
            "active": active == "messages",
        },
        {
            "label": "Reminders",
            "url": reminders_url,
            "icon": ICON_BELL,
            "active": active == "reminders",
        },
        {
            "label": "Calendar",
            "url": calendar_url,
            "icon": ICON_CALENDAR,
            "active": active == "calendar",
        },
    ]

    unread_count = ClientNotification.objects.filter(
        recipient=client, is_read=False
    ).count()

    crumb_parts = [
        {"label": "Client portal", "url": home_url},
        {"label": page_title, "url": request.path},
    ]

    staff_impersonating = is_staff_impersonating(request)
    theme = resolve_client_portal_theme(client, request)
    ui_font = resolve_client_portal_font(client, request)
    ui_density = resolve_client_portal_density(client, request)

    return {
        "client": client,
        "theme": theme,
        "ui_font": ui_font,
        "ui_density": ui_density,
        "page_title": page_title,
        "role_label": "Client",
        "session_greeting": greeting,
        "welcome_headline": "Client portal",
        "welcome_copy": (
            "Everything here is limited to your account — your matters, "
            "documents, billing, and schedule with the firm."
        ),
        "dashboard_url": home_url,
        "dashboard_active": active == "dashboard",
        "settings_url": settings_url,
        "settings_active": active == "settings",
        "theme_settings_url": theme_url,
        "theme_settings_active": active == "theme-settings",
        "billing_url": billing_url,
        "page_nav_items": page_nav_items,
        "utility_items": utility_items,
        "icon_home": ICON_HOME,
        "icon_bell": ICON_BELL,
        "icon_brief": ICON_BRIEF,
        "icon_doc": ICON_DOC,
        "icon_finance": ICON_FINANCE,
        "icon_settings": ICON_SETTINGS,
        "icon_logout": ICON_LOGOUT,
        "session_started_at": request.session.get("session_started_at"),
        "server_now": timezone.localtime().isoformat(),
        "crumb_parts": crumb_parts,
        "sign_in_method": (
            "Google"
            if client.google_sub
            else "Email & password"
            if client.password
            else "Not set"
        ),
        "firm_name": get_firm_display_name(),
        "notifications_url": reverse("accounts:client_notifications"),
        "notifications_mark_all_url": reverse(
            "accounts:client_notifications_mark_all_read"
        ),
        "notification_unread_count": unread_count,
        "notification_sound_enabled": True,
        "notification_sound_volume": 70,
        "notification_browser_enabled": True,
        "staff_impersonating": staff_impersonating,
        "staff_exit_portal_url": reverse("accounts:client_logout"),
    }
