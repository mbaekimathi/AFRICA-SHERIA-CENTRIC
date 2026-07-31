from urllib.parse import urlparse

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Employee


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="security@sheria.test",
)
class EmployeePasswordResetTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create_user(
            login_code="484848",
            password="OLDPASS",
            first_name="Reset",
            last_name="Employee",
            personal_email="reset.employee@example.com",
            personal_phone="+254700000048",
            role=Employee.Role.EMPLOYEE,
            status=Employee.Status.ACTIVE,
            id_type=Employee.IdType.CITIZEN,
            identification_number="48484848",
            id_country="KE",
        )

    def test_login_page_has_forgot_password_link(self):
        response = self.client.get(reverse("accounts:login"))

        self.assertContains(response, "Forgot password?")
        self.assertContains(response, reverse("accounts:password_reset"))

    def test_reset_email_is_sent_to_personal_email(self):
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": "RESET.EMPLOYEE@EXAMPLE.COM"},
        )

        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.employee.personal_email])
        self.assertIn("/employee/password-reset/", mail.outbox[0].body)

    def test_unknown_email_shows_same_result_without_sending(self):
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": "unknown@example.com"},
        )

        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(mail.outbox, [])

    def test_reset_link_changes_password(self):
        self.client.post(
            reverse("accounts:password_reset"),
            {"email": self.employee.personal_email},
        )
        reset_url = next(
            line.strip()
            for line in mail.outbox[0].body.splitlines()
            if "/employee/password-reset/" in line
        )
        reset_path = urlparse(reset_url).path

        response = self.client.get(reset_path, follow=True)
        self.assertEqual(response.status_code, 200)
        confirm_path = response.request["PATH_INFO"]
        response = self.client.post(
            confirm_path,
            {
                "new_password1": "newpass",
                "new_password2": "newpass",
            },
        )

        self.assertRedirects(response, reverse("accounts:password_reset_complete"))
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.check_password("NEWPASS"))
