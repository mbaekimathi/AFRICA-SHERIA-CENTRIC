from unittest.mock import MagicMock, patch

from django.test import TestCase

from accounts.models import (
    Client,
    CommunicationSettings,
    Employee,
    EmployeeCommunication,
    WhatsAppConversation,
    WhatsAppMessage,
)


class EmployeeCommunicationsPagesTests(TestCase):
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
        self.assertContains(
            response,
            f'id="id_work_email_{self.colleague.pk}"',
            html=False,
        )

    def test_manager_can_change_employee_work_email_from_email_channel(self):
        self.colleague.work_email_password_encrypted = "saved-mailbox-credential"
        self.colleague.save(update_fields=["work_email_password_encrypted"])
        update_url = (
            self.channel_url("email-communications", str(self.colleague.pk))
            + "work-email/"
        )

        response = self.http.post(
            update_url,
            {"work_email": "new.address@sheriacentric.com"},
        )

        self.assertRedirects(
            response,
            self.channel_url("email-communications"),
            fetch_redirect_response=False,
        )
        self.colleague.refresh_from_db()
        self.assertEqual(
            self.colleague.work_email, "new.address@sheriacentric.com"
        )
        self.assertEqual(self.colleague.work_email_password_encrypted, "")

    def test_work_email_change_rejects_an_address_used_by_another_employee(self):
        update_url = (
            self.channel_url("email-communications", str(self.colleague.pk))
            + "work-email/"
        )

        response = self.http.post(
            update_url,
            {"work_email": self.user.work_email.upper()},
            follow=True,
        )

        self.assertContains(
            response,
            "That work email is already assigned to another employee.",
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
            self.channel_url("email-communications", str(self.colleague.pk))
            + "work-email/"
        )

        with (
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
                {"action": "generate"},
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
        self.assertContains(log, "Employee")

        detail = self.http.get(f"{log_url}{record.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Attached is the weekly matter report.")
        self.assertContains(detail, self.colleague.work_email)

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

    def test_unknown_channel_is_not_found(self):
        response = self.http.get(
            self.channel_url("fax-communications", str(self.colleague.pk))
        )
        self.assertEqual(response.status_code, 404)


class MessageLoggingTests(TestCase):
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
