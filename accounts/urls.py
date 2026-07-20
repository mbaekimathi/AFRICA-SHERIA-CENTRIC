from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    # Public site
    path("", views.HomeView.as_view(), name="home"),
    path("about/", views.FirmAboutView.as_view(), name="firm_about"),
    path("practice/", views.FirmPracticeListView.as_view(), name="firm_practice_list"),
    path(
        "practice/<slug:slug>/",
        views.FirmPracticeDetailView.as_view(),
        name="firm_practice_detail",
    ),
    path("gallery/", views.FirmGalleryListView.as_view(), name="firm_gallery_list"),
    path(
        "gallery/<slug:slug>/",
        views.FirmGalleryDetailView.as_view(),
        name="firm_gallery_detail",
    ),
    path("faqs/", views.FirmFaqsView.as_view(), name="firm_faqs"),
    path("contact/", views.FirmContactView.as_view(), name="firm_contact"),
    path("blog/", views.BlogListView.as_view(), name="blog_list"),
    path("blog/<slug:slug>/", views.BlogDetailView.as_view(), name="blog_detail"),
    path("terms/", views.FirmTermsView.as_view(), name="firm_terms"),
    path("blog-sitemap.xml", views.BlogSitemapView.as_view(), name="blog_sitemap"),
    path("robots.txt", views.RobotsTxtView.as_view(), name="robots_txt"),
    # Employee auth
    path("employee/login/", views.AdvocateLoginView.as_view(), name="login"),
    path("login/", views.AdvocateLoginView.as_view(), name="login-alt"),
    path("signup/", views.SignUpView.as_view(), name="signup"),
    path("api/check-login-code/", views.check_login_code, name="check_login_code"),
    path(
        "api/workspace/list-revision/",
        views.workspace_list_revision,
        name="workspace_list_revision",
    ),
    path(
        "api/workspace/notifications/",
        views.workspace_notifications,
        name="workspace_notifications",
    ),
    path(
        "api/workspace/notifications/<int:notification_id>/open/",
        views.workspace_notification_open,
        name="workspace_notification_open",
    ),
    path(
        "api/workspace/notifications/mark-all-read/",
        views.workspace_notifications_mark_all_read,
        name="workspace_notifications_mark_all_read",
    ),
    path(
        "api/workspace/entity-status/",
        views.workspace_entity_status,
        name="workspace_entity_status",
    ),
    path(
        "<slug:role>/dashboard/finance-billing/general-accounts/payments/"
        "invoice/<int:invoice_id>/stk-status/",
        views.invoice_stk_status,
        name="invoice_stk_status",
    ),
    path(
        "client/finance-billing/invoice/<int:invoice_id>/stk-status/",
        views.client_invoice_stk_status,
        name="client_invoice_stk_status",
    ),
    path(
        "invoice/shared/<str:token>/stk-status/",
        views.shared_invoice_stk_status,
        name="shared_invoice_stk_status",
    ),
    path(
        "api/workspace/clients/search/",
        views.workspace_client_search,
        name="workspace_client_search",
    ),
    path(
        "api/workspace/case-field-suggestions/",
        views.workspace_case_field_suggestions,
        name="workspace_case_field_suggestions",
    ),
    path(
        "employee/onboarding/",
        views.EmployeeOnboardingView.as_view(),
        name="employee_onboarding",
    ),
    path("employee/api/status/", views.employee_status, name="employee_status"),
    path(
        "employee/pending/",
        views.AboutWorkView.as_view(),
        name="employee_pending",
    ),
    path("about-work/", views.AboutWorkView.as_view(), name="about_work"),
    path("logout/", LogoutView.as_view(), name="logout"),
    # Client auth
    path("client/login/", views.ClientLoginView.as_view(), name="client_login"),
    path("client/signup/", views.ClientSignUpView.as_view(), name="client_signup"),
    path("client/google/", views.client_google_auth, name="client_google"),
    path(
        "integrations/google/connect/",
        views.google_drive_connect,
        name="google_drive_connect",
    ),
    path(
        "integrations/google/callback/",
        views.google_drive_callback,
        name="google_drive_callback",
    ),
    path(
        "integrations/google/disconnect/",
        views.google_drive_disconnect,
        name="google_drive_disconnect",
    ),
    path(
        "integrations/mpesa/callback/",
        views.mpesa_stk_callback,
        name="mpesa_stk_callback",
    ),
    path(
        "client/onboarding/",
        views.ClientOnboardingView.as_view(),
        name="client_onboarding",
    ),
    path("client/pending/", views.ClientPendingView.as_view(), name="client_pending"),
    path(
        "client/dashboard/",
        views.ClientDashboardView.as_view(),
        name="client_dashboard",
    ),
    path(
        "client/finance-billing/",
        views.ClientBillingView.as_view(),
        name="client_billing",
    ),
    path(
        "client/finance-billing/invoice/<int:invoice_id>/",
        views.ClientInvoiceView.as_view(),
        name="client_invoice",
    ),
    path(
        "client/finance-billing/invoice/<int:invoice_id>/pay/",
        views.ClientPayInvoiceView.as_view(),
        name="client_pay_invoice",
    ),
    path(
        "client/finance-billing/invoice/<int:invoice_id>/pdf/",
        views.ClientInvoicePdfView.as_view(),
        name="client_invoice_pdf",
    ),
    path(
        "client/api/notifications/",
        views.client_notifications,
        name="client_notifications",
    ),
    path(
        "client/api/notifications/<int:notification_id>/open/",
        views.client_notification_open,
        name="client_notification_open",
    ),
    path(
        "client/api/notifications/mark-all-read/",
        views.client_notifications_mark_all_read,
        name="client_notifications_mark_all_read",
    ),
    path("client/api/status/", views.client_status, name="client_status"),
    path("client/logout/", views.ClientLogoutView.as_view(), name="client_logout"),
    # Workspace entry
    path("workspace/", views.EmployeesHomeView.as_view(), name="employees_home"),
    # Legacy flat URLs (before role catch-alls)
    path("dashboard/", views.EmployeesHomeView.as_view(), name="dashboard"),
    path(
        "dashboard/firm-administrator/",
        views.LegacyDashboardRedirectView.as_view(role_slug="firm-administrator"),
        name="dashboard_firm_admin",
    ),
    path(
        "dashboard/managing-partner/",
        views.LegacyDashboardRedirectView.as_view(role_slug="managing-partner"),
        name="dashboard_managing_partner",
    ),
    path(
        "dashboard/advocate/",
        views.LegacyDashboardRedirectView.as_view(role_slug="advocate"),
        name="dashboard_advocate",
    ),
    path(
        "dashboard/intern/",
        views.LegacyDashboardRedirectView.as_view(role_slug="intern"),
        name="dashboard_intern",
    ),
    path(
        "dashboard/it-support/",
        views.LegacyDashboardRedirectView.as_view(role_slug="it-support"),
        name="dashboard_it_support",
    ),
    path(
        "dashboard/employee/",
        views.LegacyDashboardRedirectView.as_view(role_slug="employee"),
        name="dashboard_employee",
    ),
    path("settings/", views.LegacySettingsRedirectView.as_view(), name="settings"),
    path("employees/", views.EmployeesHomeView.as_view(), name="employees_legacy"),
    path(
        "employees/<slug:role>/",
        views.LegacyEmployeesPrefixRedirectView.as_view(),
        name="employees_role_legacy",
    ),
    path(
        "employees/<slug:role>/<path:pages>/",
        views.LegacyEmployeesPrefixRedirectView.as_view(),
        name="employees_pages_legacy",
    ),
    # Client review actions (before role page catch-all)
    path(
        "<slug:role>/dashboard/user-management/client-management/"
        "approve-pending-clients/onboard/<int:client_id>/",
        views.AssistClientOnboardingView.as_view(),
        name="assist_client_onboarding",
    ),
    path(
        "<slug:role>/dashboard/user-management/client-management/"
        "approve-pending-clients/approve/<int:client_id>/",
        views.ApproveClientView.as_view(),
        name="approve_client",
    ),
    # Employee review actions (before role page catch-all)
    path(
        "<slug:role>/dashboard/user-management/employee-management/"
        "onboarding-approvals/onboard/<int:employee_id>/",
        views.AssistEmployeeOnboardingView.as_view(),
        name="assist_employee_onboarding",
    ),
    path(
        "<slug:role>/dashboard/user-management/employee-management/"
        "onboarding-approvals/approve/<int:employee_id>/",
        views.ApproveEmployeeView.as_view(),
        name="approve_employee",
    ),
    # Case / matter review actions (before role page catch-all)
    path(
        "<slug:role>/dashboard/matter-management/litigation-matters/"
        "case/<int:case_id>/edit-case-details/",
        views.EditActiveLitigationCaseView.as_view(),
        name="edit_active_litigation_case",
    ),
    path(
        "<slug:role>/dashboard/matter-management/litigation-matters/"
        "case/<int:case_id>/create-task/",
        views.CreateCaseTaskView.as_view(),
        name="create_case_task",
    ),
    path(
        "<slug:role>/dashboard/matter-management/litigation-matters/"
        "case/<int:case_id>/update-court-attendance/",
        views.UpdateCourtAttendanceView.as_view(),
        name="update_court_attendance",
    ),
    path(
        "<slug:role>/dashboard/matter-management/litigation-matters/"
        "case/<int:case_id>/upload-documents/",
        views.UploadCaseDocumentsView.as_view(),
        name="upload_case_documents",
    ),
    path(
        "<slug:role>/dashboard/matter-management/litigation-matters/"
        "case/<int:case_id>/case-audit-progress/",
        views.CaseAuditProgressView.as_view(),
        name="case_audit_progress",
    ),
    path(
        "<slug:role>/dashboard/documents/<int:document_id>/open/",
        views.OpenDocumentView.as_view(),
        name="open_document",
    ),
    path(
        "<slug:role>/dashboard/documents/<int:document_id>/activity/",
        views.DocumentActivityAnalyticsView.as_view(),
        name="document_activity",
    ),
    path(
        "<slug:role>/dashboard/documents/<int:document_id>/download/",
        views.DownloadDocumentView.as_view(),
        name="download_document",
    ),
    path(
        "<slug:role>/dashboard/documents/<int:document_id>/sessions/"
        "<int:session_id>/ping/",
        views.DocumentSessionPingView.as_view(),
        name="document_session_ping",
    ),
    path(
        "<slug:role>/dashboard/matter-management/litigation-matters/"
        "case/<int:case_id>/<slug:action>/",
        views.LitigationCaseActionView.as_view(),
        name="litigation_case_action",
    ),
    path(
        "<slug:role>/dashboard/matter-management/litigation-matters/"
        "case/<int:case_id>/",
        views.ViewLitigationCaseView.as_view(),
        name="view_litigation_case",
    ),
    path(
        "<slug:role>/dashboard/matter-management/litigation-matters/"
        "approve-registered-cases/approve/<int:case_id>/",
        views.ApproveLitigationCaseView.as_view(),
        name="approve_litigation_case",
    ),
    path(
        "<slug:role>/dashboard/matter-management/litigation-matters/"
        "approve-registered-cases/approve/<int:case_id>/edit/",
        views.EditLitigationCaseView.as_view(),
        name="edit_litigation_case",
    ),
    path(
        "<slug:role>/dashboard/matter-management/non-litigation-matters/"
        "matter/<int:matter_id>/edit-matter-details/",
        views.EditActiveNonLitigationMatterView.as_view(),
        name="edit_active_non_litigation_matter",
    ),
    path(
        "<slug:role>/dashboard/matter-management/non-litigation-matters/"
        "matter/<int:matter_id>/create-task/",
        views.CreateMatterTaskView.as_view(),
        name="create_matter_task",
    ),
    path(
        "<slug:role>/dashboard/matter-management/non-litigation-matters/"
        "matter/<int:matter_id>/update-matter-attendance/",
        views.UpdateMatterAttendanceView.as_view(),
        name="update_matter_attendance",
    ),
    path(
        "<slug:role>/dashboard/matter-management/non-litigation-matters/"
        "matter/<int:matter_id>/upload-documents/",
        views.UploadMatterDocumentsView.as_view(),
        name="upload_matter_documents",
    ),
    path(
        "<slug:role>/dashboard/matter-management/non-litigation-matters/"
        "matter/<int:matter_id>/<slug:action>/",
        views.NonLitigationMatterActionView.as_view(),
        name="non_litigation_matter_action",
    ),
    path(
        "<slug:role>/dashboard/matter-management/non-litigation-matters/"
        "matter/<int:matter_id>/",
        views.ViewNonLitigationMatterView.as_view(),
        name="view_non_litigation_matter",
    ),
    path(
        "<slug:role>/dashboard/matter-management/non-litigation-matters/"
        "approve-registered-matters/approve/<int:matter_id>/",
        views.ApproveNonLitigationMatterView.as_view(),
        name="approve_non_litigation_matter",
    ),
    path(
        "<slug:role>/dashboard/matter-management/non-litigation-matters/"
        "approve-registered-matters/approve/<int:matter_id>/edit/",
        views.EditNonLitigationMatterView.as_view(),
        name="edit_non_litigation_matter",
    ),
    path(
        "<slug:role>/dashboard/my-blogs/<int:post_id>/edit/",
        views.EditMyBlogView.as_view(),
        name="edit_my_blog",
    ),
    path(
        "<slug:role>/dashboard/company-blogs/<int:post_id>/review/",
        views.ReviewCompanyBlogView.as_view(),
        name="review_company_blog",
    ),
    path(
        "<slug:role>/dashboard/practice-areas/<int:area_id>/edit/",
        views.EditPracticeAreaView.as_view(),
        name="edit_practice_area",
    ),
    path(
        "<slug:role>/dashboard/company-faqs/<int:faq_id>/edit/",
        views.EditFAQView.as_view(),
        name="edit_faq",
    ),
    path(
        "<slug:role>/dashboard/company-gallery/<int:item_id>/edit/",
        views.EditGalleryImageView.as_view(),
        name="edit_gallery_image",
    ),
    # Task accept / reject / view (assignee only)
    path(
        "<slug:role>/dashboard/tasks/case/<int:task_id>/",
        views.ViewCaseTaskView.as_view(),
        name="view_case_task",
    ),
    path(
        "<slug:role>/dashboard/tasks/matter/<int:task_id>/",
        views.ViewMatterTaskView.as_view(),
        name="view_matter_task",
    ),
    path(
        "<slug:role>/dashboard/tasks/case/<int:task_id>/respond/",
        views.RespondCaseTaskView.as_view(),
        name="respond_case_task",
    ),
    path(
        "<slug:role>/dashboard/tasks/matter/<int:task_id>/respond/",
        views.RespondMatterTaskView.as_view(),
        name="respond_matter_task",
    ),
    path(
        "<slug:role>/dashboard/finance-billing/general-accounts/invoicing/"
        "invoice/<int:invoice_id>/",
        views.ViewInvoiceView.as_view(),
        name="view_invoice",
    ),
    path(
        "<slug:role>/dashboard/finance-billing/general-accounts/invoicing/"
        "invoice/<int:invoice_id>/pdf/",
        views.InvoicePdfView.as_view(),
        name="invoice_pdf",
    ),
    path(
        "invoice/shared/<str:token>/pdf/",
        views.SharedInvoicePdfView.as_view(),
        name="invoice_pdf_shared",
    ),
    path(
        "invoice/shared/<str:token>/pay/",
        views.SharedInvoicePayView.as_view(),
        name="invoice_pay_shared",
    ),
    path(
        "<slug:role>/dashboard/finance-billing/general-accounts/payments/"
        "invoice/<int:invoice_id>/",
        views.PayInvoiceView.as_view(),
        name="pay_invoice",
    ),
    # Role workspace: /<role>/<page>/...  (catch-alls last)
    path("<slug:role>/", views.RoleHomeView.as_view(), name="role_home"),
    path(
        "<slug:role>/<path:pages>/",
        views.RoleWorkspaceView.as_view(),
        name="workspace",
    ),
]
