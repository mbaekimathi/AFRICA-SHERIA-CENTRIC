"""Build a printable PDF for an invoice."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


INK = colors.HexColor("#15202b")
MUTED = colors.HexColor("#5b6770")
LINE = colors.HexColor("#d8dee4")
SOFT = colors.HexColor("#f4f6f8")
ACCENT = colors.HexColor("#0f6e56")


def _money(value) -> str:
    try:
        return f"KES {float(value):,.2f}"
    except (TypeError, ValueError):
        return f"KES {value}"


def _p(text: str, style) -> Paragraph:
    return Paragraph((text or "").replace("\n", "<br/>"), style)


def _firm_header_lines(firm) -> list[str]:
    """Compact contact lines for the invoice letterhead."""
    lines = []
    phone = (getattr(firm, "phone", "") or "").strip()
    if phone:
        lines.append(phone)
    email = (getattr(firm, "email", "") or "").strip()
    if email:
        lines.append(email)
    return lines


def _firm_footer_line(firm) -> str:
    """Single compact footer line with core firm contacts."""
    parts = [getattr(firm, "display_name", "") or ""]
    phone = (getattr(firm, "phone", "") or "").strip()
    if phone:
        parts.append(phone)
    email = (getattr(firm, "email", "") or "").strip()
    if email:
        parts.append(email)
    pin = (getattr(firm, "tax_pin", "") or "").strip()
    if pin:
        parts.append(f"PIN {pin}")
    return " · ".join(part for part in parts if part)


def build_invoice_pdf(invoice, firm) -> bytes:
    """Return PDF bytes for the given invoice and firm profile."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=invoice.invoice_number,
        author=getattr(firm, "display_name", "") or "Invoice",
    )

    styles = getSampleStyleSheet()
    firm_name = ParagraphStyle(
        "FirmName",
        parent=styles["Normal"],
        fontName="Times-Bold",
        fontSize=15,
        textColor=INK,
        leading=18,
    )
    legal = ParagraphStyle(
        "Legal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        textColor=MUTED,
        leading=10,
    )
    tagline = ParagraphStyle(
        "Tagline",
        parent=legal,
        fontName="Helvetica-Oblique",
        fontSize=8.5,
    )
    meta = ParagraphStyle(
        "Meta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        textColor=MUTED,
        leading=10.5,
        alignment=TA_RIGHT,
    )
    title = ParagraphStyle(
        "InvTitle",
        parent=styles["Normal"],
        fontName="Times-Bold",
        fontSize=20,
        textColor=INK,
        alignment=TA_LEFT,
        leading=24,
    )
    right_meta = ParagraphStyle(
        "RightMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=INK,
        alignment=TA_RIGHT,
        leading=12,
    )
    label = ParagraphStyle(
        "Label",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        textColor=ACCENT,
        leading=10,
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        textColor=INK,
        leading=13,
    )
    muted_body = ParagraphStyle(
        "MutedBody",
        parent=body,
        textColor=MUTED,
        fontSize=9,
    )
    thanks = ParagraphStyle(
        "Thanks",
        parent=styles["Normal"],
        fontName="Times-Italic",
        fontSize=11,
        textColor=MUTED,
        leading=14,
        alignment=TA_CENTER,
    )
    footer_center = ParagraphStyle(
        "FooterCenter",
        parent=muted_body,
        alignment=TA_CENTER,
        fontSize=8,
        leading=11,
    )

    client = invoice.client
    header_lines = _firm_header_lines(firm)
    left_blocks = [_p(firm.display_name, firm_name)]
    city = (getattr(firm, "city", "") or "").strip()
    country = (getattr(firm, "country", "") or "").strip()
    place = ", ".join(part for part in (city, country) if part)
    if place:
        left_blocks.append(_p(place, legal))

    letterhead = Table(
        [
            [
                left_blocks,
                [_p(line, meta) for line in header_lines] or [""],
            ]
        ],
        colWidths=[110 * mm, 65 * mm],
    )
    letterhead.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 0, SOFT),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (0, 0), 8),
                ("RIGHTPADDING", (1, 0), (1, 0), 8),
            ]
        )
    )

    inv_meta = Table(
        [
            [
                [
                    _p("Invoice", title),
                    _p(invoice.invoice_number, ParagraphStyle("Num", parent=body, fontName="Helvetica-Bold")),
                ],
                [
                    _p(f"Issue date: {invoice.issue_date.strftime('%d %b %Y')}", right_meta),
                    _p(f"Due date: {invoice.due_date.strftime('%d %b %Y')}", right_meta),
                ],
            ]
        ],
        colWidths=[100 * mm, 75 * mm],
    )
    inv_meta.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -1), 0.6, LINE),
            ]
        )
    )

    bill_lines = [client.get_full_name()]
    if client.email:
        bill_lines.append(client.email)
    if client.phone:
        bill_lines.append(client.phone)

    parties = Table(
        [
            [
                [
                    _p("BILL TO", label),
                    Spacer(1, 1.5 * mm),
                    _p(
                        bill_lines[0],
                        ParagraphStyle(
                            "BillName",
                            parent=body,
                            fontName="Helvetica-Bold",
                            fontSize=11,
                        ),
                    ),
                    *[_p(line, muted_body) for line in bill_lines[1:]],
                ],
                "",
            ]
        ],
        colWidths=[120 * mm, 55 * mm],
    )
    parties.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    items = Table(
        [
            ["Description", "Qty", "Amount (KES)"],
            [
                _p(invoice.description or "—", body),
                "1",
                f"{float(invoice.amount):,.2f}",
            ],
        ],
        colWidths=[118 * mm, 18 * mm, 39 * mm],
    )
    items.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SOFT),
                ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 9.5),
                ("TEXTCOLOR", (0, 1), (-1, -1), INK),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("LINEABOVE", (0, 0), (-1, 0), 0.5, LINE),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
            ]
        )
    )

    totals = Table(
        [
            ["Subtotal", _money(invoice.amount)],
            ["Tax", _money(invoice.tax_amount)],
            ["Total due", _money(invoice.total_amount)],
        ],
        colWidths=[35 * mm, 40 * mm],
        hAlign="RIGHT",
    )
    totals.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 1), "Helvetica"),
                ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("TEXTCOLOR", (0, 0), (0, 1), MUTED),
                ("TEXTCOLOR", (1, 0), (-1, -1), INK),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LINEABOVE", (0, 2), (-1, 2), 1.2, INK),
                ("TOPPADDING", (0, 2), (-1, 2), 6),
            ]
        )
    )

    story = [
        letterhead,
        Spacer(1, 3 * mm),
        inv_meta,
        Spacer(1, 2 * mm),
        parties,
        Spacer(1, 3 * mm),
        items,
        Spacer(1, 4 * mm),
        totals,
    ]
    if invoice.notes:
        story.extend(
            [
                Spacer(1, 6 * mm),
                _p("NOTES", label),
                Spacer(1, 1 * mm),
                _p(invoice.notes, muted_body),
            ]
        )

    stamp_bits = [f"Status: {invoice.get_status_display()}"]
    approved_by = getattr(invoice, "approved_by", None)
    if approved_by:
        stamp_bits.append(f"Approved by: {approved_by.get_full_name()}")
    story.extend(
        [
            Spacer(1, 8 * mm),
            _p(" · ".join(stamp_bits), muted_body),
            Spacer(1, 8 * mm),
            HRFlowable(width="100%", thickness=0.6, color=LINE, spaceBefore=2, spaceAfter=6),
            _p("Thank you for your business.", thanks),
            Spacer(1, 2 * mm),
            _p(_firm_footer_line(firm), footer_center),
        ]
    )

    doc.build(story)
    return buffer.getvalue()
