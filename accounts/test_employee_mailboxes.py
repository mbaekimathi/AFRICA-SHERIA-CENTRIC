from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.urls import reverse

from accounts.models import (
    CommunicationSettings,
    Employee,
    EmployeeActivityPermission,
    EmployeeMailbox,
)
from accounts.views import UpdateEmployeeWorkEmailView
from accounts.work_email_notify import make_set_password_token
from accounts.work_mailbox import WorkMailbox, WorkMailboxError


def _provisioned_setting():
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
    return setting


class EmployeeMailboxModelTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create_user(
            login_code="404040",
            password="test-pass-123",
            first_name="Multi",
            last_name="Box",
            personal_email="multi.box@example.com",
            role=Employee.Role.EMPLOYEE,
            status=Employee.Status.ACTIVE,
            work_email="multi.box@sheriacentric.com",
        )

    def test_mailbox_rows_lists_primary_then_extras(self):
        self.employee.set_work_mailbox_password("pw-primary")
        extra = EmployeeMailbox.objects.create(
            employee=self.employee, email="dept@sheriacentric.com"
        )
        extra.set_mailbox_password("pw-extra")

        rows = self.employee.mailbox_rows()
        self.assertEqual(
            [(row["key"], row["email"]) for row in rows],
            [("", "multi.box@sheriacentric.com"), (str(extra.pk), "dept@sheriacentric.com")],
        )
        self.assertTrue(rows[0]["connected"])
        self.assertTrue(rows[1]["connected"])
        self.assertTrue(rows[0]["is_primary"])
        self.assertFalse(rows[1]["is_primary"])

    def test_linked_mailbox_for_only_returns_own_rows(self):
        own = EmployeeMailbox.objects.create(
            employee=self.employee, email="own@sheriacentric.com"
        )
        other = Employee.objects.create_user(
            login_code="404041",
            password="test-pass-123",
            first_name="Other",
            last_name="Person",
            role=Employee.Role.EMPLOYEE,
            status=Employee.Status.ACTIVE,
        )
        foreign = EmployeeMailbox.objects.create(
            employee=other, email="foreign@sheriacentric.com"
        )

        self.assertEqual(self.employee.linked_mailbox_for(str(own.pk)), own)
        self.assertIsNone(self.employee.linked_mailbox_for(str(foreign.pk)))
        self.assertIsNone(self.employee.linked_mailbox_for(""))
        self.assertIsNone(self.employee.linked_mailbox_for("not-a-number"))

    def test_password_round_trip_stays_encrypted(self):
        extra = EmployeeMailbox.objects.create(
            employee=self.employee, email="vault@sheriacentric.com"
        )
        self.assertFalse(extra.mailbox_connected)
        extra.set_mailbox_password("secret-pw")
        extra.refresh_from_db()
        self.assertNotEqual(extra.mailbox_password_encrypted, "secret-pw")
        self.assertEqual(extra.get_mailbox_password(), "secret-pw")
        self.assertTrue(extra.mailbox_connected)
        extra.clear_mailbox_password()
        self.assertFalse(extra.mailbox_connected)

    def test_email_must_be_unique(self):
        EmployeeMailbox.objects.create(
            employee=self.employee, email="dupe@sheriacentric.com"
        )
        with self.assertRaises(Exception):
            EmployeeMailbox.objects.create(
                employee=self.employee, email="dupe@sheriacentric.com"
            )


class WorkMailboxSelectionTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create_user(
            login_code="414141",
            password="test-pass-123",
            first_name="Pick",
            last_name="Box",
            role=Employee.Role.EMPLOYEE,
            status=Employee.Status.ACTIVE,
            work_email="pick.box@sheriacentric.com",
        )
        self.extra = EmployeeMailbox.objects.create(
            employee=self.employee, email="shared@sheriacentric.com"
        )

    def test_init_uses_the_linked_address_and_password(self):
        self.extra.set_mailbox_password("extra-pw")
        mailbox = WorkMailbox(self.employee, mailbox=self.extra)
        self.assertEqual(mailbox.address, "shared@sheriacentric.com")
        self.assertEqual(mailbox.password, "extra-pw")
        self.assertEqual(mailbox.host, "mail.sheriacentric.com")

    def test_init_defaults_to_the_primary_address(self):
        self.employee.set_work_mailbox_password("primary-pw")
        mailbox = WorkMailbox(self.employee)
        self.assertEqual(mailbox.address, "pick.box@sheriacentric.com")
        self.assertEqual(mailbox.password, "primary-pw")

    def test_linked_mailbox_without_password_requires_connect(self):
        with self.assertRaises(WorkMailboxError):
            WorkMailbox(self.employee, mailbox=self.extra)

    @patch("accounts.work_mailbox.imaplib.IMAP4_SSL")
    def test_connect_mailbox_stores_on_the_linked_record(self, imap_cls):
        client = MagicMock()
        imap_cls.return_value.__enter__.return_value = client

        from accounts.work_mailbox import connect_mailbox

        connect_mailbox(self.employee, "imap-pw", mailbox=self.extra)

        client.login.assert_called_once_with(
            "shared@sheriacentric.com", "imap-pw"
        )
        self.extra.refresh_from_db()
        self.employee.refresh_from_db()
        self.assertEqual(self.extra.get_mailbox_password(), "imap-pw")
        self.assertEqual(self.employee.work_email_password_encrypted, "")


