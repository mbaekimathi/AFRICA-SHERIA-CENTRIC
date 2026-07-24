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

FOOTER_SAMPLES = (
    {
        "value": CompanyLetterheadSetting.FooterTemplate.COMPACT,
        "label": "Compact line",
        "blurb": "Single footer line with address parts joined — quiet and space-efficient.",
    },
    {
        "value": CompanyLetterheadSetting.FooterTemplate.CENTERED,
        "label": "Centered stack",
        "blurb": "Thanks and address stacked and centered under the document.",
    },
    {
        "value": CompanyLetterheadSetting.FooterTemplate.RULED,
        "label": "Ruled footer",
        "blurb": "Accent rule above a clean address block — formal close.",
    },
    {
        "value": CompanyLetterheadSetting.FooterTemplate.STACKED,
        "label": "Left stack",
        "blurb": "Left-aligned address lines under the thanks note.",
    },
    {
        "value": CompanyLetterheadSetting.FooterTemplate.SPLIT,
        "label": "Split thanks",
        "blurb": "Thanks on the left, address details on the right.",
    },
    {
        "value": CompanyLetterheadSetting.FooterTemplate.BAR,
        "label": "Accent bar",
        "blurb": "Full-width accent strip carrying the address when enabled.",
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

CONTACT_FIELDS = (
    ("email", "", "email"),
    ("phone", "", "phone"),
)

ADDRESS_FIELDS = (
    ("physical_address", "", "physical_address"),
    ("postal_address", "", "postal_address"),
    ("city", "", "city"),
    ("country", "", "country"),
)


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


def footer_samples(*, current: str | None = None) -> list[dict]:
    current = current or CompanyLetterheadSetting.FooterTemplate.COMPACT
    return [
        {
            **sample,
            "is_current": sample["value"] == current,
        }
        for sample in FOOTER_SAMPLES
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


def _field_value(firm: FirmCompanyInformation, attr: str) -> str:
    raw = getattr(firm, attr, "") or ""
    if attr == "physical_address":
        parts = [part.strip() for part in str(raw).splitlines() if part.strip()]
        return ", ".join(parts) if parts else ""
    return str(raw).strip()


def firm_detail_rows(
    firm: FirmCompanyInformation,
    *,
    include_contacts: bool = True,
    include_address: bool = True,
) -> list[dict]:
    """Contact and address rows for letterhead / footer rendering."""
    rows: list[dict] = []
    if include_contacts:
        for key, label, attr in CONTACT_FIELDS:
            value = _field_value(firm, attr)
            if value:
                rows.append(
                    {
                        "key": key,
                        "label": label,
                        "value": value,
                        "kind": "contact",
                    }
                )
    if include_address:
        for key, label, attr in ADDRESS_FIELDS:
            value = _field_value(firm, attr)
            if value:
                rows.append(
                    {
                        "key": key,
                        "label": label,
                        "value": value,
                        "kind": "address",
                    }
                )
    return rows


def firm_address_lines(firm: FirmCompanyInformation) -> list[str]:
    """Plain address values for footer / PDF helpers."""
    return [
        row["value"]
        for row in firm_detail_rows(firm, include_contacts=False, include_address=True)
    ]


def firm_contact_lines(firm: FirmCompanyInformation) -> list[str]:
    """Plain contact values for letterhead / PDF helpers."""
    return [
        row["value"]
        for row in firm_detail_rows(firm, include_contacts=True, include_address=False)
    ]


def firm_address_compact(firm: FirmCompanyInformation) -> str:
    """Single-line address for compact footers."""
    return " · ".join(firm_address_lines(firm))


def letterhead_render_context(
    *,
    firm: FirmCompanyInformation | None = None,
    setting: CompanyLetterheadSetting | None = None,
) -> dict:
    """Context keys for letterhead + footer partials (invoices, receipts, designer)."""
    from .models import (
        CompanyDigitalSignatureSetting,
        CompanyDigitalStampSetting,
    )

    firm = firm or FirmCompanyInformation.get_solo()
    setting = setting or CompanyLetterheadSetting.get_solo()
    stamp_setting = CompanyDigitalStampSetting.get_solo()
    signature_setting = CompanyDigitalSignatureSetting.get_solo()
    contact_rows = firm_detail_rows(
        firm,
        include_contacts=True,
        include_address=False,
    )
    address_rows = firm_detail_rows(
        firm,
        include_contacts=False,
        include_address=True,
    )
    address_lines = [row["value"] for row in address_rows]
    return {
        "firm": firm,
        "letterhead": setting,
        "letterhead_detail_rows": contact_rows,
        "letterhead_contact_rows": contact_rows,
        "letterhead_address_rows": address_rows,
        "letterhead_address_lines": address_lines,
        "letterhead_contact_lines": [row["value"] for row in contact_rows],
        "letterhead_address_compact": " · ".join(address_lines),
        "letterhead_accent_hex": accent_hex(setting.accent),
        "digital_stamp": stamp_setting,
        "stamp_accent_hex": accent_hex(stamp_setting.accent),
        "digital_signature": signature_setting,
        "signature_accent_hex": accent_hex(signature_setting.accent),
    }
