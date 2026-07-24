"""Client portal module views — always scoped to the session client."""

from __future__ import annotations

import os

from django.contrib import messages
from django.http import FileResponse, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from .client_access import (
    client_calendar_by_day,
    client_cases,
    client_document_catalog,
    client_documents,
    client_matters,
    client_owns_drive_file,
    client_reminders,
    get_object_or_404_case,
    get_object_or_404_document,
    get_object_or_404_matter,
)
from .client_portal import client_portal_context
from .forms import ClientAccountSettingsForm, ClientAppearanceSettingsForm
from .google_drive import (
    GoogleDriveAPIError,
    download_drive_file,
    get_drive_file_meta,
    preview_drive_file,
)
from .models import ClientNotification, CompanyThemeSetting, Employee
from .appearance import (
    appearance_catalog,
    sync_session_client_appearance,
)


class ClientMattersView(View):
    template_name = "accounts/client_matters.html"

    def get(self, request):
        from .views import _require_active_client

        client, denied = _require_active_client(request)
        if denied:
            return denied

        cases = list(client_cases(client))
        matters = list(client_matters(client))
        context = client_portal_context(
            request, client, page_title="My matters", active="matters"
        )
        context.update(
            {
                "cases": cases,
                "matters": matters,
                "case_count": len(cases),
                "matter_count": len(matters),
            }
        )
        return render(request, self.template_name, context)


class ClientMatterCaseView(View):
    template_name = "accounts/client_matter_case.html"

    def get(self, request, case_id):
        from .views import _require_active_client

        client, denied = _require_active_client(request)
        if denied:
            return denied

        case = get_object_or_404_case(client, case_id)
        attendances = list(
            case.court_attendances.select_related("recorded_by").order_by(
                "-attendance_date", "-pk"
            )[:12]
        )
        documents = list(
            client_documents(client).filter(case=case)[:20]
        )
        for doc in documents:
            doc.client_view_url = reverse(
                "accounts:client_document_view", kwargs={"document_id": doc.pk}
            )
        context = client_portal_context(
            request,
            client,
            page_title=str(case),
            active="matters",
        )
        context.update(
            {
                "case": case,
                "attendances": attendances,
                "documents": documents,
                "list_url": reverse("accounts:client_matters"),
            }
        )
        return render(request, self.template_name, context)


class ClientMatterDetailView(View):
    template_name = "accounts/client_matter_detail.html"

    def get(self, request, matter_id):
        from .views import _require_active_client

        client, denied = _require_active_client(request)
        if denied:
            return denied

        matter = get_object_or_404_matter(client, matter_id)
        attendances = list(
            matter.matter_attendances.select_related("recorded_by").order_by(
                "-attendance_date", "-pk"
            )[:12]
        )
        documents = list(
            client_documents(client).filter(matter=matter)[:20]
        )
        for doc in documents:
            doc.client_view_url = reverse(
                "accounts:client_document_view", kwargs={"document_id": doc.pk}
            )
        context = client_portal_context(
            request,
            client,
            page_title=matter.matter_title,
            active="matters",
        )
        context.update(
            {
                "matter": matter,
                "attendances": attendances,
                "documents": documents,
                "list_url": reverse("accounts:client_matters"),
            }
        )
        return render(request, self.template_name, context)


class ClientDocumentsView(View):
    template_name = "accounts/client_documents.html"

    def get(self, request):
        from .views import _require_active_client

        client, denied = _require_active_client(request)
        if denied:
            return denied

        documents = client_document_catalog(client)
        context = client_portal_context(
            request, client, page_title="Documents", active="documents"
        )
        context.update(
            {
                "documents": documents,
                "document_count": len(documents),
            }
        )
        return render(request, self.template_name, context)


