"""Only the address that is genuinely on file may be refused at sign-up."""

from django.test import TestCase
from django.urls import reverse

from accounts.forms import (
    ClientSignUpForm,
    SignUpForm,
    normalize_email,
    stored_email_match,
)
from accounts.models import Client, Employee


def employee_signup_data(**overrides):
    data = {
        "courtesy_title": Employee.CourtesyTitle.MR,
        "first_name": "New",
        "last_name": "Starter",
        "personal_email": "new.starter@gmail.com",
        "country_code": "KE|+254",
        "personal_phone": "712345678",
        "id_type": Employee.IdType.CITIZEN,
        "id_country": "KE",
        "alien_number": "",
        "login_code": "778899",
        "password1": "STARTERPASS9",
        "password2": "STARTERPASS9",
    }
    data.update(overrides)
    return data


class CollationHits:
    """A queryset stub standing in for a collation that equates two addresses."""

    def __init__(self, rows):
        self.rows = rows

    def filter(self, **_lookup):
        return self.rows


def client_signup_data(**overrides):
    data = {
        "client_type": Client.ClientType.INDIVIDUAL,
        "first_name": "New",
        "last_name": "Client",
        "company_name": "",
        "email": "new.client@gmail.com",
        "country_code": "KE|+254",
        "phone": "712345678",
        "password1": "CLIENTPASS9",
        "password2": "CLIENTPASS9",
    }
    data.update(overrides)
    return data


class StoredEmailMatchTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create_user(
            login_code="200001",
            password="EXISTINGPASS9",
            first_name="Ada",
            last_name="Lovelace",
            personal_email="ada.lovelace@gmail.com",
            personal_phone="+254700000001",
        )

    def match(self, value):
        return stored_email_match(
            Employee.objects.all(), "personal_email", value
        )[0]

    def test_the_same_address_is_taken(self):
        self.assertEqual(self.match("ada.lovelace@gmail.com"), "taken")

    def test_case_and_spacing_are_the_same_address(self):
        self.assertEqual(self.match("  Ada.Lovelace@GMAIL.com  "), "taken")

    def test_a_different_address_is_free(self):
        for value in (
            "adalovelace@gmail.com",
            "ada-lovelace@gmail.com",
            "ada.lovelace@googlemail.com",
            "ada.lovelace2@gmail.com",
        ):
            with self.subTest(value=value):
                self.assertEqual(self.match(value), "")

    def test_an_address_the_database_cannot_tell_apart_is_reported_separately(self):
        # The collation returns a row whose address is not the one typed. The
        # unique index would still refuse the insert, so it is not free either.
        match, owner = stored_email_match(
            CollationHits([self.employee]), "personal_email", "adá.lovelace@gmail.com"
        )
        self.assertEqual(match, "lookalike")
        self.assertEqual(owner, self.employee)

    def test_a_blank_address_is_free(self):
        self.assertEqual(self.match("   "), "")

    def test_normalize_email_trims_and_lowercases(self):
        self.assertEqual(normalize_email("  Ada@GMAIL.com "), "ada@gmail.com")


class EmployeeSignUpEmailTests(TestCase):
    def setUp(self):
        self.active = Employee.objects.create_user(
            login_code="200002",
            password="EXISTINGPASS9",
            first_name="Ada",
            last_name="Lovelace",
            personal_email="ada.lovelace@gmail.com",
            personal_phone="+254700000002",
            status=Employee.Status.ACTIVE,
        )

    def test_an_unused_address_passes(self):
        form = SignUpForm(data=employee_signup_data())
        self.assertNotIn("personal_email", form.errors)

    def test_a_near_miss_of_a_stored_address_passes(self):
        form = SignUpForm(
            data=employee_signup_data(personal_email="adalovelace@gmail.com")
        )
        self.assertNotIn("personal_email", form.errors)

    def test_the_stored_address_is_refused(self):
        form = SignUpForm(
            data=employee_signup_data(personal_email="Ada.Lovelace@Gmail.com")
        )
        self.assertEqual(
            form.errors["personal_email"],
            ["An account with this email already exists."],
        )

    def test_a_sign_up_still_awaiting_approval_says_so(self):
        Employee.objects.create_user(
            login_code="200003",
            password="EXISTINGPASS9",
            first_name="Grace",
            last_name="Hopper",
            personal_email="grace.hopper@gmail.com",
            personal_phone="+254700000003",
            status=Employee.Status.PENDING_APPROVAL,
        )
        form = SignUpForm(
            data=employee_signup_data(personal_email="grace.hopper@gmail.com")
        )
        self.assertEqual(
            form.errors["personal_email"],
            [
                "This email was already used to sign up, and that account is "
                "still waiting to be approved."
            ],
        )

    def test_an_address_the_database_cannot_store_is_explained(self):
        form = SignUpForm(
            data=employee_signup_data(personal_email="ada.lovelace@gmäil.com")
        )
        self.assertIn("does not tell it apart", form.errors["personal_email"][0])


