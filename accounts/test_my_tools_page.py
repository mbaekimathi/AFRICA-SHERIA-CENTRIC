from django.test import TestCase

from accounts.models import (
    CompanyDigitalSignatureSetting,
    Employee,
    EmployeeDigitalStampSetting,
)


class MyToolsPageTests(TestCase):
    def setUp(self):
        self.user = Employee.objects.create_user(
            login_code="555555",
            password="test-pass-123",
            first_name="Tools",
            last_name="Partner",
            personal_email="tools.partner@example.com",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.user)
        self.url = self.user.workspace_url("dashboard", "my-tools")

    def test_page_prompts_setup_when_no_tools_saved(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/my_tools.html")
        self.assertContains(response, "No stamp saved yet")
        self.assertContains(response, "No signature saved yet")
        self.assertNotContains(response, "module-card")

    def test_page_renders_the_saved_tools(self):
        EmployeeDigitalStampSetting.objects.create(
            employee=self.user,
            template=EmployeeDigitalStampSetting.Template.OVAL,
            accent=EmployeeDigitalStampSetting.Accent.TEAL,
        )
        CompanyDigitalSignatureSetting.objects.create(
            pk=1,
            template=CompanyDigitalSignatureSetting.Template.SCRIPT,
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "doc-stamp--oval")
        self.assertContains(response, "doc-signature--script")
        self.assertContains(response, "Tools Partner")
        self.assertNotContains(response, "No stamp saved yet")
