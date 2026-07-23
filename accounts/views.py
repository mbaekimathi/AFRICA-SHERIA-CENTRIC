from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.db.models import ProtectedError, Q, Value
from django.db.models.functions import Concat
from django.http import FileResponse, HttpResponse, JsonResponse
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
from datetime import date, timedelta
from django.utils.safestring import mark_safe
from .appearance import appearance_catalog
from .client_auth import (
    end_staff_impersonation,
    get_client,
    is_staff_impersonating,
    login_client,
    logout_client,
    redirect_for_client,
    start_staff_impersonation,
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
    StaffClientProfileForm,
    StaffRegisterClientForm,
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
    employees_available_for_payroll,
    FAQForm,
    FinanceSettingsForm,
    CommunicationSettingsForm,
    GalleryImageForm,
    GenerateInvoiceForm,
    InvoiceStkPaymentForm,
    LatestNewsScrapeForm,
    LoginForm,
    MatterAttendanceBringUpItemFormSet,
    MatterAttendanceQuorumFormSet,
    MatterPartyEditFormSet,
    MatterPartyFormSet,
    NotificationSettingsForm,
    PracticeAreaForm,
    ProfileSettingsForm,
    RegisterCaseForm,
    RegisterMatterForm,
    RegisterPayrollForm,
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
    download_drive_file,
    validate_oauth_state,
)
from .blog_analytics import record_blog_event
from .blog_share import (
    build_share_intents,
    company_share_accounts,
    pop_share_intents,
    stash_share_intents,
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
    BlogPostEvent,
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
    EmployeeActivityPermission,
    EmployeeBlogPost,
    EmployeeWorkSession,
    CommunicationSettings,
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
    MatterAttendanceBringUpItem,
    MatterAttendanceQuorumMember,
    MatterParty,
    MatterTask,
    NewsSearchJob,
    NewsWatch,
    NonLitigationMatter,
    Notification,
    PayrollDeduction,
    PayrollPayment,
    PayrollRun,
    RoleActivityPermission,
    WebsiteTemplateSetting,
)
from .notifications import (
    notifications_payload,
    notify_case_task,
    notify_google_drive_disconnected,
    notify_matter_task,
    notify_task_accepted,
    notify_task_completed,
    notify_task_rejected,
)
from .news_blog import build_news_blog_draft
from .employee_performance import (
    annotate_employee_performance_summaries,
    build_employee_performance_analytics,
    employee_summary_metrics,
)
from .employee_sessions import (
    batch_employee_session_summaries,
    build_employee_session_analytics,
    end_employee_session,
    start_employee_session,
)
from .workspace import (
    activity_permission_actions,
    assign_session_greeting,
    attach_greeting_cookie,
    client_account_page_nav_items,
    collect_module_activities,
    DASHBOARD_PAGE_LINKS,
    employee_preactive_context,
    extend_page_trail,
    litigation_case_nav_items,
    LITIGATION_CASE_ACTION_SLUGS,
    mark_session_start,
    module_activity_url,
    module_slug_for_trail,
    non_litigation_matter_nav_items,
    NON_LITIGATION_MATTER_ACTION_SLUGS,
    PAGE_LOCAL_LINKS,
    PAGE_TITLES,
    redirect_if_workspace_action_denied,
    resolve_workspace_page,
    resolve_workspace_post_action,
    role_activity_is_allowed,
    role_page_slugs,
    roles_activity_permission_url,
    set_employee_activity_permission,
    set_role_activity_permission,
    set_workspace_access_denied_modal,
    system_module_hint,
    SYSTEM_MODULE_SLUGS,
    workspace_activity_access_allowed,
    workspace_activity_action_permitted,
    workspace_action_denial_copy,
    workspace_activity_denial_copy,
    workspace_detail_permission_action,
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
        record_blog_event(request, post, BlogPostEvent.EventType.VIEW)
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
                "blog_track_url": reverse("accounts:blog_event_track", kwargs={"slug": post.slug}),
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


@method_decorator(csrf_exempt, name="dispatch")
class BlogEventTrackView(View):
    """Record a public blog CTA / interaction from the website."""

    def post(self, request, slug):
        post = get_object_or_404(
            EmployeeBlogPost,
            slug=slug,
            status=EmployeeBlogPost.Status.PUBLISHED,
        )
        event_type = ""
        content_type = (request.content_type or "").lower()
        if "application/json" in content_type:
            try:
                payload = json.loads(request.body.decode("utf-8") or "{}")
            except (TypeError, ValueError, UnicodeDecodeError):
                payload = {}
            event_type = str(payload.get("event_type") or "")
        else:
            event_type = request.POST.get("event_type", "")
        stored = record_blog_event(request, post, event_type)
        return JsonResponse({"ok": bool(stored)})


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
        start_employee_session(self.request, user)
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


class EmployeeLogoutView(View):
    """Sign out and close the tracked employee work session."""

    def post(self, request):
        end_employee_session(
            request,
            kind=EmployeeWorkSession.LogoutKind.MANUAL,
        )
        logout(request)
        return redirect("accounts:login")


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
            start_employee_session(request, user)
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
            f"with folders for {summary['clients_created']} client(s) and "
            f"{summary.get('employees_created', 0)} employee(s).",
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
    user, denied = _guard_invoicing(request, role, action="pay")
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
        if is_staff_impersonating(request):
            return_url = end_staff_impersonation(request)
            messages.info(
                request,
                "You have left the client portal and returned to your staff session.",
            )
            if return_url:
                return redirect(return_url)
            if request.user.is_authenticated:
                return redirect(
                    request.user.workspace_url(*CLIENT_PROFILE_TRAIL)
                )
            return redirect("accounts:home")

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
@require_POST
def company_contacts_verify(request):
    """Live-verify firm contact channels (email, phone, website, social)."""
    user = request.user
    if user.status != Employee.Status.ACTIVE:
        return JsonResponse({"error": "forbidden"}, status=403)
    if "company-contacts" not in role_page_slugs(user.role):
        return JsonResponse({"error": "forbidden"}, status=403)

    from .contact_verification import CHANNEL_SPECS, verify_company_contacts

    overrides: dict[str, str] = {}
    content_type = (request.content_type or "").lower()
    if "application/json" in content_type:
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return JsonResponse({"error": "invalid_json"}, status=400)
        if isinstance(payload, dict):
            values = payload.get("values")
            if isinstance(values, dict):
                source = values
            else:
                source = payload
            allowed = {spec["key"] for spec in CHANNEL_SPECS}
            for key, raw in source.items():
                if key in allowed:
                    overrides[key] = "" if raw is None else str(raw)
    else:
        allowed = {spec["key"] for spec in CHANNEL_SPECS}
        for key in allowed:
            if key in request.POST:
                overrides[key] = request.POST.get(key) or ""

    result = verify_company_contacts(
        FirmCompanyInformation.get_solo(),
        overrides=overrides or None,
    )
    return JsonResponse({"ok": True, **result})


@login_required
@require_POST
def communication_settings_verify(request):
    """Live-verify email SMTP, SMS, and WhatsApp provider configuration."""
    user = request.user
    if user.status != Employee.Status.ACTIVE:
        return JsonResponse({"error": "forbidden"}, status=403)
    if "communication-settings" not in role_page_slugs(user.role):
        return JsonResponse({"error": "forbidden"}, status=403)

    from .communication_verification import (
        OVERRIDE_KEYS,
        verify_communication_settings,
    )

    overrides: dict = {}
    content_type = (request.content_type or "").lower()
    if "application/json" in content_type:
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return JsonResponse({"error": "invalid_json"}, status=400)
        if isinstance(payload, dict):
            values = payload.get("values")
            if isinstance(values, dict):
                source = values
            else:
                source = payload
            for key, raw in source.items():
                if key in OVERRIDE_KEYS:
                    overrides[key] = raw
    else:
        for key in OVERRIDE_KEYS:
            if key in request.POST:
                overrides[key] = request.POST.get(key)

    result = verify_communication_settings(
        CommunicationSettings.get_solo(),
        overrides=overrides or None,
    )
    return JsonResponse({"ok": True, **result})


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

    limit = request.GET.get("limit")
    if limit and str(limit).isdigit():
        qs = qs.order_by("company_name", "first_name", "last_name")[: int(limit)]
    elif query:
        qs = qs.order_by("company_name", "first_name", "last_name")[:15]
    else:
        qs = qs.order_by("company_name", "first_name", "last_name")

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


def _client_profile_avatar(client) -> dict:
    """Avatar fields for matter-browse client profile tiles."""
    is_corporate = client.client_type == Client.ClientType.CORPORATE
    if is_corporate:
        source = (client.company_name or client.email or "?").strip()
        initials = (source[:1] or "?").upper()
    else:
        first = (client.first_name or "").strip()
        last = (client.last_name or "").strip()
        if first or last:
            initials = f"{first[:1]}{last[:1]}".upper()
        else:
            initials = ((client.email or "?")[:1]).upper()
    photo_url = ""
    if client.profile_photo:
        try:
            photo_url = client.profile_photo.url
        except ValueError:
            photo_url = ""
    return {
        "photo_url": photo_url,
        "initials": initials or "?",
        "is_corporate": is_corporate,
        "name": client.get_full_name(),
    }


MATTER_CATEGORY_ICON_META = {
    "conveyancing": ("home", 3),
    "commercial": ("handshake", 1),
    "employment": ("briefcase", 5),
    "intellectual_property": ("bulb", 7),
    "corporate": ("building", 2),
    "probate": ("scroll", 4),
    "immigration": ("globe", 5),
    "regulatory": ("shield", 6),
    "due_diligence": ("search-doc", 1),
    "advisory": ("advice", 2),
    "other": ("folder", 1),
}

COURT_RANK_ICON_META = {
    "supreme_court": ("scales", 3),
    "court_of_appeal": ("scales", 1),
    "high_court": ("courthouse", 5),
    "elc": ("land", 6),
    "elrc": ("briefcase", 2),
    "magistrates": ("gavel", 3),
    "kadhis": ("scroll", 7),
    "court_martial": ("shield", 4),
    "small_claims": ("gavel", 1),
    "tribunal": ("building", 5),
}


def _normalize_choice_key(raw: str, choices) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    mapping = dict(choices)
    if value in mapping:
        return value
    lowered = value.lower()
    for key, label in choices:
        if key.lower() == lowered or label.lower() == lowered:
            return key
    return value


def matter_browse_icon_meta(kind: str, raw_key: str = "", *, index: int = 0) -> dict:
    """Return icon slug + tone for matter-browse 3D tiles."""
    if kind == "client":
        return {"icon": "client", "tone": (index % 6) + 1}
    if kind == "category":
        key = _normalize_choice_key(
            raw_key, NonLitigationMatter.MatterCategory.choices
        )
        icon, tone = MATTER_CATEGORY_ICON_META.get(
            key, ("folder", (index % 6) + 1)
        )
        return {"icon": icon, "tone": tone}
    if kind == "court":
        key = _normalize_choice_key(raw_key, LitigationCase.CourtRank.choices)
        icon, tone = COURT_RANK_ICON_META.get(
            key, ("courthouse", (index % 6) + 1)
        )
        return {"icon": icon, "tone": tone}
    return {"icon": "folder", "tone": (index % 6) + 1}


def group_litigation_cases(cases, group_by: str):
    """Group active litigation cases by court rank or client for card browse UI."""
    mode = group_by if group_by in {"court", "client"} else "court"
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
                    "icon": "client",
                    "icon_tone": (index % 6) + 1,
                    "profile": _client_profile_avatar(client),
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
            icon_meta = matter_browse_icon_meta("court", key, index=index)
            groups.append(
                {
                    "key": f"court-{key}",
                    "label": label,
                    "subtitle": subtitle,
                    "count": len(items),
                    "items": items,
                    "tone": icon_meta["tone"] - 1,
                    "icon": icon_meta["icon"],
                    "icon_tone": icon_meta["tone"],
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


def resolve_matter_group_by(request, *, session_key: str, allowed: set[str], default: str):
    """Resolve browse grouping from query, then session, then default."""
    requested = (request.GET.get("group") or "").strip()
    if requested in allowed:
        request.session[session_key] = requested
        return requested
    saved = request.session.get(session_key)
    if saved in allowed:
        return saved
    return default


def group_non_litigation_matters(matters, group_by: str):
    """Group active non-litigation matters by client or category for card browse UI."""
    mode = group_by if group_by in {"category", "client"} else "category"
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
                    "icon": "client",
                    "icon_tone": (index % 6) + 1,
                    "profile": _client_profile_avatar(client),
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
            icon_meta = matter_browse_icon_meta("category", key, index=index)
            groups.append(
                {
                    "key": f"category-{key}",
                    "label": label,
                    "subtitle": subtitle,
                    "count": len(items),
                    "items": items,
                    "tone": icon_meta["tone"] - 1,
                    "icon": icon_meta["icon"],
                    "icon_tone": icon_meta["tone"],
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


def build_client_account_summaries(clients):
    """Build per-client invoice account summaries for the client accounts page."""
    from decimal import Decimal

    if not clients:
        return []

    client_ids = [client.pk for client in clients]
    invoices_by_client = defaultdict(list)
    invoices = (
        Invoice.objects.filter(client_id__in=client_ids)
        .exclude(status=Invoice.Status.CANCELLED)
        .select_related("client")
        .order_by("-issue_date", "-created_at")
    )
    for invoice in invoices:
        invoices_by_client[invoice.client_id].append(invoice)

    summaries = []
    for index, client in enumerate(clients):
        items = invoices_by_client.get(client.pk, [])
        total_invoiced = sum(
            (invoice.total_amount for invoice in items),
            Decimal("0.00"),
        )
        total_paid = sum(
            (invoice.amount_paid for invoice in items),
            Decimal("0.00"),
        )
        balance_due = sum(
            (invoice.balance_due for invoice in items),
            Decimal("0.00"),
        )
        open_count = sum(
            1 for invoice in items if invoice.status != Invoice.Status.PAID
        )
        search_bits = [
            client.get_full_name(),
            client.get_client_type_display(),
            client.phone or "",
            client.email or "",
            *[
                f"{invoice.invoice_number} {invoice.description} "
                f"{invoice.get_status_display()}"
                for invoice in items
            ],
        ]
        summaries.append(
            {
                "client": client,
                "label": client.get_full_name(),
                "subtitle": (
                    f"{client.get_client_type_display()} · "
                    f"{_client_contact_subtitle(client)}"
                ),
                "invoices": items,
                "invoice_count": len(items),
                "total_invoiced": total_invoiced,
                "total_paid": total_paid,
                "balance_due": balance_due,
                "open_count": open_count,
                "tone": index % 6,
                "search_text": " ".join(search_bits).lower(),
            }
        )
    return summaries


def _parse_client_ids_param(raw_value):
    """Parse a comma-separated list of client primary keys from a query string."""
    if not raw_value:
        return []

    client_ids = []
    seen = set()
    for part in raw_value.split(","):
        part = part.strip()
        if not part or not part.isdigit():
            continue
        client_id = int(part)
        if client_id in seen:
            continue
        seen.add(client_id)
        client_ids.append(client_id)
    return client_ids


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
    client_profile_template = "accounts/client_profile.html"
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
    latest_news_template = "accounts/latest_news.html"
    company_faq_form_template = "accounts/company_faq_form.html"
    website_template_template = "accounts/website_template.html"
    system_settings_template = "accounts/system_settings.html"
    finance_settings_template = "accounts/finance_settings.html"
    communication_settings_template = "accounts/communication_settings.html"
    invoicing_template = "accounts/invoicing.html"
    generate_invoice_template = "accounts/generate_invoice.html"
    payments_template = "accounts/payments.html"
    client_accounts_template = "accounts/client_accounts.html"
    client_account_detail_template = "accounts/client_account_detail.html"
    payroll_template = "accounts/payroll.html"
    employee_payroll_detail_template = "accounts/employee_payroll_detail.html"
    register_payroll_template = "accounts/register_payroll.html"
    payroll_receipt_template = "accounts/payroll_receipt.html"
    roles_permissions_template = "accounts/roles_permissions.html"
    roles_module_detail_template = "accounts/roles_module_detail.html"
    roles_activity_permission_template = "accounts/roles_activity_permission.html"
    performance_compliance_template = "accounts/performance_compliance.html"
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

        # Enforce role and employee activity locks (not on permission UI).
        denied = self._redirect_if_activity_locked(
            request, user, resolved, action="view"
        )
        if denied is not None:
            return denied

        context = workspace_context(
            user,
            request=request,
            page_title=resolved["page_title"],
            page_trail=resolved["trail"],
            active_page=resolved["leaf"],
        )

        if resolved.get("is_roles_activity_permission"):
            context.update(self._roles_activity_permission_context(user, resolved))
            response = render(
                request, self.roles_activity_permission_template, context
            )
        elif resolved.get("is_roles_module_detail"):
            context.update(self._roles_module_detail_context(user, resolved))
            response = render(request, self.roles_module_detail_template, context)
        elif (
            resolved["leaf"] == "system-settings"
            and user.role == Employee.Role.IT_SUPPORT
        ):
            from .system_analytics import build_system_analytics

            context.update(
                build_system_analytics(request.GET.get("range", "24h"))
            )
            response = render(request, self.system_settings_template, context)
        elif resolved["is_settings"]:
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
            generated_draft = request.session.pop("news_blog_draft", None)
            context.update(
                self._my_blog_form_context(
                    user,
                    initial=(
                        generated_draft.get("initial")
                        if generated_draft
                        else None
                    ),
                    news_source=(
                        generated_draft.get("source")
                        if generated_draft
                        else None
                    ),
                )
            )
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
        elif resolved.get("is_communication_settings"):
            context.update(self._communication_settings_context(form=None))
            response = render(
                request, self.communication_settings_template, context
            )
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
            context.update(self._company_blogs_context(user, request=request))
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
        elif resolved.get("is_latest_news"):
            context.update(
                self._latest_news_context(user=user, request=request)
            )
            response = render(request, self.latest_news_template, context)
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
            generate_context = self._generate_invoice_context(
                user, resolved, request=request
            )
            context.update(generate_context)
            if (
                generate_context.get("selected_client")
                and "client-accounts" in resolved["trail"]
            ):
                context["page_nav_items"] = client_account_page_nav_items(
                    user,
                    resolved["trail"],
                    client_pk=generate_context["selected_client"].pk,
                    active_slug="generate-invoice",
                )
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
        elif resolved["leaf"] == "client-accounts":
            client_context = self._client_accounts_context(
                request, user=user, resolved=resolved
            )
            context.update(client_context)
            if client_context.get("selected_client"):
                context["page_nav_items"] = client_account_page_nav_items(
                    user,
                    resolved["trail"],
                    client_pk=client_context["selected_client"].pk,
                )
            template = (
                self.client_account_detail_template
                if client_context.get("account_detail")
                else self.client_accounts_template
            )
            response = render(request, template, context)
        elif resolved["leaf"] == "payroll":
            payroll_context = self._payroll_context(request, user, resolved)
            context.update(payroll_context)
            template = (
                self.employee_payroll_detail_template
                if payroll_context.get("employee_detail")
                else self.payroll_template
            )
            response = render(request, template, context)
        elif resolved["leaf"] == "register-payroll":
            context.update(self._register_payroll_context(user, resolved))
            response = render(request, self.register_payroll_template, context)
        elif resolved["leaf"] == "payroll-receipt":
            context.update(self._payroll_receipt_context(request, user, resolved))
            response = render(request, self.payroll_receipt_template, context)
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
        elif resolved["leaf"] == "performance-compliance":
            context.update(self._performance_compliance_context())
            response = render(request, self.performance_compliance_template, context)
        elif resolved["leaf"] == "roles-permissions":
            roles_trail = list(resolved["trail"])
            context["system_modules"] = [
                {
                    "label": label,
                    "slug": slug,
                    "icon": icon,
                    "url": user.workspace_url(*roles_trail, slug),
                    "hint": system_module_hint(slug),
                }
                for label, slug, icon in DASHBOARD_PAGE_LINKS
            ]
            response = render(request, self.roles_permissions_template, context)
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
        elif resolved["leaf"] == "client-profile":
            context["clients"] = Client.objects.filter(
                status__in=[
                    Client.Status.ACTIVE,
                    Client.Status.SUSPENDED,
                ]
            ).order_by("status", "company_name", "first_name", "last_name", "email")
            context["client_count"] = context["clients"].count()
            response = render(request, self.client_profile_template, context)
        elif resolved["leaf"] == "litigation-matters":
            cases = list(
                LitigationCase.objects.filter(
                    status=LitigationCase.Status.ACTIVE
                )
                .select_related("client", "assigned_to", "registered_by")
                .prefetch_related("parties")
                .order_by("-filing_date", "-created_at")
            )
            preferred_group = resolve_matter_group_by(
                request,
                session_key="litigation_matters_group_by",
                allowed={"court", "client"},
                default="court",
            )
            group_by, case_groups = group_litigation_cases(cases, preferred_group)
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
            preferred_group = resolve_matter_group_by(
                request,
                session_key="non_litigation_matters_group_by",
                allowed={"category", "client"},
                default="category",
            )
            group_by, matter_groups = group_non_litigation_matters(
                matters, preferred_group
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

    def _redirect_if_activity_locked(self, request, user, resolved, *, action="view"):
        if (
            "roles-permissions" in resolved["trail"]
            or resolved["leaf"] in SYSTEM_MODULE_SLUGS
            or resolved["leaf"] == "dashboard"
        ):
            return None

        module_slug = module_slug_for_trail(resolved["trail"])
        if not module_slug:
            return None

        activity_slug = resolved["leaf"]
        if workspace_activity_action_permitted(
            user, module_slug, activity_slug, action
        ):
            return None

        title, message = workspace_action_denial_copy(
            user, module_slug, activity_slug, action
        )
        set_workspace_access_denied_modal(
            request,
            title=title,
            message=message,
        )
        return redirect(user.dashboard_url)

    def post(self, request, role, pages="dashboard"):
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

        if resolved.get("is_roles_activity_permission"):
            return self._post_roles_activity_permission(request, user, resolved)

        denied = self._redirect_if_activity_locked(
            request,
            user,
            resolved,
            action=resolve_workspace_post_action(resolved["leaf"], request),
        )
        if denied is not None:
            return denied

        if resolved["leaf"] not in {
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
            "communication-settings",
            "register-case",
            "register-new-matter",
            "register-client",
            "register-employee",
            "generate-invoice",
            "register-payroll",
            "latest-news",
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

        if resolved["leaf"] == "communication-settings":
            return self._post_communication_settings(request, user, resolved)

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

        if resolved["leaf"] == "payroll":
            return self._post_payroll(request, user, resolved)

        if resolved["leaf"] == "register-payroll":
            return self._post_register_payroll(request, user, resolved)

        if resolved["leaf"] == "latest-news":
            return self._post_latest_news(request, user, resolved)

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
    def _roles_module_detail_context(user, resolved):
        leaf = resolved["leaf"]
        trail = list(resolved["trail"])
        module_meta = next(
            (
                {"label": label, "slug": slug, "icon": icon}
                for label, slug, icon in DASHBOARD_PAGE_LINKS
                if slug == leaf
            ),
            {
                "label": PAGE_TITLES.get(leaf, leaf.replace("-", " ").title()),
                "slug": leaf,
                "icon": "",
            },
        )
        module_activities = []
        roles_root = trail[: trail.index("roles-permissions") + 1]
        for activity in collect_module_activities(leaf):
            item = dict(activity)
            item["url"] = roles_activity_permission_url(
                user, roles_root, leaf, activity
            )
            item["open_url"] = module_activity_url(user, leaf, activity)
            module_activities.append(item)
        return {
            "page_title": f"{module_meta['label']} — Roles & Permissions",
            "module": {
                **module_meta,
                "hint": system_module_hint(leaf),
                "open_url": user.workspace_url("dashboard", leaf),
            },
            "module_activities": module_activities,
            "activity_count": len(module_activities),
            "roles_permissions_url": user.workspace_url(*roles_root),
        }

    @staticmethod
    def _roles_activity_permission_context(user, resolved):
        trail = list(resolved["trail"])
        module_slug = resolved.get("roles_module_slug") or ""
        activity_slug = resolved["leaf"]
        roles_idx = trail.index("roles-permissions")
        roles_root = trail[: roles_idx + 1]
        module_root = trail[: roles_idx + 2]

        module_meta = next(
            (
                {"label": label, "slug": slug, "icon": icon}
                for label, slug, icon in DASHBOARD_PAGE_LINKS
                if slug == module_slug
            ),
            {
                "label": PAGE_TITLES.get(
                    module_slug, module_slug.replace("-", " ").title()
                ),
                "slug": module_slug,
                "icon": "",
            },
        )
        activity_meta = next(
            (
                activity
                for activity in collect_module_activities(module_slug)
                if activity["slug"] == activity_slug
            ),
            {
                "label": PAGE_TITLES.get(
                    activity_slug, activity_slug.replace("-", " ").title()
                ),
                "slug": activity_slug,
                "icon": "",
                "path": PAGE_TITLES.get(
                    activity_slug, activity_slug.replace("-", " ").title()
                ),
                "path_slugs": trail[roles_idx + 2 :],
                "linkable": True,
            },
        )
        open_url = module_activity_url(user, module_slug, activity_meta)
        activity_actions = activity_permission_actions(activity_slug)

        locked_roles = {
            row.role
            for row in RoleActivityPermission.objects.filter(
                module_slug=module_slug,
                activity_slug=activity_slug,
                is_allowed=False,
            ).only("role")
        }

        employees = list(
            Employee.objects.filter(
                status__in=[
                    Employee.Status.ACTIVE,
                    Employee.Status.SUSPENDED,
                    Employee.Status.PENDING_APPROVAL,
                    Employee.Status.PENDING_ONBOARDING,
                ]
            ).order_by("role", "first_name", "last_name", "login_code")
        )
        employees_by_role = {role: [] for role, _label in Employee.Role.choices}
        for employee in employees:
            employees_by_role.setdefault(employee.role, []).append(employee)

        employee_ids = [employee.pk for employee in employees]
        employee_action_rows = {
            (row.employee_id, row.action): row.is_allowed
            for row in EmployeeActivityPermission.objects.filter(
                module_slug=module_slug,
                activity_slug=activity_slug,
                employee_id__in=employee_ids,
            ).only("employee_id", "action", "is_allowed")
        }

        role_groups = []
        allowed_count = 0
        locked_count = 0
        total_employees = 0
        for role_value, role_label in Employee.Role.choices:
            members = employees_by_role.get(role_value, [])
            is_allowed = role_value not in locked_roles
            if is_allowed:
                allowed_count += 1
            else:
                locked_count += 1
            total_employees += len(members)

            member_rows = []
            for employee in members:
                actions = []
                for action in activity_actions:
                    actions.append(
                        {
                            **action,
                            "is_allowed": employee_action_rows.get(
                                (employee.pk, action["slug"]), True
                            ),
                        }
                    )
                member_rows.append(
                    {
                        "employee": employee,
                        "actions": actions,
                    }
                )

            role_groups.append(
                {
                    "role": role_value,
                    "label": role_label,
                    "is_allowed": is_allowed,
                    "members": member_rows,
                    "employee_count": len(members),
                }
            )

        return {
            "page_title": f"{activity_meta['label']} — Access",
            "module": module_meta,
            "activity": activity_meta,
            "activity_open_url": open_url,
            "activity_actions": activity_actions,
            "role_groups": role_groups,
            "allowed_role_count": allowed_count,
            "locked_role_count": locked_count,
            "total_employee_count": total_employees,
            "module_url": user.workspace_url(*module_root),
            "roles_permissions_url": user.workspace_url(*roles_root),
        }

    def _post_roles_activity_permission(self, request, user, resolved):
        module_slug = resolved.get("roles_module_slug") or ""
        activity_slug = resolved["leaf"]
        permission_action = (request.POST.get("permission_action") or "role").strip()

        if permission_action == "employee_action":
            return self._post_employee_activity_action(
                request, user, resolved, module_slug, activity_slug
            )

        role = (request.POST.get("role") or "").strip()
        valid_roles = {value for value, _label in Employee.Role.choices}
        if role not in valid_roles or not module_slug:
            messages.error(request, "Invalid role permission update.")
            return redirect(user.workspace_url(*resolved["trail"]))

        is_allowed = request.POST.get("is_allowed") == "1"
        set_role_activity_permission(
            role=role,
            module_slug=module_slug,
            activity_slug=activity_slug,
            is_allowed=is_allowed,
            updated_by=user,
        )
        role_label = dict(Employee.Role.choices).get(role, role)
        if is_allowed:
            messages.success(
                request,
                f"{role_label} can now access this activity.",
            )
        else:
            messages.success(
                request,
                f"{role_label} is locked from this activity.",
            )
        return redirect(user.workspace_url(*resolved["trail"]))

    def _post_employee_activity_action(
        self, request, user, resolved, module_slug, activity_slug
    ):
        try:
            employee_id = int(request.POST.get("employee_id", ""))
        except (TypeError, ValueError):
            messages.error(request, "Invalid employee permission update.")
            return redirect(user.workspace_url(*resolved["trail"]))

        action = (request.POST.get("action") or "").strip()
        valid_actions = {
            item["slug"] for item in activity_permission_actions(activity_slug)
        }
        if action not in valid_actions:
            messages.error(request, "Invalid action permission update.")
            return redirect(user.workspace_url(*resolved["trail"]))

        employee = Employee.objects.filter(pk=employee_id).first()
        if employee is None:
            messages.error(request, "Employee not found.")
            return redirect(user.workspace_url(*resolved["trail"]))

        if not role_activity_is_allowed(
            employee.role, module_slug, activity_slug
        ):
            messages.error(
                request,
                "Enable this role for the activity before setting employee actions.",
            )
            return redirect(user.workspace_url(*resolved["trail"]))

        is_allowed = request.POST.get("is_allowed") == "1"
        set_employee_activity_permission(
            employee_id=employee_id,
            module_slug=module_slug,
            activity_slug=activity_slug,
            action=action,
            is_allowed=is_allowed,
            updated_by=user,
        )
        action_label = next(
            (
                item["label"]
                for item in activity_permission_actions(activity_slug)
                if item["slug"] == action
            ),
            action.replace("-", " ").title(),
        )
        employee_name = employee.get_full_name() or employee.login_code
        if is_allowed:
            messages.success(
                request,
                f"{employee_name} can now {action_label.lower()} in this activity.",
            )
        else:
            messages.success(
                request,
                f"{employee_name} is locked from {action_label.lower()}.",
            )
        return redirect(user.workspace_url(*resolved["trail"]))

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
    def _my_blog_form_context(
        user, *, form=None, post=None, initial=None, news_source=None
    ):
        if form is not None:
            blog_form = form
        elif post is not None:
            blog_form = EmployeeBlogForm(instance=post)
        else:
            blog_form = EmployeeBlogForm(initial=initial)

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
        elif initial:
            seo = EmployeeBlogPost(
                title=initial.get("title", ""),
                body=initial.get("body", ""),
                excerpt=initial.get("excerpt", ""),
                meta_title=initial.get("meta_title", ""),
                meta_description=initial.get("meta_description", ""),
                focus_keyword=initial.get("focus_keyword", ""),
                tags=initial.get("tags", ""),
                slug=initial.get("slug", ""),
            ).seo_checklist()
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
            "news_source": news_source,
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
        from .contact_verification import CHANNEL_SPECS, LABEL_BY_STATUS, TONE_BY_STATUS

        company = FirmCompanyInformation.get_solo()
        # Placeholders so the page paints immediately; JS runs live verification.
        pending_channels = []
        for spec in CHANNEL_SPECS:
            if spec["kind"] not in {"email", "phone", "url"}:
                continue
            value = (getattr(company, spec["key"], "") or "").strip()
            status = "checking" if value else "not_set"
            pending_channels.append(
                {
                    "key": spec["key"],
                    "label": spec["label"],
                    "kind": spec["kind"],
                    "value": value,
                    "status": status,
                    "tone": TONE_BY_STATUS.get(status, "suspended"),
                    "status_label": LABEL_BY_STATUS.get(
                        status, status.replace("_", " ").title()
                    ),
                    "detail": (
                        "Verifying live connection…"
                        if value
                        else f"{spec['label']} is not set."
                    ),
                    "required": bool(spec.get("required")),
                    "href": "",
                }
            )
        return {
            "company_information": company,
            "form": form or CompanyContactsForm(instance=company),
            "contact_verify_url": reverse("accounts:company_contacts_verify"),
            "contact_connections": {
                "overall_status": "checking",
                "overall_tone": "partial",
                "overall_label": "Verifying connections…",
                "overall_detail": "Checking email, phone, website, and social profiles.",
                "connected_count": 0,
                "problem_count": 0,
                "not_set_count": 0,
                "channel_count": len(pending_channels),
                "connection_channels": pending_channels,
                "by_key": {c["key"]: c for c in pending_channels},
            },
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
        firm_qs = EmployeeBlogPost.objects.exclude(
            status=EmployeeBlogPost.Status.DRAFT
        ).select_related("author", "approved_by")
        submitted_posts = list(
            firm_qs.filter(status=EmployeeBlogPost.Status.SUBMITTED).order_by(
                "-submitted_at", "-updated_at", "-created_at"
            )
        )
        published_posts = list(
            firm_qs.filter(status=EmployeeBlogPost.Status.PUBLISHED).order_by(
                "-published_at", "-updated_at", "-created_at"
            )
        )
        pending_count = len(submitted_posts)
        published_count = len(published_posts)
        return {
            "submitted_blog_posts": submitted_posts,
            "published_blog_posts": published_posts,
            "firm_blog_count": pending_count + published_count,
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
            "latest_news_url": user.workspace_url(
                "dashboard", "research-blogs", "latest-news"
            ),
        }

    @staticmethod
    def _latest_news_context(*, user=None, request=None, form=None, result=None):
        job = None
        selected_watch = None
        if result is None and user is not None and request is not None:
            job_id = request.GET.get("job")
            if job_id and str(job_id).isdigit():
                job = NewsSearchJob.objects.filter(
                    pk=job_id,
                    requested_by=user,
                    status=NewsSearchJob.Status.SUCCEEDED,
                ).first()
                if job:
                    result = job.result
            watch_id = request.GET.get("watch")
            if result is None and watch_id and str(watch_id).isdigit():
                selected_watch = NewsWatch.objects.filter(
                    pk=watch_id,
                    requested_by=user,
                ).first()
                if selected_watch:
                    Notification.objects.filter(
                        recipient=user,
                        is_read=False,
                        source_key__startswith=f"news_watch:{selected_watch.pk}:",
                    ).update(is_read=True, read_at=timezone.now())
                    items = list(selected_watch.articles.all()[:30])
                    article_id = request.GET.get("article")
                    if article_id and str(article_id).isdigit():
                        items.sort(
                            key=lambda item: item.pk != int(article_id)
                        )
                    result = {
                        "country_name": country_name(
                            selected_watch.filters.get("country_code")
                        ),
                        "industry": selected_watch.filters.get("industry", ""),
                        "requested_details": selected_watch.name,
                        "period": "Daily watch",
                        "query": selected_watch.name,
                        "providers": ["Daily News Watch"],
                        "retrieved_at": (
                            selected_watch.last_checked_at.strftime(
                                "%d %b %Y, %H:%M"
                            )
                            if selected_watch.last_checked_at
                            else ""
                        ),
                        "enriched_count": sum(
                            bool(item.description) for item in items
                        ),
                        "articles": [item.article_data for item in items],
                    }
        watches = (
            list(
                NewsWatch.objects.filter(requested_by=user).order_by(
                    "-is_active", "-created_at"
                )
            )
            if user is not None
            else []
        )
        if user is not None:
            for watch in watches:
                watch.unread_update_count = Notification.objects.filter(
                    recipient=user,
                    is_read=False,
                    source_key__startswith=f"news_watch:{watch.pk}:",
                ).count()

        return {
            "form": form or LatestNewsScrapeForm(),
            "news_result": result,
            "news_job": job,
            "selected_news_watch": selected_watch,
            "news_watches": watches,
        }

    def _post_latest_news(self, request, user, resolved):
        from .news_scraper import NewsScrapeError, search_latest_news

        form = LatestNewsScrapeForm(request.POST)
        result = None
        if form.is_valid():
            try:
                result = search_latest_news(
                    country_code=form.cleaned_data["country"],
                    industry=form.cleaned_data["industry"],
                    requested_details=form.cleaned_data["requested_details"],
                    period=form.cleaned_data["period"],
                    language=form.cleaned_data["language"],
                    sort_by=form.cleaned_data["sort_by"],
                    exact_phrase=form.cleaned_data["exact_phrase"],
                    excluded_words=form.cleaned_data["excluded_words"],
                    source_domain=form.cleaned_data["source_domain"],
                )
            except NewsScrapeError as exc:
                form.add_error(None, str(exc))

        context = workspace_context(
            user,
            request=request,
            page_title=resolved["page_title"],
            page_trail=resolved["trail"],
            active_page=resolved["leaf"],
        )
        context.update(self._latest_news_context(form=form, result=result))
        response = render(request, self.latest_news_template, context)
        return attach_greeting_cookie(response, request)

    @staticmethod
    def _company_blogs_context(user, request=None):
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
        share_intents = pop_share_intents(request) if request is not None else []
        return {
            "pending_blog_posts": pending,
            "published_blog_posts": published,
            "pending_blog_count": len(pending),
            "published_blog_count": len(published),
            "public_blog_list_url": reverse("accounts:blog_list"),
            "blog_share_intents": share_intents,
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
    def _communication_settings_context(*, form=None):
        from .communication_verification import pending_connection_snapshot

        setting = CommunicationSettings.get_solo()
        return {
            "communication_setting": setting,
            "form": form or CommunicationSettingsForm(instance=setting),
            "email_ready": setting.email_ready,
            "sms_ready": setting.sms_ready,
            "whatsapp_ready": setting.whatsapp_ready,
            "communication_verify_url": reverse(
                "accounts:communication_settings_verify"
            ),
            "communication_connections": pending_connection_snapshot(setting),
        }

    def _post_communication_settings(self, request, user, resolved):
        setting = CommunicationSettings.get_solo()
        form = CommunicationSettingsForm(request.POST, instance=setting)
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
            channels = ", ".join(choice.enabled_channels) or "none"
            messages.success(
                request,
                f"Communication settings saved. Enabled channels: {channels}.",
            )
            return redirect(user.workspace_url(*resolved["trail"]))

        context.update(self._communication_settings_context(form=form))
        response = render(
            request, self.communication_settings_template, context
        )
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
        form = StaffRegisterClientForm(request.POST, request.FILES)
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
            "form": form or StaffRegisterClientForm(),
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
    def _client_accounts_context(request, *, user=None, resolved=None):
        active_clients_qs = Client.objects.filter(status=Client.Status.ACTIVE).order_by(
            "company_name", "first_name", "last_name", "email"
        )
        list_url = (
            user.workspace_url(*resolved["trail"])
            if user is not None and resolved is not None
            else "."
        )

        client_param = (request.GET.get("client") or "").strip()
        if client_param.isdigit():
            client = active_clients_qs.filter(pk=int(client_param)).first()
            if client is not None:
                summaries = build_client_account_summaries([client])
                return {
                    "account_detail": summaries[0] if summaries else None,
                    "selected_client": client,
                    "back_url": list_url,
                }

        corporate_clients = list(
            active_clients_qs.filter(client_type=Client.ClientType.CORPORATE)
        )
        individual_clients = list(
            active_clients_qs.filter(client_type=Client.ClientType.INDIVIDUAL)
        )
        return {
            "corporate_clients": corporate_clients,
            "individual_clients": individual_clients,
            "corporate_client_count": len(corporate_clients),
            "individual_client_count": len(individual_clients),
            "active_client_count": active_clients_qs.count(),
            "list_url": list_url,
            "client_search_url": reverse("accounts:workspace_client_search"),
        }

    @staticmethod
    def _payroll_url(user, trail, *, employee_id=None):
        clean = [
            part for part in trail
            if part and part not in ("register-payroll", "payroll-receipt")
        ]
        if not clean or clean[-1] != "payroll":
            clean = extend_page_trail(clean, "payroll")
        url = user.workspace_url(*clean)
        if employee_id:
            url = f"{url}?employee={employee_id}"
        return url

    @classmethod
    def _payroll_context(cls, request, user, resolved):
        from decimal import Decimal

        payroll_base_url = cls._payroll_url(user, resolved["trail"])
        register_payroll_url = user.workspace_url(
            "dashboard",
            "finance-billing",
            "employee-accounts",
            "payroll",
            "register-payroll",
        )
        payroll_receipt_base_url = user.workspace_url(
            "dashboard",
            "finance-billing",
            "employee-accounts",
            "payroll",
            "payroll-receipt",
        )

        employee_param = (request.GET.get("employee") or "").strip()
        if employee_param.isdigit():
            detail = cls._employee_payroll_detail_context(
                int(employee_param),
                user=user,
                resolved=resolved,
                payroll_base_url=payroll_base_url,
                register_payroll_url=register_payroll_url,
                payroll_receipt_base_url=payroll_receipt_base_url,
            )
            if detail is not None:
                return detail

        employees = list(
            Employee.objects.filter(
                status__in=[
                    Employee.Status.ACTIVE,
                    Employee.Status.SUSPENDED,
                    Employee.Status.PENDING_APPROVAL,
                ]
            ).order_by("role", "first_name", "last_name", "login_code")
        )

        employee_rows = []
        total_monthly_salary = Decimal("0.00")
        configured_salary_count = 0
        payroll_run_count = 0

        for employee in employees:
            if employee.monthly_salary is not None:
                total_monthly_salary += employee.monthly_salary
                configured_salary_count += 1

            runs = list(
                employee.payroll_runs.order_by("-pay_period_start", "-registered_at")
            )
            payroll_run_count += len(runs)
            has_unpaid = any(run.status == PayrollRun.Status.REGISTERED for run in runs)

            if not runs:
                payroll_status = "not_registered"
                payroll_status_label = "Not registered"
            elif has_unpaid:
                payroll_status = "registered"
                payroll_status_label = "Awaiting payment"
            else:
                payroll_status = "paid"
                payroll_status_label = "Paid"

            employee_rows.append(
                {
                    "employee": employee,
                    "payroll_status": payroll_status,
                    "payroll_status_label": payroll_status_label,
                    "run_count": len(runs),
                    "detail_url": f"{payroll_base_url}?employee={employee.pk}",
                }
            )

        unregistered_rows = [
            row for row in employee_rows if row["payroll_status"] == "not_registered"
        ]
        registered_rows = [
            row for row in employee_rows if row["payroll_status"] != "not_registered"
        ]

        return {
            "employee_rows": employee_rows,
            "unregistered_rows": unregistered_rows,
            "registered_rows": registered_rows,
            "employee_count": len(employee_rows),
            "configured_salary_count": configured_salary_count,
            "total_monthly_salary": total_monthly_salary,
            "payroll_run_count": payroll_run_count,
            "register_payroll_url": register_payroll_url,
            "payroll_receipt_base_url": payroll_receipt_base_url,
        }

    @staticmethod
    def _employee_payroll_detail_context(
        employee_id,
        *,
        user,
        resolved,
        payroll_base_url,
        register_payroll_url,
        payroll_receipt_base_url,
    ):
        employee = (
            Employee.objects.filter(
                pk=employee_id,
                status__in=[
                    Employee.Status.ACTIVE,
                    Employee.Status.SUSPENDED,
                    Employee.Status.PENDING_APPROVAL,
                ],
            )
            .first()
        )
        if employee is None:
            return None

        payroll_runs = list(
            PayrollRun.objects.filter(employee=employee)
            .prefetch_related("deductions", "payments")
            .order_by("-pay_period_start", "-registered_at")
        )
        payments = list(
            PayrollPayment.objects.filter(payroll_run__employee=employee)
            .select_related("payroll_run", "recorded_by")
            .order_by("-paid_at")
        )

        return {
            "employee_detail": employee,
            "selected_employee": employee,
            "page_title": f"{employee.get_full_name() or employee.login_code} — Payroll account",
            "payroll_runs": payroll_runs,
            "payments": payments,
            "payroll_url": payroll_base_url,
            "back_url": payroll_base_url,
            "register_payroll_url": register_payroll_url,
            "payroll_receipt_base_url": payroll_receipt_base_url,
        }

    def _post_payroll(self, request, user, resolved):
        from decimal import Decimal, InvalidOperation

        action = (request.POST.get("action") or "").strip()
        return_employee_id = (request.POST.get("return_employee_id") or "").strip()

        def payroll_return_url():
            if return_employee_id.isdigit():
                return self._payroll_url(
                    user, resolved["trail"], employee_id=int(return_employee_id)
                )
            return self._payroll_url(user, resolved["trail"])

        if action != "pay-payroll":
            return redirect(payroll_return_url())

        payroll_run_id = request.POST.get("payroll_run_id")
        payroll_run = get_object_or_404(
            PayrollRun.objects.select_related("employee"), pk=payroll_run_id
        )

        if payroll_run.status == PayrollRun.Status.PAID:
            messages.info(
                request,
                f"Payroll for {payroll_run.employee.get_full_name()} is already paid.",
            )
            return redirect(payroll_return_url())

        try:
            amount_paid = Decimal(request.POST.get("amount_paid", "0")).quantize(
                Decimal("0.01")
            )
        except (InvalidOperation, ValueError):
            amount_paid = Decimal("0")

        reference_code = (request.POST.get("reference_code") or "").strip()

        if amount_paid <= 0:
            messages.error(request, "Enter a valid payment amount.")
            return redirect(payroll_return_url())
        if not reference_code:
            messages.error(request, "Enter a payment reference code.")
            return redirect(payroll_return_url())

        payment = PayrollPayment.objects.create(
            receipt_number=PayrollPayment.next_receipt_number(),
            payroll_run=payroll_run,
            amount_paid=amount_paid,
            reference_code=reference_code,
            recorded_by=user,
        )

        payroll_run.status = PayrollRun.Status.PAID
        payroll_run.save(update_fields=["status", "updated_at"])

        receipt_url = user.workspace_url(
            "dashboard",
            "finance-billing",
            "employee-accounts",
            "payroll",
            "payroll-receipt",
        ) + f"?payment={payment.pk}"

        messages.success(
            request,
            f"Payment of KES {amount_paid:,.2f} recorded for "
            f"{payroll_run.employee.get_full_name()}. "
            f'<a href="{receipt_url}">View receipt</a>',
        )
        return redirect(receipt_url)

    def _payroll_receipt_context(self, request, user, resolved):
        payment_id = request.GET.get("payment")
        payment = get_object_or_404(
            PayrollPayment.objects.select_related(
                "payroll_run", "payroll_run__employee", "recorded_by"
            ),
            pk=payment_id,
        )
        firm = FirmCompanyInformation.get_solo()
        employee = payment.payroll_run.employee
        return {
            "payment": payment,
            "run": payment.payroll_run,
            "employee": employee,
            "firm": firm,
            "payroll_url": self._payroll_url(
                user, resolved["trail"], employee_id=employee.pk
            ),
        }

    @classmethod
    def _register_payroll_context(cls, user, resolved, form=None):
        import json

        from .forms import default_pay_period
        from .payroll_calc import payroll_rate_defaults_json

        period_start, period_end, frequency = default_pay_period()
        if form is not None:
            period_start, period_end, frequency = form._resolved_pay_period()

        employees = employees_available_for_payroll(
            period_start, period_end, frequency
        )
        employee_choices = [
            {
                "id": employee.pk,
                "label": employee.get_full_name() or employee.login_code,
                "salary": (
                    str(employee.monthly_salary)
                    if employee.monthly_salary is not None
                    else ""
                ),
            }
            for employee in Employee.objects.filter(
                status__in=[
                    Employee.Status.ACTIVE,
                    Employee.Status.SUSPENDED,
                    Employee.Status.PENDING_APPROVAL,
                ]
            ).order_by("first_name", "last_name", "login_code")
        ]
        registered_map = {}
        for row in PayrollRun.objects.values(
            "pay_period_start", "pay_period_end", "pay_frequency", "employee_id"
        ):
            key = (
                f"{row['pay_period_start'].isoformat()}|"
                f"{row['pay_period_end'].isoformat()}|"
                f"{row['pay_frequency']}"
            )
            registered_map.setdefault(key, []).append(row["employee_id"])

        return {
            "form": form or RegisterPayrollForm(),
            "payroll_url": cls._payroll_url(user, resolved["trail"]),
            "employee_choices_json": json.dumps(employee_choices),
            "registered_payroll_map_json": json.dumps(registered_map),
            "payroll_rate_defaults_json": json.dumps(payroll_rate_defaults_json()),
            "no_eligible_employees": not employees.exists(),
        }

    def _post_register_payroll(self, request, user, resolved):
        form = RegisterPayrollForm(request.POST)
        context = workspace_context(
            user,
            request=request,
            page_title=resolved["page_title"],
            page_trail=resolved["trail"],
            active_page=resolved["leaf"],
        )

        if form.is_valid():
            payroll_run = form.save(commit=False)
            employee = payroll_run.employee
            payroll_run.payment_method = employee.payment_method or ""
            payroll_run.payment_method_label = (
                employee.get_payment_method_display()
                if employee.payment_method
                else ""
            )
            payroll_run.payout_destination = employee.payroll_payout_destination()
            payroll_run.registered_by = user
            payroll_run.save()
            payroll_run.sync_deduction_lines()
            messages.success(
                request,
                f"Payroll registered for {employee.get_full_name()} "
                f"(net KES {payroll_run.net_pay:,.2f}).",
            )
            return redirect(self._payroll_url(user, resolved["trail"]))

        context.update(self._register_payroll_context(user, resolved, form=form))
        response = render(request, self.register_payroll_template, context)
        return attach_greeting_cookie(response, request)

    @staticmethod
    def _invoicing_url(user, trail):
        clean = [part for part in trail if part and part != "generate-invoice"]
        if not clean or clean[-1] != "invoicing":
            clean = extend_page_trail(clean, "invoicing")
        return user.workspace_url(*clean)

    @classmethod
    def _generate_invoice_context(cls, user, resolved, request=None, form=None):
        client = None
        client_param = ""
        if request is not None:
            client_param = (request.GET.get("client") or request.POST.get("client") or "").strip()
        if client_param.isdigit():
            client = Client.objects.filter(
                pk=int(client_param),
                status=Client.Status.ACTIVE,
            ).first()

        is_client_account_flow = "client-accounts" in resolved["trail"]

        if form is None:
            initial = {}
            if client:
                initial["client"] = client.pk
            form = GenerateInvoiceForm(initial=initial)
            if client and is_client_account_flow:
                form.fields["client"].widget = forms.HiddenInput()

        if is_client_account_flow and client:
            account_trail = [
                part for part in resolved["trail"] if part != "generate-invoice"
            ]
            back_url = f"{user.workspace_url(*account_trail)}?client={client.pk}"
        else:
            back_url = cls._invoicing_url(user, resolved["trail"])

        return {
            "form": form,
            "invoicing_url": back_url,
            "cancel_url": back_url,
            "selected_client": client,
            "client_locked": bool(client and is_client_account_flow),
            "is_client_account_invoice": is_client_account_flow,
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
        generate_context = self._generate_invoice_context(
            user, resolved, request=request, form=form
        )
        if (
            generate_context.get("selected_client")
            and "client-accounts" in resolved["trail"]
        ):
            context["page_nav_items"] = client_account_page_nav_items(
                user,
                resolved["trail"],
                client_pk=generate_context["selected_client"].pk,
                active_slug="generate-invoice",
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
            if "client-accounts" in resolved["trail"]:
                account_trail = [
                    part for part in resolved["trail"] if part != "generate-invoice"
                ]
                return redirect(
                    f"{user.workspace_url(*account_trail)}?client={invoice.client_id}"
                )
            return redirect(self._invoicing_url(user, resolved["trail"]))

        context.update(generate_context)
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
    def _performance_compliance_context():
        employees = list(
            annotate_employee_performance_summaries(
                Employee.objects.filter(
                    status__in=[
                        Employee.Status.ACTIVE,
                        Employee.Status.SUSPENDED,
                    ]
                )
            ).order_by("status", "first_name", "last_name", "login_code")
        )
        session_summaries = batch_employee_session_summaries(
            [employee.pk for employee in employees],
            days=30,
        )
        for employee in employees:
            metrics = employee_summary_metrics(employee)
            employee.tasks_total = metrics["tasks_total"]
            employee.tasks_done = metrics["tasks_done"]
            employee.completion_rate = metrics["completion_rate"]
            employee.active_workload = metrics["active_workload"]
            employee.overdue_tasks = metrics["overdue_tasks"]
            session_summary = session_summaries.get(employee.pk, {})
            employee.average_login_time = session_summary.get(
                "average_login_time", "—"
            )
            employee.is_online = session_summary.get("is_online", False)
            employee.working_sessions_count = session_summary.get(
                "working_sessions_count", 0
            )
            employee.active_session_duration = session_summary.get(
                "active_session_duration", "—"
            )
        return {
            "employees": employees,
            "employee_count": len(employees),
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
            entity_url = reverse(
                "accounts:view_litigation_case",
                kwargs={
                    "role": user.role_slug,
                    "case_id": task.case_id,
                },
            )
            if task.status == CaseTask.Status.ACCEPTED:
                entity_url = f"{entity_url}?task={task.pk}"
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
                    "entity_url": entity_url,
                    "entity_label": "Open case",
                    "complete_url": reverse(
                        "accounts:complete_case_task",
                        kwargs={
                            "role": user.role_slug,
                            "task_id": task.pk,
                        },
                    ),
                }
            )
        for task in matter_tasks:
            entity_url = reverse(
                "accounts:view_non_litigation_matter",
                kwargs={
                    "role": user.role_slug,
                    "matter_id": task.matter_id,
                },
            )
            if task.status == MatterTask.Status.ACCEPTED:
                entity_url = f"{entity_url}?task={task.pk}"
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
                    "entity_url": entity_url,
                    "entity_label": "Open matter",
                    "complete_url": reverse(
                        "accounts:complete_matter_task",
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
        open_view_modal = False
        if highlight_kind and highlight_id:
            for item in tasks:
                if (
                    item["kind"] == highlight_kind
                    and item["task"].pk == highlight_id
                    and item["task"].status == CaseTask.Status.ACCEPTED
                ):
                    open_view_modal = True
                    break

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
            "open_view_modal": open_view_modal,
            "accept_target": None,
            "reject_target": None,
        }

    @staticmethod
    def _calendar_context(user, request):
        """Month calendar: tasks for most roles; cases/matters for managing partner."""
        if user.role == Employee.Role.MANAGING_PARTNER:
            return RoleWorkspaceView._managing_partner_calendar_context(
                user, request
            )

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
            extras = _court_appearance_calendar_extras(attendance)
            by_day.setdefault(appearance_date.day, []).append(
                {
                    "kind": "court",
                    "task": None,
                    "due_date": appearance_date,
                    "status": "active",
                    "status_label": extras["status_label"],
                    "subject": f"{activity} — {attendance.case}",
                    "subject_meta": attendance.case.client.get_full_name(),
                    "virtual_link": extras["virtual_link"],
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

        kind_order = {
            "court": 0,
            "matter_attendance": 1,
            "case": 2,
            "matter": 3,
            "filing": 4,
            "opened": 5,
        }
        upcoming_by_kind = sorted(
            upcoming,
            key=lambda event: (
                kind_order.get(event.get("kind"), 99),
                event.get("due_date") or date.max,
                event.get("subject") or "",
            ),
        )

        return {
            "calendar_weeks": calendar_weeks,
            "calendar_year": year,
            "calendar_month": month,
            "calendar_month_label": month_label,
            "calendar_today": today,
            "calendar_due_count": due_count,
            "calendar_upcoming": upcoming,
            "calendar_upcoming_by_kind": upcoming_by_kind,
            "calendar_prev_url": f"{base_url}?year={prev_year}&month={prev_month}",
            "calendar_next_url": f"{base_url}?year={next_year}&month={next_month}",
            "calendar_today_url": (
                f"{base_url}?year={today.year}&month={today.month}"
            ),
            "weekday_labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            "calendar_lead": (
                "Due dates for tasks assigned to you, plus next court "
                "appearances on your cases."
            ),
            "calendar_list_hint": "Your assigned tasks and court appearances",
            "calendar_empty_copy": (
                "Task due dates and next court appearances on your cases "
                "will appear here."
            ),
            "calendar_shows_cases_matters": False,
        }

    @staticmethod
    def _managing_partner_calendar_context(user, request):
        """Firm-wide upcoming cases and matters (no tasks) for managing partner."""
        today, year, month, month_start, month_end = _calendar_month_from_request(
            request
        )
        role = user.role_slug
        by_day: dict[int, list] = {}

        active_cases = LitigationCase.objects.filter(
            status=LitigationCase.Status.ACTIVE
        ).select_related("client", "assigned_to")
        case_ids = list(active_cases.values_list("pk", flat=True))

        for case in active_cases.filter(
            filing_date__gte=month_start,
            filing_date__lte=month_end,
        ):
            assignee = (
                case.assigned_to.get_full_name()
                if case.assigned_to_id
                else "Unassigned"
            )
            _append_calendar_event(
                by_day,
                case.filing_date,
                {
                    "kind": "filing",
                    "due_date": case.filing_date,
                    "status": "active",
                    "status_label": "Filing date",
                    "subject": f"Filed — {case}",
                    "subject_meta": f"{case.client.get_full_name()} · {assignee}",
                    "url": reverse(
                        "accounts:view_litigation_case",
                        kwargs={"role": role, "case_id": case.pk},
                    ),
                },
            )

        court_appearances = (
            CourtAttendance.objects.filter(
                case_id__in=case_ids,
                next_court_date__gte=month_start,
                next_court_date__lte=month_end,
            )
            .select_related("case", "case__client", "case__assigned_to")
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
            assignee = (
                attendance.case.assigned_to.get_full_name()
                if attendance.case.assigned_to_id
                else "Unassigned"
            )
            extras = _court_appearance_calendar_extras(attendance)
            _append_calendar_event(
                by_day,
                appearance_date,
                {
                    "kind": "court",
                    "due_date": appearance_date,
                    "status": "active",
                    "status_label": extras["status_label"],
                    "subject": f"{activity} — {attendance.case}",
                    "subject_meta": (
                        f"{attendance.case.client.get_full_name()} · {assignee}"
                    ),
                    "virtual_link": extras["virtual_link"],
                    "url": reverse(
                        "accounts:view_litigation_case",
                        kwargs={
                            "role": role,
                            "case_id": attendance.case_id,
                        },
                    ),
                },
            )

        active_matters = NonLitigationMatter.objects.filter(
            status=NonLitigationMatter.Status.ACTIVE
        ).select_related("client", "assigned_to")
        matter_ids = list(active_matters.values_list("pk", flat=True))

        for matter in active_matters.filter(
            date_opened__gte=month_start,
            date_opened__lte=month_end,
        ):
            assignee = (
                matter.assigned_to.get_full_name()
                if matter.assigned_to_id
                else "Unassigned"
            )
            _append_calendar_event(
                by_day,
                matter.date_opened,
                {
                    "kind": "opened",
                    "due_date": matter.date_opened,
                    "status": "active",
                    "status_label": "Date opened",
                    "subject": f"Opened — {matter.matter_title}",
                    "subject_meta": (
                        f"{matter.client.get_full_name()} · {assignee}"
                    ),
                    "url": reverse(
                        "accounts:view_non_litigation_matter",
                        kwargs={"role": role, "matter_id": matter.pk},
                    ),
                },
            )

        matter_appearances = (
            MatterAttendance.objects.filter(
                matter_id__in=matter_ids,
                next_attendance_date__gte=month_start,
                next_attendance_date__lte=month_end,
            )
            .select_related("matter", "matter__client", "matter__assigned_to")
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
            assignee = (
                attendance.matter.assigned_to.get_full_name()
                if attendance.matter.assigned_to_id
                else "Unassigned"
            )
            client_flag = ""
            if attendance.next_client_attendance:
                client_flag = (
                    f" · {attendance.get_next_client_attendance_display()}"
                )
            _append_calendar_event(
                by_day,
                appearance_date,
                {
                    "kind": "matter_attendance",
                    "due_date": appearance_date,
                    "status": "active",
                    "status_label": f"Matter date{client_flag}",
                    "subject": f"{activity} — {attendance.matter.matter_title}",
                    "subject_meta": (
                        f"{attendance.matter.client.get_full_name()} · {assignee}"
                    ),
                    "url": reverse(
                        "accounts:view_non_litigation_matter",
                        kwargs={
                            "role": role,
                            "matter_id": attendance.matter_id,
                        },
                    ),
                },
            )

        base_url = user.workspace_url("dashboard", "calendar")
        payload = _calendar_grid_payload(today, year, month, by_day, base_url)
        payload.update(
            {
                "calendar_lead": (
                    "Upcoming litigation cases and non-litigation matters "
                    "across the firm — filing dates, court dates, and matter "
                    "attendances."
                ),
                "calendar_list_hint": (
                    "Active cases and matters with dates this month"
                ),
                "calendar_empty_copy": (
                    "Filing dates, next court appearances, matter opened dates, "
                    "and next matter attendances will appear here."
                ),
                "calendar_shows_cases_matters": True,
            }
        )
        return payload

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
        from .notifications import ensure_task_outcome_messages

        ensure_task_outcome_messages(user)
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

CLIENT_PROFILE_TRAIL = (
    "dashboard",
    "user-management",
    "client-management",
    "client-profile",
)

CLIENT_MANAGEMENT_TRAIL = (
    "dashboard",
    "user-management",
    "client-management",
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


def _calendar_month_from_request(request):
    """Parse year/month query params for workspace calendars."""
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
    return today, year, month, month_start, month_end


def _calendar_grid_payload(today, year, month, by_day, base_url):
    """Build month grid + navigation URLs from a day→events map."""
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

    month_start = date(year, month, 1)
    month_label = month_start.strftime("%B %Y")
    due_count = sum(len(v) for v in by_day.values())

    upcoming = []
    for day_num in sorted(by_day):
        upcoming.extend(by_day[day_num])

    # Grouped list (by category, then date) for the agenda panel.
    kind_order = {
        "court": 0,
        "matter_attendance": 1,
        "case": 2,
        "matter": 3,
        "filing": 4,
        "opened": 5,
    }
    upcoming_by_kind = sorted(
        upcoming,
        key=lambda event: (
            kind_order.get(event.get("kind"), 99),
            event.get("due_date") or date.max,
            event.get("subject") or "",
        ),
    )

    return {
        "calendar_weeks": calendar_weeks,
        "calendar_year": year,
        "calendar_month": month,
        "calendar_month_label": month_label,
        "calendar_today": today,
        "calendar_due_count": due_count,
        "calendar_upcoming": upcoming,
        "calendar_upcoming_by_kind": upcoming_by_kind,
        "calendar_prev_url": f"{base_url}?year={prev_year}&month={prev_month}",
        "calendar_next_url": f"{base_url}?year={next_year}&month={next_month}",
        "calendar_today_url": (
            f"{base_url}?year={today.year}&month={today.month}"
        ),
        "weekday_labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    }


def _append_calendar_event(by_day, event_date, event):
    if not event_date:
        return
    by_day.setdefault(event_date.day, []).append(event)


def _court_appearance_calendar_extras(attendance):
    """Status label and virtual link for a next court appearance."""
    client_flag = ""
    if attendance.next_client_attendance:
        client_flag = f" · {attendance.get_next_client_attendance_display()}"
    virtual_link = ""
    if (
        attendance.next_client_attendance
        == CourtAttendance.ClientAttendance.VIRTUAL
    ):
        virtual_link = (attendance.virtual_link or "").strip()
    return {
        "status_label": f"Court date{client_flag}",
        "virtual_link": virtual_link,
    }


def _client_case_calendar_by_day(user, client, month_start, month_end):
    """Dates for all of a client's litigation cases in the month."""
    by_day: dict[int, list] = {}
    role = user.role_slug
    visible_statuses = (
        CaseTask.Status.PENDING,
        CaseTask.Status.ACCEPTED,
        CaseTask.Status.DONE,
    )
    client_cases = LitigationCase.objects.filter(client=client).exclude(
        status=LitigationCase.Status.PENDING_APPROVAL
    )
    case_ids = list(client_cases.values_list("pk", flat=True))

    for case in client_cases.filter(
        filing_date__gte=month_start,
        filing_date__lte=month_end,
    ):
        _append_calendar_event(
            by_day,
            case.filing_date,
            {
                "kind": "filing",
                "due_date": case.filing_date,
                "status": "active",
                "status_label": "Filing date",
                "subject": f"Filed — {case}",
                "subject_meta": client.get_full_name(),
                "url": reverse(
                    "accounts:view_litigation_case",
                    kwargs={"role": role, "case_id": case.pk},
                ),
            },
        )

    attendances = (
        CourtAttendance.objects.filter(case_id__in=case_ids)
        .filter(
            Q(attendance_date__gte=month_start, attendance_date__lte=month_end)
            | Q(
                next_court_date__gte=month_start,
                next_court_date__lte=month_end,
            )
        )
        .select_related("case", "case__client")
        .order_by("attendance_date", "pk")
    )
    for attendance in attendances:
        case_url = reverse(
            "accounts:view_litigation_case",
            kwargs={"role": role, "case_id": attendance.case_id},
        )
        if month_start <= attendance.attendance_date <= month_end:
            activity = attendance.activity_type or "Court attendance"
            _append_calendar_event(
                by_day,
                attendance.attendance_date,
                {
                    "kind": "court",
                    "due_date": attendance.attendance_date,
                    "status": "done",
                    "status_label": "Court attendance",
                    "subject": f"{activity} — {attendance.case}",
                    "subject_meta": client.get_full_name(),
                    "url": case_url,
                },
            )
        if (
            attendance.next_court_date
            and month_start <= attendance.next_court_date <= month_end
        ):
            activity = (
                attendance.next_activity_type
                or attendance.activity_type
                or "Court appearance"
            )
            extras = _court_appearance_calendar_extras(attendance)
            _append_calendar_event(
                by_day,
                attendance.next_court_date,
                {
                    "kind": "court",
                    "due_date": attendance.next_court_date,
                    "status": "active",
                    "status_label": extras["status_label"],
                    "subject": f"{activity} — {attendance.case}",
                    "subject_meta": client.get_full_name(),
                    "virtual_link": extras["virtual_link"],
                    "url": case_url,
                },
            )

    case_tasks = (
        CaseTask.objects.filter(
            case_id__in=case_ids,
            status__in=visible_statuses,
            due_date__gte=month_start,
            due_date__lte=month_end,
        )
        .select_related("case", "case__client")
        .order_by("due_date", "status")
    )
    for task in case_tasks:
        task_url = reverse(
            "accounts:view_case_task",
            kwargs={"role": role, "task_id": task.pk},
        )
        if task.status != CaseTask.Status.ACCEPTED:
            task_url = reverse(
                "accounts:view_litigation_case",
                kwargs={"role": role, "case_id": task.case_id},
            )
        _append_calendar_event(
            by_day,
            task.due_date,
            {
                "kind": "case",
                "due_date": task.due_date,
                "status": task.status,
                "status_label": task.get_status_display(),
                "subject": str(task),
                "subject_meta": f"{task.case} · {client.get_full_name()}",
                "url": task_url,
            },
        )

    return by_day


def _client_matter_calendar_by_day(user, client, month_start, month_end):
    """Dates for all of a client's non-litigation matters in the month."""
    by_day: dict[int, list] = {}
    role = user.role_slug
    visible_statuses = (
        MatterTask.Status.PENDING,
        MatterTask.Status.ACCEPTED,
        MatterTask.Status.DONE,
    )
    client_matters = NonLitigationMatter.objects.filter(client=client).exclude(
        status=NonLitigationMatter.Status.PENDING_APPROVAL
    )
    matter_ids = list(client_matters.values_list("pk", flat=True))

    for matter in client_matters.filter(
        date_opened__gte=month_start,
        date_opened__lte=month_end,
    ):
        _append_calendar_event(
            by_day,
            matter.date_opened,
            {
                "kind": "opened",
                "due_date": matter.date_opened,
                "status": "active",
                "status_label": "Date opened",
                "subject": f"Opened — {matter.matter_title}",
                "subject_meta": client.get_full_name(),
                "url": reverse(
                    "accounts:view_non_litigation_matter",
                    kwargs={"role": role, "matter_id": matter.pk},
                ),
            },
        )

    attendances = (
        MatterAttendance.objects.filter(matter_id__in=matter_ids)
        .filter(
            Q(
                attendance_date__gte=month_start,
                attendance_date__lte=month_end,
            )
            | Q(
                next_attendance_date__gte=month_start,
                next_attendance_date__lte=month_end,
            )
        )
        .select_related("matter", "matter__client")
        .order_by("attendance_date", "pk")
    )
    for attendance in attendances:
        matter_url = reverse(
            "accounts:view_non_litigation_matter",
            kwargs={"role": role, "matter_id": attendance.matter_id},
        )
        if month_start <= attendance.attendance_date <= month_end:
            activity = attendance.activity_type or "Matter attendance"
            _append_calendar_event(
                by_day,
                attendance.attendance_date,
                {
                    "kind": "matter_attendance",
                    "due_date": attendance.attendance_date,
                    "status": "done",
                    "status_label": "Matter attendance",
                    "subject": f"{activity} — {attendance.matter.matter_title}",
                    "subject_meta": client.get_full_name(),
                    "url": matter_url,
                },
            )
        if (
            attendance.next_attendance_date
            and month_start <= attendance.next_attendance_date <= month_end
        ):
            activity = (
                attendance.next_activity_type
                or attendance.activity_type
                or "Matter attendance"
            )
            client_flag = ""
            if attendance.next_client_attendance:
                client_flag = (
                    f" · {attendance.get_next_client_attendance_display()}"
                )
            _append_calendar_event(
                by_day,
                attendance.next_attendance_date,
                {
                    "kind": "matter_attendance",
                    "due_date": attendance.next_attendance_date,
                    "status": "active",
                    "status_label": f"Matter date{client_flag}",
                    "subject": f"{activity} — {attendance.matter.matter_title}",
                    "subject_meta": client.get_full_name(),
                    "url": matter_url,
                },
            )

    matter_tasks = (
        MatterTask.objects.filter(
            matter_id__in=matter_ids,
            status__in=visible_statuses,
            due_date__gte=month_start,
            due_date__lte=month_end,
        )
        .select_related("matter", "matter__client")
        .order_by("due_date", "status")
    )
    for task in matter_tasks:
        task_url = reverse(
            "accounts:view_matter_task",
            kwargs={"role": role, "task_id": task.pk},
        )
        if task.status != MatterTask.Status.ACCEPTED:
            task_url = reverse(
                "accounts:view_non_litigation_matter",
                kwargs={"role": role, "matter_id": task.matter_id},
            )
        _append_calendar_event(
            by_day,
            task.due_date,
            {
                "kind": "matter",
                "due_date": task.due_date,
                "status": task.status,
                "status_label": task.get_status_display(),
                "subject": str(task),
                "subject_meta": (
                    f"{task.matter.matter_title} · {client.get_full_name()}"
                ),
                "url": task_url,
            },
        )

    return by_day


INVOICING_TRAIL = (
    "dashboard",
    "finance-billing",
    "client-accounts",
    "invoicing",
)

PAYMENTS_TRAIL = (
    "dashboard",
    "finance-billing",
    "general-accounts",
    "payments",
)

_MATTER_MODULE = "matter-management"
_USER_MODULE = "user-management"
_FINANCE_MODULE = "finance-billing"
_RESEARCH_MODULE = "research-blogs"


def _employee_workspace_guard(
    request,
    role,
    *,
    module_slug=None,
    activity_slug=None,
    action="view",
    redirect_to=None,
):
    user = request.user
    if user.status != Employee.Status.ACTIVE:
        return None, redirect_for_employee(request, user)
    if Employee.role_from_slug(role) is None or role != user.role_slug:
        return None, redirect(user.dashboard_url)
    if module_slug and activity_slug:
        denied = redirect_if_workspace_action_denied(
            request,
            user,
            module_slug=module_slug,
            activity_slug=activity_slug,
            action=action,
            redirect_to=redirect_to,
        )
        if denied is not None:
            return None, denied
    return user, None


def _guard_perm(request, role, *, module, activity, action, redirect_to=None):
    return _employee_workspace_guard(
        request,
        role,
        module_slug=module,
        activity_slug=activity,
        action=action,
        redirect_to=redirect_to,
    )


def _guard_client_pending(request, role, *, action="view", redirect_to=None):
    return _guard_perm(
        request,
        role,
        module=_USER_MODULE,
        activity="approve-pending-clients",
        action=action,
        redirect_to=redirect_to,
    )


def _guard_client_profile(request, role, *, action="view", redirect_to=None):
    return _guard_perm(
        request,
        role,
        module=_USER_MODULE,
        activity="client-profile",
        action=action,
        redirect_to=redirect_to,
    )


def _guard_employee_pending(request, role, *, action="view", redirect_to=None):
    return _guard_perm(
        request,
        role,
        module=_USER_MODULE,
        activity="onboarding-approvals",
        action=action,
        redirect_to=redirect_to,
    )


def _guard_case_approve(request, role, *, action="view", redirect_to=None):
    return _guard_perm(
        request,
        role,
        module=_MATTER_MODULE,
        activity="approve-registered-cases",
        action=action,
        redirect_to=redirect_to,
    )


def _guard_case_register(request, role, *, action="view", redirect_to=None):
    return _guard_perm(
        request,
        role,
        module=_MATTER_MODULE,
        activity="register-case",
        action=action,
        redirect_to=redirect_to,
    )


def _guard_litigation(request, role, *, action="view", redirect_to=None):
    return _guard_perm(
        request,
        role,
        module=_MATTER_MODULE,
        activity="litigation-matters",
        action=action,
        redirect_to=redirect_to,
    )


def _case_task_access_denied(request, user, case, permission, *, redirect_to=None):
    """
    Block assignees whose active case task restricts a named permission.

    Returns an HttpResponse when denied, otherwise None. Employees without an
    active task on the case are unaffected.
    """
    access = CaseTask.effective_access_for(user, case)
    if access is None:
        return None
    field = f"allow_{(permission or '').strip().lower()}"
    if access.get(field, True):
        return None
    label = (permission or "perform this action").strip().lower() or "perform this action"
    messages.error(
        request,
        f"Your task on this case restricts {label} access.",
    )
    if redirect_to is None:
        if (permission or "").strip().lower() == "view":
            redirect_to = user.workspace_url("dashboard", "tasks")
        else:
            redirect_to = reverse(
                "accounts:view_litigation_case",
                kwargs={"role": user.role_slug, "case_id": case.pk},
            )
    return redirect(redirect_to)


def _matter_task_access_denied(request, user, matter, permission, *, redirect_to=None):
    """
    Block assignees whose active matter task restricts a named permission.

    Returns an HttpResponse when denied, otherwise None. Employees without an
    active task on the matter are unaffected.
    """
    access = MatterTask.effective_access_for(user, matter)
    if access is None:
        return None
    field = f"allow_{(permission or '').strip().lower()}"
    if access.get(field, True):
        return None
    label = (permission or "perform this action").strip().lower() or "perform this action"
    messages.error(
        request,
        f"Your task on this matter restricts {label} access.",
    )
    if redirect_to is None:
        if (permission or "").strip().lower() == "view":
            redirect_to = user.workspace_url("dashboard", "tasks")
        else:
            redirect_to = reverse(
                "accounts:view_non_litigation_matter",
                kwargs={"role": user.role_slug, "matter_id": matter.pk},
            )
    return redirect(redirect_to)


def _preferred_task_id(request):
    raw = (request.GET.get("task") or "").strip()
    try:
        return int(raw) if raw else None
    except (TypeError, ValueError):
        return None


def _live_case_tasks_for_user(case, user, *, preferred_id=None):
    """Accepted tasks for this assignee on the case, preferred id first."""
    tasks = list(
        CaseTask.objects.filter(
            case=case,
            assignee=user,
            status=CaseTask.Status.ACCEPTED,
        )
        .select_related("created_by", "case", "case__client")
        .order_by("due_date", "pk")
    )
    if preferred_id:
        preferred = next((task for task in tasks if task.pk == preferred_id), None)
        if preferred:
            tasks = [preferred] + [task for task in tasks if task.pk != preferred_id]
    return tasks


def _live_matter_tasks_for_user(matter, user, *, preferred_id=None):
    """Accepted tasks for this assignee on the matter, preferred id first."""
    tasks = list(
        MatterTask.objects.filter(
            matter=matter,
            assignee=user,
            status=MatterTask.Status.ACCEPTED,
        )
        .select_related("created_by", "matter", "matter__client")
        .order_by("due_date", "pk")
    )
    if preferred_id:
        preferred = next((task for task in tasks if task.pk == preferred_id), None)
        if preferred:
            tasks = [preferred] + [task for task in tasks if task.pk != preferred_id]
    return tasks


def _entity_live_task_context(request, *, kind, tasks, role):
    """Context for the live task FAB + complete modal on case/matter pages."""
    live_tasks = []
    is_case = kind == "case"
    complete_name = (
        "accounts:complete_case_task" if is_case else "accounts:complete_matter_task"
    )
    entity_field_label = "Case" if is_case else "Matter"
    for task in tasks:
        if is_case:
            subject = str(task.case)
            subject_meta = task.case.client.get_full_name()
        else:
            subject = str(task.matter)
            subject_meta = task.matter.client.get_full_name()
        live_tasks.append(
            {
                "task": task,
                "kind": kind,
                "subject": subject,
                "subject_meta": subject_meta,
                "entity_field_label": entity_field_label,
                "complete_url": reverse(
                    complete_name,
                    kwargs={"role": role, "task_id": task.pk},
                ),
            }
        )
    # Prefer ?task= for ordering only — never auto-open; modal opens on FAB/banner click.
    return {
        "live_tasks": live_tasks,
        "live_task_count": len(live_tasks),
        "live_task_kind": kind,
        "open_live_task_modal": False,
    }


def _guard_matter_approve(request, role, *, action="view", redirect_to=None):
    return _guard_perm(
        request,
        role,
        module=_MATTER_MODULE,
        activity="approve-registered-matters",
        action=action,
        redirect_to=redirect_to,
    )


def _guard_matter_register(request, role, *, action="view", redirect_to=None):
    return _guard_perm(
        request,
        role,
        module=_MATTER_MODULE,
        activity="register-new-matter",
        action=action,
        redirect_to=redirect_to,
    )


def _guard_non_litigation(request, role, *, action="view", redirect_to=None):
    return _guard_perm(
        request,
        role,
        module=_MATTER_MODULE,
        activity="non-litigation-matters",
        action=action,
        redirect_to=redirect_to,
    )


def _guard_invoicing(request, role, *, action="view", redirect_to=None):
    return _guard_perm(
        request,
        role,
        module=_FINANCE_MODULE,
        activity="invoicing",
        action=action,
        redirect_to=redirect_to,
    )


def _guard_entity_document(request, role, document, *, action="view", redirect_to=None):
    if document.case_id:
        return _guard_litigation(
            request, role, action=action, redirect_to=redirect_to
        )
    if document.matter_id:
        return _guard_non_litigation(
            request, role, action=action, redirect_to=redirect_to
        )
    return _employee_workspace_guard(request, role)


@login_required
@require_POST
def latest_news_job_start(request, role):
    """Validate filters, persist a job, and start background news retrieval."""
    user, denied = _guard_perm(
        request,
        role,
        module=_RESEARCH_MODULE,
        activity="latest-news",
        action="register",
    )
    if denied:
        return JsonResponse({"error": "forbidden"}, status=403)

    form = LatestNewsScrapeForm(request.POST)
    if not form.is_valid():
        return JsonResponse(
            {"errors": form.errors.get_json_data()},
            status=400,
        )

    filters = {
        key: form.cleaned_data[key]
        for key in (
            "country",
            "industry",
            "requested_details",
            "period",
            "language",
            "sort_by",
            "exact_phrase",
            "excluded_words",
            "source_domain",
        )
    }
    filters["country_code"] = filters.pop("country")
    job = NewsSearchJob.objects.create(
        requested_by=user,
        filters=filters,
    )
    from .news_jobs import launch_news_search

    launch_news_search(job.pk)
    return JsonResponse(
        {
            "job_id": job.pk,
            "status_url": reverse(
                "accounts:latest_news_job_status",
                kwargs={"role": role, "job_id": job.pk},
            ),
            "cancel_url": reverse(
                "accounts:latest_news_job_cancel",
                kwargs={"role": role, "job_id": job.pk},
            ),
        },
        status=202,
    )


@login_required
@require_GET
def latest_news_job_status(request, role, job_id):
    """Return real progress for a search owned by the signed-in employee."""
    user, denied = _guard_perm(
        request,
        role,
        module=_RESEARCH_MODULE,
        activity="latest-news",
        action="view",
    )
    if denied:
        return JsonResponse({"error": "forbidden"}, status=403)
    job = get_object_or_404(NewsSearchJob, pk=job_id, requested_by=user)
    payload = {
        "status": job.status,
        "progress": job.progress,
        "label": job.progress_label,
        "error": job.error,
        "terminal": job.status
        in {
            NewsSearchJob.Status.SUCCEEDED,
            NewsSearchJob.Status.FAILED,
            NewsSearchJob.Status.CANCELLED,
        },
    }
    if job.status == NewsSearchJob.Status.SUCCEEDED:
        result_url = user.workspace_url(
            "dashboard", "research-blogs", "latest-news"
        )
        payload["result_url"] = f"{result_url}?job={job.pk}"
    return JsonResponse(payload)


@login_required
@require_POST
def latest_news_job_cancel(request, role, job_id):
    """Request cancellation and immediately stop progress in the UI."""
    user, denied = _guard_perm(
        request,
        role,
        module=_RESEARCH_MODULE,
        activity="latest-news",
        action="edit",
    )
    if denied:
        return JsonResponse({"error": "forbidden"}, status=403)
    job = get_object_or_404(NewsSearchJob, pk=job_id, requested_by=user)
    if job.status in {NewsSearchJob.Status.QUEUED, NewsSearchJob.Status.RUNNING}:
        job.cancel_requested = True
        job.status = NewsSearchJob.Status.CANCELLED
        job.progress_label = "Search cancelled"
        job.finished_at = timezone.now()
        job.save(
            update_fields=[
                "cancel_requested",
                "status",
                "progress_label",
                "finished_at",
                "updated_at",
            ]
        )
    return JsonResponse(
        {
            "status": job.status,
            "progress": job.progress,
            "label": job.progress_label,
            "terminal": True,
        }
    )


@login_required
@require_POST
def latest_news_blog_draft(request, role, job_id, article_index):
    """Generate an attributed editor draft from one owned news result."""
    user, denied = _guard_perm(
        request,
        role,
        module=_RESEARCH_MODULE,
        activity="latest-news",
        action="register",
    )
    if denied:
        return denied

    job = get_object_or_404(
        NewsSearchJob,
        pk=job_id,
        requested_by=user,
        status=NewsSearchJob.Status.SUCCEEDED,
    )
    articles = job.result.get("articles") or []
    if article_index < 0 or article_index >= len(articles):
        messages.error(request, "That news article is no longer available.")
        return redirect(
            user.workspace_url("dashboard", "research-blogs", "latest-news")
        )

    initial, source = build_news_blog_draft(
        article=articles[article_index],
        filters=job.filters,
        country_name=country_name(job.filters.get("country")),
    )
    request.session["news_blog_draft"] = {
        "initial": initial,
        "source": source,
    }
    messages.success(
        request,
        "News article draft generated. Review the facts and wording before saving.",
    )
    return redirect(user.workspace_url("dashboard", "my-blogs-new"))


@login_required
@require_POST
def latest_news_watch_search(request, role, job_id):
    """Save a completed search for automatic daily update checks."""
    user, denied = _guard_perm(
        request,
        role,
        module=_RESEARCH_MODULE,
        activity="latest-news",
        action="edit",
    )
    if denied:
        return denied
    job = get_object_or_404(
        NewsSearchJob,
        pk=job_id,
        requested_by=user,
        status=NewsSearchJob.Status.SUCCEEDED,
    )
    from .news_watch import seed_watch, watch_key

    filters = dict(job.filters)
    key = watch_key(NewsWatch.Kind.SEARCH, filters)
    topic = filters.get("requested_details") or "Latest news"
    watch, created = NewsWatch.objects.get_or_create(
        requested_by=user,
        key=key,
        defaults={
            "kind": NewsWatch.Kind.SEARCH,
            "name": topic[:180],
            "filters": filters,
            "last_checked_at": timezone.now(),
            "next_check_at": timezone.now() + timedelta(days=1),
        },
    )
    if not watch.is_active:
        watch.is_active = True
        watch.next_check_at = timezone.now() + timedelta(days=1)
        watch.save(update_fields=["is_active", "next_check_at", "updated_at"])
    seed_watch(watch, job.result.get("articles") or [])
    messages.success(
        request,
        (
            "Search saved. We will check it daily and notify you about new articles."
            if created
            else "This search is already in your daily watches."
        ),
    )
    return redirect(
        f"{user.workspace_url('dashboard', 'research-blogs', 'latest-news')}?job={job.pk}"
    )


@login_required
@require_POST
def latest_news_watch_publisher(request, role, job_id, article_index):
    """Watch the selected publisher for new matching coverage."""
    user, denied = _guard_perm(
        request,
        role,
        module=_RESEARCH_MODULE,
        activity="latest-news",
        action="edit",
    )
    if denied:
        return denied
    job = get_object_or_404(
        NewsSearchJob,
        pk=job_id,
        requested_by=user,
        status=NewsSearchJob.Status.SUCCEEDED,
    )
    articles = job.result.get("articles") or []
    if article_index < 0 or article_index >= len(articles):
        messages.error(request, "That publisher is no longer available.")
        return redirect(
            user.workspace_url("dashboard", "research-blogs", "latest-news")
        )

    from .news_watch import publisher_domain, seed_watch, watch_key

    article = articles[article_index]
    domain = publisher_domain(article.get("url") or "")
    if not domain:
        messages.error(request, "The publisher domain could not be identified.")
        return redirect(
            f"{user.workspace_url('dashboard', 'research-blogs', 'latest-news')}?job={job.pk}"
        )
    filters = dict(job.filters)
    # A publisher watch follows the source broadly rather than repeating the
    # original topic query. Country and language still localise the feed.
    filters["requested_details"] = ""
    filters["industry"] = "other"
    filters["exact_phrase"] = ""
    filters["excluded_words"] = ""
    filters["sort_by"] = "newest"
    filters["source_domain"] = domain
    key = watch_key(NewsWatch.Kind.PUBLISHER, filters, domain)
    publisher = article.get("source_name") or domain
    watch, created = NewsWatch.objects.get_or_create(
        requested_by=user,
        key=key,
        defaults={
            "kind": NewsWatch.Kind.PUBLISHER,
            "name": publisher[:180],
            "filters": filters,
            "publisher_domain": domain,
            "last_checked_at": timezone.now(),
            "next_check_at": timezone.now() + timedelta(days=1),
        },
    )
    if not watch.is_active:
        watch.is_active = True
        watch.next_check_at = timezone.now() + timedelta(days=1)
        watch.save(update_fields=["is_active", "next_check_at", "updated_at"])
    baseline = [
        item
        for item in articles
        if publisher_domain(item.get("url") or "") == domain
        or item.get("source_name") == article.get("source_name")
    ]
    seed_watch(watch, baseline)
    messages.success(
        request,
        (
            f"{publisher} is now watched daily for new updates."
            if created
            else f"{publisher} is already in your daily watches."
        ),
    )
    return redirect(
        f"{user.workspace_url('dashboard', 'research-blogs', 'latest-news')}?job={job.pk}"
    )


@login_required
@require_POST
def latest_news_watch_remove(request, role, watch_id):
    """Remove a news watch owned by the signed-in employee."""
    user, denied = _guard_perm(
        request,
        role,
        module=_RESEARCH_MODULE,
        activity="latest-news",
        action="edit",
    )
    if denied:
        return denied
    watch = get_object_or_404(NewsWatch, pk=watch_id, requested_by=user)
    watch.delete()
    messages.success(request, "Daily news watch removed.")
    return redirect(
        user.workspace_url("dashboard", "research-blogs", "latest-news")
    )


@login_required
@require_POST
def latest_news_watch_update(request, role, watch_id):
    """Update the independent check frequency for one owned news watch."""
    user, denied = _guard_perm(
        request,
        role,
        module=_RESEARCH_MODULE,
        activity="latest-news",
        action="edit",
    )
    if denied:
        return denied
    watch = get_object_or_404(NewsWatch, pk=watch_id, requested_by=user)
    frequency = (request.POST.get("frequency") or "").strip()
    if frequency not in NewsWatch.Frequency.values:
        messages.error(request, "Select a valid monitoring frequency.")
        return redirect(
            user.workspace_url("dashboard", "research-blogs", "latest-news")
        )

    from .news_watch import watch_interval

    watch.frequency = frequency
    watch.next_check_at = timezone.now() + watch_interval(frequency)
    watch.check_started_at = None
    watch.save(
        update_fields=[
            "frequency",
            "next_check_at",
            "check_started_at",
            "updated_at",
        ]
    )
    messages.success(
        request,
        f"Monitoring for “{watch.name}” will run {watch.get_frequency_display().lower()}.",
    )
    return redirect(
        user.workspace_url("dashboard", "research-blogs", "latest-news")
    )


@login_required
@require_POST
def latest_news_watch_check(request, role, watch_id):
    """Start a manual check for one owned news watch."""
    user, denied = _guard_perm(
        request,
        role,
        module=_RESEARCH_MODULE,
        activity="latest-news",
        action="register",
    )
    if denied:
        if request.headers.get("Accept") == "application/json":
            return JsonResponse({"error": "forbidden"}, status=403)
        return denied
    watch = get_object_or_404(NewsWatch, pk=watch_id, requested_by=user)
    from .news_watch import launch_news_watch_now

    state = launch_news_watch_now(watch.pk)
    wants_json = "application/json" in (request.headers.get("Accept") or "")
    latest_url = user.workspace_url(
        "dashboard", "research-blogs", "latest-news"
    )
    if state == "busy":
        if wants_json:
            return JsonResponse(
                {
                    "error": "busy",
                    "message": f"“{watch.name}” is already being checked.",
                },
                status=409,
            )
        messages.info(
            request,
            f"“{watch.name}” is already being checked. Try again in a moment.",
        )
        return redirect(f"{latest_url}?watch={watch.pk}")

    if wants_json:
        return JsonResponse(
            {
                "watch_id": watch.pk,
                "status_url": reverse(
                    "accounts:latest_news_watch_status",
                    kwargs={"role": role, "watch_id": watch.pk},
                ),
                "cancel_url": reverse(
                    "accounts:latest_news_watch_cancel",
                    kwargs={"role": role, "watch_id": watch.pk},
                ),
            },
            status=202,
        )

    messages.success(
        request,
        f"Checking “{watch.name}” for updates…",
    )
    return redirect(f"{latest_url}?watch={watch.pk}")


@login_required
@require_GET
def latest_news_watch_status(request, role, watch_id):
    """Return progress for a manual watch check."""
    user, denied = _guard_perm(
        request,
        role,
        module=_RESEARCH_MODULE,
        activity="latest-news",
        action="view",
    )
    if denied:
        return JsonResponse({"error": "forbidden"}, status=403)
    watch = get_object_or_404(NewsWatch, pk=watch_id, requested_by=user)
    from .news_watch import get_manual_check_status

    status = get_manual_check_status(watch.pk)
    payload = {
        "status": status.get("status") or "queued",
        "progress": status.get("progress") or 0,
        "label": status.get("label") or "Preparing check…",
        "error": status.get("error") or "",
        "found": status.get("found") or 0,
        "terminal": bool(
            status.get("terminal")
            or status.get("status")
            in {"succeeded", "failed", "cancelled"}
        ),
    }
    if status.get("status") == "succeeded":
        result_url = status.get("result_url") or (
            f"{user.workspace_url('dashboard', 'research-blogs', 'latest-news')}"
            f"?watch={watch.pk}"
        )
        payload["result_url"] = result_url
    return JsonResponse(payload)


@login_required
@require_POST
def latest_news_watch_cancel(request, role, watch_id):
    """Request cancellation of a manual watch check."""
    user, denied = _guard_perm(
        request,
        role,
        module=_RESEARCH_MODULE,
        activity="latest-news",
        action="edit",
    )
    if denied:
        return JsonResponse({"error": "forbidden"}, status=403)
    watch = get_object_or_404(NewsWatch, pk=watch_id, requested_by=user)
    from .news_watch import get_manual_check_status, request_manual_check_cancel

    status = request_manual_check_cancel(watch.pk)
    current = get_manual_check_status(watch.pk)
    return JsonResponse(
        {
            "status": current.get("status") or "cancelled",
            "progress": current.get("progress") or 0,
            "label": status.get("label") or "Cancelling check…",
            "terminal": bool(current.get("terminal")),
        }
    )


def _pending_clients_list_url(user):
    return user.workspace_url(*PENDING_CLIENTS_TRAIL)


def _client_profile_list_url(user):
    return user.workspace_url(*CLIENT_PROFILE_TRAIL)


def _client_management_list_url(user):
    return user.workspace_url(*CLIENT_MANAGEMENT_TRAIL)


def _purge_pending_client_account(client):
    """Delete a client row, then uploaded files and Drive folder (if any)."""
    file_fields = (
        "profile_photo",
        "identification_document",
        "alien_document",
        "business_document",
        "company_registration_document",
        "kra_pin_document",
        "signed_instruction_note",
    )
    stored_files = []
    for field_name in file_fields:
        field_file = getattr(client, field_name, None)
        if field_file and field_file.name:
            stored_files.append((field_file.storage, field_file.name))

    drive_folder_id = client.drive_folder_id

    with transaction.atomic():
        client.delete()

    for storage, name in stored_files:
        try:
            storage.delete(name)
        except Exception:
            pass

    if drive_folder_id:
        trash_drive_file(drive_folder_id)


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
        user, denied = _guard_client_pending(request, role, action="edit")
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
        user, denied = _guard_client_pending(request, role, action="edit")
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
        user, denied = _guard_client_pending(request, role, action="view")
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
        user, denied = _guard_client_pending(request, role, action="approve")
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
                rows.append(("National ID", "", client.identification_document))
            else:
                rows.append(("Passport", "", client.alien_document))
        else:
            if client.corporate_kind == Client.CorporateKind.BUSINESS:
                rows.append(
                    ("Business certificate", "", client.business_document)
                )
            else:
                rows.append(("CR12", "", client.company_registration_document))
        rows.extend(
            [
                ("KRA PIN", "", client.kra_pin_document),
                ("Signed instruction note", "", client.signed_instruction_note),
            ]
        )
        return rows


@method_decorator(login_required, name="dispatch")
class DeclinePendingClientView(View):
    """Decline a pending client from the list and permanently delete their account."""

    def post(self, request, role, client_id):
        user, denied = _guard_client_pending(request, role, action="approve")
        if denied:
            return denied

        client = get_object_or_404(Client, pk=client_id)
        if client.status not in {
            Client.Status.PENDING_ONBOARDING,
            Client.Status.PENDING_APPROVAL,
        }:
            messages.info(
                request,
                "This client is not pending onboarding or approval.",
            )
            return redirect(_pending_clients_list_url(user))

        client_name = client.get_full_name()
        try:
            _purge_pending_client_account(client)
        except ProtectedError:
            messages.error(
                request,
                f"Cannot decline {client_name}: linked cases, matters, or "
                "invoices must be removed first.",
            )
            return redirect(_pending_clients_list_url(user))

        messages.success(
            request,
            f"Declined {client_name}. Their account and uploaded details "
            "have been permanently deleted.",
        )
        return redirect(_pending_clients_list_url(user))


@method_decorator(login_required, name="dispatch")
class LoginAsClientView(View):
    """Staff: open the client portal signed in as the selected client."""

    def post(self, request, role, client_id):
        user, denied = _guard_client_profile(request, role, action="view")
        if denied:
            return denied

        client = get_object_or_404(Client, pk=client_id)
        if client.status != Client.Status.ACTIVE:
            messages.error(
                request,
                "Only active clients can be opened in the client portal.",
            )
            return redirect(_client_profile_list_url(user))

        return_url = _client_profile_list_url(user)
        start_staff_impersonation(request, client, return_url=return_url)
        messages.info(
            request,
            f"You are viewing the client portal as {client.get_full_name()}.",
        )
        return redirect_for_client(client)


@method_decorator(login_required, name="dispatch")
class EditClientProfileView(View):
    """Staff edit all details for an active or suspended client."""

    template_name = "accounts/edit_client_profile.html"

    def get_client(self, client_id):
        return get_object_or_404(Client, pk=client_id)

    def _managed_statuses(self):
        return {Client.Status.ACTIVE, Client.Status.SUSPENDED}

    def _document_rows(self, client):
        return ApproveClientView._document_rows(client)

    def _page_context(self, request, user, client, form):
        context = workspace_context(
            user,
            request=request,
            page_title="Client profile",
            page_trail=list(CLIENT_MANAGEMENT_TRAIL),
            active_page="client-management",
        )
        context["client"] = client
        context["form"] = form
        context["list_url"] = _client_management_list_url(user)
        context["documents"] = self._document_rows(client)
        return context

    def get(self, request, role, client_id):
        user, denied = _guard_client_profile(request, role, action="edit")
        if denied:
            return denied

        client = self.get_client(client_id)
        if client.status not in self._managed_statuses():
            messages.info(
                request,
                "Only active or suspended clients can be edited here.",
            )
            return redirect(_client_management_list_url(user))

        context = self._page_context(
            request, user, client, StaffClientProfileForm(client=client)
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, client_id):
        user, denied = _guard_client_profile(request, role, action="edit")
        if denied:
            return denied

        client = self.get_client(client_id)
        if client.status not in self._managed_statuses():
            messages.info(
                request,
                "Only active or suspended clients can be edited here.",
            )
            return redirect(_client_management_list_url(user))

        form = StaffClientProfileForm(
            request.POST, request.FILES, client=client
        )
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"Updated profile for {client.get_full_name()}.",
            )
            return redirect(
                "accounts:edit_client_profile",
                role=role,
                client_id=client.pk,
            )

        context = self._page_context(request, user, client, form)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class ToggleClientSuspensionView(View):
    """Suspend an active client or restore a suspended client."""

    def post(self, request, role, client_id):
        user, denied = _guard_client_profile(request, role, action="edit")
        if denied:
            return denied

        client = get_object_or_404(Client, pk=client_id)
        if client.status == Client.Status.ACTIVE:
            client.status = Client.Status.SUSPENDED
            client.save(update_fields=["status"])
            messages.success(
                request,
                f"{client.get_full_name()} has been suspended.",
            )
        elif client.status == Client.Status.SUSPENDED:
            client.status = Client.Status.ACTIVE
            client.save(update_fields=["status"])
            messages.success(
                request,
                f"{client.get_full_name()} has been unsuspended and is active again.",
            )
        else:
            messages.info(
                request,
                "Only active or suspended clients can be suspended or unsuspended.",
            )
            return redirect(_client_management_list_url(user))

        next_url = (request.POST.get("next") or "").strip()
        if next_url == "list":
            return redirect(_client_profile_list_url(user))
        return redirect(
            "accounts:edit_client_profile",
            role=role,
            client_id=client.pk,
        )


@method_decorator(login_required, name="dispatch")
class DeleteClientProfileView(View):
    """Permanently delete an active or suspended client from the system."""

    def post(self, request, role, client_id):
        user, denied = _guard_client_profile(request, role, action="delete")
        if denied:
            return denied

        client = get_object_or_404(Client, pk=client_id)
        if client.status not in {
            Client.Status.ACTIVE,
            Client.Status.SUSPENDED,
        }:
            messages.info(
                request,
                "Only active or suspended clients can be deleted here.",
            )
            return redirect(_client_management_list_url(user))

        client_name = client.get_full_name()
        try:
            _purge_pending_client_account(client)
        except ProtectedError:
            messages.error(
                request,
                f"Cannot delete {client_name}: linked cases, matters, or "
                "invoices must be removed first.",
            )
            return redirect(
                "accounts:edit_client_profile",
                role=role,
                client_id=client_id,
            )

        messages.success(
            request,
            f"Deleted {client_name}. Their account and uploaded details "
            "have been permanently removed.",
        )
        return redirect(_client_management_list_url(user))


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
        user, denied = _guard_case_approve(request, role, action="view")
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
        user, denied = _guard_case_approve(request, role, action="approve")
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
        user, denied = _guard_case_register(request, role, action="view")
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
        user, denied = _guard_case_register(request, role, action="register")
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

            for party_form in party_formset.deleted_forms:
                if party_form.instance.pk:
                    party_form.instance.delete()

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
        user, denied = _guard_litigation(request, role, action="view")
        if denied:
            return denied

        case = self.get_case(case_id)
        redirect_response = self._guard(request, role, case)
        if redirect_response:
            return redirect_response

        access_denied = _case_task_access_denied(request, user, case, "edit")
        if access_denied:
            return access_denied

        form = RegisterCaseForm(instance=case)
        party_formset = CasePartyEditFormSet(
            queryset=case.parties.order_by("sort_order", "pk"),
            prefix="parties",
        )
        context = self._context(user, case, form, party_formset)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, case_id):
        user, denied = _guard_litigation(request, role, action="edit")
        if denied:
            return denied

        case = self.get_case(case_id)
        redirect_response = self._guard(request, role, case)
        if redirect_response:
            return redirect_response

        access_denied = _case_task_access_denied(request, user, case, "edit")
        if access_denied:
            return access_denied

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

            for party_form in party_formset.deleted_forms:
                if party_form.instance.pk:
                    party_form.instance.delete()

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
        user, denied = _guard_matter_approve(request, role, action="view")
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
        user, denied = _guard_matter_approve(request, role, action="approve")
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
        user, denied = _guard_matter_register(request, role, action="view")
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
        user, denied = _guard_matter_register(request, role, action="register")
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

            for party_form in party_formset.deleted_forms:
                if party_form.instance.pk:
                    party_form.instance.delete()

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
        user, denied = _guard_non_litigation(request, role, action="view")
        if denied:
            return denied

        matter = self.get_matter(matter_id)
        redirect_response = self._guard(request, role, matter)
        if redirect_response:
            return redirect_response

        access_denied = _matter_task_access_denied(request, user, matter, "edit")
        if access_denied:
            return access_denied

        form = RegisterMatterForm(instance=matter)
        party_formset = MatterPartyEditFormSet(
            queryset=matter.parties.order_by("sort_order", "pk"),
            prefix="parties",
        )
        context = self._context(user, matter, form, party_formset)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, matter_id):
        user, denied = _guard_non_litigation(request, role, action="edit")
        if denied:
            return denied

        matter = self.get_matter(matter_id)
        redirect_response = self._guard(request, role, matter)
        if redirect_response:
            return redirect_response

        access_denied = _matter_task_access_denied(request, user, matter, "edit")
        if access_denied:
            return access_denied

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

            for party_form in party_formset.deleted_forms:
                if party_form.instance.pk:
                    party_form.instance.delete()

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
        company = FirmCompanyInformation.get_solo()
        share_accounts = company_share_accounts(company)
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
                "social_share_accounts": share_accounts,
                "company_contacts_url": user.workspace_url(
                    "dashboard", "company-contacts"
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
            share_note = ""
            if request.POST.get("share_on_publish") == "1":
                selected = request.POST.getlist("share_accounts")
                intents = build_share_intents(
                    request=request,
                    post=post,
                    selected_field_keys=selected,
                )
                if intents:
                    stash_share_intents(request, intents)
                    labels = ", ".join(item["label"] for item in intents)
                    share_note = f" Share ready for {labels}."
                elif selected:
                    share_note = (
                        " No matching social accounts were available to share."
                    )
                else:
                    share_note = (
                        " Share was enabled but no social accounts were selected."
                    )
            messages.success(
                request,
                f"“{post.title}” is now published on the website.{share_note}",
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
        user, denied = _guard_employee_pending(request, role, action="edit")
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
        user, denied = _guard_employee_pending(request, role, action="edit")
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
        user, denied = _guard_employee_pending(request, role, action="view")
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
        user, denied = _guard_employee_pending(request, role, action="approve")
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
        user, denied = _guard_litigation(request, role, action="view")
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

        access_denied = _case_task_access_denied(request, user, case, "view")
        if access_denied:
            return access_denied

        live_tasks = _live_case_tasks_for_user(
            case, user, preferred_id=_preferred_task_id(request)
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
        context.update(
            _entity_live_task_context(
                request, kind="case", tasks=live_tasks, role=role
            )
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
        user, denied = _guard_invoicing(request, role, action="view")
        if denied:
            return denied

        invoice = self.get_invoice(invoice_id)
        context = self._context(user, invoice, request=request)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, invoice_id):
        user, denied = _guard_invoicing(request, role, action="edit")
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
                    Invoice.Status.PARTIALLY_PAID,
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
        user, denied = _guard_invoicing(request, role, action="view")
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
        user, denied = _guard_invoicing(request, role, action="view")
        if denied:
            return denied

        invoice = self.get_invoice(invoice_id)
        context = self._context(user, invoice, request=request)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, invoice_id):
        user, denied = _guard_invoicing(request, role, action="pay")
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
        user, denied = _guard_litigation(request, role, action="attend")
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
        user, denied = _guard_litigation(request, role, action="attend")
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

    def _context(
        self,
        user,
        case,
        form,
        advocate_formset,
        bringup_formset,
        **kwargs_edit,
    ):
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
        previous_attendances = list(
            case.court_attendances.select_related("recorded_by")
            .prefetch_related("advocates", "bring_up_items__allocated_to")
            .all()
        )
        edit_form = kwargs_edit.get("edit_form") or UpdateCourtAttendanceForm(
            prefix="edit"
        )
        edit_advocate_formset = kwargs_edit.get(
            "edit_advocate_formset"
        ) or CourtAttendanceAdvocateFormSet(prefix="edit-advocates")
        edit_bringup_formset = kwargs_edit.get(
            "edit_bringup_formset"
        ) or CourtAttendanceBringUpItemFormSet(prefix="edit-bringups")
        editing_attendance = kwargs_edit.get("editing_attendance")
        open_edit_modal = bool(kwargs_edit.get("open_edit_modal"))

        attendance_payload = [
            self._serialize_attendance(user, attendance)
            for attendance in previous_attendances
        ]

        context.update(
            {
                "case": case,
                "form": form,
                "advocate_formset": advocate_formset,
                "bringup_formset": bringup_formset,
                "edit_form": edit_form,
                "edit_advocate_formset": edit_advocate_formset,
                "edit_bringup_formset": edit_bringup_formset,
                "editing_attendance": editing_attendance,
                "open_edit_modal": open_edit_modal,
                "detail_url": detail_url,
                "list_url": _active_cases_list_url(user),
                "previous_attendances": previous_attendances,
                "previous_attendances_data": attendance_payload,
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
                "reminder_frequency_choices": (
                    CourtAttendanceBringUpItem.ReminderFrequency.choices
                ),
            }
        )
        return context

    def _serialize_attendance(self, user, attendance):
        edit_url = reverse(
            "accounts:edit_court_attendance",
            kwargs={
                "role": user.role_slug,
                "case_id": attendance.case_id,
                "attendance_id": attendance.pk,
            },
        )
        return {
            "id": attendance.pk,
            "edit_url": edit_url,
            "activity_type": attendance.activity_type,
            "judicial_officer": attendance.judicial_officer,
            "court_room": attendance.court_room or "",
            "attendance_date": (
                attendance.attendance_date.isoformat()
                if attendance.attendance_date
                else ""
            ),
            "attendance_date_display": (
                attendance.attendance_date.strftime("%d %b %Y")
                if attendance.attendance_date
                else "—"
            ),
            "presence": attendance.presence,
            "presence_display": attendance.get_presence_display(),
            "court_directions": attendance.court_directions or "",
            "description": attendance.description or "",
            "next_action": attendance.next_action or "",
            "next_activity_type": attendance.next_activity_type or "",
            "next_court_date": (
                attendance.next_court_date.isoformat()
                if attendance.next_court_date
                else ""
            ),
            "next_court_date_display": (
                attendance.next_court_date.strftime("%d %b %Y")
                if attendance.next_court_date
                else ""
            ),
            "next_judicial_officer": attendance.next_judicial_officer or "",
            "next_client_attendance": attendance.next_client_attendance or "",
            "next_client_attendance_display": (
                attendance.get_next_client_attendance_display()
                if attendance.next_client_attendance
                else ""
            ),
            "virtual_link": attendance.virtual_link or "",
            "recorded_by": (
                attendance.recorded_by.get_full_name()
                if attendance.recorded_by
                else ""
            ),
            "advocates": [
                {
                    "advocate_name": advocate.advocate_name,
                    "what_they_said": advocate.what_they_said or "",
                }
                for advocate in attendance.advocates.all()
            ],
            "bring_up_items": [
                {
                    "description": item.description,
                    "reminder_frequency": item.reminder_frequency or "",
                    "reminder_frequency_display": (
                        item.get_reminder_frequency_display()
                        if item.reminder_frequency
                        else ""
                    ),
                    "allocated_to": item.allocated_to_id or "",
                    "allocated_to_name": (
                        (
                            f"{item.allocated_to.get_full_name()} "
                            f"({item.allocated_to.get_role_display()})"
                        )
                        if item.allocated_to
                        else ""
                    ),
                }
                for item in attendance.bring_up_items.all()
            ],
        }


@method_decorator(login_required, name="dispatch")
class EditCourtAttendanceView(View):
    """Update an existing court attendance record for a litigation case."""

    template_name = "accounts/update_court_attendance.html"
    action_slug = "update-court-attendance"

    def get_case(self, case_id):
        return get_object_or_404(
            LitigationCase.objects.select_related(
                "client", "assigned_to", "registered_by"
            ),
            pk=case_id,
        )

    def get_attendance(self, case, attendance_id):
        return get_object_or_404(
            CourtAttendance.objects.select_related("recorded_by").prefetch_related(
                "advocates", "bring_up_items__allocated_to"
            ),
            pk=attendance_id,
            case=case,
        )

    def get(self, request, role, case_id, attendance_id):
        user, denied = _guard_litigation(request, role, action="attend")
        if denied:
            return denied

        case = self.get_case(case_id)
        if case.status == LitigationCase.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_litigation_case",
                role=role,
                case_id=case.pk,
            )

        attendance = self.get_attendance(case, attendance_id)
        create_view = UpdateCourtAttendanceView()
        create_view.request = request
        context = create_view._context(
            user,
            case,
            UpdateCourtAttendanceForm(),
            CourtAttendanceAdvocateFormSet(prefix="advocates"),
            CourtAttendanceBringUpItemFormSet(prefix="bringups"),
            edit_form=UpdateCourtAttendanceForm(
                instance=attendance, prefix="edit"
            ),
            edit_advocate_formset=self._advocate_formset(attendance),
            edit_bringup_formset=self._bringup_formset(attendance),
            editing_attendance=attendance,
            open_edit_modal=True,
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, case_id, attendance_id):
        user, denied = _guard_litigation(request, role, action="attend")
        if denied:
            return denied

        case = self.get_case(case_id)
        if case.status == LitigationCase.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_litigation_case",
                role=role,
                case_id=case.pk,
            )

        attendance = self.get_attendance(case, attendance_id)
        form = UpdateCourtAttendanceForm(
            request.POST, instance=attendance, prefix="edit"
        )
        advocate_formset = CourtAttendanceAdvocateFormSet(
            request.POST, prefix="edit-advocates"
        )
        bringup_formset = CourtAttendanceBringUpItemFormSet(
            request.POST, prefix="edit-bringups"
        )

        if not (
            form.is_valid()
            and advocate_formset.is_valid()
            and bringup_formset.is_valid()
        ):
            create_view = UpdateCourtAttendanceView()
            create_view.request = request
            context = create_view._context(
                user,
                case,
                UpdateCourtAttendanceForm(),
                CourtAttendanceAdvocateFormSet(prefix="advocates"),
                CourtAttendanceBringUpItemFormSet(prefix="bringups"),
                edit_form=form,
                edit_advocate_formset=advocate_formset,
                edit_bringup_formset=bringup_formset,
                editing_attendance=attendance,
                open_edit_modal=True,
            )
            response = render(request, self.template_name, context)
            return attach_greeting_cookie(response, request)

        with transaction.atomic():
            form.save()
            attendance.advocates.all().delete()
            attendance.bring_up_items.all().delete()

            advocate_count = 0
            for advocate_form in advocate_formset:
                if not getattr(advocate_form, "cleaned_data", None):
                    continue
                if advocate_form.cleaned_data.get("DELETE"):
                    continue
                name = (
                    advocate_form.cleaned_data.get("advocate_name") or ""
                ).strip()
                if not name:
                    continue
                CourtAttendanceAdvocate.objects.create(
                    attendance=attendance,
                    advocate_name=name,
                    what_they_said=advocate_form.cleaned_data.get(
                        "what_they_said"
                    )
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
            f"Court attendance updated for "
            f"{attendance.attendance_date.strftime('%d/%m/%Y')}.",
        )
        return redirect(
            "accounts:update_court_attendance",
            role=role,
            case_id=case.pk,
        )

    def _advocate_formset(self, attendance):
        initial = [
            {
                "advocate_name": advocate.advocate_name,
                "what_they_said": advocate.what_they_said,
            }
            for advocate in attendance.advocates.all()
        ]
        return CourtAttendanceAdvocateFormSet(
            prefix="edit-advocates",
            initial=initial,
        )

    def _bringup_formset(self, attendance):
        initial = [
            {
                "description": item.description,
                "reminder_frequency": item.reminder_frequency,
                "allocated_to": item.allocated_to_id,
            }
            for item in attendance.bring_up_items.all()
        ]
        return CourtAttendanceBringUpItemFormSet(
            prefix="edit-bringups",
            initial=initial,
        )


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
        user, denied = _guard_litigation(request, role, action="task")
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
        user, denied = _guard_litigation(request, role, action="task")
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

        access = form.cleaned_access_permissions()
        task = CaseTask.objects.create(
            case=case,
            assignee=form.cleaned_data["assigned_to"],
            title=form.cleaned_data["title"].strip(),
            instructions=form.cleaned_data.get("instructions") or "",
            due_date=form.cleaned_data["due_date"],
            created_by=user,
            **access,
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


def _group_documents_by_party_type(documents, party_type_choices):
    """Group library documents into party-type sections (known order first)."""
    buckets = {key: [] for key, _label in party_type_choices}
    uncategorized = []
    for document in documents:
        key = (document.party_type or "").strip()
        if key in buckets:
            buckets[key].append(document)
        else:
            uncategorized.append(document)

    groups = []
    for key, label in party_type_choices:
        items = buckets.get(key) or []
        if not items:
            continue
        groups.append(
            {
                "key": key,
                "label": label,
                "documents": items,
                "count": len(items),
            }
        )
    if uncategorized:
        groups.append(
            {
                "key": "uncategorized",
                "label": "Uncategorized",
                "documents": uncategorized,
                "count": len(uncategorized),
            }
        )
    return groups


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
        user, denied = _guard_litigation(request, role, action="upload")
        if denied:
            return denied

        case = self.get_case(case_id)
        if case.status == LitigationCase.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_litigation_case",
                role=role,
                case_id=case.pk,
            )

        access_denied = _case_task_access_denied(
            request,
            user,
            case,
            "view",
            redirect_to=reverse(
                "accounts:view_litigation_case",
                kwargs={"role": role, "case_id": case.pk},
            ),
        )
        if access_denied:
            return access_denied

        party_type_choices = CaseParty.PartyType.choices
        context = self._context(
            user,
            case,
            CreateGoogleDocumentForm(
                prefix="create",
                auto_id="create_%s",
                party_type_choices=party_type_choices,
            ),
            UploadDocumentForm(
                prefix="upload",
                auto_id="upload_%s",
                party_type_choices=party_type_choices,
            ),
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, case_id):
        user, denied = _guard_litigation(request, role, action="upload")
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
        permission_by_action = {
            "create_google": "upload",
            "upload": "upload",
            "rename": "edit",
            "delete": "delete",
        }
        needed = permission_by_action.get(action, "upload")
        library_url = reverse(
            "accounts:upload_case_documents",
            kwargs={"role": role, "case_id": case.pk},
        )
        access_denied = _case_task_access_denied(
            request,
            user,
            case,
            needed,
            redirect_to=f"{library_url}#docs-library",
        )
        if access_denied:
            return access_denied

        party_type_choices = CaseParty.PartyType.choices
        create_form = CreateGoogleDocumentForm(
            prefix="create",
            auto_id="create_%s",
            party_type_choices=party_type_choices,
        )
        upload_form = UploadDocumentForm(
            prefix="upload",
            auto_id="upload_%s",
            party_type_choices=party_type_choices,
        )

        try:
            if action == "create_google":
                create_form = CreateGoogleDocumentForm(
                    request.POST,
                    prefix="create",
                    auto_id="create_%s",
                    party_type_choices=party_type_choices,
                )
                if create_form.is_valid():
                    self._create_google_doc(user, case, create_form)
                    return self._library_redirect(role, case.pk)
            elif action == "upload":
                upload_form = UploadDocumentForm(
                    request.POST,
                    request.FILES,
                    prefix="upload",
                    auto_id="upload_%s",
                    party_type_choices=party_type_choices,
                )
                if upload_form.is_valid():
                    self._upload_file(user, case, upload_form)
                    return self._library_redirect(role, case.pk)
            elif action == "rename":
                self._rename_document(request, case)
                return self._library_redirect(role, case.pk)
            elif action == "delete":
                self._delete_document(request, case)
                return self._library_redirect(role, case.pk)
            else:
                messages.error(request, "Unknown document action.")
                return self._library_redirect(role, case.pk)
        except (GoogleDriveAPIError, GoogleDriveOAuthError) as exc:
            messages.error(request, str(exc))
            return self._library_redirect(role, case.pk)

        context = self._context(user, case, create_form, upload_form)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def _create_google_doc(self, user, case, form):
        connection = GoogleDriveConnection.get_solo()
        if not connection.is_connected:
            raise GoogleDriveAPIError(
                "Connect Google Drive in settings before creating documents."
            )
        title = form.cleaned_data["title"]
        google_type = form.cleaned_data["google_type"]
        description = form.cleaned_data["description"]
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
            **form.party_type_kwargs(),
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
            **form.party_type_kwargs(),
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
            Document,
            pk=request.POST.get("document_id"),
            case=case,
        )
        form = RenameDocumentForm(
            request.POST,
            party_type_choices=CaseParty.PartyType.choices,
        )
        if not form.is_valid():
            messages.error(
                request,
                "Enter a valid document name and party type.",
            )
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
        document.party_type = form.cleaned_data.get("party_type") or ""
        document.save(
            update_fields=[
                "title",
                "description",
                "notes",
                "party_type",
                "updated_at",
            ]
        )
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

    def _library_redirect(self, role, case_id):
        url = reverse(
            "accounts:upload_case_documents",
            kwargs={"role": role, "case_id": case_id},
        )
        return redirect(f"{url}#docs-library")

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
        party_type_choices = CaseParty.PartyType.choices
        edit_form = RenameDocumentForm(
            auto_id="edit_%s",
            party_type_choices=party_type_choices,
        )
        documents = _documents_with_activity(
            case.documents.all(),
            actor=user,
            sync_google=True,
            role=user.role_slug,
        )
        task_access = CaseTask.effective_access_for(user, case)
        if task_access is None:
            task_access = {
                "allow_view": True,
                "allow_edit": True,
                "allow_download": True,
                "allow_delete": True,
                "allow_upload": True,
            }
        context.update(
            {
                "case": case,
                "matter": None,
                "entity_kind": self.entity_kind,
                "entity_label": case.court_case_number or f"Case #{case.pk}",
                "create_form": create_form,
                "upload_form": upload_form,
                "edit_form": edit_form,
                "party_type_choices": party_type_choices,
                "documents": documents,
                "document_groups": _group_documents_by_party_type(
                    documents, party_type_choices
                ),
                "detail_url": detail_url,
                "detail_label": "Back to case",
                "list_url": _active_cases_list_url(user),
                "google_drive_connected": connection.is_connected,
                "google_drive_settings_url": user.workspace_url(
                    "dashboard", "google-drive-settings"
                ),
                "task_access": task_access,
            }
        )
        return context


@method_decorator(login_required, name="dispatch")
class CaseCalendarView(View):
    """Month calendar of dates for a client's litigation cases."""

    template_name = "accounts/entity_calendar.html"
    action_slug = "case-calendar"

    def get(self, request, role, case_id):
        user, denied = _guard_litigation(request, role, action="view")
        if denied:
            return denied

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

        today, year, month, month_start, month_end = _calendar_month_from_request(
            request
        )
        by_day = _client_case_calendar_by_day(
            user, case.client, month_start, month_end
        )
        base_url = reverse(
            "accounts:case_calendar",
            kwargs={"role": role, "case_id": case.pk},
        )
        detail_url = reverse(
            "accounts:view_litigation_case",
            kwargs={"role": role, "case_id": case.pk},
        )
        context = workspace_context(
            user,
            request=request,
            page_title="Case calendar",
            page_trail=list(ACTIVE_CASES_TRAIL),
            active_page=self.action_slug,
            page_nav_items=litigation_case_nav_items(
                user.role_slug, case.pk, active_slug=self.action_slug
            ),
        )
        context.update(
            _calendar_grid_payload(today, year, month, by_day, base_url)
        )
        context.update(
            {
                "case": case,
                "client": case.client,
                "detail_url": detail_url,
                "detail_label": "Back to case",
                "list_url": _active_cases_list_url(user),
                "calendar_lead": (
                    f"Court dates, attendances, and case tasks for "
                    f"{case.client.get_full_name()}."
                ),
                "calendar_list_hint": (
                    "All litigation dates for this client this month"
                ),
                "calendar_empty_copy": (
                    "Court attendances, next hearing dates, filing dates, "
                    "and case task due dates for this client will appear here."
                ),
                "entity_kind": "case",
            }
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class LitigationCaseActionView(View):
    """Stub workspace pages for litigation case sidebar actions."""

    template_name = "accounts/matter_entity_action.html"

    def get(self, request, role, case_id, action):
        user, denied = _guard_litigation(
            request,
            role,
            action=workspace_detail_permission_action(action),
        )
        if denied:
            return denied
        if action == "update-court-attendance":
            return redirect(
                "accounts:update_court_attendance",
                role=role,
                case_id=case_id,
            )
        if action == "case-calendar":
            return redirect(
                "accounts:case_calendar",
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
        user, denied = _guard_non_litigation(request, role, action="view")
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

        access_denied = _matter_task_access_denied(request, user, matter, "view")
        if access_denied:
            return access_denied

        live_tasks = _live_matter_tasks_for_user(
            matter, user, preferred_id=_preferred_task_id(request)
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
        context.update(
            _entity_live_task_context(
                request, kind="matter", tasks=live_tasks, role=role
            )
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
        user, denied = _guard_non_litigation(request, role, action="attend")
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
            UpdateMatterAttendanceForm(),
            MatterAttendanceQuorumFormSet(prefix="quorum"),
            MatterAttendanceBringUpItemFormSet(prefix="bringups"),
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, matter_id):
        user, denied = _guard_non_litigation(request, role, action="attend")
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
        quorum_formset = MatterAttendanceQuorumFormSet(
            request.POST, prefix="quorum"
        )
        bringup_formset = MatterAttendanceBringUpItemFormSet(
            request.POST, prefix="bringups"
        )
        if not (
            form.is_valid()
            and quorum_formset.is_valid()
            and bringup_formset.is_valid()
        ):
            context = self._context(
                user, matter, form, quorum_formset, bringup_formset
            )
            response = render(request, self.template_name, context)
            return attach_greeting_cookie(response, request)

        with transaction.atomic():
            attendance = form.save(commit=False)
            attendance.matter = matter
            attendance.recorded_by = user
            attendance.save()
            self._save_related(attendance, quorum_formset, bringup_formset)

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

    def _save_related(self, attendance, quorum_formset, bringup_formset):
        quorum_count = 0
        for quorum_form in quorum_formset:
            if not getattr(quorum_form, "cleaned_data", None):
                continue
            if quorum_form.cleaned_data.get("DELETE"):
                continue
            name = (
                quorum_form.cleaned_data.get("participant_name") or ""
            ).strip()
            if not name:
                continue
            MatterAttendanceQuorumMember.objects.create(
                attendance=attendance,
                participant_name=name,
                what_they_said=quorum_form.cleaned_data.get("what_they_said")
                or "",
                sort_order=quorum_count,
            )
            quorum_count += 1

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
            MatterAttendanceBringUpItem.objects.create(
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

    def _context(
        self,
        user,
        matter,
        form,
        quorum_formset,
        bringup_formset,
        **kwargs_edit,
    ):
        detail_url = reverse(
            "accounts:view_non_litigation_matter",
            kwargs={"role": user.role_slug, "matter_id": matter.pk},
        )
        prior_attendances = list(
            matter.matter_attendances.select_related("recorded_by")
            .prefetch_related(
                "quorum_members", "bring_up_items__allocated_to"
            )
            .all()
        )
        edit_form = kwargs_edit.get("edit_form") or UpdateMatterAttendanceForm(
            prefix="edit"
        )
        edit_quorum_formset = kwargs_edit.get(
            "edit_quorum_formset"
        ) or MatterAttendanceQuorumFormSet(prefix="edit-quorum")
        edit_bringup_formset = kwargs_edit.get(
            "edit_bringup_formset"
        ) or MatterAttendanceBringUpItemFormSet(prefix="edit-bringups")
        editing_attendance = kwargs_edit.get("editing_attendance")
        open_edit_modal = bool(kwargs_edit.get("open_edit_modal"))
        attendance_payload = [
            self._serialize_attendance(user, attendance)
            for attendance in prior_attendances
        ]
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
                "quorum_formset": quorum_formset,
                "bringup_formset": bringup_formset,
                "edit_form": edit_form,
                "edit_quorum_formset": edit_quorum_formset,
                "edit_bringup_formset": edit_bringup_formset,
                "editing_attendance": editing_attendance,
                "open_edit_modal": open_edit_modal,
                "detail_url": detail_url,
                "list_url": _active_matters_list_url(user),
                "previous_attendances": prior_attendances,
                "previous_attendances_data": attendance_payload,
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
                "employee_choices": Employee.objects.filter(
                    status=Employee.Status.ACTIVE
                ).order_by("first_name", "last_name", "login_code"),
                "reminder_frequency_choices": (
                    MatterAttendanceBringUpItem.ReminderFrequency.choices
                ),
            }
        )
        return context

    def _serialize_attendance(self, user, attendance):
        edit_url = reverse(
            "accounts:edit_matter_attendance",
            kwargs={
                "role": user.role_slug,
                "matter_id": attendance.matter_id,
                "attendance_id": attendance.pk,
            },
        )
        return {
            "id": attendance.pk,
            "edit_url": edit_url,
            "activity_type": attendance.activity_type,
            "contact_person": attendance.contact_person or "",
            "location": attendance.location or "",
            "attendance_date": (
                attendance.attendance_date.isoformat()
                if attendance.attendance_date
                else ""
            ),
            "attendance_date_display": (
                attendance.attendance_date.strftime("%d %b %Y")
                if attendance.attendance_date
                else "—"
            ),
            "presence": attendance.presence,
            "presence_display": attendance.get_presence_display(),
            "outcome_notes": attendance.outcome_notes or "",
            "description": attendance.description or "",
            "next_action": attendance.next_action or "",
            "next_activity_type": attendance.next_activity_type or "",
            "next_attendance_date": (
                attendance.next_attendance_date.isoformat()
                if attendance.next_attendance_date
                else ""
            ),
            "next_attendance_date_display": (
                attendance.next_attendance_date.strftime("%d %b %Y")
                if attendance.next_attendance_date
                else ""
            ),
            "next_contact_person": attendance.next_contact_person or "",
            "next_client_attendance": attendance.next_client_attendance or "",
            "next_client_attendance_display": (
                attendance.get_next_client_attendance_display()
                if attendance.next_client_attendance
                else ""
            ),
            "virtual_link": attendance.virtual_link or "",
            "recorded_by": (
                attendance.recorded_by.get_full_name()
                if attendance.recorded_by
                else ""
            ),
            "quorum_members": [
                {
                    "participant_name": member.participant_name,
                    "what_they_said": member.what_they_said or "",
                }
                for member in attendance.quorum_members.all()
            ],
            "bring_up_items": [
                {
                    "description": item.description,
                    "reminder_frequency": item.reminder_frequency or "",
                    "reminder_frequency_display": (
                        item.get_reminder_frequency_display()
                        if item.reminder_frequency
                        else ""
                    ),
                    "allocated_to": item.allocated_to_id or "",
                    "allocated_to_name": (
                        (
                            f"{item.allocated_to.get_full_name()} "
                            f"({item.allocated_to.get_role_display()})"
                        )
                        if item.allocated_to
                        else ""
                    ),
                }
                for item in attendance.bring_up_items.all()
            ],
        }


@method_decorator(login_required, name="dispatch")
class EditMatterAttendanceView(View):
    """Update an existing matter attendance record."""

    template_name = "accounts/update_matter_attendance.html"
    action_slug = "update-matter-attendance"

    def get_matter(self, matter_id):
        return get_object_or_404(
            NonLitigationMatter.objects.select_related(
                "client", "assigned_to", "registered_by"
            ),
            pk=matter_id,
        )

    def get_attendance(self, matter, attendance_id):
        return get_object_or_404(
            MatterAttendance.objects.select_related("recorded_by").prefetch_related(
                "quorum_members", "bring_up_items__allocated_to"
            ),
            pk=attendance_id,
            matter=matter,
        )

    def get(self, request, role, matter_id, attendance_id):
        user, denied = _guard_non_litigation(request, role, action="attend")
        if denied:
            return denied

        matter = self.get_matter(matter_id)
        if matter.status == NonLitigationMatter.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_non_litigation_matter",
                role=role,
                matter_id=matter.pk,
            )

        attendance = self.get_attendance(matter, attendance_id)
        create_view = UpdateMatterAttendanceView()
        create_view.request = request
        context = create_view._context(
            user,
            matter,
            UpdateMatterAttendanceForm(),
            MatterAttendanceQuorumFormSet(prefix="quorum"),
            MatterAttendanceBringUpItemFormSet(prefix="bringups"),
            edit_form=UpdateMatterAttendanceForm(
                instance=attendance, prefix="edit"
            ),
            edit_quorum_formset=self._quorum_formset(attendance),
            edit_bringup_formset=self._bringup_formset(attendance),
            editing_attendance=attendance,
            open_edit_modal=True,
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, matter_id, attendance_id):
        user, denied = _guard_non_litigation(request, role, action="attend")
        if denied:
            return denied

        matter = self.get_matter(matter_id)
        if matter.status == NonLitigationMatter.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_non_litigation_matter",
                role=role,
                matter_id=matter.pk,
            )

        attendance = self.get_attendance(matter, attendance_id)
        form = UpdateMatterAttendanceForm(
            request.POST, instance=attendance, prefix="edit"
        )
        quorum_formset = MatterAttendanceQuorumFormSet(
            request.POST, prefix="edit-quorum"
        )
        bringup_formset = MatterAttendanceBringUpItemFormSet(
            request.POST, prefix="edit-bringups"
        )
        if not (
            form.is_valid()
            and quorum_formset.is_valid()
            and bringup_formset.is_valid()
        ):
            create_view = UpdateMatterAttendanceView()
            create_view.request = request
            context = create_view._context(
                user,
                matter,
                UpdateMatterAttendanceForm(),
                MatterAttendanceQuorumFormSet(prefix="quorum"),
                MatterAttendanceBringUpItemFormSet(prefix="bringups"),
                edit_form=form,
                edit_quorum_formset=quorum_formset,
                edit_bringup_formset=bringup_formset,
                editing_attendance=attendance,
                open_edit_modal=True,
            )
            response = render(request, self.template_name, context)
            return attach_greeting_cookie(response, request)

        with transaction.atomic():
            form.save()
            attendance.quorum_members.all().delete()
            attendance.bring_up_items.all().delete()
            create_view = UpdateMatterAttendanceView()
            create_view._save_related(
                attendance, quorum_formset, bringup_formset
            )

        messages.success(
            request,
            f"Matter attendance updated for "
            f"{attendance.attendance_date.strftime('%d/%m/%Y')}.",
        )
        return redirect(
            "accounts:update_matter_attendance",
            role=role,
            matter_id=matter.pk,
        )

    def _quorum_formset(self, attendance):
        initial = [
            {
                "participant_name": member.participant_name,
                "what_they_said": member.what_they_said,
            }
            for member in attendance.quorum_members.all()
        ]
        return MatterAttendanceQuorumFormSet(
            prefix="edit-quorum",
            initial=initial,
        )

    def _bringup_formset(self, attendance):
        initial = [
            {
                "description": item.description,
                "reminder_frequency": item.reminder_frequency,
                "allocated_to": item.allocated_to_id,
            }
            for item in attendance.bring_up_items.all()
        ]
        return MatterAttendanceBringUpItemFormSet(
            prefix="edit-bringups",
            initial=initial,
        )


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
        user, denied = _guard_non_litigation(request, role, action="task")
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
        user, denied = _guard_non_litigation(request, role, action="task")
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

        access = form.cleaned_access_permissions()
        task = MatterTask.objects.create(
            matter=matter,
            assignee=form.cleaned_data["assigned_to"],
            title=form.cleaned_data["title"].strip(),
            instructions=form.cleaned_data.get("instructions") or "",
            due_date=form.cleaned_data["due_date"],
            created_by=user,
            **access,
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
        user, denied = _guard_non_litigation(request, role, action="upload")
        if denied:
            return denied

        matter = self.get_matter(matter_id)
        if matter.status == NonLitigationMatter.Status.PENDING_APPROVAL:
            return redirect(
                "accounts:approve_non_litigation_matter",
                role=role,
                matter_id=matter.pk,
            )

        access_denied = _matter_task_access_denied(
            request,
            user,
            matter,
            "view",
            redirect_to=reverse(
                "accounts:view_non_litigation_matter",
                kwargs={"role": role, "matter_id": matter.pk},
            ),
        )
        if access_denied:
            return access_denied

        party_type_choices = MatterParty.PartyType.choices
        context = self._context(
            user,
            matter,
            CreateGoogleDocumentForm(
                prefix="create",
                auto_id="create_%s",
                party_type_choices=party_type_choices,
            ),
            UploadDocumentForm(
                prefix="upload",
                auto_id="upload_%s",
                party_type_choices=party_type_choices,
            ),
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def post(self, request, role, matter_id):
        user, denied = _guard_non_litigation(request, role, action="upload")
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
        permission_by_action = {
            "create_google": "upload",
            "upload": "upload",
            "rename": "edit",
            "delete": "delete",
        }
        needed = permission_by_action.get(action, "upload")
        library_url = reverse(
            "accounts:upload_matter_documents",
            kwargs={"role": role, "matter_id": matter.pk},
        )
        access_denied = _matter_task_access_denied(
            request,
            user,
            matter,
            needed,
            redirect_to=f"{library_url}#docs-library",
        )
        if access_denied:
            return access_denied

        party_type_choices = MatterParty.PartyType.choices
        create_form = CreateGoogleDocumentForm(
            prefix="create",
            auto_id="create_%s",
            party_type_choices=party_type_choices,
        )
        upload_form = UploadDocumentForm(
            prefix="upload",
            auto_id="upload_%s",
            party_type_choices=party_type_choices,
        )

        try:
            if action == "create_google":
                create_form = CreateGoogleDocumentForm(
                    request.POST,
                    prefix="create",
                    auto_id="create_%s",
                    party_type_choices=party_type_choices,
                )
                if create_form.is_valid():
                    self._create_google_doc(user, matter, create_form)
                    return self._library_redirect(role, matter.pk)
            elif action == "upload":
                upload_form = UploadDocumentForm(
                    request.POST,
                    request.FILES,
                    prefix="upload",
                    auto_id="upload_%s",
                    party_type_choices=party_type_choices,
                )
                if upload_form.is_valid():
                    self._upload_file(user, matter, upload_form)
                    return self._library_redirect(role, matter.pk)
            elif action == "rename":
                self._rename_document(request, matter)
                return self._library_redirect(role, matter.pk)
            elif action == "delete":
                self._delete_document(request, matter)
                return self._library_redirect(role, matter.pk)
            else:
                messages.error(request, "Unknown document action.")
                return self._library_redirect(role, matter.pk)
        except (GoogleDriveAPIError, GoogleDriveOAuthError) as exc:
            messages.error(request, str(exc))
            return self._library_redirect(role, matter.pk)

        context = self._context(user, matter, create_form, upload_form)
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)

    def _create_google_doc(self, user, matter, form):
        connection = GoogleDriveConnection.get_solo()
        if not connection.is_connected:
            raise GoogleDriveAPIError(
                "Connect Google Drive in settings before creating documents."
            )
        title = form.cleaned_data["title"]
        google_type = form.cleaned_data["google_type"]
        description = form.cleaned_data["description"]
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
            **form.party_type_kwargs(),
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
            **form.party_type_kwargs(),
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
            Document,
            pk=request.POST.get("document_id"),
            matter=matter,
        )
        form = RenameDocumentForm(
            request.POST,
            party_type_choices=MatterParty.PartyType.choices,
        )
        if not form.is_valid():
            messages.error(
                request,
                "Enter a valid document name and party type.",
            )
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
        document.party_type = form.cleaned_data.get("party_type") or ""
        document.save(
            update_fields=[
                "title",
                "description",
                "notes",
                "party_type",
                "updated_at",
            ]
        )
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

    def _library_redirect(self, role, matter_id):
        url = reverse(
            "accounts:upload_matter_documents",
            kwargs={"role": role, "matter_id": matter_id},
        )
        return redirect(f"{url}#docs-library")

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
        party_type_choices = MatterParty.PartyType.choices
        edit_form = RenameDocumentForm(
            auto_id="edit_%s",
            party_type_choices=party_type_choices,
        )
        documents = _documents_with_activity(
            matter.documents.all(),
            actor=user,
            sync_google=True,
            role=user.role_slug,
        )
        task_access = MatterTask.effective_access_for(user, matter)
        if task_access is None:
            task_access = {
                "allow_view": True,
                "allow_edit": True,
                "allow_download": True,
                "allow_delete": True,
                "allow_upload": True,
            }
        context.update(
            {
                "case": None,
                "matter": matter,
                "entity_kind": self.entity_kind,
                "entity_label": matter.matter_title,
                "create_form": create_form,
                "upload_form": upload_form,
                "edit_form": edit_form,
                "party_type_choices": party_type_choices,
                "documents": documents,
                "document_groups": _group_documents_by_party_type(
                    documents, party_type_choices
                ),
                "detail_url": detail_url,
                "detail_label": "Back to matter",
                "list_url": _active_matters_list_url(user),
                "google_drive_connected": connection.is_connected,
                "google_drive_settings_url": user.workspace_url(
                    "dashboard", "google-drive-settings"
                ),
                "task_access": task_access,
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
        user, denied = _guard_litigation(request, role, action="audit")
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
class EmployeePerformanceAnalyticsView(View):
    """Detailed performance analytics for a single employee."""

    template_name = "accounts/employee_performance_analytics.html"

    def get(self, request, role, employee_id):
        user, denied = _guard_perm(
            request,
            role,
            module=_USER_MODULE,
            activity="performance-compliance",
            action="view",
        )
        if denied:
            return denied

        employee = get_object_or_404(
            Employee.objects.filter(
                status__in=[
                    Employee.Status.ACTIVE,
                    Employee.Status.SUSPENDED,
                ]
            ),
            pk=employee_id,
        )
        days_raw = (request.GET.get("range") or "90").strip()
        days = 90
        if days_raw in {"7", "30", "90"}:
            days = int(days_raw)
        active_tab = (request.GET.get("tab") or "overview").strip().lower()
        if active_tab not in {"overview", "visuals"}:
            active_tab = "overview"
        analytics = build_employee_performance_analytics(employee, days=days)
        trail = [
            "dashboard",
            "user-management",
            "employee-management",
            "performance-compliance",
        ]
        context = workspace_context(
            user,
            request=request,
            page_title="Employee performance",
            page_trail=trail,
            active_page="performance-compliance",
        )
        context.update(
            {
                "employee": employee,
                "analytics": analytics,
                "range_days": days,
                "active_tab": active_tab,
                "performance_list_url": user.workspace_url(*trail),
            }
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class BlogPostAnalyticsView(View):
    """Website conversion and interaction analytics for a published blog post."""

    template_name = "accounts/blog_analytics.html"

    def get(self, request, role, post_id):
        user = request.user
        if user.status != Employee.Status.ACTIVE:
            return redirect_for_employee(request, user)
        if role != user.role_slug:
            return redirect(
                reverse(
                    "accounts:blog_post_analytics",
                    kwargs={"role": user.role_slug, "post_id": post_id},
                )
            )
        post = get_object_or_404(
            EmployeeBlogPost.objects.select_related("author", "approved_by"),
            pk=post_id,
            status=EmployeeBlogPost.Status.PUBLISHED,
        )
        days_raw = (request.GET.get("range") or "30").strip()
        days = 30
        if days_raw in {"7", "30", "90"}:
            days = int(days_raw)
        analytics = post.web_analytics(days=days)
        trail = ["dashboard", "research-blogs"]
        context = workspace_context(
            user,
            request=request,
            page_title="Blog analytics",
            page_trail=trail,
            active_page="research-blogs",
        )
        context.update(
            {
                "blog_post": post,
                "analytics": analytics,
                "range_days": days,
                "research_blogs_url": user.workspace_url(
                    "dashboard", "research-blogs"
                ),
                "public_post_url": post.get_absolute_url(),
                "review_url": reverse(
                    "accounts:review_company_blog",
                    kwargs={"role": user.role_slug, "post_id": post.pk},
                ),
            }
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class DocumentActivityAnalyticsView(View):
    """Detailed activity analytics for a single document."""

    template_name = "accounts/document_activity.html"

    def get(self, request, role, document_id):
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
        user, denied = _guard_entity_document(
            request, role, document, action="audit"
        )
        if denied:
            return denied

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
        document = get_object_or_404(
            Document.objects.select_related("case", "matter", "uploaded_by"),
            pk=document_id,
        )
        user, denied = _guard_entity_document(
            request, role, document, action="upload"
        )
        if denied:
            return denied

        if document.case_id:
            access_denied = _case_task_access_denied(
                request,
                user,
                document.case,
                "view",
                redirect_to=_document_library_return_url(document, role),
            )
            if access_denied:
                return access_denied
        elif document.matter_id:
            access_denied = _matter_task_access_denied(
                request,
                user,
                document.matter,
                "view",
                redirect_to=_document_library_return_url(document, role),
            )
            if access_denied:
                return access_denied

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
    """Log a download, then serve the file (local or from Google Drive)."""

    def get(self, request, role, document_id):
        document = get_object_or_404(
            Document.objects.select_related("case", "matter"),
            pk=document_id,
        )
        user, denied = _guard_entity_document(
            request, role, document, action="upload"
        )
        if denied:
            return denied

        if document.case_id:
            access_denied = _case_task_access_denied(
                request,
                user,
                document.case,
                "download",
                redirect_to=_document_library_return_url(document, role),
            )
            if access_denied:
                return access_denied
        elif document.matter_id:
            access_denied = _matter_task_access_denied(
                request,
                user,
                document.matter,
                "download",
                redirect_to=_document_library_return_url(document, role),
            )
            if access_denied:
                return access_denied

        log_document_activity(
            document,
            user,
            DocumentActivity.Action.DOWNLOADED,
            detail=document.original_filename or document.title,
        )

        if document.local_file:
            filename = (
                document.original_filename
                or document.local_file.name.rsplit("/", 1)[-1]
                or document.title
                or "document"
            )
            return FileResponse(
                document.local_file.open("rb"),
                as_attachment=True,
                filename=filename,
            )

        if document.drive_file_id:
            try:
                content, filename, content_type = download_drive_file(
                    document.drive_file_id,
                    mime_type=document.mime_type or "",
                    title=document.title or "",
                    original_filename=document.original_filename or "",
                )
            except GoogleDriveAPIError as exc:
                messages.error(request, str(exc))
                return redirect(_document_library_return_url(document, role))
            response = HttpResponse(content, content_type=content_type)
            safe_name = (filename or document.title or "document").replace('"', "")
            response["Content-Disposition"] = f'attachment; filename="{safe_name}"'
            return response

        messages.error(request, "No downloadable file is available.")
        return redirect(_document_library_return_url(document, role))


@method_decorator(login_required, name="dispatch")
class DocumentSessionPingView(View):
    """Heartbeat / end endpoint for an open document session."""

    def post(self, request, role, document_id, session_id):
        session = get_object_or_404(
            DocumentOpenSession.objects.select_related("document"),
            pk=session_id,
            document_id=document_id,
            actor=request.user,
        )
        user, denied = _guard_entity_document(
            request, role, session.document, action="upload"
        )
        if denied:
            return JsonResponse({"ok": False, "error": "unauthorized"}, status=403)

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
class MatterCalendarView(View):
    """Month calendar of dates for a client's non-litigation matters."""

    template_name = "accounts/entity_calendar.html"
    action_slug = "matter-calendar"

    def get(self, request, role, matter_id):
        user, denied = _guard_non_litigation(request, role, action="view")
        if denied:
            return denied

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

        today, year, month, month_start, month_end = _calendar_month_from_request(
            request
        )
        by_day = _client_matter_calendar_by_day(
            user, matter.client, month_start, month_end
        )
        base_url = reverse(
            "accounts:matter_calendar",
            kwargs={"role": role, "matter_id": matter.pk},
        )
        detail_url = reverse(
            "accounts:view_non_litigation_matter",
            kwargs={"role": role, "matter_id": matter.pk},
        )
        context = workspace_context(
            user,
            request=request,
            page_title="Matter calendar",
            page_trail=list(ACTIVE_MATTERS_TRAIL),
            active_page=self.action_slug,
            page_nav_items=non_litigation_matter_nav_items(
                user.role_slug, matter.pk, active_slug=self.action_slug
            ),
        )
        context.update(
            _calendar_grid_payload(today, year, month, by_day, base_url)
        )
        context.update(
            {
                "matter": matter,
                "client": matter.client,
                "detail_url": detail_url,
                "detail_label": "Back to matter",
                "list_url": _active_matters_list_url(user),
                "calendar_lead": (
                    f"Matter dates, attendances, and tasks for "
                    f"{matter.client.get_full_name()}."
                ),
                "calendar_list_hint": (
                    "All non-litigation dates for this client this month"
                ),
                "calendar_empty_copy": (
                    "Matter attendances, next attendance dates, opened dates, "
                    "and matter task due dates for this client will appear here."
                ),
                "entity_kind": "matter",
            }
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class NonLitigationMatterActionView(View):
    """Stub workspace pages for non-litigation matter sidebar actions."""

    template_name = "accounts/matter_entity_action.html"

    def get(self, request, role, matter_id, action):
        user, denied = _guard_non_litigation(
            request,
            role,
            action=workspace_detail_permission_action(action),
        )
        if denied:
            return denied
        if action == "update-matter-attendance":
            return redirect(
                "accounts:update_matter_attendance",
                role=role,
                matter_id=matter_id,
            )
        if action == "matter-calendar":
            return redirect(
                "accounts:matter_calendar",
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
    """Assignee opens an accepted case task by landing on the related case."""

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
        user, denied = _guard_litigation(request, role, action="task")
        if denied:
            return denied

        task = self.get_task(task_id, user)
        case = task.case

        if task.status in {CaseTask.Status.ACCEPTED, CaseTask.Status.DONE}:
            case_url = reverse(
                "accounts:view_litigation_case",
                kwargs={"role": role, "case_id": case.pk},
            )
            if task.status == CaseTask.Status.ACCEPTED:
                return redirect(f"{case_url}?task={task.pk}")
            return redirect(case_url)

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
                "open_url": "",
                "can_open": False,
            }
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class ViewMatterTaskView(View):
    """Assignee opens an accepted matter task by landing on the related matter."""

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
        user, denied = _guard_non_litigation(request, role, action="task")
        if denied:
            return denied

        task = self.get_task(task_id, user)
        matter = task.matter

        if task.status in {MatterTask.Status.ACCEPTED, MatterTask.Status.DONE}:
            matter_url = reverse(
                "accounts:view_non_litigation_matter",
                kwargs={"role": role, "matter_id": matter.pk},
            )
            if task.status == MatterTask.Status.ACCEPTED:
                return redirect(f"{matter_url}?task={task.pk}")
            return redirect(matter_url)

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
                "open_url": "",
                "can_open": False,
            }
        )
        response = render(request, self.template_name, context)
        return attach_greeting_cookie(response, request)


@method_decorator(login_required, name="dispatch")
class CompleteCaseTaskView(View):
    """Assignee marks an accepted case task as done."""

    kind = "case"
    complete_url_name = "accounts:complete_case_task"
    entity_url_name = "accounts:view_litigation_case"
    entity_id_kwarg = "case_id"

    def get_task(self, task_id, user):
        return get_object_or_404(
            CaseTask.objects.select_related("case", "created_by", "assignee"),
            pk=task_id,
            assignee=user,
        )

    def entity_id(self, task):
        return task.case_id

    def entity_redirect(self, role, task):
        return redirect(
            self.entity_url_name,
            role=role,
            **{self.entity_id_kwarg: self.entity_id(task)},
        )

    def post(self, request, role, task_id):
        guard = (
            _guard_litigation
            if self.kind == "case"
            else _guard_non_litigation
        )
        user, denied = guard(request, role, action="task")
        if denied:
            return denied

        task = self.get_task(task_id, user)
        accepted = (
            CaseTask.Status.ACCEPTED
            if self.kind == "case"
            else MatterTask.Status.ACCEPTED
        )
        done = (
            CaseTask.Status.DONE
            if self.kind == "case"
            else MatterTask.Status.DONE
        )

        if task.status != accepted:
            messages.info(request, "Only an accepted task can be marked complete.")
            return self._redirect_after_complete(request, role, task)

        task.status = done
        task.responded_at = task.responded_at or timezone.now()
        task.save(update_fields=["status", "responded_at", "updated_at"])
        notified = notify_task_completed(task, kind=self.kind)
        if notified and notified.recipient_id != user.pk:
            messages.success(
                request,
                "Task marked as complete. The employee who allocated it has been notified.",
            )
        else:
            messages.success(request, "Task marked as complete.")
        return self._redirect_after_complete(request, role, task)

    def _redirect_after_complete(self, request, role, task):
        next_url = (request.POST.get("next") or "").strip()
        if next_url.startswith("/") and not next_url.startswith("//"):
            return redirect(next_url)
        return self.entity_redirect(role, task)


@method_decorator(login_required, name="dispatch")
class CompleteMatterTaskView(CompleteCaseTaskView):
    """Assignee marks an accepted matter task as done."""

    kind = "matter"
    complete_url_name = "accounts:complete_matter_task"
    entity_url_name = "accounts:view_non_litigation_matter"
    entity_id_kwarg = "matter_id"

    def get_task(self, task_id, user):
        return get_object_or_404(
            MatterTask.objects.select_related("matter", "created_by", "assignee"),
            pk=task_id,
            assignee=user,
        )

    def entity_id(self, task):
        return task.matter_id


@method_decorator(login_required, name="dispatch")
class RespondCaseTaskView(View):
    """Assignee accepts or rejects a case task (reject requires a reason)."""

    kind = "case"
    respond_url_name = "accounts:respond_case_task"
    view_url_name = "accounts:view_case_task"
    entity_url_name = "accounts:view_litigation_case"
    entity_id_kwarg = "case_id"

    def get_task(self, task_id, user):
        return get_object_or_404(
            CaseTask.objects.select_related("case", "created_by", "assignee"),
            pk=task_id,
            assignee=user,
        )

    def task_subject(self, task):
        return str(task.case)

    def entity_id(self, task):
        return task.case_id

    def accepted_redirect(self, role, task):
        entity_url = reverse(
            self.entity_url_name,
            kwargs={"role": role, self.entity_id_kwarg: self.entity_id(task)},
        )
        return redirect(f"{entity_url}?task={task.pk}")

    def post(self, request, role, task_id):
        guard = (
            _guard_litigation
            if self.kind == "case"
            else _guard_non_litigation
        )
        user, denied = guard(request, role, action="task")
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
            if task.status == CaseTask.Status.ACCEPTED:
                return self.accepted_redirect(role, task)
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
            return self.accepted_redirect(role, task)

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
    entity_url_name = "accounts:view_non_litigation_matter"
    entity_id_kwarg = "matter_id"

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

    def entity_id(self, task):
        return task.matter_id


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
