from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone

from .country_codes import (
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
    CourtAttendance,
    CourtAttendanceAdvocate,
    CourtAttendanceBringUpItem,
    Employee,
    EmployeeBlogPost,
    FirmCompanyInformation,
    FirmFAQ,
    FirmPracticeArea,
    LitigationCase,
    MatterAttendance,
    MatterParty,
    MatterTask,
    NonLitigationMatter,
    WebsiteTemplateSetting,
)
from .utils import optimize_image, optimize_profile_photo


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
    identification_number = forms.CharField(
        required=False,
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "National ID number",
            }
        ),
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
            "identification_number",
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
        "identification_number",
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

    def clean_identification_number(self):
        return (self.cleaned_data.get("identification_number") or "").strip().upper()

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
        identification_number = (cleaned.get("identification_number") or "").strip()
        alien_number = (cleaned.get("alien_number") or "").strip()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        country_value = cleaned.get("country_code")
        local_phone = cleaned.get("personal_phone")

        if country_value and local_phone and "personal_phone" not in self.errors:
            _iso, dial = parse_country_value(country_value)
            cleaned["full_personal_phone"] = f"{dial}{local_phone}"

        if id_type == Employee.IdType.CITIZEN:
            if not identification_number:
                self.add_error(
                    "identification_number",
                    "Identification number is required for citizens.",
                )
            cleaned["alien_number"] = ""
        elif id_type == Employee.IdType.NON_CITIZEN:
            if not alien_number:
                self.add_error(
                    "alien_number",
                    "Alien number is required for non-citizens.",
                )
            cleaned["identification_number"] = ""

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
        user.identification_number = self.cleaned_data.get("identification_number", "")
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
        return user


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
    identification_number = forms.CharField(
        required=False,
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "National ID number",
                "id": "id_identification_number",
            }
        ),
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
    alien_number = forms.CharField(
        required=False,
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Alien / permit number",
                "id": "id_alien_number",
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
    business_number = forms.CharField(
        required=False,
        max_length=80,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Business registration number",
                "id": "id_business_number",
            }
        ),
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
    company_registration_number = forms.CharField(
        required=False,
        max_length=80,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Company registration number",
                "id": "id_company_registration_number",
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
            self.fields["identification_number"].initial = (
                client.identification_number or ""
            ).upper()
            self.fields["alien_number"].initial = (client.alien_number or "").upper()
            self.fields["corporate_kind"].initial = (
                client.corporate_kind or Client.CorporateKind.BUSINESS
            )
            self.fields["business_number"].initial = (client.business_number or "").upper()
            self.fields["company_registration_number"].initial = (
                client.company_registration_number or ""
            ).upper()

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

    def clean_identification_number(self):
        return (self.cleaned_data.get("identification_number") or "").strip().upper()

    def clean_alien_number(self):
        return (self.cleaned_data.get("alien_number") or "").strip().upper()

    def clean_business_number(self):
        return (self.cleaned_data.get("business_number") or "").strip().upper()

    def clean_company_registration_number(self):
        return (
            (self.cleaned_data.get("company_registration_number") or "").strip().upper()
        )

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
            cleaned["business_number"] = ""
            cleaned["company_registration_number"] = ""
            id_type = cleaned.get("id_type") or Client.IdType.CITIZEN
            cleaned["id_type"] = id_type
            if id_type == Client.IdType.CITIZEN:
                if not cleaned.get("identification_number"):
                    self.add_error(
                        "identification_number",
                        "Identification number is required.",
                    )
                doc = cleaned.get("identification_document")
                if not doc and not (self.client and self.client.identification_document):
                    self.add_error(
                        "identification_document",
                        "Upload your identification card.",
                    )
                cleaned["alien_number"] = ""
            else:
                if not cleaned.get("alien_number"):
                    self.add_error("alien_number", "Alien number is required.")
                doc = cleaned.get("alien_document")
                if not doc and not (self.client and self.client.alien_document):
                    self.add_error("alien_document", "Upload your alien document.")
                cleaned["identification_number"] = ""
        elif client_type == Client.ClientType.CORPORATE:
            if not cleaned.get("company_name"):
                self.add_error("company_name", "Confirm the business or company name.")
            cleaned["first_name"] = ""
            cleaned["last_name"] = ""
            cleaned["id_type"] = ""
            cleaned["identification_number"] = ""
            cleaned["alien_number"] = ""
            kind = cleaned.get("corporate_kind")
            if not kind:
                self.add_error(
                    "corporate_kind",
                    "Select whether this is a business or a company.",
                )
            elif kind == Client.CorporateKind.BUSINESS:
                cleaned["company_registration_number"] = ""
                if not cleaned.get("business_number"):
                    self.add_error("business_number", "Business number is required.")
                doc = cleaned.get("business_document")
                if not doc and not (self.client and self.client.business_document):
                    self.add_error(
                        "business_document",
                        "Upload the business registration document.",
                    )
            elif kind == Client.CorporateKind.COMPANY:
                cleaned["business_number"] = ""
                if not cleaned.get("company_registration_number"):
                    self.add_error(
                        "company_registration_number",
                        "Company number is required.",
                    )
                doc = cleaned.get("company_registration_document")
                if not doc and not (
                    self.client and self.client.company_registration_document
                ):
                    self.add_error(
                        "company_registration_document",
                        "Upload the company registration document.",
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
        client.identification_number = self.cleaned_data.get(
            "identification_number", ""
        )
        client.alien_number = self.cleaned_data.get("alien_number", "")
        client.corporate_kind = self.cleaned_data.get("corporate_kind", "")
        client.business_number = self.cleaned_data.get("business_number", "")
        client.company_registration_number = self.cleaned_data.get(
            "company_registration_number", ""
        )

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

        if client.client_type == Client.ClientType.CORPORATE:
            client.identification_document = None
            client.alien_document = None
            if client.corporate_kind == Client.CorporateKind.BUSINESS:
                client.company_registration_document = None
            else:
                client.business_document = None
        else:
            client.corporate_kind = ""
            client.business_document = None
            client.company_registration_document = None
            if client.id_type == Client.IdType.CITIZEN:
                client.alien_document = None
            else:
                client.identification_document = None

        client.status = Client.Status.PENDING_APPROVAL
        if commit:
            client.save()
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
        if commit:
            employee.save()
        return employee


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
            "description",
            "next_action",
            "next_activity_type",
            "next_court_date",
            "next_judicial_officer",
            "next_client_attendance",
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
            "description": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 4,
                    "placeholder": "Enter detailed outcome information...",
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
            "next_client_attendance": forms.Select(attrs={"class": "form-input"}),
        }
        labels = {
            "activity_type": "Activity Type",
            "judicial_officer": "Judicial Officer",
            "court_room": "Court Room",
            "attendance_date": "Date of Court Attendance",
            "presence": "Court Attendance",
            "court_directions": "Court Directions",
            "description": "Description",
            "next_action": "Next Action",
            "next_activity_type": "Next Activity Type",
            "next_court_date": "Next Court Date",
            "next_judicial_officer": "Next Judicial Officer",
            "next_client_attendance": "Next Client Attendance",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["activity_type"].required = True
        self.fields["judicial_officer"].required = True
        self.fields["attendance_date"].required = True
        self.fields["presence"].required = True
        self.fields["court_room"].required = False
        self.fields["court_directions"].required = False
        self.fields["description"].required = False
        self.fields["next_action"].required = False
        self.fields["next_activity_type"].required = False
        self.fields["next_court_date"].required = False
        self.fields["next_judicial_officer"].required = False
        self.fields["next_client_attendance"].required = False
        self.fields["next_client_attendance"].choices = [
            ("", "Select attendance..."),
            *CourtAttendance.ClientAttendance.choices,
        ]
        if not self.is_bound and not self.initial.get("attendance_date"):
            self.initial["attendance_date"] = timezone.localdate()
            self.initial.setdefault("presence", CourtAttendance.Presence.PRESENT)


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
        self.fields["allocated_to"].empty_label = "Search employee..."

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
            "attendance_date",
            "description",
            "next_action",
            "next_activity_type",
            "next_attendance_date",
            "next_client_attendance",
            "bring_update",
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
            "attendance_date": forms.DateInput(
                attrs={
                    "class": "form-input",
                    "type": "date",
                    "autocomplete": "off",
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
            "next_client_attendance": forms.Select(attrs={"class": "form-input"}),
            "bring_update": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 4,
                    "placeholder": "Enter bring-up / update notes...",
                }
            ),
        }
        labels = {
            "activity_type": "Activity Type",
            "attendance_date": "Date of Attendance",
            "description": "Description",
            "next_action": "Next Action",
            "next_activity_type": "Next Activity Type",
            "next_attendance_date": "Next Attendance Date",
            "next_client_attendance": "Next Client Attendance",
            "bring_update": "Bring Update",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["activity_type"].required = True
        self.fields["attendance_date"].required = True
        self.fields["description"].required = False
        self.fields["next_action"].required = False
        self.fields["next_activity_type"].required = False
        self.fields["next_attendance_date"].required = False
        self.fields["next_client_attendance"].required = False
        self.fields["bring_update"].required = False
        self.fields["next_client_attendance"].choices = [
            ("", "Select attendance..."),
            *MatterAttendance.ClientAttendance.choices,
        ]
        if not self.is_bound and not self.initial.get("attendance_date"):
            self.initial["attendance_date"] = timezone.localdate()


class CreateCaseTaskForm(forms.Form):
    """Create a follow-up case task for the locked litigation case."""

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = Employee.objects.filter(
            status=Employee.Status.ACTIVE
        ).order_by("first_name", "last_name", "login_code")
        self.fields["assigned_to"].help_text = (
            "Select the employee who will receive and work on this case task."
        )


class CreateMatterTaskForm(forms.Form):
    """Create a follow-up matter task for the locked non-litigation matter."""

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = Employee.objects.filter(
            status=Employee.Status.ACTIVE
        ).order_by("first_name", "last_name", "login_code")
        self.fields["assigned_to"].help_text = (
            "Select the employee who will receive and work on this matter task."
        )


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
    Personal theme, font, and density for the signed-in employee only.

    Saves to that employee's row — never a firm-wide or system default.
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
        # `product` is an alias of `default` — keep a single recommended choice in the UI.
        self.fields["ui_theme"].choices = [
            (key, label)
            for key, label in Employee.UiTheme.choices
            if key != Employee.UiTheme.PRODUCT
        ]
        self.fields["ui_font"].choices = list(Employee.UiFont.choices)
        self.fields["ui_density"].choices = list(Employee.UiDensity.choices)
        if self.instance and (self.instance.ui_theme or "") == Employee.UiTheme.PRODUCT:
            self.initial["ui_theme"] = Employee.UiTheme.DEFAULT

    def clean_ui_theme(self):
        value = self.cleaned_data.get("ui_theme") or Employee.UiTheme.DEFAULT
        if value == Employee.UiTheme.PRODUCT:
            return Employee.UiTheme.DEFAULT
        return value

    def save(self, commit=True):
        """Persist appearance only on this employee instance."""
        employee = super().save(commit=False)
        if commit:
            employee.save(update_fields=["ui_theme", "ui_font", "ui_density"])
        return employee


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


class CompanyInformationForm(forms.ModelForm):
    """Firm-wide company profile under System Settings."""

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


class CompanyContactsForm(forms.ModelForm):
    """Firm contact and address details for the website."""

    class Meta:
        model = FirmCompanyInformation
        fields = [
            "email",
            "phone",
            "website",
            "physical_address",
            "postal_address",
            "city",
            "country",
        ]
        labels = {
            "email": "Primary email",
            "phone": "Primary phone",
            "website": "Website",
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


FIRM_CORE_VALUE_CHOICES = (
    ("Integrity", "Integrity"),
    ("Client-Centered Service", "Client-Centered Service"),
    ("Accessibility", "Accessibility"),
    ("Excellence", "Excellence"),
    ("Confidentiality", "Confidentiality"),
    ("Innovation", "Innovation"),
    ("Diligence", "Diligence"),
)


class MultipleFileInput(forms.ClearableFileInput):
    """File input that accepts multiple files (Django 5+)."""

    allow_multiple_selected = True


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

    images = forms.FileField(
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


class CreateGoogleDocumentForm(forms.Form):
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


class UploadDocumentForm(forms.Form):
    """Upload a file, name it, and link it to the current case or matter."""

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


class RenameDocumentForm(forms.Form):
    """Edit document name, description, and notes (and rename on Drive)."""

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

    def clean_title(self):
        title = (self.cleaned_data.get("title") or "").strip()
        if not title:
            raise ValidationError("Enter a document name.")
        return title

    def clean_description(self):
        return (self.cleaned_data.get("description") or "").strip()

    def clean_notes(self):
        return (self.cleaned_data.get("notes") or "").strip()

