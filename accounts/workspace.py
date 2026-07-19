"""Workspace navigation helpers for role dashboards."""

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from .models import Employee

SESSION_GREETING_KEY = "greeting_name_key"
SESSION_STARTED_AT_KEY = "session_started_at"
GREETING_COOKIE = "sc_greeting_name"
GREETING_KEYS = ("last", "first")


def mark_session_start(request) -> str:
    """Record when this login session began (ISO timestamp, local timezone)."""
    started = timezone.localtime().isoformat()
    request.session[SESSION_STARTED_AT_KEY] = started
    return started


def ensure_session_started_at(request) -> str:
    """Backfill session start for already-authenticated users."""
    started = request.session.get(SESSION_STARTED_AT_KEY)
    if not started:
        started = mark_session_start(request)
    return started


def _notification_badge_context(user) -> dict:
    """Initial bell + sidebar badge counts for first paint (before live poll)."""
    # Lazy import: notifications.py imports workspace helpers at module load.
    from .notifications import utility_badge_counts

    badges = utility_badge_counts(user)
    return {
        "notification_unread_count": sum(badges.values()),
        "notification_badges": badges,
    }


def time_of_day_greeting(when=None) -> str:
    moment = timezone.localtime(when) if when else timezone.localtime()
    hour = moment.hour
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


def greeting_variant_map(user) -> dict[str, str]:
    """Map session keys to courtesy-titled names, dropping duplicates."""
    mapping = {
        "last": user.get_titled_last_name(),
        "first": user.get_titled_first_name(),
    }
    seen = set()
    unique = {}
    for key in GREETING_KEYS:
        name = (mapping.get(key) or "").strip()
        if name and name not in seen:
            unique[key] = name
            seen.add(name)
    return unique


def assign_session_greeting(request, user) -> str:
    """
    Pick one greeting name for this login session.
    Alternates last/first name across sessions using a cookie.
    """
    variants = greeting_variant_map(user)
    keys = list(variants.keys()) or ["last"]
    previous = request.COOKIES.get(GREETING_COOKIE, "")
    if previous in keys and len(keys) > 1:
        chosen = keys[(keys.index(previous) + 1) % len(keys)]
    else:
        chosen = keys[0]
    request.session[SESSION_GREETING_KEY] = chosen
    return chosen


def ensure_session_greeting(request, user) -> str:
    chosen = request.session.get(SESSION_GREETING_KEY)
    variants = greeting_variant_map(user)
    if chosen not in variants:
        chosen = assign_session_greeting(request, user)
    return chosen


def session_greeting_name(request, user) -> str:
    variants = greeting_variant_map(user)
    key = ensure_session_greeting(request, user)
    return variants.get(key) or user.login_code


def attach_greeting_cookie(response, request):
    """Remember which name this session used so the next session can exchange."""
    chosen = request.session.get(SESSION_GREETING_KEY)
    if not chosen:
        return response
    response.set_cookie(
        GREETING_COOKIE,
        chosen,
        max_age=60 * 60 * 24 * 365,
        samesite="Lax",
        httponly=False,
    )
    return response


def workspace_reverse(role_slug: str, *pages: str) -> str:
    trail = "/".join(part.strip("/") for part in pages if part)
    return reverse(
        "accounts:workspace",
        kwargs={"role": role_slug, "pages": trail or "dashboard"},
    )


