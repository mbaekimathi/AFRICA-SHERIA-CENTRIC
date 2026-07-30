import shutil
import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from accounts.digital_stamp import stamp_postal_line, stamp_render_context
from accounts.models import (
    CompanyDigitalStampSetting,
    Employee,
    EmployeeDigitalStampSetting,
    FirmCompanyInformation,
)


def stamp_upload(name="my-stamp.png"):
    """A small blue mark on white paper, like a cropped stamp scan."""
    image = Image.new("RGB", (120, 70), "white")
    for x in range(20, 100):
        for y in range(25, 45):
            image.putpixel((x, y), (26, 34, 224))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class DigitalStampDesignerTests(TestCase):
    def setUp(self):
        self.user = Employee.objects.create_user(
            login_code="666666",
            password="test-pass-123",
            first_name="Stamp",
            last_name="Partner",
            personal_email="stamp.partner@example.com",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.user)
        self.url = self.user.workspace_url(
            "dashboard",
            "system-settings",
            "document-settings",
            "digital-stamp",
        )
        self.firm = FirmCompanyInformation.get_solo()
        self.firm.postal_address = "P. O. Box 7728 - 00100"
        self.firm.city = "Nairobi"
        self.firm.save()

    def test_designer_offers_the_advocate_block_and_ink_accent(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "stamp-sample-card--advocate")
        self.assertContains(response, "Advocate block")
        self.assertContains(response, "Stamp ink blue")

    def test_saving_the_advocate_block_renders_the_postal_line(self):
        response = self.client.post(
            self.url,
            {
                "template": "advocate",
                "accent": "ink",
                "show_firm_name": "on",
                "show_status": "on",
                "show_approver": "on",
                "show_date": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        setting = CompanyDigitalStampSetting.get_solo()
        self.assertEqual(setting.template, "advocate")
        self.assertEqual(setting.accent, "ink")
        self.assertContains(response, "doc-stamp--advocate")
        self.assertContains(response, "doc-stamp--accent-ink")
        self.assertContains(response, "P. O. Box 7728 - 00100, Nairobi")
        self.assertContains(response, "--stamp-ink: #1a22e0")

    def test_postal_line_does_not_repeat_the_city(self):
        self.firm.postal_address = "P. O. Box 90, Nairobi"
        self.firm.save()
        self.assertEqual(
            stamp_postal_line(self.firm), "P. O. Box 90, Nairobi"
        )

    def test_render_context_falls_back_to_letterhead_accents(self):
        setting = CompanyDigitalStampSetting.get_solo()
        setting.accent = CompanyDigitalStampSetting.Accent.FOREST
        ctx = stamp_render_context(setting=setting)
        self.assertEqual(ctx["stamp_accent_hex"], "#0f6e56")

    def test_designer_shows_the_upload_section(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Add your own stamp")
        self.assertContains(response, 'id="stamp-upload"')
        self.assertContains(response, "enctype=\"multipart/form-data\"")


class StampUploadTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp(prefix="stamp-test-media-")
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
            login_code="777777",
            password="test-pass-123",
            first_name="Scan",
            last_name="Advocate",
            personal_email="scan.advocate@example.com",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.user)
        self.company_url = self.user.workspace_url(
            "dashboard",
            "system-settings",
            "document-settings",
            "digital-stamp",
        )
        self.personal_url = self.user.workspace_url(
            "dashboard", "my-tools", "my-digital-stamp"
        )
        self.payload = {
            "template": "classic",
            "accent": "ink",
            "show_firm_name": "on",
            "show_status": "on",
            "show_approver": "on",
            "show_date": "on",
        }

    def test_uploading_a_company_stamp_replaces_the_designed_stamp(self):
        response = self.client.post(
            self.company_url,
            {**self.payload, "stamp_image": stamp_upload()},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        setting = CompanyDigitalStampSetting.get_solo()
        self.assertTrue(setting.has_scan)
        # Documents render the scan, not the generated frame.
        self.assertContains(response, "doc-stamp--scan")
        self.assertContains(response, setting.stamp_image.url)
        self.assertNotContains(response, "doc-stamp__ring")

    def test_clearing_the_upload_restores_the_designed_stamp(self):
        self.client.post(
            self.company_url,
            {**self.payload, "stamp_image": stamp_upload()},
            follow=True,
        )
        response = self.client.post(
            self.company_url,
            {**self.payload, "clear_stamp_image": "on"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CompanyDigitalStampSetting.get_solo().has_scan)
        self.assertContains(response, "doc-stamp__ring")
        self.assertNotContains(response, "doc-stamp--scan")

    def test_personal_stamp_accepts_an_upload(self):
        response = self.client.post(
            self.personal_url,
            {**self.payload, "stamp_image": stamp_upload("mine.png")},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        setting = EmployeeDigitalStampSetting.objects.get(employee=self.user)
        self.assertTrue(setting.has_scan)
        self.assertContains(response, "doc-stamp--scan")

    def test_oversized_upload_is_rejected(self):
        oversized = SimpleUploadedFile(
            "huge.png", b"0" * (5 * 1024 * 1024 + 1), content_type="image/png"
        )
        response = self.client.post(
            self.company_url,
            {**self.payload, "stamp_image": oversized},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CompanyDigitalStampSetting.get_solo().has_scan)


class MyDigitalStampOverrideTests(TestCase):
    def setUp(self):
        self.user = Employee.objects.create_user(
            login_code="555551",
            password="test-pass-123",
            first_name="Personal",
            last_name="Stamp",
            personal_email="personal.stamp@example.com",
            role=Employee.Role.ADVOCATE,
            status=Employee.Status.ACTIVE,
        )
        self.other = Employee.objects.create_user(
            login_code="555552",
            password="test-pass-123",
            first_name="Company",
            last_name="Stamp",
            personal_email="company.stamp@example.com",
            role=Employee.Role.ADVOCATE,
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.user)
        self.url = self.user.workspace_url(
            "dashboard", "my-tools", "my-digital-stamp"
        )
        self.company = CompanyDigitalStampSetting.get_solo()
        self.company.template = CompanyDigitalStampSetting.Template.SQUARE
        self.company.save()
        self.payload = {
            "template": "oval",
            "accent": "teal",
            "show_firm_name": "on",
            "show_status": "on",
            "show_approver": "on",
            "show_date": "on",
        }

    def test_opening_the_page_does_not_activate_an_override(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "currently carry the firm default stamp")
        self.assertFalse(
            EmployeeDigitalStampSetting.objects.filter(employee=self.user).exists()
        )

    def test_saving_creates_an_override_without_changing_the_company(self):
        response = self.client.post(self.url, self.payload, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "overrides the firm default")
        self.assertContains(response, "Use the firm default instead")
        personal = EmployeeDigitalStampSetting.objects.get(employee=self.user)
        self.assertEqual(personal.template, EmployeeDigitalStampSetting.Template.OVAL)
        self.company.refresh_from_db()
        self.assertEqual(
            self.company.template, CompanyDigitalStampSetting.Template.SQUARE
        )

    def test_rendering_uses_only_the_signers_personal_stamp(self):
        self.client.post(self.url, self.payload)
        mine = stamp_render_context(signer=self.user)["digital_stamp"]
        company = stamp_render_context(signer=self.other)["digital_stamp"]
        self.assertIsInstance(mine, EmployeeDigitalStampSetting)
        self.assertEqual(mine.employee, self.user)
        self.assertIsInstance(company, CompanyDigitalStampSetting)

    def test_reverting_restores_the_company_stamp(self):
        self.client.post(self.url, self.payload)
        response = self.client.post(
            self.url, {"use_company_stamp": "1"}, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            EmployeeDigitalStampSetting.objects.filter(employee=self.user).exists()
        )
        self.assertContains(response, "firm default stamp again")
