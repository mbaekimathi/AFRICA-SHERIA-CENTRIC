from django.test import TestCase

from accounts.models import Employee


class RegisterEmployeePageTests(TestCase):
    def setUp(self):
        self.user = Employee.objects.create_user(
            login_code="606060",
            password="test-pass-123",
            first_name="Register",
            last_name="Partner",
            personal_email="register.partner@example.com",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.user)
        self.url = self.user.workspace_url(
            "dashboard",
            "user-management",
            "employee-management",
            "register-employee",
        )

    def test_page_renders_the_sectioned_register_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/register_employee.html")
        self.assertContains(response, "page--register-employee")
        self.assertContains(response, 'class="register-form"')
        self.assertContains(response, "register-grid--2")

    def test_page_keeps_the_hooks_auth_js_depends_on(self):
        response = self.client.get(self.url)
        for hook in (
            'id="signup-form"',
            'id="phone-field"',
            'id="country-trigger"',
            'id="country-menu"',
            'id="country-list"',
            'id="id-country-field"',
            'id="id-country-trigger"',
            'id="id-country-menu"',
            'id="alien-id-field"',
            'id="country-codes-data"',
            'id="login-code-status"',
            'id="password-match-status"',
            'id="photo-preview"',
            'id="photo-preview-img"',
            'id="signup-submit"',
            'data-target="id_password1"',
            'data-target="id_password2"',
        ):
            with self.subTest(hook=hook):
                self.assertContains(response, hook)
