from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_date
from django.utils import timezone
from decimal import Decimal

from .country_codes import (
    COUNTRY_DIAL_CODES,
    DEFAULT_COUNTRY,
    countries_for_js,
    country_choices,
    dial_for_iso,
    nationality_choices,
    parse_country_value,
)
from .models import (
    CaseParty,
    CaseTask,
    Client,
    CompanyExpenseAccount,
    CompanyAccountTopup,
    CompanyExpensePayment,
    ClientAccountTopup,
    CourtAttendance,
    CourtAttendanceAdvocate,
    CourtAttendanceBringUpItem,
    Employee,
    EmployeeBlogPost,
    CommunicationSettings,
    CompanyLetterheadSetting,
    CompanyDigitalStampSetting,
    CompanyDigitalSignatureSetting,
    EmployeeDigitalStampSetting,
    CompanyThemeSetting,
    FinanceSettings,
    FirmCompanyInformation,
    FirmFAQ,
    FirmGalleryImage,
    FirmPracticeArea,
    Invoice,
    LitigationCase,
    MatterAttendance,
    MatterAttendanceBringUpItem,
    MatterAttendanceQuorumMember,
    MatterParty,
    MatterTask,
    NonLitigationMatter,
    PayrollDeduction,
    PayrollRun,
    EmployeeAdvance,
    PettyCashExpenseRequest,
    WebsiteTemplateSetting,
)
from .utils import optimize_image, optimize_logo, optimize_profile_photo


class LatestNewsScrapeForm(forms.Form):
    INDUSTRY_CHOICES = (
        ("legal", "Legal and justice"),
        ("finance", "Finance and banking"),
        ("technology", "Technology"),
        ("healthcare", "Healthcare"),
        ("energy", "Energy"),
        ("real-estate", "Real estate"),
        ("agriculture", "Agriculture"),
        ("manufacturing", "Manufacturing"),
        ("telecommunications", "Telecommunications"),
        ("transport", "Transport and logistics"),
        ("education", "Education"),
        ("government", "Government and public policy"),
        ("entertainment", "Media and entertainment"),
        ("sports", "Sports"),
        ("other", "Other"),
    )
    PERIOD_CHOICES = (
        ("1d", "Past 24 hours"),
        ("7d", "Past 7 days"),
        ("30d", "Past 30 days"),
    )
    LANGUAGE_CHOICES = (
        ("en", "English"),
        ("sw", "Swahili"),
        ("fr", "French"),
        ("ar", "Arabic"),
        ("de", "German"),
        ("es", "Spanish"),
        ("pt", "Portuguese"),
    )
    SORT_CHOICES = (
        ("relevance", "Most relevant"),
        ("newest", "Newest first"),
        ("credibility", "Source credibility"),
    )

    country = forms.ChoiceField(
        label="Country",
        choices=[(iso, name) for iso, name, _dial in COUNTRY_DIAL_CODES],
        initial=DEFAULT_COUNTRY,
        widget=forms.Select(attrs={"class": "form-input"}),
    )
    industry = forms.ChoiceField(
        label="Industry",
        choices=INDUSTRY_CHOICES,
        initial="legal",
        widget=forms.Select(attrs={"class": "form-input"}),
    )
    period = forms.ChoiceField(
        label="Published within",
        choices=PERIOD_CHOICES,
        initial="7d",
        widget=forms.Select(attrs={"class": "form-input"}),
    )
    language = forms.ChoiceField(
        label="Language",
        choices=LANGUAGE_CHOICES,
        initial="en",
        widget=forms.Select(attrs={"class": "form-input"}),
    )
    sort_by = forms.ChoiceField(
        label="Sort results",
        choices=SORT_CHOICES,
        initial="relevance",
        widget=forms.Select(attrs={"class": "form-input"}),
    )
    requested_details = forms.CharField(
        label="Topic or details to narrow the news",
        max_length=500,
        widget=forms.Textarea(
            attrs={
                "class": "form-input",
                "rows": 3,
                "placeholder": (
                    "Example: employment court rulings involving unfair dismissal "
                    "and compensation awards"
                ),
            }
        ),
    )

    def clean_requested_details(self):
        value = " ".join(self.cleaned_data["requested_details"].split())
        if len(value) < 3:
            raise ValidationError("Add a topic, keyword or other detail.")
        return value

    exact_phrase = forms.CharField(
        label="Exact phrase",
        max_length=160,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Example: unfair termination",
            }
        ),
    )
    excluded_words = forms.CharField(
        label="Exclude words",
        max_length=200,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Separate words with commas",
            }
        ),
    )
    source_domain = forms.CharField(
        label="Only show this publisher or domain",
        max_length=160,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Example: reuters.com",
            }
        ),
    )

    def clean_exact_phrase(self):
        return " ".join(self.cleaned_data.get("exact_phrase", "").split())

    def clean_excluded_words(self):
        raw = self.cleaned_data.get("excluded_words", "")
        values = [part.strip() for part in raw.replace(";", ",").split(",")]
        return ", ".join(value for value in values if value)

    def clean_source_domain(self):
        value = self.cleaned_data.get("source_domain", "").strip().lower()
        value = value.removeprefix("https://").removeprefix("http://")
        return value.split("/", 1)[0].removeprefix("www.")


ALLOWED_CLIENT_EMAIL_DOMAINS = (
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.co.uk",
    "yahoo.co.ke",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "icloud.com",
    "me.com",
    "proton.me",
    "protonmail.com",
    "aol.com",
)


def client_email_provider(email: str) -> str:
    domain = (email or "").rsplit("@", 1)[-1].lower().strip()
    if domain in ("gmail.com", "googlemail.com"):
        return "google"
    if domain.startswith("yahoo."):
        return "yahoo"
    if domain in ("outlook.com", "hotmail.com", "live.com", "msn.com"):
        return "microsoft"
    if domain in ("icloud.com", "me.com", "mac.com"):
        return "apple"
    if domain in ("proton.me", "protonmail.com"):
        return "proton"
    return "email"


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="6-digit login code",
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "e.g. 123456",
                "inputmode": "numeric",
                "pattern": r"\d{6}",
                "maxlength": "6",
                "autocomplete": "username",
                "id": "id_login_code",
            }
        ),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-input",
                "placeholder": "Password",
                "autocomplete": "current-password",
                "id": "id_password",
            }
        )
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Invalid login code or password.",
        "suspended": "This account has been suspended.",
    }

    def clean(self):
        login_code = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if login_code and password:
            login_code = str(login_code).strip()
            password = str(password).upper()
            self.cleaned_data["password"] = password
            if not login_code.isdigit() or len(login_code) != 6:
                raise ValidationError(
                    "Login code must be exactly 6 digits.",
                    code="invalid_login",
                )

            try:
                employee = Employee.objects.get(login_code=login_code)
            except Employee.DoesNotExist:
                raise self.get_invalid_login_error() from None

            if employee.status == Employee.Status.SUSPENDED:
                self.user_cache = None
                raise ValidationError(
                    self.error_messages["suspended"],
                    code="suspended",
                )

            self.user_cache = authenticate(
                self.request,
                username=login_code,
                password=password,
            )
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


class SignUpForm(UserCreationForm):
    courtesy_title = forms.ChoiceField(
        choices=[("", "Title")] + list(Employee.CourtesyTitle.choices),
        widget=forms.Select(
            attrs={
                "class": "form-input form-input--title",
                "autocomplete": "honorific-prefix",
                "aria-label": "Title",
                "title": "Courtesy title",
                "required": True,
                "id": "id_courtesy_title",
            }
        ),
    )
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "First name",
                "autocomplete": "given-name",
            }
        ),
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Last name",
                "autocomplete": "family-name",
            }
        ),
    )
    personal_email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-input",
                "placeholder": "Personal email",
                "autocomplete": "email",
            }
        ),
    )
    country_code = forms.ChoiceField(
        choices=country_choices(),
        initial=f"{DEFAULT_COUNTRY}|+254",
        widget=forms.HiddenInput(attrs={"id": "id_country_code"}),
    )
    personal_phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "class": "form-input phone-local-input",
                "placeholder": "712 345 678",
                "autocomplete": "tel-national",
                "inputmode": "tel",
                "id": "id_personal_phone",
            }
        ),
    )
    id_type = forms.ChoiceField(
        choices=Employee.IdType.choices,
        widget=forms.RadioSelect(attrs={"class": "radio-group"}),
    )
    id_country = forms.ChoiceField(
        choices=nationality_choices(),
        initial=DEFAULT_COUNTRY,
        widget=forms.HiddenInput(attrs={"id": "id_id_country"}),
    )
    alien_number = forms.CharField(
        required=False,
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Alien / permit number",
            }
        ),
    )
    login_code = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Choose 6 digits",
                "inputmode": "numeric",
                "pattern": r"\d{6}",
                "maxlength": "6",
                "autocomplete": "off",
                "id": "id_login_code",
            }
        ),
    )
    profile_photo = forms.ImageField(
        required=False,
        widget=forms.FileInput(
            attrs={
                "class": "form-input form-input--file",
                "accept": "image/*",
                "capture": "user",
                "id": "id_profile_photo",
            }
        ),
    )
    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-input",
                "placeholder": "e.g. 000000",
                "autocomplete": "new-password",
                "id": "id_password1",
                "minlength": "6",
            }
        ),
    )
    password2 = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-input",
                "placeholder": "Re-enter password",
                "autocomplete": "new-password",
                "id": "id_password2",
                "minlength": "6",
            }
        ),
    )

    class Meta:
        model = Employee
        fields = (
            "courtesy_title",
            "first_name",
            "last_name",
            "personal_email",
            "personal_phone",
            "id_type",
            "id_country",
            "alien_number",
            "login_code",
            "password1",
            "password2",
            "profile_photo",
        )

    UPPERCASE_FIELDS = (
        "first_name",
        "last_name",
        "personal_phone",
        "alien_number",
        "login_code",
        "password1",
        "password2",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["id_type"].initial = Employee.IdType.CITIZEN
        self.fields["country_code"].initial = dial_for_iso(DEFAULT_COUNTRY)
        self.fields["id_country"].initial = DEFAULT_COUNTRY
        self.countries_json = countries_for_js()
        self.default_country = DEFAULT_COUNTRY
        for name in self.UPPERCASE_FIELDS:
            if name in self.fields:
                attrs = self.fields[name].widget.attrs
                attrs["class"] = f"{attrs.get('class', '')} input-uppercase".strip()
                attrs["autocapitalize"] = "characters"

    def clean_first_name(self):
        return self.cleaned_data["first_name"].strip().upper()

    def clean_courtesy_title(self):
        title = (self.cleaned_data.get("courtesy_title") or "").strip()
        if not title:
            raise ValidationError("Please select a courtesy title.")
        return title

    def clean_last_name(self):
        return self.cleaned_data["last_name"].strip().upper()

    def clean_personal_phone(self):
        raw = self.cleaned_data["personal_phone"].strip().upper()
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) < 7 or len(digits) > 15:
            raise ValidationError("Enter a valid phone number (7–15 digits).")
        # Drop a single leading 0 (common local format) before adding country code.
        if digits.startswith("0"):
            digits = digits[1:]
        if len(digits) < 6:
            raise ValidationError("Enter a valid phone number.")
        return digits

    def clean_alien_number(self):
        return (self.cleaned_data.get("alien_number") or "").strip().upper()

    def clean_login_code(self):
        code = self.cleaned_data["login_code"].strip().upper()
        if not code.isdigit() or len(code) != 6:
            raise ValidationError("Login code must be exactly 6 digits.")
        if Employee.objects.filter(login_code=code).exists():
            raise ValidationError("This login code is already taken.")
        return code

    def clean_personal_email(self):
        email = self.cleaned_data["personal_email"].lower().strip()
        if Employee.objects.filter(personal_email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean_password1(self):
        password = (self.cleaned_data.get("password1") or "").upper()
        if not password:
            raise ValidationError("Password is required.")
        if len(password) < 6:
            raise ValidationError("Password must be at least 6 characters.")
        validate_password(password, user=None)
        return password

    def clean_password2(self):
        return (self.cleaned_data.get("password2") or "").upper()

    def clean(self):
        cleaned = super().clean()
        id_type = cleaned.get("id_type")
        alien_number = (cleaned.get("alien_number") or "").strip()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        country_value = cleaned.get("country_code")
        local_phone = cleaned.get("personal_phone")

        if country_value and local_phone and "personal_phone" not in self.errors:
            _iso, dial = parse_country_value(country_value)
            cleaned["full_personal_phone"] = f"{dial}{local_phone}"

        if id_type == Employee.IdType.CITIZEN:
            cleaned["alien_number"] = ""
        elif id_type == Employee.IdType.NON_CITIZEN:
            if not alien_number:
                self.add_error(
                    "alien_number",
                    "Alien number is required for non-citizens.",
                )

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Passwords do not match.")

        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.courtesy_title = self.cleaned_data.get("courtesy_title", "")
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.personal_email = self.cleaned_data["personal_email"]
        user.personal_phone = self.cleaned_data.get(
            "full_personal_phone", self.cleaned_data["personal_phone"]
        )
        user.id_type = self.cleaned_data["id_type"]
        user.id_country = self.cleaned_data.get("id_country", DEFAULT_COUNTRY)
        user.identification_number = ""
        user.alien_number = self.cleaned_data.get("alien_number", "")
        user.login_code = self.cleaned_data["login_code"]
        user.role = Employee.Role.EMPLOYEE
        user.status = Employee.Status.PENDING_ONBOARDING
        user.work_email = None
        user.work_phone = None

        photo = self.cleaned_data.get("profile_photo")
        if photo:
            user.profile_photo = optimize_profile_photo(photo)

        if commit:
            user.save()
            self._sync_signup_drive_uploads(user)
        return user

    @staticmethod
    def _sync_signup_drive_uploads(user):
        """Create Work/{Name}/Personal and upload photo."""
        try:
            from .google_drive import (
                GoogleDriveAPIError,
                GoogleDriveOAuthError,
                ensure_employee_folder_structure,
                sync_employee_personal_detail_uploads,
            )
        except Exception:
            return
        try:
            ensure_employee_folder_structure(user)
            if user.profile_photo:
                sync_employee_personal_detail_uploads(
                    user, field_names=("profile_photo",)
                )
        except (GoogleDriveAPIError, GoogleDriveOAuthError):
            pass


class ClientLoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-input",
                "placeholder": "you@gmail.com",
                "autocomplete": "email",
                "id": "id_client_email",
            }
        ),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-input",
                "placeholder": "Password",
                "autocomplete": "current-password",
                "id": "id_client_password",
            }
        )
    )

    def __init__(self, *args, **kwargs):
        self.client_cache = None
        super().__init__(*args, **kwargs)

    def clean_email(self):
        return self.cleaned_data["email"].lower().strip()

    def clean(self):
        from .models import Client

        cleaned = super().clean()
        email = cleaned.get("email")
        password = cleaned.get("password")
        if not email or not password:
            return cleaned

        try:
            client = Client.objects.get(email__iexact=email)
        except Client.DoesNotExist:
            raise ValidationError("Invalid email or password.") from None

        if client.status == Client.Status.SUSPENDED:
            raise ValidationError(
                "This client account has been suspended.",
                code="suspended",
            )

        if not client.password:
            raise ValidationError(
                "This account uses Google sign-in. Choose Continue with Google.",
                code="google_only",
            )

        if not client.check_password(password):
            raise ValidationError("Invalid email or password.")

        self.client_cache = client
        return cleaned

    def get_client(self):
        return self.client_cache


def _split_phone(full_phone: str) -> tuple[str, str]:
    """Return (country_choice_value, local_digits) from a stored E.164-ish phone."""
    from .country_codes import COUNTRY_DIAL_CODES

    digits = "".join(ch for ch in (full_phone or "") if ch.isdigit() or ch == "+")
    if digits.startswith("+"):
        raw = digits
    elif digits:
        raw = f"+{digits}"
    else:
        return dial_for_iso(DEFAULT_COUNTRY), ""

    # Longest dial match wins.
    matches = sorted(COUNTRY_DIAL_CODES, key=lambda c: len(c[2]), reverse=True)
    for iso, _name, dial in matches:
        if raw.startswith(dial):
            local = raw[len(dial) :]
            return f"{iso}|{dial}", local
    return dial_for_iso(DEFAULT_COUNTRY), "".join(ch for ch in digits if ch.isdigit())


