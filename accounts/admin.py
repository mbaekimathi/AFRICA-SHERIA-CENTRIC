from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

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
    EmployeeActivityPermission,
    EmployeeBlogPost,
    CommunicationSettings,
    FirmCompanyInformation,
    FirmCompanyProfileImage,
    FirmFAQ,
    FirmGalleryImage,
    FirmPracticeArea,
    FirmPracticeAreaImage,
    FinanceSettings,
    GoogleDriveConnection,
    ClientNotification,
    Invoice,
    LitigationCase,
    MatterAttendance,
    MatterParty,
    MatterTask,
    MpesaStkRequest,
    NonLitigationMatter,
    Notification,
    PayrollDeduction,
    PayrollPayment,
    PayrollRun,
    RoleActivityPermission,
    WebsiteTemplateSetting,
)


@admin.register(Employee)
class EmployeeAdmin(UserAdmin):
    ordering = ("login_code",)
    list_display = (
        "login_code",
        "first_name",
        "last_name",
        "personal_email",
        "role",
        "status",
        "is_staff",
    )
    list_display_links = ("login_code", "first_name", "last_name")
    list_editable = ("role", "status")
    list_filter = ("role", "status", "id_type", "is_staff")
    search_fields = (
        "login_code",
        "first_name",
        "last_name",
        "personal_email",
        "identification_number",
        "alien_number",
    )
    radio_fields = {"id_type": admin.HORIZONTAL}
    fieldsets = (
        (None, {"fields": ("login_code", "password")}),
        (
            "Personal info",
            {
                "fields": (
                    "courtesy_title",
                    "first_name",
                    "last_name",
                    "personal_email",
                    "work_email",
                    "personal_phone",
                    "work_phone",
                    "id_type",
                    "id_country",
                    "identification_number",
                    "alien_number",
                    "profile_photo",
                )
            },
        ),
        ("Role & status", {"fields": ("role", "status")}),
        (
            "Workspace preferences",
            {"fields": ("ui_theme", "ui_font", "ui_density", "notification_sound", "about_me")},
        ),
        (
            "Payroll & compensation",
            {
                "fields": (
                    "payment_method",
                    "mobile_money_company",
                    "mobile_money_number",
                    "bank_name",
                    "bank_account_number",
                    "monthly_salary",
                )
            },
        ),
        (
            "Compliance documents",
            {
                "fields": (
                    "employment_contract",
                    "national_id_or_passport",
                    "kra_pin_certificate",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "login_code",
                    "personal_email",
                    "courtesy_title",
                    "first_name",
                    "last_name",
                    "personal_phone",
                    "id_type",
                    "id_country",
                    "identification_number",
                    "alien_number",
                    "role",
                    "status",
                    "password1",
                    "password2",
                ),
            },
        ),
    )


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    ordering = ("company_name", "first_name", "last_name")
    list_display = (
        "email",
        "client_type",
        "display_name",
        "phone",
        "status",
        "date_joined",
    )
    list_editable = ("status",)
    list_filter = ("status", "client_type", "corporate_kind", "id_type")
    search_fields = (
        "email",
        "first_name",
        "last_name",
        "company_name",
        "phone",
        "google_sub",
        "identification_number",
        "alien_number",
        "business_number",
        "company_registration_number",
    )
    readonly_fields = (
        "date_joined",
        "last_login",
        "google_sub",
        "drive_folder_id",
        "drive_litigation_folder_id",
        "drive_non_litigation_folder_id",
    )

    @admin.display(description="Name")
    def display_name(self, obj):
        return obj.get_full_name()

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "client_type",
                    "corporate_kind",
                    "email",
                    "phone",
                    "first_name",
                    "last_name",
                    "company_name",
                    "physical_address",
                    "profile_photo",
                    "status",
                    "google_sub",
                )
            },
        ),
        (
            "Identification",
            {
                "fields": (
                    "id_type",
                    "identification_number",
                    "identification_document",
                    "alien_number",
                    "alien_document",
                    "business_number",
                    "business_document",
                    "company_registration_number",
                    "company_registration_document",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
        (
            "Google Drive",
            {
                "fields": (
                    "drive_folder_id",
                    "drive_litigation_folder_id",
                    "drive_non_litigation_folder_id",
                )
            },
        ),
    )


class CasePartyInline(admin.TabularInline):
    model = CaseParty
    extra = 0
    fields = (
        "sort_order",
        "party_name",
        "party_type",
        "category",
        "firm_agent",
        "phone",
        "email",
        "is_client_party",
    )


class CaseTaskInline(admin.TabularInline):
    model = CaseTask
    extra = 0
    fields = (
        "assignee",
        "due_date",
        "reminder_at",
        "status",
        "instructions",
        "rejection_reason",
        "responded_at",
        "created_by",
    )
    readonly_fields = ("created_by", "responded_at")


@admin.register(LitigationCase)
class LitigationCaseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "filing_date",
        "client",
        "court_rank",
        "case_category",
        "case_type",
        "court_case_number",
        "station",
        "status",
        "assigned_to",
        "registered_by",
    )
    list_filter = ("status", "court_rank", "case_category", "case_type", "station")
    search_fields = (
        "court_case_number",
        "description",
        "client__first_name",
        "client__last_name",
        "client__company_name",
        "client__phone",
        "client__email",
    )
    date_hierarchy = "filing_date"
    inlines = [CasePartyInline, CaseTaskInline]
    readonly_fields = ("created_at", "updated_at", "approved_at")


@admin.register(CaseParty)
class CasePartyAdmin(admin.ModelAdmin):
    list_display = (
        "party_name",
        "party_type",
        "category",
        "case",
        "phone",
        "email",
        "is_client_party",
    )
    list_filter = ("party_type", "category", "is_client_party")
    search_fields = ("party_name", "phone", "email", "firm_agent")


@admin.register(CaseTask)
class CaseTaskAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "case",
        "assignee",
        "due_date",
        "reminder_at",
        "status",
        "created_by",
        "responded_at",
        "created_at",
    )
    list_filter = ("status", "due_date")
    search_fields = (
        "title",
        "instructions",
        "rejection_reason",
        "assignee__first_name",
        "assignee__last_name",
        "case__court_case_number",
    )
    readonly_fields = ("created_at", "updated_at", "responded_at")


