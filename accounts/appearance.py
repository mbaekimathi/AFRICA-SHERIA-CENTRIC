"""Workspace appearance catalogs for theme settings."""

from .models import Employee

# Grouped theme picker: (group_label, [(value, label, blurb), ...])
THEME_GROUPS = (
    (
        "Recommended",
        (
            (
                "default",
                "Company default",
                "Follow the firm theme set in System settings",
            ),
            (
                "product",
                "Black & White",
                "Simple charcoal and paper - quiet, balanced mono",
            ),
        ),
    ),
    (
        "Role palettes",
        (
            ("firm_admin", "Firm indigo", "Restrained indigo for chambers"),
            ("managing_partner", "Partner slate", "Navy shell with bright panel-blue controls"),
            ("advocate", "Advocate teal", "Calm practice greens"),
            ("intern", "Intern blue", "Clear training blues"),
            ("it_support", "IT steel", "Technical cool steel"),
            ("employee", "Employee mauve", "Warm neutral mauve"),
        ),
    ),
    (
        "Studio collection",
        (
            ("midnight", "Midnight", "Full dark navy workspace"),
            ("graphite", "Graphite", "Cool industrial gray"),
            ("cedar", "Cedar", "Warm timber neutrals"),
            ("cobalt", "Cobalt", "Sharp professional blue"),
            ("olive", "Olive", "Muted botanical green"),
            ("copper", "Copper", "Burnished metal warmth"),
            ("arctic", "Arctic", "Icy coastal light"),
            ("espresso", "Espresso", "Dark roast neutrals"),
            ("jade", "Jade", "Polished teal accents"),
            ("marine", "Marine", "Deep coastal blue"),
        ),
    ),
    (
        "Accent collection",
        (
            ("sunrise", "Sunrise", "Coral accent on dark shell"),
            ("citrus", "Citrus", "Gold accent, readable ink"),
            ("azure", "Azure", "Navy shell with bright panel-blue accent"),
            ("emerald", "Emerald", "Fresh green, calm body"),
            ("saffron", "Saffron", "Golden accent, soft canvas"),
            ("flamingo", "Flamingo", "Rose accent, balanced contrast"),
            ("electric", "Electric", "Cyan accent for chrome"),
            ("ruby", "Ruby", "Crimson accent, clear contrast"),
            ("lime", "Lime", "Fresh lime on dark shell"),
            ("orchid", "Orchid", "Violet accent, soft surfaces"),
        ),
    ),
    (
        "Modern studio",
        (
            (
                "violet_glow",
                "Aurora",
                "Indigo signal, deep night shell — product-forward",
            ),
            (
                "teal_matter",
                "Cascade",
                "Fresh teal with a calm, polished desk feel",
            ),
            (
                "orange_brief",
                "Copper",
                "Warm amber accents on a refined charcoal shell",
            ),
            (
                "rose_seal",
                "Garnet",
                "Confident rose for seals, status, and focus",
            ),
            (
                "blue_docket",
                "Atlas",
                "Crisp corporate blue for dockets and dashboards",
            ),
            (
                "verdant_leaf",
                "Grove",
                "Modern green for clear, steady reading",
            ),
            (
                "amethyst_file",
                "Violet",
                "Atelier violet with luminous soft surfaces",
            ),
            (
                "indigo_list",
                "Ink",
                "Deep indigo for lists, categories, and focus work",
            ),
            (
                "ember_court",
                "Ember",
                "Energetic ember for court calendars and urgency",
            ),
            (
                "fuchsia_client",
                "Berry",
                "Contemporary berry for client-facing sessions",
            ),
            (
                "cyan_harbor",
                "Glacier",
                "Cool cyan clarity for harbor-clean workflows",
            ),
            (
                "blush_advice",
                "Blush",
                "Soft modern rose for advisory and counsel notes",
            ),
        ),
    ),
)

DENSITY_CATALOG = (
    ("comfortable", "Comfortable", "Balanced type and spacing for daily practice work"),
    ("compact", "Compact", "Tighter rows, denser lists, more on screen"),
    ("airy", "Airy", "Roomier padding for focused reading"),
)