class ClientDocumentView(View):
    """Read-only viewer page for a Document belonging to the session client."""

    template_name = "accounts/client_document_view.html"

    def get(self, request, document_id):
        from .views import _require_active_client

        client, denied = _require_active_client(request)
        if denied:
            return denied

        document = get_object_or_404_document(client, document_id)
        if not (document.local_file or document.drive_file_id):
            messages.error(request, "This document cannot be viewed.")
            return redirect("accounts:client_documents")

        context = client_portal_context(
            request,
            client,
            page_title=document.title,
            active="documents",
        )
        context.update(
            {
                "document_title": document.title,
                "document_type": document.type_label,
                "list_url": reverse("accounts:client_documents"),
                "file_url": reverse(
                    "accounts:client_document_file",
                    kwargs={"document_id": document.pk},
                ),
            }
        )
        return render(request, self.template_name, context)


class ClientDocumentFileView(View):
    """Stream document bytes inline (view-only) for the session client."""

    def get(self, request, document_id):
        from .views import _require_active_client

        client, denied = _require_active_client(request)
        if denied:
            return denied

        document = get_object_or_404_document(client, document_id)

        # Prefer a readable local file; otherwise fall back to Drive preview.
        if document.local_file:
            try:
                local_path = document.local_file.path
            except Exception:
                local_path = ""
            if local_path and os.path.isfile(local_path):
                filename = (
                    document.original_filename
                    or document.local_file.name.rsplit("/", 1)[-1]
                    or document.title
                    or "document"
                )
                return FileResponse(
                    document.local_file.open("rb"),
                    as_attachment=False,
                    filename=filename,
                )

        if document.drive_file_id:
            try:
                content, filename, content_type = preview_drive_file(
                    document.drive_file_id,
                    mime_type=document.mime_type or "",
                    title=document.title or "",
                    original_filename=document.original_filename or "",
                )
            except GoogleDriveAPIError as exc:
                messages.error(request, str(exc))
                return redirect("accounts:client_documents")
            response = HttpResponse(content, content_type=content_type)
            safe_name = (filename or document.title or "document").replace('"', "")
            response["Content-Disposition"] = f'inline; filename="{safe_name}"'
            return response

        messages.error(request, "No viewable file is available.")
        return redirect("accounts:client_documents")


class ClientDriveDocumentView(View):
    """Read-only viewer for a Drive file under the session client's matters."""

    template_name = "accounts/client_document_view.html"

    def get(self, request, drive_file_id):
        from .views import _require_active_client

        client, denied = _require_active_client(request)
        if denied:
            return denied

        drive_file_id = (drive_file_id or "").strip()
        if not client_owns_drive_file(client, drive_file_id):
            messages.error(request, "That document is not available on your account.")
            return redirect("accounts:client_documents")

        title = "Document"
        try:
            meta = get_drive_file_meta(drive_file_id)
            title = meta.get("name") or title
            type_label = meta.get("mimeType") or "File"
        except GoogleDriveAPIError:
            type_label = "File"

        context = client_portal_context(
            request, client, page_title=title, active="documents"
        )
        context.update(
            {
                "document_title": title,
                "document_type": type_label,
                "list_url": reverse("accounts:client_documents"),
                "file_url": reverse(
                    "accounts:client_drive_document_file",
                    kwargs={"drive_file_id": drive_file_id},
                ),
            }
        )
        return render(request, self.template_name, context)


class ClientDriveDocumentFileView(View):
    """Stream a Drive file inline when it belongs to the session client."""

    def get(self, request, drive_file_id):
        from .views import _require_active_client

        client, denied = _require_active_client(request)
        if denied:
            return denied

        drive_file_id = (drive_file_id or "").strip()
        if not client_owns_drive_file(client, drive_file_id):
            messages.error(request, "That document is not available on your account.")
            return redirect("accounts:client_documents")

        mime_type = ""
        title = "document"
        try:
            meta = get_drive_file_meta(drive_file_id)
            mime_type = meta.get("mimeType") or ""
            title = meta.get("name") or title
        except GoogleDriveAPIError:
            pass

        try:
            content, filename, content_type = preview_drive_file(
                drive_file_id,
                mime_type=mime_type,
                title=title,
            )
        except GoogleDriveAPIError as exc:
            messages.error(request, str(exc))
            return redirect("accounts:client_documents")

        response = HttpResponse(content, content_type=content_type)
        safe_name = (filename or title or "document").replace('"', "")
        response["Content-Disposition"] = f'inline; filename="{safe_name}"'
        return response