class CourtAttendanceAdvocateInline(admin.TabularInline):
    model = CourtAttendanceAdvocate
    extra = 0


class CourtAttendanceBringUpInline(admin.TabularInline):
    model = CourtAttendanceBringUpItem
    extra = 0
    raw_id_fields = ("allocated_to",)


@admin.register(CourtAttendance)
class CourtAttendanceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "case",
        "activity_type",
        "attendance_date",
        "presence",
        "judicial_officer",
        "next_court_date",
        "recorded_by",
    )
    list_filter = ("presence", "attendance_date", "next_court_date")
    search_fields = (
        "activity_type",
        "judicial_officer",
        "court_room",
        "case__court_case_number",
        "description",
    )
    date_hierarchy = "attendance_date"
    inlines = [CourtAttendanceAdvocateInline, CourtAttendanceBringUpInline]
    readonly_fields = ("created_at", "updated_at")


@admin.register(MatterAttendance)
class MatterAttendanceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "matter",
        "activity_type",
        "attendance_date",
        "next_attendance_date",
        "recorded_by",
    )
    list_filter = ("attendance_date", "next_attendance_date")
    search_fields = (
        "activity_type",
        "description",
        "next_action",
        "bring_update",
        "matter__matter_title",
    )
    date_hierarchy = "attendance_date"
    readonly_fields = ("created_at", "updated_at")


class MatterPartyInline(admin.TabularInline):
    model = MatterParty
    extra = 0
    fields = (
        "sort_order",
        "party_name",
        "party_type",
        "category",
        "firm_agent",
        "phone",
        "email",
        "is_client_party",
    )


class MatterTaskInline(admin.TabularInline):
    model = MatterTask
    extra = 0
    fields = (
        "assignee",
        "due_date",
        "reminder_at",
        "status",
        "instructions",
        "rejection_reason",
        "responded_at",
        "created_by",
    )
    readonly_fields = ("created_by", "responded_at")


@admin.register(NonLitigationMatter)
class NonLitigationMatterAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "date_opened",
        "matter_title",
        "client",
        "matter_category",
        "status",
        "assigned_to",
        "registered_by",
    )
    list_filter = ("status", "matter_category")
    search_fields = (
        "matter_title",
        "matter_category",
        "client_instructions",
        "client__first_name",
        "client__last_name",
        "client__company_name",
    )
    date_hierarchy = "date_opened"
    inlines = [MatterPartyInline, MatterTaskInline]
    readonly_fields = ("created_at", "updated_at", "approved_at")