FONT_CATALOG = (
    ("plex", "Plex Chambers", "IBM Plex Sans", "IBM Plex Sans", "Clean firm UI default"),
    ("source", "Source Editorial", "Source Sans 3", "Source Serif 4", "Clean editorial pair"),
    ("manrope", "Manrope Editorial", "Manrope", "Lora", "Modern geometric + serif"),
    ("jakarta", "Jakarta Crimson", "Plus Jakarta Sans", "Crimson Pro", "Sharp corporate polish"),
    ("dm", "DM Pair", "DM Sans", "DM Serif Display", "Matched DM family"),
    ("public", "Public News", "Public Sans", "Newsreader", "Civic & precise"),
    ("lexend", "Lexend Spectral", "Lexend", "Spectral", "Readable + scholarly"),
    ("figtree", "Figtree Display", "Figtree", "Instrument Serif", "Friendly display contrast"),
    ("sora", "Sora Brief", "Sora", "Bitter", "Brief-ready geometric"),
    ("outfit", "Outfit Literata", "Outfit", "Literata", "Contemporary literature"),
    ("syne", "Syne Vollkorn", "Syne", "Vollkorn", "Expressive counsel voice"),
    ("epilogue", "Epilogue Newsreader", "Epilogue", "Newsreader", "Newsroom clarity"),
    ("space", "Space Fraunces", "Space Grotesk", "Fraunces", "Tech display soft serif"),
    ("archivo", "Archivo Playfair", "Archivo", "Playfair Display", "Bold condensed + display"),
    ("urbanist", "Urbanist Cormorant", "Urbanist", "Cormorant Garamond", "Urban + literary"),
    ("bricolage", "Bricolage Fraunces", "Bricolage Grotesque", "Fraunces", "Characterful studio pair"),
    ("work", "Work Zilla", "Work Sans", "Zilla Slab", "Utilitarian slab mix"),
    ("albert", "Albert Cardo", "Albert Sans", "Cardo", "Neutral + classic book"),
    ("redhat", "Red Hat Stack", "Red Hat Display", "Red Hat Text", "Matched Red Hat stack"),
    ("cabin", "Cabin Alegreya", "Cabin", "Alegreya", "Humanist warmth"),
)


def resolve_theme_css_key(value: str | None) -> str:
    """Map a stored theme choice to the CSS class key (theme-*)."""
    chosen = (value or Employee.UiTheme.DEFAULT).strip()
    if not chosen or chosen in {Employee.UiTheme.DEFAULT, Employee.UiTheme.PRODUCT}:
        return Employee.UiTheme.PRODUCT
    valid = {
        key
        for key, _label in Employee.UiTheme.choices
        if key not in {Employee.UiTheme.DEFAULT, Employee.UiTheme.PRODUCT}
    }
    return chosen if chosen in valid else Employee.UiTheme.PRODUCT


# Session mirror of personal appearance (overrides company theme for this user/role only)
SESSION_APPEARANCE_KEY = "workspace_appearance"


def follows_company_theme(theme_value: str | None) -> bool:
    """True when the stored choice means 'use the firm company theme'."""
    return (theme_value or "").strip() in {"", Employee.UiTheme.DEFAULT}


def sync_session_appearance(request, user) -> None:
    """
    Keep this login session's theme in sync with the signed-in employee.

    Scoped to this user + role so it never bleeds into other accounts or roles.
    """
    if request is None or not getattr(request, "session", None):
        return
    request.session[SESSION_APPEARANCE_KEY] = {
        "user_id": user.pk,
        "role": user.role,
        "role_slug": user.role_slug,
        "ui_theme": (user.ui_theme or Employee.UiTheme.DEFAULT).strip()
        or Employee.UiTheme.DEFAULT,
        "ui_font": (user.ui_font or Employee.UiFont.PLEX).strip() or Employee.UiFont.PLEX,
        "ui_density": (user.ui_density or Employee.UiDensity.COMFORTABLE).strip()
        or Employee.UiDensity.COMFORTABLE,
    }
    request.session.modified = True


def clear_session_appearance(request) -> None:
    if request is None or not getattr(request, "session", None):
        return
    if SESSION_APPEARANCE_KEY in request.session:
        del request.session[SESSION_APPEARANCE_KEY]
        request.session.modified = True


def _session_appearance_for(user, request) -> dict | None:
    if request is None or not getattr(request, "session", None):
        return None
    snap = request.session.get(SESSION_APPEARANCE_KEY)
    if not isinstance(snap, dict):
        return None
    if snap.get("user_id") != user.pk or snap.get("role") != user.role:
        return None
    return snap


