import re
from decimal import Decimal

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.db.models import F
from django.utils import timezone


class EmployeeManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, login_code, password, **extra_fields):
        if not login_code:
            raise ValueError("Employees must have a 6-digit login code.")
        login_code = str(login_code).strip()
        user = self.model(login_code=login_code, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, login_code, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("role", Employee.Role.EMPLOYEE)
        extra_fields.setdefault("status", Employee.Status.PENDING_ONBOARDING)
        return self._create_user(login_code, password, **extra_fields)

    def create_superuser(self, login_code, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", Employee.Role.FIRM_ADMIN)
        extra_fields.setdefault("status", Employee.Status.ACTIVE)
        extra_fields.setdefault("personal_email", f"admin{login_code}@sheria.local")
        extra_fields.setdefault("first_name", "Firm")
        extra_fields.setdefault("last_name", "Admin")
        extra_fields.setdefault("personal_phone", "+254700000000")
        extra_fields.setdefault("id_type", Employee.IdType.CITIZEN)
        extra_fields.setdefault("id_country", "KE")
        extra_fields.setdefault("identification_number", f"ADMIN{login_code}")

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(login_code, password, **extra_fields)


def employee_folder_name(employee) -> str:
    """Stable folder label from employee names (Drive + local media)."""
    name = f"{getattr(employee, 'first_name', '')} {getattr(employee, 'last_name', '')}".strip()
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if cleaned:
        return cleaned[:100]
    login = (getattr(employee, "login_code", "") or "").strip()
    pk = getattr(employee, "pk", None)
    if login:
        return f"Employee {login}"
    if pk:
        return f"Employee {pk}"
    return "Employee"


def employee_personal_details_upload_to(instance, filename):
    """
    Local media path:
    work/{Employee Name}/personal/{file}
    """
    folder = employee_folder_name(instance)
    safe_name = (filename or "upload").replace("\\", "/").split("/")[-1]
    safe_name = re.sub(r"[^\w.\- ()]+", "_", safe_name).strip("._") or "upload"
    return f"work/{folder}/personal/{safe_name}"


def client_folder_name(client) -> str:
    """Stable folder label from client display name (Drive + local media)."""
    if getattr(client, "client_type", "") == "corporate":
        name = (getattr(client, "company_name", "") or "").strip()
    else:
        name = f"{getattr(client, 'first_name', '')} {getattr(client, 'last_name', '')}".strip()
        if not name:
            name = (getattr(client, "company_name", "") or "").strip()
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if cleaned:
        return cleaned[:100]
    email = (getattr(client, "email", "") or "").strip()
    pk = getattr(client, "pk", None)
    if email:
        return email.split("@")[0][:100]
    if pk:
        return f"Client {pk}"
    return "Client"


def client_personal_documents_upload_to(instance, filename):
    """
    Local media path:
    clients/{Client Name}/personal-documents/{file}
    """
    folder = client_folder_name(instance)
    safe_name = (filename or "upload").replace("\\", "/").split("/")[-1]
    safe_name = re.sub(r"[^\w.\- ()]+", "_", safe_name).strip("._") or "upload"
    return f"clients/{folder}/personal-documents/{safe_name}"


class Employee(AbstractUser):
    class Role(models.TextChoices):
        FIRM_ADMIN = "firm_admin", "Firm Administrator"
        MANAGING_PARTNER = "managing_partner", "Managing Partner"
        ADVOCATE = "advocate", "Advocate"
        INTERN = "intern", "Intern"
        IT_SUPPORT = "it_support", "IT Support"
        EMPLOYEE = "employee", "Employee"

    class Status(models.TextChoices):
        PENDING_ONBOARDING = "pending_onboarding", "Pending Onboarding"
        PENDING_APPROVAL = "pending_approval", "Pending Approval"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    class PaymentMethod(models.TextChoices):
        MOBILE = "mobile", "Mobile money"
        BANK = "bank", "Bank transfer"
        CASH = "cash", "Cash"

    class IdType(models.TextChoices):
        CITIZEN = "citizen", "Citizen"
        NON_CITIZEN = "non_citizen", "Non-Citizen"

    class CourtesyTitle(models.TextChoices):
        MR = "Mr", "Mr."
        MRS = "Mrs", "Mrs."
        MS = "Ms", "Ms."
        MISS = "Miss", "Miss"
        DR = "Dr", "Dr."
        PROF = "Prof", "Prof."
        HON = "Hon", "Hon."
        ADV = "Adv", "Adv."
        REV = "Rev", "Rev."
        ENG = "Eng", "Eng."

    class UiTheme(models.TextChoices):
        DEFAULT = "default", "Black & White"
        PRODUCT = "product", "Black & White"
        FIRM_ADMIN = "firm_admin", "Firm indigo"
        MANAGING_PARTNER = "managing_partner", "Partner slate"
        ADVOCATE = "advocate", "Advocate teal"
        INTERN = "intern", "Intern blue"
        IT_SUPPORT = "it_support", "IT steel"
        EMPLOYEE = "employee", "Employee mauve"
        MIDNIGHT = "midnight", "Midnight"
        GRAPHITE = "graphite", "Graphite"
        CEDAR = "cedar", "Cedar"
        COBALT = "cobalt", "Cobalt"
        OLIVE = "olive", "Olive"
        COPPER = "copper", "Copper"
        ARCTIC = "arctic", "Arctic"
        ESPRESSO = "espresso", "Espresso"
        JADE = "jade", "Jade"
        MARINE = "marine", "Marine"
        SUNRISE = "sunrise", "Sunrise"
        CITRUS = "citrus", "Citrus"
        AZURE = "azure", "Azure"
        EMERALD = "emerald", "Emerald"
        SAFFRON = "saffron", "Saffron"
        FLAMINGO = "flamingo", "Flamingo"
        ELECTRIC = "electric", "Electric"
        RUBY = "ruby", "Ruby"
        LIME = "lime", "Lime"
        ORCHID = "orchid", "Orchid"
        VIOLET_GLOW = "violet_glow", "Aurora"
        TEAL_MATTER = "teal_matter", "Cascade"
        ORANGE_BRIEF = "orange_brief", "Copper"
        ROSE_SEAL = "rose_seal", "Garnet"
        BLUE_DOCKET = "blue_docket", "Atlas"
        VERDANT_LEAF = "verdant_leaf", "Grove"
        AMETHYST_FILE = "amethyst_file", "Violet"
        INDIGO_LIST = "indigo_list", "Ink"
        EMBER_COURT = "ember_court", "Ember"
        FUCHSIA_CLIENT = "fuchsia_client", "Berry"
        CYAN_HARBOR = "cyan_harbor", "Glacier"
        BLUSH_ADVICE = "blush_advice", "Blush"

    class UiFont(models.TextChoices):
        PLEX = "plex", "Plex Chambers"
        SOURCE = "source", "Source Editorial"
        MANROPE = "manrope", "Manrope Editorial"
        FIGTREE = "figtree", "Figtree Display"
        SORA = "sora", "Sora Brief"
        OUTFIT = "outfit", "Outfit Literata"
        JAKARTA = "jakarta", "Jakarta Crimson"
        SYNE = "syne", "Syne Vollkorn"
        EPILOGUE = "epilogue", "Epilogue Newsreader"
        PUBLIC = "public", "Public News"
        SPACE = "space", "Space Fraunces"
        ARCHIVO = "archivo", "Archivo Playfair"
        DM = "dm", "DM Pair"
        URBANIST = "urbanist", "Urbanist Cormorant"
        BRICOLAGE = "bricolage", "Bricolage Fraunces"
        LEXEND = "lexend", "Lexend Spectral"
        WORK = "work", "Work Zilla"
        ALBERT = "albert", "Albert Cardo"
        REDHAT = "redhat", "Red Hat Stack"
        CABIN = "cabin", "Cabin Alegreya"

    class UiDensity(models.TextChoices):
        COMFORTABLE = "comfortable", "Comfortable"
        COMPACT = "compact", "Compact"
        AIRY = "airy", "Airy"

    username = None
    email = None

    courtesy_title = models.CharField(
        max_length=10,
        choices=CourtesyTitle.choices,
        blank=True,
        default="",
        help_text="Courtesy title shown with the employee's name.",
    )
    login_code = models.CharField(
        max_length=6,
        unique=True,
        validators=[
            RegexValidator(
                regex=r"^\d{6}$",
                message="Login code must be exactly 6 digits.",
            )
        ],
        help_text="6-digit code used to sign in.",
    )
    personal_email = models.EmailField(unique=True)
    work_email = models.EmailField(
        blank=True,
        null=True,
        help_text="Coming soon — auto-generated from personal email.",
    )
    personal_phone = models.CharField(max_length=32)
    work_phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Coming soon — linked work phone number.",
    )
    id_type = models.CharField(max_length=20, choices=IdType.choices)
    id_country = models.CharField(
        max_length=2,
        default="KE",
        help_text="Country of nationality / ID issuance. Defaults to Kenya.",
    )
    identification_number = models.CharField(
        max_length=50,
        blank=True,
        help_text="National ID for citizens.",
    )
    alien_number = models.CharField(
        max_length=50,
        blank=True,
        help_text="Alien / permit number for non-citizens.",
    )
    profile_photo = models.ImageField(
        upload_to=employee_personal_details_upload_to,
        blank=True,
        null=True,
    )
    role = models.CharField(
        max_length=32,
        choices=Role.choices,
        default=Role.EMPLOYEE,
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING_ONBOARDING,
    )

    # Payroll & compensation (collected during onboarding)
    payment_method = models.CharField(
        max_length=16,
        choices=PaymentMethod.choices,
        blank=True,
        default="",
    )
    mobile_money_company = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text="Mobile money provider, e.g. M-Pesa.",
    )
    mobile_money_number = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Number that receives mobile money payouts.",
    )
    bank_name = models.CharField(max_length=120, blank=True, default="")
    bank_account_number = models.CharField(max_length=64, blank=True, default="")
    monthly_salary = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Gross monthly salary used for payroll.",
    )

    # Compliance documents (collected during onboarding)
    employment_contract = models.FileField(
        upload_to=employee_personal_details_upload_to,
        blank=True,
        null=True,
    )
    national_id_or_passport = models.FileField(
        upload_to=employee_personal_details_upload_to,
        blank=True,
        null=True,
    )
    kra_pin_certificate = models.FileField(
        upload_to=employee_personal_details_upload_to,
        blank=True,
        null=True,
    )

    # Google Drive: Work/{Name}/Personal/
    drive_folder_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Google Drive folder for this employee under Work/.",
    )
    drive_personal_details_folder_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Google Drive Personal subfolder for this employee.",
    )

    # Personal workspace appearance (this employee only — not firm-wide)
    ui_theme = models.CharField(
        max_length=32,
        choices=UiTheme.choices,
        default=UiTheme.DEFAULT,
        blank=True,
        help_text="Color theme for this user's workspace. 'default' follows the company theme.",
    )
    ui_font = models.CharField(
        max_length=32,
        choices=UiFont.choices,
        default=UiFont.PLEX,
        blank=True,
        help_text="Font pairing for this user's workspace only.",
    )
    ui_density = models.CharField(
        max_length=16,
        choices=UiDensity.choices,
        default=UiDensity.COMFORTABLE,
        blank=True,
        help_text="Spacing density for this user's workspace only.",
    )
    notification_sound = models.BooleanField(
        default=True,
        help_text="Play a sound when new unread notifications arrive.",
    )
    about_me = models.TextField(
        blank=True,
        default="",
        help_text="Short personal bio shown on this user's profile.",
    )

    USERNAME_FIELD = "login_code"
    REQUIRED_FIELDS = ["personal_email", "first_name", "last_name"]

    objects = EmployeeManager()

    class Meta:
        ordering = ["first_name", "last_name"]
        verbose_name = "Employee"
        verbose_name_plural = "Employees"

    def __str__(self):
        return f"{self.get_full_name()} ({self.login_code})"

    def get_full_name(self):
        name = f"{self.first_name} {self.last_name}".strip()
        if self.courtesy_title and name:
            return f"{self.get_courtesy_title_display()} {name}"
        return name

    def _titled_name(self, part: str) -> str:
        part = (part or "").strip()
        title = self.get_courtesy_title_display() if self.courtesy_title else ""
        if title and part:
            return f"{title} {part}"
        return part or title or self.login_code

    def get_titled_first_name(self) -> str:
        return self._titled_name(self.first_name)

    def get_titled_last_name(self) -> str:
        return self._titled_name(self.last_name)

    def greeting_name_variants(self) -> list[str]:
        """Courtesy title + last/first name pairs for session greetings."""
        last = self.get_titled_last_name()
        first = self.get_titled_first_name()
        variants = []
        for name in (last, first):
            if name and name not in variants:
                variants.append(name)
        return variants or [self.login_code]

    def payroll_payout_destination(self) -> str:
        """Human-readable payout destination for payroll listings."""
        if self.payment_method == self.PaymentMethod.MOBILE:
            parts = [
                (self.mobile_money_company or "").strip(),
                (self.mobile_money_number or "").strip(),
            ]
            label = " · ".join(part for part in parts if part)
            return label or "—"
        if self.payment_method == self.PaymentMethod.BANK:
            parts = [
                (self.bank_name or "").strip(),
                (self.bank_account_number or "").strip(),
            ]
            label = " · ".join(part for part in parts if part)
            return label or "—"
        if self.payment_method == self.PaymentMethod.CASH:
            return "Cash payout"
        return "—"

    def payroll_salary_display(self) -> str:
        if self.monthly_salary is None:
            return "—"
        return f"KES {self.monthly_salary:,.2f}"

    # URL slug for /<role>/... paths
    ROLE_URL_SLUGS = {
        Role.FIRM_ADMIN: "firm-administrator",
        Role.MANAGING_PARTNER: "managing-partner",
        Role.ADVOCATE: "advocate",
        Role.INTERN: "intern",
        Role.IT_SUPPORT: "it-support",
        Role.EMPLOYEE: "employee",
    }

    @classmethod
    def role_from_slug(cls, slug: str):
        for role, role_slug in cls.ROLE_URL_SLUGS.items():
            if role_slug == slug:
                return role
        return None

    @property
    def role_slug(self) -> str:
        return self.ROLE_URL_SLUGS.get(self.role, "employee")

    @property
    def workspace_theme(self) -> str:
        """CSS theme key for this employee's role workspace (personal or company)."""
        from .appearance import resolve_user_workspace_theme

        return resolve_user_workspace_theme(self)

    def has_personal_theme_override(self) -> bool:
        """True when this account overrides the firm company theme."""
        from .appearance import follows_company_theme

        return not follows_company_theme(self.ui_theme)

    @property
    def workspace_font(self) -> str:
        chosen = (self.ui_font or self.UiFont.PLEX).strip()
        valid = {key for key, _label in self.UiFont.choices}
        return chosen if chosen in valid else self.UiFont.PLEX

    @property
    def workspace_density(self) -> str:
        chosen = (self.ui_density or self.UiDensity.COMFORTABLE).strip()
        valid = {key for key, _label in self.UiDensity.choices}
        return (
            chosen if chosen in valid else self.UiDensity.COMFORTABLE
        )

    def workspace_url(self, *pages: str) -> str:
        from django.urls import reverse

        trail = "/".join(part.strip("/") for part in pages if part)
        return reverse(
            "accounts:workspace",
            kwargs={"role": self.role_slug, "pages": trail or "dashboard"},
        )

    @property
    def dashboard_url(self) -> str:
        return self.workspace_url("dashboard")

    @property
    def dashboard_url_name(self):
        """Backward-compatible alias — prefer dashboard_url for redirects."""
        return self.dashboard_url


def blog_cover_upload_to(instance, filename):
    return f"blogs/covers/{instance.author_id or 'new'}/{filename}"


