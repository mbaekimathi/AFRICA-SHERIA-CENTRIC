"""Company digital stamp samples and context helpers."""

from __future__ import annotations

from .letterhead import ACCENT_HEX, accent_hex
from .models import (
    CompanyDigitalStampSetting,
    EmployeeDigitalStampSetting,
    FirmCompanyInformation,
)

STAMP_SAMPLES = (
    {
        "value": CompanyDigitalStampSetting.Template.CLASSIC,
        "label": "Classic ring",
        "blurb": "Circular seal with dashed inner ring — the familiar invoice stamp.",
    },
    {
        "value": CompanyDigitalStampSetting.Template.SQUARE,
        "label": "Square seal",
        "blurb": "Double-border square stamp — formal chambers rubber-stamp look.",
    },
    {
        "value": CompanyDigitalStampSetting.Template.OVAL,
        "label": "Oval seal",
        "blurb": "Horizontal oval seal — elegant and print-friendly.",
    },
    {
        "value": CompanyDigitalStampSetting.Template.BADGE,
        "label": "Shield badge",
        "blurb": "Shield-shaped badge for a stronger official mark.",
    },
    {
        "value": CompanyDigitalStampSetting.Template.RIBBON,
        "label": "Ribbon banner",
        "blurb": "Wide banner stamp — clear status across the document.",
    },
    {
        "value": CompanyDigitalStampSetting.Template.WAX,
        "label": "Wax stamp",
        "blurb": "Raised wax-seal style with a solid ink fill.",
    },
)

ACCENT_SAMPLES = (
    {
        "value": CompanyDigitalStampSetting.Accent.FOREST,
        "label": "Forest",
        "hex": ACCENT_HEX.get("forest", "#0f6e56"),
    },
    {
        "value": CompanyDigitalStampSetting.Accent.NAVY,
        "label": "Navy",
        "hex": ACCENT_HEX.get("navy", "#1e3a5f"),
    },
    {
        "value": CompanyDigitalStampSetting.Accent.CHARCOAL,
        "label": "Charcoal",
        "hex": ACCENT_HEX.get("charcoal", "#2c333a"),
    },
    {
        "value": CompanyDigitalStampSetting.Accent.BURGUNDY,
        "label": "Burgundy",
        "hex": ACCENT_HEX.get("burgundy", "#7a1f2b"),
    },
    {
        "value": CompanyDigitalStampSetting.Accent.TEAL,
        "label": "Teal",
        "hex": ACCENT_HEX.get("teal", "#0d7377"),
    },
    {
        "value": CompanyDigitalStampSetting.Accent.GOLD,
        "label": "Gold",
        "hex": ACCENT_HEX.get("gold", "#8a6a1f"),
    },
)


def stamp_samples(*, current: str | None = None) -> list[dict]:
    current = current or CompanyDigitalStampSetting.Template.CLASSIC
    return [
        {
            **sample,
            "is_current": sample["value"] == current,
        }
        for sample in STAMP_SAMPLES
    ]


def stamp_accent_samples(*, current: str | None = None) -> list[dict]:
    current = current or CompanyDigitalStampSetting.Accent.FOREST
    return [
        {
            **sample,
            "is_current": sample["value"] == current,
        }
        for sample in ACCENT_SAMPLES
    ]


def get_digital_stamp_setting() -> CompanyDigitalStampSetting:
    return CompanyDigitalStampSetting.get_solo()


def get_employee_digital_stamp_setting(
    employee,
) -> EmployeeDigitalStampSetting:
    return EmployeeDigitalStampSetting.for_employee(employee)


def stamp_render_context(
    *,
    firm: FirmCompanyInformation | None = None,
    setting: CompanyDigitalStampSetting | EmployeeDigitalStampSetting | None = None,
    status: str = "Issued",
    status_key: str = "issued",
    label: str = "Approved by",
    name: str = "",
    date_display: str = "",
) -> dict:
    """Context for the shared digital stamp partial."""
    firm = firm or FirmCompanyInformation.get_solo()
    setting = setting or CompanyDigitalStampSetting.get_solo()
    return {
        "firm": firm,
        "digital_stamp": setting,
        "stamp_accent_hex": accent_hex(setting.accent),
        "stamp_status": status,
        "stamp_status_key": status_key,
        "stamp_label": label,
        "stamp_name": name,
        "stamp_date": date_display,
    }
