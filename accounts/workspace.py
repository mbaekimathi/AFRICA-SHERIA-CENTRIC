"""Workspace navigation helpers for role dashboards."""

from functools import lru_cache

from django.urls import reverse
from django.utils import timezone

from .models import Employee, get_firm_display_name

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


def pending_clients_count() -> int:
    """Clients awaiting onboarding completion or firm approval."""
    from .models import Client

    return Client.objects.filter(
        status__in=[
            Client.Status.PENDING_ONBOARDING,
            Client.Status.PENDING_APPROVAL,
        ]
    ).count()


def pending_employees_count() -> int:
    """Employees awaiting onboarding completion or firm approval."""
    return Employee.objects.filter(
        status__in=[
            Employee.Status.PENDING_ONBOARDING,
            Employee.Status.PENDING_APPROVAL,
        ]
    ).count()


def pending_litigation_cases_count() -> int:
    """Litigation cases awaiting firm approval."""
    from .models import LitigationCase

    return LitigationCase.objects.filter(
        status=LitigationCase.Status.PENDING_APPROVAL
    ).count()


def pending_non_litigation_matters_count() -> int:
    """Non-litigation matters awaiting firm approval."""
    from .models import NonLitigationMatter

    return NonLitigationMatter.objects.filter(
        status=NonLitigationMatter.Status.PENDING_APPROVAL
    ).count()


def _attach_page_nav_badges(page_nav_items: list[dict]) -> None:
    """Attach count badges to section nav / dashboard items that need them."""
    if not page_nav_items:
        return
    pending_clients = None
    pending_employees = None
    pending_cases = None
    pending_matters = None
    for item in page_nav_items:
        slug = item.get("slug")
        if slug == "user-management":
            if pending_clients is None:
                pending_clients = pending_clients_count()
            if pending_employees is None:
                pending_employees = pending_employees_count()
            item["badge_count"] = pending_clients + pending_employees
        elif slug in {"client-management", "approve-pending-clients"}:
            if pending_clients is None:
                pending_clients = pending_clients_count()
            item["badge_count"] = pending_clients
        elif slug in {"employee-management", "onboarding-approvals"}:
            if pending_employees is None:
                pending_employees = pending_employees_count()
            item["badge_count"] = pending_employees
        elif slug == "matter-management":
            if pending_cases is None:
                pending_cases = pending_litigation_cases_count()
            if pending_matters is None:
                pending_matters = pending_non_litigation_matters_count()
            item["badge_count"] = pending_cases + pending_matters
        elif slug in {"litigation-matters", "approve-registered-cases"}:
            if pending_cases is None:
                pending_cases = pending_litigation_cases_count()
            item["badge_count"] = pending_cases
        elif slug in {"non-litigation-matters", "approve-registered-matters"}:
            if pending_matters is None:
                pending_matters = pending_non_litigation_matters_count()
            item["badge_count"] = pending_matters


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

# Practice hubs — secondary links shown on the dashboard (and their children
# on allocated pages via PAGE_LOCAL_LINKS). Add new modules here; permissions
# and Roles & Permissions UI pick them up automatically.
SYSTEM_MODULES = (
    {
        "label": "User Management",
        "slug": "user-management",
        "icon": ICON_USERS,
        "hint": "Staff and client account access",
    },
    {
        "label": "Matter Management",
        "slug": "matter-management",
        "icon": ICON_BRIEF,
        "hint": "Litigation and non-litigation matters",
    },
    {
        "label": "Document Management",
        "slug": "document-management",
        "icon": ICON_DOC,
        "hint": "Filings, templates, and shared files",
    },
    {
        "label": "Finance & Billing",
        "slug": "finance-billing",
        "icon": ICON_FINANCE,
        "hint": "Invoices, payments, and accounts",
    },
    {
        "label": "Research & Blogs",
        "slug": "research-blogs",
        "icon": ICON_LEARN,
        "hint": "News research and firm blogs",
    },
)
DASHBOARD_PAGE_LINKS = [
    (module["label"], module["slug"], module["icon"]) for module in SYSTEM_MODULES
]
DASHBOARD_PAGE_SLUGS = {slug for _, slug, _ in DASHBOARD_PAGE_LINKS} | {"dashboard"}
SYSTEM_MODULE_SLUGS = {slug for _, slug, _ in DASHBOARD_PAGE_LINKS}

# Roles & Permissions — system modules are listed on the page, not in the sidebar.
USER_MANAGEMENT_PAGE_LINKS = [
    ("Client Management", "client-management", ICON_USERS),
    ("Employee Management", "employee-management", ICON_USERS),
]