class EmployeeBlogPost(models.Model):
    """Employee-authored blog post that can be published to the public website."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        PUBLISHED = "published", "Published"

    author = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="blog_posts",
    )
    title = models.CharField(max_length=200)
    slug = models.SlugField(
        max_length=220,
        unique=True,
        blank=True,
        help_text="URL path under /blog/. Auto-generated from the title if left blank.",
    )
    excerpt = models.CharField(
        max_length=320,
        blank=True,
        default="",
        help_text="Short summary shown on the blog list and used as a fallback meta description.",
    )
    body = models.TextField()
    cover_image = models.ImageField(
        upload_to=blog_cover_upload_to,
        blank=True,
        null=True,
        help_text="Optional cover image for social sharing and the blog list.",
    )
    meta_title = models.CharField(
        max_length=70,
        blank=True,
        default="",
        help_text="SEO title (about 50–60 characters). Falls back to the post title.",
    )
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        default="",
        help_text="SEO description (about 120–160 characters) for Google snippets.",
    )
    focus_keyword = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text="Primary phrase you want this post to rank for.",
    )
    tags = models.CharField(
        max_length=240,
        blank=True,
        default="",
        help_text="Comma-separated topics, e.g. employment law, contracts, Kenya.",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    submitted_at = models.DateTimeField(blank=True, null=True)
    published_at = models.DateTimeField(blank=True, null=True)
    approved_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="approved_blog_posts",
    )
    approved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-created_at"]
        verbose_name = "Employee blog post"
        verbose_name_plural = "Employee blog posts"
        indexes = [
            models.Index(fields=["status", "-published_at"]),
        ]

    def __str__(self):
        return f"{self.title} — {self.author.get_full_name()}"

    def save(self, *args, **kwargs):
        from django.utils.text import slugify

        if not self.slug:
            base = slugify(self.title)[:200] or "post"
            candidate = base
            n = 2
            while (
                EmployeeBlogPost.objects.filter(slug=candidate)
                .exclude(pk=self.pk)
                .exists()
            ):
                suffix = f"-{n}"
                candidate = f"{base[: 220 - len(suffix)]}{suffix}"
                n += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("accounts:blog_detail", kwargs={"slug": self.slug})

    @property
    def tag_list(self):
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]

    @property
    def word_count(self):
        return len((self.body or "").split())

    @property
    def reading_time_minutes(self):
        return max(1, round(self.word_count / 200))

    @property
    def author_initials(self):
        name = (self.author.get_full_name() if self.author_id else "") or ""
        parts = [p for p in name.replace(".", " ").split() if p]
        if len(parts) >= 2:
            return f"{parts[0][0]}{parts[-1][0]}".upper()
        if parts:
            return parts[0][:2].upper()
        return "SC"

    @property
    def effective_meta_title(self):
        return (self.meta_title or self.title or "").strip()

    @property
    def effective_meta_description(self):
        text = (self.meta_description or self.excerpt or self.body or "").strip()
        if len(text) <= 160:
            return text
        return text[:157].rsplit(" ", 1)[0] + "…"

    @property
    def is_public(self):
        return self.status == self.Status.PUBLISHED and bool(self.slug)

    def seo_checklist(self):
        """Return checklist items that guide authors toward Google-friendly posts."""
        title = (self.title or "").strip()
        meta_title = (self.meta_title or title).strip()
        meta_desc = (self.meta_description or "").strip()
        excerpt = (self.excerpt or "").strip()
        keyword = (self.focus_keyword or "").strip().lower()
        body = (self.body or "").strip()
        body_lower = body.lower()
        words = self.word_count
        slug = (self.slug or "").strip()
        heading_count = len(re.findall(r"^#{2,3}\s+\S", body, flags=re.MULTILINE))
        keyword_uses = body_lower.count(keyword) if keyword else 0
        keyword_density = (keyword_uses / words * 100) if words else 0
        has_source_link = bool(re.search(r"https?://\S+", body))

        def has_keyword(haystack: str) -> bool:
            return bool(keyword) and keyword in (haystack or "").lower()

        checks = [
            {
                "id": "title_length",
                "label": "Title is 30–60 characters",
                "ok": 30 <= len(title) <= 60,
                "hint": f"{len(title)} characters — aim for a clear, specific title.",
            },
            {
                "id": "meta_title",
                "label": "SEO title is 50–60 characters",
                "ok": 50 <= len(meta_title) <= 60,
                "hint": f"{len(meta_title)} characters — this appears in the browser tab and Google.",
            },
            {
                "id": "meta_description",
                "label": "Meta description is 120–160 characters",
                "ok": 120 <= len(meta_desc) <= 160,
                "hint": f"{len(meta_desc)} characters — write a compelling snippet for search results.",
            },
            {
                "id": "excerpt",
                "label": "Excerpt / summary added",
                "ok": 40 <= len(excerpt) <= 320,
                "hint": "A short summary helps the blog list and social previews.",
            },
            {
                "id": "focus_keyword",
                "label": "Focus keyword set",
                "ok": bool(keyword),
                "hint": "Pick one primary phrase readers would search for.",
            },
            {
                "id": "keyword_in_title",
                "label": "Focus keyword appears in the title",
                "ok": has_keyword(title),
                "hint": "Include the keyword naturally in the title.",
            },
            {
                "id": "keyword_in_meta",
                "label": "Focus keyword appears in the meta description",
                "ok": has_keyword(meta_desc),
                "hint": "Mention the keyword once in the meta description.",
            },
            {
                "id": "keyword_in_body",
                "label": "Focus keyword appears in the body",
                "ok": has_keyword(body_lower),
                "hint": "Use the keyword early, then write naturally.",
            },
            {
                "id": "body_length",
                "label": "Body has at least 300 words",
                "ok": words >= 300,
                "hint": f"{words} words — longer, helpful posts tend to rank better.",
            },
            {
                "id": "headings",
                "label": "Article uses descriptive headings",
                "ok": heading_count >= 2,
                "hint": f"{heading_count} headings — use at least two to structure the article.",
            },
            {
                "id": "keyword_density",
                "label": "Focus keyword usage is natural",
                "ok": bool(keyword) and 0.2 <= keyword_density <= 3,
                "hint": (
                    f"Used {keyword_uses} time(s) — avoid both omission and repetition."
                ),
            },
            {
                "id": "source_link",
                "label": "An external source is cited",
                "ok": has_source_link,
                "hint": "Link to a primary or authoritative source where possible.",
            },
            {
                "id": "slug",
                "label": "URL slug is set",
                "ok": bool(slug),
                "hint": "Use a short, readable slug with your keyword if it fits.",
            },
            {
                "id": "keyword_in_slug",
                "label": "Focus keyword appears in the URL slug",
                "ok": bool(keyword)
                and keyword.replace(" ", "-") in slug.lower().replace("_", "-"),
                "hint": "A keyword-rich slug helps Google understand the page.",
            },
            {
                "id": "cover",
                "label": "Cover image uploaded",
                "ok": bool(self.cover_image),
                "hint": "Images improve sharing and make the post stand out.",
            },
            {
                "id": "tags",
                "label": "At least one topic tag",
                "ok": len(self.tag_list) >= 1,
                "hint": "Tags help group related posts on the website.",
            },
        ]
        passed = sum(1 for c in checks if c["ok"])
        score = int(round((passed / len(checks)) * 100)) if checks else 0
        return {"checks": checks, "score": score, "passed": passed, "total": len(checks)}

    def web_analytics(self, *, days: int = 30) -> dict:
        """Aggregate public website views and enquiry conversions for this post."""
        from datetime import timedelta

        from django.db.models import Count
        from django.db.models.functions import TruncDate
        from django.utils import timezone

        since = timezone.now() - timedelta(days=max(1, int(days)))
        events = BlogPostEvent.objects.filter(post=self, created_at__gte=since)
        totals = {
            row["event_type"]: row["total"]
            for row in events.values("event_type").annotate(total=Count("id"))
        }
        views = int(totals.get(BlogPostEvent.EventType.VIEW, 0))
        whatsapp = int(totals.get(BlogPostEvent.EventType.CTA_WHATSAPP, 0))
        contact = int(totals.get(BlogPostEvent.EventType.CTA_CONTACT, 0))
        related = int(totals.get(BlogPostEvent.EventType.RELATED_CLICK, 0))
        conversions = whatsapp + contact
        conversion_rate = round((conversions / views) * 100, 1) if views else 0.0
        unique_visitors = (
            events.filter(event_type=BlogPostEvent.EventType.VIEW)
            .exclude(session_key="")
            .values("session_key")
            .distinct()
            .count()
        )
        daily_views = list(
            events.filter(event_type=BlogPostEvent.EventType.VIEW)
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(total=Count("id"))
            .order_by("day")
        )
        recent = list(
            events.order_by("-created_at", "-id")[:12].values(
                "event_type", "created_at", "referrer"
            )
        )
        return {
            "days": days,
            "since": since,
            "views": views,
            "unique_visitors": unique_visitors,
            "whatsapp_clicks": whatsapp,
            "contact_clicks": contact,
            "related_clicks": related,
            "interactions": whatsapp + contact + related,
            "conversions": conversions,
            "conversion_rate": conversion_rate,
            "daily_views": daily_views,
            "recent_events": recent,
        }


class BlogPostEvent(models.Model):
    """Privacy-safe public website interaction for a published blog post."""

    class EventType(models.TextChoices):
        VIEW = "view", "Page view"
        CTA_WHATSAPP = "cta_whatsapp", "WhatsApp enquire"
        CTA_CONTACT = "cta_contact", "Contact the firm"
        RELATED_CLICK = "related_click", "Related article click"

    post = models.ForeignKey(
        EmployeeBlogPost,
        on_delete=models.CASCADE,
        related_name="web_events",
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    session_key = models.CharField(max_length=64, blank=True, default="")
    referrer = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["post", "event_type", "-created_at"]),
            models.Index(fields=["post", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.event_type} on post {self.post_id}"


class Client(models.Model):
    """External client portal account (separate from firm employees)."""

    class Status(models.TextChoices):
        PENDING_ONBOARDING = "pending_onboarding", "Pending Onboarding"
        PENDING_APPROVAL = "pending_approval", "Pending Approval"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    class ClientType(models.TextChoices):
        INDIVIDUAL = "individual", "Individual client"
        CORPORATE = "corporate", "Corporate client"

    class IdType(models.TextChoices):
        CITIZEN = "citizen", "Citizen"
        NON_CITIZEN = "non_citizen", "Non-Citizen"

    class CorporateKind(models.TextChoices):
        BUSINESS = "business", "Business"
        COMPANY = "company", "Company"

    email = models.EmailField(unique=True)
    client_type = models.CharField(
        max_length=20,
        choices=ClientType.choices,
        default=ClientType.INDIVIDUAL,
    )
    corporate_kind = models.CharField(
        max_length=20,
        choices=CorporateKind.choices,
        blank=True,
        default="",
        help_text="For corporate clients: business or company.",
    )
    first_name = models.CharField(max_length=150, blank=True, default="")
    last_name = models.CharField(max_length=150, blank=True, default="")
    company_name = models.CharField(max_length=255, blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")
    physical_address = models.TextField(blank=True, default="")
    id_type = models.CharField(
        max_length=20,
        choices=IdType.choices,
        blank=True,
        default="",
    )
    identification_number = models.CharField(max_length=50, blank=True, default="")
    identification_document = models.FileField(
        upload_to=client_personal_documents_upload_to,
        blank=True,
        null=True,
    )
    alien_number = models.CharField(max_length=50, blank=True, default="")
    alien_document = models.FileField(
        upload_to=client_personal_documents_upload_to,
        blank=True,
        null=True,
    )
    business_number = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text="Business registration number.",
    )
    business_document = models.FileField(
        upload_to=client_personal_documents_upload_to,
        blank=True,
        null=True,
    )
    company_registration_number = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text="Company registration number.",
    )
    company_registration_document = models.FileField(
        upload_to=client_personal_documents_upload_to,
        blank=True,
        null=True,
        help_text="CR12 or company registration document.",
    )
    kra_pin_document = models.FileField(
        upload_to=client_personal_documents_upload_to,
        blank=True,
        null=True,
        help_text="KRA PIN certificate upload.",
    )
    signed_instruction_note = models.FileField(
        upload_to=client_personal_documents_upload_to,
        blank=True,
        null=True,
        help_text="Signed instruction note from the client.",
    )
    password = models.CharField(max_length=128, blank=True, default="")
    profile_photo = models.ImageField(
        upload_to=client_personal_documents_upload_to,
        blank=True,
        null=True,
    )
    google_sub = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="Google account subject ID when signed up via Google.",
    )
    drive_folder_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Google Drive folder for this client under Clients/.",
    )
    drive_personal_documents_folder_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Google Drive Personal Documents subfolder for this client.",
    )
    drive_litigation_folder_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Google Drive Litigation subfolder for this client.",
    )
    drive_non_litigation_folder_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Google Drive Non-Litigation subfolder for this client.",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING_ONBOARDING,
    )
    credit_balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Account credit balance",
        help_text="Prepaid credit available on this client account.",
    )
    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["company_name", "first_name", "last_name"]
        verbose_name = "Client"
        verbose_name_plural = "Clients"

    def __str__(self):
        return f"{self.get_full_name()} <{self.email}>"

    def get_full_name(self):
        if self.client_type == self.ClientType.CORPORATE and self.company_name:
            return self.company_name
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.company_name or self.email

    def set_password(self, raw_password):
        self.password = make_password(raw_password) if raw_password else ""

    def check_password(self, raw_password):
        if not self.password or not raw_password:
            return False
        return check_password(raw_password, self.password)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def apply_inbound_payment(
        self,
        amount,
        *,
        mpesa_receipt: str = "",
        note: str = "",
        created_by=None,
        method: str = "",
        phone: str = "",
        stk_request=None,
    ):
        """
        Apply client money to open invoices first (oldest due date), then surplus
        to credit_balance. The full payment (invoice slices and surplus) credits
        Main Client Accounts.

        Returns a dict: total, applied_to_invoices, credit_added, invoices_updated,
        credit_balance.
        """
        from django.db import transaction
        from django.db.models import F

        pay = Decimal(amount).quantize(Decimal("0.01"))
        empty = {
            "total": Decimal("0.00"),
            "applied_to_invoices": Decimal("0.00"),
            "credit_added": Decimal("0.00"),
            "invoices_updated": 0,
            "credit_balance": self.credit_balance or Decimal("0.00"),
        }
        if pay <= 0:
            return empty

        receipt = (mpesa_receipt or "")[:64]
        note_text = (note or "").strip()
        method_key = method or ClientAccountTopup.Method.MANUAL

        with transaction.atomic():
            remaining = pay
            invoices_updated = 0
            open_invoices = (
                Invoice.objects.select_for_update()
                .filter(
                    client_id=self.pk,
                    status__in=[
                        Invoice.Status.ISSUED,
                        Invoice.Status.GENERATED,
                        Invoice.Status.PARTIALLY_PAID,
                    ],
                )
                .order_by("due_date", "issue_date", "id")
            )
            for invoice in open_invoices:
                if remaining <= 0:
                    break
                due = invoice.balance_due
                if due <= 0:
                    continue
                chunk = remaining if remaining <= due else due
                applied, _status = invoice.apply_payment(
                    chunk,
                    mpesa_receipt=receipt,
                )
                if applied > 0:
                    remaining -= applied
                    invoices_updated += 1

            credit_added = remaining.quantize(Decimal("0.01"))
            if credit_added > 0:
                type(self).objects.filter(pk=self.pk).update(
                    credit_balance=F("credit_balance") + credit_added
                )
                CompanyExpenseAccount.credit_main_client_accounts(
                    amount=credit_added,
                    source_client=self,
                    source_note=(
                        note_text
                        or "Client payment surplus after invoices"
                    ),
                    created_by=created_by,
                )
            self.refresh_from_db(fields=["credit_balance"])

            topup = None
            if stk_request is not None:
                topup = ClientAccountTopup.objects.filter(
                    stk_request=stk_request
                ).first()

            if credit_added > 0:
                credit_note = note_text
                if invoices_updated:
                    split_note = (
                        f"KES {pay - credit_added:,.2f} applied to invoices; "
                        f"KES {credit_added:,.2f} credit."
                    )
                    credit_note = (
                        f"{note_text} ({split_note})".strip()
                        if note_text
                        else split_note
                    )
                if topup is None:
                    ClientAccountTopup.objects.create(
                        client=self,
                        amount=credit_added,
                        method=method_key,
                        status=ClientAccountTopup.Status.COMPLETED,
                        note=credit_note,
                        phone=(phone or "")[:20],
                        mpesa_receipt=receipt,
                        balance_after=self.credit_balance,
                        stk_request=stk_request,
                        created_by=created_by,
                    )
                else:
                    topup.amount = credit_added
                    topup.status = ClientAccountTopup.Status.COMPLETED
                    topup.note = credit_note or topup.note
                    topup.mpesa_receipt = receipt or topup.mpesa_receipt
                    topup.balance_after = self.credit_balance
                    topup.save(
                        update_fields=[
                            "amount",
                            "status",
                            "note",
                            "mpesa_receipt",
                            "balance_after",
                            "updated_at",
                        ]
                    )
            elif topup is not None:
                topup.status = ClientAccountTopup.Status.COMPLETED
                topup.amount = Decimal("0.00")
                topup.mpesa_receipt = receipt or topup.mpesa_receipt
                topup.balance_after = self.credit_balance
                applied_note = (
                    f"KES {pay:,.2f} applied to {invoices_updated} invoice(s)."
                )
                topup.note = (
                    f"{note_text} ({applied_note})".strip()
                    if note_text
                    else applied_note
                )
                topup.save(
                    update_fields=[
                        "status",
                        "amount",
                        "mpesa_receipt",
                        "balance_after",
                        "note",
                        "updated_at",
                    ]
                )

        return {
            "total": pay,
            "applied_to_invoices": (pay - credit_added).quantize(Decimal("0.01")),
            "credit_added": credit_added,
            "invoices_updated": invoices_updated,
            "credit_balance": self.credit_balance or Decimal("0.00"),
        }


class LitigationCase(models.Model):
    """A litigation matter registered by the firm for a client."""

    class Status(models.TextChoices):
        PENDING_APPROVAL = "pending_approval", "Pending approval"
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"
        REJECTED = "rejected", "Rejected"

    class CourtRank(models.TextChoices):
        SUPREME_COURT = "supreme_court", "Supreme Court"
        COURT_OF_APPEAL = "court_of_appeal", "Court of Appeal"
        HIGH_COURT = "high_court", "High Court"
        ELC = "elc", "Environment and Land Court"
        ELRC = "elrc", "Employment and Labour Relations Court"
        MAGISTRATES = "magistrates", "Magistrates' Courts"
        KADHIS = "kadhis", "Kadhi's Courts"
        COURT_MARTIAL = "court_martial", "Courts Martial"
        SMALL_CLAIMS = "small_claims", "Small Claims Court"
        TRIBUNAL = "tribunal", "Tribunals"

    class CaseCategory(models.TextChoices):
        CIVIL = "civil", "Civil"
        CRIMINAL = "criminal", "Criminal"
        COMMERCIAL = "commercial", "Commercial"
        FAMILY = "family", "Family"
        CONSTITUTIONAL = "constitutional", "Constitutional & Human Rights"
        JUDICIAL_REVIEW = "judicial_review", "Judicial Review"
        EMPLOYMENT = "employment", "Employment & Labour"
        ENVIRONMENT = "environment", "Environment & Land"
        SUCCESSION = "succession", "Succession"
        ANTI_CORRUPTION = "anti_corruption", "Anti-Corruption"
        ADMIRALTY = "admiralty", "Admiralty"
        OTHER = "other", "Other"

    class CaseType(models.TextChoices):
        SUIT = "suit", "Suit"
        PETITION = "petition", "Petition"
        APPLICATION = "application", "Application"
        APPEAL = "appeal", "Appeal"
        REVISION = "revision", "Revision"
        JUDICIAL_REVIEW = "judicial_review", "Judicial Review"
        ORIGINATING_SUMMONS = "originating_summons", "Originating Summons"
        MISCELLANEOUS = "miscellaneous", "Miscellaneous"
        CHARGE = "charge", "Charge / Criminal Case"
        OTHER = "other", "Other"

    class Station(models.TextChoices):
        NAIROBI = "nairobi", "Nairobi"
        MILIMANI = "milimani", "Milimani"
        MOMBASA = "mombasa", "Mombasa"
        KISUMU = "kisumu", "Kisumu"
        NAKURU = "nakuru", "Nakuru"
        ELDORET = "eldoret", "Eldoret"
        NYERI = "nyeri", "Nyeri"
        MERU = "meru", "Meru"
        KAKAMEGA = "kakamega", "Kakamega"
        KISII = "kisii", "Kisii"
        MALINDI = "malindi", "Malindi"
        GARISSA = "garissa", "Garissa"
        MACHAKOS = "machakos", "Machakos"
        KITALE = "kitale", "Kitale"
        KERICHO = "kericho", "Kericho"
        EMBU = "embu", "Embu"
        BUNGOMA = "bungoma", "Bungoma"
        THIKA = "thika", "Thika"
        KIAMBU = "kiambu", "Kiambu"
        OTHER = "other", "Other"

    filing_date = models.DateField()
    client = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name="litigation_cases",
    )
    court_rank = models.CharField(max_length=120)
    case_category = models.CharField(max_length=120)
    case_type = models.CharField(max_length=120)
    court_case_number = models.CharField(max_length=120, blank=True, default="")
    station = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING_APPROVAL,
    )
    registered_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registered_cases",
    )
    assigned_to = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_cases",
        help_text="Employee allocated when the case is approved.",
    )
    approved_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_cases",
    )
    approved_at = models.DateTimeField(blank=True, null=True)
    drive_folder_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Google Drive folder for this case under the client's Litigation folder.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-filing_date", "-created_at"]
        verbose_name = "Litigation case"
        verbose_name_plural = "Litigation cases"

    def __str__(self):
        ref = self.court_case_number or f"Case #{self.pk}"
        return f"{ref} — {self.client.get_full_name()}"

    @staticmethod
    def _choice_display(value, choices) -> str:
        """Resolve preset slug or label; pass through custom registered values."""
        raw = (value or "").strip()
        if not raw:
            return "—"
        mapping = dict(choices)
        if raw in mapping:
            return mapping[raw]
        for _key, label in choices:
            if label.lower() == raw.lower():
                return label
        return raw

    def get_court_rank_display(self):
        return self._choice_display(self.court_rank, self.CourtRank.choices)

    def get_case_category_display(self):
        return self._choice_display(self.case_category, self.CaseCategory.choices)

    def get_case_type_display(self):
        return self._choice_display(self.case_type, self.CaseType.choices)

    def get_station_display(self):
        return self._choice_display(self.station, self.Station.choices)

class CaseParty(models.Model):
    """A party on a litigation case (client side or opposing)."""

    class PartyType(models.TextChoices):
        PLAINTIFF = "plaintiff", "Plaintiff"
        DEFENDANT = "defendant", "Defendant"
        APPLICANT = "applicant", "Applicant"
        RESPONDENT = "respondent", "Respondent"
        PETITIONER = "petitioner", "Petitioner"
        APPELLANT = "appellant", "Appellant"
        ACCUSED = "accused", "Accused"
        INTERESTED_PARTY = "interested_party", "Interested Party"
        THIRD_PARTY = "third_party", "Third Party"
        OTHER = "other", "Other"

    class Category(models.TextChoices):
        INDIVIDUAL = "individual", "Individual"
        CORPORATE = "corporate", "Corporate"
        GOVERNMENT = "government", "Government"
        OTHER = "other", "Other"

    case = models.ForeignKey(
        LitigationCase,
        on_delete=models.CASCADE,
        related_name="parties",
    )
    party_name = models.CharField(max_length=255)
    party_type = models.CharField(max_length=32, choices=PartyType.choices)
    category = models.CharField(
        max_length=32,
        choices=Category.choices,
        blank=True,
        default="",
    )
    firm_agent = models.CharField(max_length=255, blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    is_client_party = models.BooleanField(
        default=False,
        help_text="True when this party row was seeded from the selected client.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = "Case party"
        verbose_name_plural = "Case parties"

    def __str__(self):
        return f"{self.party_name} ({self.get_party_type_display()})"


class CaseTask(models.Model):
    """A task assigned to an employee when a case is approved."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending acceptance"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"

    case = models.ForeignKey(
        LitigationCase,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    assignee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="case_tasks",
    )
    title = models.CharField(max_length=255, blank=True, default="")
    instructions = models.TextField(
        blank=True,
        default="",
        help_text="Instructions / brief for the assigned employee.",
    )
    due_date = models.DateField()
    reminder_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Optional reminder date and time.",
    )
    allow_view = models.BooleanField(
        default=True,
        help_text="Assignee may view case details and documents.",
    )
    allow_edit = models.BooleanField(
        default=True,
        help_text="Assignee may edit case details and rename documents.",
    )
    allow_download = models.BooleanField(
        default=True,
        help_text="Assignee may download case documents.",
    )
    allow_delete = models.BooleanField(
        default=True,
        help_text="Assignee may delete case documents.",
    )
    allow_upload = models.BooleanField(
        default=True,
        help_text="Assignee may upload or create case documents.",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    rejection_reason = models.TextField(
        blank=True,
        default="",
        help_text="Required when the assignee rejects the task.",
    )
    responded_at = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_case_tasks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    ACCESS_PERMISSION_KEYS = (
        "view",
        "edit",
        "download",
        "delete",
        "upload",
    )

    class Meta:
        ordering = ["due_date", "-created_at"]
        verbose_name = "Case task"
        verbose_name_plural = "Case tasks"

    def __str__(self):
        label = (self.title or "").strip() or f"Task #{self.pk}"
        return f"{label} — {self.assignee.get_full_name()}"

    def access_allowed(self, permission: str) -> bool:
        """Return whether this task grants a named access permission."""
        key = (permission or "").strip().lower()
        if key not in self.ACCESS_PERMISSION_KEYS:
            return False
        return bool(getattr(self, f"allow_{key}", False))

    @classmethod
    def effective_access_for(cls, employee, case):
        """
        Task-level access for an assignee on a case.

        Returns None when the employee has no pending/accepted tasks on the
        case (workspace permissions alone apply). Otherwise returns a dict of
        allow_* booleans; a permission is allowed only if every active task
        grants it (restrict wins).
        """
        if employee is None or case is None:
            return None
        tasks = list(
            cls.objects.filter(
                case_id=getattr(case, "pk", case),
                assignee_id=getattr(employee, "pk", employee),
                status__in=(cls.Status.PENDING, cls.Status.ACCEPTED),
            ).only(
                "allow_view",
                "allow_edit",
                "allow_download",
                "allow_delete",
                "allow_upload",
            )
        )
        if not tasks:
            return None
        return {
            f"allow_{key}": all(task.access_allowed(key) for task in tasks)
            for key in cls.ACCESS_PERMISSION_KEYS
        }


class CourtAttendance(models.Model):
    """A recorded court attendance / hearing for a litigation case."""

    class Presence(models.TextChoices):
        PRESENT = "present", "PRESENT"
        ABSENT = "absent", "ABSENT"
        PARTIAL = "partial", "PARTIAL"

    class ClientAttendance(models.TextChoices):
        REQUIRED = "required", "Client required"
        NOT_REQUIRED = "not_required", "Client not required"
        OPTIONAL = "optional", "Client optional"
        VIRTUAL = "virtual", "Virtual"

    case = models.ForeignKey(
        LitigationCase,
        on_delete=models.CASCADE,
        related_name="court_attendances",
    )
    activity_type = models.CharField(max_length=120)
    judicial_officer = models.CharField(max_length=255)
    court_room = models.CharField(max_length=120, blank=True, default="")
    attendance_date = models.DateField()
    presence = models.CharField(
        max_length=16,
        choices=Presence.choices,
        default=Presence.PRESENT,
    )
    court_directions = models.TextField(blank=True, default="")
    description = models.TextField(blank=True, default="")
    next_action = models.TextField(blank=True, default="")
    next_activity_type = models.CharField(max_length=120, blank=True, default="")
    next_court_date = models.DateField(blank=True, null=True)
    next_judicial_officer = models.CharField(max_length=255, blank=True, default="")
    next_client_attendance = models.CharField(
        max_length=32,
        choices=ClientAttendance.choices,
        blank=True,
        default="",
    )
    virtual_link = models.URLField(max_length=500, blank=True, default="")
    recorded_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_court_attendances",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-attendance_date", "-created_at"]
        verbose_name = "Court attendance"
        verbose_name_plural = "Court attendances"

    def __str__(self):
        return (
            f"{self.activity_type} on {self.attendance_date} — "
            f"{self.case.court_case_number or self.case.pk}"
        )


