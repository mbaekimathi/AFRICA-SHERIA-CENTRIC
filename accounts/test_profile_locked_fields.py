from django.test import TestCase

from accounts.models import Employee


class ProfileLockedFieldTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create_user(
            login_code="737373",
            password="test-pass-123",
            first_name="Locked",
            last_name="Profile",
            personal_email="locked-profile@example.com",
            personal_phone="+254700000003",
            work_email="locked.profile@firm.example.com",
            role=Employee.Role.EMPLOYEE,
            status=Employee.Status.ACTIVE,
            id_type=Employee.IdType.CITIZEN,
            identification_number="12345678",
            id_country="KE",
            payment_method=Employee.PaymentMethod.CASH,
        )
        self.client.force_login(self.employee)
        self.settings_url = self.employee.workspace_url("dashboard", "settings")

    def test_settings_page_renders_locked_details_as_read_only(self):
        response = self.client.get(self.settings_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/settings.html")
        self.assertContains(response, "Firm-managed")
        self.assertNotContains(response, 'name="first_name"')
        self.assertNotContains(response, 'name="personal_email"')
        self.assertNotContains(response, 'name="work_email"')
        self.assertNotContains(response, 'name="profile_photo"')
        self.assertNotContains(response, 'name="employment_contract"')

    def test_posted_locked_fields_are_ignored(self):
        response = self.client.post(
            self.settings_url,
            {
                "settings_action": "profile",
                "first_name": "Tampered",
                "last_name": "Tampered",
                "personal_email": "tampered@example.com",
                "work_email": "tampered@firm.example.com",
                "personal_phone": "+254700000009",
                "id_type": Employee.IdType.CITIZEN,
                "id_country": "KE",
                "identification_number": "12345678",
                "payment_method": Employee.PaymentMethod.CASH,
                "about_me": "Updated bio",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.first_name, "Locked")
        self.assertEqual(self.employee.last_name, "Profile")
        self.assertEqual(self.employee.personal_email, "locked-profile@example.com")
        self.assertEqual(self.employee.work_email, "locked.profile@firm.example.com")
        self.assertEqual(self.employee.personal_phone, "+254700000009")
        self.assertEqual(self.employee.about_me, "Updated bio")