# Client Management page-only links
CLIENT_MANAGEMENT_PAGE_LINKS = [
    ("Client Portal", "client-profile", ICON_USERS),
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

# Finance & Billing page-only links
FINANCE_BILLING_PAGE_LINKS = [
    ("General Accounts", "general-accounts", ICON_FINANCE),
    ("Client Accounts", "client-accounts", ICON_USERS),
    ("Employee Accounts", "employee-accounts", ICON_USERS),
    ("Company Accounts", "company-accounts", ICON_BRIEF),
]

# Employee Accounts page-only links
EMPLOYEE_ACCOUNTS_PAGE_LINKS = [
    ("Payroll", "payroll", ICON_FINANCE),
    ("Employee Advances", "employee-advances", ICON_BRIEF),
    ("Employee Petty Cashbook", "employee-petty-cashbook", ICON_DOC),
]

# Client Accounts page-only links
CLIENT_ACCOUNTS_PAGE_LINKS = [
    ("Generate Invoice", "generate-invoice", ICON_DOC),
]

# General Accounts page-only links
GENERAL_ACCOUNTS_PAGE_LINKS = [
    ("Payments", "payments", ICON_FINANCE),
    ("Purchasing", "purchasing", ICON_BRIEF),
    ("Inventory", "inventory", ICON_TOOLS),
    ("Sales", "sales", ICON_FINANCE),
    ("Customers", "customers", ICON_USERS),
    ("Suppliers", "suppliers", ICON_USERS),
    ("Banking", "banking", ICON_FINANCE),
    ("Accounting", "accounting", ICON_SCALE),
    ("Reporting", "reporting", ICON_LEARN),
]

# Invoicing page-only links
INVOICING_PAGE_LINKS = [
    ("Generate Invoice", "generate-invoice", ICON_DOC),
]

# Payroll page-only links
PAYROLL_PAGE_LINKS = [
    ("Register Payroll", "register-payroll", ICON_DOC),
]

# Employee Communications page-only links
EMPLOYEE_COMMUNICATIONS_PAGE_LINKS = [
    ("Email settings", "email-settings", ICON_SETTINGS),
]

# Research & Blogs page-only links
RESEARCH_BLOGS_PAGE_LINKS = [
    ("Latest News", "latest-news", ICON_LEARN),
    ("My blogs", "my-blogs", ICON_DOC),
]

# Shown only on their own hub pages — not inherited by child pages.
PAGE_LOCAL_LINKS_NO_INHERIT = {
    "finance-billing",
    "general-accounts",
    "client-accounts",
    "employee-accounts",
    "user-management",
    "employee-management",
}

SYSTEM_SETTINGS_PAGE_LINKS = [
    ("Website Template", "website-template", ICON_DOC),
    ("Company Information", "company-information", ICON_BRIEF),
    ("Document Settings", "document-settings", ICON_SETTINGS),
    ("Finance Settings", "finance-settings", ICON_FINANCE),
    ("Communication Settings", "communication-settings", ICON_BELL),
]

COMPANY_INFORMATION_PAGE_LINKS = [
    ("Company Profile", "company-profile", ICON_BRIEF),
    ("Company Contacts", "company-contacts", ICON_USERS),
    ("About Company", "about-company", ICON_DOC),
    ("Practice Areas", "practice-areas", ICON_SCALE),
    ("Company Gallery", "company-gallery", ICON_DOC),
    ("Company Blogs", "company-blogs", ICON_DOC),
    ("Company FAQs", "company-faqs", ICON_BELL),
    ("Terms and Conditions", "company-terms", ICON_SCALE),
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
    "finance-billing": FINANCE_BILLING_PAGE_LINKS,
    "general-accounts": GENERAL_ACCOUNTS_PAGE_LINKS,
    "client-accounts": CLIENT_ACCOUNTS_PAGE_LINKS,
    "employee-accounts": EMPLOYEE_ACCOUNTS_PAGE_LINKS,
    "invoicing": INVOICING_PAGE_LINKS,
    "payroll": PAYROLL_PAGE_LINKS,
    "employee-communications": EMPLOYEE_COMMUNICATIONS_PAGE_LINKS,
    "research-blogs": RESEARCH_BLOGS_PAGE_LINKS,
    "settings": [
        ("My profile", "settings", ICON_SETTINGS),
        ("About me", "about-me", ICON_DOC),
        ("Notifications", "notification-settings", ICON_BELL),
        ("Theme settings", "theme-settings", ICON_SETTINGS),
    ],
    "system-settings": SYSTEM_SETTINGS_PAGE_LINKS,
    "company-information": COMPANY_INFORMATION_PAGE_LINKS,
    "document-settings": DOCUMENT_SETTINGS_PAGE_LINKS,
}

# Personal My profile sidebar group (theme is per-account, not firm-wide)
SETTINGS_AREA_SLUGS = {
    "settings",
    "about-me",
    "notification-settings",
    "theme-settings",
}

# Research & Blogs subtree (sidebar when viewing research and authoring pages)
RESEARCH_BLOGS_AREA_SLUGS = {
    "research-blogs",
    "latest-news",
    "my-blogs",
    "my-blogs-new",
}

# Company Information subtree (sidebar when drilled into Company Information)
COMPANY_INFORMATION_AREA_SLUGS = {
    "company-information",
    "practice-areas-new",
    "company-faqs-new",
    "company-gallery-new",
} | {slug for _, slug, _ in COMPANY_INFORMATION_PAGE_LINKS}

# Document Settings subtree (sidebar when drilled into Document Settings)
DOCUMENT_SETTINGS_AREA_SLUGS = {"document-settings"} | {
    slug for _, slug, _ in DOCUMENT_SETTINGS_PAGE_LINKS
}

# Firm System settings hub + children (footer "System settings" link)
SYSTEM_SETTINGS_AREA_SLUGS = {"system-settings"} | {
    slug for _, slug, _ in SYSTEM_SETTINGS_PAGE_LINKS
} | COMPANY_INFORMATION_AREA_SLUGS | DOCUMENT_SETTINGS_AREA_SLUGS

# Pages reachable by deep link / action flows but not shown in page-local nav.
EXTRA_PAGE_SLUGS = {
    "notification-settings",
    "system-settings",
    "my-blogs-new",
    "practice-areas-new",
    "company-faqs-new",
    "company-gallery-new",
}


# Litigation case detail sidebar actions
LITIGATION_CASE_DETAIL_LINKS = [
    ("Case calendar", "case-calendar", ICON_CALENDAR),
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
    ("Matter calendar", "matter-calendar", ICON_CALENDAR),
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

# Extra activities that belong to a system module but are not in PAGE_LOCAL_LINKS.
MODULE_EXTRA_ACTIVITIES = {
    "document-management": [
        ("Upload documents", "upload-documents", ICON_DOC),
        ("View document activity", "document-activity", ICON_BRIEF),
        ("Letterhead", "letterhead", ICON_DOC),
        ("Digital stamp", "digital-stamp", ICON_BRIEF),
        ("Default signature", "default-signature", ICON_SCALE),
        ("Google Drive Settings", "google-drive-settings", ICON_SETTINGS),
    ],
    "research-blogs": [
        ("New blog post", "my-blogs-new", ICON_DOC),
        ("Company blogs", "company-blogs", ICON_DOC),
    ],
    "matter-management": [
        *[(f"Case: {label}", slug, icon) for label, slug, icon in LITIGATION_CASE_DETAIL_LINKS],
        *[
            (f"Matter: {label}", slug, icon)
            for label, slug, icon in NON_LITIGATION_MATTER_DETAIL_LINKS
        ],
    ],
}


def collect_module_activities(module_slug: str) -> list[dict]:
    """
    Flatten every navigable activity under a system module.

    Walks PAGE_LOCAL_LINKS recursively, then appends MODULE_EXTRA_ACTIVITIES.
    Skips expanding roles-permissions into other system modules.
    """
    activities: list[dict] = []
    seen: set[str] = set()

    def add_activity(*, label, slug, icon, path_labels, path_slugs, linkable=True):
        key = "/".join(path_slugs) if path_slugs else slug
        if key in seen:
            return
        seen.add(key)
        activities.append(
            {
                "label": label,
                "slug": slug,
                "icon": icon,
                "path": " / ".join(path_labels),
                "depth": max(len(path_slugs) - 1, 0),
                "path_slugs": list(path_slugs),
                "linkable": linkable,
            }
        )

    def walk(parent_slug: str, path_labels: list[str], path_slugs: list[str]):
        if parent_slug == "roles-permissions":
            return
        for label, child_slug, icon in PAGE_LOCAL_LINKS.get(parent_slug) or []:
            if child_slug in SYSTEM_MODULE_SLUGS:
                continue
            next_labels = path_labels + [label]
            next_slugs = path_slugs + [child_slug]
            add_activity(
                label=label,
                slug=child_slug,
                icon=icon,
                path_labels=next_labels,
                path_slugs=next_slugs,
                linkable=True,
            )
            walk(child_slug, next_labels, next_slugs)

    walk(module_slug, [], [])

    for label, slug, icon in MODULE_EXTRA_ACTIVITIES.get(module_slug) or []:
        # Case/matter actions are per-record; list them without a module URL.
        linkable = module_slug != "matter-management" or slug not in (
            LITIGATION_CASE_ACTION_SLUGS | NON_LITIGATION_MATTER_ACTION_SLUGS
        )
        # Document settings live under system-settings, not the module hub.
        if module_slug == "document-management" and slug in {
            "letterhead",
            "digital-stamp",
            "default-signature",
            "google-drive-settings",
            "document-activity",
            "upload-documents",
        }:
            path_slugs = [slug]
            linkable = slug in {
                "letterhead",
                "digital-stamp",
                "default-signature",
                "google-drive-settings",
            }
        elif module_slug == "research-blogs" and slug in {"company-blogs", "my-blogs-new"}:
            path_slugs = [slug]
            linkable = True
        else:
            path_slugs = [slug]
        add_activity(
            label=label,
            slug=slug,
            icon=icon,
            path_labels=[label],
            path_slugs=path_slugs,
            linkable=linkable,
        )

    return activities


def system_module_hint(module_slug: str) -> str:
    for module in SYSTEM_MODULES:
        if module["slug"] == module_slug:
            return module["hint"]
    return "Configure role access for this module"


def system_module_meta(module_slug: str) -> dict | None:
    for module in SYSTEM_MODULES:
        if module["slug"] == module_slug:
            return module
    return None


PERMISSION_ACTION_LABELS = {
    "view": "View",
    "register": "Register",
    "edit": "Edit",
    "delete": "Delete",
    "approve": "Approve",
    "allocate": "Allocate",
    "task": "Task",
    "upload": "Upload",
    "attend": "Attend",
    "audit": "Audit",
    "status": "Change status",
    "generate": "Generate",
    "pay": "Pay",
    "communicate": "Communicate",
}

DEFAULT_ACTIVITY_ACTIONS = ("view", "register", "edit", "delete")

MATTER_HUB_ACTIONS = (
    "view",
    "register",
    "approve",
    "edit",
    "delete",
    "allocate",
    "task",
    "upload",
    "attend",
    "audit",
    "status",
)

FINANCE_LEDGER_ACTIONS = ("view", "register", "edit", "delete")

# Optional per-activity overrides when pattern inference is not enough.
ACTIVITY_PERMISSION_OVERRIDES: dict[str, tuple[str, ...]] = {}

_DETAIL_SLUG_PERMISSION_ACTIONS = {
    "case-calendar": "view",
    "matter-calendar": "view",
    "update-court-attendance": "attend",
    "update-matter-attendance": "attend",
    "create-task": "task",
    "upload-documents": "upload",
    "edit-case-details": "edit",
    "edit-matter-details": "edit",
    "change-status": "status",
    "change-allocation": "allocate",
    "case-audit-progress": "audit",
    "matter-audit-progress": "audit",
    "document-activity": "audit",
}

WORKSPACE_DETAIL_ACTION_MAP = dict(_DETAIL_SLUG_PERMISSION_ACTIONS)

WORKSPACE_PAGE_POST_PREFIX_ACTIONS = (
    ("register-", "register"),
    ("approve-", "approve"),
    ("generate-", "generate"),
)

WORKSPACE_APPROVE_ACTIVITIES = frozenset(
    slug
    for slug in (
        *(
            child_slug
            for links in PAGE_LOCAL_LINKS.values()
            for _label, child_slug, _icon in links
        ),
        *(
            child_slug
            for extras in MODULE_EXTRA_ACTIVITIES.values()
            for _label, child_slug, _icon in extras
        ),
    )
    if slug.startswith("approve-")
)

WORKSPACE_EDIT_POST_PAGES = frozenset(
    {
        "settings",
        "theme-settings",
        "notification-settings",
        "about-me",
        "my-blogs",
        "my-blogs-new",
        "company-profile",
        "company-contacts",
        "about-company",
        "practice-areas",
        "practice-areas-new",
        "company-faqs",
        "company-faqs-new",
        "company-gallery",
        "company-gallery-new",
        "company-terms",
        "website-template",
        "finance-settings",
        "communication-settings",
        "letterhead",
        "digital-stamp",
        "default-signature",
        "google-drive-settings",
        "email-settings",
    }
)


def _iter_nav_link_triples():
    for links in PAGE_LOCAL_LINKS.values():
        yield from links
    for extras in MODULE_EXTRA_ACTIVITIES.values():
        yield from extras
    for links in (
        LITIGATION_CASE_DETAIL_LINKS,
        NON_LITIGATION_MATTER_DETAIL_LINKS,
        SYSTEM_SETTINGS_PAGE_LINKS,
        COMPANY_INFORMATION_PAGE_LINKS,
        DOCUMENT_SETTINGS_PAGE_LINKS,
    ):
        yield from links
    for module in SYSTEM_MODULES:
        yield module["label"], module["slug"], module["icon"]


def nav_label_for_slug(slug: str) -> str | None:
    for label, link_slug, _icon in _iter_nav_link_triples():
        if link_slug == slug:
            return label
    return None


def page_title_for(slug: str) -> str:
    return PAGE_TITLES.get(slug) or nav_label_for_slug(slug) or slug.replace(
        "-", " "
    ).title()


def infer_activity_permission_actions(
    activity_slug: str, *, module_slug: str | None = None
) -> tuple[str, ...]:
    """Derive permission toggles for a workspace activity slug."""
    if activity_slug in ACTIVITY_PERMISSION_OVERRIDES:
        return ACTIVITY_PERMISSION_OVERRIDES[activity_slug]

    detail_action = WORKSPACE_DETAIL_ACTION_MAP.get(activity_slug)
    if detail_action:
        return ("view", detail_action)

    if activity_slug.startswith("approve-"):
        return ("view", "approve")
    if activity_slug.startswith("register-"):
        return ("view", "register")
    if activity_slug.endswith("-new") and activity_slug not in {
        "theme-settings",
        "notification-settings",
    }:
        return ("view", "register", "edit")
    if activity_slug.startswith("generate-"):
        return ("view", "generate")

    if activity_slug in {"litigation-matters", "non-litigation-matters"}:
        return MATTER_HUB_ACTIONS
    if activity_slug == "client-management":
        return ("view", "register", "edit", "delete", "approve")
    if activity_slug == "client-profile":
        return ("view", "edit", "delete")
    if activity_slug == "employee-management":
        return ("view", "register", "edit", "delete", "approve", "allocate")
    if activity_slug == "finance-billing":
        return ("view", "register", "edit", "delete", "pay")
    if activity_slug == "general-accounts":
        return ("view", "register", "edit", "delete", "pay")
    if activity_slug == "invoicing":
        return ("view", "generate", "edit", "delete", "pay")
    if activity_slug == "payments":
        return ("view", "pay")
    if activity_slug == "banking":
        return ("view", "register", "edit", "pay")
    if activity_slug == "accounting":
        return ("view", "edit", "audit")
    if activity_slug == "reporting":
        return ("view", "generate")
    if activity_slug in FINANCE_LEDGER_ACTIONS and activity_slug in {
        slug for _label, slug, _icon in GENERAL_ACCOUNTS_PAGE_LINKS
    }:
        return FINANCE_LEDGER_ACTIONS
    if activity_slug in {
        "payroll",
        "employee-advances",
        "employee-petty-cashbook",
    }:
        return FINANCE_LEDGER_ACTIONS
    if activity_slug == "employee-accounts":
        return ("view", "register", "edit", "delete", "pay")
    if activity_slug == "client-accounts":
        return ("view", "register", "edit", "delete", "pay")
    if activity_slug == "roles-permissions":
        return ("view", "edit")
    if activity_slug == "employee-training":
        return ("view", "register", "edit")
    if activity_slug == "matter-allocation":
        return ("view", "allocate", "edit")
    if activity_slug == "employee-communications":
        return ("view", "communicate", "edit")
    if activity_slug == "email-settings":
        return ("view", "edit")
    if activity_slug == "performance-compliance":
        return ("view", "edit", "audit")
    if activity_slug == "leave-availability":
        return ("view", "register", "edit", "approve")
    if activity_slug == "offboarding":
        return ("view", "edit", "delete")
    if activity_slug == "latest-news":
        return ("view", "register")
    if activity_slug == "my-blogs":
        return ("view", "register", "edit", "delete", "approve")
    if activity_slug == "company-blogs":
        return ("view", "approve", "edit", "delete")
    if activity_slug == "upload-documents":
        return ("view", "upload", "delete")
    if activity_slug == "document-activity":
        return ("view", "audit")
    if activity_slug in DOCUMENT_SETTINGS_AREA_SLUGS or activity_slug.endswith(
        "-settings"
    ):
        return ("view", "edit")
    if activity_slug in {
        "letterhead",
        "digital-stamp",
        "default-signature",
        "google-drive-settings",
    }:
        return ("view", "edit")
    if activity_slug == "research-blogs":
        return ("view", "register", "edit")
    if module_slug == "document-management":
        return ("view", "edit")

    return DEFAULT_ACTIVITY_ACTIONS


def build_activity_permission_registry() -> dict[str, tuple[str, ...]]:
    """
    Build permission actions for every activity discovered under system modules.

    New PAGE_LOCAL_LINKS / MODULE_EXTRA_ACTIVITIES entries are included
    automatically; use ACTIVITY_PERMISSION_OVERRIDES only for exceptions.
    """
    registry: dict[str, tuple[str, ...]] = {}

    for module_slug in SYSTEM_MODULE_SLUGS:
        for activity in collect_module_activities(module_slug):
            slug = activity["slug"]
            registry[slug] = infer_activity_permission_actions(
                slug, module_slug=module_slug
            )

    for slug in WORKSPACE_DETAIL_ACTION_MAP:
        registry.setdefault(
            slug,
            infer_activity_permission_actions(slug),
        )

    for _label, slug, _icon in _iter_nav_link_triples():
        registry.setdefault(slug, infer_activity_permission_actions(slug))

    registry.update(ACTIVITY_PERMISSION_OVERRIDES)
    return registry


@lru_cache(maxsize=1)
def get_activity_permission_registry() -> dict[str, tuple[str, ...]]:
    return build_activity_permission_registry()


def activity_module_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for module_slug in SYSTEM_MODULE_SLUGS:
        for activity in collect_module_activities(module_slug):
            mapping.setdefault(activity["slug"], module_slug)
    return mapping


def module_slug_for_activity(activity_slug: str) -> str | None:
    return activity_module_map().get(activity_slug)


def validate_permission_registry() -> list[str]:
    """
    Return activity slugs that have no permission mapping.

    Called on startup to catch nav additions that need overrides.
    """
    registry = get_activity_permission_registry()
    missing: list[str] = []
    for module_slug in SYSTEM_MODULE_SLUGS:
        for activity in collect_module_activities(module_slug):
            if activity["slug"] not in registry:
                missing.append(activity["slug"])
    return missing


ACTIVITY_PERMISSION_ACTIONS = get_activity_permission_registry()


def module_slug_for_trail(trail: list[str] | None) -> str | None:
    return next((seg for seg in (trail or []) if seg in SYSTEM_MODULE_SLUGS), None)


def workspace_detail_permission_action(detail_action: str) -> str:
    return WORKSPACE_DETAIL_ACTION_MAP.get(detail_action, "view")


def post_requests_delete(request) -> bool:
    if not request or request.method != "POST":
        return False
    if (request.POST.get("action") or "").strip().lower() in {
        "delete",
        "remove",
        "trash",
    }:
        return True
    return any(
        key.endswith("-DELETE") and value == "on"
        for key, value in request.POST.items()
    )


def resolve_workspace_post_action(activity_slug: str, request) -> str:
    for prefix, action in WORKSPACE_PAGE_POST_PREFIX_ACTIONS:
        if activity_slug.startswith(prefix):
            return action
    if activity_slug == "latest-news":
        return "register"
    if (
        activity_slug.endswith("-new")
        and activity_slug not in {"theme-settings", "notification-settings"}
    ):
        return "register"
    if activity_slug in WORKSPACE_APPROVE_ACTIVITIES:
        return "approve"
    if post_requests_delete(request):
        return "delete"
    if activity_slug in WORKSPACE_EDIT_POST_PAGES:
        return "edit"
    return "edit"


def activity_permission_actions(activity_slug: str) -> list[dict]:
    """Return labelled actions available for an activity permission page."""
    slugs = ACTIVITY_PERMISSION_ACTIONS.get(
        activity_slug, DEFAULT_ACTIVITY_ACTIONS
    )
    return [
        {
            "slug": slug,
            "label": PERMISSION_ACTION_LABELS.get(
                slug, slug.replace("-", " ").title()
            ),
        }
        for slug in slugs
    ]


def module_activity_url(user, module_slug: str, activity: dict) -> str | None:
    """Build a workspace URL for a module activity when it is linkable."""
    if not activity.get("linkable"):
        return None
    slug = activity["slug"]
    path_slugs = activity.get("path_slugs") or [slug]
    if module_slug == "document-management" and slug in {
        "letterhead",
        "digital-stamp",
        "default-signature",
        "google-drive-settings",
    }:
        return user.workspace_url(
            "dashboard", "system-settings", "document-settings", slug
        )
    if module_slug == "research-blogs" and slug == "my-blogs-new":
        return user.workspace_url("dashboard", "research-blogs", "my-blogs-new")
    if module_slug == "research-blogs" and slug == "company-blogs":
        return user.workspace_url(
            "dashboard", "system-settings", "company-information", "company-blogs"
        )
    return user.workspace_url("dashboard", module_slug, *path_slugs)


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
    Return secondary (page-allocated) nav for this page only.

    When drilled into a child of that page (e.g. register-client under
    client-management), keep showing the parent page's local links —
    unless the parent is marked no-inherit (e.g. finance-billing,
    general-accounts, user-management, employee-management hub links
    stay on that hub page only).
    """
    trail = trail or []
    # Roles & Permissions uses in-page navigation only — no sidebar section links.
    if "roles-permissions" in trail:
        return None
    if active in SETTINGS_AREA_SLUGS:
        return PAGE_LOCAL_LINKS["settings"]
    if active in RESEARCH_BLOGS_AREA_SLUGS:
        return PAGE_LOCAL_LINKS["research-blogs"]
    if active in COMPANY_INFORMATION_AREA_SLUGS:
        return PAGE_LOCAL_LINKS["company-information"]
    if active in DOCUMENT_SETTINGS_AREA_SLUGS:
        return PAGE_LOCAL_LINKS["document-settings"]
    if active in SYSTEM_SETTINGS_AREA_SLUGS:
        return PAGE_LOCAL_LINKS["system-settings"]
    if active in PAGE_LOCAL_LINKS:
        return PAGE_LOCAL_LINKS[active]
    for segment in reversed(trail[:-1]):
        if segment in PAGE_LOCAL_LINKS_NO_INHERIT:
            continue
        links = PAGE_LOCAL_LINKS.get(segment)
        if links:
            return links
    return None


def client_account_page_nav_items(
    user,
    trail: list[str],
    *,
    client_pk: int | None = None,
    active_slug: str = "client-accounts",
):
    """Sidebar links for client account pages, optionally scoped to one client."""
    base_trail = [part for part in trail if part and part != "generate-invoice"]
    items = []
    for label, slug, icon in CLIENT_ACCOUNTS_PAGE_LINKS:
        url = user.workspace_url(*extend_page_trail(base_trail, slug))
        if client_pk and slug == "generate-invoice":
            url = f"{url}?client={client_pk}"
        items.append(
            {
                "label": label,
                "slug": slug,
                "url": url,
                "icon": icon,
                "active": active_slug == slug,
            }
        )
    return items


def main_hub_is_active(hub_slug: str, active: str, trail: list[str]) -> bool:
    """True when the current page sits in this main hub's subtree."""
    if active == hub_slug:
        return True
    return hub_slug in (trail or [])


PAGE_TITLES = {
    "dashboard": "Dashboard",
    "research-blogs": "Research & Blogs",
    "latest-news": "Latest News",
    "settings": "My profile",
    "about-me": "About me",
    "my-blogs": "My blogs",
    "my-blogs-new": "New blog post",
    "notification-settings": "Notifications",
    "system-settings": "System Settings",
    "website-template": "Website Template",
    "company-information": "Company Information",
    "company-profile": "Company Profile",
    "company-contacts": "Company Contacts",
    "about-company": "About Company",
    "practice-areas": "Practice Areas",
    "practice-areas-new": "Add practice area",
    "company-gallery": "Company Gallery",
    "company-gallery-new": "Add gallery image",
    "company-blogs": "Company Blogs",
    "company-faqs": "Company FAQs",
    "company-faqs-new": "Add FAQ",
    "company-terms": "Terms and Conditions",
    "document-settings": "Document Settings",
    "theme-settings": "Theme Settings",
    "letterhead": "Letterhead",
    "digital-stamp": "Digital stamp",
    "default-signature": "Default signature",
    "google-drive-settings": "Google Drive Settings",
    "finance-settings": "Finance Settings",
    "communication-settings": "Communication Settings",
    "messages": "Messages",
    "tasks": "Tasks",
    "reminders": "Reminders",
    "calendar": "Calendar",
    "my-tools": "My tools",
    "user-management": "User Management",
    "client-management": "Client Management",
    "register-client": "Register Client",
    "approve-pending-clients": "Approve pending clients",
    "client-profile": "Client Portal",
    "employee-management": "Employee Management",
    "register-employee": "Register Employee",
    "onboarding-approvals": "Onboarding & Approvals",
    "roles-permissions": "Roles & Permissions",
    "employee-training": "Employee Training",
    "matter-allocation": "Matter Allocation & Coverage",
    "employee-communications": "Employee Communications",
    "email-settings": "Email settings",
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
    "general-accounts": "General Accounts",
    "invoicing": "Invoicing",
    "generate-invoice": "Generate Invoice",
    "payments": "Payments",
    "purchasing": "Purchasing",
    "inventory": "Inventory",
    "sales": "Sales",
    "customers": "Customers",
    "suppliers": "Suppliers",
    "banking": "Banking",
    "accounting": "Accounting",
    "reporting": "Reporting",
    "client-accounts": "Client Accounts",
    "employee-accounts": "Employee Accounts",
    "payroll": "Payroll",
    "register-payroll": "Register Payroll",
    "payroll-receipt": "Payroll Receipt",
    "employee-advances": "Employee Advances",
    "employee-petty-cashbook": "Employee Petty Cashbook",
    "company-accounts": "Company Accounts",
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
    "case-calendar": "Case calendar",
    "matter-calendar": "Matter calendar",
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
        "is_about_me": leaf == "about-me",
        "is_my_blogs": leaf == "my-blogs",
        "is_my_blogs_new": leaf == "my-blogs-new",
        "is_google_drive_settings": leaf == "google-drive-settings",
        "is_finance_settings": leaf == "finance-settings",
        "is_communication_settings": leaf == "communication-settings",
        "is_company_information": leaf == "company-information",
        "is_company_profile": leaf == "company-profile",
        "is_website_template": leaf == "website-template",
        "is_practice_areas": leaf == "practice-areas",
        "is_practice_areas_new": leaf == "practice-areas-new",
        "is_company_faqs": leaf == "company-faqs",
        "is_company_faqs_new": leaf == "company-faqs-new",
        "is_company_blogs": leaf == "company-blogs",
        "is_company_gallery": leaf == "company-gallery",
        "is_company_gallery_new": leaf == "company-gallery-new",
        "is_company_terms": leaf == "company-terms",
        "is_research_blogs": leaf == "research-blogs",
        "is_latest_news": leaf == "latest-news",
        "is_settings_area": leaf in SETTINGS_AREA_SLUGS,
        "is_system_settings_area": leaf in SYSTEM_SETTINGS_AREA_SLUGS,
        "is_company_information_area": leaf in COMPANY_INFORMATION_AREA_SLUGS,
        "is_dashboard": leaf == "dashboard",
        "is_roles_module_detail": (
            leaf in SYSTEM_MODULE_SLUGS and "roles-permissions" in trail[:-1]
            and trail.index("roles-permissions") == len(trail) - 2
        ),
        "is_roles_activity_permission": _is_roles_activity_permission_trail(trail),
        "roles_module_slug": _roles_module_slug_from_trail(trail),
    }


def _roles_module_slug_from_trail(trail: list[str]) -> str | None:
    if "roles-permissions" not in trail:
        return None
    idx = trail.index("roles-permissions")
    after = trail[idx + 1 :]
    if not after or after[0] not in SYSTEM_MODULE_SLUGS:
        return None
    return after[0]


def _is_roles_activity_permission_trail(trail: list[str]) -> bool:
    if "roles-permissions" not in trail:
        return False
    idx = trail.index("roles-permissions")
    after = trail[idx + 1 :]
    return (
        len(after) >= 2
        and after[0] in SYSTEM_MODULE_SLUGS
    )


def role_activity_is_allowed(role: str, module_slug: str, activity_slug: str) -> bool:
    """Return whether a role may access an activity (default allow)."""
    from .models import RoleActivityPermission

    row = (
        RoleActivityPermission.objects.filter(
            role=role,
            module_slug=module_slug,
            activity_slug=activity_slug,
        )
        .only("is_allowed")
        .first()
    )
    if row is None:
        return True
    return bool(row.is_allowed)


def set_role_activity_permission(
    *,
    role: str,
    module_slug: str,
    activity_slug: str,
    is_allowed: bool,
    updated_by=None,
):
    from .models import RoleActivityPermission

    obj, _created = RoleActivityPermission.objects.update_or_create(
        role=role,
        module_slug=module_slug,
        activity_slug=activity_slug,
        defaults={
            "is_allowed": is_allowed,
            "updated_by": updated_by,
        },
    )
    return obj


def employee_activity_action_allowed(
    employee,
    module_slug: str,
    activity_slug: str,
    action: str,
) -> bool:
    """Return whether an employee may perform an action (default allow)."""
    if not role_activity_is_allowed(employee.role, module_slug, activity_slug):
        return False
    from .models import EmployeeActivityPermission

    row = (
        EmployeeActivityPermission.objects.filter(
            employee_id=employee.pk,
            module_slug=module_slug,
            activity_slug=activity_slug,
            action=action,
        )
        .only("is_allowed")
        .first()
    )
    if row is None:
        return True
    return bool(row.is_allowed)


ACCESS_DENIED_MODAL_SESSION_KEY = "workspace_access_denied_modal"


def set_workspace_access_denied_modal(request, *, title: str, message: str) -> None:
    request.session[ACCESS_DENIED_MODAL_SESSION_KEY] = {
        "title": title,
        "message": message,
    }


def pop_workspace_access_denied_modal(request):
    if request is None:
        return None
    return request.session.pop(ACCESS_DENIED_MODAL_SESSION_KEY, None)


def workspace_activity_action_permitted(
    employee, module_slug: str, activity_slug: str, action: str
) -> bool:
    if not module_slug:
        return True
    if not role_activity_is_allowed(employee.role, module_slug, activity_slug):
        return False
    return employee_activity_action_allowed(
        employee, module_slug, activity_slug, action
    )


def workspace_activity_access_allowed(
    employee, module_slug: str, activity_slug: str
) -> bool:
    """True when role and employee may open this activity page (view)."""
    return workspace_activity_action_permitted(
        employee, module_slug, activity_slug, "view"
    )


def workspace_action_denial_copy(
    employee, module_slug: str, activity_slug: str, action: str = "view"
) -> tuple[str, str]:
    activity_label = PAGE_TITLES.get(
        activity_slug, activity_slug.replace("-", " ").title()
    )
    action_label = PERMISSION_ACTION_LABELS.get(
        action, action.replace("-", " ").title()
    )
    if not role_activity_is_allowed(employee.role, module_slug, activity_slug):
        return (
            "Role access locked",
            f"Your role cannot use {activity_label}. "
            "Ask an administrator to enable it in Roles & Permissions.",
        )
    if action == "view":
        return (
            "Not permitted",
            f"You are not allowed to open {activity_label}. "
            "An administrator can grant access in Roles & Permissions.",
        )
    return (
        "Not permitted",
        f"You are not allowed to {action_label.lower()} in {activity_label}. "
        "An administrator can grant access in Roles & Permissions.",
    )


def workspace_activity_denial_copy(
    employee, module_slug: str, activity_slug: str
) -> tuple[str, str]:
    return workspace_action_denial_copy(
        employee, module_slug, activity_slug, "view"
    )


def redirect_if_workspace_action_denied(
    request,
    user,
    *,
    module_slug: str | None,
    activity_slug: str,
    action: str,
    redirect_to=None,
):
    from django.shortcuts import redirect

    if not module_slug:
        return None
    if workspace_activity_action_permitted(
        user, module_slug, activity_slug, action
    ):
        return None
    title, message = workspace_action_denial_copy(
        user, module_slug, activity_slug, action
    )
    set_workspace_access_denied_modal(
        request,
        title=title,
        message=message,
    )
    return redirect(redirect_to or user.dashboard_url)


def set_employee_activity_permission(
    *,
    employee_id: int,
    module_slug: str,
    activity_slug: str,
    action: str,
    is_allowed: bool,
    updated_by=None,
):
    from .models import EmployeeActivityPermission

    obj, _created = EmployeeActivityPermission.objects.update_or_create(
        employee_id=employee_id,
        module_slug=module_slug,
        activity_slug=activity_slug,
        action=action,
        defaults={
            "is_allowed": is_allowed,
            "updated_by": updated_by,
        },
    )
    return obj


def roles_activity_permission_url(user, roles_trail: list[str], module_slug: str, activity: dict) -> str:
    """Permission-management URL nested under Roles & Permissions."""
    path_slugs = activity.get("path_slugs") or [activity["slug"]]
    return user.workspace_url(*roles_trail, module_slug, *path_slugs)


# Side pages that nest under the current trail but should not stack on each other.
TRAIL_SIDE_PAGES = (
    {slug for _, slug, _ in SHARED_UTILITY_LINKS}
    | SETTINGS_AREA_SLUGS
    | RESEARCH_BLOGS_AREA_SLUGS
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

    # Shared main sidebar: Dashboard (primary chrome is in the template).
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
    notification_settings_url = workspace_reverse(
        role_slug, *extend_page_trail(trail, "notification-settings")
    )
    about_me_url = workspace_reverse(
        role_slug, *extend_page_trail(trail, "about-me")
    )
    my_blogs_url = workspace_reverse(
        role_slug, *extend_page_trail(trail, "my-blogs")
    )
    my_blogs_new_url = workspace_reverse(
        role_slug, *extend_page_trail(trail, "my-blogs-new")
    )
    theme_settings_url = workspace_reverse(
        role_slug, *extend_page_trail(trail, "theme-settings")
    )
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

    access_denied_modal = pop_workspace_access_denied_modal(request)

    # Secondary links — dashboard hubs on dashboard; otherwise page-allocated only.
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
                local_slugs = {slug for _, slug, _ in local_links}
                base_trail = [part for part in trail if part]
                while base_trail and base_trail[-1] in local_slugs:
                    base_trail.pop()
                page_nav_items = [
                    {
                        "label": label,
                        "slug": slug,
                        "url": workspace_reverse(
                            role_slug, *extend_page_trail(base_trail, slug)
                        ),
                        "icon": icon,
                        "active": active == slug,
                    }
                    for label, slug, icon in local_links
                ]
            else:
                page_nav_items = []

    _attach_page_nav_badges(page_nav_items)

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
        "access_denied_modal": access_denied_modal,
        "active_page": active,
        "crumb_parts": crumb_parts,
        "dashboard_url": dashboard_url,
        "dashboard_active": is_dashboard,
        "back_url": back_url_for_trail(role_slug, trail),
        "settings_url": settings_url,
        "notification_settings_url": notification_settings_url,
        "about_me_url": about_me_url,
        "my_blogs_url": my_blogs_url,
        "my_blogs_new_url": my_blogs_new_url,
        "theme_settings_url": theme_settings_url,
        "system_settings_url": system_settings_url,
        "settings_active": is_system_settings,
        "settings_disabled": False,
        "dashboard_disabled": False,
        "icon_back": ICON_BACK,
        "icon_home": ICON_HOME,
        "icon_users": ICON_USERS,
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
        "firm_name": get_firm_display_name(),
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
        "notification_settings_url": "#",
        "about_me_url": "#",
        "my_blogs_url": "#",
        "my_blogs_new_url": "#",
        "theme_settings_url": "#",
        "system_settings_url": "#",
        "settings_active": False,
        "settings_disabled": True,
        "icon_back": ICON_BACK,
        "icon_home": ICON_HOME,
        "icon_users": ICON_USERS,
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
        "firm_name": get_firm_display_name(),
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