class CourtAttendanceAdvocate(models.Model):
    """An advocate present at a court attendance."""

    attendance = models.ForeignKey(
        CourtAttendance,
        on_delete=models.CASCADE,
        related_name="advocates",
    )
    advocate_name = models.CharField(max_length=255)
    what_they_said = models.TextField(blank=True, default="")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = "Court attendance advocate"
        verbose_name_plural = "Court attendance advocates"

    def __str__(self):
        return self.advocate_name


class CourtAttendanceBringUpItem(models.Model):
    """A bring-up / reminder item arising from a court attendance."""

    class ReminderFrequency(models.TextChoices):
        ONCE = "once", "Once"
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        BEFORE_COURT = "before_court", "Before next court date"
        MONTHLY = "monthly", "Monthly"

    attendance = models.ForeignKey(
        CourtAttendance,
        on_delete=models.CASCADE,
        related_name="bring_up_items",
    )
    description = models.TextField()
    reminder_frequency = models.CharField(
        max_length=32,
        choices=ReminderFrequency.choices,
        blank=True,
        default="",
    )
    allocated_to = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="court_bring_up_items",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = "Court bring-up item"
        verbose_name_plural = "Court bring-up items"

    def __str__(self):
        return self.description[:80]


class NonLitigationMatter(models.Model):
    """A non-litigation matter registered by the firm for a client."""

    class Status(models.TextChoices):
        PENDING_APPROVAL = "pending_approval", "Pending approval"
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"
        REJECTED = "rejected", "Rejected"

    class MatterCategory(models.TextChoices):
        CONVEYANCING = "conveyancing", "Conveyancing"
        COMMERCIAL = "commercial", "Commercial Agreements"
        EMPLOYMENT = "employment", "Employment Advisory"
        IP = "intellectual_property", "Intellectual Property"
        CORPORATE = "corporate", "Corporate Secretarial"
        PROBATE = "probate", "Probate & Estate"
        IMMIGRATION = "immigration", "Immigration"
        REGULATORY = "regulatory", "Regulatory Compliance"
        DUE_DILIGENCE = "due_diligence", "Due Diligence"
        ADVISORY = "advisory", "Opinion / Advisory"
        OTHER = "other", "Other"

    date_opened = models.DateField()
    client = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name="non_litigation_matters",
    )
    matter_category = models.CharField(max_length=120)
    matter_title = models.CharField(max_length=255)
    client_instructions = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING_APPROVAL,
    )
    registered_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registered_matters",
    )
    assigned_to = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_matters",
    )
    approved_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_matters",
    )
    approved_at = models.DateTimeField(blank=True, null=True)
    drive_folder_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Google Drive folder for this matter under the client's Non-Litigation folder.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_opened", "-created_at"]
        verbose_name = "Non-litigation matter"
        verbose_name_plural = "Non-litigation matters"

    def __str__(self):
        return f"{self.matter_title} — {self.client.get_full_name()}"

    @staticmethod
    def _choice_display(value, choices) -> str:
        raw = (value or "").strip()
        if not raw:
            return "—"
        mapping = dict(choices)
        if raw in mapping:
            return mapping[raw]
        for _key, label in choices:
            if label.lower() == raw.lower():
                return label
        return raw

    def get_matter_category_display(self):
        return self._choice_display(
            self.matter_category, self.MatterCategory.choices
        )

    @property
    def reference_code(self) -> str:
        year = self.date_opened.year if self.date_opened else timezone.localdate().year
        return f"MAT-{year}-{self.pk:05d}"


