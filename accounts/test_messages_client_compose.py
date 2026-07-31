from unittest.mock import MagicMock, patch

from django.test import TestCase

from accounts.models import (
    Client,
    CommunicationSettings,
    Employee,
    EmployeeCommunication,
)
from accounts.work_mailbox import MailDetail, MailSummary, WorkMailboxError


class MessagesClientComposeTests(TestCase):
    def setUp(self):
        self.user = Employee.objects.create_user(
            login_code="919191",
            password="test-pass-123",
            first_name="Jane",
            last_name="Advocate",
            personal_email="jane.advocate@example.com",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
            work_email="jane.advocate@sheriacentric.com",
            work_phone="+254712345678",
        )
        self.client_user = Client.objects.create(
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
        setting.sms_enabled = True
        setting.sms_provider = CommunicationSettings.SmsProvider.TWILIO
        setting.sms_username = "ACxxxx"
        setting.sms_api_secret = "twilio-token"
        setting.sms_sender_id = "+254700000000"
        setting.save()

    def test_email_channel_prompts_mailbox_connect(self):
        response = self.http.get(f"{self.url}?channel=email")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "jane.advocate@sheriacentric.com")
        self.assertContains(response, 'name="action" value="connect_mailbox"')
        self.assertContains(response, "Connect mailbox")
        self.assertNotContains(response, "email-recipient-picker")

    @patch("accounts.work_mailbox.connect_mailbox")
    def test_connect_mailbox_redirects(self, connect_fn):
        response = self.http.post(
            self.url,
            {
                "action": "connect_mailbox",
                "mailbox_password": "mailbox-secret",
            },
        )
        self.assertEqual(response.status_code, 302)
        connect_fn.assert_called_once()

    def test_send_email_requires_connected_mailbox(self):
        response = self.http.post(
            self.url,
            {
                "action": "send_email",
                "to": "guest.counsel@example.org",
                "subject": "Intro",
                "body": "Please find attached.",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Connect your mailbox password")

    @patch("accounts.work_mailbox.WorkMailbox")
    def test_send_email_uses_work_mailbox(self, mailbox_cls):
        self.user.set_work_mailbox_password("mailbox-secret")
        mailbox = MagicMock()
        mailbox_cls.return_value = mailbox

        response = self.http.post(
            self.url,
            {
                "action": "send_email",
                "to": "guest.counsel@example.org",
                "cc": "cc@example.com",
                "subject": "Intro",
                "body": "Please find attached.",
            },
        )
        self.assertEqual(response.status_code, 302)
        mailbox.send_message.assert_called_once()
        kwargs = mailbox.send_message.call_args.kwargs
        self.assertEqual(kwargs["to_addrs"], ["guest.counsel@example.org"])
        self.assertEqual(kwargs["cc_addrs"], ["cc@example.com"])
        self.assertEqual(kwargs["subject"], "Intro")
        self.assertTrue(
            EmployeeCommunication.objects.filter(
                sender=self.user,
                to_address="guest.counsel@example.org",
            ).exists()
        )

    def test_send_email_rejects_when_work_email_missing(self):
        self.user.work_email = None
        self.user.clear_work_mailbox_password()
        self.user.save(update_fields=["work_email", "work_email_password_encrypted"])
        response = self.http.post(
            self.url,
            {
                "action": "send_email",
                "to": "client@example.com",
                "subject": "Hello",
                "body": "Body",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "work email")

    @patch("accounts.work_mailbox.WorkMailbox")
    def test_send_email_failure_stays_on_page(self, mailbox_cls):
        self.user.set_work_mailbox_password("mailbox-secret")
        mailbox = MagicMock()
        mailbox.send_message.side_effect = WorkMailboxError("SMTP rejected login.")
        mailbox_cls.return_value = mailbox

        response = self.http.post(
            self.url,
            {
                "action": "send_email",
                "to": "client@example.com",
                "subject": "Case update",
                "body": "Please call the office.",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SMTP rejected login.")

    @patch("accounts.mail_client.WorkMailbox")
    def test_connected_mailbox_shows_folders_and_messages(self, mailbox_cls):
        self.user.set_work_mailbox_password("mailbox-secret")
        mailbox = MagicMock()
        summary = MailSummary(
            uid="42",
            subject="Hearing date",
            from_addr="Nairobi Court <court@example.com>",
            to_addrs="jane.advocate@sheriacentric.com",
            date_display="30 Jul 2026, 10:00",
            snippet="Your matter is listed…",
            is_unread=True,
            has_attachments=False,
        )
        mailbox.list_messages.return_value = [summary]
        mailbox.folder_overview.return_value = {
            "messages": [summary],
            "unread": {"inbox": 1},
        }
        mailbox.get_message.return_value = MailDetail(
            uid="42",
            subject="Hearing date",
            from_addr="court@example.com",
            to_addrs="jane.advocate@sheriacentric.com",
            cc_addrs="",
            date_display="30 Jul 2026, 10:00",
            body_text="Your matter is listed for Monday.",
            is_unread=True,
        )
        mailbox_cls.return_value = mailbox

        response = self.http.get(f"{self.url}?channel=email&folder=inbox&uid=42")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inbox")
        self.assertContains(response, "Hearing date")
        self.assertContains(response, "Your matter is listed for Monday.")
        self.assertContains(response, "Reply")
        self.assertContains(response, "Compose")

    def test_sms_channel_requires_work_phone(self):
        self.user.work_phone = ""
        self.user.save(update_fields=["work_phone"])
        response = self.http.get(f"{self.url}?channel=sms")
        self.assertContains(response, "no work phone")

    def test_inbox_groups_messages_by_colleague(self):
        colleague = Employee.objects.create_user(
            login_code="919192",
            password="test-pass-123",
            first_name="John",
            last_name="Colleague",
            personal_email="john.colleague@example.com",
            role=Employee.Role.INTERN,
            status=Employee.Status.ACTIVE,
            work_email="john.colleague@sheriacentric.com",
        )
        EmployeeCommunication.objects.create(
            sender=colleague,
            channel=EmployeeCommunication.Channel.EMAIL,
            to_employee=self.user,
            to_address=self.user.work_email,
            subject="File update",
            body="I have uploaded the signed file.",
        )

        response = self.http.get(self.url)

        self.assertContains(response, "John Colleague")
        self.assertContains(response, "File update")
        self.assertContains(response, f"?person={colleague.pk}")

    def test_person_inbox_shows_the_full_two_way_conversation(self):
        self.user.set_work_mailbox_password("mailbox-secret")
        colleague = Employee.objects.create_user(
            login_code="919193",
            password="test-pass-123",
            first_name="Mary",
            last_name="Counsel",
            personal_email="mary.counsel@example.com",
            role=Employee.Role.ADVOCATE,
            status=Employee.Status.ACTIVE,
            work_email="mary.counsel@sheriacentric.com",
        )
        EmployeeCommunication.objects.create(
            sender=colleague,
            channel=EmployeeCommunication.Channel.EMAIL,
            to_employee=self.user,
            to_address=self.user.work_email,
            subject="Question",
            body="Have you reviewed the draft?",
        )
        EmployeeCommunication.objects.create(
            sender=self.user,
            channel=EmployeeCommunication.Channel.EMAIL,
            to_employee=colleague,
            to_address=colleague.work_email,
            subject="Re: Question",
            body="Yes, I sent my comments.",
        )

        response = self.http.get(f"{self.url}?person={colleague.pk}")

        self.assertContains(response, "Conversation with Mary Counsel")
        self.assertContains(response, "Have you reviewed the draft?")
        self.assertContains(response, "Yes, I sent my comments.")
        self.assertContains(response, "You")
        self.assertContains(response, "Compose email")
        self.assertContains(response, 'name="to"')
        self.assertContains(response, colleague.work_email)
        self.assertContains(response, f'name="person" value="{colleague.pk}"')
        self.assertNotContains(response, "mailbox__rail")
        self.assertNotContains(response, "Search mail")

    @patch("accounts.work_mailbox.WorkMailbox")
    def test_person_compose_send_returns_to_conversation(self, mailbox_cls):
        self.user.set_work_mailbox_password("mailbox-secret")
        mailbox = MagicMock()
        mailbox_cls.return_value = mailbox
        colleague = Employee.objects.create_user(
            login_code="919194",
            password="test-pass-123",
            first_name="Alex",
            last_name="Clerk",
            personal_email="alex.clerk@example.com",
            role=Employee.Role.INTERN,
            status=Employee.Status.ACTIVE,
            work_email="alex.clerk@sheriacentric.com",
        )
        EmployeeCommunication.objects.create(
            sender=colleague,
            channel=EmployeeCommunication.Channel.EMAIL,
            to_employee=self.user,
            to_address=self.user.work_email,
            subject="Hello",
            body="Checking in.",
        )

        response = self.http.post(
            self.url,
            {
                "action": "send_email",
                "person": str(colleague.pk),
                "to": colleague.work_email,
                "subject": "Re: Hello",
                "body": "All good, thanks.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"person={colleague.pk}", response["Location"])
        mailbox.send_message.assert_called_once()
        self.assertTrue(
            EmployeeCommunication.objects.filter(
                sender=self.user,
                to_employee=colleague,
                subject="Re: Hello",
            ).exists()
        )

    @patch("accounts.outbound_messaging.send_client_sms", return_value="+254712345678")
    def test_send_sms_uses_work_phone_identity(self, send_sms):
        response = self.http.post(
            self.url,
            {
                "action": "send_sms",
                "recipient": f"client:{self.client_user.pk}",
                "body": "Hearing tomorrow at 9am.",
            },
        )
        self.assertEqual(response.status_code, 302)
        kwargs = send_sms.call_args.kwargs
        self.assertEqual(kwargs["employee"], self.user)
        self.assertEqual(kwargs["to_phone"], "+254700111222")