@admin.register(MatterParty)
class MatterPartyAdmin(admin.ModelAdmin):
    list_display = (
        "party_name",
        "party_type",
        "category",
        "matter",
        "phone",
        "email",
        "is_client_party",
    )
    list_filter = ("party_type", "category", "is_client_party")
    search_fields = ("party_name", "phone", "email", "firm_agent")


@admin.register(MatterTask)
class MatterTaskAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "matter",
        "assignee",
        "due_date",
        "reminder_at",
        "status",
        "created_by",
        "responded_at",
        "created_at",
    )
    list_filter = ("status", "due_date")
    search_fields = (
        "title",
        "instructions",
        "rejection_reason",
        "assignee__first_name",
        "assignee__last_name",
        "matter__matter_title",
    )
    readonly_fields = ("created_at", "updated_at", "responded_at")


@admin.register(EmployeeBlogPost)
class EmployeeBlogPostAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "slug",
        "author",
        "status",
        "focus_keyword",
        "submitted_at",
        "approved_by",
        "updated_at",
        "published_at",
    )
    list_filter = ("status", "updated_at")
    search_fields = (
        "title",
        "slug",
        "body",
        "excerpt",
        "meta_title",
        "meta_description",
        "focus_keyword",
        "tags",
        "author__first_name",
        "author__last_name",
        "author__login_code",
    )
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = (
        "created_at",
        "updated_at",
        "submitted_at",
        "published_at",
        "approved_at",
    )
    raw_id_fields = ("author", "approved_by")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "recipient",
        "category",
        "title",
        "is_read",
        "created_at",
    )
    list_filter = ("category", "is_read", "created_at")
    search_fields = (
        "title",
        "body",
        "source_key",
        "recipient__first_name",
        "recipient__last_name",
        "recipient__login_code",
    )
    readonly_fields = ("created_at", "read_at")


@admin.register(ClientNotification)
class ClientNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "recipient",
        "category",
        "title",
        "is_read",
        "created_at",
    )
    list_filter = ("category", "is_read", "created_at")
    search_fields = (
        "title",
        "body",
        "source_key",
        "recipient__first_name",
        "recipient__last_name",
        "recipient__email",
        "recipient__company_name",
    )
    readonly_fields = ("created_at", "read_at")
    raw_id_fields = ("recipient",)


@admin.register(FirmPracticeArea)
class FirmPracticeAreaAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "rank", "updated_at", "updated_by")
    list_editable = ("rank",)
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "summary", "details", "slug")
    readonly_fields = ("created_at", "updated_at", "updated_by")


@admin.register(FirmPracticeAreaImage)
class FirmPracticeAreaImageAdmin(admin.ModelAdmin):
    list_display = ("practice_area", "sort_order", "created_at")
    list_filter = ("practice_area",)
    list_editable = ("sort_order",)


@admin.register(FirmCompanyProfileImage)
class FirmCompanyProfileImageAdmin(admin.ModelAdmin):
    list_display = ("company", "sort_order", "created_at")
    list_filter = ("company",)
    list_editable = ("sort_order",)


@admin.register(FirmFAQ)
class FirmFAQAdmin(admin.ModelAdmin):
    list_display = ("question", "rank", "updated_at", "updated_by")
    list_editable = ("rank",)
    search_fields = ("question", "answer")
    readonly_fields = ("created_at", "updated_at", "updated_by")


@admin.register(FirmGalleryImage)
class FirmGalleryImageAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "rank", "updated_at", "updated_by")
    list_editable = ("rank",)
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title", "caption", "slug")
    readonly_fields = ("created_at", "updated_at", "updated_by")


@admin.register(WebsiteTemplateSetting)
class WebsiteTemplateSettingAdmin(admin.ModelAdmin):
    list_display = ("active_template", "updated_at", "updated_by")
    readonly_fields = ("updated_at", "updated_by")


