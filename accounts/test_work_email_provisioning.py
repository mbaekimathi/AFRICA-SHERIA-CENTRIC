from unittest.mock import patch

from django.core import signing
from django.test import TestCase, RequestFactory
from django.urls import reverse

from accounts.cpanel_mail import (
    CpanelMailError,
    base_local_part,
    suggest_work_email,
)
from accounts.models import CommunicationSettings, Employee
from accounts.outbound_messaging import OutboundMessageError
from accounts.work_email_notify import (
    SET_PASSWORD_SALT,
    make_set_password_token,
    notify_work_email_created,
)


class SuggestWorkEmailTests(TestCase):
    def test_defaults_to_first_dot_second_name(self):
        self.assertEqual(
            suggest_work_email("John", "Doe", "sheriacentric.com"),
            "john.doe@sheriacentric.com",
        )

    def test_strips_accents_spaces_and_punctuation(self):
        self.assertEqual(base_local_part("Renée", "O'Brien-Smith"), "renee.obriensmith")

    def test_adds_a_suffix_when_the_address_is_taken(self):
        taken = {"john.doe@sheriacentric.com", "john.doe2@sheriacentric.com"}
        self.assertEqual(
            suggest_work_email("John", "Doe", "sheriacentric.com", taken=taken),
            "john.doe3@sheriacentric.com",
        )

    def test_rejects_an_employee_without_a_usable_name(self):
        with self.assertRaises(CpanelMailError):
            suggest_work_email("", "", "sheriacentric.com")


class ApproveEmployeeWorkEmailTests(TestCase):
    def setUp(self):
        self.partner = Employee.objects.create_user(
            login_code="707070",
            password="test-pass-123",
            first_name="Approving",
            last_name="Partner",
            personal_email="approving.partner@example.com",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
        )
        self.candidate = Employee.objects.create_user(
            login_code="707071",
            password="test-pass-123",
            first_name="John",
            last_name="Doe",
            personal_email="john.doe@example.com",
            role=Employee.Role.EMPLOYEE,
            status=Employee.Status.PENDING_APPROVAL,
        )
        self.client.force_login(self.partner)
        self.url = reverse(
            "accounts:approve_employee",
            kwargs={
                "role": self.partner.role_slug,
                "employee_id": self.candidate.pk,
            },
        )

        setting = CommunicationSettings.get_solo()
        setting.work_email_provisioning_enabled = True
        setting.cpanel_host = "server.example.com"
        setting.cpanel_username = "sheria"
        setting.cpanel_api_token = "token"
        setting.work_email_domain = "sheriacentric.com"
        setting.email_enabled = True
        setting.email_host = "mail.example.com"
        setting.email_port = 587
        setting.email_host_user = "noreply@sheriacentric.com"
        setting.email_host_password = "smtp-secret"
        setting.email_from_email = "noreply@sheriacentric.com"
        setting.email_from_name = "Sheria Centric"
        setting.save()

    def test_approval_saves_the_provisioned_mailbox(self):
        with (
            patch(
                "accounts.views.provision_work_email",
                return_value=("john.doe@sheriacentric.com", "s3cret-pass"),
            ),
            patch(
                "accounts.work_email_notify.send_firm_email",
                return_value="noreply@sheriacentric.com",
            ) as send_mail,
        ):
            response = self.client.post(
                self.url, {"action": "approve", "role": Employee.Role.EMPLOYEE}
            )

        self.assertEqual(response.status_code, 302)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Employee.Status.ACTIVE)
        self.assertEqual(self.candidate.work_email, "john.doe@sheriacentric.com")
        send_mail.assert_called_once()
        kwargs = send_mail.call_args.kwargs
        self.assertEqual(kwargs["to_email"], "john.doe@example.com")
        self.assertIn("john.doe@sheriacentric.com", kwargs["body"])
        self.assertIn("s3cret-pass", kwargs["body"])
        self.assertIn("/work-email/set-password/", kwargs["body"])

        page = self.client.get(response["Location"])
        self.assertContains(page, "john.doe@sheriacentric.com")
        self.assertContains(page, "s3cret-pass")
        self.assertContains(page, "john.doe@example.com")

    def test_credentials_are_only_shown_once(self):
        with (
            patch(
                "accounts.views.provision_work_email",
                return_value=("john.doe@sheriacentric.com", "s3cret-pass"),
            ),
            patch(
                "accounts.work_email_notify.send_firm_email",
                return_value="noreply@sheriacentric.com",
            ),
        ):
            response = self.client.post(
                self.url, {"action": "approve", "role": Employee.Role.EMPLOYEE}
            )

        list_url = response["Location"]
        self.client.get(list_url)
        self.assertNotContains(self.client.get(list_url), "s3cret-pass")

    def test_approval_continues_when_credential_email_fails(self):
        with (
            patch(
                "accounts.views.provision_work_email",
                return_value=("john.doe@sheriacentric.com", "s3cret-pass"),
            ),
            patch(
                "accounts.work_email_notify.send_firm_email",
                side_effect=OutboundMessageError("SMTP down"),
            ),
        ):
            response = self.client.post(
                self.url, {"action": "approve", "role": Employee.Role.EMPLOYEE}
            )

        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Employee.Status.ACTIVE)
        page = self.client.get(response["Location"])
        self.assertContains(page, "Could not email")
        self.assertContains(page, "SMTP down")

    def test_failure_leaves_the_employee_pending_and_offers_a_choice(self):
        with patch(
            "accounts.views.provision_work_email",
            side_effect=CpanelMailError("cPanel rejected the API token."),
        ):
            response = self.client.post(
                self.url, {"action": "approve", "role": Employee.Role.EMPLOYEE}
            )

        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Employee.Status.PENDING_APPROVAL)
        self.assertFalse(self.candidate.work_email)

        page = self.client.get(response["Location"])
        self.assertContains(page, "work-email-failure-modal")
        self.assertContains(page, "cPanel rejected the API token.")
        self.assertContains(page, "approve_without_work_email")

    def test_confirming_after_a_failure_activates_without_a_work_email(self):
        with patch(
            "accounts.views.provision_work_email",
            side_effect=CpanelMailError("cPanel rejected the API token."),
        ):
            self.client.post(
                self.url, {"action": "approve", "role": Employee.Role.EMPLOYEE}
            )

        with patch("accounts.views.provision_work_email") as never_called:
            self.client.post(
                self.url,
                {
                    "action": "approve_without_work_email",
                    "role": Employee.Role.EMPLOYEE,
                },
            )
            never_called.assert_not_called()

        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Employee.Status.ACTIVE)
        self.assertFalse(self.candidate.work_email)

    def test_approval_still_works_when_provisioning_is_not_configured(self):
        setting = CommunicationSettings.get_solo()
        setting.work_email_provisioning_enabled = False
        setting.save()

        with patch("accounts.views.provision_work_email") as never_called:
            self.client.post(
                self.url, {"action": "approve", "role": Employee.Role.EMPLOYEE}
            )
            never_called.assert_not_called()

        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, Employee.Status.ACTIVE)


class SetWorkEmailPasswordTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create_user(
            login_code="808080",
            password="test-pass-123",
            first_name="Jane",
            last_name="Advocate",
            personal_email="jane.advocate@example.com",
            role=Employee.Role.EMPLOYEE,
            status=Employee.Status.ACTIVE,
            work_email="jane.advocate@sheriacentric.com",
        )
        setting = CommunicationSettings.get_solo()
        setting.work_email_provisioning_enabled = True
        setting.cpanel_host = "server.example.com"
        setting.cpanel_username = "sheria"
        setting.cpanel_api_token = "token"
        setting.work_email_domain = "sheriacentric.com"
        setting.save()
        self.token = make_set_password_token(
            employee_id=self.employee.pk,
            work_email=self.employee.work_email,
        )
        self.url = reverse(
            "accounts:set_work_email_password",
            kwargs={"token": self.token},
        )

    def test_get_shows_the_set_password_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "jane.advocate@sheriacentric.com")
        self.assertContains(response, "New password")
        self.assertContains(response, "At least 6 characters or digits.")
        self.assertContains(response, "js-password-toggle", count=2)

    def test_accepts_a_six_character_password(self):
        with patch("accounts.views.change_mailbox_password") as change_password:
            response = self.client.post(
                self.url,
                {"password1": "abc123", "password2": "abc123"},
            )

        self.assertContains(response, "password was updated")
        self.assertEqual(change_password.call_args.args[2], "abc123")

    def test_rejects_a_password_shorter_than_six(self):
        with patch("accounts.views.change_mailbox_password") as change_password:
            response = self.client.post(
                self.url,
                {"password1": "abc12", "password2": "abc12"},
            )

        self.assertContains(response, "at least 6 characters or digits")
        change_password.assert_not_called()

    def test_post_updates_the_mailbox_password(self):
        with patch(
            "accounts.views.change_mailbox_password"
        ) as change_password:
            response = self.client.post(
                self.url,
                {
                    "password1": "NewSecurePass1!",
                    "password2": "NewSecurePass1!",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "password was updated")
        change_password.assert_called_once()
        args = change_password.call_args.args
        self.assertEqual(args[1], "jane.advocate@sheriacentric.com")
        self.assertEqual(args[2], "NewSecurePass1!")

    def test_rejects_mismatched_passwords(self):
        with patch("accounts.views.change_mailbox_password") as change_password:
            response = self.client.post(
                self.url,
                {
                    "password1": "NewSecurePass1!",
                    "password2": "DifferentPass1!",
                },
            )

        self.assertContains(response, "do not match")
        change_password.assert_not_called()

    def test_rejects_an_invalid_token(self):
        url = reverse(
            "accounts:set_work_email_password",
            kwargs={"token": "not-a-valid-token"},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "invalid", status_code=400)

    def test_notify_builds_absolute_set_password_link(self):
        request = RequestFactory().get("/")
        request.META["HTTP_HOST"] = "testserver"
        with patch(
            "accounts.work_email_notify.send_firm_email",
            return_value="noreply@sheriacentric.com",
        ) as send_mail:
            result = notify_work_email_created(
                request,
                self.employee,
                work_email="jane.advocate@sheriacentric.com",
                password="TempPass1!",
            )

        self.assertTrue(result["email_sent"])
        body = send_mail.call_args.kwargs["body"]
        self.assertIn("http://testserver/work-email/set-password/", body)
        token = (
            body.split("/work-email/set-password/")[1]
            .splitlines()[0]
            .strip()
            .rstrip("/")
        )
        payload = signing.loads(token, salt=SET_PASSWORD_SALT)
        self.assertEqual(payload["e"], self.employee.pk)
        self.assertEqual(payload["m"], "jane.advocate@sheriacentric.com")
