from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import Q, Value
from django.db.models.functions import Concat
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

import calendar as calendar_mod
import json
import logging
from collections import defaultdict
from datetime import date
from django.utils.safestring import mark_safe
from .appearance import appearance_catalog
from .client_auth import (
    get_client,
    login_client,
    logout_client,
    redirect_for_client,
)
from .client_portal import client_home_url, client_portal_context
from .country_codes import country_name
from .forms import (
    AboutMeForm,
    AppearanceSettingsForm,
    ApproveCaseForm,
    ApproveMatterForm,
    CasePartyEditFormSet,
    CasePartyFormSet,
    ClientLoginForm,
    ClientOnboardingForm,
    ClientSignUpForm,
    CompanyInformationForm,
    CompanyContactsForm,
    AboutCompanyForm,
    CompanyTermsForm,
    CourtAttendanceAdvocateFormSet,
    CourtAttendanceBringUpItemFormSet,
    CreateGoogleDocumentForm,
    CreateCaseTaskForm,
    CreateMatterTaskForm,
    EmployeeBlogForm,
    EmployeeOnboardingForm,
    FAQForm,
    FinanceSettingsForm,
    GalleryImageForm,
    GenerateInvoiceForm,
    InvoiceStkPaymentForm,
    LoginForm,
    MatterPartyEditFormSet,
    MatterPartyFormSet,
    NotificationSettingsForm,
    PracticeAreaForm,
    ProfileSettingsForm,
    RegisterCaseForm,
    RegisterMatterForm,
    RejectTaskForm,
    AcceptTaskForm,
    RenameDocumentForm,
    SignUpForm,
    UpdateCourtAttendanceForm,
    UpdateMatterAttendanceForm,
    UploadDocumentForm,
    WebsiteTemplateForm,
)
from .google_auth import GoogleAuthError, verify_google_id_token
from .google_drive import (
    GoogleDriveAPIError,
    GoogleDriveOAuthError,
    begin_oauth,
    bootstrap_drive_folders,
    build_redirect_uri,
    can_start_google_oauth,
    create_google_workspace_file,
    disconnect_google_drive,
    ensure_case_drive_folder,
    ensure_matter_drive_folder,
    exchange_code,
    firm_root_folder_name,
    google_oauth_configured,
    is_loopback_host,
    is_private_lan_host,
    pop_oauth_return,
    rename_drive_file,
    trash_drive_file,
    upload_drive_file,
    validate_oauth_state,
)
from .case_audit import build_case_audit_events, case_audit_summary
from .document_tracking import (
    detect_session_behavior,
    end_open_session,
    log_document_activity,
    start_open_session,
    sync_google_document_content,
)
from .client_notifications import (
    client_notifications_payload,
    notify_invoice_issued,
)
from .models import (
    CaseParty,
    CaseTask,
    Client,
    ClientNotification,
    CourtAttendance,
    CourtAttendanceAdvocate,
    CourtAttendanceBringUpItem,
    Document,
    DocumentActivity,
    DocumentContentSnapshot,
    DocumentOpenSession,
    Employee,
    EmployeeBlogPost,
    FinanceSettings,
    FirmCompanyInformation,
    FirmCompanyProfileImage,
    FirmFAQ,
    FirmGalleryImage,
    FirmPracticeArea,
    FirmPracticeAreaImage,
    GoogleDriveConnection,
    Invoice,
    LitigationCase,
    MatterAttendance,
    MatterParty,
    MatterTask,
    NonLitigationMatter,
    Notification,
    WebsiteTemplateSetting,
)
from .notifications import (
    notifications_payload,
    notify_case_task,
    notify_google_drive_disconnected,
    notify_matter_task,
    notify_task_accepted,
    notify_task_rejected,
)
from .workspace import (
    assign_session_greeting,
    attach_greeting_cookie,
    employee_preactive_context,
    extend_page_trail,
    litigation_case_nav_items,
    LITIGATION_CASE_ACTION_SLUGS,
    mark_session_start,
    non_litigation_matter_nav_items,
    NON_LITIGATION_MATTER_ACTION_SLUGS,
    PAGE_LOCAL_LINKS,
    PAGE_TITLES,
    resolve_workspace_page,
    workspace_context,
)
from .utils import optimize_image, render_blog_body, whatsapp_chat_url

logger = logging.getLogger(__name__)


def _firm_meta_description(company: FirmCompanyInformation, firm_name: str) -> str:
    """Build a Google-friendly meta description from company fields."""
    parts = []
    tagline = (company.tagline or "").strip()
    value = (company.value_proposition or "").strip()
    city = (company.city or "").strip()
    country = (company.country or "").strip()
    if tagline:
        parts.append(tagline.rstrip("."))
    elif value:
        parts.append(value.rstrip(".")[:140])
    else:
        parts.append(f"Professional legal counsel from {firm_name}")
    location = ", ".join(p for p in (city, country) if p)
    if location:
        parts.append(f"Based in {location}")
    phone = (company.phone or "").strip()
    if phone:
        parts.append(f"Call {phone}")
    text = ". ".join(parts).strip()
    if not text.endswith("."):
        text += "."
    return text[:160]


def _firm_organization_json_ld(request, company: FirmCompanyInformation, firm_name: str):
    """Organization / LegalService structured data for the firm homepage."""
    home_url = request.build_absolute_uri(reverse("accounts:home"))
    data: dict = {
        "@context": "https://schema.org",
        "@type": ["LegalService", "Organization"],
        "name": firm_name,
        "url": home_url,
        "description": _firm_meta_description(company, firm_name),
    }
    if company.legal_name and company.legal_name.strip() != firm_name:
        data["legalName"] = company.legal_name.strip()
    if company.email:
        data["email"] = company.email.strip()
    if company.phone:
        data["telephone"] = company.phone.strip()
    if company.website:
        same_as = [company.website.strip()]
        same_as.extend(link["url"] for link in company.social_media_links)
        data["sameAs"] = same_as
    address_parts = {
        "@type": "PostalAddress",
        "addressCountry": (company.country or "KE").strip() or "KE",
    }
    if company.physical_address:
        address_parts["streetAddress"] = company.physical_address.strip()
    if company.city:
        address_parts["addressLocality"] = company.city.strip()
    if company.postal_address:
        address_parts["postalCode"] = company.postal_address.strip()
    if company.physical_address or company.city:
        data["address"] = address_parts
    if company.founded_year:
        data["foundingDate"] = str(company.founded_year)
    areas = (company.service_areas or "").strip()
    if areas:
        data["areaServed"] = areas
    return data


def _firm_faq_json_ld(faqs) -> dict | None:
    if not faqs:
        return None
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": faq.question,
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": faq.answer,
                },
            }
            for faq in faqs
        ],
    }


class HomeView(View):
    """Public homepage — Sheria Centric product site or company firm site."""

    product_template = "accounts/home.html"
    company_template = "accounts/company_home.html"

    def get(self, request):
        setting = WebsiteTemplateSetting.get_solo()
        if setting.uses_company_website:
            company = FirmCompanyInformation.get_solo()
            firm_name = company.display_name
            practice_areas = list(
                FirmPracticeArea.objects.prefetch_related("images").order_by(
                    "rank", "name"
                )
            )
            faqs = list(FirmFAQ.objects.order_by("rank", "question")[:4])
            gallery_items = list(
                FirmGalleryImage.objects.order_by("rank", "title")[:4]
            )
            blog_posts = list(
                EmployeeBlogPost.objects.filter(
                    status=EmployeeBlogPost.Status.PUBLISHED
                )
                .select_related("author")
                .order_by("-published_at", "-updated_at")[:3]
            )
            meta_description = _firm_meta_description(company, firm_name)
            canonical_url = request.build_absolute_uri(reverse("accounts:home"))
            json_ld_graph = [_firm_organization_json_ld(request, company, firm_name)]
            whatsapp_url = ""
            if company.phone:
                whatsapp_url = whatsapp_chat_url(
                    company.phone,
                    f"Hello {firm_name}, I would like to enquire about legal services.",
                )
            slides = _build_firm_slides(
                request, company, firm_name, practice_areas, gallery_items
            )
            return render(
                request,
                self.company_template,
                {
                    "company": company,
                    "firm_name": firm_name,
                    "practice_areas": practice_areas,
                    "faqs": faqs,
                    "gallery_items": gallery_items,
                    "blog_posts": blog_posts,
                    "slides": slides,
                    "has_terms": bool((company.terms_and_conditions or "").strip()),
                    "meta_description": meta_description,
                    "canonical_url": canonical_url,
                    "json_ld": mark_safe(json.dumps(json_ld_graph, ensure_ascii=False)),
                    "whatsapp_url": whatsapp_url,
                    "nav_active": "home",
                    "firm_nav_solid": False,
                    "google_client_id": getattr(settings, "GOOGLE_CLIENT_ID", ""),
                },
            )
        return render(
            request,
            self.product_template,
            {
                "google_client_id": getattr(settings, "GOOGLE_CLIENT_ID", ""),
            },
        )


def _build_firm_slides(request, company, firm_name, practice_areas, gallery_items):
    """Hero slideshow slides from firm profile, practice areas, and gallery."""
    slides = [
        {
            "eyebrow": "Law firm · Kajiado",
            "title": firm_name,
            "text": (
                (company.visitor_feeling or company.tagline or company.value_proposition)
                or "Practical counsel for families, land, and business."
            ),
            "cta_label": "Explore practice areas",
            "cta_url": reverse("accounts:firm_practice_list"),
            "cta2_label": "Contact the firm",
            "cta2_url": reverse("accounts:firm_contact"),
            "tone": "navy",
            "image_url": "",
        }
    ]
    tones = ("teal", "ink", "slate", "navy")
    for i, area in enumerate(practice_areas[:5]):
        image_url = ""
        if area.main_image and area.main_image.image:
            image_url = area.main_image.image.url
        slides.append(
            {
                "eyebrow": "Practice area",
                "title": area.name,
                "text": area.summary or area.details[:180] or f"Counsel in {area.name}.",
                "cta_label": "Open this practice area",
                "cta_url": area.get_absolute_url(),
                "cta2_label": "All practice areas",
                "cta2_url": reverse("accounts:firm_practice_list"),
                "tone": tones[i % len(tones)],
                "image_url": image_url,
            }
        )
    for i, item in enumerate(gallery_items[:3]):
        image_url = item.image.url if item.image else ""
        slides.append(
            {
                "eyebrow": "Inside the chambers",
                "title": item.title,
                "text": item.caption or f"A look at {firm_name}.",
                "cta_label": "View gallery item",
                "cta_url": item.get_absolute_url(),
                "cta2_label": "Full gallery",
                "cta2_url": reverse("accounts:firm_gallery_list"),
                "tone": tones[(i + 1) % len(tones)],
                "image_url": image_url,
            }
        )
    return slides


def _public_firm_context(nav_active: str = "", solid_nav: bool = True):
    company = FirmCompanyInformation.get_solo()
    firm_name = company.display_name
    whatsapp_url = ""
    if company.phone:
        whatsapp_url = whatsapp_chat_url(
            company.phone,
            f"Hello {firm_name}, I would like to enquire about legal services.",
        )
    return {
        "company": company,
        "firm_name": firm_name,
        "has_terms": bool((company.terms_and_conditions or "").strip()),
        "whatsapp_url": whatsapp_url,
        "nav_active": nav_active,
        "firm_nav_solid": solid_nav,
    }


def _firm_page_render(request, template_name, nav_active, page_title, meta_description, extra=None):
    context = _public_firm_context(nav_active=nav_active, solid_nav=True)
    context.update(
        {
            "page_title": page_title,
            "meta_description": meta_description,
            "canonical_url": request.build_absolute_uri(request.path),
        }
    )
    if extra:
        context.update(extra)
    return render(request, template_name, context)


class FirmAboutView(View):
    template_name = "accounts/firm/about.html"

    def get(self, request):
        company = FirmCompanyInformation.get_solo()
        return _firm_page_render(
            request,
            self.template_name,
            "about",
            "About the firm",
            f"Learn about {company.display_name} — our story, values, and service areas in Kajiado County.",
        )


class FirmPracticeListView(View):
    template_name = "accounts/firm/practice_list.html"

    def get(self, request):
        areas = list(
            FirmPracticeArea.objects.prefetch_related("images").order_by("rank", "name")
        )
        return _firm_page_render(
            request,
            self.template_name,
            "practice",
            "Practice areas",
            f"Practice areas at {FirmCompanyInformation.get_solo().display_name} — land, family, commercial, and more.",
            {"practice_areas": areas},
        )


class FirmPracticeDetailView(View):
    template_name = "accounts/firm/practice_detail.html"

    def get(self, request, slug):
        area = get_object_or_404(
            FirmPracticeArea.objects.prefetch_related("images"),
            slug=slug,
        )
        related = list(
            FirmPracticeArea.objects.exclude(pk=area.pk).order_by("rank", "name")[:4]
        )
        firm_name = FirmCompanyInformation.get_solo().display_name
        return _firm_page_render(
            request,
            self.template_name,
            "practice",
            area.name,
            (area.summary or f"{area.name} counsel from {firm_name}.")[:160],
            {"area": area, "related_areas": related},
        )


class FirmGalleryListView(View):
    template_name = "accounts/firm/gallery_list.html"

    def get(self, request):
        items = list(FirmGalleryImage.objects.order_by("rank", "title"))
        return _firm_page_render(
            request,
            self.template_name,
            "gallery",
            "Gallery",
            f"Inside the chambers of {FirmCompanyInformation.get_solo().display_name}.",
            {"gallery_items": items},
        )


class FirmGalleryDetailView(View):
    template_name = "accounts/firm/gallery_detail.html"

    def get(self, request, slug):
        item = get_object_or_404(FirmGalleryImage, slug=slug)
        siblings = list(
            FirmGalleryImage.objects.exclude(pk=item.pk).order_by("rank", "title")[:6]
        )
        return _firm_page_render(
            request,
            self.template_name,
            "gallery",
            item.title,
            (item.caption or item.title)[:160],
            {"item": item, "siblings": siblings},
        )


class FirmFaqsView(View):
    template_name = "accounts/firm/faqs.html"

    def get(self, request):
        faqs = list(FirmFAQ.objects.order_by("rank", "question"))
        faq_ld = _firm_faq_json_ld(faqs)
        return _firm_page_render(
            request,
            self.template_name,
            "faqs",
            "Frequently asked questions",
            f"Common questions about working with {FirmCompanyInformation.get_solo().display_name}.",
            {
                "faqs": faqs,
                "json_ld": mark_safe(json.dumps(faq_ld, ensure_ascii=False))
                if faq_ld
                else "",
            },
        )


class FirmContactView(View):
    template_name = "accounts/firm/contact.html"

    def get(self, request):
        company = FirmCompanyInformation.get_solo()
        return _firm_page_render(
            request,
            self.template_name,
            "contact",
            "Contact",
            f"Contact {company.display_name} in {company.city or 'Kajiado'} — phone, email, WhatsApp, and chambers address.",
        )


class FirmTermsView(View):
    """Public terms and conditions page for the company website."""

    template_name = "accounts/firm/terms.html"

    def get(self, request):
        context = _public_firm_context(nav_active="terms", solid_nav=True)
        company = context["company"]
        terms = (company.terms_and_conditions or "").strip()
        context.update(
            {
                "page_title": "Terms and conditions",
                "meta_description": (
                    f"Terms and conditions for clients and website visitors of "
                    f"{context['firm_name']}."
                ),
                "canonical_url": request.build_absolute_uri(
                    reverse("accounts:firm_terms")
                ),
                "terms_text": terms
                or (
                    f"Terms for {context['firm_name']} will be published here shortly. "
                    f"For enquiries, please use the contact page."
                ),
            }
        )
        return render(request, self.template_name, context)


class RobotsTxtView(View):
    """robots.txt pointing search engines at the firm sitemap."""

    def get(self, request):
        sitemap_url = request.build_absolute_uri(reverse("accounts:blog_sitemap"))
        body = "\n".join(
            [
                "User-agent: *",
                "Allow: /",
                "Disallow: /employee/",
                "Disallow: /client/",
                "Disallow: /workspace/",
                "Disallow: /dashboard/",
                "Disallow: /it-support/",
                "Disallow: /admin/",
                f"Sitemap: {sitemap_url}",
                "",
            ]
        )
        return HttpResponse(body, content_type="text/plain")


class BlogListView(View):
    """Public standalone blog index for published posts."""

    template_name = "accounts/blog_list.html"

    def get(self, request):
        posts = list(
            EmployeeBlogPost.objects.filter(status=EmployeeBlogPost.Status.PUBLISHED)
            .select_related("author")
            .order_by("-published_at", "-updated_at")
        )
        context = _public_firm_context(nav_active="blog", solid_nav=True)
        context.update(
            {
                "blog_posts": posts,
                "page_title": "Insights & blogs",
                "meta_description": (
                    f"Legal insights and articles from {context['firm_name']}."
                ),
            }
        )
        return render(request, self.template_name, context)


class BlogDetailView(View):
    """Public standalone blog post page with SEO meta and structured data."""

    template_name = "accounts/blog_detail.html"

    def get(self, request, slug):
        post = get_object_or_404(
            EmployeeBlogPost.objects.select_related("author"),
            slug=slug,
            status=EmployeeBlogPost.Status.PUBLISHED,
        )
        related = list(
            EmployeeBlogPost.objects.filter(status=EmployeeBlogPost.Status.PUBLISHED)
            .exclude(pk=post.pk)
            .order_by("-published_at", "-updated_at")[:3]
        )
        context = _public_firm_context(nav_active="blog", solid_nav=True)
        absolute_url = request.build_absolute_uri(post.get_absolute_url())
        cover_url = (
            request.build_absolute_uri(post.cover_image.url)
            if post.cover_image
            else ""
        )
        body_html, toc = render_blog_body(post.body)
        author = post.author
        author_bio = (getattr(author, "about_me", "") or "").strip()
        company = context["company"]
        company_website = (getattr(company, "website", "") or "").strip()
        author_more = list(
            EmployeeBlogPost.objects.filter(
                author=author,
                status=EmployeeBlogPost.Status.PUBLISHED,
            )
            .exclude(pk=post.pk)
            .order_by("-published_at", "-updated_at")[:3]
        )
        author_published_count = (
            EmployeeBlogPost.objects.filter(
                author=author,
                status=EmployeeBlogPost.Status.PUBLISHED,
            ).count()
        )
        context.update(
            {
                "post": post,
                "related_posts": related,
                "page_title": post.effective_meta_title,
                "meta_description": post.effective_meta_description,
                "canonical_url": absolute_url,
                "og_image_url": cover_url,
                "body_html": body_html,
                "toc": toc,
                "reading_time": post.reading_time_minutes,
                "author_initials": post.author_initials,
                "author_bio": author_bio[:600],
                "author_role": author.get_role_display(),
                "author_published_count": author_published_count,
                "author_more_posts": author_more,
                "company_website": company_website,
                "company_tagline": (getattr(company, "tagline", "") or "").strip(),
                "company_email": (getattr(company, "email", "") or "").strip(),
                "company_phone": (getattr(company, "phone", "") or "").strip(),
                "company_city": (getattr(company, "city", "") or "").strip(),
                "whatsapp_url": whatsapp_chat_url(
                    getattr(company, "phone", "") or "",
                    (
                        f"Hello {context['firm_name']}, I read your article "
                        f"“{post.title}” ({absolute_url}) and would like to enquire about this."
                    ),
                ),
                "share_url": absolute_url,
                "json_ld": mark_safe(
                    json.dumps(
                        {
                            "@context": "https://schema.org",
                            "@type": "BlogPosting",
                            "headline": post.effective_meta_title,
                            "description": post.effective_meta_description,
                            "datePublished": (
                                post.published_at.isoformat()
                                if post.published_at
                                else ""
                            ),
                            "dateModified": post.updated_at.isoformat(),
                            "author": {
                                "@type": "Person",
                                "name": post.author.get_full_name(),
                                "jobTitle": author.get_role_display(),
                            },
                            "publisher": {
                                "@type": "Organization",
                                "name": context["firm_name"],
                                "url": company_website
                                or request.build_absolute_uri(
                                    reverse("accounts:home")
                                ),
                            },
                            "mainEntityOfPage": absolute_url,
                            "image": [cover_url] if cover_url else [],
                            "keywords": ", ".join(post.tag_list),
                            "wordCount": post.word_count,
                            "timeRequired": f"PT{post.reading_time_minutes}M",
                        }
                    )
                ),
            }
        )
        return render(request, self.template_name, context)


class BlogSitemapView(View):
    """XML sitemap of public firm pages and published blog posts."""

    def get(self, request):
        posts = (
            EmployeeBlogPost.objects.filter(status=EmployeeBlogPost.Status.PUBLISHED)
            .order_by("-published_at", "-updated_at")
            .only("slug", "updated_at", "published_at")
        )
        company = FirmCompanyInformation.get_solo()
        practice_areas = FirmPracticeArea.objects.order_by("rank", "name").only(
            "slug", "updated_at"
        )
        gallery_items = FirmGalleryImage.objects.order_by("rank", "title").only(
            "slug", "updated_at"
        )
        urls = [
            {
                "loc": request.build_absolute_uri(reverse("accounts:home")),
                "lastmod": company.updated_at,
                "priority": "1.0",
            },
            {
                "loc": request.build_absolute_uri(reverse("accounts:firm_about")),
                "lastmod": company.updated_at,
                "priority": "0.8",
            },
            {
                "loc": request.build_absolute_uri(
                    reverse("accounts:firm_practice_list")
                ),
                "lastmod": None,
                "priority": "0.9",
            },
            {
                "loc": request.build_absolute_uri(
                    reverse("accounts:firm_gallery_list")
                ),
                "lastmod": None,
                "priority": "0.7",
            },
            {
                "loc": request.build_absolute_uri(reverse("accounts:firm_faqs")),
                "lastmod": None,
                "priority": "0.7",
            },
            {
                "loc": request.build_absolute_uri(reverse("accounts:firm_contact")),
                "lastmod": company.updated_at,
                "priority": "0.8",
            },
            {
                "loc": request.build_absolute_uri(reverse("accounts:blog_list")),
                "lastmod": None,
                "priority": "0.8",
            },
        ]
        if (company.terms_and_conditions or "").strip():
            urls.append(
                {
                    "loc": request.build_absolute_uri(reverse("accounts:firm_terms")),
                    "lastmod": company.updated_at,
                    "priority": "0.3",
                }
            )
        for area in practice_areas:
            if area.slug:
                urls.append(
                    {
                        "loc": request.build_absolute_uri(
                            reverse(
                                "accounts:firm_practice_detail",
                                kwargs={"slug": area.slug},
                            )
                        ),
                        "lastmod": area.updated_at,
                        "priority": "0.75",
                    }
                )
        for item in gallery_items:
            if item.slug:
                urls.append(
                    {
                        "loc": request.build_absolute_uri(
                            reverse(
                                "accounts:firm_gallery_detail",
                                kwargs={"slug": item.slug},
                            )
                        ),
                        "lastmod": item.updated_at,
                        "priority": "0.5",
                    }
                )
        for post in posts:
            urls.append(
                {
                    "loc": request.build_absolute_uri(
                        reverse("accounts:blog_detail", kwargs={"slug": post.slug})
                    ),
                    "lastmod": (post.updated_at or post.published_at),
                    "priority": "0.7",
                }
            )
        xml_parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ]
        for item in urls:
            xml_parts.append("<url>")
            xml_parts.append(f"<loc>{item['loc']}</loc>")
            if item["lastmod"]:
                xml_parts.append(
                    f"<lastmod>{item['lastmod'].date().isoformat()}</lastmod>"
                )
            if item.get("priority"):
                xml_parts.append(f"<priority>{item['priority']}</priority>")
            xml_parts.append("</url>")
        xml_parts.append("</urlset>")
        return HttpResponse("\n".join(xml_parts), content_type="application/xml")


def employee_home_url(employee: Employee) -> str:
    if employee.status == Employee.Status.PENDING_ONBOARDING:
        return reverse("accounts:employee_onboarding")
    if employee.status == Employee.Status.PENDING_APPROVAL:
        return reverse("accounts:about_work")
    if employee.status == Employee.Status.ACTIVE:
        return employee.dashboard_url
    return reverse("accounts:login")


def redirect_for_employee(request_or_employee, employee=None):
    """Accept (employee) or (request, employee) for greeting cookie support."""
    if employee is None:
        employee = request_or_employee
        request = None
    else:
        request = request_or_employee

    if employee.status == Employee.Status.PENDING_ONBOARDING:
        response = redirect("accounts:employee_onboarding")
    elif employee.status == Employee.Status.PENDING_APPROVAL:
        response = redirect("accounts:about_work")
    elif employee.status == Employee.Status.ACTIVE:
        response = redirect(employee.dashboard_url)
    else:
        response = redirect("accounts:login")

    if request is not None:
        attach_greeting_cookie(response, request)
    return response


class AdvocateLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = False

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect_for_employee(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["show_suspended_modal"] = kwargs.get(
            "show_suspended_modal", False
        ) or self.request.session.pop("show_suspended_modal", False)
        return context

    def form_valid(self, form):
        user = form.get_user()
        login(self.request, user)
        assign_session_greeting(self.request, user)
        mark_session_start(self.request)
        return redirect_for_employee(self.request, user)

    def form_invalid(self, form):
        suspended = any(
            getattr(err, "code", None) == "suspended"
            for err in form.errors.as_data().get("__all__", [])
        )
        if suspended:
            return self.render_to_response(
                self.get_context_data(form=form, show_suspended_modal=True)
            )
        messages.error(self.request, "Invalid login code or password.")
        return super().form_invalid(form)


class SignUpView(View):
    template_name = "accounts/signup.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect_for_employee(request.user)
        return render(request, self.template_name, {"form": SignUpForm()})

    def post(self, request):
        form = SignUpForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            login(request, user)
            assign_session_greeting(request, user)
            mark_session_start(request)
            messages.info(
                request,
                "Account created. Complete your onboarding details next.",
            )
            response = redirect("accounts:employee_onboarding")
            return attach_greeting_cookie(response, request)
        return render(request, self.template_name, {"form": form})


class ClientLoginView(View):
    template_name = "accounts/client_login.html"

    def get(self, request):
        client = get_client(request)
        if client:
            return redirect_for_client(client)
        return render(
            request,
            self.template_name,
            {
                "form": ClientLoginForm(),
                "google_client_id": getattr(settings, "GOOGLE_CLIENT_ID", ""),
                "show_manual": False,
            },
        )

    def post(self, request):
        form = ClientLoginForm(request.POST)
        if form.is_valid():
            client = form.get_client()
            login_client(request, client)
            messages.success(request, f"Welcome back, {client.first_name}.")
            return redirect_for_client(client)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "google_client_id": getattr(settings, "GOOGLE_CLIENT_ID", ""),
                "show_manual": True,
            },
        )


class ClientSignUpView(View):
    template_name = "accounts/client_signup.html"

    def get(self, request):
        client = get_client(request)
        if client:
            return redirect_for_client(client)
        return render(
            request,
            self.template_name,
            {
                "form": ClientSignUpForm(),
                "google_client_id": getattr(settings, "GOOGLE_CLIENT_ID", ""),
            },
        )

    def post(self, request):
        form = ClientSignUpForm(request.POST, request.FILES)
        if form.is_valid():
            client = form.save()
            login_client(request, client)
            messages.info(
                request,
                "Account created. Complete your onboarding details next.",
            )
            return redirect("accounts:client_onboarding")
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "google_client_id": getattr(settings, "GOOGLE_CLIENT_ID", ""),
            },
        )


@require_POST
def client_google_auth(request):
    """Exchange a Google GIS credential for a client session."""
    credential = request.POST.get("credential", "")
    try:
        claims = verify_google_id_token(credential)
    except GoogleAuthError as exc:
        messages.error(request, str(exc))
        return redirect("accounts:client_login")

    email = claims["email"].lower().strip()
    google_sub = claims.get("sub", "")
    first_name = (claims.get("given_name") or "").strip() or "Client"
    last_name = (claims.get("family_name") or "").strip() or "User"

    client = None
    if google_sub:
        client = Client.objects.filter(google_sub=google_sub).first()
    if client is None:
        client = Client.objects.filter(email__iexact=email).first()

    if client is None:
        client = Client(
            email=email,
            first_name=first_name.title(),
            last_name=last_name.title(),
            google_sub=google_sub,
            status=Client.Status.PENDING_ONBOARDING,
        )
        client.save()
        messages.info(
            request,
            "Welcome. Your client account is pending onboarding.",
        )
    else:
        if client.status == Client.Status.SUSPENDED:
            messages.error(request, "This client account has been suspended.")
            return redirect("accounts:client_login")
        if google_sub and not client.google_sub:
            client.google_sub = google_sub
            client.save(update_fields=["google_sub"])
        messages.success(request, f"Welcome back, {client.first_name}.")

    login_client(request, client)
    return redirect_for_client(client)


def _google_drive_settings_return(request) -> str:
    """Best-effort return URL to the Google Drive Settings workspace page."""
    user = request.user
    if (
        getattr(user, "is_authenticated", False)
        and user.is_authenticated
        and hasattr(user, "workspace_url")
    ):
        return user.workspace_url("dashboard", "google-drive-settings")
    next_url = (request.GET.get("next") or request.POST.get("next") or "").strip()
    if next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return "/"


@login_required
@require_GET
def google_drive_connect(request):
    """Start Google OAuth consent for firm Drive access."""
    user = request.user
    if not isinstance(user, Employee) or user.status != Employee.Status.ACTIVE:
        messages.error(request, "Sign in with an active employee account to connect Google.")
        return redirect("accounts:login")

    return_path = _google_drive_settings_return(request)
    try:
        auth_url = begin_oauth(request, return_path)
    except GoogleDriveOAuthError as exc:
        messages.error(request, str(exc))
        return redirect(return_path)
    return redirect(auth_url)