ICON_HOME = (
    '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    '<path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1v-9.5z" '
    'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)
ICON_BACK = (
    '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    '<path d="M15 18 9 12l6-6" '
    'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)
ICON_USERS = (
    '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z'
    'M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" '
    'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)
ICON_BRIEF = (
    '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    '<path d="M10 6V4a2 2 0 0 1 2-2h0a2 2 0 0 1 2 2v2M4 8h16v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8z" '
    'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)
ICON_DOC = (
    '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5zM14 3v5h5" '
    'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)
ICON_SCALE = (
    '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    '<path d="M12 3v18M5 8l7-4 7 4M5 8c0 3 3 5 7 5s7-2 7-5M8 21h8" '
    'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)
ICON_SETTINGS = (
    '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    '<path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z'
    'M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9c.2.6.7 1 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" '
    'stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)
ICON_LOGOUT = (
    '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" '
    'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)
ICON_BELL = (
    '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.9 1.9 0 0 0 3.4 0" '
    'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)
ICON_CALENDAR = (
    '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    '<path d="M8 2v3M16 2v3M4 9h16M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z" '
    'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)
ICON_TASK = (
    '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    '<path d="M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" '
    'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)
ICON_MESSAGE = (
    '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    '<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5z" '
    'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)
ICON_TOOLS = (
    '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    '<path d="M14.7 6.3a4 4 0 0 0-5.6 5.6L3 18l3 3 6.1-6.1a4 4 0 0 0 5.6-5.6L15 12l-2.7-2.7 2.4-3z" '
    'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)
ICON_FINANCE = (
    '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    '<path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" '
    'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)
ICON_LEARN = (
    '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20M4 4v15.5M6.5 4H20v13H6.5A2.5 2.5 0 0 0 4 19.5" '
    'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)

# Role modules (page-unique entry points — shown on the dashboard only, not in shared sidebar)
ROLE_MODULES = {
    Employee.Role.FIRM_ADMIN: [
        ("People", "people", ICON_USERS),
        ("Firm settings", "firm-settings", ICON_SETTINGS),
    ],
    Employee.Role.MANAGING_PARTNER: [
        ("Matters", "matters", ICON_BRIEF),
        ("Performance", "performance", ICON_SCALE),
    ],
    Employee.Role.ADVOCATE: [
        ("My cases", "my-cases", ICON_SCALE),
        ("Documents", "documents", ICON_DOC),
    ],
    Employee.Role.INTERN: [
        ("Assignments", "assignments", ICON_BRIEF),
        ("Learning", "learning", ICON_LEARN),
    ],
    Employee.Role.IT_SUPPORT: [
        ("Systems", "systems", ICON_SETTINGS),
        ("Users", "users", ICON_USERS),
    ],
    Employee.Role.EMPLOYEE: [
        ("Documents", "documents", ICON_DOC),
    ],
}

# Kept for older imports / clarity — shared sidebar only uses Dashboard.
ROLE_NAV = {
    role: [("Dashboard", "dashboard", ICON_HOME), *modules]
    for role, modules in ROLE_MODULES.items()
}

ROLE_WELCOME = {
    Employee.Role.FIRM_ADMIN: {
        "headline": "Firm administration",
        "copy": "Approve staff, assign roles, and maintain firm-wide access controls.",
        "stats": [
            ("Pending approvals", "—"),
            ("Active personnel", "—"),
            ("Open matters", "—"),
        ],
    },
    Employee.Role.MANAGING_PARTNER: {
        "headline": "Practice oversight",
        "copy": "Monitor matter health, counsel capacity, and chamber performance.",
        "stats": [
            ("Active matters", "—"),
            ("Counsel load", "—"),
            ("This week", "—"),
        ],
    },
    Employee.Role.ADVOCATE: {
        "headline": "Counsel desk",
        "copy": "Prepare matters, manage filings, and keep client records in order.",
        "stats": [
            ("My matters", "—"),
            ("Upcoming hearings", "—"),
            ("Documents", "—"),
        ],
    },
    Employee.Role.INTERN: {
        "headline": "Training desk",
        "copy": "Complete assigned research, drafts, and supervised learning tasks.",
        "stats": [
            ("Open assignments", "—"),
            ("Due this week", "—"),
            ("Completed", "—"),
        ],
    },
    Employee.Role.IT_SUPPORT: {
        "headline": "Systems operations",
        "copy": "Support accounts, resolve access issues, and safeguard platform uptime.",
        "stats": [
            ("Open tickets", "—"),
            ("Managed accounts", "—"),
            ("Service status", "—"),
        ],
    },
    Employee.Role.EMPLOYEE: {
        "headline": "Staff workspace",
        "copy": "Access assigned tasks, internal notices, and shared firm documents.",
        "stats": [
            ("My tasks", "—"),
            ("Notices", "—"),
            ("Shared files", "—"),
        ],
    },
}

# Shared utility links — appear on every page beside System settings / Log out
SHARED_UTILITY_LINKS = [
    ("Messages", "messages", ICON_MESSAGE),
    ("Tasks", "tasks", ICON_TASK),
    ("Reminders", "reminders", ICON_BELL),
    ("Calendar", "calendar", ICON_CALENDAR),
    ("My tools", "my-tools", ICON_TOOLS),
]

# Dashboard-only management links — shown below Dashboard on dashboard pages only
DASHBOARD_PAGE_LINKS = [
    ("User Management", "user-management", ICON_USERS),
    ("Matter Management", "matter-management", ICON_BRIEF),
    ("Document Management", "document-management", ICON_DOC),
    ("Finance & Billing", "finance-billing", ICON_FINANCE),
]
DASHBOARD_PAGE_SLUGS = {slug for _, slug, _ in DASHBOARD_PAGE_LINKS} | {"dashboard"}

# User Management page-only links
USER_MANAGEMENT_PAGE_LINKS = [
    ("Client Management", "client-management", ICON_USERS),
    ("Employee Management", "employee-management", ICON_USERS),
]

# Client Management page-only links
CLIENT_MANAGEMENT_PAGE_LINKS = [
    ("Register Client", "register-client", ICON_DOC),
    ("Approve pending clients", "approve-pending-clients", ICON_USERS),
]

# Employee Management page-only links
EMPLOYEE_MANAGEMENT_PAGE_LINKS = [
    ("Register Employee", "register-employee", ICON_DOC),
    ("Onboarding & Approvals", "onboarding-approvals", ICON_USERS),
    ("Roles & Permissions", "roles-permissions", ICON_SETTINGS),
    ("Employee Training", "employee-training", ICON_LEARN),
    ("Matter Allocation & Coverage", "matter-allocation", ICON_BRIEF),
    ("Employee Communications", "employee-communications", ICON_BELL),
    ("Performance & Compliance", "performance-compliance", ICON_SCALE),
    ("Leave & Availability", "leave-availability", ICON_CALENDAR),
    ("Offboarding", "offboarding", ICON_LOGOUT),
]

# Matter Management page-only links
MATTER_MANAGEMENT_PAGE_LINKS = [
    ("Litigation Matters", "litigation-matters", ICON_SCALE),
    ("Non-Litigation Matters", "non-litigation-matters", ICON_BRIEF),
]

# Litigation Matters page-only links
LITIGATION_MATTERS_PAGE_LINKS = [
    ("Register Case", "register-case", ICON_DOC),
    ("Approve registered cases", "approve-registered-cases", ICON_SCALE),
]

# Non-Litigation Matters page-only links
NON_LITIGATION_MATTERS_PAGE_LINKS = [
    ("Register New Matter", "register-new-matter", ICON_DOC),
    ("Approve registered matters", "approve-registered-matters", ICON_BRIEF),
]

SYSTEM_SETTINGS_PAGE_LINKS = [
    ("Website Template", "website-template", ICON_DOC),
    ("Company Information", "company-information", ICON_BRIEF),
    ("Document Settings", "document-settings", ICON_SETTINGS),
    ("Theme Settings", "theme-settings", ICON_SETTINGS),
]

DOCUMENT_SETTINGS_PAGE_LINKS = [
    ("Letterhead", "letterhead", ICON_DOC),
    ("Digital stamp", "digital-stamp", ICON_BRIEF),
    ("Default signature", "default-signature", ICON_SCALE),
    ("Google Drive Settings", "google-drive-settings", ICON_SETTINGS),
]

PAGE_LOCAL_LINKS = {
    "user-management": USER_MANAGEMENT_PAGE_LINKS,
    "client-management": CLIENT_MANAGEMENT_PAGE_LINKS,
    "employee-management": EMPLOYEE_MANAGEMENT_PAGE_LINKS,
    "matter-management": MATTER_MANAGEMENT_PAGE_LINKS,
    "litigation-matters": LITIGATION_MATTERS_PAGE_LINKS,
    "non-litigation-matters": NON_LITIGATION_MATTERS_PAGE_LINKS,
    "settings": [
        ("Profile & appearance", "settings", ICON_SETTINGS),
        ("Notifications", "notification-settings", ICON_BELL),
    ],
    "system-settings": SYSTEM_SETTINGS_PAGE_LINKS,
    "document-settings": DOCUMENT_SETTINGS_PAGE_LINKS,
}

# Personal My settings / My profile sidebar group
SETTINGS_AREA_SLUGS = {"settings", "notification-settings"}

# Document Settings subtree (sidebar when drilled into Document Settings)
DOCUMENT_SETTINGS_AREA_SLUGS = {"document-settings"} | {
    slug for _, slug, _ in DOCUMENT_SETTINGS_PAGE_LINKS
}

# Firm System settings hub + children (footer "System settings" link)
SYSTEM_SETTINGS_AREA_SLUGS = {"system-settings"} | {
    slug for _, slug, _ in SYSTEM_SETTINGS_PAGE_LINKS
} | DOCUMENT_SETTINGS_AREA_SLUGS

# Pages reachable by deep link / action flows but not shown in page-local nav.
EXTRA_PAGE_SLUGS = {"notification-settings", "system-settings"}


# Litigation case detail sidebar actions
LITIGATION_CASE_DETAIL_LINKS = [
    ("Update court attendance", "update-court-attendance", ICON_CALENDAR),
    ("Create task", "create-task", ICON_TASK),
    ("Upload documents", "upload-documents", ICON_DOC),
    ("Edit case details", "edit-case-details", ICON_DOC),
    ("Change status", "change-status", ICON_SCALE),
    ("Change allocation", "change-allocation", ICON_USERS),
    ("Case audit progress", "case-audit-progress", ICON_BRIEF),
]
LITIGATION_CASE_ACTION_SLUGS = {slug for _, slug, _ in LITIGATION_CASE_DETAIL_LINKS}

# Non-litigation matter detail sidebar actions
NON_LITIGATION_MATTER_DETAIL_LINKS = [
    ("Update matter attendance", "update-matter-attendance", ICON_CALENDAR),
    ("Create task", "create-task", ICON_TASK),
    ("Upload documents", "upload-documents", ICON_DOC),
    ("Edit matter details", "edit-matter-details", ICON_DOC),
    ("Change status", "change-status", ICON_SCALE),
    ("Change allocation", "change-allocation", ICON_USERS),
    ("Matter audit progress", "matter-audit-progress", ICON_BRIEF),
]
NON_LITIGATION_MATTER_ACTION_SLUGS = {
    slug for _, slug, _ in NON_LITIGATION_MATTER_DETAIL_LINKS
}


def litigation_case_nav_items(role_slug: str, case_id: int, active_slug: str | None = None):
    """Sidebar actions for a litigation case detail page."""
    return [
        {
            "label": label,
            "slug": slug,
            "url": reverse(
                "accounts:litigation_case_action",
                kwargs={
                    "role": role_slug,
                    "case_id": case_id,
                    "action": slug,
                },
            ),
            "icon": icon,
            "active": slug == active_slug,
        }
        for label, slug, icon in LITIGATION_CASE_DETAIL_LINKS
    ]


def non_litigation_matter_nav_items(
    role_slug: str, matter_id: int, active_slug: str | None = None
):
    """Sidebar actions for a non-litigation matter detail page."""
    return [
        {
            "label": label,
            "slug": slug,
            "url": reverse(
                "accounts:non_litigation_matter_action",
                kwargs={
                    "role": role_slug,
                    "matter_id": matter_id,
                    "action": slug,
                },
            ),
            "icon": icon,
            "active": slug == active_slug,
        }
        for label, slug, icon in NON_LITIGATION_MATTER_DETAIL_LINKS
    ]


def page_local_links_for(active: str, trail: list[str] | None = None):
    """
    Return page-local nav for this page only.

    When drilled into a child of that page (e.g. register-client or
    approve-pending-clients under client-management), keep showing the
    parent page's local links.
    """
    if active in SETTINGS_AREA_SLUGS:
        return PAGE_LOCAL_LINKS["settings"]
    if active in DOCUMENT_SETTINGS_AREA_SLUGS:
        return PAGE_LOCAL_LINKS["document-settings"]
    if active in SYSTEM_SETTINGS_AREA_SLUGS:
        return PAGE_LOCAL_LINKS["system-settings"]
    if active in PAGE_LOCAL_LINKS:
        return PAGE_LOCAL_LINKS[active]
    trail = trail or []
    for segment in reversed(trail[:-1]):
        links = PAGE_LOCAL_LINKS.get(segment)
        if links and any(slug == active for _, slug, _ in links):
            return links
    return None


PAGE_TITLES = {
    "dashboard": "Dashboard",
    "settings": "My settings",
    "notification-settings": "Notifications",
    "system-settings": "System Settings",
    "website-template": "Website Template",
    "company-information": "Company Information",
    "document-settings": "Document Settings",
    "theme-settings": "Theme Settings",
    "letterhead": "Letterhead",
    "digital-stamp": "Digital stamp",
    "default-signature": "Default signature",
    "google-drive-settings": "Google Drive Settings",
    "messages": "Messages",
    "tasks": "Tasks",
    "reminders": "Reminders",
    "calendar": "Calendar",
    "my-tools": "My tools",
    "user-management": "User Management",
    "client-management": "Client Management",
    "register-client": "Register Client",
    "approve-pending-clients": "Approve pending clients",
    "employee-management": "Employee Management",
    "register-employee": "Register Employee",
    "onboarding-approvals": "Onboarding & Approvals",
    "roles-permissions": "Roles & Permissions",
    "employee-training": "Employee Training",
    "matter-allocation": "Matter Allocation & Coverage",
    "employee-communications": "Employee Communications",
    "performance-compliance": "Performance & Compliance",
    "leave-availability": "Leave & Availability",
    "offboarding": "Offboarding",
    "matter-management": "Matter Management",
    "litigation-matters": "Litigation Matters",
    "non-litigation-matters": "Non-Litigation Matters",
    "register-case": "Register Case",
    "approve-registered-cases": "Approve registered cases",
    "register-new-matter": "Register New Matter",
    "approve-registered-matters": "Approve registered matters",
    "document-management": "Document Management",
    "finance-billing": "Finance & Billing",
    "people": "People",
    "firm-settings": "Firm settings",
    "matters": "Matters",
    "performance": "Performance",
    "my-cases": "My cases",
    "documents": "Documents",
    "assignments": "Assignments",
    "learning": "Learning",
    "systems": "Systems",
    "users": "Users",
    "update-court-attendance": "Update court attendance",
    "create-task": "Create task",
    "upload-documents": "Upload documents",
    "edit-case-details": "Edit case details",
    "edit-matter-details": "Edit matter details",
    "change-status": "Change status",
    "change-allocation": "Change allocation",
    "case-audit-progress": "Case audit progress",
    "matter-audit-progress": "Matter audit progress",
    "update-matter-attendance": "Update matter attendance",
}


def parse_page_trail(pages: str) -> list[str]:
    return [part for part in (pages or "").strip("/").split("/") if part]


def role_page_slugs(role) -> set[str]:
    modules = ROLE_MODULES.get(role, ROLE_MODULES[Employee.Role.EMPLOYEE])
    shared = {slug for _, slug, _ in SHARED_UTILITY_LINKS}
    page_local = {
        slug
        for links in PAGE_LOCAL_LINKS.values()
        for _, slug, _ in links
    }
    return (
        {slug for _, slug, _ in modules}
        | shared
        | DASHBOARD_PAGE_SLUGS
        | page_local
        | EXTRA_PAGE_SLUGS
        | {"settings"}
    )


def resolve_workspace_page(role, pages: str):
    """
    Resolve /<role>/<pages>/ into a leaf page and trail.

    Nested paths keep prior segments so URLs grow as the user moves, e.g.
    dashboard → dashboard/settings.
    """
    trail = parse_page_trail(pages)
    if not trail:
        trail = ["dashboard"]

    allowed = role_page_slugs(role)
    leaf = trail[-1]
    if leaf not in allowed:
        return None

    # Nested settings (or any leaf) may follow prior nav pages.
    for segment in trail[:-1]:
        if segment not in allowed:
            return None

    return {
        "trail": trail,
        "leaf": leaf,
        "page_title": PAGE_TITLES.get(leaf, leaf.replace("-", " ").title()),
        "is_settings": leaf == "settings",
        "is_theme_settings": leaf == "theme-settings",
        "is_notification_settings": leaf == "notification-settings",
        "is_google_drive_settings": leaf == "google-drive-settings",
        "is_settings_area": leaf in SETTINGS_AREA_SLUGS,
        "is_system_settings_area": leaf in SYSTEM_SETTINGS_AREA_SLUGS,
        "is_dashboard": leaf == "dashboard",
    }


# Side pages that nest under the current trail but should not stack on each other.
TRAIL_SIDE_PAGES = (
    {slug for _, slug, _ in SHARED_UTILITY_LINKS}
    | SETTINGS_AREA_SLUGS
    | SYSTEM_SETTINGS_AREA_SLUGS
)

def extend_page_trail(trail: list[str], *pages: str) -> list[str]:
    """
    Grow /<role>/<page>/<page>/ as the user moves.

    Trailing side pages (settings, reminders, …) are replaced so they nest
    under the content trail instead of stacking forever.
    """
    clean = [part for part in trail if part]
    while clean and clean[-1] in TRAIL_SIDE_PAGES:
        clean.pop()
    if not clean:
        clean = ["dashboard"]
    for page in pages:
        slug = (page or "").strip("/")
        if not slug:
            continue
        if clean[-1] == slug:
            continue
        clean.append(slug)
    return clean


def settings_pages_for_trail(trail: list[str]) -> str:
    return "/".join(extend_page_trail(trail, "settings"))


def back_url_for_trail(role_slug: str, trail: list[str]) -> str | None:
    """Parent page in the trail, or dashboard when leaving a top-level page."""
    clean = [part for part in trail if part]
    if len(clean) > 1:
        return workspace_reverse(role_slug, *clean[:-1])
    if clean and clean[0] != "dashboard":
        return workspace_reverse(role_slug, "dashboard")
    return None


def workspace_context(
    user,
    *,
    page_title,
    page_trail=None,
    active_page=None,
    request=None,
    page_nav_items=None,
):
    role = user.role
    role_slug = user.role_slug
    trail = page_trail or ["dashboard"]
    active = active_page or trail[-1]
    is_personal_settings = active in SETTINGS_AREA_SLUGS
    is_system_settings = active in SYSTEM_SETTINGS_AREA_SLUGS
    is_settings_chrome = is_personal_settings or is_system_settings
    is_dashboard = (not is_settings_chrome) and active == "dashboard"

    # Shared sidebar: Dashboard only. Other modules stay page-unique.
    nav_items = [
        {
            "label": "Dashboard",
            "slug": "dashboard",
            "url": workspace_reverse(role_slug, "dashboard"),
            "icon": ICON_HOME,
            "active": is_dashboard,
        }
    ]

    module_source = ROLE_MODULES.get(role, ROLE_MODULES[Employee.Role.EMPLOYEE])
    module_items = [
        {
            "label": label,
            "slug": slug,
            "url": workspace_reverse(role_slug, *extend_page_trail(trail, slug)),
            "icon": icon,
            "active": slug == active and not is_settings_chrome,
        }
        for label, slug, icon in module_source
    ]

    welcome = ROLE_WELCOME.get(role, ROLE_WELCOME[Employee.Role.EMPLOYEE])
    greeting_prefix = time_of_day_greeting()
    if request is not None:
        greeting_name = session_greeting_name(request, user)
        session_started_at = ensure_session_started_at(request)
    else:
        greeting_name = user.get_titled_last_name() or user.get_titled_first_name()
        session_started_at = timezone.localtime().isoformat()

    crumb_parts = [
        {
            "label": user.get_role_display(),
            "url": workspace_reverse(role_slug, "dashboard"),
        },
    ]
    for index, segment in enumerate(trail):
        crumb_parts.append(
            {
                "label": PAGE_TITLES.get(
                    segment, segment.replace("-", " ").title()
                ),
                "url": workspace_reverse(role_slug, *trail[: index + 1]),
            }
        )

    # My profile / personal settings (header dropdown)
    settings_url = workspace_reverse(role_slug, *extend_page_trail(trail, "settings"))
    # Footer "System settings" → system-settings hub (Website Template, etc.)
    system_settings_url = workspace_reverse(
        role_slug, *extend_page_trail(trail, "system-settings")
    )
    dashboard_url = workspace_reverse(role_slug, "dashboard")
    utility_items = [
        {
            "label": label,
            "slug": slug,
            "url": workspace_reverse(role_slug, *extend_page_trail(trail, slug)),
            "icon": icon,
            "active": active == slug and not is_settings_chrome,
        }
        for label, slug, icon in SHARED_UTILITY_LINKS
    ]
    notif_ctx = _notification_badge_context(user)
    for item in utility_items:
        item["badge_count"] = notif_ctx["notification_badges"].get(item["slug"], 0)

    # Page-local sidebar links (dashboard modules, or links unique to one page).
    if page_nav_items is None:
        if is_dashboard:
            page_nav_items = [
                {
                    "label": label,
                    "slug": slug,
                    "url": workspace_reverse(
                        role_slug, *extend_page_trail(trail, slug)
                    ),
                    "icon": icon,
                    "active": False,
                }
                for label, slug, icon in DASHBOARD_PAGE_LINKS
            ]
        else:
            local_links = page_local_links_for(active, trail)
            if local_links:
                page_nav_items = [
                    {
                        "label": label,
                        "slug": slug,
                        "url": workspace_reverse(
                            role_slug, *extend_page_trail(trail, slug)
                        ),
                        "icon": icon,
                        "active": active == slug,
                    }
                    for label, slug, icon in local_links
                ]
            else:
                page_nav_items = []

    return {
        "page_title": page_title,
        "role_label": user.get_role_display(),
        "role_slug": role_slug,
        "theme": user.workspace_theme,
        "ui_font": user.workspace_font,
        "ui_density": user.workspace_density,
        "nav_items": nav_items,
        "module_items": module_items,
        "utility_items": utility_items,
        "page_nav_items": page_nav_items,
        "page_trail": trail,
        "active_page": active,
        "crumb_parts": crumb_parts,
        "dashboard_url": dashboard_url,
        "dashboard_active": is_dashboard,
        "back_url": back_url_for_trail(role_slug, trail),
        "settings_url": settings_url,
        "system_settings_url": system_settings_url,
        "settings_active": is_system_settings,
        "settings_disabled": False,
        "dashboard_disabled": False,
        "icon_back": ICON_BACK,
        "icon_home": ICON_HOME,
        "icon_settings": ICON_SETTINGS,
        "icon_logout": ICON_LOGOUT,
        "welcome_headline": welcome["headline"],
        "welcome_copy": welcome["copy"],
        "welcome_stats": welcome["stats"],
        "greeting_prefix": greeting_prefix,
        "greeting_name": greeting_name,
        "session_greeting": f"{greeting_prefix}, {greeting_name}",
        "session_started_at": session_started_at,
        "server_now": timezone.localtime().isoformat(),
        "firm_name": getattr(settings, "FIRM_DISPLAY_NAME", "Sheria Law Firm"),
        "preactive_locked": False,
        "notifications_url": reverse("accounts:workspace_notifications"),
        "notifications_mark_all_url": reverse(
            "accounts:workspace_notifications_mark_all_read"
        ),
        "notification_sound_enabled": bool(
            getattr(user, "notification_sound", True)
        ),
        "icon_bell": ICON_BELL,
        **notif_ctx,
    }


def employee_preactive_context(request, user, *, page_title, active="onboarding"):
    """
    Workspace chrome for employees who are not yet active.

    Shows the allocated role sidebar with navigation locked until approval.
    """
    role = user.role
    role_slug = user.role_slug
    home_url = (
        reverse("accounts:employee_onboarding")
        if user.status == Employee.Status.PENDING_ONBOARDING
        else reverse("accounts:about_work")
    )

    greeting_prefix = time_of_day_greeting()
    greeting_name = session_greeting_name(request, user)
    session_started_at = ensure_session_started_at(request)

    page_nav_items = [
        {
            "label": label,
            "slug": slug,
            "url": "#",
            "icon": icon,
            "active": False,
            "disabled": True,
        }
        for label, slug, icon in DASHBOARD_PAGE_LINKS
    ]

    module_items = [
        {
            "label": label,
            "slug": slug,
            "url": "#",
            "icon": icon,
            "active": False,
            "disabled": True,
        }
        for label, slug, icon in ROLE_MODULES.get(
            role, ROLE_MODULES[Employee.Role.EMPLOYEE]
        )
    ]

    utility_items = [
        {
            "label": label,
            "slug": slug,
            "url": "#",
            "icon": icon,
            "active": False,
            "disabled": True,
            "badge_count": 0,
        }
        for label, slug, icon in SHARED_UTILITY_LINKS
    ]

    status_label = user.get_status_display()
    notif_ctx = _notification_badge_context(user)
    for item in utility_items:
        item["badge_count"] = notif_ctx["notification_badges"].get(item["slug"], 0)

    return {
        "page_title": page_title,
        "role_label": user.get_role_display(),
        "role_slug": role_slug,
        "theme": user.workspace_theme,
        "ui_font": user.workspace_font,
        "ui_density": user.workspace_density,
        "nav_items": [],
        "module_items": module_items,
        "utility_items": utility_items,
        "page_nav_items": page_nav_items,
        "page_trail": [active],
        "active_page": active,
        "crumb_parts": [
            {"label": user.get_role_display(), "url": home_url},
            {"label": page_title, "url": home_url},
        ],
        "dashboard_url": home_url,
        "dashboard_active": False,
        "dashboard_disabled": True,
        "back_url": None,
        "settings_url": "#",
        "system_settings_url": "#",
        "settings_active": False,
        "settings_disabled": True,
        "icon_back": ICON_BACK,
        "icon_home": ICON_HOME,
        "icon_settings": ICON_SETTINGS,
        "icon_logout": ICON_LOGOUT,
        "welcome_headline": page_title,
        "welcome_copy": "",
        "welcome_stats": [],
        "greeting_prefix": greeting_prefix,
        "greeting_name": greeting_name,
        "session_greeting": f"{greeting_prefix}, {greeting_name}",
        "session_started_at": session_started_at,
        "server_now": timezone.localtime().isoformat(),
        "firm_name": getattr(settings, "FIRM_DISPLAY_NAME", "Sheria Law Firm"),
        "preactive_locked": True,
        "lock_badge": "Locked",
        "status_label": status_label,
        "notifications_url": reverse("accounts:workspace_notifications"),
        "notifications_mark_all_url": reverse(
            "accounts:workspace_notifications_mark_all_read"
        ),
        "notification_sound_enabled": bool(
            getattr(user, "notification_sound", True)
        ),
        "icon_bell": ICON_BELL,
        **notif_ctx,
    }