class ClientSignUpForm(forms.Form):
    client_type = forms.ChoiceField(
        choices=[],
        widget=forms.Select(
            attrs={
                "class": "form-input",
                "id": "id_client_type",
            }
        ),
    )
    first_name = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "First name",
                "autocomplete": "given-name",
                "id": "id_client_first_name",
            }
        ),
    )
    last_name = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Last name",
                "autocomplete": "family-name",
                "id": "id_client_last_name",
            }
        ),
    )
    company_name = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Company name",
                "autocomplete": "organization",
                "id": "id_client_company_name",
            }
        ),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-input",
                "placeholder": "you@gmail.com",
                "autocomplete": "email",
                "id": "id_client_email",
            }
        ),
    )
    country_code = forms.ChoiceField(
        choices=country_choices(),
        initial=f"{DEFAULT_COUNTRY}|+254",
        widget=forms.HiddenInput(attrs={"id": "id_country_code"}),
    )
    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "class": "form-input phone-local-input",
                "placeholder": "712 345 678",
                "autocomplete": "tel-national",
                "inputmode": "tel",
                "id": "id_client_phone",
            }
        ),
    )
    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-input",
                "placeholder": "Create a password",
                "autocomplete": "new-password",
                "id": "id_client_password1",
                "minlength": "6",
            }
        ),
    )
    password2 = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-input",
                "placeholder": "Re-enter password",
                "autocomplete": "new-password",
                "id": "id_client_password2",
                "minlength": "6",
            }
        ),
    )
    profile_photo = forms.ImageField(
        required=False,
        widget=forms.FileInput(
            attrs={
                "class": "form-input form-input--file",
                "accept": "image/*",
                "capture": "user",
                "id": "id_client_profile_photo",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        from .models import Client

        super().__init__(*args, **kwargs)
        self.fields["client_type"].choices = [("", "Select client type")] + list(
            Client.ClientType.choices
        )
        self.fields["country_code"].initial = dial_for_iso(DEFAULT_COUNTRY)
        self.countries_json = countries_for_js()
        for name, field in self.fields.items():
            if name in ("email", "country_code", "client_type", "profile_photo"):
                continue
            widget = field.widget
            if isinstance(
                widget,
                (forms.TextInput, forms.PasswordInput, forms.Textarea),
            ):
                attrs = widget.attrs
                attrs["class"] = f"{attrs.get('class', '')} input-uppercase".strip()
                attrs["autocapitalize"] = "characters"

    def clean_first_name(self):
        return (self.cleaned_data.get("first_name") or "").strip().upper()

    def clean_last_name(self):
        return (self.cleaned_data.get("last_name") or "").strip().upper()

    def clean_company_name(self):
        return (self.cleaned_data.get("company_name") or "").strip().upper()

    def clean_email(self):
        from .models import Client

        email = self.cleaned_data["email"].lower().strip()
        client_type = self.data.get("client_type")
        domain = email.rsplit("@", 1)[-1] if "@" in email else ""
        if client_type == "individual":
            allowed = domain in ALLOWED_CLIENT_EMAIL_DOMAINS or domain.startswith(
                "yahoo."
            )
            if not allowed:
                raise ValidationError(
                    "Use a common personal email (Google, Yahoo, Outlook, iCloud, or Proton)."
                )
        if Client.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean_phone(self):
        raw = (self.cleaned_data.get("phone") or "").strip().upper()
        digits = "".join(ch for ch in raw if ch.isdigit())
        if digits.startswith("0"):
            digits = digits[1:]
        if len(digits) < 6 or len(digits) > 15:
            raise ValidationError("Enter a valid phone number.")
        return digits

    def clean_password1(self):
        password = (self.cleaned_data.get("password1") or "").upper()
        if len(password) < 6:
            raise ValidationError("Password must be at least 6 characters.")
        validate_password(password, user=None)
        return password

    def clean_password2(self):
        return (self.cleaned_data.get("password2") or "").upper()

    def clean(self):
        from .models import Client

        cleaned = super().clean()
        client_type = cleaned.get("client_type")
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        country_value = cleaned.get("country_code")
        local_phone = cleaned.get("phone")

        if not client_type:
            self.add_error("client_type", "Select whether you are an individual or corporate client.")

        if client_type == Client.ClientType.INDIVIDUAL:
            if not cleaned.get("first_name"):
                self.add_error("first_name", "First name is required.")
            if not cleaned.get("last_name"):
                self.add_error("last_name", "Last name is required.")
            cleaned["company_name"] = ""
        elif client_type == Client.ClientType.CORPORATE:
            if not cleaned.get("company_name"):
                self.add_error("company_name", "Company name is required.")
            cleaned["first_name"] = ""
            cleaned["last_name"] = ""

        if country_value and local_phone and "phone" not in self.errors:
            _iso, dial = parse_country_value(country_value)
            cleaned["full_phone"] = f"{dial}{local_phone}"

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Passwords do not match.")
        return cleaned

    def save(self, commit=True):
        from .models import Client

        client = Client(
            email=self.cleaned_data["email"],
            client_type=self.cleaned_data["client_type"],
            first_name=self.cleaned_data.get("first_name", ""),
            last_name=self.cleaned_data.get("last_name", ""),
            company_name=self.cleaned_data.get("company_name", ""),
            phone=self.cleaned_data.get("full_phone", self.cleaned_data.get("phone", "")),
            status=Client.Status.PENDING_ONBOARDING,
        )
        client.set_password(self.cleaned_data["password1"])
        photo = self.cleaned_data.get("profile_photo")
        if photo:
            client.profile_photo = optimize_profile_photo(photo)
        if commit:
            client.save()
            self._sync_client_signup_drive_uploads(client)
        return client

    @staticmethod
    def _sync_client_signup_drive_uploads(client):
        """Create Clients/{Name}/Personal Documents and upload photo."""
        try:
            from .google_drive import (
                GoogleDriveAPIError,
                GoogleDriveOAuthError,
                ensure_client_folder_structure,
                sync_client_personal_document_uploads,
            )
        except Exception:
            return
        try:
            ensure_client_folder_structure(client)
            if client.profile_photo:
                sync_client_personal_document_uploads(
                    client, field_names=("profile_photo",)
                )
        except (GoogleDriveAPIError, GoogleDriveOAuthError):
            pass


class StaffRegisterClientForm(ClientSignUpForm):
    """IT staff register a client without collecting a password."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("password1", None)
        self.fields.pop("password2", None)

    def save(self, commit=True):
        from .models import Client

        client = Client(
            email=self.cleaned_data["email"],
            client_type=self.cleaned_data["client_type"],
            first_name=self.cleaned_data.get("first_name", ""),
            last_name=self.cleaned_data.get("last_name", ""),
            company_name=self.cleaned_data.get("company_name", ""),
            phone=self.cleaned_data.get("full_phone", self.cleaned_data.get("phone", "")),
            status=Client.Status.PENDING_ONBOARDING,
        )
        client.set_password("")
        photo = self.cleaned_data.get("profile_photo")
        if photo:
            client.profile_photo = optimize_profile_photo(photo)
        if commit:
            client.save()
            ClientSignUpForm._sync_client_signup_drive_uploads(client)
        return client


class ClientOnboardingForm(forms.Form):
    client_type = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={"class": "form-input", "id": "id_onboard_client_type"}),
    )
    first_name = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "id": "id_onboard_first_name",
                "autocomplete": "given-name",
            }
        ),
    )
    last_name = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "id": "id_onboard_last_name",
                "autocomplete": "family-name",
            }
        ),
    )
    company_name = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "id": "id_onboard_company_name",
                "autocomplete": "organization",
            }
        ),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-input",
                "id": "id_onboard_email",
                "autocomplete": "email",
            }
        ),
    )
    country_code = forms.ChoiceField(
        choices=country_choices(),
        widget=forms.HiddenInput(attrs={"id": "id_country_code"}),
    )
    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "class": "form-input phone-local-input",
                "placeholder": "712 345 678",
                "autocomplete": "tel-national",
                "inputmode": "tel",
                "id": "id_client_phone",
            }
        ),
    )
    physical_address = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-input",
                "rows": 3,
                "placeholder": "Street, city, county / country",
                "id": "id_physical_address",
            }
        ),
    )
    id_type = forms.ChoiceField(
        required=False,
        choices=[],
        widget=forms.RadioSelect(attrs={"class": "radio-group"}),
    )
    identification_document = forms.FileField(
        required=False,
        widget=forms.FileInput(
            attrs={
                "class": "form-input form-input--file",
                "accept": "image/*,.pdf",
                "id": "id_identification_document",
            }
        ),
    )
    alien_document = forms.FileField(
        required=False,
        widget=forms.FileInput(
            attrs={
                "class": "form-input form-input--file",
                "accept": "image/*,.pdf",
                "id": "id_alien_document",
            }
        ),
    )
    corporate_kind = forms.ChoiceField(
        required=False,
        choices=[],
        widget=forms.RadioSelect(attrs={"class": "radio-group"}),
    )
    business_document = forms.FileField(
        required=False,
        widget=forms.FileInput(
            attrs={
                "class": "form-input form-input--file",
                "accept": "image/*,.pdf",
                "id": "id_business_document",
            }
        ),
    )
    company_registration_document = forms.FileField(
        required=False,
        widget=forms.FileInput(
            attrs={
                "class": "form-input form-input--file",
                "accept": "image/*,.pdf",
                "id": "id_company_registration_document",
            }
        ),
    )
    kra_pin_document = forms.FileField(
        required=False,
        widget=forms.FileInput(
            attrs={
                "class": "form-input form-input--file",
                "accept": "image/*,.pdf",
                "id": "id_kra_pin_document",
            }
        ),
    )
    signed_instruction_note = forms.FileField(
        required=False,
        widget=forms.FileInput(
            attrs={
                "class": "form-input form-input--file",
                "accept": "image/*,.pdf",
                "id": "id_signed_instruction_note",
            }
        ),
    )

    def __init__(self, *args, client=None, **kwargs):
        from .models import Client

        self.client = client
        super().__init__(*args, **kwargs)
        self.fields["client_type"].choices = list(Client.ClientType.choices)
        self.fields["id_type"].choices = list(Client.IdType.choices)
        self.fields["corporate_kind"].choices = list(Client.CorporateKind.choices)
        self.countries_json = countries_for_js()

        if client and not self.is_bound:
            country_value, local = _split_phone(client.phone)
            self.fields["client_type"].initial = client.client_type or Client.ClientType.INDIVIDUAL
            self.fields["first_name"].initial = (client.first_name or "").upper()
            self.fields["last_name"].initial = (client.last_name or "").upper()
            self.fields["company_name"].initial = (client.company_name or "").upper()
            self.fields["email"].initial = client.email
            self.fields["country_code"].initial = country_value
            self.fields["phone"].initial = local
            self.fields["physical_address"].initial = (client.physical_address or "").upper()
            self.fields["id_type"].initial = client.id_type or Client.IdType.CITIZEN
            self.fields["corporate_kind"].initial = (
                client.corporate_kind or Client.CorporateKind.BUSINESS
            )

        for name, field in self.fields.items():
            if name in (
                "email",
                "country_code",
                "client_type",
                "id_type",
                "corporate_kind",
                "identification_document",
                "alien_document",
                "business_document",
                "company_registration_document",
                "kra_pin_document",
                "signed_instruction_note",
            ):
                continue
            widget = field.widget
            if isinstance(
                widget,
                (forms.TextInput, forms.PasswordInput, forms.Textarea),
            ):
                attrs = widget.attrs
                attrs["class"] = f"{attrs.get('class', '')} input-uppercase".strip()
                attrs["autocapitalize"] = "characters"

    def clean_first_name(self):
        return (self.cleaned_data.get("first_name") or "").strip().upper()

    def clean_last_name(self):
        return (self.cleaned_data.get("last_name") or "").strip().upper()

    def clean_company_name(self):
        return (self.cleaned_data.get("company_name") or "").strip().upper()

    def clean_email(self):
        from .models import Client

        email = self.cleaned_data["email"].lower().strip()
        qs = Client.objects.filter(email__iexact=email)
        if self.client:
            qs = qs.exclude(pk=self.client.pk)
        if qs.exists():
            raise ValidationError("Another account already uses this email.")
        return email

    def clean_phone(self):
        raw = (self.cleaned_data.get("phone") or "").strip().upper()
        digits = "".join(ch for ch in raw if ch.isdigit())
        if digits.startswith("0"):
            digits = digits[1:]
        if len(digits) < 6 or len(digits) > 15:
            raise ValidationError("Enter a valid phone number.")
        return digits

    def clean_physical_address(self):
        address = (self.cleaned_data.get("physical_address") or "").strip().upper()
        if len(address) < 5:
            raise ValidationError("Enter a physical address.")
        return address

    def clean(self):
        from .models import Client

        cleaned = super().clean()
        client_type = cleaned.get("client_type")
        country_value = cleaned.get("country_code")
        local_phone = cleaned.get("phone")

        if country_value and local_phone and "phone" not in self.errors:
            _iso, dial = parse_country_value(country_value)
            cleaned["full_phone"] = f"{dial}{local_phone}"

        if client_type == Client.ClientType.INDIVIDUAL:
            if not cleaned.get("first_name"):
                self.add_error("first_name", "Confirm your first name.")
            if not cleaned.get("last_name"):
                self.add_error("last_name", "Confirm your last name.")
            cleaned["company_name"] = ""
            cleaned["corporate_kind"] = ""
            id_type = cleaned.get("id_type") or Client.IdType.CITIZEN
            cleaned["id_type"] = id_type
        elif client_type == Client.ClientType.CORPORATE:
            if not cleaned.get("company_name"):
                self.add_error("company_name", "Confirm the business or company name.")
            cleaned["first_name"] = ""
            cleaned["last_name"] = ""
            cleaned["id_type"] = ""
            kind = cleaned.get("corporate_kind")
            if not kind:
                self.add_error(
                    "corporate_kind",
                    "Select whether this is a business or a company.",
                )

        return cleaned

    def save(self, commit=True):
        from .models import Client

        client = self.client
        client.client_type = self.cleaned_data["client_type"]
        client.first_name = self.cleaned_data.get("first_name", "")
        client.last_name = self.cleaned_data.get("last_name", "")
        client.company_name = self.cleaned_data.get("company_name", "")
        client.email = self.cleaned_data["email"]
        client.phone = self.cleaned_data.get(
            "full_phone", self.cleaned_data.get("phone", "")
        )
        client.physical_address = self.cleaned_data["physical_address"]
        client.id_type = self.cleaned_data.get("id_type", "")
        client.corporate_kind = self.cleaned_data.get("corporate_kind", "")

        # Optional document uploads — only overwrite when a new file is provided.
        if self.cleaned_data.get("identification_document"):
            client.identification_document = self.cleaned_data[
                "identification_document"
            ]
        if self.cleaned_data.get("alien_document"):
            client.alien_document = self.cleaned_data["alien_document"]
        if self.cleaned_data.get("business_document"):
            client.business_document = self.cleaned_data["business_document"]
        if self.cleaned_data.get("company_registration_document"):
            client.company_registration_document = self.cleaned_data[
                "company_registration_document"
            ]
        if self.cleaned_data.get("kra_pin_document"):
            client.kra_pin_document = self.cleaned_data["kra_pin_document"]
        if self.cleaned_data.get("signed_instruction_note"):
            client.signed_instruction_note = self.cleaned_data[
                "signed_instruction_note"
            ]

        if client.client_type == Client.ClientType.CORPORATE:
            client.identification_number = ""
            client.alien_number = ""
            client.identification_document = None
            client.alien_document = None
            if client.corporate_kind == Client.CorporateKind.BUSINESS:
                client.company_registration_number = ""
                client.company_registration_document = None
            else:
                client.business_number = ""
                client.business_document = None
        else:
            client.corporate_kind = ""
            client.business_number = ""
            client.business_document = None
            client.company_registration_number = ""
            client.company_registration_document = None
            client.identification_number = ""
            client.alien_number = ""
            if client.id_type == Client.IdType.CITIZEN:
                client.alien_document = None
            else:
                client.identification_document = None

        client.status = Client.Status.PENDING_APPROVAL
        uploaded_fields = [
            name
            for name in (
                "identification_document",
                "alien_document",
                "business_document",
                "company_registration_document",
                "kra_pin_document",
                "signed_instruction_note",
            )
            if self.cleaned_data.get(name)
        ]
        if commit:
            client.save()
            self._sync_client_onboarding_drive_uploads(client, uploaded_fields)
        return client

    @staticmethod
    def _sync_client_onboarding_drive_uploads(client, field_names):
        """Ensure client Drive folders and upload new personal documents."""
        try:
            from .google_drive import (
                GoogleDriveAPIError,
                GoogleDriveOAuthError,
                ensure_client_folder_structure,
                sync_client_personal_document_uploads,
            )
        except Exception:
            return
        try:
            ensure_client_folder_structure(client)
            if field_names:
                sync_client_personal_document_uploads(
                    client, field_names=field_names
                )
        except (GoogleDriveAPIError, GoogleDriveOAuthError):
            pass


class StaffClientProfileForm(ClientOnboardingForm):
    """Staff edit of an active/suspended client without changing approval status."""

    profile_photo = forms.ImageField(
        required=False,
        widget=forms.FileInput(
            attrs={
                "class": "form-input form-input--file",
                "accept": "image/*",
                "id": "id_client_profile_photo",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep optional docs optional on staff edit; do not force re-upload.
        for name in (
            "identification_document",
            "alien_document",
            "business_document",
            "company_registration_document",
            "kra_pin_document",
            "signed_instruction_note",
            "profile_photo",
        ):
            if name in self.fields:
                self.fields[name].required = False

    def save(self, commit=True):
        from .models import Client

        previous_status = self.client.status
        client = super().save(commit=False)
        # Preserve active/suspended (or any current) status — do not push to pending.
        client.status = previous_status

        photo = self.cleaned_data.get("profile_photo")
        if photo:
            client.profile_photo = optimize_profile_photo(photo)

        uploaded_fields = [
            name
            for name in (
                "identification_document",
                "alien_document",
                "business_document",
                "company_registration_document",
                "kra_pin_document",
                "signed_instruction_note",
                "profile_photo",
            )
            if self.cleaned_data.get(name)
        ]
        if commit:
            client.save()
            if uploaded_fields:
                ClientOnboardingForm._sync_client_onboarding_drive_uploads(
                    client, uploaded_fields
                )
        return client


class EmployeeOnboardingForm(forms.Form):
    payment_method = forms.ChoiceField(
        choices=[],
        widget=forms.RadioSelect(attrs={"class": "radio-group"}),
    )
    mobile_money_company = forms.CharField(
        required=False,
        max_length=80,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "e.g. M-Pesa, Airtel Money",
                "id": "id_mobile_money_company",
                "autocomplete": "organization",
            }
        ),
    )
    mobile_money_number = forms.CharField(
        required=False,
        max_length=32,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Number to receive payments",
                "id": "id_mobile_money_number",
                "autocomplete": "tel",
                "inputmode": "tel",
            }
        ),
    )
    bank_name = forms.CharField(
        required=False,
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Bank name",
                "id": "id_bank_name",
                "autocomplete": "organization",
            }
        ),
    )
    bank_account_number = forms.CharField(
        required=False,
        max_length=64,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Account number",
                "id": "id_bank_account_number",
                "autocomplete": "off",
                "inputmode": "numeric",
            }
        ),
    )
    employment_contract = forms.FileField(
        required=False,
        widget=forms.FileInput(
            attrs={
                "class": "form-input form-input--file",
                "accept": "image/*,.pdf",
                "id": "id_employment_contract",
            }
        ),
    )
    national_id_or_passport = forms.FileField(
        required=False,
        widget=forms.FileInput(
            attrs={
                "class": "form-input form-input--file",
                "accept": "image/*,.pdf",
                "id": "id_national_id_or_passport",
            }
        ),
    )
    kra_pin_certificate = forms.FileField(
        required=False,
        widget=forms.FileInput(
            attrs={
                "class": "form-input form-input--file",
                "accept": "image/*,.pdf",
                "id": "id_kra_pin_certificate",
            }
        ),
    )

    def __init__(self, *args, employee=None, **kwargs):
        from .models import Employee

        self.employee = employee
        super().__init__(*args, **kwargs)
        self.fields["payment_method"].choices = list(Employee.PaymentMethod.choices)

        if employee and not self.is_bound:
            self.fields["payment_method"].initial = (
                employee.payment_method or Employee.PaymentMethod.MOBILE
            )
            self.fields["mobile_money_company"].initial = (
                employee.mobile_money_company or ""
            ).upper()
            self.fields["mobile_money_number"].initial = employee.mobile_money_number or ""
            self.fields["bank_name"].initial = (employee.bank_name or "").upper()
            self.fields["bank_account_number"].initial = (
                employee.bank_account_number or ""
            )

        for name, field in self.fields.items():
            if name in (
                "payment_method",
                "employment_contract",
                "national_id_or_passport",
                "kra_pin_certificate",
                "mobile_money_number",
                "bank_account_number",
            ):
                continue
            widget = field.widget
            if isinstance(widget, (forms.TextInput, forms.Textarea)):
                attrs = widget.attrs
                attrs["class"] = f"{attrs.get('class', '')} input-uppercase".strip()
                attrs["autocapitalize"] = "characters"

    def clean_mobile_money_company(self):
        return (self.cleaned_data.get("mobile_money_company") or "").strip().upper()

    def clean_mobile_money_number(self):
        raw = (self.cleaned_data.get("mobile_money_number") or "").strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        if digits.startswith("0"):
            digits = digits[1:]
        return digits

    def clean_bank_name(self):
        return (self.cleaned_data.get("bank_name") or "").strip().upper()

    def clean_bank_account_number(self):
        return (self.cleaned_data.get("bank_account_number") or "").strip()

    def clean(self):
        from .models import Employee

        cleaned = super().clean()
        method = cleaned.get("payment_method")

        if method == Employee.PaymentMethod.MOBILE:
            cleaned["bank_name"] = ""
            cleaned["bank_account_number"] = ""
            if not cleaned.get("mobile_money_company"):
                self.add_error(
                    "mobile_money_company",
                    "Enter the mobile money company.",
                )
            number = cleaned.get("mobile_money_number") or ""
            if len(number) < 6 or len(number) > 15:
                self.add_error(
                    "mobile_money_number",
                    "Enter a valid mobile number to receive payments.",
                )
        elif method == Employee.PaymentMethod.BANK:
            cleaned["mobile_money_company"] = ""
            cleaned["mobile_money_number"] = ""
            if not cleaned.get("bank_name"):
                self.add_error("bank_name", "Enter the bank name.")
            if not cleaned.get("bank_account_number"):
                self.add_error("bank_account_number", "Enter the account number.")
        elif method == Employee.PaymentMethod.CASH:
            cleaned["mobile_money_company"] = ""
            cleaned["mobile_money_number"] = ""
            cleaned["bank_name"] = ""
            cleaned["bank_account_number"] = ""

        for field_name, label in (
            ("employment_contract", "employment contract"),
            ("national_id_or_passport", "national ID or passport"),
            ("kra_pin_certificate", "KRA PIN certificate"),
        ):
            uploaded = cleaned.get(field_name)
            existing = getattr(self.employee, field_name, None) if self.employee else None
            if not uploaded and not existing:
                self.add_error(field_name, f"Upload your {label}.")

        return cleaned

    def save(self, commit=True):
        from .models import Employee

        employee = self.employee
        employee.payment_method = self.cleaned_data["payment_method"]
        employee.mobile_money_company = self.cleaned_data.get(
            "mobile_money_company", ""
        )
        employee.mobile_money_number = self.cleaned_data.get("mobile_money_number", "")
        employee.bank_name = self.cleaned_data.get("bank_name", "")
        employee.bank_account_number = self.cleaned_data.get("bank_account_number", "")

        if self.cleaned_data.get("employment_contract"):
            employee.employment_contract = self.cleaned_data["employment_contract"]
        if self.cleaned_data.get("national_id_or_passport"):
            employee.national_id_or_passport = self.cleaned_data[
                "national_id_or_passport"
            ]
        if self.cleaned_data.get("kra_pin_certificate"):
            employee.kra_pin_certificate = self.cleaned_data["kra_pin_certificate"]

        if employee.payment_method == Employee.PaymentMethod.MOBILE:
            employee.bank_name = ""
            employee.bank_account_number = ""
        elif employee.payment_method == Employee.PaymentMethod.BANK:
            employee.mobile_money_company = ""
            employee.mobile_money_number = ""
        else:
            employee.mobile_money_company = ""
            employee.mobile_money_number = ""
            employee.bank_name = ""
            employee.bank_account_number = ""

        employee.status = Employee.Status.PENDING_APPROVAL
        uploaded_fields = [
            name
            for name in (
                "employment_contract",
                "national_id_or_passport",
                "kra_pin_certificate",
            )
            if self.cleaned_data.get(name)
        ]
        if commit:
            employee.save()
            self._sync_onboarding_drive_uploads(employee, uploaded_fields)
        return employee

    @staticmethod
    def _sync_onboarding_drive_uploads(employee, field_names):
        """Ensure employee Drive folders and upload new onboarding documents."""
        try:
            from .google_drive import (
                GoogleDriveAPIError,
                GoogleDriveOAuthError,
                ensure_employee_folder_structure,
                sync_employee_personal_detail_uploads,
            )
        except Exception:
            return
        try:
            ensure_employee_folder_structure(employee)
            if field_names:
                sync_employee_personal_detail_uploads(
                    employee, field_names=field_names
                )
        except (GoogleDriveAPIError, GoogleDriveOAuthError):
            pass


class RegisterCaseForm(forms.ModelForm):
    """Register a new litigation case for an active client."""

    client = forms.ModelChoiceField(
        queryset=Client.objects.filter(status=Client.Status.ACTIVE),
        widget=forms.HiddenInput(attrs={"id": "id_client"}),
        error_messages={"required": "Select a client by name or phone number."},
    )

    class Meta:
        model = LitigationCase
        fields = (
            "filing_date",
            "client",
            "court_rank",
            "case_category",
            "case_type",
            "court_case_number",
            "station",
            "description",
        )
        widgets = {
            "filing_date": forms.DateInput(
                attrs={
                    "class": "form-input",
                    "type": "date",
                    "id": "id_filing_date",
                    "autocomplete": "off",
                }
            ),
            "court_rank": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "id": "id_court_rank",
                    "placeholder": "Select or type a court rank",
                    "autocomplete": "off",
                }
            ),
            "case_category": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "id": "id_case_category",
                    "placeholder": "Select or type a case category",
                    "autocomplete": "off",
                }
            ),
            "case_type": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "id": "id_case_type",
                    "placeholder": "Select or type a case type",
                    "autocomplete": "off",
                }
            ),
            "court_case_number": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "id": "id_court_case_number",
                    "placeholder": "e.g. HCCC E001 of 2026",
                    "autocomplete": "off",
                }
            ),
            "station": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "id": "id_station",
                    "placeholder": "Select or type a station",
                    "autocomplete": "off",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "id": "id_description",
                    "rows": 4,
                    "placeholder": "Brief description of the matter",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["filing_date"].required = True
        self.fields["court_rank"].required = True
        self.fields["case_category"].required = True
        self.fields["case_type"].required = True
        self.fields["station"].required = True
        self.fields["court_case_number"].required = False
        self.fields["description"].required = False
        self.fields["client"].queryset = Client.objects.filter(
            status=Client.Status.ACTIVE
        )
        # Expose presets for the live suggest UI
        self.preset_options = {
            "court_rank": [label for _, label in LitigationCase.CourtRank.choices],
            "case_category": [
                label for _, label in LitigationCase.CaseCategory.choices
            ],
            "case_type": [label for _, label in LitigationCase.CaseType.choices],
            "station": [label for _, label in LitigationCase.Station.choices],
        }

    def _normalize_lookup(self, value: str, choices) -> str:
        raw = (value or "").strip()
        if not raw:
            return raw
        for key, label in choices:
            if raw == key or raw.lower() == label.lower():
                return label
        return raw

    def clean_court_rank(self):
        return self._normalize_lookup(
            self.cleaned_data.get("court_rank", ""),
            LitigationCase.CourtRank.choices,
        )

    def clean_case_category(self):
        return self._normalize_lookup(
            self.cleaned_data.get("case_category", ""),
            LitigationCase.CaseCategory.choices,
        )

    def clean_case_type(self):
        return self._normalize_lookup(
            self.cleaned_data.get("case_type", ""),
            LitigationCase.CaseType.choices,
        )

    def clean_station(self):
        return self._normalize_lookup(
            self.cleaned_data.get("station", ""),
            LitigationCase.Station.choices,
        )

    def clean_client(self):
        client = self.cleaned_data.get("client")
        if client and client.status != Client.Status.ACTIVE:
            raise ValidationError("Only active clients can be linked to a case.")
        return client

class CasePartyForm(forms.ModelForm):
    """One party row on the register-case form."""

    class Meta:
        model = CaseParty
        fields = (
            "party_name",
            "party_type",
            "category",
            "firm_agent",
            "phone",
            "email",
            "is_client_party",
        )
        widgets = {
            "party_name": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Party name",
                    "autocomplete": "off",
                }
            ),
            "party_type": forms.Select(attrs={"class": "form-input"}),
            "category": forms.Select(attrs={"class": "form-input"}),
            "firm_agent": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Firm or agent",
                    "autocomplete": "off",
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Phone",
                    "autocomplete": "off",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Email",
                    "autocomplete": "off",
                }
            ),
            "is_client_party": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["party_name"].required = True
        self.fields["party_type"].required = True
        self.fields["category"].required = False
        self.fields["firm_agent"].required = False
        self.fields["phone"].required = False
        self.fields["email"].required = False
        self.fields["party_type"].choices = [
            ("", "Select party type"),
            *CaseParty.PartyType.choices,
        ]
        self.fields["category"].choices = [
            ("", "Select category"),
            *CaseParty.Category.choices,
        ]


CasePartyFormSet = forms.formset_factory(
    CasePartyForm,
    extra=0,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class UpdateCourtAttendanceForm(forms.ModelForm):
    """Record a court attendance against a litigation case."""

    class Meta:
        model = CourtAttendance
        fields = (
            "activity_type",
            "judicial_officer",
            "court_room",
            "attendance_date",
            "presence",
            "court_directions",
            "next_action",
            "next_activity_type",
            "next_court_date",
            "next_judicial_officer",
            "next_client_attendance",
            "virtual_link",
        )
        widgets = {
            "activity_type": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. Mention, Hearing",
                    "autocomplete": "off",
                    "list": "activity-type-suggestions",
                }
            ),
            "judicial_officer": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Enter judicial officer name...",
                    "autocomplete": "off",
                }
            ),
            "court_room": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. Court 3",
                    "autocomplete": "off",
                }
            ),
            "attendance_date": forms.DateInput(
                attrs={
                    "class": "form-input",
                    "type": "date",
                    "autocomplete": "off",
                }
            ),
            "presence": forms.Select(attrs={"class": "form-input"}),
            "court_directions": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 3,
                    "placeholder": "Enter court directions...",
                }
            ),
            "next_action": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 3,
                    "placeholder": "Enter next action...",
                }
            ),
            "next_activity_type": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. Mention, Hearing",
                    "autocomplete": "off",
                    "list": "activity-type-suggestions",
                }
            ),
            "next_court_date": forms.DateInput(
                attrs={
                    "class": "form-input",
                    "type": "date",
                    "autocomplete": "off",
                }
            ),
            "next_judicial_officer": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Enter judicial officer name...",
                    "autocomplete": "off",
                }
            ),
            "next_client_attendance": forms.Select(
                attrs={
                    "class": "form-input",
                    "data-virtual-toggle": "true",
                }
            ),
            "virtual_link": forms.URLInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "https://meet.example.com/hearing-link",
                    "autocomplete": "off",
                    "data-virtual-link": "true",
                }
            ),
        }
        labels = {
            "activity_type": "Activity Type",
            "judicial_officer": "Judicial Officer",
            "court_room": "Court Room",
            "attendance_date": "Date of Court Attendance",
            "presence": "Court Attendance",
            "court_directions": "Court Directions",
            "next_action": "Next Action",
            "next_activity_type": "Next Activity Type",
            "next_court_date": "Next Court Date",
            "next_judicial_officer": "Next Judicial Officer",
            "next_client_attendance": "Next Client Attendance",
            "virtual_link": "Virtual hearing link",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["activity_type"].required = True
        self.fields["judicial_officer"].required = True
        self.fields["attendance_date"].required = True
        self.fields["presence"].required = True
        self.fields["court_room"].required = False
        self.fields["court_directions"].required = False
        self.fields["next_action"].required = False
        self.fields["next_activity_type"].required = False
        self.fields["next_court_date"].required = False
        self.fields["next_judicial_officer"].required = False
        self.fields["next_client_attendance"].required = False
        self.fields["virtual_link"].required = False
        self.fields["next_client_attendance"].choices = [
            ("", "Select attendance..."),
            *CourtAttendance.ClientAttendance.choices,
        ]
        if not self.is_bound and not self.initial.get("attendance_date"):
            self.initial["attendance_date"] = timezone.localdate()
            self.initial.setdefault("presence", CourtAttendance.Presence.PRESENT)

    def clean(self):
        cleaned = super().clean()
        attendance = cleaned.get("next_client_attendance") or ""
        link = (cleaned.get("virtual_link") or "").strip()
        if attendance == CourtAttendance.ClientAttendance.VIRTUAL:
            if not link:
                self.add_error(
                    "virtual_link",
                    "Enter the virtual hearing link when attendance is Virtual.",
                )
        else:
            cleaned["virtual_link"] = ""
        return cleaned


class CourtAttendanceAdvocateForm(forms.ModelForm):
    """One advocate present at a court attendance."""

    class Meta:
        model = CourtAttendanceAdvocate
        fields = ("advocate_name", "what_they_said")
        widgets = {
            "advocate_name": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "NAME OF ADVOCATE",
                    "autocomplete": "off",
                }
            ),
            "what_they_said": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 3,
                    "placeholder": "SUMMARY OF SUBMISSIONS OR REMARKS",
                }
            ),
        }
        labels = {
            "advocate_name": "Advocate name",
            "what_they_said": "What they said",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["advocate_name"].required = False
        self.fields["what_they_said"].required = False

    def clean(self):
        cleaned = super().clean()
        name = (cleaned.get("advocate_name") or "").strip()
        remarks = (cleaned.get("what_they_said") or "").strip()
        if remarks and not name:
            self.add_error("advocate_name", "Enter the advocate name.")
        cleaned["advocate_name"] = name
        cleaned["what_they_said"] = remarks
        return cleaned


CourtAttendanceAdvocateFormSet = forms.formset_factory(
    CourtAttendanceAdvocateForm,
    extra=1,
    min_num=0,
    validate_min=False,
    can_delete=True,
)


class CourtAttendanceBringUpItemForm(forms.ModelForm):
    """One bring-up item from a court attendance."""

    class Meta:
        model = CourtAttendanceBringUpItem
        fields = ("description", "reminder_frequency", "allocated_to")
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 3,
                    "placeholder": "Enter item description...",
                }
            ),
            "reminder_frequency": forms.Select(attrs={"class": "form-input"}),
            "allocated_to": forms.Select(attrs={"class": "form-input"}),
        }
        labels = {
            "description": "Description",
            "reminder_frequency": "Frequency to be Reminded",
            "allocated_to": "Allocated To",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].required = False
        self.fields["reminder_frequency"].required = False
        self.fields["allocated_to"].required = False
        self.fields["reminder_frequency"].choices = [
            ("", "Select frequency..."),
            *CourtAttendanceBringUpItem.ReminderFrequency.choices,
        ]
        self.fields["allocated_to"].queryset = Employee.objects.filter(
            status=Employee.Status.ACTIVE
        ).order_by("first_name", "last_name", "login_code")
        self.fields["allocated_to"].empty_label = "Select employee..."
        self.fields["allocated_to"].label_from_instance = (
            lambda employee: (
                f"{employee.get_full_name() or employee.login_code} "
                f"({employee.get_role_display()})"
            )
        )

    def clean(self):
        cleaned = super().clean()
        description = (cleaned.get("description") or "").strip()
        frequency = cleaned.get("reminder_frequency") or ""
        allocated = cleaned.get("allocated_to")
        if (frequency or allocated) and not description:
            self.add_error("description", "Enter an item description.")
        cleaned["description"] = description
        return cleaned


CourtAttendanceBringUpItemFormSet = forms.formset_factory(
    CourtAttendanceBringUpItemForm,
    extra=1,
    min_num=0,
    validate_min=False,
    can_delete=True,
)


class UpdateMatterAttendanceForm(forms.ModelForm):
    """Record a matter attendance against a non-litigation matter."""

    class Meta:
        model = MatterAttendance
        fields = (
            "activity_type",
            "contact_person",
            "location",
            "attendance_date",
            "presence",
            "outcome_notes",
            "description",
            "next_action",
            "next_activity_type",
            "next_attendance_date",
            "next_contact_person",
            "next_client_attendance",
            "virtual_link",
        )
        widgets = {
            "activity_type": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. Client meeting, Filing, Follow-up",
                    "autocomplete": "off",
                    "list": "matter-activity-type-suggestions",
                }
            ),
            "contact_person": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Enter contact / meeting person...",
                    "autocomplete": "off",
                }
            ),
            "location": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. Boardroom, Client offices",
                    "autocomplete": "off",
                }
            ),
            "attendance_date": forms.DateInput(
                attrs={
                    "class": "form-input",
                    "type": "date",
                    "autocomplete": "off",
                }
            ),
            "presence": forms.Select(attrs={"class": "form-input"}),
            "outcome_notes": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 3,
                    "placeholder": "Enter outcome notes / directions...",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 4,
                    "placeholder": "Enter attendance description...",
                }
            ),
            "next_action": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 3,
                    "placeholder": "Enter next action...",
                }
            ),
            "next_activity_type": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. Client meeting, Follow-up",
                    "autocomplete": "off",
                    "list": "matter-activity-type-suggestions",
                }
            ),
            "next_attendance_date": forms.DateInput(
                attrs={
                    "class": "form-input",
                    "type": "date",
                    "autocomplete": "off",
                }
            ),
            "next_contact_person": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Enter next contact person...",
                    "autocomplete": "off",
                }
            ),
            "next_client_attendance": forms.Select(
                attrs={
                    "class": "form-input",
                    "data-virtual-toggle": "true",
                }
            ),
            "virtual_link": forms.URLInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "https://meet.example.com/meeting-link",
                    "autocomplete": "off",
                    "data-virtual-link": "true",
                }
            ),
        }
        labels = {
            "activity_type": "Activity Type",
            "contact_person": "Contact Person",
            "location": "Location",
            "attendance_date": "Date of Attendance",
            "presence": "Matter Attendance",
            "outcome_notes": "Outcome / Notes",
            "description": "Description",
            "next_action": "Next Action",
            "next_activity_type": "Next Activity Type",
            "next_attendance_date": "Next Attendance Date",
            "next_contact_person": "Next Contact Person",
            "next_client_attendance": "Next Client Attendance",
            "virtual_link": "Virtual meeting link",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["activity_type"].required = True
        self.fields["attendance_date"].required = True
        self.fields["presence"].required = True
        self.fields["contact_person"].required = False
        self.fields["location"].required = False
        self.fields["outcome_notes"].required = False
        self.fields["description"].required = False
        self.fields["next_action"].required = False
        self.fields["next_activity_type"].required = False
        self.fields["next_attendance_date"].required = False
        self.fields["next_contact_person"].required = False
        self.fields["next_client_attendance"].required = False
        self.fields["virtual_link"].required = False
        self.fields["next_client_attendance"].choices = [
            ("", "Select attendance..."),
            *MatterAttendance.ClientAttendance.choices,
        ]
        if not self.is_bound and not self.initial.get("attendance_date"):
            self.initial["attendance_date"] = timezone.localdate()
            self.initial.setdefault("presence", MatterAttendance.Presence.PRESENT)

    def clean(self):
        cleaned = super().clean()
        attendance = cleaned.get("next_client_attendance") or ""
        link = (cleaned.get("virtual_link") or "").strip()
        if attendance == MatterAttendance.ClientAttendance.VIRTUAL:
            if not link:
                self.add_error(
                    "virtual_link",
                    "Enter the virtual meeting link when attendance is Virtual.",
                )
        else:
            cleaned["virtual_link"] = ""
        return cleaned


class MatterAttendanceQuorumMemberForm(forms.ModelForm):
    """One quorum participant at a matter attendance."""

    class Meta:
        model = MatterAttendanceQuorumMember
        fields = ("participant_name", "what_they_said")
        widgets = {
            "participant_name": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "NAME OF PARTICIPANT",
                    "autocomplete": "off",
                }
            ),
            "what_they_said": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 3,
                    "placeholder": "SUMMARY OF REMARKS OR CONTRIBUTIONS",
                }
            ),
        }
        labels = {
            "participant_name": "Participant name",
            "what_they_said": "What they said",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["participant_name"].required = False
        self.fields["what_they_said"].required = False

    def clean(self):
        cleaned = super().clean()
        name = (cleaned.get("participant_name") or "").strip()
        remarks = (cleaned.get("what_they_said") or "").strip()
        if remarks and not name:
            self.add_error("participant_name", "Enter the participant name.")
        cleaned["participant_name"] = name
        cleaned["what_they_said"] = remarks
        return cleaned


MatterAttendanceQuorumFormSet = forms.formset_factory(
    MatterAttendanceQuorumMemberForm,
    extra=1,
    min_num=0,
    validate_min=False,
    can_delete=True,
)


class MatterAttendanceBringUpItemForm(forms.ModelForm):
    """One bring-up item from a matter attendance."""

    class Meta:
        model = MatterAttendanceBringUpItem
        fields = ("description", "reminder_frequency", "allocated_to")
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 3,
                    "placeholder": "Enter item description...",
                }
            ),
            "reminder_frequency": forms.Select(attrs={"class": "form-input"}),
            "allocated_to": forms.Select(attrs={"class": "form-input"}),
        }
        labels = {
            "description": "Description",
            "reminder_frequency": "Frequency to be Reminded",
            "allocated_to": "Allocated To",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].required = False
        self.fields["reminder_frequency"].required = False
        self.fields["allocated_to"].required = False
        self.fields["reminder_frequency"].choices = [
            ("", "Select frequency..."),
            *MatterAttendanceBringUpItem.ReminderFrequency.choices,
        ]
        self.fields["allocated_to"].queryset = Employee.objects.filter(
            status=Employee.Status.ACTIVE
        ).order_by("first_name", "last_name", "login_code")
        self.fields["allocated_to"].empty_label = "Select employee..."
        self.fields["allocated_to"].label_from_instance = (
            lambda employee: (
                f"{employee.get_full_name() or employee.login_code} "
                f"({employee.get_role_display()})"
            )
        )

    def clean(self):
        cleaned = super().clean()
        description = (cleaned.get("description") or "").strip()
        frequency = cleaned.get("reminder_frequency") or ""
        allocated = cleaned.get("allocated_to")
        if (frequency or allocated) and not description:
            self.add_error("description", "Enter an item description.")
        cleaned["description"] = description
        return cleaned


MatterAttendanceBringUpItemFormSet = forms.formset_factory(
    MatterAttendanceBringUpItemForm,
    extra=1,
    min_num=0,
    validate_min=False,
    can_delete=True,
)


class CreateCaseTaskForm(forms.Form):
    """Create a follow-up case task for the locked litigation case."""

    TASK_ACCESS_FIELDS = (
        (
            "allow_view",
            "View",
            "See case details and open documents.",
        ),
        (
            "allow_edit",
            "Edit",
            "Edit case details and rename documents.",
        ),
        (
            "allow_download",
            "Download",
            "Download documents from this case.",
        ),
        (
            "allow_delete",
            "Delete",
            "Remove documents from this case.",
        ),
        (
            "allow_upload",
            "Upload",
            "Upload or create documents on this case.",
        ),
    )

    assigned_to = forms.ModelChoiceField(
        queryset=Employee.objects.none(),
        empty_label="Choose an employee...",
        widget=forms.Select(attrs={"class": "form-input"}),
        error_messages={"required": "Allocate the task to an employee."},
        label="Allocate task to employee",
    )
    title = forms.CharField(
        max_length=255,
        label="Task title",
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "e.g. Prepare submissions / diary next mention",
                "autocomplete": "off",
            }
        ),
        error_messages={"required": "Enter a task title."},
    )
    instructions = forms.CharField(
        required=False,
        label="Task description",
        widget=forms.Textarea(
            attrs={
                "class": "form-input",
                "rows": 4,
                "placeholder": "Write task details, dependencies, and expected output",
            }
        ),
    )
    due_date = forms.DateField(
        label="Timeline / due date",
        widget=forms.DateInput(
            attrs={
                "class": "form-input",
                "type": "date",
                "autocomplete": "off",
            }
        ),
        error_messages={"required": "Select a due date."},
    )
    allow_view = forms.BooleanField(
        label="View",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={"class": "task-access-toggle__input"}
        ),
        help_text="See case details and open documents.",
    )
    allow_edit = forms.BooleanField(
        label="Edit",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={"class": "task-access-toggle__input"}
        ),
        help_text="Edit case details and rename documents.",
    )
    allow_download = forms.BooleanField(
        label="Download",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={"class": "task-access-toggle__input"}
        ),
        help_text="Download documents from this case.",
    )
    allow_delete = forms.BooleanField(
        label="Delete",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={"class": "task-access-toggle__input"}
        ),
        help_text="Remove documents from this case.",
    )
    allow_upload = forms.BooleanField(
        label="Upload",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={"class": "task-access-toggle__input"}
        ),
        help_text="Upload or create documents on this case.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = Employee.objects.filter(
            status=Employee.Status.ACTIVE
        ).order_by("first_name", "last_name", "login_code")
        self.fields["assigned_to"].label_from_instance = (
            lambda employee: (
                f"{employee.get_full_name() or employee.login_code} "
                f"({employee.get_role_display()})"
            )
        )
        self.fields["assigned_to"].help_text = (
            "Select the employee who will receive and work on this case task."
        )

    def access_permission_rows(self):
        """Ordered rows for the compact assignee-access toggles."""
        rows = []
        for name, label, help_text in self.TASK_ACCESS_FIELDS:
            field = self[name]
            rows.append(
                {
                    "name": name,
                    "label": label,
                    "help_text": help_text,
                    "field": field,
                    "errors": field.errors,
                }
            )
        return rows

    def cleaned_access_permissions(self):
        """Boolean map of allow_* permissions from cleaned_data."""
        return {
            name: bool(self.cleaned_data.get(name, False))
            for name, _label, _help in self.TASK_ACCESS_FIELDS
        }


class CreateMatterTaskForm(forms.Form):
    """Create a follow-up matter task for the locked non-litigation matter."""

    TASK_ACCESS_FIELDS = (
        (
            "allow_view",
            "View",
            "See matter details and open documents.",
        ),
        (
            "allow_edit",
            "Edit",
            "Edit matter details and rename documents.",
        ),
        (
            "allow_download",
            "Download",
            "Download documents from this matter.",
        ),
        (
            "allow_delete",
            "Delete",
            "Remove documents from this matter.",
        ),
        (
            "allow_upload",
            "Upload",
            "Upload or create documents on this matter.",
        ),
    )

    assigned_to = forms.ModelChoiceField(
        queryset=Employee.objects.none(),
        empty_label="Choose an employee...",
        widget=forms.Select(attrs={"class": "form-input"}),
        error_messages={"required": "Allocate the task to an employee."},
        label="Allocate task to employee",
    )
    title = forms.CharField(
        max_length=255,
        label="Task title",
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "e.g. Prepare engagement letter follow-up",
                "autocomplete": "off",
            }
        ),
        error_messages={"required": "Enter a task title."},
    )
    instructions = forms.CharField(
        required=False,
        label="Task description",
        widget=forms.Textarea(
            attrs={
                "class": "form-input",
                "rows": 4,
                "placeholder": "Write task details, dependencies, and expected output",
            }
        ),
    )
    due_date = forms.DateField(
        label="Timeline / due date",
        widget=forms.DateInput(
            attrs={
                "class": "form-input",
                "type": "date",
                "autocomplete": "off",
            }
        ),
        error_messages={"required": "Select a due date."},
    )
    allow_view = forms.BooleanField(
        label="View",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={"class": "task-access-toggle__input"}
        ),
        help_text="See matter details and open documents.",
    )
    allow_edit = forms.BooleanField(
        label="Edit",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={"class": "task-access-toggle__input"}
        ),
        help_text="Edit matter details and rename documents.",
    )
    allow_download = forms.BooleanField(
        label="Download",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={"class": "task-access-toggle__input"}
        ),
        help_text="Download documents from this matter.",
    )
    allow_delete = forms.BooleanField(
        label="Delete",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={"class": "task-access-toggle__input"}
        ),
        help_text="Remove documents from this matter.",
    )
    allow_upload = forms.BooleanField(
        label="Upload",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={"class": "task-access-toggle__input"}
        ),
        help_text="Upload or create documents on this matter.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = Employee.objects.filter(
            status=Employee.Status.ACTIVE
        ).order_by("first_name", "last_name", "login_code")
        self.fields["assigned_to"].label_from_instance = (
            lambda employee: (
                f"{employee.get_full_name() or employee.login_code} "
                f"({employee.get_role_display()})"
            )
        )
        self.fields["assigned_to"].help_text = (
            "Select the employee who will receive and work on this matter task."
        )

    def access_permission_rows(self):
        """Ordered rows for the compact assignee-access toggles."""
        rows = []
        for name, label, help_text in self.TASK_ACCESS_FIELDS:
            field = self[name]
            rows.append(
                {
                    "name": name,
                    "label": label,
                    "help_text": help_text,
                    "field": field,
                    "errors": field.errors,
                }
            )
        return rows

    def cleaned_access_permissions(self):
        """Boolean map of allow_* permissions from cleaned_data."""
        return {
            name: bool(self.cleaned_data.get(name, False))
            for name, _label, _help in self.TASK_ACCESS_FIELDS
        }


class ApproveCaseForm(forms.Form):
    """Allocate an employee and create their case task on approval."""

    assigned_to = forms.ModelChoiceField(
        queryset=Employee.objects.none(),
        empty_label="Select employee",
        widget=forms.Select(
            attrs={"class": "form-input", "id": "id_assigned_to"}
        ),
        error_messages={"required": "Allocate the case to an employee."},
    )
    instructions = forms.CharField(
        required=False,
        label="Instructions / Brief",
        widget=forms.Textarea(
            attrs={
                "class": "form-input",
                "id": "id_instructions",
                "rows": 4,
                "placeholder": "Brief the assigned employee on next steps…",
            }
        ),
    )
    due_date = forms.DateField(
        label="Due date",
        widget=forms.DateInput(
            attrs={
                "class": "form-input",
                "type": "date",
                "id": "id_due_date",
                "autocomplete": "off",
            }
        ),
        error_messages={"required": "Select a due date."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = Employee.objects.filter(
            status=Employee.Status.ACTIVE
        ).order_by("first_name", "last_name", "login_code")

    def clean_assigned_to(self):
        employee = self.cleaned_data.get("assigned_to")
        if employee and employee.status != Employee.Status.ACTIVE:
            raise ValidationError("Only active employees can be allocated.")
        return employee


class RegisterMatterForm(forms.ModelForm):
    """Register a new non-litigation matter for an active client."""

    client = forms.ModelChoiceField(
        queryset=Client.objects.filter(status=Client.Status.ACTIVE),
        widget=forms.HiddenInput(attrs={"id": "id_client"}),
        error_messages={"required": "Select a client by name or phone number."},
    )

    class Meta:
        model = NonLitigationMatter
        fields = (
            "date_opened",
            "client",
            "matter_category",
            "matter_title",
            "client_instructions",
        )
        widgets = {
            "date_opened": forms.DateInput(
                attrs={
                    "class": "form-input",
                    "type": "date",
                    "id": "id_date_opened",
                    "autocomplete": "off",
                }
            ),
            "matter_category": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "id": "id_matter_category",
                    "placeholder": "Select or type a matter category",
                    "autocomplete": "off",
                }
            ),
            "matter_title": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "id": "id_matter_title",
                    "placeholder": "Matter title",
                    "autocomplete": "off",
                }
            ),
            "client_instructions": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "id": "id_client_instructions",
                    "rows": 4,
                    "placeholder": "Optional instructions from the client",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_opened"].required = True
        self.fields["matter_category"].required = True
        self.fields["matter_title"].required = True
        self.fields["client_instructions"].required = False
        self.fields["client"].queryset = Client.objects.filter(
            status=Client.Status.ACTIVE
        )

    def clean_matter_category(self):
        raw = (self.cleaned_data.get("matter_category") or "").strip()
        if not raw:
            return raw
        for key, label in NonLitigationMatter.MatterCategory.choices:
            if raw == key or raw.lower() == label.lower():
                return label
        return raw

    def clean_matter_title(self):
        return (self.cleaned_data.get("matter_title") or "").strip()

    def clean_client(self):
        client = self.cleaned_data.get("client")
        if client and client.status != Client.Status.ACTIVE:
            raise ValidationError("Only active clients can be linked to a matter.")
        return client


class MatterPartyForm(forms.ModelForm):
    class Meta:
        model = MatterParty
        fields = (
            "party_name",
            "party_type",
            "category",
            "firm_agent",
            "phone",
            "email",
            "is_client_party",
        )
        widgets = {
            "party_name": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Party name",
                    "autocomplete": "off",
                }
            ),
            "party_type": forms.Select(attrs={"class": "form-input"}),
            "category": forms.Select(attrs={"class": "form-input"}),
            "firm_agent": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Firm or agent",
                    "autocomplete": "off",
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Phone",
                    "autocomplete": "off",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Email",
                    "autocomplete": "off",
                }
            ),
            "is_client_party": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["party_name"].required = True
        self.fields["party_type"].required = True
        self.fields["category"].required = False
        self.fields["firm_agent"].required = False
        self.fields["phone"].required = False
        self.fields["email"].required = False
        self.fields["party_type"].choices = [
            ("", "Select party type"),
            *MatterParty.PartyType.choices,
        ]
        self.fields["category"].choices = [
            ("", "Select category"),
            *MatterParty.Category.choices,
        ]


MatterPartyFormSet = forms.formset_factory(
    MatterPartyForm,
    extra=0,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


CasePartyEditFormSet = forms.modelformset_factory(
    CaseParty,
    form=CasePartyForm,
    extra=0,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


MatterPartyEditFormSet = forms.modelformset_factory(
    MatterParty,
    form=MatterPartyForm,
    extra=0,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class ApproveMatterForm(ApproveCaseForm):
    """Same allocate + task fields as case approval."""

    pass


class AcceptTaskForm(forms.Form):
    """Assignee may optionally set a personal reminder when accepting."""

    reminder_at = forms.DateTimeField(
        required=False,
        label="Reminder",
        input_formats=[
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%dT%H:%M:%S",
        ],
        widget=forms.DateTimeInput(
            attrs={
                "class": "form-input",
                "type": "datetime-local",
                "id": "id_accept_reminder_at",
                "autocomplete": "off",
            }
        ),
    )

    def __init__(self, *args, due_date=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.due_date = due_date

    def clean_reminder_at(self):
        reminder_at = self.cleaned_data.get("reminder_at")
        if not reminder_at:
            return None
        if timezone.is_naive(reminder_at):
            reminder_at = timezone.make_aware(
                reminder_at, timezone.get_current_timezone()
            )
        if reminder_at <= timezone.now():
            raise ValidationError("Reminder must be in the future.")
        if self.due_date:
            reminder_date = timezone.localtime(reminder_at).date()
            if reminder_date > self.due_date:
                raise ValidationError("Reminder cannot be after the due date.")
        return reminder_at


class RejectTaskForm(forms.Form):
    """Assignee must provide a reason when rejecting a task."""

    reason = forms.CharField(
        label="Reason for rejection",
        min_length=5,
        widget=forms.Textarea(
            attrs={
                "class": "form-input",
                "id": "id_reject_reason",
                "rows": 4,
                "placeholder": "Explain why you cannot take this task…",
                "required": True,
            }
        ),
        error_messages={
            "required": "Provide a reason for rejecting this task.",
            "min_length": "Give a bit more detail (at least 5 characters).",
        },
    )

    def clean_reason(self):
        reason = (self.cleaned_data.get("reason") or "").strip()
        if len(reason) < 5:
            raise ValidationError(
                "Give a bit more detail (at least 5 characters)."
            )
        return reason


class ProfileSettingsForm(forms.ModelForm):
    """
    Edit the signed-in employee's full session profile.

    Prefills every editable field from the current user. Passwords are hashed
    and never displayed — change with current / new / confirm fields.
    """

    courtesy_title = forms.ChoiceField(
        choices=[("", "Title")] + list(Employee.CourtesyTitle.choices),
        widget=forms.Select(
            attrs={
                "class": "form-input form-input--title",
                "autocomplete": "honorific-prefix",
                "id": "id_settings_courtesy_title",
            }
        ),
    )
    id_country = forms.ChoiceField(
        choices=nationality_choices(),
        initial=DEFAULT_COUNTRY,
        widget=forms.Select(
            attrs={
                "class": "form-input",
                "id": "id_settings_id_country",
            }
        ),
    )
    login_code_display = forms.CharField(
        required=False,
        label="Login code",
        disabled=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "id": "id_settings_login_code",
                "readonly": True,
            }
        ),
    )
    role_display = forms.CharField(
        required=False,
        label="Role",
        disabled=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "id": "id_settings_role",
                "readonly": True,
            }
        ),
    )
    status_display = forms.CharField(
        required=False,
        label="Status",
        disabled=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "id": "id_settings_status",
                "readonly": True,
            }
        ),
    )
    current_password = forms.CharField(
        required=False,
        label="Current password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-input",
                "placeholder": "Enter current password to change it",
                "autocomplete": "current-password",
                "id": "id_settings_current_password",
            },
            render_value=False,
        ),
    )
    new_password = forms.CharField(
        required=False,
        label="New password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-input",
                "placeholder": "New password",
                "autocomplete": "new-password",
                "id": "id_settings_new_password",
            },
            render_value=False,
        ),
    )
    confirm_password = forms.CharField(
        required=False,
        label="Confirm new password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-input",
                "placeholder": "Re-enter new password",
                "autocomplete": "new-password",
                "id": "id_settings_confirm_password",
            },
            render_value=False,
        ),
    )

    class Meta:
        model = Employee
        fields = [
            "courtesy_title",
            "first_name",
            "last_name",
            "personal_email",
            "personal_phone",
            "work_email",
            "work_phone",
            "id_type",
            "id_country",
            "identification_number",
            "alien_number",
            "profile_photo",
            "about_me",
            "payment_method",
            "mobile_money_company",
            "mobile_money_number",
            "bank_name",
            "bank_account_number",
        ]
        widgets = {
            "first_name": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "First name",
                    "autocomplete": "given-name",
                    "id": "id_settings_first_name",
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Last name",
                    "autocomplete": "family-name",
                    "id": "id_settings_last_name",
                }
            ),
            "personal_email": forms.EmailInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Personal email",
                    "autocomplete": "email",
                    "id": "id_settings_personal_email",
                }
            ),
            "personal_phone": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Personal phone",
                    "autocomplete": "tel",
                    "inputmode": "tel",
                    "id": "id_settings_personal_phone",
                }
            ),
            "work_email": forms.EmailInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Work email (optional)",
                    "autocomplete": "email",
                    "id": "id_settings_work_email",
                }
            ),
            "work_phone": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Work phone (optional)",
                    "autocomplete": "tel",
                    "inputmode": "tel",
                    "id": "id_settings_work_phone",
                }
            ),
            "id_type": forms.RadioSelect(attrs={"class": "radio-group"}),
            "identification_number": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "National ID number",
                    "id": "id_settings_identification_number",
                }
            ),
            "alien_number": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Alien / permit number",
                    "id": "id_settings_alien_number",
                }
            ),
            "profile_photo": forms.FileInput(
                attrs={
                    "class": "form-input form-input--file",
                    "accept": "image/*",
                    "id": "id_settings_profile_photo",
                }
            ),
            "about_me": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 5,
                    "placeholder": "A short note about you…",
                    "id": "id_settings_about_me",
                    "maxlength": "2000",
                }
            ),
            "payment_method": forms.RadioSelect(attrs={"class": "radio-group"}),
            "mobile_money_company": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. M-Pesa",
                    "id": "id_settings_mobile_money_company",
                }
            ),
            "mobile_money_number": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Mobile money number",
                    "inputmode": "tel",
                    "id": "id_settings_mobile_money_number",
                }
            ),
            "bank_name": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Bank name",
                    "id": "id_settings_bank_name",
                }
            ),
            "bank_account_number": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Account number",
                    "id": "id_settings_bank_account_number",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        optional = [
            "identification_number",
            "alien_number",
            "profile_photo",
            "courtesy_title",
            "work_email",
            "work_phone",
            "about_me",
            "payment_method",
            "mobile_money_company",
            "mobile_money_number",
            "bank_name",
            "bank_account_number",
        ]
        for name in optional:
            self.fields[name].required = False

        self.fields["payment_method"].choices = list(Employee.PaymentMethod.choices)
        self.has_password = bool(
            self.instance and self.instance.pk and self.instance.has_usable_password()
        )

        # Always load the signed-in user's current values into the form.
        if self.instance and self.instance.pk and not self.is_bound:
            self.initial.update(
                {
                    "courtesy_title": self.instance.courtesy_title or "",
                    "first_name": self.instance.first_name or "",
                    "last_name": self.instance.last_name or "",
                    "personal_email": self.instance.personal_email or "",
                    "personal_phone": self.instance.personal_phone or "",
                    "work_email": self.instance.work_email or "",
                    "work_phone": self.instance.work_phone or "",
                    "id_type": self.instance.id_type or "",
                    "id_country": self.instance.id_country or DEFAULT_COUNTRY,
                    "identification_number": self.instance.identification_number
                    or "",
                    "alien_number": self.instance.alien_number or "",
                    "about_me": self.instance.about_me or "",
                    "payment_method": self.instance.payment_method or "",
                    "mobile_money_company": self.instance.mobile_money_company or "",
                    "mobile_money_number": self.instance.mobile_money_number or "",
                    "bank_name": self.instance.bank_name or "",
                    "bank_account_number": self.instance.bank_account_number or "",
                    "login_code_display": self.instance.login_code or "",
                    "role_display": self.instance.get_role_display(),
                    "status_display": self.instance.get_status_display(),
                }
            )

    def clean_personal_email(self):
        email = (self.cleaned_data.get("personal_email") or "").strip().lower()
        qs = Employee.objects.filter(personal_email__iexact=email)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("This email is already in use.")
        return email

    def clean_work_email(self):
        email = (self.cleaned_data.get("work_email") or "").strip().lower()
        return email or None

    def clean_work_phone(self):
        phone = (self.cleaned_data.get("work_phone") or "").strip()
        return phone or None

    def clean_about_me(self):
        text = (self.cleaned_data.get("about_me") or "").strip()
        if len(text) > 2000:
            raise ValidationError("Keep your about me under 2,000 characters.")
        return text

    def clean_mobile_money_company(self):
        return (self.cleaned_data.get("mobile_money_company") or "").strip()

    def clean_mobile_money_number(self):
        return (self.cleaned_data.get("mobile_money_number") or "").strip()

    def clean_bank_name(self):
        return (self.cleaned_data.get("bank_name") or "").strip()

    def clean_bank_account_number(self):
        return (self.cleaned_data.get("bank_account_number") or "").strip()

    def clean_current_password(self):
        return (self.cleaned_data.get("current_password") or "").upper()

    def clean_new_password(self):
        password = (self.cleaned_data.get("new_password") or "").upper()
        if not password:
            return ""
        if len(password) < 6:
            raise ValidationError("Password must be at least 6 characters.")
        validate_password(password, user=self.instance)
        return password

    def clean_confirm_password(self):
        return (self.cleaned_data.get("confirm_password") or "").upper()

    def clean(self):
        cleaned = super().clean()
        id_type = cleaned.get("id_type")
        if id_type == Employee.IdType.CITIZEN:
            if not (cleaned.get("identification_number") or "").strip():
                self.add_error(
                    "identification_number",
                    "National ID number is required for citizens.",
                )
        elif id_type == Employee.IdType.NON_CITIZEN:
            if not (cleaned.get("alien_number") or "").strip():
                self.add_error(
                    "alien_number",
                    "Alien / permit number is required for non-citizens.",
                )

        method = cleaned.get("payment_method") or ""
        if method == Employee.PaymentMethod.MOBILE:
            cleaned["bank_name"] = ""
            cleaned["bank_account_number"] = ""
        elif method == Employee.PaymentMethod.BANK:
            cleaned["mobile_money_company"] = ""
            cleaned["mobile_money_number"] = ""
        elif method == Employee.PaymentMethod.CASH:
            cleaned["mobile_money_company"] = ""
            cleaned["mobile_money_number"] = ""
            cleaned["bank_name"] = ""
            cleaned["bank_account_number"] = ""

        current = cleaned.get("current_password") or ""
        new = cleaned.get("new_password") or ""
        confirm = cleaned.get("confirm_password") or ""
        changing = bool(current or new or confirm)
        if changing:
            if not new:
                self.add_error("new_password", "Enter a new password.")
            if not confirm:
                self.add_error("confirm_password", "Confirm the new password.")
            if not current:
                self.add_error(
                    "current_password",
                    "Enter your current password to change it.",
                )
            elif self.instance and self.instance.pk:
                if not self.instance.check_password(current):
                    self.add_error(
                        "current_password",
                        "Current password is incorrect.",
                    )
            if new and confirm and new != confirm:
                self.add_error("confirm_password", "Passwords do not match.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        photo = self.cleaned_data.get("profile_photo")
        if photo:
            user.profile_photo = optimize_profile_photo(photo)
        new_password = self.cleaned_data.get("new_password") or ""
        if new_password:
            user.set_password(new_password)
        if commit:
            user.save()
            if photo:
                SignUpForm._sync_signup_drive_uploads(user)
        return user

    def save_with_request(self, request, commit=True):
        """Save profile and keep the current session valid after a password change."""
        from django.contrib.auth import update_session_auth_hash

        user = self.save(commit=commit)
        if commit and (self.cleaned_data.get("new_password") or ""):
            update_session_auth_hash(request, user)
        return user


class AppearanceSettingsForm(forms.ModelForm):
    """
    Personal theme, font, and density for the signed-in employee.

    `default` follows the firm Company Theme; other values override it.
    """

    class Meta:
        model = Employee
        fields = ["ui_theme", "ui_font", "ui_density"]
        widgets = {
            "ui_theme": forms.RadioSelect(attrs={"class": "theme-choice-group"}),
            "ui_font": forms.RadioSelect(attrs={"class": "font-choice-group"}),
            "ui_density": forms.RadioSelect(attrs={"class": "density-choice-group"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ui_theme"].choices = list(Employee.UiTheme.choices)
        self.fields["ui_font"].choices = list(Employee.UiFont.choices)
        self.fields["ui_density"].choices = list(Employee.UiDensity.choices)

    def clean_ui_theme(self):
        return self.cleaned_data.get("ui_theme") or Employee.UiTheme.DEFAULT

    def save(self, commit=True):
        """Persist appearance only on this employee instance."""
        employee = super().save(commit=False)
        if commit:
            employee.save(update_fields=["ui_theme", "ui_font", "ui_density"])
        return employee


class CompanyThemeForm(forms.ModelForm):
    """Firm-wide default workspace theme (System settings)."""

    class Meta:
        model = CompanyThemeSetting
        fields = ["default_ui_theme"]
        labels = {
            "default_ui_theme": "Company theme",
        }
        widgets = {
            "default_ui_theme": forms.RadioSelect(
                attrs={"class": "theme-choice-group"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hide legacy product alias — default means Black & White in company mode.
        self.fields["default_ui_theme"].choices = [
            (key, label)
            for key, label in Employee.UiTheme.choices
            if key != Employee.UiTheme.PRODUCT
        ]
        self.fields["default_ui_theme"].required = True
        if (
            self.instance
            and (self.instance.default_ui_theme or "") == Employee.UiTheme.PRODUCT
        ):
            self.initial["default_ui_theme"] = Employee.UiTheme.DEFAULT

    def clean_default_ui_theme(self):
        value = self.cleaned_data.get("default_ui_theme") or Employee.UiTheme.DEFAULT
        if value == Employee.UiTheme.PRODUCT:
            return Employee.UiTheme.DEFAULT
        return value


class CompanyLetterheadForm(forms.ModelForm):
    """Firm letterhead layout and accents (Document settings)."""

    class Meta:
        model = CompanyLetterheadSetting
        fields = [
            "template",
            "footer_template",
            "accent",
            "show_logo",
            "show_tagline",
            "show_address",
            "show_contacts",
        ]
        labels = {
            "template": "Letterhead sample",
            "footer_template": "Footer sample",
            "accent": "Accent colour",
            "show_logo": "Show logo / mark",
            "show_tagline": "Show tagline",
            "show_address": "Show address in footer",
            "show_contacts": "Show contacts",
        }
        widgets = {
            "template": forms.RadioSelect(
                attrs={"class": "letterhead-choice-group"}
            ),
            "footer_template": forms.RadioSelect(
                attrs={"class": "letterfoot-choice-group"}
            ),
            "accent": forms.RadioSelect(
                attrs={"class": "letterhead-accent-group"}
            ),
            "show_logo": forms.CheckboxInput(attrs={"class": "form-check"}),
            "show_tagline": forms.CheckboxInput(attrs={"class": "form-check"}),
            "show_address": forms.CheckboxInput(attrs={"class": "form-check"}),
            "show_contacts": forms.CheckboxInput(attrs={"class": "form-check"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["template"].choices = list(
            CompanyLetterheadSetting.Template.choices
        )
        self.fields["footer_template"].choices = list(
            CompanyLetterheadSetting.FooterTemplate.choices
        )
        self.fields["accent"].choices = list(
            CompanyLetterheadSetting.Accent.choices
        )
        self.fields["template"].required = True
        self.fields["footer_template"].required = True
        self.fields["accent"].required = True


class CompanyDigitalStampForm(forms.ModelForm):
    """Firm digital stamp layout (Document settings)."""

    class Meta:
        model = CompanyDigitalStampSetting
        fields = [
            "template",
            "accent",
            "show_firm_name",
            "show_status",
            "show_approver",
            "show_date",
        ]
        labels = {
            "template": "Stamp sample",
            "accent": "Accent colour",
            "show_firm_name": "Show firm name",
            "show_status": "Show status",
            "show_approver": "Show company name line",
            "show_date": "Show date",
        }
        widgets = {
            "template": forms.RadioSelect(
                attrs={"class": "stamp-choice-group"}
            ),
            "accent": forms.RadioSelect(
                attrs={"class": "stamp-accent-group"}
            ),
            "show_firm_name": forms.CheckboxInput(attrs={"class": "form-check"}),
            "show_status": forms.CheckboxInput(attrs={"class": "form-check"}),
            "show_approver": forms.CheckboxInput(attrs={"class": "form-check"}),
            "show_date": forms.CheckboxInput(attrs={"class": "form-check"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["template"].choices = list(
            CompanyDigitalStampSetting.Template.choices
        )
        self.fields["accent"].choices = list(
            CompanyDigitalStampSetting.Accent.choices
        )
        self.fields["template"].required = True
        self.fields["accent"].required = True


class EmployeeDigitalStampForm(forms.ModelForm):
    """Personal digital stamp layout (My tools)."""

    class Meta:
        model = EmployeeDigitalStampSetting
        fields = [
            "template",
            "accent",
            "show_firm_name",
            "show_status",
            "show_approver",
            "show_date",
        ]
        labels = {
            "template": "Stamp sample",
            "accent": "Accent colour",
            "show_firm_name": "Show firm name",
            "show_status": "Show status",
            "show_approver": "Show my name",
            "show_date": "Show date",
        }
        widgets = {
            "template": forms.RadioSelect(
                attrs={"class": "stamp-choice-group"}
            ),
            "accent": forms.RadioSelect(
                attrs={"class": "stamp-accent-group"}
            ),
            "show_firm_name": forms.CheckboxInput(attrs={"class": "form-check"}),
            "show_status": forms.CheckboxInput(attrs={"class": "form-check"}),
            "show_approver": forms.CheckboxInput(attrs={"class": "form-check"}),
            "show_date": forms.CheckboxInput(attrs={"class": "form-check"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["template"].choices = list(
            EmployeeDigitalStampSetting.Template.choices
        )
        self.fields["accent"].choices = list(
            EmployeeDigitalStampSetting.Accent.choices
        )
        self.fields["template"].required = True
        self.fields["accent"].required = True


class CompanyDigitalSignatureForm(forms.ModelForm):
    """Firm digital signature layout (Document settings)."""

    class Meta:
        model = CompanyDigitalSignatureSetting
        fields = [
            "template",
            "accent",
            "default_title",
            "show_firm_name",
            "show_name",
            "show_title",
            "show_date",
        ]
        labels = {
            "template": "Signature sample",
            "accent": "Accent colour",
            "default_title": "Default title / capacity",
            "show_firm_name": "Show firm name",
            "show_name": "Show signatory name",
            "show_title": "Show title / capacity",
            "show_date": "Show date",
        }
        widgets = {
            "template": forms.RadioSelect(
                attrs={"class": "signature-choice-group"}
            ),
            "accent": forms.RadioSelect(
                attrs={"class": "signature-accent-group"}
            ),
            "default_title": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Authorized Signatory",
                    "maxlength": "120",
                }
            ),
            "show_firm_name": forms.CheckboxInput(attrs={"class": "form-check"}),
            "show_name": forms.CheckboxInput(attrs={"class": "form-check"}),
            "show_title": forms.CheckboxInput(attrs={"class": "form-check"}),
            "show_date": forms.CheckboxInput(attrs={"class": "form-check"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["template"].choices = list(
            CompanyDigitalSignatureSetting.Template.choices
        )
        self.fields["accent"].choices = list(
            CompanyDigitalSignatureSetting.Accent.choices
        )
        self.fields["template"].required = True
        self.fields["accent"].required = True
        self.fields["default_title"].required = False

    def clean_default_title(self):
        return (self.cleaned_data.get("default_title") or "").strip()


class NotificationSettingsForm(forms.ModelForm):
    """In-app notification preferences (sound, etc.)."""

    class Meta:
        model = Employee
        fields = ["notification_sound"]
        labels = {
            "notification_sound": "Play sound for new notifications",
        }
        widgets = {
            "notification_sound": forms.CheckboxInput(
                attrs={
                    "class": "form-checkbox",
                    "id": "id_notification_sound",
                }
            ),
        }


class AboutMeForm(forms.ModelForm):
    """Personal bio for the signed-in employee."""

    class Meta:
        model = Employee
        fields = ["about_me"]
        labels = {
            "about_me": "About me",
        }
        widgets = {
            "about_me": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 8,
                    "placeholder": "Share a short note about your practice, focus areas, or how colleagues can work with you…",
                    "id": "id_about_me",
                    "maxlength": "2000",
                }
            ),
        }

    def clean_about_me(self):
        text = (self.cleaned_data.get("about_me") or "").strip()
        if len(text) > 2000:
            raise ValidationError("Keep your about me under 2,000 characters.")
        return text

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save(update_fields=["about_me"])
        return user


class EmployeeBlogForm(forms.ModelForm):
    """Create or edit an SEO-ready blog post for the public website."""

    clear_cover = forms.BooleanField(
        required=False,
        label="Remove current cover image",
        widget=forms.CheckboxInput(attrs={"class": "form-checkbox"}),
    )

    class Meta:
        model = EmployeeBlogPost
        fields = [
            "title",
            "slug",
            "excerpt",
            "body",
            "cover_image",
            "meta_title",
            "meta_description",
            "focus_keyword",
            "tags",
            "status",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Clear, specific title (include your focus keyword)",
                    "id": "id_blog_title",
                    "maxlength": "200",
                    "data-seo-field": "title",
                }
            ),
            "slug": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "url-friendly-slug",
                    "id": "id_blog_slug",
                    "maxlength": "220",
                    "data-seo-field": "slug",
                }
            ),
            "excerpt": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 3,
                    "placeholder": "One or two sentences summarising the post for the blog list…",
                    "id": "id_blog_excerpt",
                    "maxlength": "320",
                    "data-seo-field": "excerpt",
                }
            ),
            "body": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 16,
                    "placeholder": "Write a helpful post. Aim for 300+ words. Use short paragraphs and clear headings.",
                    "id": "id_blog_body",
                    "data-seo-field": "body",
                }
            ),
            "cover_image": forms.FileInput(
                attrs={
                    "class": "form-input",
                    "id": "id_blog_cover",
                    "accept": "image/*",
                    "data-seo-field": "cover",
                }
            ),
            "meta_title": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "SEO title for Google (50–60 characters)",
                    "id": "id_blog_meta_title",
                    "maxlength": "70",
                    "data-seo-field": "meta_title",
                }
            ),
            "meta_description": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 3,
                    "placeholder": "Compelling meta description (120–160 characters)",
                    "id": "id_blog_meta_description",
                    "maxlength": "160",
                    "data-seo-field": "meta_description",
                }
            ),
            "focus_keyword": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. employment contract Kenya",
                    "id": "id_blog_focus_keyword",
                    "maxlength": "80",
                    "data-seo-field": "focus_keyword",
                }
            ),
            "tags": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "employment law, contracts, Kenya",
                    "id": "id_blog_tags",
                    "maxlength": "240",
                    "data-seo-field": "tags",
                }
            ),
            "status": forms.RadioSelect(attrs={"class": "radio-group"}),
        }
        labels = {
            "title": "Post title",
            "slug": "URL slug",
            "excerpt": "Excerpt",
            "body": "Body",
            "cover_image": "Cover image",
            "meta_title": "SEO title",
            "meta_description": "Meta description",
            "focus_keyword": "Focus keyword",
            "tags": "Topic tags",
            "status": "Status",
        }
        help_texts = {
            "slug": "Appears as /blog/your-slug/. Leave blank to auto-generate from the title.",
            "excerpt": "Shown on the public blog list and used if meta description is empty.",
            "meta_title": "Overrides the browser/Google title. Leave blank to use the post title.",
            "meta_description": "The snippet Google may show under your title in search results.",
            "focus_keyword": "The main phrase you want this post to rank for.",
            "tags": "Comma-separated topics for the website.",
            "cover_image": "Recommended: landscape image, at least 1200×630px.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Authors draft or submit; publishing happens only after firm approval.
        choices = [
            (EmployeeBlogPost.Status.DRAFT, "Draft"),
            (EmployeeBlogPost.Status.SUBMITTED, "Submit for approval"),
        ]
        if (
            self.instance.pk
            and self.instance.status == EmployeeBlogPost.Status.PUBLISHED
        ):
            choices.append(
                (EmployeeBlogPost.Status.PUBLISHED, "Published (live on website)")
            )
        self.fields["status"].choices = choices
        self.fields["status"].label = "Save as"
        self.fields["slug"].required = False
        self.fields["excerpt"].required = False
        self.fields["meta_title"].required = False
        self.fields["meta_description"].required = False
        self.fields["focus_keyword"].required = False
        self.fields["tags"].required = False
        self.fields["cover_image"].required = False
        if not self.instance.pk or not self.instance.cover_image:
            self.fields["clear_cover"].widget = forms.HiddenInput()

    def clean_title(self):
        title = (self.cleaned_data.get("title") or "").strip()
        if not title:
            raise ValidationError("Enter a title for your post.")
        if len(title) > 200:
            raise ValidationError("Keep the title under 200 characters.")
        return title

    def clean_slug(self):
        from django.utils.text import slugify

        slug = (self.cleaned_data.get("slug") or "").strip()
        if not slug:
            return ""
        slug = slugify(slug)[:220]
        if not slug:
            raise ValidationError("Enter a valid URL slug using letters, numbers, and hyphens.")
        qs = EmployeeBlogPost.objects.filter(slug=slug)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Another post already uses this URL slug.")
        return slug

    def clean_excerpt(self):
        return (self.cleaned_data.get("excerpt") or "").strip()

    def clean_meta_title(self):
        return (self.cleaned_data.get("meta_title") or "").strip()

    def clean_meta_description(self):
        return (self.cleaned_data.get("meta_description") or "").strip()

    def clean_focus_keyword(self):
        return (self.cleaned_data.get("focus_keyword") or "").strip()

    def clean_tags(self):
        raw = (self.cleaned_data.get("tags") or "").strip()
        if not raw:
            return ""
        tags = [t.strip() for t in raw.split(",") if t.strip()]
        return ", ".join(tags)

    def clean_body(self):
        body = (self.cleaned_data.get("body") or "").strip()
        if not body:
            raise ValidationError("Write something in the body of your post.")
        if len(body) > 50000:
            raise ValidationError("Keep the post under 50,000 characters.")
        return body

    def clean_status(self):
        status = self.cleaned_data.get("status") or EmployeeBlogPost.Status.DRAFT
        if status == EmployeeBlogPost.Status.PUBLISHED:
            if (
                self.instance.pk
                and self.instance.status == EmployeeBlogPost.Status.PUBLISHED
            ):
                return status
            raise ValidationError(
                "Posts must be submitted for approval before they can go live."
            )
        return status

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status") or EmployeeBlogPost.Status.DRAFT
        if status == EmployeeBlogPost.Status.SUBMITTED:
            if not (cleaned.get("excerpt") or "").strip():
                self.add_error(
                    "excerpt",
                    "Add a short excerpt before submitting so the website list looks complete.",
                )
            if not (cleaned.get("focus_keyword") or "").strip():
                self.add_error(
                    "focus_keyword",
                    "Set a focus keyword before submitting so the post can target a search phrase.",
                )
            if not (cleaned.get("meta_description") or "").strip():
                self.add_error(
                    "meta_description",
                    "Add a meta description before submitting for better Google snippets.",
                )
        return cleaned

    def save(self, commit=True, *, author=None):
        new_cover = self.cleaned_data.get("cover_image")
        clear_cover = bool(self.cleaned_data.get("clear_cover"))
        # Empty file inputs come through as False and would wipe an existing image.
        if not new_cover:
            self.cleaned_data["cover_image"] = (
                self.instance.cover_image if self.instance.pk else None
            )

        post = super().save(commit=False)
        if author is not None and not post.author_id:
            post.author = author
        status = self.cleaned_data.get("status") or EmployeeBlogPost.Status.DRAFT
        if status == EmployeeBlogPost.Status.SUBMITTED:
            if not post.submitted_at:
                post.submitted_at = timezone.now()
            # Submitting (or re-submitting) takes the post offline until approved.
            post.published_at = None
            post.approved_by = None
            post.approved_at = None
        elif status == EmployeeBlogPost.Status.DRAFT:
            post.submitted_at = None
            post.published_at = None
            post.approved_by = None
            post.approved_at = None
        # PUBLISHED left unchanged when author keeps an already-live post.
        if new_cover:
            post.cover_image = optimize_image(new_cover, max_size=1600, quality=78)
        elif clear_cover and post.cover_image:
            post.cover_image.delete(save=False)
            post.cover_image = None
        if commit:
            post.save()
        return post


class MultipleFileInput(forms.FileInput):
    """File input that accepts multiple files (Django 5+)."""

    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Validate zero or more uploads from a multiple file input."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if data in self.empty_values:
            return []
        if not isinstance(data, list):
            data = [data]
        cleaned = []
        for uploaded in data:
            if uploaded in self.empty_values:
                continue
            cleaned.append(super().clean(uploaded, None))
        return cleaned


class CompanyInformationForm(forms.ModelForm):
    """Firm-wide company profile under System Settings."""

    logo = forms.ImageField(
        required=False,
        widget=forms.FileInput(
            attrs={
                "class": "form-input form-input--file",
                "accept": "image/*",
                "id": "id_company_logo",
            }
        ),
        label="Firm logo",
        help_text="Square or landscape mark used on letterhead and invoices.",
    )
    remove_logo_background = forms.BooleanField(
        required=False,
        initial=False,
        label="Remove solid background",
        help_text="Best for logos on white or other uniform backgrounds.",
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check",
                "id": "id_remove_logo_background",
            }
        ),
    )
    clear_logo = forms.BooleanField(
        required=False,
        initial=False,
        label="Clear current logo",
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check",
                "id": "id_clear_logo",
            }
        ),
    )
    images = MultipleFileField(
        required=False,
        widget=MultipleFileInput(
            attrs={
                "class": "form-input form-input--file",
                "accept": "image/*",
                "id": "id_company_profile_images",
            }
        ),
        label="Company images",
        help_text="Gallery images for the firm profile and website.",
    )

    class Meta:
        model = FirmCompanyInformation
        fields = [
            "legal_name",
            "trading_name",
            "registration_number",
            "tax_pin",
            "tagline",
        ]
        labels = {
            "legal_name": "Legal name",
            "trading_name": "Trading / brand name",
            "registration_number": "Registration number",
            "tax_pin": "Tax PIN",
            "tagline": "Tagline",
        }
        widgets = {
            "legal_name": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. Sheria Law Firm LLP",
                    "autocomplete": "organization",
                    "id": "id_company_legal_name",
                }
            ),
            "trading_name": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Optional public name",
                    "autocomplete": "organization",
                    "id": "id_company_trading_name",
                }
            ),
            "registration_number": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Business / company registration number",
                    "id": "id_company_registration_number",
                }
            ),
            "tax_pin": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. P051234567A",
                    "id": "id_company_tax_pin",
                }
            ),
            "tagline": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Short line under the firm name",
                    "id": "id_company_tagline",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["legal_name"].required = True
        for name in ("trading_name", "registration_number", "tax_pin", "tagline"):
            self.fields[name].required = False

    def clean_legal_name(self):
        name = (self.cleaned_data.get("legal_name") or "").strip()
        if not name:
            raise ValidationError("Legal name is required.")
        return name

    def apply_logo(self, company):
        """Apply clear/upload/cutout for the firm logo onto a saved company row."""
        uploaded = self.cleaned_data.get("logo")
        if uploaded:
            optimized = optimize_logo(
                uploaded,
                remove_background=bool(self.cleaned_data.get("remove_logo_background")),
            )
            if company.logo:
                company.logo.delete(save=False)
            company.logo = optimized
            company.save(update_fields=["logo", "updated_at"])
            return company

        if self.cleaned_data.get("clear_logo") and company.logo:
            company.logo.delete(save=False)
            company.logo = None
            company.save(update_fields=["logo", "updated_at"])
        return company


class CompanyContactsForm(forms.ModelForm):
    """Firm contact and address details for the website."""

    class Meta:
        model = FirmCompanyInformation
        fields = [
            "email",
            "phone",
            "website",
            "linkedin_url",
            "facebook_url",
            "instagram_url",
            "x_url",
            "youtube_url",
            "physical_address",
            "postal_address",
            "city",
            "country",
        ]
        labels = {
            "email": "Primary email",
            "phone": "Primary phone",
            "website": "Website",
            "linkedin_url": "LinkedIn",
            "facebook_url": "Facebook",
            "instagram_url": "Instagram",
            "x_url": "X (Twitter)",
            "youtube_url": "YouTube",
            "physical_address": "Physical address",
            "postal_address": "Postal address",
            "city": "City",
            "country": "Country",
        }
        widgets = {
            "email": forms.EmailInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "info@example.com",
                    "autocomplete": "email",
                    "id": "id_company_email",
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "+254 700 000 000",
                    "autocomplete": "tel",
                    "inputmode": "tel",
                    "id": "id_company_phone",
                }
            ),
            "website": forms.URLInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "https://",
                    "autocomplete": "url",
                    "id": "id_company_website",
                }
            ),
            "linkedin_url": forms.URLInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "https://linkedin.com/company/…",
                    "autocomplete": "url",
                    "id": "id_company_linkedin_url",
                }
            ),
            "facebook_url": forms.URLInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "https://facebook.com/…",
                    "autocomplete": "url",
                    "id": "id_company_facebook_url",
                }
            ),
            "instagram_url": forms.URLInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "https://instagram.com/…",
                    "autocomplete": "url",
                    "id": "id_company_instagram_url",
                }
            ),
            "x_url": forms.URLInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "https://x.com/…",
                    "autocomplete": "url",
                    "id": "id_company_x_url",
                }
            ),
            "youtube_url": forms.URLInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "https://youtube.com/@…",
                    "autocomplete": "url",
                    "id": "id_company_youtube_url",
                }
            ),
            "physical_address": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 3,
                    "placeholder": "Building, street, area",
                    "id": "id_company_physical_address",
                }
            ),
            "postal_address": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "P.O. Box …",
                    "id": "id_company_postal_address",
                }
            ),
            "city": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "City",
                    "autocomplete": "address-level2",
                    "id": "id_company_city",
                }
            ),
            "country": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Country",
                    "autocomplete": "country-name",
                    "id": "id_company_country",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.fields:
            self.fields[name].required = False

    def clean_website(self):
        return (self.cleaned_data.get("website") or "").strip()

    def clean_linkedin_url(self):
        return (self.cleaned_data.get("linkedin_url") or "").strip()

    def clean_facebook_url(self):
        return (self.cleaned_data.get("facebook_url") or "").strip()

    def clean_instagram_url(self):
        return (self.cleaned_data.get("instagram_url") or "").strip()

    def clean_x_url(self):
        return (self.cleaned_data.get("x_url") or "").strip()

    def clean_youtube_url(self):
        return (self.cleaned_data.get("youtube_url") or "").strip()


FIRM_CORE_VALUE_CHOICES = (
    ("Integrity", "Integrity"),
    ("Client-Centered Service", "Client-Centered Service"),
    ("Accessibility", "Accessibility"),
    ("Excellence", "Excellence"),
    ("Confidentiality", "Confidentiality"),
    ("Innovation", "Innovation"),
    ("Diligence", "Diligence"),
)


class AboutCompanyForm(forms.ModelForm):
    """Guided about-company story used on the firm website."""

    selected_values = forms.MultipleChoiceField(
        choices=FIRM_CORE_VALUE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(
            attrs={"class": "about-value-checks"}
        ),
        label="Core values",
    )
    custom_value_1 = forms.CharField(
        required=False,
        max_length=80,
        label="Custom value 1",
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Add your own value (optional)",
                "id": "id_custom_value_1",
            }
        ),
    )
    custom_value_2 = forms.CharField(
        required=False,
        max_length=80,
        label="Custom value 2",
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Another custom value (optional)",
                "id": "id_custom_value_2",
            }
        ),
    )

    class Meta:
        model = FirmCompanyInformation
        fields = [
            "visitor_feeling",
            "founded_year",
            "founded_by",
            "market_gap",
            "milestone",
            "service_areas",
            "value_proposition",
            "future_vision",
        ]
        labels = {
            "visitor_feeling": (
                "In one sentence, what do you want a visitor to know or feel "
                "the moment they land on your site?"
            ),
            "founded_year": "When was your firm founded?",
            "founded_by": "By whom?",
            "market_gap": (
                "What gap or need in the market inspired you to start the firm?"
            ),
            "milestone": (
                "What's one milestone worth mentioning "
                "(new office, growth, notable achievement)?"
            ),
            "service_areas": (
                "Which towns/cities does your firm currently serve?"
            ),
            "value_proposition": (
                "In one sentence: What do you do, for whom, and what outcome "
                "do you deliver?"
            ),
            "future_vision": (
                "Where do you want your firm to be in 5–10 years?"
            ),
        }
        widgets = {
            "visitor_feeling": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. Clear counsel you can trust from day one",
                    "id": "id_visitor_feeling",
                }
            ),
            "founded_year": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. 2012",
                    "id": "id_founded_year",
                }
            ),
            "founded_by": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. Jane Wanjiku & Partners",
                    "id": "id_founded_by",
                }
            ),
            "market_gap": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 3,
                    "placeholder": "Describe the need you set out to meet…",
                    "id": "id_market_gap",
                }
            ),
            "milestone": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 3,
                    "placeholder": "e.g. Opened our second office in Mombasa in 2021",
                    "id": "id_milestone",
                }
            ),
            "service_areas": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 2,
                    "placeholder": "e.g. Nairobi, Kisumu, Nakuru",
                    "id": "id_service_areas",
                }
            ),
            "value_proposition": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": (
                        "e.g. We help SMEs resolve commercial disputes quickly "
                        "and cost-effectively"
                    ),
                    "id": "id_value_proposition",
                }
            ),
            "future_vision": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 3,
                    "placeholder": "Describe your 5–10 year ambition…",
                    "id": "id_future_vision",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.Meta.fields:
            self.fields[name].required = False

        existing = []
        if self.instance and self.instance.pk:
            existing = list(self.instance.core_values or [])
        existing_map = {
            (entry.get("name") or "").strip(): (entry.get("how") or "").strip()
            for entry in existing
            if isinstance(entry, dict) and (entry.get("name") or "").strip()
        }
        preset_names = {label for label, _ in FIRM_CORE_VALUE_CHOICES}
        selected = [name for name in existing_map if name in preset_names]
        self.fields["selected_values"].initial = selected

        customs = [name for name in existing_map if name not in preset_names]
        if customs:
            self.fields["custom_value_1"].initial = customs[0]
        if len(customs) > 1:
            self.fields["custom_value_2"].initial = customs[1]

        self.value_how_fields = []
        for label, _ in FIRM_CORE_VALUE_CHOICES:
            field_name = f"how_{label.lower().replace(' ', '_').replace('-', '_')}"
            self.fields[field_name] = forms.CharField(
                required=False,
                max_length=400,
                label=f"How “{label}” shows up in your work",
                widget=forms.TextInput(
                    attrs={
                        "class": "form-input",
                        "placeholder": "One sentence…",
                        "data-value-how": label,
                    }
                ),
            )
            if label in existing_map:
                self.fields[field_name].initial = existing_map[label]
            self.value_how_fields.append((label, field_name))

        self.fields["how_custom_1"] = forms.CharField(
            required=False,
            max_length=400,
            label="How custom value 1 shows up",
            widget=forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "One sentence…",
                    "id": "id_how_custom_1",
                }
            ),
        )
        self.fields["how_custom_2"] = forms.CharField(
            required=False,
            max_length=400,
            label="How custom value 2 shows up",
            widget=forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "One sentence…",
                    "id": "id_how_custom_2",
                }
            ),
        )
        if customs:
            self.fields["how_custom_1"].initial = existing_map.get(customs[0], "")
        if len(customs) > 1:
            self.fields["how_custom_2"].initial = existing_map.get(customs[1], "")

    def clean(self):
        cleaned = super().clean()
        selected = list(cleaned.get("selected_values") or [])
        custom_1 = (cleaned.get("custom_value_1") or "").strip()
        custom_2 = (cleaned.get("custom_value_2") or "").strip()
        entries = []

        for label, field_name in self.value_how_fields:
            if label not in selected:
                continue
            how = (cleaned.get(field_name) or "").strip()
            entries.append({"name": label, "how": how})

        for name, how_key in (
            (custom_1, "how_custom_1"),
            (custom_2, "how_custom_2"),
        ):
            if not name:
                continue
            if any(e["name"].lower() == name.lower() for e in entries):
                continue
            how = (cleaned.get(how_key) or "").strip()
            entries.append({"name": name, "how": how})

        if len(entries) > 5:
            self.add_error(
                "selected_values",
                "Pick up to 5 core values (including any custom values).",
            )
        cleaned["core_values"] = entries
        return cleaned

    def save(self, commit=True):
        company = super().save(commit=False)
        company.core_values = self.cleaned_data.get("core_values") or []
        if commit:
            company.save()
        return company


class PracticeAreaForm(forms.ModelForm):
    """Create or edit a firm practice area."""

    images = MultipleFileField(
        required=False,
        widget=MultipleFileInput(
            attrs={
                "class": "form-input form-input--file",
                "accept": "image/*",
                "id": "id_practice_area_images",
            }
        ),
        label="Images",
        help_text="Upload one or more images. The first image is the main image.",
    )

    class Meta:
        model = FirmPracticeArea
        fields = ["name", "summary", "details", "rank"]
        labels = {
            "name": "Practice area",
            "summary": "What you do in this area",
            "details": "Detailed information about the area",
            "rank": "Rank",
        }
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. Litigation, Conveyancing, Family law",
                    "id": "id_practice_area_name",
                }
            ),
            "summary": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 3,
                    "placeholder": "Short description of the work you do here…",
                    "id": "id_practice_area_summary",
                }
            ),
            "details": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 6,
                    "placeholder": "Longer detail for visitors who want to know more…",
                    "id": "id_practice_area_details",
                }
            ),
            "rank": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "min": 1,
                    "step": 1,
                    "id": "id_practice_area_rank",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = True
        self.fields["summary"].required = True
        self.fields["details"].required = False
        self.fields["rank"].required = True
        self.fields["rank"].initial = self.fields["rank"].initial or 1

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise ValidationError("Practice area name is required.")
        return name

    def clean_summary(self):
        summary = (self.cleaned_data.get("summary") or "").strip()
        if not summary:
            raise ValidationError("Describe what you do in this area.")
        return summary

    def clean_rank(self):
        rank = self.cleaned_data.get("rank")
        if rank is None or rank < 1:
            raise ValidationError("Rank must be 1 or higher.")
        return rank


class FAQForm(forms.ModelForm):
    """Create or edit a firm FAQ entry."""

    class Meta:
        model = FirmFAQ
        fields = ["question", "answer", "rank"]
        labels = {
            "question": "Question",
            "answer": "Answer",
            "rank": "Rank",
        }
        widgets = {
            "question": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. How do I book a consultation?",
                    "id": "id_faq_question",
                }
            ),
            "answer": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 5,
                    "placeholder": "Clear answer visitors will see on the website…",
                    "id": "id_faq_answer",
                }
            ),
            "rank": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "min": 1,
                    "step": 1,
                    "id": "id_faq_rank",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["question"].required = True
        self.fields["answer"].required = True
        self.fields["rank"].required = True
        self.fields["rank"].initial = self.fields["rank"].initial or 1

    def clean_question(self):
        question = (self.cleaned_data.get("question") or "").strip()
        if not question:
            raise ValidationError("Question is required.")
        return question

    def clean_answer(self):
        answer = (self.cleaned_data.get("answer") or "").strip()
        if not answer:
            raise ValidationError("Answer is required.")
        return answer

    def clean_rank(self):
        rank = self.cleaned_data.get("rank")
        if rank is None or rank < 1:
            raise ValidationError("Rank must be 1 or higher.")
        return rank


class CompanyTermsForm(forms.ModelForm):
    """Firm terms and conditions for the public website."""

    class Meta:
        model = FirmCompanyInformation
        fields = ["terms_and_conditions"]
        labels = {
            "terms_and_conditions": "Terms and conditions",
        }
        widgets = {
            "terms_and_conditions": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 18,
                    "placeholder": "Write the firm’s public terms and conditions…",
                    "id": "id_company_terms",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["terms_and_conditions"].required = False

    def clean_terms_and_conditions(self):
        return (self.cleaned_data.get("terms_and_conditions") or "").strip()


class GalleryImageForm(forms.ModelForm):
    """Create or edit a firm gallery entry."""

    class Meta:
        model = FirmGalleryImage
        fields = ["title", "caption", "image", "rank"]
        labels = {
            "title": "Title",
            "caption": "Caption",
            "image": "Image",
            "rank": "Rank",
        }
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. Reception at Kiserian office",
                    "id": "id_gallery_title",
                }
            ),
            "caption": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Short description shown under the image",
                    "id": "id_gallery_caption",
                }
            ),
            "image": forms.FileInput(
                attrs={
                    "class": "form-input",
                    "accept": "image/*",
                    "id": "id_gallery_image",
                }
            ),
            "rank": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "min": 1,
                    "step": 1,
                    "id": "id_gallery_rank",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].required = True
        self.fields["caption"].required = False
        self.fields["image"].required = False
        self.fields["rank"].required = True
        self.fields["rank"].initial = self.fields["rank"].initial or 1

    def clean_title(self):
        title = (self.cleaned_data.get("title") or "").strip()
        if not title:
            raise ValidationError("Title is required.")
        return title

    def clean_caption(self):
        return (self.cleaned_data.get("caption") or "").strip()

    def clean_rank(self):
        rank = self.cleaned_data.get("rank")
        if rank is None or rank < 1:
            raise ValidationError("Rank must be 1 or higher.")
        return rank

    def save(self, commit=True):
        new_image = self.cleaned_data.get("image")
        if not new_image:
            self.cleaned_data["image"] = (
                self.instance.image if self.instance.pk else None
            )
        item = super().save(commit=False)
        if new_image:
            item.image = optimize_image(new_image, max_size=1600, quality=78)
        if commit:
            item.save()
        return item


class WebsiteTemplateForm(forms.ModelForm):
    """Choose which public homepage appears at `/`."""

    class Meta:
        model = WebsiteTemplateSetting
        fields = ["active_template"]
        labels = {
            "active_template": "Homepage website",
        }
        widgets = {
            "active_template": forms.RadioSelect(
                attrs={"class": "website-template-choice-group"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["active_template"].choices = list(
            WebsiteTemplateSetting.TemplateChoice.choices
        )
        self.fields["active_template"].required = True


class FinanceSettingsForm(forms.ModelForm):
    """Firm payment methods and M-Pesa / STK configuration."""

    class Meta:
        model = FinanceSettings
        fields = [
            "allow_mpesa",
            "allow_bank_transfer",
            "allow_cash",
            "allow_cheque",
            "mpesa_paybill_enabled",
            "mpesa_paybill_number",
            "mpesa_paybill_account_label",
            "mpesa_buy_goods_enabled",
            "mpesa_till_number",
            "mpesa_stk_enabled",
            "mpesa_stk_channel",
            "mpesa_consumer_key",
            "mpesa_consumer_secret",
            "mpesa_passkey",
            "mpesa_shortcode",
            "mpesa_callback_url",
            "mpesa_env",
        ]
        labels = {
            "allow_mpesa": "M-Pesa",
            "allow_bank_transfer": "Bank transfer",
            "allow_cash": "Cash",
            "allow_cheque": "Cheque",
            "mpesa_paybill_enabled": "Accept Paybill payments",
            "mpesa_paybill_number": "Paybill number",
            "mpesa_paybill_account_label": "Account reference label",
            "mpesa_buy_goods_enabled": "Accept Buy Goods (Till) payments",
            "mpesa_till_number": "Till number",
            "mpesa_stk_enabled": "Enable M-Pesa STK Push",
            "mpesa_stk_channel": "STK Push charges to",
            "mpesa_consumer_key": "Consumer key",
            "mpesa_consumer_secret": "Consumer secret",
            "mpesa_passkey": "Lipa Na M-Pesa passkey",
            "mpesa_shortcode": "Business shortcode (optional)",
            "mpesa_callback_url": "Callback URL",
            "mpesa_env": "Daraja environment",
        }
        help_texts = {
            "mpesa_paybill_account_label": "Shown to clients — usually invoice number.",
            "mpesa_shortcode": "Leave blank to use the Paybill or Till number above.",
            "mpesa_callback_url": "HTTPS URL Safaricom will POST to after payment (not localhost).",
            "mpesa_stk_enabled": "Lets staff and clients send Lipa Na M-Pesa prompts from invoices.",
        }
        widgets = {
            "allow_mpesa": forms.CheckboxInput(),
            "allow_bank_transfer": forms.CheckboxInput(),
            "allow_cash": forms.CheckboxInput(),
            "allow_cheque": forms.CheckboxInput(),
            "mpesa_paybill_enabled": forms.CheckboxInput(),
            "mpesa_buy_goods_enabled": forms.CheckboxInput(),
            "mpesa_stk_enabled": forms.CheckboxInput(),
            "mpesa_paybill_number": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. 123456",
                    "autocomplete": "off",
                    "inputmode": "numeric",
                }
            ),
            "mpesa_paybill_account_label": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Invoice number",
                    "autocomplete": "off",
                }
            ),
            "mpesa_till_number": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "e.g. 567890",
                    "autocomplete": "off",
                    "inputmode": "numeric",
                }
            ),
            "mpesa_stk_channel": forms.RadioSelect(),
            "mpesa_consumer_key": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Daraja consumer key",
                    "autocomplete": "off",
                }
            ),
            "mpesa_consumer_secret": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Daraja consumer secret",
                    "autocomplete": "off",
                }
            ),
            "mpesa_passkey": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Lipa Na M-Pesa online passkey",
                    "autocomplete": "off",
                }
            ),
            "mpesa_shortcode": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Defaults to Paybill or Till",
                    "autocomplete": "off",
                    "inputmode": "numeric",
                }
            ),
            "mpesa_callback_url": forms.URLInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "https://yourdomain.com/integrations/mpesa/callback/",
                    "autocomplete": "off",
                }
            ),
            "mpesa_env": forms.Select(attrs={"class": "form-input"}),
        }

    def clean_mpesa_callback_url(self):
        from .mpesa import is_valid_mpesa_callback_url

        url = (self.cleaned_data.get("mpesa_callback_url") or "").strip()
        if not url:
            return ""
        if not is_valid_mpesa_callback_url(url):
            raise ValidationError(
                "Use a public HTTPS URL with a path, e.g. "
                "https://yourdomain.com/integrations/mpesa/callback/. "
                "localhost and http:// are rejected by Safaricom."
            )
        return url

    def clean(self):
        cleaned = super().clean()
        allow_mpesa = cleaned.get("allow_mpesa")
        paybill_on = cleaned.get("mpesa_paybill_enabled")
        buy_goods_on = cleaned.get("mpesa_buy_goods_enabled")
        stk_on = cleaned.get("mpesa_stk_enabled")
        channel = cleaned.get("mpesa_stk_channel")
        paybill = (cleaned.get("mpesa_paybill_number") or "").strip()
        till = (cleaned.get("mpesa_till_number") or "").strip()

        if not allow_mpesa:
            cleaned["mpesa_paybill_enabled"] = False
            cleaned["mpesa_buy_goods_enabled"] = False
            cleaned["mpesa_stk_enabled"] = False
            return cleaned

        if paybill_on and not paybill:
            self.add_error("mpesa_paybill_number", "Enter the Paybill number.")
        if buy_goods_on and not till:
            self.add_error("mpesa_till_number", "Enter the Till number.")

        if not paybill_on and not buy_goods_on:
            self.add_error(
                None,
                "Enable Paybill and/or Buy Goods when M-Pesa is allowed.",
            )

        if stk_on:
            if channel == FinanceSettings.MpesaStkChannel.PAYBILL and not paybill_on:
                self.add_error(
                    "mpesa_stk_channel",
                    "Enable Paybill before using it for STK Push.",
                )
            if channel == FinanceSettings.MpesaStkChannel.BUY_GOODS and not buy_goods_on:
                self.add_error(
                    "mpesa_stk_channel",
                    "Enable Buy Goods before using it for STK Push.",
                )
            shortcode = (cleaned.get("mpesa_shortcode") or "").strip()
            effective = shortcode or (
                till
                if channel == FinanceSettings.MpesaStkChannel.BUY_GOODS
                else paybill
            )
            has_api = all(
                (cleaned.get(field) or "").strip()
                for field in (
                    "mpesa_consumer_key",
                    "mpesa_consumer_secret",
                    "mpesa_passkey",
                )
            )
            if has_api and not effective:
                self.add_error(
                    "mpesa_shortcode",
                    "Set a shortcode, or enter Paybill / Till details above.",
                )
            if has_api and not (cleaned.get("mpesa_callback_url") or "").strip():
                self.add_error(
                    "mpesa_callback_url",
                    "Required for live STK Push — use your public HTTPS callback URL.",
                )

        return cleaned


class CommunicationSettingsForm(forms.ModelForm):
    """Firm email, SMS, and WhatsApp provider configuration."""

    class Meta:
        model = CommunicationSettings
        fields = [
            "email_enabled",
            "email_host",
            "email_port",
            "email_host_user",
            "email_host_password",
            "email_from_email",
            "email_from_name",
            "sms_enabled",
            "sms_provider",
            "sms_username",
            "sms_api_key",
            "sms_api_secret",
            "sms_sender_id",
            "whatsapp_enabled",
            "whatsapp_business_number",
            "whatsapp_default_message",
            "whatsapp_api_enabled",
            "whatsapp_provider",
            "whatsapp_api_token",
            "whatsapp_phone_number_id",
            "whatsapp_webhook_url",
        ]
        labels = {
            "email_enabled": "Enable email",
            "email_host": "SMTP host",
            "email_port": "SMTP port",
            "email_host_user": "SMTP username",
            "email_host_password": "SMTP password",
            "email_from_email": "From email address",
            "email_from_name": "From display name",
            "sms_enabled": "Enable SMS",
            "sms_provider": "SMS provider",
            "sms_username": "API username / Account SID",
            "sms_api_key": "API key",
            "sms_api_secret": "API secret / Auth token",
            "sms_sender_id": "Sender ID / From number",
            "whatsapp_enabled": "Enable WhatsApp",
            "whatsapp_business_number": "Business WhatsApp number",
            "whatsapp_default_message": "Default chat message",
            "whatsapp_api_enabled": "Enable WhatsApp Business API",
            "whatsapp_provider": "WhatsApp API provider",
            "whatsapp_api_token": "API access token (Twilio: AccountSID:AuthToken)",
            "whatsapp_phone_number_id": "Phone number ID / sender",
            "whatsapp_webhook_url": "Webhook URL",
        }
        help_texts = {
            "email_port": "465 uses SSL automatically; 587 uses TLS automatically.",
            "email_from_email": "Address clients and staff see as the sender.",
            "sms_username": "Africa's Talking username, or Twilio Account SID.",
            "sms_api_secret": "Required for Twilio (Auth Token).",
            "sms_sender_id": "Alphanumeric sender ID or E.164 from-number.",
            "whatsapp_business_number": "Used for click-to-chat links (wa.me).",
            "whatsapp_default_message": "Optional text pre-filled when opening chat.",
            "whatsapp_api_enabled": "Turn on when you are ready to send WhatsApp messages via API.",
            "whatsapp_api_token": "Meta token, or Twilio as AccountSID:AuthToken.",
            "whatsapp_phone_number_id": "Meta Phone Number ID, or Twilio WhatsApp sender (whatsapp:+254…).",
            "whatsapp_webhook_url": "HTTPS URL for delivery / inbound webhooks.",
        }
        widgets = {
            "email_enabled": forms.CheckboxInput(),
            "sms_enabled": forms.CheckboxInput(),
            "whatsapp_enabled": forms.CheckboxInput(),
            "whatsapp_api_enabled": forms.CheckboxInput(),
            "email_host": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "smtp.example.com",
                    "autocomplete": "off",
                }
            ),
            "email_port": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "587",
                    "min": "1",
                    "max": "65535",
                }
            ),
            "email_host_user": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "user@example.com",
                    "autocomplete": "off",
                }
            ),
            "email_host_password": forms.PasswordInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "SMTP password or app password",
                    "autocomplete": "new-password",
                },
                render_value=True,
            ),
            "email_from_email": forms.EmailInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "noreply@yourfirm.com",
                    "autocomplete": "off",
                }
            ),
            "email_from_name": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Bauni Law Group",
                    "autocomplete": "off",
                }
            ),
            "sms_provider": forms.Select(attrs={"class": "form-input"}),
            "sms_username": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "sandbox or Account SID",
                    "autocomplete": "off",
                }
            ),
            "sms_api_key": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "API key",
                    "autocomplete": "off",
                }
            ),
            "sms_api_secret": forms.PasswordInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Auth token (Twilio)",
                    "autocomplete": "new-password",
                },
                render_value=True,
            ),
            "sms_sender_id": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "SHERIALAW or +2547…",
                    "autocomplete": "off",
                }
            ),
            "whatsapp_business_number": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "+2547…",
                    "autocomplete": "off",
                    "inputmode": "tel",
                }
            ),
            "whatsapp_default_message": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Hello, I would like to enquire…",
                    "autocomplete": "off",
                }
            ),
            "whatsapp_provider": forms.Select(attrs={"class": "form-input"}),
            "whatsapp_api_token": forms.PasswordInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Access token",
                    "autocomplete": "new-password",
                },
                render_value=True,
            ),
            "whatsapp_phone_number_id": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Phone number ID or whatsapp:+254…",
                    "autocomplete": "off",
                }
            ),
            "whatsapp_webhook_url": forms.URLInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "https://yourdomain.com/integrations/whatsapp/webhook/",
                    "autocomplete": "off",
                }
            ),
        }

    def clean_email_port(self):
        port = self.cleaned_data.get("email_port")
        if port is None:
            return 587
        if port < 1 or port > 65535:
            raise ValidationError("Enter a valid port between 1 and 65535.")
        return port

    def clean_whatsapp_webhook_url(self):
        url = (self.cleaned_data.get("whatsapp_webhook_url") or "").strip()
        if not url:
            return ""
        if not url.lower().startswith("https://"):
            raise ValidationError("Use a public HTTPS webhook URL.")
        return url

    def clean(self):
        cleaned = super().clean()
        email_on = cleaned.get("email_enabled")
        sms_on = cleaned.get("sms_enabled")
        wa_on = cleaned.get("whatsapp_enabled")
        wa_api_on = cleaned.get("whatsapp_api_enabled")

        if email_on:
            if not (cleaned.get("email_host") or "").strip():
                self.add_error("email_host", "Enter the SMTP host.")
            if not (cleaned.get("email_from_email") or "").strip():
                self.add_error("email_from_email", "Enter the from email address.")
        else:
            cleaned["email_enabled"] = False

        if sms_on:
            provider = cleaned.get("sms_provider")
            if provider in (
                None,
                CommunicationSettings.SmsProvider.NONE,
                "",
            ):
                self.add_error("sms_provider", "Choose an SMS provider.")
            elif provider == CommunicationSettings.SmsProvider.AFRICASTALKING:
                if not (cleaned.get("sms_username") or "").strip():
                    self.add_error("sms_username", "Enter the Africa's Talking username.")
                if not (cleaned.get("sms_api_key") or "").strip():
                    self.add_error("sms_api_key", "Enter the API key.")
                if not (cleaned.get("sms_sender_id") or "").strip():
                    self.add_error("sms_sender_id", "Enter the sender ID.")
            elif provider == CommunicationSettings.SmsProvider.TWILIO:
                if not (cleaned.get("sms_username") or "").strip():
                    self.add_error("sms_username", "Enter the Twilio Account SID.")
                if not (cleaned.get("sms_api_secret") or "").strip():
                    self.add_error("sms_api_secret", "Enter the Twilio Auth Token.")
                if not (cleaned.get("sms_sender_id") or "").strip():
                    self.add_error("sms_sender_id", "Enter the from number.")
        else:
            cleaned["sms_enabled"] = False
            cleaned["sms_provider"] = CommunicationSettings.SmsProvider.NONE

        if wa_on:
            if not (cleaned.get("whatsapp_business_number") or "").strip():
                self.add_error(
                    "whatsapp_business_number",
                    "Enter the business WhatsApp number.",
                )
            if wa_api_on:
                provider = cleaned.get("whatsapp_provider")
                if provider in (
                    None,
                    CommunicationSettings.WhatsAppProvider.NONE,
                    "",
                ):
                    self.add_error(
                        "whatsapp_provider",
                        "Choose a WhatsApp API provider.",
                    )
                if not (cleaned.get("whatsapp_api_token") or "").strip():
                    self.add_error("whatsapp_api_token", "Enter the API access token.")
                if not (cleaned.get("whatsapp_phone_number_id") or "").strip():
                    self.add_error(
                        "whatsapp_phone_number_id",
                        "Enter the phone number ID or sender.",
                    )
            else:
                cleaned["whatsapp_api_enabled"] = False
                cleaned["whatsapp_provider"] = (
                    CommunicationSettings.WhatsAppProvider.NONE
                )
        else:
            cleaned["whatsapp_enabled"] = False
            cleaned["whatsapp_api_enabled"] = False
            cleaned["whatsapp_provider"] = CommunicationSettings.WhatsAppProvider.NONE

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        use_tls, use_ssl = CommunicationSettings.smtp_security_for_port(
            instance.email_port
        )
        instance.email_use_tls = use_tls
        instance.email_use_ssl = use_ssl
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class DocumentPartyTypeMixin:
    """Require a party type selection for case/matter documents."""

    def _add_party_type_field(self, party_type_choices=None):
        choices = list(party_type_choices or CaseParty.PartyType.choices)
        self.fields["party_type"] = forms.ChoiceField(
            choices=[("", "Select party type…")] + choices,
            label="Party type",
            widget=forms.Select(attrs={"class": "form-input"}),
            error_messages={"required": "Select a party type."},
        )
        self._party_type_valid = {key for key, _label in choices}

    def clean_party_type(self):
        value = (self.cleaned_data.get("party_type") or "").strip()
        if not value:
            raise ValidationError("Select a party type.")
        if value not in self._party_type_valid:
            raise ValidationError("Select a valid party type.")
        return value

    def party_type_kwargs(self) -> dict:
        return {"party_type": self.cleaned_data.get("party_type") or ""}


class CreateGoogleDocumentForm(DocumentPartyTypeMixin, forms.Form):
    """Name and describe a file, then choose Docs / Excel / Slides."""

    GOOGLE_TYPE_CHOICES = (
        ("document", "Docs"),
        ("spreadsheet", "Excel"),
        ("presentation", "Slides"),
    )

    title = forms.CharField(
        max_length=255,
        label="File name",
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "e.g. Plaint, Budget, Hearing pack",
                "autocomplete": "off",
            }
        ),
    )
    description = forms.CharField(
        label="Description",
        widget=forms.Textarea(
            attrs={
                "class": "form-input",
                "rows": 3,
                "placeholder": "Briefly describe what this file is for",
            }
        ),
    )
    google_type = forms.ChoiceField(
        choices=GOOGLE_TYPE_CHOICES,
        initial="document",
        label="Create as",
        widget=forms.RadioSelect(
            attrs={"class": "docs-type-input"}
        ),
    )

    def __init__(self, *args, party_type_choices=None, **kwargs):
        kwargs.pop("default_client", None)
        super().__init__(*args, **kwargs)
        self._add_party_type_field(party_type_choices)

    def clean_title(self):
        title = (self.cleaned_data.get("title") or "").strip()
        if not title:
            raise ValidationError("Enter a file name.")
        return title

    def clean_description(self):
        description = (self.cleaned_data.get("description") or "").strip()
        if not description:
            raise ValidationError("Describe the file.")
        return description

    def clean_google_type(self):
        value = (self.cleaned_data.get("google_type") or "").strip()
        valid = {key for key, _label in self.GOOGLE_TYPE_CHOICES}
        if value not in valid:
            raise ValidationError("Choose Docs, Excel, or Slides.")
        return value


class UploadDocumentForm(DocumentPartyTypeMixin, forms.Form):
    """Upload a file, name it, and assign a party type."""

    title = forms.CharField(
        max_length=255,
        label="Document name",
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "e.g. Signed agreement, Court order",
                "autocomplete": "off",
            }
        ),
    )
    file = forms.FileField(
        label="File",
        widget=forms.FileInput(
            attrs={
                "class": "form-input docs-drop__input",
                "accept": (
                    ".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.rtf,"
                    ".png,.jpg,.jpeg,.gif,.webp,.csv"
                ),
            }
        ),
    )
    notes = forms.CharField(
        required=False,
        label="Notes",
        widget=forms.Textarea(
            attrs={
                "class": "form-input",
                "rows": 2,
                "placeholder": "Optional notes about this document",
            }
        ),
    )

    def __init__(self, *args, party_type_choices=None, **kwargs):
        kwargs.pop("default_client", None)
        super().__init__(*args, **kwargs)
        self._add_party_type_field(party_type_choices)

    def clean_title(self):
        title = (self.cleaned_data.get("title") or "").strip()
        if not title:
            raise ValidationError("Enter a document name.")
        return title

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        if not uploaded:
            raise ValidationError("Choose a file to upload.")
        max_bytes = 15 * 1024 * 1024
        if getattr(uploaded, "size", 0) > max_bytes:
            raise ValidationError("File must be 15 MB or smaller.")
        return uploaded


class RenameDocumentForm(DocumentPartyTypeMixin, forms.Form):
    """Edit document name, description, notes, and party type (and rename on Drive)."""

    title = forms.CharField(
        max_length=255,
        label="Document name",
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "autocomplete": "off",
                "placeholder": "Document name",
            }
        ),
    )
    description = forms.CharField(
        required=False,
        label="Description",
        widget=forms.Textarea(
            attrs={
                "class": "form-input",
                "rows": 3,
                "placeholder": "What this document is for",
            }
        ),
    )
    notes = forms.CharField(
        required=False,
        label="Notes",
        widget=forms.Textarea(
            attrs={
                "class": "form-input",
                "rows": 2,
                "placeholder": "Optional internal notes",
            }
        ),
    )

    def __init__(self, *args, party_type_choices=None, **kwargs):
        kwargs.pop("default_client", None)
        super().__init__(*args, **kwargs)
        self._add_party_type_field(party_type_choices)

    def clean_title(self):
        title = (self.cleaned_data.get("title") or "").strip()
        if not title:
            raise ValidationError("Enter a document name.")
        return title

    def clean_description(self):
        return (self.cleaned_data.get("description") or "").strip()

    def clean_notes(self):
        return (self.cleaned_data.get("notes") or "").strip()


class GenerateInvoiceForm(forms.ModelForm):
    """Create a new invoice with multiple service line items and optional tax."""

    class Meta:
        model = Invoice
        fields = [
            "client",
            "issue_date",
            "due_date",
            "description",
            "amount",
            "tax_amount",
            "notes",
        ]
        labels = {
            "client": "Client",
            "issue_date": "Issue date",
            "due_date": "Due date",
            "description": "Description",
            "amount": "Subtotal",
            "tax_amount": "Tax amount",
            "notes": "Notes",
        }
        widgets = {
            "client": forms.Select(
                attrs={
                    "class": "form-input",
                    "id": "id_invoice_client",
                }
            ),
            "issue_date": forms.DateInput(
                attrs={
                    "class": "form-input",
                    "type": "date",
                    "id": "id_invoice_issue_date",
                }
            ),
            "due_date": forms.DateInput(
                attrs={
                    "class": "form-input",
                    "type": "date",
                    "id": "id_invoice_due_date",
                }
            ),
            "description": forms.HiddenInput(
                attrs={"id": "id_invoice_description"}
            ),
            "amount": forms.HiddenInput(
                attrs={"id": "id_invoice_amount"}
            ),
            "tax_amount": forms.HiddenInput(
                attrs={"id": "id_invoice_tax_amount"}
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 2,
                    "placeholder": "Optional notes for this invoice",
                    "id": "id_invoice_notes",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = Client.objects.filter(
            status=Client.Status.ACTIVE
        ).order_by("company_name", "first_name", "last_name", "email")
        self.fields["client"].empty_label = "Select a client"
        self.fields["due_date"].required = False
        self.fields["tax_amount"].required = False
        self.fields["notes"].required = False
        today = timezone.localdate()
        self.fields["issue_date"].initial = today
        self.fields["due_date"].initial = None
        self.fields["tax_amount"].initial = 0

    def clean_description(self):
        description = (self.cleaned_data.get("description") or "").strip()
        if not description:
            raise ValidationError("Enter a description for this invoice.")
        return description

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None or amount < 0:
            raise ValidationError("Enter a valid amount (0 or greater).")
        return amount

    def clean_tax_amount(self):
        tax_amount = self.cleaned_data.get("tax_amount")
        if tax_amount is None:
            return 0
        if tax_amount < 0:
            raise ValidationError("Tax amount cannot be negative.")
        return tax_amount

    def clean_notes(self):
        return (self.cleaned_data.get("notes") or "").strip()

    def clean(self):
        cleaned = super().clean()
        issue_date = cleaned.get("issue_date")
        due_date = cleaned.get("due_date")
        if issue_date and due_date and due_date < issue_date:
            self.add_error("due_date", "Due date cannot be before the issue date.")
        return cleaned


class InvoiceStkPaymentForm(forms.Form):
    """Collect payment method, amount, and M-Pesa details for an invoice."""

    METHOD_MANUAL = "manual"
    METHOD_MPESA = "mpesa"
    METHOD_CHOICES = (
        (METHOD_MANUAL, "Manual"),
        (METHOD_MPESA, "M-Pesa STK"),
    )

    method = forms.ChoiceField(
        choices=METHOD_CHOICES,
        label="Payment method",
        required=False,
        initial=METHOD_MPESA,
        widget=forms.Select(
            attrs={"class": "form-input", "id": "id_pay_method"}
        ),
    )
    phone = forms.CharField(
        required=False,
        label="M-Pesa phone number",
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "07XX XXX XXX",
                "inputmode": "tel",
                "autocomplete": "tel",
                "id": "id_stk_phone",
            }
        ),
    )
    amount = forms.DecimalField(
        label="Amount (KES)",
        min_value=Decimal("1"),
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input",
                "placeholder": "0.00",
                "inputmode": "decimal",
                "step": "0.01",
                "min": "1",
                "id": "id_stk_amount",
            }
        ),
    )
    reference = forms.CharField(
        required=False,
        label="Reference / note",
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "e.g. bank ref, cash receipt",
                "id": "id_pay_reference",
            }
        ),
    )

    def __init__(self, *args, max_amount=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_amount = None
        if max_amount is not None:
            try:
                self.max_amount = Decimal(max_amount).quantize(Decimal("0.01"))
            except Exception:
                self.max_amount = None
        if self.max_amount is not None and self.max_amount >= 1:
            self.fields["amount"].help_text = (
                f"Balance due is KES {self.max_amount}. "
                "You may pay more — the excess is kept as client credit and "
                "added to Main Client Accounts."
            )

    def clean_phone(self):
        from .mpesa import MpesaError, normalize_msisdn

        phone = (self.cleaned_data.get("phone") or "").strip()
        if not phone:
            return ""
        try:
            return normalize_msisdn(phone)
        except MpesaError as exc:
            raise ValidationError(str(exc)) from exc

    def clean_reference(self):
        return (self.cleaned_data.get("reference") or "").strip()

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None:
            raise ValidationError("Enter the amount to charge.")
        amount = Decimal(amount).quantize(Decimal("0.01"))
        if amount < 1:
            raise ValidationError("Amount must be at least KES 1.")
        # Overpayments are allowed: invoice is settled and surplus credits
        # Main Client Accounts + the client's credit balance.
        return amount

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get("method") or self.METHOD_MPESA
        cleaned["method"] = method
        phone = cleaned.get("phone") or ""
        if method == self.METHOD_MPESA and not phone:
            self.add_error(
                "phone",
                "Enter the Safaricom number that will receive the STK push.",
            )
        return cleaned


class PayrollDeductionForm(forms.Form):
    """One deduction line when registering payroll."""

    deduction_type = forms.ChoiceField(
        choices=[("", "Select deduction")] + list(PayrollDeduction.DeductionType.choices),
        widget=forms.Select(
            attrs={
                "class": "form-input payroll-deduction-type",
            }
        ),
    )
    description = forms.CharField(
        required=False,
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "class": "form-input payroll-deduction-description",
                "placeholder": "Description (for Other)",
            }
        ),
    )
    amount = forms.DecimalField(
        required=False,
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "form-input payroll-deduction-amount",
                "min": "0",
                "step": "0.01",
                "placeholder": "0.00",
            }
        ),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("DELETE"):
            return cleaned

        deduction_type = cleaned.get("deduction_type") or ""
        amount = cleaned.get("amount")
        if not deduction_type and amount in (None, ""):
            cleaned["SKIP"] = True
            return cleaned

        if not deduction_type:
            self.add_error("deduction_type", "Select a deduction type.")
        if amount in (None, ""):
            self.add_error("amount", "Enter the deduction amount.")
        elif amount is not None and amount <= 0:
            self.add_error("amount", "Deduction amount must be greater than zero.")
        if (
            deduction_type == PayrollDeduction.DeductionType.OTHER
            and not (cleaned.get("description") or "").strip()
        ):
            self.add_error("description", "Enter a description for this deduction.")
        return cleaned


PayrollDeductionFormSet = forms.formset_factory(
    PayrollDeductionForm,
    extra=1,
    min_num=0,
    validate_min=False,
    can_delete=True,
)


def _parse_pay_period_date(value):
    if not value:
        return None
    if hasattr(value, "year"):
        return value
    return parse_date(str(value))


def default_pay_period(frequency=None):
    from .payroll_calc import DEFAULT_PAY_FREQUENCY, resolve_pay_period

    freq = frequency or DEFAULT_PAY_FREQUENCY
    start, end, _frequency = resolve_pay_period(None, freq)
    return start, end, _frequency


def payroll_registered_employee_ids(
    pay_period_start, pay_period_end=None, pay_frequency=None
):
    from .payroll_calc import resolve_pay_period

    start = _parse_pay_period_date(pay_period_start)
    frequency = pay_frequency or PayrollRun.PayFrequency.MONTHLY
    if not start:
        return set()
    start, end, frequency = resolve_pay_period(start, frequency)
    return set(
        PayrollRun.objects.filter(
            pay_period_start=start,
            pay_frequency=frequency,
        ).values_list("employee_id", flat=True)
    )


def employees_available_for_payroll(
    pay_period_start=None, pay_period_end=None, pay_frequency=None
):
    from .payroll_calc import resolve_pay_period

    start, end, frequency = resolve_pay_period(
        _parse_pay_period_date(pay_period_start),
        pay_frequency,
    )
    registered_ids = payroll_registered_employee_ids(start, end, frequency)
    return Employee.objects.filter(
        status__in=[
            Employee.Status.ACTIVE,
            Employee.Status.SUSPENDED,
            Employee.Status.PENDING_APPROVAL,
        ]
    ).exclude(pk__in=registered_ids).order_by(
        "first_name", "last_name", "login_code"
    )


class RegisterPayrollForm(forms.ModelForm):
    """Register payroll with Kenya statutory earnings, deductions, and employer costs."""

    class Meta:
        model = PayrollRun
        fields = [
            "employee",
            "pay_frequency",
            "pay_period_start",
            "basic_salary",
            "house_allowance",
            "transport_allowance",
            "medical_allowance",
            "other_allowances",
            "bonuses_overtime_commissions",
            "nssf_employee_rate",
            "nssf_employer_rate",
            "nssf_tier1_limit",
            "nssf_pensionable_cap",
            "shif_rate",
            "housing_levy_employee_rate",
            "housing_levy_employer_rate",
            "paye_personal_relief",
            "paye_band_1_max",
            "paye_band_1_rate",
            "paye_band_2_max",
            "paye_band_2_rate",
            "paye_band_3_max",
            "paye_band_3_rate",
            "paye_band_4_rate",
            "nita_levy_amount",
            "wiba_insurance_amount",
            "notes",
        ]
        widgets = {
            "employee": forms.Select(
                attrs={"class": "form-input", "id": "id_payroll_employee"}
            ),
            "pay_frequency": forms.Select(
                attrs={
                    "class": "form-input",
                    "id": "id_payroll_frequency",
                }
            ),
            "pay_period_start": forms.DateInput(
                attrs={
                    "class": "form-input",
                    "type": "date",
                    "id": "id_payroll_period_start",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 2,
                    "placeholder": "Optional payroll notes",
                    "id": "id_payroll_notes",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        from .payroll_calc import PAYROLL_RATE_DEFAULTS

        super().__init__(*args, **kwargs)
        period_start, period_end, frequency = self._resolved_pay_period()
        employees = employees_available_for_payroll(
            period_start, period_end, frequency
        )
        self.fields["employee"].queryset = employees
        self.fields["employee"].empty_label = (
            "Select an employee"
            if employees.exists()
            else "No employees available for this pay period"
        )
        self.fields["notes"].required = False
        self.fields["pay_frequency"].choices = PayrollRun.PayFrequency.choices

        money_fields = (
            "basic_salary",
            "house_allowance",
            "transport_allowance",
            "medical_allowance",
            "other_allowances",
            "bonuses_overtime_commissions",
            "nssf_tier1_limit",
            "nssf_pensionable_cap",
            "paye_personal_relief",
            "paye_band_1_max",
            "paye_band_2_max",
            "paye_band_3_max",
            "nita_levy_amount",
            "wiba_insurance_amount",
        )
        rate_fields = (
            "nssf_employee_rate",
            "nssf_employer_rate",
            "shif_rate",
            "housing_levy_employee_rate",
            "housing_levy_employer_rate",
            "paye_band_1_rate",
            "paye_band_2_rate",
            "paye_band_3_rate",
            "paye_band_4_rate",
        )
        for name in money_fields:
            self.fields[name].required = False
            self.fields[name].widget.attrs.update(
                {
                    "class": "form-input payroll-money",
                    "min": "0",
                    "step": "0.01",
                    "placeholder": "0.00",
                    "id": f"id_payroll_{name}",
                }
            )
        for name in rate_fields:
            self.fields[name].widget.attrs.update(
                {
                    "class": "form-input payroll-rate",
                    "min": "0",
                    "step": "0.01",
                    "id": f"id_payroll_{name}",
                }
            )
        self.fields["basic_salary"].required = True

        if not self.is_bound:
            self.fields["pay_period_start"].initial = period_start
            self.fields["pay_frequency"].initial = frequency
            for name, value in PAYROLL_RATE_DEFAULTS.items():
                if name in self.fields and name not in {
                    "nita_levy_amount",
                    "wiba_insurance_amount",
                }:
                    self.fields[name].initial = value
            self.fields["nita_levy_amount"].initial = PAYROLL_RATE_DEFAULTS[
                "nita_levy_amount"
            ]
            self.fields["wiba_insurance_amount"].initial = Decimal("0.00")

        self.payroll_breakdown = None

    def _resolved_pay_period(self):
        from .payroll_calc import resolve_pay_period

        if self.is_bound:
            start = _parse_pay_period_date(self.data.get("pay_period_start"))
            frequency = self.data.get("pay_frequency") or PayrollRun.PayFrequency.MONTHLY
            if start:
                return resolve_pay_period(start, frequency)
        initial_start = self.initial.get("pay_period_start")
        initial_frequency = (
            self.initial.get("pay_frequency") or PayrollRun.PayFrequency.MONTHLY
        )
        start = _parse_pay_period_date(initial_start)
        if start:
            return resolve_pay_period(start, initial_frequency)
        return resolve_pay_period(None, initial_frequency)

    def clean_employee(self):
        employee = self.cleaned_data.get("employee")
        if not employee:
            return employee
        start, end, frequency = self._resolved_pay_period()
        if employee.pk in payroll_registered_employee_ids(start, end, frequency):
            raise ValidationError(
                "This employee already has payroll registered for the selected period."
            )
        return employee

    def clean_basic_salary(self):
        basic = self.cleaned_data.get("basic_salary")
        if basic is None:
            raise ValidationError("Enter the basic salary.")
        basic = Decimal(basic).quantize(Decimal("0.01"))
        if basic <= 0:
            raise ValidationError("Basic salary must be greater than zero.")
        return basic

    def clean(self):
        from .payroll_calc import PayrollEarnings, PayrollRates, calculate_payroll

        cleaned = super().clean()
        from .payroll_calc import pay_period_end_for_frequency

        start = cleaned.get("pay_period_start")
        frequency = cleaned.get("pay_frequency") or PayrollRun.PayFrequency.MONTHLY
        employee = cleaned.get("employee")
        if start:
            cleaned["pay_period_end"] = pay_period_end_for_frequency(start, frequency)
        else:
            return cleaned

        if employee and start:
            if employee.pk in payroll_registered_employee_ids(
                start, cleaned["pay_period_end"], frequency
            ):
                raise ValidationError(
                    "Payroll is already registered for this employee and pay period."
                )

        if self.errors:
            return cleaned

        # Optional blank money inputs become None; coerce to 0 so MySQL NOT NULL columns save.
        money_defaults = (
            "house_allowance",
            "transport_allowance",
            "medical_allowance",
            "other_allowances",
            "bonuses_overtime_commissions",
            "nssf_tier1_limit",
            "nssf_pensionable_cap",
            "paye_personal_relief",
            "paye_band_1_max",
            "paye_band_2_max",
            "paye_band_3_max",
            "nita_levy_amount",
            "wiba_insurance_amount",
        )
        for name in money_defaults:
            if cleaned.get(name) is None:
                cleaned[name] = Decimal("0.00")

        rate_defaults = (
            "nssf_employee_rate",
            "nssf_employer_rate",
            "shif_rate",
            "housing_levy_employee_rate",
            "housing_levy_employer_rate",
            "paye_band_1_rate",
            "paye_band_2_rate",
            "paye_band_3_rate",
            "paye_band_4_rate",
        )
        for name in rate_defaults:
            if cleaned.get(name) is None:
                cleaned[name] = Decimal("0.00")

        earnings = PayrollEarnings(
            basic_salary=cleaned.get("basic_salary") or Decimal("0"),
            house_allowance=cleaned["house_allowance"],
            transport_allowance=cleaned["transport_allowance"],
            medical_allowance=cleaned["medical_allowance"],
            other_allowances=cleaned["other_allowances"],
            bonuses_overtime_commissions=cleaned["bonuses_overtime_commissions"],
        )
        if earnings.gross_salary <= 0:
            raise ValidationError("Total earnings must be greater than zero.")

        rates = PayrollRates(
            nssf_employee_rate=cleaned["nssf_employee_rate"],
            nssf_employer_rate=cleaned["nssf_employer_rate"],
            nssf_tier1_limit=cleaned["nssf_tier1_limit"],
            nssf_pensionable_cap=cleaned["nssf_pensionable_cap"],
            shif_rate=cleaned["shif_rate"],
            housing_levy_employee_rate=cleaned["housing_levy_employee_rate"],
            housing_levy_employer_rate=cleaned["housing_levy_employer_rate"],
            paye_personal_relief=cleaned["paye_personal_relief"],
            paye_band_1_max=cleaned["paye_band_1_max"],
            paye_band_1_rate=cleaned["paye_band_1_rate"],
            paye_band_2_max=cleaned["paye_band_2_max"],
            paye_band_2_rate=cleaned["paye_band_2_rate"],
            paye_band_3_max=cleaned["paye_band_3_max"],
            paye_band_3_rate=cleaned["paye_band_3_rate"],
            paye_band_4_rate=cleaned["paye_band_4_rate"],
            nita_levy_amount=cleaned["nita_levy_amount"],
            wiba_insurance_amount=cleaned["wiba_insurance_amount"],
        )
        breakdown = calculate_payroll(earnings, rates)
        if breakdown.net_pay < 0:
            raise ValidationError(
                "Total employee deductions exceed gross earnings. "
                "Adjust earnings or statutory rates."
            )
        self.payroll_breakdown = breakdown
        return cleaned

    def save(self, commit=True):
        from .payroll_calc import pay_period_end_for_frequency

        payroll_run = super().save(commit=False)
        start = self.cleaned_data["pay_period_start"]
        frequency = self.cleaned_data.get("pay_frequency") or PayrollRun.PayFrequency.MONTHLY
        payroll_run.pay_frequency = frequency
        payroll_run.pay_period_end = pay_period_end_for_frequency(start, frequency)
        breakdown = self.payroll_breakdown
        if breakdown is None:
            payroll_run.recalculate_totals(save=False)
        else:
            payroll_run.gross_salary = breakdown.gross_salary
            payroll_run.nssf_employee_amount = breakdown.nssf_employee_amount
            payroll_run.shif_amount = breakdown.shif_amount
            payroll_run.housing_levy_employee_amount = (
                breakdown.housing_levy_employee_amount
            )
            payroll_run.paye_amount = breakdown.paye_amount
            payroll_run.taxable_income = breakdown.taxable_income
            payroll_run.total_deductions = breakdown.total_employee_deductions
            payroll_run.net_pay = breakdown.net_pay
            payroll_run.nssf_employer_amount = breakdown.nssf_employer_amount
            payroll_run.housing_levy_employer_amount = (
                breakdown.housing_levy_employer_amount
            )
            payroll_run.total_employer_cost = breakdown.total_employer_cost
        if commit:
            payroll_run.save()
            payroll_run.sync_deduction_lines()
        return payroll_run


def next_available_pay_period(employee, frequency=None):
    """Return the next pay period for an employee that has no payroll run yet."""
    from datetime import timedelta

    from .payroll_calc import (
        DEFAULT_PAY_FREQUENCY,
        pay_period_end_for_frequency,
        resolve_pay_period,
    )

    frequency = frequency or DEFAULT_PAY_FREQUENCY
    start, end, frequency = resolve_pay_period(None, frequency)
    for _ in range(48):
        if employee.pk not in payroll_registered_employee_ids(start, end, frequency):
            return start, end, frequency
        if frequency == PayrollRun.PayFrequency.DAILY:
            start = start + timedelta(days=1)
        elif frequency == PayrollRun.PayFrequency.WEEKLY:
            start = start + timedelta(days=7)
        elif frequency == PayrollRun.PayFrequency.ANNUALLY:
            start = start.replace(year=start.year + 1)
        else:
            if start.month == 12:
                start = start.replace(year=start.year + 1, month=1, day=1)
            else:
                start = start.replace(month=start.month + 1, day=1)
        end = pay_period_end_for_frequency(start, frequency)
    return start, end, frequency


class UpdateEmployeeSalaryForm(forms.Form):
    """Update an employee's monthly salary and create a new payroll run."""

    monthly_salary = forms.DecimalField(
        min_value=Decimal("0.01"),
        max_digits=14,
        decimal_places=2,
        label="Monthly salary (KES)",
        widget=forms.NumberInput(
            attrs={
                "class": "form-input",
                "id": "id_update_salary_amount",
                "min": "0.01",
                "step": "0.01",
                "placeholder": "0.00",
            }
        ),
    )
    pay_frequency = forms.ChoiceField(
        choices=PayrollRun.PayFrequency.choices,
        label="Pay frequency",
        widget=forms.Select(
            attrs={"class": "form-input", "id": "id_update_salary_frequency"}
        ),
    )
    pay_period_start = forms.DateField(
        label="Pay period start",
        widget=forms.DateInput(
            attrs={
                "class": "form-input",
                "type": "date",
                "id": "id_update_salary_period_start",
            }
        ),
    )

    def __init__(self, employee, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.employee = employee
        start, _end, frequency = next_available_pay_period(employee)
        if not self.is_bound:
            self.fields["pay_frequency"].initial = frequency
            self.fields["pay_period_start"].initial = start
            if employee.monthly_salary is not None:
                self.fields["monthly_salary"].initial = employee.monthly_salary

    def clean_monthly_salary(self):
        salary = self.cleaned_data["monthly_salary"]
        salary = Decimal(salary).quantize(Decimal("0.01"))
        if salary <= 0:
            raise ValidationError("Salary must be greater than zero.")
        return salary

    def clean(self):
        from .payroll_calc import pay_period_end_for_frequency

        cleaned = super().clean()
        start = cleaned.get("pay_period_start")
        frequency = cleaned.get("pay_frequency") or PayrollRun.PayFrequency.MONTHLY
        if not start:
            return cleaned
        end = pay_period_end_for_frequency(start, frequency)
        cleaned["pay_period_end"] = end
        if self.employee.pk in payroll_registered_employee_ids(start, end, frequency):
            raise ValidationError(
                "Payroll is already registered for this employee and pay period. "
                "Choose a different start date."
            )
        return cleaned

    def save(self, *, registered_by):
        from .payroll_calc import PAYROLL_RATE_DEFAULTS

        salary = self.cleaned_data["monthly_salary"]
        frequency = self.cleaned_data["pay_frequency"]
        start = self.cleaned_data["pay_period_start"]

        self.employee.monthly_salary = salary
        self.employee.save(update_fields=["monthly_salary"])

        last_run = (
            self.employee.payroll_runs.order_by(
                "-pay_period_start", "-registered_at"
            ).first()
        )

        data = {
            "employee": str(self.employee.pk),
            "pay_frequency": frequency,
            "pay_period_start": start.isoformat(),
            "basic_salary": str(salary),
            "house_allowance": str(last_run.house_allowance if last_run else "0"),
            "transport_allowance": str(
                last_run.transport_allowance if last_run else "0"
            ),
            "medical_allowance": str(last_run.medical_allowance if last_run else "0"),
            "other_allowances": str(last_run.other_allowances if last_run else "0"),
            "bonuses_overtime_commissions": str(
                last_run.bonuses_overtime_commissions if last_run else "0"
            ),
            "notes": "Salary update",
        }
        for key, value in PAYROLL_RATE_DEFAULTS.items():
            if last_run is not None and hasattr(last_run, key):
                data[key] = str(getattr(last_run, key))
            else:
                data[key] = str(value)

        register_form = RegisterPayrollForm(data)
        if not register_form.is_valid():
            errors = []
            for field_errors in register_form.errors.values():
                errors.extend(str(err) for err in field_errors)
            raise ValidationError(errors or ["Could not create the payroll run."])

        payroll_run = register_form.save(commit=False)
        payroll_run.payment_method = self.employee.payment_method or ""
        payroll_run.payment_method_label = (
            self.employee.get_payment_method_display()
            if self.employee.payment_method
            else ""
        )
        payroll_run.payout_destination = self.employee.payroll_payout_destination()
        payroll_run.registered_by = registered_by
        payroll_run.notes = "Salary update"
        payroll_run.save()
        payroll_run.sync_deduction_lines()
        return payroll_run


class RegisterCompanyAccountForm(forms.ModelForm):
    """Register a firm expense account under Company Accounts."""

    payment_methods = forms.MultipleChoiceField(
        choices=CompanyExpenseAccount.PaymentMethod.choices,
        required=True,
        widget=forms.CheckboxSelectMultiple(
            attrs={"class": "company-account-method-checks"}
        ),
        label="Payment methods used",
        error_messages={
            "required": "Select at least one payment method.",
        },
    )

    class Meta:
        model = CompanyExpenseAccount
        fields = [
            "name",
            "bank_name",
            "bank_account_number",
            "description",
            "payment_methods",
        ]
        labels = {
            "name": "Account name",
            "bank_name": "Bank name",
            "bank_account_number": "Bank account number",
            "description": "Description of the expense account",
        }
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-input form-input--uppercase",
                    "placeholder": "E.G. OFFICE SUPPLIES, TRAVEL, UTILITIES",
                    "autocomplete": "off",
                    "style": "text-transform: uppercase;",
                }
            ),
            "bank_name": forms.TextInput(
                attrs={
                    "class": "form-input form-input--uppercase",
                    "placeholder": "E.G. EQUITY BANK, KCB, ABSA",
                    "autocomplete": "organization",
                    "style": "text-transform: uppercase;",
                }
            ),
            "bank_account_number": forms.TextInput(
                attrs={
                    "class": "form-input form-input--uppercase",
                    "placeholder": "ACCOUNT NUMBER",
                    "autocomplete": "off",
                    "inputmode": "text",
                    "style": "text-transform: uppercase;",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 3,
                    "placeholder": "What this expense account is used for",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = True
        self.fields["bank_name"].required = True
        self.fields["bank_account_number"].required = True
        self.fields["description"].required = False
        if self.instance and self.instance.pk and self.instance.payment_methods:
            self.initial["payment_methods"] = list(self.instance.payment_methods)

    def clean_name(self):
        return (self.cleaned_data.get("name") or "").strip().upper()

    def clean_bank_name(self):
        return (self.cleaned_data.get("bank_name") or "").strip().upper()

    def clean_bank_account_number(self):
        return (self.cleaned_data.get("bank_account_number") or "").strip().upper()

    def clean_description(self):
        return (self.cleaned_data.get("description") or "").strip()

    def clean_payment_methods(self):
        methods = list(self.cleaned_data.get("payment_methods") or [])
        if not methods:
            raise ValidationError("Select at least one payment method.")
        return methods


class TopupClientAccountForm(forms.Form):
    """Record a client payment (manual or M-Pesa) against their account."""

    METHOD_MANUAL = ClientAccountTopup.Method.MANUAL
    METHOD_MPESA = ClientAccountTopup.Method.MPESA

    method = forms.ChoiceField(
        choices=ClientAccountTopup.Method.choices,
        label="Payment method",
        widget=forms.Select(
            attrs={"class": "form-input", "id": "id_client_topup_method"}
        ),
        initial=ClientAccountTopup.Method.MANUAL,
    )
    amount = forms.DecimalField(
        min_value=Decimal("1.00"),
        max_digits=14,
        decimal_places=2,
        label="Amount (KES)",
        widget=forms.NumberInput(
            attrs={
                "class": "form-input",
                "step": "0.01",
                "min": "1",
                "placeholder": "0.00",
                "id": "id_client_topup_amount",
            }
        ),
    )
    phone = forms.CharField(
        required=False,
        label="M-Pesa phone number",
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "07XX XXX XXX",
                "inputmode": "tel",
                "autocomplete": "tel",
                "id": "id_client_topup_phone",
            }
        ),
    )
    note = forms.CharField(
        required=False,
        label="Note",
        widget=forms.Textarea(
            attrs={
                "class": "form-input",
                "rows": 2,
                "placeholder": "Optional note for this payment",
                "id": "id_client_topup_note",
            }
        ),
    )

    def __init__(self, *args, client=None, **kwargs):
        self.client = client
        super().__init__(*args, **kwargs)
        if client and client.phone and not self.is_bound:
            self.fields["phone"].initial = client.phone

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None:
            return amount
        amount = amount.quantize(Decimal("0.01"))
        if amount < 1:
            raise ValidationError("Amount must be at least KES 1.")
        return amount

    def clean_note(self):
        return (self.cleaned_data.get("note") or "").strip()

    def clean_phone(self):
        from .mpesa import MpesaError, normalize_msisdn

        phone = (self.cleaned_data.get("phone") or "").strip()
        if not phone:
            return ""
        try:
            return normalize_msisdn(phone)
        except MpesaError as exc:
            raise ValidationError(str(exc)) from exc

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get("method")
        phone = cleaned.get("phone") or ""
        if method == ClientAccountTopup.Method.MPESA and not phone:
            self.add_error(
                "phone",
                "Enter the Safaricom number that will receive the STK push.",
            )
        return cleaned


class TopupCompanyAccountForm(forms.Form):
    """Add income to a registered company account."""

    account = forms.ModelChoiceField(
        queryset=CompanyExpenseAccount.objects.none(),
        label="Receiving account",
        empty_label="Select receiving account",
        widget=forms.Select(attrs={"class": "form-input", "id": "id_topup_account"}),
        error_messages={"required": "Select the account that will receive the money."},
    )
    amount = forms.DecimalField(
        min_value=Decimal("0.01"),
        max_digits=14,
        decimal_places=2,
        label="Amount (KES)",
        widget=forms.NumberInput(
            attrs={
                "class": "form-input",
                "step": "0.01",
                "min": "0.01",
                "placeholder": "0.00",
                "id": "id_topup_amount",
            }
        ),
        error_messages={"required": "Enter the amount to move."},
    )
    source_type = forms.ChoiceField(
        choices=CompanyAccountTopup.SourceType.choices,
        label="Source of funds",
        widget=forms.Select(
            attrs={"class": "form-input", "id": "id_topup_source_type"}
        ),
        error_messages={"required": "Select where this money is coming from."},
    )
    source_client = forms.ModelChoiceField(
        queryset=Client.objects.none(),
        required=False,
        label="From client",
        empty_label="Select client",
        widget=forms.Select(
            attrs={"class": "form-input", "id": "id_topup_source_client"}
        ),
    )
    source_company_account = forms.ModelChoiceField(
        queryset=CompanyExpenseAccount.objects.none(),
        required=False,
        label="From company account",
        empty_label="Select source account",
        widget=forms.Select(
            attrs={"class": "form-input", "id": "id_topup_source_company_account"}
        ),
    )
    source_note = forms.CharField(
        required=False,
        label="Source note",
        widget=forms.Textarea(
            attrs={
                "class": "form-input",
                "rows": 3,
                "placeholder": "Where this income came from",
                "id": "id_topup_source_note",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        accounts = CompanyExpenseAccount.objects.order_by("name", "id")
        self.fields["account"].queryset = accounts
        self.fields["account"].label_from_instance = (
            lambda obj: f"{obj.name} — {obj.bank_name} (KES {obj.balance:,.2f})"
        )
        self.fields["source_company_account"].queryset = accounts
        self.fields["source_company_account"].label_from_instance = (
            lambda obj: f"{obj.name} — {obj.bank_name} (KES {obj.balance:,.2f})"
        )

        clients = list(
            Client.objects.filter(status=Client.Status.ACTIVE).order_by(
                "company_name", "first_name", "last_name", "email"
            )
        )
        self.fields["source_client"].queryset = Client.objects.filter(
            pk__in=[client.pk for client in clients]
        ).order_by("company_name", "first_name", "last_name", "email")
        self.fields["source_client"].label_from_instance = (
            lambda obj: (
                f"{obj.get_full_name()} "
                f"(credit KES {(obj.credit_balance or Decimal('0.00')):,.2f})"
            )
        )

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None:
            return amount
        amount = amount.quantize(Decimal("0.01"))
        if amount <= 0:
            raise ValidationError("Amount must be greater than zero.")
        return amount

    def clean_source_note(self):
        return (self.cleaned_data.get("source_note") or "").strip()

    def clean(self):
        cleaned = super().clean()
        source_type = cleaned.get("source_type")
        account = cleaned.get("account")
        amount = cleaned.get("amount")
        source_client = cleaned.get("source_client")
        source_company_account = cleaned.get("source_company_account")
        source_note = cleaned.get("source_note") or ""

        if source_type == CompanyAccountTopup.SourceType.CLIENT:
            if not source_client:
                self.add_error("source_client", "Select the client this income came from.")
            elif amount is not None:
                credit = (source_client.credit_balance or Decimal("0.00")).quantize(
                    Decimal("0.01")
                )
                if amount > credit:
                    self.add_error(
                        "amount",
                        f"Client credit is only KES {credit:,.2f}.",
                    )
            cleaned["source_company_account"] = None
            cleaned["source_note"] = ""
        elif source_type == CompanyAccountTopup.SourceType.COMPANY_ACCOUNT:
            if not source_company_account:
                self.add_error(
                    "source_company_account",
                    "Select the company account this income came from.",
                )
            elif account and source_company_account.pk == account.pk:
                self.add_error(
                    "source_company_account",
                    "Source account must be different from the account being topped up.",
                )
            elif amount is not None and source_company_account:
                # Re-read balance in case the cached instance is stale.
                source_balance = (
                    CompanyExpenseAccount.objects.filter(
                        pk=source_company_account.pk
                    )
                    .values_list("balance", flat=True)
                    .first()
                )
                source_balance = (source_balance or Decimal("0.00")).quantize(
                    Decimal("0.01")
                )
                if amount > source_balance:
                    self.add_error(
                        "amount",
                        f"Source account balance is only KES {source_balance:,.2f}.",
                    )
            cleaned["source_client"] = None
            cleaned["source_note"] = ""
        elif source_type == CompanyAccountTopup.SourceType.OTHER:
            if not source_note:
                self.add_error("source_note", "Enter a source note for Others.")
            cleaned["source_client"] = None
            cleaned["source_company_account"] = None
        return cleaned

class PayCompanyExpenseForm(forms.Form):
    """Pay an expense from a company account (debits the account balance)."""

    account = forms.ModelChoiceField(
        queryset=CompanyExpenseAccount.objects.none(),
        label="Pay from account",
        empty_label="Select account",
        widget=forms.Select(
            attrs={"class": "form-input", "id": "id_expense_pay_account"}
        ),
        error_messages={"required": "Select the account to pay from."},
    )
    expense_type = forms.ChoiceField(
        choices=CompanyExpensePayment.ExpenseType.choices,
        label="Expense type",
        widget=forms.Select(
            attrs={"class": "form-input", "id": "id_expense_pay_type"}
        ),
        error_messages={"required": "Select an expense type."},
    )
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.none(),
        required=False,
        label="Employee",
        empty_label="Select employee",
        widget=forms.Select(
            attrs={"class": "form-input", "id": "id_expense_pay_employee"}
        ),
    )
    description = forms.CharField(
        label="Description",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-input",
                "rows": 3,
                "placeholder": "Describe this expense",
                "id": "id_expense_pay_description",
            }
        ),
    )
    amount = forms.DecimalField(
        min_value=Decimal("0.01"),
        max_digits=14,
        decimal_places=2,
        label="Amount (KES)",
        widget=forms.NumberInput(
            attrs={
                "class": "form-input",
                "step": "0.01",
                "min": "0.01",
                "placeholder": "0.00",
                "id": "id_expense_pay_amount",
            }
        ),
        error_messages={"required": "Enter the amount being paid."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        accounts = CompanyExpenseAccount.objects.order_by("name", "id")
        self.fields["account"].queryset = accounts
        self.fields["account"].label_from_instance = (
            lambda obj: f"{obj.name} — {obj.bank_name} (KES {obj.balance:,.2f})"
        )

        employees = list(
            Employee.objects.filter(status=Employee.Status.ACTIVE).order_by(
                "first_name", "last_name", "login_code"
            )
        )
        # Earliest unpaid registered run per employee.
        unpaid_by_employee = {}
        for run in PayrollRun.objects.filter(
            employee_id__in=[e.pk for e in employees],
            status=PayrollRun.Status.REGISTERED,
        ).order_by("pay_period_end", "id"):
            unpaid_by_employee.setdefault(run.employee_id, run)

        self.unpaid_payroll_by_employee = unpaid_by_employee
        self.payroll_net_map = {
            str(emp_id): str(run.net_pay.quantize(Decimal("0.01")))
            for emp_id, run in unpaid_by_employee.items()
        }

        self.fields["employee"].queryset = Employee.objects.filter(
            pk__in=[e.pk for e in employees]
        ).order_by("first_name", "last_name", "login_code")

        def employee_label(obj):
            name = obj.get_full_name() or obj.login_code
            run = unpaid_by_employee.get(obj.pk)
            if run is None:
                return f"{name} — no unpaid payroll"
            return (
                f"{name} — unpaid "
                f"{run.pay_period_start:%d %b}–{run.pay_period_end:%d %b %Y} "
                f"(KES {run.net_pay:,.2f})"
            )

        self.fields["employee"].label_from_instance = employee_label

    def clean_description(self):
        return (self.cleaned_data.get("description") or "").strip()

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None:
            return amount
        amount = amount.quantize(Decimal("0.01"))
        if amount <= 0:
            raise ValidationError("Amount must be greater than zero.")
        return amount

    def clean(self):
        cleaned = super().clean()
        account = cleaned.get("account")
        amount = cleaned.get("amount")
        expense_type = cleaned.get("expense_type")
        employee = cleaned.get("employee")

        if expense_type == CompanyExpensePayment.ExpenseType.PAYROLL:
            if not employee:
                self.add_error("employee", "Select the employee to pay.")
            else:
                run = getattr(self, "unpaid_payroll_by_employee", {}).get(employee.pk)
                if run is None:
                    # Fresh lookup in case form was rebound.
                    run = (
                        PayrollRun.objects.filter(
                            employee=employee,
                            status=PayrollRun.Status.REGISTERED,
                        )
                        .order_by("pay_period_end", "id")
                        .first()
                    )
                if run is None:
                    self.add_error(
                        "employee",
                        "This employee has no unpaid registered payroll. "
                        "Register payroll first.",
                    )
                else:
                    cleaned["payroll_run"] = run
                    if not cleaned.get("description"):
                        cleaned["description"] = (
                            f"Payroll — {employee.get_full_name() or employee.login_code} "
                            f"({run.pay_period_start:%d %b %Y}–"
                            f"{run.pay_period_end:%d %b %Y})"
                        )
        else:
            cleaned["employee"] = None
            cleaned["payroll_run"] = None
            if not cleaned.get("description"):
                self.add_error("description", "Enter a description for this expense.")

        if account is not None and amount is not None:
            balance = (
                CompanyExpenseAccount.objects.filter(pk=account.pk)
                .values_list("balance", flat=True)
                .first()
            )
            balance = (balance or Decimal("0.00")).quantize(Decimal("0.01"))
            if amount > balance:
                self.add_error(
                    "amount",
                    f"Account balance is only KES {balance:,.2f}.",
                )
        return cleaned


class RegisterEmployeeAdvanceForm(forms.ModelForm):
    """Register a salary advance against an eligible registered payroll run."""

    class Meta:
        model = EmployeeAdvance
        fields = ["payroll_run", "amount", "reason"]
        widgets = {
            "payroll_run": forms.Select(
                attrs={"class": "form-input", "id": "id_advance_payroll_run"}
            ),
            "amount": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "id": "id_advance_amount",
                    "min": "0.01",
                    "step": "0.01",
                    "placeholder": "0.00",
                }
            ),
            "reason": forms.Select(
                attrs={"class": "form-input", "id": "id_advance_reason"}
            ),
        }

    def __init__(self, *args, preferred_payroll_run_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        all_registered = (
            PayrollRun.objects.filter(status=PayrollRun.Status.REGISTERED)
            .select_related("employee")
            .prefetch_related("salary_advances")
            .order_by(
                "employee__first_name",
                "employee__last_name",
                "-pay_period_start",
            )
        )
        eligible_ids = [
            run.pk for run in all_registered if run.is_advance_eligible()
        ]
        runs = all_registered.filter(pk__in=eligible_ids)
        self.fields["payroll_run"].queryset = runs
        self.fields["payroll_run"].empty_label = (
            "Select employee"
            if runs.exists()
            else "No eligible employees for advances"
        )
        self.fields["payroll_run"].label = "Registered payroll"
        self.fields["amount"].label = "Advance amount (KES)"
        self.fields["reason"].label = "Reason"
        self.fields["reason"].choices = [
            ("", "Select reason")
        ] + list(EmployeeAdvance.Reason.choices)

        if preferred_payroll_run_id and not self.is_bound:
            preferred = runs.filter(pk=preferred_payroll_run_id).first()
            if preferred is not None:
                self.fields["payroll_run"].initial = preferred.pk
                self.fields["amount"].initial = preferred.max_advance_amount()

        self.payroll_payable_map = {}
        self.payroll_max_advance_map = {}
        self.payroll_salary_map = {}
        for run in runs:
            self.payroll_payable_map[str(run.pk)] = str(run.amount_payable())
            self.payroll_max_advance_map[str(run.pk)] = str(run.max_advance_amount())
            self.payroll_salary_map[str(run.pk)] = str(run.advance_salary_basis())

        def label_from_instance(obj):
            name = obj.employee.get_full_name() or obj.employee.login_code
            amount = obj.max_advance_amount()
            return f"{name} — KES {amount:,.2f}"

        self.fields["payroll_run"].label_from_instance = label_from_instance

    def clean_reason(self):
        reason = (self.cleaned_data.get("reason") or "").strip()
        if not reason:
            raise forms.ValidationError("Select a reason for this advance.")
        return reason

    def clean(self):
        cleaned = super().clean()
        payroll_run = cleaned.get("payroll_run")
        amount = cleaned.get("amount")
        if payroll_run is None or amount is None:
            return cleaned

        if payroll_run.status != PayrollRun.Status.REGISTERED:
            self.add_error(
                "payroll_run",
                "Advances can only be registered against unpaid payroll runs.",
            )
            return cleaned

        if not payroll_run.is_advance_eligible():
            self.add_error(
                "payroll_run",
                "This employee is not eligible for an advance. "
                "Salary must be above half of the remaining payroll amount.",
            )
            return cleaned

        max_advance = payroll_run.max_advance_amount()
        half_salary = payroll_run.half_salary_cap()
        payable = payroll_run.amount_payable()
        if amount <= 0:
            self.add_error("amount", "Enter an advance amount greater than zero.")
        elif amount > max_advance:
            self.add_error(
                "amount",
                f"Advance cannot exceed KES {max_advance:,.2f} "
                f"(half salary KES {half_salary:,.2f}, "
                f"payable KES {payable:,.2f}).",
            )
        return cleaned

    def save(self, commit=True, *, recorded_by=None):
        advance = super().save(commit=False)
        advance.employee = advance.payroll_run.employee
        advance.status = EmployeeAdvance.Status.OUTSTANDING
        advance.notes = ""
        if recorded_by is not None:
            advance.recorded_by = recorded_by
        if commit:
            advance.save()
        return advance


class RegisterPettyCashExpenseForm(forms.ModelForm):
    """Register an employee petty-cash expense (submitted as pending approval)."""

    CLAIM_EXPENSE_TYPES = [
        choice
        for choice in CompanyExpensePayment.ExpenseType.choices
        if choice[0] != CompanyExpensePayment.ExpenseType.PAYROLL
    ]

    class Meta:
        model = PettyCashExpenseRequest
        fields = ["expense_type", "description", "amount"]
        widgets = {
            "expense_type": forms.Select(
                attrs={"class": "form-input", "id": "id_petty_cash_expense_type"}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 3,
                    "placeholder": "Describe this petty cash expense",
                    "id": "id_petty_cash_description",
                }
            ),
            "amount": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "id": "id_petty_cash_amount",
                    "min": "0.01",
                    "step": "0.01",
                    "placeholder": "0.00",
                }
            ),
        }

    def __init__(self, *args, submitted_by=None, **kwargs):
        self.submitted_by = submitted_by
        super().__init__(*args, **kwargs)
        self.fields["expense_type"].choices = [
            ("", "Select expense type")
        ] + list(self.CLAIM_EXPENSE_TYPES)
        self.fields["expense_type"].label = "Expense type"
        self.fields["description"].label = "Description"
        self.fields["amount"].label = "Amount (KES)"

    def clean_expense_type(self):
        expense_type = (self.cleaned_data.get("expense_type") or "").strip()
        if not expense_type:
            raise ValidationError("Select an expense type.")
        if expense_type == CompanyExpensePayment.ExpenseType.PAYROLL:
            raise ValidationError(
                "Payroll is paid from Company Accounts, not petty cash claims."
            )
        return expense_type

    def clean_description(self):
        description = (self.cleaned_data.get("description") or "").strip()
        if not description:
            raise ValidationError("Describe this expense.")
        return description

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None:
            return amount
        amount = amount.quantize(Decimal("0.01"))
        if amount <= 0:
            raise ValidationError("Amount must be greater than zero.")
        return amount

    def clean(self):
        cleaned = super().clean()
        if self.submitted_by is None:
            raise ValidationError("You must be signed in to register an expense.")
        return cleaned

    def save(self, commit=True, *, submitted_by=None):
        request_row = super().save(commit=False)
        actor = submitted_by if submitted_by is not None else self.submitted_by
        if actor is None:
            raise ValidationError("You must be signed in to register an expense.")
        request_row.employee = actor
        request_row.status = PettyCashExpenseRequest.Status.PENDING
        request_row.rejection_reason = ""
        request_row.reviewed_by = None
        request_row.reviewed_at = None
        request_row.expense_payment = None
        request_row.submitted_by = actor
        if commit:
            request_row.save()
        return request_row