@login_required
@require_GET
def google_drive_callback(request):
    """OAuth redirect URI — exchange code and return to settings."""
    user = request.user
    return_path = pop_oauth_return(request) or _google_drive_settings_return(request)

    if not isinstance(user, Employee) or user.status != Employee.Status.ACTIVE:
        messages.error(request, "Sign in with an active employee account to connect Google.")
        return redirect("accounts:login")

    error = (request.GET.get("error") or "").strip()
    if error:
        messages.error(
            request,
            "Google authorization was cancelled or denied."
            if error == "access_denied"
            else f"Google authorization failed ({error}).",
        )
        return redirect(return_path)

    try:
        validate_oauth_state(request, request.GET.get("state") or "")
        code = (request.GET.get("code") or "").strip()
        if not code:
            raise GoogleDriveOAuthError("Missing authorization code from Google.")
        connection = exchange_code(request, code)
    except GoogleDriveOAuthError as exc:
        messages.error(request, str(exc))
        return redirect(return_path)

    label = connection.account_email or connection.account_name or "Google account"
    try:
        summary = bootstrap_drive_folders(connection)
        root_name = firm_root_folder_name()
        messages.success(
            request,
            f"Connected to Google Drive as {label}. "
            f"Created “{root_name}/Clients” and “{root_name}/Work”, "
            f"with folders for {summary['clients_created']} client(s).",
        )
        if summary["clients_errors"]:
            messages.warning(
                request,
                f"Could not create Drive folders for "
                f"{summary['clients_errors']} client(s). Try reconnecting later.",
            )
    except (GoogleDriveAPIError, GoogleDriveOAuthError) as exc:
        messages.success(request, f"Connected to Google Drive as {label}.")
        messages.warning(
            request,
            f"Could not finish creating the firm Drive folders: {exc}",
        )
    return redirect(return_path)


@login_required
@require_POST
def google_drive_disconnect(request):
    """
    Disconnect firm Google Drive — only via explicit Disconnect button POST.
    Notifies all active employees in Messages / the notification bell.
    """
    user = request.user
    return_path = _google_drive_settings_return(request)

    if not isinstance(user, Employee) or user.status != Employee.Status.ACTIVE:
        messages.error(request, "Sign in with an active employee account.")
        return redirect("accounts:login")

    # Require the disconnect form action so stray POSTs cannot clear credentials.
    if (request.POST.get("google_drive_action") or "").strip() != "disconnect":
        messages.error(request, "Disconnect was not confirmed.")
        return redirect(return_path)

    connection = GoogleDriveConnection.get_solo()
    if not connection.is_connected:
        messages.info(request, "Google Drive is already disconnected.")
        return redirect(return_path)

    account_label = (
        connection.account_email or connection.account_name or "Google account"
    )
    disconnect_google_drive(revoke=True)
    notify_google_drive_disconnected(disconnected_by=user)
    messages.success(
        request,
        f"Disconnected {account_label}. All employees have been notified.",
    )
    return redirect(return_path)


@csrf_exempt
@require_POST
def mpesa_stk_callback(request):
    """Safaricom Daraja STK result webhook — updates invoice payment status."""
    from .mpesa import process_stk_callback

    raw = request.body.decode("utf-8", errors="replace") if request.body else ""
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {}

    try:
        outcome = process_stk_callback(payload)
    except Exception:
        logger.exception("M-Pesa STK callback processing failed")
        outcome = None

    if outcome:
        logger.info(
            "M-Pesa STK callback processed status=%s receipt=%s checkout=%s",
            outcome.get("status"),
            outcome.get("mpesa_receipt"),
            outcome.get("checkout_request_id"),
        )
    else:
        body = (payload or {}).get("Body") or {}
        stk = body.get("stkCallback") or {}
        logger.info(
            "M-Pesa STK callback ResultCode=%s CheckoutRequestID=%s",
            stk.get("ResultCode"),
            stk.get("CheckoutRequestID") or "",
        )

    return JsonResponse({"ResultCode": 0, "ResultDesc": "Accepted"})


def _invoice_payable_statuses():
    return {
        Invoice.Status.ISSUED,
        Invoice.Status.GENERATED,
        Invoice.Status.PARTIALLY_PAID,
    }


def _stk_form_for_invoice(invoice, data=None, *, phone=""):
    max_amount = invoice.balance_due
    if data is not None:
        return InvoiceStkPaymentForm(data, max_amount=max_amount)
    return InvoiceStkPaymentForm(
        initial={"phone": phone, "amount": max_amount},
        max_amount=max_amount,
    )


def _session_stk_payload(stk_request, outcome=None):
    payload = {
        "invoice_id": stk_request.invoice_id,
        "checkout_request_id": stk_request.checkout_request_id,
        "merchant_request_id": stk_request.merchant_request_id,
        "phone": stk_request.phone,
        "amount": str(stk_request.amount),
        "simulated": stk_request.simulated,
        "stk_status": stk_request.status,
        "result_code": stk_request.result_code,
        "result_desc": stk_request.result_desc,
        "mpesa_receipt": stk_request.mpesa_receipt,
    }
    if outcome:
        payload["stk_status"] = outcome.get("status") or payload["stk_status"]
        payload["result_code"] = outcome.get("result_code") or ""
        payload["result_desc"] = outcome.get("result_desc") or ""
        payload["mpesa_receipt"] = outcome.get("mpesa_receipt") or ""
        payload["invoice_status"] = outcome.get("invoice_status")
        payload["invoice_status_label"] = outcome.get("invoice_status_label")
        payload["amount_paid"] = outcome.get("amount_paid")
        payload["balance_due"] = outcome.get("balance_due")
        payload["payment_applied"] = outcome.get("payment_applied")
    return payload


def _start_invoice_stk(invoice, *, phone, amount):
    from .mpesa import (
        create_stk_request,
        initiate_stk_push,
        mpesa_configured,
    )

    result = initiate_stk_push(
        phone=phone,
        amount=amount,
        account_reference=invoice.invoice_number,
        description=f"Pay {invoice.invoice_number}",
        callback_url=getattr(settings, "MPESA_CALLBACK_URL", "") or "",
    )
    stk = create_stk_request(invoice, result)
    return result, stk, mpesa_configured()


def _check_invoice_stk(session_dict, invoice):
    from .models import MpesaStkRequest
    from .mpesa import MpesaError, refresh_stk_request

    checkout_id = (session_dict.get("checkout_request_id") or "").strip()
    if not checkout_id or session_dict.get("invoice_id") != invoice.pk:
        raise MpesaError(
            "Start an STK push first, then check status after the customer responds."
        )

    try:
        stk = MpesaStkRequest.objects.select_related("invoice").get(
            checkout_request_id=checkout_id,
            invoice=invoice,
        )
    except MpesaStkRequest.DoesNotExist as exc:
        raise MpesaError(
            "Could not find this STK request. Send a new payment prompt."
        ) from exc

    outcome = refresh_stk_request(stk)
    session_dict.clear()
    session_dict.update(_session_stk_payload(stk, outcome))
    return outcome


def _stk_status_response(outcome: dict) -> dict:
    """JSON-serializable STK status for live polling."""
    status = outcome.get("status") or "pending"
    return {
        "status": status,
        "result_code": outcome.get("result_code") or "",
        "result_desc": outcome.get("result_desc") or "",
        "mpesa_receipt": outcome.get("mpesa_receipt") or "",
        "amount": outcome.get("amount") or "",
        "phone": outcome.get("phone") or "",
        "amount_paid": outcome.get("amount_paid") or "",
        "balance_due": outcome.get("balance_due") or "",
        "invoice_status": outcome.get("invoice_status") or "",
        "invoice_status_label": outcome.get("invoice_status_label") or "",
        "payment_applied": bool(outcome.get("payment_applied")),
        "terminal": status in {"success", "failed", "error", "idle"},
    }


def _poll_invoice_stk_status(request, invoice, session_key: str) -> dict:
    """Refresh STK status from Daraja/session and return poll payload."""
    from .mpesa import MpesaError

    push = dict(request.session.get(session_key) or {})
    if not push or push.get("invoice_id") != invoice.pk:
        return _stk_status_response({"status": "idle", "result_desc": "No active STK push."})

    try:
        outcome = _check_invoice_stk(push, invoice)
        request.session[session_key] = push
        request.session.modified = True
        return _stk_status_response(outcome)
    except MpesaError as exc:
        return _stk_status_response({"status": "error", "result_desc": str(exc)})


@login_required
@require_GET
def invoice_stk_status(request, role, invoice_id):
    """Live poll: M-Pesa STK result for staff pay invoice page."""
    user, denied = _employee_workspace_guard(request, role)
    if denied:
        return JsonResponse({"error": "forbidden"}, status=403)

    invoice = get_object_or_404(Invoice, pk=invoice_id)
    payload = _poll_invoice_stk_status(request, invoice, PayInvoiceView.session_key)
    return JsonResponse(payload)


@require_GET
def client_invoice_stk_status(request, invoice_id):
    """Live poll: M-Pesa STK result for client pay invoice page."""
    client, denied = _require_active_client(request)
    if denied:
        return JsonResponse({"error": "forbidden"}, status=403)

    invoice = get_object_or_404(_client_invoice_queryset(client), pk=invoice_id)
    payload = _poll_invoice_stk_status(
        request, invoice, ClientPayInvoiceView.session_key
    )
    return JsonResponse(payload)


@require_GET
def shared_invoice_stk_status(request, token):
    """Live poll: M-Pesa STK result for shared invoice pay link."""
    invoice, error = _shared_invoice_from_token(token)
    if error:
        return error

    payload = _poll_invoice_stk_status(
        request, invoice, SharedInvoicePayView.session_key
    )
    return JsonResponse(payload)


class ClientOnboardingView(View):
    template_name = "accounts/client_onboarding.html"

    def get(self, request):
        client = get_client(request)
        if not client:
            return redirect("accounts:client_login")
        if client.status == Client.Status.SUSPENDED:
            logout_client(request)
            return redirect("accounts:client_login")
        if client.status != Client.Status.PENDING_ONBOARDING:
            return redirect_for_client(client)

        context = client_portal_context(
            request,
            client,
            page_title="Onboarding",
            active="profile",
        )
        context["form"] = ClientOnboardingForm(client=client)
        return render(request, self.template_name, context)

    def post(self, request):
        client = get_client(request)
        if not client:
            return redirect("accounts:client_login")
        if client.status != Client.Status.PENDING_ONBOARDING:
            return redirect_for_client(client)

        form = ClientOnboardingForm(request.POST, request.FILES, client=client)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Details submitted. Your account is now pending firm approval.",
            )
            return redirect("accounts:client_pending")

        context = client_portal_context(
            request,
            client,
            page_title="Onboarding",
            active="profile",
        )
        context["form"] = form
        return render(request, self.template_name, context)


class ClientPendingView(View):
    template_name = "accounts/client_pending.html"

    def get(self, request):
        client = get_client(request)
        if not client:
            return redirect("accounts:client_login")
        if client.status == Client.Status.SUSPENDED:
            logout_client(request)
            return redirect("accounts:client_login")
        if client.status == Client.Status.PENDING_ONBOARDING:
            return redirect("accounts:client_onboarding")
        if client.status == Client.Status.ACTIVE:
            return redirect("accounts:client_dashboard")
        if client.status != Client.Status.PENDING_APPROVAL:
            return redirect_for_client(client)

        context = client_portal_context(
            request,
            client,
            page_title="Pending approval",
            active="profile",
        )
        return render(request, self.template_name, context)


class ClientDashboardView(View):
    template_name = "accounts/client_dashboard.html"

    def get(self, request):
        client = get_client(request)
        if not client:
            return redirect("accounts:client_login")
        if client.status == Client.Status.SUSPENDED:
            logout_client(request)
            return redirect("accounts:client_login")
        if client.status != Client.Status.ACTIVE:
            return redirect_for_client(client)

        context = client_portal_context(
            request,
            client,
            page_title="Dashboard",
            active="dashboard",
        )
        display_name = client.get_full_name() or client.email
        context["welcome_headline"] = f"Welcome, {display_name}"
        context["welcome_copy"] = (
            "Your client account is active. Use Finance & Billing to view and pay "
            "invoices issued to you, and follow other portal areas as they open."
        )
        return render(request, self.template_name, context)


@require_GET
def client_status(request):
    """Poll endpoint so the pending page can redirect once approved."""
    client = get_client(request)
    if not client:
        return JsonResponse(
            {
                "authenticated": False,
                "status": None,
                "redirect_url": reverse("accounts:client_login"),
            }
        )
    # Re-read status from DB so approval changes are visible immediately.
    try:
        status = Client.objects.values_list("status", flat=True).get(pk=client.pk)
    except Client.DoesNotExist:
        logout_client(request)
        return JsonResponse(
            {
                "authenticated": False,
                "status": None,
                "redirect_url": reverse("accounts:client_login"),
            }
        )
    client.status = status
    if status == Client.Status.SUSPENDED:
        logout_client(request)
        return JsonResponse(
            {
                "authenticated": False,
                "status": Client.Status.SUSPENDED,
                "redirect_url": reverse("accounts:client_login"),
            }
        )
    return JsonResponse(
        {
            "authenticated": True,
            "status": status,
            "redirect_url": client_home_url(client),
        }
    )


class ClientLogoutView(View):
    def post(self, request):
        logout_client(request)
        messages.info(request, "You have been signed out.")
        return redirect("accounts:home")

    def get(self, request):
        return self.post(request)


CLIENT_INVOICE_STATUSES = (
    Invoice.Status.ISSUED,
    Invoice.Status.PARTIALLY_PAID,
    Invoice.Status.PAID,
    Invoice.Status.CANCELLED,
)


def _require_active_client(request):
    """Return (client, None) or (None, redirect response)."""
    client = get_client(request)
    if not client:
        return None, redirect("accounts:client_login")
    if client.status == Client.Status.SUSPENDED:
        logout_client(request)
        return None, redirect("accounts:client_login")
    if client.status != Client.Status.ACTIVE:
        return None, redirect_for_client(client)
    return client, None


def _client_invoice_queryset(client):
    return Invoice.objects.filter(
        client=client,
        status__in=CLIENT_INVOICE_STATUSES,
    ).select_related("approved_by", "created_by")


class ClientBillingView(View):
    """Client Finance & Billing hub — issued invoices awaiting payment."""

    template_name = "accounts/client_billing.html"

    def get(self, request):
        client, denied = _require_active_client(request)
        if denied:
            return denied

        invoices = list(_client_invoice_queryset(client))
        outstanding = [
            inv for inv in invoices if inv.status in {
                Invoice.Status.ISSUED,
                Invoice.Status.PARTIALLY_PAID,
            }
        ]
        from decimal import Decimal

        context = client_portal_context(
            request,
            client,
            page_title="Finance & Billing",
            active="billing",
        )
        context.update(
            {
                "invoices": invoices,
                "outstanding_count": len(outstanding),
                "outstanding_total": sum(
                    (inv.total_amount for inv in outstanding),
                    start=Decimal("0"),
                ),
            }
        )
        return render(request, self.template_name, context)


class ClientInvoiceView(View):
    """Client-facing invoice document with pay / download actions."""

    template_name = "accounts/client_invoice.html"

    def get(self, request, invoice_id):
        client, denied = _require_active_client(request)
        if denied:
            return denied

        invoice = get_object_or_404(
            _client_invoice_queryset(client),
            pk=invoice_id,
        )
        # Opening the invoice from a notification marks related alerts read.
        ClientNotification.objects.filter(
            recipient=client,
            source_key=f"invoice_issued:{invoice.pk}",
            is_read=False,
        ).update(is_read=True, read_at=timezone.now())

        firm = FirmCompanyInformation.get_solo()
        context = client_portal_context(
            request,
            client,
            page_title=invoice.invoice_number,
            active="billing",
        )
        context.update(
            {
                "invoice": invoice,
                "firm": firm,
                "list_url": reverse("accounts:client_billing"),
                "pay_url": reverse(
                    "accounts:client_pay_invoice",
                    kwargs={"invoice_id": invoice.pk},
                ),
                "pdf_url": reverse(
                    "accounts:client_invoice_pdf",
                    kwargs={"invoice_id": invoice.pk},
                ),
                "can_pay": invoice.is_payable,
            }
        )
        return render(request, self.template_name, context)


class ClientInvoicePdfView(View):
    """Authenticated PDF download for the logged-in client."""

    def get(self, request, invoice_id):
        client, denied = _require_active_client(request)
        if denied:
            return denied

        invoice = get_object_or_404(
            _client_invoice_queryset(client),
            pk=invoice_id,
        )
        return _invoice_pdf_response(invoice)


class ClientPayInvoiceView(View):
    """Client portal M-Pesa payment for an issued invoice."""

    template_name = "accounts/client_pay_invoice.html"
    session_key = "client_invoice_stk_push"

    def get(self, request, invoice_id):
        client, denied = _require_active_client(request)
        if denied:
            return denied

        invoice = get_object_or_404(
            _client_invoice_queryset(client),
            pk=invoice_id,
        )
        context = self._context(request, client, invoice)
        return render(request, self.template_name, context)

    def post(self, request, invoice_id):
        client, denied = _require_active_client(request)
        if denied:
            return denied

        invoice = get_object_or_404(
            _client_invoice_queryset(client),
            pk=invoice_id,
        )
        action = (request.POST.get("action") or "stk").strip()

        if invoice.status == Invoice.Status.PAID:
            messages.info(request, "This invoice is already paid.")
            return redirect("accounts:client_invoice", invoice_id=invoice.pk)

        if invoice.status not in _invoice_payable_statuses():
            messages.error(request, "This invoice cannot be paid.")
            return redirect("accounts:client_invoice", invoice_id=invoice.pk)

        if action in {"confirm", "check_status"}:
            return self._check_payment_status(request, invoice)

        form = _stk_form_for_invoice(invoice, request.POST)
        if not form.is_valid():
            context = self._context(request, client, invoice, form=form)
            return render(request, self.template_name, context)

        from .mpesa import MpesaError

        try:
            result, _stk, live = _start_invoice_stk(
                invoice,
                phone=form.cleaned_data["phone"],
                amount=form.cleaned_data["amount"],
            )
            push = _session_stk_payload(_stk)
            push["started_at"] = result.get("started_at") or ""
            request.session[self.session_key] = push
            request.session.modified = True
        except MpesaError as exc:
            messages.error(request, str(exc))
            context = self._context(request, client, invoice, form=form)
            return render(request, self.template_name, context)

        messages.success(
            request,
            result.get("customer_message")
            or "STK push sent. We are checking payment status live.",
        )
        if not live:
            messages.info(
                request,
                "Payment is running in simulation mode — status will update automatically.",
            )
        return redirect("accounts:client_pay_invoice", invoice_id=invoice.pk)

    def _check_payment_status(self, request, invoice):
        from .mpesa import MpesaError

        push = dict(request.session.get(self.session_key) or {})
        try:
            outcome = _check_invoice_stk(push, invoice)
            request.session[self.session_key] = push
            request.session.modified = True
        except MpesaError as exc:
            messages.error(request, str(exc))
            return redirect("accounts:client_pay_invoice", invoice_id=invoice.pk)

        status = outcome.get("status")
        if status == "success":
            receipt = outcome.get("mpesa_receipt") or "—"
            messages.success(
                request,
                f"Payment successful. M-Pesa receipt {receipt}. "
                f"Invoice is now {outcome.get('invoice_status_label')} "
                f"(paid KES {outcome.get('amount_paid')}, "
                f"balance KES {outcome.get('balance_due')}).",
            )
            invoice.refresh_from_db()
            if invoice.status == Invoice.Status.PAID:
                request.session.pop(self.session_key, None)
                return redirect("accounts:client_invoice", invoice_id=invoice.pk)
        elif status == "failed":
            messages.error(
                request,
                outcome.get("result_desc") or "M-Pesa payment failed.",
            )
        else:
            messages.info(
                request,
                outcome.get("result_desc")
                or "Payment is still pending. Ask the payer to complete the prompt, then check again.",
            )
        return redirect("accounts:client_pay_invoice", invoice_id=invoice.pk)

    def _context(self, request, client, invoice, *, form=None):
        from .mpesa import mpesa_configured

        initial_phone = (client.phone or "").strip()
        form = form or _stk_form_for_invoice(invoice, phone=initial_phone)
        push = request.session.get(self.session_key)
        if push and push.get("invoice_id") != invoice.pk:
            push = None

        context = client_portal_context(
            request,
            client,
            page_title=f"Pay {invoice.invoice_number}",
            active="billing",
        )
        context.update(
            {
                "invoice": invoice,
                "form": form,
                "list_url": reverse("accounts:client_billing"),
                "invoice_url": reverse(
                    "accounts:client_invoice",
                    kwargs={"invoice_id": invoice.pk},
                ),
                "stk_push": push,
                "stk_poll_url": reverse(
                    "accounts:client_invoice_stk_status",
                    kwargs={"invoice_id": invoice.pk},
                ),
                "mpesa_live": mpesa_configured(),
                "can_pay": invoice.is_payable,
            }
        )
        return context


@require_GET
def client_notifications(request):
    """Live notification feed for the client portal topbar bell."""
    client, denied = _require_active_client(request)
    if denied:
        return JsonResponse({"error": "forbidden"}, status=403)
    return JsonResponse(client_notifications_payload(client))


@require_GET
def client_notification_open(request, notification_id):
    """Mark a client notification read and redirect to its target page."""
    client, denied = _require_active_client(request)
    if denied:
        return denied

    notification = get_object_or_404(
        ClientNotification,
        pk=notification_id,
        recipient=client,
    )
    notification.mark_read()
    return redirect(notification.target_url)


@require_POST
def client_notifications_mark_all_read(request):
    """Mark every unread notification for the current client as read."""
    client, denied = _require_active_client(request)
    if denied:
        return JsonResponse({"error": "forbidden"}, status=403)

    now = timezone.now()
    updated = ClientNotification.objects.filter(
        recipient=client, is_read=False
    ).update(is_read=True, read_at=now)
    return JsonResponse(
        {
            "ok": True,
            "marked": updated,
            "unread_count": 0,
            "badges": {},
        }
    )


@require_GET
def check_login_code(request):
    code = (request.GET.get("code") or "").strip()
    if not code.isdigit() or len(code) != 6:
        return JsonResponse(
            {"available": False, "message": "Enter exactly 6 digits."}
        )
    try:
        taken = Employee.objects.filter(login_code=code).exists()
    except Exception:
        return JsonResponse(
            {
                "available": False,
                "message": "Could not verify code right now. Restart the server.",
            },
            status=503,
        )
    return JsonResponse(
        {
            "available": not taken,
            "message": "Login code is available."
            if not taken
            else "This login code is already taken.",
        }
    )


@method_decorator(login_required, name="dispatch")
class EmployeeOnboardingView(View):
    template_name = "accounts/employee_onboarding.html"

    def get(self, request):
        user = request.user
        if user.status == Employee.Status.SUSPENDED:
            return redirect("accounts:login")
        if user.status != Employee.Status.PENDING_ONBOARDING:
            return redirect_for_employee(request, user)

        context = employee_preactive_context(
            request,
            user,
            page_title="Onboarding",
            active="onboarding",
        )
        context["form"] = EmployeeOnboardingForm(employee=user)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request):
        user = request.user
        if user.status != Employee.Status.PENDING_ONBOARDING:
            return redirect_for_employee(request, user)

        form = EmployeeOnboardingForm(
            request.POST, request.FILES, employee=user
        )
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Details submitted. Your account is now pending firm approval.",
            )
            response = redirect("accounts:about_work")
            return attach_greeting_cookie(response, request)

        context = employee_preactive_context(
            request,
            user,
            page_title="Onboarding",
            active="onboarding",
        )
        context["form"] = form
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@require_GET
def employee_status(request):
    """Poll endpoint so the pending page can redirect once approved."""
    if not request.user.is_authenticated:
        return JsonResponse(
            {
                "authenticated": False,
                "status": None,
                "redirect_url": reverse("accounts:login"),
            }
        )
    # Re-read status from DB so approval changes are visible immediately.
    try:
        status = Employee.objects.values_list("status", flat=True).get(
            pk=request.user.pk
        )
    except Employee.DoesNotExist:
        return JsonResponse(
            {
                "authenticated": False,
                "status": None,
                "redirect_url": reverse("accounts:login"),
            }
        )
    if status == Employee.Status.SUSPENDED:
        return JsonResponse(
            {
                "authenticated": False,
                "status": Employee.Status.SUSPENDED,
                "redirect_url": reverse("accounts:login"),
            }
        )
    user = request.user
    user.status = status
    return JsonResponse(
        {
            "authenticated": True,
            "status": status,
            "redirect_url": employee_home_url(user),
        }
    )


WORKSPACE_LIST_SPECS = {
    "pending-clients": lambda: Client.objects.filter(
        status__in=[
            Client.Status.PENDING_ONBOARDING,
            Client.Status.PENDING_APPROVAL,
        ]
    ).order_by("pk").values_list("pk", "status"),
    "pending-employees": lambda: Employee.objects.filter(
        status__in=[
            Employee.Status.PENDING_ONBOARDING,
            Employee.Status.PENDING_APPROVAL,
        ]
    ).order_by("pk").values_list("pk", "status"),
    "pending-cases": lambda: LitigationCase.objects.filter(
        status=LitigationCase.Status.PENDING_APPROVAL
    ).order_by("pk").values_list("pk", "status"),
    "active-cases": lambda: LitigationCase.objects.filter(
        status=LitigationCase.Status.ACTIVE
    ).order_by("pk").values_list("pk", "status"),
    "pending-matters": lambda: NonLitigationMatter.objects.filter(
        status=NonLitigationMatter.Status.PENDING_APPROVAL
    ).order_by("pk").values_list("pk", "status"),
    "active-matters": lambda: NonLitigationMatter.objects.filter(
        status=NonLitigationMatter.Status.ACTIVE
    ).order_by("pk").values_list("pk", "status"),
    "clients": lambda: Client.objects.filter(
        status__in=[Client.Status.ACTIVE, Client.Status.SUSPENDED]
    ).order_by("pk").values_list("pk", "status"),
    "employees": lambda: Employee.objects.filter(
        status__in=[Employee.Status.ACTIVE, Employee.Status.SUSPENDED]
    ).order_by("pk").values_list("pk", "status"),
}


@login_required
@require_GET
def workspace_list_revision(request):
    """
    Tiny fingerprint for workspace list pages.

    The browser polls this instead of reloading HTML until the revision changes.
    """
    user = request.user
    if user.status != Employee.Status.ACTIVE:
        return JsonResponse({"error": "forbidden"}, status=403)

    list_key = (request.GET.get("list") or "").strip()
    builder = WORKSPACE_LIST_SPECS.get(list_key)
    if builder is None:
        return JsonResponse({"error": "unknown_list"}, status=400)

    rows = list(builder())
    revision = "|".join(f"{pk}:{status}" for pk, status in rows)
    return JsonResponse({"list": list_key, "count": len(rows), "revision": revision})


@login_required
@require_GET
def workspace_notifications(request):
    """Live notification feed for the workspace topbar bell."""
    user = request.user
    if user.status != Employee.Status.ACTIVE:
        return JsonResponse({"error": "forbidden"}, status=403)
    return JsonResponse(notifications_payload(user))


@login_required
@require_GET
def workspace_notification_open(request, notification_id):
    """Mark a notification read and redirect to its target page."""
    user = request.user
    if user.status != Employee.Status.ACTIVE:
        return JsonResponse({"error": "forbidden"}, status=403)

    notification = get_object_or_404(
        Notification,
        pk=notification_id,
        recipient=user,
    )
    notification.mark_read()
    return redirect(notification.target_url)


@login_required
@require_POST
def workspace_notifications_mark_all_read(request):
    """Mark every unread notification for the current employee as read."""
    user = request.user
    if user.status != Employee.Status.ACTIVE:
        return JsonResponse({"error": "forbidden"}, status=403)

    now = timezone.now()
    updated = Notification.objects.filter(recipient=user, is_read=False).update(
        is_read=True,
        read_at=now,
    )
    return JsonResponse(
        {
            "ok": True,
            "marked": updated,
            "unread_count": 0,
            "badges": {
                "tasks": 0,
                "calendar": 0,
                "reminders": 0,
                "messages": 0,
            },
        }
    )


@login_required
@require_GET
def workspace_entity_status(request):
    """Status fingerprint for a client/employee under review."""
    user = request.user
    if user.status != Employee.Status.ACTIVE:
        return JsonResponse({"error": "forbidden"}, status=403)

    kind = (request.GET.get("kind") or "").strip()
    try:
        entity_id = int(request.GET.get("id") or "")
    except (TypeError, ValueError):
        return JsonResponse({"error": "invalid_id"}, status=400)

    if kind == "client":
        try:
            status = Client.objects.values_list("status", flat=True).get(pk=entity_id)
        except Client.DoesNotExist:
            return JsonResponse({"exists": False, "status": None})
        return JsonResponse({"exists": True, "kind": kind, "status": status})

    if kind == "employee":
        try:
            status = Employee.objects.values_list("status", flat=True).get(
                pk=entity_id
            )
        except Employee.DoesNotExist:
            return JsonResponse({"exists": False, "status": None})
        return JsonResponse({"exists": True, "kind": kind, "status": status})

    if kind == "case":
        try:
            status = LitigationCase.objects.values_list("status", flat=True).get(
                pk=entity_id
            )
        except LitigationCase.DoesNotExist:
            return JsonResponse({"exists": False, "status": None})
        return JsonResponse({"exists": True, "kind": kind, "status": status})

    if kind == "matter":
        try:
            status = NonLitigationMatter.objects.values_list(
                "status", flat=True
            ).get(pk=entity_id)
        except NonLitigationMatter.DoesNotExist:
            return JsonResponse({"exists": False, "status": None})
        return JsonResponse({"exists": True, "kind": kind, "status": status})

    return JsonResponse({"error": "unknown_kind"}, status=400)


