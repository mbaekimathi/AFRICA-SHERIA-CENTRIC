"""Completeness analysis for Company Information website readiness."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import FirmCompanyInformation
from .workspace import (
    COMPANY_INFORMATION_PAGE_LINKS,
    extend_page_trail,
    workspace_reverse,
)


def _filled(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


@dataclass
class FieldCheck:
    key: str
    label: str
    filled: bool
    required: bool = True


@dataclass
class SectionAnalysis:
    slug: str
    label: str
    status: str  # complete | partial | missing | not_started
    status_label: str
    filled_count: int = 0
    total_count: int = 0
    missing_required: list[str] = field(default_factory=list)
    missing_optional: list[str] = field(default_factory=list)
    summary: str = ""
    url: str | None = None
    icon: str = ""

    @property
    def percent(self) -> int:
        if self.total_count <= 0:
            return 0 if self.status != "complete" else 100
        return int(round(100 * self.filled_count / self.total_count))


def _section_from_checks(
    *,
    slug: str,
    label: str,
    icon: str,
    checks: list[FieldCheck],
    url: str | None,
    empty_summary: str,
) -> SectionAnalysis:
    required = [c for c in checks if c.required]
    optional = [c for c in checks if not c.required]
    filled = [c for c in checks if c.filled]
    missing_required = [c.label for c in required if not c.filled]
    missing_optional = [c.label for c in optional if not c.filled]

    if not checks:
        status = "not_started"
        status_label = "Not registered"
        summary = empty_summary
    elif missing_required:
        if any(c.filled for c in required):
            status = "partial"
            status_label = "Incomplete"
            summary = f"Missing: {', '.join(missing_required)}."
        else:
            status = "missing"
            status_label = "Not registered"
            summary = f"Required: {', '.join(missing_required)}."
    elif missing_optional:
        status = "partial"
        status_label = "Almost ready"
        summary = f"Optional still empty: {', '.join(missing_optional)}."
    else:
        status = "complete"
        status_label = "Registered"
        summary = "All details for this section are registered."

    return SectionAnalysis(
        slug=slug,
        label=label,
        status=status,
        status_label=status_label,
        filled_count=len(filled),
        total_count=len(checks),
        missing_required=missing_required,
        missing_optional=missing_optional,
        summary=summary,
        url=url,
        icon=icon,
    )


def _content_section(
    *,
    slug: str,
    label: str,
    icon: str,
    url: str | None,
    summary: str,
) -> SectionAnalysis:
    return SectionAnalysis(
        slug=slug,
        label=label,
        status="not_started",
        status_label="Not registered",
        filled_count=0,
        total_count=1,
        missing_required=[label],
        summary=summary,
        url=url,
        icon=icon,
    )


def analyze_company_information(
    company: FirmCompanyInformation | None = None,
    *,
    role_slug: str,
    trail: list[str] | None = None,
) -> dict:
    """
    Score how completely company website details are registered.

    Profile and contacts are checked against FirmCompanyInformation.
    Content sections without models yet are reported as not registered.
    """
    company = company or FirmCompanyInformation.get_solo()
    trail = list(trail or ["dashboard", "company-information"])

    def url_for(slug: str) -> str:
        return workspace_reverse(role_slug, *extend_page_trail(trail, slug))

    profile_checks = [
        FieldCheck("legal_name", "Legal name", _filled(company.legal_name), True),
        FieldCheck(
            "trading_name",
            "Trading / brand name",
            _filled(company.trading_name),
            False,
        ),
        FieldCheck("tagline", "Tagline", _filled(company.tagline), True),
        FieldCheck("logo", "Firm logo", bool(company.logo), True),
        FieldCheck(
            "registration_number",
            "Registration number",
            _filled(company.registration_number),
            False,
        ),
        FieldCheck("tax_pin", "Tax PIN", _filled(company.tax_pin), False),
        FieldCheck(
            "lsk_number",
            "LSK / practising number",
            _filled(company.lsk_number),
            False,
        ),
        FieldCheck(
            "professional_credentials",
            "Professional credentials",
            _filled(company.professional_credentials),
            False,
        ),
        FieldCheck(
            "profile_images",
            "Company images",
            company.profile_images.exists(),
            False,
        ),
    ]

    website_image_checks = [
        FieldCheck(
            "website_hero_image",
            "Homepage hero image",
            bool(company.website_hero_image),
            True,
        ),
        FieldCheck(
            "website_story_image",
            "Story / origin photo",
            bool(company.website_story_image),
            False,
        ),
        FieldCheck(
            "website_about_hero_image",
            "About page hero",
            bool(company.website_about_hero_image),
            False,
        ),
        FieldCheck(
            "website_credentials_image",
            "Credentials photo",
            bool(company.website_credentials_image),
            False,
        ),
        FieldCheck(
            "website_practice_hero_image",
            "Practice page hero",
            bool(company.website_practice_hero_image),
            False,
        ),
        FieldCheck(
            "website_team_hero_image",
            "Team page hero",
            bool(company.website_team_hero_image),
            False,
        ),
        FieldCheck(
            "website_gallery_hero_image",
            "Gallery page hero",
            bool(company.website_gallery_hero_image),
            False,
        ),
        FieldCheck(
            "website_faqs_hero_image",
            "FAQs page hero",
            bool(company.website_faqs_hero_image),
            False,
        ),
        FieldCheck(
            "website_blog_hero_image",
            "Insights page hero",
            bool(company.website_blog_hero_image),
            False,
        ),
        FieldCheck(
            "website_contact_hero_image",
            "Contact page hero",
            bool(company.website_contact_hero_image),
            False,
        ),
    ]
    contact_checks = [
        FieldCheck("email", "Primary email", _filled(company.email), True),
        FieldCheck("phone", "Primary phone", _filled(company.phone), True),
        FieldCheck(
            "whatsapp_number",
            "Public WhatsApp number",
            _filled(company.whatsapp_number),
            False,
        ),
        FieldCheck("website", "Website URL", _filled(company.website), False),
        FieldCheck(
            "physical_address",
            "Physical address",
            _filled(company.physical_address),
            True,
        ),
        FieldCheck("city", "City", _filled(company.city), True),
        FieldCheck("country", "Country", _filled(company.country), True),
        FieldCheck(
            "postal_address",
            "Postal address",
            _filled(company.postal_address),
            False,
        ),
        FieldCheck(
            "business_hours",
            "Business hours",
            _filled(company.business_hours),
            True,
        ),
        FieldCheck(
            "directions",
            "Directions",
            _filled(company.directions),
            False,
        ),
        FieldCheck(
            "map_embed_url",
            "Map embed URL",
            _filled(company.map_embed_url),
            False,
        ),
        FieldCheck(
            "social_media",
            "Social media profiles",
            bool(company.social_media_links),
            False,
        ),
    ]
    about_checks = [
        FieldCheck(
            "visitor_feeling",
            "Visitor first impression",
            _filled(company.visitor_feeling),
            True,
        ),
        FieldCheck(
            "founded_year",
            "Founded year",
            _filled(company.founded_year),
            False,
        ),
        FieldCheck(
            "founded_by",
            "Founded by",
            _filled(company.founded_by),
            False,
        ),
        FieldCheck(
            "market_gap",
            "Market gap / inspiration",
            _filled(company.market_gap),
            True,
        ),
        FieldCheck(
            "milestone",
            "Milestone",
            _filled(company.milestone),
            False,
        ),
        FieldCheck(
            "service_areas",
            "Towns / cities served",
            _filled(company.service_areas),
            True,
        ),
        FieldCheck(
            "value_proposition",
            "What you do / for whom / outcome",
            _filled(company.value_proposition),
            True,
        ),
        FieldCheck(
            "future_vision",
            "5–10 year vision",
            _filled(company.future_vision),
            False,
        ),
        FieldCheck(
            "core_values",
            "Core values",
            bool(company.core_values),
            True,
        ),
    ]
    homepage_checks = [
        FieldCheck(
            "hero_headline",
            "Hero headline",
            _filled(company.hero_headline),
            False,
        ),
        FieldCheck(
            "hero_subtext",
            "Hero supporting text",
            _filled(company.hero_subtext),
            True,
        ),
        FieldCheck(
            "hero_primary_cta_label",
            "Primary CTA label",
            _filled(company.hero_primary_cta_label),
            False,
        ),
        FieldCheck(
            "consultation_blurb",
            "Consultation invitation",
            _filled(company.consultation_blurb),
            False,
        ),
    ]

    from .models import (
        Employee,
        EmployeeBlogPost,
        FirmFAQ,
        FirmGalleryImage,
        FirmPracticeArea,
        FirmTeamMember,
        FirmTestimonial,
    )

    practice_area_count = FirmPracticeArea.objects.count()
    practice_checks = [
        FieldCheck(
            "practice_areas",
            "At least one practice area",
            practice_area_count > 0,
            True,
        ),
    ]

    team_count = (
        Employee.objects.filter(
            status=Employee.Status.ACTIVE,
            website_published=True,
        ).count()
        + FirmTeamMember.objects.filter(is_published=True).count()
    )
    team_checks = [
        FieldCheck(
            "team_members",
            "At least one published team profile (employee or guest)",
            team_count > 0,
            True,
        ),
    ]

    testimonial_count = FirmTestimonial.objects.filter(is_published=True).count()
    testimonial_checks = [
        FieldCheck(
            "testimonials",
            "At least one published testimonial",
            testimonial_count > 0,
            False,
        ),
    ]

    faq_count = FirmFAQ.objects.count()
    faq_checks = [
        FieldCheck(
            "faqs",
            "At least one FAQ",
            faq_count > 0,
            True,
        ),
    ]

    published_blog_count = EmployeeBlogPost.objects.filter(
        status=EmployeeBlogPost.Status.PUBLISHED
    ).count()
    blog_checks = [
        FieldCheck(
            "published_blogs",
            "At least one published blog post",
            published_blog_count > 0,
            True,
        ),
    ]

    gallery_count = FirmGalleryImage.objects.count()
    gallery_checks = [
        FieldCheck(
            "gallery",
            "At least one gallery item",
            gallery_count > 0,
            True,
        ),
    ]

    privacy_checks = [
        FieldCheck(
            "privacy_policy",
            "Privacy policy text",
            bool((company.privacy_policy or "").strip()),
            True,
        ),
        FieldCheck(
            "legal_disclaimer",
            "Legal disclaimer",
            bool((company.legal_disclaimer or "").strip()),
            False,
        ),
    ]

    terms_checks = [
        FieldCheck(
            "terms_and_conditions",
            "Terms and conditions text",
            bool((company.terms_and_conditions or "").strip()),
            True,
        ),
    ]

    sections: list[SectionAnalysis] = []
    for label, slug, icon in COMPANY_INFORMATION_PAGE_LINKS:
        if slug == "company-profile":
            sections.append(
                _section_from_checks(
                    slug=slug,
                    label=label,
                    icon=icon,
                    checks=profile_checks,
                    url=url_for(slug),
                    empty_summary="Company profile has not been registered.",
                )
            )
        elif slug == "company-contacts":
            sections.append(
                _section_from_checks(
                    slug=slug,
                    label=label,
                    icon=icon,
                    checks=contact_checks,
                    url=url_for(slug),
                    empty_summary="Company contacts have not been registered.",
                )
            )
        elif slug == "about-company":
            sections.append(
                _section_from_checks(
                    slug=slug,
                    label=label,
                    icon=icon,
                    checks=about_checks,
                    url=url_for(slug),
                    empty_summary="About company has not been registered.",
                )
            )
        elif slug == "company-homepage":
            sections.append(
                _section_from_checks(
                    slug=slug,
                    label=label,
                    icon=icon,
                    checks=homepage_checks,
                    url=url_for(slug),
                    empty_summary="Homepage content has not been registered.",
                )
            )
        elif slug == "company-website-images":
            sections.append(
                _section_from_checks(
                    slug=slug,
                    label=label,
                    icon=icon,
                    checks=website_image_checks,
                    url=url_for(slug),
                    empty_summary="Website section images have not been uploaded yet.",
                )
            )
        elif slug == "practice-areas":
            sections.append(
                _section_from_checks(
                    slug=slug,
                    label=label,
                    icon=icon,
                    checks=practice_checks,
                    url=url_for(slug),
                    empty_summary="No practice areas have been registered yet.",
                )
            )
        elif slug == "company-team":
            sections.append(
                _section_from_checks(
                    slug=slug,
                    label=label,
                    icon=icon,
                    checks=team_checks,
                    url=url_for(slug),
                    empty_summary="No team profiles are published on the website yet.",
                )
            )
        elif slug == "company-testimonials":
            sections.append(
                _section_from_checks(
                    slug=slug,
                    label=label,
                    icon=icon,
                    checks=testimonial_checks,
                    url=url_for(slug),
                    empty_summary="No testimonials have been registered yet.",
                )
            )
        elif slug == "company-faqs":
            sections.append(
                _section_from_checks(
                    slug=slug,
                    label=label,
                    icon=icon,
                    checks=faq_checks,
                    url=url_for(slug),
                    empty_summary="No FAQs have been registered yet.",
                )
            )
        elif slug == "company-blogs":
            sections.append(
                _section_from_checks(
                    slug=slug,
                    label=label,
                    icon=icon,
                    checks=blog_checks,
                    url=url_for(slug),
                    empty_summary="No blog posts have been approved for the website yet.",
                )
            )
        elif slug == "company-gallery":
            sections.append(
                _section_from_checks(
                    slug=slug,
                    label=label,
                    icon=icon,
                    checks=gallery_checks,
                    url=url_for(slug),
                    empty_summary="No gallery media has been registered yet.",
                )
            )
        elif slug == "company-privacy":
            sections.append(
                _section_from_checks(
                    slug=slug,
                    label=label,
                    icon=icon,
                    checks=privacy_checks,
                    url=url_for(slug),
                    empty_summary="Privacy policy has not been registered yet.",
                )
            )
        elif slug == "company-terms":
            sections.append(
                _section_from_checks(
                    slug=slug,
                    label=label,
                    icon=icon,
                    checks=terms_checks,
                    url=url_for(slug),
                    empty_summary="Terms and conditions have not been registered yet.",
                )
            )
        else:
            sections.append(
                _content_section(
                    slug=slug,
                    label=label,
                    icon=icon,
                    url=url_for(slug),
                    summary=f"{label} has not been registered yet.",
                )
            )

    complete = sum(1 for s in sections if s.status == "complete")
    partial = sum(1 for s in sections if s.status == "partial")
    missing = sum(1 for s in sections if s.status in {"missing", "not_started"})
    total = len(sections)
    overall_percent = (
        int(round(sum(s.percent for s in sections) / total)) if total else 0
    )

    if overall_percent >= 90:
        readiness_label = "Website ready"
        readiness_tone = "active"
    elif overall_percent >= 50:
        readiness_label = "Partially registered"
        readiness_tone = "partial"
    elif overall_percent > 0:
        readiness_label = "Getting started"
        readiness_tone = "pending"
    else:
        readiness_label = "Not registered"
        readiness_tone = "suspended"

    action_items: list[dict] = []
    gap_groups: list[dict] = []
    next_action: dict | None = None
    for section in sections:
        if section.status == "complete":
            continue
        labels = section.missing_required or section.missing_optional
        priority = "required" if section.missing_required else "optional"
        for item in labels:
            action_items.append(
                {
                    "section": section.label,
                    "item": item,
                    "url": section.url,
                    "priority": priority,
                }
            )
        gap_groups.append(
            {
                "section": section.label,
                "url": section.url,
                "status": section.status,
                "status_label": section.status_label,
                "percent": section.percent,
                "required": list(section.missing_required),
                "optional": list(section.missing_optional),
                "summary": section.summary,
            }
        )
        if next_action is None and section.missing_required:
            next_action = {
                "section": section.label,
                "url": section.url,
                "item": section.missing_required[0],
                "count": len(section.missing_required),
                "more_count": max(0, len(section.missing_required) - 1),
            }

    required_action_count = sum(
        1 for a in action_items if a["priority"] == "required"
    )

    return {
        "company": company,
        "sections": sections,
        "overall_percent": overall_percent,
        "readiness_label": readiness_label,
        "readiness_tone": readiness_tone,
        "complete_count": complete,
        "partial_count": partial,
        "missing_count": missing,
        "section_count": total,
        "action_items": action_items,
        "gap_groups": gap_groups,
        "next_action": next_action,
        "required_action_count": required_action_count,
        "display_name": company.display_name,
        "updated_at": company.updated_at,
        "updated_by": company.updated_by,
    }
