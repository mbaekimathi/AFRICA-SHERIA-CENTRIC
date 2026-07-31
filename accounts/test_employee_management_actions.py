from django.contrib.sessions.models import Session
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Employee, EmployeeWorkSession


class EmployeeManagementActionTests(TestCase):
    def setUp(self):
        self.manager = Employee.objects.create_user(
            login_code="616161",
            password="test-pass-123",
            first_name="Managing",
            last_name="Partner",
            personal_email="manager-actions@example.com",
            personal_phone="+254700000001",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
        )
        self.employee = Employee.objects.create_user(
            login_code="626262",
            password="test-pass-123",
            first_name="Action",
            last_name="Employee",
            personal_email="employee-actions@example.com",
            personal_phone="+254700000002",
            role=Employee.Role.EMPLOYEE,
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.manager)
        self.list_url = self.manager.workspace_url(
            "dashboard",
            "user-management",
            "employee-management",
        )

    def test_list_shows_edit_suspend_and_offboarding_actions(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse(
                "accounts:edit_employee_details",
                kwargs={
                    "role": self.manager.role_slug,
                    "employee_id": self.employee.pk,
                },
            ),
        )
        self.assertContains(
            response,
            reverse(
                "accounts:toggle_employee_suspension",
                kwargs={
                    "role": self.manager.role_slug,
                    "employee_id": self.employee.pk,
                },
            ),
        )
        self.assertContains(
            response,
            f"/offboarding/?employee={self.employee.pk}",
        )

    def test_edit_page_opens_for_active_employee(self):
        response = self.client.get(
            reverse(
                "accounts:edit_employee_details",
                kwargs={
                    "role": self.manager.role_slug,
                    "employee_id": self.employee.pk,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/edit_employee_details.html")
        self.assertContains(response, "Save employee details")

    def test_suspension_action_toggles_employee_status(self):
        url = reverse(
            "accounts:toggle_employee_suspension",
            kwargs={
                "role": self.manager.role_slug,
                "employee_id": self.employee.pk,
            },
        )

        response = self.client.post(url)
        self.assertRedirects(response, self.list_url)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.SUSPENDED)

        self.client.post(url)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.ACTIVE)

    def test_manager_cannot_suspend_own_account(self):
        url = reverse(
            "accounts:toggle_employee_suspension",
            kwargs={
                "role": self.manager.role_slug,
                "employee_id": self.manager.pk,
            },
        )

        self.client.post(url)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.status, Employee.Status.ACTIVE)

    def test_suspension_logs_out_employee_and_blocks_login(self):
        employee_client = Client()
        employee_client.force_login(self.employee)
        session_key = employee_client.session.session_key
        EmployeeWorkSession.objects.create(
            employee=self.employee,
            session_key=session_key or "",
            login_at=self.employee.date_joined,
            last_active_at=self.employee.date_joined,
        )

        url = reverse(
            "accounts:toggle_employee_suspension",
            kwargs={
                "role": self.manager.role_slug,
                "employee_id": self.employee.pk,
            },
        )
        self.client.post(url)

        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.SUSPENDED)
        self.assertFalse(
            EmployeeWorkSession.objects.filter(
                employee=self.employee,
                logout_at__isnull=True,
            ).exists()
        )
        self.assertFalse(Session.objects.filter(session_key=session_key).exists())

        locked = employee_client.get(self.employee.dashboard_url)
        self.assertEqual(locked.status_code, 302)
        self.assertIn(reverse("accounts:login"), locked.url)

        login_response = employee_client.post(
            reverse("accounts:login"),
            {"username": self.employee.login_code, "password": "test-pass-123"},
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertFalse(login_response.wsgi_request.user.is_authenticated)
        self.assertTrue(login_response.context["show_suspended_modal"])
        self.assertContains(login_response, "Your account has been suspended")
        self.assertContains(login_response, "Managing Partner")
        self.assertContains(login_response, 'id="suspended-modal"')
        self.assertContains(login_response, 'data-auto-open="true"')

    def test_login_attempt_by_suspended_employee_shows_popup(self):
        self.employee.status = Employee.Status.SUSPENDED
        self.employee.save(update_fields=["status"])

        fresh_client = Client()
        response = fresh_client.post(
            reverse("accounts:login"),
            {"username": self.employee.login_code, "password": "test-pass-123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertTrue(response.context["show_suspended_modal"])
        self.assertEqual(response.context["suspended_modal_reason"], "login")
        self.assertContains(response, "Sign-in blocked")
        self.assertContains(
            response, "You cannot sign in because your account is currently suspended."
        )
        self.assertContains(response, "Managing Partner")
        self.assertContains(response, 'data-auto-open="true"')

    def test_login_page_without_suspension_has_no_popup(self):
        response = Client().get(reverse("accounts:login"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["show_suspended_modal"])
        self.assertNotContains(response, 'data-auto-open="true"')