@login_required
@require_GET
def workspace_client_search(request):
    """Search active clients by name or phone for case registration."""
    user = request.user
    if user.status != Employee.Status.ACTIVE:
        return JsonResponse({"error": "forbidden"}, status=403)

    query = (request.GET.get("q") or "").strip()
    qs = Client.objects.filter(status=Client.Status.ACTIVE)

    if query:
        digits = "".join(ch for ch in query if ch.isdigit())
        name_q = (
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(company_name__icontains=query)
            | Q(phone__icontains=query)
            | Q(email__icontains=query)
            | Q(full_name__icontains=query)
        )
        if len(digits) >= 3:
            name_q = name_q | Q(phone__icontains=digits)
        qs = qs.annotate(
            full_name=Concat("first_name", Value(" "), "last_name")
        ).filter(name_q)

    qs = qs.order_by("company_name", "first_name", "last_name")[:15]

    results = []
    for client in qs:
        category = (
            CaseParty.Category.CORPORATE
            if client.client_type == Client.ClientType.CORPORATE
            else CaseParty.Category.INDIVIDUAL
        )
        results.append(
            {
                "id": client.pk,
                "name": client.get_full_name(),
                "phone": client.phone or "",
                "email": client.email or "",
                "client_type": client.client_type,
                "category": category,
                "label": f"{client.get_full_name()} · {client.phone or client.email}",
            }
        )
    return JsonResponse({"results": results})


CASE_SUGGEST_FIELDS = frozenset(
    {
        "filing_date",
        "court_rank",
        "case_category",
        "case_type",
        "court_case_number",
        "station",
        "client",
        "date_opened",
        "matter_category",
        "matter_title",
    }
)

CASE_CHOICE_PRESETS = {
    "court_rank": [label for _, label in LitigationCase.CourtRank.choices],
    "case_category": [label for _, label in LitigationCase.CaseCategory.choices],
    "case_type": [label for _, label in LitigationCase.CaseType.choices],
    "station": [label for _, label in LitigationCase.Station.choices],
    "matter_category": [
        label for _, label in NonLitigationMatter.MatterCategory.choices
    ],
}

CASE_CHOICE_LABELS = {
    "court_rank": dict(LitigationCase.CourtRank.choices),
    "case_category": dict(LitigationCase.CaseCategory.choices),
    "case_type": dict(LitigationCase.CaseType.choices),
    "station": dict(LitigationCase.Station.choices),
    "matter_category": dict(NonLitigationMatter.MatterCategory.choices),
}

MATTER_SUGGEST_MODEL_FIELDS = frozenset(
    {"date_opened", "matter_category", "matter_title"}
)


@login_required
@require_GET
def workspace_case_field_suggestions(request):
    """
    Live suggestions from presets and previously registered case values.

    Court rank / category / type / station also accept free-typed new values.
    """
    user = request.user
    if user.status != Employee.Status.ACTIVE:
        return JsonResponse({"error": "forbidden"}, status=403)

    field = (request.GET.get("field") or "").strip()
    query = (request.GET.get("q") or "").strip().lower()
    if field not in CASE_SUGGEST_FIELDS:
        return JsonResponse({"error": "unknown_field"}, status=400)

    limit = 20
    results = []

    if field == "client":
        client_ids = []
        for cid in list(
            LitigationCase.objects.order_by("-created_at").values_list(
                "client_id", flat=True
            )[:80]
        ) + list(
            NonLitigationMatter.objects.order_by("-created_at").values_list(
                "client_id", flat=True
            )[:80]
        ):
            if cid not in client_ids:
                client_ids.append(cid)
            if len(client_ids) >= 40:
                break
        clients = {
            c.pk: c
            for c in Client.objects.filter(
                pk__in=client_ids, status=Client.Status.ACTIVE
            )
        }
        for cid in client_ids:
            client = clients.get(cid)
            if not client:
                continue
            name = client.get_full_name()
            haystack = " ".join(
                [
                    name,
                    client.phone or "",
                    client.email or "",
                    client.company_name or "",
                ]
            ).lower()
            if query and query not in haystack:
                continue
            category = (
                CaseParty.Category.CORPORATE
                if client.client_type == Client.ClientType.CORPORATE
                else CaseParty.Category.INDIVIDUAL
            )
            results.append(
                {
                    "value": str(client.pk),
                    "label": name,
                    "meta": client.phone or client.email or "",
                    "id": client.pk,
                    "name": name,
                    "phone": client.phone or "",
                    "email": client.email or "",
                    "client_type": client.client_type,
                    "category": category,
                }
            )
            if len(results) >= limit:
                break
        return JsonResponse({"field": field, "results": results})

    labels = CASE_CHOICE_LABELS.get(field)
    presets = CASE_CHOICE_PRESETS.get(field) or []
    seen = set()

    for label in presets:
        if query and query not in label.lower():
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append({"value": label, "label": label, "meta": "Preset"})
        if len(results) >= limit:
            return JsonResponse({"field": field, "results": results})

    if field in MATTER_SUGGEST_MODEL_FIELDS:
        history_qs = NonLitigationMatter.objects.order_by("-created_at").values_list(
            field, flat=True
        )[:250]
        date_field = field == "date_opened"
    else:
        history_qs = LitigationCase.objects.order_by("-created_at").values_list(
            field, flat=True
        )[:250]
        date_field = field == "filing_date"

    for raw in history_qs:
        if raw in (None, ""):
            continue
        if date_field:
            value = raw.isoformat() if hasattr(raw, "isoformat") else str(raw)
            label = raw.strftime("%d %b %Y") if hasattr(raw, "strftime") else value
        elif labels is not None:
            stored = str(raw).strip()
            label = labels.get(stored, stored)
            value = label
        else:
            value = str(raw).strip()
            if not value:
                continue
            label = value

        key = value.lower()
        if key in seen:
            continue
        if query and query not in label.lower() and query not in value.lower():
            continue
        seen.add(key)
        meta = "Previously used" if presets or field == "matter_title" else ""
        results.append({"value": value, "label": label, "meta": meta})
        if len(results) >= limit:
            break

    free_register = field in CASE_CHOICE_PRESETS or field in {
        "matter_title",
        "matter_category",
    }
    if free_register and query and query not in seen and len(results) < limit:
        typed = (request.GET.get("q") or "").strip()
        if typed:
            results.insert(
                0,
                {"value": typed, "label": typed, "meta": "Register new"},
            )

    return JsonResponse({"field": field, "results": results})


