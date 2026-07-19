"""Client portal layout context helpers."""

from django.urls import reverse
from django.utils import timezone

from .models import Client, get_firm_display_name
from .workspace import (
    ICON_BELL,
    ICON_BRIEF,
    ICON_CALENDAR,
    ICON_DOC,
    ICON_HOME,
    ICON_LOGOUT,
    ICON_MESSAGE,
    ICON_SCALE,
    ICON_SETTINGS,
    ICON_TASK,
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

    page_nav_items = [
        {
            "label": "My profile",
            "url": home_url,
            "icon": ICON_USERS,
            "active": active == "profile",
        },
        {
            "label": "My matters",
            "url": home_url,
            "icon": ICON_BRIEF,
            "active": active == "matters",
            "disabled": True,
        },
        {
            "label": "Documents",
            "url": home_url,
            "icon": ICON_DOC,
            "active": active == "documents",
            "disabled": True,
        },
        {
            "label": "Billing",
            "url": home_url,
            "icon": ICON_SCALE,
            "active": active == "billing",
            "disabled": True,
        },
    ]

    utility_items = [
        {
            "label": "Messages",
            "url": home_url,
            "icon": ICON_MESSAGE,
            "active": active == "messages",
            "disabled": True,
        },
        {
            "label": "Tasks",
            "url": home_url,
            "icon": ICON_TASK,
            "active": active == "tasks",
            "disabled": True,
        },
        {
            "label": "Reminders",
            "url": home_url,
            "icon": ICON_BELL,
            "active": active == "reminders",
            "disabled": True,
        },
        {
            "label": "Calendar",
            "url": home_url,
            "icon": ICON_CALENDAR,
            "active": active == "calendar",
            "disabled": True,
        },
    ]

    return {
        "client": client,
        "theme": "client",
        "page_title": page_title,
        "role_label": "Client",
        "session_greeting": greeting,
        "welcome_headline": "Client portal",
        "welcome_copy": "Follow your matters and stay connected with the firm representing you.",
        "dashboard_url": home_url,
        "dashboard_active": active == "dashboard",
        "settings_url": home_url,
        "settings_active": active == "settings",
        "page_nav_items": page_nav_items,
        "utility_items": utility_items,
        "icon_home": ICON_HOME,
        "icon_settings": ICON_SETTINGS,
        "icon_logout": ICON_LOGOUT,
        "session_started_at": request.session.get("session_started_at"),
        "server_now": timezone.localtime().isoformat(),
        "crumb_parts": [
            {"label": "Client portal", "url": home_url},
            {"label": page_title, "url": home_url},
        ],
        "sign_in_method": (
            "Google"
            if client.google_sub
            else "Email & password"
            if client.password
            else "Not set"
        ),
        "firm_name": get_firm_display_name(),
    }
