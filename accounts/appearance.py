"""Workspace appearance catalogs for theme settings."""

from .models import Employee

# Grouped theme picker: (group_label, [(value, label, blurb), ...])
THEME_GROUPS = (
    (
        "Recommended",
        (
            (
                "default",
                "Black & White",
                "Simple charcoal and paper - quiet, balanced mono",
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
            ("managing_partner", "Partner slate", "Executive blue-slate shell"),
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
            ("azure", "Azure", "Modern sky blue accent"),
            ("emerald", "Emerald", "Fresh green, calm body"),
            ("saffron", "Saffron", "Golden accent, soft canvas"),
            ("flamingo", "Flamingo", "Rose accent, balanced contrast"),
            ("electric", "Electric", "Cyan accent for chrome"),
            ("ruby", "Ruby", "Crimson accent, clear contrast"),
            ("lime", "Lime", "Fresh lime on dark shell"),
            ("orchid", "Orchid", "Violet accent, soft surfaces"),
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


def appearance_catalog(*, include_product_alias: bool = False):
    """
    Build picker catalogs.

    `product` is an alias of `default` (both resolve to theme-product).
    Hide the duplicate from the UI unless explicitly requested.
    """
    theme_label = dict(Employee.UiTheme.choices)
    font_label = dict(Employee.UiFont.choices)
    groups = []
    for group_label, options in THEME_GROUPS:
        visible = []
        for value, label, blurb in options:
            if value == "product" and not include_product_alias:
                continue
            visible.append(
                {
                    "value": value,
                    "label": theme_label.get(value, label),
                    "blurb": blurb,
                    "preview": "product" if value in {"default", "product"} else value,
                    "featured": value in {"default", "product"},
                }
            )
        if visible:
            groups.append({"label": group_label, "options": visible})
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