class ClientDocumentDownloadView(View):
    """Download a document only if it belongs to the session client."""

    def get(self, request, document_id):
        from .views import _require_active_client

        client, denied = _require_active_client(request)
        if denied:
            return denied

        document = get_object_or_404_document(client, document_id)

        if document.local_file:
            try:
                local_path = document.local_file.path
            except Exception:
                local_path = ""
            if local_path and os.path.isfile(local_path):
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
                return redirect("accounts:client_documents")
            response = HttpResponse(content, content_type=content_type)
            safe_name = (filename or document.title or "document").replace('"', "")
            response["Content-Disposition"] = f'attachment; filename="{safe_name}"'
            return response

        messages.error(request, "No downloadable file is available.")
        return redirect("accounts:client_documents")


class ClientMessagesView(View):
    template_name = "accounts/client_messages.html"

    def get(self, request):
        from .views import _require_active_client

        client, denied = _require_active_client(request)
        if denied:
            return denied

        message_list = list(
            ClientNotification.objects.filter(
                recipient=client,
                category=ClientNotification.Category.MESSAGE,
            ).order_by("-created_at")
        )
        unread_count = sum(1 for item in message_list if not item.is_read)
        # Opening the inbox marks message notifications read.
        if unread_count:
            ClientNotification.objects.filter(
                recipient=client,
                category=ClientNotification.Category.MESSAGE,
                is_read=False,
            ).update(is_read=True, read_at=timezone.now())
            for item in message_list:
                item.is_read = True

        context = client_portal_context(
            request, client, page_title="Messages", active="messages"
        )
        context.update(
            {
                "message_notifications": message_list,
                "message_count": len(message_list),
                "message_unread_count": unread_count,
            }
        )
        return render(request, self.template_name, context)


class ClientRemindersView(View):
    template_name = "accounts/client_reminders.html"

    def get(self, request):
        from .views import _require_active_client

        client, denied = _require_active_client(request)
        if denied:
            return denied

        reminders = client_reminders(client)
        due = [item for item in reminders if item["is_due"]]
        upcoming = [item for item in reminders if not item["is_due"]]
        context = client_portal_context(
            request, client, page_title="Reminders", active="reminders"
        )
        context.update(
            {
                "reminders": reminders,
                "due_reminders": due,
                "upcoming_reminders": upcoming,
                "due_reminder_count": len(due),
                "upcoming_reminder_count": len(upcoming),
            }
        )
        return render(request, self.template_name, context)


class ClientCalendarView(View):
    template_name = "accounts/client_calendar.html"

    def get(self, request):
        from .views import (
            _calendar_grid_payload,
            _calendar_month_from_request,
            _require_active_client,
        )

        client, denied = _require_active_client(request)
        if denied:
            return denied

        today, year, month, month_start, month_end = _calendar_month_from_request(
            request
        )
        by_day = client_calendar_by_day(client, month_start, month_end)
        base_url = reverse("accounts:client_calendar")
        payload = _calendar_grid_payload(today, year, month, by_day, base_url)
        payload.update(
            {
                "calendar_lead": (
                    "Court dates and attendances on matters registered for "
                    "your account only."
                ),
                "calendar_list_hint": "Your upcoming and recorded attendances",
                "calendar_empty_copy": (
                    "When the firm records court or matter dates on your files, "
                    "they will appear here."
                ),
                "calendar_shows_cases_matters": True,
                "calendar_legend_kinds": ("court", "matter_attendance"),
            }
        )
        context = client_portal_context(
            request, client, page_title="Calendar", active="calendar"
        )
        context.update(payload)
        return render(request, self.template_name, context)