class ClientSignUpEmailTests(TestCase):
    def setUp(self):
        Client.objects.create(
            email="mekatilili@gmail.com",
            client_type=Client.ClientType.INDIVIDUAL,
            first_name="Meka",
            last_name="Tilili",
            phone="+254700000004",
        )

    def test_an_unused_address_passes(self):
        form = ClientSignUpForm(data=client_signup_data())
        self.assertNotIn("email", form.errors)

    def test_a_near_miss_of_a_stored_address_passes(self):
        form = ClientSignUpForm(data=client_signup_data(email="mekatilili2@gmail.com"))
        self.assertNotIn("email", form.errors)

    def test_the_stored_address_is_refused(self):
        form = ClientSignUpForm(data=client_signup_data(email="Mekatilili@Gmail.com"))
        self.assertEqual(
            form.errors["email"], ["An account with this email already exists."]
        )

    def test_an_address_the_database_cannot_store_is_explained(self):
        # Corporate, because individual clients are held to a domain allow-list.
        form = ClientSignUpForm(
            data=client_signup_data(
                client_type=Client.ClientType.CORPORATE,
                company_name="Mekatilili Ltd",
                first_name="",
                last_name="",
                email="mekatilili@gmäil.com",
            )
        )
        self.assertIn("does not tell it apart", form.errors["email"][0])


class DeclinePendingEmployeeTests(TestCase):
    """Declining a sign-up releases the address it was holding."""

    def setUp(self):
        self.partner = Employee.objects.create_user(
            login_code="300001",
            password="PARTNERPASS9",
            first_name="Approving",
            last_name="Partner",
            personal_email="approving.partner@gmail.com",
            personal_phone="+254700000010",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
        )
        self.candidate = Employee.objects.create_user(
            login_code="300002",
            password="CANDIDATEPASS9",
            first_name="Abandoned",
            last_name="Signup",
            personal_email="abandoned.signup@gmail.com",
            personal_phone="+254700000011",
            status=Employee.Status.PENDING_ONBOARDING,
        )
        self.client.force_login(self.partner)

    def decline_url(self, employee):
        return reverse(
            "accounts:decline_pending_employee",
            kwargs={
                "role": self.partner.role_slug,
                "employee_id": employee.pk,
            },
        )

    def test_the_pending_list_offers_the_decline_action(self):
        page = self.client.get(
            self.partner.workspace_url(
                "dashboard",
                "user-management",
                "employee-management",
                "onboarding-approvals",
            )
        )
        self.assertContains(page, self.decline_url(self.candidate))

    def test_declining_deletes_the_sign_up_and_frees_the_address(self):
        response = self.client.post(self.decline_url(self.candidate))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Employee.objects.filter(pk=self.candidate.pk).exists())

        form = SignUpForm(
            data=employee_signup_data(personal_email="abandoned.signup@gmail.com")
        )
        self.assertNotIn("personal_email", form.errors)

    def test_an_active_employee_cannot_be_declined(self):
        self.candidate.status = Employee.Status.ACTIVE
        self.candidate.save(update_fields=["status"])

        self.client.post(self.decline_url(self.candidate))

        self.assertTrue(Employee.objects.filter(pk=self.candidate.pk).exists())

    def test_you_cannot_decline_your_own_account(self):
        self.partner.status = Employee.Status.PENDING_APPROVAL
        self.partner.save(update_fields=["status"])

        self.client.post(self.decline_url(self.partner))

        self.assertTrue(Employee.objects.filter(pk=self.partner.pk).exists())