@admin.register(FinanceSettings)
class FinanceSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "allow_mpesa",
        "allow_bank_transfer",
        "mpesa_stk_enabled",
        "updated_at",
        "updated_by",
    )
    readonly_fields = ("updated_at", "updated_by")
    fieldsets = (
        (
            "Payment methods",
            {
                "fields": (
                    "allow_mpesa",
                    "allow_bank_transfer",
                    "allow_cash",
                    "allow_cheque",
                )
            },
        ),
        (
            "M-Pesa Paybill / Buy Goods",
            {
                "fields": (
                    "mpesa_paybill_enabled",
                    "mpesa_paybill_number",
                    "mpesa_paybill_account_label",
                    "mpesa_buy_goods_enabled",
                    "mpesa_till_number",
                )
            },
        ),
        (
            "M-Pesa STK Push",
            {
                "fields": (
                    "mpesa_stk_enabled",
                    "mpesa_stk_channel",
                    "mpesa_consumer_key",
                    "mpesa_consumer_secret",
                    "mpesa_passkey",
                    "mpesa_shortcode",
                    "mpesa_callback_url",
                    "mpesa_env",
                )
            },
        ),
        ("Meta", {"fields": ("updated_at", "updated_by")}),
    )


@admin.register(CommunicationSettings)
class CommunicationSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "email_enabled",
        "sms_enabled",
        "whatsapp_enabled",
        "updated_at",
        "updated_by",
    )
    readonly_fields = ("updated_at", "updated_by")
    fieldsets = (
        (
            "Email (SMTP)",
            {
                "fields": (
                    "email_enabled",
                    "email_host",
                    "email_port",
                    "email_host_user",
                    "email_host_password",
                    "email_from_email",
                    "email_from_name",
                )
            },
        ),
        (
            "SMS",
            {
                "fields": (
                    "sms_enabled",
                    "sms_provider",
                    "sms_username",
                    "sms_api_key",
                    "sms_api_secret",
                    "sms_sender_id",
                )
            },
        ),
        (
            "WhatsApp",
            {
                "fields": (
                    "whatsapp_enabled",
                    "whatsapp_business_number",
                    "whatsapp_default_message",
                    "whatsapp_api_enabled",
                    "whatsapp_provider",
                    "whatsapp_api_token",
                    "whatsapp_phone_number_id",
                    "whatsapp_webhook_url",
                )
            },
        ),
        ("Meta", {"fields": ("updated_at", "updated_by")}),
    )


@admin.register(FirmCompanyInformation)
class FirmCompanyInformationAdmin(admin.ModelAdmin):
    list_display = (
        "legal_name",
        "trading_name",
        "email",
        "phone",
        "city",
        "country",
        "updated_at",
        "updated_by",
    )
    readonly_fields = ("updated_at", "updated_by")
    fieldsets = (
        (
            "Identity",
            {
                "fields": (
                    "legal_name",
                    "trading_name",
                    "tagline",
                    "registration_number",
                    "tax_pin",
                )
            },
        ),
        (
            "Contact",
            {
                "fields": (
                    "email",
                    "phone",
                    "website",
                    "linkedin_url",
                    "facebook_url",
                    "instagram_url",
                    "x_url",
                    "youtube_url",
                )
            },
        ),
        (
            "Address",
            {
                "fields": (
                    "physical_address",
                    "postal_address",
                    "city",
                    "country",
                )
            },
        ),
        (
            "About company",
            {
                "fields": (
                    "visitor_feeling",
                    "founded_year",
                    "founded_by",
                    "market_gap",
                    "milestone",
                    "service_areas",
                    "value_proposition",
                    "future_vision",
                    "core_values",
                )
            },
        ),
        ("Meta", {"fields": ("updated_by", "updated_at")}),
    )


@admin.register(GoogleDriveConnection)
class GoogleDriveConnectionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "account_email",
        "account_name",
        "root_folder_id",
        "connected_by",
        "connected_at",
        "updated_at",
    )
    readonly_fields = (
        "access_token",
        "refresh_token",
        "token_expiry",
        "scopes",
        "account_email",
        "account_name",
        "root_folder_id",
        "clients_folder_id",
        "work_folder_id",
        "connected_by",
        "connected_at",
        "updated_at",
    )


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "source",
        "case",
        "matter",
        "uploaded_by",
        "updated_at",
    )
    list_filter = ("source",)
    search_fields = (
        "title",
        "original_filename",
        "drive_file_id",
        "case__court_case_number",
        "matter__matter_title",
    )
    readonly_fields = ("created_at", "updated_at", "drive_file_id", "web_view_link")
    raw_id_fields = ("case", "matter", "uploaded_by")