class MatterParty(models.Model):
    """A party on a non-litigation matter."""

    class PartyType(models.TextChoices):
        CLIENT = "client", "Client"
        COUNTERPARTY = "counterparty", "Counterparty"
        BENEFICIARY = "beneficiary", "Beneficiary"
        WITNESS = "witness", "Witness"
        INSTRUCTING_PARTY = "instructing_party", "Instructing Party"
        OTHER = "other", "Other"

    class Category(models.TextChoices):
        INDIVIDUAL = "individual", "Individual"
        CORPORATE = "corporate", "Corporate"
        GOVERNMENT = "government", "Government"
        OTHER = "other", "Other"

    matter = models.ForeignKey(
        NonLitigationMatter,
        on_delete=models.CASCADE,
        related_name="parties",
    )
    party_name = models.CharField(max_length=255)
    party_type = models.CharField(max_length=32, choices=PartyType.choices)
    category = models.CharField(
        max_length=32,
        choices=Category.choices,
        blank=True,
        default="",
    )
    firm_agent = models.CharField(max_length=255, blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    is_client_party = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = "Matter party"
        verbose_name_plural = "Matter parties"

    def __str__(self):
        return f"{self.party_name} ({self.get_party_type_display()})"


class MatterTask(models.Model):
    """A task assigned when a non-litigation matter is approved."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending acceptance"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"

    matter = models.ForeignKey(
        NonLitigationMatter,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    assignee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="matter_tasks",
    )
    title = models.CharField(max_length=255, blank=True, default="")
    instructions = models.TextField(blank=True, default="")
    due_date = models.DateField()
    reminder_at = models.DateTimeField(blank=True, null=True)
    allow_view = models.BooleanField(
        default=True,
        help_text="Assignee may view matter details and documents.",
    )
    allow_edit = models.BooleanField(
        default=True,
        help_text="Assignee may edit matter details and rename documents.",
    )
    allow_download = models.BooleanField(
        default=True,
        help_text="Assignee may download matter documents.",
    )
    allow_delete = models.BooleanField(
        default=True,
        help_text="Assignee may delete matter documents.",
    )
    allow_upload = models.BooleanField(
        default=True,
        help_text="Assignee may upload or create matter documents.",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    rejection_reason = models.TextField(
        blank=True,
        default="",
        help_text="Required when the assignee rejects the task.",
    )
    responded_at = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_matter_tasks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    ACCESS_PERMISSION_KEYS = (
        "view",
        "edit",
        "download",
        "delete",
        "upload",
    )

    class Meta:
        ordering = ["due_date", "-created_at"]
        verbose_name = "Matter task"
        verbose_name_plural = "Matter tasks"

    def __str__(self):
        label = (self.title or "").strip() or f"Task #{self.pk}"
        return f"{label} — {self.assignee.get_full_name()}"

    def access_allowed(self, permission: str) -> bool:
        """Return whether this task grants a named access permission."""
        key = (permission or "").strip().lower()
        if key not in self.ACCESS_PERMISSION_KEYS:
            return False
        return bool(getattr(self, f"allow_{key}", False))

    @classmethod
    def effective_access_for(cls, employee, matter):
        """
        Task-level access for an assignee on a matter.

        Returns None when the employee has no pending/accepted tasks on the
        matter (workspace permissions alone apply). Otherwise returns a dict of
        allow_* booleans; a permission is allowed only if every active task
        grants it (restrict wins).
        """
        if employee is None or matter is None:
            return None
        tasks = list(
            cls.objects.filter(
                matter_id=getattr(matter, "pk", matter),
                assignee_id=getattr(employee, "pk", employee),
                status__in=(cls.Status.PENDING, cls.Status.ACCEPTED),
            ).only(
                "allow_view",
                "allow_edit",
                "allow_download",
                "allow_delete",
                "allow_upload",
            )
        )
        if not tasks:
            return None
        return {
            f"allow_{key}": all(task.access_allowed(key) for task in tasks)
            for key in cls.ACCESS_PERMISSION_KEYS
        }


class MatterAttendance(models.Model):
    """A recorded attendance / progress update for a non-litigation matter."""

    class Presence(models.TextChoices):
        PRESENT = "present", "PRESENT"
        ABSENT = "absent", "ABSENT"
        PARTIAL = "partial", "PARTIAL"

    class ClientAttendance(models.TextChoices):
        REQUIRED = "required", "Client required"
        NOT_REQUIRED = "not_required", "Client not required"
        OPTIONAL = "optional", "Client optional"
        VIRTUAL = "virtual", "Virtual"

    matter = models.ForeignKey(
        NonLitigationMatter,
        on_delete=models.CASCADE,
        related_name="matter_attendances",
    )
    activity_type = models.CharField(max_length=120)
    contact_person = models.CharField(max_length=255, blank=True, default="")
    location = models.CharField(max_length=120, blank=True, default="")
    attendance_date = models.DateField()
    presence = models.CharField(
        max_length=16,
        choices=Presence.choices,
        default=Presence.PRESENT,
    )
    outcome_notes = models.TextField(blank=True, default="")
    description = models.TextField(blank=True, default="")
    next_action = models.TextField(blank=True, default="")
    next_activity_type = models.CharField(max_length=120, blank=True, default="")
    next_attendance_date = models.DateField(blank=True, null=True)
    next_contact_person = models.CharField(max_length=255, blank=True, default="")
    next_client_attendance = models.CharField(
        max_length=32,
        choices=ClientAttendance.choices,
        blank=True,
        default="",
    )
    virtual_link = models.URLField(max_length=500, blank=True, default="")
    bring_update = models.TextField(blank=True, default="")
    recorded_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_matter_attendances",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-attendance_date", "-created_at"]
        verbose_name = "Matter attendance"
        verbose_name_plural = "Matter attendances"

    def __str__(self):
        return (
            f"{self.activity_type} on {self.attendance_date} — "
            f"{self.matter.reference_code}"
        )


class MatterAttendanceQuorumMember(models.Model):
    """A participant recorded in the quorum for a matter attendance."""

    attendance = models.ForeignKey(
        MatterAttendance,
        on_delete=models.CASCADE,
        related_name="quorum_members",
    )
    participant_name = models.CharField(max_length=255)
    what_they_said = models.TextField(blank=True, default="")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = "Matter attendance quorum member"
        verbose_name_plural = "Matter attendance quorum members"

    def __str__(self):
        return self.participant_name


class MatterAttendanceBringUpItem(models.Model):
    """A bring-up / reminder item arising from a matter attendance."""

    class ReminderFrequency(models.TextChoices):
        ONCE = "once", "Once"
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        BEFORE_ATTENDANCE = "before_attendance", "Before next attendance"
        MONTHLY = "monthly", "Monthly"

    attendance = models.ForeignKey(
        MatterAttendance,
        on_delete=models.CASCADE,
        related_name="bring_up_items",
    )
    description = models.TextField()
    reminder_frequency = models.CharField(
        max_length=32,
        choices=ReminderFrequency.choices,
        blank=True,
        default="",
    )
    allocated_to = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="matter_bring_up_items",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = "Matter bring-up item"
        verbose_name_plural = "Matter bring-up items"

    def __str__(self):
        return self.description[:80]


class Notification(models.Model):
    """In-app notification for an employee (tasks, reminders, messages)."""

    class Category(models.TextChoices):
        TASK = "task", "Task"
        REMINDER = "reminder", "Reminder"
        MESSAGE = "message", "Message"

    recipient = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    category = models.CharField(max_length=16, choices=Category.choices)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default="")
    target_url = models.CharField(
        max_length=500,
        help_text="Workspace path to open when the notification is clicked.",
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(blank=True, null=True)
    # Dedup / source linkage (e.g. "case_task:12", "matter_task_reminder:5")
    source_key = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read", "-created_at"]),
            models.Index(fields=["recipient", "category", "-created_at"]),
        ]
        # Uniqueness of (recipient, source_key) is enforced in helpers via
        # get_or_create. Conditional unique constraints are not supported on MariaDB.
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"

    def __str__(self):
        return f"{self.get_category_display()}: {self.title}"

    def mark_read(self):
        if self.is_read:
            return
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=["is_read", "read_at"])


class ClientNotification(models.Model):
    """In-app notification for a client portal user (billing, messages)."""

    class Category(models.TextChoices):
        BILLING = "billing", "Billing"
        MESSAGE = "message", "Message"

    recipient = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    category = models.CharField(max_length=16, choices=Category.choices)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default="")
    target_url = models.CharField(
        max_length=500,
        help_text="Client portal path to open when the notification is clicked.",
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(blank=True, null=True)
    source_key = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read", "-created_at"]),
            models.Index(fields=["recipient", "category", "-created_at"]),
        ]
        verbose_name = "Client notification"
        verbose_name_plural = "Client notifications"

    def __str__(self):
        return f"{self.get_category_display()}: {self.title}"

    def mark_read(self):
        if self.is_read:
            return
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=["is_read", "read_at"])


class FirmCompanyInformation(models.Model):
    """
    Firm-wide company profile (singleton row, pk=1).

    Edited under System Settings → Company Information. Display name falls back
    to settings.FIRM_DISPLAY_NAME when legal/trading names are empty.
    """

    legal_name = models.CharField(max_length=255, blank=True, default="")
    trading_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Public / brand name if different from the legal name.",
    )
    registration_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Business or company registration number.",
    )
    tax_pin = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="Tax PIN",
        help_text="KRA PIN or equivalent tax identifier.",
    )
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=40, blank=True, default="")
    website = models.URLField(blank=True, default="")
    linkedin_url = models.URLField(blank=True, default="")
    facebook_url = models.URLField(blank=True, default="")
    instagram_url = models.URLField(blank=True, default="")
    x_url = models.URLField(
        blank=True,
        default="",
        verbose_name="X (Twitter) URL",
    )
    youtube_url = models.URLField(blank=True, default="")
    physical_address = models.TextField(blank=True, default="")
    postal_address = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=120, blank=True, default="")
    country = models.CharField(max_length=120, blank=True, default="Kenya")
    tagline = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Short line used under the firm name where needed.",
    )
    logo = models.ImageField(
        upload_to="company/logo/",
        blank=True,
        null=True,
        help_text="Firm logo for letterhead, invoices, and brand mark.",
    )
    # —— About company (website story) ——
    visitor_feeling = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="One sentence: what a visitor should know or feel on landing.",
    )
    founded_year = models.CharField(max_length=20, blank=True, default="")
    founded_by = models.CharField(max_length=255, blank=True, default="")
    market_gap = models.TextField(
        blank=True,
        default="",
        help_text="Gap or need in the market that inspired the firm.",
    )
    milestone = models.TextField(
        blank=True,
        default="",
        help_text="One milestone worth mentioning.",
    )
    service_areas = models.TextField(
        blank=True,
        default="",
        help_text="Towns and cities the firm currently serves.",
    )
    value_proposition = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="One sentence: what you do, for whom, and the outcome.",
    )
    future_vision = models.TextField(
        blank=True,
        default="",
        help_text="Where the firm wants to be in 5–10 years.",
    )
    core_values = models.JSONField(
        blank=True,
        default=list,
        help_text='List of {"name": "...", "how": "..."} core value entries.',
    )
    terms_and_conditions = models.TextField(
        blank=True,
        default="",
        help_text="Public terms and conditions shown on the firm website.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_information_updates",
    )

    class Meta:
        verbose_name = "Company information"
        verbose_name_plural = "Company information"

    def __str__(self):
        return self.display_name

    @classmethod
    def get_solo(cls):
        from django.conf import settings

        default_name = (
            getattr(settings, "FIRM_DISPLAY_NAME", "") or ""
        ).strip() or "Sheria Law Firm"
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={"legal_name": default_name},
        )
        return obj

    @property
    def display_name(self) -> str:
        from django.conf import settings

        name = (self.trading_name or self.legal_name or "").strip()
        if name:
            return name
        return (
            getattr(settings, "FIRM_DISPLAY_NAME", "") or ""
        ).strip() or "Sheria Law Firm"

    @property
    def social_media_links(self) -> list[dict[str, str]]:
        """Configured social profiles for the public website."""
        links = []
        for key, label in (
            ("linkedin_url", "LinkedIn"),
            ("facebook_url", "Facebook"),
            ("instagram_url", "Instagram"),
            ("x_url", "X"),
            ("youtube_url", "YouTube"),
        ):
            url = (getattr(self, key, "") or "").strip()
            if url:
                links.append({"key": key, "label": label, "url": url})
        return links

    @property
    def main_image(self):
        return self.profile_images.order_by("sort_order", "id").first()

    @property
    def logo_or_main(self):
        """Preferred brand mark: dedicated logo, else first profile image."""
        if self.logo:
            return self.logo
        main = self.main_image
        return main.image if main and main.image else None


def company_profile_image_upload_to(instance, filename):
    return f"company/profile/{filename}"


class FirmCompanyProfileImage(models.Model):
    """Brand image for the firm profile. Lowest sort_order is the main image."""

    company = models.ForeignKey(
        FirmCompanyInformation,
        on_delete=models.CASCADE,
        related_name="profile_images",
    )
    image = models.ImageField(upload_to=company_profile_image_upload_to)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Company profile image"
        verbose_name_plural = "Company profile images"

    def __str__(self):
        return f"{self.company.display_name} image #{self.sort_order}"

    @property
    def is_main(self) -> bool:
        main = self.company.main_image
        return bool(main and main.pk == self.pk)


def get_firm_display_name() -> str:
    """Resolved firm name for workspace chrome and portals."""
    return FirmCompanyInformation.get_solo().display_name


def practice_area_image_upload_to(instance, filename):
    return f"company/practice-areas/{instance.practice_area_id or 'new'}/{filename}"


class FirmPracticeArea(models.Model):
    """A ranked practice area for the firm website."""

    name = models.CharField(max_length=160, verbose_name="Practice area")
    slug = models.SlugField(
        max_length=180,
        unique=True,
        blank=True,
        default="",
        help_text="Public URL slug for /practice/<slug>/",
    )
    summary = models.TextField(
        blank=True,
        default="",
        verbose_name="What we do in this area",
        help_text="Short description of the work in this practice area.",
    )
    details = models.TextField(
        blank=True,
        default="",
        verbose_name="Detailed information",
        help_text="Longer copy for the practice area page.",
    )
    rank = models.PositiveIntegerField(
        default=1,
        help_text="Lower numbers appear first (1 = highest priority).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="practice_area_updates",
    )

    class Meta:
        ordering = ["rank", "name"]
        verbose_name = "Practice area"
        verbose_name_plural = "Practice areas"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        from django.utils.text import slugify

        if not (self.slug or "").strip():
            base = slugify(self.name)[:160] or "practice-area"
            candidate = base
            n = 2
            while (
                FirmPracticeArea.objects.filter(slug=candidate)
                .exclude(pk=self.pk)
                .exists()
            ):
                candidate = f"{base}-{n}"
                n += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("accounts:firm_practice_detail", kwargs={"slug": self.slug})

    @property
    def main_image(self):
        return self.images.order_by("sort_order", "id").first()


class FirmPracticeAreaImage(models.Model):
    """Image for a practice area. Lowest sort_order is the main image."""

    practice_area = models.ForeignKey(
        FirmPracticeArea,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to=practice_area_image_upload_to)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Practice area image"
        verbose_name_plural = "Practice area images"

    def __str__(self):
        return f"{self.practice_area.name} image #{self.sort_order}"

    @property
    def is_main(self) -> bool:
        main = self.practice_area.main_image
        return bool(main and main.pk == self.pk)


class FirmFAQ(models.Model):
    """A ranked FAQ entry for the firm website."""

    question = models.CharField(max_length=255, verbose_name="Question")
    answer = models.TextField(verbose_name="Answer")
    rank = models.PositiveIntegerField(
        default=1,
        help_text="Lower numbers appear first (1 = highest priority).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="faq_updates",
    )

    class Meta:
        ordering = ["rank", "question"]
        verbose_name = "Company FAQ"
        verbose_name_plural = "Company FAQs"

    def __str__(self):
        return self.question


def gallery_image_upload_to(instance, filename):
    return f"company/gallery/{filename}"


class FirmGalleryImage(models.Model):
    """A photo or visual for the firm website gallery."""

    title = models.CharField(max_length=160)
    slug = models.SlugField(
        max_length=180,
        unique=True,
        blank=True,
        default="",
        help_text="Public URL slug for /gallery/<slug>/",
    )
    caption = models.CharField(max_length=320, blank=True, default="")
    image = models.ImageField(
        upload_to=gallery_image_upload_to,
        blank=True,
        null=True,
    )
    rank = models.PositiveIntegerField(
        default=1,
        help_text="Lower numbers appear first (1 = highest priority).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gallery_updates",
    )

    class Meta:
        ordering = ["rank", "title"]
        verbose_name = "Company gallery image"
        verbose_name_plural = "Company gallery images"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        from django.utils.text import slugify

        if not (self.slug or "").strip():
            base = slugify(self.title)[:160] or "gallery-item"
            candidate = base
            n = 2
            while (
                FirmGalleryImage.objects.filter(slug=candidate)
                .exclude(pk=self.pk)
                .exists()
            ):
                candidate = f"{base}-{n}"
                n += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("accounts:firm_gallery_detail", kwargs={"slug": self.slug})


class WebsiteTemplateSetting(models.Model):
    """
    Firm-wide choice for which public homepage appears at `/` (singleton, pk=1).
    """

    class TemplateChoice(models.TextChoices):
        SHERIA_CENTRIC = "sheria_centric", "Sheria Centric website"
        COMPANY = "company", "Company website"

    active_template = models.CharField(
        max_length=32,
        choices=TemplateChoice.choices,
        default=TemplateChoice.SHERIA_CENTRIC,
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="website_template_updates",
    )

    class Meta:
        verbose_name = "Website template setting"
        verbose_name_plural = "Website template setting"

    def __str__(self):
        return self.get_active_template_display()

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def uses_company_website(self) -> bool:
        return self.active_template == self.TemplateChoice.COMPANY


class CompanyThemeSetting(models.Model):
    """
    Firm-wide default workspace theme (singleton, pk=1).

    Applied on workspace pages when an employee still uses the recommended
    default / legacy product alias — personal Theme settings override this.
    """

    default_ui_theme = models.CharField(
        max_length=32,
        choices=Employee.UiTheme.choices,
        default=Employee.UiTheme.DEFAULT,
        help_text="Default color theme for workspace pages when a user has not chosen a personal theme.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_theme_updates",
    )

    class Meta:
        verbose_name = "Company theme setting"
        verbose_name_plural = "Company theme setting"

    def __str__(self):
        return self.get_default_ui_theme_display()

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def resolved_theme(self) -> str:
        """CSS theme key for firm default (default/product → product shell)."""
        from .appearance import resolve_theme_css_key

        return resolve_theme_css_key(self.default_ui_theme)


class CompanyLetterheadSetting(models.Model):
    """
    Firm letterhead layout for invoices, receipts, and printable docs (singleton).

    Edited under System Settings → Document Settings → Letterhead.
    Company profile / contacts supply the live firm details shown in previews.
    """

    class Template(models.TextChoices):
        CLASSIC = "classic", "Classic split"
        CENTERED = "centered", "Centered seal"
        BANNER = "banner", "Accent banner"
        RULED = "ruled", "Ruled header"
        SPLIT = "split", "Modern split"
        MINIMAL = "minimal", "Minimal stack"

    class FooterTemplate(models.TextChoices):
        COMPACT = "compact", "Compact line"
        CENTERED = "centered", "Centered stack"
        RULED = "ruled", "Ruled footer"
        STACKED = "stacked", "Left stack"
        SPLIT = "split", "Split thanks"
        BAR = "bar", "Accent bar"

    class Accent(models.TextChoices):
        FOREST = "forest", "Forest"
        NAVY = "navy", "Navy"
        CHARCOAL = "charcoal", "Charcoal"
        BURGUNDY = "burgundy", "Burgundy"
        TEAL = "teal", "Teal"
        GOLD = "gold", "Gold"

    template = models.CharField(
        max_length=32,
        choices=Template.choices,
        default=Template.CLASSIC,
        help_text="Letterhead layout sample used on invoices and receipts.",
    )
    footer_template = models.CharField(
        max_length=32,
        choices=FooterTemplate.choices,
        default=FooterTemplate.COMPACT,
        help_text="Footer layout sample used on invoices and receipts.",
    )
    accent = models.CharField(
        max_length=32,
        choices=Accent.choices,
        default=Accent.FOREST,
        help_text="Accent colour applied to rules, marks, and banners.",
    )
    show_logo = models.BooleanField(
        default=True,
        help_text="Show the company profile image (or initials mark) when available.",
    )
    show_tagline = models.BooleanField(
        default=True,
        help_text="Show the company tagline under the firm name when set.",
    )
    show_address = models.BooleanField(
        default=True,
        help_text="Show physical, postal, city, and country in the document footer.",
    )
    show_contacts = models.BooleanField(
        default=True,
        help_text="Show phone and email contact lines on the letterhead.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_letterhead_updates",
    )

    class Meta:
        verbose_name = "Company letterhead setting"
        verbose_name_plural = "Company letterhead setting"

    def __str__(self):
        return self.get_template_display()

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def css_modifier(self) -> str:
        return f"doc-letterhead--{self.template} doc-letterhead--accent-{self.accent}"

    @property
    def footer_css_modifier(self) -> str:
        return (
            f"doc-letterfoot--{self.footer_template} "
            f"doc-letterfoot--accent-{self.accent}"
        )


class CompanyDigitalStampSetting(models.Model):
    """
    Firm digital stamp layout for invoices and receipts (singleton).

    Edited under System Settings → Document Settings → Digital stamp.
    """

    class Template(models.TextChoices):
        CLASSIC = "classic", "Classic ring"
        SQUARE = "square", "Square seal"
        OVAL = "oval", "Oval seal"
        BADGE = "badge", "Shield badge"
        RIBBON = "ribbon", "Ribbon banner"
        WAX = "wax", "Wax stamp"

    class Accent(models.TextChoices):
        FOREST = "forest", "Forest"
        NAVY = "navy", "Navy"
        CHARCOAL = "charcoal", "Charcoal"
        BURGUNDY = "burgundy", "Burgundy"
        TEAL = "teal", "Teal"
        GOLD = "gold", "Gold"

    template = models.CharField(
        max_length=32,
        choices=Template.choices,
        default=Template.CLASSIC,
        help_text="Digital stamp layout sample used on invoices and receipts.",
    )
    accent = models.CharField(
        max_length=32,
        choices=Accent.choices,
        default=Accent.FOREST,
        help_text="Accent colour for the stamp ink and borders.",
    )
    show_firm_name = models.BooleanField(
        default=True,
        help_text="Show the firm display name on the stamp.",
    )
    show_status = models.BooleanField(
        default=True,
        help_text="Show the document status (Paid, Issued, etc.).",
    )
    show_approver = models.BooleanField(
        default=True,
        help_text="Show the company name line on the stamp.",
    )
    show_date = models.BooleanField(
        default=True,
        help_text="Show the approval or payment date when available.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_digital_stamp_updates",
    )

    class Meta:
        verbose_name = "Company digital stamp setting"
        verbose_name_plural = "Company digital stamp setting"

    def __str__(self):
        return self.get_template_display()

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def css_modifier(self) -> str:
        return f"doc-stamp--{self.template} doc-stamp--accent-{self.accent}"


class EmployeeDigitalStampSetting(models.Model):
    """
    Per-employee digital stamp layout (My tools → My digital stamp).
    """

    class Template(models.TextChoices):
        CLASSIC = "classic", "Classic ring"
        SQUARE = "square", "Square seal"
        OVAL = "oval", "Oval seal"
        BADGE = "badge", "Shield badge"
        RIBBON = "ribbon", "Ribbon banner"
        WAX = "wax", "Wax stamp"

    class Accent(models.TextChoices):
        FOREST = "forest", "Forest"
        NAVY = "navy", "Navy"
        CHARCOAL = "charcoal", "Charcoal"
        BURGUNDY = "burgundy", "Burgundy"
        TEAL = "teal", "Teal"
        GOLD = "gold", "Gold"

    employee = models.OneToOneField(
        Employee,
        on_delete=models.CASCADE,
        related_name="digital_stamp_setting",
    )
    template = models.CharField(
        max_length=32,
        choices=Template.choices,
        default=Template.CLASSIC,
        help_text="Personal digital stamp layout sample.",
    )
    accent = models.CharField(
        max_length=32,
        choices=Accent.choices,
        default=Accent.NAVY,
        help_text="Accent colour for the stamp ink and borders.",
    )
    show_firm_name = models.BooleanField(
        default=True,
        help_text="Show the firm display name on the stamp.",
    )
    show_status = models.BooleanField(
        default=True,
        help_text="Show the document status (Paid, Issued, etc.).",
    )
    show_approver = models.BooleanField(
        default=True,
        help_text="Show your name on the stamp.",
    )
    show_date = models.BooleanField(
        default=True,
        help_text="Show the approval or payment date when available.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Employee digital stamp setting"
        verbose_name_plural = "Employee digital stamp settings"

    def __str__(self):
        return f"{self.employee} — {self.get_template_display()}"

    @classmethod
    def for_employee(cls, employee: Employee):
        obj, _ = cls.objects.get_or_create(employee=employee)
        return obj

    @property
    def css_modifier(self) -> str:
        return f"doc-stamp--{self.template} doc-stamp--accent-{self.accent}"


class CompanyDigitalSignatureSetting(models.Model):
    """
    Firm default digital signature layout for invoices and receipts (singleton).

    Edited under System Settings → Document Settings → Default signature.
    """

    class Template(models.TextChoices):
        CLASSIC = "classic", "Classic line"
        SCRIPT = "script", "Script flourish"
        FORMAL = "formal", "Formal block"
        MONOGRAM = "monogram", "Monogram mark"
        STACKED = "stacked", "Stacked authority"
        COMPACT = "compact", "Compact strip"

    class Accent(models.TextChoices):
        FOREST = "forest", "Forest"
        NAVY = "navy", "Navy"
        CHARCOAL = "charcoal", "Charcoal"
        BURGUNDY = "burgundy", "Burgundy"
        TEAL = "teal", "Teal"
        GOLD = "gold", "Gold"

    template = models.CharField(
        max_length=32,
        choices=Template.choices,
        default=Template.CLASSIC,
        help_text="Digital signature layout sample used on invoices and receipts.",
    )
    accent = models.CharField(
        max_length=32,
        choices=Accent.choices,
        default=Accent.NAVY,
        help_text="Accent colour for the signature ink and rules.",
    )
    default_title = models.CharField(
        max_length=120,
        blank=True,
        default="Authorized Signatory",
        help_text="Default title / capacity shown under the signatory name.",
    )
    show_firm_name = models.BooleanField(
        default=True,
        help_text="Show the firm display name on the signature block.",
    )
    show_name = models.BooleanField(
        default=True,
        help_text="Show the signatory name when available.",
    )
    show_title = models.BooleanField(
        default=True,
        help_text="Show the signatory title / capacity.",
    )
    show_date = models.BooleanField(
        default=True,
        help_text="Show the signature date when available.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_digital_signature_updates",
    )

    class Meta:
        verbose_name = "Company digital signature setting"
        verbose_name_plural = "Company digital signature setting"

    def __str__(self):
        return self.get_template_display()

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def css_modifier(self) -> str:
        return (
            f"doc-signature--{self.template} "
            f"doc-signature--accent-{self.accent}"
        )


class GoogleDriveConnection(models.Model):
    """
    Firm-wide Google Drive OAuth connection (singleton row, pk=1).

    Used by Document Settings so the system can store and retrieve Drive files.
    """

    access_token = models.TextField(blank=True, default="")
    refresh_token = models.TextField(blank=True, default="")
    token_expiry = models.DateTimeField(blank=True, null=True)
    scopes = models.TextField(blank=True, default="")
    account_email = models.EmailField(blank=True, default="")
    account_name = models.CharField(max_length=255, blank=True, default="")
    # Firm Drive tree: Company / Clients / Work
    root_folder_id = models.CharField(max_length=128, blank=True, default="")
    clients_folder_id = models.CharField(max_length=128, blank=True, default="")
    work_folder_id = models.CharField(max_length=128, blank=True, default="")
    employees_details_folder_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Deprecated. Employee folders now live directly under Work/{Name}/Personal.",
    )
    connected_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="google_drive_connections",
    )
    connected_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Google Drive connection"
        verbose_name_plural = "Google Drive connection"

    def __str__(self):
        if self.is_connected:
            return f"Google Drive ({self.account_email or 'connected'})"
        return "Google Drive (not connected)"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def is_connected(self) -> bool:
        return bool(self.refresh_token or self.access_token)

    @property
    def has_folder_structure(self) -> bool:
        return bool(
            self.root_folder_id and self.clients_folder_id and self.work_folder_id
        )

    def clear_tokens(self, *, keep_folder_ids: bool = False):
        """
        Clear OAuth credentials so the firm shows as disconnected.

        When keep_folder_ids is True (auth invalidated automatically), firm
        folder IDs are retained so a later reconnect can reuse the tree.
        """
        self.access_token = ""
        self.refresh_token = ""
        self.token_expiry = None
        self.scopes = ""
        self.account_email = ""
        self.account_name = ""
        self.connected_by = None
        self.connected_at = None
        update_fields = [
            "access_token",
            "refresh_token",
            "token_expiry",
            "scopes",
            "account_email",
            "account_name",
            "connected_by",
            "connected_at",
            "updated_at",
        ]
        if not keep_folder_ids:
            self.root_folder_id = ""
            self.clients_folder_id = ""
            self.work_folder_id = ""
            self.employees_details_folder_id = ""
            update_fields.extend(
                [
                    "root_folder_id",
                    "clients_folder_id",
                    "work_folder_id",
                    "employees_details_folder_id",
                ]
            )
        self.save(update_fields=update_fields)


class Document(models.Model):
    """A named document linked to a litigation case or non-litigation matter."""

    class Source(models.TextChoices):
        GOOGLE_DOC = "google_doc", "Google file"
        UPLOADED = "uploaded", "Uploaded file"

    case = models.ForeignKey(
        LitigationCase,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="documents",
    )
    matter = models.ForeignKey(
        NonLitigationMatter,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="documents",
    )
    title = models.CharField(max_length=255)
    source = models.CharField(max_length=16, choices=Source.choices)
    drive_file_id = models.CharField(max_length=128, blank=True, default="")
    web_view_link = models.URLField(blank=True, default="")
    mime_type = models.CharField(max_length=120, blank=True, default="")
    original_filename = models.CharField(max_length=255, blank=True, default="")
    local_file = models.FileField(
        upload_to="matter-documents/%Y/%m/",
        blank=True,
        null=True,
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Short summary of what this document is for.",
    )
    notes = models.TextField(blank=True, default="")
    drive_modified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last modified time reported by Google Drive.",
    )
    drive_head_revision_id = models.CharField(max_length=128, blank=True, default="")
    drive_version = models.CharField(max_length=64, blank=True, default="")
    content_hash = models.CharField(max_length=64, blank=True, default="")
    content_preview = models.TextField(
        blank=True,
        default="",
        help_text="Latest plain-text preview synced from Google.",
    )
    content_synced_at = models.DateTimeField(null=True, blank=True)
    viewing_seconds = models.PositiveIntegerField(default=0)
    editing_seconds = models.PositiveIntegerField(default=0)
    creating_seconds = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_documents",
    )
    party_type = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Party type this document relates to (case or matter party roles).",
    )
    linked_client = models.ForeignKey(
        "Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_documents",
        help_text="Registered client this document is linked to.",
    )
    linked_client_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Name when linking to an unregistered client.",
    )
    linked_client_phone = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Phone when linking to an unregistered client.",
    )
    linked_client_email = models.EmailField(
        blank=True,
        default="",
        help_text="Optional email when linking to an unregistered client.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-created_at"]
        verbose_name = "Document"
        verbose_name_plural = "Documents"
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(case__isnull=False, matter__isnull=True)
                    | models.Q(case__isnull=True, matter__isnull=False)
                ),
                name="document_case_xor_matter",
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def party_type_label(self) -> str:
        """Human-readable party type for this document's case or matter."""
        value = (self.party_type or "").strip()
        if not value:
            return ""
        if self.case_id:
            return dict(CaseParty.PartyType.choices).get(value, value.replace("_", " ").title())
        if self.matter_id:
            return dict(MatterParty.PartyType.choices).get(
                value, value.replace("_", " ").title()
            )
        return value.replace("_", " ").title()

    @property
    def linked_party_label(self) -> str:
        """Display label for the party this document is linked to."""
        if self.party_type_label:
            return self.party_type_label
        if self.linked_client_id and self.linked_client:
            return self.linked_client.get_full_name()
        name = (self.linked_client_name or "").strip()
        if name:
            return name
        return ""

    @property
    def linked_party_contact(self) -> str:
        """Phone or email for a legacy linked client (registered or manual)."""
        if self.linked_client_id and self.linked_client:
            return self.linked_client.phone or self.linked_client.email or ""
        phone = (self.linked_client_phone or "").strip()
        email = (self.linked_client_email or "").strip()
        return phone or email

    @property
    def can_open(self) -> bool:
        """Whether the document can be opened for viewing/editing content."""
        if (self.open_url or "").strip():
            return True
        return bool(self.local_file)

    @property
    def can_download(self) -> bool:
        """Whether the document can be downloaded (local copy or Drive file)."""
        if self.local_file:
            return True
        return bool((self.drive_file_id or "").strip())

    @property
    def type_label(self) -> str:
        mime = (self.mime_type or "").strip()
        if mime == "application/vnd.google-apps.document":
            return "Google Docs"
        if mime == "application/vnd.google-apps.spreadsheet":
            return "Google Sheets"
        if mime == "application/vnd.google-apps.presentation":
            return "Google Slides"
        if self.source == self.Source.UPLOADED:
            return "Uploaded file"
        if self.source == self.Source.GOOGLE_DOC:
            return "Google Docs"
        return self.get_source_display()

    @property
    def edit_url(self) -> str:
        if self.drive_file_id and self.source == self.Source.GOOGLE_DOC:
            mime = (self.mime_type or "").strip()
            if mime == "application/vnd.google-apps.spreadsheet":
                return (
                    f"https://docs.google.com/spreadsheets/d/"
                    f"{self.drive_file_id}/edit"
                )
            if mime == "application/vnd.google-apps.presentation":
                return (
                    f"https://docs.google.com/presentation/d/"
                    f"{self.drive_file_id}/edit"
                )
            return f"https://docs.google.com/document/d/{self.drive_file_id}/edit"
        return self.web_view_link or ""

    @property
    def open_url(self) -> str:
        return self.edit_url or self.web_view_link or ""

    def activity_summary(self) -> dict:
        """Aggregated analytics for library display (uses prefetch when present)."""
        viewing = self.viewing_seconds or 0
        editing = self.editing_seconds or 0
        creating = self.creating_seconds or 0
        open_count = 0
        last_opened_at = None

        if self.pk:
            sessions = list(self.open_sessions.all())
            # Prefer live session sums when counters are empty but sessions exist.
            if sessions and (viewing + editing + creating) == 0:
                for session in sessions:
                    kind = session.kind or DocumentOpenSession.Kind.VIEWING
                    seconds = session.duration_seconds or 0
                    if kind == DocumentOpenSession.Kind.EDITING:
                        editing += seconds
                    elif kind == DocumentOpenSession.Kind.CREATING:
                        creating += seconds
                    else:
                        viewing += seconds
            for activity in self.activities.all():
                if activity.action == DocumentActivity.Action.OPENED:
                    open_count += 1
                    if last_opened_at is None:
                        last_opened_at = activity.created_at

        total = viewing + editing + creating
        return {
            "open_count": open_count,
            "viewing_seconds": viewing,
            "editing_seconds": editing,
            "creating_seconds": creating,
            "total_seconds": total,
            "last_opened_at": last_opened_at,
        }

    def detailed_analytics(self) -> dict:
        """Richer analytics for the document activity page."""
        summary = self.activity_summary()
        sessions = list(self.open_sessions.select_related("actor").all())
        total = summary["total_seconds"] or 0

        def share(seconds: int) -> float:
            if total <= 0:
                return 0.0
            return round((seconds / total) * 100, 1)

        by_kind = {
            DocumentOpenSession.Kind.VIEWING: {"count": 0, "seconds": 0},
            DocumentOpenSession.Kind.EDITING: {"count": 0, "seconds": 0},
            DocumentOpenSession.Kind.CREATING: {"count": 0, "seconds": 0},
        }
        by_actor: dict[str, dict] = {}
        for session in sessions:
            kind = session.kind or DocumentOpenSession.Kind.VIEWING
            if kind not in by_kind:
                kind = DocumentOpenSession.Kind.VIEWING
            seconds = session.duration_seconds or 0
            by_kind[kind]["count"] += 1
            by_kind[kind]["seconds"] += seconds
            actor_name = (
                session.actor.get_full_name()
                if session.actor_id and session.actor
                else "Unknown"
            )
            bucket = by_actor.setdefault(
                actor_name,
                {
                    "name": actor_name,
                    "sessions": 0,
                    "seconds": 0,
                    "viewing_seconds": 0,
                    "editing_seconds": 0,
                    "creating_seconds": 0,
                },
            )
            bucket["sessions"] += 1
            bucket["seconds"] += seconds
            if kind == DocumentOpenSession.Kind.EDITING:
                bucket["editing_seconds"] += seconds
            elif kind == DocumentOpenSession.Kind.CREATING:
                bucket["creating_seconds"] += seconds
            else:
                bucket["viewing_seconds"] += seconds

        ended_sessions = [s for s in sessions if s.ended_at]
        avg_seconds = (
            int(sum(s.duration_seconds or 0 for s in ended_sessions) / len(ended_sessions))
            if ended_sessions
            else 0
        )
        longest = max(
            (s.duration_seconds or 0 for s in sessions),
            default=0,
        )

        return {
            **summary,
            "session_count": len(sessions),
            "active_session_count": sum(1 for s in sessions if s.ended_at is None),
            "avg_session_seconds": avg_seconds,
            "longest_session_seconds": longest,
            "viewing_share": share(summary["viewing_seconds"]),
            "editing_share": share(summary["editing_seconds"]),
            "creating_share": share(summary["creating_seconds"]),
            "by_kind": by_kind,
            "by_actor": sorted(
                by_actor.values(), key=lambda row: row["seconds"], reverse=True
            ),
            "recent_sessions": sessions[:25],
            "content_synced_at": self.content_synced_at,
            "drive_modified_at": self.drive_modified_at,
        }



class DocumentActivity(models.Model):
    """Immutable event log for a matter/case document."""

    class Action(models.TextChoices):
        CREATED = "created", "Created"
        UPLOADED = "uploaded", "Uploaded"
        OPENED = "opened", "Opened"
        DOWNLOADED = "downloaded", "Downloaded"
        RENAMED = "renamed", "Renamed"
        CONTENT_EDITED = "content_edited", "Content edited"
        SESSION_ENDED = "session_ended", "Session ended"

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="activities",
    )
    actor = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_activities",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    detail = models.CharField(max_length=255, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Document activity"
        verbose_name_plural = "Document activities"

    def __str__(self):
        return f"{self.get_action_display()} — {self.document_id}"

    @property
    def actor_name(self) -> str:
        if self.actor_id and self.actor:
            return self.actor.get_full_name()
        return "Unknown"


