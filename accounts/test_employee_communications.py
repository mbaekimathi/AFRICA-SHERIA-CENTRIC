import shutil
import tempfile
from unittest.mock import MagicMock, patch

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from accounts.models import (
    Client,
    CommunicationSettings,
    Employee,
    EmployeeActivityPermission,
    EmployeeCommunication,
    EmployeeCommunicationAttachment,
    WhatsAppConversation,
    WhatsAppMessage,
)


class EmployeeCommunicationsPagesTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp(prefix="comm-test-media-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)

    def setUp(self):
        self.user = Employee.objects.create_user(
            login_code="828282",
            password="test-pass-123",
            first_name="Mary",
            last_name="Partner",
            personal_email="mary.partner@example.com",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
            work_email="mary.partner@sheriacentric.com",
            work_phone="+254712000111",
        )
        self.colleague = Employee.objects.create_user(
            login_code="838383",
            password="test-pass-123",
            first_name="Peter",
            last_name="Associate",
            personal_email="peter.associate@example.com",
            role=Employee.Role.ADVOCATE,
            status=Employee.Status.ACTIVE,
            work_email="peter.associate@sheriacentric.com",
            work_phone="+254712000222",
        )
        self.firm_client = Client.objects.create(
            email="client@example.com",
            first_name="Sam",
            last_name="Client",
            phone="+254700111222",
            status=Client.Status.ACTIVE,
            password="x",
        )
        self.http = self.client
        self.http.force_login(self.user)
        self.hub_trail = (
            "dashboard",
            "user-management",
            "employee-management",
            "employee-communications",
        )

    def channel_url(self, slug, *extra):
        return self.user.workspace_url(*self.hub_trail, slug, *extra)

    def test_hub_links_to_the_three_channel_pages(self):
        response = self.http.get(self.user.workspace_url(*self.hub_trail))
        self.assertEqual(response.status_code, 200)
        for slug in (
            "email-communications",
            "whatsapp-communications",
            "sms-communications",
            "email-settings",
        ):
            self.assertContains(response, f"{slug}/")

    def test_email_channel_lists_employees_with_counts(self):
        EmployeeCommunication.objects.create(
            sender=self.colleague,
            channel=EmployeeCommunication.Channel.EMAIL,
            from_identity=self.colleague.work_email,
            to_client=self.firm_client,
            to_address=self.firm_client.email,
            subject="Hearing date",
            body="The hearing moved to Friday.",
        )
        response = self.http.get(self.channel_url("email-communications"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Peter Associate")
        self.assertContains(
            response, self.channel_url("email-communications", str(self.colleague.pk))
        )
        self.assertContains(response, "View emails")
        self.assertContains(response, "Email settings")
        self.assertNotContains(
            response,
            f'id="id_work_email_{self.colleague.pk}"',
            html=False,
        )

    def test_email_settings_lists_employees_for_work_email_editing(self):
        response = self.http.get(self.channel_url("email-settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Peter Associate")
        self.assertContains(response, "Mary Partner")
        self.assertContains(response, "Employee work emails")
        self.assertContains(
            response,
            f'id="id_work_email_{self.colleague.pk}"',
            html=False,
        )
        self.assertNotContains(response, "not commissioned yet")

    def test_manager_can_change_employee_work_email_from_email_settings(self):
        self.colleague.work_email_password_encrypted = "saved-mailbox-credential"
        self.colleague.save(update_fields=["work_email_password_encrypted"])
        update_url = (
            self.channel_url("email-settings", str(self.colleague.pk))
            + "work-email/"
        )

        response = self.http.post(
            update_url,
            {
                "work_email": "new.address@sheriacentric.com",
                "return_to": "email-settings",
            },
        )

        self.assertRedirects(
            response,
            self.channel_url("email-settings"),
            fetch_redirect_response=False,
        )
        self.colleague.refresh_from_db()
        self.assertEqual(
            self.colleague.work_email, "new.address@sheriacentric.com"
        )
        self.assertEqual(self.colleague.work_email_password_encrypted, "")

    def test_manager_can_send_work_email_password_reset_link(self):
        setting = CommunicationSettings.get_solo()
        setting.work_email_provisioning_enabled = True
        setting.cpanel_host = "server.example.com"
        setting.cpanel_username = "sheria"
        setting.cpanel_api_token = "token"
        setting.work_email_domain = "sheriacentric.com"
        setting.email_enabled = True
        setting.email_host = "mail.example.com"
        setting.email_port = 465
        setting.email_from_email = "noreply@example.com"
        setting.save()
        update_url = (
            self.channel_url("email-settings", str(self.colleague.pk))
            + "work-email/"
        )

        with (
            patch("accounts.views.change_mailbox_password") as change_password,
            patch(
                "accounts.work_email_notify.send_firm_email",
                return_value="noreply@example.com",
            ) as send_mail,
        ):
            response = self.http.post(
                update_url,
                {
                    "action": "reset_password",
                    "return_to": "email-settings",
                },
                follow=True,
            )

        change_password.assert_not_called()
        send_mail.assert_called_once()
        self.assertEqual(
            send_mail.call_args.kwargs["to_email"],
            self.colleague.personal_email,
        )
        self.assertIn("reset", send_mail.call_args.kwargs["subject"].lower())
        self.assertIn("/work-email/set-password/", send_mail.call_args.kwargs["body"])
        self.assertNotIn("Temporary password", send_mail.call_args.kwargs["body"])
        self.assertContains(response, "password reset link")
        self.assertContains(response, self.colleague.personal_email)

    def test_work_email_change_rejects_an_address_used_by_another_employee(self):
        update_url = (
            self.channel_url("email-settings", str(self.colleague.pk))
            + "work-email/"
        )

        response = self.http.post(
            update_url,
            {
                "work_email": self.user.work_email.upper(),
                "return_to": "email-settings",
            },
            follow=True,
        )

        self.assertContains(
            response,
            "That work email is already linked to an employee account.",
        )
        self.colleague.refresh_from_db()
        self.assertEqual(
            self.colleague.work_email, "peter.associate@sheriacentric.com"
        )

    def test_manager_can_generate_allocate_and_notify_when_email_is_missing(self):
        self.colleague.work_email = None
        self.colleague.save(update_fields=["work_email"])
        setting = CommunicationSettings.get_solo()
        setting.work_email_provisioning_enabled = True
        setting.cpanel_host = "server.example.com"
        setting.cpanel_username = "sheria"
        setting.cpanel_api_token = "token"
        setting.work_email_domain = "sheriacentric.com"
        setting.save()
        update_url = (
            self.channel_url("email-settings", str(self.colleague.pk))
            + "work-email/"
        )

        with (
            patch(
                "accounts.views.find_reusable_mailbox",
                return_value="",
            ),
            patch(
                "accounts.views.provision_work_email",
                return_value=("peter.associate@sheriacentric.com", "one-time-pass"),
            ) as provision,
            patch(
                "accounts.work_email_notify.send_firm_email",
                return_value="noreply@sheriacentric.com",
            ) as send_mail,
        ):
            response = self.http.post(
                update_url,
                {"action": "generate", "return_to": "email-settings"},
                follow=True,
            )

        self.colleague.refresh_from_db()
        self.assertEqual(
            self.colleague.work_email, "peter.associate@sheriacentric.com"
        )
        provision.assert_called_once()
        send_mail.assert_called_once()
        self.assertEqual(
            send_mail.call_args.kwargs["to_email"],
            self.colleague.personal_email,
        )
        self.assertIn("one-time-pass", send_mail.call_args.kwargs["body"])
        self.assertContains(response, "Login instructions were sent")

    def test_generate_asks_before_reusing_an_existing_cpanel_mailbox(self):
        self.colleague.work_email = None
        self.colleague.save(update_fields=["work_email"])
        setting = CommunicationSettings.get_solo()
        setting.work_email_provisioning_enabled = True
        setting.cpanel_host = "server.example.com"
        setting.cpanel_username = "sheria"
        setting.cpanel_api_token = "token"
        setting.work_email_domain = "sheriacentric.com"
        setting.save()
        update_url = (
            self.channel_url("email-settings", str(self.colleague.pk))
            + "work-email/"
        )

        with (
            patch(
                "accounts.views.find_reusable_mailbox",
                return_value="peter.associate@sheriacentric.com",
            ),
            patch("accounts.views.provision_work_email") as provision,
            patch("accounts.views.adopt_existing_mailbox") as adopt,
        ):
            response = self.http.post(
                update_url,
                {"action": "generate", "return_to": "email-settings"},
                follow=True,
            )

        provision.assert_not_called()
        adopt.assert_not_called()
        self.colleague.refresh_from_db()
        self.assertFalse(self.colleague.work_email)
        self.assertContains(response, "Existing mailbox found")
        self.assertContains(response, "peter.associate@sheriacentric.com")
        self.assertContains(response, "Use existing")

    def test_manager_can_adopt_existing_mailbox_after_confirming(self):
        self.colleague.work_email = None
        self.colleague.save(update_fields=["work_email"])
        setting = CommunicationSettings.get_solo()
        setting.work_email_provisioning_enabled = True
        setting.cpanel_host = "server.example.com"
        setting.cpanel_username = "sheria"
        setting.cpanel_api_token = "token"
        setting.work_email_domain = "sheriacentric.com"
        setting.save()
        update_url = (
            self.channel_url("email-settings", str(self.colleague.pk))
            + "work-email/"
        )
        session = self.http.session
        session["work_email_reuse_candidate"] = {
            "employee_id": self.colleague.pk,
            "email": "peter.associate@sheriacentric.com",
            "name": "Peter Associate",
        }
        session.save()

        with (
            patch(
                "accounts.views.adopt_existing_mailbox",
                return_value=("peter.associate@sheriacentric.com", "rotated-pass"),
            ) as adopt,
            patch(
                "accounts.work_email_notify.send_firm_email",
                return_value="noreply@sheriacentric.com",
            ) as send_mail,
        ):
            response = self.http.post(
                update_url,
                {"action": "adopt_existing", "return_to": "email-settings"},
                follow=True,
            )

        adopt.assert_called_once()
        send_mail.assert_called_once()
        self.assertIn("allocated to you", send_mail.call_args.kwargs["body"])
        self.colleague.refresh_from_db()
        self.assertEqual(
            self.colleague.work_email, "peter.associate@sheriacentric.com"
        )
        self.assertContains(response, "Allocated existing")
        self.assertContains(response, "Login instructions were sent")

    def test_generate_explains_smtp_is_not_enough_when_cpanel_is_missing(self):
        self.colleague.work_email = None
        self.colleague.save(update_fields=["work_email"])
        setting = CommunicationSettings.get_solo()
        setting.email_enabled = True
        setting.email_host = "mail.example.com"
        setting.email_port = 465
        setting.email_from_email = "noreply@example.com"
        setting.work_email_provisioning_enabled = False
        setting.save()
        update_url = (
            self.channel_url("email-settings", str(self.colleague.pk))
            + "work-email/"
        )

        with patch("accounts.views.provision_work_email") as provision:
            response = self.http.post(
                update_url,
                {"action": "generate", "return_to": "email-settings"},
                follow=True,
            )

        provision.assert_not_called()
        self.colleague.refresh_from_db()
        self.assertFalse(self.colleague.work_email)
        self.assertContains(response, "Work emails (cPanel)")
        self.assertContains(response, "only sends mail")

    def test_email_settings_offers_setup_when_provisioning_is_incomplete(self):
        self.colleague.work_email = None
        self.colleague.save(update_fields=["work_email"])
        setting = CommunicationSettings.get_solo()
        setting.email_enabled = True
        setting.email_host = "mail.example.com"
        setting.email_from_email = "noreply@example.com"
        setting.work_email_provisioning_enabled = False
        setting.save()

        response = self.http.get(self.channel_url("email-settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Work email creation is not ready")
        self.assertContains(response, "Set up creation")
        self.assertContains(response, "#communication-work-email-panel")
        self.assertNotContains(
            response,
            'name="action"\n                      value="generate"',
            html=False,
        )
        self.assertNotContains(response, 'value="generate"')

    def test_log_and_detail_show_the_full_message(self):
        record = EmployeeCommunication.objects.create(
            sender=self.colleague,
            channel=EmployeeCommunication.Channel.EMAIL,
            from_identity=self.colleague.work_email,
            to_employee=self.user,
            to_address=self.user.work_email,
            subject="Weekly report",
            body="Attached is the weekly matter report.",
        )
        log_url = self.channel_url("email-communications", str(self.colleague.pk))
        log = self.http.get(log_url)
        self.assertEqual(log.status_code, 200)
        self.assertContains(log, "Weekly report")
        self.assertContains(log, "Sent")
        self.assertContains(log, "Employee")

        received_log = self.http.get(
            self.channel_url("email-communications", str(self.user.pk))
        )
        self.assertEqual(received_log.status_code, 200)
        self.assertContains(received_log, "Weekly report")
        self.assertContains(received_log, "Received")
        self.assertContains(received_log, "Peter Associate")

        detail = self.http.get(f"{log_url}{record.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Attached is the weekly matter report.")
        self.assertContains(detail, self.colleague.work_email)

    def test_detail_lists_attachments_with_view_and_download_links(self):
        record = EmployeeCommunication.objects.create(
            sender=self.colleague,
            channel=EmployeeCommunication.Channel.EMAIL,
            from_identity=self.colleague.work_email,
            to_client=self.firm_client,
            to_address=self.firm_client.email,
            subject="Contract",
            body="Signed contract attached.",
        )
        attachment = EmployeeCommunicationAttachment.objects.create(
            communication=record,
            filename="contract.pdf",
            content_type="application/pdf",
            size=4,
            file=ContentFile(b"%PDF", name="contract.pdf"),
        )
        log_url = self.channel_url("email-communications", str(self.colleague.pk))
        detail = self.http.get(f"{log_url}{record.pk}/")

        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "1 attachment")
        self.assertContains(detail, "contract.pdf")
        file_url = f"{log_url}{record.pk}/attachments/{attachment.pk}/"
        self.assertContains(detail, file_url)
        self.assertContains(detail, f"{file_url}?download=1")

    def test_attachment_view_and_download_endpoints(self):
        record = EmployeeCommunication.objects.create(
            sender=self.colleague,
            channel=EmployeeCommunication.Channel.EMAIL,
            from_identity=self.colleague.work_email,
            to_client=self.firm_client,
            to_address=self.firm_client.email,
            subject="Contract",
            body="Signed contract attached.",
        )
        attachment = EmployeeCommunicationAttachment.objects.create(
            communication=record,
            filename="contract.pdf",
            content_type="application/pdf",
            size=4,
            file=ContentFile(b"%PDF", name="contract.pdf"),
        )
        file_url = (
            f"{self.channel_url('email-communications', str(self.colleague.pk))}"
            f"{record.pk}/attachments/{attachment.pk}/"
        )

        inline = self.http.get(file_url)
        self.assertEqual(inline.status_code, 200)
        self.assertEqual(inline["Content-Type"], "application/pdf")
        self.assertTrue(inline["Content-Disposition"].startswith("inline"))
        self.assertIn('filename="contract.pdf"', inline["Content-Disposition"])
        self.assertEqual(b"".join(inline.streaming_content), b"%PDF")

        download = self.http.get(f"{file_url}?download=1")
        self.assertEqual(download.status_code, 200)
        self.assertTrue(download["Content-Disposition"].startswith("attachment"))

    def test_attachment_of_another_employees_message_is_not_found(self):
        record = EmployeeCommunication.objects.create(
            sender=self.colleague,
            channel=EmployeeCommunication.Channel.EMAIL,
            from_identity=self.colleague.work_email,
            to_client=self.firm_client,
            to_address=self.firm_client.email,
            subject="Contract",
            body="Signed contract attached.",
        )
        attachment = EmployeeCommunicationAttachment.objects.create(
            communication=record,
            filename="contract.pdf",
            content_type="application/pdf",
            size=4,
            file=ContentFile(b"%PDF", name="contract.pdf"),
        )
        other_log_url = self.channel_url("email-communications", str(self.user.pk))
        response = self.http.get(
            f"{other_log_url}{record.pk}/attachments/{attachment.pk}/"
        )
        self.assertEqual(response.status_code, 404)

    def test_log_only_shows_that_employees_messages(self):
        mine = EmployeeCommunication.objects.create(
            sender=self.user,
            channel=EmployeeCommunication.Channel.SMS,
            to_client=self.firm_client,
            to_address=self.firm_client.phone,
            body="Court at 9am.",
        )
        response = self.http.get(
            f"{self.channel_url('sms-communications', str(self.colleague.pk))}{mine.pk}/"
        )
        self.assertEqual(response.status_code, 404)

    def test_sms_log_excludes_email_records(self):
        EmployeeCommunication.objects.create(
            sender=self.colleague,
            channel=EmployeeCommunication.Channel.EMAIL,
            to_client=self.firm_client,
            to_address=self.firm_client.email,
            subject="Only an email",
            body="Body",
        )
        response = self.http.get(
            self.channel_url("sms-communications", str(self.colleague.pk))
        )
        self.assertNotContains(response, "Only an email")

    def test_whatsapp_log_reads_the_conversation_store(self):
        conversation = WhatsAppConversation.objects.create(
            msisdn="254700111222",
            client=self.firm_client,
            display_name="Sam Client",
        )
        message = WhatsAppMessage.objects.create(
            conversation=conversation,
            direction=WhatsAppMessage.Direction.OUTBOUND,
            body="Documents received, thank you.",
            status=WhatsAppMessage.Status.SENT,
            sent_by=self.colleague,
        )
        log_url = self.channel_url("whatsapp-communications", str(self.colleague.pk))
        log = self.http.get(log_url)
        self.assertContains(log, "Documents received")

        detail = self.http.get(f"{log_url}{message.pk}/")
        self.assertContains(detail, "Documents received, thank you.")

    def test_detail_shows_reply_form_for_email(self):
        record = EmployeeCommunication.objects.create(
            sender=self.colleague,
            channel=EmployeeCommunication.Channel.EMAIL,
            from_identity=self.colleague.work_email,
            to_client=self.firm_client,
            to_address=self.firm_client.email,
            subject="Contract",
            body="Signed contract attached.",
        )
        detail = self.http.get(
            f"{self.channel_url('email-communications', str(self.colleague.pk))}"
            f"{record.pk}/"
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Send reply")
        self.assertContains(detail, "Re: Contract")
        self.assertContains(detail, self.firm_client.email)

    def test_whatsapp_detail_hides_the_reply_form(self):
        conversation = WhatsAppConversation.objects.create(
            msisdn="254700111222",
            client=self.firm_client,
            display_name="Sam Client",
        )
        message = WhatsAppMessage.objects.create(
            conversation=conversation,
            direction=WhatsAppMessage.Direction.OUTBOUND,
            body="Documents received, thank you.",
            status=WhatsAppMessage.Status.SENT,
            sent_by=self.colleague,
        )
        detail = self.http.get(
            f"{self.channel_url('whatsapp-communications', str(self.colleague.pk))}"
            f"{message.pk}/"
        )
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, "Send reply")

    @patch("accounts.work_mailbox.WorkMailbox")
    def test_reply_sends_and_logs_a_new_record(self, mailbox_cls):
        mailbox = MagicMock()
        mailbox.address = self.user.work_email
        mailbox_cls.return_value = mailbox
        record = EmployeeCommunication.objects.create(
            sender=self.colleague,
            channel=EmployeeCommunication.Channel.EMAIL,
            from_identity=self.colleague.work_email,
            to_client=self.firm_client,
            to_address=self.firm_client.email,
            subject="Contract",
            body="Signed contract attached.",
        )
        detail_url = (
            f"{self.channel_url('email-communications', str(self.colleague.pk))}"
            f"{record.pk}/"
        )

        response = self.http.post(
            detail_url,
            {"subject": "Re: Contract", "body": "Thanks, received."},
        )

        self.assertRedirects(response, detail_url, fetch_redirect_response=False)
        mailbox.send_message.assert_called_once()
        self.assertEqual(
            mailbox.send_message.call_args.kwargs["to_addrs"],
            [self.firm_client.email],
        )
        reply = EmployeeCommunication.objects.get(sender=self.user)
        self.assertEqual(reply.channel, EmployeeCommunication.Channel.EMAIL)
        self.assertEqual(reply.to_client, self.firm_client)
        self.assertIsNone(reply.to_employee)
        self.assertEqual(reply.to_address, self.firm_client.email)
        self.assertEqual(reply.subject, "Re: Contract")
        self.assertEqual(reply.body, "Thanks, received.")

    @patch("accounts.work_mailbox.WorkMailbox")
    def test_reply_to_a_received_email_goes_to_its_sender(self, mailbox_cls):
        sender_emp = Employee.objects.create_user(
            login_code="868686",
            password="test-pass-123",
            first_name="Amina",
            last_name="Clerk",
            personal_email="amina.clerk@example.com",
            role=Employee.Role.ADVOCATE,
            status=Employee.Status.ACTIVE,
            work_email="amina.clerk@sheriacentric.com",
        )
        mailbox = MagicMock()
        mailbox.address = self.user.work_email
        mailbox_cls.return_value = mailbox
        record = EmployeeCommunication.objects.create(
            sender=sender_emp,
            channel=EmployeeCommunication.Channel.EMAIL,
            from_identity=sender_emp.work_email,
            to_employee=self.colleague,
            to_address=self.colleague.work_email,
            subject="Intake question",
            body="When is the filing?",
        )
        detail_url = (
            f"{self.channel_url('email-communications', str(self.colleague.pk))}"
            f"{record.pk}/"
        )

        detail = self.http.get(detail_url)
        self.assertContains(detail, sender_emp.work_email)

        response = self.http.post(detail_url, {"body": "Friday morning."})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            mailbox.send_message.call_args.kwargs["to_addrs"],
            [sender_emp.work_email],
        )
        reply = EmployeeCommunication.objects.get(sender=self.user)
        self.assertEqual(reply.to_employee, sender_emp)
        self.assertEqual(reply.subject, "Re: Intake question")

    @patch("accounts.work_mailbox.WorkMailbox")
    def test_reply_requires_a_body(self, mailbox_cls):
        record = EmployeeCommunication.objects.create(
            sender=self.colleague,
            channel=EmployeeCommunication.Channel.EMAIL,
            from_identity=self.colleague.work_email,
            to_client=self.firm_client,
            to_address=self.firm_client.email,
            subject="Contract",
            body="Signed contract attached.",
        )
        detail_url = (
            f"{self.channel_url('email-communications', str(self.colleague.pk))}"
            f"{record.pk}/"
        )

        response = self.http.post(detail_url, {"subject": "Re: Contract", "body": ""})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Write a reply before sending.")
        mailbox_cls.return_value.send_message.assert_not_called()
        self.assertFalse(
            EmployeeCommunication.objects.filter(sender=self.user).exists()
        )

    @patch("accounts.work_mailbox.WorkMailbox")
    def test_reply_is_locked_without_the_communicate_action(self, mailbox_cls):
        EmployeeActivityPermission.objects.create(
            employee=self.user,
            module_slug="user-management",
            activity_slug="email-communications",
            action="communicate",
            is_allowed=False,
        )
        record = EmployeeCommunication.objects.create(
            sender=self.colleague,
            channel=EmployeeCommunication.Channel.EMAIL,
            from_identity=self.colleague.work_email,
            to_client=self.firm_client,
            to_address=self.firm_client.email,
            subject="Contract",
            body="Signed contract attached.",
        )
        detail_url = (
            f"{self.channel_url('email-communications', str(self.colleague.pk))}"
            f"{record.pk}/"
        )

        detail = self.http.get(detail_url)
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, "Send reply")

        response = self.http.post(detail_url, {"body": "Thanks, received."})
        self.assertEqual(response.status_code, 302)
        mailbox_cls.return_value.send_message.assert_not_called()
        self.assertFalse(
            EmployeeCommunication.objects.filter(sender=self.user).exists()
        )

    def test_unknown_channel_is_not_found(self):
        response = self.http.get(
            self.channel_url("fax-communications", str(self.colleague.pk))
        )
        self.assertEqual(response.status_code, 404)


class MessageLoggingTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp(prefix="comm-log-test-media-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)

    def setUp(self):
        self.user = Employee.objects.create_user(
            login_code="848484",
            password="test-pass-123",
            first_name="Jane",
            last_name="Advocate",
            personal_email="jane.advocate@example.com",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
            work_email="jane.advocate@sheriacentric.com",
            work_phone="+254712345678",
        )
        self.colleague = Employee.objects.create_user(
            login_code="858585",
            password="test-pass-123",
            first_name="Peter",
            last_name="Associate",
            personal_email="peter.associate@example.com",
            role=Employee.Role.ADVOCATE,
            status=Employee.Status.ACTIVE,
            work_email="peter.associate@sheriacentric.com",
        )
        self.firm_client = Client.objects.create(
            email="client@example.com",
            first_name="Sam",
            last_name="Client",
            phone="+254700111222",
            status=Client.Status.ACTIVE,
            password="x",
        )
        self.http = self.client
        self.http.force_login(self.user)
        self.url = self.user.workspace_url("dashboard", "messages")

        setting = CommunicationSettings.get_solo()
        setting.email_enabled = True
        setting.email_host = "mail.sheriacentric.com"
        setting.email_port = 465
        setting.email_host_user = "noreply@sheriacentric.com"
        setting.email_host_password = "smtp-secret"
        setting.email_from_email = "noreply@sheriacentric.com"
        setting.email_use_ssl = True
        setting.email_use_tls = False
        setting.save()
        self.user.set_work_mailbox_password("mailbox-secret")

    @patch("accounts.work_mailbox.WorkMailbox")
    def test_client_email_is_logged(self, mailbox_cls):
        mailbox = MagicMock()
        mailbox.address = self.user.work_email
        mailbox_cls.return_value = mailbox

        response = self.http.post(
            self.url,
            {
                "action": "send_email",
                "recipient": f"client:{self.firm_client.pk}",
                "subject": "Case update",
                "body": "Please call the office.",
            },
        )
        self.assertEqual(response.status_code, 302)
        mailbox.send_message.assert_called_once()
        self.assertEqual(
            mailbox.send_message.call_args.kwargs["to_addrs"],
            [self.firm_client.email],
        )
        record = EmployeeCommunication.objects.get(sender=self.user)
        self.assertEqual(record.channel, EmployeeCommunication.Channel.EMAIL)
        self.assertEqual(record.to_client, self.firm_client)
        self.assertIsNone(record.to_employee)
        self.assertEqual(record.to_address, self.firm_client.email)
        self.assertEqual(record.status, EmployeeCommunication.Status.SENT)

    @patch("accounts.work_mailbox.WorkMailbox")
    def test_colleague_email_is_logged(self, mailbox_cls):
        mailbox = MagicMock()
        mailbox.address = self.user.work_email
        mailbox_cls.return_value = mailbox

        response = self.http.post(
            self.url,
            {
                "action": "send_email",
                "recipient": f"employee:{self.colleague.pk}",
                "subject": "Weekly report",
                "body": "Please send it today.",
            },
        )
        self.assertEqual(response.status_code, 302)
        mailbox.send_message.assert_called_once()
        self.assertEqual(
            mailbox.send_message.call_args.kwargs["to_addrs"],
            [self.colleague.work_email],
        )
        record = EmployeeCommunication.objects.get(sender=self.user)
        self.assertEqual(record.to_employee, self.colleague)
        self.assertIsNone(record.to_client)
        self.assertEqual(record.to_address, self.colleague.work_email)

    @patch("accounts.work_mailbox.WorkMailbox")
    def test_sent_email_attachments_are_stored_on_the_log_record(
        self, mailbox_cls
    ):
        mailbox = MagicMock()
        mailbox.address = self.user.work_email
        mailbox_cls.return_value = mailbox

        response = self.http.post(
            self.url,
            {
                "action": "send_email",
                "recipient": f"client:{self.firm_client.pk}",
                "subject": "Contract",
                "body": "Signed contract attached.",
                "attachments": SimpleUploadedFile(
                    "contract.pdf",
                    b"%PDF-bytes",
                    content_type="application/pdf",
                ),
            },
        )
        self.assertEqual(response.status_code, 302)
        record = EmployeeCommunication.objects.get(sender=self.user)
        attachment = record.attachments.get()
        self.assertEqual(attachment.filename, "contract.pdf")
        self.assertEqual(attachment.content_type, "application/pdf")
        self.assertEqual(attachment.size, len(b"%PDF-bytes"))
        with attachment.file.open("rb") as handle:
            self.assertEqual(handle.read(), b"%PDF-bytes")

    def test_sending_to_yourself_is_rejected(self):
        response = self.http.post(
            self.url,
            {
                "action": "send_email",
                "recipient": f"employee:{self.user.pk}",
                "subject": "Note",
                "body": "Hello",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(EmployeeCommunication.objects.exists())