class ClientSettingsView(View):
    template_name = "accounts/client_settings.html"

    def get(self, request):
        from .views import _require_active_client

        client, denied = _require_active_client(request)
        if denied:
            return denied

        context = client_portal_context(
            request, client, page_title="Account settings", active="settings"
        )
        context["form"] = ClientAccountSettingsForm(client=client)
        context["has_password"] = bool(client.password)
        return render(request, self.template_name, context)

    def post(self, request):
        from .views import _require_active_client

        client, denied = _require_active_client(request)
        if denied:
            return denied

        form = ClientAccountSettingsForm(
            request.POST, request.FILES, client=client
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Your account settings have been updated.")
            return redirect("accounts:client_settings")

        context = client_portal_context(
            request, client, page_title="Account settings", active="settings"
        )
        context["form"] = form
        context["has_password"] = bool(client.password)
        return render(request, self.template_name, context)


def _client_theme_settings_context(client, *, appearance_form=None):
    form = appearance_form or ClientAppearanceSettingsForm(instance=client)
    form_theme = form["ui_theme"].value() or client.ui_theme
    company = CompanyThemeSetting.get_solo()
    company_css = company.resolved_theme()
    company_theme_key = (
        Employee.UiTheme.DEFAULT
        if company_css == Employee.UiTheme.PRODUCT
        else company_css
    )
    company_theme_label = dict(Employee.UiTheme.choices).get(
        company_theme_key, "Black & White"
    )
    catalog = appearance_catalog(
        current_theme=form_theme,
        company_theme_label=company_theme_label,
        company_theme_preview=company.default_ui_theme,
    )
    theme_key = form_theme or Employee.UiTheme.DEFAULT
    if theme_key == Employee.UiTheme.DEFAULT:
        current_theme_label = f"Company default ({company_theme_label})"
    else:
        current_theme_label = dict(Employee.UiTheme.choices).get(
            theme_key,
            "Black & White",
        )
    font_value = form["ui_font"].value() or client.portal_font
    density_value = form["ui_density"].value() or client.portal_density
    return {
        "appearance_form": form,
        "theme_groups": catalog["theme_groups"],
        "font_catalog": catalog["font_catalog"],
        "density_catalog": catalog["density_catalog"],
        "theme_count": catalog["theme_count"],
        "font_count": catalog["font_count"],
        "current_theme_label": current_theme_label,
        "current_font_label": dict(Employee.UiFont.choices).get(
            font_value, "Plex Chambers"
        ),
        "current_density_label": dict(Employee.UiDensity.choices).get(
            density_value, "Comfortable"
        ),
        "company_theme_label": company_theme_label,
        "has_personal_theme_override": not ((form_theme or "") in {"", "default"}),
    }


class ClientThemeSettingsView(View):
    template_name = "accounts/client_theme_settings.html"

    def get(self, request):
        from .views import _require_active_client

        client, denied = _require_active_client(request)
        if denied:
            return denied

        context = client_portal_context(
            request, client, page_title="Theme settings", active="theme-settings"
        )
        context.update(_client_theme_settings_context(client))
        return render(request, self.template_name, context)

    def post(self, request):
        from .views import _require_active_client

        client, denied = _require_active_client(request)
        if denied:
            return denied

        form = ClientAppearanceSettingsForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            sync_session_client_appearance(request, client)
            messages.success(request, "Your portal theme has been updated.")
            return redirect("accounts:client_theme_settings")

        context = client_portal_context(
            request, client, page_title="Theme settings", active="theme-settings"
        )
        context.update(_client_theme_settings_context(client, appearance_form=form))
        return render(request, self.template_name, context)
