"""Company digital signature samples and context helpers."""

from __future__ import annotations

from .letterhead import ACCENT_HEX, accent_hex
from .models import CompanyDigitalSignatureSetting, FirmCompanyInformation

SIGNATURE_SAMPLES = (
    {
        "value": CompanyDigitalSignatureSetting.Template.CLASSIC,
        "label": "Classic line",
        "blurb": "Name over a signature rule with title beneath — the familiar document close.",
    },
    {
        "value": CompanyDigitalSignatureSetting.Template.SCRIPT,
        "label": "Script flourish",
        "blurb": "Handwritten-style name with a soft underline — elegant chambers correspondence.",
    },
    {
        "value": CompanyDigitalSignatureSetting.Template.FORMAL,
        "label": "Formal block",
        "blurb": "Bordered authorization block for invoices and official receipts.",
    },
    {
        "value": CompanyDigitalSignatureSetting.Template.MONOGRAM,
        "label": "Monogram mark",
        "blurb": "Large initials mark with the signatory name and title alongside.",
    },
    {
        "value": CompanyDigitalSignatureSetting.Template.STACKED,
        "label": "Stacked authority",
        "blurb": "Vertical firm → name → title → date stack for clear hierarchy.",
    },
    {
        "value": CompanyDigitalSignatureSetting.Template.COMPACT,
        "label": "Compact strip",
        "blurb": "Space-efficient horizontal strip for dense printable documents.",
    },
)

ACCENT_SAMPLES = (
    {
        "value": CompanyDigitalSignatureSetting.Accent.FOREST,
        "label": "Forest",
        "hex": ACCENT_HEX.get("forest", "#0f6e56"),
    },
    {
        "value": CompanyDigitalSignatureSetting.Accent.NAVY,
        "label": "Navy",
        "hex": ACCENT_HEX.get("navy", "#1e3a5f"),
    },
    {
        "value": CompanyDigitalSignatureSetting.Accent.CHARCOAL,
        "label": "Charcoal",
        "hex": ACCENT_HEX.get("charcoal", "#2c333a"),
    },
    {
        "value": CompanyDigitalSignatureSetting.Accent.BURGUNDY,
        "label": "Burgundy",
        "hex": ACCENT_HEX.get("burgundy", "#7a1f2b"),
    },
    {
        "value": CompanyDigitalSignatureSetting.Accent.TEAL,
        "label": "Teal",
        "hex": ACCENT_HEX.get("teal", "#0d7377"),
    },
    {
        "value": CompanyDigitalSignatureSetting.Accent.GOLD,
        "label": "Gold",
        "hex": ACCENT_HEX.get("gold", "#8a6a1f"),
    },
)


def signature_samples(*, current: str | None = None) -> list[dict]:
    current = current or CompanyDigitalSignatureSetting.Template.CLASSIC
    return [
        {
            **sample,
            "is_current": sample["value"] == current,
        }
        for sample in SIGNATURE_SAMPLES
    ]


def signature_accent_samples(*, current: str | None = None) -> list[dict]:
    current = current or CompanyDigitalSignatureSetting.Accent.NAVY
    return [
        {
            **sample,
            "is_current": sample["value"] == current,
        }
        for sample in ACCENT_SAMPLES
    ]


def get_digital_signature_setting() -> CompanyDigitalSignatureSetting:
    return CompanyDigitalSignatureSetting.get_solo()


def _initials_from_name(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "SC"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return f"{parts[0][0]}{parts[-1][0]}".upper()


def signature_render_context(
    *,
    firm: FirmCompanyInformation | None = None,
    setting: CompanyDigitalSignatureSetting | None = None,
    name: str = "",
    title: str = "",
    date_display: str = "",
) -> dict:
    """Context for the shared digital signature partial."""
    firm = firm or FirmCompanyInformation.get_solo()
    setting = setting or CompanyDigitalSignatureSetting.get_solo()
    resolved_title = (title or setting.default_title or "").strip()
    resolved_name = (name or "").strip()
    return {
        "firm": firm,
        "digital_signature": setting,
        "signature_accent_hex": accent_hex(setting.accent),
        "signature_name": resolved_name,
        "signature_title": resolved_title,
        "signature_date": date_display,
        "signature_initials": _initials_from_name(resolved_name or firm.display_name),
    }
