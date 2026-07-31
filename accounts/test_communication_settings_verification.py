import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from accounts.communication_verification import (
    STATUS_CONNECTED,
    verify_work_email_cpanel,
)
from accounts.forms import CommunicationSettingsForm
from accounts.models import CommunicationSettings, Employee


def healthy_result():
    return {
        "verified_at": "2026-07-30T21:00:00+03:00",
        "overall_status": "connected",
        "overall_tone": "active",
        "overall_label": "Configuration healthy",
        "overall_detail": "All enabled channels verified live (1).",
        "connected_count": 1,
        "problem_count": 0,
        "not_set_count": 0,
        "channel_count": 4,
        "problem_locations": [],
        "connection_channels": [],
        "by_key": {},
        "verification_passed": True,
    }


def unhealthy_result():
    result = healthy_result()
    result.update(
        {
            "overall_status": "issues",
            "overall_tone": "pending",
            "overall_label": "Needs attention",
            "overall_detail": "SMTP authentication failed.",
            "connected_count": 0,
            "problem_count": 1,
            "verification_passed": False,
        }
    )
    return result


class CommunicationSettingsVerificationTests(TestCase):
    def setUp(self):
        self.user = Employee.objects.create_user(
            login_code="818181",
            password="test-pass-123",
            first_name="Managing",
            last_name="Partner",
            personal_email="managing.partner@example.com",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.user)
        self.url = reverse("accounts:communication_settings_verify")
        self.setting = CommunicationSettings.get_solo()
        self.setting.email_host_password = "saved-smtp-password"
        self.setting.cpanel_api_token = "saved-cpanel-token"
        self.setting.save()

    def values(self):
        return {
            "email_enabled": True,
            "email_host": "mail.sheriacentric.com",
            "email_port": "465",
            "email_host_user": "noreply@sheriacentric.com",
            "email_host_password": "",
            "email_from_email": "noreply@sheriacentric.com",
            "email_from_name": "Sheria Centric",
            "work_email_provisioning_enabled": False,
            "cpanel_host": "",
            "cpanel_port": "2083",
            "cpanel_username": "",
            "cpanel_api_token": "",
            "work_email_domain": "",
            "work_email_quota_mb": "1024",
            "sms_enabled": False,
            "sms_provider": "none",
            "sms_username": "",
            "sms_api_key": "",
            "sms_api_secret": "",
            "sms_sender_id": "",
            "whatsapp_enabled": False,
            "whatsapp_business_number": "",
            "whatsapp_default_message": "",
            "whatsapp_api_enabled": False,
            "whatsapp_provider": "none",
            "whatsapp_api_token": "",
            "whatsapp_phone_number_id": "",
            "whatsapp_webhook_url": "",
            "whatsapp_webhook_verify_token": "",
        }

    @patch(
        "accounts.communication_verification.verify_communication_settings",
        return_value=healthy_result(),
    )
    def test_verify_and_save_persists_only_after_success(self, _verify):
        response = self.client.post(
            self.url,
            data=json.dumps({"values": self.values(), "save": True}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["saved"])
        self.setting.refresh_from_db()
        self.assertTrue(self.setting.email_enabled)
        self.assertEqual(self.setting.email_host, "mail.sheriacentric.com")
        self.assertEqual(self.setting.email_port, 465)
        self.assertTrue(self.setting.email_use_ssl)
        self.assertFalse(self.setting.email_use_tls)
        self.assertEqual(self.setting.verified_by, self.user)
        self.assertIsNotNone(self.setting.verified_at)

    @patch(
        "accounts.communication_verification.verify_communication_settings",
        return_value=unhealthy_result(),
    )
    def test_failed_verification_does_not_replace_saved_configuration(self, _verify):
        self.setting.email_host = "old.example.com"
        self.setting.save()

        response = self.client.post(
            self.url,
            data=json.dumps({"values": self.values(), "save": True}),
            content_type="application/json",
        )

        self.assertFalse(response.json()["saved"])
        self.setting.refresh_from_db()
        self.assertEqual(self.setting.email_host, "old.example.com")
        self.assertIsNone(self.setting.verified_at)

    @patch(
        "accounts.communication_verification.verify_communication_settings",
        return_value=healthy_result(),
    )
    def test_blank_secret_inputs_keep_saved_credentials(self, _verify):
        self.client.post(
            self.url,
            data=json.dumps({"values": self.values(), "save": True}),
            content_type="application/json",
        )

        self.setting.refresh_from_db()
        self.assertEqual(
            self.setting.email_host_password, "saved-smtp-password"
        )
        self.assertEqual(self.setting.cpanel_api_token, "saved-cpanel-token")

    @patch(
        "accounts.communication_verification.verify_communication_settings",
        return_value=healthy_result(),
    )
    def test_automatic_check_does_not_write_to_database(self, _verify):
        response = self.client.post(
            self.url,
            data=json.dumps({"values": self.values(), "save": False}),
            content_type="application/json",
        )

        self.assertFalse(response.json()["saved"])
        self.setting.refresh_from_db()
        self.assertFalse(self.setting.email_enabled)
        self.assertIsNone(self.setting.verified_at)

    def test_normal_form_save_also_preserves_blank_secrets(self):
        form = CommunicationSettingsForm(self.values(), instance=self.setting)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.email_host_password, "saved-smtp-password")
        self.assertEqual(saved.cpanel_api_token, "saved-cpanel-token")


class CpanelConnectionVerificationTests(TestCase):
    @patch(
        "accounts.communication_verification.list_mailboxes",
        return_value={"noreply@sheriacentric.com"},
    )
    def test_verification_authenticates_and_lists_mailboxes(self, list_mailboxes):
        result = verify_work_email_cpanel(
            {
                "work_email_provisioning_enabled": True,
                "cpanel_host": "server.example.com",
                "cpanel_port": 2083,
                "cpanel_username": "sheria",
                "cpanel_api_token": "api-token",
                "work_email_domain": "sheriacentric.com",
            }
        )

        self.assertEqual(result.status, STATUS_CONNECTED)
        self.assertIn("authenticated successfully", result.detail)
        list_mailboxes.assert_called_once()