def resolve_user_workspace_theme(
    user,
    request=None,
    *,
    page_role_slug: str | None = None,
) -> str:
    """
    CSS theme for workspace pages.

    Priority on this user's own role pages:
      1. Personal theme (DB / session) when not following company default
      2. Firm company theme

    Personal overrides never change the company setting and never apply to
    other roles or other users. Off this user's role path → company theme.
    """
    from .models import CompanyThemeSetting

    own_role = user.role_slug
    on_own_role_pages = page_role_slug is None or page_role_slug == own_role

    chosen = (user.ui_theme or Employee.UiTheme.DEFAULT).strip()
    snap = _session_appearance_for(user, request)
    if snap and on_own_role_pages:
        session_theme = (snap.get("ui_theme") or "").strip()
        if session_theme:
            chosen = session_theme

    if on_own_role_pages and not follows_company_theme(chosen):
        if chosen == Employee.UiTheme.PRODUCT:
            return Employee.UiTheme.PRODUCT
        return resolve_theme_css_key(chosen)

    return CompanyThemeSetting.get_solo().resolved_theme()


def normalize_theme_value(value: str | None, *, company_mode: bool = False) -> str:
    """Map stored aliases to the picker value shown in the UI."""
    raw = (value or "").strip()
    if company_mode:
        # Firm picker: default and product both mean Black & White product shell
        if raw in {"", "product", "default"}:
            return "default"
        return raw
    # Personal picker: keep product distinct (explicit Black & White override)
    if raw in {"", "default"}:
        return "default"
    return raw


def pin_current_theme(
    groups: list[dict],
    current_value: str | None,
    *,
    company_mode: bool = False,
) -> list[dict]:
    """
    Put the active theme in a leading "Current theme" group.

    Removes the duplicate from later groups so radio values stay unique.
    """
    current = normalize_theme_value(current_value, company_mode=company_mode)
    current_option = None
    remaining: list[dict] = []
    for group in groups:
        options = []
        for option in group["options"]:
            if (
                current_option is None
                and normalize_theme_value(option["value"], company_mode=company_mode)
                == current
            ):
                scope = "Firm default theme" if company_mode else "Your active workspace theme"
                current_option = {
                    **option,
                    "featured": True,
                    "is_current": True,
                    "blurb": f"{scope} — {option['blurb']}",
                }
            else:
                options.append(option)
        if options:
            remaining.append({**group, "options": options})
    if not current_option:
        return groups
    return [{"label": "Current theme", "options": [current_option]}, *remaining]


def appearance_catalog(
    *,
    include_product_alias: bool = True,
    current_theme: str | None = None,
    company_mode: bool = False,
    company_theme_label: str | None = None,
    company_theme_preview: str | None = None,
):
    """
    Build picker catalogs.

    Personal mode: `default` = follow company theme; `product` = explicit Black & White.
    Company mode: `default` = Black & White product shell (product alias hidden).
    When `current_theme` is set, that option is pinned at the top.
    """
    theme_label = dict(Employee.UiTheme.choices)
    font_label = dict(Employee.UiFont.choices)
    firm_preview = resolve_theme_css_key(company_theme_preview or "default")
    groups = []
    for group_label, options in THEME_GROUPS:
        visible = []
        for value, label, blurb in options:
            if company_mode and value == "product":
                continue
            if not company_mode and value == "product" and not include_product_alias:
                continue

            if company_mode and value == "default":
                option_label = "Black & White"
                option_blurb = "Simple charcoal and paper - quiet, balanced mono"
                preview = "product"
            elif not company_mode and value == "default":
                option_label = "Company default"
                option_blurb = (
                    f"Firm default: {company_theme_label}"
                    if company_theme_label
                    else blurb
                )
                preview = firm_preview
            elif value == "product":
                option_label = "Black & White"
                option_blurb = blurb
                preview = "product"
            else:
                option_label = theme_label.get(value, label)
                option_blurb = blurb
                preview = value

            visible.append(
                {
                    "value": value,
                    "label": option_label,
                    "blurb": option_blurb,
                    "preview": preview,
                    "featured": value in {"default", "product"},
                    "is_current": False,
                }
            )
        if visible:
            groups.append({"label": group_label, "options": visible})
    if current_theme is not None:
        groups = pin_current_theme(
            groups, current_theme, company_mode=company_mode
        )
    return {
        "theme_groups": groups,
        "font_catalog": [
            {
                "value": value,
                "label": font_label.get(value, label),
                "sans": sans,
                "serif": serif,
                "mood": mood,
            }
            for value, label, sans, serif, mood in FONT_CATALOG
        ],
        "density_catalog": [
            {"value": value, "label": label, "blurb": blurb}
            for value, label, blurb in DENSITY_CATALOG
        ],
        "theme_count": sum(len(g["options"]) for g in groups),
        "font_count": len(FONT_CATALOG),
    }
