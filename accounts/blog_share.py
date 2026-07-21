"""Share a published blog post to the firm's configured social profiles."""

from __future__ import annotations

from urllib.parse import quote

from .models import FirmCompanyInformation

# field_key on FirmCompanyInformation → share behaviour
PLATFORM_SPECS = {
    "linkedin_url": {
        "id": "linkedin",
        "label": "LinkedIn",
        "supports_direct_share": True,
        "hint": "Opens LinkedIn’s share composer with this post’s link.",
    },
    "facebook_url": {
        "id": "facebook",
        "label": "Facebook",
        "supports_direct_share": True,
        "hint": "Opens Facebook’s share dialog with this post’s link.",
    },
    "instagram_url": {
        "id": "instagram",
        "label": "Instagram",
        "supports_direct_share": False,
        "hint": "Opens your Instagram profile; the post link is copied for you to paste.",
    },
    "x_url": {
        "id": "x",
        "label": "X",
        "supports_direct_share": True,
        "hint": "Opens X’s composer with this post’s title and link.",
    },
    "youtube_url": {
        "id": "youtube",
        "label": "YouTube",
        "supports_direct_share": False,
        "hint": "Opens your YouTube channel; the post link is copied for you to paste.",
    },
}

SESSION_KEY = "blog_share_intents"


def company_share_accounts(
    company: FirmCompanyInformation | None = None,
) -> list[dict]:
    """Configured social accounts available for share-on-approve."""
    company = company or FirmCompanyInformation.get_solo()
    accounts: list[dict] = []
    for link in company.social_media_links:
        field_key = link["key"]
        spec = PLATFORM_SPECS.get(field_key)
        if not spec:
            continue
        accounts.append(
            {
                "field_key": field_key,
                "platform": spec["id"],
                "label": link["label"],
                "profile_url": link["url"],
                "supports_direct_share": spec["supports_direct_share"],
                "hint": spec["hint"],
            }
        )
    return accounts


def _share_url_for_platform(
    *,
    platform: str,
    post_url: str,
    title: str,
    profile_url: str,
) -> tuple[str, str]:
    """Return (open_url, mode) where mode is 'share' or 'profile'."""
    encoded_url = quote(post_url, safe="")
    encoded_title = quote(title or "", safe="")
    if platform == "linkedin":
        return (
            f"https://www.linkedin.com/sharing/share-offsite/?url={encoded_url}",
            "share",
        )
    if platform == "facebook":
        return (
            f"https://www.facebook.com/sharer/sharer.php?u={encoded_url}",
            "share",
        )
    if platform == "x":
        return (
            f"https://twitter.com/intent/tweet?url={encoded_url}&text={encoded_title}",
            "share",
        )
    return profile_url or post_url, "profile"


def build_share_intents(
    *,
    request,
    post,
    selected_field_keys: list[str],
    company: FirmCompanyInformation | None = None,
) -> list[dict]:
    """
    Build share targets for the selected company social accounts.

    Each intent: label, url, mode ('share'|'profile'), post_url, platform.
    """
    if not selected_field_keys:
        return []
    selected = {key.strip() for key in selected_field_keys if key and key.strip()}
    if not selected:
        return []

    company = company or FirmCompanyInformation.get_solo()
    post_url = request.build_absolute_uri(post.get_absolute_url())
    title = (post.title or "").strip()
    intents: list[dict] = []

    for account in company_share_accounts(company):
        if account["field_key"] not in selected:
            continue
        open_url, mode = _share_url_for_platform(
            platform=account["platform"],
            post_url=post_url,
            title=title,
            profile_url=account["profile_url"],
        )
        if not open_url:
            continue
        intents.append(
            {
                "label": account["label"],
                "platform": account["platform"],
                "url": open_url,
                "mode": mode,
                "post_url": post_url,
                "title": title,
            }
        )
    return intents


def pop_share_intents(request) -> list[dict]:
    """Read and clear pending share intents from the session."""
    intents = request.session.pop(SESSION_KEY, None)
    if intents:
        request.session.modified = True
    return list(intents or [])


def stash_share_intents(request, intents: list[dict]) -> None:
    """Store share intents so the next page can present them."""
    if not intents:
        return
    request.session[SESSION_KEY] = intents
    request.session.modified = True