class DocumentOpenSession(models.Model):
    """Tracks time spent while a document is open for viewing/editing."""

    class Kind(models.TextChoices):
        VIEWING = "viewing", "Viewing"
        EDITING = "editing", "Editing"
        CREATING = "creating", "Creating"

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="open_sessions",
    )
    actor = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_open_sessions",
    )
    kind = models.CharField(
        max_length=16,
        choices=Kind.choices,
        default=Kind.VIEWING,
        help_text="Auto-detected from Google content changes during the session.",
    )
    baseline_content_hash = models.CharField(max_length=64, blank=True, default="")
    baseline_char_count = models.PositiveIntegerField(default=0)
    first_change_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    ended_reason = models.CharField(max_length=32, blank=True, default="")
    content_changed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-started_at", "-id"]
        verbose_name = "Document open session"
        verbose_name_plural = "Document open sessions"

    def __str__(self):
        return f"Session {self.pk} on document {self.document_id}"

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    def touch(self):
        from django.utils import timezone

        if self.ended_at:
            return
        self.last_seen_at = timezone.now()
        self.duration_seconds = max(
            0, int((self.last_seen_at - self.started_at).total_seconds())
        )
        self.save(update_fields=["last_seen_at", "duration_seconds"])

    def close(self, reason: str = "closed"):
        from django.utils import timezone

        if self.ended_at:
            return False
        now = timezone.now()
        self.ended_at = now
        self.last_seen_at = now
        self.duration_seconds = max(0, int((now - self.started_at).total_seconds()))
        self.ended_reason = (reason or "closed")[:32]
        self.save(
            update_fields=[
                "ended_at",
                "last_seen_at",
                "duration_seconds",
                "ended_reason",
            ]
        )
        return True


