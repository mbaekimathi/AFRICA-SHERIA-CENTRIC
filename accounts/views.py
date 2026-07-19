from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import Q, Value
from django.db.models.functions import Concat
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_GET, require_POST

import calendar as calendar_mod
from collections import defaultdict
from datetime import date

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
    AppearanceSettingsForm,
    ApproveCaseForm,
    ApproveMatterForm,
    CasePartyEditFormSet,
    CasePartyFormSet,
    ClientLoginForm,
    ClientOnboardingForm,
    ClientSignUpForm,
    CourtAttendanceAdvocateFormSet,
    CourtAttendanceBringUpItemFormSet,
    CreateGoogleDocumentForm,
    CreateCaseTaskForm,
    CreateMatterTaskForm,
    EmployeeOnboardingForm,
    LoginForm,
    MatterPartyEditFormSet,
    MatterPartyFormSet,
    NotificationSettingsForm,
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
from .models import (
    CaseParty,
    CaseTask,
    Client,
    CourtAttendance,
    CourtAttendanceAdvocate,
    CourtAttendanceBringUpItem,
    Document,
    DocumentActivity,
    DocumentContentSnapshot,
    DocumentOpenSession,
    Employee,
    GoogleDriveConnection,
    LitigationCase,
    MatterAttendance,
    MatterParty,
    MatterTask,
    NonLitigationMatter,
    Notification,
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
    PAGE_TITLES,
    resolve_workspace_page,
    workspace_context,
)


class HomeView(View):
    """Public Sheria-Centric website home."""

    template_name = "accounts/home.html"

    def get(self, request):
        return render(
            request,
            self.template_name,
            {
                "google_client_id": getattr(settings, "GOOGLE_CLIENT_ID", ""),
            },
        )


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
            "Your client account is active. Use the portal to follow your matters, "
            "documents, and billing as they become available."
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
    google_drive_settings_template = "accounts/google_drive_settings.html"
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
        elif resolved.get("is_google_drive_settings"):
            context.update(self._google_drive_settings_context(request, resolved))
            response = render(
                request, self.google_drive_settings_template, context
            )
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
            "register-case",
            "register-new-matter",
            "register-client",
            "register-employee",
        }:
            return redirect(user.dashboard_url)

        if resolved["leaf"] in {"settings", "theme-settings", "notification-settings"}:
            return self._post_settings(request, user, resolved)

        if resolved["leaf"] == "register-client":
            return self._post_register_client(request, user, resolved)

        if resolved["leaf"] == "register-employee":
            return self._post_register_employee(request, user, resolved)

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
            appearance_form = AppearanceSettingsForm(request.POST, instance=user)
            profile_form = ProfileSettingsForm(instance=user)
            notification_form = NotificationSettingsForm(instance=user)
            if appearance_form.is_valid():
                appearance_form.save()
                messages.success(request, "Appearance preferences saved.")
                return redirect(user.workspace_url(*resolved["trail"]))
            context.update(
                self._settings_context(
                    user,
                    profile_form=profile_form,
                    appearance_form=appearance_form,
                    notification_form=notification_form,
                )
            )
            template = (
                self.theme_settings_template
                if resolved["leaf"] == "theme-settings"
                else self.settings_template
            )
            response = render(request, template, context)
            return attach_greeting_cookie(response, request)

        if action == "notifications":
            notification_form = NotificationSettingsForm(
                request.POST, instance=user
            )
            profile_form = ProfileSettingsForm(instance=user)
            appearance_form = AppearanceSettingsForm(instance=user)
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

        profile_form = ProfileSettingsForm(
            request.POST, request.FILES, instance=user
        )
        appearance_form = AppearanceSettingsForm(instance=user)
        notification_form = NotificationSettingsForm(instance=user)
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, "Profile details updated.")
            return redirect(user.workspace_url(*resolved["trail"]))

        context.update(
            self._settings_context(
                user,
                profile_form=profile_form,
                appearance_form=appearance_form,
                notification_form=notification_form,
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
        open_edit=False,
        open_view=False,
    ):
        catalog = appearance_catalog()
        return {
            "profile_form": profile_form or ProfileSettingsForm(instance=user),
            "appearance_form": appearance_form
            or AppearanceSettingsForm(instance=user),
            "notification_form": notification_form
            or NotificationSettingsForm(instance=user),
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
                (
                    Employee.UiTheme.DEFAULT
                    if (user.ui_theme or "") in {"", "product", "default"}
                    else user.ui_theme
                ),
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