@admin.register(DocumentActivity)
class DocumentActivityAdmin(admin.ModelAdmin):
    list_display = ("document", "action", "actor", "detail", "created_at")
    list_filter = ("action",)
    search_fields = ("document__title", "detail", "actor__first_name", "actor__last_name")
    readonly_fields = ("created_at",)
    raw_id_fields = ("document", "actor")


@admin.register(DocumentOpenSession)
class DocumentOpenSessionAdmin(admin.ModelAdmin):
    list_display = (
        "document",
        "actor",
        "started_at",
        "ended_at",
        "duration_seconds",
        "ended_reason",
    )
    list_filter = ("ended_reason",)
    search_fields = ("document__title", "actor__first_name", "actor__last_name")
    readonly_fields = ("started_at", "last_seen_at")
    raw_id_fields = ("document", "actor")


@admin.register(DocumentContentSnapshot)
class DocumentContentSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "document",
        "char_count",
        "modifier_name",
        "drive_modified_at",
        "captured_at",
    )
    search_fields = (
        "document__title",
        "modifier_name",
        "modifier_email",
        "revision_id",
    )
    readonly_fields = ("captured_at", "content_hash")
    raw_id_fields = ("document", "captured_by")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "client",
        "issue_date",
        "due_date",
        "amount",
        "tax_amount",
        "amount_paid",
        "status",
        "last_mpesa_receipt",
        "created_by",
        "approved_by",
        "created_at",
    )
    list_filter = ("status", "issue_date")
    search_fields = (
        "invoice_number",
        "description",
        "last_mpesa_receipt",
        "client__first_name",
        "client__last_name",
        "client__company_name",
        "client__email",
    )
    readonly_fields = ("invoice_number", "approved_at", "created_at", "updated_at")
    raw_id_fields = ("client", "created_by", "approved_by")
    date_hierarchy = "issue_date"


@admin.register(MpesaStkRequest)
class MpesaStkRequestAdmin(admin.ModelAdmin):
    list_display = (
        "checkout_request_id",
        "invoice",
        "amount",
        "phone",
        "status",
        "mpesa_receipt",
        "payment_applied",
        "created_at",
    )
    list_filter = ("status", "simulated", "payment_applied")
    search_fields = (
        "checkout_request_id",
        "merchant_request_id",
        "mpesa_receipt",
        "phone",
        "invoice__invoice_number",
    )
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("invoice",)


@admin.register(EmployeeActivityPermission)
class EmployeeActivityPermissionAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "module_slug",
        "activity_slug",
        "action",
        "is_allowed",
        "updated_at",
        "updated_by",
    )
    list_filter = ("module_slug", "activity_slug", "action", "is_allowed")
    search_fields = (
        "employee__login_code",
        "employee__first_name",
        "employee__last_name",
        "module_slug",
        "activity_slug",
        "action",
    )
    readonly_fields = ("updated_at",)
    raw_id_fields = ("employee", "updated_by")


class PayrollDeductionInline(admin.TabularInline):
    model = PayrollDeduction
    extra = 0


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "pay_frequency",
        "pay_period_start",
        "pay_period_end",
        "gross_salary",
        "total_deductions",
        "net_pay",
        "status",
        "registered_at",
    )
    list_filter = ("status", "pay_frequency", "pay_period_end")
    search_fields = (
        "employee__first_name",
        "employee__last_name",
        "employee__login_code",
    )
    readonly_fields = ("registered_at", "updated_at")
    raw_id_fields = ("employee", "registered_by")
    inlines = [PayrollDeductionInline]


@admin.register(PayrollPayment)
class PayrollPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "receipt_number",
        "payroll_run",
        "amount_paid",
        "reference_code",
        "paid_at",
    )
    list_filter = ("paid_at",)
    search_fields = ("receipt_number", "reference_code")
    readonly_fields = ("paid_at",)
    raw_id_fields = ("payroll_run", "recorded_by")


@admin.register(RoleActivityPermission)
class RoleActivityPermissionAdmin(admin.ModelAdmin):
    list_display = (
        "role",
        "module_slug",
        "activity_slug",
        "is_allowed",
        "updated_at",
        "updated_by",
    )
    list_filter = ("role", "module_slug", "is_allowed")
    search_fields = ("module_slug", "activity_slug")
    readonly_fields = ("updated_at",)
    raw_id_fields = ("updated_by",)