class DocumentContentSnapshot(models.Model):
    """A synced plain-text snapshot of Google Drive document content."""

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="content_snapshots",
    )
    revision_id = models.CharField(max_length=128, blank=True, default="")
    content_hash = models.CharField(max_length=64, blank=True, default="")
    content_text = models.TextField(blank=True, default="")
    char_count = models.PositiveIntegerField(default=0)
    modifier_name = models.CharField(max_length=255, blank=True, default="")
    modifier_email = models.EmailField(blank=True, default="")
    drive_modified_at = models.DateTimeField(null=True, blank=True)
    captured_at = models.DateTimeField(auto_now_add=True)
    captured_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_content_snapshots",
    )

    class Meta:
        ordering = ["-captured_at", "-id"]
        verbose_name = "Document content snapshot"
        verbose_name_plural = "Document content snapshots"

    def __str__(self):
        return f"Snapshot {self.pk} for document {self.document_id}"

    @property
    def preview(self) -> str:
        text = (self.content_text or "").strip()
        if len(text) <= 280:
            return text
        return text[:277].rstrip() + "…"


class Invoice(models.Model):
    """A firm invoice generated under Finance & Billing → General Accounts."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        GENERATED = "generated", "Generated"
        ISSUED = "issued", "Issued"
        PARTIALLY_PAID = "partially_paid", "Partially paid"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    invoice_number = models.CharField(max_length=40, unique=True)
    client = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    issue_date = models.DateField()
    due_date = models.DateField(
        null=True,
        blank=True,
        help_text="Optional payment due date.",
    )
    description = models.TextField(
        help_text="What this invoice covers.",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    tax_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )
    amount_paid = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text="Total amount received against this invoice.",
    )
    last_mpesa_receipt = models.CharField(max_length=64, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.GENERATED,
    )
    created_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices_created",
    )
    approved_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices_approved",
        help_text="Employee who issued / approved this invoice for the client.",
    )
    approved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issue_date", "-created_at", "-id"]
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"

    def __str__(self):
        return f"{self.invoice_number} — {self.client}"

    @property
    def total_amount(self):
        return (self.amount or 0) + (self.tax_amount or 0)

    @property
    def balance_due(self):
        from decimal import Decimal

        paid = self.amount_paid or Decimal("0")
        balance = self.total_amount - paid
        return balance if balance > 0 else Decimal("0.00")

    @property
    def is_payable(self) -> bool:
        return self.status in {
            self.Status.ISSUED,
            self.Status.GENERATED,
            self.Status.PARTIALLY_PAID,
        } and self.balance_due > 0

    def apply_payment(self, amount, *, mpesa_receipt: str = ""):
        """
        Record a payment and set status to partially_paid or paid.
        Credits Main Client Accounts for the invoice slice and any overpayment.
        Overpayment also increases the client's credit_balance.
        Returns (applied_to_invoice, new_status).
        """
        from decimal import Decimal

        from django.db import transaction
        from django.db.models import F

        pay = Decimal(amount).quantize(Decimal("0.01"))
        if pay <= 0:
            return Decimal("0.00"), self.status

        with transaction.atomic():
            current = (self.amount_paid or Decimal("0")).quantize(Decimal("0.01"))
            total = Decimal(self.total_amount).quantize(Decimal("0.01"))
            remaining = total - current
            if remaining <= 0:
                self.status = self.Status.PAID
                self.save(update_fields=["status", "updated_at"])
                # Entire amount is surplus against an already-paid invoice.
                if pay > 0 and self.client_id:
                    CompanyExpenseAccount.credit_main_client_accounts(
                        amount=pay,
                        source_client=self.client,
                        source_note=(
                            f"Invoice {self.invoice_number} overpayment."
                        ),
                    )
                    Client.objects.filter(pk=self.client_id).update(
                        credit_balance=F("credit_balance") + pay
                    )
                return Decimal("0.00"), self.status

            applied = pay if pay <= remaining else remaining
            excess = (pay - applied).quantize(Decimal("0.01"))
            self.amount_paid = current + applied
            if mpesa_receipt:
                self.last_mpesa_receipt = (mpesa_receipt or "")[:64]
            if self.amount_paid >= total:
                self.amount_paid = total
                self.status = self.Status.PAID
            else:
                self.status = self.Status.PARTIALLY_PAID

            fields = ["amount_paid", "status", "updated_at"]
            if mpesa_receipt:
                fields.append("last_mpesa_receipt")
            self.save(update_fields=fields)

            receipt_note = f" Receipt {mpesa_receipt}." if mpesa_receipt else ""
            if applied > 0:
                CompanyExpenseAccount.credit_main_client_accounts(
                    amount=applied,
                    source_client=self.client,
                    source_note=(
                        f"Invoice {self.invoice_number} payment.{receipt_note}"
                    ).strip(),
                )
            if excess > 0:
                CompanyExpenseAccount.credit_main_client_accounts(
                    amount=excess,
                    source_client=self.client,
                    source_note=(
                        f"Invoice {self.invoice_number} overpayment.{receipt_note}"
                    ).strip(),
                )
                if self.client_id:
                    Client.objects.filter(pk=self.client_id).update(
                        credit_balance=F("credit_balance") + excess
                    )
            return applied, self.status

    @classmethod
    def next_invoice_number(cls):
        today = timezone.localdate()
        prefix = f"INV-{today.strftime('%Y%m%d')}-"
        latest = (
            cls.objects.filter(invoice_number__startswith=prefix)
            .order_by("-invoice_number")
            .values_list("invoice_number", flat=True)
            .first()
        )
        if latest:
            try:
                seq = int(latest.rsplit("-", 1)[-1]) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1
        return f"{prefix}{seq:04d}"


class PayrollRun(models.Model):
    """A registered payroll period for an employee with deductions."""

    class Status(models.TextChoices):
        REGISTERED = "registered", "Registered"
        PAID = "paid", "Paid"

    class PayFrequency(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        ANNUALLY = "annually", "Annually"

    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="payroll_runs",
    )
    pay_frequency = models.CharField(
        max_length=16,
        choices=PayFrequency.choices,
        default=PayFrequency.MONTHLY,
    )
    pay_period_start = models.DateField()
    pay_period_end = models.DateField()

    # Earnings (add-ons)
    basic_salary = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    house_allowance = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    transport_allowance = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    medical_allowance = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    other_allowances = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    bonuses_overtime_commissions = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    gross_salary = models.DecimalField(max_digits=14, decimal_places=2)

    # Editable statutory rates (snapshotted per run)
    nssf_employee_rate = models.DecimalField(
        max_digits=6, decimal_places=2, default=6
    )
    nssf_employer_rate = models.DecimalField(
        max_digits=6, decimal_places=2, default=1.5
    )
    nssf_tier1_limit = models.DecimalField(
        max_digits=14, decimal_places=2, default=7000
    )
    nssf_pensionable_cap = models.DecimalField(
        max_digits=14, decimal_places=2, default=36000
    )
    shif_rate = models.DecimalField(max_digits=6, decimal_places=2, default=2.75)
    housing_levy_employee_rate = models.DecimalField(
        max_digits=6, decimal_places=2, default=1.5
    )
    housing_levy_employer_rate = models.DecimalField(
        max_digits=6, decimal_places=2, default=1.5
    )
    paye_personal_relief = models.DecimalField(
        max_digits=14, decimal_places=2, default=2400
    )
    paye_band_1_max = models.DecimalField(
        max_digits=14, decimal_places=2, default=24000
    )
    paye_band_1_rate = models.DecimalField(
        max_digits=6, decimal_places=2, default=10
    )
    paye_band_2_max = models.DecimalField(
        max_digits=14, decimal_places=2, default=32333
    )
    paye_band_2_rate = models.DecimalField(
        max_digits=6, decimal_places=2, default=25
    )
    paye_band_3_max = models.DecimalField(
        max_digits=14, decimal_places=2, default=500000
    )
    paye_band_3_rate = models.DecimalField(
        max_digits=6, decimal_places=2, default=30
    )
    paye_band_4_rate = models.DecimalField(
        max_digits=6, decimal_places=2, default=35
    )

    # Calculated employee deductions
    nssf_employee_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    shif_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    housing_levy_employee_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    paye_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    taxable_income = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    total_deductions = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )
    net_pay = models.DecimalField(max_digits=14, decimal_places=2)

    # Employer-only costs
    nssf_employer_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    housing_levy_employer_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    nita_levy_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=50
    )
    wiba_insurance_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    total_employer_cost = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )

    payment_method = models.CharField(max_length=16, blank=True, default="")
    payment_method_label = models.CharField(max_length=64, blank=True, default="")
    payout_destination = models.CharField(max_length=255, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.REGISTERED,
    )
    registered_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payroll_runs_registered",
    )
    registered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-pay_period_end", "-registered_at", "-id"]
        verbose_name = "Payroll run"
        verbose_name_plural = "Payroll runs"
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "pay_frequency", "pay_period_start"],
                name="unique_payroll_period_per_employee",
            )
        ]

    def __str__(self):
        return (
            f"{self.employee} · {self.get_pay_frequency_display()} "
            f"{self.pay_period_start:%d %b %Y} "
            f"({self.get_status_display()})"
        )

    def recalculate_totals(self, *, save=True):
        from .payroll_calc import PayrollEarnings, PayrollRates, calculate_payroll

        breakdown = calculate_payroll(
            PayrollEarnings(
                basic_salary=self.basic_salary,
                house_allowance=self.house_allowance,
                transport_allowance=self.transport_allowance,
                medical_allowance=self.medical_allowance,
                other_allowances=self.other_allowances,
                bonuses_overtime_commissions=self.bonuses_overtime_commissions,
            ),
            PayrollRates(
                nssf_employee_rate=self.nssf_employee_rate,
                nssf_employer_rate=self.nssf_employer_rate,
                nssf_tier1_limit=self.nssf_tier1_limit,
                nssf_pensionable_cap=self.nssf_pensionable_cap,
                shif_rate=self.shif_rate,
                housing_levy_employee_rate=self.housing_levy_employee_rate,
                housing_levy_employer_rate=self.housing_levy_employer_rate,
                paye_personal_relief=self.paye_personal_relief,
                paye_band_1_max=self.paye_band_1_max,
                paye_band_1_rate=self.paye_band_1_rate,
                paye_band_2_max=self.paye_band_2_max,
                paye_band_2_rate=self.paye_band_2_rate,
                paye_band_3_max=self.paye_band_3_max,
                paye_band_3_rate=self.paye_band_3_rate,
                paye_band_4_rate=self.paye_band_4_rate,
                nita_levy_amount=self.nita_levy_amount,
                wiba_insurance_amount=self.wiba_insurance_amount,
            ),
        )
        self.gross_salary = breakdown.gross_salary
        self.nssf_employee_amount = breakdown.nssf_employee_amount
        self.shif_amount = breakdown.shif_amount
        self.housing_levy_employee_amount = breakdown.housing_levy_employee_amount
        self.paye_amount = breakdown.paye_amount
        self.taxable_income = breakdown.taxable_income
        self.total_deductions = breakdown.total_employee_deductions
        self.net_pay = breakdown.net_pay
        self.nssf_employer_amount = breakdown.nssf_employer_amount
        self.housing_levy_employer_amount = breakdown.housing_levy_employer_amount
        self.total_employer_cost = breakdown.total_employer_cost
        if save:
            self.save()

    def outstanding_advance_total(self):
        from decimal import Decimal

        total = self.salary_advances.filter(
            status=EmployeeAdvance.Status.OUTSTANDING
        ).aggregate(total=models.Sum("amount"))["total"]
        return total or Decimal("0.00")

    def amount_payable(self, *, deduct_advances=True):
        from decimal import Decimal

        net = self.net_pay or Decimal("0.00")
        if not deduct_advances:
            return net if net > 0 else Decimal("0.00")
        payable = net - self.outstanding_advance_total()
        return payable if payable > 0 else Decimal("0.00")

    def advance_salary_basis(self):
        """Salary used to judge advance eligibility (monthly, else payroll earnings)."""
        from decimal import Decimal

        employee_salary = self.employee.monthly_salary
        if employee_salary is not None and employee_salary > 0:
            return employee_salary
        if self.basic_salary and self.basic_salary > 0:
            return self.basic_salary
        if self.gross_salary and self.gross_salary > 0:
            return self.gross_salary
        return self.net_pay or Decimal("0.00")

    def half_salary_cap(self):
        from decimal import Decimal

        return (self.advance_salary_basis() / Decimal("2")).quantize(Decimal("0.01"))

    def max_advance_amount(self):
        from decimal import Decimal

        payable = self.amount_payable()
        half_salary = self.half_salary_cap()
        capped = min(payable, half_salary)
        return capped if capped > 0 else Decimal("0.00")

    def is_advance_eligible(self):
        """
        Eligible when salary is above half the remaining payroll amount
        and there is still advance headroom (max advance > 0).
        """
        from decimal import Decimal

        if self.status != self.Status.REGISTERED:
            return False
        salary = self.advance_salary_basis()
        payable = self.amount_payable()
        if salary <= 0 or payable <= 0:
            return False
        # salary must be above half of the remaining payroll total
        if salary <= (payable / Decimal("2")):
            return False
        return self.max_advance_amount() > 0

    def sync_deduction_lines(self):
        """Persist statutory amounts as deduction line items."""
        mapping = [
            (PayrollDeduction.DeductionType.NSSF, self.nssf_employee_amount),
            (PayrollDeduction.DeductionType.NHIF_SHIF, self.shif_amount),
            (PayrollDeduction.DeductionType.OTHER, self.housing_levy_employee_amount, "Housing Levy"),
            (PayrollDeduction.DeductionType.PAYE, self.paye_amount),
        ]
        self.deductions.all().delete()
        for entry in mapping:
            if len(entry) == 3:
                dtype, amount, label = entry
            else:
                dtype, amount = entry
                label = ""
            if amount and amount > 0:
                PayrollDeduction.objects.create(
                    payroll_run=self,
                    deduction_type=dtype,
                    description=label,
                    amount=amount,
                )


class PayrollPayment(models.Model):
    """A payment record against a payroll run, generating a receipt."""

    receipt_number = models.CharField(max_length=40, unique=True)
    payroll_run = models.ForeignKey(
        PayrollRun,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2)
    reference_code = models.CharField(max_length=100)
    paid_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payroll_payments_recorded",
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-paid_at"]
        verbose_name = "Payroll payment"
        verbose_name_plural = "Payroll payments"

    def __str__(self):
        return f"{self.receipt_number} — {self.payroll_run.employee}"

    @classmethod
    def next_receipt_number(cls):
        today = timezone.localdate()
        prefix = f"PAY-{today.strftime('%Y%m%d')}-"
        latest = (
            cls.objects.filter(receipt_number__startswith=prefix)
            .order_by("-receipt_number")
            .values_list("receipt_number", flat=True)
            .first()
        )
        if latest:
            try:
                seq = int(latest.rsplit("-", 1)[-1]) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1
        return f"{prefix}{seq:04d}"


class EmployeeAdvance(models.Model):
    """Salary advance recovered from a registered payroll run."""

    class Status(models.TextChoices):
        OUTSTANDING = "outstanding", "Outstanding"
        RECOVERED = "recovered", "Recovered"

    class Reason(models.TextChoices):
        MEDICAL = "medical", "Medical emergency"
        SCHOOL_FEES = "school_fees", "School fees"
        RENT = "rent", "Rent / housing"
        FAMILY = "family", "Family emergency"
        TRAVEL = "travel", "Travel"
        UTILITIES = "utilities", "Utilities / bills"
        OTHER = "other", "Other"

    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="salary_advances",
    )
    payroll_run = models.ForeignKey(
        PayrollRun,
        on_delete=models.PROTECT,
        related_name="salary_advances",
        help_text="Registered payroll run this advance will be recovered from.",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(
        max_length=32,
        choices=Reason.choices,
        default=Reason.OTHER,
    )
    notes = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OUTSTANDING,
    )
    recorded_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salary_advances_recorded",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    recovered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Employee advance"
        verbose_name_plural = "Employee advances"

    def __str__(self):
        return (
            f"{self.employee} · KES {self.amount:,.2f} "
            f"({self.get_status_display()})"
        )


class PayrollDeduction(models.Model):
    """A deduction line on a payroll run."""

    class DeductionType(models.TextChoices):
        PAYE = "paye", "PAYE"
        NSSF = "nssf", "NSSF"
        NHIF_SHIF = "nhif_shif", "NHIF / SHIF"
        PENSION = "pension", "Pension"
        LOAN = "loan", "Loan repayment"
        ADVANCE = "advance", "Salary advance"
        OTHER = "other", "Other"

    payroll_run = models.ForeignKey(
        PayrollRun,
        on_delete=models.CASCADE,
        related_name="deductions",
    )
    deduction_type = models.CharField(
        max_length=16,
        choices=DeductionType.choices,
    )
    description = models.CharField(max_length=120, blank=True, default="")
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["id"]
        verbose_name = "Payroll deduction"
        verbose_name_plural = "Payroll deductions"

    def __str__(self):
        return f"{self.display_label} — KES {self.amount:,.2f}"

    @property
    def display_label(self) -> str:
        if self.deduction_type == self.DeductionType.OTHER and self.description:
            return self.description
        return self.get_deduction_type_display()


class MpesaStkRequest(models.Model):
    """Tracks an STK push for an invoice payment or client account top-up."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    class Purpose(models.TextChoices):
        INVOICE_PAYMENT = "invoice_payment", "Invoice payment"
        CLIENT_TOPUP = "client_topup", "Client account top-up"

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="stk_requests",
        null=True,
        blank=True,
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="stk_requests",
        null=True,
        blank=True,
    )
    purpose = models.CharField(
        max_length=32,
        choices=Purpose.choices,
        default=Purpose.INVOICE_PAYMENT,
    )
    checkout_request_id = models.CharField(max_length=128, unique=True)
    merchant_request_id = models.CharField(max_length=128, blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    result_code = models.CharField(max_length=32, blank=True, default="")
    result_desc = models.CharField(max_length=255, blank=True, default="")
    mpesa_receipt = models.CharField(max_length=64, blank=True, default="")
    simulated = models.BooleanField(default=False)
    payment_applied = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "M-Pesa STK request"
        verbose_name_plural = "M-Pesa STK requests"

    def __str__(self):
        return f"{self.checkout_request_id} ({self.status})"

    @property
    def is_client_topup(self) -> bool:
        return self.purpose == self.Purpose.CLIENT_TOPUP


class ClientAccountTopup(models.Model):
    """Record of a client paying up (manual or M-Pesa) on their account."""

    class Method(models.TextChoices):
        MANUAL = "manual", "Manual"
        MPESA = "mpesa", "M-Pesa"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="account_topups",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=16, choices=Method.choices)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.COMPLETED,
    )
    note = models.TextField(blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")
    mpesa_receipt = models.CharField(max_length=64, blank=True, default="")
    balance_after = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    stk_request = models.OneToOneField(
        MpesaStkRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="client_topup",
    )
    created_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="client_account_topups_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Client account top-up"
        verbose_name_plural = "Client account top-ups"

    def __str__(self):
        return f"{self.client}: +{self.amount} ({self.method})"


class NewsSearchJob(models.Model):
    """Persistent progress and result state for a cancellable news search."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    requested_by = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="news_search_jobs",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.QUEUED,
    )
    progress = models.PositiveSmallIntegerField(default=0)
    progress_label = models.CharField(max_length=160, blank=True, default="Queued")
    filters = models.JSONField(default=dict)
    result = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=500, blank=True, default="")
    cancel_requested = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["requested_by", "status", "-created_at"]),
        ]

    def __str__(self):
        return f"News search {self.pk} ({self.status}, {self.progress}%)"


class SystemRequestMetric(models.Model):
    """Privacy-safe request and database timing used by IT diagnostics."""

    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=8)
    status_code = models.PositiveSmallIntegerField()
    duration_ms = models.FloatField()
    db_duration_ms = models.FloatField(default=0)
    db_query_count = models.PositiveIntegerField(default=0)
    response_bytes = models.PositiveBigIntegerField(default=0)
    user_role = models.CharField(max_length=32, blank=True, default="")
    error_type = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["-created_at"],
                name="system_metric_created_idx",
            ),
            models.Index(
                fields=["endpoint", "-created_at"],
                name="system_metric_route_idx",
            ),
            models.Index(
                fields=["status_code", "-created_at"],
                name="system_metric_status_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.method} {self.endpoint} "
            f"{self.status_code} ({self.duration_ms:.0f} ms)"
        )


class NewsWatch(models.Model):
    """A saved news search or publisher subscription with its own schedule."""

    class Kind(models.TextChoices):
        SEARCH = "search", "Saved search"
        PUBLISHER = "publisher", "Publisher"

    class Frequency(models.TextChoices):
        HOURLY = "1h", "Every hour"
        SIX_HOURS = "6h", "Every 6 hours"
        DAILY = "24h", "Daily"

    requested_by = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="news_watches",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    name = models.CharField(max_length=180)
    key = models.CharField(max_length=64)
    filters = models.JSONField(default=dict)
    publisher_domain = models.CharField(max_length=180, blank=True, default="")
    frequency = models.CharField(
        max_length=8,
        choices=Frequency.choices,
        default=Frequency.DAILY,
    )
    is_active = models.BooleanField(default=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    next_check_at = models.DateTimeField(null=True, blank=True)
    check_started_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["requested_by", "key"],
                name="unique_employee_news_watch",
            )
        ]
        indexes = [
            models.Index(
                fields=["is_active", "next_check_at"],
                name="news_watch_due_idx",
            ),
            models.Index(
                fields=["requested_by", "is_active"],
                name="news_watch_owner_idx",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"


class NewsWatchArticle(models.Model):
    """An article already observed for a watch, used for notification deduplication."""

    watch = models.ForeignKey(
        NewsWatch,
        on_delete=models.CASCADE,
        related_name="articles",
    )
    fingerprint = models.CharField(max_length=64)
    title = models.CharField(max_length=500)
    url = models.URLField(max_length=1000)
    source_name = models.CharField(max_length=180, blank=True, default="")
    published_at = models.CharField(max_length=100, blank=True, default="")
    description = models.TextField(blank=True, default="")
    article_data = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-first_seen_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["watch", "fingerprint"],
                name="unique_news_watch_article",
            )
        ]
        indexes = [
            models.Index(
                fields=["watch", "-first_seen_at"],
                name="news_watch_article_idx",
            ),
        ]

    def __str__(self):
        return f"{self.title} — {self.watch.name}"


class FinanceSettings(models.Model):
    """
    Firm-wide payment methods and M-Pesa configuration (singleton, pk=1).
    """

    class MpesaStkChannel(models.TextChoices):
        PAYBILL = "paybill", "Paybill"
        BUY_GOODS = "buy_goods", "Buy Goods (Till)"

    class MpesaEnv(models.TextChoices):
        SANDBOX = "sandbox", "Sandbox"
        PRODUCTION = "production", "Production"

    allow_mpesa = models.BooleanField(default=True)
    allow_bank_transfer = models.BooleanField(default=True)
    allow_cash = models.BooleanField(default=True)
    allow_cheque = models.BooleanField(default=False)

    mpesa_paybill_enabled = models.BooleanField(default=False)
    mpesa_paybill_number = models.CharField(max_length=20, blank=True, default="")
    mpesa_paybill_account_label = models.CharField(
        max_length=64,
        blank=True,
        default="Invoice number",
        help_text="What clients enter as the account reference for Paybill.",
    )

    mpesa_buy_goods_enabled = models.BooleanField(default=False)
    mpesa_till_number = models.CharField(max_length=20, blank=True, default="")

    mpesa_stk_enabled = models.BooleanField(default=False)
    mpesa_stk_channel = models.CharField(
        max_length=16,
        choices=MpesaStkChannel.choices,
        default=MpesaStkChannel.PAYBILL,
    )
    mpesa_consumer_key = models.CharField(max_length=255, blank=True, default="")
    mpesa_consumer_secret = models.CharField(max_length=255, blank=True, default="")
    mpesa_passkey = models.CharField(max_length=255, blank=True, default="")
    mpesa_shortcode = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Daraja BusinessShortCode. Defaults to Paybill or Till when blank.",
    )
    mpesa_callback_url = models.URLField(blank=True, default="")
    mpesa_env = models.CharField(
        max_length=16,
        choices=MpesaEnv.choices,
        default=MpesaEnv.SANDBOX,
    )

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finance_settings_updates",
    )

    class Meta:
        verbose_name = "Finance settings"
        verbose_name_plural = "Finance settings"

    def __str__(self):
        methods = []
        if self.allow_mpesa:
            methods.append("M-Pesa")
        if self.allow_bank_transfer:
            methods.append("Bank")
        if self.allow_cash:
            methods.append("Cash")
        if self.allow_cheque:
            methods.append("Cheque")
        return "Finance settings (" + (", ".join(methods) or "none") + ")"

    @classmethod
    def get_solo(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        if created:
            from django.conf import settings as django_settings

            key = getattr(django_settings, "MPESA_CONSUMER_KEY", "") or ""
            secret = getattr(django_settings, "MPESA_CONSUMER_SECRET", "") or ""
            shortcode = getattr(django_settings, "MPESA_SHORTCODE", "") or ""
            passkey = getattr(django_settings, "MPESA_PASSKEY", "") or ""
            callback = getattr(django_settings, "MPESA_CALLBACK_URL", "") or ""
            env = getattr(django_settings, "MPESA_ENV", "sandbox") or "sandbox"
            if key or secret or shortcode or passkey:
                obj.mpesa_consumer_key = key
                obj.mpesa_consumer_secret = secret
                obj.mpesa_passkey = passkey
                obj.mpesa_shortcode = shortcode
                obj.mpesa_callback_url = callback
                obj.mpesa_env = (
                    cls.MpesaEnv.PRODUCTION
                    if env.lower() == "production"
                    else cls.MpesaEnv.SANDBOX
                )
                if shortcode:
                    obj.mpesa_paybill_enabled = True
                    obj.mpesa_paybill_number = shortcode
                obj.save()
        return obj

    @property
    def enabled_payment_methods(self) -> list[str]:
        labels = []
        if self.allow_mpesa:
            labels.append("M-Pesa")
        if self.allow_bank_transfer:
            labels.append("Bank transfer")
        if self.allow_cash:
            labels.append("Cash")
        if self.allow_cheque:
            labels.append("Cheque")
        return labels

    @property
    def stk_business_shortcode(self) -> str:
        if self.mpesa_shortcode.strip():
            return self.mpesa_shortcode.strip()
        if self.mpesa_stk_channel == self.MpesaStkChannel.BUY_GOODS:
            return self.mpesa_till_number.strip()
        return self.mpesa_paybill_number.strip()

    @property
    def stk_transaction_type(self) -> str:
        if self.mpesa_stk_channel == self.MpesaStkChannel.BUY_GOODS:
            return "CustomerBuyGoodsOnline"
        return "CustomerPayBillOnline"

    @property
    def stk_ready(self) -> bool:
        return bool(
            self.allow_mpesa
            and self.mpesa_stk_enabled
            and self.mpesa_consumer_key.strip()
            and self.mpesa_consumer_secret.strip()
            and self.mpesa_passkey.strip()
            and self.stk_business_shortcode
        )


class CompanyExpenseAccount(models.Model):
    """
    Firm expense / company account registered under Finance → Company Accounts.
    Includes system default ledgers seeded by `ensure_default_accounts`.
    """

    SYSTEM_MAIN_CLIENT_ACCOUNTS = "main_client_accounts"
    SYSTEM_PETTY_CASH_BOOK = "petty_cash_book"

    class PaymentMethod(models.TextChoices):
        MPESA = "mpesa", "M-Pesa"
        BANK_TRANSFER = "bank_transfer", "Bank transfer"
        CASH = "cash", "Cash"
        CHEQUE = "cheque", "Cheque"

    name = models.CharField(
        max_length=255,
        verbose_name="Account name",
    )
    bank_name = models.CharField(
        max_length=255,
        verbose_name="Bank name",
        help_text="Bank holding the money for this expense account.",
    )
    bank_account_number = models.CharField(
        max_length=64,
        verbose_name="Bank account number",
    )
    description = models.TextField(blank=True, default="")
    system_key = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="Stable key for system default accounts. Null for user-created accounts.",
    )
    payment_methods = models.JSONField(
        default=list,
        blank=True,
        help_text="List of payment method keys used for this expense account.",
    )
    balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Current balance",
    )
    created_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_expense_accounts_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        verbose_name = "Company expense account"
        verbose_name_plural = "Company expense accounts"

    def __str__(self):
        return f"{self.name} ({self.bank_name})"

    @property
    def is_system_default(self) -> bool:
        return bool(self.system_key)

    @property
    def payment_method_labels(self) -> list[str]:
        labels = dict(self.PaymentMethod.choices)
        return [
            labels.get(key, key)
            for key in (self.payment_methods or [])
            if key in labels
        ]

    @classmethod
    def ensure_default_accounts(cls):
        """Create built-in company ledgers if they are missing."""
        defaults = [
            {
                "system_key": cls.SYSTEM_MAIN_CLIENT_ACCOUNTS,
                "name": "Main Client Accounts",
                "bank_name": "System ledger",
                "bank_account_number": "MAIN-CLIENT",
                "description": "Money from invoices and clients",
                "payment_methods": [choice.value for choice in cls.PaymentMethod],
            },
            {
                "system_key": cls.SYSTEM_PETTY_CASH_BOOK,
                "name": "Petty Cash Book",
                "bank_name": "System ledger",
                "bank_account_number": "PETTY-CASH",
                "description": "Daily unplanned expenses",
                "payment_methods": [
                    cls.PaymentMethod.CASH,
                    cls.PaymentMethod.MPESA,
                ],
            },
        ]
        created = []
        for spec in defaults:
            account, was_created = cls.objects.get_or_create(
                system_key=spec["system_key"],
                defaults={
                    "name": spec["name"],
                    "bank_name": spec["bank_name"],
                    "bank_account_number": spec["bank_account_number"],
                    "description": spec["description"],
                    "payment_methods": spec["payment_methods"],
                    "balance": Decimal("0.00"),
                },
            )
            if was_created:
                created.append(account)
            elif not (account.description or "").strip():
                account.description = spec["description"]
                account.save(update_fields=["description", "updated_at"])
        return created

    @classmethod
    def get_main_client_accounts(cls):
        cls.ensure_default_accounts()
        return cls.objects.get(system_key=cls.SYSTEM_MAIN_CLIENT_ACCOUNTS)

    @classmethod
    def get_petty_cash_book(cls):
        cls.ensure_default_accounts()
        return cls.objects.get(system_key=cls.SYSTEM_PETTY_CASH_BOOK)

    @classmethod
    def credit_main_client_accounts(
        cls,
        *,
        amount,
        source_client=None,
        source_note="",
        created_by=None,
    ):
        """
        Top up the Main Client Accounts ledger (invoice / client money in).
        Returns the CompanyAccountTopup row, or None when amount is zero.
        """
        pay = Decimal(amount).quantize(Decimal("0.01"))
        if pay <= 0:
            return None

        with transaction.atomic():
            cls.ensure_default_accounts()
            locked = cls.objects.select_for_update().get(
                system_key=cls.SYSTEM_MAIN_CLIENT_ACCOUNTS
            )
            cls.objects.filter(pk=locked.pk).update(balance=F("balance") + pay)
            locked.refresh_from_db(fields=["balance"])
            return CompanyAccountTopup.objects.create(
                account=locked,
                amount=pay,
                source_type=CompanyAccountTopup.SourceType.CLIENT,
                source_client=source_client,
                source_note=(source_note or "").strip(),
                balance_after=locked.balance,
                created_by=created_by,
            )


class CompanyAccountTopup(models.Model):
    """Income added to a company expense account."""

    class SourceType(models.TextChoices):
        CLIENT = "client", "Client"
        COMPANY_ACCOUNT = "company_account", "Company account"
        OTHER = "other", "Others"

    account = models.ForeignKey(
        CompanyExpenseAccount,
        on_delete=models.CASCADE,
        related_name="topups",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    source_type = models.CharField(
        max_length=32,
        choices=SourceType.choices,
        default=SourceType.OTHER,
    )
    source_client = models.ForeignKey(
        "Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_account_topups",
    )
    source_company_account = models.ForeignKey(
        CompanyExpenseAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="topups_as_source",
    )
    source_note = models.TextField(
        blank=True,
        default="",
        verbose_name="Source note",
        help_text="Free-text source when Others is selected.",
    )
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    created_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_account_topups_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Company account top-up"
        verbose_name_plural = "Company account top-ups"

    def __str__(self):
        return f"{self.account.name}: +{self.amount}"

    @property
    def source_display(self) -> str:
        if self.source_type == self.SourceType.CLIENT and self.source_client_id:
            return f"Client — {self.source_client}"
        if (
            self.source_type == self.SourceType.COMPANY_ACCOUNT
            and self.source_company_account_id
        ):
            return f"Company account — {self.source_company_account.name}"
        note = (self.source_note or "").strip()
        if note:
            return f"Others — {note}"
        return self.get_source_type_display()


class CompanyExpensePayment(models.Model):
    """Money paid out from a company account for an expense."""

    class ExpenseType(models.TextChoices):
        OFFICE_SUPPLIES = "office_supplies", "Office supplies"
        TRANSPORT = "transport", "Transport / travel"
        UTILITIES = "utilities", "Utilities"
        COMMUNICATION = "communication", "Communication"
        COURT_FEES = "court_fees", "Court fees"
        FILING_FEES = "filing_fees", "Filing fees"
        PROFESSIONAL_FEES = "professional_fees", "Professional fees"
        PAYROLL = "payroll", "Payroll"
        STAFF_WELFARE = "staff_welfare", "Staff welfare"
        MAINTENANCE = "maintenance", "Maintenance / repairs"
        BANK_CHARGES = "bank_charges", "Bank charges"
        RENT = "rent", "Rent"
        OTHER = "other", "Other"

    account = models.ForeignKey(
        CompanyExpenseAccount,
        on_delete=models.CASCADE,
        related_name="expense_payments",
    )
    expense_type = models.CharField(
        max_length=32,
        choices=ExpenseType.choices,
        default=ExpenseType.OTHER,
    )
    description = models.TextField(
        help_text="What this expense payment covers.",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    employee = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_expense_payments",
        help_text="Set when expense type is Payroll.",
    )
    payroll_payment = models.ForeignKey(
        "PayrollPayment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expense_payments",
    )
    created_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_expense_payments_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Company expense payment"
        verbose_name_plural = "Company expense payments"

    def __str__(self):
        return f"{self.account.name}: -{self.amount} ({self.get_expense_type_display()})"


class PettyCashExpenseRequest(models.Model):
    """
    Employee petty-cash expense claim.

    Submitted from Employee Petty Cashbook as pending; approved from the
    company Petty Cash Book page (debits the system Petty Cash Book ledger).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="petty_cash_expense_requests",
        help_text="Employee the expense is claimed for.",
    )
    expense_type = models.CharField(
        max_length=32,
        choices=CompanyExpensePayment.ExpenseType.choices,
        default=CompanyExpensePayment.ExpenseType.OTHER,
    )
    description = models.TextField(
        help_text="What this petty cash expense covers.",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    submitted_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="petty_cash_expense_requests_submitted",
    )
    reviewed_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="petty_cash_expense_requests_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")
    expense_payment = models.OneToOneField(
        CompanyExpensePayment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="petty_cash_request",
        help_text="Ledger payment created when this request is approved.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Petty cash expense request"
        verbose_name_plural = "Petty cash expense requests"

    def __str__(self):
        return (
            f"{self.employee} · KES {self.amount:,.2f} "
            f"({self.get_status_display()})"
        )

    @classmethod
    def pending_count(cls) -> int:
        return cls.objects.filter(status=cls.Status.PENDING).count()


class CommunicationSettings(models.Model):
    """
    Firm-wide email, SMS, and WhatsApp provider configuration (singleton, pk=1).
    """

    class SmsProvider(models.TextChoices):
        NONE = "none", "Not set"
        AFRICASTALKING = "africastalking", "Africa's Talking"
        TWILIO = "twilio", "Twilio"

    class WhatsAppProvider(models.TextChoices):
        NONE = "none", "Not set"
        META = "meta", "Meta Cloud API"
        TWILIO = "twilio", "Twilio"

    # --- Email (SMTP) ---
    email_enabled = models.BooleanField(default=False)
    email_host = models.CharField(max_length=255, blank=True, default="")
    email_port = models.PositiveIntegerField(default=587)
    email_use_tls = models.BooleanField(default=True)
    email_use_ssl = models.BooleanField(default=False)
    email_host_user = models.CharField(max_length=255, blank=True, default="")
    email_host_password = models.CharField(max_length=255, blank=True, default="")
    email_from_email = models.EmailField(blank=True, default="")
    email_from_name = models.CharField(max_length=120, blank=True, default="")

    @staticmethod
    def smtp_security_for_port(port: int | None) -> tuple[bool, bool]:
        """
        Auto-select SMTP security from port.
        Returns (use_tls, use_ssl).
        """
        try:
            port_n = int(port or 0)
        except (TypeError, ValueError):
            port_n = 0
        if port_n in {465, 994}:
            return False, True
        # 587 / 2587 / 25 and anything else: prefer STARTTLS
        return True, False

    @staticmethod
    def smtp_security_label(port: int | None) -> str:
        use_tls, use_ssl = CommunicationSettings.smtp_security_for_port(port)
        if use_ssl:
            return "SSL (auto)"
        if use_tls:
            return "TLS (auto)"
        return "None"

    @property
    def email_security_label(self) -> str:
        return self.smtp_security_label(self.email_port)

    # --- SMS ---
    sms_enabled = models.BooleanField(default=False)
    sms_provider = models.CharField(
        max_length=32,
        choices=SmsProvider.choices,
        default=SmsProvider.NONE,
    )
    sms_username = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Africa's Talking username (or Twilio Account SID).",
    )
    sms_api_key = models.CharField(max_length=255, blank=True, default="")
    sms_api_secret = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Twilio Auth Token when using Twilio.",
    )
    sms_sender_id = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Sender ID or from-number shown on SMS.",
    )

    # --- WhatsApp ---
    whatsapp_enabled = models.BooleanField(default=False)
    whatsapp_business_number = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Business WhatsApp number for click-to-chat (e.g. +2547…).",
    )
    whatsapp_default_message = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Pre-filled message when opening WhatsApp chat.",
    )
    whatsapp_api_enabled = models.BooleanField(default=False)
    whatsapp_provider = models.CharField(
        max_length=32,
        choices=WhatsAppProvider.choices,
        default=WhatsAppProvider.NONE,
    )
    whatsapp_api_token = models.CharField(max_length=512, blank=True, default="")
    whatsapp_phone_number_id = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Meta Phone Number ID, or Twilio WhatsApp sender.",
    )
    whatsapp_webhook_url = models.URLField(blank=True, default="")

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="communication_settings_updates",
    )

    class Meta:
        verbose_name = "Communication settings"
        verbose_name_plural = "Communication settings"

    def __str__(self):
        channels = []
        if self.email_enabled:
            channels.append("Email")
        if self.sms_enabled:
            channels.append("SMS")
        if self.whatsapp_enabled:
            channels.append("WhatsApp")
        return "Communication settings (" + (", ".join(channels) or "none") + ")"

    @classmethod
    def get_solo(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        if created:
            from django.conf import settings as django_settings

            host = getattr(django_settings, "EMAIL_HOST", "") or ""
            user = getattr(django_settings, "EMAIL_HOST_USER", "") or ""
            password = getattr(django_settings, "EMAIL_HOST_PASSWORD", "") or ""
            from_email = getattr(django_settings, "DEFAULT_FROM_EMAIL", "") or ""
            port = getattr(django_settings, "EMAIL_PORT", None)
            use_tls = getattr(django_settings, "EMAIL_USE_TLS", None)
            use_ssl = getattr(django_settings, "EMAIL_USE_SSL", None)
            if host or user or from_email:
                obj.email_enabled = True
                obj.email_host = host
                obj.email_host_user = user
                obj.email_host_password = password
                obj.email_from_email = from_email
                if port is not None:
                    try:
                        obj.email_port = int(port)
                    except (TypeError, ValueError):
                        pass
                if use_tls is not None:
                    obj.email_use_tls = bool(use_tls)
                if use_ssl is not None:
                    obj.email_use_ssl = bool(use_ssl)
                obj.save()
        return obj

    @property
    def enabled_channels(self) -> list[str]:
        labels = []
        if self.email_enabled:
            labels.append("Email")
        if self.sms_enabled:
            labels.append("SMS")
        if self.whatsapp_enabled:
            labels.append("WhatsApp")
        return labels

    @property
    def email_ready(self) -> bool:
        return bool(
            self.email_enabled
            and self.email_host.strip()
            and self.email_from_email.strip()
            and self.email_port
        )

    @property
    def sms_ready(self) -> bool:
        if not self.sms_enabled:
            return False
        if self.sms_provider == self.SmsProvider.AFRICASTALKING:
            return bool(
                self.sms_username.strip()
                and self.sms_api_key.strip()
                and self.sms_sender_id.strip()
            )
        if self.sms_provider == self.SmsProvider.TWILIO:
            return bool(
                self.sms_username.strip()
                and self.sms_api_secret.strip()
                and self.sms_sender_id.strip()
            )
        return False

    @property
    def whatsapp_ready(self) -> bool:
        if not self.whatsapp_enabled:
            return False
        if self.whatsapp_api_enabled:
            return bool(
                self.whatsapp_provider != self.WhatsAppProvider.NONE
                and self.whatsapp_api_token.strip()
                and self.whatsapp_phone_number_id.strip()
            )
        return bool(self.whatsapp_business_number.strip())


class RoleActivityPermission(models.Model):
    """Per-role lock for a system-module activity (default allow when no row)."""

    role = models.CharField(max_length=32, choices=Employee.Role.choices)
    module_slug = models.SlugField(max_length=64)
    activity_slug = models.SlugField(max_length=64)
    is_allowed = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="role_activity_permission_updates",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["role", "module_slug", "activity_slug"],
                name="uniq_role_module_activity_permission",
            )
        ]
        ordering = ["module_slug", "activity_slug", "role"]
        verbose_name = "Role activity permission"
        verbose_name_plural = "Role activity permissions"

    def __str__(self):
        state = "allowed" if self.is_allowed else "locked"
        return f"{self.role} / {self.module_slug}/{self.activity_slug}: {state}"


