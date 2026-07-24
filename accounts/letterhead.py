"""Company letterhead samples and context helpers."""

from __future__ import annotations

from .models import CompanyLetterheadSetting, FirmCompanyInformation

LETTERHEAD_SAMPLES = (
    {
        "value": CompanyLetterheadSetting.Template.CLASSIC,
        "label": "Classic split",
        "blurb": "Logo and firm name on the left, contacts aligned right — the familiar invoice header.",
    },
    {
        "value": CompanyLetterheadSetting.Template.CENTERED,
        "label": "Centered seal",
        "blurb": "Centered mark and name with contacts beneath — formal correspondence style.",
    },
    {
        "value": CompanyLetterheadSetting.Template.BANNER,
        "label": "Accent banner",
        "blurb": "Full-width colour bar with firm identity and contacts in a confident strip.",
    },
    {
        "value": CompanyLetterheadSetting.Template.RULED,
        "label": "Ruled header",
        "blurb": "Clean name line with a strong accent rule — understated and print-ready.",
    },
    {
        "value": CompanyLetterheadSetting.Template.SPLIT,
        "label": "Modern split",
        "blurb": "Brand block and contacts separated by a vertical accent — contemporary chambers look.",
    },
    {
        "value": CompanyLetterheadSetting.Template.MINIMAL,
        "label": "Minimal stack",
        "blurb": "Compact left-aligned stack with a thin top accent — quiet and space-efficient.",
    },
)

ACCENT_SAMPLES = (
    {
        "value": CompanyLetterheadSetting.Accent.FOREST,
        "label": "Forest",
        "hex": "#0f6e56",
    },
    {
        "value": CompanyLetterheadSetting.Accent.NAVY,
        "label": "Navy",
        "hex": "#1e3a5f",
    },
    {
        "value": CompanyLetterheadSetting.Accent.CHARCOAL,
        "label": "Charcoal",
        "hex": "#2c333a",
    },
    {
        "value": CompanyLetterheadSetting.Accent.BURGUNDY,
        "label": "Burgundy",
        "hex": "#7a1f2b",
    },
    {
        "value": CompanyLetterheadSetting.Accent.TEAL,
        "label": "Teal",
        "hex": "#0d7377",
    },
    {
        "value": CompanyLetterheadSetting.Accent.GOLD,
        "label": "Gold",
        "hex": "#8a6a1f",
    },
)

ACCENT_HEX = {item["value"]: item["hex"] for item in ACCENT_SAMPLES}


def accent_hex(accent: str) -> str:
    return ACCENT_HEX.get(accent, ACCENT_HEX[CompanyLetterheadSetting.Accent.FOREST])


def letterhead_samples(*, current: str | None = None) -> list[dict]:
    current = current or CompanyLetterheadSetting.Template.CLASSIC
    return [
        {
            **sample,
            "is_current": sample["value"] == current,
        }
        for sample in LETTERHEAD_SAMPLES
    ]


def accent_samples(*, current: str | None = None) -> list[dict]:
    current = current or CompanyLetterheadSetting.Accent.FOREST
    return [
        {
            **sample,
            "is_current": sample["value"] == current,
        }
        for sample in ACCENT_SAMPLES
    ]


def get_letterhead_setting() -> CompanyLetterheadSetting:
    return CompanyLetterheadSetting.get_solo()


def firm_address_lines(firm: FirmCompanyInformation) -> list[str]:
    lines: list[str] = []
    physical = (firm.physical_address or "").strip()
    if physical:
        lines.extend(
            part.strip() for part in physical.splitlines() if part.strip()
        )
    postal = (firm.postal_address or "").strip()
    if postal:
        lines.append(postal)
    place = ", ".join(
        part for part in ((firm.city or "").strip(), (firm.country or "").strip()) if part
    )
    if place and place not in lines:
        lines.append(place)
    return lines


def firm_contact_lines(firm: FirmCompanyInformation) -> list[str]:
    lines: list[str] = []
    for attr in ("phone", "email", "website"):
        value = (getattr(firm, attr, "") or "").strip()
        if value:
            lines.append(value)
    return lines


def letterhead_render_context(
    *,
    firm: FirmCompanyInformation | None = None,
    setting: CompanyLetterheadSetting | None = None,
) -> dict:
    """Context keys for the shared letterhead partial (invoices, receipts, designer)."""
    firm = firm or FirmCompanyInformation.get_solo()
    setting = setting or CompanyLetterheadSetting.get_solo()
    return {
        "firm": firm,
        "letterhead": setting,
        "letterhead_address_lines": firm_address_lines(firm),
        "letterhead_contact_lines": firm_contact_lines(firm),
        "letterhead_accent_hex": accent_hex(setting.accent),
    }
