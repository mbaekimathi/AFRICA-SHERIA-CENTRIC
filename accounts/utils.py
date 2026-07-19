from io import BytesIO
import re
from html import escape

from django.core.files.base import ContentFile
from django.utils.safestring import mark_safe
from PIL import Image, ImageOps


def optimize_profile_photo(uploaded_file, max_size=400, quality=72):
    """Compress and resize a profile photo for fast loading (WebP)."""
    return optimize_image(uploaded_file, max_size=max_size, quality=quality)


def optimize_image(uploaded_file, max_size=1600, quality=78):
    """Compress and resize an image for web use (WebP)."""
    image = Image.open(uploaded_file)
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")
    image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    buffer = BytesIO()
    image.save(buffer, format="WEBP", quality=quality, method=6)
    buffer.seek(0)

    base_name = uploaded_file.name.rsplit(".", 1)[0]
    return ContentFile(buffer.read(), name=f"{base_name}.webp")


_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+)$")
_UL_RE = re.compile(r"^[-*]\s+(.+)$")
_OL_RE = re.compile(r"^(\d+)[.)]\s+(.+)$")


def _slugify_heading(text: str, used: dict[str, int]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"
    count = used.get(base, 0) + 1
    used[base] = count
    return base if count == 1 else f"{base}-{count}"


def render_blog_body(text: str) -> tuple[str, list[dict]]:
    """
    Convert plain blog text with light Markdown into safe HTML.

    Supports ## / ### headings, bullet lists, numbered lists, and paragraphs.
    Returns (html, toc) where toc is [{id, label, level}, ...].
    """
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return "", []

    lines = raw.split("\n")
    html_parts: list[str] = []
    toc: list[dict] = []
    used_ids: dict[str, int] = {}
    paragraph: list[str] = []
    list_type: str | None = None
    list_items: list[str] = []

    def flush_paragraph():
        nonlocal paragraph
        if paragraph:
            html_parts.append(f"<p>{' '.join(paragraph)}</p>")
            paragraph = []

    def flush_list():
        nonlocal list_type, list_items
        if list_type and list_items:
            tag = "ul" if list_type == "ul" else "ol"
            items = "".join(f"<li>{item}</li>" for item in list_items)
            html_parts.append(f"<{tag}>{items}</{tag}>")
        list_type = None
        list_items = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        heading = _HEADING_RE.match(stripped)
        if heading:
            flush_paragraph()
            flush_list()
            hashes, label = heading.group(1), heading.group(2).strip()
            level = len(hashes)
            heading_id = _slugify_heading(label, used_ids)
            safe_label = escape(label)
            html_parts.append(
                f'<h{level} id="{heading_id}">{safe_label}</h{level}>'
            )
            toc.append({"id": heading_id, "label": label, "level": level})
            continue

        ul = _UL_RE.match(stripped)
        if ul:
            flush_paragraph()
            if list_type not in (None, "ul"):
                flush_list()
            list_type = "ul"
            list_items.append(escape(ul.group(1).strip()))
            continue

        ol = _OL_RE.match(stripped)
        if ol:
            flush_paragraph()
            if list_type not in (None, "ol"):
                flush_list()
            list_type = "ol"
            list_items.append(escape(ol.group(2).strip()))
            continue

        flush_list()
        paragraph.append(escape(stripped))

    flush_paragraph()
    flush_list()
    return mark_safe("\n".join(html_parts)), toc


def whatsapp_chat_url(phone: str, message: str = "") -> str:
    """Build a wa.me chat URL from a phone number and optional prefilled message."""
    digits = re.sub(r"\D+", "", phone or "")
    if digits.startswith("0") and len(digits) >= 9:
        # Local Kenyan-style numbers → assume +254
        digits = "254" + digits.lstrip("0")
    if not digits:
        return ""
    from urllib.parse import quote

    base = f"https://wa.me/{digits}"
    text = (message or "").strip()
    if not text:
        return base
    return f"{base}?text={quote(text)}"