class EmployeeActivityPermission(models.Model):
    """Per-employee action lock within a system-module activity."""

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="activity_action_permissions",
    )
    module_slug = models.SlugField(max_length=64)
    activity_slug = models.SlugField(max_length=64)
    action = models.CharField(max_length=32)
    is_allowed = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee_activity_permission_updates",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "module_slug", "activity_slug", "action"],
                name="uniq_employee_module_activity_action",
            )
        ]
        ordering = ["module_slug", "activity_slug", "employee_id", "action"]
        verbose_name = "Employee activity permission"
        verbose_name_plural = "Employee activity permissions"

    def __str__(self):
        state = "allowed" if self.is_allowed else "locked"
        return (
            f"{self.employee_id} / {self.module_slug}/{self.activity_slug}"
            f"/{self.action}: {state}"
        )


class EmployeeWorkSession(models.Model):
    """Login, logout, and active working time for an employee workspace session."""

    class LogoutKind(models.TextChoices):
        MANUAL = "manual", "Signed out"
        EXPIRED = "expired", "Session expired"
        REPLACED = "replaced", "New login"

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="work_sessions",
    )
    session_key = models.CharField(max_length=64, blank=True, default="")
    login_at = models.DateTimeField()
    logout_at = models.DateTimeField(blank=True, null=True)
    last_active_at = models.DateTimeField()
    working_seconds = models.PositiveIntegerField(default=0)
    logout_kind = models.CharField(
        max_length=16,
        choices=LogoutKind.choices,
        blank=True,
        default="",
    )

    class Meta:
        ordering = ["-login_at", "-id"]
        indexes = [
            models.Index(fields=["employee", "-login_at"]),
            models.Index(fields=["session_key", "logout_at"]),
        ]
        verbose_name = "Employee work session"
        verbose_name_plural = "Employee work sessions"

    def __str__(self):
        label = self.employee.get_full_name() if self.employee_id else "Employee"
        return f"{label} session from {self.login_at:%Y-%m-%d %H:%M}"

    @property
    def is_active(self) -> bool:
        return self.logout_at is None

    @property
    def duration_seconds(self) -> int:
        end = self.logout_at or timezone.now()
        return max(0, int((end - self.login_at).total_seconds()))

    @property
    def live_working_seconds(self) -> int:
        total = self.working_seconds or 0
        if not self.is_active or not self.last_active_at:
            return total
        gap = (timezone.now() - self.last_active_at).total_seconds()
        if gap <= IDLE_TIMEOUT_SECONDS:
            total += int(gap)
        return total


IDLE_TIMEOUT_SECONDS = 15 * 60