class ExtraMailboxSettingsTests(TestCase):
    def setUp(self):
        self.manager = Employee.objects.create_user(
            login_code="424242",
            password="test-pass-123",
            first_name="Mail",
            last_name="Manager",
            personal_email="mail.manager@example.com",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
        )
        self.employee = Employee.objects.create_user(
            login_code="434343",
            password="test-pass-123",
            first_name="Link",
            last_name="Me",
            personal_email="link.me@example.com",
            role=Employee.Role.EMPLOYEE,
            status=Employee.Status.ACTIVE,
            work_email="link.me@sheriacentric.com",
        )
        _provisioned_setting()
        self.client.force_login(self.manager)
        self.url = reverse(
            "accounts:update_employee_work_email",
            kwargs={
                "role": self.manager.role_slug,
                "employee_id": self.employee.pk,
            },
        )

    def _post(self, **data):
        data.setdefault("return_to", "email-settings")
        return self.client.post(self.url, data)

    @patch("accounts.work_email_notify.notify_work_email_created")
    @patch("accounts.views.create_mailbox")
    @patch("accounts.views.list_mailboxes", return_value=set())
    def test_add_extra_creates_and_links_a_mailbox(
        self, _list, create_fn, notify_fn
    ):
        notify_fn.return_value = {
            "email_sent": True,
            "personal_email": "link.me@example.com",
        }

        response = self._post(
            action="add_extra", extra_email="dept@sheriacentric.com"
        )

        self.assertEqual(response.status_code, 302)
        extra = EmployeeMailbox.objects.get(employee=self.employee)
        self.assertEqual(extra.email, "dept@sheriacentric.com")
        self.assertEqual(extra.created_by, self.manager)
        create_fn.assert_called_once()
        self.assertEqual(create_fn.call_args.args[1], "dept@sheriacentric.com")
        notify_fn.assert_called_once()
        self.assertEqual(
            notify_fn.call_args.kwargs["work_email"], "dept@sheriacentric.com"
        )

    @patch("accounts.work_email_notify.notify_work_email_created")
    @patch("accounts.views.adopt_existing_mailbox")
    @patch(
        "accounts.views.list_mailboxes",
        return_value={"orphan@sheriacentric.com"},
    )
    def test_add_extra_adopts_an_existing_cpanel_mailbox(
        self, _list, adopt_fn, notify_fn
    ):
        adopt_fn.return_value = ("orphan@sheriacentric.com", "rotated-pw")
        notify_fn.return_value = {
            "email_sent": True,
            "personal_email": "link.me@example.com",
        }

        self._post(action="add_extra", extra_email="orphan@sheriacentric.com")

        adopt_fn.assert_called_once()
        self.assertTrue(
            EmployeeMailbox.objects.filter(
                employee=self.employee, email="orphan@sheriacentric.com"
            ).exists()
        )
        self.assertTrue(notify_fn.call_args.kwargs["reused"])

    @patch("accounts.views.list_mailboxes", return_value=set())
    def test_add_extra_rejects_a_primary_address(self, _list):
        self._post(action="add_extra", extra_email=self.employee.work_email)
        self.assertFalse(
            EmployeeMailbox.objects.filter(employee=self.employee).exists()
        )

    @patch("accounts.views.list_mailboxes", return_value=set())
    def test_add_extra_rejects_a_duplicate_linked_address(self, _list):
        EmployeeMailbox.objects.create(
            employee=self.employee, email="taken@sheriacentric.com"
        )
        self._post(action="add_extra", extra_email="taken@sheriacentric.com")
        self.assertEqual(
            EmployeeMailbox.objects.filter(
                email="taken@sheriacentric.com"
            ).count(),
            1,
        )

    @patch("accounts.views.list_mailboxes", return_value=set())
    def test_add_extra_rejects_other_domains(self, _list):
        self._post(action="add_extra", extra_email="dept@outside.example")
        self.assertFalse(
            EmployeeMailbox.objects.filter(employee=self.employee).exists()
        )

    @patch("accounts.views.list_mailboxes", return_value=set())
    def test_add_extra_accepts_local_part_with_domain_default(self, _list):
        with (
            patch("accounts.views.create_mailbox"),
            patch(
                "accounts.work_email_notify.notify_work_email_created",
                return_value={"email_sent": False, "email_error": "no smtp"},
            ),
        ):
            self._post(action="add_extra", extra_email="partial")
        self.assertTrue(
            EmployeeMailbox.objects.filter(
                employee=self.employee, email="partial@sheriacentric.com"
            ).exists()
        )

    def test_remove_extra_unlinks_the_record(self):
        extra = EmployeeMailbox.objects.create(
            employee=self.employee, email="gone@sheriacentric.com"
        )
        response = self._post(action="remove_extra", mailbox_id=str(extra.pk))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            EmployeeMailbox.objects.filter(pk=extra.pk).exists()
        )

    @patch("accounts.work_email_notify.notify_work_email_reset_link")
    def test_reset_extra_password_emails_the_link(self, notify_fn):
        extra = EmployeeMailbox.objects.create(
            employee=self.employee, email="reset@sheriacentric.com"
        )
        notify_fn.return_value = {
            "email_sent": True,
            "personal_email": "link.me@example.com",
        }

        self._post(action="reset_extra_password", mailbox_id=str(extra.pk))

        notify_fn.assert_called_once()
        self.assertEqual(
            notify_fn.call_args.kwargs["work_email"], "reset@sheriacentric.com"
        )

    def test_primary_update_rejects_an_address_linked_as_extra(self):
        EmployeeMailbox.objects.create(
            employee=self.employee, email="linked@sheriacentric.com"
        )
        self._post(action="update", work_email="linked@sheriacentric.com")
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.work_email, "link.me@sheriacentric.com")

    def test_reserved_work_emails_include_linked_addresses(self):
        EmployeeMailbox.objects.create(
            employee=self.employee, email="held@sheriacentric.com"
        )
        reserved = UpdateEmployeeWorkEmailView._reserved_work_emails(
            exclude_employee_id=self.employee.pk
        )
        self.assertIn("held@sheriacentric.com", reserved)
        self.assertNotIn(self.employee.work_email, reserved)

    def _deny_edit(self, *activities):
        for activity in activities:
            EmployeeActivityPermission.objects.create(
                employee=self.manager,
                module_slug="user-management",
                activity_slug=activity,
                action="edit",
                is_allowed=False,
            )

    @patch("accounts.views.list_mailboxes", return_value=set())
    def test_email_settings_edit_permission_allows_add(self, _list):
        self._deny_edit("employee-management")
        with (
            patch("accounts.views.create_mailbox"),
            patch(
                "accounts.work_email_notify.notify_work_email_created",
                return_value={"email_sent": True, "personal_email": "x@y.z"},
            ),
        ):
            self._post(action="add_extra", extra_email="perm@sheriacentric.com")
        self.assertTrue(
            EmployeeMailbox.objects.filter(
                email="perm@sheriacentric.com"
            ).exists()
        )

    @patch("accounts.views.list_mailboxes", return_value=set())
    def test_no_edit_permission_blocks_add(self, _list):
        self._deny_edit("employee-management", "email-settings")
        self._post(action="add_extra", extra_email="blocked@sheriacentric.com")
        self.assertFalse(
            EmployeeMailbox.objects.filter(
                email="blocked@sheriacentric.com"
            ).exists()
        )


