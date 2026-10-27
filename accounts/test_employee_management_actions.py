from unittest.mock import patch

from django.contrib.sessions.models import Session
from django.test import Client, TestCase
from django.urls import reverse

from django.utils import timezone

from accounts.cpanel_mail import CpanelMailError
from accounts.models import (
    CaseTask,
    Client as FirmClient,
    CommunicationSettings,
    Employee,
    EmployeeWorkSession,
    LitigationCase,
)
from accounts.workspace import set_employee_activity_permission


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
            work_email="action.employee@sheriacentric.com",
            work_email_password_encrypted="saved-mailbox-credential",
        )
        setting = CommunicationSettings.get_solo()
        setting.cpanel_host = "server.example.com"
        setting.cpanel_username = "sheria"
        setting.cpanel_api_token = "token"
        setting.work_email_domain = "sheriacentric.com"
        setting.email_enabled = True
        setting.email_host = "mail.example.com"
        setting.email_port = 465
        setting.email_from_email = "noreply@example.com"
        setting.save()
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

        with (
            patch("accounts.views.suspend_mailbox") as suspend,
            patch("accounts.views.unsuspend_mailbox") as unsuspend,
            patch(
                "accounts.work_email_notify.send_firm_email",
                return_value="noreply@example.com",
            ),
        ):
            response = self.client.post(url)
            self.assertRedirects(response, self.list_url)
            self.employee.refresh_from_db()
            self.assertEqual(self.employee.status, Employee.Status.SUSPENDED)
            suspend.assert_called_once()

            self.client.post(url)
            self.employee.refresh_from_db()
            self.assertEqual(self.employee.status, Employee.Status.ACTIVE)
            unsuspend.assert_called_once()

    def test_suspension_suspends_work_email_and_notifies_personal_inbox(self):
        url = reverse(
            "accounts:toggle_employee_suspension",
            kwargs={
                "role": self.manager.role_slug,
                "employee_id": self.employee.pk,
            },
        )

        with (
            patch("accounts.views.suspend_mailbox") as suspend,
            patch(
                "accounts.work_email_notify.send_firm_email",
                return_value="noreply@example.com",
            ) as send_mail,
        ):
            response = self.client.post(url, follow=True)

        suspend.assert_called_once()
        self.assertEqual(
            suspend.call_args.args[1],
            "action.employee@sheriacentric.com",
        )
        send_mail.assert_called_once()
        self.assertEqual(
            send_mail.call_args.kwargs["to_email"],
            self.employee.personal_email,
        )
        self.assertIn("suspended", send_mail.call_args.kwargs["subject"].lower())
        self.assertIn(
            "action.employee@sheriacentric.com",
            send_mail.call_args.kwargs["body"],
        )
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.SUSPENDED)
        self.assertEqual(self.employee.work_email_password_encrypted, "")
        self.assertContains(response, "Work email")
        self.assertContains(response, "notice was sent")

    def test_suspension_still_succeeds_when_mailbox_api_fails(self):
        url = reverse(
            "accounts:toggle_employee_suspension",
            kwargs={
                "role": self.manager.role_slug,
                "employee_id": self.employee.pk,
            },
        )

        with (
            patch(
                "accounts.views.suspend_mailbox",
                side_effect=CpanelMailError("cPanel unavailable"),
            ),
            patch(
                "accounts.work_email_notify.send_firm_email",
                return_value="noreply@example.com",
            ) as send_mail,
        ):
            response = self.client.post(url, follow=True)

        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.SUSPENDED)
        send_mail.assert_called_once()
        self.assertContains(response, "could not be suspended")
        self.assertContains(response, "notice was sent")

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
        with (
            patch("accounts.views.suspend_mailbox"),
            patch(
                "accounts.work_email_notify.send_firm_email",
                return_value="noreply@example.com",
            ),
        ):
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

    def _offboarding_url(self, employee=None):
        url = self.manager.workspace_url(
            "dashboard",
            "user-management",
            "employee-management",
            "offboarding",
        )
        if employee is not None:
            url = f"{url}?employee={employee.pk}"
        return url

    def _offboard_post_url(self, employee):
        return reverse(
            "accounts:offboard_employee",
            kwargs={
                "role": self.manager.role_slug,
                "employee_id": employee.pk,
            },
        )

    def test_offboarding_page_shows_what_will_change(self):
        response = self.client.get(self._offboarding_url(self.employee))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/offboarding.html")
        self.assertContains(
            response, "What changes when this employee is offboarded"
        )
        self.assertContains(response, "Active → Suspended")
        self.assertContains(response, "action.employee@sheriacentric.com")
        self.assertContains(response, self._offboard_post_url(self.employee))

    def test_offboarding_page_rejects_unmanaged_employee(self):
        pending = Employee.objects.create_user(
            login_code="636363",
            password="test-pass-123",
            first_name="Pending",
            last_name="Employee",
            personal_email="pending-offboard@example.com",
            personal_phone="+254700000003",
            role=Employee.Role.EMPLOYEE,
            status=Employee.Status.PENDING_APPROVAL,
        )

        response = self.client.get(self._offboarding_url(pending))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "That employee is not available for offboarding."
        )
        self.assertIsNone(response.context["selected_employee"])

    def test_offboard_suspends_releases_work_and_notifies(self):
        client_person = FirmClient.objects.create(
            email="offboard.client@example.com",
            first_name="Offboard",
            last_name="Client",
            status=FirmClient.Status.ACTIVE,
        )
        case = LitigationCase.objects.create(
            filing_date=timezone.localdate(),
            client=client_person,
            court_rank="high_court",
            case_category="civil",
            case_type="suit",
            station="nairobi",
            status=LitigationCase.Status.ACTIVE,
            assigned_to=self.employee,
        )
        task = CaseTask.objects.create(
            case=case,
            assignee=self.employee,
            title="Handover brief",
            created_by=self.manager,
            status=CaseTask.Status.ACCEPTED,
        )
        employee_client = Client()
        employee_client.force_login(self.employee)
        session_key = employee_client.session.session_key
        EmployeeWorkSession.objects.create(
            employee=self.employee,
            session_key=session_key or "",
            login_at=self.employee.date_joined,
            last_active_at=self.employee.date_joined,
        )

        with (
            patch("accounts.views.suspend_mailbox") as suspend,
            patch(
                "accounts.work_email_notify.send_firm_email",
                return_value="noreply@example.com",
            ) as send_mail,
        ):
            response = self.client.post(
                self._offboard_post_url(self.employee), {"confirm": "yes"}
            )

        self.assertRedirects(response, self.list_url)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.SUSPENDED)
        self.assertEqual(self.employee.work_email_password_encrypted, "")
        case.refresh_from_db()
        self.assertIsNone(case.assigned_to_id)
        task.refresh_from_db()
        self.assertEqual(task.status, CaseTask.Status.CANCELLED)
        suspend.assert_called_once()
        send_mail.assert_called_once()
        self.assertFalse(
            EmployeeWorkSession.objects.filter(
                employee=self.employee, logout_at__isnull=True
            ).exists()
        )
        self.assertFalse(Session.objects.filter(session_key=session_key).exists())

    def test_offboard_requires_confirmation(self):
        response = self.client.post(self._offboard_post_url(self.employee))

        self.assertRedirects(response, self._offboarding_url(self.employee))
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.ACTIVE)

    def test_offboard_blocks_own_account(self):
        response = self.client.post(
            self._offboard_post_url(self.manager), {"confirm": "yes"}
        )

        self.assertRedirects(response, self._offboarding_url(self.manager))
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.status, Employee.Status.ACTIVE)

    def test_offboard_blocked_without_edit_permission(self):
        set_employee_activity_permission(
            employee_id=self.manager.pk,
            module_slug="user-management",
            activity_slug="offboarding",
            action="edit",
            is_allowed=False,
            updated_by=self.manager,
        )

        self.client.post(
            self._offboard_post_url(self.employee), {"confirm": "yes"}
        )

        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, Employee.Status.ACTIVE)

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