@method_decorator(login_required, name="dispatch")
class AboutWorkView(View):
    """Pending-approval holding page with about-our-work details."""

    template_name = "accounts/about_work.html"

    def get(self, request):
        if request.user.status == Employee.Status.PENDING_ONBOARDING:
            return redirect("accounts:employee_onboarding")
        if request.user.status == Employee.Status.ACTIVE:
            return redirect(request.user.dashboard_url)
        if request.user.status == Employee.Status.SUSPENDED:
            return redirect("accounts:login")
        if request.user.status != Employee.Status.PENDING_APPROVAL:
            return redirect_for_employee(request, request.user)

        context = employee_preactive_context(
            request,
            request.user,
            page_title="Pending approval",
            active="pending-approval",
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


# Alias for /employee/pending/
EmployeePendingView = AboutWorkView


@method_decorator(login_required, name="dispatch")
class EmployeesHomeView(View):
    """ /workspace/ → role dashboard for the signed-in employee. """

    def get(self, request):
        return redirect_for_employee(request.user)


@method_decorator(login_required, name="dispatch")
class RoleHomeView(View):
    """ /<role>/ → /<role>/dashboard/ """

    def get(self, request, role):
        user = request.user
        if user.status != Employee.Status.ACTIVE:
            return redirect_for_employee(request, user)
        if role != user.role_slug:
            return redirect(user.dashboard_url)
        if Employee.role_from_slug(role) is None:
            return redirect(user.dashboard_url)
        return redirect(user.workspace_url("dashboard"))


def _choice_sort_key(value, choices):
    """Sort known choice slugs/labels by declared order; unknowns last A–Z."""
    raw = (value or "").strip()
    mapping = dict(choices)
    if raw in mapping:
        return (0, list(mapping.keys()).index(raw), mapping[raw].lower())
    for index, (_key, label) in enumerate(choices):
        if label.lower() == raw.lower():
            return (0, index, label.lower())
    return (1, 0, (raw or "—").lower())


def _client_contact_subtitle(client):
    phone = (client.phone or "").strip()
    email = (client.email or "").strip()
    parts = [part for part in (phone, email) if part]
    return " · ".join(parts) if parts else "No contact details"


def group_litigation_cases(cases, group_by: str):
    """Group active litigation cases by client or court for card browse UI."""
    mode = group_by if group_by in {"court", "client"} else "client"
    buckets = defaultdict(list)

    if mode == "client":
        for case in cases:
            buckets[case.client.pk].append(case)
        groups = []
        for index, (key, items) in enumerate(buckets.items()):
            client = items[0].client
            label = client.get_full_name()
            subtitle = _client_contact_subtitle(client)
            search_bits = [
                label,
                client.phone or "",
                client.email or "",
                *[
                    f"{case.court_case_number} {case.get_court_rank_display()} "
                    f"{case.get_case_category_display()}"
                    for case in items
                ],
            ]
            groups.append(
                {
                    "key": f"client-{key}",
                    "label": label,
                    "subtitle": subtitle,
                    "count": len(items),
                    "items": items,
                    "tone": index % 6,
                    "search_text": " ".join(search_bits).lower(),
                    "kind": "client",
                }
            )
        groups.sort(key=lambda g: g["label"].lower())
    else:
        for case in cases:
            key = (case.court_rank or "").strip() or "—"
            buckets[key].append(case)
        groups = []
        for index, (key, items) in enumerate(buckets.items()):
            label = items[0].get_court_rank_display()
            stations = sorted(
                {
                    case.get_station_display()
                    for case in items
                    if case.get_station_display()
                }
            )
            subtitle = (
                " · ".join(stations[:3])
                if stations
                else "Active litigation cases"
            )
            if len(stations) > 3:
                subtitle = f"{subtitle} · +{len(stations) - 3} more"
            search_bits = [
                label,
                subtitle,
                *[
                    f"{case.court_case_number} {case.client.get_full_name()} "
                    f"{case.client.phone or ''} {case.client.email or ''}"
                    for case in items
                ],
            ]
            groups.append(
                {
                    "key": f"court-{key}",
                    "label": label,
                    "subtitle": subtitle,
                    "count": len(items),
                    "items": items,
                    "tone": index % 6,
                    "search_text": " ".join(search_bits).lower(),
                    "kind": "court",
                }
            )
        groups.sort(
            key=lambda g: _choice_sort_key(
                g["items"][0].court_rank, LitigationCase.CourtRank.choices
            )
        )

    return mode, groups


def group_non_litigation_matters(matters, group_by: str):
    """Group active non-litigation matters by client or category for card browse UI."""
    mode = group_by if group_by in {"category", "client"} else "client"
    buckets = defaultdict(list)

    if mode == "client":
        for matter in matters:
            buckets[matter.client.pk].append(matter)
        groups = []
        for index, (key, items) in enumerate(buckets.items()):
            client = items[0].client
            label = client.get_full_name()
            subtitle = _client_contact_subtitle(client)
            search_bits = [
                label,
                client.phone or "",
                client.email or "",
                *[
                    f"{matter.matter_title} {matter.get_matter_category_display()}"
                    for matter in items
                ],
            ]
            groups.append(
                {
                    "key": f"client-{key}",
                    "label": label,
                    "subtitle": subtitle,
                    "count": len(items),
                    "items": items,
                    "tone": index % 6,
                    "search_text": " ".join(search_bits).lower(),
                    "kind": "client",
                }
            )
        groups.sort(key=lambda g: g["label"].lower())
    else:
        for matter in matters:
            key = (matter.matter_category or "").strip() or "—"
            buckets[key].append(matter)
        groups = []
        for index, (key, items) in enumerate(buckets.items()):
            label = items[0].get_matter_category_display()
            subtitle = "Active non-litigation matters"
            search_bits = [
                label,
                *[
                    f"{matter.matter_title} {matter.client.get_full_name()} "
                    f"{matter.client.phone or ''} {matter.client.email or ''}"
                    for matter in items
                ],
            ]
            groups.append(
                {
                    "key": f"category-{key}",
                    "label": label,
                    "subtitle": subtitle,
                    "count": len(items),
                    "items": items,
                    "tone": index % 6,
                    "search_text": " ".join(search_bits).lower(),
                    "kind": "category",
                }
            )
        groups.sort(
            key=lambda g: _choice_sort_key(
                g["items"][0].matter_category,
                NonLitigationMatter.MatterCategory.choices,
            )
        )

    return mode, groups


def group_invoices(invoices, group_by: str = "client"):
    """Group invoices by client for the invoicing browse UI."""
    buckets = defaultdict(list)
    for invoice in invoices:
        buckets[invoice.client.pk].append(invoice)

    groups = []
    for index, (key, items) in enumerate(buckets.items()):
        client = items[0].client
        label = client.get_full_name()
        subtitle = (
            f"{client.get_client_type_display()} · "
            f"{_client_contact_subtitle(client)}"
        )
        search_bits = [
            label,
            client.get_client_type_display(),
            client.phone or "",
            client.email or "",
            *[
                f"{invoice.invoice_number} {invoice.description} "
                f"{invoice.get_status_display()}"
                for invoice in items
            ],
        ]
        groups.append(
            {
                "key": f"client-{key}",
                "label": label,
                "subtitle": subtitle,
                "count": len(items),
                "items": items,
                "tone": index % 6,
                "search_text": " ".join(search_bits).lower(),
                "kind": "client",
            }
        )
    groups.sort(key=lambda g: g["label"].lower())
    return "client", groups


@method_decorator(login_required, name="dispatch")
class RoleWorkspaceView(View):
    """
    /<role>/<pages>/

    Pages nest as the user moves, e.g.
    /advocate/dashboard/
    /advocate/dashboard/settings/
    /advocate/my-cases/
    """

    dashboard_template = "accounts/dashboard.html"
    settings_template = "accounts/settings.html"
    theme_settings_template = "accounts/theme_settings.html"
    employee_management_template = "accounts/employee_management.html"
    client_management_template = "accounts/client_management.html"
    approve_pending_clients_template = "accounts/approve_pending_clients.html"
    register_client_template = "accounts/register_client.html"
    register_employee_template = "accounts/register_employee.html"
    onboarding_approvals_template = "accounts/onboarding_approvals.html"
    register_case_template = "accounts/register_case.html"
    approve_registered_cases_template = "accounts/approve_registered_cases.html"
    litigation_matters_template = "accounts/litigation_matters.html"
    register_matter_template = "accounts/register_matter.html"
    approve_registered_matters_template = "accounts/approve_registered_matters.html"
    non_litigation_matters_template = "accounts/non_litigation_matters.html"
    tasks_template = "accounts/tasks.html"
    calendar_template = "accounts/calendar.html"
    reminders_template = "accounts/reminders.html"
    messages_template = "accounts/messages.html"
    notification_settings_template = "accounts/notification_settings.html"
    about_me_template = "accounts/about_me.html"
    my_blogs_template = "accounts/my_blogs.html"
    my_blog_form_template = "accounts/my_blog_form.html"
    google_drive_settings_template = "accounts/google_drive_settings.html"
    company_information_template = "accounts/company_information.html"
    company_profile_template = "accounts/company_profile.html"
    company_contacts_template = "accounts/company_contacts.html"
    about_company_template = "accounts/about_company.html"
    practice_areas_template = "accounts/practice_areas.html"
    practice_area_form_template = "accounts/practice_area_form.html"
    company_faqs_template = "accounts/company_faqs.html"
    company_blogs_template = "accounts/company_blogs.html"
    company_gallery_template = "accounts/company_gallery.html"
    company_gallery_form_template = "accounts/company_gallery_form.html"
    company_terms_template = "accounts/company_terms.html"
    research_blogs_template = "accounts/research_blogs.html"
    company_faq_form_template = "accounts/company_faq_form.html"
    website_template_template = "accounts/website_template.html"
    finance_settings_template = "accounts/finance_settings.html"
    invoicing_template = "accounts/invoicing.html"
    generate_invoice_template = "accounts/generate_invoice.html"
    payments_template = "accounts/payments.html"
    page_template = "accounts/workspace_page.html"

    def get(self, request, role, pages="dashboard"):
        user = request.user
        if user.status != Employee.Status.ACTIVE:
            return redirect_for_employee(request, user)
        if Employee.role_from_slug(role) is None:
            return redirect(user.dashboard_url)
        if role != user.role_slug:
            return redirect(user.workspace_url(*pages.strip("/").split("/")))

        resolved = resolve_workspace_page(user.role, pages)
        if not resolved:
            return redirect(user.dashboard_url)

        context = workspace_context(
            user,
            request=request,
            page_title=resolved["page_title"],
            page_trail=resolved["trail"],
            active_page=resolved["leaf"],
        )

        if resolved["is_settings"]:
            context.update(self._settings_context(user))
            response = render(request, self.settings_template, context)
        elif resolved.get("is_theme_settings"):
            context.update(self._settings_context(user))
            response = render(request, self.theme_settings_template, context)
        elif resolved.get("is_notification_settings"):
            context.update(self._settings_context(user))
            response = render(
                request, self.notification_settings_template, context
            )
        elif resolved.get("is_about_me"):
            context.update(self._settings_context(user))
            response = render(request, self.about_me_template, context)
        elif resolved.get("is_my_blogs"):
            context.update(self._my_blogs_context(user))
            response = render(request, self.my_blogs_template, context)
        elif resolved.get("is_my_blogs_new"):
            context.update(self._my_blog_form_context(user))
            response = render(request, self.my_blog_form_template, context)
        elif resolved.get("is_google_drive_settings"):
            context.update(self._google_drive_settings_context(request, resolved))
            response = render(
                request, self.google_drive_settings_template, context
            )
        elif resolved.get("is_website_template"):
            context.update(self._website_template_context(user))
            response = render(request, self.website_template_template, context)
        elif resolved.get("is_finance_settings"):
            context.update(self._finance_settings_context(form=None))
            response = render(request, self.finance_settings_template, context)
        elif resolved.get("is_company_information"):
            from .company_readiness import analyze_company_information

            context["analysis"] = analyze_company_information(
                role_slug=user.role_slug,
                trail=list(resolved["trail"]),
            )
            response = render(
                request, self.company_information_template, context
            )
        elif resolved.get("is_company_profile"):
            context.update(self._company_profile_context())
            response = render(request, self.company_profile_template, context)
        elif resolved["leaf"] == "company-contacts":
            context.update(self._company_contacts_context())
            response = render(request, self.company_contacts_template, context)
        elif resolved["leaf"] == "about-company":
            context.update(self._about_company_context())
            response = render(request, self.about_company_template, context)
        elif resolved.get("is_practice_areas"):
            context.update(self._practice_areas_context(user))
            response = render(request, self.practice_areas_template, context)
        elif resolved.get("is_practice_areas_new"):
            context.update(self._practice_area_form_context(user))
            response = render(request, self.practice_area_form_template, context)
        elif resolved.get("is_company_faqs"):
            context.update(self._company_faqs_context(user))
            response = render(request, self.company_faqs_template, context)
        elif resolved.get("is_company_faqs_new"):
            context.update(self._company_faq_form_context(user))
            response = render(request, self.company_faq_form_template, context)
        elif resolved.get("is_company_blogs"):
            context.update(self._company_blogs_context(user))
            response = render(request, self.company_blogs_template, context)
        elif resolved.get("is_company_gallery"):
            context.update(self._company_gallery_context(user))
            response = render(request, self.company_gallery_template, context)
        elif resolved.get("is_company_gallery_new"):
            context.update(self._company_gallery_form_context(user))
            response = render(
                request, self.company_gallery_form_template, context
            )
        elif resolved.get("is_company_terms"):
            context.update(self._company_terms_context())
            response = render(request, self.company_terms_template, context)
        elif resolved.get("is_research_blogs"):
            context.update(self._research_blogs_context(user))
            response = render(request, self.research_blogs_template, context)
        elif resolved["leaf"] == "invoicing":
            invoices = list(
                Invoice.objects.select_related("client", "created_by").order_by(
                    "-issue_date", "-created_at"
                )
            )
            _group_by, invoice_groups = group_invoices(invoices)
            context["invoices"] = invoices
            context["invoice_count"] = len(invoices)
            context["invoice_groups"] = invoice_groups
            response = render(request, self.invoicing_template, context)
        elif resolved["leaf"] == "generate-invoice":
            context.update(self._generate_invoice_context(user, resolved))
            response = render(request, self.generate_invoice_template, context)
        elif resolved["leaf"] == "payments":
            from decimal import Decimal

            invoices = list(
                Invoice.objects.select_related("client")
                .exclude(status=Invoice.Status.CANCELLED)
                .order_by("-issue_date", "-created_at")
            )
            _group_by, payment_groups = group_invoices(invoices)
            for group in payment_groups:
                items = group["items"]
                group["balance_due"] = sum(
                    (inv.balance_due for inv in items),
                    Decimal("0.00"),
                )
                group["open_count"] = sum(
                    1 for inv in items if inv.status != Invoice.Status.PAID
                )
            context["invoices"] = invoices
            context["invoice_count"] = len(invoices)
            context["payment_groups"] = payment_groups
            context["unpaid_invoices"] = [
                inv
                for inv in invoices
                if inv.status != Invoice.Status.PAID
            ]
            response = render(request, self.payments_template, context)
        elif resolved["is_dashboard"]:
            response = render(request, self.dashboard_template, context)
        elif resolved["leaf"] == "employee-management":
            context["employees"] = Employee.objects.filter(
                status__in=[
                    Employee.Status.ACTIVE,
                    Employee.Status.SUSPENDED,
                ]
            ).order_by("status", "first_name", "last_name", "login_code")
            context["employee_count"] = context["employees"].count()
            response = render(request, self.employee_management_template, context)
        elif resolved["leaf"] == "register-employee":
            context.update(self._register_employee_context(user))
            response = render(request, self.register_employee_template, context)
        elif resolved["leaf"] == "onboarding-approvals":
            context["employees"] = Employee.objects.filter(
                status__in=[
                    Employee.Status.PENDING_ONBOARDING,
                    Employee.Status.PENDING_APPROVAL,
                ]
            ).order_by("status", "date_joined", "first_name", "last_name")
            context["employee_count"] = context["employees"].count()
            response = render(request, self.onboarding_approvals_template, context)
        elif resolved["leaf"] == "client-management":
            context["clients"] = Client.objects.filter(
                status__in=[
                    Client.Status.ACTIVE,
                    Client.Status.SUSPENDED,
                ]
            ).order_by("status", "company_name", "first_name", "last_name", "email")
            context["client_count"] = context["clients"].count()
            response = render(request, self.client_management_template, context)
        elif resolved["leaf"] == "register-client":
            context.update(self._register_client_context(user))
            response = render(request, self.register_client_template, context)
        elif resolved["leaf"] == "approve-pending-clients":
            context["clients"] = Client.objects.filter(
                status__in=[
                    Client.Status.PENDING_ONBOARDING,
                    Client.Status.PENDING_APPROVAL,
                ]
            ).order_by("status", "date_joined", "company_name", "first_name", "last_name")
            context["client_count"] = context["clients"].count()
            response = render(
                request, self.approve_pending_clients_template, context
            )
        elif resolved["leaf"] == "litigation-matters":
            cases = list(
                LitigationCase.objects.filter(
                    status=LitigationCase.Status.ACTIVE
                )
                .select_related("client", "assigned_to", "registered_by")
                .prefetch_related("parties")
                .order_by("-filing_date", "-created_at")
            )
            group_by, case_groups = group_litigation_cases(
                cases, request.GET.get("group", "client")
            )
            context["cases"] = cases
            context["case_count"] = len(cases)
            context["group_by"] = group_by
            context["case_groups"] = case_groups
            response = render(request, self.litigation_matters_template, context)
        elif resolved["leaf"] == "register-case":
            context.update(self._register_case_context())
            response = render(request, self.register_case_template, context)
        elif resolved["leaf"] == "approve-registered-cases":
            context["cases"] = (
                LitigationCase.objects.filter(
                    status=LitigationCase.Status.PENDING_APPROVAL
                )
                .select_related("client", "registered_by")
                .prefetch_related("parties")
                .order_by("created_at", "filing_date")
            )
            context["case_count"] = context["cases"].count()
            response = render(
                request, self.approve_registered_cases_template, context
            )
        elif resolved["leaf"] == "non-litigation-matters":
            matters = list(
                NonLitigationMatter.objects.filter(
                    status=NonLitigationMatter.Status.ACTIVE
                )
                .select_related("client", "assigned_to", "registered_by")
                .prefetch_related("parties")
                .order_by("-date_opened", "-created_at")
            )
            group_by, matter_groups = group_non_litigation_matters(
                matters, request.GET.get("group", "client")
            )
            context["matters"] = matters
            context["matter_count"] = len(matters)
            context["group_by"] = group_by
            context["matter_groups"] = matter_groups
            response = render(
                request, self.non_litigation_matters_template, context
            )
        elif resolved["leaf"] == "register-new-matter":
            context.update(self._register_matter_context())
            response = render(request, self.register_matter_template, context)
        elif resolved["leaf"] == "approve-registered-matters":
            context["matters"] = (
                NonLitigationMatter.objects.filter(
                    status=NonLitigationMatter.Status.PENDING_APPROVAL
                )
                .select_related("client", "registered_by")
                .prefetch_related("parties")
                .order_by("created_at", "date_opened")
            )
            context["matter_count"] = context["matters"].count()
            response = render(
                request, self.approve_registered_matters_template, context
            )
        elif resolved["leaf"] == "tasks":
            context.update(self._tasks_context(user, request))
            response = render(request, self.tasks_template, context)
        elif resolved["leaf"] == "messages":
            context.update(self._messages_context(user, request))
            response = render(request, self.messages_template, context)
        elif resolved["leaf"] == "calendar":
            context.update(self._calendar_context(user, request))
            response = render(request, self.calendar_template, context)
        elif resolved["leaf"] == "reminders":
            context.update(self._reminders_context(user, request))
            response = render(request, self.reminders_template, context)
        else:
            response = render(request, self.page_template, context)

        return attach_greeting_cookie(response, request)

    def post(self, request, role, pages="dashboard"):
        user = request.user
        if user.status != Employee.Status.ACTIVE:
            return redirect_for_employee(request, user)
        if Employee.role_from_slug(role) is None:
            return redirect(user.dashboard_url)
        if role != user.role_slug:
            return redirect(user.workspace_url(*pages.strip("/").split("/")))

        resolved = resolve_workspace_page(user.role, pages)
        if not resolved or resolved["leaf"] not in {
            "settings",
            "theme-settings",
            "notification-settings",
            "about-me",
            "my-blogs",
            "my-blogs-new",
            "company-profile",
            "company-contacts",
            "about-company",
            "practice-areas",
            "practice-areas-new",
            "company-faqs",
            "company-faqs-new",
            "company-gallery",
            "company-gallery-new",
            "company-terms",
            "website-template",
            "finance-settings",
            "register-case",
            "register-new-matter",
            "register-client",
            "register-employee",
            "generate-invoice",
        }:
            return redirect(user.dashboard_url)

        if resolved["leaf"] in {
            "settings",
            "theme-settings",
            "notification-settings",
            "about-me",
            "my-blogs",
            "my-blogs-new",
        }:
            return self._post_settings(request, user, resolved)

        if resolved["leaf"] == "website-template":
            return self._post_website_template(request, user, resolved)

        if resolved["leaf"] == "finance-settings":
            return self._post_finance_settings(request, user, resolved)

        if resolved["leaf"] == "company-profile":
            return self._post_company_profile(request, user, resolved)

        if resolved["leaf"] == "company-contacts":
            return self._post_company_contacts(request, user, resolved)

        if resolved["leaf"] == "about-company":
            return self._post_about_company(request, user, resolved)

        if resolved["leaf"] in {"practice-areas", "practice-areas-new"}:
            return self._post_practice_area(request, user, resolved)

        if resolved["leaf"] in {"company-faqs", "company-faqs-new"}:
            return self._post_company_faq(request, user, resolved)

        if resolved["leaf"] in {"company-gallery", "company-gallery-new"}:
            return self._post_company_gallery(request, user, resolved)

        if resolved["leaf"] == "company-terms":
            return self._post_company_terms(request, user, resolved)

        if resolved["leaf"] == "register-client":
            return self._post_register_client(request, user, resolved)

        if resolved["leaf"] == "register-employee":
            return self._post_register_employee(request, user, resolved)

        if resolved["leaf"] == "generate-invoice":
            return self._post_generate_invoice(request, user, resolved)

        if resolved["leaf"] == "register-new-matter":
            return self._post_register_matter(request, user, resolved)

        form = RegisterCaseForm(request.POST)
        party_formset = CasePartyFormSet(request.POST, prefix="parties")
        context = workspace_context(
            user,
            request=request,
            page_title=resolved["page_title"],
            page_trail=resolved["trail"],
            active_page=resolved["leaf"],
        )

        if form.is_valid() and party_formset.is_valid():
            parties = [
                f
                for f in party_formset
                if f.cleaned_data and not f.cleaned_data.get("DELETE")
            ]
            if not parties:
                messages.error(request, "Add at least one party.")
                context.update(self._register_case_context(form, party_formset))
                response = render(request, self.register_case_template, context)
                return attach_greeting_cookie(response, request)

            case = form.save(commit=False)
            case.registered_by = user
            case.status = LitigationCase.Status.PENDING_APPROVAL
            case.save()

            for index, party_form in enumerate(parties):
                party = party_form.save(commit=False)
                party.case = case
                party.sort_order = index
                if index == 0:
                    party.is_client_party = True
                party.save()

            messages.success(
                request,
                f"Case registered for {case.client.get_full_name()} and is "
                "pending approval.",
            )
            return redirect(user.workspace_url(*PENDING_CASES_TRAIL))

        context.update(self._register_case_context(form, party_formset))
        response = render(request, self.register_case_template, context)
        return attach_greeting_cookie(response, request)

    def _post_settings(self, request, user, resolved):
        action = (request.POST.get("settings_action") or "").strip()
        context = workspace_context(
            user,
            request=request,
            page_title=resolved["page_title"],
            page_trail=resolved["trail"],
            active_page=None,
        )

        if action == "appearance":
            # Bound only to the signed-in employee — never firm/system settings.
            appearance_form = AppearanceSettingsForm(request.POST, instance=user)
            profile_form = ProfileSettingsForm(instance=user)
            notification_form = NotificationSettingsForm(instance=user)
            about_me_form = AboutMeForm(instance=user)
            if appearance_form.is_valid():
                appearance_form.save()
                messages.success(
                    request,
                    "Your appearance preferences were saved for your account only.",
                )
                return redirect(user.workspace_url(*resolved["trail"]))
            context.update(
                self._settings_context(
                    user,
                    profile_form=profile_form,
                    appearance_form=appearance_form,
                    notification_form=notification_form,
                    about_me_form=about_me_form,
                )
            )
            response = render(request, self.theme_settings_template, context)
            return attach_greeting_cookie(response, request)

        if action == "about_me":
            about_me_form = AboutMeForm(request.POST, instance=user)
            profile_form = ProfileSettingsForm(instance=user)
            appearance_form = AppearanceSettingsForm(instance=user)
            notification_form = NotificationSettingsForm(instance=user)
            about_trail = extend_page_trail(list(resolved["trail"]), "about-me")
            if about_me_form.is_valid():
                about_me_form.save()
                messages.success(request, "About me saved to your profile.")
                return redirect(user.workspace_url(*about_trail))
            context.update(
                self._settings_context(
                    user,
                    profile_form=profile_form,
                    appearance_form=appearance_form,
                    notification_form=notification_form,
                    about_me_form=about_me_form,
                )
            )
            response = render(request, self.about_me_template, context)
            return attach_greeting_cookie(response, request)

        if action == "blog":
            blogs_trail = extend_page_trail(list(resolved["trail"]), "my-blogs")
            blog_form = EmployeeBlogForm(request.POST, request.FILES)
            if blog_form.is_valid():
                post = blog_form.save(author=user)
                if post.status == EmployeeBlogPost.Status.SUBMITTED:
                    messages.success(
                        request,
                        "Blog post submitted for approval. It will appear on the website once approved.",
                    )
                else:
                    messages.success(
                        request,
                        "Blog post saved as a draft. Submit it for approval when it is ready.",
                    )
                return redirect(user.workspace_url(*blogs_trail))
            context.update(self._my_blog_form_context(user, form=blog_form))
            response = render(request, self.my_blog_form_template, context)
            return attach_greeting_cookie(response, request)

        if action == "notifications":
            notification_form = NotificationSettingsForm(
                request.POST, instance=user
            )
            profile_form = ProfileSettingsForm(instance=user)
            appearance_form = AppearanceSettingsForm(instance=user)
            about_me_form = AboutMeForm(instance=user)
            notify_trail = extend_page_trail(
                list(resolved["trail"]), "notification-settings"
            )
            if notification_form.is_valid():
                notification_form.save()
                messages.success(request, "Notification preferences saved.")
                return redirect(user.workspace_url(*notify_trail))
            context.update(
                self._settings_context(
                    user,
                    profile_form=profile_form,
                    appearance_form=appearance_form,
                    notification_form=notification_form,
                    about_me_form=about_me_form,
                )
            )
            response = render(
                request, self.notification_settings_template, context
            )
            return attach_greeting_cookie(response, request)

        if resolved["leaf"] == "notification-settings":
            return redirect(
                user.workspace_url(
                    *extend_page_trail(
                        list(resolved["trail"]), "notification-settings"
                    )
                )
            )

        if resolved["leaf"] == "about-me":
            return redirect(
                user.workspace_url(
                    *extend_page_trail(list(resolved["trail"]), "about-me")
                )
            )

        if resolved["leaf"] in {"my-blogs", "my-blogs-new"}:
            return redirect(
                user.workspace_url(
                    *extend_page_trail(list(resolved["trail"]), "my-blogs")
                )
            )

        profile_form = ProfileSettingsForm(
            request.POST, request.FILES, instance=user
        )
        appearance_form = AppearanceSettingsForm(instance=user)
        notification_form = NotificationSettingsForm(instance=user)
        about_me_form = AboutMeForm(instance=user)
        if profile_form.is_valid():
            profile_form.save_with_request(request)
            if profile_form.cleaned_data.get("new_password"):
                messages.success(
                    request,
                    "Profile and password updated for your account.",
                )
            else:
                messages.success(request, "Profile details updated.")
            return redirect(user.workspace_url(*resolved["trail"]))

        context.update(
            self._settings_context(
                user,
                profile_form=profile_form,
                appearance_form=appearance_form,
                notification_form=notification_form,
                about_me_form=about_me_form,
                open_edit=True,
            )
        )
        response = render(request, self.settings_template, context)
        return attach_greeting_cookie(response, request)

    @staticmethod
    def _settings_context(
        user,
        *,
        profile_form=None,
        appearance_form=None,
        notification_form=None,
        about_me_form=None,
        open_edit=False,
        open_view=False,
    ):
        resolved_appearance = appearance_form or AppearanceSettingsForm(instance=user)
        form_theme = resolved_appearance["ui_theme"].value() or user.ui_theme
        catalog = appearance_catalog(current_theme=form_theme)
        theme_key = (
            Employee.UiTheme.DEFAULT
            if (form_theme or "") in {"", "product", "default"}
            else form_theme
        )
        return {
            "profile_form": profile_form or ProfileSettingsForm(instance=user),
            "appearance_form": resolved_appearance,
            "notification_form": notification_form
            or NotificationSettingsForm(instance=user),
            "about_me_form": about_me_form or AboutMeForm(instance=user),
            "nationality_label": country_name(user.id_country),
            "theme_groups": catalog["theme_groups"],
            "font_catalog": catalog["font_catalog"],
            "density_catalog": catalog["density_catalog"],
            "theme_count": catalog["theme_count"],
            "font_count": catalog["font_count"],
            "theme_choices": Employee.UiTheme.choices,
            "font_choices": Employee.UiFont.choices,
            "open_edit_modal": open_edit,
            "open_view_modal": open_view,
            "current_theme_label": dict(Employee.UiTheme.choices).get(
                theme_key,
                "Black & White",
            ),
            "current_font_label": dict(Employee.UiFont.choices).get(
                user.workspace_font, "Plex Chambers"
            ),
            "current_density_label": dict(Employee.UiDensity.choices).get(
                user.workspace_density, "Comfortable"
            ),
            "notification_sound_enabled": bool(user.notification_sound),
        }

    @staticmethod
    def _my_blogs_context(user):
        return {
            "blog_posts": list(
                EmployeeBlogPost.objects.filter(author=user).order_by(
                    "-updated_at", "-created_at"
                )
            ),
            "public_blog_list_url": reverse("accounts:blog_list"),
        }

    @staticmethod
    def _my_blog_form_context(user, *, form=None, post=None):
        if form is not None:
            blog_form = form
        elif post is not None:
            blog_form = EmployeeBlogForm(instance=post)
        else:
            blog_form = EmployeeBlogForm()

        if form is not None and form.is_bound:
            draft = EmployeeBlogPost(
                title=form.data.get("title", ""),
                body=form.data.get("body", ""),
                excerpt=form.data.get("excerpt", ""),
                meta_title=form.data.get("meta_title", ""),
                meta_description=form.data.get("meta_description", ""),
                focus_keyword=form.data.get("focus_keyword", ""),
                tags=form.data.get("tags", ""),
                slug=form.data.get("slug", ""),
            )
            if (
                post is not None
                and post.cover_image
                and not form.data.get("clear_cover")
            ):
                draft.cover_image = post.cover_image
            seo = draft.seo_checklist()
        elif post is not None:
            seo = post.seo_checklist()
        else:
            seo = EmployeeBlogPost(
                title="",
                body="",
                excerpt="",
                meta_title="",
                meta_description="",
                focus_keyword="",
                tags="",
                slug="",
            ).seo_checklist()

        return {
            "blog_form": blog_form,
            "blog_post": post,
            "seo_checklist": seo,
            "public_blog_list_url": reverse("accounts:blog_list"),
            "public_post_url": (
                post.get_absolute_url()
                if post is not None and post.is_public
                else ""
            ),
        }

    @staticmethod
    def _company_profile_context(*, form=None):
        company = FirmCompanyInformation.get_solo()
        existing_images = list(
            company.profile_images.order_by("sort_order", "id")
        )
        return {
            "company_information": company,
            "existing_images": existing_images,
            "form": form or CompanyInformationForm(instance=company),
        }

    @staticmethod
    def _sync_company_profile_images(request, company, *, append=True):
        """Apply deletes, reorder, and newly uploaded company profile images."""
        delete_ids = request.POST.getlist("delete_images")
        if delete_ids:
            company.profile_images.filter(pk__in=delete_ids).delete()

        for image in company.profile_images.all():
            raw = request.POST.get(f"image_order_{image.pk}")
            if raw is None or raw == "":
                continue
            try:
                image.sort_order = max(0, int(raw))
            except (TypeError, ValueError):
                continue
            image.save(update_fields=["sort_order"])

        uploads = request.FILES.getlist("images")
        if uploads:
            start = 0
            if append:
                last = (
                    company.profile_images.order_by("-sort_order")
                    .values_list("sort_order", flat=True)
                    .first()
                )
                start = (last + 1) if last is not None else 0
            for index, uploaded in enumerate(uploads):
                optimized = optimize_image(uploaded, max_size=1600, quality=78)
                FirmCompanyProfileImage.objects.create(
                    company=company,
                    image=optimized,
                    sort_order=start + index,
                )

        for index, image in enumerate(
            company.profile_images.order_by("sort_order", "id")
        ):
            if image.sort_order != index:
                image.sort_order = index
                image.save(update_fields=["sort_order"])

    @staticmethod
    def _company_contacts_context(*, form=None):
        company = FirmCompanyInformation.get_solo()
        return {
            "company_information": company,
            "form": form or CompanyContactsForm(instance=company),
        }

    @staticmethod
    def _about_company_context(*, form=None):
        company = FirmCompanyInformation.get_solo()
        form = form or AboutCompanyForm(instance=company)
        if form.is_bound:
            selected = set(form.data.getlist("selected_values"))
        else:
            selected = set(form.fields["selected_values"].initial or [])
        value_rows = [
            {
                "label": label,
                "field": form[field_name],
                "checked": label in selected,
            }
            for label, field_name in form.value_how_fields
        ]
        return {
            "company_information": company,
            "form": form,
            "value_rows": value_rows,
        }

    def _post_company_profile(self, request, user, resolved):
        company = FirmCompanyInformation.get_solo()
        form = CompanyInformationForm(request.POST, request.FILES, instance=company)
        context = workspace_context(
            user,
            request=request,
            page_title=resolved["page_title"],
            page_trail=resolved["trail"],
            active_page=resolved["leaf"],
        )
        if form.is_valid():
            info = form.save(commit=False)
            info.updated_by = user
            info.save()
            self._sync_company_profile_images(request, info, append=True)
            messages.success(request, "Company profile saved.")
            return redirect(user.workspace_url(*resolved["trail"]))

        context.update(self._company_profile_context(form=form))
        response = render(request, self.company_profile_template, context)
        return attach_greeting_cookie(response, request)

    def _post_company_contacts(self, request, user, resolved):
        company = FirmCompanyInformation.get_solo()
        form = CompanyContactsForm(request.POST, instance=company)
        context = workspace_context(
            user,
            request=request,
            page_title=resolved["page_title"],
            page_trail=resolved["trail"],
            active_page=resolved["leaf"],
        )
        if form.is_valid():
            info = form.save(commit=False)
            info.updated_by = user
            info.save()
            messages.success(request, "Company contacts saved.")
            return redirect(user.workspace_url(*resolved["trail"]))

        context.update(self._company_contacts_context(form=form))
        response = render(request, self.company_contacts_template, context)
        return attach_greeting_cookie(response, request)

    def _post_about_company(self, request, user, resolved):
        company = FirmCompanyInformation.get_solo()
        form = AboutCompanyForm(request.POST, instance=company)
        context = workspace_context(
            user,
            request=request,
            page_title=resolved["page_title"],
            page_trail=resolved["trail"],
            active_page=resolved["leaf"],
        )
        if form.is_valid():
            info = form.save(commit=False)
            info.updated_by = user
            info.save()
            messages.success(request, "About company saved.")
            return redirect(user.workspace_url(*resolved["trail"]))

        context.update(self._about_company_context(form=form))
        response = render(request, self.about_company_template, context)
        return attach_greeting_cookie(response, request)

    @staticmethod
    def _practice_areas_list_url(user):
        return user.workspace_url("dashboard", "practice-areas")

    @staticmethod
    def _practice_areas_new_url(user):
        return user.workspace_url("dashboard", "practice-areas-new")

    @staticmethod
    def _practice_areas_context(user):
        areas = list(
            FirmPracticeArea.objects.prefetch_related("images").order_by(
                "rank", "name"
            )
        )
        return {
            "practice_areas": areas,
            "practice_areas_new_url": RoleWorkspaceView._practice_areas_new_url(
                user
            ),
        }

    @staticmethod
    def _practice_area_form_context(user, *, form=None, practice_area=None):
        form = form or PracticeAreaForm(instance=practice_area)
        existing_images = []
        if practice_area and practice_area.pk:
            existing_images = list(
                practice_area.images.order_by("sort_order", "id")
            )
        return {
            "form": form,
            "practice_area": practice_area,
            "existing_images": existing_images,
            "practice_areas_url": RoleWorkspaceView._practice_areas_list_url(user),
        }

    @staticmethod
    def _sync_practice_area_images(request, practice_area, *, append=True):
        """Apply deletes, reorder, and newly uploaded images."""
        delete_ids = request.POST.getlist("delete_images")
        if delete_ids:
            practice_area.images.filter(pk__in=delete_ids).delete()

        for image in practice_area.images.all():
            raw = request.POST.get(f"image_order_{image.pk}")
            if raw is None or raw == "":
                continue
            try:
                image.sort_order = max(0, int(raw))
            except (TypeError, ValueError):
                continue
            image.save(update_fields=["sort_order"])

        uploads = request.FILES.getlist("images")
        if uploads:
            start = 0
            if append:
                last = (
                    practice_area.images.order_by("-sort_order")
                    .values_list("sort_order", flat=True)
                    .first()
                )
                start = (last + 1) if last is not None else 0
            for index, uploaded in enumerate(uploads):
                optimized = optimize_image(uploaded, max_size=1600, quality=78)
                FirmPracticeAreaImage.objects.create(
                    practice_area=practice_area,
                    image=optimized,
                    sort_order=start + index,
                )

        # Normalize so the lowest order is 0 (main image).
        for index, image in enumerate(
            practice_area.images.order_by("sort_order", "id")
        ):
            if image.sort_order != index:
                image.sort_order = index
                image.save(update_fields=["sort_order"])

    def _post_practice_area(self, request, user, resolved):
        # List page only supports create via the dedicated new URL.
        if resolved["leaf"] == "practice-areas":
            return redirect(self._practice_areas_new_url(user))

        form = PracticeAreaForm(request.POST, request.FILES)
        context = workspace_context(
            user,
            request=request,
            page_title=resolved["page_title"],
            page_trail=resolved["trail"],
            active_page=resolved["leaf"],
        )
        if form.is_valid():
            area = form.save(commit=False)
            area.updated_by = user
            area.save()
            self._sync_practice_area_images(request, area, append=False)
            messages.success(request, f"Practice area “{area.name}” added.")
            return redirect(self._practice_areas_list_url(user))

        context.update(self._practice_area_form_context(user, form=form))
        response = render(request, self.practice_area_form_template, context)
        return attach_greeting_cookie(response, request)

    @staticmethod
    def _company_faqs_list_url(user):
        return user.workspace_url("dashboard", "company-faqs")

    @staticmethod
    def _company_faqs_new_url(user):
        return user.workspace_url("dashboard", "company-faqs-new")

    @staticmethod
    def _company_blogs_list_url(user):
        return user.workspace_url("dashboard", "company-blogs")

    @staticmethod
    def _research_blogs_context(user):
        my_posts = EmployeeBlogPost.objects.filter(author=user)
        firm_posts = list(
            EmployeeBlogPost.objects.exclude(status=EmployeeBlogPost.Status.DRAFT)
            .select_related("author", "approved_by")
            .order_by("-updated_at", "-created_at")
        )
        pending_count = sum(
            1
            for post in firm_posts
            if post.status == EmployeeBlogPost.Status.SUBMITTED
        )
        published_count = sum(
            1
            for post in firm_posts
            if post.status == EmployeeBlogPost.Status.PUBLISHED
        )
        return {
            "firm_blog_posts": firm_posts,
            "firm_blog_count": len(firm_posts),
            "my_blog_count": my_posts.count(),
            "my_draft_count": my_posts.filter(
                status=EmployeeBlogPost.Status.DRAFT
            ).count(),
            "my_submitted_count": my_posts.filter(
                status=EmployeeBlogPost.Status.SUBMITTED
            ).count(),
            "my_published_count": my_posts.filter(
                status=EmployeeBlogPost.Status.PUBLISHED
            ).count(),
            "pending_blog_count": pending_count,
            "published_blog_count": published_count,
            "my_blogs_url": user.workspace_url("dashboard", "my-blogs"),
            "my_blogs_new_url": user.workspace_url("dashboard", "my-blogs-new"),
            "company_blogs_url": RoleWorkspaceView._company_blogs_list_url(user),
            "public_blog_list_url": reverse("accounts:blog_list"),
        }

    @staticmethod
    def _company_blogs_context(user):
        pending = list(
            EmployeeBlogPost.objects.filter(
                status=EmployeeBlogPost.Status.SUBMITTED
            )
            .select_related("author")
            .order_by("submitted_at", "updated_at")
        )
        published = list(
            EmployeeBlogPost.objects.filter(
                status=EmployeeBlogPost.Status.PUBLISHED
            )
            .select_related("author", "approved_by")
            .order_by("-published_at", "-updated_at")
        )
        return {
            "pending_blog_posts": pending,
            "published_blog_posts": published,
            "pending_blog_count": len(pending),
            "published_blog_count": len(published),
            "public_blog_list_url": reverse("accounts:blog_list"),
        }

    @staticmethod
    def _company_faqs_context(user):
        faqs = list(FirmFAQ.objects.order_by("rank", "question"))
        return {
            "faqs": faqs,
            "company_faqs_new_url": RoleWorkspaceView._company_faqs_new_url(
                user
            ),
        }

    @staticmethod
    def _company_faq_form_context(user, *, form=None, faq=None):
        form = form or FAQForm(instance=faq)
        return {
            "form": form,
            "faq": faq,
            "company_faqs_url": RoleWorkspaceView._company_faqs_list_url(user),
        }

    def _post_company_faq(self, request, user, resolved):
        if resolved["leaf"] == "company-faqs":
            return redirect(self._company_faqs_new_url(user))

        form = FAQForm(request.POST)
        context = workspace_context(
            user,
            request=request,
            page_title=resolved["page_title"],
            page_trail=resolved["trail"],
            active_page=resolved["leaf"],
        )
        if form.is_valid():
            faq = form.save(commit=False)
            faq.updated_by = user
            faq.save()
            messages.success(request, f"FAQ “{faq.question}” added.")
            return redirect(self._company_faqs_list_url(user))

        context.update(self._company_faq_form_context(user, form=form))
        response = render(request, self.company_faq_form_template, context)
        return attach_greeting_cookie(response, request)

    @staticmethod
    def _company_gallery_list_url(user):
        return user.workspace_url("dashboard", "company-gallery")

    @staticmethod
    def _company_gallery_new_url(user):
        return user.workspace_url("dashboard", "company-gallery-new")

    @staticmethod
    def _company_gallery_context(user):
        items = list(FirmGalleryImage.objects.order_by("rank", "title"))
        return {
            "gallery_items": items,
            "company_gallery_new_url": RoleWorkspaceView._company_gallery_new_url(
                user
            ),
        }

    @staticmethod
    def _company_gallery_form_context(user, *, form=None, item=None):
        return {
            "form": form or GalleryImageForm(instance=item),
            "gallery_item": item,
            "company_gallery_url": RoleWorkspaceView._company_gallery_list_url(
                user
            ),
        }

    def _post_company_gallery(self, request, user, resolved):
        if resolved["leaf"] == "company-gallery":
            return redirect(self._company_gallery_new_url(user))

        form = GalleryImageForm(request.POST, request.FILES)
        context = workspace_context(
            user,
            request=request,
            page_title=resolved["page_title"],
            page_trail=resolved["trail"],
            active_page=resolved["leaf"],
        )
        if form.is_valid():
            item = form.save(commit=False)
            item.updated_by = user
            item.save()
            messages.success(request, f"Gallery item “{item.title}” added.")
            return redirect(self._company_gallery_list_url(user))

        context.update(self._company_gallery_form_context(user, form=form))
        response = render(request, self.company_gallery_form_template, context)
        return attach_greeting_cookie(response, request)

    @staticmethod
    def _company_terms_context(*, form=None):
        company = FirmCompanyInformation.get_solo()
        return {
            "company_information": company,
            "form": form or CompanyTermsForm(instance=company),
        }

    def _post_company_terms(self, request, user, resolved):
        company = FirmCompanyInformation.get_solo()
        form = CompanyTermsForm(request.POST, instance=company)
        context = workspace_context(
            user,
            request=request,
            page_title=resolved["page_title"],
            page_trail=resolved["trail"],
            active_page=resolved["leaf"],
        )
        if form.is_valid():
            info = form.save(commit=False)
            info.updated_by = user
            info.save()
            messages.success(request, "Terms and conditions saved.")
            return redirect(user.workspace_url(*resolved["trail"]))

        context.update(self._company_terms_context(form=form))
        response = render(request, self.company_terms_template, context)
        return attach_greeting_cookie(response, request)

    @staticmethod
    def _website_template_context(user, *, form=None):
        setting = WebsiteTemplateSetting.get_solo()
        return {
            "website_setting": setting,
            "form": form or WebsiteTemplateForm(instance=setting),
            "company_information_url": user.workspace_url(
                "dashboard", "company-information"
            ),
        }

    def _post_website_template(self, request, user, resolved):
        setting = WebsiteTemplateSetting.get_solo()
        form = WebsiteTemplateForm(request.POST, instance=setting)
        context = workspace_context(
            user,
            request=request,
            page_title=resolved["page_title"],
            page_trail=resolved["trail"],
            active_page=resolved["leaf"],
        )
        if form.is_valid():
            choice = form.save(commit=False)
            choice.updated_by = user
            choice.save()
            messages.success(
                request,
                f"Homepage set to {choice.get_active_template_display()}.",
            )
            return redirect(user.workspace_url(*resolved["trail"]))

        context.update(self._website_template_context(user, form=form))
        response = render(request, self.website_template_template, context)
        return attach_greeting_cookie(response, request)

    @staticmethod
    def _finance_settings_context(*, form=None):
        setting = FinanceSettings.get_solo()
        from .mpesa import MPESA_CALLBACK_PATH, is_valid_mpesa_callback_url

        return {
            "finance_setting": setting,
            "form": form or FinanceSettingsForm(instance=setting),
            "stk_ready": setting.stk_ready,
            "mpesa_callback_path": MPESA_CALLBACK_PATH,
            "mpesa_callback_valid": is_valid_mpesa_callback_url(
                setting.mpesa_callback_url or ""
            ),
        }

    def _post_finance_settings(self, request, user, resolved):
        setting = FinanceSettings.get_solo()
        form = FinanceSettingsForm(request.POST, instance=setting)
        context = workspace_context(
            user,
            request=request,
            page_title=resolved["page_title"],
            page_trail=resolved["trail"],
            active_page=resolved["leaf"],
        )
        if form.is_valid():
            choice = form.save(commit=False)
            choice.updated_by = user
            choice.save()
            methods = ", ".join(choice.enabled_payment_methods) or "none"
            messages.success(
                request,
                f"Finance settings saved. Allowed methods: {methods}.",
            )
            return redirect(user.workspace_url(*resolved["trail"]))

        context.update(self._finance_settings_context(form=form))
        response = render(request, self.finance_settings_template, context)
        return attach_greeting_cookie(response, request)

    @staticmethod
    def _google_drive_settings_context(request, resolved):
        connection = GoogleDriveConnection.get_solo()
        host = request.get_host()
        on_loopback = is_loopback_host(host)
        on_private_lan = is_private_lan_host(host)
        can_connect = can_start_google_oauth(host)
        trail = "/".join(resolved["trail"])
        localhost_settings_url = (
            f"http://localhost:8000/{request.user.role_slug}/{trail}/"
        )
        root_name = firm_root_folder_name()
        return {
            "google_drive": connection,
            "google_drive_connected": connection.is_connected,
            "google_drive_has_structure": connection.has_folder_structure,
            "google_oauth_ready": google_oauth_configured(),
            "google_oauth_can_connect": can_connect,
            "google_oauth_on_loopback": on_loopback,
            "google_oauth_on_private_lan": on_private_lan,
            "google_oauth_redirect_uri": build_redirect_uri(request),
            "google_localhost_settings_url": localhost_settings_url,
            "google_connect_url": reverse("accounts:google_drive_connect"),
            "google_disconnect_url": reverse("accounts:google_drive_disconnect"),
            "firm_drive_root_name": root_name,
            "google_drive_web_url": (
                f"https://drive.google.com/drive/folders/{connection.root_folder_id}"
                if connection.root_folder_id
                else ""
            ),
        }

    def _post_register_client(self, request, user, resolved):
        form = ClientSignUpForm(request.POST, request.FILES)
        context = workspace_context(
            user,
            request=request,
            page_title=resolved["page_title"],
            page_trail=resolved["trail"],
            active_page=resolved["leaf"],
        )

        if form.is_valid():
            client = form.save()
            messages.success(
                request,
                f"{client.get_full_name()} has been registered and is "
                "pending onboarding.",
            )
            return redirect(
                user.workspace_url(
                    "dashboard",
                    "user-management",
                    "client-management",
                )
            )

        context.update(self._register_client_context(user, form))
        response = render(request, self.register_client_template, context)
        return attach_greeting_cookie(response, request)

    @staticmethod
    def _register_client_context(user, form=None):
        return {
            "form": form or ClientSignUpForm(),
            "list_url": user.workspace_url(
                "dashboard",
                "user-management",
                "client-management",
            ),
        }

    def _post_register_employee(self, request, user, resolved):
        form = SignUpForm(request.POST, request.FILES)
        context = workspace_context(
            user,
            request=request,
            page_title=resolved["page_title"],
            page_trail=resolved["trail"],
            active_page=resolved["leaf"],
        )

        if form.is_valid():
            employee = form.save()
            messages.success(
                request,
                f"{employee.get_full_name()} has been registered and is "
                "pending onboarding.",
            )
            return redirect(
                user.workspace_url(
                    "dashboard",
                    "user-management",
                    "employee-management",
                )
            )

        context.update(self._register_employee_context(user, form))
        response = render(request, self.register_employee_template, context)
        return attach_greeting_cookie(response, request)

    @staticmethod
    def _register_employee_context(user, form=None):
        return {
            "form": form or SignUpForm(),
            "list_url": user.workspace_url(
                "dashboard",
                "user-management",
                "employee-management",
            ),
        }

    @staticmethod
    def _invoicing_url(user, trail):
        clean = [part for part in trail if part and part != "generate-invoice"]
        if not clean or clean[-1] != "invoicing":
            clean = extend_page_trail(clean, "invoicing")
        return user.workspace_url(*clean)

    @classmethod
    def _generate_invoice_context(cls, user, resolved, form=None):
        return {
            "form": form or GenerateInvoiceForm(),
            "invoicing_url": cls._invoicing_url(user, resolved["trail"]),
        }

    def _post_generate_invoice(self, request, user, resolved):
        form = GenerateInvoiceForm(request.POST)
        context = workspace_context(
            user,
            request=request,
            page_title=resolved["page_title"],
            page_trail=resolved["trail"],
            active_page=resolved["leaf"],
        )

        if form.is_valid():
            invoice = form.save(commit=False)
            invoice.invoice_number = Invoice.next_invoice_number()
            invoice.created_by = user
            invoice.status = Invoice.Status.GENERATED
            invoice.save()
            messages.success(
                request,
                f"Invoice {invoice.invoice_number} generated for "
                f"{invoice.client.get_full_name()}.",
            )
            return redirect(self._invoicing_url(user, resolved["trail"]))

        context.update(self._generate_invoice_context(user, resolved, form))
        response = render(request, self.generate_invoice_template, context)
        return attach_greeting_cookie(response, request)

    def _post_register_matter(self, request, user, resolved):
        form = RegisterMatterForm(request.POST)
        party_formset = MatterPartyFormSet(request.POST, prefix="parties")
        context = workspace_context(
            user,
            request=request,
            page_title=resolved["page_title"],
            page_trail=resolved["trail"],
            active_page=resolved["leaf"],
        )

        if form.is_valid() and party_formset.is_valid():
            parties = [
                f
                for f in party_formset
                if f.cleaned_data and not f.cleaned_data.get("DELETE")
            ]
            if not parties:
                messages.error(request, "Add at least one party.")
                context.update(self._register_matter_context(form, party_formset))
                response = render(request, self.register_matter_template, context)
                return attach_greeting_cookie(response, request)

            matter = form.save(commit=False)
            matter.registered_by = user
            matter.status = NonLitigationMatter.Status.PENDING_APPROVAL
            matter.save()

            for index, party_form in enumerate(parties):
                party = party_form.save(commit=False)
                party.matter = matter
                party.sort_order = index
                if index == 0:
                    party.is_client_party = True
                party.save()

            messages.success(
                request,
                f"Matter registered for {matter.client.get_full_name()} and is "
                "pending approval.",
            )
            return redirect(user.workspace_url(*PENDING_MATTERS_TRAIL))

        context.update(self._register_matter_context(form, party_formset))
        response = render(request, self.register_matter_template, context)
        return attach_greeting_cookie(response, request)

    @staticmethod
    def _register_case_context(form=None, party_formset=None):
        form = form or RegisterCaseForm()
        party_formset = party_formset or CasePartyFormSet(
            prefix="parties",
            initial=[{"is_client_party": True}],
        )
        selected_client = None
        client_id = form["client"].value() if form.is_bound else form.initial.get("client")
        if client_id:
            selected_client = Client.objects.filter(
                pk=client_id, status=Client.Status.ACTIVE
            ).first()
        return {
            "form": form,
            "party_formset": party_formset,
            "client_search_url": reverse("accounts:workspace_client_search"),
            "field_suggestions_url": reverse(
                "accounts:workspace_case_field_suggestions"
            ),
            "selected_client": selected_client,
        }

    @staticmethod
    def _register_matter_context(form=None, party_formset=None):
        form = form or RegisterMatterForm()
        party_formset = party_formset or MatterPartyFormSet(
            prefix="parties",
            initial=[{"is_client_party": True}],
        )
        selected_client = None
        client_id = form["client"].value() if form.is_bound else form.initial.get("client")
        if client_id:
            selected_client = Client.objects.filter(
                pk=client_id, status=Client.Status.ACTIVE
            ).first()
        return {
            "form": form,
            "party_formset": party_formset,
            "client_search_url": reverse("accounts:workspace_client_search"),
            "field_suggestions_url": reverse(
                "accounts:workspace_case_field_suggestions"
            ),
            "selected_client": selected_client,
        }

    @staticmethod
    def _tasks_context(user, request):
        """Build assignee-only task list for the Tasks utility page."""
        case_tasks = list(
            CaseTask.objects.filter(assignee=user)
            .select_related("case", "case__client", "created_by")
            .order_by("-created_at")
        )
        matter_tasks = list(
            MatterTask.objects.filter(assignee=user)
            .select_related("matter", "matter__client", "created_by")
            .order_by("-created_at")
        )

        tasks = []
        for task in case_tasks:
            tasks.append(
                {
                    "kind": "case",
                    "task": task,
                    "subject": str(task.case),
                    "subject_meta": task.case.client.get_full_name(),
                    "accept_url": reverse(
                        "accounts:respond_case_task",
                        kwargs={
                            "role": user.role_slug,
                            "task_id": task.pk,
                        },
                    ),
                    "reject_url": reverse(
                        "accounts:respond_case_task",
                        kwargs={
                            "role": user.role_slug,
                            "task_id": task.pk,
                        },
                    ),
                    "view_url": reverse(
                        "accounts:view_case_task",
                        kwargs={
                            "role": user.role_slug,
                            "task_id": task.pk,
                        },
                    ),
                }
            )
        for task in matter_tasks:
            tasks.append(
                {
                    "kind": "matter",
                    "task": task,
                    "subject": str(task.matter),
                    "subject_meta": task.matter.client.get_full_name(),
                    "accept_url": reverse(
                        "accounts:respond_matter_task",
                        kwargs={
                            "role": user.role_slug,
                            "task_id": task.pk,
                        },
                    ),
                    "reject_url": reverse(
                        "accounts:respond_matter_task",
                        kwargs={
                            "role": user.role_slug,
                            "task_id": task.pk,
                        },
                    ),
                    "view_url": reverse(
                        "accounts:view_matter_task",
                        kwargs={
                            "role": user.role_slug,
                            "task_id": task.pk,
                        },
                    ),
                }
            )

        # Newest assignments first.
        tasks.sort(key=lambda item: item["task"].created_at, reverse=True)

        highlight_kind = (request.GET.get("kind") or "").strip().lower()
        highlight_id = request.GET.get("id")
        try:
            highlight_id = int(highlight_id) if highlight_id else None
        except (TypeError, ValueError):
            highlight_id = None

        pending_count = sum(
            1 for item in tasks if item["task"].status == CaseTask.Status.PENDING
        )

        return {
            "tasks": tasks,
            "task_count": len(tasks),
            "pending_count": pending_count,
            "accept_form": AcceptTaskForm(),
            "reject_form": RejectTaskForm(),
            "highlight_kind": highlight_kind,
            "highlight_id": highlight_id,
            "open_accept_modal": False,
            "open_reject_modal": False,
            "accept_target": None,
            "reject_target": None,
        }

    @staticmethod
    def _calendar_context(user, request):
        """Month calendar of this employee's task due dates only."""
        today = timezone.localdate()
        try:
            year = int(request.GET.get("year") or today.year)
            month = int(request.GET.get("month") or today.month)
        except (TypeError, ValueError):
            year, month = today.year, today.month

        if month < 1 or month > 12 or year < 2000 or year > 2100:
            year, month = today.year, today.month

        month_start = date(year, month, 1)
        _, last_day = calendar_mod.monthrange(year, month)
        month_end = date(year, month, last_day)

        visible_statuses = (
            CaseTask.Status.PENDING,
            CaseTask.Status.ACCEPTED,
            CaseTask.Status.DONE,
        )

        case_tasks = (
            CaseTask.objects.filter(
                assignee=user,
                status__in=visible_statuses,
                due_date__gte=month_start,
                due_date__lte=month_end,
            )
            .select_related("case", "case__client")
            .order_by("due_date", "status")
        )
        matter_tasks = (
            MatterTask.objects.filter(
                assignee=user,
                status__in=visible_statuses,
                due_date__gte=month_start,
                due_date__lte=month_end,
            )
            .select_related("matter", "matter__client")
            .order_by("due_date", "status")
        )

        tasks_url = user.workspace_url("dashboard", "tasks")
        by_day: dict[int, list] = {}

        for task in case_tasks:
            by_day.setdefault(task.due_date.day, []).append(
                {
                    "kind": "case",
                    "task": task,
                    "due_date": task.due_date,
                    "status": task.status,
                    "status_label": task.get_status_display(),
                    "subject": str(task.case),
                    "subject_meta": task.case.client.get_full_name(),
                    "url": reverse(
                        "accounts:view_case_task",
                        kwargs={"role": user.role_slug, "task_id": task.pk},
                    )
                    if task.status == CaseTask.Status.ACCEPTED
                    else f"{tasks_url}?kind=case&id={task.pk}",
                }
            )
        for task in matter_tasks:
            by_day.setdefault(task.due_date.day, []).append(
                {
                    "kind": "matter",
                    "task": task,
                    "due_date": task.due_date,
                    "status": task.status,
                    "status_label": task.get_status_display(),
                    "subject": str(task.matter),
                    "subject_meta": task.matter.client.get_full_name(),
                    "url": reverse(
                        "accounts:view_matter_task",
                        kwargs={"role": user.role_slug, "task_id": task.pk},
                    )
                    if task.status == MatterTask.Status.ACCEPTED
                    else f"{tasks_url}?kind=matter&id={task.pk}",
                }
            )

        court_appearances = (
            CourtAttendance.objects.filter(
                case__assigned_to=user,
                next_court_date__gte=month_start,
                next_court_date__lte=month_end,
            )
            .select_related("case", "case__client")
            .order_by("next_court_date", "pk")
        )
        for attendance in court_appearances:
            appearance_date = attendance.next_court_date
            if not appearance_date:
                continue
            activity = (
                attendance.next_activity_type
                or attendance.activity_type
                or "Court appearance"
            )
            by_day.setdefault(appearance_date.day, []).append(
                {
                    "kind": "court",
                    "task": None,
                    "due_date": appearance_date,
                    "status": "active",
                    "status_label": "Court date",
                    "subject": f"{activity} — {attendance.case}",
                    "subject_meta": attendance.case.client.get_full_name(),
                    "url": reverse(
                        "accounts:view_litigation_case",
                        kwargs={
                            "role": user.role_slug,
                            "case_id": attendance.case_id,
                        },
                    ),
                }
            )

        matter_appearances = (
            MatterAttendance.objects.filter(
                matter__assigned_to=user,
                next_attendance_date__gte=month_start,
                next_attendance_date__lte=month_end,
            )
            .select_related("matter", "matter__client")
            .order_by("next_attendance_date", "pk")
        )
        for attendance in matter_appearances:
            appearance_date = attendance.next_attendance_date
            if not appearance_date:
                continue
            activity = (
                attendance.next_activity_type
                or attendance.activity_type
                or "Matter attendance"
            )
            by_day.setdefault(appearance_date.day, []).append(
                {
                    "kind": "matter_attendance",
                    "task": None,
                    "due_date": appearance_date,
                    "status": "active",
                    "status_label": "Matter date",
                    "subject": f"{activity} — {attendance.matter.matter_title}",
                    "subject_meta": attendance.matter.client.get_full_name(),
                    "url": reverse(
                        "accounts:view_non_litigation_matter",
                        kwargs={
                            "role": user.role_slug,
                            "matter_id": attendance.matter_id,
                        },
                    ),
                }
            )

        weeks = calendar_mod.Calendar(firstweekday=0).monthdayscalendar(year, month)
        calendar_weeks = []
        for week in weeks:
            days = []
            for day_num in week:
                if day_num == 0:
                    days.append(
                        {
                            "day": None,
                            "is_today": False,
                            "events": [],
                            "event_count": 0,
                        }
                    )
                else:
                    events = by_day.get(day_num, [])
                    days.append(
                        {
                            "day": day_num,
                            "is_today": (
                                year == today.year
                                and month == today.month
                                and day_num == today.day
                            ),
                            "events": events,
                            "event_count": len(events),
                        }
                    )
            calendar_weeks.append(days)

        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1
        if month == 12:
            next_year, next_month = year + 1, 1
        else:
            next_year, next_month = year, month + 1

        base_url = user.workspace_url("dashboard", "calendar")
        month_label = month_start.strftime("%B %Y")
        due_count = sum(len(v) for v in by_day.values())

        upcoming = []
        for day_num in sorted(by_day):
            for item in by_day[day_num]:
                upcoming.append(item)

        return {
            "calendar_weeks": calendar_weeks,
            "calendar_year": year,
            "calendar_month": month,
            "calendar_month_label": month_label,
            "calendar_today": today,
            "calendar_due_count": due_count,
            "calendar_upcoming": upcoming,
            "calendar_prev_url": f"{base_url}?year={prev_year}&month={prev_month}",
            "calendar_next_url": f"{base_url}?year={next_year}&month={next_month}",
            "calendar_today_url": (
                f"{base_url}?year={today.year}&month={today.month}"
            ),
            "weekday_labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        }

    @staticmethod
    def _reminders_context(user, request):
        """List personal task reminders set by this employee."""
        now = timezone.now()
        visible_statuses = (
            CaseTask.Status.PENDING,
            CaseTask.Status.ACCEPTED,
            CaseTask.Status.DONE,
        )
        tasks_url = user.workspace_url("dashboard", "tasks")

        case_tasks = (
            CaseTask.objects.filter(
                assignee=user,
                reminder_at__isnull=False,
                status__in=visible_statuses,
            )
            .select_related("case", "case__client", "created_by")
            .order_by("-reminder_at")
        )
        matter_tasks = (
            MatterTask.objects.filter(
                assignee=user,
                reminder_at__isnull=False,
                status__in=visible_statuses,
            )
            .select_related("matter", "matter__client", "created_by")
            .order_by("-reminder_at")
        )

        reminders = []
        for task in case_tasks:
            reminders.append(
                {
                    "kind": "case",
                    "task": task,
                    "subject": str(task.case),
                    "subject_meta": task.case.client.get_full_name(),
                    "url": reverse(
                        "accounts:view_case_task",
                        kwargs={"role": user.role_slug, "task_id": task.pk},
                    )
                    if task.status == CaseTask.Status.ACCEPTED
                    else f"{tasks_url}?kind=case&id={task.pk}",
                    "is_due": task.reminder_at <= now,
                }
            )
        for task in matter_tasks:
            reminders.append(
                {
                    "kind": "matter",
                    "task": task,
                    "subject": str(task.matter),
                    "subject_meta": task.matter.client.get_full_name(),
                    "url": reverse(
                        "accounts:view_matter_task",
                        kwargs={"role": user.role_slug, "task_id": task.pk},
                    )
                    if task.status == MatterTask.Status.ACCEPTED
                    else f"{tasks_url}?kind=matter&id={task.pk}",
                    "is_due": task.reminder_at <= now,
                }
            )

        # Newest reminder times first within each section.
        reminders.sort(key=lambda item: item["task"].reminder_at, reverse=True)

        due_reminders = [item for item in reminders if item["is_due"]]
        upcoming_reminders = [item for item in reminders if not item["is_due"]]

        return {
            "reminders": reminders,
            "due_reminders": due_reminders,
            "upcoming_reminders": upcoming_reminders,
            "reminder_count": len(reminders),
            "due_reminder_count": len(due_reminders),
            "upcoming_reminder_count": len(upcoming_reminders),
            "reminders_now": now,
        }

    @staticmethod
    def _messages_context(user, request):
        """List message notifications for this employee, newest first."""
        message_list = list(
            Notification.objects.filter(
                recipient=user,
                category=Notification.Category.MESSAGE,
            ).order_by("-created_at")
        )
        unread_count = sum(1 for item in message_list if not item.is_read)
        return {
            "message_notifications": message_list,
            "message_count": len(message_list),
            "message_unread_count": unread_count,
        }


PENDING_CLIENTS_TRAIL = (
    "dashboard",
    "user-management",
    "client-management",
    "approve-pending-clients",
)

PENDING_EMPLOYEES_TRAIL = (
    "dashboard",
    "user-management",
    "employee-management",
    "onboarding-approvals",
)

PENDING_CASES_TRAIL = (
    "dashboard",
    "matter-management",
    "litigation-matters",
    "approve-registered-cases",
)

ACTIVE_CASES_TRAIL = (
    "dashboard",
    "matter-management",
    "litigation-matters",
)

PENDING_MATTERS_TRAIL = (
    "dashboard",
    "matter-management",
    "non-litigation-matters",
    "approve-registered-matters",
)

ACTIVE_MATTERS_TRAIL = (
    "dashboard",
    "matter-management",
    "non-litigation-matters",
)

INVOICING_TRAIL = (
    "dashboard",
    "finance-billing",
    "general-accounts",
    "invoicing",
)

PAYMENTS_TRAIL = (
    "dashboard",
    "finance-billing",
    "general-accounts",
    "payments",
)


def _employee_workspace_guard(request, role):
    user = request.user
    if user.status != Employee.Status.ACTIVE:
        return None, redirect_for_employee(request, user)
    if Employee.role_from_slug(role) is None or role != user.role_slug:
        return None, redirect(user.dashboard_url)
    return user, None


def _pending_clients_list_url(user):
    return user.workspace_url(*PENDING_CLIENTS_TRAIL)


def _pending_employees_list_url(user):
    return user.workspace_url(*PENDING_EMPLOYEES_TRAIL)


def _pending_cases_list_url(user):
    return user.workspace_url(*PENDING_CASES_TRAIL)


def _active_cases_list_url(user):
    return user.workspace_url(*ACTIVE_CASES_TRAIL)


def _invoicing_list_url(user):
    return user.workspace_url(*INVOICING_TRAIL)


def _payments_list_url(user):
    return user.workspace_url(*PAYMENTS_TRAIL)


def _invoice_pay_url(user, invoice_id: int) -> str:
    return reverse(
        "accounts:pay_invoice",
        kwargs={"role": user.role_slug, "invoice_id": invoice_id},
    )


def _pending_matters_list_url(user):
    return user.workspace_url(*PENDING_MATTERS_TRAIL)


def _active_matters_list_url(user):
    return user.workspace_url(*ACTIVE_MATTERS_TRAIL)


@method_decorator(login_required, name="dispatch")
class AssistClientOnboardingView(View):
    """Employee assists a pending-onboarding client to complete details."""

    template_name = "accounts/assist_client_onboarding.html"

    def get_client(self, client_id):
        return get_object_or_404(Client, pk=client_id)

    def get(self, request, role, client_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        client = self.get_client(client_id)
        if client.status != Client.Status.PENDING_ONBOARDING:
            messages.info(
                request,
                "This client is no longer pending onboarding.",
            )
            return redirect(_pending_clients_list_url(user))

        context = workspace_context(
            user,
            request=request,
            page_title="Assist onboarding",
            page_trail=list(PENDING_CLIENTS_TRAIL),
            active_page="approve-pending-clients",
        )
        context["client"] = client
        context["form"] = ClientOnboardingForm(client=client)
        context["list_url"] = _pending_clients_list_url(user)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, client_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        client = self.get_client(client_id)
        if client.status != Client.Status.PENDING_ONBOARDING:
            messages.info(
                request,
                "This client is no longer pending onboarding.",
            )
            return redirect(_pending_clients_list_url(user))

        form = ClientOnboardingForm(request.POST, request.FILES, client=client)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"Onboarding completed for {client.get_full_name()}. "
                "The client is now pending approval.",
            )
            return redirect(_pending_clients_list_url(user))

        context = workspace_context(
            user,
            request=request,
            page_title="Assist onboarding",
            page_trail=list(PENDING_CLIENTS_TRAIL),
            active_page="approve-pending-clients",
        )
        context["client"] = client
        context["form"] = form
        context["list_url"] = _pending_clients_list_url(user)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class ApproveClientView(View):
    """Employee reviews client details/uploads and approves the account."""

    template_name = "accounts/approve_client.html"

    def get_client(self, client_id):
        return get_object_or_404(Client, pk=client_id)

    def get(self, request, role, client_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        client = self.get_client(client_id)
        if client.status != Client.Status.PENDING_APPROVAL:
            messages.info(
                request,
                "This client is not awaiting approval.",
            )
            return redirect(_pending_clients_list_url(user))

        context = workspace_context(
            user,
            request=request,
            page_title="Approve client",
            page_trail=list(PENDING_CLIENTS_TRAIL),
            active_page="approve-pending-clients",
        )
        context["client"] = client
        context["list_url"] = _pending_clients_list_url(user)
        context["documents"] = self._document_rows(client)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, client_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        client = self.get_client(client_id)
        if client.status != Client.Status.PENDING_APPROVAL:
            messages.info(
                request,
                "This client is not awaiting approval.",
            )
            return redirect(_pending_clients_list_url(user))

        action = (request.POST.get("action") or "").strip()
        if action == "approve":
            client.status = Client.Status.ACTIVE
            client.save(update_fields=["status"])
            messages.success(
                request,
                f"{client.get_full_name()} has been approved and is now active.",
            )
            return redirect(_pending_clients_list_url(user))

        messages.error(request, "Unknown action.")
        return redirect(
            "accounts:approve_client",
            role=role,
            client_id=client.pk,
        )

    @staticmethod
    def _document_rows(client):
        rows = []
        if client.client_type == Client.ClientType.INDIVIDUAL:
            if client.id_type == Client.IdType.CITIZEN:
                rows.append(
                    (
                        "National ID",
                        client.identification_number,
                        client.identification_document,
                    )
                )
            else:
                rows.append(
                    (
                        "Alien document",
                        client.alien_number,
                        client.alien_document,
                    )
                )
        elif client.corporate_kind == Client.CorporateKind.BUSINESS:
            rows.append(
                (
                    "Business registration",
                    client.business_number,
                    client.business_document,
                )
            )
        else:
            rows.append(
                (
                    "Company registration",
                    client.company_registration_number,
                    client.company_registration_document,
                )
            )
        return rows


@method_decorator(login_required, name="dispatch")
class ApproveLitigationCaseView(View):
    """Review a pending case, allocate an employee, task them, and approve."""

    template_name = "accounts/approve_litigation_case.html"

    def get_case(self, case_id):
        return get_object_or_404(
            LitigationCase.objects.select_related(
                "client", "registered_by"
            ).prefetch_related("parties"),
            pk=case_id,
        )

    def get(self, request, role, case_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        case = self.get_case(case_id)
        if case.status != LitigationCase.Status.PENDING_APPROVAL:
            messages.info(request, "This case is not awaiting approval.")
            return redirect(_pending_cases_list_url(user))

        context = self._context(user, case, ApproveCaseForm())
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, case_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        case = self.get_case(case_id)
        if case.status != LitigationCase.Status.PENDING_APPROVAL:
            messages.info(request, "This case is not awaiting approval.")
            return redirect(_pending_cases_list_url(user))

        action = (request.POST.get("action") or "").strip()
        if action != "approve":
            messages.error(request, "Unknown action.")
            return redirect(
                "accounts:approve_litigation_case",
                role=role,
                case_id=case.pk,
            )

        form = ApproveCaseForm(request.POST)
        if not form.is_valid():
            context = self._context(user, case, form, open_modal=True)
            response = render(request, self.template_name, context)
            return attach_greeting_cookie(response, request)

        assignee = form.cleaned_data["assigned_to"]
        case.assigned_to = assignee
        case.approved_by = user
        case.approved_at = timezone.now()
        case.status = LitigationCase.Status.ACTIVE
        case.save(
            update_fields=[
                "assigned_to",
                "approved_by",
                "approved_at",
                "status",
                "updated_at",
            ]
        )

        task = CaseTask.objects.create(
            case=case,
            assignee=assignee,
            instructions=form.cleaned_data.get("instructions") or "",
            due_date=form.cleaned_data["due_date"],
            created_by=user,
        )
        notify_case_task(task)

        messages.success(
            request,
            f"Case approved and tasked to {assignee.get_full_name()}. "
            "Only they can view and accept or reject the task.",
        )
        return redirect(_pending_cases_list_url(user))

    def _context(self, user, case, form, open_modal=False):
        context = workspace_context(
            user,
            request=self.request,
            page_title="Approve case",
            page_trail=list(PENDING_CASES_TRAIL),
            active_page="approve-registered-cases",
        )
        context["case"] = case
        context["parties"] = case.parties.all()
        context["form"] = form
        context["list_url"] = _pending_cases_list_url(user)
        context["edit_url"] = reverse(
            "accounts:edit_litigation_case",
            kwargs={
                "role": user.role_slug,
                "case_id": case.pk,
            },
        )
        context["open_allocate_modal"] = open_modal
        return context


@method_decorator(login_required, name="dispatch")
class EditLitigationCaseView(View):
    """Edit a pending case before approval."""

    template_name = "accounts/register_case.html"

    def get_case(self, case_id):
        return get_object_or_404(
            LitigationCase.objects.select_related("client").prefetch_related(
                "parties"
            ),
            pk=case_id,
        )

    def get(self, request, role, case_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        case = self.get_case(case_id)
        if case.status != LitigationCase.Status.PENDING_APPROVAL:
            messages.info(request, "This case is not awaiting approval.")
            return redirect(_pending_cases_list_url(user))

        form = RegisterCaseForm(instance=case)
        party_formset = CasePartyEditFormSet(
            queryset=case.parties.order_by("sort_order", "pk"),
            prefix="parties",
        )
        context = self._context(user, case, form, party_formset)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, case_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        case = self.get_case(case_id)
        if case.status != LitigationCase.Status.PENDING_APPROVAL:
            messages.info(request, "This case is not awaiting approval.")
            return redirect(_pending_cases_list_url(user))

        form = RegisterCaseForm(request.POST, instance=case)
        party_formset = CasePartyEditFormSet(
            request.POST,
            queryset=case.parties.order_by("sort_order", "pk"),
            prefix="parties",
        )
        if form.is_valid() and party_formset.is_valid():
            parties = [
                f
                for f in party_formset
                if f.cleaned_data and not f.cleaned_data.get("DELETE")
            ]
            if not parties:
                messages.error(request, "Add at least one party.")
                context = self._context(user, case, form, party_formset)
                response = render(request, self.template_name, context)
                return attach_greeting_cookie(response, request)

            case = form.save(commit=False)
            case.status = LitigationCase.Status.PENDING_APPROVAL
            case.save()

            for obj in party_formset.deleted_objects:
                obj.delete()

            for index, party_form in enumerate(parties):
                party = party_form.save(commit=False)
                party.case = case
                party.sort_order = index
                party.is_client_party = index == 0
                party.save()

            messages.success(request, "Case details updated.")
            return redirect(
                "accounts:approve_litigation_case",
                role=role,
                case_id=case.pk,
            )

        context = self._context(user, case, form, party_formset)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def _context(self, user, case, form, party_formset):
        context = workspace_context(
            user,
            request=self.request,
            page_title="Edit case",
            page_trail=list(PENDING_CASES_TRAIL),
            active_page="approve-registered-cases",
        )
        selected_client = None
        client_id = form["client"].value()
        if client_id:
            selected_client = Client.objects.filter(
                pk=client_id, status=Client.Status.ACTIVE
            ).first()
        context.update(
            {
                "form": form,
                "party_formset": party_formset,
                "client_search_url": reverse("accounts:workspace_client_search"),
                "field_suggestions_url": reverse(
                    "accounts:workspace_case_field_suggestions"
                ),
                "selected_client": selected_client,
                "is_edit": True,
                "edit_mode": "pending",
                "cancel_url": reverse(
                    "accounts:approve_litigation_case",
                    kwargs={"role": user.role_slug, "case_id": case.pk},
                ),
            }
        )
        return context


@method_decorator(login_required, name="dispatch")
class EditActiveLitigationCaseView(View):
    """Edit an active litigation case from the case detail sidebar."""

    template_name = "accounts/register_case.html"
    action_slug = "edit-case-details"

    def get_case(self, case_id):
        return get_object_or_404(
            LitigationCase.objects.select_related(
                "client", "assigned_to"
            ).prefetch_related("parties"),
            pk=case_id,
        )

    def get(self, request, role, case_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        case = self.get_case(case_id)
        redirect_response = self._guard(request, role, case)
        if redirect_response:
            return redirect_response

        form = RegisterCaseForm(instance=case)
        party_formset = CasePartyEditFormSet(
            queryset=case.parties.order_by("sort_order", "pk"),
            prefix="parties",
        )
        context = self._context(user, case, form, party_formset)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, case_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        case = self.get_case(case_id)
        redirect_response = self._guard(request, role, case)
        if redirect_response:
            return redirect_response

        form = RegisterCaseForm(request.POST, instance=case)
        party_formset = CasePartyEditFormSet(
            request.POST,
            queryset=case.parties.order_by("sort_order", "pk"),
            prefix="parties",
        )
        if form.is_valid() and party_formset.is_valid():
            parties = [
                f
                for f in party_formset
                if f.cleaned_data and not f.cleaned_data.get("DELETE")
            ]
            if not parties:
                messages.error(request, "Add at least one party.")
                context = self._context(user, case, form, party_formset)
                response = render(request, self.template_name, context)
                return attach_greeting_cookie(response, request)

            previous_status = case.status
            case = form.save(commit=False)
            case.status = previous_status
            case.save()

            for obj in party_formset.deleted_objects:
                obj.delete()

            for index, party_form in enumerate(parties):
                party = party_form.save(commit=False)
                party.case = case
                party.sort_order = index
                party.is_client_party = index == 0
                party.save()

            messages.success(request, "Case details updated.")
            return redirect(
                "accounts:view_litigation_case",
                role=role,
                case_id=case.pk,
            )

        context = self._context(user, case, form, party_formset)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def _guard(self, request, role, case):
        if case.status == LitigationCase.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:edit_litigation_case",
                role=role,
                case_id=case.pk,
            )
        if case.status != LitigationCase.Status.ACTIVE:
            messages.info(request, "Only active cases can be edited here.")
            return redirect(
                "accounts:view_litigation_case",
                role=role,
                case_id=case.pk,
            )
        return None

    def _context(self, user, case, form, party_formset):
        detail_url = reverse(
            "accounts:view_litigation_case",
            kwargs={"role": user.role_slug, "case_id": case.pk},
        )
        context = workspace_context(
            user,
            request=self.request,
            page_title="Edit case details",
            page_trail=list(ACTIVE_CASES_TRAIL),
            active_page=self.action_slug,
            page_nav_items=litigation_case_nav_items(
                user.role_slug, case.pk, active_slug=self.action_slug
            ),
        )
        selected_client = None
        client_id = form["client"].value()
        if client_id:
            selected_client = Client.objects.filter(
                pk=client_id, status=Client.Status.ACTIVE
            ).first()
        context.update(
            {
                "form": form,
                "party_formset": party_formset,
                "client_search_url": reverse("accounts:workspace_client_search"),
                "field_suggestions_url": reverse(
                    "accounts:workspace_case_field_suggestions"
                ),
                "selected_client": selected_client,
                "is_edit": True,
                "edit_mode": "active",
                "cancel_url": detail_url,
            }
        )
        return context


@method_decorator(login_required, name="dispatch")
class ApproveNonLitigationMatterView(View):
    """Review a pending matter, allocate an employee, task them, and approve."""

    template_name = "accounts/approve_non_litigation_matter.html"

    def get_matter(self, matter_id):
        return get_object_or_404(
            NonLitigationMatter.objects.select_related(
                "client", "registered_by"
            ).prefetch_related("parties"),
            pk=matter_id,
        )

    def get(self, request, role, matter_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        matter = self.get_matter(matter_id)
        if matter.status != NonLitigationMatter.Status.PENDING_APPROVAL:
            messages.info(request, "This matter is not awaiting approval.")
            return redirect(_pending_matters_list_url(user))

        context = self._context(user, matter, ApproveMatterForm())
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, matter_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        matter = self.get_matter(matter_id)
        if matter.status != NonLitigationMatter.Status.PENDING_APPROVAL:
            messages.info(request, "This matter is not awaiting approval.")
            return redirect(_pending_matters_list_url(user))

        action = (request.POST.get("action") or "").strip()
        if action != "approve":
            messages.error(request, "Unknown action.")
            return redirect(
                "accounts:approve_non_litigation_matter",
                role=role,
                matter_id=matter.pk,
            )

        form = ApproveMatterForm(request.POST)
        if not form.is_valid():
            context = self._context(user, matter, form, open_modal=True)
            response = render(request, self.template_name, context)
            return attach_greeting_cookie(response, request)

        assignee = form.cleaned_data["assigned_to"]
        matter.assigned_to = assignee
        matter.approved_by = user
        matter.approved_at = timezone.now()
        matter.status = NonLitigationMatter.Status.ACTIVE
        matter.save(
            update_fields=[
                "assigned_to",
                "approved_by",
                "approved_at",
                "status",
                "updated_at",
            ]
        )

        task = MatterTask.objects.create(
            matter=matter,
            assignee=assignee,
            instructions=form.cleaned_data.get("instructions") or "",
            due_date=form.cleaned_data["due_date"],
            created_by=user,
        )
        notify_matter_task(task)

        messages.success(
            request,
            f"Matter approved and tasked to {assignee.get_full_name()}. "
            "Only they can view and accept or reject the task.",
        )
        return redirect(_pending_matters_list_url(user))

    def _context(self, user, matter, form, open_modal=False):
        context = workspace_context(
            user,
            request=self.request,
            page_title="Approve matter",
            page_trail=list(PENDING_MATTERS_TRAIL),
            active_page="approve-registered-matters",
        )
        context["matter"] = matter
        context["parties"] = matter.parties.all()
        context["form"] = form
        context["list_url"] = _pending_matters_list_url(user)
        context["edit_url"] = reverse(
            "accounts:edit_non_litigation_matter",
            kwargs={
                "role": user.role_slug,
                "matter_id": matter.pk,
            },
        )
        context["open_allocate_modal"] = open_modal
        return context


@method_decorator(login_required, name="dispatch")
class EditNonLitigationMatterView(View):
    """Edit a pending matter before approval."""

    template_name = "accounts/register_matter.html"

    def get_matter(self, matter_id):
        return get_object_or_404(
            NonLitigationMatter.objects.select_related("client").prefetch_related(
                "parties"
            ),
            pk=matter_id,
        )

    def get(self, request, role, matter_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        matter = self.get_matter(matter_id)
        if matter.status != NonLitigationMatter.Status.PENDING_APPROVAL:
            messages.info(request, "This matter is not awaiting approval.")
            return redirect(_pending_matters_list_url(user))

        form = RegisterMatterForm(instance=matter)
        party_formset = MatterPartyEditFormSet(
            queryset=matter.parties.order_by("sort_order", "pk"),
            prefix="parties",
        )
        context = self._context(user, matter, form, party_formset)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, matter_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        matter = self.get_matter(matter_id)
        if matter.status != NonLitigationMatter.Status.PENDING_APPROVAL:
            messages.info(request, "This matter is not awaiting approval.")
            return redirect(_pending_matters_list_url(user))

        form = RegisterMatterForm(request.POST, instance=matter)
        party_formset = MatterPartyEditFormSet(
            request.POST,
            queryset=matter.parties.order_by("sort_order", "pk"),
            prefix="parties",
        )
        if form.is_valid() and party_formset.is_valid():
            parties = [
                f
                for f in party_formset
                if f.cleaned_data and not f.cleaned_data.get("DELETE")
            ]
            if not parties:
                messages.error(request, "Add at least one party.")
                context = self._context(user, matter, form, party_formset)
                response = render(request, self.template_name, context)
                return attach_greeting_cookie(response, request)

            matter = form.save(commit=False)
            matter.status = NonLitigationMatter.Status.PENDING_APPROVAL
            matter.save()

            for obj in party_formset.deleted_objects:
                obj.delete()

            for index, party_form in enumerate(parties):
                party = party_form.save(commit=False)
                party.matter = matter
                party.sort_order = index
                party.is_client_party = index == 0
                party.save()

            messages.success(request, "Matter details updated.")
            return redirect(
                "accounts:approve_non_litigation_matter",
                role=role,
                matter_id=matter.pk,
            )

        context = self._context(user, matter, form, party_formset)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def _context(self, user, matter, form, party_formset):
        context = workspace_context(
            user,
            request=self.request,
            page_title="Edit matter",
            page_trail=list(PENDING_MATTERS_TRAIL),
            active_page="approve-registered-matters",
        )
        selected_client = None
        client_id = form["client"].value()
        if client_id:
            selected_client = Client.objects.filter(
                pk=client_id, status=Client.Status.ACTIVE
            ).first()
        context.update(
            {
                "form": form,
                "party_formset": party_formset,
                "client_search_url": reverse("accounts:workspace_client_search"),
                "field_suggestions_url": reverse(
                    "accounts:workspace_case_field_suggestions"
                ),
                "selected_client": selected_client,
                "is_edit": True,
                "edit_mode": "pending",
                "cancel_url": reverse(
                    "accounts:approve_non_litigation_matter",
                    kwargs={"role": user.role_slug, "matter_id": matter.pk},
                ),
            }
        )
        return context


@method_decorator(login_required, name="dispatch")
class EditActiveNonLitigationMatterView(View):
    """Edit an active non-litigation matter from the matter detail sidebar."""

    template_name = "accounts/register_matter.html"
    action_slug = "edit-matter-details"

    def get_matter(self, matter_id):
        return get_object_or_404(
            NonLitigationMatter.objects.select_related(
                "client", "assigned_to"
            ).prefetch_related("parties"),
            pk=matter_id,
        )

    def get(self, request, role, matter_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        matter = self.get_matter(matter_id)
        redirect_response = self._guard(request, role, matter)
        if redirect_response:
            return redirect_response

        form = RegisterMatterForm(instance=matter)
        party_formset = MatterPartyEditFormSet(
            queryset=matter.parties.order_by("sort_order", "pk"),
            prefix="parties",
        )
        context = self._context(user, matter, form, party_formset)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, matter_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        matter = self.get_matter(matter_id)
        redirect_response = self._guard(request, role, matter)
        if redirect_response:
            return redirect_response

        form = RegisterMatterForm(request.POST, instance=matter)
        party_formset = MatterPartyEditFormSet(
            request.POST,
            queryset=matter.parties.order_by("sort_order", "pk"),
            prefix="parties",
        )
        if form.is_valid() and party_formset.is_valid():
            parties = [
                f
                for f in party_formset
                if f.cleaned_data and not f.cleaned_data.get("DELETE")
            ]
            if not parties:
                messages.error(request, "Add at least one party.")
                context = self._context(user, matter, form, party_formset)
                response = render(request, self.template_name, context)
                return attach_greeting_cookie(response, request)

            previous_status = matter.status
            matter = form.save(commit=False)
            matter.status = previous_status
            matter.save()

            for obj in party_formset.deleted_objects:
                obj.delete()

            for index, party_form in enumerate(parties):
                party = party_form.save(commit=False)
                party.matter = matter
                party.sort_order = index
                party.is_client_party = index == 0
                party.save()

            messages.success(request, "Matter details updated.")
            return redirect(
                "accounts:view_non_litigation_matter",
                role=role,
                matter_id=matter.pk,
            )

        context = self._context(user, matter, form, party_formset)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def _guard(self, request, role, matter):
        if matter.status == NonLitigationMatter.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:edit_non_litigation_matter",
                role=role,
                matter_id=matter.pk,
            )
        if matter.status != NonLitigationMatter.Status.ACTIVE:
            messages.info(request, "Only active matters can be edited here.")
            return redirect(
                "accounts:view_non_litigation_matter",
                role=role,
                matter_id=matter.pk,
            )
        return None

    def _context(self, user, matter, form, party_formset):
        detail_url = reverse(
            "accounts:view_non_litigation_matter",
            kwargs={"role": user.role_slug, "matter_id": matter.pk},
        )
        context = workspace_context(
            user,
            request=self.request,
            page_title="Edit matter details",
            page_trail=list(ACTIVE_MATTERS_TRAIL),
            active_page=self.action_slug,
            page_nav_items=non_litigation_matter_nav_items(
                user.role_slug, matter.pk, active_slug=self.action_slug
            ),
        )
        selected_client = None
        client_id = form["client"].value()
        if client_id:
            selected_client = Client.objects.filter(
                pk=client_id, status=Client.Status.ACTIVE
            ).first()
        context.update(
            {
                "form": form,
                "party_formset": party_formset,
                "client_search_url": reverse("accounts:workspace_client_search"),
                "field_suggestions_url": reverse(
                    "accounts:workspace_case_field_suggestions"
                ),
                "selected_client": selected_client,
                "is_edit": True,
                "edit_mode": "active",
                "cancel_url": detail_url,
            }
        )
        return context


@method_decorator(login_required, name="dispatch")
class EditPracticeAreaView(View):
    """Edit, reorder images, or delete a firm practice area."""

    template_name = "accounts/practice_area_form.html"

    def _area_or_404(self, area_id):
        return get_object_or_404(
            FirmPracticeArea.objects.prefetch_related("images"),
            pk=area_id,
        )

    def get(self, request, role, area_id):
        user = request.user
        if user.status != Employee.Status.ACTIVE:
            return redirect_for_employee(request, user)
        if role != user.role_slug:
            return redirect(
                reverse(
                    "accounts:edit_practice_area",
                    kwargs={"role": user.role_slug, "area_id": area_id},
                )
            )
        area = self._area_or_404(area_id)
        trail = ["dashboard", "practice-areas"]
        context = workspace_context(
            user,
            request=request,
            page_title="Edit practice area",
            page_trail=trail,
            active_page="practice-areas",
        )
        context.update(
            RoleWorkspaceView._practice_area_form_context(
                user, practice_area=area
            )
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, area_id):
        user = request.user
        if user.status != Employee.Status.ACTIVE:
            return redirect_for_employee(request, user)
        if role != user.role_slug:
            return redirect(
                reverse(
                    "accounts:edit_practice_area",
                    kwargs={"role": user.role_slug, "area_id": area_id},
                )
            )
        area = self._area_or_404(area_id)
        list_url = RoleWorkspaceView._practice_areas_list_url(user)

        if request.POST.get("practice_area_delete"):
            name = area.name
            area.delete()
            messages.success(request, f"Practice area “{name}” deleted.")
            return redirect(list_url)

        form = PracticeAreaForm(request.POST, request.FILES, instance=area)
        trail = ["dashboard", "practice-areas"]
        context = workspace_context(
            user,
            request=request,
            page_title="Edit practice area",
            page_trail=trail,
            active_page="practice-areas",
        )
        if form.is_valid():
            area = form.save(commit=False)
            area.updated_by = user
            area.save()
            RoleWorkspaceView._sync_practice_area_images(
                request, area, append=True
            )
            messages.success(request, f"Practice area “{area.name}” saved.")
            return redirect(list_url)

        context.update(
            RoleWorkspaceView._practice_area_form_context(
                user, form=form, practice_area=area
            )
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class EditGalleryImageView(View):
    """Edit or delete a firm gallery image."""

    template_name = "accounts/company_gallery_form.html"

    def _item_or_404(self, item_id):
        return get_object_or_404(FirmGalleryImage, pk=item_id)

    def get(self, request, role, item_id):
        user = request.user
        if user.status != Employee.Status.ACTIVE:
            return redirect_for_employee(request, user)
        if role != user.role_slug:
            return redirect(
                reverse(
                    "accounts:edit_gallery_image",
                    kwargs={"role": user.role_slug, "item_id": item_id},
                )
            )
        item = self._item_or_404(item_id)
        trail = ["dashboard", "company-gallery"]
        context = workspace_context(
            user,
            request=request,
            page_title="Edit gallery image",
            page_trail=trail,
            active_page="company-gallery",
        )
        context.update(
            RoleWorkspaceView._company_gallery_form_context(user, item=item)
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, item_id):
        user = request.user
        if user.status != Employee.Status.ACTIVE:
            return redirect_for_employee(request, user)
        if role != user.role_slug:
            return redirect(
                reverse(
                    "accounts:edit_gallery_image",
                    kwargs={"role": user.role_slug, "item_id": item_id},
                )
            )
        item = self._item_or_404(item_id)
        list_url = RoleWorkspaceView._company_gallery_list_url(user)

        if request.POST.get("gallery_delete"):
            title = item.title
            item.delete()
            messages.success(request, f"Gallery item “{title}” deleted.")
            return redirect(list_url)

        form = GalleryImageForm(request.POST, request.FILES, instance=item)
        trail = ["dashboard", "company-gallery"]
        context = workspace_context(
            user,
            request=request,
            page_title="Edit gallery image",
            page_trail=trail,
            active_page="company-gallery",
        )
        if form.is_valid():
            item = form.save(commit=False)
            item.updated_by = user
            item.save()
            messages.success(request, f"Gallery item “{item.title}” saved.")
            return redirect(list_url)

        context.update(
            RoleWorkspaceView._company_gallery_form_context(
                user, form=form, item=item
            )
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class EditFAQView(View):
    """Edit or delete a firm FAQ entry."""

    template_name = "accounts/company_faq_form.html"

    def _faq_or_404(self, faq_id):
        return get_object_or_404(FirmFAQ, pk=faq_id)

    def get(self, request, role, faq_id):
        user = request.user
        if user.status != Employee.Status.ACTIVE:
            return redirect_for_employee(request, user)
        if role != user.role_slug:
            return redirect(
                reverse(
                    "accounts:edit_faq",
                    kwargs={"role": user.role_slug, "faq_id": faq_id},
                )
            )
        faq = self._faq_or_404(faq_id)
        trail = ["dashboard", "company-faqs"]
        context = workspace_context(
            user,
            request=request,
            page_title="Edit FAQ",
            page_trail=trail,
            active_page="company-faqs",
        )
        context.update(
            RoleWorkspaceView._company_faq_form_context(user, faq=faq)
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, faq_id):
        user = request.user
        if user.status != Employee.Status.ACTIVE:
            return redirect_for_employee(request, user)
        if role != user.role_slug:
            return redirect(
                reverse(
                    "accounts:edit_faq",
                    kwargs={"role": user.role_slug, "faq_id": faq_id},
                )
            )
        faq = self._faq_or_404(faq_id)
        list_url = RoleWorkspaceView._company_faqs_list_url(user)

        if request.POST.get("faq_delete"):
            question = faq.question
            faq.delete()
            messages.success(request, f"FAQ “{question}” deleted.")
            return redirect(list_url)

        form = FAQForm(request.POST, instance=faq)
        trail = ["dashboard", "company-faqs"]
        context = workspace_context(
            user,
            request=request,
            page_title="Edit FAQ",
            page_trail=trail,
            active_page="company-faqs",
        )
        if form.is_valid():
            faq = form.save(commit=False)
            faq.updated_by = user
            faq.save()
            messages.success(request, f"FAQ “{faq.question}” saved.")
            return redirect(list_url)

        context.update(
            RoleWorkspaceView._company_faq_form_context(
                user, form=form, faq=faq
            )
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class EditMyBlogView(View):
    """Edit or delete a personal blog post owned by the signed-in employee."""

    template_name = "accounts/my_blog_form.html"

    def _post_or_404(self, user, post_id):
        return get_object_or_404(EmployeeBlogPost, pk=post_id, author=user)

    def get(self, request, role, post_id):
        user = request.user
        if user.status != Employee.Status.ACTIVE:
            return redirect_for_employee(request, user)
        if role != user.role_slug:
            return redirect(
                reverse(
                    "accounts:edit_my_blog",
                    kwargs={"role": user.role_slug, "post_id": post_id},
                )
            )
        post = self._post_or_404(user, post_id)
        trail = ["dashboard", "my-blogs"]
        context = workspace_context(
            user,
            request=request,
            page_title="Edit blog post",
            page_trail=trail,
            active_page="my-blogs",
        )
        context.update(
            RoleWorkspaceView._my_blog_form_context(user, post=post)
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, post_id):
        user = request.user
        if user.status != Employee.Status.ACTIVE:
            return redirect_for_employee(request, user)
        if role != user.role_slug:
            return redirect(
                reverse(
                    "accounts:edit_my_blog",
                    kwargs={"role": user.role_slug, "post_id": post_id},
                )
            )
        post = self._post_or_404(user, post_id)
        blogs_url = user.workspace_url("dashboard", "my-blogs")

        if request.POST.get("blog_delete") == "1":
            post.delete()
            messages.success(request, "Blog post deleted.")
            return redirect(blogs_url)

        form = EmployeeBlogForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            updated = form.save(author=user)
            if updated.status == EmployeeBlogPost.Status.SUBMITTED:
                messages.success(
                    request,
                    "Blog post submitted for approval. It will appear on the website once approved.",
                )
            elif updated.status == EmployeeBlogPost.Status.PUBLISHED:
                messages.success(request, "Live blog post updated.")
            else:
                messages.success(
                    request,
                    "Blog post saved as a draft. Submit it for approval when it is ready.",
                )
            return redirect(blogs_url)

        trail = ["dashboard", "my-blogs"]
        context = workspace_context(
            user,
            request=request,
            page_title="Edit blog post",
            page_trail=trail,
            active_page="my-blogs",
        )
        context.update(
            RoleWorkspaceView._my_blog_form_context(user, form=form, post=post)
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class ReviewCompanyBlogView(View):
    """Review a submitted blog post and approve it for the public website."""

    template_name = "accounts/review_company_blog.html"

    def _post_or_404(self, post_id):
        return get_object_or_404(
            EmployeeBlogPost.objects.select_related("author", "approved_by"),
            pk=post_id,
        )

    def get(self, request, role, post_id):
        user = request.user
        if user.status != Employee.Status.ACTIVE:
            return redirect_for_employee(request, user)
        if role != user.role_slug:
            return redirect(
                reverse(
                    "accounts:review_company_blog",
                    kwargs={"role": user.role_slug, "post_id": post_id},
                )
            )
        post = self._post_or_404(post_id)
        trail = ["dashboard", "company-blogs"]
        context = workspace_context(
            user,
            request=request,
            page_title="Review blog post",
            page_trail=trail,
            active_page="company-blogs",
        )
        context.update(
            {
                "blog_post": post,
                "company_blogs_url": RoleWorkspaceView._company_blogs_list_url(
                    user
                ),
                "seo_checklist": post.seo_checklist(),
                "public_post_url": (
                    post.get_absolute_url() if post.is_public else ""
                ),
            }
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, post_id):
        user = request.user
        if user.status != Employee.Status.ACTIVE:
            return redirect_for_employee(request, user)
        if role != user.role_slug:
            return redirect(
                reverse(
                    "accounts:review_company_blog",
                    kwargs={"role": user.role_slug, "post_id": post_id},
                )
            )
        post = self._post_or_404(post_id)
        list_url = RoleWorkspaceView._company_blogs_list_url(user)
        action = request.POST.get("blog_review_action", "").strip()

        if action == "approve":
            if post.status not in {
                EmployeeBlogPost.Status.SUBMITTED,
                EmployeeBlogPost.Status.PUBLISHED,
            }:
                messages.error(
                    request,
                    "Only submitted posts can be approved for the website.",
                )
                return redirect(list_url)
            post.status = EmployeeBlogPost.Status.PUBLISHED
            if not post.published_at:
                post.published_at = timezone.now()
            post.approved_by = user
            post.approved_at = timezone.now()
            post.save(
                update_fields=[
                    "status",
                    "published_at",
                    "approved_by",
                    "approved_at",
                    "updated_at",
                ]
            )
            messages.success(
                request,
                f"“{post.title}” is now published on the website.",
            )
            return redirect(list_url)

        if action == "return_draft":
            post.status = EmployeeBlogPost.Status.DRAFT
            post.submitted_at = None
            post.published_at = None
            post.approved_by = None
            post.approved_at = None
            post.save(
                update_fields=[
                    "status",
                    "submitted_at",
                    "published_at",
                    "approved_by",
                    "approved_at",
                    "updated_at",
                ]
            )
            messages.success(
                request,
                f"“{post.title}” was returned to the author as a draft.",
            )
            return redirect(list_url)

        if action == "unpublish":
            if post.status != EmployeeBlogPost.Status.PUBLISHED:
                messages.error(request, "Only live posts can be unpublished.")
                return redirect(list_url)
            post.status = EmployeeBlogPost.Status.DRAFT
            post.submitted_at = None
            post.published_at = None
            post.approved_by = None
            post.approved_at = None
            post.save(
                update_fields=[
                    "status",
                    "submitted_at",
                    "published_at",
                    "approved_by",
                    "approved_at",
                    "updated_at",
                ]
            )
            messages.success(
                request,
                f"“{post.title}” was unpublished and returned to draft.",
            )
            return redirect(list_url)

        messages.error(request, "Choose a valid review action.")
        return redirect(
            reverse(
                "accounts:review_company_blog",
                kwargs={"role": user.role_slug, "post_id": post.pk},
            )
        )


@method_decorator(login_required, name="dispatch")
class AssistEmployeeOnboardingView(View):
    """Firm staff assists a pending-onboarding employee to complete details."""

    template_name = "accounts/assist_employee_onboarding.html"

    def get_employee(self, employee_id):
        return get_object_or_404(Employee, pk=employee_id)

    def get(self, request, role, employee_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        employee = self.get_employee(employee_id)
        if employee.status != Employee.Status.PENDING_ONBOARDING:
            messages.info(
                request,
                "This employee is no longer pending onboarding.",
            )
            return redirect(_pending_employees_list_url(user))

        context = workspace_context(
            user,
            request=request,
            page_title="Assist onboarding",
            page_trail=list(PENDING_EMPLOYEES_TRAIL),
            active_page="onboarding-approvals",
        )
        context["employee"] = employee
        context["form"] = EmployeeOnboardingForm(employee=employee)
        context["list_url"] = _pending_employees_list_url(user)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, employee_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        employee = self.get_employee(employee_id)
        if employee.status != Employee.Status.PENDING_ONBOARDING:
            messages.info(
                request,
                "This employee is no longer pending onboarding.",
            )
            return redirect(_pending_employees_list_url(user))

        form = EmployeeOnboardingForm(
            request.POST, request.FILES, employee=employee
        )
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"Onboarding completed for {employee.get_full_name()}. "
                "The employee is now pending approval.",
            )
            return redirect(_pending_employees_list_url(user))

        context = workspace_context(
            user,
            request=request,
            page_title="Assist onboarding",
            page_trail=list(PENDING_EMPLOYEES_TRAIL),
            active_page="onboarding-approvals",
        )
        context["employee"] = employee
        context["form"] = form
        context["list_url"] = _pending_employees_list_url(user)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class ApproveEmployeeView(View):
    """Firm staff reviews employee details/uploads and approves the account."""

    template_name = "accounts/approve_employee.html"

    def get_employee(self, employee_id):
        return get_object_or_404(Employee, pk=employee_id)

    def get(self, request, role, employee_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        employee = self.get_employee(employee_id)
        if employee.status != Employee.Status.PENDING_APPROVAL:
            messages.info(
                request,
                "This employee is not awaiting approval.",
            )
            return redirect(_pending_employees_list_url(user))

        context = workspace_context(
            user,
            request=request,
            page_title="Approve employee",
            page_trail=list(PENDING_EMPLOYEES_TRAIL),
            active_page="onboarding-approvals",
        )
        context["employee"] = employee
        context["list_url"] = _pending_employees_list_url(user)
        context["documents"] = self._document_rows(employee)
        context["role_choices"] = Employee.Role.choices
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, employee_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        employee = self.get_employee(employee_id)
        if employee.status != Employee.Status.PENDING_APPROVAL:
            messages.info(
                request,
                "This employee is not awaiting approval.",
            )
            return redirect(_pending_employees_list_url(user))

        action = (request.POST.get("action") or "").strip()
        if action == "approve":
            allocated_role = (request.POST.get("role") or "").strip()
            valid_roles = {value for value, _label in Employee.Role.choices}
            if allocated_role not in valid_roles:
                messages.error(request, "Select a role before approving.")
                return redirect(
                    "accounts:approve_employee",
                    role=role,
                    employee_id=employee.pk,
                )

            employee.role = allocated_role
            employee.status = Employee.Status.ACTIVE
            employee.save(update_fields=["role", "status"])
            messages.success(
                request,
                f"{employee.get_full_name()} has been approved as "
                f"{employee.get_role_display()} and is now active.",
            )
            return redirect(_pending_employees_list_url(user))

        messages.error(request, "Unknown action.")
        return redirect(
            "accounts:approve_employee",
            role=role,
            employee_id=employee.pk,
        )

    @staticmethod
    def _document_rows(employee):
        return [
            ("Employment contract", "", employee.employment_contract),
            ("National ID or passport", "", employee.national_id_or_passport),
            ("KRA PIN certificate", "", employee.kra_pin_certificate),
        ]


@method_decorator(login_required, name="dispatch")
class ViewLitigationCaseView(View):
    """Read-only detail page for a litigation case from the matters list."""

    template_name = "accounts/view_litigation_case.html"

    def get(self, request, role, case_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        case = get_object_or_404(
            LitigationCase.objects.select_related(
                "client",
                "registered_by",
                "assigned_to",
                "approved_by",
            ).prefetch_related("parties"),
            pk=case_id,
        )
        if case.status == LitigationCase.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_litigation_case",
                role=role,
                case_id=case.pk,
            )

        context = workspace_context(
            user,
            request=request,
            page_title="View case",
            page_trail=list(ACTIVE_CASES_TRAIL),
            active_page="litigation-matters",
            page_nav_items=litigation_case_nav_items(user.role_slug, case.pk),
        )
        context.update(
            {
                "case": case,
                "parties": case.parties.all(),
                "list_url": _active_cases_list_url(user),
            }
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class ViewInvoiceView(View):
    """Invoice document view — issue, share, and pay entry points."""

    template_name = "accounts/view_invoice.html"

    def get_invoice(self, invoice_id):
        return get_object_or_404(
            Invoice.objects.select_related("client", "created_by", "approved_by"),
            pk=invoice_id,
        )

    def get(self, request, role, invoice_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        invoice = self.get_invoice(invoice_id)
        context = self._context(user, invoice, request=request)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, invoice_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        invoice = self.get_invoice(invoice_id)
        action = (request.POST.get("action") or "").strip()

        if action == "issue":
            if invoice.status in {
                Invoice.Status.PAID,
                Invoice.Status.CANCELLED,
            }:
                messages.error(
                    request,
                    "This invoice cannot be issued in its current status.",
                )
                return redirect(
                    "accounts:view_invoice",
                    role=role,
                    invoice_id=invoice.pk,
                )
            if invoice.status != Invoice.Status.ISSUED:
                invoice.status = Invoice.Status.ISSUED
                invoice.approved_by = user
                invoice.approved_at = timezone.now()
                invoice.save(
                    update_fields=[
                        "status",
                        "approved_by",
                        "approved_at",
                        "updated_at",
                    ]
                )
                notify_invoice_issued(invoice)
                messages.success(
                    request,
                    f"{invoice.invoice_number} marked as Issued. "
                    f"{invoice.client.get_full_name()} has been notified in their portal.",
                )
            return redirect(
                f"{reverse('accounts:view_invoice', kwargs={'role': role, 'invoice_id': invoice.pk})}"
                f"?share=1"
            )

        return redirect(
            "accounts:view_invoice",
            role=role,
            invoice_id=invoice.pk,
        )

    def _context(self, user, invoice, *, request=None):
        from .mpesa import MpesaError, normalize_msisdn
        from urllib.parse import quote

        from django.core import signing

        page_nav_items = [
            {
                "label": label,
                "slug": slug,
                "url": user.workspace_url(
                    *extend_page_trail(list(INVOICING_TRAIL), slug)
                ),
                "icon": icon,
                "active": False,
            }
            for label, slug, icon in PAGE_LOCAL_LINKS.get("invoicing", [])
        ]

        firm = FirmCompanyInformation.get_solo()
        pay_url = _invoice_pay_url(user, invoice.pk)
        pdf_download_url = reverse(
            "accounts:invoice_pdf",
            kwargs={"role": user.role_slug, "invoice_id": invoice.pk},
        )
        share_token = signing.dumps(
            {"invoice_id": invoice.pk},
            salt="invoice-pdf-share",
        )
        pdf_share_path = reverse(
            "accounts:invoice_pdf_shared",
            kwargs={"token": share_token},
        )
        pay_share_path = reverse(
            "accounts:invoice_pay_shared",
            kwargs={"token": share_token},
        )
        absolute_pdf_url = ""
        absolute_pay_url = ""
        if request is not None:
            absolute_pdf_url = request.build_absolute_uri(pdf_share_path)
            absolute_pay_url = request.build_absolute_uri(pay_share_path)

        share_message = (
            f"Invoice {invoice.invoice_number} from {firm.display_name}\n"
            f"Amount due: KES {invoice.total_amount}\n"
            f"Due date: {invoice.due_date.strftime('%d %b %Y')}"
        )
        if absolute_pdf_url:
            share_message += f"\n\nPDF invoice:\n{absolute_pdf_url}"
        if absolute_pay_url and invoice.status != Invoice.Status.PAID:
            share_message += f"\n\nPay online (M-Pesa):\n{absolute_pay_url}"
        elif absolute_pay_url:
            share_message += f"\n\nPayment page:\n{absolute_pay_url}"

        whatsapp_url = ""
        client_phone = (invoice.client.phone or "").strip()
        if client_phone:
            try:
                msisdn = normalize_msisdn(client_phone)
                whatsapp_url = (
                    f"https://wa.me/{msisdn}?text={quote(share_message)}"
                )
            except MpesaError:
                whatsapp_url = ""

        email_url = ""
        client_email = (invoice.client.email or "").strip()
        if client_email:
            subject = quote(
                f"Invoice {invoice.invoice_number} — {firm.display_name}"
            )
            body = quote(share_message)
            email_url = f"mailto:{client_email}?subject={subject}&body={body}"

        open_share = bool(
            request is not None and request.GET.get("share") == "1"
        )

        context = workspace_context(
            user,
            request=request,
            page_title=invoice.invoice_number,
            page_trail=list(INVOICING_TRAIL),
            active_page="invoicing",
            page_nav_items=page_nav_items,
        )
        context.update(
            {
                "invoice": invoice,
                "list_url": _invoicing_list_url(user),
                "firm": firm,
                "pay_url": pay_url,
                "pdf_url": pdf_download_url,
                "pdf_share_url": absolute_pdf_url or pdf_share_path,
                "pay_share_url": absolute_pay_url or pay_share_path,
                "can_pay": invoice.status
                not in {Invoice.Status.PAID, Invoice.Status.CANCELLED},
                "can_issue": invoice.status
                in {Invoice.Status.DRAFT, Invoice.Status.GENERATED},
                "can_share": invoice.status
                in {
                    Invoice.Status.ISSUED,
                    Invoice.Status.GENERATED,
                    Invoice.Status.PAID,
                },
                "whatsapp_url": whatsapp_url,
                "email_url": email_url,
                "open_share_modal": open_share
                and invoice.status == Invoice.Status.ISSUED,
            }
        )
        return context


def _invoice_pdf_response(invoice):
    from .invoice_pdf import build_invoice_pdf

    firm = FirmCompanyInformation.get_solo()
    pdf_bytes = build_invoice_pdf(invoice, firm)
    filename = f"{invoice.invoice_number}.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@method_decorator(login_required, name="dispatch")
class InvoicePdfView(View):
    """Authenticated PDF download for an invoice."""

    def get(self, request, role, invoice_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied
        invoice = get_object_or_404(
            Invoice.objects.select_related("client", "approved_by"),
            pk=invoice_id,
        )
        return _invoice_pdf_response(invoice)


class SharedInvoicePdfView(View):
    """Public signed PDF link used when sharing via WhatsApp or email."""

    def get(self, request, token):
        invoice, error = _shared_invoice_from_token(token)
        if error:
            return error
        return _invoice_pdf_response(invoice)


def _shared_invoice_from_token(token):
    """Return (invoice, None) or (None, HttpResponse error)."""
    from django.core import signing

    try:
        payload = signing.loads(
            token,
            salt="invoice-pdf-share",
            max_age=60 * 60 * 24 * 30,
        )
        invoice_id = int(payload["invoice_id"])
    except (
        signing.BadSignature,
        signing.SignatureExpired,
        KeyError,
        TypeError,
        ValueError,
    ):
        return None, HttpResponse(
            "This invoice link is invalid or has expired.",
            status=404,
        )

    invoice = get_object_or_404(
        Invoice.objects.select_related("client", "approved_by", "created_by"),
        pk=invoice_id,
    )
    return invoice, None


class SharedInvoicePayView(View):
    """Public signed payment page linked from WhatsApp / email shares."""

    template_name = "accounts/shared_invoice_pay.html"
    session_key = "shared_invoice_stk_push"

    def get(self, request, token):
        invoice, error = _shared_invoice_from_token(token)
        if error:
            return error
        context = self._context(request, invoice, token)
        return render(request, self.template_name, context)

    def post(self, request, token):
        invoice, error = _shared_invoice_from_token(token)
        if error:
            return error

        action = (request.POST.get("action") or "stk").strip()
        pay_redirect = redirect(
            "accounts:invoice_pay_shared",
            token=token,
        )

        if invoice.status == Invoice.Status.PAID:
            messages.info(request, "This invoice is already paid.")
            return pay_redirect

        if invoice.status == Invoice.Status.CANCELLED:
            messages.error(request, "Cancelled invoices cannot be paid.")
            return pay_redirect

        if invoice.status not in _invoice_payable_statuses():
            messages.error(request, "This invoice cannot be paid yet.")
            return pay_redirect

        if action in {"confirm", "check_status"}:
            return self._check_payment_status(request, invoice, token)

        form = _stk_form_for_invoice(invoice, request.POST)
        if not form.is_valid():
            context = self._context(request, invoice, token, form=form)
            return render(request, self.template_name, context)

        from .mpesa import MpesaError

        try:
            result, stk, live = _start_invoice_stk(
                invoice,
                phone=form.cleaned_data["phone"],
                amount=form.cleaned_data["amount"],
            )
            push = _session_stk_payload(stk)
            push["started_at"] = result.get("started_at") or ""
            request.session[self.session_key] = push
            request.session.modified = True
        except MpesaError as exc:
            messages.error(request, str(exc))
            context = self._context(request, invoice, token, form=form)
            return render(request, self.template_name, context)

        messages.success(
            request,
            result.get("customer_message")
            or "STK push sent. We are checking payment status live.",
        )
        if not live:
            messages.info(
                request,
                "Payment is running in simulation mode — status will update automatically.",
            )
        return pay_redirect

    def _check_payment_status(self, request, invoice, token):
        from .mpesa import MpesaError

        push = dict(request.session.get(self.session_key) or {})
        try:
            outcome = _check_invoice_stk(push, invoice)
            request.session[self.session_key] = push
            request.session.modified = True
        except MpesaError as exc:
            messages.error(request, str(exc))
            return redirect("accounts:invoice_pay_shared", token=token)

        status = outcome.get("status")
        if status == "success":
            receipt = outcome.get("mpesa_receipt") or "—"
            messages.success(
                request,
                f"Payment successful. M-Pesa receipt {receipt}. "
                f"Invoice is now {outcome.get('invoice_status_label')} "
                f"(paid KES {outcome.get('amount_paid')}, "
                f"balance KES {outcome.get('balance_due')}).",
            )
        elif status == "failed":
            messages.error(
                request,
                outcome.get("result_desc") or "M-Pesa payment failed.",
            )
        else:
            messages.info(
                request,
                outcome.get("result_desc")
                or "Payment is still pending. Complete the prompt, then check again.",
            )
        return redirect("accounts:invoice_pay_shared", token=token)

    def _context(self, request, invoice, token, *, form=None):
        from .mpesa import mpesa_configured

        firm = FirmCompanyInformation.get_solo()
        initial_phone = (invoice.client.phone or "").strip()
        form = form or _stk_form_for_invoice(invoice, phone=initial_phone)
        push = request.session.get(self.session_key)
        if push and push.get("invoice_id") != invoice.pk:
            push = None

        return {
            "invoice": invoice,
            "firm": firm,
            "form": form,
            "stk_push": push,
            "stk_poll_url": reverse(
                "accounts:shared_invoice_stk_status",
                kwargs={"token": token},
            ),
            "mpesa_live": mpesa_configured(),
            "can_pay": invoice.is_payable,
            "pdf_url": reverse(
                "accounts:invoice_pdf_shared",
                kwargs={"token": token},
            ),
            "firm_name": firm.display_name,
        }


@method_decorator(login_required, name="dispatch")
class PayInvoiceView(View):
    """Payments page for an invoice — send M-Pesa STK push."""

    template_name = "accounts/pay_invoice.html"
    session_key = "invoice_stk_push"

    def get_invoice(self, invoice_id):
        return get_object_or_404(
            Invoice.objects.select_related(
                "client", "created_by", "approved_by"
            ).prefetch_related("stk_requests"),
            pk=invoice_id,
        )

    def get(self, request, role, invoice_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        invoice = self.get_invoice(invoice_id)
        context = self._context(user, invoice, request=request)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, invoice_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        invoice = self.get_invoice(invoice_id)
        action = (request.POST.get("action") or "stk").strip()

        if invoice.status == Invoice.Status.PAID:
            messages.info(request, "This invoice is already paid.")
            return redirect("accounts:view_invoice", role=role, invoice_id=invoice.pk)

        if invoice.status == Invoice.Status.CANCELLED:
            messages.error(request, "Cancelled invoices cannot be paid.")
            return redirect("accounts:view_invoice", role=role, invoice_id=invoice.pk)

        if action in {"confirm", "check_status"}:
            return self._check_payment_status(request, user, invoice)

        form = _stk_form_for_invoice(invoice, request.POST)
        if not form.is_valid():
            context = self._context(user, invoice, form=form, request=request)
            response = render(request, self.template_name, context)
            return attach_greeting_cookie(response, request)

        from .mpesa import MpesaError

        try:
            result, stk, live = _start_invoice_stk(
                invoice,
                phone=form.cleaned_data["phone"],
                amount=form.cleaned_data["amount"],
            )
            push = _session_stk_payload(stk)
            push["started_at"] = result.get("started_at") or ""
            request.session[self.session_key] = push
            request.session.modified = True
        except MpesaError as exc:
            messages.error(request, str(exc))
            context = self._context(user, invoice, form=form, request=request)
            response = render(request, self.template_name, context)
            return attach_greeting_cookie(response, request)

        messages.success(
            request,
            result.get("customer_message")
            or "STK push sent. We are checking payment status live.",
        )
        if not live:
            messages.info(
                request,
                "M-Pesa API credentials are not configured, so this STK was simulated — "
                "status will update automatically.",
            )
        return redirect("accounts:pay_invoice", role=role, invoice_id=invoice.pk)

    def _check_payment_status(self, request, user, invoice):
        from .mpesa import MpesaError

        push = dict(request.session.get(self.session_key) or {})
        try:
            outcome = _check_invoice_stk(push, invoice)
            request.session[self.session_key] = push
            request.session.modified = True
        except MpesaError as exc:
            messages.error(request, str(exc))
            return redirect(
                "accounts:pay_invoice",
                role=user.role_slug,
                invoice_id=invoice.pk,
            )

        status = outcome.get("status")
        if status == "success":
            receipt = outcome.get("mpesa_receipt") or "—"
            messages.success(
                request,
                f"Payment successful. M-Pesa receipt {receipt}. "
                f"Invoice is now {outcome.get('invoice_status_label')} "
                f"(paid KES {outcome.get('amount_paid')}, "
                f"balance KES {outcome.get('balance_due')}).",
            )
            invoice.refresh_from_db()
            if invoice.status == Invoice.Status.PAID:
                request.session.pop(self.session_key, None)
                return redirect(
                    "accounts:view_invoice",
                    role=user.role_slug,
                    invoice_id=invoice.pk,
                )
        elif status == "failed":
            messages.error(
                request,
                outcome.get("result_desc") or "M-Pesa payment failed.",
            )
        else:
            messages.info(
                request,
                outcome.get("result_desc")
                or "Payment is still pending. Ask the payer to complete the prompt, then check again.",
            )
        return redirect(
            "accounts:pay_invoice",
            role=user.role_slug,
            invoice_id=invoice.pk,
        )

    def _context(self, user, invoice, *, form=None, request=None):
        from .mpesa import mpesa_configured

        initial_phone = ""
        if invoice.client.phone:
            initial_phone = invoice.client.phone
        form = form or _stk_form_for_invoice(invoice, phone=initial_phone)
        push = None
        if request is not None:
            push = request.session.get(self.session_key)
            if push and push.get("invoice_id") != invoice.pk:
                push = None

        from .models import MpesaStkRequest

        payment_records = list(
            invoice.stk_requests.filter(status=MpesaStkRequest.Status.SUCCESS)[:50]
        )

        page_nav_items = []

        context = workspace_context(
            user,
            request=request,
            page_title=f"Pay {invoice.invoice_number}",
            page_trail=list(PAYMENTS_TRAIL),
            active_page="payments",
            page_nav_items=page_nav_items,
        )
        context.update(
            {
                "invoice": invoice,
                "form": form,
                "list_url": _payments_list_url(user),
                "invoice_url": reverse(
                    "accounts:view_invoice",
                    kwargs={"role": user.role_slug, "invoice_id": invoice.pk},
                ),
                "stk_push": push,
                "stk_poll_url": reverse(
                    "accounts:invoice_stk_status",
                    kwargs={
                        "role": user.role_slug,
                        "invoice_id": invoice.pk,
                    },
                ),
                "mpesa_live": mpesa_configured(),
                "can_pay": invoice.is_payable,
                "payment_records": payment_records,
            }
        )
        return context


@method_decorator(login_required, name="dispatch")
class UpdateCourtAttendanceView(View):
    """Record court attendance against an active litigation case."""

    template_name = "accounts/update_court_attendance.html"
    action_slug = "update-court-attendance"

    def get_case(self, case_id):
        return get_object_or_404(
            LitigationCase.objects.select_related(
                "client", "assigned_to", "registered_by"
            ),
            pk=case_id,
        )

    def get(self, request, role, case_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        case = self.get_case(case_id)
        if case.status == LitigationCase.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_litigation_case",
                role=role,
                case_id=case.pk,
            )

        context = self._context(
            user,
            case,
            UpdateCourtAttendanceForm(),
            CourtAttendanceAdvocateFormSet(prefix="advocates"),
            CourtAttendanceBringUpItemFormSet(prefix="bringups"),
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, case_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        case = self.get_case(case_id)
        if case.status == LitigationCase.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_litigation_case",
                role=role,
                case_id=case.pk,
            )

        form = UpdateCourtAttendanceForm(request.POST)
        advocate_formset = CourtAttendanceAdvocateFormSet(
            request.POST, prefix="advocates"
        )
        bringup_formset = CourtAttendanceBringUpItemFormSet(
            request.POST, prefix="bringups"
        )

        if not (
            form.is_valid()
            and advocate_formset.is_valid()
            and bringup_formset.is_valid()
        ):
            context = self._context(
                user, case, form, advocate_formset, bringup_formset
            )
            response = render(request, self.template_name, context)
            return attach_greeting_cookie(response, request)

        attendance = form.save(commit=False)
        attendance.case = case
        attendance.recorded_by = user
        attendance.save()

        advocate_count = 0
        for index, advocate_form in enumerate(advocate_formset):
            if not getattr(advocate_form, "cleaned_data", None):
                continue
            if advocate_form.cleaned_data.get("DELETE"):
                continue
            name = (advocate_form.cleaned_data.get("advocate_name") or "").strip()
            if not name:
                continue
            CourtAttendanceAdvocate.objects.create(
                attendance=attendance,
                advocate_name=name,
                what_they_said=advocate_form.cleaned_data.get("what_they_said")
                or "",
                sort_order=advocate_count,
            )
            advocate_count += 1

        item_count = 0
        for bringup_form in bringup_formset:
            if not getattr(bringup_form, "cleaned_data", None):
                continue
            if bringup_form.cleaned_data.get("DELETE"):
                continue
            description = (
                bringup_form.cleaned_data.get("description") or ""
            ).strip()
            if not description:
                continue
            CourtAttendanceBringUpItem.objects.create(
                attendance=attendance,
                description=description,
                reminder_frequency=bringup_form.cleaned_data.get(
                    "reminder_frequency"
                )
                or "",
                allocated_to=bringup_form.cleaned_data.get("allocated_to"),
                sort_order=item_count,
            )
            item_count += 1

        messages.success(
            request,
            f"Court attendance recorded for "
            f"{attendance.attendance_date.strftime('%d/%m/%Y')}.",
        )
        return redirect(
            "accounts:view_litigation_case",
            role=role,
            case_id=case.pk,
        )

    def _context(self, user, case, form, advocate_formset, bringup_formset):
        detail_url = reverse(
            "accounts:view_litigation_case",
            kwargs={"role": user.role_slug, "case_id": case.pk},
        )
        context = workspace_context(
            user,
            request=self.request,
            page_title="Update court attendance",
            page_trail=list(ACTIVE_CASES_TRAIL),
            active_page=self.action_slug,
            page_nav_items=litigation_case_nav_items(
                user.role_slug, case.pk, active_slug=self.action_slug
            ),
        )
        context.update(
            {
                "case": case,
                "form": form,
                "advocate_formset": advocate_formset,
                "bringup_formset": bringup_formset,
                "detail_url": detail_url,
                "list_url": _active_cases_list_url(user),
                "previous_attendances": (
                    case.court_attendances.select_related("recorded_by")
                    .prefetch_related("advocates", "bring_up_items__allocated_to")
                    .all()
                ),
                "activity_type_suggestions": [
                    "Mention",
                    "Hearing",
                    "Ruling",
                    "Judgment",
                    "Mention for directions",
                    "Taxation",
                    "Call-over",
                ],
                "employee_choices": Employee.objects.filter(
                    status=Employee.Status.ACTIVE
                ).order_by("first_name", "last_name", "login_code"),
            }
        )
        return context


@method_decorator(login_required, name="dispatch")
class CreateCaseTaskView(View):
    """Create a follow-up task for the current litigation case."""

    template_name = "accounts/create_case_task.html"
    action_slug = "create-task"

    def get_case(self, case_id):
        return get_object_or_404(
            LitigationCase.objects.select_related(
                "client", "assigned_to", "registered_by"
            ),
            pk=case_id,
        )

    def get(self, request, role, case_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        case = self.get_case(case_id)
        if case.status == LitigationCase.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_litigation_case",
                role=role,
                case_id=case.pk,
            )

        form = CreateCaseTaskForm(
            initial={
                "assigned_to": case.assigned_to_id,
                "due_date": timezone.localdate(),
            }
        )
        context = self._context(user, case, form)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, case_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        case = self.get_case(case_id)
        if case.status == LitigationCase.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_litigation_case",
                role=role,
                case_id=case.pk,
            )

        form = CreateCaseTaskForm(request.POST)
        if not form.is_valid():
            context = self._context(user, case, form)
            response = render(request, self.template_name, context)
            return attach_greeting_cookie(response, request)

        task = CaseTask.objects.create(
            case=case,
            assignee=form.cleaned_data["assigned_to"],
            title=form.cleaned_data["title"].strip(),
            instructions=form.cleaned_data.get("instructions") or "",
            due_date=form.cleaned_data["due_date"],
            created_by=user,
        )
        notify_case_task(task)
        messages.success(
            request,
            f"Task created and sent to {task.assignee.get_full_name()}.",
        )
        return redirect(
            "accounts:create_case_task",
            role=role,
            case_id=case.pk,
        )

    def _context(self, user, case, form):
        detail_url = reverse(
            "accounts:view_litigation_case",
            kwargs={"role": user.role_slug, "case_id": case.pk},
        )
        context = workspace_context(
            user,
            request=self.request,
            page_title="Create task",
            page_trail=list(ACTIVE_CASES_TRAIL),
            active_page=self.action_slug,
            page_nav_items=litigation_case_nav_items(
                user.role_slug, case.pk, active_slug=self.action_slug
            ),
        )
        context.update(
            {
                "case": case,
                "form": form,
                "detail_url": detail_url,
                "list_url": _active_cases_list_url(user),
                "existing_tasks": (
                    case.tasks.select_related("assignee", "created_by")
                    .order_by("-created_at")
                ),
            }
        )
        return context


@method_decorator(login_required, name="dispatch")
class UploadCaseDocumentsView(View):
    """Create, upload, rename, and manage documents for a litigation case."""

    template_name = "accounts/upload_documents.html"
    action_slug = "upload-documents"
    entity_kind = "case"

    def get_case(self, case_id):
        return get_object_or_404(
            LitigationCase.objects.select_related(
                "client", "assigned_to", "registered_by"
            ),
            pk=case_id,
        )

    def get(self, request, role, case_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        case = self.get_case(case_id)
        if case.status == LitigationCase.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_litigation_case",
                role=role,
                case_id=case.pk,
            )

        context = self._context(
            user,
            case,
            CreateGoogleDocumentForm(auto_id="create_%s"),
            UploadDocumentForm(auto_id="upload_%s"),
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, case_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        case = self.get_case(case_id)
        if case.status == LitigationCase.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_litigation_case",
                role=role,
                case_id=case.pk,
            )

        action = (request.POST.get("document_action") or "").strip()
        create_form = CreateGoogleDocumentForm(auto_id="create_%s")
        upload_form = UploadDocumentForm(auto_id="upload_%s")

        try:
            if action == "create_google":
                create_form = CreateGoogleDocumentForm(
                    request.POST, auto_id="create_%s"
                )
                if create_form.is_valid():
                    self._create_google_doc(
                        user,
                        case,
                        create_form.cleaned_data["title"],
                        create_form.cleaned_data["google_type"],
                        create_form.cleaned_data["description"],
                    )
                    return redirect(
                        "accounts:upload_case_documents",
                        role=role,
                        case_id=case.pk,
                    )
            elif action == "upload":
                upload_form = UploadDocumentForm(
                    request.POST, request.FILES, auto_id="upload_%s"
                )
                if upload_form.is_valid():
                    self._upload_file(user, case, upload_form)
                    return redirect(
                        "accounts:upload_case_documents",
                        role=role,
                        case_id=case.pk,
                    )
            elif action == "rename":
                self._rename_document(request, case)
                return redirect(
                    "accounts:upload_case_documents",
                    role=role,
                    case_id=case.pk,
                )
            elif action == "delete":
                self._delete_document(request, case)
                return redirect(
                    "accounts:upload_case_documents",
                    role=role,
                    case_id=case.pk,
                )
            else:
                messages.error(request, "Unknown document action.")
                return redirect(
                    "accounts:upload_case_documents",
                    role=role,
                    case_id=case.pk,
                )
        except GoogleDriveAPIError as exc:
            messages.error(request, str(exc))
            return redirect(
                "accounts:upload_case_documents",
                role=role,
                case_id=case.pk,
            )

        context = self._context(user, case, create_form, upload_form)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def _create_google_doc(
        self, user, case, title, google_type="document", description=""
    ):
        connection = GoogleDriveConnection.get_solo()
        if not connection.is_connected:
            raise GoogleDriveAPIError(
                "Connect Google Drive in settings before creating documents."
            )
        folder_id = ensure_case_drive_folder(case)
        created = create_google_workspace_file(
            title, type_key=google_type, parent_id=folder_id
        )
        label = created.get("_workspace_label") or "Google Docs"
        document = Document.objects.create(
            case=case,
            title=title,
            source=Document.Source.GOOGLE_DOC,
            drive_file_id=created.get("id") or "",
            web_view_link=created.get("webViewLink") or "",
            mime_type=created.get("mimeType")
            or "application/vnd.google-apps.document",
            description=description or "",
            uploaded_by=user,
        )
        log_document_activity(
            document,
            user,
            DocumentActivity.Action.CREATED,
            detail=f"Created as {label}",
            metadata={"google_type": google_type, "source": document.source},
        )
        messages.success(
            self.request,
            f"“{title}” created in {label}. Open it to start working.",
        )
        return document

    def _upload_file(self, user, case, form):
        connection = GoogleDriveConnection.get_solo()
        if not connection.is_connected:
            raise GoogleDriveAPIError(
                "Connect Google Drive in settings before uploading documents."
            )
        uploaded = form.cleaned_data["file"]
        title = form.cleaned_data["title"]
        notes = (form.cleaned_data.get("notes") or "").strip()
        content = uploaded.read()
        folder_id = ensure_case_drive_folder(case)
        created = upload_drive_file(
            name=title,
            content=content,
            mime_type=getattr(uploaded, "content_type", "") or "",
            parent_id=folder_id,
            original_filename=getattr(uploaded, "name", "") or title,
        )
        document = Document(
            case=case,
            title=title,
            source=Document.Source.UPLOADED,
            drive_file_id=created.get("id") or "",
            web_view_link=created.get("webViewLink") or "",
            mime_type=created.get("mimeType")
            or getattr(uploaded, "content_type", "")
            or "",
            original_filename=getattr(uploaded, "name", "") or "",
            notes=notes,
            uploaded_by=user,
        )
        uploaded.seek(0)
        document.local_file.save(
            getattr(uploaded, "name", "upload.bin"),
            uploaded,
            save=False,
        )
        document.save()
        log_document_activity(
            document,
            user,
            DocumentActivity.Action.UPLOADED,
            detail=document.original_filename or title,
            metadata={"source": document.source},
        )
        messages.success(
            self.request, f"“{title}” uploaded and linked to this case."
        )
        return document

    def _rename_document(self, request, case):
        document = get_object_or_404(
            Document, pk=request.POST.get("document_id"), case=case
        )
        form = RenameDocumentForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Enter a valid document name.")
            return
        title = form.cleaned_data["title"]
        description = form.cleaned_data.get("description") or ""
        notes = form.cleaned_data.get("notes") or ""
        old_title = document.title
        if document.drive_file_id:
            rename_drive_file(document.drive_file_id, title)
        document.title = title
        document.description = description
        document.notes = notes
        document.save(update_fields=["title", "description", "notes", "updated_at"])
        if old_title != title:
            log_document_activity(
                document,
                request.user,
                DocumentActivity.Action.RENAMED,
                detail=f"{old_title} → {title}",
            )
        messages.success(request, f"“{title}” details saved.")

    def _delete_document(self, request, case):
        document = get_object_or_404(
            Document, pk=request.POST.get("document_id"), case=case
        )
        title = document.title
        if document.drive_file_id:
            trash_drive_file(document.drive_file_id)
        if document.local_file:
            document.local_file.delete(save=False)
        document.delete()
        messages.success(request, f"“{title}” removed from this case.")

    def _context(self, user, case, create_form, upload_form):
        detail_url = reverse(
            "accounts:view_litigation_case",
            kwargs={"role": user.role_slug, "case_id": case.pk},
        )
        connection = GoogleDriveConnection.get_solo()
        context = workspace_context(
            user,
            request=self.request,
            page_title="Upload documents",
            page_trail=list(ACTIVE_CASES_TRAIL),
            active_page=self.action_slug,
            page_nav_items=litigation_case_nav_items(
                user.role_slug, case.pk, active_slug=self.action_slug
            ),
        )
        context.update(
            {
                "case": case,
                "matter": None,
                "entity_kind": self.entity_kind,
                "entity_label": case.court_case_number or f"Case #{case.pk}",
                "create_form": create_form,
                "upload_form": upload_form,
                "documents": _documents_with_activity(
                    case.documents, actor=user, sync_google=True, role=user.role_slug
                ),
                "detail_url": detail_url,
                "detail_label": "Back to case",
                "list_url": _active_cases_list_url(user),
                "google_drive_connected": connection.is_connected,
                "google_drive_settings_url": user.workspace_url(
                    "dashboard", "google-drive-settings"
                ),
            }
        )
        return context


@method_decorator(login_required, name="dispatch")
class LitigationCaseActionView(View):
    """Stub workspace pages for litigation case sidebar actions."""

    template_name = "accounts/matter_entity_action.html"

    def get(self, request, role, case_id, action):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied
        if action == "update-court-attendance":
            return redirect(
                "accounts:update_court_attendance",
                role=role,
                case_id=case_id,
            )
        if action == "create-task":
            return redirect(
                "accounts:create_case_task",
                role=role,
                case_id=case_id,
            )
        if action == "edit-case-details":
            return redirect(
                "accounts:edit_active_litigation_case",
                role=role,
                case_id=case_id,
            )
        if action == "upload-documents":
            return redirect(
                "accounts:upload_case_documents",
                role=role,
                case_id=case_id,
            )
        if action == "case-audit-progress":
            return redirect(
                "accounts:case_audit_progress",
                role=role,
                case_id=case_id,
            )
        if action not in LITIGATION_CASE_ACTION_SLUGS:
            return redirect(
                "accounts:view_litigation_case",
                role=role,
                case_id=case_id,
            )

        case = get_object_or_404(
            LitigationCase.objects.select_related("client"),
            pk=case_id,
        )
        if case.status == LitigationCase.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_litigation_case",
                role=role,
                case_id=case.pk,
            )

        page_title = PAGE_TITLES.get(
            action, action.replace("-", " ").title()
        )
        detail_url = reverse(
            "accounts:view_litigation_case",
            kwargs={"role": role, "case_id": case.pk},
        )
        context = workspace_context(
            user,
            request=request,
            page_title=page_title,
            page_trail=list(ACTIVE_CASES_TRAIL),
            active_page=action,
            page_nav_items=litigation_case_nav_items(
                user.role_slug, case.pk, active_slug=action
            ),
        )
        context.update(
            {
                "case": case,
                "entity_label": case.court_case_number or f"Case #{case.pk}",
                "entity_kind": "case",
                "detail_url": detail_url,
                "detail_label": "Back to case",
                "list_url": _active_cases_list_url(user),
            }
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class ViewNonLitigationMatterView(View):
    """Read-only detail page for a non-litigation matter from the matters list."""

    template_name = "accounts/view_non_litigation_matter.html"

    def get(self, request, role, matter_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        matter = get_object_or_404(
            NonLitigationMatter.objects.select_related(
                "client",
                "registered_by",
                "assigned_to",
                "approved_by",
            ).prefetch_related("parties"),
            pk=matter_id,
        )
        if matter.status == NonLitigationMatter.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_non_litigation_matter",
                role=role,
                matter_id=matter.pk,
            )

        context = workspace_context(
            user,
            request=request,
            page_title="View matter",
            page_trail=list(ACTIVE_MATTERS_TRAIL),
            active_page="non-litigation-matters",
            page_nav_items=non_litigation_matter_nav_items(
                user.role_slug, matter.pk
            ),
        )
        context.update(
            {
                "matter": matter,
                "parties": matter.parties.all(),
                "list_url": _active_matters_list_url(user),
            }
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class UpdateMatterAttendanceView(View):
    """Record matter attendance against an active non-litigation matter."""

    template_name = "accounts/update_matter_attendance.html"
    action_slug = "update-matter-attendance"

    def get_matter(self, matter_id):
        return get_object_or_404(
            NonLitigationMatter.objects.select_related(
                "client", "assigned_to", "registered_by"
            ),
            pk=matter_id,
        )

    def get(self, request, role, matter_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        matter = self.get_matter(matter_id)
        if matter.status == NonLitigationMatter.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_non_litigation_matter",
                role=role,
                matter_id=matter.pk,
            )

        context = self._context(user, matter, UpdateMatterAttendanceForm())
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, matter_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        matter = self.get_matter(matter_id)
        if matter.status == NonLitigationMatter.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_non_litigation_matter",
                role=role,
                matter_id=matter.pk,
            )

        form = UpdateMatterAttendanceForm(request.POST)
        if not form.is_valid():
            context = self._context(user, matter, form)
            response = render(request, self.template_name, context)
            return attach_greeting_cookie(response, request)

        attendance = form.save(commit=False)
        attendance.matter = matter
        attendance.recorded_by = user
        attendance.save()

        messages.success(
            request,
            f"Matter attendance recorded for "
            f"{attendance.attendance_date.strftime('%d/%m/%Y')}.",
        )
        return redirect(
            "accounts:view_non_litigation_matter",
            role=role,
            matter_id=matter.pk,
        )

    def _context(self, user, matter, form):
        detail_url = reverse(
            "accounts:view_non_litigation_matter",
            kwargs={"role": user.role_slug, "matter_id": matter.pk},
        )
        prior_attendances = list(
            matter.matter_attendances.select_related("recorded_by").all()
        )
        context = workspace_context(
            user,
            request=self.request,
            page_title="Update matter attendance",
            page_trail=list(ACTIVE_MATTERS_TRAIL),
            active_page=self.action_slug,
            page_nav_items=non_litigation_matter_nav_items(
                user.role_slug, matter.pk, active_slug=self.action_slug
            ),
        )
        context.update(
            {
                "matter": matter,
                "form": form,
                "detail_url": detail_url,
                "list_url": _active_matters_list_url(user),
                "previous_attendances": prior_attendances,
                "is_first_attendance": len(prior_attendances) == 0,
                "activity_type_suggestions": [
                    "Client meeting",
                    "Filing",
                    "Follow-up",
                    "Drafting",
                    "Review",
                    "Signing",
                    "Correspondence",
                ],
            }
        )
        return context


@method_decorator(login_required, name="dispatch")
class CreateMatterTaskView(View):
    """Create a follow-up task for the current non-litigation matter."""

    template_name = "accounts/create_matter_task.html"
    action_slug = "create-task"

    def get_matter(self, matter_id):
        return get_object_or_404(
            NonLitigationMatter.objects.select_related(
                "client", "assigned_to", "registered_by"
            ),
            pk=matter_id,
        )

    def get(self, request, role, matter_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        matter = self.get_matter(matter_id)
        if matter.status == NonLitigationMatter.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_non_litigation_matter",
                role=role,
                matter_id=matter.pk,
            )

        form = CreateMatterTaskForm(
            initial={
                "assigned_to": matter.assigned_to_id,
                "due_date": timezone.localdate(),
            }
        )
        context = self._context(user, matter, form)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, matter_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        matter = self.get_matter(matter_id)
        if matter.status == NonLitigationMatter.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_non_litigation_matter",
                role=role,
                matter_id=matter.pk,
            )

        form = CreateMatterTaskForm(request.POST)
        if not form.is_valid():
            context = self._context(user, matter, form)
            response = render(request, self.template_name, context)
            return attach_greeting_cookie(response, request)

        task = MatterTask.objects.create(
            matter=matter,
            assignee=form.cleaned_data["assigned_to"],
            title=form.cleaned_data["title"].strip(),
            instructions=form.cleaned_data.get("instructions") or "",
            due_date=form.cleaned_data["due_date"],
            created_by=user,
        )
        notify_matter_task(task)
        messages.success(
            request,
            f"Task created and sent to {task.assignee.get_full_name()}.",
        )
        return redirect(
            "accounts:create_matter_task",
            role=role,
            matter_id=matter.pk,
        )

    def _context(self, user, matter, form):
        detail_url = reverse(
            "accounts:view_non_litigation_matter",
            kwargs={"role": user.role_slug, "matter_id": matter.pk},
        )
        context = workspace_context(
            user,
            request=self.request,
            page_title="Create task",
            page_trail=list(ACTIVE_MATTERS_TRAIL),
            active_page=self.action_slug,
            page_nav_items=non_litigation_matter_nav_items(
                user.role_slug, matter.pk, active_slug=self.action_slug
            ),
        )
        context.update(
            {
                "matter": matter,
                "form": form,
                "detail_url": detail_url,
                "list_url": _active_matters_list_url(user),
                "existing_tasks": (
                    matter.tasks.select_related("assignee", "created_by")
                    .order_by("-created_at")
                ),
            }
        )
        return context


@method_decorator(login_required, name="dispatch")
class UploadMatterDocumentsView(View):
    """Create, upload, rename, and manage documents for a non-litigation matter."""

    template_name = "accounts/upload_documents.html"
    action_slug = "upload-documents"
    entity_kind = "matter"

    def get_matter(self, matter_id):
        return get_object_or_404(
            NonLitigationMatter.objects.select_related(
                "client", "assigned_to", "registered_by"
            ),
            pk=matter_id,
        )

    def get(self, request, role, matter_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        matter = self.get_matter(matter_id)
        if matter.status == NonLitigationMatter.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_non_litigation_matter",
                role=role,
                matter_id=matter.pk,
            )

        context = self._context(
            user,
            matter,
            CreateGoogleDocumentForm(auto_id="create_%s"),
            UploadDocumentForm(auto_id="upload_%s"),
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, matter_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        matter = self.get_matter(matter_id)
        if matter.status == NonLitigationMatter.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_non_litigation_matter",
                role=role,
                matter_id=matter.pk,
            )

        action = (request.POST.get("document_action") or "").strip()
        create_form = CreateGoogleDocumentForm(auto_id="create_%s")
        upload_form = UploadDocumentForm(auto_id="upload_%s")

        try:
            if action == "create_google":
                create_form = CreateGoogleDocumentForm(
                    request.POST, auto_id="create_%s"
                )
                if create_form.is_valid():
                    self._create_google_doc(
                        user,
                        matter,
                        create_form.cleaned_data["title"],
                        create_form.cleaned_data["google_type"],
                        create_form.cleaned_data["description"],
                    )
                    return redirect(
                        "accounts:upload_matter_documents",
                        role=role,
                        matter_id=matter.pk,
                    )
            elif action == "upload":
                upload_form = UploadDocumentForm(
                    request.POST, request.FILES, auto_id="upload_%s"
                )
                if upload_form.is_valid():
                    self._upload_file(user, matter, upload_form)
                    return redirect(
                        "accounts:upload_matter_documents",
                        role=role,
                        matter_id=matter.pk,
                    )
            elif action == "rename":
                self._rename_document(request, matter)
                return redirect(
                    "accounts:upload_matter_documents",
                    role=role,
                    matter_id=matter.pk,
                )
            elif action == "delete":
                self._delete_document(request, matter)
                return redirect(
                    "accounts:upload_matter_documents",
                    role=role,
                    matter_id=matter.pk,
                )
            else:
                messages.error(request, "Unknown document action.")
                return redirect(
                    "accounts:upload_matter_documents",
                    role=role,
                    matter_id=matter.pk,
                )
        except GoogleDriveAPIError as exc:
            messages.error(request, str(exc))
            return redirect(
                "accounts:upload_matter_documents",
                role=role,
                matter_id=matter.pk,
            )

        context = self._context(user, matter, create_form, upload_form)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def _create_google_doc(
        self, user, matter, title, google_type="document", description=""
    ):
        connection = GoogleDriveConnection.get_solo()
        if not connection.is_connected:
            raise GoogleDriveAPIError(
                "Connect Google Drive in settings before creating documents."
            )
        folder_id = ensure_matter_drive_folder(matter)
        created = create_google_workspace_file(
            title, type_key=google_type, parent_id=folder_id
        )
        label = created.get("_workspace_label") or "Google Docs"
        document = Document.objects.create(
            matter=matter,
            title=title,
            source=Document.Source.GOOGLE_DOC,
            drive_file_id=created.get("id") or "",
            web_view_link=created.get("webViewLink") or "",
            mime_type=created.get("mimeType")
            or "application/vnd.google-apps.document",
            description=description or "",
            uploaded_by=user,
        )
        log_document_activity(
            document,
            user,
            DocumentActivity.Action.CREATED,
            detail=f"Created as {label}",
            metadata={"google_type": google_type, "source": document.source},
        )
        messages.success(
            self.request,
            f"“{title}” created in {label}. Open it to start working.",
        )
        return document

    def _upload_file(self, user, matter, form):
        connection = GoogleDriveConnection.get_solo()
        if not connection.is_connected:
            raise GoogleDriveAPIError(
                "Connect Google Drive in settings before uploading documents."
            )
        uploaded = form.cleaned_data["file"]
        title = form.cleaned_data["title"]
        notes = (form.cleaned_data.get("notes") or "").strip()
        content = uploaded.read()
        folder_id = ensure_matter_drive_folder(matter)
        created = upload_drive_file(
            name=title,
            content=content,
            mime_type=getattr(uploaded, "content_type", "") or "",
            parent_id=folder_id,
            original_filename=getattr(uploaded, "name", "") or title,
        )
        document = Document(
            matter=matter,
            title=title,
            source=Document.Source.UPLOADED,
            drive_file_id=created.get("id") or "",
            web_view_link=created.get("webViewLink") or "",
            mime_type=created.get("mimeType")
            or getattr(uploaded, "content_type", "")
            or "",
            original_filename=getattr(uploaded, "name", "") or "",
            notes=notes,
            uploaded_by=user,
        )
        uploaded.seek(0)
        document.local_file.save(
            getattr(uploaded, "name", "upload.bin"),
            uploaded,
            save=False,
        )
        document.save()
        log_document_activity(
            document,
            user,
            DocumentActivity.Action.UPLOADED,
            detail=document.original_filename or title,
            metadata={"source": document.source},
        )
        messages.success(
            self.request, f"“{title}” uploaded and linked to this matter."
        )
        return document

    def _rename_document(self, request, matter):
        document = get_object_or_404(
            Document, pk=request.POST.get("document_id"), matter=matter
        )
        form = RenameDocumentForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Enter a valid document name.")
            return
        title = form.cleaned_data["title"]
        description = form.cleaned_data.get("description") or ""
        notes = form.cleaned_data.get("notes") or ""
        old_title = document.title
        if document.drive_file_id:
            rename_drive_file(document.drive_file_id, title)
        document.title = title
        document.description = description
        document.notes = notes
        document.save(update_fields=["title", "description", "notes", "updated_at"])
        if old_title != title:
            log_document_activity(
                document,
                request.user,
                DocumentActivity.Action.RENAMED,
                detail=f"{old_title} → {title}",
            )
        messages.success(request, f"“{title}” details saved.")

    def _delete_document(self, request, matter):
        document = get_object_or_404(
            Document, pk=request.POST.get("document_id"), matter=matter
        )
        title = document.title
        if document.drive_file_id:
            trash_drive_file(document.drive_file_id)
        if document.local_file:
            document.local_file.delete(save=False)
        document.delete()
        messages.success(request, f"“{title}” removed from this matter.")

    def _context(self, user, matter, create_form, upload_form):
        detail_url = reverse(
            "accounts:view_non_litigation_matter",
            kwargs={"role": user.role_slug, "matter_id": matter.pk},
        )
        connection = GoogleDriveConnection.get_solo()
        context = workspace_context(
            user,
            request=self.request,
            page_title="Upload documents",
            page_trail=list(ACTIVE_MATTERS_TRAIL),
            active_page=self.action_slug,
            page_nav_items=non_litigation_matter_nav_items(
                user.role_slug, matter.pk, active_slug=self.action_slug
            ),
        )
        context.update(
            {
                "case": None,
                "matter": matter,
                "entity_kind": self.entity_kind,
                "entity_label": matter.matter_title,
                "create_form": create_form,
                "upload_form": upload_form,
                "documents": _documents_with_activity(
                    matter.documents, actor=user, sync_google=True, role=user.role_slug
                ),
                "detail_url": detail_url,
                "detail_label": "Back to matter",
                "list_url": _active_matters_list_url(user),
                "google_drive_connected": connection.is_connected,
                "google_drive_settings_url": user.workspace_url(
                    "dashboard", "google-drive-settings"
                ),
            }
        )
        return context


def _documents_with_activity(queryset, *, actor=None, sync_google: bool = False, role=""):
    from django.db.models import Prefetch

    documents = list(
        queryset.select_related("uploaded_by")
        .prefetch_related(
            Prefetch(
                "activities",
                queryset=DocumentActivity.objects.select_related("actor"),
            ),
            Prefetch(
                "content_snapshots",
                queryset=DocumentContentSnapshot.objects.order_by("-captured_at", "-id"),
            ),
            "open_sessions",
        )
        .all()
    )
    if sync_google:
        for document in documents:
            if document.drive_file_id:
                try:
                    sync_google_document_content(document, actor=actor)
                except GoogleDriveAPIError:
                    # Never block the library page on Drive sync issues.
                    pass
        # Re-fetch activities/snapshots after sync so new edits appear immediately.
        documents = list(
            queryset.select_related("uploaded_by")
            .prefetch_related(
                Prefetch(
                    "activities",
                    queryset=DocumentActivity.objects.select_related("actor"),
                ),
                Prefetch(
                    "content_snapshots",
                    queryset=DocumentContentSnapshot.objects.order_by(
                        "-captured_at", "-id"
                    ),
                ),
                "open_sessions",
            )
            .all()
        )
    if role:
        for document in documents:
            document.activity_url = reverse(
                "accounts:document_activity",
                kwargs={"role": role, "document_id": document.pk},
            )
            document.tracked_open_url = reverse(
                "accounts:open_document",
                kwargs={"role": role, "document_id": document.pk},
            )
    return documents


def _document_library_return_url(document, role):
    if document.case_id:
        return reverse(
            "accounts:upload_case_documents",
            kwargs={"role": role, "case_id": document.case_id},
        )
    return reverse(
        "accounts:upload_matter_documents",
        kwargs={"role": role, "matter_id": document.matter_id},
    )


@method_decorator(login_required, name="dispatch")
class CaseAuditProgressView(View):
    """Full chronological audit trail for a litigation case."""

    template_name = "accounts/case_audit_progress.html"
    action_slug = "case-audit-progress"

    def get(self, request, role, case_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        case = get_object_or_404(
            LitigationCase.objects.select_related(
                "client",
                "registered_by",
                "assigned_to",
                "approved_by",
            ).prefetch_related("parties"),
            pk=case_id,
        )
        if case.status == LitigationCase.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_litigation_case",
                role=role,
                case_id=case.pk,
            )

        events = build_case_audit_events(case, role=role)
        summary = case_audit_summary(events)
        detail_url = reverse(
            "accounts:view_litigation_case",
            kwargs={"role": role, "case_id": case.pk},
        )
        context = workspace_context(
            user,
            request=request,
            page_title="Case audit progress",
            page_trail=list(ACTIVE_CASES_TRAIL),
            active_page=self.action_slug,
            page_nav_items=litigation_case_nav_items(
                user.role_slug, case.pk, active_slug=self.action_slug
            ),
        )
        context.update(
            {
                "case": case,
                "entity_label": case.court_case_number or f"Case #{case.pk}",
                "entity_kind": "case",
                "detail_url": detail_url,
                "detail_label": "Back to case",
                "list_url": _active_cases_list_url(user),
                "events": events,
                "audit_summary": summary,
            }
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class DocumentActivityAnalyticsView(View):
    """Detailed activity analytics for a single document."""

    template_name = "accounts/document_activity.html"

    def get(self, request, role, document_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        document = get_object_or_404(
            Document.objects.select_related(
                "case",
                "case__client",
                "matter",
                "matter__client",
                "uploaded_by",
            ).prefetch_related(
                "open_sessions__actor",
                "activities__actor",
            ),
            pk=document_id,
        )
        library_url = _document_library_return_url(document, role)
        analytics = document.detailed_analytics()
        page_trail = list(
            ACTIVE_CASES_TRAIL if document.case_id else ACTIVE_MATTERS_TRAIL
        )
        context = workspace_context(
            user,
            request=request,
            page_title="Document activity",
            page_trail=page_trail,
            active_page="upload-documents",
        )
        entity_label = ""
        if document.case_id:
            entity_label = (
                document.case.court_case_number or f"Case #{document.case_id}"
            )
        elif document.matter_id:
            entity_label = document.matter.matter_title

        context.update(
            {
                "document": document,
                "analytics": analytics,
                "library_url": library_url,
                "entity_kind": "case" if document.case_id else "matter",
                "entity_label": entity_label,
                "open_url": reverse(
                    "accounts:open_document",
                    kwargs={"role": role, "document_id": document.pk},
                ),
            }
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class OpenDocumentView(View):
    """Start a tracked open session, then show the time-tracking page."""

    template_name = "accounts/document_open_session.html"

    def get(self, request, role, document_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        document = get_object_or_404(
            Document.objects.select_related("case", "matter", "uploaded_by"),
            pk=document_id,
        )
        target_url = (document.open_url or "").strip()
        if not target_url and document.local_file:
            target_url = document.local_file.url
        if not target_url:
            messages.error(request, "This document has no openable link.")
            return redirect(_document_library_return_url(document, role))

        session = start_open_session(document, user)
        ping_url = reverse(
            "accounts:document_session_ping",
            kwargs={
                "role": role,
                "document_id": document.pk,
                "session_id": session.pk,
            },
        )
        library_url = _document_library_return_url(document, role)
        wants_json = (
            request.GET.get("format") == "json"
            or "application/json" in (request.headers.get("Accept") or "")
        )
        if wants_json:
            return JsonResponse(
                {
                    "ok": True,
                    "document_id": document.pk,
                    "document_title": document.title,
                    "session_id": session.pk,
                    "target_url": target_url,
                    "ping_url": ping_url,
                    "library_url": library_url,
                }
            )

        context = workspace_context(
            user,
            request=request,
            page_title="Document session",
            page_trail=list(
                ACTIVE_CASES_TRAIL if document.case_id else ACTIVE_MATTERS_TRAIL
            ),
            active_page="upload-documents",
        )
        context.update(
            {
                "document": document,
                "session": session,
                "target_url": target_url,
                "ping_url": ping_url,
                "library_url": library_url,
                "entity_kind": "case" if document.case_id else "matter",
            }
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class DownloadDocumentView(View):
    """Log a download, then serve or redirect to the file."""

    def get(self, request, role, document_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        document = get_object_or_404(Document, pk=document_id)
        log_document_activity(
            document,
            user,
            DocumentActivity.Action.DOWNLOADED,
            detail=document.original_filename or document.title,
        )
        if document.local_file:
            return redirect(document.local_file.url)
        if document.open_url:
            return redirect(document.open_url)
        messages.error(request, "No downloadable file is available.")
        return redirect(_document_library_return_url(document, role))


@method_decorator(login_required, name="dispatch")
class DocumentSessionPingView(View):
    """Heartbeat / end endpoint for an open document session."""

    def post(self, request, role, document_id, session_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return JsonResponse({"ok": False, "error": "unauthorized"}, status=403)

        session = get_object_or_404(
            DocumentOpenSession.objects.select_related("document"),
            pk=session_id,
            document_id=document_id,
            actor=user,
        )
        action = (request.POST.get("action") or "ping").strip().lower()
        if action in {"end", "close", "stop"}:
            end_open_session(session, reason=request.POST.get("reason") or "closed")
            return JsonResponse(
                {
                    "ok": True,
                    "ended": True,
                    "duration_seconds": session.duration_seconds,
                    "kind": session.kind,
                }
            )

        if session.ended_at:
            return JsonResponse(
                {
                    "ok": True,
                    "ended": True,
                    "duration_seconds": session.duration_seconds,
                    "kind": session.kind,
                }
            )

        session.touch()
        kind = session.kind
        if (request.POST.get("sync_content") or "").strip() == "1":
            kind = detect_session_behavior(session, sync=True)
        else:
            kind = session.kind

        return JsonResponse(
            {
                "ok": True,
                "ended": False,
                "duration_seconds": session.duration_seconds,
                "kind": kind,
                "content_changed": session.content_changed,
            }
        )


@method_decorator(login_required, name="dispatch")
class NonLitigationMatterActionView(View):
    """Stub workspace pages for non-litigation matter sidebar actions."""

    template_name = "accounts/matter_entity_action.html"

    def get(self, request, role, matter_id, action):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied
        if action == "update-matter-attendance":
            return redirect(
                "accounts:update_matter_attendance",
                role=role,
                matter_id=matter_id,
            )
        if action == "create-task":
            return redirect(
                "accounts:create_matter_task",
                role=role,
                matter_id=matter_id,
            )
        if action == "edit-matter-details":
            return redirect(
                "accounts:edit_active_non_litigation_matter",
                role=role,
                matter_id=matter_id,
            )
        if action == "upload-documents":
            return redirect(
                "accounts:upload_matter_documents",
                role=role,
                matter_id=matter_id,
            )
        if action not in NON_LITIGATION_MATTER_ACTION_SLUGS:
            return redirect(
                "accounts:view_non_litigation_matter",
                role=role,
                matter_id=matter_id,
            )

        matter = get_object_or_404(
            NonLitigationMatter.objects.select_related("client"),
            pk=matter_id,
        )
        if matter.status == NonLitigationMatter.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_non_litigation_matter",
                role=role,
                matter_id=matter.pk,
            )

        page_title = PAGE_TITLES.get(
            action, action.replace("-", " ").title()
        )
        detail_url = reverse(
            "accounts:view_non_litigation_matter",
            kwargs={"role": role, "matter_id": matter.pk},
        )
        context = workspace_context(
            user,
            request=request,
            page_title=page_title,
            page_trail=list(ACTIVE_MATTERS_TRAIL),
            active_page=action,
            page_nav_items=non_litigation_matter_nav_items(
                user.role_slug, matter.pk, active_slug=action
            ),
        )
        context.update(
            {
                "matter": matter,
                "entity_label": matter.matter_title,
                "entity_kind": "matter",
                "detail_url": detail_url,
                "detail_label": "Back to matter",
                "list_url": _active_matters_list_url(user),
            }
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class ViewCaseTaskView(View):
    """Assignee views an accepted (or otherwise assigned) case task."""

    template_name = "accounts/view_case_task.html"
    kind = "case"

    def get_task(self, task_id, user):
        return get_object_or_404(
            CaseTask.objects.select_related(
                "case",
                "case__client",
                "case__registered_by",
                "created_by",
                "assignee",
            ).prefetch_related("case__parties"),
            pk=task_id,
            assignee=user,
        )

    def get(self, request, role, task_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        task = self.get_task(task_id, user)
        case = task.case
        tasks_url = user.workspace_url("dashboard", "tasks")
        context = workspace_context(
            user,
            request=request,
            page_title="View task",
            page_trail=["dashboard", "tasks"],
            active_page="tasks",
        )
        context.update(
            {
                "task": task,
                "kind": self.kind,
                "case": case,
                "parties": case.parties.all(),
                "list_url": f"{tasks_url}?kind={self.kind}&id={task.pk}",
            }
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class ViewMatterTaskView(View):
    """Assignee views an accepted (or otherwise assigned) matter task."""

    template_name = "accounts/view_matter_task.html"
    kind = "matter"

    def get_task(self, task_id, user):
        return get_object_or_404(
            MatterTask.objects.select_related(
                "matter",
                "matter__client",
                "matter__registered_by",
                "created_by",
                "assignee",
            ).prefetch_related("matter__parties"),
            pk=task_id,
            assignee=user,
        )

    def get(self, request, role, task_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        task = self.get_task(task_id, user)
        matter = task.matter
        tasks_url = user.workspace_url("dashboard", "tasks")
        context = workspace_context(
            user,
            request=request,
            page_title="View task",
            page_trail=["dashboard", "tasks"],
            active_page="tasks",
        )
        context.update(
            {
                "task": task,
                "kind": self.kind,
                "matter": matter,
                "parties": matter.parties.all(),
                "list_url": f"{tasks_url}?kind={self.kind}&id={task.pk}",
            }
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class RespondCaseTaskView(View):
    """Assignee accepts or rejects a case task (reject requires a reason)."""

    kind = "case"
    respond_url_name = "accounts:respond_case_task"
    view_url_name = "accounts:view_case_task"

    def get_task(self, task_id, user):
        return get_object_or_404(
            CaseTask.objects.select_related("case", "created_by", "assignee"),
            pk=task_id,
            assignee=user,
        )

    def task_subject(self, task):
        return str(task.case)

    def post(self, request, role, task_id):
        user, denied = _employee_workspace_guard(request, role)
        if denied:
            return denied

        task = self.get_task(task_id, user)
        action = (request.POST.get("action") or "").strip()
        tasks_url = user.workspace_url("dashboard", "tasks")
        respond_url = reverse(
            self.respond_url_name,
            kwargs={"role": role, "task_id": task.pk},
        )

        if task.status != CaseTask.Status.PENDING:
            messages.info(request, "This task has already been responded to.")
            return redirect(f"{tasks_url}?kind={self.kind}&id={task.pk}")

        if action == "accept":
            form = AcceptTaskForm(request.POST, due_date=task.due_date)
            if not form.is_valid():
                return self._tasks_page(
                    request,
                    user,
                    accept_form=form,
                    open_accept=True,
                    accept_target={
                        "kind": self.kind,
                        "task_id": task.pk,
                        "url": respond_url,
                        "subject": self.task_subject(task),
                        "due_date": task.due_date.isoformat(),
                    },
                )

            task.status = CaseTask.Status.ACCEPTED
            task.rejection_reason = ""
            task.reminder_at = form.cleaned_data.get("reminder_at")
            task.responded_at = timezone.now()
            task.save(
                update_fields=[
                    "status",
                    "rejection_reason",
                    "reminder_at",
                    "responded_at",
                    "updated_at",
                ]
            )
            notify_task_accepted(task, kind=self.kind)
            if task.reminder_at:
                messages.success(
                    request,
                    "Task accepted. Your reminder has been set.",
                )
            else:
                messages.success(request, "Task accepted.")
            return redirect(
                reverse(
                    self.view_url_name,
                    kwargs={"role": role, "task_id": task.pk},
                )
            )

        if action == "reject":
            form = RejectTaskForm(request.POST)
            if not form.is_valid():
                return self._tasks_page(
                    request,
                    user,
                    reject_form=form,
                    open_reject=True,
                    reject_target={
                        "kind": self.kind,
                        "task_id": task.pk,
                        "url": respond_url,
                        "subject": self.task_subject(task),
                    },
                )

            task.status = CaseTask.Status.REJECTED
            task.rejection_reason = form.cleaned_data["reason"]
            task.responded_at = timezone.now()
            task.save(
                update_fields=[
                    "status",
                    "rejection_reason",
                    "responded_at",
                    "updated_at",
                ]
            )
            notify_task_rejected(task, kind=self.kind)
            messages.success(
                request,
                "Task rejected. The person who tasked you has been notified.",
            )
            return redirect(f"{tasks_url}?kind={self.kind}&id={task.pk}")

        messages.error(request, "Unknown action.")
        return redirect(tasks_url)

    @staticmethod
    def _tasks_page(
        request,
        user,
        *,
        accept_form=None,
        reject_form=None,
        open_accept=False,
        open_reject=False,
        accept_target=None,
        reject_target=None,
    ):
        context = workspace_context(
            user,
            request=request,
            page_title="Tasks",
            page_trail=["dashboard", "tasks"],
            active_page="tasks",
        )
        context.update(RoleWorkspaceView._tasks_context(user, request))
        if accept_form is not None:
            context["accept_form"] = accept_form
        if reject_form is not None:
            context["reject_form"] = reject_form
        context["open_accept_modal"] = open_accept
        context["open_reject_modal"] = open_reject
        context["accept_target"] = accept_target
        context["reject_target"] = reject_target
        response = render(request, "accounts/tasks.html", context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class RespondMatterTaskView(RespondCaseTaskView):
    """Assignee accepts or rejects a matter task (reject requires a reason)."""

    kind = "matter"
    respond_url_name = "accounts:respond_matter_task"
    view_url_name = "accounts:view_matter_task"

    def get_task(self, task_id, user):
        return get_object_or_404(
            MatterTask.objects.select_related(
                "matter", "created_by", "assignee"
            ),
            pk=task_id,
            assignee=user,
        )

    def task_subject(self, task):
        return str(task.matter)


@method_decorator(login_required, name="dispatch")
class LegacySettingsRedirectView(View):
    def get(self, request):
        user = request.user
        if user.status != Employee.Status.ACTIVE:
            return redirect_for_employee(user)
        return redirect(user.workspace_url("dashboard", "settings"))


@method_decorator(login_required, name="dispatch")
class LegacyDashboardRedirectView(View):
    role_slug = None

    def get(self, request):
        user = request.user
        if user.status != Employee.Status.ACTIVE:
            return redirect_for_employee(user)
        if self.role_slug and self.role_slug != user.role_slug:
            return redirect(user.dashboard_url)
        return redirect(user.dashboard_url)


@method_decorator(login_required, name="dispatch")
class LegacyEmployeesPrefixRedirectView(View):
    """ /employees/<role>/... → /<role>/... """

    def get(self, request, role, pages="dashboard"):
        user = request.user
        if user.status != Employee.Status.ACTIVE:
            return redirect_for_employee(user)
        trail = [part for part in pages.strip("/").split("/") if part] or ["dashboard"]
        if role != user.role_slug:
            return redirect(user.workspace_url(*trail))
        return redirect(user.workspace_url(*trail))