class MessagesLinkedMailboxTests(TestCase):
    def setUp(self):
        self.user = Employee.objects.create_user(
            login_code="454545",
            password="test-pass-123",
            first_name="Split",
            last_name="Inbox",
            personal_email="split.inbox@example.com",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
            work_email="split.inbox@sheriacentric.com",
        )
        self.extra = EmployeeMailbox.objects.create(
            employee=self.user, email="department@sheriacentric.com"
        )
        self.client.force_login(self.user)
        self.url = self.user.workspace_url("dashboard", "messages")

    @patch("accounts.mail_client.WorkMailbox")
    def test_mailbox_param_selects_the_linked_inbox(self, mailbox_cls):
        self.extra.set_mailbox_password("extra-pw")
        mailbox = MagicMock()
        mailbox.folder_overview.return_value = {
            "messages": [],
            "unread": {},
        }
        mailbox_cls.return_value = mailbox

        response = self.client.get(
            f"{self.url}?channel=email&mailbox={self.extra.pk}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            mailbox_cls.call_args.kwargs["mailbox"].pk, self.extra.pk
        )
        self.assertContains(response, "department@sheriacentric.com")

    @patch("accounts.mail_client.WorkMailbox")
    def test_no_param_uses_the_primary_inbox(self, mailbox_cls):
        self.user.set_work_mailbox_password("primary-pw")
        mailbox = MagicMock()
        mailbox.folder_overview.return_value = {
            "messages": [],
            "unread": {},
        }
        mailbox_cls.return_value = mailbox

        self.client.get(f"{self.url}?channel=email")

        self.assertIsNone(mailbox_cls.call_args.kwargs["mailbox"])

    @patch("accounts.mail_client.WorkMailbox")
    def test_foreign_mailbox_param_falls_back_to_primary(self, mailbox_cls):
        self.user.set_work_mailbox_password("primary-pw")
        other = Employee.objects.create_user(
            login_code="464646",
            password="test-pass-123",
            first_name="Not",
            last_name="Yours",
            role=Employee.Role.EMPLOYEE,
            status=Employee.Status.ACTIVE,
        )
        foreign = EmployeeMailbox.objects.create(
            employee=other, email="foreign@sheriacentric.com"
        )
        mailbox = MagicMock()
        mailbox.folder_overview.return_value = {
            "messages": [],
            "unread": {},
        }
        mailbox_cls.return_value = mailbox

        self.client.get(f"{self.url}?channel=email&mailbox={foreign.pk}")

        self.assertIsNone(mailbox_cls.call_args.kwargs["mailbox"])

    @patch("accounts.work_mailbox.connect_mailbox")
    def test_connect_mailbox_passes_the_linked_record(self, connect_fn):
        self.client.post(
            self.url,
            {
                "action": "connect_mailbox",
                "mailbox_password": "extra-pw",
                "mailbox": str(self.extra.pk),
            },
        )
        connect_fn.assert_called_once()
        self.assertEqual(
            connect_fn.call_args.kwargs["mailbox"].pk, self.extra.pk
        )

    def test_disconnect_clears_only_the_linked_credential(self):
        self.user.set_work_mailbox_password("primary-pw")
        self.extra.set_mailbox_password("extra-pw")

        self.client.post(
            self.url,
            {
                "action": "disconnect_mailbox",
                "mailbox": str(self.extra.pk),
            },
        )

        self.user.refresh_from_db()
        self.extra.refresh_from_db()
        self.assertEqual(self.extra.mailbox_password_encrypted, "")
        self.assertNotEqual(self.user.work_email_password_encrypted, "")

    @patch("accounts.work_mailbox.WorkMailbox")
    def test_send_uses_the_selected_mailbox(self, mailbox_cls):
        self.extra.set_mailbox_password("extra-pw")
        mailbox = MagicMock()
        mailbox.address = "department@sheriacentric.com"
        mailbox_cls.return_value = mailbox

        response = self.client.post(
            self.url,
            {
                "action": "send_email",
                "to": "client@example.com",
                "subject": "Hello",
                "body": "From the shared inbox.",
                "mailbox": str(self.extra.pk),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(f"mailbox={self.extra.pk}", response["Location"])
        self.assertEqual(
            mailbox_cls.call_args.kwargs["mailbox"].pk, self.extra.pk
        )
        mailbox.send_message.assert_called_once()

    @patch("accounts.mail_client.WorkMailbox")
    def test_no_primary_defaults_to_first_linked_mailbox(self, mailbox_cls):
        self.user.work_email = None
        self.user.save(update_fields=["work_email"])
        self.extra.set_mailbox_password("extra-pw")
        mailbox = MagicMock()
        mailbox.folder_overview.return_value = {
            "messages": [],
            "unread": {},
        }
        mailbox_cls.return_value = mailbox

        self.client.get(f"{self.url}?channel=email")

        self.assertEqual(
            mailbox_cls.call_args.kwargs["mailbox"].pk, self.extra.pk
        )


class LinkedMailboxSetPasswordTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create_user(
            login_code="474747",
            password="test-pass-123",
            first_name="Reset",
            last_name="Linked",
            personal_email="reset.linked@example.com",
            role=Employee.Role.EMPLOYEE,
            status=Employee.Status.ACTIVE,
        )
        self.extra = EmployeeMailbox.objects.create(
            employee=self.employee, email="team@sheriacentric.com"
        )
        _provisioned_setting()
        self.url = reverse(
            "accounts:set_work_email_password",
            kwargs={
                "token": make_set_password_token(
                    employee_id=self.employee.pk,
                    work_email=self.extra.email,
                )
            },
        )

    def test_get_shows_the_linked_address(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "team@sheriacentric.com")

    @patch("accounts.views.change_mailbox_password")
    def test_post_stores_the_password_on_the_linked_record(self, change_fn):
        response = self.client.post(
            self.url,
            {"password1": "NewPass99", "password2": "NewPass99"},
        )

        self.assertEqual(response.status_code, 200)
        change_fn.assert_called_once()
        self.assertEqual(change_fn.call_args.args[1], "team@sheriacentric.com")
        self.extra.refresh_from_db()
        self.employee.refresh_from_db()
        self.assertTrue(self.extra.mailbox_connected)
        self.assertEqual(self.employee.work_email_password_encrypted, "")

    def test_token_for_a_removed_mailbox_is_rejected(self):
        self.extra.delete()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 400)


class SuspensionLinkedMailboxTests(TestCase):
    def setUp(self):
        self.manager = Employee.objects.create_user(
            login_code="484848",
            password="test-pass-123",
            first_name="Suspend",
            last_name="Boss",
            personal_email="suspend.boss@example.com",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
        )
        self.employee = Employee.objects.create_user(
            login_code="494949",
            password="test-pass-123",
            first_name="Two",
            last_name="Boxes",
            personal_email="two.boxes@example.com",
            role=Employee.Role.EMPLOYEE,
            status=Employee.Status.ACTIVE,
            work_email="two.boxes@sheriacentric.com",
        )
        self.employee.set_work_mailbox_password("primary-pw")
        self.extra = EmployeeMailbox.objects.create(
            employee=self.employee, email="side@sheriacentric.com"
        )
        self.extra.set_mailbox_password("extra-pw")
        _provisioned_setting()
        self.client.force_login(self.manager)
        self.url = reverse(
            "accounts:toggle_employee_suspension",
            kwargs={
                "role": self.manager.role_slug,
                "employee_id": self.employee.pk,
            },
        )

    @patch("accounts.work_email_notify.send_firm_email", return_value="x@y.z")
    @patch("accounts.views.suspend_mailbox")
    def test_suspend_locks_every_linked_mailbox(self, suspend_fn, _mail):
        self.client.post(self.url)

        addresses = {call.args[1] for call in suspend_fn.call_args_list}
        self.assertEqual(
            addresses,
            {"two.boxes@sheriacentric.com", "side@sheriacentric.com"},
        )
        self.employee.refresh_from_db()
        self.extra.refresh_from_db()
        self.assertEqual(self.employee.work_email_password_encrypted, "")
        self.assertEqual(self.extra.mailbox_password_encrypted, "")

    @patch("accounts.work_email_notify.send_firm_email", return_value="x@y.z")
    @patch("accounts.views.unsuspend_mailbox")
    def test_restore_unlocks_every_linked_mailbox(self, unsuspend_fn, _mail):
        self.employee.status = Employee.Status.SUSPENDED
        self.employee.save(update_fields=["status"])

        self.client.post(self.url)

        addresses = {call.args[1] for call in unsuspend_fn.call_args_list}
        self.assertEqual(
            addresses,
            {"two.boxes@sheriacentric.com", "side@sheriacentric.com"},
        )
