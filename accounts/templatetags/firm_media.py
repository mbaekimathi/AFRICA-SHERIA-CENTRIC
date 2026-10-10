from pathlib import Path

from django import template
from django.conf import settings
from django.templatetags.static import static

from accounts.utils import stored_image_url

register = template.Library()


def _static_file_version(path: str) -> str:
    candidates = []
    for directory in getattr(settings, "STATICFILES_DIRS", []):
        candidates.append(Path(directory) / path)
    static_root = getattr(settings, "STATIC_ROOT", None)
    if static_root:
        candidates.append(Path(static_root) / path)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(int(candidate.stat().st_mtime))
        except OSError:
            continue
    return "1"


@register.simple_tag
def static_bust(path: str) -> str:
    """Static URL with ?v=<mtime> so browsers always fetch edited assets."""
    url = static(path)
    version = _static_file_version(path)
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}v={version}"

_ICON_RULES = (
    (("family", "matrimonial", "succession", "probate", "children"), "family"),
    (("convey", "property", "land", "title", "estate"), "land"),
    (("commercial", "corporate", "company", "business"), "commercial"),
    (("employ", "labour", "labor", "workplace"), "employment"),
    (("dispute", "adr", "mediat", "arbitrat"), "adr"),
    (("litigat", "civil", "court", "suit"), "litigation"),
)


@register.filter
def stored_media_url(file_field):
    return stored_image_url(file_field)


@register.filter
def firm_media_pick(pool, index=0):
    """Pick a posted firm image from the media pool by rotating index."""
    if not pool:
        return ""
    try:
        i = int(index or 0)
    except (TypeError, ValueError):
        i = 0
    return pool[i % len(pool)]


@register.filter
def firm_stock(index=0):
    """Deprecated: stock photos removed — use firm_media_pool|firm_media_pick."""
    return ""


@register.filter
def practice_icon(name):
    """Map a practice area name to an icon key used by _icons.html."""
    text = (name or "").lower()
    for needles, icon in _ICON_RULES:
        if any(n in text for n in needles):
            return icon
    return "scales"
